"""Synthetic report checks for the console-independent release check tool."""
from __future__ import annotations

import unittest

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
                                  'scenarios': [{'scenario': 'boot', 'internal_differential': True},
                                                {'scenario': 'play', 'internal_differential': True}]},
            'final_checks': [{'scenario': 'boot', 'interpreter_cycles': 0, 'interpreter_rom_cycles': 0},
                             {'scenario': 'play', 'interpreter_cycles': 0, 'interpreter_rom_cycles': 0}]}


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
        self.assertEqual(checked['shape'], 'arcade')
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

    def test_a_neo_geo_report_reads_through_the_same_shape(self):
        report = arcade_report()
        report['system'] = {'id': 'ng', 'name': 'Neo Geo'}
        checked = check_report(report, 'ng', 'standard', 0)
        self.assertEqual(checked['problems'], [])
        self.assertEqual(checked['shape'], 'arcade')


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

    def test_a_console_without_a_sound_cpu_reports_zero_audio(self):
        report = console16_report()
        report['system'] = {'id': 'sms', 'name': 'Master System'}
        del report['cartridge_device']
        for check in report['final_checks']:
            del check['audio_interpreted_opcodes']
        checked = check_report(report, 'sms', 'standard', 0)
        self.assertEqual(checked['problems'], [])
        self.assertEqual([row['audio_interpreted'] for row in checked['counts']['scenarios']], [0, 0])


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
        self.assertIn('play: no native/reference differential in the report', checked['problems'])


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
        self.assertEqual(checked['shape'], 'x68000')

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
