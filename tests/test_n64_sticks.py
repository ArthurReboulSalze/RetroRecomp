"""The Nintendo 64's gamepad through the host kit's loop (tools/n64_sticks_selftest.py): runs when a C compiler and the pinned
SDL2 build are available, and skips cleanly otherwise. No ROM, no visible window, no sound device."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('n64_sticks_selftest', ROOT / 'tools' / 'n64_sticks_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class N64SticksTests(unittest.TestCase):
    def test_left_stick_reaches_the_core_and_the_right_stick_presses_the_c_buttons(self):
        reason = selftest.ready()
        if reason:
            self.skipTest(reason)
        # A folder of the build tree (not a temporary one), so that a second run only relinks what changed.
        code, output, seconds = selftest.run_checks(ROOT / '.build/n64-sticks-selftest')
        self.assertEqual(code, 0, output)
        self.assertIn('PASS', output)
        self.assertLess(seconds, 20, output)


if __name__ == '__main__':
    unittest.main()
