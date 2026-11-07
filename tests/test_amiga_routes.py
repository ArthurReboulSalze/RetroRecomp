"""A route the game ends itself (its own Quit) is a valid reference when it ran long enough; any other stop is a failure."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import amiga_conversion as conversion
from retrorecomp.core import ConversionError


def fake_player(report):
    """A `spawn` that leaves the report a real player would write and exits as it does (2 when the install stopped)."""
    def spawn(args, **kwargs):
        folder = Path(args[args.index('--report') + 1]).parent
        (folder / 'result.json').write_text(json.dumps(report), encoding='utf-8')
        return SimpleNamespace(returncode=2 if report.get('stopped') else 0)
    return spawn


class EndedRouteTests(unittest.TestCase):
    def run_route(self, report, *, frames=3000, game_may_quit=True):
        with tempfile.TemporaryDirectory() as folder, patch.object(conversion, 'spawn', fake_player(report)):
            return conversion.replay(Path('player'), Path(folder) / 'run', frames, Path('inputs.txt'), game_may_quit=game_may_quit)

    def test_a_game_that_quits_after_enough_frames_ends_its_route_there(self):
        report = self.run_route({'quit': True, 'stopped': True, 'frames': 1702, 'error': 'the game quit'})
        self.assertTrue(report['ended_by_game'])
        self.assertEqual(report['frames'], 1702)

    def test_a_quit_before_the_minimum_is_a_failure(self):
        with self.assertRaisesRegex(ConversionError, 'stopped at frame 400'):
            self.run_route({'quit': True, 'stopped': True, 'frames': 400, 'error': 'the game quit'})

    def test_any_other_stop_is_a_failure(self):
        with self.assertRaisesRegex(ConversionError, 'stopped at frame 2000'):
            self.run_route({'quit': False, 'stopped': True, 'frames': 2000, 'error': 'resload call refused'})

    def test_a_replay_that_may_not_quit_keeps_the_old_rule(self):
        with self.assertRaisesRegex(ConversionError, 'stopped at frame 1702'):
            self.run_route({'quit': True, 'stopped': True, 'frames': 1702, 'error': 'the game quit'}, game_may_quit=False)

    def test_a_complete_run_is_unchanged(self):
        report = self.run_route({'quit': False, 'stopped': False, 'frames': 3000, 'error': ''})
        self.assertNotIn('ended_by_game', report)


if __name__ == '__main__':
    unittest.main()
