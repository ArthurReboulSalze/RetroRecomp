"""The Game Boy Color's shared paths on authored numbers: no game, no ROM byte, no engine."""
import hashlib
import json
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import gameboy, gbc_knowledge as gk, knowledge, knowledge_exchange, path_profiles as pp
from retrorecomp.systems import get_profile

ROM = random.Random(7).randbytes(0x20000)                              # eight banks
IDENTITY = hashlib.sha256(ROM).hexdigest()
OTHER = hashlib.sha256(random.Random(8).randbytes(0x20000)).hexdigest()
ENTRIES = [(0, 0x150), (1, 0x4000), (3, 0x7ffe), (7, 0x5123)]          # the usual windows: offsets alone say the address
ODD = [*ENTRIES, (0, 0x4150)]                                          # bank 0 seen in the switched window: rows keep the address


def record(entries=ENTRIES, identity=IDENTITY, core=None):
    return gk.make_record(identity, len(ROM), entries, core=core)


def shape_of(value) -> str:
    return value['cpus']['sm83']['paths']['entries'][0]['shape']


class RecordTests(unittest.TestCase):
    def test_a_record_passes_the_schema_3_validator_with_an_empty_layout(self):
        value = record()
        pp.validate_game(value)
        self.assertEqual(gk.validate_record(value, IDENTITY), value)
        self.assertEqual(value['identity'], {'system': 'gbc', 'sources': {'rom': {'bytes': len(ROM), 'sha256': IDENTITY}}, 'layout': {}})
        self.assertEqual((shape_of(value), gk.rows(value)), ('gb_offsets', sorted(ENTRIES)))
        self.assertEqual((shape_of(record(ODD)), gk.rows(record(ODD))), ('gb_rows', sorted(ODD)))
        self.assertEqual(record(list(reversed(ENTRIES))), value)
        self.assertEqual(record([])['cpus']['sm83']['paths'], {})
        self.assertEqual(gk.validate_record(record([]), IDENTITY), record([]))

    def test_what_is_refused(self):
        for bad in ([(8, 0x4000)], [(1, 0x8000)], [(-1, 0x100)]):
            with self.assertRaises(ValueError):
                record(bad)
        with self.assertRaises(ValueError):
            gk.validate_record(record(), OTHER)
        value = record()
        value['identity']['layout'] = {'format': 1}
        with self.assertRaises(ValueError):
            gk.validate_record(value)
        self.assertIsNone(gk.salvaged_record(OTHER, record()))
        self.assertEqual(gk.entry_set({'cpus': {}}), set())

    def test_the_names_the_ceiling_and_the_rules_the_site_reads(self):
        self.assertEqual({name for name, _ in gk.entry_set(record())}, set(gk.PATH_CAPS))
        profile = pp.PROFILES[('sm83', 'gbc')]
        self.assertEqual(gk.PATH_CAPS['gbc_entry'], min(profile.caps['gb_offsets'], profile.caps['gb_rows']))
        self.assertEqual(gk.RECORD_RULES['layout'], [])
        self.assertEqual(gk.RECORD_RULES['sources'], {'only': ['rom'], 'required': ['rom'], 'hashed': True, 'game': 'rom'})
        self.assertEqual(gk.RECORD_RULES['paths'], {'sm83': {'entries': {'src': 'rom'}}})

    def test_rebuild_and_merge_keep_the_paths_and_never_mix_engines_or_cartridges(self):
        value = record()
        self.assertEqual(gk.rebuild(value, gk.entry_set(value)), value)
        self.assertEqual(gk.rows(gk.rebuild(value, set())), [])
        self.assertEqual(gk.rows(gk.merged(IDENTITY, record(ENTRIES[:2]), record(ENTRIES[2:]))), sorted(ENTRIES))
        old = record(ENTRIES[:1], core='a' * 40)
        self.assertEqual(gk.merged(IDENTITY, old, value), value)
        self.assertEqual(gk.merged(IDENTITY, value, old), value)
        self.assertFalse(gk.same_images(value, record(identity=OTHER)))
        self.assertNotEqual(gk.record_digest(value), gk.record_digest(record(ENTRIES[:3])))

    def test_the_engine_string_is_the_pin_and_the_path_revision(self):
        now = gk.engine()
        with mock.patch.object(gameboy, 'ENGINE_REV', '0' * 40):
            self.assertNotEqual(gk.engine(), now)
        with mock.patch.object(gk, 'PATH_REVISION', gk.PATH_REVISION + 1):
            self.assertNotEqual(gk.engine(), now)


class SharingTests(unittest.TestCase):
    def test_the_machine_is_in_the_experimental_tier_and_withdrawn_with_it(self):
        for names in (pp.EXPERIMENTAL_SHARED, pp.SCHEMA3_ONLY, pp.WITHDRAWABLE):
            self.assertIn('gbc', names)
        self.assertIs(knowledge.schema3_module('gbc'), gk)
        self.assertIsNone(knowledge.schema3_module('gb'))          # the Game Boy's records keep their first format
        declared = get_profile('gbc').shared_knowledge
        self.assertEqual((declared.tier, declared.withdrawable, declared.quick_check_from_shared, declared.module),
                         ('experimental', True, False, 'gbc_knowledge'))

    def test_the_exchange_reads_the_record_as_a_version_3_file_and_a_side_bank_holds_it(self):
        value = record()
        knowledge_exchange.validate_mixed_payload({'schema': 1, 'consoles': {'gbc': {IDENTITY: value}}})
        with self.assertRaises(ValueError):
            knowledge_exchange.validate_mixed_payload({'schema': 1, 'consoles': {'gbc': {OTHER: value}}})
        self.assertEqual(knowledge_exchange.unknown_hints('gbc', value), len(ENTRIES))
        self.assertEqual(knowledge_exchange.record_engine('gbc', value), gk.engine())
        self.assertEqual(knowledge_exchange._current_engines()['gbc'], gk.engine())
        with tempfile.TemporaryDirectory() as folder:
            bank = Path(folder) / 'imported-v3.json.gz'
            knowledge.write_side_bank(bank, {'gbc:' + IDENTITY: value})
            self.assertEqual(knowledge.read_side_bank(bank), {'gbc:' + IDENTITY: value})

    def test_a_qualified_record_counts_for_its_engine_only_and_an_imported_one_always_guides(self):
        qualified, imported = record(ENTRIES[:2]), record(ENTRIES[2:], core='b' * 40)
        with mock.patch.object(knowledge, 'qualified_game', lambda system, identity: qualified), \
                mock.patch.object(knowledge, 'imported_game', lambda system, identity: imported):
            self.assertEqual(gk.shared_entries(IDENTITY, len(ROM)), set(ENTRIES))
            self.assertEqual(gk.shared_entries(IDENTITY, len(ROM), imported=False), set(ENTRIES[:2]))
            self.assertEqual(gk.shared_entries(IDENTITY, len(ROM) * 2), set())          # a record of another image
            self.assertEqual(gk.shared_entries(OTHER, len(ROM)), set())
        with mock.patch.object(knowledge, 'qualified_game', lambda system, identity: record(core='c' * 40)), \
                mock.patch.object(knowledge, 'imported_game', lambda system, identity: {}):
            self.assertEqual(gk.shared_entries(IDENTITY, len(ROM)), set())

    def test_the_converter_reads_the_banks_for_the_color_only(self):
        with mock.patch.object(gk, 'shared_entries', lambda identity, size, imported=True: {(1, 0x4000)}):
            color = gameboy.GameBoyRom(Path('a.gbc'), ROM, 0, IDENTITY, 'A', 0xC0, 'gbc')
            monochrome = gameboy.GameBoyRom(Path('a.gb'), ROM, 0, IDENTITY, 'A', 0, 'gb')
            self.assertEqual(gameboy._bank_entries(color), {(1, 0x4000)})
            self.assertEqual(gameboy._bank_entries(monochrome), set())

    def test_the_library_record_is_what_a_conversion_wrote_and_the_report_names_it(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            with mock.patch('retrorecomp.library.library_root', lambda system: folder):
                self.assertIsNone(gk.library_record(IDENTITY))
                written, truncated = gk.remember(IDENTITY, len(ROM), [*ENTRIES, (99, 0x4000)])
                self.assertEqual((gk.rows(written), truncated), (sorted(ENTRIES), False))
                self.assertEqual(gk.library_record(IDENTITY), written)
                summary = folder / IDENTITY / 'compilation.json'
                data = json.loads(summary.read_text(encoding='utf-8'))
                summary.write_text(json.dumps({**data, 'fresh_reference_passed': False}), encoding='utf-8')
                self.assertIsNone(gk.library_record(IDENTITY))
        block = gk.knowledge_block(written, truncated, 3)
        self.assertEqual((block['record_sha256'], block['paths'], block['received_entries'], block['shared'], block['raw_bytes_stored']),
                         (gk.record_digest(written), {'entries': len(ENTRIES)}, 3, True, False))


if __name__ == '__main__':
    unittest.main()
