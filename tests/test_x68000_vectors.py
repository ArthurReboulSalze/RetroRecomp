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


if __name__ == '__main__':
    unittest.main()
