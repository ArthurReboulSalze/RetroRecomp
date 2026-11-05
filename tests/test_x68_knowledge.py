"""X68000 in the shared base: numeric records from fresh reference runs, side banks, exchange, base, switch.

The X68000 is supported since 1.6.9 and shares its paths as the experimental tier of the base (like the CPS-1): they are tied to the
engine revision that validated them, carry their own format number, and can be withdrawn with one line. Numbers only: no disk
byte, no IPL byte, no RAM word, no code. No ROM, disk or firmware is involved: the images below are authored.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import knowledge, knowledge_exchange as kx, online, path_profiles as pp, x68_knowledge
from tests import test_shared_base as shared_base

IDENTITY = '6' * 64
KEY = f'x68:{IDENTITY}'
MOVE_W = bytes.fromhex('303c1234')            # move.w #$1234,d0 (two words)
NOP = bytes.fromhex('4e71')
MOVE_L = bytes.fromhex('203c11223344')        # move.l #$11223344,d0 (three words)
RTS = bytes.fromhex('4e75')
PROGRAM = MOVE_W + NOP + MOVE_L + RTS         # 14 bytes, four instructions in a row
LOAD = 0x6000                                 # where the game loads it
BSR = '61001234'                              # bsr.w: a valid instruction that no image holds


def disk(extra=b''):
    """An authored disk image: filler that holds none of the instructions below, and PROGRAM at 0x400."""
    data = bytearray(b'\x00\x01' * 0x1000)
    data[0x400:0x400 + len(PROGRAM)] = PROGRAM
    return bytes(data) + extra


def ipl_image():
    """An authored 128 KiB IPL (no SCSI boot marker): the bytes are the instruction words below at known places."""
    data = bytearray(b'\x4e\x71' * (128 * 1024 // 2))
    data[0x100:0x104] = MOVE_W
    data[0x104:0x106] = RTS
    return bytes(data)


def variant(pc, words):
    return {'pc': pc, 'words': words if isinstance(words, str) else words.hex(), 'hits': 1}


def program_variants(base=LOAD):
    out, pc = [], base
    for raw in (MOVE_W, NOP, MOVE_L, RTS):
        out.append(variant(pc, raw))
        pc += len(raw)
    return out


def ipl_spans(ipl, entries=((0x100, 2), (0x104, 1))):
    return [{'source': 'ipl', 'sha256': hashlib.sha256(ipl).hexdigest(), 'address': 0xfc0000, 'offset': 0, 'length': 128 * 1024,
             'entries': [list(entry) for entry in entries]}]


def a_record(extra=(), with_ipl=True):
    ipl = ipl_image()
    record, _ = x68_knowledge.promote(IDENTITY, disk(), ipl if with_ipl else None, program_variants(),
                                      ipl_spans(ipl) if with_ipl else [])
    return x68_knowledge.rebuild(record, x68_knowledge.entry_set(record) | set(extra)) if extra else record


class WordCountTests(unittest.TestCase):
    def test_the_table_has_the_word_counts_of_known_instructions(self):
        counts = {0x4e75: 1, 0x4e71: 1, 0x303c: 2, 0x203c: 3, 0x4eb9: 3, 0x2039: 3, 0x6100: 2, 0x6000: 2, 0x60ff: 1, 0x4e7a: 1}
        self.assertEqual({word: x68_knowledge.word_count(word) for word in counts}, counts)
        self.assertEqual(len(x68_knowledge.word_counts()), 65536)
        self.assertTrue(all(1 <= n <= 5 for n in x68_knowledge.word_counts()))

    def test_the_table_is_the_one_the_engine_pin_names(self):
        digest = hashlib.sha256(x68_knowledge.word_counts()).hexdigest()
        pins = json.loads(Path(__file__).with_name('x68_generator_pins.json').read_text(encoding='utf-8'))
        self.assertEqual(digest, pins['word_counts_sha256'],
                         'The word-count table changed: it follows the decoder pin; raise x68_knowledge.GENERATOR_REVISION and the pins')


class TranslationTests(unittest.TestCase):
    def test_a_run_of_instructions_in_the_disk_becomes_one_span_of_numbers(self):
        spans, ipl_rows, counts = x68_knowledge.translate(disk(), None, program_variants(), [])
        self.assertEqual(spans, [(LOAD, 0x400, len(PROGRAM))])
        self.assertEqual(ipl_rows, [])
        self.assertEqual((counts['ram']['observed'], counts['ram']['tied'], counts['ram']['private'], counts['ram']['spans']), (4, 4, 0, 1))
        self.assertEqual(counts['ram']['anchored'], 4)           # a span of 14 bytes is a place of the disks

    def test_a_short_instruction_found_by_chance_is_tied_but_not_anchored(self):
        # `rts` is somewhere in any image: it is tied (a ceiling, and a valid hint) but a two-byte span proves nothing about where the code comes from.
        spans, _, counts = x68_knowledge.translate(disk(), None, [variant(0x7000, RTS)], [])
        self.assertEqual((len(spans), counts['ram']['tied'], counts['ram']['anchored']), (1, 1, 0))
        self.assertEqual(x68_knowledge.ANCHOR_BYTES, 8)

    def test_an_instruction_that_no_even_offset_holds_is_found_private_without_a_search_of_the_image(self):
        image = x68_knowledge._Image(disk())
        self.assertFalse(image.may_contain(bytes.fromhex(BSR)))
        self.assertEqual(image.find(bytes.fromhex(BSR)), -1)
        self.assertEqual(image.find(PROGRAM), 0x400)
        self.assertEqual(image.find(PROGRAM), 0x400, 'the answer is kept')
        # A false alarm of the hashed table is searched and found absent, never reported present.
        self.assertEqual(image.find_run(bytes.fromhex('303c12344e7199')), -1)
    def test_what_is_not_in_the_disks_stays_private_and_is_counted(self):
        variants = program_variants() + [variant(0x7000, BSR), variant(0xe00010, RTS)]
        spans, _, counts = x68_knowledge.translate(disk(), None, variants, [])
        self.assertEqual(spans, [(LOAD, 0x400, len(PROGRAM))])
        self.assertEqual((counts['ram']['private'], counts['other_windows']['private']), (1, 1))
        self.assertEqual(counts['ram']['tied'] + counts['ram']['private'] + counts['other_windows']['observed'], 6)

    def test_a_gap_or_a_difference_ends_a_run_and_the_longest_found_prefix_is_kept(self):
        # The third instruction is not the one the disk holds after the second: the run is cut after two.
        changed = program_variants()
        changed[2] = variant(LOAD + 6, '203c99999999')
        spans, _, counts = x68_knowledge.translate(disk(), None, changed, [])
        self.assertEqual(spans[0], (LOAD, 0x400, len(MOVE_W) + len(NOP)))
        self.assertEqual(counts['ram']['tied'], 3)         # the rts after the changed one is found alone, elsewhere
        # A hole in the addresses starts a second run.
        spans, _, _ = x68_knowledge.translate(disk(), None, program_variants()[:2] + program_variants(LOAD + 0x100)[2:], [])
        self.assertEqual([row[0] for row in spans], [LOAD, LOAD + 0x106])

    def test_malformed_observations_are_ignored(self):
        junk = [variant(LOAD + 1, MOVE_W), variant(LOAD, '30'), variant(LOAD, 'zz11'), {'pc': 'x', 'words': '4e75'},
                variant(LOAD, '303c'), variant(LOAD, '4e75' * 12), 'not a row']
        spans, _, counts = x68_knowledge.translate(disk(), None, junk, [])
        self.assertEqual(spans, [])
        self.assertEqual(counts['malformed'], len(junk))

    def test_an_instruction_that_is_not_one_of_the_word_count_table_is_not_shared(self):
        # 0x303c takes two words: the observed bytes of one word are not that instruction.
        spans, _, counts = x68_knowledge.translate(disk(), None, [variant(LOAD, '303c')], [])
        self.assertEqual((spans, counts['malformed']), ([], 1))

    def test_ipl_code_becomes_positions_in_the_ipl_it_was_observed_with(self):
        ipl = ipl_image()
        _, rows, counts = x68_knowledge.translate(disk(), ipl, [], ipl_spans(ipl))
        self.assertEqual(rows, [(0xfc0100, 0x100, 4), (0xfc0104, 0x104, 2)])
        self.assertEqual(counts['ipl'], {'observed': 2, 'tied': 2, 'private': 0})
        # Spans observed with another IPL, or an IPL not mapped as the file is (a SCSI boot marker), are not shared.
        other = bytearray(ipl)
        other[0x10600:0x10604] = b'\x00\xfc\x00\x00'
        _, rows, counts = x68_knowledge.translate(disk(), bytes(other), [], ipl_spans(ipl))
        self.assertEqual((rows, counts['ipl']['private']), ([], 2))
        _, rows, counts = x68_knowledge.translate(disk(), bytes(other), [], ipl_spans(bytes(other)))
        self.assertEqual((rows, counts['ipl']['private']), ([], 2))

    def test_the_paths_rebuild_the_very_instructions_from_the_players_own_images(self):
        ipl = ipl_image()
        record = a_record()
        expanded, left = x68_knowledge.expanded_rows(record, disk(), ipl)
        self.assertEqual(left, {})
        self.assertEqual(sorted(expanded), sorted([(row['pc'], row['words']) for row in program_variants()]
                                                 + [(0xfc0100, MOVE_W.hex()), (0xfc0104, RTS.hex())]))

    def test_the_record_holds_no_byte_of_the_disk_or_the_ipl(self):
        text = json.dumps(a_record())
        data, ipl = disk(), ipl_image()
        for image in (data, ipl):
            for start in range(0x3f0, 0x420, 2):
                self.assertNotIn(image[start:start + 8].hex(), text)
        self.assertNotIn(PROGRAM.hex(), text)
        self.assertNotIn('words', text)

    def test_promotion_keeps_what_the_library_already_held_for_these_images_and_engine(self):
        ipl = ipl_image()
        first = a_record()
        more = [variant(0x6100, MOVE_W), variant(0x6104, NOP)]
        record, counts = x68_knowledge.promote(IDENTITY, disk(), ipl, more, [], previous=first)
        spans, ipl_rows = x68_knowledge.rows(record)
        self.assertEqual(sorted(spans), [(LOAD, 0x400, 14), (0x6100, 0x400, 6)])
        self.assertEqual(len(ipl_rows), 2, 'the IPL paths of the same IPL are kept')
        # A record of other disks or another IPL is not carried over.
        other_ipl = bytearray(ipl)
        other_ipl[0x200:0x202] = b'\x00\x00'
        record, _ = x68_knowledge.promote(IDENTITY, disk(), bytes(other_ipl), more, [], previous=first)
        self.assertEqual(x68_knowledge.rows(record)[1], [])
        record, _ = x68_knowledge.promote(IDENTITY, disk(b'\x00\x00'), ipl, more, [], previous=first)
        self.assertEqual(len(x68_knowledge.rows(record)[0]), 1)

    def test_the_rows_are_bounded_and_the_cut_is_reported(self):
        variants = [variant(0x1000 + 0x10 * index, MOVE_W) for index in range(20)]
        with patch.object(x68_knowledge, 'SPAN_LIMIT', 5):
            record, counts = x68_knowledge.promote(IDENTITY, disk(), None, variants, [])
        self.assertTrue(counts['truncated'])
        self.assertEqual(len(x68_knowledge.rows(record)[0]), 5)
        record, counts = x68_knowledge.promote(IDENTITY, disk(), None, variants, [])
        self.assertFalse(counts['truncated'])


class RecordTests(unittest.TestCase):
    def test_a_record_is_a_valid_schema_3_document_with_its_own_format(self):
        record = a_record()
        pp.validate_game(record)
        self.assertEqual(record['identity']['layout'], {'format': x68_knowledge.FORMAT})
        self.assertEqual(set(record['identity']['sources']), {'disk', 'ipl'})
        self.assertEqual(set(record['cpus']), {'m68k'})
        self.assertEqual(x68_knowledge.record_engine(record), x68_knowledge.engine())
        self.assertEqual(x68_knowledge.validate_record(record, IDENTITY), record)
        with self.assertRaises(ValueError):
            x68_knowledge.validate_record(record, '7' * 64)
        self.assertEqual(set(a_record(with_ipl=False)['identity']['sources']), {'disk'})

    def test_a_format_this_converter_does_not_know_is_skipped_not_fatal(self):
        newer = a_record()
        newer['identity']['layout']['format'] = 2
        with self.assertRaises(x68_knowledge.UnknownFormat):
            x68_knowledge.validate_record(newer, IDENTITY)
        self.assertIsNone(x68_knowledge.salvaged_record(IDENTITY, newer))
        self.assertEqual(x68_knowledge.salvaged_record(IDENTITY, a_record()), a_record())

    def test_a_record_that_lies_about_its_sources_or_machine_is_refused(self):
        def broken(mutate):
            record = json.loads(json.dumps(a_record()))
            mutate(record)
            with self.assertRaises(ValueError):
                x68_knowledge.validate_record(record, IDENTITY)
        broken(lambda r: r['identity']['sources'].pop('disk'))
        broken(lambda r: r['identity']['sources'].update(cart={'bytes': 4, 'sha256': '1' * 64}))
        broken(lambda r: r['identity']['sources']['ipl'].update(bytes=1000))
        broken(lambda r: r['identity']['sources']['ipl'].pop('sha256'))
        broken(lambda r: r['identity']['sources']['disk'].pop('sha256'))
        broken(lambda r: r['identity']['sources']['disk'].update(bytes=7))
        broken(lambda r: r['identity']['layout'].update(ram_mib=2))
        broken(lambda r: r['identity'].update(system='cps1'))
        broken(lambda r: r['cpus'].update(z80=r['cpus']['m68k']))
        broken(lambda r: r.update(devices={'gsu': {}}))
        broken(lambda r: r['cpus']['m68k']['paths']['spans'][0].update(src='ipl'))
        broken(lambda r: r['cpus']['m68k']['paths']['ram_code'][0].update(src='disk'))
        broken(lambda r: r['cpus']['m68k']['paths'].update(entries=[pp._table_block('phys', [(2,)], 1, 'disk')]))

    def test_rows_outside_their_image_or_the_address_windows_are_refused(self):
        ipl = ipl_image()
        for spans, ipl_rows in (([(LOAD, len(disk()) - 4, 14)], []),               # beyond the disks
                                ([(0xc00000, 0, 4)], []),                          # not RAM
                                ([(LOAD + 1, 0, 4)], []),                          # odd address
                                ([(LOAD, 1, 4)], []),                              # odd offset
                                ([], [(0xfc0000, 128 * 1024 - 2, 4)]),             # beyond the IPL
                                ([], [(0x1000, 0, 4)])):                           # IPL rows live in the IPL window
            record = x68_knowledge.make_record(IDENTITY, disk(), ipl, spans, ipl_rows)
            with self.assertRaises(ValueError, msg=str((spans, ipl_rows))):
                x68_knowledge.validate_record(record, IDENTITY)

    def test_merging_never_mixes_engines_or_images(self):
        first = a_record()
        richer = a_record(extra={('x68_span', (0x7000, 0x400, 4))})
        merged = x68_knowledge.merged(IDENTITY, first, richer)
        self.assertEqual(x68_knowledge.entry_set(merged), x68_knowledge.entry_set(richer))
        other_engine = json.loads(json.dumps(richer))
        other_engine['cpus']['m68k']['core'] = '9' * 40
        self.assertEqual(x68_knowledge.merged(IDENTITY, first, other_engine), first)
        self.assertEqual(x68_knowledge.merged(IDENTITY, other_engine, first), first)
        other_images, _ = x68_knowledge.promote(IDENTITY, disk(b'\x00\x00'), None, program_variants(), [])
        self.assertEqual(x68_knowledge.merged(IDENTITY, first, other_images), first)
        self.assertEqual(x68_knowledge.merged(IDENTITY, {}, first), first)

    def test_two_players_with_the_same_disks_and_different_ipls_hold_records_of_the_same_game(self):
        ipl = ipl_image()
        other = bytearray(ipl)
        other[0x300:0x302] = b'\x00\x00'
        other = bytes(other)
        mine = a_record()                                           # disk paths and the IPL rows of `ipl`
        yours, _ = x68_knowledge.promote(IDENTITY, disk(), other, program_variants()[:2] + [variant(0x6100, MOVE_W)], ipl_spans(other, entries=((0x100, 2),)))
        bare = a_record(with_ipl=False)                             # a record with no IPL row names no IPL
        self.assertTrue(x68_knowledge.same_images(mine, yours))
        self.assertTrue(x68_knowledge.same_images(mine, bare))
        both = x68_knowledge.merged(IDENTITY, mine, yours)
        # The disk paths of both are kept; the IPL rows only of one IPL (the first's), never mixed.
        self.assertEqual(set(x68_knowledge.rows(both)[0]), set(x68_knowledge.rows(mine)[0]) | set(x68_knowledge.rows(yours)[0]))
        self.assertEqual(x68_knowledge.rows(both)[1], x68_knowledge.rows(mine)[1])
        self.assertEqual(both['identity']['sources']['ipl'], mine['identity']['sources']['ipl'])
        # A record with no IPL rows takes the other's; the same IPL unites the rows.
        merged_bare = x68_knowledge.merged(IDENTITY, bare, mine)
        self.assertEqual(x68_knowledge.rows(merged_bare)[1], x68_knowledge.rows(mine)[1])
        richer, _ = x68_knowledge.promote(IDENTITY, disk(), ipl, [], ipl_spans(ipl, entries=((0x108, 1),)))
        united = x68_knowledge.merged(IDENTITY, mine, richer)
        self.assertEqual(len(x68_knowledge.rows(united)[1]), 3)
        self.assertEqual(x68_knowledge.merged(IDENTITY, bare, a_record(with_ipl=False)), bare)

    def test_the_hints_are_for_these_disks_and_this_ipl_only(self):
        record, ipl = a_record(), ipl_image()
        with self.assertRaises(ValueError):
            x68_knowledge.expanded_rows(record, disk(b'\x00\x00'), ipl)
        other = bytearray(ipl)
        other[0x300:0x302] = b'\x00\x00'
        rows, left = x68_knowledge.expanded_rows(record, disk(), bytes(other))
        self.assertEqual(len(rows), 4)
        self.assertEqual(left, {'ipl': 'another IPL'})
        rows, left = x68_knowledge.expanded_rows(record, disk(), None)
        self.assertEqual((len(rows), left), (4, {'ipl': 'another IPL'}))

    def test_shared_rows_count_what_each_source_gave_and_why_one_was_ignored(self):
        record, ipl = a_record(), ipl_image()
        stale = json.loads(json.dumps(record))
        stale['cpus']['m68k']['core'] = '9' * 40
        rows, info = x68_knowledge.shared_rows(IDENTITY, disk(), ipl, qualified=stale, imported=record, library=record)
        self.assertEqual(info['ignored'], {'qualified': 'another engine revision'})
        self.assertEqual((info['qualified'], info['library'], info['imported']), (0, 6, 6))
        self.assertEqual(len(rows), 12)
        newer = json.loads(json.dumps(record))
        newer['identity']['layout']['format'] = 2
        rows, info = x68_knowledge.shared_rows(IDENTITY, disk(), ipl, imported=newer, library={'junk': 1})
        self.assertEqual(rows, [])
        self.assertEqual(set(info['ignored']), {'imported', 'library'})


class EngineTests(unittest.TestCase):
    def setUp(self):
        x68_knowledge.engine_core.cache_clear()
        self.addCleanup(x68_knowledge.engine_core.cache_clear)

    def test_each_input_of_the_engine_moves_the_core(self):
        base = x68_knowledge.engine()
        self.assertRegex(base, '^[0-9a-f]{40}$')
        with patch.object(x68_knowledge, 'GENERATOR_REVISION', 99):
            x68_knowledge.engine_core.cache_clear()
            self.assertNotEqual(x68_knowledge.engine(), base)
        x68_knowledge.engine_core.cache_clear()
        from retrorecomp import console16
        pinned = dict(console16.REPOSITORIES, md=(console16.REPOSITORIES['md'][0], '5' * 40))
        with patch('retrorecomp.console16.REPOSITORIES', pinned):
            x68_knowledge.engine_core.cache_clear()
            self.assertNotEqual(x68_knowledge.engine(), base)
        x68_knowledge.engine_core.cache_clear()
        real = x68_knowledge.text_digest
        with patch.object(x68_knowledge, 'text_digest', side_effect=lambda name, root=None: 'f' * 64 if name.endswith('decode.c') else real(name, root)):
            x68_knowledge.engine_core.cache_clear()
            self.assertNotEqual(x68_knowledge.engine(), base)
        x68_knowledge.engine_core.cache_clear()
        self.assertEqual(x68_knowledge.engine(), base)

    def test_text_is_hashed_without_line_ends_and_the_files_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'a.c').write_bytes(b'one\r\ntwo\r\n')
            (Path(folder) / 'b.c').write_bytes(b'one\ntwo\n')
            self.assertEqual(x68_knowledge.text_digest('a.c', Path(folder)), x68_knowledge.text_digest('b.c', Path(folder)))
        for name in x68_knowledge.NATIVE_INPUTS + x68_knowledge.GENERATOR_SOURCES:
            self.assertTrue((Path(__file__).resolve().parents[1] / name).is_file(), name)

    # The Python that generates the code a RAM path becomes. Editing one of these files without raising
    # x68_knowledge.GENERATOR_REVISION would let a path validated by the old code count as qualified for the new one, so this test
    # fails until both are done: raise the revision, then update the digests of tests/x68_generator_pins.json.
    def test_the_generator_sources_are_pinned_to_their_revision(self):
        root = Path(__file__).resolve().parents[1]
        found = {name: x68_knowledge.text_digest(name, root) for name in x68_knowledge.GENERATOR_SOURCES}
        pins = json.loads(Path(__file__).with_name('x68_generator_pins.json').read_text(encoding='utf-8'))
        self.assertEqual(pins['revision'], x68_knowledge.GENERATOR_REVISION,
                         'GENERATOR_REVISION changed: update tests/x68_generator_pins.json')
        self.assertEqual(pins['sources'], found,
                         'An X68000 generator source changed: raise x68_knowledge.GENERATOR_REVISION (the X68000 paths qualified by '
                         'the old code must be validated again), then update tests/x68_generator_pins.json')


class Library:
    """An X68000 library and side banks in a temporary folder."""

    def start(self, test):
        temp = tempfile.TemporaryDirectory()
        test.addCleanup(temp.cleanup)
        test.root = Path(temp.name).resolve()
        test.library = test.root / 'library' / 'x68'
        test.folder = test.root / 'datas' / 'knowledge'
        test.imported = test.folder / 'imported.json.gz'
        test.qualified = test.folder / 'qualified.json.gz'
        environment = {name: value for name, value in os.environ.items()
                       if name not in ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_BUNDLED_KNOWLEDGE')}
        for item in (patch.dict(os.environ, environment, clear=True),
                     patch('retrorecomp.library.library_root', side_effect=lambda system='sms': test.root / 'library' / system),
                     patch('retrorecomp.paths.data_directory', return_value=test.root / 'datas'),
                     patch('retrorecomp.knowledge.imported_path', return_value=test.imported),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=test.imported)):
            item.start()
            test.addCleanup(item.stop)
        for name in ('_imported_bank', '_qualified_bank', '_side_games', '_observation_bank'):
            test.addCleanup(getattr(knowledge, name).cache_clear)

    def keep(self, test, record, **flags):
        directory = test.library / IDENTITY
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'compilation.json').write_text(json.dumps({
            'schema': 1, 'system': 'x68', 'title': 'Test', 'game': IDENTITY, 'source_identity': '8' * 64, 'rom_sha256': IDENTITY,
            'fresh_reference_passed': True, 'record': record, **flags}), encoding='utf-8')


class LibraryTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)

    def test_the_record_of_a_verified_conversion_is_read_back_and_anything_else_is_not(self):
        self.assertIsNone(x68_knowledge.library_record(IDENTITY))
        Library().keep(self, a_record())
        self.assertEqual(x68_knowledge.library_record(IDENTITY), a_record())
        Library().keep(self, a_record(), fresh_reference_passed=False)
        self.assertIsNone(x68_knowledge.library_record(IDENTITY))
        Library().keep(self, a_record(), game='9' * 64)
        self.assertIsNone(x68_knowledge.library_record(IDENTITY))
        Library().keep(self, a_record(), system='cps1')
        self.assertIsNone(x68_knowledge.library_record(IDENTITY))
        damaged = a_record()
        damaged['cpus']['m68k']['core'] = 'not a core'
        Library().keep(self, damaged)
        self.assertIsNone(x68_knowledge.library_record(IDENTITY))
        (self.library / IDENTITY / 'compilation.json').write_text('{ not json', encoding='utf-8')
        self.assertIsNone(x68_knowledge.library_record(IDENTITY))
        # A summary written before 1.6.9 has no record.
        (self.library / IDENTITY / 'compilation.json').write_text(json.dumps(
            {'schema': 1, 'system': 'x68', 'game': IDENTITY, 'fresh_reference_passed': True}), encoding='utf-8')
        self.assertIsNone(x68_knowledge.library_record(IDENTITY))


class SideBankTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)

    def test_the_schema_1_banks_never_change_by_a_byte_when_the_x68000_is_stored(self):
        self.assertFalse(self.imported.exists() or self.qualified.exists())
        knowledge.write_side_bank(knowledge.imported_v3_path(), {KEY: a_record()})
        knowledge.write_side_bank(knowledge.qualified_v3_path(), {KEY: a_record()})
        self.assertFalse(self.imported.exists() or self.qualified.exists(), 'no schema 1 bank is created or touched')
        self.assertEqual(knowledge.imported_game('x68', IDENTITY), a_record())
        self.assertEqual(knowledge.qualified_game('x68', IDENTITY), a_record())

    def test_a_damaged_or_unknown_game_is_set_aside_alone(self):
        newer = a_record()
        newer['identity']['layout']['format'] = 2
        other = f'x68:{"5" * 64}'
        knowledge.write_side_bank(knowledge.imported_v3_path(), {KEY: a_record()})
        document = json.loads(__import__('gzip').decompress(knowledge.imported_v3_path().read_bytes()))
        document['games'][other] = newer
        knowledge.imported_v3_path().write_bytes(__import__('gzip').compress(json.dumps(document).encode(), mtime=0))
        knowledge._side_games.cache_clear()
        self.assertEqual(knowledge.imported_game('x68', IDENTITY), a_record())
        self.assertEqual(knowledge.imported_game('x68', '5' * 64), {})

    def test_withdrawing_the_x68000_from_the_sharing_reads_nothing_and_breaks_nothing(self):
        knowledge.write_side_bank(knowledge.imported_v3_path(), {KEY: a_record()})
        before = knowledge.imported_v3_path().read_bytes()
        stable = pp.STABLE_SHARED + tuple(system for system in pp.EXPERIMENTAL_SHARED if system != 'x68')
        with patch.object(pp, 'SHARED_SYSTEMS', stable), patch.object(pp, 'SCHEMA3_ONLY', tuple(s for s in pp.SCHEMA3_ONLY if s != 'x68')), \
                patch.object(kx, 'SYSTEMS', stable):
            self.assertIsNone(knowledge.schema3_module('x68'))
            self.assertEqual(knowledge.imported_game('x68', IDENTITY), {})
            self.assertEqual(knowledge.qualified_game('x68', IDENTITY), {})
            self.assertFalse(knowledge.discard_imported('x68', IDENTITY, 'x'))
        self.assertEqual(knowledge.imported_v3_path().read_bytes(), before, 'the file was not touched')
        self.assertEqual(knowledge.imported_game('x68', IDENTITY), a_record(), 'it comes back with the name')

    def test_the_x68000_is_the_experimental_tier_of_the_base_and_nothing_gates_on_its_status(self):
        from retrorecomp.systems.x68000 import X68000Profile
        self.assertEqual(X68000Profile.status, 'supported')
        self.assertEqual(X68000Profile.shared_knowledge.tier, 'experimental')
        self.assertTrue(X68000Profile.shared_knowledge.withdrawable)
        self.assertIn('x68', pp.EXPERIMENTAL_SHARED)
        self.assertIn('x68', pp.SHARED_SYSTEMS)
        import inspect
        for function in (x68_knowledge.promote, x68_knowledge.shared_rows, x68_knowledge.translate, kx.collect_knowledge):
            text = inspect.getsource(function)
            self.assertNotIn('.status', text.replace("getattr(game, 'status'", ''))
            self.assertNotIn('.experimental', text)


def library_report(**changes):
    record = a_record()
    value = {'tool': 'Retro-Recomp', 'created_utc': '2026-11-05T10:00:00+00:00', 'system': {'id': 'x68'},
             'rom': {'sha256': IDENTITY}, 'native_validation': {'passed': True}, 'scan_level': 'standard', 'status': 'supported',
             'knowledge': {'record_sha256': x68_knowledge.record_digest(record), 'machine_status': 'supported'}}
    return {**value, **changes}


class ExchangeTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)
        self.path = self.root / 'report.json'
        patcher = patch('retrorecomp.knowledge_exchange.engines', side_effect=lambda: {})
        patcher.start()
        self.addCleanup(patcher.stop)

    def game(self, **changes):
        self.path.write_text(json.dumps(library_report(**changes)), encoding='utf-8')
        return SimpleNamespace(system='x68', identity=IDENTITY, title='Test Game', report=str(self.path), source='',
                               watch='', status='current')

    def collect(self, game=None):
        with patch('retrorecomp.knowledge_exchange._current_engines', return_value={'x68': x68_knowledge.engine()}):
            return kx.collect_knowledge([game or self.game()])

    def test_the_library_record_of_a_verified_conversion_is_collected_as_numbers_and_travels_in_a_version_3_file(self):
        Library().keep(self, a_record())
        found = self.collect()
        self.assertEqual((found['games'], found['consoles']), (1, {'x68': 1}))
        self.assertEqual(found['payload']['consoles']['x68'][IDENTITY], a_record())
        self.assertEqual(found['levels'], {'x68': {IDENTITY: 'standard'}})
        self.assertEqual(found['observations'], {})
        self.assertNotIn('words', json.dumps(found['payload']))
        shared = self.root / 'share.rrknowledge'
        result = kx.write_knowledge(found, shared, channel='file', version=3)
        self.assertEqual(result['version'], 3)
        document = kx.read_exchange(shared)
        self.assertEqual(document['knowledge']['consoles']['x68'][IDENTITY], a_record())
        paths = kx.discovery_paths(document)
        self.assertEqual((len(paths[('x68', IDENTITY)]['hints']), paths[('x68', IDENTITY)]['known']), (3, False))

    def test_what_is_not_qualified_for_these_disks_and_this_engine_is_not_shared(self):
        Library().keep(self, a_record())
        self.assertEqual(self.collect(self.game(status='current', knowledge={'record_sha256': '0' * 64}))['games'], 0)
        other = a_record()
        other['cpus']['m68k']['core'] = '9' * 40
        Library().keep(self, other)
        self.assertEqual(self.collect()['games'], 0)
        Library().keep(self, a_record(), fresh_reference_passed=False)
        self.assertEqual(self.collect()['games'], 0)

    def test_import_keeps_the_side_bank_apart_and_adds_only_what_is_new(self):
        shared = self.root / 'share.rrknowledge'
        record = a_record()
        found = {'games': 1, 'consoles': {'x68': 1}, 'discoveries': 6, 'omitted': {}, 'observations': {},
                 'observation_count': 0, 'payload': {'schema': 1, 'consoles': {'x68': {IDENTITY: record}}},
                 'titles': {'x68': {IDENTITY: 'Test Game'}}, 'levels': {}, 'converted': {}}
        kx.write_knowledge(found, shared, channel=None, version=3)
        preview = kx.preview_import(shared)
        self.assertEqual((preview['games'], preview['consoles']), (1, {'x68': 1}))
        outcome = kx.import_knowledge(shared)
        self.assertEqual((outcome['new'], outcome['consoles']), (1, {'x68': 1}))
        self.assertEqual(knowledge.imported_game('x68', IDENTITY), record)
        self.assertEqual(knowledge.read(self.imported), {'schema': 1, 'consoles': {}}, 'the schema 1 bank is untouched')
        self.assertEqual(kx.import_knowledge(shared)['unchanged'], 1)
        richer = a_record(extra={('x68_span', (0x7000, 0x400, 4))})
        found['payload']['consoles']['x68'][IDENTITY] = richer
        kx.write_knowledge(found, shared, channel=None, version=3)
        self.assertEqual(kx.import_knowledge(shared)['enriched'], 1)
        self.assertEqual(knowledge.imported_game('x68', IDENTITY), richer)

    def test_a_game_of_a_format_this_converter_does_not_know_is_left_out_alone(self):
        newer = a_record()
        newer['identity']['layout']['format'] = 2
        outcome = kx.import_fetched({KEY: {'records': [newer, a_record()], 'observations': []}})
        self.assertEqual(outcome['accepted'][KEY], {'records': 1, 'observations': 0})
        self.assertEqual(knowledge.imported_game('x68', IDENTITY), a_record())


class BaseTests(shared_base.BaseHarness):
    """The base carries the X68000 (format 3 holds it); the converter qualifies what its engine qualified and keeps the rest to check."""

    def setUp(self):
        super().setUp()
        Library().start(self)
        self.addCleanup(knowledge._side_games.cache_clear)
        self.engines['x68'] = x68_knowledge.engine()

    def entry(self, *, qualified=(), parts=()):
        value = {'format': 3, 'system': 'x68', 'identity': IDENTITY,
                 'qualified': sorted(qualified, key=lambda item: item['cores']),
                 'parts': sorted(parts, key=lambda item: item['source'])}
        return hashlib.sha256(kx.canonical_bytes(value)).hexdigest(), value

    def publish3(self, version, sha, sources, value):
        self.publish(version, {KEY: (sha, sources)}, entries=[(sha, value)])

    def test_qualified_for_this_engine_goes_to_the_qualified_side_bank_the_rest_is_to_check(self):
        mine = a_record()
        other = a_record(extra={('x68_span', (0x7100, 0x400, 4))})
        other['cpus']['m68k']['core'] = '9' * 40            # an earlier revision of the engine
        waiting = a_record(extra={('x68_span', (0x7200, 0x400, 4))})
        sha, value = self.entry(
            qualified=[{'cores': kx.record_engine('x68', mine), 'level': 'extended', 'by': 'players', 'record': mine},
                       {'cores': kx.record_engine('x68', other), 'level': 'standard', 'by': 'maintainer', 'record': other}],
            parts=[{'source': 47, 'level': 'standard', 'record': waiting, 'observations': []}])
        self.publish3(5, sha, [47], value)
        prepared = online.prepare_batch([KEY])
        self.assertEqual((prepared['base']['version'], prepared['base']['games'], prepared['base']['qualified']), (5, 1, 1))
        self.assertEqual(knowledge.qualified_game('x68', IDENTITY), mine)
        imported = knowledge.imported_game('x68', IDENTITY)
        self.assertTrue(x68_knowledge.entry_set(imported) >= x68_knowledge.entry_set(mine))
        self.assertIn(('x68_span', (0x7200, 0x400, 4)), x68_knowledge.entry_set(imported))
        self.assertEqual(knowledge.imported_observations('x68', IDENTITY), [], 'no raw rows for the X68000')
        self.assertEqual(knowledge.read(self.imported), {'schema': 1, 'consoles': {}}, 'schema 1 banks untouched')
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['sources'], use['qualified']['by'], use['qualified']['engine']), ([47], 'players', x68_knowledge.engine()))

    def test_a_new_engine_revision_makes_every_qualified_path_wait_again(self):
        mine = a_record()
        sha, value = self.entry(qualified=[{'cores': kx.record_engine('x68', mine), 'level': 'standard', 'by': 'players', 'record': mine}])
        self.publish3(5, sha, [47], value)
        self.engines['x68'] = '8' * 40
        online.prepare_batch([KEY])
        self.assertEqual(knowledge.qualified_game('x68', IDENTITY), {})
        self.assertEqual(knowledge.imported_game('x68', IDENTITY), mine, 'still guides discovery, checked like everything else')

    def test_an_entry_of_a_format_this_converter_does_not_know_gives_nothing_and_breaks_nothing(self):
        newer = a_record()
        newer['identity']['layout']['format'] = 2
        sha, value = self.entry(qualified=[{'cores': kx.record_engine('x68', a_record()), 'level': 'standard', 'by': 'players',
                                            'record': newer}])
        self.publish3(5, sha, [47], value)
        online.prepare_batch([KEY])
        self.assertEqual(knowledge.qualified_game('x68', IDENTITY), {})


class StampTests(unittest.TestCase):
    def setUp(self):
        Library().start(self)

    def test_the_knowledge_stamp_follows_the_side_banks(self):
        from retrorecomp.compilation_inputs import knowledge_stamp
        empty = knowledge_stamp('x68', IDENTITY)
        self.assertEqual(empty, hashlib.sha256(b'{}').hexdigest())
        knowledge.write_side_bank(knowledge.qualified_v3_path(), {KEY: a_record()})
        qualified = knowledge_stamp('x68', IDENTITY)
        self.assertNotEqual(qualified, empty)
        knowledge.write_side_bank(knowledge.imported_v3_path(), {KEY: a_record(extra={('x68_span', (0x7000, 0x400, 4))})})
        self.assertNotEqual(knowledge_stamp('x68', IDENTITY), qualified)


class ReportTests(unittest.TestCase):
    def test_the_report_says_whether_the_x68000_is_in_the_sharing_not_always_yes(self):
        from retrorecomp import x68000_conversion
        record = a_record()
        promotion = {'paths': {'ram_spans': 1, 'ipl': 2}, 'ram': {}, 'other_windows': {}, 'malformed': 0, 'ipl': {}, 'truncated': False}
        shared = x68000_conversion.knowledge_block(record, promotion, {})
        self.assertIs(shared['shared'], True)
        self.assertEqual(shared['cores'], x68_knowledge.engine())
        self.assertEqual(shared['record_sha256'], x68_knowledge.record_digest(record))
        self.assertEqual(shared['machine_status'], 'supported')
        self.assertIs(shared['raw_words_stored'], False)
        stable = tuple(system for system in pp.SHARED_SYSTEMS if system != 'x68')
        with patch.object(pp, 'SHARED_SYSTEMS', stable):
            self.assertIs(x68000_conversion.knowledge_block(record, promotion, {})['shared'], False)


if __name__ == '__main__':
    unittest.main()
