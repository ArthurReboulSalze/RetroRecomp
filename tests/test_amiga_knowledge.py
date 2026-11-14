"""The Amiga in the shared base: numeric records of RAM code tied to the player's own install and of Kickstart code tied to the player's
own Kickstart (retrorecomp/amiga_knowledge.py on the common part, retrorecomp/m68k_media_knowledge.py), and what a conversion does with them.

Numbers only: no install byte, no Kickstart byte, no RAM word, no code. No install, ROM or Kickstart is involved: the images below are
authored.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import amiga_conversion, amiga_knowledge, knowledge, path_profiles as pp

IDENTITY = '5' * 64
MOVE_W = bytes.fromhex('303c1234')            # move.w #$1234,d0 (two words)
NOP = bytes.fromhex('4e71')
MOVE_L = bytes.fromhex('203c11223344')        # move.l #$11223344,d0 (three words)
RTS = bytes.fromhex('4e75')
PROGRAM = MOVE_W + NOP + MOVE_L + RTS         # 14 bytes, four instructions in a row
LOAD = 0x20000                                # where the slave loads it (chip RAM)
BSR = '61001234'                              # bsr.w: a valid instruction that no image holds


def install(extra=b''):
    """An authored install medium: filler that holds none of the instructions below, and PROGRAM at 0x400."""
    data = bytearray(b'\x00\x01' * 0x1000)
    data[0x400:0x400 + len(PROGRAM)] = PROGRAM
    return bytes(data) + extra


def kickstart():
    """An authored 256 KiB Kickstart: NOPs, with MOVE_W and RTS at known places."""
    data = bytearray(NOP * (0x40000 // 2))
    data[0x100:0x104] = MOVE_W
    data[0x104:0x106] = RTS
    return bytes(data)


def variant(pc, words):
    return {'pc': pc, 'words': words if isinstance(words, str) else words.hex()}


def program_variants(base=LOAD):
    out, pc = [], base
    for raw in (MOVE_W, NOP, MOVE_L, RTS):
        out.append(variant(pc, raw))
        pc += len(raw)
    return out


KICK_OBSERVED = [(0xFC0100, MOVE_W.hex()), (0xFC0104, RTS.hex())]


def a_record(with_kickstart=True):
    record, _ = amiga_knowledge.promote(IDENTITY, install(), kickstart() if with_kickstart else None, program_variants(),
                                        KICK_OBSERVED if with_kickstart else [])
    return record


class RecordTests(unittest.TestCase):
    def test_a_run_of_instructions_in_the_install_becomes_one_span_and_kickstart_code_rows_of_its_image(self):
        spans, kick_rows, counts = amiga_knowledge.translate(install(), kickstart(), program_variants(), KICK_OBSERVED)
        self.assertEqual(spans, [(LOAD, 0x400, len(PROGRAM))])
        self.assertEqual(kick_rows, [(0xFC0100, 0x100, 4), (0xFC0104, 0x104, 2)])
        self.assertEqual(counts['ram'], {'observed': 4, 'tied': 4, 'anchored': 4, 'private': 0, 'spans': 1})
        self.assertEqual(counts['kickstart'], {'observed': 2, 'tied': 2, 'private': 0})

    def test_kickstart_code_a_slave_patched_or_outside_the_window_stays_private(self):
        observed = [(0xFC0100, BSR), (0xFC0104, RTS.hex()), (0xF80000, RTS.hex()), (0xFC0105, RTS.hex()), (0xFC0200, 'zz')]
        _, kick_rows, counts = amiga_knowledge.translate(install(), kickstart(), [], observed)
        self.assertEqual(kick_rows, [(0xFC0104, 0x104, 2)])
        self.assertEqual(counts['kickstart'], {'observed': 5, 'tied': 1, 'private': 4})
        # Another size of Kickstart: nothing is tied to it.
        self.assertEqual(amiga_knowledge.translate(install(), kickstart()[:0x20000], [], KICK_OBSERVED)[1], [])

    def test_code_that_is_not_in_the_install_stays_private_and_is_counted(self):
        variants = program_variants() + [variant(0x30000, BSR)]
        spans, _, counts = amiga_knowledge.translate(install(), None, variants, [])
        self.assertEqual(spans, [(LOAD, 0x400, len(PROGRAM))])
        self.assertEqual(counts['ram']['private'], 1)

    def test_a_record_is_a_valid_schema_3_document_of_the_amiga_with_numbers_only(self):
        record = a_record()
        self.assertIs(pp.validate_game(record), record)
        self.assertEqual(record['game'], f'amiga:{IDENTITY}')
        self.assertEqual(record['identity']['layout'], {})          # no format number of its own, as the Game Boy Advance's
        self.assertEqual(set(record['identity']['sources']), {'install', 'kickstart'})
        self.assertEqual(record['identity']['sources']['kickstart'], {'bytes': 0x40000, 'sha256': hashlib.sha256(kickstart()).hexdigest()})
        text = json.dumps(record)
        for raw in (PROGRAM, MOVE_L, kickstart()[0x100:0x106]):
            self.assertNotIn(raw.hex(), text)
        self.assertEqual({name for name, _ in amiga_knowledge.entry_set(record)}, set(amiga_knowledge.PATH_CAPS))
        profile = pp.PROFILES[('m68k', 'amiga')]
        self.assertEqual(amiga_knowledge.PATH_CAPS, {'amiga_span': profile.caps['span'], 'amiga_kick': profile.caps['insn']})
        # A record without Kickstart rows does not name a Kickstart.
        self.assertEqual(set(a_record(with_kickstart=False)['identity']['sources']), {'install'})

    def test_a_record_that_lies_is_refused_with_the_amigas_words(self):
        def refused(change):
            broken = json.loads(json.dumps(a_record()))
            change(broken)
            with self.assertRaises(ValueError) as caught:
                amiga_knowledge.validate_record(broken, IDENTITY)
            return str(caught.exception)
        self.assertEqual(refused(lambda r: r['identity']['layout'].update(format=9)), 'Invalid layout.')
        # A Kickstart of another size: refused by the schema's bounds of the Amiga's sources.
        self.assertEqual(refused(lambda r: r['identity']['sources']['kickstart'].update(bytes=0x80000)), 'Invalid source size.')
        self.assertIn('Amiga', refused(lambda r: r['identity']['sources']['install'].update(bytes=0x2001)))
        with self.assertRaises(ValueError) as caught:
            amiga_knowledge.validate_record(a_record(), '6' * 64)
        self.assertEqual(str(caught.exception), 'Amiga hints do not match their install identity.')

    def test_rows_outside_ram_or_the_kickstart_window_are_refused(self):
        record = a_record()
        far = amiga_knowledge.make_record(IDENTITY, install(), None, [(0xE00000, 0x400, 4)])
        with self.assertRaises(ValueError):
            amiga_knowledge.validate_record(far, IDENTITY)
        boot = amiga_knowledge.make_record(IDENTITY, install(), kickstart(), [], [(0xF80100, 0x100, 4)])
        with self.assertRaises(ValueError):
            amiga_knowledge.validate_record(boot, IDENTITY)
        self.assertIs(amiga_knowledge.validate_record(record, IDENTITY), record)


class RecordRulesTests(unittest.TestCase):
    def test_the_rules_the_site_reads_accept_and_refuse_the_records_validate_record_does(self):
        """RECORD_RULES is what the site's builder reads, so it must say what the converter enforces: an interpreter of the rules and
        `validate_record` agree on records the schema and the profile accept."""
        rules = amiga_knowledge.RECORD_RULES

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
                amiga_knowledge.validate_record(value, IDENTITY)
                return True
            except ValueError:
                return False

        good = a_record()
        cases = [good, a_record(with_kickstart=False),
                 amiga_knowledge.make_record(IDENTITY, install(), None, [(0xFC0000, 0x400, 4)]),          # a span in the Kickstart window
                 amiga_knowledge.make_record(IDENTITY, install(), kickstart(), [], [(0x20000, 0x100, 4)]),  # a Kickstart row in RAM
                 amiga_knowledge.make_record(IDENTITY, install(), kickstart(), [(0xDBFFFC, 0x400, 4)], [(0xFFFFFC, 0x3FFFC, 4)])]
        no_hash = json.loads(json.dumps(good))
        no_hash['identity']['sources']['kickstart'].pop('sha256')
        no_kick = json.loads(json.dumps(good))
        no_kick['identity']['sources'].pop('kickstart')
        layout = json.loads(json.dumps(good))
        layout['identity']['layout'] = {}
        cases += [no_hash, no_kick, layout]
        seen = set()
        for value in cases:
            verdict = judged(value)
            if verdict is None:
                continue
            seen.add(verdict)
            self.assertEqual(accepted_by_rules(value), verdict, json.dumps(value)[:200])
        self.assertEqual(seen, {True, False})
        self.assertIsNone(rules['sources']['game'])          # the game id is the archive's SHA-256, not a source's


class ExpansionTests(unittest.TestCase):
    def test_the_paths_rebuild_the_very_instructions_from_the_players_own_install_and_kickstart(self):
        rows, left = amiga_knowledge.expanded_rows(a_record(), install(), kickstart())
        self.assertEqual(left, {})
        self.assertEqual(sorted(rows), sorted([(v['pc'], v['words']) for v in program_variants()] + KICK_OBSERVED))

    def test_another_kickstart_gives_the_install_rows_only_and_says_why(self):
        other = bytearray(kickstart())
        other[0] ^= 1
        rows, left = amiga_knowledge.expanded_rows(a_record(), install(), bytes(other))
        self.assertEqual(left, {'kickstart': 'another Kickstart'})
        self.assertEqual(sorted(rows), sorted((v['pc'], v['words']) for v in program_variants()))
        with self.assertRaises(ValueError) as caught:
            amiga_knowledge.expanded_rows(a_record(), install(b'\0\0'), kickstart())
        self.assertEqual(str(caught.exception), 'Amiga hints are for other install files.')

    def test_shared_rows_count_each_bank_and_ignore_a_qualified_record_of_another_engine(self):
        record = a_record()
        stale = json.loads(json.dumps(record))
        stale['cpus']['m68k']['core'] = '0' * 40
        rows, info = amiga_knowledge.shared_rows(IDENTITY, install(), kickstart(), qualified=stale, imported=record)
        self.assertEqual(info['ignored'], {'qualified': 'another engine revision'})
        self.assertEqual(info['imported'], 6)
        self.assertEqual(len(rows), 6)


class InstallMediaTests(unittest.TestCase):
    def test_the_install_media_is_the_slave_then_the_files_by_name_each_padded_to_an_even_length(self):
        members = [SimpleNamespace(name='g/game.slave'), SimpleNamespace(name='g/data/b'), SimpleNamespace(name='g/data/a')]
        files = {'b': members[1], 'a': members[2]}
        stored = {'g/game.slave': b'SLV', 'g/data/b': b'BB', 'g/data/a': b'A'}
        with patch('retrorecomp.amiga_whdload.install', return_value=SimpleNamespace(slave_path='g/game.slave', files=files)), \
                patch('retrorecomp.amiga_lha.members', return_value=members), \
                patch('retrorecomp.amiga_lha.extract', side_effect=lambda blob, member: stored[member.name]):
            self.assertEqual(amiga_knowledge.install_content(b'archive'), b'SLV\0' + b'A\0' + b'BB')


class ConversionTests(unittest.TestCase):
    """What the conversion takes from the records it is offered, and the record it keeps."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.library = Path(folder.name)
        # The library is this folder: the conversion and the knowledge module both read it through the variable.
        patcher = patch.dict(os.environ, {'RETRO_RECOMP_LIBRARY_DIR': str(self.library)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.source = SimpleNamespace(game_key=IDENTITY, sha256=IDENTITY)

    def test_received_rows_are_split_between_ram_and_the_kickstart_and_checked_like_observations(self):
        with patch.object(knowledge, 'qualified_game', return_value=None), patch.object(knowledge, 'imported_game', return_value=a_record()):
            ram, kick, info = amiga_conversion.shared_hints(self.source, install(), kickstart())
        self.assertEqual(ram, {(v['pc'], v['words']) for v in program_variants()})
        self.assertEqual(kick, {0xFC0100, 0xFC0104})
        self.assertEqual(info['imported'], 6)
        # A row the generator cannot take (outside the Amiga's apertures) fails the conversion: the batch converts again without it.
        with patch.object(amiga_knowledge, 'shared_rows', return_value=([(0xA00000, NOP.hex())], {'imported': 1})):
            with self.assertRaises(Exception):
                amiga_conversion.shared_hints(self.source, install(), None)

    def test_nothing_is_offered_when_the_install_cannot_be_read(self):
        self.assertEqual(amiga_conversion.shared_hints(self.source, None, None)[2]['ignored'], {'install': 'unreadable'})

    def test_the_kept_record_is_read_back_merged_with_the_next_conversions(self):
        record, promotion = amiga_conversion.promoted_record(self.source, install(), kickstart(), {(v['pc'], v['words']) for v in program_variants()},
                                                             set(KICK_OBSERVED))
        amiga_conversion.keep_record(self.source, record, promotion)
        self.assertEqual(amiga_knowledge.library_record(IDENTITY), record)
        self.assertTrue((self.library / 'amiga' / IDENTITY / amiga_knowledge.RECORD_FILE).is_file())
        # A later conversion that saw less keeps what the record held; one of another Kickstart keeps the first Kickstart's rows.
        later, _ = amiga_conversion.promoted_record(self.source, install(), None, set(), set())
        self.assertEqual(amiga_knowledge.entry_set(later), amiga_knowledge.entry_set(record) - {('amiga_kick', row) for row in amiga_knowledge.rows(record)[1]})
        block = amiga_conversion.knowledge_block(record, promotion, {'imported': 0})
        self.assertEqual(block['record_sha256'], amiga_knowledge.record_digest(record))
        self.assertEqual(block['received'], {'offered': 0, 'reached': 0, 'added': 0})
        self.assertIs(block['shared'], True)
        self.assertEqual(block['promotion']['kickstart'], {'observed': 2, 'tied': 2, 'private': 0})


class EngineTests(unittest.TestCase):
    def setUp(self):
        amiga_knowledge.engine_core.cache_clear()
        self.addCleanup(amiga_knowledge.engine_core.cache_clear)

    def test_each_input_of_the_engine_moves_the_core(self):
        base = amiga_knowledge.engine()
        self.assertRegex(base, '^[0-9a-f]{40}$')
        with patch.object(amiga_knowledge, 'GENERATOR_REVISION', 99):
            amiga_knowledge.engine_core.cache_clear()
            self.assertNotEqual(amiga_knowledge.engine(), base)
        amiga_knowledge.engine_core.cache_clear()
        with patch('retrorecomp.amiga_vamiga.VAMIGA_REV', '5' * 40):
            amiga_knowledge.engine_core.cache_clear()
            self.assertNotEqual(amiga_knowledge.engine(), base)
        amiga_knowledge.engine_core.cache_clear()
        real = amiga_knowledge.text_digest
        with patch.object(amiga_knowledge, 'text_digest', side_effect=lambda name, root=None: 'f' * 64 if name.endswith('moira_map.cpp') else real(name, root)):
            amiga_knowledge.engine_core.cache_clear()
            self.assertNotEqual(amiga_knowledge.engine(), base)
        amiga_knowledge.engine_core.cache_clear()
        self.assertEqual(amiga_knowledge.engine(), base)
        for name in amiga_knowledge.NATIVE_INPUTS + amiga_knowledge.GENERATOR_SOURCES:
            self.assertTrue((Path(__file__).resolve().parents[1] / name).is_file(), name)

    # The Python that generates the code a RAM path becomes. Editing one of these files without raising amiga_knowledge.GENERATOR_REVISION
    # would let a path validated by the old code count as qualified for the new one, so this test fails until both are done: raise the
    # revision, then update the digests of tests/amiga_generator_pins.json.
    def test_the_generator_sources_are_pinned_to_their_revision(self):
        root = Path(__file__).resolve().parents[1]
        found = {name: amiga_knowledge.text_digest(name, root) for name in amiga_knowledge.GENERATOR_SOURCES}
        pins = json.loads(Path(__file__).with_name('amiga_generator_pins.json').read_text(encoding='utf-8'))
        self.assertEqual(pins['revision'], amiga_knowledge.GENERATOR_REVISION, 'GENERATOR_REVISION changed: update tests/amiga_generator_pins.json')
        self.assertEqual(pins['sources'], found,
                         'An Amiga generator source changed: raise amiga_knowledge.GENERATOR_REVISION (the Amiga paths qualified by the old code '
                         'must be validated again), then update tests/amiga_generator_pins.json')


class SharingTests(unittest.TestCase):
    def test_the_amiga_is_the_experimental_tier_of_the_base_and_one_line_withdraws_it(self):
        self.assertIn('amiga', pp.EXPERIMENTAL_SHARED)
        self.assertIn('amiga', pp.SCHEMA3_ONLY)
        self.assertIs(knowledge.schema3_module('amiga'), amiga_knowledge)
        with patch.object(pp, 'SHARED_SYSTEMS', tuple(system for system in pp.SHARED_SYSTEMS if system != 'amiga')):
            self.assertIsNone(knowledge.schema3_module('amiga'))


if __name__ == '__main__':
    unittest.main()
