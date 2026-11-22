"""The Z80's bus cycles per encoding (retrorecomp/z80_timing.py): its shape, the totals every Z80 document states, and, when the
SingleStepTests sample is cached (.deps/z80-vectors, tools/fetch_z80_vectors.py), the T-state by T-state check of
tools/z80_timing_vectors.py with its positive controls. No ROM."""
import importlib.util
from pathlib import Path
import unittest

from retrorecomp.z80_chain import COST_GROUPS
from retrorecomp.z80_timing import cycles, length

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = {('', 0xCB), ('', 0xDD), ('', 0xED), ('', 0xFD)}


class TableTests(unittest.TestCase):
    def test_every_encoding_has_cycles_of_known_kinds(self):
        for group in COST_GROUPS:
            for opcode in range(256):
                base, extra = cycles(group, opcode)
                self.assertTrue(base and base[0] == ('m1', 'pc', 1), (group, opcode))
                for kind, source, count in base + extra:
                    self.assertIn(kind, ('m1', 'rd', 'wr', 'in', 'out', 'int'))
                    self.assertTrue(source and count >= 1)
                self.assertTrue(4 <= length(base) <= 23, (group, opcode, length(base)))
        with self.assertRaises(ValueError):
            cycles('xy', 0)
        with self.assertRaises(ValueError):
            cycles('', 256)

    def test_the_totals_of_the_z80_documents(self):
        # (group, opcode, T-states, T-states when taken or repeating): UM0080's counts, undocumented forms as measured on the chip.
        cases = [('', 0x00, 4, None), ('', 0x01, 10, None), ('', 0x09, 11, None), ('', 0x10, 8, 13), ('', 0x18, 12, None),
                 ('', 0x20, 7, 12), ('', 0x22, 16, None), ('', 0x2A, 16, None), ('', 0x34, 11, None), ('', 0x36, 10, None),
                 ('', 0x46, 7, None), ('', 0x76, 4, None), ('', 0xC0, 5, 11), ('', 0xC1, 10, None), ('', 0xC4, 10, 17),
                 ('', 0xC5, 11, None), ('', 0xC9, 10, None), ('', 0xCD, 17, None), ('', 0xD3, 11, None), ('', 0xDB, 11, None),
                 ('', 0xE3, 19, None), ('', 0xF9, 6, None), ('', 0xFF, 11, None),
                 ('cb', 0x00, 8, None), ('cb', 0x46, 12, None), ('cb', 0x06, 15, None),
                 ('dd', 0x21, 14, None), ('dd', 0x34, 23, None), ('dd', 0x36, 19, None), ('dd', 0x46, 19, None), ('dd', 0x77, 19, None),
                 ('dd', 0xE3, 23, None), ('dd', 0xE9, 8, None), ('dd', 0x00, 8, None), ('fd', 0x86, 19, None),
                 ('ddcb', 0x46, 20, None), ('ddcb', 0x06, 23, None), ('fdcb', 0xC6, 23, None),
                 ('ed', 0x40, 12, None), ('ed', 0x41, 12, None), ('ed', 0x42, 15, None), ('ed', 0x43, 20, None),
                 ('ed', 0x44, 8, None), ('ed', 0x45, 14, None), ('ed', 0x47, 9, None), ('ed', 0x57, 9, None), ('ed', 0x67, 18, None),
                 ('ed', 0xA0, 16, None), ('ed', 0xB0, 16, 21), ('ed', 0xB1, 16, 21), ('ed', 0xB2, 16, 21), ('ed', 0xB3, 16, 21),
                 ('ed', 0x00, 8, None), ('ed', 0xFF, 8, None)]
        for group, opcode, plain, taken in cases:
            base, extra = cycles(group, opcode)
            self.assertEqual(length(base), plain, (group, hex(opcode)))
            self.assertEqual(length(base) + length(extra) if extra else None, taken, (group, hex(opcode)))

    def test_a_prefix_before_an_opcode_without_hl_is_one_more_m1(self):
        for opcode in (0x00, 0x01, 0x10, 0x18, 0x3E, 0x80, 0xC3, 0xC9, 0xCD, 0xD3, 0xDB):
            base, extra = cycles('', opcode)
            prefixed, prefixed_extra = cycles('dd', opcode)
            self.assertEqual(length(prefixed), length(base) + 4)
            self.assertEqual(length(prefixed_extra), length(extra))

    def test_a_repeat_ends_with_its_single_forms_cycles(self):
        for single in (0xA0, 0xA1, 0xA2, 0xA3, 0xA8, 0xA9, 0xAA, 0xAB):
            self.assertEqual(cycles('ed', single + 0x10)[0], cycles('ed', single)[0])
            self.assertEqual(length(cycles('ed', single + 0x10)[1]), 5)


class VectorTests(unittest.TestCase):
    def test_the_singlesteptests_sample_agrees_cycle_for_cycle(self):
        cache = sorted((ROOT / '.deps' / 'z80-vectors').glob('*.json'))
        if not cache:
            self.skipTest('the SingleStepTests sample is not cached (python -B tools/fetch_z80_vectors.py)')
        spec = importlib.util.spec_from_file_location('z80_timing_vectors', ROOT / 'tools' / 'z80_timing_vectors.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        import contextlib
        import io
        import sys
        output = io.StringIO()
        argv = sys.argv
        sys.argv = ['z80_timing_vectors.py', '--vectors', str(cache[0])]
        try:
            with contextlib.redirect_stdout(output):
                status = module.main()
        finally:
            sys.argv = argv
        text = output.getvalue()
        self.assertIn(' 0 differ in 0 families', text)
        self.assertIn('PUSH without its internal cycle differs on 32/32', text)
        whole = (ROOT / '.deps' / 'z80-vectors' / 'families').is_dir()
        # Without the whole family files (--fetch), the few branches seen one way only in the sample stay unseen: exit 1.
        self.assertEqual(status, 0 if whole else 1, text)

    def test_the_expansion_reads_the_bus_as_the_vectors_do(self):
        spec = importlib.util.spec_from_file_location('z80_timing_vectors', ROOT / 'tools' / 'z80_timing_vectors.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # INC (HL) at 4C94h, I 94h, R 5Eh, HL 8D10h: the M1 (PC twice, IR twice), the read and its internal T-state, the write.
        state = {'pc': 0x4C94, 'sp': 0, 'a': 0, 'b': 0, 'c': 0, 'd': 0, 'e': 0, 'h': 0x8D, 'l': 0x10, 'i': 0x94, 'r': 0x5E,
                 'ix': 0, 'iy': 0, 'ram': []}
        self.assertEqual(module.expand('', cycles('', 0x34)[0], state),
                         [0x4C94, 0x4C94, 0x945E, 0x945E] + [0x8D10] * 4 + [0x8D10] * 3)
        self.assertEqual(module.family_encoding('dd cb __ 06'), ('ddcb', 0x06))
        self.assertEqual(module.family_encoding('ed b0'), ('ed', 0xB0))
        self.assertEqual(module.family_encoding('34'), ('', 0x34))


if __name__ == '__main__':
    unittest.main()
