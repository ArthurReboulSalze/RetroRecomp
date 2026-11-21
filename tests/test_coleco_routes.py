"""The ColecoVision's routes (retrorecomp/coleco_routes.py): the script text is what native/coleco_machine/coleco_headless.inc reads, the
walk is deterministic, a route drives controller 1 only and there is no Pause button to press."""
import re
import unittest
from pathlib import Path

from retrorecomp import route_start, scan_levels, coleco_routes as routes

ROOT = Path(__file__).resolve().parents[1]
HEADLESS = (ROOT / 'native/coleco_machine/coleco_headless.inc').read_bytes().decode('utf-8')
MACHINE = (ROOT / 'native/coleco_machine/coleco_machine.h').read_bytes().decode('utf-8')
IDENTITY = 'a' * 64
VARIANT = ((routes.B1,), 2)


class ScriptTests(unittest.TestCase):
    def test_a_script_has_the_lines_the_headless_reader_scans(self):
        self.assertIn('"%lu pad %u %x"', HEADLESS)
        text = routes.script([('pad', 10, 0, 0x11), ('pad', 30, 1, 0x000), ('pad', 40, 0, 0x2C0)])
        self.assertEqual(text, '10 pad 0 011\n30 pad 1 000\n40 pad 0 2C0\n')

    def test_the_events_are_written_in_frame_order(self):
        text = routes.script([('pad', 30, 0, 1), ('pad', 10, 0, 2)])
        self.assertEqual(text, '10 pad 0 002\n30 pad 0 001\n')

    def test_the_pad_bits_are_the_machines(self):
        for name, value in (('UP', 1), ('DOWN', 2), ('LEFT', 4), ('RIGHT', 8), ('B1', 16), ('B2', 32)):
            self.assertRegex(MACHINE, rf'CV_PAD_{name} = {value}\b')
            self.assertEqual(getattr(routes, name), value)
        self.assertRegex(MACHINE, r'CV_PAD_KEY_SHIFT = 6\b')
        self.assertEqual(routes.KEY_SHIFT, 6)
        for name, lines in (('1', 0x02), ('2', 0x08)):
            self.assertRegex(MACHINE, rf'CV_KEY_{name} = 0x{lines:02X}\b')
            self.assertEqual(getattr(routes, f'KEY_{name}'), lines << 6)
        self.assertEqual(routes.MASK, 0x0BFF)                                 # CV_PAD_MASK: 0x0FFF without the reserved bit 10
        self.assertRegex(MACHINE, r'CV_PAD_MASK = 0x0FFF & ~\(1 << 10\)')

    def test_every_line_of_a_route_is_a_pad_line_of_controller_one_inside_the_mask(self):
        for _name, _frames, text in routes.routes(IDENTITY, frames=3600, level='thorough', variant=VARIANT):
            for line in text.splitlines():
                self.assertRegex(line, r'^\d+ pad 0 [0-9A-F]{3}$')
                self.assertEqual(int(line.split()[3], 16) & ~routes.MASK, 0)

    def test_no_route_presses_a_reserved_bit_or_names_anything_but_pad_events(self):
        for _name, _frames, text in routes.routes(IDENTITY, frames=3600, level='thorough', variant=VARIANT):
            self.assertNotIn('pause', text)
            for line in text.splitlines():
                self.assertEqual(int(line.split()[3], 16) & (1 << 10), 0)
                self.assertEqual(int(line.split()[3], 16) & (1 << 11), 0)       # the host's own flag is never scripted


class RouteTests(unittest.TestCase):
    def test_the_levels_give_the_scan_levels_routes(self):
        names = lambda level: [name for name, _, _ in routes.routes(IDENTITY, frames=3600, level=level)]
        self.assertEqual(names('quick'), ['play'])
        self.assertEqual(names('standard'), ['attract', 'play'])
        self.assertEqual(names('extended'), ['attract', 'play', 'long-1'])
        self.assertEqual(names('thorough'), ['attract', 'play', 'long-1', 'long-2'])

    def test_the_lengths_are_the_levels(self):
        rows = {name: frames for name, frames, _ in routes.routes(IDENTITY, frames=1000, level='thorough')}
        self.assertEqual(rows, {'attract': 1000, 'play': routes.PLAY_FRAMES, 'long-1': scan_levels.LONG_ROUTE_FRAMES,
                                'long-2': scan_levels.LONG_ROUTE_FRAMES})

    def test_attract_has_no_input(self):
        self.assertEqual(routes.routes(IDENTITY, frames=3600, level='standard')[0], ('attract', 3600, ''))

    def test_a_route_is_determined_by_the_cartridge(self):
        first = routes.routes(IDENTITY, frames=3600, level='extended', variant=VARIANT)
        self.assertEqual(first, routes.routes(IDENTITY, frames=3600, level='extended', variant=VARIANT))
        self.assertNotEqual(first[1][2], routes.routes('b' * 64, frames=3600, level='extended', variant=VARIANT)[1][2])
        self.assertNotEqual(first[2][2], first[1][2])
        self.assertEqual(routes.route_seed(IDENTITY, 'long-2') - routes.route_seed(IDENTITY, 'long-1'), 7919)

    def test_the_start_presses_come_after_the_bios_title_and_the_walk_after_them(self):
        events = routes.events(3600, routes.route_seed(IDENTITY, 'play'), ((routes.B2,), 3))
        presses = [event for event in events if event[1] < routes.walk_start(3)]
        first, step, held = routes.FIRST_PRESS, routes.PRESS_SPACING, routes.PRESS_FRAMES
        self.assertEqual([(frame, bits) for _, frame, _, bits in presses],
                         [(first, 32), (first + held, 0), (first + step, 32), (first + step + held, 0), (first + 2 * step, 32),
                          (first + 2 * step + held, 0)])
        self.assertTrue(all(event[1] >= routes.walk_start(3) for event in events[len(presses):]))
        self.assertGreaterEqual(routes.FIRST_PRESS, 600)                       # the BIOS's title screen is over

    def test_a_sequence_of_two_buttons_presses_them_in_turn(self):
        events = routes.events(3600, 7, ((routes.KEY_1, routes.B1), 3))
        presses = [bits for _, frame, _, bits in events if frame < routes.walk_start(3) and bits]
        self.assertEqual(presses, [routes.KEY_1, routes.B1, routes.KEY_1])

    def test_the_quiet_part_of_the_walk_holds_directions_only(self):
        start = routes.walk_start(1)
        events = routes.events(6000, 12345, ((routes.B1,), 1))
        buttons = routes.B1 | routes.B2 | routes.KEY_1 | routes.KEY_2
        for _, frame, _, bits in events:
            if start <= frame < start + routes.QUIET_WALK:
                self.assertEqual(bits & buttons, 0, frame)

    def test_an_event_changes_what_is_held(self):
        events = routes.events(6000, 99, ((routes.KEY_1, routes.B1), 2))
        bits = [event[3] for event in events]
        self.assertTrue(all(a != b for a, b in zip(bits, bits[1:])))
        self.assertEqual(sorted(event[1] for event in events), [event[1] for event in events])


class StartTests(unittest.TestCase):
    def test_the_variants_are_sequences_by_presses_that_leave_ten_seconds_of_walk(self):
        found = routes.candidates(3600)
        self.assertEqual(len(found), 8)                                        # (fire), (key 1) x 1..3 and (key 1, fire) x 2..3
        self.assertEqual({presses for _, presses in found}, {1, 2, 3})
        self.assertEqual(routes.candidates(1000), [])                          # too short for any walk
        for sequence, presses in found:
            self.assertLessEqual(routes.walk_start(presses) + 600, 3600)
            self.assertGreaterEqual(presses, len(sequence))                    # every button of a sequence is pressed once at least

    def test_the_names_say_the_buttons_and_the_presses(self):
        self.assertEqual([routes.variant_name((s, 2)) for s in routes.START_SEQUENCES], ['fire1x2', 'key1x2', 'key1+fire1x2'])

    def test_the_tie_break_is_the_fewest_presses_then_the_shortest_sequence_then_the_order(self):
        order = sorted(routes.candidates(3600), key=routes.variant_order)
        self.assertEqual(order[0], ((routes.B1,), 1))
        self.assertEqual(order[1], ((routes.KEY_1,), 1))
        self.assertEqual(order[-1][1], 3)
        self.assertEqual(order[-1][0], (routes.KEY_1, routes.B1))

    def test_route_start_picks_the_variant_that_reaches_most_with_this_tie_break(self):
        alive = {'last_picture_change_frame': 3590}
        results = {v: {'liveness': alive, 'divergence': 5, 'reach': 3} for v in routes.candidates(3600)}
        self.assertEqual(route_start.choose_start(results, 3600, routes.variant_order), ((routes.B1,), 1))
        results[((routes.KEY_1, routes.B1), 2)]['reach'] = 9
        chosen = route_start.choose_start(results, 3600, routes.variant_order)
        self.assertEqual(chosen, ((routes.KEY_1, routes.B1), 2))
        self.assertTrue(re.fullmatch(r'(fire[12]|key[12])(\+(fire[12]|key[12]))*x[123]', routes.variant_name(chosen)))


if __name__ == '__main__':
    unittest.main()
