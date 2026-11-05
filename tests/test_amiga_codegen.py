"""The Amiga's Moira hooks of the shared observed-code generator, on an authored opcode table (no ROM, no compiler)."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import amiga_codegen


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

    def test_a_step_calls_the_template_of_its_opcode(self):
        table(self.path, {0xd240: ('AddEaRg', 2, 0, 2), 0x4e75: ('Rts', 77, 12, 0)})
        amiga_codegen.load_opcode_map(self.path)
        definition, declaration = amiga_codegen._step('rr_amiga_form_3', {'words': [0xd240, 0, 0]}, 'MN_ADD', '')
        self.assertIn('void rr_amiga_form_3(vamiga::moira::Moira &m, uint16_t op)', definition)
        self.assertIn('RrAmigaSteps::run_AddEaRg<vamiga::moira::Core::C68000, (vamiga::moira::Instr)2, '
                      '(vamiga::moira::Mode)0, (vamiga::moira::Size)2>(m, op);', definition)
        self.assertEqual(declaration, 'void rr_amiga_form_3(vamiga::moira::Moira &m, uint16_t op);\n')

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

    def test_the_index_hooks(self):
        self.assertIn('#define MSB_FIRST 1', amiga_codegen.INDEX_HEAD)
        self.assertIn('struct RrAmigaStep', amiga_codegen.INDEX_HEAD)
        self.assertIn('return s->run;', amiga_codegen.index_tail([]))


if __name__ == '__main__':
    unittest.main()
