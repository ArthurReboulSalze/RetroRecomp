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

from dataclasses import dataclass
import ipaddress
import struct
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

SSDP_ADDRESS = ('239.255.255.250', 1900)
SEARCH_TARGETS = ('urn:schemas-upnp-org:device:InternetGatewayDevice:1', 'urn:schemas-upnp-org:device:InternetGatewayDevice:2')
WAN_SERVICES = ('urn:schemas-upnp-org:service:WANIPConnection:2', 'urn:schemas-upnp-org:service:WANIPConnection:1',
                'urn:schemas-upnp-org:service:WANPPPConnection:1')
NATPMP_PORT = 5351
LEASE_SECONDS = 7200
DESCRIPTION = 'Retro-Recomp room'
ECHO_URL = 'https://retro-recomp.com/api/v1/ip'
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

