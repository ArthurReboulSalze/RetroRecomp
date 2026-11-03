"""X68000 independent MC68000 vector replay (gate G10): the ROM-free, compiler-free parts of tools/x68000_vector_selftest.py.

The replay itself builds C and takes a few minutes: `python -B tools/x68000_vector_selftest.py` (BUILDING.md)."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('x68000_vector_selftest', ROOT / 'tools' / 'x68000_vector_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class ObservationTests(unittest.TestCase):
    def test_each_vector_instruction_is_observed_at_its_own_address_with_its_own_bytes(self):
        for name, count in {'m68k-shifts': 834, 'md-prefetch': 2089 + 82, 'md-exceptions': 864}.items():
            with self.subTest(fixture=name):
                header, program, fixture = selftest.shared.cases_header(name)
                samples = selftest.observations(name, program)
                tests = list(fixture['tests'])
                if name == 'md-prefetch':
                    tests += json.loads((ROOT / 'tests/fixtures/md-prefetch/authored.json').read_text(encoding='utf-8'))['tests']
                self.assertEqual(len(tests), count)
                self.assertEqual([address for address, _ in samples], sorted({t['initial']['pc'] - 4 for t in tests}))
                for address, words in samples:
                    self.assertEqual(len(words), 2 * selftest.OBSERVED_BYTES)
                    self.assertEqual(bytes.fromhex(words), program[address:address + selftest.OBSERVED_BYTES])
                    self.assertLess(address, 0xc00000)    # inside the machine's RAM window: the steps are guarded on live RAM

    def test_the_harness_is_a_developer_tool_that_moves_no_stamp(self):
        from retrorecomp import stamp_inputs
        self.assertIn('native/x68000_vector_checks.c', stamp_inputs.NOT_INPUTS)

    def test_the_replay_reuses_the_shared_reading_of_the_fixtures(self):
        self.assertIs(selftest.shared.problems, selftest.shared.problems)
        self.assertEqual(selftest.FIXTURES, ('m68k-shifts', 'md-prefetch', 'md-exceptions'))


class ProblemTests(unittest.TestCase):
    def test_a_native_step_that_differs_from_a_vector_is_a_problem(self):
        result = {'groups': [{'group': 'ADD.w', 'cases': 10, 'native_executed': 10, 'native_state': 9, 'reference_state': 10,
                              'native_clock': 10, 'reference_clock': 10, 'paths_equal': 9, 'paths_clock_equal': 10}]}
        self.assertTrue(selftest.shared.problems(result))
        result['groups'][0].update(native_state=10, paths_equal=10)
        self.assertEqual(selftest.shared.problems(result), [])


class GroupsReplayTests(unittest.TestCase):
    def group(self, name='ADD.w', cases=10, **bad):
        row = {'group': name, 'cases': cases, 'native_executed': cases, 'native_state': cases, 'reference_state': cases,
               'native_clock': cases, 'reference_clock': cases, 'paths_equal': cases, 'paths_clock_equal': cases}
        row.update(bad)
        return row

    def test_the_recorded_deviations_name_groups_of_the_fixture_and_fit_their_size(self):
        recorded = json.loads((ROOT / 'tests/fixtures/m68k-groups/deviations-musashi-machines.json').read_text(encoding='utf-8'))
        sizes = {}
        for test in json.loads((ROOT / 'tests/fixtures/m68k-groups/cases.json').read_text(encoding='utf-8'))['tests']:
            sizes[test['group']] = sizes.get(test['group'], 0) + 1
        self.assertEqual(selftest.GROUPS, 'm68k-groups')
        self.assertTrue(recorded)
        for name, counts in recorded.items():
            self.assertIn(name, sizes)
            self.assertTrue(all(0 < value <= sizes[name] for value in counts.values()), name)
        # LINK A7, UNLK A7 and NEGX.B were listed until the three machines took the Mega Drive's state rules (1.6.7): only the
        # decimal instructions on operands that are not digits remain.
        self.assertEqual(set(recorded), {'ABCD', 'NBCD', 'SBCD'})

    def test_a_group_that_agrees_with_the_vectors_and_is_not_listed_passes(self):
        self.assertEqual(selftest.group_problems({'groups': [self.group()]}, {}), [])

    def test_a_group_that_differs_and_is_not_listed_is_a_problem(self):
        result = {'groups': [self.group(native_state=9, paths_equal=9)]}
        self.assertEqual(selftest.group_deviations(result), {'ADD.w': {'native_state': 1, 'paths': 1}})
        self.assertTrue(selftest.group_problems(result, {}))
        self.assertEqual(selftest.group_problems(result, {'ADD.w': {'native_state': 1, 'paths': 1}}), [])

    def test_a_listed_count_that_changed_is_a_problem_in_both_directions(self):
        listed = {'ADD.w': {'native_state': 2}}
        self.assertTrue(selftest.group_problems({'groups': [self.group(native_state=9)]}, listed))
        self.assertTrue(selftest.group_problems({'groups': [self.group(native_state=7)]}, listed))
        self.assertTrue(selftest.group_problems({'groups': [self.group()]}, listed))

    def test_a_clock_that_differs_from_a_vector_or_a_step_not_run_natively_is_a_problem(self):
        self.assertTrue(selftest.group_problems({'groups': [self.group(native_clock=9)]}, {}))
        self.assertTrue(selftest.group_problems({'groups': [self.group(reference_clock=9)]}, {}))
        self.assertTrue(selftest.group_problems({'groups': [self.group(native_executed=9)]}, {}))

    def test_the_groups_fixture_goes_through_its_own_problem_check(self):
        result = {'fixture': 'm68k-groups', 'groups': [self.group(native_state=9)]}
        self.assertTrue(selftest.problems(result))


if __name__ == '__main__':
    unittest.main()
