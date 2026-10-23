"""Scan levels: shared vocabulary, per-console budgets and preference parsing."""
import unittest

from smsrecomp import scan_levels as sl


class ScanLevelTests(unittest.TestCase):
    def test_standard_is_the_former_default_everywhere(self):
        for console in sl.CONSOLES:
            plan = sl.plan_for(console, None, passes=3, frames=sl.DEFAULT_FRAMES[console])
            self.assertEqual((plan.level, plan.passes, plan.frames, plan.long_routes),
                             ('standard', 3, sl.DEFAULT_FRAMES[console], 0), console)
        self.assertEqual(sl.console16_budget('standard', 3600),
                         {'advanced': False, 'demo_frames': 3600, 'route_count': 0, 'route_frames': 18000})
        self.assertEqual(sl.x68000_budget('standard'), {'exploration': True, 'long_count': 0, 'long_frames': 18000})
        self.assertEqual(sl.nes_budget('standard')['advanced'], False)
        self.assertEqual(sl.gameboy_budget('standard'), {'varied': True, 'deep_allowed': True, 'route_count': 0, 'route_frames': 18000})

    def test_former_switches_map_to_levels(self):
        self.assertEqual(sl.plan_for('md', None, md_advanced_scan=True).level, 'thorough')
        self.assertEqual(sl.plan_for('snes', None, md_advanced_scan=True).level, 'thorough')
        self.assertEqual(sl.plan_for('nes', None, nes_advanced_scan=True).level, 'extended')
        self.assertEqual(sl.plan_for('gb', None, md_advanced_scan=True, nes_advanced_scan=True).level, 'standard')

    def test_saved_entries_override_switches_and_shared_limits(self):
        saved = {'md': {'level': 'extended', 'passes': 2}, 'x68': {'frames': 6000},
                 'bogus': {'level': 'thorough'}, 'gb': {'level': 'nope', 'passes': 99, 'frames': True}}
        self.assertEqual(sl.normalize(saved), {'md': {'level': 'extended', 'passes': 2}, 'x68': {'frames': 6000}})
        plan = sl.plan_for('md', saved, passes=3, frames=3600, md_advanced_scan=True)
        self.assertEqual((plan.level, plan.passes, plan.frames), ('extended', 2, 3600))
        plan = sl.plan_for('x68', saved, passes=3, frames=4000)
        self.assertEqual((plan.level, plan.passes, plan.frames), ('standard', 3, 6000))
        # A command-line level wins over the saved entry.
        self.assertEqual(sl.plan_for('md', saved, level='quick').level, 'quick')

    def test_quick_runs_one_capped_pass(self):
        for console in sl.CONSOLES:
            plan = sl.plan_for(console, {console: {'level': 'quick', 'passes': 5, 'frames': 9000}})
            self.assertEqual((plan.passes, plan.frames), (1, min(9000, sl.QUICK_FRAMES[console])), console)
        self.assertEqual(sl.plan_for('md', None, level='quick', frames=600).frames, 600)

    def test_extended_and_thorough_differ_on_every_console(self):
        self.assertEqual(sl.console16_budget('extended', 3600)['demo_frames'], 12000)
        self.assertEqual(sl.console16_budget('thorough', 3600)['demo_frames'], 24000)
        self.assertEqual((sl.console16_budget('extended', 3600)['route_count'], sl.console16_budget('thorough', 3600)['route_count']), (1, 2))
        self.assertEqual(sl.console16_budget('thorough', 30000)['demo_frames'], 30000)
        self.assertEqual(sl.x68000_budget('extended'), {'exploration': True, 'long_count': 1, 'long_frames': 18000})
        self.assertEqual(sl.x68000_budget('thorough'), {'exploration': True, 'long_count': 3, 'long_frames': 36000})
        self.assertEqual(sl.x68000_budget('quick')['exploration'], False)
        self.assertEqual((sl.nes_budget('extended')['route_count'], sl.nes_budget('thorough')['route_count']), (0, 2))
        self.assertTrue(sl.nes_budget('extended')['advanced'] and sl.nes_budget('thorough')['advanced'])
        self.assertEqual(sl.nes_budget('quick'), {'advanced': False, 'play_left': False, 'route_count': 0, 'route_frames': 18000})
        for budget in (sl.gameboy_budget, sl.sega_budget, sl.neogeo_budget):
            self.assertEqual((budget('extended')['route_count'], budget('thorough')['route_count']), (1, 2))
        self.assertEqual(sl.gameboy_budget('quick'), {'varied': False, 'deep_allowed': False, 'route_count': 0, 'route_frames': 18000})

    def test_nes_and_game_boy_scenario_builders_follow_the_budgets(self):
        import tempfile
        from pathlib import Path
        from smsrecomp import random_routes as rr
        from smsrecomp.nes import _write_probe_scripts, _scenario_frames
        from smsrecomp.gameboy_coverage import probe_scenarios
        identity = 'c' * 64
        with tempfile.TemporaryDirectory() as temp:
            routes = rr.long_routes('nes', identity, count=2, frames=18000)
            scripts = _write_probe_scripts(Path(temp), 3600, advanced=True, play_left=True, long_routes=routes)
            self.assertEqual(list(scripts)[-2:], ['long_1', 'long_2'])
            self.assertTrue(scripts['long_1'].read_text(encoding='ascii').startswith('0 -\n'))
            budgets = _scenario_frames(scripts, 3600, routes)
            self.assertEqual((budgets['boot'], budgets['play_right'], budgets['long_1'], budgets['long_2']),
                             (3600, 3600, 18000, 18000))
            quick = _write_probe_scripts(Path(temp), 1800, advanced=False, play_left=False)
            self.assertEqual(list(quick), ['boot', 'play_right'])
        gb_routes = rr.long_routes('gb', identity, count=1, frames=18000, two_players=False)
        scenarios = probe_scenarios(3600, varied=True, long_routes=gb_routes)
        self.assertEqual([s.name for s in scenarios], ['boot', 'play_r', 'play_l', 'varied', 'long-1'])
        self.assertEqual((scenarios[-1].frames, scenarios[0].frames), (18000, None))
        self.assertIn(':S:', scenarios[-1].input_script)
        self.assertEqual([s.name for s in probe_scenarios(3600, varied=False)], ['boot', 'play_r', 'play_l'])

    def test_unknown_inputs_are_refused(self):
        with self.assertRaises(ValueError):
            sl.plan_for('amiga', None)
        with self.assertRaises(ValueError):
            sl.plan_for('md', None, level='maximal')
        self.assertEqual(sl.plan_for('md', None).as_dict()['long_routes'], 0)


if __name__ == '__main__':
    unittest.main()
