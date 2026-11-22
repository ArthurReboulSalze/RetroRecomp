"""The Amstrad CPC conversion's play route (retrorecomp/cpc_routes.py): seeded by the disk, in order, within the machine's keys
and sticks, the title-screen keys first."""
import unittest

from retrorecomp import cpc_routes


class RouteTests(unittest.TestCase):
    def test_the_same_disk_plays_the_same_route(self):
        one = cpc_routes.play_events(3600, 'a' * 64)
        self.assertEqual(one, cpc_routes.play_events(3600, 'a' * 64))
        self.assertNotEqual(one, cpc_routes.play_events(3600, 'b' * 64))

    def test_events_in_order_within_the_route_and_the_machine(self):
        events = cpc_routes.play_events(3600, 'c' * 64)
        frames = [event[0] for event in events]
        self.assertEqual(frames, sorted(frames))
        self.assertGreaterEqual(frames[0], cpc_routes.PLAY_FROM)
        self.assertLess(frames[-1], 3600)
        for _frame, kind, code, value in events:
            if kind == 'key':
                self.assertTrue(0 <= code < 80 and value in (0, 1))
            else:
                self.assertEqual(code, 0)
                self.assertLessEqual(value, 0x3F)

    def test_the_title_screen_keys_come_first(self):
        events = cpc_routes.play_events(3600, 'd' * 64)
        pressed = [(kind, code if kind == 'key' else value) for _f, kind, code, value in events if value]
        self.assertEqual(pressed[:2], [('key', cpc_routes.KEY_N), ('key', cpc_routes.KEY_RETURN)])
        first = [event for event in events if event[0] < cpc_routes.PLAY_FROM + len(cpc_routes.FIRST_ANSWERS) * cpc_routes.ANSWER_GAP]
        self.assertFalse([event for event in first if event[1] == 'joy' and event[3] & 0x0F])   # no direction while answering
        keys = {code for kind, code in pressed if kind == 'key'}
        self.assertTrue({cpc_routes.KEY_SPACE, cpc_routes.KEY_N, cpc_routes.KEY_RETURN, cpc_routes.KEY_1} <= keys)

    def test_a_long_route_presses_the_start_keys_again_past_the_conversions_routes(self):
        events = cpc_routes.play_events(18000, 'e' * 64)
        frames = [event[0] for event in events]
        self.assertEqual(frames, sorted(frames))
        starts = {cpc_routes.KEY_SPACE, cpc_routes.KEY_N, cpc_routes.KEY_J, cpc_routes.KEY_1, cpc_routes.KEY_RETURN, cpc_routes.KEY_2}
        later = [frame for frame, kind, code, value in events if frame >= cpc_routes.LATER_FROM and value
                 and ((kind == 'key' and code in starts) or (kind == 'joy' and value == cpc_routes.JOY_FIRE1))]
        self.assertGreaterEqual(len(later), (18000 - cpc_routes.LATER_FROM) // cpc_routes.LATER_EVERY - 1)
        # The conversion's route (LATER_FROM frames) holds none of them: what it plays is the same as before.
        self.assertFalse([e for e in cpc_routes.play_events(cpc_routes.LATER_FROM, 'e' * 64) if e[0] >= cpc_routes.LATER_FROM])

    def test_the_script_text(self):
        text = cpc_routes.script([(900, 'key', 47, 1), (904, 'key', 47, 0), (908, 'joy', 0, 0x26)])
        self.assertEqual(text, '900 key 47 1\n904 key 47 0\n908 joy 0 26\n')


if __name__ == '__main__':
    unittest.main()
