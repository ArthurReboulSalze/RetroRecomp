"""How an Internet room's host becomes reachable, and which public address it gives in its key (Arthur, 19 November 2026).

In order, and no call to retro-recomp.com when the first two give the address:
  (a) the box, asked on the local network: UPnP IGD (SSDP discovery, the device description, then SOAP: the external
      address, a port mapping for TCP and UDP, removed when the room closes) or, when the box has no UPnP, NAT-PMP
      (RFC 6886: the external address and the two mappings);
  (b) the PC's own global IPv6 address, read from its interfaces (a UDP socket "connected" to a global address: nothing
      is sent, the system only picks the source address it would use);
  (c) only when both fail, the address retro-recomp.com sees (`ECHO_URL`, one HTTPS GET; the window says so first);
  and the address the player types is always taken instead.

What cannot work is said, not guessed: an external address that is private or in 100.64.0.0/10 (shared by the operator,
CGNAT), or that differs from the one seen from outside (two boxes in a row), means nobody can reach this PC from the
Internet ("let the other player host, open the port in your box, or use a VPN between friends").

The parsing is pure and tested on answers written in the shape real boxes give (`tests/test_netplay_reach.py`). The functions that talk
to the box take the socket and the HTTP opener as arguments, so a test never touches a router; nothing here runs before the
player chooses Internet in the room and confirms its warnings.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from http.client import HTTPException
import ipaddress
import socket
import struct
import time
import urllib.request
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

SSDP_ADDRESS = ('239.255.255.250', 1900)
SEARCH_TARGETS = ('urn:schemas-upnp-org:device:InternetGatewayDevice:1', 'urn:schemas-upnp-org:device:InternetGatewayDevice:2')
WAN_SERVICES = ('urn:schemas-upnp-org:service:WANIPConnection:2', 'urn:schemas-upnp-org:service:WANIPConnection:1',
                'urn:schemas-upnp-org:service:WANPPPConnection:1')
NATPMP_PORT = 5351
LEASE_SECONDS = 7200
DESCRIPTION = 'Retro-Recomp room'
ECHO_URL = 'https://retro-recomp.com/api/v1/netplay/ip'
MAX_ANSWER = 64 * 1024                 # a description or a SOAP answer longer than this is not read
SHARED = ipaddress.IPv4Network('100.64.0.0/10')

# ---- what the host found, for the window (`model.reach` of the interface contract) ----

PROBING, UPNP, IPV6, SITE, TYPED, FORWARD_NEEDED, CGNAT, WAITING = (
    'probing', 'upnp', 'ipv6', 'site', 'typed', 'forward_needed', 'cgnat', 'waiting')


@dataclass(frozen=True)
class Reach:
    state: str                         # one of the names above
    ipv4: str | None = None            # the public IPv4 address the key carries
    ipv6: str | None = None            # the global IPv6 address the key carries
    mapped: bool = False               # the box holds our mapping (to remove when the room closes)
    # what `release` needs to remove the mapping; they never take part in a comparison
    via: str = field(default='', compare=False, repr=False)          # 'upnp' or 'natpmp' when mapped
    control: str = field(default='', compare=False, repr=False)      # UPnP: the control URL
    service: str = field(default='', compare=False, repr=False)      # UPnP: the WAN service type
    gateway: str = field(default='', compare=False, repr=False)      # NAT-PMP: the box's address
    port: int = field(default=0, compare=False, repr=False)          # the mapped port (TCP and UDP)


def classify_external(address: str | None, seen_from_outside: str | None = None) -> str:
    """'public', 'cgnat' (shared by the operator, or private behind a second box) or 'unknown'."""
    try:
        ip = ipaddress.IPv4Address(address) if address else None
    except ValueError:
        return 'unknown'
    if ip is None:
        return 'unknown'
    if ip in SHARED or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_unspecified:
        return 'cgnat'
    if seen_from_outside and seen_from_outside != str(ip):
        return 'cgnat'
    return 'public'


# ---- (b) the PC's own global IPv6 address ----

def local_ipv6(socket_module=None) -> str | None:
    """The global IPv6 address this PC would send from, or None. No packet leaves the PC."""
    import socket as default_socket
    module = socket_module or default_socket
    try:
        with module.socket(module.AF_INET6, module.SOCK_DGRAM) as probe:
            probe.connect(('2001:4860:4860::8888', 9))
            address = probe.getsockname()[0].split('%')[0]
    except OSError:
        return None
    try:
        ip = ipaddress.IPv6Address(address)
    except ValueError:
        return None
    return str(ip) if ip.is_global and not ip.ipv4_mapped else None


# ---- (a) UPnP IGD ----

def ssdp_search(target: str) -> bytes:
    return ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\nMX: 2\r\n'
            f'ST: {target}\r\n\r\n').encode('ascii')


def parse_ssdp_answer(data: bytes, source_ip: str) -> str | None:
    """The description URL of an SSDP answer, or None. Only a URL on the answering box itself, over http, is taken: a
    LOCATION that points elsewhere (another machine, the Internet) is never fetched."""
    try:
        text = data[:4096].decode('latin-1')
    except UnicodeDecodeError:
        return None
    if not text.startswith('HTTP/1.1 200'):
        return None
    for line in text.split('\r\n'):
        name, _, value = line.partition(':')
        if name.strip().lower() == 'location':
            url = value.strip()
            parsed = urlparse(url)
            if parsed.scheme == 'http' and parsed.hostname == source_ip and parsed.port:
                return url
            return None
    return None


def _strip(tag: str) -> str:
    return tag.rsplit('}', 1)[-1]


def parse_description(xml: bytes, base_url: str) -> tuple[str, str] | None:
    """(control URL, service type) of the box's WAN connection service, or None. The URL stays on the same box."""
    if len(xml) > MAX_ANSWER or b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        return None
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return None
    base = next((element.text.strip() for element in root.iter() if _strip(element.tag) == 'URLBase' and element.text), base_url)
    found = {}
    for service in root.iter():
        if _strip(service.tag) != 'service':
            continue
        fields = {_strip(child.tag): (child.text or '').strip() for child in service}
        if fields.get('serviceType') in WAN_SERVICES and fields.get('controlURL'):
            found[fields['serviceType']] = fields['controlURL']
    for service_type in WAN_SERVICES:
        if service_type in found:
            url = urljoin(base, found[service_type])
            if urlparse(url).hostname == urlparse(base_url).hostname:
                return url, service_type
            return None
    return None


def soap_body(service_type: str, action: str, arguments: dict) -> bytes:
    inner = ''.join(f'<{name}>{value}</{name}>' for name, value in arguments.items())
    return ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="{service_type}">{inner}</u:{action}></s:Body></s:Envelope>').encode('utf-8')


def add_mapping_arguments(protocol: str, port: int, local_address: str, lease: int = LEASE_SECONDS) -> dict:
    return {'NewRemoteHost': '', 'NewExternalPort': port, 'NewProtocol': protocol, 'NewInternalPort': port,
            'NewInternalClient': local_address, 'NewEnabled': 1, 'NewPortMappingDescription': DESCRIPTION,
            'NewLeaseDuration': lease}


def delete_mapping_arguments(protocol: str, port: int) -> dict:
    return {'NewRemoteHost': '', 'NewExternalPort': port, 'NewProtocol': protocol}


def parse_soap(xml: bytes, wanted: str) -> str | None:
    """The text of the element `wanted` in a SOAP answer, or None (also for a SOAP fault)."""
    if len(xml) > MAX_ANSWER or b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        return None
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return None
    if any(_strip(element.tag) == 'Fault' for element in root.iter()):
        return None
    return next(((element.text or '').strip() for element in root.iter() if _strip(element.tag) == wanted), None)


def soap_ok(xml: bytes, action: str) -> bool:
    """Whether a SOAP answer is the success answer of `action`."""
    if len(xml) > MAX_ANSWER or b'<!DOCTYPE' in xml or b'<!ENTITY' in xml:
        return False
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return False
    tags = [_strip(element.tag) for element in root.iter()]
    return 'Fault' not in tags and f'{action}Response' in tags


# ---- (a) NAT-PMP (RFC 6886) ----

def natpmp_address_request() -> bytes:
    return b'\x00\x00'


def parse_natpmp_address(data: bytes) -> str | None:
    if len(data) != 12 or data[0] != 0 or data[1] != 128:
        return None
    result, = struct.unpack_from('>H', data, 2)
    return str(ipaddress.IPv4Address(data[8:12])) if result == 0 else None


def natpmp_map_request(protocol: str, port: int, lease: int = LEASE_SECONDS) -> bytes:
    opcode = {'UDP': 1, 'TCP': 2}[protocol]
    return struct.pack('>BBHHHI', 0, opcode, 0, port, port, lease)


def parse_natpmp_map(data: bytes, protocol: str, port: int) -> bool:
    """Whether the box mapped `port` to itself on the same external port (another external port is not used: the key
    names one port)."""
    if len(data) != 16 or data[0] != 0 or data[1] != 128 + {'UDP': 1, 'TCP': 2}[protocol]:
        return False
    result, _epoch, internal, external, lease = struct.unpack_from('>HIHHI', data, 2)
    return result == 0 and internal == port and external == port and lease > 0


# ---- (c) the site's echo ----

def parse_echo(body: bytes) -> str | None:
    """The address in the site's answer (`{"ip": "<address>"}`), or None."""
    import json
    if len(body) > 512:
        return None
    try:
        value = json.loads(body.decode('utf-8')).get('ip')
        return str(ipaddress.ip_address(value)) if isinstance(value, str) else None
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None


def gateway_guess(local_address: str) -> str | None:
    """The usual address of the box for NAT-PMP: the .1 of the PC's /24 (a box that is elsewhere answers nothing)."""
    try:
        ip = ipaddress.IPv4Address(local_address)
    except ValueError:
        return None
    return str(ipaddress.IPv4Address(int(ip) & 0xFFFFFF00 | 1)) if ip.is_private else None



# ---- the live layer: the parsers above, used over sockets and HTTP ----
# Every socket factory (`socket_factory()` gives a new UDP socket), HTTP opener (`opener.open(request, timeout=...)`, as
# `make_opener()` builds) and clock is an argument. An error of any kind gives None or False, never an exception.

HTTP_TIMEOUT = 4.0                     # seconds for one HTTP request to the box or to the site
NATPMP_WAITS = (0.25, 0.5, 1.0)        # RFC 6886 doubles from 250 ms; cut here so the whole wait stays under 2 seconds
MAX_DATAGRAMS = 64                     # datagrams read in one wait, so a flood of garbage cannot hold the search
PROTOCOLS = ('TCP', 'UDP')
_PMP_OPCODE = {'UDP': 1, 'TCP': 2}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an error: an answer never sends us to another address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def udp_socket():
    """The socket factory of a real search: one IPv4 UDP socket (SSDP, NAT-PMP)."""
    return socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def search(local_address: str, port: int) -> Reach:
    """`find_public` with the real sockets and opener (what an Internet room's host runs, in a worker thread). The PC's
    IPv6 is not offered yet: the room listens on its IPv4 address only, so a key must carry an IPv4 address."""
    return find_public(local_address, port, socket_factory=udp_socket, opener=make_opener(), ipv6_reader=lambda: None,
                       allow_site=True)


def unmap(found: Reach) -> bool:
    """`release` with the real sockets and opener (when the room closes)."""
    return release(found, socket_factory=udp_socket, opener=make_opener())


def make_opener():
    """The HTTP opener for the functions below: no proxy, no redirect, nothing but plain `open(request, timeout=...)`."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())


def _is_lan_address(text) -> bool:
    """Whether `text` is an IPv4 address of a box on the local network (private, link-local or shared), not the PC itself."""
    try:
        ip = ipaddress.IPv4Address(text)
    except ValueError:
        return False
    return (ip.is_private or ip.is_link_local or ip in SHARED) and not (ip.is_loopback or ip.is_unspecified)


def _lan_host(url) -> str | None:
    """The host of an http URL that names a box on the local network, or None. Nothing else is ever fetched."""
    try:
        parsed = urlparse(url)
        parsed.port                                   # a bad port raises ValueError
    except (ValueError, AttributeError):
        return None
    if parsed.scheme != 'http' or not _is_lan_address(parsed.hostname):
        return None
    return parsed.hostname


def _close(sock) -> None:
    try:
        sock.close()
    except (OSError, AttributeError):
        pass


def _fetch(opener, request: urllib.request.Request, host: str, limit: int, timeout: float) -> bytes | None:
    """The body of one HTTP answer (at most limit + 1 bytes, so that a parser sees an answer that is too long), or None.
    An answer that comes from a host other than `host` (a redirect that was followed anyway) is dropped."""
    try:
        with opener.open(request, timeout=timeout) as response:
            geturl = getattr(response, 'geturl', None)
            if geturl is not None and urlparse(geturl()).hostname != host:
                return None
            status = getattr(response, 'status', None)
            if isinstance(status, int) and not 200 <= status < 300:
                return None
            body = response.read(limit + 1)
    except (OSError, ValueError, HTTPException):
        return None
    return body if isinstance(body, bytes) else None


def upnp_discover(local_address: str, socket_factory, timeout: float, clock=time.monotonic) -> str | None:
    """Search the local network for an Internet gateway: an SSDP M-SEARCH from `local_address` to 239.255.255.250:1900 for
    each of SEARCH_TARGETS, then read answers until `timeout` seconds. Returns the description URL of the first box whose
    answer `parse_ssdp_answer` accepts (and that is on the local network), or None."""
    try:
        ipaddress.IPv4Address(local_address)
        probe = socket_factory()
    except (ValueError, OSError):
        return None
    try:
        try:
            probe.bind((local_address, 0))
            try:                                      # leave by the right network card, a few hops at most
                probe.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
                probe.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_address))
            except OSError:
                pass
            for target in SEARCH_TARGETS:
                probe.sendto(ssdp_search(target), SSDP_ADDRESS)
        except OSError:
            return None
        deadline = clock() + timeout
        for _ in range(MAX_DATAGRAMS):
            remaining = deadline - clock()
            if remaining <= 0:
                break
            try:
                probe.settimeout(remaining)
                data, source = probe.recvfrom(4096)
            except OSError:
                break
            try:
                source_ip = source[0]
            except (TypeError, IndexError):
                continue
            if isinstance(data, bytes) and _is_lan_address(source_ip):
                url = parse_ssdp_answer(data, source_ip)
                if url:
                    return url
        return None
    finally:
        _close(probe)


def upnp_service(url: str, opener, timeout: float = HTTP_TIMEOUT) -> tuple[str, str] | None:
    """Fetch the description at `url` (at most MAX_ANSWER bytes, only from a box on the local network) and return
    (control URL, service type) of its WAN connection service, or None."""
    host = _lan_host(url)
    if host is None:
        return None
    body = _fetch(opener, urllib.request.Request(url, method='GET'), host, MAX_ANSWER, timeout)
    return parse_description(body, url) if body is not None else None


def _soap_call(control: str, service: str, action: str, arguments: dict, opener, timeout: float) -> bytes | None:
    """One SOAP POST to the control URL; the answer's body (read at most MAX_ANSWER + 1 bytes), or None."""
    host = _lan_host(control)
    if host is None or service not in WAN_SERVICES:
        return None
    try:
        request = urllib.request.Request(
            control, data=soap_body(service, action, arguments), method='POST',
            headers={'SOAPAction': f'"{service}#{action}"', 'Content-Type': 'text/xml; charset="utf-8"'})
    except ValueError:
        return None
    return _fetch(opener, request, host, MAX_ANSWER, timeout)


def upnp_external_address(control: str, service: str, opener, timeout: float = HTTP_TIMEOUT) -> str | None:
    """The external IPv4 address the box says it has (GetExternalIPAddress), or None (also for a SOAP fault)."""
    body = _soap_call(control, service, 'GetExternalIPAddress', {}, opener, timeout)
    answer = parse_soap(body, 'NewExternalIPAddress') if body is not None else None
    try:
        return str(ipaddress.IPv4Address(answer)) if answer else None
    except ValueError:
        return None


def _valid_port(port) -> bool:
    return isinstance(port, int) and not isinstance(port, bool) and 0 < port < 65536


def upnp_map(control: str, service: str, opener, port: int, local_address: str, lease: int = LEASE_SECONDS,
             timeout: float = HTTP_TIMEOUT) -> bool:
    """Ask the box to forward `port` to `local_address`, TCP then UDP (AddPortMapping, a lease in seconds). True only when
    both are accepted; when the second is refused, the first is removed again."""
    try:
        ipaddress.IPv4Address(local_address)
    except ValueError:
        return False
    if not _valid_port(port) or not isinstance(lease, int) or lease < 0:
        return False
    done = []
    for protocol in PROTOCOLS:
        body = _soap_call(control, service, 'AddPortMapping', add_mapping_arguments(protocol, port, local_address, lease),
                          opener, timeout)
        if body is None or not soap_ok(body, 'AddPortMapping'):
            for held in done:
                _soap_call(control, service, 'DeletePortMapping', delete_mapping_arguments(held, port), opener, timeout)
            return False
        done.append(protocol)
    return True


def upnp_unmap(control: str, service: str, opener, port: int, timeout: float = HTTP_TIMEOUT) -> bool:
    """Remove the TCP and the UDP mapping of `port` (DeletePortMapping). Both are tried; True when the box accepted both."""
    if not _valid_port(port):
        return False
    removed = True
    for protocol in PROTOCOLS:
        body = _soap_call(control, service, 'DeletePortMapping', delete_mapping_arguments(protocol, port), opener, timeout)
        removed = (body is not None and soap_ok(body, 'DeletePortMapping')) and removed
    return removed


# ---- NAT-PMP over a UDP socket ----

def _natpmp_exchange(gateway: str, socket_factory, request: bytes, opcode: int, timeout: float, clock) -> bytes | None:
    """Send `request` to gateway:5351 and return the first answer from there that is version 0 with this response opcode
    (whatever its result code), or None. RFC 6886 retries at 250 ms, 500 ms and 1 s (cut so that all stay within
    `timeout`); a datagram from anywhere else, or one of another kind, is ignored."""
    if not _is_lan_address(gateway):
        return None
    try:
        sock = socket_factory()
    except OSError:
        return None
    try:
        deadline = clock() + timeout
        for wait in NATPMP_WAITS:
            now = clock()
            if now >= deadline:
                break
            period_end = min(now + wait, deadline)
            try:
                sock.sendto(request, (gateway, NATPMP_PORT))
            except OSError:
                return None
            for _ in range(MAX_DATAGRAMS):
                remaining = period_end - clock()
                if remaining <= 0:
                    break
                try:
                    sock.settimeout(remaining)
                    data, source = sock.recvfrom(64)
                except (TimeoutError, BlockingIOError):
                    break
                except OSError:                       # "connection reset": the box answered that nobody listens on 5351
                    return None
                try:
                    from_gateway = tuple(source[:2]) == (gateway, NATPMP_PORT)
                except TypeError:
                    from_gateway = False
                if from_gateway and isinstance(data, bytes) and len(data) >= 4 and data[0] == 0 and data[1] == opcode:
                    return data
        return None
    finally:
        _close(sock)


def natpmp_external_address(gateway: str, socket_factory, timeout: float = 2.0, clock=time.monotonic) -> str | None:
    """The external IPv4 address a NAT-PMP box reports, or None (no such box, a refusal, no answer in `timeout`)."""
    data = _natpmp_exchange(gateway, socket_factory, natpmp_address_request(), 128, timeout, clock)
    return parse_natpmp_address(data) if data is not None else None


def _natpmp_delete_request(protocol: str, port: int) -> bytes:
    """RFC 6886's way to remove a mapping: lease 0 and an external port of 0."""
    return struct.pack('>BBHHHI', 0, _PMP_OPCODE[protocol], 0, port, 0, 0)


def _natpmp_deleted(data: bytes, protocol: str, port: int) -> bool:
    if len(data) != 16 or data[1] != 128 + _PMP_OPCODE[protocol]:
        return False
    result, _epoch, internal, _external, _lease = struct.unpack_from('>HIHHI', data, 2)
    return result == 0 and internal == port


def _natpmp_remove(gateway: str, socket_factory, protocol: str, port: int, timeout: float, clock) -> bool:
    data = _natpmp_exchange(gateway, socket_factory, _natpmp_delete_request(protocol, port),
                            128 + _PMP_OPCODE[protocol], timeout, clock)
    return data is not None and _natpmp_deleted(data, protocol, port)


def natpmp_map(gateway: str, socket_factory, port: int, lease: int = LEASE_SECONDS, timeout: float = 2.0,
               clock=time.monotonic) -> bool:
    """Ask a NAT-PMP box to map `port` to this PC on the same external port, TCP then UDP. True only when both are
    granted; when the second is refused, the first is removed again."""
    if not _valid_port(port) or not isinstance(lease, int) or lease <= 0:
        return False
    done = []
    for protocol in PROTOCOLS:
        data = _natpmp_exchange(gateway, socket_factory, natpmp_map_request(protocol, port, lease),
                                128 + _PMP_OPCODE[protocol], timeout, clock)
        if data is None or not parse_natpmp_map(data, protocol, port):
            for held in done:
                _natpmp_remove(gateway, socket_factory, held, port, timeout, clock)
            return False
        done.append(protocol)
    return True


def natpmp_unmap(gateway: str, socket_factory, port: int, timeout: float = 2.0, clock=time.monotonic) -> bool:
    """Remove the TCP and the UDP mapping of `port` (a request with lease 0). Both are tried; True when the box confirmed both."""
    if not _valid_port(port):
        return False
    removed = True
    for protocol in PROTOCOLS:
        removed = _natpmp_remove(gateway, socket_factory, protocol, port, timeout, clock) and removed
    return removed


# ---- the site's echo ----

def site_echo(opener, timeout: float = HTTP_TIMEOUT) -> str | None:
    """The address retro-recomp.com sees for this PC: one GET of ECHO_URL, read at most 513 bytes, then `parse_echo`."""
    host = urlparse(ECHO_URL).hostname
    body = _fetch(opener, urllib.request.Request(ECHO_URL, method='GET'), host, 512, timeout)
    return parse_echo(body) if body is not None else None


# ---- the whole search, in Arthur's order ----

def find_public(local_address: str, port: int, *, socket_factory, opener, ipv6_reader, allow_site: bool,
                timeout: float = 2.5, http_timeout: float = HTTP_TIMEOUT, lease: int = LEASE_SECONDS,
                clock=time.monotonic) -> Reach:
    """Find the public address the room's key carries, and open `port` (TCP and UDP) on the box when it allows it.

    (a) the box: UPnP (external address, then the mapping), then NAT-PMP. A box whose external address is private or
        shared (CGNAT) is not mapped: nobody could reach it. (b) the PC's own global IPv6 (`ipv6_reader()`). (c) the
        site's echo, only when `allow_site` is True; with False the opener is never asked for it.
    The state of the answer: 'upnp' (a mapping is held, `via` says by which protocol), 'ipv6', 'site', 'cgnat',
    'forward_needed' (an address is known, the box did not map: the player opens the port) or 'waiting' (nothing found).
    The caller calls `release` when the room closes. A call takes about `timeout` seconds for the SSDP search and up to
    2 for each NAT-PMP step, so it belongs in a worker thread."""
    box_address = None                                 # the external address a box reported, whether or not it is mapped
    description = upnp_discover(local_address, socket_factory, timeout, clock)
    if description:
        service = upnp_service(description, opener, http_timeout)
        if service:
            control, service_type = service
            external = upnp_external_address(control, service_type, opener, http_timeout)
            if external:
                box_address = external
                if (classify_external(external) != 'cgnat'
                        and upnp_map(control, service_type, opener, port, local_address, lease, http_timeout)):
                    return Reach(UPNP, ipv4=external, mapped=True, via='upnp', control=control, service=service_type, port=port)
    shared = box_address is not None and classify_external(box_address) == 'cgnat'
    gateway = urlparse(description).hostname if description else gateway_guess(local_address)
    if gateway and not shared:
        external = natpmp_external_address(gateway, socket_factory, timeout, clock)
        if external:
            box_address = box_address or external
            if classify_external(external) == 'cgnat':
                box_address, shared = external, True
            elif natpmp_map(gateway, socket_factory, port, lease, timeout, clock):
                return Reach(UPNP, ipv4=external, mapped=True, via='natpmp', gateway=gateway, port=port)
    try:
        ipv6 = ipv6_reader()
    except Exception:                                  # a reader we were given: whatever it does, the search goes on
        ipv6 = None
    if ipv6:
        return Reach(IPV6, ipv6=ipv6)
    if shared:
        return Reach(CGNAT, ipv4=box_address)
    if allow_site:
        seen = site_echo(opener, http_timeout)
        if seen and ':' in seen:
            return Reach(SITE, ipv6=seen)
        if seen:
            if box_address and classify_external(box_address, seen) == 'cgnat':
                return Reach(CGNAT, ipv4=box_address)  # the box says one address, the site sees another: two boxes
            return Reach(FORWARD_NEEDED if box_address else SITE, ipv4=seen)
    if box_address:
        return Reach(FORWARD_NEEDED, ipv4=box_address)
    return Reach(WAITING)


def release(reach: Reach, *, socket_factory, opener, timeout: float = 2.5, http_timeout: float = HTTP_TIMEOUT,
            clock=time.monotonic) -> bool:
    """Remove the mapping `find_public` made (when the room closes). True when nothing was held or the box confirmed the
    removal; False when it did not (the lease then ends by itself, `LEASE_SECONDS` after the mapping)."""
    if not reach.mapped:
        return True
    if reach.via == 'upnp':
        return upnp_unmap(reach.control, reach.service, opener, reach.port, http_timeout)
    if reach.via == 'natpmp':
        return natpmp_unmap(reach.gateway, socket_factory, reach.port, timeout, clock)
    return False
