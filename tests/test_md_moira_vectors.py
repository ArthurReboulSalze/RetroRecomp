"""The ROM-free, compiler-free parts of tools/megadrive_moira_vectors.py (Mega Drive gate G10, slice 1): the choosing of the states, the
conversion of what Moira did into a SingleStepTests-format vector, the reading of the replay's report and the sorting of the differences into
families. The run itself builds vAmiga's Core, the maker and the Mega Drive's steps and takes minutes: `python -B tools/megadrive_moira_vectors.py`.
Every record below is authored here, none comes from a run of Moira."""
import importlib.util
import inspect
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load('megadrive_moira_vectors')
replay = load('megadrive_prefetch_selftest')


def sext(value, bits):
    return tool.to_signed(value, bits)


def operand_of(form, state):
    """The operand's address as the 68000 computes it from the instruction words and the registers (an independent decoding of the mode)."""
    words, mode = state['words'], form['mode']
    start = 1 + (2 if form['size'] == 'l' and form['op'] in tool.IMMEDIATE else 1 if form['op'] in tool.IMMEDIATE else 0)
    ext = words[start:]
    number = words[0] & 7
    register = state[tool.stack_key(state)] if number == 7 else state[f'a{number}']
    size = tool.SIZE_BYTES[form['size']]
    if mode == '(An)' or mode == '(An)+':
        return register & 0xffffff
    if mode == '-(An)':
        return (register - (2 if number == 7 and size == 1 else size)) & 0xffffff
    if mode == '(d16,An)':
        return (register + sext(ext[0], 16)) & 0xffffff
    if mode == '(d8,An,Xn)':
        word = ext[0]
        index = state[('a' if word >> 15 else 'd') + str(word >> 12 & 7)]
        index = sext(index, 32) if word >> 11 & 1 else sext(index, 16)
        return (register + sext(word, 8) + index) & 0xffffff
    if mode == 'abs.W':
        return sext(ext[0], 16) & 0xffffff
    return (ext[0] << 16 | ext[1]) & 0xffffff


class StateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states = tool.make_states()

    def test_the_forms_and_their_counts(self):
        forms = tool.form_list()
        self.assertEqual(len(forms), 88)
        self.assertEqual(len({form['group'] for form in forms}), 88)
        roles = {role: sum(form['count'] for form in forms if form['role'] == role) for role in ('missing form', 'control', 'decimal')}
        self.assertEqual(roles, {'missing form': 56 * 48, 'control': 20 * 24, 'decimal': 12 * 48})
        self.assertEqual(len(self.states), 3744)
        self.assertEqual({(f['op'], f['size']) for f in forms if f['role'] == 'missing form'},
                         {(op, 'l') for op in ('ADDI', 'SUBI', 'ANDI', 'ORI', 'EORI')} | {('CMPI', 'b'), ('CMPI', 'w'), ('CMPI', 'l')})

    def test_the_same_seed_gives_the_same_states_and_another_does_not(self):
        again = tool.make_states()
        self.assertEqual([state['words'] for _, state in again[:200]], [state['words'] for _, state in self.states[:200]])
        self.assertEqual([state['seed'] for _, state in again], [state['seed'] for _, state in self.states])
        other = tool.make_states(seed=tool.SEED + 1)
        self.assertNotEqual([state['seed'] for _, state in other[:50]], [state['seed'] for _, state in self.states[:50]])

    def test_every_operand_is_where_the_mode_says_and_where_the_state_put_its_bytes(self):
        checked = 0
        for form, state in self.states:
            if 'address' not in state['meta']:
                continue
            checked += 1
            address = operand_of(form, state)
            self.assertEqual(address, state['meta']['address'], form['group'])
            self.assertIn(address, state['over'])
            if form['size'] != 'b':
                self.assertEqual(address & 1, 0, form['group'])
        self.assertEqual(checked, 3744 - 48 * 5)      # all but five forms: ABCD and SBCD in both forms, NBCD Dn

    def test_the_instruction_words_are_the_documented_encodings(self):
        seen = {}
        for form, state in self.states:
            seen.setdefault(form['group'], state['words'][0])
        self.assertEqual(seen['ADDI.l (An)'] >> 6, 0x0600 >> 6 | 2)
        self.assertEqual(seen['CMPI.b abs.L'], 0x0C00 | 0 << 6 | 7 << 3 | 1)
        self.assertEqual(seen['EORI.l -(An)'] & 0xfff8, 0x0A80 | 4 << 3)
        self.assertEqual(seen['NBCD Dn'] & 0xfff8, 0x4800)
        self.assertEqual(seen['ABCD -(Ay),-(Ax)'] & 0xf1f8, 0xC108)
        self.assertEqual(seen['SBCD Dy,Dx'] & 0xf1f8, 0x8100)

    def test_the_decimal_forms_mix_decimal_and_other_operands(self):
        decimal = [state['meta']['operands'] for form, state in self.states if form['op'] in tool.DECIMAL]
        valid = sum(all(tool.is_decimal(v) for v in operands) for operands in decimal)
        self.assertTrue(0.3 < valid / len(decimal) < 0.8)

    def test_code_is_apart_from_data_and_inside_the_replay_image(self):
        pcs = [state['pc'] for _, state in self.states]
        self.assertEqual(len(set(pcs)), len(pcs))
        self.assertTrue(all(b - a == 0x100 for a, b in zip(pcs, pcs[1:])))
        self.assertLess(max(pcs) + 0x100, 0x400000)
        for form, state in self.states:
            for address in state['over']:
                self.assertFalse(min(pcs) <= address < max(pcs) + 0x100, form['group'])

    def test_the_maker_input_and_output_round_trip(self):
        form, state = self.states[0]
        line = tool.input_line(7, state).split()
        self.assertEqual(int(line[0]), 7)
        self.assertEqual(len(line), 1 + 19 + 1 + len(state['words']) + 1 + 1 + 2 * len(state['over']))
        out = tool.parse_output_line('7 28 ' + ' '.join(str(n) for n in range(21)) + ' 2 0 4 1048580 2 1111 1 6 1048582 2 2222 3 100 5 6 101 7 8 102 9 10')
        self.assertEqual((out['index'], out['clock'], out['regs']['d0'], out['regs']['pc'], out['regs']['irc']), (7, 28, 0, 18, 20))
        self.assertEqual(out['accesses'], [(0, 4, 1048580, 2, 1111), (1, 6, 1048582, 2, 2222)])
        self.assertEqual(out['bytes'], [(100, 5, 6), (101, 7, 8), (102, 9, 10)])


class VectorTests(unittest.TestCase):
    def test_the_bus_cycles_of_a_vector(self):
        # a word read at once, an idle gap, an even byte write, an idle gap, an odd byte read, a trailing idle period
        found = tool.transactions([(0, 2, 0x1004, 2, 0x1234), (1, 12, 0x2000, 1, 0x56), (0, 18, 0x2001, 1, 0x78)], 30, True, range(0x1000, 0x1008))
        self.assertEqual(found, [['r', 4, 6, 0x1004, '.w', 0x1234, 1, 1], ['n', 6], ['w', 4, 5, 0x2000, '.b', 0x5600, 1, 0], ['n', 2],
                                 ['r', 4, 5, 0x2000, '.b', 0x78, 0, 1], ['n', 10]])
        self.assertEqual(sum(item[1] for item in found), 30)

    def test_two_cycles_cannot_overlap(self):
        with self.assertRaises(ValueError):
            tool.transactions([(0, 2, 0x1000, 2, 0), (0, 4, 0x1002, 2, 0)], 12, False, range(0))

    def authored(self):
        form = {'op': 'ORI', 'size': 'w', 'mode': '(An)', 'role': 'control', 'group': 'ORI.w (An)'}
        state = dict.fromkeys(tool.REGS, 0) | {'sr': 0x2700, 'pc': 0x100000, 'ssp': 0x300000, 'words': [0x0050, 0x00ff, 0x4e71, 0x4e71], 'length': 2,
                                               'over': {}, 'seed': 1, 'meta': {}}
        regs = dict.fromkeys(tool.REGS, 0) | {'ird': 0x4e71, 'irc': 0x4e71, 'sr': 0x2708, 'pc': 0x100004, 'ssp': 0x300000}
        run = {'index': 0, 'clock': 16, 'regs': regs, 'accesses': [(0, 4, 0x100004, 2, 0x4e71), (0, 10, 0x200000, 2, 7), (1, 14, 0x200000, 2, 0xff)],
               'bytes': [(0x100000, 0x00, 0x00), (0x200001, 7, 0xff), (0x200000, 0, 0)]}
        return form, state, run

    def test_a_vector_has_the_architectural_pc_plus_the_queue_and_sorted_memory(self):
        form, state, run = self.authored()
        test = tool.vector(12, form, state, run)
        self.assertEqual(test['group'], '00012')
        self.assertEqual((test['initial']['pc'], test['final']['pc']), (0x100004, 0x100008))
        self.assertEqual((test['initial']['prefetch'], test['final']['prefetch']), ([0x0050, 0x00ff], [0x4e71, 0x4e71]))
        self.assertEqual(test['initial']['ram'], [[0x100000, 0], [0x200000, 0], [0x200001, 7]])
        self.assertEqual(test['final']['ram'], [[0x100000, 0], [0x200000, 0], [0x200001, 0xff]])
        self.assertEqual(test['length'], 16)
        self.assertNotIn('sr_mask', test)
        self.assertEqual(test['final']['sr'], 0x2708)
        for key in tool.REGS[:18]:
            self.assertIn(key, test['initial'])

    def test_a_decimal_vector_masks_v(self):
        form, state, run = self.authored()
        form = dict(form, op='ABCD')
        self.assertEqual(tool.vector(0, form, state, run)['sr_mask'], 0xfffd)

    def test_a_run_that_did_not_go_straight_on_is_refused(self):
        form, state, run = self.authored()
        run['regs']['pc'] = 0x000010
        with self.assertRaises(ValueError):
            tool.vector(0, form, state, run)


class ReportTests(unittest.TestCase):
    TEXT = '\n'.join([
        'FAIL 00003: ADDI.l -(An) native register[17] expected=00002708 actual=00002700',
        'FAIL 00003: ADDI.l -(An) native CPU cycles expected=00000020 actual=00000022',
        '  vector: r@4:100004=1234 w@20:200000=0001',
        '  actual: r@4:100004=1234 w@20:200000=0001',
        'FAIL 00009: ADDI.l (An) native bus[5].field[3] expected=00200000 actual=00200002',
        '  vector: r@4:100004=1234 w@24:200000=aaaa w@28:200002=bbbb',
        '  actual: r@4:100004=1234 w@24:200002=bbbb w@28:200000=aaaa',
        'FAIL 00009: ADDI.l (An) reference bus[5].field[3] expected=00200000 actual=00200002',
        '  vector: w@24:200000=aaaa w@28:200002=bbbb',
        '  actual: w@24:200002=bbbb w@28:200000=aaaa',
        'not a failure line'])

    def test_the_failing_fields_and_bus_lists_are_read(self):
        report = tool.parse_report(self.TEXT)
        self.assertEqual(sorted(report['native']), [3, 9])
        self.assertEqual(sorted(report['reference']), [9])
        self.assertEqual(report['native'][3]['fields'], [('register[17]', 0x2708, 0x2700), ('CPU cycles', 0x20, 0x22)])
        self.assertEqual(report['native'][9]['vector_tx'][1], ('w', 24, 0x200000, 0xaaaa))
        self.assertEqual(tool.clock_delta(report['native'][3]), 2)

    def test_categories(self):
        self.assertEqual([tool.category(name) for name in ('register[3]', 'register[17]', 'register[18]', 'memory[200000]', 'audio cycles', 'CPU cycles',
                                                           'queue word', 'queue PC/valid', 'transaction count', 'bus[2].field[1]', 'status')],
                         ['regs', 'sr', 'pc', 'memory', 'clocks', 'clocks', 'queue', 'queue', 'bus', 'bus', 'other'])


class FamilyTests(unittest.TestCase):
    META_LONG = {'group': 'ADDI.l (An)', 'op': 'ADDI', 'size': 'l', 'mode': '(An)', 'role': 'missing form'}

    def outcome(self, fields, vector_tx=None, actual_tx=None):
        return {'fields': fields, 'vector_tx': vector_tx, 'actual_tx': actual_tx}

    def test_the_two_writes_of_a_long_in_the_other_order_are_a_known_model_difference(self):
        moira = [('r', 4, 0x100004, 1), ('w', 24, 0x200000, 0xaaaa), ('w', 28, 0x200002, 0xbbbb)]
        ours = [('r', 4, 0x100004, 1), ('w', 24, 0x200002, 0xbbbb), ('w', 28, 0x200000, 0xaaaa)]
        verdict = tool.classify(self.outcome([('bus[1].field[3]', 0x200000, 0x200002)], moira, ours), self.META_LONG)
        self.assertEqual((verdict['families'], verdict['unexplained']), ({'long write order'}, set()))
        self.assertTrue(tool.swapped_long_writes(moira, ours))

    def test_other_bus_differences_are_not_that_family(self):
        moira = [('r', 4, 0x100004, 1), ('w', 24, 0x200000, 0xaaaa), ('w', 28, 0x200002, 0xbbbb)]
        for ours in ([('r', 4, 0x100004, 1), ('w', 24, 0x200002, 0xbbbb), ('w', 30, 0x200000, 0xaaaa)],           # a clock moved
                     [('r', 4, 0x100004, 1), ('w', 24, 0x200002, 0xbbbb), ('w', 28, 0x200000, 0xaaab)],           # another value
                     [('r', 4, 0x100004, 1), ('w', 24, 0x200000, 0xaaaa)],                                         # a cycle missing
                     [('r', 4, 0x100004, 1), ('r', 24, 0x200000, 0xaaaa), ('w', 28, 0x200002, 0xbbbb)]):           # a write became a read
            self.assertFalse(tool.swapped_long_writes(moira, ours))
            verdict = tool.classify(self.outcome([('bus[1].field[3]', 0, 0)], moira, ours), self.META_LONG)
            self.assertEqual(verdict['unexplained'], {'bus'})
        self.assertFalse(tool.swapped_long_writes(moira, moira))
        # the vector's two writes must be in Moira's order (ascending): the opposite is not the family
        self.assertFalse(tool.swapped_long_writes(list(reversed(moira[1:])), list(moira[1:])))

    def test_a_state_difference_with_a_swapped_write_is_not_excused(self):
        moira = [('w', 24, 0x200000, 0xaaaa), ('w', 28, 0x200002, 0xbbbb)]
        ours = [('w', 24, 0x200002, 0xbbbb), ('w', 28, 0x200000, 0xaaaa)]
        verdict = tool.classify(self.outcome([('memory[200000]', 1, 2), ('bus[0].field[3]', 0, 0)], moira, ours), self.META_LONG)
        self.assertEqual((verdict['families'], verdict['unexplained']), ({'long write order'}, {'memory'}))

    def test_the_same_cycles_at_other_clocks_are_the_idle_placement_lead(self):
        moira = [('r', 4, 0x100004, 1), ('r', 8, 0x100006, 2), ('r', 14, 0x200000, 3), ('w', 18, 0x200000, 4)]
        ours = [('r', 6, 0x100004, 1), ('r', 10, 0x100006, 2), ('r', 14, 0x200000, 3), ('w', 18, 0x200000, 4)]
        self.assertEqual(tool.bus_flags(moira, ours), ({'clock placement'}, [2, 2]))
        verdict = tool.classify(self.outcome([('bus[0].field[1]', 4, 6), ('bus[1].field[1]', 8, 10)], moira, ours), self.META_LONG)
        self.assertEqual((verdict['families'], verdict['unexplained'], verdict['shifts']), ({'idle clock placement'}, set(), [2, 2]))
        self.assertEqual(tool.FAMILIES['idle clock placement'].status, 'lead')
        # a clock that moved and a total that moved too stay two findings
        verdict = tool.classify(self.outcome([('bus[0].field[1]', 4, 6), ('CPU cycles', 20, 22)], moira, ours), self.META_LONG)
        self.assertEqual(verdict['families'], {'idle clock placement', 'clocks'})
        # both effects on one vector
        both = [('r', 4, 0x100004, 1), ('w', 8, 0x200000, 5), ('w', 12, 0x200002, 6)]
        ours = [('r', 6, 0x100004, 1), ('w', 8, 0x200002, 6), ('w', 12, 0x200000, 5)]
        self.assertEqual(tool.bus_flags(both, ours), ({'clock placement', 'long write order'}, [2]))

    def test_a_write_with_other_data_is_the_decimal_family_only_for_a_decimal_instruction_on_undefined_digits(self):
        moira = [('r', 4, 0x100004, 1), ('w', 8, 0x200000, 0x8b00)]
        ours = [('r', 4, 0x100004, 1), ('w', 8, 0x200000, 0x9b00)]
        self.assertEqual(tool.bus_flags(moira, ours), ({'write data'}, []))
        fields = [('memory[200000]', 0x8b, 0x9b), ('bus[1].field[4]', 0x8b00, 0x9b00)]
        meta = {'group': 'NBCD (An)', 'op': 'NBCD', 'size': 'b', 'mode': '(An)', 'role': 'decimal', 'operands': [0x0b]}
        verdict = tool.classify(self.outcome(fields, moira, ours), meta)
        self.assertEqual((verdict['families'], verdict['unexplained']), ({'undefined decimal digits'}, set()))
        verdict = tool.classify(self.outcome(fields, moira, ours), dict(meta, operands=[0x09]))
        self.assertEqual(verdict['unexplained'], {'memory', 'bus'})
        verdict = tool.classify(self.outcome(fields, moira, ours), dict(self.META_LONG))
        self.assertEqual(verdict['unexplained'], {'memory', 'bus'})

    def test_a_decimal_result_on_digits_that_are_not_decimal_is_expected_and_on_decimal_digits_is_not(self):
        meta = {'group': 'ABCD Dy,Dx', 'op': 'ABCD', 'size': 'b', 'mode': 'Dy,Dx', 'role': 'decimal', 'operands': [0x1a, 0x05]}
        verdict = tool.classify(self.outcome([('register[0]', 1, 2), ('register[17]', 0, 1)]), meta)
        self.assertEqual((verdict['families'], verdict['unexplained']), ({'undefined decimal digits'}, set()))
        verdict = tool.classify(self.outcome([('register[0]', 1, 2)]), dict(meta, operands=[0x19, 0x05]))
        self.assertEqual((verdict['families'], verdict['unexplained']), (set(), {'regs'}))
        verdict = tool.classify(self.outcome([('register[0]', 1, 2), ('bus[3].field[1]', 1, 2)]), meta)
        self.assertEqual(verdict['unexplained'], {'bus'})

    def test_a_clock_is_a_lead_and_a_missing_family_is_unexplained(self):
        verdict = tool.classify(self.outcome([('audio cycles', 20, 22), ('CPU cycles', 20, 22)]), self.META_LONG)
        self.assertEqual((verdict['families'], verdict['unexplained']), ({'clocks'}, set()))
        self.assertEqual(tool.FAMILIES['clocks'].status, 'lead')
        verdict = tool.classify(self.outcome([('register[2]', 1, 2)]), self.META_LONG)
        self.assertEqual((verdict['families'], verdict['unexplained']), (set(), {'regs'}))

    def test_the_per_form_counts(self):
        meta = [self.META_LONG, self.META_LONG, dict(self.META_LONG, group='CMPI.l (An)')]
        report = {'native': {1: self.outcome([('CPU cycles', 20, 22)]), 2: self.outcome([('register[1]', 0, 1)])}, 'reference': {}}
        rows = tool.evaluate(meta, [{'name': 'a'}, {'name': 'b'}, {'name': 'c'}], report)
        self.assertEqual((rows['ADDI.l (An)']['vectors'], rows['ADDI.l (An)']['whole']), (2, 1))
        self.assertEqual(rows['ADDI.l (An)']['clock_deltas'], {2: 1})
        self.assertEqual(rows['CMPI.l (An)']['unexplained'], {'regs': 1})


class ExhaustiveTests(unittest.TestCase):
    def row(self, **combos):
        return {'states': 10, 'valid_states': 4, 'upper_bits_changed': 0, 'queue_or_pc_wrong': 0, 'status_wrong': 0, 'wrong_path': 0, 'combos': combos}

    def test_the_counts_are_split_by_operands_and_by_what_differs(self):
        row = self.row(**{'valid:0': 3, 'valid:32': 1, 'undefined:0': 2, 'undefined:32': 1, 'undefined:1': 2, 'undefined:5': 1})
        self.assertEqual(tool.split_combos(row), {'valid equal': 3, 'valid V only': 1, 'valid outside V': 0,
                                                  'undefined equal': 2, 'undefined V only': 1, 'undefined outside V': 3})
        self.assertEqual(tool.exhaustive_problems({'abcd': {'native': row, 'reference': row}}), [])
        self.assertIn('abcd native: 1 states', tool.exhaustive_problems({'abcd': {
            'native': self.row(**{'valid:2': 1}), 'reference': self.row(**{'valid:2': 1})}})[0][:40])
        self.assertTrue(tool.exhaustive_problems({'sbcd': {'native': row, 'reference': self.row(**{'valid:0': 4})}}))
        broken = dict(row, upper_bits_changed=1)
        self.assertEqual(len(tool.exhaustive_problems({'nbcd': {'native': broken, 'reference': row}})), 1)
        self.assertEqual(len(tool.summarise_exhaustive({'abcd': {'native': row, 'reference': row}})), 2)

    def test_the_instruction_words_are_register_forms(self):
        self.assertEqual({kind: word & 0xf1f8 for kind, word in tool.EXHAUSTIVE.items() if kind != 'nbcd'}, {'abcd': 0xC100, 'sbcd': 0x8100})
        self.assertEqual(tool.EXHAUSTIVE['nbcd'], 0x4800)
        self.assertEqual(len(set(tool.EXHAUSTIVE_PC.values())), 3)


class FixtureTests(unittest.TestCase):
    def test_a_vector_of_the_groups_fixture_is_read_against_moiras_run(self):
        regs = dict.fromkeys(tool.REGS, 0)
        state = regs | {'sr': 0x2700, 'pc': 0x1000}
        test = {'group': 'NBCD', 'name': '000 NBCD D0 4800', 'length': 6, 'sr_mask': 0xfffd,
                'initial': state | {'pc': 0x1004, 'prefetch': [0x4800, 0x4e71], 'ram': [[0x1000, 0x48]]},
                'final': state | {'d0': 5, 'sr': 0x2710, 'pc': 0x1006, 'prefetch': [0x4e71, 0x4e71], 'ram': [[0x1000, 0x48]]},
                'transactions': [['r', 4, 6, 0x1004, '.w', 0x4e71, 1, 1], ['n', 2]]}
        run = {'clock': 6, 'regs': regs | {'d0': 5, 'sr': 0x2712, 'pc': 0x1002, 'ird': 0x4e71, 'irc': 0x4e71},
               'accesses': [(0, 2, 0x1004, 2, 0x4e71)], 'bytes': [(0x1000, 0x48, 0x48)]}
        self.assertEqual(tool.moira_against_vector(test, run), [])         # V is masked
        self.assertEqual(tool.moira_against_vector(test, dict(run, clock=8, accesses=[(0, 4, 0x1004, 2, 0x4e71)])), ['clocks', 'bus'])
        self.assertEqual(tool.moira_against_vector(test, dict(run, regs=dict(run['regs'], d0=6))), ['registers'])
        self.assertEqual(tool.moira_against_vector(test, dict(run, regs=dict(run['regs'], irc=0))), ['pc or queue'])
        self.assertEqual(tool.moira_against_vector(test, dict(run, bytes=[(0x1000, 0x48, 0x49)])), ['memory'])

    def test_the_failing_vectors_of_a_fixture_with_its_own_names_are_read(self):
        text = '\n'.join(['FAIL NBCD: 008 NBCD D2 4802 native register[2] expected=00000001 actual=00000002',
                          'FAIL ABCD: 006 ABCD -(A1), -(A7) cf09 reference memory[1] expected=1 actual=2'])
        self.assertEqual(tool.failing_vectors(text), {('NBCD', '008 NBCD D2 4802')})
        self.assertEqual(tool.failing_vectors(text, 'reference'), {('ABCD', '006 ABCD -(A1), -(A7) cf09')})

    def test_the_forms_seen_in_the_fixtures_today(self):
        found = tool.existing_vectors()
        self.assertEqual(found['ADDI.l -(An)'], 0)
        self.assertEqual(found['CMPI.b -(An)'], 0)
        self.assertGreater(found['NBCD Dn'], 0)
        self.assertGreater(found['ABCD -(Ay),-(Ax)'], 0)


class HarnessTests(unittest.TestCase):
    def test_the_all_fields_mode_applies_to_the_harness_exactly_once_and_changes_nothing_without_the_variable(self):
        text = (ROOT / 'native' / 'md_prefetch_checks.c').read_text(encoding='utf-8')
        patched = tool.all_fields_harness(text)
        self.assertIn('RR_MD_COLLECT_ALL', patched)
        self.assertNotIn('RR_MD_COLLECT_ALL', text)
        self.assertEqual(patched.count('case_flagged = 0;'), 1)
        with self.assertRaises(ValueError):
            tool.all_fields_harness(patched)

    def test_the_replay_builder_keeps_its_old_calls(self):
        parameters = inspect.signature(replay.build).parameters
        self.assertEqual(list(parameters), ['fixture_name', 'folder', 'harness'])
        self.assertEqual([parameters[name].default for name in parameters], ['md-prefetch', None, None])


if __name__ == '__main__':
    unittest.main()
