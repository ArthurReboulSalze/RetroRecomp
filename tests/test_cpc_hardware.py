"""The Amstrad CPC's chips (native/cpc_machine and native/upd765): their checks run when a C compiler is available
(tools/cpc_hardware_selftest.py, tools/upd765_selftest.py)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def _tool(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _need_toolchain(case: unittest.TestCase):
    try:
        from retrorecomp.core import toolchain
        toolchain()
    except Exception as error:      # no compiler in this installation
        case.skipTest(f'no C toolchain: {error}')


class CpcChipTests(unittest.TestCase):
    def test_crtc_gate_array_and_keyboard(self):
        _need_toolchain(self)
        with tempfile.TemporaryDirectory() as folder:
            result = _tool('cpc_hardware_selftest').run_checks(Path(folder))
        self.assertEqual(result['failed'], 0)
        self.assertGreaterEqual(result['passed'], 84)

    def test_floppy_controller_and_disk_images(self):
        _need_toolchain(self)
        with tempfile.TemporaryDirectory() as folder:
            result = _tool('upd765_selftest').run_checks(Path(folder))
        self.assertEqual(result['failed'], 0)
        self.assertGreaterEqual(result['passed'], 61)


if __name__ == '__main__':
    unittest.main()
