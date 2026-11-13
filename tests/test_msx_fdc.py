"""The MSX2+ disk controller: its checks run when a C compiler is available (tools/msx_fdc_selftest.py)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('msx_fdc_selftest', ROOT / 'tools' / 'msx_fdc_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class DiskControllerTests(unittest.TestCase):
    def test_a_write_changes_exactly_the_sectors_it_was_given(self):
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            result = selftest.run_checks(Path(folder))
        self.assertEqual(result['failed'], 0)
        self.assertGreaterEqual(result['passed'], 21)


if __name__ == '__main__':
    unittest.main()
