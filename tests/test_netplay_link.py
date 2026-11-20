"""The link cable of the handhelds in a session (the contract of 20 Nov 2026, .build notes LINK_CONTRACT): a fourth input mode,
'link', one console per seat; the game is told by SETUP_LINK and says it can link by CAP_LINK; the lobby offers it for a
machine only once its profile's `netplay_link_seats` is set (after a two-seat proof). No game here."""
import struct
import unittest
from unittest.mock import patch

from retrorecomp.netplay import control, seat_map, session_pipe as pipe


def hello(caps=pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT | pipe.CAP_LINK, players=1):
    return pipe.Hello(pipe.ABI, players, caps, 1024, 59727, 'Game Boy')


class LinkModeTests(unittest.TestCase):
    def test_the_mode_exists_on_the_wire_and_in_the_header(self):
        self.assertEqual(seat_map.LINK, 3)
        self.assertEqual(seat_map.NAMES[seat_map.LINK], 'link')
        self.assertIn(seat_map.LINK, control.SHARINGS)
        self.assertEqual(pipe.SHARING_LINK, seat_map.LINK)
        self.assertEqual(seat_map.ports(seat_map.LINK, 2), 2)          # one console, one port, per seat
        words, _state = seat_map.step(seat_map.start(seat_map.LINK, 2), [(0x11, 0), (0x22, 0)])
        self.assertEqual(words, (0x11, 0x22))

    def test_a_handheld_links_only_once_its_profile_says_so(self):
        self.assertEqual(seat_map.link_seats('gb'), 2)                  # the Game Boy's link is proven (20 Nov 2026): two consoles
        with patch.object(seat_map, 'link_seats', lambda machine: 0):    # a handheld whose profile does not say so yet
            self.assertFalse(seat_map.allowed('gb', seat_map.LINK))
            self.assertEqual(seat_map.effective('gb', seat_map.LINK), seat_map.SHARED_ALL)
        self.assertEqual(seat_map.effective('nes', seat_map.LINK), seat_map.PER_PLAYER)
        with patch.object(seat_map, 'link_seats', lambda machine: 2 if machine == 'gb' else 0):
            self.assertTrue(seat_map.allowed('gb', seat_map.LINK))
            self.assertEqual(seat_map.effective('gb', seat_map.LINK), seat_map.LINK)
            self.assertEqual(seat_map.effective('gb', seat_map.PER_PLAYER), seat_map.SHARED_ALL)   # the other modes as before

    def test_the_game_must_say_it_links_and_setup_tells_it(self):
        pipe.check_hello(hello(), 2, link=True)
        with self.assertRaisesRegex(pipe.Refused, 'link cable'):
            pipe.check_hello(hello(caps=pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT), 2, link=True)
        with self.assertRaisesRegex(pipe.Refused, 'seats asked'):
            pipe.check_hello(hello(), 1, link=True)
        payload = pipe.setup(1, 2, 8, guest=True, options='speed=1', link=True)[4:]
        self.assertEqual(struct.unpack_from('<BBBB', payload), (1, 2, 8, pipe.SETUP_GUEST | pipe.SETUP_LINK))
        self.assertEqual(pipe.setup(0, 2)[4 + 3], 0)

    def test_the_lobby_seats_as_many_as_the_link_plays(self):
        from retrorecomp.netplay.lobby import HostLobby
        from tests.test_netplay_lobby import game
        lobby = HostLobby('Arthur')
        lobby.game = game(machine='gb', seats_max=1)
        with patch.object(seat_map, 'link_seats', lambda machine: 2 if machine == 'gb' else 0):
            self.assertIsNone(lobby.set_sharing(seat_map.LINK))
            self.assertEqual(lobby.sharing, seat_map.LINK)
            self.assertEqual(lobby.seat_limit(), 2)


if __name__ == '__main__':
    unittest.main()
