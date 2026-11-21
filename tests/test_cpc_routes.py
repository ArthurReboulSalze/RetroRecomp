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
        self.assertEqual(pressed[0], ('key', cpc_routes.KEY_SPACE))
        keys = {code for kind, code in pressed if kind == 'key'}
        self.assertTrue({cpc_routes.KEY_SPACE, cpc_routes.KEY_N, cpc_routes.KEY_RETURN, cpc_routes.KEY_1} <= keys)

    def test_the_script_text(self):
        text = cpc_routes.script([(900, 'key', 47, 1), (904, 'key', 47, 0), (908, 'joy', 0, 0x26)])
        self.assertEqual(text, '900 key 47 1\n904 key 47 0\n908 joy 0 26\n')


if __name__ == '__main__':
    unittest.main()
