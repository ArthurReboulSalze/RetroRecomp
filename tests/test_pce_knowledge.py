"""The PC Engine's shared paths on authored ROMs: numbers only, no game, no ROM byte."""
import hashlib
import json
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import knowledge, path_profiles as pp, pce_knowledge as pk

IDENTITY = 'ab' * 32
OTHER = 'cd' * 32
MPR = (0xFF, 0xF8, 1, 2, 3, 4, 5, 0)
OTHER_MPR = (0xFF, 0xF8, 1, 2, 3, 4, 6, 0)


def authored_rom(banks=8, seed=1):
    return random.Random(seed).randbytes(banks * pk.BANK)


def observation(rom, pc, mpr, length, *, offset=None):
    physical = pk.physical_of(pc, mpr, length)
    start = (pk.bank_map(len(rom))[physical[0] >> 13] * pk.BANK + (physical[0] & 0x1fff)) if offset is None else offset
    return {'pc': pc, 'mpr': list(mpr), 'physical': physical, 'data': list(rom[start:start + length]), 'native_hits': 0, 'interpreted_hits': 5}


class BankMapTests(unittest.TestCase):
    def test_the_engine_s_mirror_maps(self):
        self.assertEqual(pk.bank_map(16 * pk.BANK)[0x13], 3)                 # 128 KiB: modulo
        plain = pk.bank_map(48 * pk.BANK)                                    # 384 KiB
        self.assertEqual((plain[0x25], plain[0x45]), (5, 0x25))
        plain = pk.bank_map(64 * pk.BANK)                                    # 512 KiB
        self.assertEqual((plain[0x3F], plain[0x45]), (0x3F, 0x25))
        plain = pk.bank_map(96 * pk.BANK)                                    # 768 KiB
        self.assertEqual((plain[0x3F], plain[0x45]), (0x3F, 0x45))

    def test_a_size_that_is_not_whole_banks_is_refused(self):
        with self.assertRaises(ValueError):
            pk.bank_map(pk.BANK + 1)

    def test_physical_addresses_follow_the_bank_registers_and_wrap(self):
        self.assertEqual(pk.physical_of(0x5FFF, MPR, 2), [(MPR[2] << 13) | 0x1FFF, MPR[3] << 13])
        self.assertEqual(pk.physical_of(0xFFFF, MPR, 2), [(MPR[7] << 13) | 0x1FFF, MPR[0] << 13])


class RecordTests(unittest.TestCase):
    def setUp(self):
        self.rom = authored_rom()
        self.entries = [(MPR, 0x4000, 0x2000, 3), (MPR, 0x4003, 0x2003, 2), (OTHER_MPR, 0x4000, 0x2000, 3)]

    def record(self, entries=None, identity=IDENTITY):
        return pk.make_record(identity, self.rom, self.entries if entries is None else entries)

    def test_a_record_passes_the_schema_3_validator_with_an_empty_layout(self):
        record = self.record()
        pp.validate_game(record)
        self.assertEqual(pk.validate_record(record, IDENTITY), record)
        self.assertEqual(record['identity']['layout'], {})
        self.assertEqual(set(pk.rows(record)), set(self.entries))

    def test_a_record_holds_numbers_about_the_rom_and_no_byte_of_it(self):
        rows = [(MPR, 0x4000 + n, 0x2000 + n, 7) for n in range(0, 700, 7)]
        text = json.dumps(self.record(rows))
        for start in range(0x2000, 0x2000 + 700, 16):
            self.assertNotIn(self.rom[start:start + 16].hex(), text)
        self.assertNotIn('data', text)
        self.assertNotIn('physical', text)

    def test_equal_paths_give_equal_documents_whatever_their_order(self):
        self.assertEqual(self.record(), self.record(list(reversed(self.entries))))

    def test_contexts_are_compared_by_their_values_not_their_numbers(self):
        alone = self.record([(OTHER_MPR, 0x4000, 0x2000, 3)])
        self.assertEqual(pk.entry_set(alone) & pk.entry_set(self.record()), {('pce_insn', (OTHER_MPR, 0x4000, 0x2000, 3))})

    def test_rebuild_and_merge_keep_the_paths(self):
        record = self.record()
        self.assertEqual(pk.rebuild(record, pk.entry_set(record)), record)
        self.assertEqual(pk.rows(pk.rebuild(record, set())), [])
        first, second = self.record(self.entries[:1]), self.record(self.entries[1:])
        self.assertEqual(pk.merged(IDENTITY, first, second), record)

    def test_records_of_another_engine_or_rom_never_mix(self):
        current, old = self.record(self.entries[:1]), pk.make_record(IDENTITY, self.rom, self.entries[1:], core='0' * 40)
        self.assertEqual(pk.merged(IDENTITY, current, old), current)
        self.assertEqual(pk.merged(IDENTITY, old, current), current)

    def test_a_context_the_table_does_not_hold_is_refused(self):
        record = self.record()
        block = record['cpus']['huc6280']['paths']['ram_code'][0]
        rows = pp.decode_table(block['table'], 3, 65536)
        rows[0] = (rows[0][0] + (9 << 16), rows[0][1], rows[0][2])
        block['table'] = pp.encode_table(rows, 3)
        with self.assertRaises(ValueError):
            pk.validate_record(record)
        self.assertIsNone(pk.salvaged_record(IDENTITY, record))

    def test_a_record_of_another_card_is_refused(self):
        with self.assertRaises(ValueError):
            pk.validate_record(self.record(), OTHER)

    def test_the_engine_identity_is_the_pin_not_our_stamp(self):
        from retrorecomp.pce_conversion import ENGINE_REV
        self.assertEqual(pk.engine(), hashlib.sha1(f'pce:{pk.GENERATOR_REVISION}:{ENGINE_REV}'.encode()).hexdigest())


class TranslateTests(unittest.TestCase):
    def setUp(self):
        self.rom = authored_rom()
        self.card_mpr = (0xFF, 0xF8, 1, 2, 3, 4, 5, 0)

    def test_code_on_the_card_is_where_it_runs_from(self):
        rows, counts = pk.translate(self.rom, 'base', [observation(self.rom, 0x4000, self.card_mpr, 3)])
        self.assertEqual(rows, [(self.card_mpr, 0x4000, 1 * pk.BANK, 3)])
        self.assertEqual((counts['card'], counts['ram_tied'], counts['private']), (1, 0, 0))

    def test_work_ram_code_is_tied_to_a_place_of_the_rom_with_the_same_bytes(self):
        item = observation(self.rom, 0x2100, self.card_mpr, 7, offset=0x3456)
        rows, counts = pk.translate(self.rom, 'base', [item])
        self.assertEqual(rows, [(self.card_mpr, 0x2100, self.rom.find(bytes(item['data'])), 7)])
        self.assertEqual(counts['ram_tied'], 1)

    def test_code_the_rom_does_not_hold_stays_private(self):
        missing = next(bytes([n]) * 7 for n in range(256) if bytes([n]) * 7 not in self.rom)
        item = {'pc': 0x2100, 'mpr': list(self.card_mpr), 'physical': pk.physical_of(0x2100, self.card_mpr, 7), 'data': list(missing), 'native_hits': 0, 'interpreted_hits': 1}
        rows, counts = pk.translate(self.rom, 'base', [item])
        self.assertEqual((rows, counts['private']), ([], 1))

    def test_the_street_fighter_board_shares_nothing(self):
        rows, counts = pk.translate(self.rom, 'sf2', [observation(self.rom, 0x4000, self.card_mpr, 3)])
        self.assertEqual((rows, counts['private'], counts['board']), ([], 1, 'sf2'))

    def test_a_mirrored_bank_is_found_at_its_rom_place(self):
        rom = authored_rom(48)
        mpr = (0xFF, 0xF8, 0x45, 2, 3, 4, 5, 0)                 # physical bank $45 is ROM bank $25 on the 384 KiB board
        rows, _ = pk.translate(rom, 'base', [observation(rom, 0x4000, mpr, 2)])
        self.assertEqual(rows, [(mpr, 0x4000, 0x25 * pk.BANK, 2)])

    def test_promote_keeps_the_library_s_paths_and_says_what_it_did(self):
        first, _ = pk.promote(IDENTITY, self.rom, 'base', [observation(self.rom, 0x4000, self.card_mpr, 3)])
        second, counts = pk.promote(IDENTITY, self.rom, 'base', [observation(self.rom, 0x6000, self.card_mpr, 2)], previous=first)
        self.assertEqual(len(pk.rows(second)), 2)
        self.assertEqual(counts['paths'], {'instructions': 2, 'contexts': 1})
        self.assertFalse(counts['truncated'])
        self.assertFalse(counts['raw_bytes_stored'])

    def test_a_previous_record_of_another_engine_is_not_kept(self):
        old = pk.make_record(IDENTITY, self.rom, [(self.card_mpr, 0x4000, pk.BANK, 3)], core='0' * 40)
        record, _ = pk.promote(IDENTITY, self.rom, 'base', [observation(self.rom, 0x6000, self.card_mpr, 2)], previous=old)
        self.assertEqual(len(pk.rows(record)), 1)


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.rom = authored_rom()
        self.mpr = (0xFF, 0xF8, 1, 2, 3, 4, 5, 0)
        self.record = pk.make_record(IDENTITY, self.rom, [(self.mpr, 0x4000, pk.BANK, 3), (self.mpr, 0x6000, 2 * pk.BANK, 2)])

    def test_the_instructions_come_back_from_the_player_s_own_rom(self):
        rows = pk.expanded_rows(self.record, self.rom)
        self.assertEqual({(row['pc'], tuple(row['data'])) for row in rows},
                         {(0x4000, tuple(self.rom[pk.BANK:pk.BANK + 3])), (0x6000, tuple(self.rom[2 * pk.BANK:2 * pk.BANK + 2]))})
        self.assertEqual(rows[0]['physical'], pk.physical_of(rows[0]['pc'], self.mpr, len(rows[0]['data'])))

    def test_another_rom_is_refused_and_counted_as_ignored(self):
        other = authored_rom(seed=2)
        with self.assertRaises(ValueError):
            pk.expanded_rows(self.record, other)
        rows, info = pk.shared_rows(IDENTITY, other, imported=self.record)
        self.assertEqual(rows, [])
        self.assertIn('another ROM', info['ignored']['imported'])

    def test_a_qualified_record_of_another_engine_is_ignored_and_an_imported_one_guides(self):
        old = pk.make_record(IDENTITY, self.rom, pk.rows(self.record), core='0' * 40)
        rows, info = pk.shared_rows(IDENTITY, self.rom, qualified=old)
        self.assertEqual((rows, info['ignored']['qualified']), ([], 'another engine revision'))
        rows, info = pk.shared_rows(IDENTITY, self.rom, imported=old)
        self.assertEqual((len(rows), info['imported']), (2, 2))

    def test_the_capture_holds_what_the_conversion_does_not_know_within_the_bound(self):
        rows = pk.expanded_rows(self.record, self.rom)
        known = {(tuple(rows[0]['mpr']), rows[0]['pc'], tuple(rows[0]['data']))}
        capture, left = pk.received_capture(rows, known, runtime_abi=29, capacity=65536)
        self.assertEqual((len(capture['observations']), left, capture['retired_instructions'], capture['complete']), (1, 0, 1, True))
        capture, left = pk.received_capture(rows, known, runtime_abi=29, capacity=1)
        self.assertEqual((capture, left), (None, 1))
        self.assertEqual(pk.received_capture(rows, {(tuple(r['mpr']), r['pc'], tuple(r['data'])) for r in rows}, runtime_abi=29, capacity=65536), (None, 0))

    def test_the_pinned_engine_reads_the_capture(self):
        engine = Path(__file__).resolve().parents[1] / '.deps' / 'pcenginerecomp'
        if not (engine / 'pcerecomp' / 'capture.py').is_file():
            self.skipTest('the pinned engine is not checked out')
        sys.path.insert(0, str(engine))
        try:
            from pcerecomp.capture import validate_capture
        finally:
            sys.path.remove(str(engine))
        # Real instruction shapes: the decoder checks lengths, so the bytes are authored opcodes (NOP, LDA #, JMP abs).
        rom = bytearray(authored_rom())
        rom[pk.BANK:pk.BANK + 6] = bytes((0xEA, 0xA9, 0x12, 0x4C, 0x00, 0x40))
        rom = bytes(rom)
        record = pk.make_record(IDENTITY, rom, [(self.mpr, 0x4000, pk.BANK, 1), (self.mpr, 0x4001, pk.BANK + 1, 2), (self.mpr, 0x4003, pk.BANK + 3, 3)])
        capture, _ = pk.received_capture(pk.expanded_rows(record, rom), set(), runtime_abi=29, capacity=65536)
        self.assertEqual(len(validate_capture(capture)), 3)


class SharingTests(unittest.TestCase):
    def test_the_pc_engine_is_in_the_experimental_tier_and_withdrawn_with_it(self):
        self.assertIn('pce', pp.EXPERIMENTAL_SHARED)
        self.assertIn('pce', pp.SCHEMA3_ONLY)
        self.assertIn('pce', pp.WITHDRAWABLE)
        self.assertIs(knowledge.schema3_module('pce'), pk)
        with mock.patch.object(pp, 'SHARED_SYSTEMS', tuple(s for s in pp.SHARED_SYSTEMS if s != 'pce')):
            self.assertIsNone(knowledge.schema3_module('pce'))

    def test_a_received_side_bank_record_is_read_for_its_game(self):
        rom = authored_rom()
        record = pk.make_record(IDENTITY, rom, [((0xFF, 0xF8, 1, 2, 3, 4, 5, 0), 0x4000, pk.BANK, 3)])
        self.assertIsNotNone(pk.salvaged_record(IDENTITY, json.loads(json.dumps(record))))

    def test_the_library_reads_only_a_record_a_passed_conversion_wrote(self):
        rom = authored_rom()
        record = pk.make_record(IDENTITY, rom, [((0xFF, 0xF8, 1, 2, 3, 4, 5, 0), 0x4000, pk.BANK, 3)])
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            with mock.patch('retrorecomp.library.library_root', lambda system: folder):
                self.assertIsNone(pk.library_record(IDENTITY))
                (folder / IDENTITY).mkdir()
                summary = folder / IDENTITY / 'compilation.json'
                summary.write_text(json.dumps({'system': 'pce', 'game': IDENTITY, 'fresh_reference_passed': False, 'record': record}), encoding='utf-8')
                self.assertIsNone(pk.library_record(IDENTITY))
                summary.write_text(json.dumps({'system': 'pce', 'game': IDENTITY, 'fresh_reference_passed': True, 'record': record}), encoding='utf-8')
                self.assertEqual(pk.library_record(IDENTITY), record)


if __name__ == '__main__':
    unittest.main()
