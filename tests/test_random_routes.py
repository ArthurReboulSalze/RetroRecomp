"""Reproducible pseudo-random discovery routes; no ROM is needed."""
from pathlib import Path
import tempfile
import unittest

from smsrecomp import random_routes as rr

IDENTITY = 'a' * 64
OTHER = 'b' * 64


class RandomRouteTests(unittest.TestCase):
    def test_same_identity_gives_identical_scripts_and_other_identity_differs(self):
        for console in rr.CONSOLES:
            first = rr.script_text(rr.long_route(console, IDENTITY, 0))
            again = rr.script_text(rr.long_route(console, IDENTITY, 0))
            self.assertEqual(first, again, console)
            self.assertNotEqual(first, rr.script_text(rr.long_route(console, OTHER, 0)), console)
            self.assertNotEqual(first, rr.script_text(rr.long_route(console, IDENTITY, 1)), console)

    def test_routes_are_long_varied_and_within_host_limits(self):
        for console in ('md', 'snes'):
            for route in rr.long_routes(console, IDENTITY, frames=36000, six_buttons=True):
                text = rr.console16_script(route)
                rows = [tuple(int(v) for v in line.split()) for line in text.splitlines()]
                self.assertLessEqual(len(rows), rr.CONSOLE16_LINE_LIMIT)
                self.assertGreater(len(rows), 200, 'a long route must keep playing')
                frames = [row[0] for row in rows]
                self.assertEqual(frames, sorted(set(frames)), 'strictly increasing frames')
                self.assertEqual(frames[0], 0)
                self.assertLess(frames[-1], 36000)
                self.assertTrue(all(0 <= p1 <= 0xFFF and 0 <= p2 <= 0xFFF for _, p1, p2 in rows))
                self.assertEqual(rows[-1][1:], (0, 0), 'the route ends neutral')
        neogeo = rr.long_route('ng', IDENTITY, 0, frames=36000)
        rows = [line.split() for line in rr.neogeo_script(neogeo).splitlines()]
        self.assertLessEqual(len(rows), rr.NEOGEO_LINE_LIMIT)
        self.assertTrue(all(len(row) == 5 for row in rows))
        self.assertTrue(any(row[3] == '1' for row in rows), 'a credit is inserted')
        self.assertTrue(any(row[4] in ('1', '3') for row in rows), 'player 1 presses Start')

    def test_no_opposing_directions_and_buttons_match_each_console(self):
        for console in rr.CONSOLES:
            route = rr.long_route(console, IDENTITY, 2, six_buttons=False)
            for step in route.steps:
                for pad in (step.p1, step.p2):
                    self.assertFalse({'up', 'down'} <= pad or {'left', 'right'} <= pad, console)
                    allowed = set(rr.DIRECTIONS) | set(rr.CONSOLES[console]['main']) | {'start'}
                    if rr.CONSOLES[console]['select']:
                        allowed.add(rr.CONSOLES[console]['select'])
                    if console == 'snes':
                        allowed |= set(rr.CONSOLES['snes']['extra'])
                    self.assertTrue(pad <= allowed, (console, pad))
        three = rr.console16_script(rr.long_route('md', IDENTITY, 0, six_buttons=False))
        self.assertTrue(all(int(line.split()[1]) < 0x100 for line in three.splitlines()),
                        'three-button games never see X/Y/Z or Mode')
        six = rr.console16_script(rr.long_route('md', IDENTITY, 0, six_buttons=True))
        self.assertTrue(any(int(line.split()[1]) & 0x700 for line in six.splitlines()))

    def test_start_presses_are_paired_after_the_opening(self):
        route = rr.long_route('snes', IDENTITY, 0)
        presses = [step.frame for previous, step in zip(route.steps, route.steps[1:])
                   if 'start' in step.p1 and 'start' not in previous.p1]
        opening = [frame for frame in presses if frame < 1500]
        self.assertGreaterEqual(len(opening), 2)
        later = [frame for frame in presses if frame >= 1500]
        self.assertEqual(len(later) % 2, 0, 'pause presses come in pairs')
        self.assertTrue(all(20 <= b - a <= 64 for a, b in zip(later[::2], later[1::2])))
        # A chained route is already in the game: no opening Start presses at
        # all, only the paired pause/resume presses of the body.
        for console in rr.CONSOLES:
            chained = rr.long_route(console, IDENTITY, 1, continues_from='long-1')
            presses = [step.frame for previous, step in zip(chained.steps, chained.steps[1:])
                       if 'start' in step.p1 and 'start' not in previous.p1]
            self.assertEqual(len(presses) % 2, 0, console)
            self.assertTrue(all(20 <= b - a <= 64 for a, b in zip(presses[::2], presses[1::2])), console)
            self.assertEqual(chained.steps[0].frame, 0)
            self.assertEqual((chained.steps[0].p1, chained.steps[0].p2, chained.steps[0].coin), (frozenset(), frozenset(), 0))
            self.assertGreaterEqual(chained.steps[1].frame, rr.CHAIN_SETTLE_FRAMES, console)
            self.assertFalse(any(step.coin for step in chained.steps), 'no new credit on a chained route')

    def test_chained_routes_drop_the_opening_and_replay_the_same_body(self):
        def shape(steps):
            return [(a.p1, a.p2, a.coin, b.frame - a.frame) for a, b in zip(steps, steps[1:])]
        for console in rr.CONSOLES:
            alone = rr.long_route(console, IDENTITY, 1)
            chained = rr.long_route(console, IDENTITY, 1, continues_from='long-1')
            self.assertIsNone(alone.continues_from)
            self.assertEqual(chained.continues_from, 'long-1')
            self.assertEqual((chained.name, chained.seed, chained.index, chained.frames),
                             (alone.name, alone.seed, alone.index, alone.frames), 'same seed, same route identity')
            body, whole = shape(chained.steps[1:]), shape(alone.steps)
            head = body[:40]
            starts = [i for i in range(len(whole)) if whole[i:i + 40] == head]
            self.assertEqual(len(starts), 1, console)
            start = starts[0]
            has_start = rr.CONSOLES[console].get('start', True)
            self.assertGreaterEqual(start, 6 if has_start else 2,
                                    'the standalone opening (Start presses and confirmations) is dropped')
            self.assertEqual(any('start' in step.p1 for step in alone.steps[:start + 1]), has_start, console)
            # Same phases in the same order with the same timing, up to the
            # standalone route's final neutral step; the chained route then
            # keeps playing new phases where the standalone one ended.
            self.assertEqual(whole[start:-1], body[:len(whole) - start - 1], console)
            self.assertGreater(len(chained.steps), len(alone.steps) - start, console)
            self.assertEqual(chained.steps[-1].frame, alone.frames - 1)
            self.assertEqual((chained.steps[-1].p1, chained.steps[-1].p2), (frozenset(), frozenset()))
            self.assertEqual(chained.metadata()['continues_from'], 'long-1')
        self.assertLessEqual(len(rr.console16_script(rr.long_route('md', IDENTITY, 1, six_buttons=True,
                                                                   continues_from='long-1')).splitlines()),
                             rr.CONSOLE16_LINE_LIMIT)

    def test_long_routes_are_independent_by_default_and_chain_on_request(self):
        for console in ('md', 'snes'):
            chained = rr.long_routes(console, IDENTITY, count=3, chain=True)
            self.assertEqual([route.continues_from for route in chained], [None, 'long-1', 'long-2'])
            self.assertEqual([route.name for route in chained], ['long-1', 'long-2', 'long-3'])
            separate = rr.long_routes(console, IDENTITY, count=3)
            self.assertEqual([route.continues_from for route in separate], [None, None, None])
            self.assertEqual([route.name for route in separate], ['long-1', 'long-2', 'long-3'])
            self.assertEqual(rr.script_text(chained[0]), rr.script_text(separate[0]))
            self.assertEqual(rr.script_text(separate[0]), rr.script_text(rr.long_route(console, IDENTITY, 0)))
            self.assertEqual(rr.script_text(separate[1]), rr.script_text(rr.long_route(console, IDENTITY, 1)))
            self.assertNotEqual(rr.script_text(chained[1]), rr.script_text(separate[1]))
            self.assertEqual([route.metadata()['continues_from'] for route in chained], [None, 'long-1', 'long-2'])

    def test_nes_script_uses_names_and_player_two_prefix(self):
        route = rr.long_route('nes', IDENTITY, 0)
        text = rr.nes_script(route)
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith('0 '))
        self.assertTrue(any(' START' in line for line in lines))
        self.assertTrue(any(' 2:' in line for line in lines), 'player 2 taps are emitted')
        for line in lines:
            frame, keys = line.split(' ', 1)
            int(frame)
            keys = keys[2:] if keys.startswith('2:') else keys
            self.assertTrue(keys == '-' or all(k in rr.NES_NAMES.values() for k in keys.split('+')), line)

    def test_written_files_use_ascii_and_line_feeds(self):
        with tempfile.TemporaryDirectory() as temp:
            for console, suffix in (('md', '-inputs.txt'), ('nes', '.input'), ('ng', '.inputs')):
                path = rr.write_route(rr.long_route(console, IDENTITY, 0, frames=3000), Path(temp))
                self.assertEqual(path.name, 'long-1' + suffix)
                raw = path.read_bytes()
                self.assertNotIn(b'\r', raw)
                raw.decode('ascii')
            meta = rr.long_route('md', IDENTITY, 1, frames=3000).metadata()
            self.assertEqual((meta['scenario'], meta['index'], meta['frames']), ('long-2', 1, 3000))
            self.assertEqual(meta['seed'], rr.route_seed('md', IDENTITY, 1))
            self.assertIsNone(meta['continues_from'])

    def test_invalid_requests_are_refused(self):
        with self.assertRaises(ValueError):
            rr.long_route('x68', IDENTITY, 0)
        with self.assertRaises(ValueError):
            rr.long_route('md', IDENTITY, 0, frames=100)

    def test_game_boy_and_sega_adapters_follow_their_host_grammars(self):
        import re
        gb = rr.long_route('gb', IDENTITY, 0, two_players=False)
        items = rr.gameboy_script(gb).split(',')
        self.assertTrue(all(re.fullmatch(r'\d+:[UDLRABST]+:\d+', item) for item in items), items[:5])
        self.assertTrue(any(':S:' in item for item in items), 'Start opens the game')
        starts = [int(item.split(':')[0]) for item in items]
        self.assertEqual(starts, sorted(starts))
        self.assertFalse(any(step.p2 for step in gb.steps), 'one Game Boy player')
        for console in ('sms', 'gg'):
            route = rr.long_route(console, IDENTITY, 0, two_players=False)
            values = rr.sega_press(route)
            self.assertTrue(all(re.fullmatch(r'\d+:[UDLRABS]*', value) for value in values), values[:5])
            self.assertEqual(any('S' in value.split(':')[1] for value in values), console == 'gg',
                             'only the Game Gear has Start')
            self.assertFalse(any(value.split(':')[1] == '' and index == 0 for index, value in enumerate(values)))
            self.assertEqual(rr.script_text(route), '\n'.join(values) + '\n')
        self.assertEqual(rr.gameboy_script(gb), rr.gameboy_script(rr.long_route('gb', IDENTITY, 0, two_players=False)))


if __name__ == '__main__':
    unittest.main()
