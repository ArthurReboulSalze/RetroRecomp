"""The Mega Drive's choice of multitap (retrorecomp/megadrive_multitap.py), on authored cartridge bytes: no ROM."""
import hashlib
import unittest

from retrorecomp import megadrive_multitap as multitap

BLANK = bytes(0x200)


class Cartridge:
    def __init__(self, data: bytes, sha256: str | None = None):
        self.data = data
        self.sha256 = sha256 or hashlib.sha256(data).hexdigest()


def cartridge(io=b'J', code=b''):
    data = bytearray(0x400)
    data[0x100:0x110] = b'SEGA MEGA DRIVE '
    data[0x190:0x190 + len(io)] = io
    return Cartridge(bytes(data) + code)


class MultitapTests(unittest.TestCase):
    def test_an_ordinary_cartridge_has_two_players_and_no_adapter(self):
        self.assertEqual(multitap.detect(cartridge()), {'multitap': None, 'players': 2})
        self.assertIn('#define RR_MD_MULTITAP 0\n', multitap.header_lines(cartridge()))
        self.assertIn('#define RR_MD_PLAYERS 2\n', multitap.header_lines(cartridge()))

    def test_the_header_declares_the_team_player(self):
        found = multitap.detect(cartridge(io=b'J4'))
        self.assertEqual(found, {'multitap': 'team_player_and_4_way_play', 'players': 4})
        self.assertIn('#define RR_MD_MULTITAP 1\n', multitap.header_lines(cartridge(io=b'J4')))

    def test_the_games_own_4_way_play_probe_selects_the_ports(self):
        probe = b'\x13\xfc\x00\x7c\x00\xa1\x00\x05'   # move.b #$7C,($A10005).l
        self.assertEqual(multitap.detect(cartridge(code=probe))['multitap'], 'team_player_and_4_way_play')
        # Another value written to port B, or $7C written elsewhere, is not the probe.
        self.assertIsNone(multitap.detect(cartridge(code=b'\x13\xfc\x00\x40\x00\xa1\x00\x05'))['multitap'])
        self.assertIsNone(multitap.detect(cartridge(code=b'\x13\xfc\x00\x7c\x00\xa1\x00\x03'))['multitap'])

    def test_the_reviewed_tables_name_the_j_cart_and_undeclared_team_player_dumps(self):
        sha = next(iter(multitap.JCART_DUMPS))
        self.assertEqual(multitap.detect(Cartridge(BLANK, sha)), {'multitap': 'j_cart', 'players': 4})
        self.assertIn('#define RR_MD_MULTITAP 2\n', multitap.header_lines(Cartridge(BLANK, sha)))
        team = next(iter(multitap.TEAM_PLAYER_DUMPS))
        self.assertEqual(multitap.detect(Cartridge(BLANK, team))['multitap'], 'team_player_and_4_way_play')

    def test_the_tables_hold_full_sha256_identities(self):
        for table in (multitap.JCART_DUMPS, multitap.TEAM_PLAYER_DUMPS):
            for sha in table:
                self.assertRegex(sha, r'^[0-9a-f]{64}$')
        self.assertFalse(set(multitap.JCART_DUMPS) & set(multitap.TEAM_PLAYER_DUMPS))


if __name__ == '__main__':
    unittest.main()
