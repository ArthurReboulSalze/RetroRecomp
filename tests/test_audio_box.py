"""The box filter of the sound chips (native/audio_box.h): its checks run when a C compiler is available (tools/audio_box_selftest.py)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('audio_box_selftest', ROOT / 'tools' / 'audio_box_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class AudioBoxTests(unittest.TestCase):
    def test_levels_become_the_same_samples_whatever_the_calls(self):
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        with tempfile.TemporaryDirectory() as folder:
            result = selftest.run_checks(Path(folder))
        self.assertEqual(result['failed'], 0)
        self.assertGreaterEqual(result['passed'], 17)


if __name__ == '__main__':
    unittest.main()
