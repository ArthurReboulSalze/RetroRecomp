"""Atari ST native code (retrorecomp/atarist_codegen.py), ROM-free: the handler names read from a synthetic cpustbl.c, the opcode map of the reference player, the samples that can
become native, the text of a form and of an instruction, the index."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import atarist_codegen
from retrorecomp.systems import get_profile

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

    def test_only_opcodes_with_a_handler_become_native_and_a_form_without_its_text_calls_it(self):
        (self.folder / 'map.txt').write_text(opcode_map({0x4e75: 2}), encoding='ascii')
        atarist_codegen.load_opcode_map(self.folder / 'map.txt', self.folder / 'cpustbl.c')
        self.assertEqual(atarist_codegen.native_samples([(0x1000, '4e75'), (0x1002, 'a000')]), [(0x1000, '4e75')])
        self.assertIn('op_4e75_14_ff(0x4e75);', atarist_codegen.form_definition('rr_st_form_4e75', 0x4e75))
        with self.assertRaises(ValueError):
            atarist_codegen.form_definition('rr_st_form_a000', 0xa000)

    def test_a_form_is_the_handler_text_with_the_opcode_as_a_literal(self):
        (self.folder / 'map.txt').write_text(opcode_map({0x4e75: 2}), encoding='ascii')
        (self.folder / 'cpuemu_13.c').write_text('void REGPARAM2 op_4e75_14_ff(uae_u32 opcode)\n{\n\tuae_u32 real_opcode = opcode;\n\treturn;\n}\n', encoding='utf-8')
        atarist_codegen.load_opcode_map(self.folder / 'map.txt', self.folder / 'cpustbl.c')
        form = atarist_codegen.form_definition('rr_st_form_4e75', 0x4e75)
        self.assertIn('uae_u32 opcode = 0x4e75;', form)
        self.assertIn('uae_u32 real_opcode = opcode;', form)
        self.assertNotIn('op_4e75_14_ff', form)

    def test_an_instruction_runs_its_form_counts_and_goes_on_to_what_it_knows_comes_next(self):
        (self.folder / 'map.txt').write_text(opcode_map({0x0000: 0, 0x4e75: 2}), encoding='ascii')
        atarist_codegen.load_opcode_map(self.folder / 'map.txt', self.folder / 'cpustbl.c')
        observed = get_profile('atarist').observed_code
        decoded = [{'addr': 0x1000, 'words': [0x0000, 0x0012], 'word_count': 2, 'has_target': False, 'target_addr': 0, 'byte_length': 4},
                   {'addr': 0x1004, 'words': [0x4e75], 'word_count': 1, 'has_target': False, 'target_addr': 0, 'byte_length': 2}]

        def decode(command, log=None):
            Path(command[2]).write_text(json.dumps(decoded), encoding='utf-8')
        with mock.patch.object(atarist_codegen, 'run', decode):
            steps = atarist_codegen.write_steps(self.folder, [(0x1000, '00000012'), (0x1004, '4e75')], observed=observed, decode_tool=Path('decode'))
        self.assertEqual((steps['native_instructions'], steps['forms'], steps['pcs']), (2, 2, 2))
        chain = ''.join(path.read_text(encoding='utf-8') for path in sorted((self.folder / 'steps').glob('chain*.c')))
        first = chain[chain.index('void rr_st_at_001000_0000(void) {'):]
        self.assertIn('rr_st_form_0000();', first)
        self.assertIn('rr_st_native_total++;', first)
        self.assertIn('if (rr_st_next(0x1004, 0x4e75)) RR_ST_NEXT rr_st_at_001004_4e75();', first)
        index = (self.folder / 'steps' / 'index.c').read_text(encoding='utf-8')
        self.assertIn('RrStCode rr_st_lookup(uint32_t pc,uint32_t opcode)', index)
        self.assertNotIn('m68k_decoder', index)   # no text of the recompiler's decoder in a game
        self.assertNotIn('m68k_decoder', chain)


if __name__ == '__main__':
    unittest.main()
