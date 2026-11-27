"""The CRT and LCD looks of the host kit (HOST_KIT D35): their checks run when a C compiler and the pinned SDL2 are available
(tools/crt_look_selftest.py)."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('crt_look_selftest', ROOT / 'tools' / 'crt_look_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class CrtLookTests(unittest.TestCase):
    def test_overlays_cycle_and_whole_looks_without_a_window(self):
        try:
            from retrorecomp.core import toolchain
            from retrorecomp.platforms import sdl_install
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        if not (sdl_install() / 'include').is_dir():
            self.skipTest('the pinned SDL2 is not built in .deps')
        with tempfile.TemporaryDirectory() as folder:
            result = selftest.run_checks(Path(folder))
        self.assertEqual(result['failed'], 0)
        self.assertGreaterEqual(result["passed"], 50)


if __name__ == '__main__':
    unittest.main()
