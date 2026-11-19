"""How an Internet room's host becomes reachable (retrorecomp/netplay/reach.py): the parsers, on answers written in the
shape real boxes give, and the live layer on fake sockets and a fake HTTP opener. No socket to a router, no Internet, no ROM."""
import io
import struct
import unittest
import urllib.error
import urllib.request

from retrorecomp.netplay import reach

DESCRIPTION = b"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0"><device><deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType>
<deviceList><device><deviceType>urn:schemas-upnp-org:device:WANDevice:1</deviceType><deviceList><device>
<deviceType>urn:schemas-upnp-org:device:WANConnectionDevice:1</deviceType><serviceList><service>
<serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType><serviceId>urn:upnp-org:serviceId:WANIPConn1</serviceId>
<controlURL>/ctl/IPConn</controlURL><eventSubURL>/evt/IPConn</eventSubURL><SCPDURL>/WANIPCn.xml</SCPDURL></service>
</serviceList></device></deviceList></device></deviceList></device></root>"""


class UpnpTests(unittest.TestCase):
    def test_ssdp_answer_only_points_at_the_box_that_answered(self):
        answer = (b'HTTP/1.1 200 OK\r\nCACHE-CONTROL: max-age=120\r\nST: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n'
                  b'LOCATION: http://192.168.1.254:5000/rootDesc.xml\r\nSERVER: box\r\n\r\n')
        self.assertEqual(reach.parse_ssdp_answer(answer, '192.168.1.254'), 'http://192.168.1.254:5000/rootDesc.xml')
        self.assertIsNone(reach.parse_ssdp_answer(answer, '192.168.1.10'))                  # another machine answered with it
        self.assertIsNone(reach.parse_ssdp_answer(answer.replace(b'192.168.1.254:5000', b'evil.example:80'), '192.168.1.254'))
        self.assertIsNone(reach.parse_ssdp_answer(answer.replace(b'http://', b'https://'), '192.168.1.254'))
        self.assertIsNone(reach.parse_ssdp_answer(b'NOTIFY * HTTP/1.1\r\n\r\n', '192.168.1.254'))
        self.assertIn(b'ST: urn:schemas-upnp-org:device:InternetGatewayDevice:1', reach.ssdp_search(reach.SEARCH_TARGETS[0]))

    def test_the_wan_service_of_a_description(self):
        found = reach.parse_description(DESCRIPTION, 'http://192.168.1.254:5000/rootDesc.xml')
        self.assertEqual(found, ('http://192.168.1.254:5000/ctl/IPConn', 'urn:schemas-upnp-org:service:WANIPConnection:1'))
        ppp = DESCRIPTION.replace(b'WANIPConnection:1', b'WANPPPConnection:1')
        self.assertEqual(reach.parse_description(ppp, 'http://192.168.1.254:5000/x')[1], 'urn:schemas-upnp-org:service:WANPPPConnection:1')
        elsewhere = DESCRIPTION.replace(b'<controlURL>/ctl/IPConn', b'<controlURL>http://10.9.9.9/ctl')
        self.assertIsNone(reach.parse_description(elsewhere, 'http://192.168.1.254:5000/rootDesc.xml'))   # never another host
        for bad in (b'<root/>', b'not xml', b'<!DOCTYPE x [<!ENTITY a "b">]><root>&a;</root>', b'<a>' * 40000):
            self.assertIsNone(reach.parse_description(bad, 'http://192.168.1.254:5000/rootDesc.xml'))

    def test_soap_requests_and_answers(self):
        body = reach.soap_body('urn:schemas-upnp-org:service:WANIPConnection:1', 'AddPortMapping',
                               reach.add_mapping_arguments('UDP', 24611, '192.168.1.58'))
        for part in (b'<NewExternalPort>24611</NewExternalPort>', b'<NewProtocol>UDP</NewProtocol>',
                     b'<NewInternalClient>192.168.1.58</NewInternalClient>', b'<NewLeaseDuration>7200</NewLeaseDuration>'):
            self.assertIn(part, body)
        external = (b'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                    b'<u:GetExternalIPAddressResponse xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">'
                    b'<NewExternalIPAddress>82.65.10.20</NewExternalIPAddress></u:GetExternalIPAddressResponse></s:Body></s:Envelope>')
        self.assertEqual(reach.parse_soap(external, 'NewExternalIPAddress'), '82.65.10.20')
        fault = (b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault><faultstring>UPnPError'
                 b'</faultstring><detail><UPnPError><errorCode>718</errorCode></UPnPError></detail></s:Fault></s:Body></s:Envelope>')
        self.assertIsNone(reach.parse_soap(fault, 'NewExternalIPAddress'))
        self.assertFalse(reach.soap_ok(fault, 'AddPortMapping'))
        ok = (b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:AddPortMappingResponse '
              b'xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1"/></s:Body></s:Envelope>')
        self.assertTrue(reach.soap_ok(ok, 'AddPortMapping'))
        self.assertFalse(reach.soap_ok(ok, 'DeletePortMapping'))


class NatPmpTests(unittest.TestCase):
    def test_external_address_and_mappings(self):
        self.assertEqual(reach.natpmp_address_request(), b'\x00\x00')
        answer = struct.pack('>BBHI', 0, 128, 0, 1234) + bytes((82, 65, 10, 20))
        self.assertEqual(reach.parse_natpmp_address(answer), '82.65.10.20')
        self.assertIsNone(reach.parse_natpmp_address(struct.pack('>BBHI', 0, 128, 3, 1234) + bytes(4)))   # result: not authorised
        self.assertIsNone(reach.parse_natpmp_address(answer[:-1]))
        self.assertEqual(reach.natpmp_map_request('TCP', 24611), struct.pack('>BBHHHI', 0, 2, 0, 24611, 24611, 7200))
        mapped = struct.pack('>BBHIHHI', 0, 130, 0, 1234, 24611, 24611, 7200)
        self.assertTrue(reach.parse_natpmp_map(mapped, 'TCP', 24611))
        self.assertFalse(reach.parse_natpmp_map(mapped, 'UDP', 24611))
        self.assertFalse(reach.parse_natpmp_map(struct.pack('>BBHIHHI', 0, 130, 0, 1234, 24611, 40000, 7200), 'TCP', 24611))


class ClassifyTests(unittest.TestCase):
    def test_public_shared_and_double(self):
        self.assertEqual(reach.classify_external('82.65.10.20'), 'public')
        for shared in ('100.64.3.4', '100.127.0.1', '10.0.0.2', '192.168.0.1', '172.16.5.5'):
            self.assertEqual(reach.classify_external(shared), 'cgnat', shared)
        self.assertEqual(reach.classify_external('82.65.10.20', seen_from_outside='82.65.10.21'), 'cgnat')    # two boxes
        self.assertEqual(reach.classify_external('82.65.10.20', seen_from_outside='82.65.10.20'), 'public')
        self.assertEqual(reach.classify_external(None), 'unknown')
        self.assertEqual(reach.classify_external('x'), 'unknown')

    def test_the_echo_and_the_gateway_guess(self):
        self.assertEqual(reach.parse_echo(b'{"ip": "82.65.10.20"}'), '82.65.10.20')
        self.assertEqual(reach.parse_echo(b'{"ip": "2a01:e0a::5"}'), '2a01:e0a::5')
        for bad in (b'', b'{}', b'{"ip": "x"}', b'{"ip": 5}', b'[1]', b'x' * 600, b'\xff'):
            self.assertIsNone(reach.parse_echo(bad))
        self.assertEqual(reach.gateway_guess('192.168.1.58'), '192.168.1.1')
        self.assertIsNone(reach.gateway_guess('82.65.10.20'))

    def test_the_local_ipv6_reads_only_the_source_address(self):
        class Probe:
            def __init__(self, address):
                self.address, self.sent = address, []

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def connect(self, target):
                self.target = target

            def getsockname(self):
                return (self.address, 0, 0, 0)

            def sendto(self, *args):                 # never called: a connected UDP socket sends nothing by itself
                self.sent.append(args)

        class Module:
            AF_INET6, SOCK_DGRAM = 23, 2

            def __init__(self, address):
                self.address = address

            def socket(self, *args):
                return Probe(self.address)
        self.assertEqual(reach.local_ipv6(Module('2a01:e0a:1:2::5')), '2a01:e0a:1:2::5')
        self.assertEqual(reach.local_ipv6(Module('2a01:e0a:1:2::5%12')), '2a01:e0a:1:2::5')
        for not_global in ('fe80::1', 'fd00::1', '::1', '::ffff:1.2.3.4'):
            self.assertIsNone(reach.local_ipv6(Module(not_global)), not_global)


# ---- the live layer, on fake sockets and a fake HTTP opener: nothing here touches a network ----

LOCAL = '192.168.1.58'
BOX = '192.168.1.254'
SERVICE = 'urn:schemas-upnp-org:service:WANIPConnection:1'
CONTROL = f'http://{BOX}:5000/ctl/IPConn'
DESCRIPTION_URL = f'http://{BOX}:5000/rootDesc.xml'
SOAP_HEAD = b'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
SOAP_TAIL = b'</s:Body></s:Envelope>'


def soap_answer(action, inner=b''):
    return (SOAP_HEAD + f'<u:{action}Response xmlns:u="{SERVICE}">'.encode() + inner
            + f'</u:{action}Response>'.encode() + SOAP_TAIL)


def external_answer(address):
    return soap_answer('GetExternalIPAddress', f'<NewExternalIPAddress>{address}</NewExternalIPAddress>'.encode())


FAULT = (SOAP_HEAD + b'<s:Fault><faultstring>UPnPError</faultstring><detail><UPnPError><errorCode>718</errorCode></UPnPError>'
         b'</detail></s:Fault>' + SOAP_TAIL)


def ssdp_answer(host=BOX):
    return (f'HTTP/1.1 200 OK\r\nST: {reach.SEARCH_TARGETS[0]}\r\nLOCATION: http://{host}:5000/rootDesc.xml\r\n\r\n').encode()


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeSocket:
    """A UDP socket whose datagrams come from `network.responder(data, address)`; a read with nothing to read waits out
    its timeout on the fake clock and raises TimeoutError."""

    def __init__(self, network):
        self.network, self.queue, self.timeout, self.closed, self.bound, self.options = network, [], None, False, None, []

    def settimeout(self, value):
        self.timeout = value

    def setsockopt(self, *args):
        self.options.append(args)

    def bind(self, address):
        if self.network.bind_error:
            raise OSError('bind')
        self.bound = address

    def sendto(self, data, address):
        self.network.sent.append((data, address))
        if self.network.send_error:
            raise OSError('send')
        self.queue.extend(self.network.responder(data, address))

    def recvfrom(self, size):
        if self.queue:
            item = self.queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        self.network.clock.now += self.timeout or 0
        raise TimeoutError('timed out')

    def close(self):
        self.closed = True


class FakeNetwork:
    def __init__(self, responder=None):
        self.responder = responder or (lambda data, address: [])
        self.clock = FakeClock()
        self.sent, self.sockets = [], []
        self.bind_error = self.send_error = self.factory_error = False

    def __call__(self):
        if self.factory_error:
            raise OSError('no socket')
        self.sockets.append(FakeSocket(self))
        return self.sockets[-1]


class FakeResponse:
    def __init__(self, body, url=None, status=200):
        self.body, self.url, self.status, self.read_sizes = body, url, status, []

    def read(self, size=-1):
        self.read_sizes.append(size)
        return self.body if size < 0 else self.body[:size]

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """`handler(request)` gives the body (bytes), a FakeResponse, or raises; every request is kept."""

    def __init__(self, handler=None):
        self.handler, self.requests, self.timeouts = handler or (lambda request: b''), [], []

    def open(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        answer = self.handler(request)
        if isinstance(answer, bytes):
            answer = FakeResponse(answer, request.full_url)
        elif answer.url is None:
            answer.url = request.full_url
        return answer

    def actions(self):
        return [request.get_header('Soapaction').strip('"').split('#')[1] for request in self.requests
                if request.get_header('Soapaction')]


def box_handler(external='82.65.10.20', map_ok=True, echo=b'{"ip": "82.65.10.20"}'):
    def handler(request):
        url, action = request.full_url, (request.get_header('Soapaction') or '').strip('"').split('#')[-1]
        if url == DESCRIPTION_URL:
            return DESCRIPTION
        if url == CONTROL and action == 'GetExternalIPAddress':
            return external_answer(external)
        if url == CONTROL and action == 'AddPortMapping':
            return soap_answer(action) if map_ok else FAULT
        if url == CONTROL and action == 'DeletePortMapping':
            return soap_answer(action)
        if url == reach.ECHO_URL:
            return echo
        raise OSError('no route')
    return handler


def pmp_answer(request, external='82.65.10.20', grant=True):
    """What a NAT-PMP box says to `request`."""
    if request == b'\x00\x00':
        return struct.pack('>BBHI', 0, 128, 0, 99) + bytes(int(part) for part in external.split('.'))
    _version, opcode, _reserved, internal, wanted, lease = struct.unpack('>BBHHHI', request)
    if not grant:
        return struct.pack('>BBHIHHI', 0, 128 + opcode, 2, 99, internal, 0, 0)
    return struct.pack('>BBHIHHI', 0, 128 + opcode, 0, 99, internal, wanted or internal, lease)


class DiscoverTests(unittest.TestCase):
    def test_search_goes_to_the_multicast_address_for_each_target_and_closes(self):
        network = FakeNetwork(lambda data, address: [(ssdp_answer(), (BOX, 1900))] if data.startswith(b'M-SEARCH') else [])
        url = reach.upnp_discover(LOCAL, network, 2.0, network.clock)
        self.assertEqual(url, DESCRIPTION_URL)
        sock = network.sockets[0]
        self.assertEqual(sock.bound, (LOCAL, 0))
        self.assertTrue(sock.closed)
        self.assertEqual([address for _data, address in network.sent], [reach.SSDP_ADDRESS] * len(reach.SEARCH_TARGETS))
        for (data, _address), target in zip(network.sent, reach.SEARCH_TARGETS):
            self.assertEqual(data, reach.ssdp_search(target))

    def test_garbage_and_answers_from_other_boxes_are_skipped(self):
        answers = [(b'\xff\xfe garbage', (BOX, 1900)), (ssdp_answer('192.168.1.99'), (BOX, 1900)),   # LOCATION on another host
                   (ssdp_answer('8.8.8.8'), ('8.8.8.8', 1900)),  # an answer from the Internet
                   (ssdp_answer(), ('::1',)), (ssdp_answer(), None), (ssdp_answer(), (BOX, 1900))]
        network = FakeNetwork(lambda data, address: answers)
        self.assertEqual(reach.upnp_discover(LOCAL, network, 2.0, network.clock), DESCRIPTION_URL)

    def test_no_answer_waits_the_timeout_then_gives_none(self):
        network = FakeNetwork()
        self.assertIsNone(reach.upnp_discover(LOCAL, network, 2.0, network.clock))
        self.assertTrue(2.0 <= network.clock.now <= 2.01)
        self.assertTrue(network.sockets[0].closed)

    def test_a_flood_of_garbage_is_bounded(self):
        network = FakeNetwork(lambda data, address: [(b'x', (BOX, 1900))] * 500)
        self.assertIsNone(reach.upnp_discover(LOCAL, network, 2.0, network.clock))
        self.assertTrue(network.sockets[0].closed)

    def test_socket_errors_and_bad_addresses_give_none(self):
        network = FakeNetwork()
        network.bind_error = True
        self.assertIsNone(reach.upnp_discover(LOCAL, network, 1.0, network.clock))
        self.assertTrue(network.sockets[0].closed)
        network = FakeNetwork()
        network.send_error = True
        self.assertIsNone(reach.upnp_discover(LOCAL, network, 1.0, network.clock))
        network = FakeNetwork()
        network.factory_error = True
        self.assertIsNone(reach.upnp_discover(LOCAL, network, 1.0, network.clock))
        self.assertIsNone(reach.upnp_discover('not an address', network, 1.0, network.clock))
        self.assertIsNone(reach.upnp_discover('::1', network, 1.0, network.clock))


class UpnpLiveTests(unittest.TestCase):
    def test_description_is_fetched_with_a_bounded_read(self):
        opener = FakeOpener(lambda request: DESCRIPTION)
        self.assertEqual(reach.upnp_service(DESCRIPTION_URL, opener), (CONTROL, SERVICE))
        self.assertEqual(opener.requests[0].get_method(), 'GET')
        self.assertEqual(opener.timeouts, [reach.HTTP_TIMEOUT])
        response = FakeResponse(b'<a>' * 1000000)
        self.assertIsNone(reach.upnp_service(DESCRIPTION_URL, FakeOpener(lambda request: response)))
        self.assertEqual(response.read_sizes, [reach.MAX_ANSWER + 1])

    def test_description_failures_give_none(self):
        def broken(request):
            raise OSError('refused')
        self.assertIsNone(reach.upnp_service(DESCRIPTION_URL, FakeOpener(broken)))
        self.assertIsNone(reach.upnp_service(DESCRIPTION_URL, FakeOpener(lambda request: b'not xml')))
        self.assertIsNone(reach.upnp_service(DESCRIPTION_URL, FakeOpener(lambda request: FakeResponse(DESCRIPTION, status=404))))
        error = urllib.error.HTTPError(DESCRIPTION_URL, 500, 'x', {}, io.BytesIO(b'x'))
        self.assertIsNone(reach.upnp_service(DESCRIPTION_URL, FakeOpener(lambda request: (_ for _ in ()).throw(error))))

    def test_only_a_box_on_the_local_network_is_ever_fetched(self):
        opener = FakeOpener(lambda request: DESCRIPTION)
        for url in ('http://8.8.8.8:5000/rootDesc.xml', 'https://192.168.1.254/rootDesc.xml', 'http://evil.example/x',
                    'http://127.0.0.1:5000/x', 'http://192.168.1.254@8.8.8.8/x', 'http://192.168.1.254:99999/x',
                    'ftp://192.168.1.1/x',
                    '', 'garbage'):
            self.assertIsNone(reach.upnp_service(url, opener), url)
            self.assertIsNone(reach.upnp_external_address(url, SERVICE, opener), url)
            self.assertFalse(reach.upnp_map(url, SERVICE, opener, 24611, LOCAL), url)
            self.assertFalse(reach.upnp_unmap(url, SERVICE, opener, 24611), url)
        self.assertEqual(opener.requests, [])

    def test_a_redirect_or_an_answer_from_another_host_is_dropped(self):
        moved = FakeResponse(DESCRIPTION, url='http://8.8.8.8/rootDesc.xml')
        self.assertIsNone(reach.upnp_service(DESCRIPTION_URL, FakeOpener(lambda request: moved)))
        self.assertIsNone(reach.upnp_external_address(CONTROL, SERVICE, FakeOpener(
            lambda request: FakeResponse(external_answer('1.2.3.4'), url='http://8.8.8.8/ctl'))))
        refusing = reach.make_opener()
        for handler in refusing.handlers:
            if isinstance(handler, urllib.request.HTTPRedirectHandler):
                self.assertIsNone(handler.redirect_request(None, None, 302, 'Found', {}, 'http://8.8.8.8/'))
        self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) for h in refusing.handlers))  # no system proxy for a box

    def test_external_address(self):
        opener = FakeOpener(lambda request: external_answer('82.65.10.20'))
        self.assertEqual(reach.upnp_external_address(CONTROL, SERVICE, opener), '82.65.10.20')
        request = opener.requests[0]
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Soapaction'), f'"{SERVICE}#GetExternalIPAddress"')
        self.assertEqual(request.get_header('Content-type'), 'text/xml; charset="utf-8"')
        self.assertIn(b'<u:GetExternalIPAddress ', request.data)
        for answer in (FAULT, b'', b'not xml', external_answer('not an address'), external_answer(''), external_answer('::1'),
                       b'<!DOCTYPE x [<!ENTITY a "b">]><x/>'):
            self.assertIsNone(reach.upnp_external_address(CONTROL, SERVICE, FakeOpener(lambda request, a=answer: a)))
        self.assertIsNone(reach.upnp_external_address(CONTROL, 'urn:evil"><x/>', opener))      # a service that is not a WAN one
        self.assertEqual(len(opener.requests), 1)

    def test_soap_fault_as_http_500_is_a_failure(self):
        error = urllib.error.HTTPError(CONTROL, 500, 'Internal Server Error', {}, io.BytesIO(FAULT))

        def failing(request):
            raise error
        opener = FakeOpener(failing)
        self.assertIsNone(reach.upnp_external_address(CONTROL, SERVICE, opener))
        self.assertFalse(reach.upnp_map(CONTROL, SERVICE, opener, 24611, LOCAL))
        self.assertFalse(reach.upnp_unmap(CONTROL, SERVICE, opener, 24611))

    def test_map_is_tcp_then_udp_and_true_only_if_both(self):
        opener = FakeOpener(lambda request: soap_answer('AddPortMapping'))
        self.assertTrue(reach.upnp_map(CONTROL, SERVICE, opener, 24611, LOCAL, 3600))
        self.assertEqual([request.get_header('Soapaction') for request in opener.requests], [f'"{SERVICE}#AddPortMapping"'] * 2)
        self.assertIn(b'<NewProtocol>TCP</NewProtocol>', opener.requests[0].data)
        self.assertIn(b'<NewProtocol>UDP</NewProtocol>', opener.requests[1].data)
        self.assertIn(b'<NewLeaseDuration>3600</NewLeaseDuration>', opener.requests[0].data)
        self.assertIn(b'<NewInternalClient>192.168.1.58</NewInternalClient>', opener.requests[1].data)
        self.assertEqual(opener.requests[0].get_header('Content-type'), 'text/xml; charset="utf-8"')

    def test_a_refused_second_mapping_removes_the_first(self):
        def handler(request):
            if b'<NewProtocol>UDP</NewProtocol>' in request.data and b'AddPortMapping' in request.data:
                return FAULT
            return soap_answer('AddPortMapping')
        opener = FakeOpener(handler)
        self.assertFalse(reach.upnp_map(CONTROL, SERVICE, opener, 24611, LOCAL))
        self.assertEqual(opener.actions(), ['AddPortMapping', 'AddPortMapping', 'DeletePortMapping'])
        self.assertIn(b'<NewProtocol>TCP</NewProtocol>', opener.requests[2].data)
        refused = FakeOpener(lambda request: FAULT)
        self.assertFalse(reach.upnp_map(CONTROL, SERVICE, refused, 24611, LOCAL))
        self.assertEqual(len(refused.requests), 1)                         # nothing to take back, and UDP is not tried

    def test_map_arguments_are_checked_before_anything_is_sent(self):
        opener = FakeOpener(lambda request: soap_answer('AddPortMapping'))
        for port, address, lease in ((0, LOCAL, 7200), (70000, LOCAL, 7200), ('24611', LOCAL, 7200), (True, LOCAL, 7200),
                                     (24611, '<x/>', 7200), (24611, 'a.b', 7200), (24611, LOCAL, -1), (24611, LOCAL, '1')):
            self.assertFalse(reach.upnp_map(CONTROL, SERVICE, opener, port, address, lease), (port, address, lease))
        self.assertFalse(reach.upnp_map(CONTROL, 'urn:other', opener, 24611, LOCAL))
        self.assertEqual(opener.requests, [])

    def test_unmap_tries_both_and_reports_both(self):
        opener = FakeOpener(lambda request: soap_answer('DeletePortMapping'))
        self.assertTrue(reach.upnp_unmap(CONTROL, SERVICE, opener, 24611))
        self.assertEqual(opener.actions(), ['DeletePortMapping'] * 2)
        self.assertIn(b'<NewProtocol>TCP</NewProtocol>', opener.requests[0].data)
        self.assertIn(b'<NewProtocol>UDP</NewProtocol>', opener.requests[1].data)
        half = FakeOpener(lambda request: FAULT if b'TCP' in request.data else soap_answer('DeletePortMapping'))
        self.assertFalse(reach.upnp_unmap(CONTROL, SERVICE, half, 24611))
        self.assertEqual(len(half.requests), 2)
        self.assertFalse(reach.upnp_unmap(CONTROL, SERVICE, opener, 0))


class NatPmpLiveTests(unittest.TestCase):
    def pmp_network(self, **options):
        return FakeNetwork(lambda data, address: [(pmp_answer(data, **options), (BOX, 5351))])

    def test_external_address(self):
        network = self.pmp_network()
        self.assertEqual(reach.natpmp_external_address(BOX, network, 2.0, network.clock), '82.65.10.20')
        self.assertEqual(network.sent, [(b'\x00\x00', (BOX, 5351))])
        self.assertTrue(network.sockets[0].closed)

    def test_no_answer_retries_by_the_rfc_and_stays_within_two_seconds(self):
        network = FakeNetwork()
        self.assertIsNone(reach.natpmp_external_address(BOX, network, 2.0, network.clock))
        self.assertEqual(len(network.sent), 3)
        self.assertTrue(1.7 <= network.clock.now <= 2.0)
        short = FakeNetwork()
        self.assertIsNone(reach.natpmp_external_address(BOX, short, 0.4, short.clock))
        self.assertLessEqual(short.clock.now, 0.4)

    def test_a_lost_first_request_is_sent_again(self):
        calls = []

        def responder(data, address):
            calls.append(data)
            return [] if len(calls) == 1 else [(pmp_answer(data), (BOX, 5351))]
        network = FakeNetwork(responder)
        self.assertEqual(reach.natpmp_external_address(BOX, network, 2.0, network.clock), '82.65.10.20')
        self.assertEqual(len(calls), 2)

    def test_datagrams_from_elsewhere_or_garbage_are_ignored(self):
        good = pmp_answer(b'\x00\x00')
        network = FakeNetwork(lambda data, address: [(good, ('192.168.1.77', 5351)), (good, (BOX, 4000)), (b'junk', (BOX, 5351)),
                                                     (b'', (BOX, 5351)),
                                                     (struct.pack('>BBHI', 0, 130, 0, 1) + bytes(4), (BOX, 5351))])
        self.assertIsNone(reach.natpmp_external_address(BOX, network, 2.0, network.clock))
        network = FakeNetwork(lambda data, address: [(b'junk', (BOX, 5351)), (good, (BOX, 5351))])
        self.assertEqual(reach.natpmp_external_address(BOX, network, 2.0, network.clock), '82.65.10.20')

    def test_a_refusal_is_final_and_a_reset_means_nobody_listens(self):
        network = FakeNetwork(lambda data, address: [(struct.pack('>BBHI', 0, 128, 3, 1) + bytes(4), (BOX, 5351))])
        self.assertIsNone(reach.natpmp_external_address(BOX, network, 2.0, network.clock))
        self.assertEqual(len(network.sent), 1)
        network = FakeNetwork(lambda data, address: [ConnectionResetError('icmp')])
        self.assertIsNone(reach.natpmp_external_address(BOX, network, 2.0, network.clock))
        self.assertEqual(len(network.sent), 1)

    def test_only_a_box_on_the_local_network_is_asked(self):
        network = self.pmp_network()
        for gateway in ('8.8.8.8', '127.0.0.1', '::1', 'evil.example', ''):
            self.assertIsNone(reach.natpmp_external_address(gateway, network, 2.0, network.clock), gateway)
            self.assertFalse(reach.natpmp_map(gateway, network, 24611, 7200, 2.0, network.clock), gateway)
        self.assertEqual((network.sent, network.sockets), ([], []))

    def test_socket_errors_give_none_or_false(self):
        network = self.pmp_network()
        network.factory_error = True
        self.assertIsNone(reach.natpmp_external_address(BOX, network, 2.0, network.clock))
        self.assertFalse(reach.natpmp_map(BOX, network, 24611, 7200, 2.0, network.clock))
        self.assertFalse(reach.natpmp_unmap(BOX, network, 24611, 2.0, network.clock))
        network = self.pmp_network()
        network.send_error = True
        self.assertIsNone(reach.natpmp_external_address(BOX, network, 2.0, network.clock))
        self.assertTrue(network.sockets[0].closed)

    def test_map_is_tcp_then_udp_on_the_same_port(self):
        network = self.pmp_network()
        self.assertTrue(reach.natpmp_map(BOX, network, 24611, 3600, 2.0, network.clock))
        self.assertEqual([data for data, _address in network.sent],
                         [struct.pack('>BBHHHI', 0, 2, 0, 24611, 24611, 3600),
                          struct.pack('>BBHHHI', 0, 1, 0, 24611, 24611, 3600)])
        self.assertTrue(all(address == (BOX, 5351) for _data, address in network.sent))
        self.assertTrue(all(sock.closed for sock in network.sockets))

    def test_a_refused_or_changed_mapping_is_false_and_the_first_is_removed(self):
        def responder(data, address):
            _v, opcode, _r, internal, wanted, lease = struct.unpack('>BBHHHI', data)
            if lease == 0:
                return [(pmp_answer(data), (BOX, 5351))]
            if opcode == 1:
                return [(struct.pack('>BBHIHHI', 0, 129, 0, 99, internal, 40000, lease), (BOX, 5351))]    # another external port
            return [(pmp_answer(data), (BOX, 5351))]
        network = FakeNetwork(responder)
        self.assertFalse(reach.natpmp_map(BOX, network, 24611, 7200, 2.0, network.clock))
        self.assertEqual([data[1] for data, _a in network.sent], [2, 1, 2])
        self.assertEqual(network.sent[2][0], struct.pack('>BBHHHI', 0, 2, 0, 24611, 0, 0))  # lease 0, external port 0
        refused = self.pmp_network(grant=False)
        self.assertFalse(reach.natpmp_map(BOX, refused, 24611, 7200, 2.0, refused.clock))
        self.assertEqual(len(refused.sent), 1)
        for port, lease in ((0, 7200), (70000, 7200), (24611, 0), (24611, -5)):
            self.assertFalse(reach.natpmp_map(BOX, refused, port, lease, 2.0, refused.clock))

    def test_unmap_sends_lease_zero_for_both(self):
        def responder(data, address):
            _v, opcode, _r, internal, wanted, lease = struct.unpack('>BBHHHI', data)
            return [(struct.pack('>BBHIHHI', 0, 128 + opcode, 0, 99, internal, 0, 0), (BOX, 5351))]
        network = FakeNetwork(responder)
        self.assertTrue(reach.natpmp_unmap(BOX, network, 24611, 2.0, network.clock))
        self.assertEqual([data for data, _a in network.sent],
                         [struct.pack('>BBHHHI', 0, 2, 0, 24611, 0, 0), struct.pack('>BBHHHI', 0, 1, 0, 24611, 0, 0)])
        silent = FakeNetwork()
        self.assertFalse(reach.natpmp_unmap(BOX, silent, 24611, 2.0, silent.clock))
        self.assertEqual(len(silent.sent), 6)  # both tried, 3 sends each
        self.assertFalse(reach.natpmp_unmap(BOX, network, 0, 2.0, network.clock))


class SiteEchoTests(unittest.TestCase):
    def test_one_get_of_the_echo_url(self):
        opener = FakeOpener(lambda request: b'{"ip": "82.65.10.20"}')
        self.assertEqual(reach.site_echo(opener, 3.0), '82.65.10.20')
        self.assertEqual([request.full_url for request in opener.requests], [reach.ECHO_URL])
        self.assertEqual((opener.requests[0].get_method(), opener.requests[0].data, opener.timeouts), ('GET', None, [3.0]))

    def test_every_failure_gives_none(self):
        def broken(request):
            raise OSError('down')
        self.assertIsNone(reach.site_echo(FakeOpener(broken)))
        self.assertIsNone(reach.site_echo(FakeOpener(lambda request: b'<html>')))
        self.assertIsNone(reach.site_echo(FakeOpener(lambda request: FakeResponse(b'{"ip": "1.2.3.4"}', status=500))))
        moved = FakeResponse(b'{"ip": "1.2.3.4"}', url='https://evil.example/')
        self.assertIsNone(reach.site_echo(FakeOpener(lambda request: moved)))
        big = FakeResponse(b'{"ip": "1.2.3.4"}' + b' ' * 1000000)
        self.assertIsNone(reach.site_echo(FakeOpener(lambda request: big)))
        self.assertEqual(big.read_sizes, [513])


class FindPublicTests(unittest.TestCase):
    """The whole search against a fake box that can speak UPnP, NAT-PMP or neither."""

    def run_search(self, *, upnp=True, natpmp=False, external='82.65.10.20', map_ok=True, ipv6=None, allow_site=True,
                   echo=b'{"ip": "82.65.10.20"}', pmp_gateway=BOX, local=LOCAL, http=None):
        def responder(data, address):
            if address == reach.SSDP_ADDRESS and upnp:
                return [(ssdp_answer(), (BOX, 1900))]
            if address == (pmp_gateway, 5351) and natpmp:
                return [(pmp_answer(data, external=external), (pmp_gateway, 5351))]
            return []
        self.network = FakeNetwork(responder)
        self.opener = FakeOpener(http or box_handler(external, map_ok, echo))
        self.ipv6_calls = []

        def ipv6_reader():
            self.ipv6_calls.append(1)
            if isinstance(ipv6, Exception):
                raise ipv6
            return ipv6
        return reach.find_public(local, 24611, socket_factory=self.network, opener=self.opener, ipv6_reader=ipv6_reader,
                                 allow_site=allow_site, clock=self.network.clock)

    def echo_requests(self):
        return [request for request in self.opener.requests if request.full_url == reach.ECHO_URL]

    def test_upnp_maps_and_neither_ipv6_nor_the_site_is_asked(self):
        result = self.run_search()
        self.assertEqual(result, reach.Reach('upnp', ipv4='82.65.10.20', mapped=True))
        self.assertEqual((result.via, result.control, result.service, result.port), ('upnp', CONTROL, SERVICE, 24611))
        self.assertEqual(self.opener.actions(), ['GetExternalIPAddress', 'AddPortMapping', 'AddPortMapping'])
        self.assertEqual((self.ipv6_calls, self.echo_requests()), ([], []))

    def test_a_box_without_upnp_that_answers_nat_pmp(self):
        result = self.run_search(upnp=False, natpmp=True, local='192.168.1.58', pmp_gateway='192.168.1.1')
        self.assertEqual(result, reach.Reach('upnp', ipv4='82.65.10.20', mapped=True))
        self.assertEqual((result.via, result.gateway, result.port), ('natpmp', '192.168.1.1', 24611))
        self.assertEqual(self.opener.requests, [])                                       # no HTTP at all
        self.assertEqual(self.ipv6_calls, [])

    def test_upnp_that_fails_falls_through_to_nat_pmp(self):
        def broken(request):
            raise OSError('refused')
        result = self.run_search(upnp=True, natpmp=True, http=broken, pmp_gateway=BOX)
        self.assertEqual((result.state, result.via, result.gateway), ('upnp', 'natpmp', BOX))
        result = self.run_search(upnp=True, natpmp=True, map_ok=False, pmp_gateway=BOX)           # UPnP refuses the mapping
        self.assertEqual((result.state, result.via), ('upnp', 'natpmp'))

    def test_a_cgnat_address_is_not_mapped_and_not_sent_to_the_site(self):
        for shared in ('100.64.12.7', '10.20.30.40'):
            result = self.run_search(external=shared)
            self.assertEqual((result.state, result.ipv4, result.mapped), ('cgnat', shared, False), shared)
            self.assertEqual(self.opener.actions(), ['GetExternalIPAddress'])
            self.assertEqual(self.echo_requests(), [])
        result = self.run_search(upnp=False, natpmp=True, external='100.64.1.2', pmp_gateway='192.168.1.1')
        self.assertEqual((result.state, result.mapped), ('cgnat', False))
        asked = [data for data, address in self.network.sent if address[1] == 5351]
        self.assertEqual(asked, [b'\x00\x00'])                                           # only the address was asked

    def test_cgnat_with_a_global_ipv6_still_works_by_ipv6(self):
        result = self.run_search(external='100.64.12.7', ipv6='2a01:e0a:1:2::5')
        self.assertEqual(result, reach.Reach('ipv6', ipv6='2a01:e0a:1:2::5'))
        self.assertEqual(self.echo_requests(), [])

    def test_nothing_on_the_box_then_ipv6_and_no_site(self):
        result = self.run_search(upnp=False, ipv6='2a01:e0a:1:2::5')
        self.assertEqual(result, reach.Reach('ipv6', ipv6='2a01:e0a:1:2::5'))
        self.assertEqual(self.echo_requests(), [])

    def test_the_site_only_when_allowed_and_only_after_the_rest(self):
        result = self.run_search(upnp=False)
        self.assertEqual(result, reach.Reach('site', ipv4='82.65.10.20'))
        self.assertEqual(len(self.echo_requests()), 1)
        self.assertEqual(self.ipv6_calls, [1])
        result = self.run_search(upnp=False, allow_site=False)
        self.assertEqual(result, reach.Reach('waiting'))
        self.assertEqual(self.opener.requests, [])                                       # the opener is never asked for the echo
        result = self.run_search(upnp=False, echo=b'{"ip": "2a01:e0a::9"}')
        self.assertEqual(result, reach.Reach('site', ipv6='2a01:e0a::9'))
        self.assertEqual(self.run_search(upnp=False, echo=b'garbage'), reach.Reach('waiting'))

    def test_an_address_without_a_mapping_is_forward_needed(self):
        result = self.run_search(map_ok=False, allow_site=False)
        self.assertEqual((result.state, result.ipv4, result.mapped), ('forward_needed', '82.65.10.20', False))
        self.assertEqual(self.echo_requests(), [])
        result = self.run_search(map_ok=False)                                           # the site sees the same address
        self.assertEqual((result.state, result.ipv4), ('forward_needed', '82.65.10.20'))
        self.assertEqual(self.opener.actions().count('DeletePortMapping'), 0)  # the first (TCP) mapping failed: nothing held

    def test_two_boxes_in_a_row_is_cgnat(self):
        result = self.run_search(map_ok=False, echo=b'{"ip": "82.65.10.99"}')
        self.assertEqual((result.state, result.ipv4), ('cgnat', '82.65.10.20'))

    def test_a_failing_ipv6_reader_does_not_stop_the_search(self):
        result = self.run_search(upnp=False, ipv6=RuntimeError('no interface'))
        self.assertEqual(result, reach.Reach('site', ipv4='82.65.10.20'))

    def test_a_silent_network_waits_a_bounded_time(self):
        result = self.run_search(upnp=False, allow_site=False)
        self.assertEqual(result, reach.Reach('waiting'))
        self.assertLessEqual(self.network.clock.now, 2.5 + 2.0)
        self.assertTrue(all(sock.closed for sock in self.network.sockets))

    def test_release_removes_what_was_mapped(self):
        result = self.run_search()
        opener = FakeOpener(box_handler())
        self.assertTrue(reach.release(result, socket_factory=FakeNetwork(), opener=opener))
        self.assertEqual(opener.actions(), ['DeletePortMapping', 'DeletePortMapping'])
        result = self.run_search(upnp=False, natpmp=True, pmp_gateway='192.168.1.1')

        def responder(data, address):
            _v, opcode, _r, internal, wanted, lease = struct.unpack('>BBHHHI', data)
            return [(struct.pack('>BBHIHHI', 0, 128 + opcode, 0, 99, internal, 0, 0), ('192.168.1.1', 5351))]
        network = FakeNetwork(responder)
        self.assertTrue(reach.release(result, socket_factory=network, opener=FakeOpener(), clock=network.clock))
        self.assertEqual([data for data, _a in network.sent],
                         [struct.pack('>BBHHHI', 0, 2, 0, 24611, 0, 0), struct.pack('>BBHHHI', 0, 1, 0, 24611, 0, 0)])
        self.assertFalse(reach.release(result, socket_factory=FakeNetwork(), opener=FakeOpener(), timeout=0.5))

    def test_release_of_nothing_touches_nothing(self):
        network, opener = FakeNetwork(), FakeOpener()
        for held in (reach.Reach('ipv6', ipv6='2a01:e0a::9'), reach.Reach('site', ipv4='1.2.3.4'), reach.Reach('waiting')):
            self.assertTrue(reach.release(held, socket_factory=network, opener=opener))
        self.assertEqual((network.sent, opener.requests), ([], []))
        self.assertFalse(reach.release(reach.Reach('upnp', ipv4='1.2.3.4', mapped=True), socket_factory=network, opener=opener))


if __name__ == '__main__':
    unittest.main()
