"""Amiga independent MC68000 vector replay (gate G10): the ROM-free, compiler-free parts of tools/amiga_vector_selftest.py.

The replay itself builds vAmiga's Core and takes a few minutes after the first build: `python -B tools/amiga_vector_selftest.py`
(BUILDING.md). These tests need neither a compiler nor a Kickstart; they skip when the SingleStepTests fixtures are absent."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('amiga_vector_selftest', ROOT / 'tools' / 'amiga_vector_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)

FIXTURES_PRESENT = all((ROOT / 'tests' / 'fixtures' / name / 'cases.json').is_file() for name in selftest.FIXTURES)


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
    def test_only_the_trace_delivery_vectors_are_left_out(self):
        self.assertEqual(selftest.classify(vector(sr=0xa700)), 'run')
        self.assertEqual(selftest.classify(vector(sr=0xa710, name='post-instruction trace MULU source=0000 dest=0000ffff')), 'trace_delivery')

    @unittest.skipUnless(FIXTURES_PRESENT, 'the SingleStepTests fixtures are not in this tree')
    def test_every_vector_of_a_fixture_is_counted_once(self):
        expected = {'m68k-groups': 2895, 'm68k-shifts': 834, 'md-prefetch': 2089 + 82, 'md-exceptions': 864}
        for name in selftest.FIXTURES:
            with self.subTest(fixture=name):
                tests = selftest.fixture_tests(name)
                self.assertEqual(len(tests), expected[name])
                run, left = selftest.selection(name)
                self.assertEqual(len(run) + sum(left.values()), len(tests))
                self.assertEqual(left, {'trace_delivery': 2} if name == 'md-prefetch' else {})


class ConversionTests(unittest.TestCase):
    def test_the_pc_loses_the_two_prefetched_words_and_wraps_on_the_24_bit_bus(self):
        self.assertEqual(selftest.architectural_pc(328828), 328824)
        self.assertEqual(selftest.architectural_pc(2, 4), 0xfffffe)
        self.assertEqual(selftest.architectural_pc(0x1234567 + 4), 0x234567)
        values = selftest.state_values(vector(pc=0x1004)['initial'])
        self.assertEqual(values[18], 0x1000)
        self.assertEqual(values[15:18], [0x3000, 0x4000, 0x2700])
        self.assertEqual(values[19:], [0xd240, 0x4e71])

    def test_a_stopped_stop_keeps_its_pc_and_every_other_vector_loses_the_queue_words(self):
        stop = vector(group='STOP', length=4)
        self.assertEqual((selftest.stops(stop), selftest.final_pc_offset(stop)), (1, 0))
        user = vector(group='STOP')
        user['length'] = 34
        self.assertEqual((selftest.stops(user), selftest.final_pc_offset(user)), (0, 4))
        self.assertEqual((selftest.stops(vector()), selftest.final_pc_offset(vector())), (0, 4))

    def test_the_bus_cycles_start_where_the_idle_periods_end(self):
        test = vector(transactions=[['n', 2], ['r', 4, 5, 0x1000, '.b', 0, 1, 0], ['w', 4, 6, 0x1002, '.w', 0, 1, 1], ['n', 6],
                                    ['r', 4, 6, 0x1004, '.w', 0, 1, 1]])
        self.assertEqual(selftest.transactions(test), [(0, 2, 0x1000, 1), (1, 6, 0x1002, 2), (0, 16, 0x1004, 2)])
        self.assertIsNone(selftest.transactions(vector()))
        with self.assertRaises(ValueError):
            selftest.transactions(vector(transactions=[['t', 4, 0, 0, '.w', 0, 1, 1]]))

    @unittest.skipUnless(FIXTURES_PRESENT, 'the SingleStepTests fixtures are not in this tree')
    def test_the_fixtures_transactions_add_up_to_their_clocks(self):
        for name in ('m68k-shifts', 'm68k-groups', 'md-prefetch'):
            for test in selftest.fixture_tests(name)[:200]:
                self.assertEqual(sum(item[1] for item in test['transactions']), selftest.cycles_of(test))

    def test_a_vector_is_one_line_the_harness_can_read(self):
        test = vector(sr=0x2704, ram=((0x1000, 1), (0x1001, 2)), final_ram=((0x1000, 1), (0x1001, 9), (0x2000, 7)), sr_mask=0xffe0,
                      transactions=[['r', 4, 6, 0x1004, '.w', 0, 1, 1]])
        fields = [int(field) for field in selftest.vector_line(7, test).split(' ')]
        self.assertEqual(fields[:5], [7, 4, 0xffe0, 0, 1])                  # index, clocks, SR mask, stopped, transaction count
        self.assertEqual(fields[5:9], [0, 0, 0x1004, 2])                    # the transaction: read, clock 0, address, size
        initial, final, tail = fields[9:30], fields[30:51], fields[51:]
        self.assertEqual(initial[15:21], [0x3000, 0x4000, 0x2704, 0x1000, 0xd240, 0x4e71])
        self.assertEqual(final[18], 0x1002)
        self.assertEqual(tail, [2, 0x1000, 1, 0x1001, 2, 3, 0x1000, 1, 0x1001, 9, 0x2000, 7])
        self.assertEqual(selftest.vector_line(0, vector()).split(' ')[4], '-1')      # no transaction list

    @unittest.skipUnless(FIXTURES_PRESENT, 'the SingleStepTests fixtures are not in this tree')
    def test_the_real_fixtures_give_lines_of_the_same_shape(self):
        for name in selftest.FIXTURES:
            for index, test in enumerate(selftest.fixture_tests(name)[:50]):
                fields = selftest.vector_line(index, test).split(' ')
                ntx = int(fields[4])
                head = 5 + 4 * max(ntx, 0) + 42
                before = int(fields[head])
                after = int(fields[head + 1 + 2 * before])
                self.assertEqual(len(fields), head + 1 + 2 * before + 1 + 2 * after)
                self.assertEqual(int(fields[1]), selftest.cycles_of(test))

    def test_the_observed_sample_of_a_vector_is_its_queue_then_its_ram(self):
        test = vector(ram=((0x1000, 0xd2), (0x1001, 0x40), (0x1002, 0x4e), (0x1003, 0x71), (0x1004, 0x12), (0x1005, 0x34)))
        address, words = selftest.code_sample(test)
        self.assertEqual(address, 0x1000)
        self.assertEqual(len(words), 2 * selftest.SAMPLE_BYTES)
        self.assertEqual(words[:12], 'd2404e711234')
        self.assertEqual(words[12:], '0' * (2 * selftest.SAMPLE_BYTES - 12))


def row(regs='', ram=0, cyc=4, bo=0, bt=0, off=2, nat=1, nd=''):
    """One line of the harness's answer."""
    return {'i': 0, 'regs': regs, 'detail': '', 'ram': ram, 'cyc': cyc, 'bo': bo, 'bt': bt, 'off': off, 'stop': 0, 'nat': nat, 'nd': nd, 'seq': ''}


def with_opcode(op, group='ADD.l', **extra):
    test = vector(group=group, **extra)
    test['initial']['prefetch'] = [op, 0x4e71]
    return test


class DeviationTests(unittest.TestCase):
    def test_a_vector_that_agrees_everywhere_has_no_deviation(self):
        self.assertEqual(selftest.deviations(row(), vector(), 2), [])

    def test_state_clocks_and_bus_are_separate_kinds(self):
        test = vector(transactions=[['r', 4, 6, 0x1004, '.w', 0, 1, 1]])
        self.assertEqual(selftest.deviations(row(regs='d0 '), test, 2), ['state'])
        self.assertEqual(selftest.deviations(row(ram=1), test, 2), ['state'])
        self.assertEqual(selftest.deviations(row(cyc=6), test, 2), ['clocks'])
        self.assertEqual(selftest.deviations(row(bo=1), test, 2), ['bus'])
        self.assertEqual(selftest.deviations(row(bt=1), test, 2), ['bus'])
        self.assertEqual(selftest.deviations(row(off=4), test, 2), ['bus'])
        self.assertEqual(selftest.deviations(row(regs='sr ', cyc=6, bo=1), test, 2), ['state', 'clocks', 'bus'])
        self.assertEqual(selftest.deviations(row(bo=1, off=9), vector(), 2), [])         # a fixture with no transaction list has no bus kind

    def test_the_family_predicates_read_the_opcode_of_the_vector(self):
        family = {(f.key, f.name): f for f in selftest.FAMILIES}
        memory = family[(('m68k-groups', 'ADD.l', 'bus'), 'long result written to memory')]
        self.assertTrue(memory.applies(with_opcode(0xd1a9), row()))       # ADD.l D0,(d16,A1)
        self.assertTrue(memory.applies(with_opcode(0x54a9), row()))       # ADDQ.l #2,(d16,A1)
        self.assertTrue(memory.applies(with_opcode(0x069f), row()))       # ADDI.l #imm,(A7)+
        self.assertFalse(memory.applies(with_opcode(0x0681), row()))      # ADDI.l #imm,D1
        self.assertFalse(memory.applies(with_opcode(0xd081), row()))      # ADD.l D1,D0
        self.assertFalse(memory.applies(with_opcode(0xd2a9), row()))      # ADD.l (d16,A1),D1: a register destination
        extended = family[(('m68k-groups', 'ADDX.l', 'bus'), 'predecrement long operands')]
        self.assertTrue(extended.applies(with_opcode(0xdf8c), row()))
        self.assertFalse(extended.applies(with_opcode(0xd781), row()))
        btst = family[(('m68k-groups', 'BTST', 'clocks'), 'BTST Dn,#imm')]
        self.assertTrue(btst.applies(with_opcode(0x0b3c), row()))
        self.assertFalse(btst.applies(with_opcode(0x0b12), row()))
        movem = {f.name: f for f in selftest.FAMILIES if f.group == 'MOVEM.l-phases'}
        self.assertTrue(movem['MOVEM.l from memory'].applies(with_opcode(0x4cd7), row()))
        self.assertFalse(movem['MOVEM.l from memory'].applies(with_opcode(0x48e7), row()))
        self.assertTrue(movem['MOVEM.l to -(An)'].applies(with_opcode(0x48e7), row()))      # MOVEM.l list,-(A7)
        self.assertFalse(movem['MOVEM.l to -(An)'].applies(with_opcode(0x48d7), row()))     # (A7): another store mode
        chk = next(f for f in selftest.FAMILIES if f.name == 'CHK with a negative Dn')
        negative, positive = with_opcode(0x4b86, group='CHK-phases'), with_opcode(0x4b86, group='CHK-phases')
        negative['initial']['d5'] = 0xffff8000
        positive['initial']['d5'] = 0x00007fff
        self.assertTrue(chk.applies(negative, row()))
        self.assertFalse(chk.applies(positive, row()))
        stop = next(f for f in selftest.FAMILIES if f.group == 'STOP')
        stopped = vector(group='STOP', length=4)
        self.assertTrue(stop.applies(stopped, row(regs='irc ')))
        self.assertFalse(stop.applies(stopped, row(regs='irc pc ')))        # a second difference is not this family
        privilege = vector(group='STOP')
        privilege['length'] = 34                                           # a STOP in user mode takes the privilege exception
        self.assertFalse(stop.applies(privilege, row(regs='irc ')))


class EvaluationTests(unittest.TestCase):
    def result(self, tests, rows, fixture='m68k-groups'):
        return {'fixture': fixture, 'rows': rows, 'tests': tests, 'selected': len(tests), 'left_out': {}, 'total': len(tests)}

    def test_a_deviation_in_no_family_is_unexplained_and_a_problem(self):
        tests = [vector(group='ADD.w', transactions=[['r', 4, 6, 0x1004, '.w', 0, 1, 1]])]
        result = self.result(tests, [row(bo=1)])
        evaluated = selftest.evaluate(result)
        self.assertEqual((evaluated['totals']['deviating'], evaluated['totals']['unexplained']), (1, 1))
        found = selftest.problems(evaluated, result)
        self.assertTrue(any('in no family' in text for text in found))

    def test_a_deviation_a_family_covers_is_counted_there_and_a_changed_count_is_a_problem(self):
        family = selftest.FAMILIES[0]                           # ADD.l, memory destination, bus
        self.assertEqual(family.key, ('m68k-groups', 'ADD.l', 'bus'))
        test = with_opcode(0xd1a9, transactions=[['r', 4, 6, 0x1004, '.w', 0, 1, 1]])
        result = self.result([test], [row(bo=1)])
        evaluated = selftest.evaluate(result)
        self.assertEqual((evaluated['totals']['in_a_family'], evaluated['totals']['unexplained']), (1, 0))
        self.assertEqual(evaluated['covered'][family.key + (0,)], 1)
        found = selftest.problems(evaluated, result)
        self.assertEqual([text for text in found if 'in no family' in text], [])
        self.assertTrue(any(text.startswith(f'family {family.name}') for text in found))        # 1 vector, 10 recorded

    def test_the_native_step_must_equal_the_interpreter_and_exist(self):
        tests = [vector(), vector()]
        result = self.result(tests, [row(nat=2, nd='d0 '), row(nat=0)])
        found = selftest.problems(selftest.evaluate(result), result)
        self.assertTrue(any('differs from the interpreter' in text for text in found))
        self.assertTrue(any('no native step' in text for text in found))

    def test_a_vector_that_did_not_run_is_a_problem(self):
        result = self.result([vector()], [row()])
        result['selected'] = 2
        self.assertTrue(any('ran' in text for text in selftest.problems(selftest.evaluate(result), result)))

    def test_a_clean_fixture_has_no_problem(self):
        result = self.result([vector(), vector()], [row(), row()], fixture='m68k-shifts')
        self.assertEqual(selftest.problems(selftest.evaluate(result), result), [])

    def test_the_chk_cause_is_checked_on_register_operands(self):
        def chk(dn, bound, clocks):
            test = with_opcode(0x4b86 & ~7 | 6, group='CHK-phases')           # CHK D6,D5
            test['initial'].update(d5=dn & 0xffffffff, d6=bound & 0xffffffff)
            test['length'] = clocks
            return test
        agree = self.result([chk(-30000, 10000, 38), chk(-5, 10000, 40)], [row(cyc=40), row(cyc=40)], fixture='md-prefetch')
        self.assertEqual(selftest.cause_checks(agree), [])
        wrong = self.result([chk(-5, 10000, 40)], [row(cyc=42)], fixture='md-prefetch')
        self.assertTrue(selftest.cause_checks(wrong))


class RecordedFamiliesTests(unittest.TestCase):
    def test_every_family_names_a_known_fixture_and_kind_and_has_a_written_reason(self):
        seen = set()
        for family in selftest.FAMILIES:
            self.assertIn(family.fixture, selftest.FIXTURES)
            self.assertIn(family.kind, selftest.KINDS)
            self.assertGreater(family.count, 0)
            self.assertGreater(len(family.reason), 60, family.key)
            self.assertGreater(len(family.basis), 10, family.key)
            self.assertTrue(callable(family.applies))
            seen.add((family.key, family.name))
        self.assertEqual(len(seen), len(selftest.FAMILIES))

    def test_the_recorded_counts_are_the_ones_the_run_prints(self):
        self.assertEqual(sum(f.count for f in selftest.FAMILIES), 336)
        self.assertEqual(len(selftest.FAMILIES), 18)

    def test_the_harness_source_is_where_the_build_expects_it(self):
        source = ROOT / 'native' / 'amiga_machine' / 'amiga_vector_checks.cpp'
        self.assertTrue(source.is_file())
        text = source.read_text(encoding='utf-8')
        self.assertIn('rr_moira_native', text)           # the hook the native steps run through
        self.assertIn('--opcode-map', text)              # the table the generator names Moira's handlers from


class WorkspaceTests(unittest.TestCase):
    def test_the_workspace_is_the_tree_unless_named(self):
        self.assertEqual(selftest.workspace_of(['a'])[1], ['a'])
        folder, rest = selftest.workspace_of(['--workspace', str(ROOT), 'md-prefetch'])
        self.assertEqual((folder, rest), (ROOT.resolve(), ['md-prefetch']))
        self.assertEqual(selftest.work_dir(ROOT), ROOT / '.build' / 'amiga-vectors')


if __name__ == '__main__':
    unittest.main()
