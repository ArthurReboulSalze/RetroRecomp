"""The exploration routes of a PC Engine CD: deterministic scripts, frames never going back, and styles that really differ."""
from __future__ import annotations

import sys
import tempfile
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

    def test_a_later_segment_releases_the_pads_and_holds_only_the_styles_own_inputs(self):
        first = pcecd_routes.segment_rows('menu', 0, 3600, 11, 3, False)
        self.assertEqual(first, pcecd_routes.rows('menu', 3600, 11, 3, False))
        later = pcecd_routes.segment_rows('tap', 3600, 7200, 11, 3, False)
        self.assertEqual(later[0], (3600, 0, 0))
        self.assertTrue(all(3600 < row[0] < 7200 for row in later[1:]))
        self.assertTrue(all(row[0] >= 3600 for row in later))


class ChainTests(unittest.TestCase):
    """The segmented exploration with the engine's runs replaced: which style wins and how the route is composed."""

    def test_the_style_that_runs_the_most_new_code_wins_each_segment_and_the_route_is_composed(self):
        # per segment, the code identities each style reaches; segment 1's winner reaches the same count as another, with more new ones
        reached = [{'walk': {1, 2}, 'menu': {1, 2, 3}, 'action': {1}, 'tap': set()},
                   {'walk': {1, 2, 3, 4, 5}, 'menu': {1, 2, 3}, 'action': {7, 8, 9}, 'tap': {6}}]
        calls = []

        def run(executable, folder, name, frames, script, *options, ends_at=None):
            index, style = int(name[1:name.index('-')]), name.split('-', 1)[1]
            options = list(options)
            calls.append((name, frames, ends_at, '--load-state' in options, script.read_text(encoding='ascii')))
            capture = Path(options[options.index('--code-capture') + 1])
            capture.write_text('{"format":"pce-code-capture-2"}\n' + ''.join(
                f'{{"pc":{pc},"mpr":[0],"data":[0],"native_hits":0}}\n' for pc in sorted(reached[index][style])), encoding='utf-8')
            Path(options[options.index('--save-state') + 1]).write_bytes(b'state')
            trace = folder / (name + '.csv')
            trace.write_text('frame,cpu,ram,image,pcm,x\n', encoding='ascii')
            return {'trace': trace, 'frames': frames if ends_at is None else ends_at}

        saved_run, saved_liveness = hu.run, hu.route_liveness
        hu.run, hu.route_liveness = run, lambda trace: {'distinct_pictures': 1}
        try:
            with tempfile.TemporaryDirectory(prefix='rr-pcecd-chain-') as temp:
                text, report = pcecd_routes.chain(Path('observe.exe'), Path(temp), 'ab' * 32, 7200, 3, False, (), lambda *a: None, workers=1)
        finally:
            hu.run, hu.route_liveness = saved_run, saved_liveness
        self.assertEqual([row['style'] for row in report], ['menu', 'action'])          # walk's 5 hold only 4 and 5 as new; action's 3 are all new
        self.assertEqual([row['new_identities'] for row in report], [3, 3])
        self.assertEqual(report[1]['scores']['walk'][0], 2)
        expected = hu._script(pcecd_routes.segment_rows('menu', 0, 3600, pcecd_routes.segment_seed('ab' * 32, 0), 3, False)
                              + pcecd_routes.segment_rows('action', 3600, 7200, pcecd_routes.segment_seed('ab' * 32, 1), 3, False))
        self.assertEqual(text, expected)
        # the first segment starts the machine, a later one continues from the chosen state and ends one frame after the save point
        self.assertEqual({(frames, ends, loaded) for name, frames, ends, loaded, _ in calls if name.startswith('s0-')}, {(3601, None, False)})
        self.assertEqual({(frames, ends, loaded) for name, frames, ends, loaded, _ in calls if name.startswith('s1-')}, {(3601, 7201, True)})


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
