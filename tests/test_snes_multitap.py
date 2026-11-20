"""The Super Multitap list of the Super Nintendo: reviewed data keyed by the dump, and what the converter does with it."""
import re
import unittest

from retrorecomp import snes_multitap
from retrorecomp.systems import find_profile


class MultitapListTests(unittest.TestCase):
    def test_every_entry_is_a_dump_a_title_a_pad_count_and_a_source(self):
        for sha, entry in snes_multitap.MULTITAP_GAMES.items():
            self.assertRegex(sha, r'^[0-9a-f]{64}$')
            self.assertTrue(entry['title'] and entry['source'])
            self.assertIn(entry['pads'], (3, 4))   # the host kit seats four players; a tap game uses at least three pads

    def test_a_game_that_is_not_listed_has_no_tap(self):
        self.assertEqual(snes_multitap.multitap_pads('0' * 64), 0)
        for sha, entry in snes_multitap.MULTITAP_GAMES.items():
            self.assertEqual(snes_multitap.multitap_pads(sha), entry['pads'])

    def test_the_profile_seats_four_players_as_a_ceiling_and_answers_a_session(self):
        profile = find_profile('snes')
        self.assertTrue(profile.netplay_session)
        self.assertEqual(profile.netplay_seats, 4)
        self.assertTrue(profile.netplay_seats_ceiling)

    def test_the_game_header_only_names_a_listed_game(self):
        from pathlib import Path
        import tempfile
        from types import SimpleNamespace
        from retrorecomp import supernintendo
        for sha, expected in (('0' * 64, False), (next(iter(snes_multitap.MULTITAP_GAMES)), True)):
            rom = SimpleNamespace(sha256=sha, data=b'\0' * 0x8000, mapping='lorom', title='X', standard='ntsc')
            with tempfile.TemporaryDirectory() as folder:
                try:
                    supernintendo.write_profile(Path(folder), rom, 'X')
                except Exception:   # the rest of the generation of a blank image is not this test's business: the header is written first
                    pass
                header = Path(folder, 'retro_snes_game.h')
                self.assertTrue(header.is_file())
                self.assertEqual(bool(re.search(r'#define RR_SN_MULTITAP \d', header.read_text())), expected)


if __name__ == '__main__':
    unittest.main()
