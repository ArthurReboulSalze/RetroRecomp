"""Atari ST independent MC68000 vector replay (gate G10): the ROM-free, compiler-free parts of tools/atarist_vector_selftest.py.

The replay itself builds C against the adapted Hatari and takes a minute: `python -B tools/atarist_vector_selftest.py` (BUILDING.md)."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('atarist_vector_selftest', ROOT / 'tools' / 'atarist_vector_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


def vector(sr=0x2700, ram=((0x1000, 1), (0x1001, 2)), final_ram=None, group='ADD.w', name='000 ADD.w D0, D1', pc=0x1004, **extra):
    """A synthetic SingleStepTests vector: the instruction at pc - 4, two prefetched words."""
    state = {key: 0 for key in selftest.REGS}
    state.update(usp=0x3000, ssp=0x4000, sr=sr, pc=pc)
    initial = dict(state, prefetch=[0xd240, 0x4e71], ram=[list(pair) for pair in ram])
    final = dict(state, pc=pc + 2, prefetch=[0x4e71, 0], ram=[list(pair) for pair in (final_ram or ram)])
    test = {'group': group, 'name': name, 'initial': initial, 'final': final, 'length': 4}
    test.update(extra)
    return test


class SelectionTests(unittest.TestCase):
    def test_a_vector_inside_the_ram_window_runs_in_both_passes(self):
        test = vector(ram=((0x800, 1), (0x3ffffe, 2)))
        self.assertEqual(selftest.classify(test), 'run')
        self.assertEqual(selftest.classify(test, flat=True), 'run')

    def test_a_vector_beyond_the_ram_of_the_session_runs_in_the_flat_pass_only(self):
        test = vector(ram=((0x1000, 1), (0x400000, 2)))
        self.assertEqual(selftest.RAM_END, 0x400000)
        self.assertEqual(selftest.classify(test), 'beyond_ram')
        self.assertEqual(selftest.classify(test, flat=True), 'run')
        # a final-state-only address counts too, and the address is masked to the 24-bit bus
        self.assertEqual(selftest.classify(vector(final_ram=((0x1000, 1), (0xff8800, 2)))), 'beyond_ram')
        self.assertEqual(selftest.classify(vector(ram=((0x1000, 1), (0x1000000 + 0x2000, 2)))), 'run')

    def test_the_first_eight_bytes_are_the_roms_mirror(self):
        self.assertEqual(selftest.classify(vector(ram=((0x1000, 1), (7, 2)))), 'rom_mirror')
        self.assertEqual(selftest.classify(vector(ram=((0x1000, 1), (8, 2)))), 'run')
        self.assertEqual(selftest.classify(vector(ram=((0x1000, 1), (7, 2))), flat=True), 'run')

    def test_the_system_area_below_0x800_is_the_supervisors(self):
        low = ((0x1000, 1), (0x400, 2))
        self.assertEqual(selftest.classify(vector(sr=0x2000, ram=low)), 'run')
        self.assertEqual(selftest.classify(vector(sr=0x0000, ram=low)), 'user_system_area')
        self.assertEqual(selftest.classify(vector(sr=0x0000, ram=low), flat=True), 'run')

    def test_only_the_trace_delivery_vectors_are_left_out_for_the_trace_bit(self):
        self.assertEqual(selftest.classify(vector(sr=0xa700)), 'run')
        self.assertEqual(selftest.classify(vector(sr=0xa710, name='post-instruction trace MULU source=0000 dest=0000ffff')), 'trace_delivery')

    def test_every_vector_of_a_fixture_is_counted_once(self):
        for name in selftest.FIXTURES:
            with self.subTest(fixture=name):
                tests = selftest.fixture_tests(name)
                for flat in (False, True):
                    run, left = selftest.selection(name, flat)
                    self.assertEqual(len(run) + sum(left.values()), len(tests))
                    if flat:
                        self.assertEqual(set(left), {'trace_delivery'} if name == 'md-prefetch' else set())
        run, left = selftest.selection('m68k-shifts', False)
        self.assertEqual((len(run), left), (834, {}))
        self.assertEqual(len(selftest.fixture_tests('md-prefetch')), 2089 + 82)


class ConversionTests(unittest.TestCase):
    def test_the_pc_loses_the_two_prefetched_words_and_wraps_on_the_24_bit_bus(self):
        self.assertEqual(selftest.architectural_pc(328828), 328824)
        self.assertEqual(selftest.architectural_pc(2, 4), 0xfffffe)
        self.assertEqual(selftest.architectural_pc(0x1234567 + 4), 0x234567)
        state = vector(pc=0x1004)['initial']
        values = selftest.state_values(state)
        self.assertEqual(values[18], 0x1000)
        self.assertEqual(values[15:18], [0x3000, 0x4000, 0x2700])

    def test_a_stopped_stop_keeps_the_same_offset_and_is_compared_as_stopped(self):
        stop = vector(group='STOP', length=4)
        stop['length'] = 4
        self.assertEqual(selftest.stops(stop), 1)
        self.assertEqual(selftest.final_pc_offset(stop), 4)
        user = vector(group='STOP')
        user['length'] = 34
        self.assertEqual(selftest.stops(user), 0)
        self.assertEqual(selftest.stops(vector()), 0)

    def test_the_vectors_transactions_are_placed_on_four_cycle_slots(self):
        # ABCD -(A1),-(A7) of the groups fixture: 2 idle, three reads, one write: 18 clocks, 20 once every access starts on a slot
        test = vector(transactions=[['n', 2], ['r', 4, 5, 0, '.b', 0, 1, 0], ['r', 4, 5, 0, '.b', 0, 1, 0],
                                    ['r', 4, 6, 0, '.w', 0, 1, 1], ['w', 4, 5, 0, '.b', 0, 1, 0]])
        self.assertEqual(selftest.aligned_cycles(test), 20)
        self.assertEqual(selftest.aligned_cycles(vector(transactions=[['r', 4, 6, 0, '.w', 0, 1, 1], ['n', 2]])), 6)
        self.assertEqual(selftest.aligned_cycles(vector(transactions=[['n', 8], ['r', 4, 6, 0, '.w', 0, 1, 1]])), 12)
        self.assertEqual(selftest.aligned_cycles(vector()), -1)
        for name in ('m68k-shifts', 'm68k-groups', 'md-prefetch'):    # the fixtures' own transactions add up to their clocks
            for test in selftest.fixture_tests(name)[:200]:
                clocks = sum(item[1] for item in test['transactions'])
                self.assertEqual(clocks, selftest.cycles_of(test))
                self.assertGreaterEqual(selftest.aligned_cycles(test), clocks)
                self.assertLess(selftest.aligned_cycles(test) - clocks, 4 * len(test['transactions']))

    def test_a_vector_is_one_line_the_harness_can_read(self):
        test = vector(sr=0x2704, ram=((0x1000, 1), (0x1001, 2)), final_ram=((0x1000, 1), (0x1001, 9), (0x2000, 7)), sr_mask=0xffe0,
                      transactions=[['r', 4, 6, 0, '.w', 0, 1, 1]])
        fields = selftest.vector_line(test).split(' ')
        self.assertEqual(fields[:2], ['ADD.w:000_ADD.w_D0,_D1', 'ADD.w'])
        self.assertEqual([int(field) for field in fields[2:8]], [4, 4, 0xffe0, 0, 0xd240, 0x4e71])     # clocks, aligned, mask, stopped, ir, irc
        initial, final, tail = fields[8:27], fields[27:46], fields[46:]
        self.assertEqual([int(x) for x in initial[15:19]], [0x3000, 0x4000, 0x2704, 0x1000])
        self.assertEqual(int(final[18]), 0x1002)
        self.assertEqual([int(x) for x in tail], [2, 0x1000, 1, 0x1001, 2, 3, 0x1000, 1, 0x1001, 9, 0x2000, 7])

    def test_the_real_fixtures_give_lines_of_the_same_shape(self):
        for name in selftest.FIXTURES:
            tests = selftest.fixture_tests(name)[:50]
            for test in tests:
                fields = selftest.vector_line(test).split(' ')
                before = int(fields[46])
                after = int(fields[46 + 1 + 2 * before])
                self.assertEqual(len(fields), 46 + 1 + 2 * before + 1 + 2 * after)
                self.assertEqual(int(fields[2]), selftest.cycles_of(test))


class ProblemTests(unittest.TestCase):
    def row(self, group='ADD.w', run=10, **bad):
        row = {'group': group, 'run': run, 'state_ok': run, 'cycle_ok': run, 'cycle_bus': 0, 'cycle_other': 0, 'cycle_unmodelled': 0,
               'plain_ok': run, 'model_checked': run, 'model_ok': run, 'native_step': run, 'native_state_ok': run, 'paths_equal': run}
        row.update(bad)
        return row

    def result(self, *groups, fixture='m68k-groups', mode='st', selected=None, outside=0):
        rows = list(groups)
        totals = {key: sum(row[key] for row in rows) for key in rows[0] if key != 'group'}
        return {'fixture': fixture, 'mode': mode, 'groups': rows, 'totals': totals, 'selected': totals['run'] if selected is None else selected,
                'outside_window': outside}

    def test_a_run_that_agrees_everywhere_has_no_problem(self):
        self.assertEqual(selftest.problems(self.result(self.row())), [])

    def test_a_state_or_clock_difference_that_is_not_recorded_is_a_problem(self):
        self.assertTrue(selftest.problems(self.result(self.row(state_ok=9))))
        self.assertTrue(selftest.problems(self.result(self.row(cycle_other=1, cycle_ok=9))))

    def test_a_recorded_difference_passes_only_with_its_recorded_count(self):
        (fixture, mode), groups = next(iter(selftest.RECORDED_STATE.items()))
        for group, count in groups.items():
            self.assertEqual(selftest.problems(self.result(self.row(group, 80, state_ok=80 - count), fixture=fixture, mode=mode)), [])
            self.assertTrue(selftest.problems(self.result(self.row(group, 80, state_ok=80 - count + 1), fixture=fixture, mode=mode)))
            self.assertTrue(selftest.problems(self.result(self.row(group, 80), fixture=fixture, mode=mode)))

    def test_a_native_step_that_differs_from_the_interpreter_or_a_vector_not_run_is_a_problem(self):
        self.assertTrue(selftest.problems(self.result(self.row(paths_equal=9))))
        self.assertTrue(selftest.problems(self.result(self.row(), selected=11)))
        self.assertTrue(selftest.problems(self.result(self.row(), outside=1)))

    def test_the_harness_is_a_developer_tool_that_moves_no_stamp(self):
        from retrorecomp import stamp_inputs
        self.assertIn('native/atarist_machine/atarist_vector_checks.c', stamp_inputs.NOT_INPUTS)


if __name__ == '__main__':
    unittest.main()
