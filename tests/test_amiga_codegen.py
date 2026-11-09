"""The Amiga's native code generator, on an authored opcode table (no ROM, no compiler)."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import amiga_codegen
from retrorecomp.systems import get_profile


def table(path, override=None):
    lines = []
    for op in range(65536):
        name, i, m, s, *words = (override or {}).get(op, ('Illegal', 1, 0, 0))
        lines.append(f'{op:04x} {name} {i} {m} {s} {words[0] if words else 1}')
    path.write_text('\n'.join(lines) + '\n', encoding='ascii')


class AmigaCodegenTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'map.txt'

    def tearDown(self):
        self.temp.cleanup()

    def test_a_form_not_translated_is_the_template_of_its_opcode_with_the_opcode_as_a_literal(self):
        table(self.path, {0xc0c1: ('Mulu', 90, 0, 2), 0x4e75: ('Rts', 77, 12, 0)})
        amiga_codegen.load_opcode_map(self.path)
        definition = amiga_codegen._form('rr_amiga_form_c0c1', 0xc0c1)
        self.assertIn('extern "C" RR_AMIGA_FORM void rr_amiga_form_c0c1(void *m)', definition)
        self.assertIn('RrAmigaSteps::run_Mulu<vamiga::moira::Core::C68000, (vamiga::moira::Instr)90, '
                      '(vamiga::moira::Mode)0, (vamiga::moira::Size)2>(*static_cast<vamiga::moira::Moira *>(m), 0xc0c1);', definition)

    def test_a_translated_form_says_so_and_is_counted_apart(self):
        table(self.path, {0x4e71: ('Nop', 1, 12, 4), 0xc0c1: ('Mulu', 90, 0, 2)})
        amiga_codegen.load_opcode_map(self.path)
        self.assertIn('RrAmigaSteps::translated<0x4e71>', amiga_codegen._form('rr_amiga_form_4e71', 0x4e71))
        project = Path(self.temp.name) / 'project'
        project.mkdir()
        stats = amiga_codegen.write_steps(project, [(0x1000, '4e71'), (0x1002, 'c0c1')], observed=get_profile('amiga').observed_code)
        self.assertEqual((stats['forms'], stats['translated_forms'], stats['native_instructions'], stats['translated_instructions']), (2, 1, 2, 1))
        chain = ''.join((project / 'steps' / f'chain{n:02}.cpp').read_text(encoding='utf-8') for n in range(amiga_codegen.PARTS))
        self.assertIn('rr_amiga_translated_total++', self.body(chain, 'rr_amiga_at_001000_4e71'))
        self.assertNotIn('rr_amiga_translated_total++', self.body(chain, 'rr_amiga_at_001002_c0c1'))

    def test_the_header_has_one_forwarder_per_handler_inside_the_friend(self):
        table(self.path, {0xd240: ('AddEaRg', 2, 0, 2)})
        amiga_codegen.load_opcode_map(self.path)
        text = amiga_codegen._semantics('rr_amiga_', lambda t: t)
        self.assertIn('struct RrAmigaSteps {', text)
        self.assertEqual(text.count('static void run_'), 2)          # AddEaRg and Illegal
        self.assertIn('m.execAddEaRg<C, I, M, S>(op);', text)

    def test_an_incomplete_or_damaged_table_is_refused(self):
        self.path.write_text('0000 AndiRg 89 0 1 2\n', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            amiga_codegen.load_opcode_map(self.path)
        table(self.path, {5: ('Bad-Name', 1, 0, 0)})
        with self.assertRaisesRegex(ValueError, 'handler name'):
            amiga_codegen.load_opcode_map(self.path)

    def generated(self, samples):
        table(self.path, {0x4e71: ('Nop', 1, 0, 0), 0x6002: ('Bcc', 12, 12, 1), 0x7000: ('Moveq', 4, 0, 0), 0x6000: ('Bra', 28, 12, 2, 2),
                          0x51c8: ('Dbcc', 30, 12, 2, 2), 0x4ef9: ('Jmp', 40, 8, 0, 3), 0x303c: ('Move0', 50, 11, 2, 2)})
        amiga_codegen.load_opcode_map(self.path)
        project = Path(self.temp.name) / 'project'
        project.mkdir()
        stats = amiga_codegen.write_steps(project, samples, observed=get_profile('amiga').observed_code)
        chain = ''.join((project / 'steps' / f'chain{n:02}.cpp').read_text(encoding='utf-8') for n in range(amiga_codegen.PARTS))
        return stats, chain, (project / 'steps' / 'index.c').read_text(encoding='utf-8')

    @staticmethod
    def body(chain, name):
        text = chain[chain.index(f'void {name}(void *p) {{'):]
        return text[:text.index('\n}')]

    def test_an_instruction_goes_on_only_to_what_it_knows_and_only_with_that_opcode_latched(self):
        stats, chain, index = self.generated([(0x1000, '4e71'), (0x1002, '6002'), (0x1004, '7000'), (0x1006, '4e71'), (0x1006, '7000')])
        self.assertEqual((stats['native_instructions'], stats['pcs'], stats['forms']), (5, 4, 3))
        nop = self.body(chain, 'rr_amiga_at_001000_4e71')
        self.assertIn('rr_amiga_form_4e71(p);', nop)
        self.assertLess(nop.index('rr_amiga_form_4e71(p);'), nop.index('rr_amiga_native_total++'))
        self.assertLess(nop.index('rr_amiga_native_total++'), nop.index('S::pending(m)'))
        self.assertLess(nop.index('S::pending(m)'), nop.index('S::at(m, 0x1002, 0x6002)'))
        branch = self.body(chain, 'rr_amiga_at_001002_6002')
        # The target first, each opcode seen there, then the fall-through.
        self.assertLess(branch.index('S::at(m, 0x1006, 0x4e71)'), branch.index('S::at(m, 0x1006, 0x7000)'))
        self.assertLess(branch.index('S::at(m, 0x1006, 0x7000)'), branch.index('S::at(m, 0x1004, 0x7000)'))
        self.assertNotIn('S::at', self.body(chain, 'rr_amiga_at_001006_7000'))
        self.assertIn('RrAmigaCode rr_amiga_lookup(uint32_t pc,uint16_t opcode)', index)
        self.assertNotIn('m68k_decoder', index + chain)

    def test_the_words_and_the_named_address_come_from_the_table_and_the_words_seen(self):
        _, chain, _ = self.generated([(0x1000, '6000fffe0000'), (0x2000, '51c8fffc4e71'), (0x3000, '4ef9000012344e71'), (0x3100, '303c12344e71'),
                                      (0x1234, '4e71'), (0x0ffe, '4e71'), (0x1ffe, '4e71'), (0x3104, '4e71'), (0x3006, '4e71')])
        self.assertIn('S::at(m, 0x1000, 0x6000)', self.body(chain, 'rr_amiga_at_001000_6000'))     # Backward, 16-bit displacement
        self.assertIn('S::at(m, 0x1ffe, 0x4e71)', self.body(chain, 'rr_amiga_at_002000_51c8'))
        self.assertIn('S::at(m, 0x1234, 0x4e71)', self.body(chain, 'rr_amiga_at_003000_4ef9'))
        self.assertIn('S::at(m, 0x3006, 0x4e71)', self.body(chain, 'rr_amiga_at_003000_4ef9'))     # Three words, as the table says
        self.assertIn('S::at(m, 0x3104, 0x4e71)', self.body(chain, 'rr_amiga_at_003100_303c'))

    def test_two_extension_words_at_one_address_are_one_instruction(self):
        table_words = [(0x1000, '303c0001'), (0x1000, '303c0002')]
        stats, chain, _ = self.generated(table_words)
        self.assertEqual((stats['instructions'], stats['native_instructions']), (2, 1))
        self.assertEqual(chain.count('void rr_amiga_at_001000_303c(void *p) {'), 1)

    def test_the_kickstart_is_counted_apart(self):
        _, chain, _ = self.generated([(0x1000, '4e71'), (0x200000, '4e71'), (0xfc0000, '4e71')])
        self.assertNotIn('rr_amiga_kick_total', self.body(chain, 'rr_amiga_at_001000_4e71'))
        self.assertIn('0x200000u - rr_amiga_kick_base < rr_amiga_kick_size', self.body(chain, 'rr_amiga_at_200000_4e71'))
        self.assertIn('rr_amiga_kick_total++', self.body(chain, 'rr_amiga_at_fc0000_4e71'))

    def sweep_table(self):
        table(self.path, {0x4e71: ('Nop', 1, 12, 4), 0x6604: ('Bcc', 14, 12, 1), 0x4e75: ('Rts', 77, 12, 4), 0x7001: ('Moveq', 4, 11, 4), 0x303c: ('Move0', 50, 11, 2, 2)})
        amiga_codegen.load_opcode_map(self.path)

    @staticmethod
    def image(start, *words):
        return [(start, b''.join(word.to_bytes(2, 'big') for word in words))]

    def test_a_sweep_follows_the_branch_not_taken_and_stops_where_the_code_does(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        # BNE +4 at $1000: the route saw the branch taken ($1006); what falls through it was never run.
        memory = self.image(0x1000, 0x6604, 0x7001, 0x4e75, 0x4e71, 0x4e75, 0x0000)
        swept = amiga_codegen.sweep([(0x1000, '6604'), (0x1006, '4e71')], [memory], observed=observed)
        self.assertEqual(swept, [(0x1002, '7001'), (0x1004, '4e75'), (0x1008, '4e75')])    # $100a holds no legal opcode

    def test_a_window_gives_the_instruction_that_ran_and_counts_what_a_walk_finds_apart(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        # moveq #1,d0; rts; nop: the walk goes on past the return, and neither of those is known to have run.
        started, walked = amiga_codegen.walk_records([(0x1000, bytes.fromhex('70014e754e71'))], observed=observed)
        self.assertEqual(started, [(0x1000, '7001')])
        self.assertEqual(walked, [(0x1002, '4e75'), (0x1004, '4e71')])

    def test_a_walk_stops_at_what_cannot_be_an_instruction(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        illegal = next(opcode for opcode, entry in amiga_codegen._MAP.items() if entry[0] == 'Illegal')
        data = bytes.fromhex('7001') + illegal.to_bytes(2, 'big') + bytes.fromhex('4e71')
        started, walked = amiga_codegen.walk_records([(0x1000, data)], observed=observed)
        self.assertEqual((started, walked), ([(0x1000, '7001')], []))

    def test_an_instruction_that_also_began_a_window_counts_as_having_run(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        started, walked = amiga_codegen.walk_records([(0x1000, bytes.fromhex('70014e75')), (0x1002, bytes.fromhex('4e75'))], observed=observed)
        self.assertEqual(started, [(0x1000, '7001'), (0x1002, '4e75')])
        self.assertEqual(walked, [])

    def test_learned_and_walked_instructions_count_apart_from_what_a_route_ran(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            stats = amiga_codegen.write_steps(project, [(0x1000, '4e71')], observed=observed, swept=[(0x1006, '4e71')], learned=[(0x1000, '4e71'), (0x1002, '7001')], walked=[(0x1002, '7001'), (0x1004, '4e75')])
            chains = ''.join(path.read_text(encoding='utf-8') for path in sorted((project / 'steps').glob('chain*.cpp')))
        self.assertEqual((stats['swept_instructions'], stats['learned_instructions'], stats['walked_instructions']), (1, 1, 1))
        count = lambda pc, opcode: chains[chains.index(f'void rr_amiga_at_{pc:06x}_{opcode:04x}(void *p) {{'):].split('}', 1)[0]
        self.assertNotIn('rr_amiga_learned_total', count(0x1000, 0x4e71))    # A route ran it: that is what it counts as.
        self.assertIn('rr_amiga_learned_total++', count(0x1002, 0x7001))
        self.assertIn('rr_amiga_walked_total++', count(0x1004, 0x4e75))
        self.assertIn('rr_amiga_swept_total++', count(0x1006, 0x4e71))

    def test_a_sweep_fills_the_pages_where_code_ran_in_ram_not_in_rom_and_not_other_pages(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        # $1000: a return, so nothing falls through it; a subroutine further in the page, and another in the next page.
        memory = [(0x1000, b'\x4e\x75' + b'\x00\x00' * 7 + b'\x70\x01'), (0x2000, b'\x70\x01')]
        self.assertEqual(amiga_codegen.sweep([(0x1000, '4e75')], [memory], observed=observed), [(0x1010, '7001')])
        self.assertEqual(amiga_codegen.sweep([(0x1000, '4e75')], [], observed=observed, rom_images=[memory]), [])

    def test_a_sweep_starts_only_where_the_image_still_holds_what_was_observed(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        # The code of $1000 was replaced: its branch names nothing any more; in a ROM image nothing else is added.
        memory = self.image(0x1000, 0x7001, 0x4e71)
        self.assertEqual(amiga_codegen.sweep([(0x1000, '6604')], [], observed=observed, rom_images=[memory]), [])

    def test_a_sweep_keeps_the_words_of_an_instruction_and_is_bounded(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        memory = self.image(0x1000, 0x4e71, 0x303c, 0x1234, 0x4e71, 0x4e71, 0x4e71)
        self.assertEqual(amiga_codegen.sweep([(0x1000, '4e71')], [memory], observed=observed)[0], (0x1002, '303c1234'))
        self.assertEqual(len(amiga_codegen.sweep([(0x1000, '4e71')], [memory], observed=observed, limit=2)), 2)

    def test_a_sweep_leaves_a_window_no_code_can_be_in(self):
        self.sweep_table()
        observed = get_profile('amiga').observed_code
        memory = self.image(0x9ffffe, 0x4e71, 0x4e71, 0x4e71)
        swept = amiga_codegen.sweep([(0x9ffffe, '4e71')], [memory], observed=observed)
        self.assertEqual(swept, [])

    def test_a_swept_instruction_counts_apart_and_an_observed_one_never_does(self):
        self.sweep_table()
        project = Path(self.temp.name) / 'project'
        project.mkdir()
        stats = amiga_codegen.write_steps(project, [(0x1000, '4e71')], observed=get_profile('amiga').observed_code, swept=[(0x1002, '7001')])
        self.assertEqual((stats['instructions'], stats['native_instructions'], stats['swept_instructions']), (1, 2, 1))
        chain = ''.join((project / 'steps' / f'chain{n:02}.cpp').read_text(encoding='utf-8') for n in range(amiga_codegen.PARTS))
        self.assertIn('rr_amiga_swept_total++', self.body(chain, 'rr_amiga_at_001002_7001'))
        self.assertNotIn('rr_amiga_swept_total++', self.body(chain, 'rr_amiga_at_001000_4e71'))
        self.assertIn('S::at(m, 0x1002, 0x7001)', self.body(chain, 'rr_amiga_at_001000_4e71'))

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
