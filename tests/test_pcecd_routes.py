"""The exploration routes of a PC Engine CD: deterministic scripts, frames never going back, and styles that really differ."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retrorecomp import pce_conversion as hu, pcecd_routes  # noqa: E402


class StyleTests(unittest.TestCase):
    def test_every_style_is_deterministic_and_its_frames_never_go_back(self):
        for style in pcecd_routes.STYLES:
            with self.subTest(style):
                first = pcecd_routes.rows(style, 18000, 0xABCDEF, 3, False)
                again = pcecd_routes.rows(style, 18000, 0xABCDEF, 3, False)
                self.assertEqual(first, again)
                self.assertTrue(first)
                self.assertTrue(all(a[0] <= b[0] for a, b in zip(first, first[1:])))
                self.assertLess(first[-1][0], 18000)
                self.assertEqual(pcecd_routes.script(style, 18000, 0xABCDEF, 3, False), hu._script(first))

    def test_the_styles_press_different_things(self):
        by = {style: pcecd_routes.rows(style, 6000, 7, 2, True) for style in pcecd_routes.STYLES}
        pads = {style: {row[1] for row in rows} for style, rows in by.items()}
        # the menu style steps a cursor down and answers it: Down alone, then I alone; it never holds a direction with a button
        self.assertIn(hu.DOWN, pads['menu'])
        self.assertIn(hu.I, pads['menu'])
        self.assertFalse(any(pad & (hu.I | hu.II) and pad & (hu.UP | hu.DOWN | hu.LEFT | hu.RIGHT) for pad in pads['menu']))
        # the action style holds directions with a button
        self.assertTrue(any(pad & hu.I and pad & hu.RIGHT for pad in pads['action']))
        self.assertNotEqual(by['menu'], by['action'])
        self.assertNotEqual(by['walk'], by['action'])

    def test_the_start_is_the_same_for_every_style(self):
        starts = {style: pcecd_routes.rows(style, 6000, 7, 3, True)[:12] for style in pcecd_routes.STYLES}
        self.assertEqual(starts['menu'], starts['action'])
        self.assertEqual(starts['menu'], starts['walk'])

    def test_an_unknown_style_is_refused(self):
        with self.assertRaises(ValueError):
            pcecd_routes.rows('guess', 1000, 1)

    def test_a_style_is_scored_by_code_identities_then_pictures(self):
        self.assertGreater(pcecd_routes.score({'capture_identities': 9}, {'distinct_pictures': 1}), pcecd_routes.score({'capture_identities': 8}, {'distinct_pictures': 99}))
        self.assertGreater(pcecd_routes.score({'capture_identities': 9}, {'distinct_pictures': 5}), pcecd_routes.score({'capture_identities': 9}, {'distinct_pictures': 4}))
        self.assertEqual(pcecd_routes.score({}, {}), (0, 0))


class LobbyTests(unittest.TestCase):
    def test_the_report_names_the_system_card_at_the_top_level_for_the_lobby(self):
        # The lobby compares a firmware only from a top-level record with a sha256 (netplay/lobby_check.FIRMWARE_KEYS): two players with another System Card are
        # refused before the launch. The nested firmware.system_card record is not seen by it.
        from retrorecomp.netplay import lobby_check
        source = (Path(__file__).resolve().parents[1] / 'retrorecomp' / 'pcecd_conversion.py').read_text(encoding='utf-8')
        self.assertIn("'bios': card.metadata()", source)
        digest = 'e' * 64
        one = lobby_check.firmware_digest({'bios': {'sha256': digest, 'kind': 'player'}})
        other = lobby_check.firmware_digest({'bios': {'sha256': 'd' * 64, 'kind': 'player'}})
        self.assertNotEqual(one, bytes(32))
        self.assertNotEqual(one, other)
        self.assertEqual(lobby_check.firmware_digest({'firmware': {'system_card': {'sha256': digest}}}), bytes(32))


class MultitapTableTests(unittest.TestCase):
    def test_the_table_is_reviewed_data_keyed_by_disc_digest(self):
        from retrorecomp import pcecd
        self.assertTrue(pcecd.MULTITAP_PLAYERS)
        for digest, players in pcecd.MULTITAP_PLAYERS.items():
            self.assertRegex(digest, r'^[0-9a-f]{64}$')
            self.assertIn(players, (3, 4))             # two is what every other disc gets; a room seats four

        class Disc:
            def __init__(self, sha256):
                self.sha256 = sha256
        self.assertEqual(pcecd.players_of(Disc('0' * 64)), 2)
        listed = next(iter(pcecd.MULTITAP_PLAYERS))
        self.assertEqual(pcecd.players_of(Disc(listed)), pcecd.MULTITAP_PLAYERS[listed])


if __name__ == '__main__':
    unittest.main()
