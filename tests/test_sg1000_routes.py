"""The SG-1000's routes (retrorecomp/sg1000_routes.py): the script text is what native/sg1000_machine/sg1000_headless.inc reads, the
walk is deterministic and the Pause button is never pressed by a route."""
import re
import unittest
from pathlib import Path

from retrorecomp import route_start, scan_levels, sg1000_routes as routes

ROOT = Path(__file__).resolve().parents[1]
HEADLESS = (ROOT / 'native/sg1000_machine/sg1000_headless.inc').read_bytes().decode('utf-8')
MACHINE = (ROOT / 'native/sg1000_machine/sg1000_machine.h').read_bytes().decode('utf-8')
IDENTITY = 'a' * 64
VARIANT = (routes.B1, 2)


class ScriptTests(unittest.TestCase):
    def test_a_script_has_the_lines_the_headless_reader_scans(self):
        self.assertIn('"%lu pad %u %x"', HEADLESS)
        self.assertIn('"%lu pause"', HEADLESS)
        text = routes.script([('pad', 10, 0, 0x11), ('pause', 20), ('pad', 30, 1, 0x00)])
        self.assertEqual(text, '10 pad 0 11\n20 pause\n30 pad 1 00\n')

    def test_the_events_are_written_in_frame_order(self):
        text = routes.script([('pad', 30, 0, 1), ('pad', 10, 0, 2)])
        self.assertEqual(text, '10 pad 0 02\n30 pad 0 01\n')

    def test_the_pad_bits_are_the_machines(self):
        for name, value in (('UP', 1), ('DOWN', 2), ('LEFT', 4), ('RIGHT', 8), ('B1', 16), ('B2', 32)):
            self.assertRegex(MACHINE, rf'SG_PAD_{name} = {value}\b')
            self.assertEqual(getattr(routes, name), value)

    def test_every_line_of_a_route_is_a_pad_line_of_pad_one(self):
        for _name, _frames, text in routes.routes(IDENTITY, frames=1800, level='thorough', variant=VARIANT):
            for line in text.splitlines():
                self.assertRegex(line, r'^\d+ pad 0 [0-9A-F]{2}$')
                self.assertEqual(int(line.split()[3], 16) & ~0x3F, 0)

    def test_no_route_presses_pause(self):
        for _name, _frames, text in routes.routes(IDENTITY, frames=1800, level='thorough', variant=VARIANT):
            self.assertNotIn('pause', text)


class RouteTests(unittest.TestCase):
    def test_the_levels_give_the_scan_levels_routes(self):
        names = lambda level: [name for name, _, _ in routes.routes(IDENTITY, frames=1800, level=level)]
        self.assertEqual(names('quick'), ['play'])
        self.assertEqual(names('standard'), ['attract', 'play'])
        self.assertEqual(names('extended'), ['attract', 'play', 'long-1'])
        self.assertEqual(names('thorough'), ['attract', 'play', 'long-1', 'long-2'])

    def test_the_lengths_are_the_levels(self):
        rows = {name: frames for name, frames, _ in routes.routes(IDENTITY, frames=1000, level='thorough')}
        self.assertEqual(rows, {'attract': 1000, 'play': routes.PLAY_FRAMES, 'long-1': scan_levels.LONG_ROUTE_FRAMES,
                                'long-2': scan_levels.LONG_ROUTE_FRAMES})

    def test_attract_has_no_input(self):
        self.assertEqual(routes.routes(IDENTITY, frames=1800, level='standard')[0], ('attract', 1800, ''))

    def test_a_route_is_determined_by_the_cartridge(self):
        first = routes.routes(IDENTITY, frames=1800, level='extended', variant=VARIANT)
        self.assertEqual(first, routes.routes(IDENTITY, frames=1800, level='extended', variant=VARIANT))
        self.assertNotEqual(first[1][2], routes.routes('b' * 64, frames=1800, level='extended', variant=VARIANT)[1][2])
        self.assertNotEqual(first[2][2], first[1][2])
        self.assertEqual(routes.route_seed(IDENTITY, 'long-2') - routes.route_seed(IDENTITY, 'long-1'), 7919)

    def test_the_start_presses_come_first_and_the_walk_after(self):
        events = routes.events(1800, routes.route_seed(IDENTITY, 'play'), (routes.B2, 3))
        presses = [event for event in events if event[1] < routes.walk_start(3)]
        self.assertEqual([(frame, bits) for _, frame, _, bits in presses],
                         [(180, 32), (186, 0), (360, 32), (366, 0), (540, 32), (546, 0)])
        self.assertTrue(all(event[1] >= routes.walk_start(3) for event in events[len(presses):]))

    def test_the_quiet_part_of_the_walk_holds_directions_only(self):
        start = routes.walk_start(1)
        events = routes.events(3000, 12345, (routes.B1, 1))
        for _, frame, _, bits in events:
            if start <= frame < start + routes.QUIET_WALK:
                self.assertEqual(bits & (routes.B1 | routes.B2), 0, frame)

    def test_an_event_changes_what_is_held(self):
        events = routes.events(3000, 99, (routes.B1 | routes.B2, 2))
        bits = [event[3] for event in events]
        self.assertTrue(all(a != b for a, b in zip(bits, bits[1:])))
        self.assertEqual(events[-1][3], 0) if events and events[-1][1] < 3000 else None
        self.assertEqual(sorted(event[1] for event in events), [event[1] for event in events])


class StartTests(unittest.TestCase):
    def test_the_variants_are_buttons_by_presses_that_leave_ten_seconds_of_walk(self):
        found = routes.candidates(1800)
        self.assertEqual(len(found), 9)
        self.assertEqual({presses for _, presses in found}, {1, 2, 3})
        self.assertEqual(routes.candidates(1000), [])                      # too short for any walk
        for buttons, presses in found:
            self.assertLessEqual(routes.walk_start(presses) + 600, 1800)

    def test_the_names_say_the_buttons_and_the_presses(self):
        self.assertEqual([routes.variant_name((b, 2)) for b in routes.START_BUTTONS], ['1x2', '2x2', '12x2'])

    def test_the_tie_break_is_the_fewest_presses_then_the_fewest_buttons_then_button_one(self):
        order = sorted(routes.candidates(1800), key=routes.variant_order)
        self.assertEqual(order[0], (routes.B1, 1))
        self.assertEqual(order[1], (routes.B2, 1))
        self.assertEqual(order[2], (routes.B1 | routes.B2, 1))
        self.assertEqual(order[-1][1], 3)

    def test_route_start_picks_the_variant_that_reaches_most_with_this_tie_break(self):
        alive = {'last_picture_change_frame': 1790}
        results = {v: {'liveness': alive, 'divergence': 5, 'reach': 3} for v in routes.candidates(1800)}
        self.assertEqual(route_start.choose_start(results, 1800, routes.variant_order), (routes.B1, 1))
        results[(routes.B2, 2)]['reach'] = 9
        self.assertEqual(route_start.choose_start(results, 1800, routes.variant_order), (routes.B2, 2))
        self.assertTrue(re.fullmatch(r'[12]{1,2}x[123]', routes.variant_name((routes.B2, 2))))


if __name__ == '__main__':
    unittest.main()
