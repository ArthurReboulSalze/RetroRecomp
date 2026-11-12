"""The record builder and the verdict of tools/gba_bogus_rows_audit.py: no cartridge of a game, no conversion, no engine."""
import hashlib
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from retrorecomp import gba_knowledge as gk, knowledge, path_profiles as pp
from tools import gba_bogus_rows_audit as audit

ROM = random.Random(3).randbytes(0x20000)


class BuilderTests(unittest.TestCase):
    def test_the_rows_are_invented_from_the_seed_and_valid_in_the_schema_and_the_modules_rules(self):
        roots, spans = audit.bogus_rows(len(ROM), 7, 2000)
        self.assertEqual((len(roots), len(spans)), (2000, 2000))
        self.assertEqual(audit.bogus_rows(len(ROM), 7, 2000), (roots, spans))
        self.assertNotEqual(audit.bogus_rows(len(ROM), 8, 2000), (roots, spans))
        self.assertTrue(all(gk.root_valid(root, len(ROM)) for root in roots))
        self.assertTrue(all(root & 1 or not root % 4 for root in roots))
        self.assertTrue(any(root & 1 for root in roots) and any(not root & 1 for root in roots))        # both modes
        self.assertTrue(all(gk.span_valid(row, len(ROM)) for row in spans))
        windows = [(0x02000000, 0x02040000), (0x03000000, 0x03008000)]
        self.assertTrue(all(any(low <= row[0] < high for low, high in windows) for row in spans))
        self.assertEqual({row[0] >> 24 for row in spans}, {2, 3})                                         # both work RAMs

    def test_the_count_is_bounded_by_the_schema_and_by_the_cartridge(self):
        roots, spans = audit.bogus_rows(len(ROM), 1, 5000)
        self.assertEqual((len(roots), len(spans)), (5000, gk.SPAN_LIMIT))
        roots, spans = audit.bogus_rows(0x200, 1, 2000)                                                    # a cartridge too small for so many distinct roots
        self.assertLessEqual(len(roots), 0x200)
        self.assertTrue(all(gk.root_valid(root, 0x200) for root in roots))

    def test_the_record_is_the_one_a_hostile_sender_would_upload_and_holds_no_byte_of_the_cartridge(self):
        record = audit.bogus_record(ROM, 7, 2000)
        identity = hashlib.sha256(ROM).hexdigest()
        self.assertEqual(gk.validate_record(record, identity), record)
        self.assertEqual(gk.record_engine(record), gk.engine())
        self.assertEqual((len(gk.rows(record)[0]), len(gk.rows(record)[1])), (2000, 2000))
        self.assertEqual(pp.validate_game(record), record)

    def test_installed_in_a_scratch_data_folder_it_is_received_like_any_imported_record(self):
        record = audit.bogus_record(ROM, 7, 2000)
        identity = hashlib.sha256(ROM).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            datas = Path(folder) / 'datas'
            environment = {name: value for name, value in os.environ.items()
                           if name not in ('RETRO_RECOMP_LIBRARY_DIR', 'SMSRECOMP_LIBRARY_DIR', 'RETRO_RECOMP_BUNDLED_KNOWLEDGE')}
            knowledge._side_games.cache_clear()
            self.addCleanup(knowledge._side_games.cache_clear)
            written = audit.install(record, datas)
            self.assertEqual(written, datas / 'knowledge' / 'imported-v3.json.gz')
            with mock.patch.dict(os.environ, environment, clear=True), mock.patch('retrorecomp.paths.data_directory', return_value=datas):
                received = knowledge.imported_game('gba', identity)
                self.assertEqual(received, record)
                used, info = gk.shared_rows(identity, len(ROM), imported=received)
            self.assertEqual((len(used.roots), len(used.spans), info['pending'], info['qualified_by_the_base']), (2000, 2000, 4000, 0))

    def test_a_source_is_a_cartridge_or_a_converted_games_project_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            (folder / 'rom.gba').write_bytes(b'x')
            cartridge = folder / 'Game.gba'
            cartridge.write_bytes(b'y')
            self.assertEqual(audit.resolve_source(folder), folder / 'rom.gba')
            self.assertEqual(audit.resolve_source(cartridge), cartridge)
            with self.assertRaises(SystemExit):
                audit.resolve_source(folder / 'missing.gba')


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.bogus = ([0x100, 0x201], [(0x03000100, 0x400, 0x40)])
        self.report = {'native_validation': {'passed': True, 'scenarios': [{'scenario': 'boot', 'match': True}, {'scenario': 'generic', 'match': True}]},
                       'final_checks': [{'scenario': 'boot', 'interpreted_opcodes': 0}, {'scenario': 'generic', 'interpreted_opcodes': 32}],
                       'native_coverage': {'generated': {'functions': 120}, 'unresolved_misses': 1, 'shared_paths': {'used_roots': 2, 'qualified_by_this_converter': 0}}}
        self.clean = {'native_validation': {'passed': True}, 'final_checks': [{'scenario': 'boot', 'interpreted_opcodes': 0}, {'scenario': 'generic', 'interpreted_opcodes': 32}],
                      'native_coverage': {'generated': {'functions': 100}}}
        self.records = {'players_paths': {'roots': {0x300}, 'spans': set()}, 'promoted': {'roots': {0x300}, 'spans': set()}}

    def test_a_conversion_that_passed_and_kept_the_rows_out_of_its_paths_is_ok(self):
        text = 'function gf_func_08000100 and an address 0x08000200'
        summary = audit.summarize(self.report, '', self.bogus, self.records, self.clean, generator_log=text, generated_text=text + ' 08000100')
        self.assertTrue(summary['ok'] and summary['passed'])
        self.assertEqual(summary['interpreted_instructions'], {'boot': 0, 'generic': 32})
        self.assertEqual((summary['functions'], summary['extra_functions_over_the_clean_conversion']), (120, 20))
        self.assertEqual((summary['bogus_roots_named_in_generator_log'], summary['bogus_rows_in_players_paths'], summary['bogus_rows_in_promoted_record']), (2, 0, 0))
        self.assertEqual(summary['invented'], {'roots': 2, 'ram_copies': 1})
        self.assertEqual(summary['clean']['functions'], 100)

    def test_a_conversion_that_raised_is_reported_with_its_message_and_is_not_ok(self):
        summary = audit.summarize(None, 'the check against the engine\'s interpreter failed', self.bogus, self.records)
        self.assertFalse(summary['ok'] or summary['passed'])
        self.assertIn('interpreter', summary['error'])

    def test_a_scenario_that_differs_is_not_a_pass(self):
        self.report['native_validation']['passed'] = False
        self.assertFalse(audit.summarize(self.report, '', self.bogus, self.records)['ok'])
        self.report['native_validation']['passed'] = None
        self.assertFalse(audit.summarize(self.report, '', self.bogus, self.records)['ok'])

    def test_an_invented_row_that_reached_the_players_paths_or_the_shared_record_fails_the_audit(self):
        for where in ('players_paths', 'promoted'):
            records = {**self.records, where: {'roots': {0x201}, 'spans': {(0x03000100, 0x400, 0x40)}}}
            summary = audit.summarize(self.report, '', self.bogus, records)
            self.assertTrue(summary['passed'])
            self.assertFalse(summary['ok'], where)
            self.assertEqual(summary['bogus_rows_in_players_paths' if where == 'players_paths' else 'bogus_rows_in_promoted_record'], 2)


if __name__ == '__main__':
    unittest.main()
