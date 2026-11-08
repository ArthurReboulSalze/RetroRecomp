"""Atari ST native-step hooks (retrorecomp/atarist_codegen.py), ROM-free: the handler names read from a synthetic cpustbl.c, the
opcode map of the reference player, the samples that can become steps and the text of a step."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import atarist_codegen

CPUSTBL = '''/* generated */
const struct cputbl op_smalltbl_13[] = {
{ NULL, op_4e40_13_ff, 0x4e40, 2, { 0, 0 }, 0 }, /* TRAP */
{ 0 }};
const struct cputbl op_smalltbl_14[] = {
{ NULL, op_0000_14_ff, 0x0000, 4, { 0, 0 }, 0 }, /* OR */
{ NULL, op_4e40_13_ff, 0x4e40, 2, { 0, 0 }, 0 }, /* TRAP */
{ NULL, op_4e75_14_ff, 0x4e75, 2, { 0, 0 }, 1 }, /* RTS */
{ 0 }};
const struct cputbl op_smalltbl_20[] = {
{ op_4e75_20_ff, NULL, 0x4e75, 2, { 0, 0 }, 1 }, /* RTS */
{ 0 }};
'''


def opcode_map(entries: dict) -> str:
    return ''.join(f'{op:04x} {entries.get(op, "-")}\n' for op in range(65536))


class CodegenTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        (self.folder / 'cpustbl.c').write_text(CPUSTBL, encoding='utf-8')

    def test_the_names_come_from_the_cycle_exact_table_in_entry_order(self):
        self.assertEqual(atarist_codegen.table_handlers(self.folder / 'cpustbl.c'),
                         ['op_0000_14_ff', 'op_4e40_13_ff', 'op_4e75_14_ff'])

    def test_the_map_names_every_opcode_from_its_entry_and_keeps_illegal_ones_apart(self):
        (self.folder / 'map.txt').write_text(opcode_map({0x0000: 0, 0x0001: 0, 0x4e40: 1, 0x4e4f: 1, 0x4e75: 2}), encoding='ascii')
        table = atarist_codegen.load_opcode_map(self.folder / 'map.txt', self.folder / 'cpustbl.c')
        self.assertEqual(len(table), 65536)
        self.assertEqual(table[0x0001], 'op_0000_14_ff')
        self.assertEqual(table[0x4e4f], 'op_4e40_13_ff')   # a handler shared with another table keeps its own name
        self.assertEqual(table[0xa000], '-')

    def test_an_incomplete_map_or_an_unknown_entry_is_refused(self):
        (self.folder / 'short.txt').write_text('0000 0\n', encoding='ascii')
        with self.assertRaises(ValueError):
            atarist_codegen.load_opcode_map(self.folder / 'short.txt', self.folder / 'cpustbl.c')
        (self.folder / 'bad.txt').write_text(opcode_map({0x4e75: 7}), encoding='ascii')
        with self.assertRaises(ValueError):
            atarist_codegen.load_opcode_map(self.folder / 'bad.txt', self.folder / 'cpustbl.c')

    def test_only_opcodes_with_a_handler_become_steps_and_a_step_calls_it(self):
        (self.folder / 'map.txt').write_text(opcode_map({0x4e75: 2}), encoding='ascii')
        atarist_codegen.load_opcode_map(self.folder / 'map.txt', self.folder / 'cpustbl.c')
        self.assertEqual(atarist_codegen.native_samples([(0x1000, '4e75'), (0x1002, 'a000')]), [(0x1000, '4e75')])
        definition, declaration = atarist_codegen._step('rr_st_form_0', {'words': [0x4e75]}, 'MN_RTS', '')
        self.assertIn('op_4e75_14_ff(op);', definition)
        self.assertEqual(declaration, 'void rr_st_form_0(uint32_t op);\n')
        with self.assertRaises(ValueError):
            atarist_codegen._step('rr_st_form_1', {'words': [0xa000]}, 'MN_LINEA', '')


if __name__ == '__main__':
    unittest.main()
