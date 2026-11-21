"""The Amstrad CPC on the reference Z80 interpreter (tools/cpc_reference.py): authored programs as the system ROM. Runs when a C
compiler and the engine checkout are present (the main checkout's .deps/smsggrecomp)."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cpc_reference', ROOT / 'tools' / 'cpc_reference.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class ProgramTests(unittest.TestCase):
    def test_the_authored_programs_are_well_formed(self):
        for program in (tool.timing_program(), tool.interrupt_program(), tool.disk_program()):
            self.assertEqual(len(program), 0x8000)
        self.assertEqual(tool.interrupt_program()[0x38], 0xE5)          # the handler at 0038h
        self.assertEqual(len(tool.disk_image()), 256 + 256 + 9 * 512)

    def test_the_reference_runs_them(self):
        engine = ROOT / '.deps' / 'smsggrecomp'
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        if not (engine / 'runner' / 'external' / 'superzazu' / 'z80.c').is_file():
            self.skipTest('no engine checkout (.deps/smsggrecomp)')
        results = tool.checks(tool.build(engine))
        self.assertEqual([name for name, ok in results.items() if not ok], [])


if __name__ == '__main__':
    unittest.main()
