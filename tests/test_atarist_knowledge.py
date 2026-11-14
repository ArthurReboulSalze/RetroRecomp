"""Atari ST in the shared base: numeric records from fresh reference runs, rebuilt from the player's own disks and TOS.

The Atari ST shares its paths as the experimental tier of the base (like the X68000 and the Amiga, on the common `m68k_media_knowledge`): they are tied to the engine
revision that validated them, carry their own format number and can be withdrawn with one line. Numbers only: no disk byte, no TOS byte, no RAM word, no code. No ROM,
disk or TOS is involved: the images below are authored. What the common part does for every machine is tested in tests/test_m68k_media_knowledge.py; here is what is the
Atari ST's: its TOS rows, the logical content of its disks, its engine, its profile and its library of one summary per TOS.
"""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from retrorecomp import atarist_disk, atarist_knowledge as ak, knowledge, m68k_media_knowledge as media, path_profiles as pp
from retrorecomp.systems import get_profile

IDENTITY = '7' * 64
KEY = f'atarist:{IDENTITY}'
MOVE_W = bytes.fromhex('303c1234')            # move.w #$1234,d0 (two words)
NOP = bytes.fromhex('4e71')
MOVE_L = bytes.fromhex('203c11223344')        # move.l #$11223344,d0 (three words)
RTS = bytes.fromhex('4e75')
PROGRAM = MOVE_W + NOP + MOVE_L + RTS         # 14 bytes, four instructions in a row
LOAD = 0x6000                                 # where the game loads it
BSR = '61001234'                              # bsr.w: a valid instruction that no image holds


def disk(extra=b''):
    """An authored disk content: filler that holds none of the instructions below, and PROGRAM at 0x400."""
    data = bytearray(b'\x00\x01' * 0x1000)
    data[0x400:0x400 + len(PROGRAM)] = PROGRAM
    return bytes(data) + extra


def tos_image(fill=b'\x4e\x71'):
    """An authored 192 KiB TOS: `fill` everywhere and the words below at known places."""
    data = bytearray(fill * (ak.TOS_BYTES // len(fill)))
    data[0x100:0x104] = MOVE_W
    data[0x104:0x106] = RTS
    return bytes(data)


def program_observed(base=LOAD):
    out, pc = [], base
    for raw in (MOVE_W, NOP, MOVE_L, RTS):
        out.append((pc, raw.hex()))
        pc += len(raw)
    return out


def tos_observed():
    return [(ak.TOS_BASE + 0x100, MOVE_W.hex()), (ak.TOS_BASE + 0x104, RTS.hex())]


def a_record():
    record, _ = ak.promote(IDENTITY, disk(), tos_image(), program_observed() + tos_observed())
    return record


class RecordTests(unittest.TestCase):
    def test_a_conversion_makes_one_span_and_the_tos_rows_and_no_byte(self):
        record, counts = ak.promote(IDENTITY, disk(), tos_image(), program_observed() + tos_observed())
        spans, tos_rows = ak.rows(record)
        self.assertEqual(spans, [(LOAD, 0x400, len(PROGRAM))])
        self.assertEqual(tos_rows, [(ak.TOS_BASE + 0x100, 0x100, 4), (ak.TOS_BASE + 0x104, 0x104, 2)])
        self.assertEqual(counts['ram']['anchored'], 4)
        self.assertEqual(counts['tos'], {'observed': 2, 'tied': 2, 'private': 0})
        self.assertFalse(counts['raw_words_stored'])
        text = json.dumps(record)
        for raw in (MOVE_W, MOVE_L):
            self.assertNotIn(raw.hex(), text)
        self.assertEqual(record['game'], KEY)
        self.assertEqual(set(record['identity']['sources']), {'disk', 'tos'})
        self.assertEqual(record['identity']['layout'], {})          # no format number: a layout key would move every console's game stamp
        self.assertIsNone(ak.FORMAT)

    def test_what_is_not_in_the_images_stays_private_and_counted(self):
        observed = program_observed() + [(0x8000, BSR), (0x8004, '6002'), (ak.TOS_BASE + 0x200, MOVE_W.hex()), (0xFA0030, NOP.hex()), (0x9001, NOP.hex()), (0x9000, '4e')]
        record, counts = ak.promote(IDENTITY, disk(), tos_image(), observed)
        self.assertEqual(ak.rows(record)[0], [(LOAD, 0x400, len(PROGRAM))])
        self.assertEqual(ak.rows(record)[1], [])
        self.assertEqual(counts['tos'], {'observed': 2, 'tied': 0, 'private': 2})        # the bytes of this TOS at that place are not the observed ones; Hatari's cartridge code
        self.assertEqual(counts['malformed'], 2)                                          # an odd address, a half instruction
        self.assertGreaterEqual(counts['ram']['private'], 1)

    def test_the_record_validates_and_refuses_what_is_not_the_machines(self):
        record = a_record()
        self.assertIs(ak.validate_record(record, IDENTITY), record)
        with self.assertRaises(ValueError):
            ak.validate_record(record, '8' * 64)
        wrong = json.loads(json.dumps(record))
        wrong['game'] = 'x68:' + IDENTITY
        with self.assertRaises(ValueError):
            ak.validate_record(wrong)
        future = json.loads(json.dumps(record))
        future['identity']['layout'] = {'format': 2}
        with self.assertRaises(ValueError):
            ak.validate_record(future)
        self.assertIsNone(ak.salvaged_record(IDENTITY, future))
        self.assertIs(ak.salvaged_record(IDENTITY, record), record)

    def test_a_tos_row_outside_the_tos_window_and_a_span_beyond_the_ram_are_refused(self):
        outside = ak.make_record(IDENTITY, disk(), tos_image(), (), [(ak.TOS_BASE - 4, 0, 4)])
        with self.assertRaises(ValueError):
            ak.validate_record(outside)
        wide = ak.make_record(IDENTITY, disk(), None, [(ak.RAM_LIMIT - 4, 0x400, len(PROGRAM))], ())
        with self.assertRaises(ValueError):
            ak.validate_record(wide)

    def test_the_paths_are_the_profile_ceilings_and_the_names_those_of_entry_set(self):
        profile = pp.PROFILES[('m68k', 'atarist')]
        self.assertEqual(ak.PATH_CAPS, {'atarist_span': profile.caps['span'], 'atarist_tos': profile.caps['insn']})
        self.assertEqual(ak.KNOWLEDGE.path_caps, ak.PATH_CAPS)
        self.assertEqual({name for name, _ in ak.entry_set(a_record())}, set(ak.PATH_CAPS))

    def test_a_game_of_custom_tracks_only_still_has_a_source_for_its_tos_rows(self):
        raw = b'IPFRAW' * 100
        content = ak.disk_content([('stx', raw)])
        self.assertEqual(content, raw)                                    # no standard sector: the images themselves
        self.assertEqual(ak.disk_content([('stx', raw + b'x')]), raw + b'x\0')   # an odd size is padded: the common part refuses it
        record, counts = ak.promote(IDENTITY, content, tos_image(), program_observed() + tos_observed())
        self.assertEqual(ak.rows(record)[0], [])                         # nothing of the program is in the images
        self.assertEqual(len(ak.rows(record)[1]), 2)                     # the TOS rows travel


class ExpandTests(unittest.TestCase):
    def test_a_player_with_the_same_images_gets_the_same_instructions(self):
        out, left = ak.expanded_rows(a_record(), disk(), tos_image())
        self.assertEqual(left, {})
        self.assertEqual(sorted(out), sorted(program_observed() + tos_observed()))

    def test_other_disks_refuse_the_record_and_another_tos_leaves_its_rows_out(self):
        record = a_record()
        with self.assertRaises(ValueError):
            ak.expanded_rows(record, disk(b'\x00\x00'), tos_image())
        out, left = ak.expanded_rows(record, disk(), tos_image(b'\x4e\x75'))
        self.assertEqual(left, {'tos': 'another TOS'})
        self.assertEqual(sorted(out), sorted(program_observed()))

    def test_shared_rows_counts_each_source_and_says_what_it_ignored(self):
        record = a_record()
        rows, info = ak.shared_rows(IDENTITY, disk(), tos_image(), qualified=record, imported=record, library=record)
        self.assertEqual((info['qualified'], info['library'], info['imported']), (6, 6, 6))
        self.assertEqual(len(rows), 18)
        stale = ak.make_record(IDENTITY, disk(), None, [(LOAD, 0x400, len(PROGRAM))], (), core='0' * 40)
        rows, info = ak.shared_rows(IDENTITY, disk(), tos_image(), qualified=stale, imported=stale)
        self.assertEqual(info['ignored'], {'qualified': 'another engine revision'})
        self.assertEqual(info['imported'], 4)                   # an imported path guides whatever its engine; the guard and the validation decide
        other, info = ak.shared_rows(IDENTITY, disk(b'\x00\x00'), tos_image(), qualified=record)
        self.assertEqual(other, [])
        self.assertIn('qualified', info['ignored'])


class MergeTests(unittest.TestCase):
    def test_promote_keeps_the_previous_records_paths_for_the_same_images(self):
        first, _ = ak.promote(IDENTITY, disk(), tos_image(), program_observed())
        second, counts = ak.promote(IDENTITY, disk(), tos_image(), tos_observed(), previous=first)
        self.assertEqual((len(ak.rows(second)[0]), len(ak.rows(second)[1])), (1, 2))
        self.assertFalse(counts['truncated'])

    def test_another_tos_keeps_the_first_records_tos_rows_and_other_engines_never_mix(self):
        first = a_record()
        other_tos, _ = ak.promote(IDENTITY, disk(), tos_image(b'\x4e\x75'), [(ak.TOS_BASE + 0x100, '4e75')] + program_observed())
        union = ak.merged(IDENTITY, first, other_tos)
        self.assertEqual(union['identity']['sources']['tos'], first['identity']['sources']['tos'])
        old = ak.make_record(IDENTITY, disk(), None, [(LOAD, 0x400, len(PROGRAM))], (), core='1' * 40)
        self.assertEqual(ak.merged(IDENTITY, old, first), first)       # the current engine's record is kept
        self.assertEqual(ak.merged(IDENTITY, first, old), first)

    def test_entry_set_and_rebuild_round_trip(self):
        record = a_record()
        self.assertEqual(ak.rebuild(record, ak.entry_set(record)), record)


class RecordRulesTests(unittest.TestCase):
    def test_the_rules_the_site_reads_accept_and_refuse_the_records_validate_record_does(self):
        """RECORD_RULES is what the site's builder reads, so it must say what the converter enforces: an interpreter of the rules and `validate_record` agree on records the schema
        and the profile accept."""
        rules = ak.RECORD_RULES

        def accepted_by_rules(value) -> bool:
            identity = value['identity']
            sources = identity['sources']
            if list(identity['layout']) != rules['layout'] or set(sources) - set(rules['sources']['only']) or set(rules['sources']['required']) - set(sources):
                return False
            if rules['sources']['hashed'] and not all('sha256' in source for source in sources.values()):
                return False
            for cpu, section in value['cpus'].items():
                for kind, blocks in section['paths'].items():
                    rule = rules['paths'][cpu][kind]
                    for block in blocks:
                        if block['src'] != rule['src'] or rule['requires'] not in sources:
                            return False
                        low, end = rule['window']
                        if any(not low <= row[0] or row[0] + row[2] > end for row in pp.decode_table(block['table'], 3, 1 << 20)):
                            return False
            return True

        def judged(value):
            try:
                pp.validate_game(value)
            except ValueError:
                return None                 # the schema and the profile refuse it: not a question for the rules
            try:
                ak.validate_record(value, IDENTITY)
                return True
            except ValueError:
                return False

        good = a_record()
        cases = [good, ak.make_record(IDENTITY, disk(), None, [(LOAD, 0x400, len(PROGRAM))], ()),
                 ak.make_record(IDENTITY, disk(), tos_image(), [(ak.TOS_BASE, 0x400, 4)], ()),                  # a span in the TOS window
                 ak.make_record(IDENTITY, disk(), tos_image(), (), [(0x20000, 0x100, 4)]),                     # a TOS row in RAM
                 ak.make_record(IDENTITY, disk(), tos_image(), [(ak.RAM_LIMIT - 4, 0x400, 4)], [(ak.TOS_BASE + ak.TOS_BYTES - 4, 0x2FFFC, 4)])]
        no_hash = json.loads(json.dumps(good))
        no_hash['identity']['sources']['tos'].pop('sha256')
        no_tos = json.loads(json.dumps(good))
        no_tos['identity']['sources'].pop('tos')
        layout = json.loads(json.dumps(good))
        layout['identity']['layout'] = {'format': 1}
        cases += [no_hash, no_tos, layout]
        seen = set()
        for value in cases:
            verdict = judged(value)
            if verdict is None:
                continue
            seen.add(verdict)
            self.assertEqual(accepted_by_rules(value), verdict, json.dumps(value)[:200])
        self.assertEqual(seen, {True, False})
        self.assertIsNone(rules['sources']['game'])          # the game id is the SHA-256 of the file the player gave, not a source's


class EngineTests(unittest.TestCase):
    def test_the_engine_is_a_digest_of_hatari_the_native_files_and_the_revision(self):
        self.assertRegex(ak.engine(), '^[0-9a-f]{40}$')
        self.assertEqual(ak.engine(), ak.engine_core())
        self.assertEqual(ak.record_engine(a_record()), ak.engine())
        self.assertEqual(ak.record_engine(None), '')

    def test_the_generator_sources_are_pinned_with_the_revision(self):
        pins = json.loads(Path(__file__).with_name('atarist_generator_pins.json').read_text(encoding='utf-8'))
        root = Path(__file__).resolve().parents[1]
        found = {name: hashlib.sha256((root / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in ak.GENERATOR_SOURCES}
        self.assertEqual(pins['revision'], ak.GENERATOR_REVISION, 'GENERATOR_REVISION changed: update tests/atarist_generator_pins.json')
        self.assertEqual(pins['sources'], found, 'a generator source changed: raise atarist_knowledge.GENERATOR_REVISION if a path could notice (the old paths must be '
                                                  'validated again), then update tests/atarist_generator_pins.json')

    def test_the_word_counts_are_the_common_modules_table(self):
        self.assertIs(ak.word_count, media.word_count)


class ProfileTests(unittest.TestCase):
    def test_the_profile_declares_the_experimental_tier_its_module_and_the_common_stamp_group(self):
        profile = get_profile('atarist')
        shared = profile.shared_knowledge
        self.assertEqual((shared.tier, shared.withdrawable, shared.module, shared.quick_check_from_shared), ('experimental', True, 'atarist_knowledge', False))
        self.assertIn('m68k_media_knowledge', profile.stamp_groups)
        self.assertIn('atarist', pp.EXPERIMENTAL_SHARED)
        self.assertIn('atarist', pp.SHARED_SYSTEMS)
        self.assertIs(knowledge.schema3_module('atarist'), ak)

    def test_the_machine_leaves_the_sharing_with_one_line(self):
        with patch.object(pp, 'SHARED_SYSTEMS', tuple(s for s in pp.SHARED_SYSTEMS if s != 'atarist')):
            self.assertIsNone(knowledge.schema3_module('atarist'))


class LibraryTests(unittest.TestCase):
    def test_the_library_record_is_read_from_the_summaries_of_the_tos_folders(self):
        record = a_record()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            game = root / IDENTITY
            for key, rec, passed in (('tos-emutos-1.4', record, True), ('tos-abc', record, False), ('tos-def', {'garbage': 1}, True)):
                (game / key).mkdir(parents=True)
                (game / key / 'compilation.json').write_text(json.dumps({'system': 'atarist', 'game': IDENTITY, 'fresh_reference_passed': passed, 'record': rec}), encoding='utf-8')
            with patch('retrorecomp.library.library_root', lambda system: root):
                self.assertEqual(ak.library_record(IDENTITY), record)
                self.assertIsNone(ak.library_record('9' * 64))


def st_image(sectors_per_track=9, tracks=2):
    """An authored plain-sector ST image: sector n holds n % 251 repeated."""
    boot = bytearray(512)
    struct.pack_into('<HH', boot, 24, sectors_per_track, 2)
    out = bytearray()
    for lsn in range(sectors_per_track * 2 * tracks):
        out += bytes(boot) if lsn == 0 else bytes([lsn % 251]) * 512
    return bytes(out)


class LogicalContentTests(unittest.TestCase):
    def test_a_plain_sector_image_is_its_own_content_and_an_unreadable_one_has_none(self):
        image = st_image()
        self.assertEqual(atarist_disk.logical_content(image, 'st'), image)
        self.assertEqual(atarist_disk.logical_content(image, '.ST'), image)
        self.assertEqual(atarist_disk.logical_content(b'garbage', 'stx'), b'')
        self.assertEqual(atarist_disk.logical_content(b'garbage', 'ipf'), b'')

    def test_the_disks_of_a_game_follow_each_other(self):
        one, two = st_image(), st_image(tracks=1)
        self.assertEqual(ak.disk_content([('st', one), ('st', two)]), one + two)


if __name__ == '__main__':
    unittest.main()
