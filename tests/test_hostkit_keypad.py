"""The on-screen keypad through the host kit's loop (tools/hostkit_keypad_selftest.py): runs when a C compiler and the pinned
SDL2 build are available, and skips cleanly otherwise. No ROM, no visible window, no sound device."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('hostkit_keypad_selftest', ROOT / 'tools' / 'hostkit_keypad_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class KeypadTests(unittest.TestCase):
    def test_the_keypad_opens_presses_closes_and_reaches_the_game_only_through_the_pad_word(self):
        reason = selftest.ready()
        if reason:
            self.skipTest(reason)
        # A folder of the build tree (not a temporary one), so that a second run only relinks what changed.
        code, output, seconds = selftest.run_checks(ROOT / '.build/hostkit-keypad-selftest')
        self.assertEqual(code, 0, output)
        self.assertIn('PASS', output)
        self.assertLess(seconds, selftest.HANG_SECONDS, output)     # a hang, not a speed (a busy PC)


if __name__ == '__main__':
    unittest.main()
