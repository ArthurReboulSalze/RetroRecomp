"""CPS-1 independent MC68000 vector replay (gate G10): the ROM-free, compiler-free parts of tools/cps1_vector_selftest.py.

The replay itself builds C and takes about two minutes: `python -B tools/cps1_vector_selftest.py` (BUILDING.md)."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cps1_vector_selftest', ROOT / 'tools' / 'cps1_vector_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class VectorHeaderTests(unittest.TestCase):
    def test_every_fixture_makes_one_flat_image_without_conflicting_code(self):
        expected = {'m68k-shifts': 834, 'md-prefetch': 2089 + 82, 'md-exceptions': 864}
        for name, count in expected.items():
            with self.subTest(fixture=name):
                header, image, fixture = selftest.cases_header(name)
                self.assertEqual(len(image), selftest.PROGRAM_BYTES)
                self.assertEqual(header.count('\nstatic const BytePair initial_'), count)
                self.assertIn(f'static const BytePair initial_{count - 1}[]', header)
                self.assertEqual(fixture['revision'], '64b253116a3de04aaac4346c43680960dc9b67e5')
                self.assertTrue(any(image))

    def test_the_two_authored_trace_vectors_have_their_own_group(self):
        header, _, _ = selftest.cases_header('md-prefetch')
        self.assertEqual(header.count(f'"{selftest.TRACE_GROUP}: post-instruction trace'), 2)

    def test_the_pc_is_architectural_and_a_stopped_stop_keeps_the_following_instruction(self):
        state = {key: 0 for key in selftest.REGS}
        state['pc'] = 0x1004
        self.assertTrue(selftest.state_literal(state).endswith(',4096u}'))
        self.assertTrue(selftest.state_literal(state, 0).endswith(',4100u}'))


class ProblemTests(unittest.TestCase):
    GOOD = {'groups': [
        {'group': 'ADD.w', 'cases': 10, 'native_executed': 10, 'native_state': 10, 'reference_state': 10, 'native_clock': 10,
         'reference_clock': 10, 'paths_equal': 10, 'paths_clock_equal': 10},
        {'group': 'DIVU-variable', 'cases': 10, 'native_executed': 10, 'native_state': 10, 'reference_state': 7,
         'native_clock': 10, 'reference_clock': 10, 'paths_equal': 7, 'paths_clock_equal': 10},
        {'group': f'authored {selftest.TRACE_GROUP}', 'cases': 2, 'native_executed': 2, 'native_state': 0, 'reference_state': 0,
         'native_clock': 0, 'reference_clock': 0, 'paths_equal': 2, 'paths_clock_equal': 2}]}

    def test_a_clean_run_has_no_problem(self):
        self.assertEqual(selftest.problems(self.GOOD), [])

    def test_each_kind_of_deviation_is_reported(self):
        def altered(index, **change):
            result = copy.deepcopy(self.GOOD)
            result['groups'][index].update(change)
            return selftest.problems(result)
        self.assertTrue(altered(0, native_state=9))                       # a native step differs from a vector
        self.assertTrue(altered(0, native_clock=9))                       # clocks differ
        self.assertTrue(altered(0, native_executed=9))                    # a vector fell back to the interpreter
        self.assertTrue(altered(0, reference_state=9, paths_equal=9))     # an unlisted group where the reference differs
        self.assertTrue(altered(0, paths_equal=9))                        # paths differ while the reference is right
        self.assertEqual(altered(1, reference_state=6, paths_equal=6), [])  # a listed group may deviate


if __name__ == '__main__':
    unittest.main()
