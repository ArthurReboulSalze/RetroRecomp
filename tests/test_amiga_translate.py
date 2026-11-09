"""The Amiga's translator of 68000 forms, on text (no ROM, no compiler). What it translates is proved elsewhere: tools/amiga_vector_selftest.py runs every
translated opcode against Moira's handler, and each conversion compares every frame with the fresh reference."""
import unittest

from retrorecomp import amiga_translate as translate
from retrorecomp.amiga_translate import AI, AL, AN, BYTE, DI, DN, IM, IP, IX, LONG, PD, PI, WORD


class TranslateTest(unittest.TestCase):
    def body(self, opcode, handler, mode, size):
        text = translate.translate(opcode, handler, mode, size)
        self.assertIsNotNone(text)
        return text

    def test_what_it_does_not_know_stays_moiras_code(self):
        self.assertIsNone(translate.translate(0xc0c0, 'Mulu', DN, WORD))
        self.assertIsNone(translate.translate(0x4e73, 'Rte', IP, WORD))
        self.assertIsNone(translate.translate(0x4afc, 'Illegal', IP, WORD))

    def test_only_the_68000(self):
        self.assertIsNotNone(translate.translate(0x4e71, 'Nop', IP, LONG))
        self.assertIsNone(translate.translate(0x4e71, 'Nop', IP, LONG, core='C68020'))

    def test_registers_are_literals_and_the_bus_stays_the_machines(self):
        text = self.body(0x3211, 'Move0', AI, WORD)      # MOVE.W (A1),D1
        self.assertIn('ea = r.a[1];', text)
        self.assertIn('m.read<Core::C68000, AddrSpace::DATA, Word, 0>(ea)', text)
        self.assertIn('r.d[1] = WRITE<Word>(r.d[1], data);', text)
        self.assertIn('m.prefetch<Core::C68000, POLL>();', text)
        self.assertNotIn('opcode', text)
        self.assertNotIn('exec', text)

    def test_an_extension_word_is_read_live(self):
        text = self.body(0x302a, 'Move0', DI, WORD)      # MOVE.W d(A2),D0
        self.assertIn('ea = U32_ADD(r.a[2], (i16)q.irc);', text)
        self.assertIn('m.readExt<Core::C68000>();', text)
        self.assertIn('AE_DEC_PC', text)                 # Moira's frame for an address error in this mode

    def test_the_stack_pointer_keeps_its_byte_step(self):
        self.assertIn('U32_DEC(r.a[7], 2);', self.body(0x1027, 'Move0', PD, BYTE))
        self.assertIn('U32_INC(r.a[7], 2);', self.body(0x101f, 'Move0', PI, BYTE))
        self.assertIn('U32_INC(r.a[6], 1);', self.body(0x101e, 'Move0', PI, BYTE))

    def test_a_condition_comes_from_its_field(self):
        self.assertIn('if (!r.sr.z) {', self.body(0x6602, 'Bcc', 12, BYTE))
        self.assertIn('if (r.sr.z) {', self.body(0x6702, 'Bcc', 12, BYTE))
        self.assertIn('if (!(false)) {', self.body(0x51c8, 'Dbcc', 12, WORD))

    def test_addition_and_subtraction_share_a_handler(self):
        self.assertIn('U64_ADD(op1, op2)', self.body(0xd041, 'AddEaRg', DN, WORD))
        self.assertIn('U64_SUB(op2, op1)', self.body(0x9041, 'AddEaRg', DN, WORD))
        self.assertIn('U64_SUB3(op2, op1, r.sr.x)', self.body(0x9141, 'AddxRg', DN, WORD))

    def test_logic_comes_from_the_opcode(self):
        self.assertIn('& (', self.body(0xc041, 'AndEaRg', DN, WORD))
        self.assertIn('| (', self.body(0x8041, 'AndEaRg', DN, WORD))
        self.assertIn('^ (', self.body(0xb141, 'AndRgEa', DN, WORD))
        self.assertIn('| (', self.body(0x0041, 'AndiRg', DN, WORD))
        self.assertIn('^ (', self.body(0x0a41, 'AndiRg', DN, WORD))

    def test_a_long_move_from_a_register_writes_before_its_flags(self):
        text = self.body(0x2281, 'Move2', DN, LONG)      # MOVE.L D1,(A1)
        self.assertLess(text.index('m.write<'), text.index('r.sr.n ='))
        text = self.body(0x3281, 'Move2', DN, WORD)
        self.assertLess(text.index('r.sr.n = NBIT<Word>(data);'), text.index('m.write<'))

    def test_a_move_to_a_long_address_after_a_memory_read_fetches_in_the_middle(self):
        text = self.body(0x23d0, 'Move8', AI, LONG)
        self.assertLess(text.index('m.read<'), text.index('ea2 |= q.irc;'))
        self.assertLess(text.index('ea2 |= q.irc;'), text.index('m.write<'))
        self.assertGreater(text.rindex('m.readExt<'), text.index('m.write<'))
        self.assertNotIn('ea2', self.body(0x23c0, 'Move8', DN, LONG))

    def test_a_shift_charges_its_count(self):
        self.assertIn('m.sync(6);', self.body(0xe548, 'ShiftIm', IM, WORD))      # LSL.W #2,D0
        self.assertIn('const int cnt = 8;', self.body(0xe148, 'ShiftIm', IM, WORD))
        self.assertIn('int cyc = 4 + 2 * cnt;', self.body(0xe1a8, 'ShiftRg', DN, LONG))

    def test_bits(self):
        self.assertNotIn('m.write<', self.body(0x0810, 'BitImEa', AI, BYTE))      # BTST writes nothing
        self.assertIn('data |= (1u << b);', self.body(0x08d0, 'BitImEa', AI, BYTE))
        self.assertIn('src & 0b111;', self.body(0x08d0, 'BitImEa', AI, BYTE))
        self.assertIn('src & 0b11111;', self.body(0x08c0, 'BitImDy', DN, BYTE))

    def test_jumps_pass_their_last_extension_word_without_fetching_it(self):
        text = self.body(0x4ef9, 'Jmp', AL, LONG)
        self.assertIn('r.pc += 2;', text)
        self.assertEqual(text.count('m.readExt<'), 1)
        self.assertIn('m.fullPrefetch<Core::C68000, POLL>();', text)
        self.assertIn('m.sync(4);', self.body(0x4ef0, 'Jmp', IX, LONG))
        self.assertIn('AE_DEC_PC', self.body(0x4eb0, 'Jsr', IX, LONG))
        self.assertNotIn('AE_DEC_PC', self.body(0x4e90, 'Jsr', AI, LONG))

    def test_every_handler_answers_for_a_form_of_its_own(self):
        for handler, (opcode, mode, size) in {
                'Bra': (0x6002, 12, BYTE), 'Bsr': (0x6102, 12, BYTE), 'Cmp': (0xb041, DN, WORD), 'CmpiEa': (0x0c50, AI, WORD), 'CmpiRg': (0x0c40, DN, WORD), 'Cmpa': (0xb0c1, DN, WORD),
                'Tst': (0x4a50, AI, WORD), 'Move3': (0x32c1, DN, WORD), 'Move4': (0x3301, DN, WORD), 'Move5': (0x3341, DN, WORD), 'Move6': (0x3381, DN, WORD), 'Move7': (0x31c1, DN, WORD),
                'Movea': (0x3041, AN, WORD), 'Moveq': (0x7001, 11, LONG), 'AndiEa': (0x0250, AI, WORD), 'AddRgEa': (0xd150, AI, WORD), 'AddqDn': (0x5240, DN, WORD), 'AddqAn': (0x5248, AN, WORD),
                'AddqEa': (0x5250, AI, WORD), 'AddiRg': (0x0640, DN, WORD), 'AddiEa': (0x0650, AI, WORD), 'Adda': (0xd0c1, DN, WORD), 'BitDxEa': (0x0350, AI, BYTE), 'BitDxDy': (0x0341, DN, BYTE),
                'Lea': (0x41d0, AI, LONG), 'Rts': (0x4e75, IP, LONG), 'Swap': (0x4840, DN, WORD), 'Clr': (0x4250, AI, WORD), 'MovemEaRg': (0x4c90, AI, WORD), 'MovemRgEa': (0x48a0, PD, WORD),
                'Ext': (0x4880, DN, WORD), 'NegRg': (0x4440, DN, WORD), 'Pea': (0x4850, AI, LONG), 'Dbcc': (0x51c8, 12, WORD), 'AndEaRg': (0xc051, AI, WORD), 'AndRgEa': (0xc151, AI, WORD),
                'Move8': (0x33c1, DN, WORD), 'Move2': (0x3281, DN, WORD), 'Move0': (0x3001, DN, WORD), 'BitImDy': (0x0800, DN, BYTE), 'BitImEa': (0x0810, AI, BYTE), 'AndiRg': (0x0240, DN, WORD),
                'AddxRg': (0xd141, DN, WORD), 'AddEaRg': (0xd041, DN, WORD), 'Bcc': (0x6602, 12, BYTE), 'ShiftIm': (0xe548, IM, WORD), 'ShiftRg': (0xe168, DN, WORD), 'Jmp': (0x4ed0, AI, LONG),
                'Jsr': (0x4e90, AI, LONG), 'Nop': (0x4e71, IP, LONG)}.items():
            with self.subTest(handler):
                self.assertIn(handler, translate.HANDLERS)
                self.assertIn('\n', self.body(opcode, handler, mode, size))
        self.assertEqual(len(translate.HANDLERS), 50)

    def test_a_negx_is_not_a_clear(self):
        self.assertIsNone(translate.translate(0x4240, 'NegRg', DN, WORD))
        self.assertIn('U64_SUB3', self.body(0x4040, 'NegRg', DN, WORD))
        self.assertIn('~CLIP<Word>(r.d[0])', self.body(0x4640, 'NegRg', DN, WORD))


if __name__ == '__main__':
    unittest.main()
