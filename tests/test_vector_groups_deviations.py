"""The groups fixture (2,895 vectors of 85 instruction groups) replayed by the Neo Geo, the CPS-1 and the X68000: the ROM-free,
compiler-free parts (gate G10). The replays build C: `tools/neogeo_vector_selftest.py`, `tools/cps1_vector_selftest.py` and
`tools/x68000_vector_selftest.py`, each with `m68k-groups`.

Since the three machines take the Mega Drive's state rules for `LINK A7`, `UNLK A7`, `NEGX` and the decimal instructions
(`retrorecomp/m68000_state_rules.py`) and Musashi follows them (`retrorecomp/musashi_fixes.py`), no vector of the fixture is known to
differ: the shared lists are empty and a group that differs is a regression."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cps1_vector_selftest', ROOT / 'tools' / 'cps1_vector_selftest.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def group(name='ADD.w', cases=10, **bad):
    row = {'group': name, 'cases': cases, 'native_executed': cases, 'native_state': cases, 'reference_state': cases,
           'native_clock': cases, 'reference_clock': cases, 'paths_equal': cases, 'paths_clock_equal': cases}
    row.update(bad)
    return row


class RecordedDeviationsTests(unittest.TestCase):
    def recorded(self):
        return json.loads((ROOT / 'tests/fixtures' / shared.GROUPS / shared.DEVIATIONS).read_text(encoding='utf-8'))

    def test_the_shared_list_is_empty_since_the_decimal_rule(self):
        # The 22 decimal vectors (ABCD 2, NBCD 18, SBCD 2) the pinned text missed are reproduced since the decimal rule of the state rules
        # (13 November 2026): nothing is known to differ in this fixture any more, so a group that differs is a regression.
        self.assertEqual(self.recorded(), {})

    def test_the_three_replays_use_the_one_list_and_the_one_comparison(self):
        for path in ('tools/cps1_vector_selftest.py', 'tools/neogeo_vector_selftest.py', 'tools/x68000_vector_selftest.py'):
            self.assertIn('machine_problems', (ROOT / path).read_text(encoding='utf-8'), path)
        self.assertIn('vector_deviations.differences', (ROOT / 'tools/cps1_vector_selftest.py').read_text(encoding='utf-8'))
        self.assertIn('vector_deviations.differences', (ROOT / 'tools/megadrive_groups_selftest.py').read_text(encoding='utf-8'))

    def test_the_state_rules_are_those_of_the_mega_drive_and_the_text_is_not_copied(self):
        from retrorecomp import m68000_state_rules, megadrive_rules
        self.assertEqual(list(m68000_state_rules.RULES), ['LINK A7', 'UNLK A7', 'NEGX', 'decimal helpers', 'ABCD', 'SBCD', 'NBCD', 'decimal V'])
        for position, name in enumerate(m68000_state_rules.RULES, 1):          # read by position: RTR (0) stays the Mega Drive's alone
            self.assertIs(m68000_state_rules.RULES[name], megadrive_rules.STATE_RULES[position])
        self.assertIn('pushed', m68000_state_rules.RULES['LINK A7'][1])
        self.assertIn('popped', m68000_state_rules.RULES['UNLK A7'][1])
        self.assertIn('kept_z', m68000_state_rules.RULES['NEGX'][1])
        for name in ('ABCD', 'SBCD', 'NBCD'):
            self.assertIn('bcd_', m68000_state_rules.RULES[name][1])

    def test_each_rule_applies_once_and_a_moved_text_is_refused(self):
        from retrorecomp import m68000_state_rules
        from retrorecomp.core import ConversionError
        text = ''.join(old for old, _ in m68000_state_rules.RULES.values())
        fixed = m68000_state_rules.adapt_state_rules(text)
        for what, (old, new) in m68000_state_rules.RULES.items():
            if what != 'decimal helpers':                      # that rule keeps its anchor line and puts the helpers in front of it
                self.assertNotIn(old, fixed, what)
            self.assertIn(new, fixed, what)
        with self.assertRaises(ConversionError):
            m68000_state_rules.adapt_state_rules('nothing here')
        with self.assertRaises(ConversionError):
            m68000_state_rules.adapt_state_rules(text + text)

    def test_the_three_generators_apply_the_rules_after_adapt_semantics(self):
        for path in ('retrorecomp/cps1_codegen.py', 'retrorecomp/neogeo_codegen.py', 'retrorecomp/m68k_observed.py'):
            self.assertIn('adapt_state_rules(adapt_semantics(', (ROOT / path).read_text(encoding='utf-8'), path)

    def test_the_mega_drive_generator_does_not_use_the_module_of_the_three(self):
        # The Mega Drive applies megadrive_rules itself; the module of the three only reads its data, so the Mega Drive does not move.
        self.assertNotIn('m68000_state_rules', (ROOT / 'retrorecomp/megadrive_codegen.py').read_text(encoding='utf-8'))
        self.assertNotIn('m68000_state_rules', (ROOT / 'retrorecomp/megadrive_rules.py').read_text(encoding='utf-8'))


class JudgementTests(unittest.TestCase):
    def test_a_group_that_agrees_and_is_not_listed_passes(self):
        self.assertEqual(shared.group_problems({'groups': [group()]}, {}), [])

    def test_a_group_that_differs_and_is_not_listed_is_a_problem_and_a_listed_one_passes(self):
        result = {'groups': [group(native_state=9, paths_equal=9)]}
        self.assertEqual(shared.group_deviations(result), {'ADD.w': {'native_state': 1, 'paths': 1}})
        self.assertTrue(shared.group_problems(result, {}))
        self.assertEqual(shared.group_problems(result, {'ADD.w': {'native_state': 1, 'paths': 1}}), [])

    def test_a_listed_count_that_changed_is_a_problem_in_both_directions(self):
        listed = {'ADD.w': {'native_state': 2}}
        self.assertTrue(shared.group_problems({'groups': [group(native_state=9)]}, listed))
        self.assertTrue(shared.group_problems({'groups': [group(native_state=7)]}, listed))
        self.assertTrue(shared.group_problems({'groups': [group()]}, listed))

    def test_a_clock_that_differs_or_a_step_not_run_natively_is_a_problem(self):
        for bad in ({'native_clock': 9}, {'reference_clock': 9}, {'native_executed': 9}):
            self.assertTrue(shared.group_problems({'groups': [group(**bad)]}, {}), bad)

    def test_the_other_fixtures_keep_the_shared_rules(self):
        self.assertEqual(shared.machine_problems({'fixture': 'm68k-shifts', 'groups': [group()]}), [])
        self.assertTrue(shared.machine_problems({'fixture': 'm68k-shifts', 'groups': [group(native_state=9)]}))


if __name__ == '__main__':
    unittest.main()
