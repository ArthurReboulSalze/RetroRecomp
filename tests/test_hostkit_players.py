"""Four players through the host kit's loop (tools/hostkit_players_selftest.py): runs when a C compiler and the pinned
SDL2 build are available, and skips cleanly otherwise. No ROM, no visible window, no sound device."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hostkit_players_selftest', ROOT / 'tools' / 'hostkit_players_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class FourPlayerTests(unittest.TestCase):
    def test_every_player_reaches_the_machine_and_only_player_one_restarts(self):
        reason = selftest.ready()
        if reason:
            self.skipTest(reason)
        # A folder of the build tree (not a temporary one), so that a second run only relinks what changed.
        results = selftest.run_checks(ROOT / '.build/hostkit-players-selftest')
        self.assertEqual(set(results), {'players4', 'players2'})
        for name, (code, output, seconds) in results.items():
            with self.subTest(board=name):
                self.assertEqual(code, 0, output)
                self.assertIn('PASS', output)
                self.assertLess(seconds, 20, output)


if __name__ == '__main__':
    unittest.main()
