"""The Z80 chain's CPU state (native/z80_chain_state.inc) and the quick-state file (native/state_file.h): the CPU's fields in the
order the Master System and the MSX already write (so their states stay byte-equal when they move onto it), and the checks of
tools/z80_chain_state_selftest.py when a C compiler and the pinned engine are there."""
import importlib.util
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('z80_chain_state_selftest', ROOT / 'tools' / 'z80_chain_state_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)

FIELD = re.compile(r'RR_FIELD\(\w+, (\w+), (\d+), (.+?)\);')


def cpu_fields(path: str, start: str) -> list[tuple[str, str, str]]:
    """The RR_FIELD calls of the CPU block that opens at `start` in `path`, up to the cycle."""
    text = (ROOT / path).read_text(encoding='utf-8')
    block = text[text.index(start):]
    fields = []
    for match in FIELD.finditer(block):
        fields.append((match.group(1), match.group(2), match.group(3).replace(' ', '')))
        if match.group(1) == 'cyc':
            return fields
    raise AssertionError(f'no cycle in {path}')


class Z80ChainStateTests(unittest.TestCase):
    def test_the_cpu_fields_are_the_master_systems_and_the_msxs(self):
        shared = cpu_fields('native/z80_chain_state.inc', 'static void rr_z80_cpu_state')
        self.assertEqual(shared, cpu_fields('native/gamestate.inc', 'static void smsrecomp_machine_state'))
        self.assertEqual(shared, cpu_fields('native/msx_machine/msx_state_file.inc', 'static void msx_cpu_state'))
        self.assertEqual(sum(int(width) for _, width, _ in shared), 43)

    def test_the_file_helper_leaves_the_envelope_as_it_is(self):
        text = (ROOT / 'native' / 'state_file.h').read_text(encoding='utf-8')
        self.assertIn('#include "state_envelope.h"', text)
        self.assertIn('rr_state_envelope_write(&e', text)
        self.assertIn('rr_state_envelope_read(&e', text)

    def test_the_checks_pass(self):
        try:
            from retrorecomp.core import toolchain
            toolchain()
        except Exception as error:      # no compiler in this installation
            self.skipTest(f'no C toolchain: {error}')
        engine = ROOT / '.deps' / 'smsggrecomp'
        if not (engine / 'external' / 'z80-recomp-core' / 'include' / 'sms_runtime.h').is_file():
            self.skipTest('the pinned engine is not in .deps')
        with tempfile.TemporaryDirectory() as folder:
            result = selftest.run_checks(engine, Path(folder))
        self.assertEqual(result['failed'], 0, [line for line in result['lines'] if line.startswith('FAIL')])
        self.assertGreaterEqual(result['passed'], 35)


if __name__ == '__main__':
    unittest.main()
