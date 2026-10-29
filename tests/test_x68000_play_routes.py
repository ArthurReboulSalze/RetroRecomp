"""The authored X68000 play routes are valid qualification inputs of exactly one disk set each (no game is needed)."""
import re
import unittest

from retrorecomp.x68000_conversion import valid_qualification_events
from tools.x68000_play_routes import ROUTES


class PlayRouteTests(unittest.TestCase):
    def test_every_route_is_a_valid_bounded_input_script_of_one_exact_set(self):
        self.assertTrue(ROUTES)
        for identity, route in ROUTES.items():
            with self.subTest(route.title):
                self.assertRegex(identity, r'^[0-9a-f]{64}$')
                count = max(4000, min(route.frames, 10000))
                self.assertEqual(count, route.frames)
                self.assertTrue(valid_qualification_events(route.events, count))
                self.assertTrue(route.reaches)
                self.assertTrue(all(type(value) is int for event in route.events for value in (event[0], event[1], event[3], event[4])))

    def test_the_validity_rule_refuses_what_the_conversion_refuses(self):
        self.assertFalse(valid_qualification_events([(0, 1, 'key', 13, 2)], 4000))      # a key value is 0 or 1
        self.assertFalse(valid_qualification_events([(0, 9999, 'key', 13, 1)], 4000))   # beyond the route
        self.assertFalse(valid_qualification_events([(5, 5, 'joy', 0, 1)], 4000))       # an empty span
        self.assertFalse(valid_qualification_events([(0, 4, 'mouse', 4, 1)], 4000))     # no such mouse code
        self.assertTrue(valid_qualification_events([(0, 10, 'mouse', 0, -64)], 4000))

    def test_a_route_holds_numbers_not_game_bytes(self):
        for route in ROUTES.values():
            self.assertTrue(all(len(event) == 5 and isinstance(event[2], str) and re.fullmatch(r'key|joy|joy2|mouse', event[2])
                                for event in route.events))


if __name__ == '__main__':
    unittest.main()
