"""How an Internet room's host becomes reachable (retrorecomp/netplay/reach.py): parsing only, on answers written in the
shape real boxes give. No socket to a router, no Internet, no ROM."""
import struct
import unittest

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


if __name__ == '__main__':
    unittest.main()
