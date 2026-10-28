"""The time of each phase of a conversion: the recorder, the report field, the readers and the batch log line.

No ROM, no conversion and no real clock: a fake clock that the fake converters advance.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from retrorecomp import compiled_games, report_schema, timings
from retrorecomp.batch import convert_batch, identify
from retrorecomp.library import atomic_json
from retrorecomp.report_schema import read_report, with_schema_v2
from tests.test_report_schema import FIXTURES, published, sms_report
from tools.release_check import check_report

EXT = '.exe' if os.name == 'nt' else ''


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def perf_counter(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class RecorderTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.recorder = timings.Recorder(self.clock.perf_counter)

    def test_a_phase_owns_its_time_and_the_rest_is_other(self):
        self.clock.advance(1.0)
        with self.recorder.phase('compile'):
            self.clock.advance(42.14)
        self.clock.advance(0.5)
        with self.recorder.phase('native_runs'):
            self.clock.advance(5.0)
        self.assertEqual(self.recorder.snapshot(),
                         {'compile': 42.1, 'native_runs': 5.0, 'other': 1.5, 'total': 48.6})

    def test_a_phase_inside_another_takes_its_time_from_it(self):
        with self.recorder.phase('publication'):
            self.clock.advance(2.0)
            with self.recorder.phase('packing'):
                self.clock.advance(30.0)
            self.clock.advance(1.0)
        figures = self.recorder.snapshot()
        self.assertEqual((figures['publication'], figures['packing'], figures['total']), (3.0, 30.0, 33.0))

    def test_the_same_phase_adds_up(self):
        for _ in range(3):
            with self.recorder.phase('native_runs'):
                self.clock.advance(2.0)
        self.assertEqual(self.recorder.snapshot()['native_runs'], 6.0)

    def test_learning_passes_after_the_first_are_discovery_whatever_they_do(self):
        self.recorder.begin_pass(1)
        with self.recorder.phase('compile'):
            self.clock.advance(10.0)
        self.assertEqual(self.recorder.snapshot()['discovery'], 0.0, 'there from the first pass, at zero')
        self.recorder.begin_pass(2)
        self.clock.advance(1.0)                 # outside any phase, inside the pass
        with self.recorder.phase('compile'):
            self.clock.advance(7.0)
        with self.recorder.phase('native_runs'):
            self.clock.advance(3.0)
        self.recorder.end_passes()
        self.clock.advance(0.5)
        with self.recorder.phase('reference_runs'):
            self.clock.advance(4.0)
        self.assertEqual(self.recorder.snapshot(),
                         {'compile': 10.0, 'discovery': 11.0, 'reference_runs': 4.0, 'other': 0.5, 'total': 25.5})

    def test_a_single_pass_leaves_discovery_at_zero(self):
        self.recorder.begin_pass(1)
        with self.recorder.phase('native_runs'):
            self.clock.advance(3.0)
        self.recorder.end_passes()
        self.assertEqual(self.recorder.snapshot()['discovery'], 0.0)

    def test_a_console_without_passes_has_no_discovery_figure(self):
        with self.recorder.phase('compile'):
            self.clock.advance(1.0)
        self.assertNotIn('discovery', self.recorder.snapshot())

    def test_a_failed_quick_attempt_becomes_one_phase(self):
        self.recorder.begin_pass(1)
        with self.recorder.phase('compile'):
            self.clock.advance(10.0)
        self.clock.advance(2.0)
        self.recorder.collapse(timings.FAILED_QUICK)
        with self.recorder.phase('compile'):
            self.clock.advance(5.0)
        figures = self.recorder.snapshot()
        self.assertEqual((figures['failed_quick_attempt'], figures['compile'], figures['total']), (12.0, 5.0, 17.0))
        self.assertNotIn('discovery', figures)

    def test_an_error_inside_a_phase_still_closes_it(self):
        with self.assertRaises(RuntimeError):
            with self.recorder.phase('compile'):
                self.clock.advance(4.0)
                raise RuntimeError('build failed')
        self.clock.advance(1.0)
        figures = self.recorder.snapshot()
        self.assertEqual((figures['compile'], figures['other']), (4.0, 1.0))

    def test_the_figures_are_json(self):
        with self.recorder.phase('compile'):
            self.clock.advance(1.234)
        self.assertEqual(json.loads(json.dumps(self.recorder.snapshot()))['compile'], 1.2)


class ModuleLevelTests(unittest.TestCase):
    def test_without_a_recorder_everything_does_nothing(self):
        self.assertIsNone(timings.current())
        with timings.phase('compile'):
            pass
        timings.begin_pass(2)
        timings.end_passes()
        timings.collapse('x')
        self.assertIsNone(timings.snapshot())

    def test_a_recorder_belongs_to_the_thread_that_started_it(self):
        from concurrent.futures import ThreadPoolExecutor
        clock = FakeClock()
        _, token = timings.start(clock.perf_counter)
        self.addCleanup(timings.stop, token)

        def helper():
            # Python 3.14 gives a pool worker a copy of the submitting context, so it may see the recorder.
            with timings.phase('native_runs'):
                clock.advance(100.0)
            timings.begin_pass(2)
            timings.collapse('x')
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(helper).result()
        worker = threading.Thread(target=helper)
        worker.start()
        worker.join()
        with timings.phase('compile'):
            clock.advance(2.0)
        figures = timings.snapshot()
        self.assertEqual(figures['compile'], 2.0)
        self.assertNotIn('native_runs', figures, 'a helper thread of a converter cannot disturb the figures')
        self.assertNotIn('x', figures)
        self.assertNotIn('discovery', figures)

    def test_instrument_names_a_function_from_outside_and_only_once(self):
        module = types.SimpleNamespace()
        calls = []

        def build(project, *, flag=False):
            calls.append((project, flag))
            return 'built'
        module.build = build
        clock = FakeClock()
        _, token = timings.start(clock.perf_counter)
        self.addCleanup(timings.stop, token)
        timings.instrument(module, 'build', 'compile')
        wrapper = module.build
        timings.instrument(module, 'build', 'compile')
        self.assertIs(module.build, wrapper)
        self.assertEqual(module.build('p', flag=True), 'built')
        self.assertEqual(calls, [('p', True)])
        self.assertEqual(wrapper.__name__, 'build')
        self.assertIn('compile', timings.snapshot())

    def test_describe_is_one_short_line(self):
        figures = {'compile': 42.14, 'native_runs': 0.01, 'discovery': 0.0, 'reference_runs': 18.3, 'other': 1.2,
                   'total': 62.5}
        self.assertEqual(timings.describe(figures),
                         'times: compile 42.1 s, discovery 0.0 s, reference runs 18.3 s, other 1.2 s, total 62.5 s')
        self.assertIsNone(timings.describe(None))
        self.assertIsNone(timings.describe({'compile': 1.0}))


class VocabularyTests(unittest.TestCase):
    PACKAGE = Path(timings.__file__).parent
    CONVERTERS = {'core.py': 'sms and gg', 'gameboy.py': 'gb', 'nes.py': 'nes', 'console16.py': 'md and snes',
                  'neogeo_conversion.py': 'ng', 'cps1_conversion.py': 'cps1', 'x68000_conversion.py': 'x68'}

    def used_names(self):
        import re
        names = {}
        for source in sorted(self.PACKAGE.glob('*.py')):
            text = source.read_text(encoding='utf-8')
            for name in re.findall(r"\.phase\('([a-z_]+)'", text) + re.findall(r"instrument\([^)]*'([a-z_]+)'\)", text):
                names.setdefault(name, set()).add(source.name)
        return names

    def test_every_phase_a_converter_marks_is_in_the_vocabulary(self):
        used = self.used_names()
        self.assertTrue(used)
        self.assertEqual({name for name in used if name not in timings.ORDER}, set(), used)

    def test_each_converter_marks_its_compile_and_its_runs(self):
        used = self.used_names()
        for module, console in self.CONVERTERS.items():
            with self.subTest(module=module, console=console):
                text = (self.PACKAGE / module).read_text(encoding='utf-8')
                self.assertTrue('timings' in text and ('timings.phase' in text or 'stages.phase' in text), module)
        # The compile step of Neo Geo is named from neogeo_conversion (neogeo_build is hashed into its state key).
        self.assertIn('neogeo_conversion.py', used['compile'])
        for phase in ('code_generation', 'compile', 'native_runs', 'reference_runs'):
            self.assertGreaterEqual(len(used[phase]), 4, phase)


class ReportFieldTests(unittest.TestCase):
    FIGURES = {'code_generation': 2.0, 'compile': 40.0, 'discovery': 0.0, 'other': 1.0, 'total': 43.0}

    def test_a_report_without_the_field_reads_none_in_every_shape(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                self.assertIsNone(read_report(make())['timings'])
                self.assertIsNone(read_report(with_schema_v2(make()))['timings'])
                self.assertNotIn('timings', with_schema_v2(make()), 'left out on disk, never written as null')

    def test_a_report_with_the_field_keeps_it_through_the_builder_and_the_reader(self):
        for label, make in FIXTURES.items():
            with self.subTest(fixture=label):
                old = published(make())
                old['timings'] = dict(self.FIGURES)
                document = with_schema_v2(old)
                self.assertEqual(document['timings'], self.FIGURES)
                self.assertEqual(read_report(document)['timings'], self.FIGURES)
                self.assertEqual(read_report(old)['timings'], self.FIGURES)
                self.assertEqual(report_schema.legacy_view(document), old)
                self.assertEqual(with_schema_v2(document), document)
                self.assertEqual(tuple(read_report(document)), report_schema.REQUIRED_KEYS)

    def test_a_value_that_is_not_a_set_of_figures_reads_none(self):
        for value in ('fast', 3.2, [], {}, {'compile': 'long', 'total': 'x'}, {'compile': 3.0},
                      {'compile': 3.0, 'total': True}):
            with self.subTest(value=value):
                report = sms_report()
                report['timings'] = value
                self.assertIsNone(read_report(report)['timings'])
                self.assertIsNone(read_report(with_schema_v2(report))['timings'])

    def test_entries_that_are_not_seconds_are_dropped_from_the_reading(self):
        report = sms_report()
        report['timings'] = {'compile': 3.0, 'note': 'x', 'flag': True, 'negative': -1.0, 'total': 4.0}
        self.assertEqual(read_report(report)['timings'], {'compile': 3.0, 'total': 4.0})

    def test_the_other_readers_do_not_care_whether_it_is_there(self):
        with tempfile.TemporaryDirectory() as folder:
            for label in ('sms zero fallback', 'sms with fallback'):
                bare = published(FIXTURES[label]())
                timed = copy.deepcopy(bare)
                timed['timings'] = dict(self.FIGURES)
                self.assertEqual(check_report(with_schema_v2(timed), 'sms', 'standard', 0),
                                 check_report(with_schema_v2(bare), 'sms', 'standard', 0))
                self.assertEqual(report_schema.fallback_summary(timed), report_schema.fallback_summary(bare))
                results = []
                for form, report in (('bare', bare), ('timed', timed)):
                    root = Path(folder) / label.replace(' ', '-') / form
                    path = root / 'datas/reports/game/conversion-report.json'
                    path.parent.mkdir(parents=True)
                    atomic_json(path, {**with_schema_v2(report), 'executable': 'Game' + EXT,
                                       'rom': {**report['rom'], 'sha256': 'a' * 64}})
                    results.append(compiled_games.game_from_report(path, root))
                bare_game, timed_game = results
                self.assertEqual((timed_game.status, timed_game.level, timed_game.tested_fallback),
                                 (bare_game.status, bare_game.level, bare_game.tested_fallback))


class BatchPipelineTests(unittest.TestCase):
    """A fake converter that does what the real ones do (mark its phases, advance the clock) behind the real batch."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.games_root = self.root / 'games'
        self.clock = FakeClock()
        patcher = patch('retrorecomp.timings.time', self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def item(self, value=1):
        folder = self.root / 'roms'
        folder.mkdir(exist_ok=True)
        path = folder / 'Timed game (Europe).sms'
        path.write_bytes(bytes([value]) * 8192)
        return identify(path)

    def converter(self, *, passes=1):
        clock = self.clock

        def convert(path, *, output, title, **options):
            from retrorecomp.report_schema import write_report
            timings.begin_pass(1)
            with timings.phase('code_generation'):
                clock.advance(2.0)
            with timings.phase('compile'):
                clock.advance(40.04)
            with timings.phase('native_runs'):
                clock.advance(5.0)
            for number in range(2, passes + 1):
                timings.begin_pass(number)
                with timings.phase('compile'):
                    clock.advance(10.0)
                with timings.phase('native_runs'):
                    clock.advance(5.0)
            timings.end_passes()
            with timings.phase('reference_runs'):
                clock.advance(18.3)
            output.mkdir(parents=True, exist_ok=True)
            exe = output / ('Timed_game' + EXT)
            exe.write_bytes(path.read_bytes())
            report = sms_report()
            report.update(executable=exe.name, build_executable=str(exe))
            report['rom'] = {**report['rom'], 'name': path.name}
            write_report(output / 'conversion-report.json', report)
            return exe

        return convert

    def publisher(self):
        from retrorecomp.publishing import publish_executable
        clock = self.clock

        def publish(source, target, **options):
            clock.advance(1.5)
            with timings.phase('packing'):          # what packing.compact_executable does
                clock.advance(30.0)
            return publish_executable(source, target, **{**options, 'compact': False})

        return publish

    def run_batch(self, convert, **options):
        log = []
        with patch('retrorecomp.systems.master_system.MasterSystemProfile.convert', side_effect=convert), \
                patch('retrorecomp.batch.publish_executable', side_effect=self.publisher()):
            record = convert_batch([self.item()], self.games_root, emit=log.append, **options)
        self.assertEqual((record['succeeded'], record['failed']), (1, 0), log)
        report_path = Path(record['games'][0]['report'])
        return log, json.loads(report_path.read_text(encoding='utf-8')), report_path

    def test_the_report_carries_the_phases_and_the_log_says_them_in_one_line(self):
        log, report, _ = self.run_batch(self.converter())
        figures = report['timings']
        self.assertEqual(figures, {'code_generation': 2.0, 'compile': 40.0, 'native_runs': 5.0, 'discovery': 0.0,
                                   'reference_runs': 18.3, 'packing': 30.0, 'publication': 1.5, 'other': 0.0,
                                   'total': 96.8})
        self.assertLessEqual(abs(sum(v for k, v in figures.items() if k != 'total') - figures['total']), 0.5)
        lines = [line for line in log if ': times: ' in line]
        self.assertEqual(lines, ['Timed game: times: code generation 2.0 s, compile 40.0 s, native runs 5.0 s, '
                                 'reference runs 18.3 s, packing 30.0 s, publication 1.5 s, discovery 0.0 s, '
                                 'total 96.8 s'])
        self.assertEqual(read_report(report)['timings'], figures, 'schema 2 reads it back')
        self.assertEqual(report['schema'], {'name': 'retro-recomp-report', 'version': 2})

    def test_learning_passes_are_counted_apart(self):
        _, report, _ = self.run_batch(self.converter(passes=3))
        figures = report['timings']
        self.assertEqual((figures['compile'], figures['native_runs'], figures['discovery']), (40.0, 5.0, 30.0))
        self.assertEqual(figures['total'], 126.8)

    def test_a_failed_quick_check_is_told_apart_from_the_full_conversion(self):
        item = self.item()
        converter = self.converter()
        clock = self.clock
        scan_levels = []

        def convert(path, **options):
            scan_levels.append(options.get('scan_level'))
            if options.get('scan_level') == 'quick':
                with timings.phase('compile'):
                    clock.advance(8.0)
                from retrorecomp.core import ConversionError
                raise ConversionError('quick routes failed')
            return converter(path, **options)

        log = []
        with patch('retrorecomp.knowledge_exchange._bundled', return_value={'rom_entries': [[512]]}), \
                patch('retrorecomp.systems.master_system.MasterSystemProfile.convert', side_effect=convert), \
                patch('retrorecomp.batch.publish_executable', side_effect=self.publisher()):
            record = convert_batch([item], self.games_root, emit=log.append)
        self.assertEqual((record['succeeded'], scan_levels), (1, ['quick', None]))
        figures = json.loads(Path(record['games'][0]['report']).read_text(encoding='utf-8'))['timings']
        self.assertEqual((figures['failed_quick_attempt'], figures['compile']), (8.0, 40.0))

    def test_the_figures_of_one_game_never_reach_another(self):
        _, first, _ = self.run_batch(self.converter())
        self.assertIsNone(timings.current())
        second_item = self.item(2)
        with patch('retrorecomp.systems.master_system.MasterSystemProfile.convert', side_effect=self.converter()), \
                patch('retrorecomp.batch.publish_executable', side_effect=self.publisher()):
            record = convert_batch([second_item], self.games_root, emit=lambda text: None)
        second = json.loads(Path(record['games'][0]['report']).read_text(encoding='utf-8'))['timings']
        self.assertEqual(second['total'], first['timings']['total'])

    def test_a_converter_that_marks_nothing_still_reports_a_total(self):
        def convert(path, *, output, title, **options):
            from retrorecomp.report_schema import write_report
            self.clock.advance(3.0)
            output.mkdir(parents=True, exist_ok=True)
            exe = output / ('Timed_game' + EXT)
            exe.write_bytes(path.read_bytes())
            report = sms_report()
            report.update(executable=exe.name, build_executable=str(exe))
            write_report(output / 'conversion-report.json', report)
            return exe
        _, report, _ = self.run_batch(convert)
        self.assertEqual((report['timings']['other'], report['timings']['total']), (3.0, 3.0 + 31.5))


if __name__ == '__main__':
    unittest.main()
