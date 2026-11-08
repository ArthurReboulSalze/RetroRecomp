"""The Amiga's native code generator, on an authored opcode table and canned decoder answers (no ROM, no compiler)."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import amiga_codegen, m68k_observed
from retrorecomp.systems import get_profile


def table(path, override=None):
    lines = []
    for op in range(65536):
        name, i, m, s = (override or {}).get(op, ('Illegal', 1, 0, 0))
        lines.append(f'{op:04x} {name} {i} {m} {s}')
    path.write_text('\n'.join(lines) + '\n', encoding='ascii')


class AmigaCodegenTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'map.txt'

    def tearDown(self):
        self.temp.cleanup()

    def test_a_form_is_the_template_of_its_opcode_with_the_opcode_as_a_literal(self):
        table(self.path, {0xd240: ('AddEaRg', 2, 0, 2), 0x4e75: ('Rts', 77, 12, 0)})
        amiga_codegen.load_opcode_map(self.path)
        definition = amiga_codegen._form('rr_amiga_form_d240', 0xd240)
        self.assertIn('extern "C" RR_AMIGA_FORM void rr_amiga_form_d240(void *m)', definition)
        self.assertIn('RrAmigaSteps::run_AddEaRg<vamiga::moira::Core::C68000, (vamiga::moira::Instr)2, '
                      '(vamiga::moira::Mode)0, (vamiga::moira::Size)2>(*static_cast<vamiga::moira::Moira *>(m), 0xd240);', definition)

    def test_the_header_has_one_forwarder_per_handler_inside_the_friend(self):
        table(self.path, {0xd240: ('AddEaRg', 2, 0, 2)})
        amiga_codegen.load_opcode_map(self.path)
        text = amiga_codegen._semantics('rr_amiga_', lambda t: t)
        self.assertIn('struct RrAmigaSteps {', text)
        self.assertEqual(text.count('static void run_'), 2)          # AddEaRg and Illegal
        self.assertIn('m.execAddEaRg<C, I, M, S>(op);', text)

    def test_an_incomplete_or_damaged_table_is_refused(self):
        self.path.write_text('0000 AndiRg 89 0 1\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            amiga_codegen.load_opcode_map(self.path)
        table(self.path, {5: ('Bad-Name', 1, 0, 0)})
        with self.assertRaisesRegex(ValueError, 'handler name'):
            amiga_codegen.load_opcode_map(self.path)

    def generated(self, decoded, samples):
        table(self.path, {0x4e71: ('Nop', 1, 0, 0), 0x6002: ('Bra', 3, 0, 0), 0x7000: ('MoveqRg', 4, 0, 0)})
        amiga_codegen.load_opcode_map(self.path)
        bodies = m68k_observed.InstructionBodies(['MN_OTHER', 'MN_NOP'], {'MN_NOP': ''}, '', '', 'e' * 64)
        project = Path(self.temp.name) / 'project'
        project.mkdir()

        def fake_run(command, log=None):
            Path(command[2]).write_text(json.dumps(decoded), encoding='utf-8')
        with patch.object(amiga_codegen, 'run', fake_run):
            stats = amiga_codegen.write_steps(project, samples, observed=get_profile('amiga').observed_code, bodies=bodies, decode_tool=Path('decode'))
        chain = ''.join((project / 'steps' / f'chain{n:02}.cpp').read_text(encoding='utf-8') for n in range(amiga_codegen.PARTS))
        return stats, chain, (project / 'steps' / 'index.c').read_text(encoding='utf-8')

    @staticmethod
    def instruction(addr, words, length=None, target=None):
        return {'mnemonic': 1, 'addr': addr, 'words': words, 'word_count': len(words), 'byte_length': length or 2 * len(words),
                'target_addr': target or 0, 'has_target': int(target is not None)}

    def test_an_instruction_goes_on_only_to_what_it_knows_and_only_with_that_opcode_latched(self):
        decoded = [self.instruction(0x1000, [0x4e71]), self.instruction(0x1002, [0x6002], target=0x1006), self.instruction(0x1004, [0x7000]),
                   self.instruction(0x1006, [0x4e71]), self.instruction(0x1006, [0x7000])]
        stats, chain, index = self.generated(decoded, [(0x1000, '4e71')])
        self.assertEqual((stats['native_instructions'], stats['pcs'], stats['forms']), (5, 4, 3))
        nop = chain[chain.index('void rr_amiga_at_001000_4e71(void *p) {'):]
        nop = nop[:nop.index('\n}')]
        self.assertIn('rr_amiga_form_4e71(p);', nop)
        self.assertLess(nop.index('rr_amiga_form_4e71(p);'), nop.index('rr_amiga_native_total++'))
        self.assertLess(nop.index('rr_amiga_native_total++'), nop.index('S::pending(m)'))
        self.assertLess(nop.index('S::pending(m)'), nop.index('S::at(m, 0x1002, 0x6002)'))
        branch = chain[chain.index('void rr_amiga_at_001002_6002(void *p) {'):]
        branch = branch[:branch.index('\n}')]
        # The target first, each opcode seen there, then the fall-through.
        self.assertLess(branch.index('S::at(m, 0x1006, 0x4e71)'), branch.index('S::at(m, 0x1006, 0x7000)'))
        self.assertLess(branch.index('S::at(m, 0x1006, 0x7000)'), branch.index('S::at(m, 0x1004, 0x7000)'))
        last = chain[chain.index('void rr_amiga_at_001006_7000(void *p) {'):]
        self.assertNotIn('S::at', last[:last.index('\n}')])
        self.assertIn('RrAmigaCode rr_amiga_lookup(uint32_t pc,uint16_t opcode)', index)
        self.assertNotIn('m68k_decoder', index + chain)

    def test_two_extension_words_at_one_address_are_one_instruction(self):
        decoded = [self.instruction(0x1000, [0x7000, 1]), self.instruction(0x1000, [0x7000, 2])]
        stats, chain, _ = self.generated(decoded, [(0x1000, '7000')])
        self.assertEqual((stats['instructions'], stats['native_instructions']), (2, 1))
        self.assertEqual(chain.count('void rr_amiga_at_001000_7000(void *p) {'), 1)

    def test_the_kickstart_is_counted_apart(self):
        decoded = [self.instruction(0x1000, [0x4e71]), self.instruction(0x200000, [0x4e71]), self.instruction(0xfc0000, [0x4e71])]
        _, chain, _ = self.generated(decoded, [(0x1000, '4e71')])

        def body(name):
            text = chain[chain.index(f'void {name}(void *p) {{'):]
            return text[:text.index('\n}')]
        self.assertNotIn('rr_amiga_kick_total', body('rr_amiga_at_001000_4e71'))
        self.assertIn('0x200000u - rr_amiga_kick_base < rr_amiga_kick_size', body('rr_amiga_at_200000_4e71'))
        self.assertIn('rr_amiga_kick_total++', body('rr_amiga_at_fc0000_4e71'))

    def test_the_declaration_the_profile_will_carry(self):
        observed = get_profile('amiga').observed_code
        self.assertEqual((observed.source_extension, observed.index_extension), (amiga_codegen.SOURCE_EXTENSION, amiga_codegen.INDEX_EXTENSION))
        self.assertEqual((observed.prefix, observed.step_type, observed.source_extension, observed.index_extension),
                         ('rr_amiga_', 'RrAmigaStep', '.cpp', '.c'))
        observed.check_sample(0x1ffffe, '4e75')
        observed.check_sample(0xc00000, '4e75')
        with self.assertRaises(ValueError):
            observed.check_sample(0xbfe000, '4e75')


if __name__ == '__main__':
    unittest.main()
