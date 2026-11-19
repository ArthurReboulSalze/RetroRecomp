"""The Internet room's side of the converter (the window's contract of 19 November 2026): the host's config and key, the
guest's key or typed form, the model's fields, and one real room on loopback joined with a key. 127.0.0.1 only, under
`tests`; nothing reaches a router or the Internet. No ROM."""
import socket
import tempfile
import threading
import unittest

from retrorecomp.netplay import internet_key, invitation, lan_transport, lobby_client
from retrorecomp.netplay.invitation import InvitationError

SECRET = bytes(range(16))


class ConfigTests(unittest.TestCase):
    def test_the_host_config_of_an_internet_room_and_its_key(self):
        with tempfile.TemporaryDirectory() as folder:
            config, key = lobby_client.host_config('192.168.1.58', 24611, 'Arthur', 'per_player', folder, internet=True,
                                                   public_address='82.65.10.20')
            self.assertTrue(config['room']['internet'])
            room = internet_key.parse_key(key)
            self.assertEqual((room.address, room.port, room.secret.hex()), ('82.65.10.20', 24611, config['room']['secret']))
            config, key = lobby_client.host_config('192.168.1.58', 24611, 'Arthur', 'per_player', folder, internet=True)
            self.assertEqual(key, '')                                 # no public address yet: no key to show
            config, text = lobby_client.host_config('192.168.1.58', 24611, 'Arthur', 'per_player', folder)
            self.assertFalse(config['room']['internet'])
            self.assertTrue(text.startswith('rr1:lan:192.168.1.58:24611:'))
            self.assertFalse(lobby_client.INTERNET)                   # greyed in the window until the room works over the Internet

    def test_the_guest_takes_a_key_an_invitation_or_the_typed_form_and_says_what_is_wrong(self):
        key = internet_key.format_key(24611, SECRET, '82.65.10.20')
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(lobby_client.guest_config(key, 'Nadia', folder)['room']['invitation'], key)
            lan = invitation.format_invitation('192.168.1.20', 24611, SECRET)
            self.assertEqual(lobby_client.guest_config(lan, 'Nadia', folder)['room']['invitation'], lan)
            typed = lobby_client.guest_config_manual('82.65.10.20', '', internet_key.format_code(SECRET), 'Nadia', folder)
            self.assertEqual(internet_key.parse_key(typed['room']['invitation']).secret, SECRET)
            for text, code in ((key[:-2] + ('A' if key[-2] != 'A' else 'B') + key[-1], 'typo'), ('RR3-' + key[4:], 'other_version'),
                               ('hello', 'bad'), ('rr1:lan:8.8.8.8:24611:' + invitation.encode_secret(SECRET), 'bad')):
                with self.assertRaises(InvitationError) as raised:
                    lobby_client.guest_config(text, 'Nadia', folder)
                self.assertEqual(raised.exception.code, code, text[:12])
            with self.assertRaises(InvitationError) as raised:
                code = internet_key.format_code(SECRET)
                lobby_client.guest_config_manual('82.65.10.20', '24611', code[:-1] + ('7' if code[-1] != '7' else '8'), 'Nadia', folder)
            self.assertEqual(raised.exception.code, 'typo')

    def test_the_model_makes_the_key_when_the_room_opens_and_follows_the_public_address(self):
        model = lobby_client.LobbyModel()
        model.secret, model.internet, model.reach = SECRET, True, 'probing'
        model.apply({'event': 'room_open', 'address': '192.168.1.58', 'port': 24611})
        self.assertEqual((model.key, internet_key.parse_code(model.code)), ('', SECRET))
        model.set_public('82.65.10.20', 'upnp')
        self.assertEqual((model.reach, model.public, internet_key.parse_key(model.key).address), ('upnp', '82.65.10.20', '82.65.10.20'))
        self.assertEqual(model.invitation, model.key)
        controller = lobby_client.LobbyController(library=None, model=model)
        controller.set_public_address(' 2a01:e0a::5 ')
        self.assertEqual((model.reach, internet_key.parse_key(model.key).addresses), ('typed', ('2a01:e0a::5',)))
        model.apply({'event': 'launching', 'tier': 'rollback', 'prediction': 5})
        self.assertEqual(model.link['path'], 'ipv4')
        local = lobby_client.LobbyModel()
        local.apply({'event': 'launching', 'tier': 'delay'})
        self.assertEqual(local.link['path'], 'lan')
        self.assertEqual(lan_transport.room_code(lan_transport.PORT_CLOSED), 'port_closed')


def loopback_refused():
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(('127.0.0.1', 0))
            probe.listen(1)
        finally:
            probe.close()
    except OSError as error:
        return f'loopback sockets are refused here ({error})'
    return None


@unittest.skipIf(loopback_refused(), loopback_refused() or '')
class LoopbackInternetRoomTests(unittest.TestCase):
    def test_a_guest_joins_an_internet_room_with_its_key_and_a_wrong_key_gets_port_silence(self):
        events = []
        host = lan_transport.RoomHost('127.0.0.1', 0, SECRET, 4, name='Arthur', tests=True, internet=True, on_event=events.append)
        port = host.open()
        try:
            key = internet_key.format_key(port, SECRET, '127.0.0.1', tests=True)
            guest = lan_transport.RoomGuest(internet_key.parse_key(key, tests=True), 'Nadia', tests=True)
            guest.connect()
            self.assertTrue(guest.internet)
            joined = threading.Event()
            for _ in range(100):
                if any(event.get('event') == 'joined' for event in list(events)):
                    joined.set()
                    break
                threading.Event().wait(0.05)
            self.assertTrue(joined.is_set(), events)
            guest.close()
            wrong = internet_key.format_key(port, bytes(16), '127.0.0.1', tests=True)
            with self.assertRaises(lan_transport.RoomError) as refused:
                lan_transport.RoomGuest(internet_key.parse_key(wrong, tests=True), 'Mallory', tests=True).connect(timeout=2.0)
            self.assertIn(refused.exception.code, ('unreachable', 'port_closed'))
        finally:
            host.close()


if __name__ == '__main__':
    unittest.main()
