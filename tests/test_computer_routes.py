"""The long route of a computer: determined by its seed, the same body as the Atari ST's, and on the Amiga never the slave's quit key."""
import unittest

from retrorecomp import amiga_conversion, atarist_conversion, computer_routes
from retrorecomp.scan_levels import LONG_ROUTE_FRAMES


class LongRouteTests(unittest.TestCase):
    def test_a_seed_gives_one_route(self):
        keys = (13, 32, 121, 49, 50)
        self.assertEqual(computer_routes.long_events('x', 6000, keys), computer_routes.long_events('x', 6000, keys))
        self.assertNotEqual(computer_routes.long_events('x', 6000, keys), computer_routes.long_events('y', 6000, keys))

    def test_it_draws_the_atari_st_route_when_given_its_seed_and_keys(self):
        keys = (atarist_conversion.KEY_RETURN, atarist_conversion.KEY_SPACE, 121, 49, 50)
        ours = computer_routes.long_events('atarist-long:abc:0', LONG_ROUTE_FRAMES, keys)
        self.assertEqual(ours, atarist_conversion.long_route('abc', 0, LONG_ROUTE_FRAMES, 1))

    def test_the_amiga_route_stays_inside_the_frames_and_the_event_bound(self):
        events = amiga_conversion.long_route('abc', 0, LONG_ROUTE_FRAMES, 0x45)
        self.assertLess(max(event[1] for event in events), LONG_ROUTE_FRAMES)
        self.assertLessEqual(len(events), 4096)
        self.assertEqual({event[2] for event in events}, {'joy', 'key', 'mouse'})

    def test_the_amiga_route_never_presses_the_quit_key(self):
        for quit_key in amiga_conversion.LONG_ROUTE_KEYS:
            events = amiga_conversion.long_route('abc', 0, LONG_ROUTE_FRAMES, quit_key)
            self.assertNotIn(quit_key, {event[3] for event in events if event[2] == 'key'})

    def test_the_amiga_route_is_the_game_s_own(self):
        self.assertNotEqual(amiga_conversion.long_route('abc', 0, 6000, 0x45), amiga_conversion.long_route('abd', 0, 6000, 0x45))
        self.assertNotEqual(amiga_conversion.long_route('abc', 0, 6000, 0x45), amiga_conversion.long_route('abc', 1, 6000, 0x45))


if __name__ == '__main__':
    unittest.main()
