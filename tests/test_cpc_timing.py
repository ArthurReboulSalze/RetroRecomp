"""The Amstrad CPC's Z80 instruction costs (retrorecomp/cpc_timing.py): the Gate Array's rule, the documented values, and the
table against its derivation from the SingleStepTests traces when they are on disk (.deps/z80-vectors)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from retrorecomp import cpc_timing

ROOT = Path(__file__).resolve().parents[1]

# Documented CPC costs in microseconds (table, opcode, not taken, taken or repeating), independent of the derivation.
DOCUMENTED = (
    ('base', 0x00, 1, None), ('base', 0x01, 3, None), ('base', 0x03, 2, None), ('base', 0x09, 3, None),
    ('base', 0x10, 3, 4), ('base', 0x18, 3, None), ('base', 0x20, 2, 3), ('base', 0x22, 5, None), ('base', 0x32, 4, None),
    ('base', 0x34, 3, None), ('base', 0x36, 3, None), ('base', 0x7E, 2, None), ('base', 0xC0, 2, 4), ('base', 0xC1, 3, None),
    ('base', 0xC3, 3, None), ('base', 0xC4, 3, 5), ('base', 0xC5, 4, None), ('base', 0xC7, 4, None), ('base', 0xC9, 3, None),
    ('base', 0xCD, 5, None), ('base', 0xD3, 3, None), ('base', 0xDB, 3, None), ('base', 0xE3, 6, None), ('base', 0xE9, 1, None),
    ('base', 0xF9, 2, None), ('cb', 0x00, 2, None), ('cb', 0x46, 3, None), ('cb', 0xC6, 4, None),
    ('ed', 0x40, 4, None), ('ed', 0x41, 4, None), ('ed', 0x42, 4, None), ('ed', 0x43, 6, None), ('ed', 0x44, 2, None),
    ('ed', 0x45, 4, None), ('ed', 0x47, 3, None), ('ed', 0x57, 3, None), ('ed', 0x6F, 5, None), ('ed', 0xA0, 5, None),
    ('ed', 0xA1, 4, None), ('ed', 0xA2, 5, None), ('ed', 0xA3, 5, None), ('ed', 0xB0, 5, 6), ('ed', 0xB1, 4, 6),
    ('ed', 0xB3, 5, 6),
    ('dd', 0x09, 4, None), ('dd', 0x21, 4, None), ('dd', 0x34, 6, None), ('dd', 0x36, 6, None), ('dd', 0x46, 5, None),
    ('dd', 0xE1, 4, None), ('dd', 0xE3, 7, None), ('dd', 0xE5, 5, None), ('dd', 0xE9, 2, None), ('dd', 0xF9, 3, None),
    ('ddcb', 0x46, 6, None), ('ddcb', 0xC6, 7, None), ('fdcb', 0x06, 7, None),
)


class RuleTests(unittest.TestCase):
    def test_an_access_waits_for_the_gate_arrays_phase(self):
        fetch = ['----', 'r-m-', '----', '----']
        self.assertEqual(cpc_timing.cpc_nops(fetch), 1)
        # PUSH: a 5-T fetch then two writes strobed on T6 and T9: moved to T9 and T13, 16 T-states.
        self.assertEqual(cpc_timing.cpc_nops(['----', 'r-m-', '----', '----', '----', '----', '-wm-', '----', '----', '-wm-',
                                              '----']), 4)
        # OUT (C),r: the I/O strobe on T10 moves to T13.
        self.assertEqual(cpc_timing.cpc_nops(fetch + fetch + ['----', '----', '-w-i', '----']), 4)
        # Internal T-states alone round up to the microsecond.
        self.assertEqual(cpc_timing.cpc_nops(fetch + ['----', '----']), 2)

    def test_halt_and_interrupts(self):
        self.assertEqual(cpc_timing.HALT, 1)
        self.assertEqual(cpc_timing.INTERRUPT, {0: 5, 1: 5, 2: 7})


class TableTests(unittest.TestCase):
    def test_every_table_has_256_costs_from_0_to_9(self):
        self.assertEqual(set(cpc_timing.COSTS), {'base', 'cb', 'ed', 'dd', 'fd', 'ddcb', 'fdcb'})
        for table, row in cpc_timing.COSTS.items():
            with self.subTest(table=table):
                self.assertEqual(len(row), 256)
                self.assertTrue(row.isdigit())
        for prefix in (0xCB, 0xDD, 0xED, 0xFD):
            self.assertEqual(cpc_timing.cost('base', prefix), 0)
        self.assertEqual(cpc_timing.cost('dd', 0xCB), 0)
        self.assertEqual(cpc_timing.cost('dd', 0xDD), 1)

    def test_the_documented_costs(self):
        for table, opcode, plain, taken in DOCUMENTED:
            with self.subTest(table=table, opcode=f'{opcode:02X}'):
                self.assertEqual(cpc_timing.cost(table, opcode), plain)
                self.assertEqual(cpc_timing.cost(table, opcode, taken=True), plain if taken is None else taken)

    def test_the_table_equals_its_derivation_from_the_vectors(self):
        sys.path.insert(0, str(ROOT / 'tools'))
        spec = importlib.util.spec_from_file_location('cpc_timing_table', ROOT / 'tools' / 'cpc_timing_table.py')
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        path = tool.vectors_path()
        if not path.is_file():
            self.skipTest('the SingleStepTests vectors are not fetched here (tools/fetch_z80_vectors.py)')
        costs, extra = tool.derive(path)
        self.assertEqual({table: [cpc_timing.cost(table, n) for n in range(256)] for table in costs}, costs)
        self.assertEqual(cpc_timing.EXTRA, extra)


if __name__ == '__main__':
    unittest.main()
