"""The seven writers write schema 2 beside their own keys, and the callers read it through one module (stage C2).

No ROM and no conversion: the reports are the synthetic ones of tests/test_report_schema.py, one per writer
shape, checked against the writers' own code (the keys their report literals carry are read from the source),
and the three writers that tests already run with mocks (console16, Game Boy) are checked where those tests
read the report they wrote.
"""
import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import retrorecomp
from retrorecomp import compiled_games, freshness, knowledge_build, online, report_schema
from retrorecomp.report_schema import (KNOWLEDGE_KEYS, MEASURES, OPTIONAL_ON_DISK, REQUIRED_KEYS, V2_ONLY_KEYS,
                                       ReportShapeError, fallback_summary, legacy_view, read_report,
                                       with_schema_v2, write_report)
from tests.test_report_schema import (FIXTURES, SHA, console16_report, decided, gb_report, legacy_summary,
                                      neogeo_report, nes_report, published, sms_report, x68_report)

PACKAGE = Path(retrorecomp.__file__).parent
WRITERS = {'core.py': 'sms and gg', 'gameboy.py': 'gb', 'nes.py': 'nes', 'console16.py': 'md and snes',
           'neogeo_conversion.py': 'ng', 'cps1_conversion.py': 'cps1', 'x68000_conversion.py': 'x68'}
# What batch.py adds to a report after the conversion (published() in test_report_schema reproduces it).
BATCH_KEYS = {'ui_languages', 'language_switch_key', 'language_scope', 'upgrade', 'shared_paths', 'bundled_paths',
              'published_directory', 'source_rom', 'packing', 'export_receipt', 'timings'}
# Written by the converter itself, in the parts of the code the report literal does not show.
NEOGEO_LATE = {'conversion_phases_seconds', 'validation_workers', 'runtime_modes', 'scan_level',
               'qualification_scope', 'qualification_extra_routes'}


def report_keys(module):
    """The top-level keys the report dict of a writer module can carry: its literal(s), the keys a spread adds
    and the subscripts assigned afterwards, read from the source without running anything."""
    tree = ast.parse((PACKAGE / module).read_text(encoding='utf-8'))
    keys = set()

    def strings(node):
        return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'report' for t in node.targets):
            if isinstance(node.value, ast.Dict):
                for key, value in zip(node.value.keys, node.value.values):
                    if key is None:       # **({'cartridge_device': device} if ... else {})
                        keys |= {k.value for d in ast.walk(value) if isinstance(d, ast.Dict) for k in d.keys
                                 if isinstance(k, ast.Constant)}
                    elif isinstance(key, ast.Constant):
                        keys.add(key.value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                        and target.value.id == 'report' and isinstance(target.slice, ast.Constant)):
                    keys.add(target.slice.value)
    return keys


class Writers(unittest.TestCase):
    def test_each_of_the_seven_writers_goes_through_the_shared_builder(self):
        for module in WRITERS:
            with self.subTest(module=module):
                source = (PACKAGE / module).read_text(encoding='utf-8')
                self.assertIn('from .report_schema import write_report', source)
                named = [line for line in source.splitlines() if 'conversion-report.json' in line]
                self.assertEqual(sum('write_report(' in line for line in named), 1, 'one write, through the builder')
                for line in named:
                    self.assertFalse('atomic_json' in line or 'write_text(' in line, line)

    def test_every_writer_carries_scan_level_at_the_top(self):
        # Mega Drive, Super Nintendo and NES kept it under advanced_scan only (the cause of the 1.5.6 hotfix).
        for module in WRITERS:
            with self.subTest(module=module):
                self.assertIn('scan_level', report_keys(module))

    def test_the_fixtures_do_not_invent_keys_the_writers_never_write(self):
        by_fixture = {'sms': 'core.py', 'gg': 'core.py', 'gb': 'gameboy.py', 'nes': 'nes.py', 'md': 'console16.py',
                      'snes': 'console16.py', 'ng': 'neogeo_conversion.py', 'cps1': 'cps1_conversion.py',
                      'x68': 'x68000_conversion.py'}
        for label, make in FIXTURES.items():
            report = make()
            module = by_fixture[report['system']['id']]
            with self.subTest(fixture=label):
                unknown = set(report) - report_keys(module) - BATCH_KEYS
                self.assertEqual(unknown, set())

    def test_no_key_of_a_writer_collides_with_a_schema_2_section(self):
        for module in WRITERS:
            with self.subTest(module=module):
                self.assertEqual(report_keys(module) & set(V2_ONLY_KEYS), set())
        self.assertEqual(BATCH_KEYS & set(V2_ONLY_KEYS), set())
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                self.assertEqual(set(published(make())) & set(V2_ONLY_KEYS), set())

    def test_the_x68000_report_has_a_wall_time_and_no_constant_vdp_claim(self):
        source = (PACKAGE / 'x68000_conversion.py').read_text(encoding='utf-8')
        self.assertIn("'reference_vdp_trace_match':None", source)
        self.assertNotIn("'reference_vdp_trace_match':True", source)
        self.assertIn('conversion_wall_seconds', report_keys('x68000_conversion.py'))


class DualWrite(unittest.TestCase):
    def test_every_old_key_stays_with_its_value(self):
        for label, make in FIXTURES.items():
            for form, build in (('as written', make), ('as published', lambda: published(make()))):
                with self.subTest(fixture=label, form=form):
                    old = build()
                    before = copy.deepcopy(old)
                    new = with_schema_v2(old)
                    self.assertEqual(old, before, 'the writer\'s dict is not modified')
                    for key, value in old.items():
                        self.assertIn(key, new)
                        if key == 'system':
                            self.assertEqual({k: v for k, v in new[key].items() if k != 'status'}, value)
                        elif key == 'rom':
                            self.assertEqual({k: v for k, v in new[key].items() if k != 'source_identity'}, value)
                        elif key == 'knowledge':
                            self.assertEqual({k: v for k, v in new[key].items() if k not in KNOWLEDGE_KEYS}, value)
                        else:
                            self.assertEqual(new[key], value)
                    self.assertEqual(legacy_view(new), old, 'the old shape can be had back exactly')
                    self.assertEqual(json.loads(json.dumps(new)), new)

    def test_schema_comes_first_and_every_section_is_there(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                new = with_schema_v2(make())
                self.assertEqual(next(iter(new)), 'schema')
                self.assertEqual(new['schema'], {'name': 'retro-recomp-report', 'version': 2})
                self.assertEqual(new['read_from']['schema_version'], 2)
                self.assertIs(new['read_from']['legacy_keys'], True)
                for key in REQUIRED_KEYS:
                    if key not in OPTIONAL_ON_DISK:
                        self.assertIn(key, new)
                self.assertEqual(tuple(new['validation']), MEASURES)

    def test_a_key_the_old_shape_left_out_is_not_written_as_null(self):
        # Old readers take a missing key for "absent" and a null for a value: report.get('upgrade', {}).get(...),
        # report.get('target', current), report.get('created_utc', '') >= ...
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                old = make()
                new = with_schema_v2(old)
                for key in OPTIONAL_ON_DISK:
                    self.assertEqual(key in new, key in old, key)
                for key in ('upgrade', 'export_receipt'):
                    self.assertNotIn(key, new)
                self.assertIsNone(read_report(new)[key])

    def test_the_document_read_equals_the_old_shape_read_plus_the_new_fields(self):
        for label, make in FIXTURES.items():
            for form, build in (('as written', make), ('as published', lambda: published(make()))):
                with self.subTest(fixture=label, form=form):
                    old = build()
                    from_old, from_new = read_report(old), read_report(with_schema_v2(old))
                    self.assertEqual(tuple(from_new), REQUIRED_KEYS)
                    self.assertEqual(from_old['read_from']['schema_version'], 1)
                    self.assertEqual(from_new['read_from'],
                                     {'schema_version': 2, 'writer': from_old['read_from']['writer'],
                                      'legacy_keys': True})
                    for key in REQUIRED_KEYS:
                        if key != 'read_from':
                            self.assertEqual(from_new[key], from_old[key], key)

    def test_the_new_fields_are_what_the_writers_now_carry(self):
        # scan_level at the top for every shape; the section agrees with where each writer used to keep it.
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                old = make()
                self.assertIn('scan_level', old)
                self.assertEqual(read_report(old)['scan']['level'], old['scan_level'])
                if 'advanced_scan' in old:
                    self.assertEqual(old['advanced_scan']['level'], old['scan_level'])

    def test_writing_again_after_the_batch_derives_the_sections_anew(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                first = with_schema_v2(make())
                self.assertIsNone(read_report(first)['packed'] and read_report(first)['packed']['packer'])
                self.assertEqual(with_schema_v2(first), first, 'applying the builder twice changes nothing')
                # batch.py adds its fields to the dict the converter wrote, then writes again.
                after_batch = with_schema_v2(published(first, upgrade={'check_level': 'quick', 'discovery': {
                    'version': '1.5.5', 'scan_level': 'extended', 'final_checks': []}}))
                self.assertEqual(after_batch, with_schema_v2(published(make(), upgrade={
                    'check_level': 'quick', 'discovery': {'version': '1.5.5', 'scan_level': 'extended',
                                                          'final_checks': []}})))
                read = read_report(after_batch)
                self.assertEqual(read['upgrade']['check_level'], 'quick')
                self.assertEqual(read['build']['published_directory'], 'C:/out')
                self.assertEqual(read['build']['source_rom'], 'C:/roms/g.rom')
                self.assertEqual(read['packed']['packer'], 'UPX')
                self.assertEqual(read['rom']['sha256'], SHA)
                receipt = copy.deepcopy(after_batch)
                receipt['export_receipt'] = {'schema': 3, 'sha256': '3' * 64}
                self.assertEqual(read_report(with_schema_v2(receipt))['export_receipt'], receipt['export_receipt'])

    def test_neo_geo_keeps_its_own_knowledge_record_beside_the_schema_2_keys(self):
        old = neogeo_report()
        new = with_schema_v2(old)
        self.assertEqual(new['knowledge']['use'], {'imported': 0})
        self.assertEqual(new['knowledge']['observations'], 3)
        self.assertEqual(new['knowledge']['record'], old['knowledge'])
        self.assertEqual(set(read_report(new)['knowledge']), set(KNOWLEDGE_KEYS))
        self.assertEqual(with_schema_v2(new)['knowledge'], new['knowledge'])
        self.assertEqual(new['knowledge']['record'].get('record'), None)

    def test_x68000_keeps_source_identity_at_the_top_and_in_the_rom(self):
        new = with_schema_v2(x68_report())
        self.assertEqual(new['source_identity'], 'b' * 64)
        self.assertEqual(new['rom']['source_identity'], 'b' * 64)
        self.assertEqual(legacy_view(new)['rom'], x68_report()['rom'])

    def test_a_report_of_no_known_shape_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'conversion-report.json'
            for bad in ({'tool': 'Retro-Recomp', 'system': {'id': 'n64'}, 'final_checks': []},
                        {**sms_report(), 'final_checks': 5}):
                with self.subTest(report=bad.get('system')):
                    with self.assertRaises(ReportShapeError):
                        write_report(path, bad)
                    self.assertFalse(path.exists())

    def test_write_report_fills_the_target_and_the_time_and_replaces_the_file_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'conversion-report.json'
            path.write_text('previous', encoding='utf-8')
            gb = gb_report()
            self.assertNotIn('created_utc', gb)
            self.assertNotIn('target', gb)
            with patch('retrorecomp.platforms.target_id', return_value='windows-x86_64'):
                document = write_report(path, gb)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8')), document)
            self.assertEqual(document['target'], 'windows-x86_64')
            self.assertRegex(document['created_utc'], r'^\d{4}-\d\d-\d\dT')
            self.assertEqual(list(document)[:4], ['schema', 'read_from', 'tool', 'version'])
            self.assertEqual(list(document)[4:6], ['created_utc', 'target'])
            self.assertEqual(read_report(path)['created_utc'], document['created_utc'])
            self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ['conversion-report.json'])
            # A writer that carries them keeps its own values.
            sms = sms_report()
            with patch('retrorecomp.platforms.target_id', return_value='linux-x86_64'):
                kept = write_report(path, sms)
            self.assertEqual((kept['target'], kept['created_utc']), (sms['target'], sms['created_utc']))


class OldReadersOnNewReports(unittest.TestCase):
    """The readers written for the old shapes answer the same on an old report and on the same report written now."""

    def pair(self, make, **published_args):
        old = published(make(), **published_args)
        return old, with_schema_v2(old)

    def test_the_summary_is_the_same_whether_the_report_is_old_or_new(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                old, new = self.pair(make)
                from_old, from_new = fallback_summary(old), fallback_summary(new)
                self.assertEqual(from_old, from_new)
                # ...and the replica of the expressions the callers had answers the same on the new document,
                # because it still holds every old key.
                got = dict(from_new, video_standard=from_new['video_standard'] or 'HINT')
                self.assertEqual(decided(legacy_summary(new), new), got)

    def test_the_lenient_summary_reads_what_the_callers_always_read_and_the_strict_one_refuses_it(self):
        # tools/gui_smoke.py and several tests hold a report of this size: no tool, no console, no marker.
        small = {'executable': 'G.exe', 'rom': {'sha256': SHA}, 'final_checks': [], 'status': 'converted'}
        self.assertEqual(fallback_summary(small, lenient=True),
                         {'conversion_stage': 'converted', 'main_interpreted_opcodes': 0, 'device': None,
                          'audio_cpu': None, 'audio_interpreted_opcodes': 0, 'video_standard': None,
                          'interpreter_percent': None, 'interpreter_cycles': 0, 'reference_vdp_trace_match': None})
        with self.assertRaises(ReportShapeError):
            fallback_summary(small)
        rows = {'final_checks': [{'interpreter_percent': 0}, {'interpreter_percent': 2.5, 'interpreter_cycles': 7,
                                                              'audio_interpreted_opcodes': 3,
                                                              'interpreted_opcodes': 9}],
                'reference_vdp_trace_match': True, 'video_model': {'standard': 'pal'}, 'audio_cpu': 'Z80'}
        self.assertEqual(fallback_summary(rows, lenient=True),
                         decided(legacy_summary(rows), {'system': {'id': None}, **rows}))
        for broken in ({}, {'final_checks': 3}, {'final_checks': [1]}, []):
            with self.subTest(broken=broken), self.assertRaises(ReportShapeError):
                fallback_summary(broken, lenient=True)

    def test_a_game_listed_from_a_report_is_the_same_old_or_new(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                old, new = self.pair(make)
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / 'conversion-report.json'
                    games = []
                    for report in (old, new):
                        path.write_text(json.dumps(report), encoding='utf-8')
                        games.append(compiled_games.game_from_report(path, Path(folder)))
                self.assertEqual(games[0], games[1])
                self.assertEqual(compiled_games.report_level(old), compiled_games.report_level(new))

    def test_the_scan_level_is_read_from_every_place_a_report_keeps_it(self):
        level = compiled_games.report_level
        # Reports of 1.5.x held it under advanced_scan only: not read any more (releases before 1.6.0).
        self.assertEqual(level({'advanced_scan': {'level': 'thorough'}}), 'standard')
        self.assertEqual(level({'scan_level': 'thorough'}), 'thorough')
        # Schema 2 holds it in scan.level (this is what a report with no old key at all would carry).
        self.assertEqual(level({'scan': {'level': 'extended'}}), 'extended')
        self.assertEqual(level({'scan': {'level': None}, 'scan_level': 'quick'}), 'standard')
        self.assertEqual(level({'scan_level': 'quick', 'scan': {'level': 'extended'},
                                'upgrade': {'discovery': {'scan_level': 'thorough'}}}), 'thorough')
        self.assertEqual(level({'scan': 'broken', 'advanced_scan': 'broken'}), 'standard')
        # The report as written and its schema-2 form are read the same.
        for label in ('nes with fallback', 'md with fallback', 'snes superfx device'):
            with self.subTest(fixture=label):
                new = FIXTURES[label]()
                self.assertEqual(level(with_schema_v2(new)), level(new))
                self.assertEqual(level(read_report(new)), level(new))

    def test_freshness_reads_the_same_old_or_new(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                old, new = self.pair(make)
                self.assertEqual(freshness.feedback(old), freshness.feedback(new))
                record_old, record_new = freshness.upgrade_record(old), freshness.upgrade_record(new)
                # The inherited discovery says the level the writer now stores at the top: before, Mega Drive,
                # Super Nintendo and NES reports had no top-level key and an upgrade recorded 'standard'.
                self.assertEqual({k: v for k, v in record_old['discovery'].items() if k != 'scan_level'},
                                 {k: v for k, v in record_new['discovery'].items() if k != 'scan_level'})
                self.assertEqual(record_new['discovery']['scan_level'], old['scan_level'])
                self.assertEqual(record_old['reason'], record_new['reason'])

    def test_a_current_export_is_still_current_when_its_report_is_in_schema_2(self):
        for label in ('sms zero fallback', 'nes zero fallback', 'snes superfx device', 'ng completed',
                      'x68 zero fallback'):
            with self.subTest(fixture=label), tempfile.TemporaryDirectory() as folder:
                folder = Path(folder)
                target = folder / FIXTURES[label]()['executable']
                target.write_bytes(b'MZ game')
                item = type('Item', (), {'sha256': SHA, 'system': FIXTURES[label]()['system']['id']})()
                results = []
                for write in (lambda r: r, with_schema_v2):
                    report = FIXTURES[label]()
                    report['runtime_feedback'] = {'identity': SHA, 'fingerprint': 'f' * 8}
                    report['export_receipt'] = {'schema': 3, 'request': 'sig', 'game': 'g', 'host': 'h',
                                                'sha256': freshness.digest(target)}
                    path = folder / 'conversion-report.json'
                    path.write_text(json.dumps(write(report)), encoding='utf-8')
                    with patch('retrorecomp.freshness.ingest', return_value={'fingerprint': 'f' * 8}):
                        results.append(freshness.current(item, target, path, 'sig', lambda text: None))
                self.assertIsNotNone(results[0])
                self.assertEqual([r['export_receipt'] for r in results], [results[0]['export_receipt']] * 2)

    def test_the_knowledge_builder_picks_the_same_reports(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            paths = []
            for index, label in enumerate(('sms zero fallback', 'gb zero fallback', 'snes no device',
                                           'ng completed', 'x68 zero fallback')):
                report = FIXTURES[label]()
                report['rom']['sha256'] = f'{index:064x}'
                for form, write in (('old', lambda r: r), ('new', with_schema_v2)):
                    path = folder / f'{label}-{form}.json'
                    path.write_text(json.dumps(write(report)), encoding='utf-8')
                    paths.append(path)
            picked = knowledge_build.qualified_reports(paths)
            old = knowledge_build.qualified_reports([p for p in paths if p.stem.endswith('old')])
            new = knowledge_build.qualified_reports([p for p in paths if p.stem.endswith('new')])
            self.assertEqual(len(picked), 5)
            self.assertEqual(set(old), set(new))
            for key in old:
                self.assertEqual(legacy_view(new[key]), old[key])

    def test_the_problem_report_keeps_every_old_field_and_carries_the_schema_2_sections(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                old, new = self.pair(make)
                fields_old, fields_new = online.report_fields(old), online.report_fields(new)
                for key, value in fields_old.items():
                    if key != 'system':
                        self.assertEqual(fields_new[key], value, key)
                self.assertEqual(fields_new['system']['id'], fields_old['system']['id'])
                for key in ('schema', 'scan_level', 'scan', 'cpus', 'devices', 'validation', 'honesty'):
                    self.assertIn(key, fields_new, key)
                self.assertNotIn('cpus', fields_old)
                self.assertEqual(fields_new['cpus'], read_report(new)['cpus'])
                self.assertLessEqual(len(json.dumps(fields_new)), online.REPORT_FIELDS_LIMIT)
        self.assertEqual(online.REPORT_BULKY[-3:], ('scan', 'cpus', 'validation'))

    def test_a_too_large_report_drops_the_old_bulk_before_the_schema_2_sections(self):
        report = with_schema_v2(console16_report('md'))
        report['history'] = ['x' * 5000] * 20
        report['final_checks'] = [dict(row, bulk='y' * 5000) for row in report['final_checks'] * 8]
        fields = online.report_fields(report)
        self.assertNotIn('history', fields)
        self.assertNotIn('final_checks', fields)
        self.assertIn('cpus', fields)
        self.assertIn('validation', fields)

    def test_schema_2_sections_hold_what_the_window_text_needs(self):
        # The window picks its text from the profile and the summary; the numbers come from the sections.
        report = read_report(with_schema_v2(console16_report('snes', main=40, audio=2, device=6_000_000)))
        summary = fallback_summary(report)
        self.assertEqual((summary['main_interpreted_opcodes'], summary['audio_interpreted_opcodes']), (40, 2))
        self.assertEqual(summary['device']['instructions'], 6_000_000)


class WritersThatTestsRun(unittest.TestCase):
    """report_schema.write_report is what the writers call: it needs the platform's target and a library module."""

    def test_the_builder_is_an_interface_module_and_imports_nothing_heavy_at_load(self):
        from retrorecomp.compilation_inputs import INTERFACE_MODULES
        self.assertIn('report_schema', INTERFACE_MODULES)
        source = (PACKAGE / 'report_schema.py').read_text(encoding='utf-8')
        top = [line for line in source.splitlines() if line.startswith(('import ', 'from '))]
        self.assertEqual(top, ['from __future__ import annotations', 'import copy', 'import json',
                               'from dataclasses import dataclass', 'from pathlib import Path'])


if __name__ == '__main__':
    unittest.main()
