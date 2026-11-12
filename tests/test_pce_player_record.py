"""The PC Engine's player's own record (kind 20): what the game notes, how the conversion reads it back from its own ROM, and that the game
really records. Authored ROMs only: numbers about a card, no game, no ROM byte of a real one."""
import random
import re
import unittest
from pathlib import Path

from retrorecomp import feedback, pce_knowledge as pk
from retrorecomp.systems import get_profile

ROOT = Path(__file__).resolve().parents[1]
MPR = (0xFF, 0xF8, 1, 2, 3, 4, 5, 0)          # logical $4000-$5FFF is ROM bank 1, $2000-$3FFF is work RAM


def authored_rom(banks=8, seed=3):
    rom = bytearray(random.Random(seed).randbytes(banks * pk.BANK))
    rom[pk.BANK + 0x10:pk.BANK + 0x13] = bytes((0xA9, 0x42, 0x60))      # bank 1: LDA #$42 then RTS, at logical $4010
    return bytes(rom)


def note(pc, mpr, code, kind=pk.FEEDBACK_KIND, auxiliary=0):
    return feedback.Observation(kind, pc, auxiliary, bytes(mpr) + bytes(code))


class NoteReadingTests(unittest.TestCase):
    def setUp(self):
        self.rom = authored_rom()

    def test_a_note_of_the_card_comes_back_as_a_root_read_from_the_rom(self):
        rows, info = pk.player_rows([note(0x4010, MPR, (0xA9, 0x42))], self.rom)
        self.assertEqual((info['notes'], info['kept'], info['ignored']), (1, 1, {}))
        self.assertEqual(rows, [{'pc': 0x4010, 'mpr': list(MPR), 'data': [0xA9, 0x42], 'rom_offsets': [pk.BANK + 0x10, pk.BANK + 0x11]}])

    def test_what_is_not_the_card_s_is_left_out_and_counted_by_reason(self):
        rows, info = pk.player_rows([
            note(0x2010, MPR, (0xA9, 0x42)),                         # work RAM: not on the card
            note(0x4010, MPR, (0xA9, 0x43)),                         # the card holds other bytes there (another ROM)
            note(0x4010, MPR, (0xA9,)),                              # a length that is not the opcode's
            note(0x10010, MPR, (0xA9, 0x42)),                        # a logical address past 16 bits
            note(0x4010, MPR, (0xA9, 0x42), auxiliary=1),            # a field a note never uses
            note(0x4010, MPR, ()),                                   # no instruction byte at all
            note(0x4010, MPR, (0xA9, 0x42), kind=21),                # another kind: not this record
        ], self.rom)
        self.assertEqual(rows, [])
        self.assertEqual((info['notes'], info['kept']), (6, 0))
        self.assertEqual(info['ignored'], {'not on the card': 1, 'the card holds other bytes there': 1, 'malformed note': 4})

    def test_the_same_instruction_noted_twice_is_one_root(self):
        rows, info = pk.player_rows([note(0x4010, MPR, (0xA9, 0x42)), note(0x4010, MPR, (0xA9, 0x42))], self.rom)
        self.assertEqual((len(rows), info['kept']), (1, 1))

    def test_the_record_is_a_source_of_its_own_beside_the_others(self):
        rows, info = pk.shared_rows('ab' * 32, self.rom, player=[note(0x4010, MPR, (0xA9, 0x42)), note(0x2010, MPR, (0xA9, 0x42))])
        self.assertEqual((len(rows), info['player'], info['qualified'], info['library'], info['imported']), (1, 1, 0, 0, 0))
        self.assertEqual(info['ignored'], {'player': {'not on the card': 1}})
        rows, info = pk.shared_rows('ab' * 32, self.rom)
        self.assertEqual((rows, info['player']), ([], 0))

    def test_the_player_s_rows_come_first_for_the_engine_s_bound(self):
        other = pk.make_record('ab' * 32, self.rom, [(MPR, 0x4020, pk.BANK + 0x20, 2)])
        rows, info = pk.shared_rows('ab' * 32, self.rom, imported=other, player=[note(0x4010, MPR, (0xA9, 0x42))])
        self.assertEqual([row['pc'] for row in rows], [0x4010, 0x4020])
        self.assertEqual((info['player'], info['imported']), (1, 1))

    def test_the_engine_gets_numbers_only(self):
        rows, _ = pk.shared_rows('ab' * 32, self.rom, player=[note(0x4010, MPR, (0xA9, 0x42))])
        roots = pk.roots_document(rows, image_sha256='ab' * 32, header='none', encoding='linear')
        self.assertEqual(roots['roots'], [{'pc': 0x4010, 'mpr': list(MPR), 'selector': 0, 'rom_offsets': [pk.BANK + 0x10, pk.BANK + 0x11]}])
        self.assertFalse(roots['execution_evidence'])


class GameRecordsTests(unittest.TestCase):
    """The profile declares the kind, and the game's sources call the recorder: without them the report would claim a record nobody writes."""

    def test_the_profile_declares_the_kind_the_game_writes(self):
        self.assertIn(pk.FEEDBACK_KIND, get_profile('pce').feedback_kinds)
        self.assertIn(f'RR_FB_PCE={pk.FEEDBACK_KIND}', re.sub(r'\s+', '', (ROOT / 'native/runtime_feedback.h').read_text(encoding='utf-8')))

    def test_the_game_starts_the_recorder_and_registers_its_note(self):
        main = (ROOT / 'native/pce_main.c').read_text(encoding='utf-8')
        self.assertIn('rr_feedback_start(!headless)', main)
        self.assertIn('rr_feedback_note(RR_FB_PCE', main)
        self.assertIn('pce_machine_set_recorder(record_instruction, rr_feedback_enabled)', main)

    def test_the_bridge_notes_what_the_interpreter_ran_on_a_card_bank_of_a_standard_board_only(self):
        bridge = (ROOT / 'native/pce_machine.cpp').read_text(encoding='utf-8')
        self.assertIn('cpu.interpreter_steps != before_interpreted', bridge)
        self.assertIn('recipe.profile == pce::HuCardProfile::base', bridge)
        self.assertIn('policy == pce::ExecutionPolicy::hybrid', bridge)
        self.assertIn('if ((physical >> 13) >= 0x80) return;', bridge)

    def test_the_street_fighter_board_never_records_and_the_report_says_so(self):
        main = (ROOT / 'native/pce_main.c').read_text(encoding='utf-8')
        self.assertIn('if (RR_PCE_BOARD != PCE_BOARD_SF2) {', main)
        conversion = (ROOT / 'retrorecomp/pce_conversion.py').read_text(encoding='utf-8')
        self.assertIn("if card.board != 'base':", conversion)
        self.assertIn("'recording_default': False, 'recording': 'not available on this board'", conversion)

    def test_the_roots_go_to_the_engine_beside_the_history(self):
        from types import SimpleNamespace
        from retrorecomp import pce_conversion
        calls, hints = [], {}
        build = SimpleNamespace(PceBuildError=RuntimeError,
                                emit_roots_module=lambda *args: calls.append(('roots', args[-1])) or {'declared_instructions': 5, 'emitted_instructions': 5},
                                emit_history_module=lambda *args: calls.append(('history', args[-1])) or {})
        manifest, kept = pce_conversion.emit_with_roots(build, 'roots.json', 'image.pce', 'index.json', 'module', hints, lambda text: None)
        self.assertEqual((kept, calls, hints['declared']['declared_instructions']), (True, [('roots', 'module')], 5))
        self.assertEqual(manifest['declared_instructions'], 5)

    def test_a_refusal_of_the_declared_roots_never_fails_the_conversion(self):
        import tempfile
        from types import SimpleNamespace
        from retrorecomp import pce_conversion
        said, hints = [], {}
        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / 'module-1'
            module.mkdir()
            (module / 'half-written.cpp').write_text('x', encoding='ascii')

            def history(index, target):
                self.assertFalse(Path(target).exists())          # the engine writes a new folder only: the refused one is gone
                return {'native_instructions_emitted': 7}

            def refuse(*arguments):
                raise RuntimeError('pcerecomp emit-roots failed (2):\nDuplicate identical declared root\nmore')
            build = SimpleNamespace(PceBuildError=RuntimeError, emit_roots_module=refuse, emit_history_module=history)
            manifest, kept = pce_conversion.emit_with_roots(build, 'roots.json', 'image.pce', 'index.json', module, hints, said.append)
        self.assertEqual((manifest, kept), ({'native_instructions_emitted': 7}, False))
        self.assertEqual(hints, {'declared_refused': 'pcerecomp emit-roots failed (2):'})
        self.assertEqual(len(said), 1)
        self.assertNotIn('declared', hints)

    def test_the_report_says_the_game_learns_only_where_it_records(self):
        conversion = (ROOT / 'retrorecomp/pce_conversion.py').read_text(encoding='utf-8')
        self.assertIn("'runtime_learning': card.board == pce_knowledge.SHARED_BOARD", conversion)

    def test_the_length_table_of_the_bridge_is_the_converter_s(self):
        bridge = (ROOT / 'native/pce_machine.cpp').read_text(encoding='utf-8')
        table = re.search(r'kLengths\{([0-9,]+)\}', bridge)
        self.assertIsNotNone(table)
        self.assertEqual(bytes(int(value) for value in table.group(1).split(',')), pk.INSTRUCTION_LENGTHS)
        self.assertEqual(len(pk.INSTRUCTION_LENGTHS), 256)

    def test_a_note_fits_a_record_of_the_shared_recorder(self):
        # runtime_feedback.c keeps 16 bytes of data per record: eight bank registers and up to seven bytes of one instruction.
        self.assertLessEqual(8 + max(pk.INSTRUCTION_LENGTHS), 16)
        encoded = feedback.encode([note(0x4010, MPR, (0xA9, 0x42))], 'pce', 'ab' * 32)
        rows, _ = feedback.decode(encoded, 'pce', 'ab' * 32)
        self.assertEqual(rows, [note(0x4010, MPR, (0xA9, 0x42))])


if __name__ == '__main__':
    unittest.main()
