"""The Amstrad CPC natively (tools/cpc_native.py): authored programs translated by the banked Z80 chain against the reference.
The full run needs a C compiler, the engine checkout and the CPC's own generator (.deps/recompiler-build-cpc*)."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('cpc_native', ROOT / 'tools' / 'cpc_native.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class CompareTests(unittest.TestCase):
    def test_every_field_counts_but_the_step_counts(self):
        native = {'cycles': 10, 'pc': 1, 'native_steps': 5, 'fallback_steps': 0}
        reference = {'cycles': 10, 'pc': 1, 'steps': 5}
        self.assertEqual(tool.compare(native, reference), {})
        self.assertEqual(tool.compare({**native, 'pc': 2}, reference), {'pc': (2, 1)})
        self.assertEqual(tool.compare({**native, 'ram_fnv': 3}, reference), {'ram_fnv': (3, None)})


class NativeTests(unittest.TestCase):
    def test_native_equals_reference_on_the_authored_programs(self):
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        if not list((ROOT / '.deps').glob('recompiler-build-cpc*')) or not (ROOT / '.deps' / 'smsggrecomp').is_dir():
            self.skipTest("no CPC generator built here (.deps/recompiler-build-cpc*)")
        results = tool.checks()
        self.assertEqual({name: result['differences'] for name, result in results.items() if not result['equal']}, {})
        self.assertEqual({name: result['fallback_steps'] for name, result in results.items() if name != 'ram'},
                         {name: 0 for name in results if name != 'ram'})
        # Code built in RAM: interpreted and counted on the first generation, native with byte guards once learned.
        first, second = results['ram']['fallback_steps']
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)


if __name__ == '__main__':
    unittest.main()
