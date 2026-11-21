import copy
import json
import tempfile
import unittest
from pathlib import Path

from retrorecomp import time_estimates as te
from retrorecomp.systems import ALL_PROFILES
from tools import conversion_times


def tr(key, **values):
    """A stand-in for the window's tr: the key and its values, so the tests read what was chosen."""
    return key + (':' + ','.join(f'{name}={value}' for name, value in sorted(values.items())) if values else '')


TABLE = {
    'format': 1,
    'reference': {'label': 'Test PC'},
    'level_factors': {'quick': 0.5, 'standard': 1.0, 'extended': 2.0, 'thorough': 3.0},
    'machines': {
        'aa': {'standard': {'seconds': [60, 120, 180], 'longest': 300},
               'extended': {'seconds': [200, 250, 400], 'longest': 500}},
        'bb': {'standard': {'seconds': [600, 900, 1200], 'longest': 1500}},
    },
    'first_use': {'shared_build_seconds': 180, 'machines': {'bb': {'seconds': 420}}},
}


class TableTests(unittest.TestCase):
    def test_bundled_table_is_valid_and_names_known_machines(self):
        data = te.load()
        self.assertEqual(data['format'], te.FORMAT)
        self.assertEqual(data['reference']['label'], 'Ryzen 9 3900X')
        known = {profile.id for profile in ALL_PROFILES}
        self.assertTrue(set(data['machines']) <= known, set(data['machines']) - known)
        self.assertTrue(set(data['first_use']['machines']) <= known)
        # Every cell says where it comes from (reviewed data, not code conditions).
        for machine, levels in data['machines'].items():
            for level, cell in levels.items():
                self.assertGreaterEqual(cell['reports'], 3, (machine, level))
                self.assertRegex(cell['versions'], r'^\d+\.\d+\.\d+\.\.\d+\.\d+\.\d+$')
        self.assertIs(te.table(), te.table())

    def test_every_machine_the_converter_offers_has_a_row(self):
        # A machine that is not developer-only shows a level estimate in the Options (gui_estimates.py): without a row of its own the text is empty
        # (tools/gui_smoke.py failed on the PC Engine CD, 21 Nov 2026). The standard level is the one every row carries; a machine opened later fails here.
        from retrorecomp.systems import registry
        machines = te.load()['machines']
        missing = [profile.id for profile in registry.listed_profiles() if 'standard' not in machines.get(profile.id, {})]
        self.assertEqual(missing, [], 'add a row (standard level) to assets/conversion-times.json from the machine own conversion reports (tools/conversion_times.py)')

    def test_validation_refuses_a_bad_table(self):
        for change in (lambda d: d.update(format=2), lambda d: d['reference'].pop('label'),
                       lambda d: d['level_factors'].update(standard=2.0),
                       lambda d: d['machines']['aa'].pop('standard'),
                       lambda d: d['machines']['aa']['standard'].update(seconds=[180, 120, 60]),
                       lambda d: d['machines']['aa']['standard'].update(longest=10),
                       lambda d: d['machines']['aa'].update(slow={'seconds': [1, 2, 3], 'longest': 4}),
                       lambda d: d['first_use'].pop('shared_build_seconds')):
            data = copy.deepcopy(TABLE)
            change(data)
            with self.assertRaises(ValueError):
                te.validate(data)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'times.json'
            path.write_text(json.dumps(TABLE), encoding='utf-8')
            self.assertEqual(te.load(path)['reference']['label'], 'Test PC')


class GameTimeTests(unittest.TestCase):
    def test_measured_level_and_derived_level(self):
        measured = te.game_time('aa', 'extended', TABLE)
        self.assertEqual((measured.low, measured.typical, measured.high, measured.longest, measured.measured),
                         (200, 250, 400, 500, True))
        derived = te.game_time('aa', 'thorough', TABLE)
        self.assertEqual((derived.low, derived.typical, derived.high, derived.longest, derived.measured),
                         (180, 360, 540, 900, False))
        self.assertEqual(te.game_time('aa', 'no-such-level', TABLE).typical, 120)
        self.assertIsNone(te.game_time('zz', 'standard', TABLE))

    def test_a1200_standard_matches_what_the_owner_sees(self):
        # Arthur's Amiga 1200 conversions take 10 to 25 min on the reference PC (16 Nov 2026).
        found = te.game_time('a1200', 'standard')
        self.assertTrue(found.measured)
        self.assertTrue(8 * 60 <= found.low <= found.typical <= found.high <= found.longest <= 25 * 60, found)


class BatchTests(unittest.TestCase):
    def test_workers_share_the_work_but_never_beat_the_longest_game(self):
        self.assertEqual(te.batch_seconds([], 3), 0)
        self.assertEqual(te.batch_seconds([('aa', 100)] * 6, 3), 200)
        self.assertEqual(te.batch_seconds([('aa', 100)] * 2, 8), 100)
        self.assertEqual(te.batch_seconds([('aa', 100), ('bb', 900)], 3), 900)
        self.assertEqual(te.batch_seconds([('aa', 100)] * 4, 0), 400)

    def test_a_machine_held_to_fewer_workers(self):
        games = [('bb', 600)] * 4 + [('aa', 60)] * 6
        self.assertEqual(te.batch_seconds(games, 4), 2760 / 4)
        self.assertEqual(te.batch_seconds(games, 4, {'bb': 1}), 2400)
        self.assertEqual(te.batch_seconds(games, 4, {'bb': 8}), 2760 / 4)

    def test_queue_estimate_counts_first_use_apart(self):
        entries = [('aa', 'standard'), ('bb', 'standard'), ('zz', 'standard')]
        plain = te.queue_estimate(entries, jobs=3, data=TABLE)
        self.assertEqual((plain.games, plain.unknown, plain.typical, plain.high, plain.longest),
                         (2, 1, 900, 1200, 1500))
        self.assertEqual((plain.first_build, plain.first_download, plain.new_machines), (0.0, False, ()))
        tools = te.queue_estimate(entries, jobs=3, tools_missing=True, converted_machines={'aa', 'bb', 'zz'}, data=TABLE)
        self.assertEqual((tools.first_build, tools.first_download), (180.0, True))
        new = te.queue_estimate(entries, jobs=3, converted_machines={'aa'}, data=TABLE)
        self.assertEqual((new.first_build, new.first_download, new.new_machines), (420.0, True, ('bb', 'zz')))
        self.assertEqual(te.queue_estimate([('aa', 'quick')], jobs=1, data=TABLE).typical, 60)


class TextTests(unittest.TestCase):
    def test_durations_round_generously(self):
        # An order of magnitude per console (Arthur, 16 Nov 2026): 1 min steps under 5 min, 5 under 30, 10 under an
        # hour, then half hours.
        self.assertEqual(te.duration_text(30, tr), 'time_under_minute')
        self.assertEqual(te.duration_text(30, tr, up=True), 'time_minutes:minutes=1')
        self.assertEqual(te.duration_text(200, tr), 'time_minutes:minutes=3')
        self.assertEqual(te.duration_text(799, tr), 'time_minutes:minutes=15')
        self.assertEqual(te.duration_text(1107, tr, up=True), 'time_minutes:minutes=20')
        self.assertEqual(te.duration_text(1463, tr, up=True), 'time_minutes:minutes=25')
        self.assertEqual(te.duration_text(2580, tr, up=True), 'time_minutes:minutes=50')
        self.assertEqual(te.duration_text(3300, tr, up=True), 'time_hours_only:hours=1')
        self.assertEqual(te.duration_text(3600, tr), 'time_hours_only:hours=1')
        self.assertEqual(te.duration_text(4501, tr, up=True), 'time_hours:hours=1,minutes=30')
        self.assertEqual(te.rounded_minutes(0), 0)
        self.assertEqual(te.rounded_minutes(0, up=True), 0)

    def test_ranges(self):
        # The Amiga 1200 at Standard: 646 s to 1107 s measured, shown as 10 to 20 min.
        self.assertEqual(te.span_text(646, 1107, tr),
                         'time_range:high=time_minutes:minutes=20,low=time_minutes:minutes=10')
        self.assertEqual(te.span_text(32, 37, tr), 'time_up_to:high=time_minutes:minutes=1')
        self.assertEqual(te.span_text(600, 600, tr), 'time_up_to:high=time_minutes:minutes=10')
        self.assertEqual(te.span_text(2580, 4800, tr),
                         'time_range:high=time_hours:hours=1,minutes=30,low=time_minutes:minutes=40')

    def test_paths_effect_follows_the_profiles(self):
        # Quick check from received paths: shorter; full discovery kept: more native code only; no sharing: no note.
        self.assertEqual(te.paths_effect('md'), 'shorter')
        self.assertEqual(te.paths_effect('amiga'), 'native')
        self.assertEqual(te.paths_effect('psx'), 'native')
        self.assertEqual(te.paths_effect('a1200'), 'native')          # shares since 1.7.9, full discovery kept
        self.assertIsNone(te.paths_effect('n64'))                     # does not share
        self.assertIsNone(te.paths_effect('no-such-machine'))
        self.assertTrue(te.queue_estimate([('md', 'standard')], jobs=3).paths)
        self.assertFalse(te.queue_estimate([('n64', 'standard')], jobs=3).paths)
        self.assertEqual(te.elapsed_text(75), '1:15')
        self.assertEqual(te.elapsed_text(3725), '1:02:05')
        self.assertEqual(te.elapsed_text(-3), '0:00')

    def test_every_string_the_estimates_use_exists(self):
        from retrorecomp.i18n import STRINGS
        for key in ('time_under_minute', 'time_minutes', 'time_hours', 'time_hours_only', 'estimate_queue',
                    'estimate_unknown', 'estimate_first_build', 'estimate_first_download', 'estimate_level',
                    'estimate_level_derived', 'estimate_log', 'estimate_elapsed', 'estimate_running',
                    'estimate_running_over', 'converting_elapsed', 'converting_clock', 'stop_elapsed', 'first_use_note',
                    'time_range', 'time_up_to', 'estimate_paths_queue', 'estimate_paths_shorter', 'estimate_paths_native',
                    'estimate_paths_time'):
            self.assertIn(key, STRINGS)


class WithPathsTests(unittest.TestCase):
    def test_the_owner_s_a1200_figure_shows_only_once_the_machine_shares_paths(self):
        from unittest.mock import patch
        from retrorecomp.gui_estimates import EstimatesMixin

        class Window(EstimatesMixin):
            def tr(self, key, **values):
                return tr(key, **values)

        # Arthur, 16 Nov 2026: about 20 to 25 min of recompilation without discovery when the A1200 shares paths.
        self.assertEqual(te.with_paths_time('a1200'), (1200, 1500))
        self.assertIn('owner', te.table()['with_paths']['a1200']['source'])
        self.assertIsNone(te.with_paths_time('md'))
        window = Window()
        with patch.object(te, 'paths_effect', return_value=None):                    # a machine that does not share
            self.assertNotIn('estimate_paths', window.level_estimate_text('a1200'))
        text = window.level_estimate_text('a1200')                                     # the A1200 shares since 1.7.9
        self.assertIn('estimate_paths_native', text)
        self.assertIn('estimate_paths_time:span=time_range:high=time_minutes:minutes=25,low=time_minutes:minutes=20', text)
        bad = copy.deepcopy(TABLE)
        bad['with_paths'] = {'aa': {'seconds': [1500, 1200], 'source': 'x'}}
        with self.assertRaises(ValueError):
            te.validate(bad)
        bad['with_paths'] = {'zz': {'seconds': [1200, 1500], 'source': 'x'}}
        with self.assertRaises(ValueError):
            te.validate(bad)


class MeasureToolTests(unittest.TestCase):
    def report(self, **changes):
        data = {'system': 'aa', 'version': '1.7.5', 'target': 'windows-x86_64', 'created_utc': 'x',
                'toolchain': {'kind': 'llvm'}, 'scan': {'level': 'standard'}, 'timings': {'total': 100.0}}
        data.update(changes)
        return data

    def test_which_reports_count(self):
        self.assertEqual(conversion_times.report_row(self.report())['seconds'], 100.0)
        self.assertIsNone(conversion_times.report_row(self.report(target='linux-x86_64')))
        self.assertIsNone(conversion_times.report_row(self.report(toolchain={'kind': 'msvc'})))
        self.assertIsNone(conversion_times.report_row(self.report(timings={})))
        self.assertEqual(conversion_times.report_row(
            self.report(timings={}, conversion_wall_seconds=42.0, toolchain=None))['seconds'], 42.0)
        self.assertEqual(conversion_times.report_row(self.report(system={'id': 'bb'}))['system'], 'bb')

    def test_summary_cells(self):
        rows = [{'system': 'aa', 'level': 'standard', 'version': '1.7.5', 'seconds': value, 'created': str(value)}
                for value in (100, 200, 300, 400, 2)]
        rows += [{'system': 'aa', 'level': 'extended', 'version': '1.6.8', 'seconds': 900, 'created': 'e'}]
        rows += [{'system': 'aa', 'level': 'quick', 'version': '1.5.0', 'seconds': 50, 'created': 'q'}]
        table = conversion_times.summarize(rows)
        self.assertEqual(table['aa']['standard'], {'seconds': [175, 250, 325], 'longest': 400, 'reports': 4,
                                                   'versions': '1.7.5..1.7.5'})
        self.assertEqual(table['aa']['few']['extended']['reports'], 1)
        self.assertNotIn('quick', table['aa'])
        self.assertNotIn('quick', table['aa']['few'])

    def test_collect_reads_reports_once(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ('one', 'two'):
                path = Path(folder) / name / 'conversion-report.json'
                path.parent.mkdir()
                path.write_text(json.dumps(self.report()), encoding='utf-8')
            self.assertEqual(len(conversion_times.collect([folder])), 1)


if __name__ == '__main__':
    unittest.main()
