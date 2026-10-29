"""Synthetic report checks for the console-independent release check tool."""
from __future__ import annotations

import unittest

from retrorecomp.report_schema import REQUIRED_KEYS, with_schema_v2
from retrorecomp.systems import ALL_PROFILES
from tests.test_report_schema import FIXTURES
from tools import release_check
from tools.release_check import batch_problems, check_report, report_problems


def arcade_report() -> dict:
    return {'system': {'id': 'cps1', 'name': 'Capcom CPS-1'}, 'scan_level': 'standard',
            'native_validation': {'passed': True, 'packed_reference_match': True},
            'final_checks': [{'name': 'attract', 'reference_match': True, 'interpreted_opcodes': 0,
                              'audio_interpreted_opcodes': 0},
                             {'name': 'play', 'reference_match': True, 'interpreted_opcodes': 0,
                              'audio_interpreted_opcodes': 0}],
            'game_states': {'validation': {'fresh_process_match': True, 'truncated_state_rejected': True}}}


def console16_report() -> dict:
    return {'system': {'id': 'snes', 'name': 'Super Nintendo'}, 'advanced_scan': {'level': 'standard'},
            'native_validation': {'passed': True,
                                  'comparisons': [{'scenario': 'demo', 'differences': []},
                                                  {'scenario': 'play', 'differences': []}]},
            'final_checks': [{'scenario': 'demo', 'main_interpreted_opcodes': 0,
                              'audio_interpreted_opcodes': 0},
                             {'scenario': 'play', 'interpreted_opcodes': 0, 'audio_interpreted_opcodes': 0}],
            'cartridge_device': {'chip': 'GSU-1', 'mode': 'not_run', 'counter_unit': 'device instructions',
                                 'failed': False,
                                 'scenarios': [{'scenario': 'demo', 'frames': 100, 'interpreted_instructions': 0},
                                               {'scenario': 'play', 'frames': 100, 'interpreted_instructions': 40}]}}


def nes_report() -> dict:
    return {'system': {'id': 'nes', 'name': 'Nintendo Entertainment System'},
            'advanced_scan': {'level': 'standard'},
            'native_validation': {'passed': True,
                                  'scenarios': [{'scenario': 'boot', 'internal_differential': True,
                                                 'audio_pcm_match': True},
                                                {'scenario': 'play', 'internal_differential': True,
                                                 'audio_pcm_match': True}]},
            'final_checks': [{'scenario': 'boot', 'interpreter_cycles': 0, 'interpreter_rom_cycles': 0},
                             {'scenario': 'play', 'interpreter_cycles': 0, 'interpreter_rom_cycles': 0}]}


def core_report() -> dict:
    return {'system': {'id': 'sms', 'name': 'Master System'}, 'scan_level': 'standard', 'strict_checks': [],
            'native_validation': {'passed': True,
                                  'scenarios': [{'scenario': 'boot', 'passed': True, 'checks': {},
                                                 'missing_or_invalid_evidence': []}]},
            'final_checks': [{'scenario': 'boot', 'requested_frames': 600, 'interpreter_cycles': 0,
                              'total_cycles': 1000}]}


def gameboy_report() -> dict:
    return {'system': {'id': 'gb', 'name': 'Game Boy'}, 'scan_level': 'standard',
            'native_validation': {'passed': True, 'cpu_differential': '[DIFF] Matched for 100 steps / 60 frames',
                                  'scenarios': [{'scenario': 'boot', 'result': '[DIFF] Matched'}]},
            'final_checks': [{'scenario': 'boot', 'interpreter_cycles': 0, 'interpreter_handoffs': 0,
                              'fallback_sites': 0}]}


def x68000_report() -> dict:
    return {'system': {'id': 'x68', 'name': 'Sharp X68000'}, 'scan_level': 'standard',
            'native_validation': {'passed': True}, 'exploration_checks': [],
            'final_checks': [{'frames': 300, 'native_entries': 1000, 'interpreted_opcodes': 0,
                              'reference_match': True},
                             {'route': 'route-a', 'frames': 200, 'native_entries': 500,
                              'interpreted_opcodes': 0, 'reference_match': True}],
            'game_states': {'fresh_process_verified': True}}


class ArcadeTests(unittest.TestCase):
    def check(self, report, max_fallback: int = 0, **options):
        return check_report(report, 'cps1', 'standard', max_fallback, **options)

    def test_a_complete_standard_report_passes_every_gate(self):
        checked = self.check(arcade_report())
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['shape'], 'cps1_conversion')
        self.assertEqual([checked['gates'][name]['status'] for name in
                          ('conversion', 'native_reference', 'fallback', 'device', 'packed', 'states')],
                         ['pass', 'pass', 'pass', 'absent', 'pass', 'pass'])

    def test_a_wrong_report_level_fails_conversion(self):
        checked = self.check({**arcade_report(), 'scan_level': 'quick'})
        self.assertEqual(checked['gates']['conversion']['status'], 'fail')
        self.assertIn("scan level is 'quick', not 'standard'", checked['problems'])

    def test_interpreted_opcodes_over_the_limit_are_counted_per_scenario(self):
        report = arcade_report()
        report['final_checks'][1]['interpreted_opcodes'] = 75546
        checked = self.check(report)
        self.assertEqual(checked['gates']['fallback']['status'], 'fail')
        self.assertIn('play: 75,546 interpreted 68000/Z80 opcodes (limit 0)', checked['problems'])
        self.assertEqual(self.check(report, max_fallback=80000)['gates']['fallback']['status'], 'pass')

    def test_a_reference_mismatch_fails_native_reference(self):
        report = arcade_report()
        report['final_checks'][0]['reference_match'] = False
        checked = self.check(report)
        self.assertEqual(checked['gates']['native_reference']['status'], 'fail')
        self.assertIn('attract: native and reference differ', checked['problems'])

    def test_state_results_are_named_exactly(self):
        report = arcade_report()
        report['game_states']['validation']['fresh_process_match'] = False
        checked = self.check(report)
        self.assertEqual(checked['gates']['states']['status'], 'fail')
        self.assertIn('F8/F9 did not continue identically in a fresh process', checked['problems'])
        report['game_states']['validation']['fresh_process_match'] = True
        report['game_states']['validation']['truncated_state_rejected'] = False
        checked = self.check(report)
        self.assertIn('a damaged quick state was not rejected', checked['problems'])

    def test_a_failed_packed_comparison_fails(self):
        report = arcade_report()
        report['native_validation']['packed_reference_match'] = False
        checked = self.check(report)
        self.assertEqual(checked['gates']['packed']['status'], 'fail')
        self.assertIn('the packed executable was not compared with the reference', checked['problems'])

    def test_neo_geo_state_routes_and_refused_count_are_the_state_evidence(self):
        # The real Neo Geo report: one row per route and a count of refused damaged states.
        report = arcade_report()
        report['system'] = {'id': 'ng', 'name': 'Neo Geo'}
        report['game_states'] = {'validation': {
            'routes': [{'warmup': 30, 'fresh_process_match': True}, {'warmup': 4500, 'fresh_process_match': True}],
            'invalid_states_rejected': 26}}
        checked = check_report(report, 'ng', 'standard', 0, require_states=True)
        self.assertEqual(checked['gates']['states']['status'], 'pass')
        report['game_states']['validation']['routes'][1]['fresh_process_match'] = False
        checked = check_report(report, 'ng', 'standard', 0, require_states=True)
        self.assertIn('F8/F9 did not continue identically in a fresh process', checked['problems'])

    def test_a_neo_geo_report_reads_through_the_same_shape(self):
        report = arcade_report()
        report['system'] = {'id': 'ng', 'name': 'Neo Geo'}
        checked = check_report(report, 'ng', 'standard', 0)
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['shape'], 'neogeo_conversion')


class Console16Tests(unittest.TestCase):
    def check(self, report, max_fallback: int = 0, **options):
        return check_report(report, 'snes', 'standard', max_fallback, **options)

    def test_a_complete_report_passes_and_device_counts_stay_apart(self):
        checked = self.check(console16_report(), max_device=40)
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['gates']['device']['status'], 'pass')
        self.assertEqual(checked['counts']['device']['total_instructions'], 40)
        self.assertEqual(checked['counts']['device']['chip'], 'GSU-1')

    def test_device_instructions_are_only_checked_against_a_given_limit(self):
        checked = self.check(console16_report())
        self.assertEqual(checked['gates']['device']['status'], 'unchecked')
        checked = self.check(console16_report(), max_device=39)
        self.assertEqual(checked['gates']['device']['status'], 'fail')
        self.assertIn('GSU-1: 40 interpreted device instructions (limit 39)', checked['problems'])

    def test_a_failed_device_command_fails(self):
        report = console16_report()
        report['cartridge_device']['failed'] = True
        checked = self.check(report)
        self.assertEqual(checked['gates']['device']['status'], 'fail')
        self.assertIn('the cartridge device reported a failed command', checked['problems'])

    def test_a_scenario_without_a_reference_comparison_fails(self):
        report = console16_report()
        report['native_validation']['comparisons'] = [{'scenario': 'demo', 'differences': []}]
        checked = self.check(report)
        self.assertEqual(checked['gates']['native_reference']['status'], 'fail')
        self.assertIn('play: no native/reference comparison in the report', checked['problems'])

    def test_reference_differences_fail(self):
        report = console16_report()
        report['native_validation']['comparisons'][1]['differences'] = ['cpu_hash']
        checked = self.check(report)
        self.assertIn('play: native and reference differ', checked['problems'])

    def test_packed_and_states_are_absent_unless_required(self):
        checked = self.check(console16_report())
        self.assertEqual(checked['gates']['packed']['status'], 'absent')
        self.assertEqual(checked['gates']['states']['status'], 'absent')
        self.assertEqual(self.check(console16_report(), require_packed=True)['gates']['packed']['status'], 'fail')
        self.assertEqual(self.check(console16_report(), require_states=True)['gates']['states']['status'], 'fail')

    def test_a_sound_cpu_without_counts_in_the_report_reports_zero_audio(self):
        report = console16_report()
        for check in report['final_checks']:
            del check['audio_interpreted_opcodes']
        checked = self.check(report)
        self.assertEqual(checked['problems'], [])
        self.assertEqual([row['audio_interpreted'] for row in checked['counts']['scenarios']], [0, 0])

    def test_a_console_without_a_sound_cpu_has_no_audio_count(self):
        checked = check_report(core_report(), 'sms', 'standard', 0)
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['shape'], 'core')
        self.assertEqual([row['audio_interpreted'] for row in checked['counts']['scenarios']], [None])


class NesTests(unittest.TestCase):
    def check(self, report, max_fallback: int = 0, **options):
        return check_report(report, 'nes', 'standard', max_fallback, **options)

    def test_a_complete_report_passes(self):
        checked = self.check(nes_report())
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['shape'], 'nes')

    def test_interpreted_cycles_over_the_limit_fail(self):
        report = nes_report()
        report['final_checks'][1]['interpreter_cycles'] = 1200
        checked = self.check(report)
        self.assertEqual(checked['gates']['fallback']['status'], 'fail')
        self.assertIn('play: 1,200 interpreted CPU cycles (limit 0)', checked['problems'])

    def test_a_scenario_without_a_differential_fails_native_reference(self):
        report = nes_report()
        report['native_validation']['scenarios'] = [{'scenario': 'boot', 'internal_differential': True}]
        checked = self.check(report)
        self.assertIn('play: no native/reference comparison in the report', checked['problems'])

    def test_a_differential_without_the_audio_comparison_is_not_a_match(self):
        report = nes_report()
        del report['native_validation']['scenarios'][1]['audio_pcm_match']
        checked = self.check(report)
        self.assertIn('play: native and reference differ', checked['problems'])


class GameBoyTests(unittest.TestCase):
    def test_a_complete_report_passes(self):
        checked = check_report(gameboy_report(), 'gb', 'standard', 0)
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['shape'], 'gameboy')

    def test_interpreted_cycles_over_the_limit_fail(self):
        report = gameboy_report()
        report['final_checks'][0]['interpreter_cycles'] = 90
        checked = check_report(report, 'gb', 'standard', 0)
        self.assertIn('boot: 90 interpreted CPU cycles (limit 0)', checked['problems'])

    def test_a_missing_cpu_comparison_fails_native_reference(self):
        report = gameboy_report()
        report['native_validation']['scenarios'] = [{'scenario': 'boot', 'result': ''}]
        checked = check_report(report, 'gb', 'standard', 0)
        self.assertIn('no native/reference CPU comparison in the report', checked['problems'])


class X68000Tests(unittest.TestCase):
    def test_a_complete_report_passes_with_its_fresh_process_proof(self):
        checked = check_report(x68000_report(), 'x68', 'standard', 0)
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['gates']['states']['status'], 'pass')
        self.assertEqual(checked['shape'], 'x68000_conversion')

    def test_a_route_over_the_limit_is_named(self):
        report = x68000_report()
        report['final_checks'][1]['interpreted_opcodes'] = 12
        checked = check_report(report, 'x68', 'standard', 0)
        self.assertIn('route-a: 12 interpreted opcodes (limit 0)', checked['problems'])

    def test_a_reference_mismatch_fails(self):
        report = x68000_report()
        report['final_checks'][0]['reference_match'] = False
        checked = check_report(report, 'x68', 'standard', 0)
        self.assertIn('main: native and reference differ', checked['problems'])


class UnknownShapeTests(unittest.TestCase):
    def test_an_unknown_report_is_never_guessed(self):
        checked = check_report({'hello': 'world'}, 'cps1', 'standard', 0)
        self.assertIsNone(checked['shape'])
        self.assertIn('unknown report shape', checked['problems'])
        self.assertEqual({gate['status'] for gate in checked['gates'].values()}, {'absent'})

    def test_a_report_from_another_console_is_reported(self):
        checked = check_report(nes_report(), 'cps1', 'standard', 0)
        self.assertIn("system is 'nes', not 'cps1'", checked['problems'])
        self.assertIn('unknown report shape', checked['problems'])

    def test_an_unknown_console_is_reported(self):
        checked = check_report(arcade_report(), 'gamecube', 'standard', 0)
        self.assertIn('unknown console', checked['problems'])


class DerivedFromTheProfilesTests(unittest.TestCase):
    def test_the_consoles_and_readers_are_the_registered_profiles(self):
        ids = tuple(profile.id for profile in ALL_PROFILES)
        self.assertEqual(release_check.CONSOLES, ids)
        self.assertEqual(tuple(release_check.READERS), ids)
        self.assertTrue(all(callable(reader) for reader in release_check.READERS.values()))

    def test_a_fallback_count_is_named_as_it_always_was(self):
        labels = {profile.id: release_check._unit_label(profile) for profile in ALL_PROFILES}
        self.assertEqual({k: v for k, v in labels.items() if k in ('sms', 'gg', 'gb', 'nes', 'md', 'snes', 'ng', 'cps1', 'x68')}, {
            'sms': 'CPU cycles', 'gg': 'CPU cycles', 'gb': 'CPU cycles', 'nes': 'CPU cycles',
            'md': 'main/audio CPU opcodes', 'snes': 'main/audio CPU opcodes', 'ng': '68000/Z80 opcodes',
            'cps1': '68000/Z80 opcodes', 'x68': 'opcodes'})

    def test_a_writer_without_wording_is_named_from_the_profile(self):
        from tests.test_registration_surface import SyntheticProfile
        from retrorecomp.systems.specs import ReportShape

        def label(display):
            profile = type('Synthetic', (SyntheticProfile,), {'fallback_display': display,
                                                              'report_shape': ReportShape('zz_conversion', 'marker')})()
            return release_check._unit_label(profile)

        self.assertEqual((label('cycles'), label('opcodes')), ('CPU cycles', 'opcodes'))

    def test_every_shape_is_read_the_same_whether_old_keys_are_there_or_not(self):
        # The report the writers write (schema 2 beside their keys), the writer's own keys, and schema 2 alone.
        for label, make in FIXTURES.items():
            legacy = make()
            console = legacy['system']['id']
            written = with_schema_v2(legacy)
            only_v2 = {key: written[key] for key in REQUIRED_KEYS if key in written}
            profile = next(profile for profile in ALL_PROFILES if profile.id == console)
            forms = {'legacy': legacy, 'written': written, 'schema 2 only': only_v2}
            checked = {name: check_report(form, console, 'standard', 10 ** 9, 10 ** 9)
                       for name, form in forms.items()}
            with self.subTest(fixture=label):
                self.assertEqual(checked['legacy']['shape'], profile.report_shape.writer)
                self.assertEqual(checked['written'], checked['legacy'])
                self.assertEqual(checked['schema 2 only'], checked['legacy'])

    def test_a_report_of_another_writer_is_not_read_as_the_console_s(self):
        # The Game Boy shape under the Master System reader: a different writer, so no shape.
        checked = check_report(gameboy_report(), 'sms', 'standard', 0)
        self.assertIsNone(checked['shape'])
        self.assertIn('unknown report shape', checked['problems'])


class BatchTests(unittest.TestCase):
    def test_a_batch_that_stops_its_games_fails(self):
        ok = {'succeeded': 1, 'failed': 0, 'games': [{'rom': '1941.zip', 'status': 'success', 'system': 'cps1'}]}
        self.assertEqual(batch_problems(ok, 1), [])
        stopped = {'succeeded': 0, 'failed': 1,
                   'games': [{'rom': '1941.zip', 'status': 'failed', 'error': "KeyError: 'cps1'"}]}
        self.assertEqual(batch_problems(stopped, 1),
                         ['batch: 0 of 1 succeeded, 1 failed', "1941.zip: failed KeyError: 'cps1'"])

    def test_a_forced_console_checks_what_the_converter_detected(self):
        record = {'succeeded': 1, 'failed': 0,
                  'games': [{'rom': 'game.zip', 'status': 'success', 'system': 'md'}]}
        self.assertEqual(batch_problems(record, 1, 'md'), [])
        self.assertEqual(batch_problems(record, 1, 'cps1'), ["game.zip: detected as 'md'"])


class CompatibilityTests(unittest.TestCase):
    """The CPS-1 wrapper keeps its historical function results."""

    def test_report_problems_wording_is_unchanged(self):
        from tools.cps1_release_check import report_problems as cps1_report_problems
        self.assertEqual(cps1_report_problems(arcade_report(), 'standard', 0), [])
        self.assertEqual(report_problems(arcade_report(), 'standard', 0), [])
        self.assertEqual(cps1_report_problems(arcade_report(), 'extended', 0),
                         ["scan level is 'standard', not 'extended'"])

    def test_batch_problems_wording_is_unchanged(self):
        from tools.cps1_release_check import batch_problems as cps1_batch_problems
        stopped = {'succeeded': 0, 'failed': 1,
                   'games': [{'rom': '1941.zip', 'status': 'failed', 'error': "KeyError: 'cps1'"}]}
        self.assertEqual(cps1_batch_problems(stopped, 1),
                         ['batch: 0 of 1 succeeded, 1 failed', "1941.zip: failed KeyError: 'cps1'"])


if __name__ == '__main__':
    unittest.main()
