"""The EEPROM saves of the CPS-1.5 boards: their checks run when a C compiler is available (tools/cps1_persistence_selftest.py)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cps1_persistence_selftest', ROOT / 'tools' / 'cps1_persistence_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class PersistenceTests(unittest.TestCase):
    def test_a_save_is_written_loaded_and_never_replaced_when_unusable(self):
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            result = selftest.run_checks(Path(folder))
        self.assertEqual(result['failed'], 0)
        self.assertGreaterEqual(result['passed'], 9)


if __name__ == '__main__':
    unittest.main()
