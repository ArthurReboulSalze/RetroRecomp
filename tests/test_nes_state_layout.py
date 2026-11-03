"""The NES quick-state serialisers and the key that names their layout (no ROM needed)."""
import tempfile
import unittest
from pathlib import Path

from retrorecomp import nes_state_layout as layout
from retrorecomp.core import ConversionError
from retrorecomp.paths import ROOT

ENGINE = ROOT / '.deps' / 'nesrecomp'


def structs(text, *names):
    return layout.parse(text, set(names))


class StateLayoutGeneratorTests(unittest.TestCase):
    def test_every_member_is_written_one_after_the_other_and_padding_is_not(self):
        known = structs('''typedef struct { uint8_t a; uint32_t b; uint8_t c[3]; uint16_t d; } Padded;''', 'Padded')
        code = layout.generate(known, ['Padded'], preamble=False)
        for member in 'abcd':
            self.assertIn(f'sizeof(s->{member})', code)
        # No whole-struct copy: the compiler's padding between a and b never reaches a file.
        self.assertNotIn('sizeof(Padded)', code)
        self.assertNotIn('sizeof(*s)', code)

    def test_nested_and_anonymous_structs_and_arrays_of_structs(self):
        known = structs('''
            typedef struct { uint8_t x; uint64_t y; } Inner;
            typedef struct { Inner pair[2]; struct { uint16_t p, q; } m; uint8_t tail; } Outer;''', 'Inner', 'Outer')
        code = layout.generate(known, ['Outer'], preamble=False)
        self.assertLess(code.index('rr_ser_Inner('), code.index('rr_ser_Outer('))
        self.assertIn('rr_ser_Inner(b, (const Inner *)&s->pair + i)', code)
        self.assertIn('sizeof(s->m.p)', code)
        self.assertIn('sizeof(s->m.q)', code)

    def test_declarations_with_several_names_and_a_two_word_type(self):
        known = structs('typedef struct { unsigned length, cycles; uint8_t reg[3][3], control; } Many;', 'Many')
        code = layout.generate(known, ['Many'], preamble=False)
        for member in ('length', 'cycles', 'reg', 'control'):
            self.assertIn(f'sizeof(s->{member})', code)

    def test_a_skipped_member_is_not_written_and_any_other_pointer_stops_the_staging(self):
        known = structs('typedef struct { uint8_t *prg; uint32_t len; } HwCart;', 'HwCart')
        code = layout.generate(known, ['HwCart'], preamble=False)
        self.assertNotRegex(code, r'&s->prg\b')
        self.assertIn('sizeof(s->len)', code)
        other = structs('typedef struct { uint8_t *buffer; } Other;', 'Other')
        with self.assertRaises(ConversionError):
            layout.generate(other, ['Other'])

    def test_the_skipped_pointer_is_told_from_a_register_of_the_same_name(self):
        # The cartridge's `prg` pointer is left out; the mapper's PRG register `m.prg` (MMC1, VRC6...) is a state.
        known = structs('typedef struct { uint8_t *prg; struct { uint8_t ctrl, prg; } m; } HwCart;', 'HwCart')
        code = layout.generate(known, ['HwCart'], preamble=False)
        self.assertNotRegex(code, r'&s->prg\b')
        self.assertIn('sizeof(s->m.prg)', code)
        self.assertIn('sizeof(s->m.ctrl)', code)

    def test_what_cannot_be_written_safely_stops_the_staging(self):
        for text in ('typedef struct { uint32_t flag : 1; } Bits;',
                     'typedef struct { union { uint8_t a; uint16_t b; } u; } Bits;',
                     'typedef struct { long value; } Bits;',
                     'typedef struct { long double value; } Bits;',
                     'typedef struct { Unknown inner; } Bits;'):
            with self.subTest(text=text):
                try:
                    known = structs(text, 'Bits')
                    layout.generate(known, ['Bits'])
                except ConversionError:
                    continue
                self.fail('accepted: ' + text)

    def test_conditional_members_keep_their_condition_in_every_function(self):
        known = structs('typedef struct { uint8_t a;\n#if DEBUG\n uint8_t b;\n#endif\n} Cond;', 'Cond')
        code = layout.generate(known, ['Cond'], preamble=False)
        self.assertEqual(code.count('#if DEBUG'), 3)
        self.assertEqual(code.count('#endif'), 3)

    def test_a_file_offset_is_eight_bytes_on_every_host(self):
        code = layout.generate(structs('typedef struct { size_t offset; } Off;', 'Off'), ['Off'], preamble=False)
        self.assertIn('uint64_t', code)
        self.assertIn('n += 8;', code)

    def test_a_missing_root_is_an_error(self):
        with self.assertRaises(ConversionError):
            layout.generate({}, ['Absent'])


@unittest.skipUnless((ENGINE / 'runner/cyc/hw_internal.h').is_file(), 'the pinned NES engine is not checked out')
class StateKeyTests(unittest.TestCase):
    def test_the_state_key_does_not_depend_on_the_build_folder(self):
        from retrorecomp.nes_machine import prepare_machine
        keys, cmakes = [], []
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            for base in (Path(first) / 'a', Path(second) / 'deeper' / 'other place' / 'b'):
                machine = prepare_machine(base, ENGINE)
                keys.append((machine / 'nes_state_abi.h').read_text())
                cmakes.append((machine / 'cyc.cmake').read_text())
        self.assertNotEqual(cmakes[0], cmakes[1], 'the staged build file names the folder, the key must not')
        self.assertEqual(keys[0], keys[1])
        self.assertRegex(keys[0], r'#define RR_NES_STATE_ABI "[0-9a-f]{64}"')

    def test_the_serialisers_are_staged_with_the_engine_structs(self):
        from retrorecomp.nes_machine import prepare_machine
        with tempfile.TemporaryDirectory() as folder:
            machine = prepare_machine(Path(folder) / 'x', ENGINE)
            main = (machine / 'nes_state_main.inc').read_text()
            for name in ('Cpu6502', 'HwMachine', 'HwCart', 'HwPpu', 'Mmc5State', 'NesCartInfo', 'RrMachineState'):
                self.assertIn(f'rr_ser_{name}(', main)
            cart = main[main.index('rr_ser_HwCart('):]
            cart = cart[:cart.index('return b;')]
            self.assertNotRegex(cart, r'&s->(prg|chr)\b')
            # The mapper's own registers are states, among them the PRG register that shares its name with the
            # cartridge's pointer (1.6.5 and 1.6.6 left it out: after F9 a VRC6 game ran on bank 0).
            for register in ('m.prg', 'm.ctrl', 'm.chr0', 'm.chr1'):
                self.assertIn(f'sizeof(s->{register})', main)
            apu = (machine / 'nes_state_apu.inc').read_text()
            self.assertIn('rr_ser_HwApu(', apu)
            self.assertIn('rr_ser_RrAudio(', apu)
            audio = apu[apu.index('rr_ser_RrAudio('):]
            audio = audio[:audio.index('return b;')]
            self.assertNotRegex(audio, r'&s->(ring|head|tail)\b')
            self.assertIn('rr_ser_OPLL(', (machine / 'nes_state_vrc7.inc').read_text())

    def test_every_member_of_a_saved_structure_is_written_or_left_out_for_a_declared_reason(self):
        from retrorecomp.nes_machine import prepare_machine, state_audit
        with tempfile.TemporaryDirectory() as folder:
            machine = prepare_machine(Path(folder) / 'x', ENGINE)
            root = machine.parents[1]
            rows = state_audit(lambda name: (root / name).read_text(encoding='utf-8'))
            written_code = ''.join((machine / name).read_text() for name in
                                   ('nes_state_main.inc', 'nes_state_apu.inc', 'nes_state_vrc7.inc'))
        self.assertGreater(len(rows), 300)
        left_out = {(row['struct'], row['member']): row for row in rows if not row['written']}
        # Nothing is left out without a reason, and every reason in SKIPPED names exactly one member by its path:
        # a name shared by two members of a structure (a pointer and a register) cannot drop one in silence.
        self.assertEqual(set(left_out), set(layout.SKIPPED))
        for key, row in left_out.items():
            self.assertTrue(row['reason'], key)
        for row in rows:
            if row['written']:
                self.assertFalse(row['type'].endswith('*'), f'{row["struct"]}.{row["member"]} is a pointer')
                if row['type'] in layout.FIXED_TYPES:
                    # The writer of a struct reaches its members by path; a struct-typed member goes through its own writer.
                    self.assertIn(f's->{row["member"]}', written_code, f'{row["struct"]}.{row["member"]}')


class AuthoredPrgCartridgeTests(unittest.TestCase):
    def test_each_board_has_its_program_in_the_fixed_bank_and_distinct_banks(self):
        import sys
        sys.path.insert(0, str(ROOT / 'tools'))
        import nes_state_prg_check as check
        for board, spec in check.BOARDS.items():
            with self.subTest(board=board):
                rom = check.authored_cartridge(board)
                self.assertEqual(rom[:4], b'NES')
                self.assertEqual(len(rom), 16 + check.PRG_SIZE + 0x2000)
                self.assertEqual((rom[7] & 0xF0) | (rom[6] >> 4), spec['mapper'])
                prg = rom[16:16 + check.PRG_SIZE]
                first = [prg[index * spec['window']] for index in range(check.PRG_SIZE // spec['window'] - 1)]
                self.assertEqual(len(set(first)), len(first), 'banks must start with different bytes')
                reset = prg[-4] | prg[-3] << 8
                self.assertGreaterEqual(reset, spec['fixed'])
                self.assertEqual(prg[check.PRG_SIZE - (0x10000 - reset)], 0x78, 'the reset vector points at SEI')


if __name__ == '__main__':
    unittest.main()
