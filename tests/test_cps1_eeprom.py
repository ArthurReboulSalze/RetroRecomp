"""The 93C46 model of the CPS-1.5 boards: its checks run when a C compiler is available (tools/cps1_eeprom_selftest.py)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cps1_eeprom_selftest', ROOT / 'tools' / 'cps1_eeprom_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class EepromModelTests(unittest.TestCase):
    def test_the_model_answers_like_the_chip(self):
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            result = selftest.run_checks(Path(folder))
        self.assertEqual(result['failed'], 0)
        self.assertGreaterEqual(result['passed'], 19)


if __name__ == '__main__':
    unittest.main()
