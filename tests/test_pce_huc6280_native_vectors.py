"""The native tier of the HuC6280 vector check (tools/pce_huc6280_native_vector_selftest.py): selection, grouping, case files and
judgement, on synthetic vectors and rows. No network, no compiler, no engine checkout."""
import importlib.util
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))

SPEC = importlib.util.spec_from_file_location('pce_huc6280_native_vector_selftest', TOOLS / 'pce_huc6280_native_vector_selftest.py')
selftest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selftest)

NATIVE_SOURCE = Path(__file__).resolve().parents[1] / 'native' / 'pce_huc6280_native_checks.cpp'


class FakeIsa:
    """Just enough of the engine's decoder: opcode A9 is a 2-byte immediate load, D0 a 2-byte branch, A5 a 2-byte zero-page one."""
    NATIVE = {0xA9, 0xD0, 0xA5, 0x03}

    @staticmethod
    def decode(read, pc, mpr):
        pc &= 0xFFFF
        opcode = read(pc)
        size = 1 if opcode == 0x03 else 2
        data = tuple(read((pc + offset) & 0xFFFF) for offset in range(size))
        target = None
        if opcode == 0xD0:
            offset = data[1] - 256 if data[1] > 127 else data[1]
            target = (pc + 2 + offset) & 0xFFFF
        return SimpleNamespace(data=data, next_pc=(pc + size) & 0xFFFF, target=target)


def state(pc=0x2000, mpr=(1, 2, 3, 4, 5, 6, 7, 8), ram=()):
    return {'a': 1, 'x': 2, 'y': 3, 's': 4, 'p': 0x22, 'pc': pc, 'mpr': tuple(mpr), 'ram': list(ram)}


def vector(opcode=0xA9, pc=0x2000, mpr=(1, 2, 3, 4, 5, 6, 7, 8), recorded=4, final_mpr=None, ram=None):
    """LDA #$55 at logical pc, whose bytes sit in the page the mapping gives to that window."""
    page = mpr[pc >> 13]
    base = (page << 13) | (pc & 0x1FFF)
    cells = [(base, opcode), (base + 1, 0x55)] if ram is None else ram
    return {'name': f'{opcode:02X}_#0', 'opcode': opcode, 'init': state(pc, mpr, cells),
            'final': state(pc + 2, final_mpr or mpr, cells), 'cycles': 2, 'recorded': recorded}


class PinTests(unittest.TestCase):
    def test_the_known_differences_are_the_interpreters_own(self):
        for opcode, known in selftest.KNOWN.items():
            self.assertIn(opcode, selftest.interpreter.KNOWN)
            self.assertEqual(selftest.interpreter.KNOWN[opcode]['reason'], known['reason'])
            self.assertTrue(set(known) - {'reason'}, opcode)
            self.assertLessEqual(max(value for key, value in known.items() if key != 'reason'), selftest.PER_OPCODE)
        self.assertNotIn('43', selftest.KNOWN)            # TMA is left to the interpreter tier

    def test_the_selection_adds_up(self):
        selection = selftest.EXPECTED_SELECTION
        self.assertEqual(256, selection['native_opcodes'] + selection['reserved_opcodes_skipped'])
        self.assertEqual(len(selftest.interpreter.REFUSED), selection['reserved_opcodes_skipped'])
        self.assertEqual(set(selftest.REASONS), set(selection['excluded']))
        self.assertEqual(selftest.EXPECTED['cases'], selection['read'] - sum(selection['excluded'].values()))
        self.assertEqual(5000, selection['excluded'][selftest.REASONS[0]])       # TAM and TMA: 2 opcodes, all their vectors
        self.assertEqual(selftest.EXPECTED_OPCODES, 256 - len(selftest.interpreter.REFUSED) - 3)

    def test_the_totals_add_up(self):
        expected = selftest.EXPECTED
        self.assertEqual(expected['cases'], expected['executed'] + expected['not_executed'])
        self.assertEqual(0, expected['not_executed'])
        self.assertEqual(0, expected['native_vs_interpreter_different'])
        # The pinned differences are flags alone or cycles alone, never both on one case.
        self.assertEqual(expected['executed'] - expected['flags'], expected['state_equal'])
        self.assertEqual(expected['executed'] - expected['flags'] - expected['cycles_different'], expected['both_equal'])
        self.assertEqual(expected['cases'] - sum(selftest.EXPECTED_SHORT.values()),
                         selftest.PER_OPCODE * (selftest.EXPECTED_OPCODES - len(selftest.EXPECTED_SHORT)))
        for opcode, known in selftest.KNOWN.items():
            self.assertNotIn(opcode, selftest.EXPECTED_SHORT)
        self.assertEqual(sum(value for known in selftest.KNOWN.values() for key, value in known.items() if key == 'flags'),
                         expected['flags'])
        self.assertEqual(sum(value for known in selftest.KNOWN.values() for key, value in known.items() if key == 'cycles'),
                         expected['cycles_different'])

    def test_the_modules_are_pinned_and_capped(self):
        self.assertGreaterEqual(selftest.EXPECTED_MODULES * selftest.MODULE_SITES, selftest.EXPECTED['cases'])
        self.assertEqual(40, selftest.PER_OPCODE)
        self.assertEqual(tuple(range(0x20, 0x28)), selftest.CANONICAL)

    def test_the_native_source_is_the_one_the_tool_builds(self):
        self.assertTrue(NATIVE_SOURCE.is_file())
        self.assertIn('native/pce_huc6280_native_checks.cpp', (TOOLS / 'pce_huc6280_native_vector_selftest.py').read_text(encoding='utf-8'))
        text = NATIVE_SOURCE.read_text(encoding='utf-8')
        self.assertIn('generated_step', text)
        self.assertIn('interpret_step', text)


class CorpusReadingTests(unittest.TestCase):
    def pack_state(self, s):
        data = struct.pack('<i5BH8Bi', 0, s['a'], s['x'], s['y'], s['s'], s['p'], s['pc'], *s['mpr'], len(s['ram']))
        return data + b''.join(struct.pack('<IB', address, value) for address, value in s['ram'])

    def test_a_file_is_read_back_vector_by_vector(self):
        first, second = vector(), vector(opcode=0xD0, pc=0x4000)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'a9.json.bin'
            payload = struct.pack('<I', 2)
            for item in (first, second):
                payload += struct.pack('<i', 0) + item['name'].encode().ljust(50, b'\0') + struct.pack('<I', item['opcode'])
                payload += self.pack_state(item['init']) + self.pack_state(item['final'])
                payload += struct.pack('<II', item['cycles'], item['recorded']) + b'\x01\x00\x00\x00' * item['recorded']
            path.write_bytes(payload)
            read = list(selftest.vectors(path))
        self.assertEqual([first, second], read)


class SelectionTests(unittest.TestCase):
    def test_a_vector_moves_to_the_canonical_mapping(self):
        case, reason = selftest.canonical_case(vector(), FakeIsa)
        self.assertIsNone(reason)
        self.assertEqual(selftest.CANONICAL, case['init']['mpr'])
        # logical 0x2000 is window 1 and lands in canonical page 0x21
        self.assertEqual({(0x21 << 13): 0xA9, (0x21 << 13) + 1: 0x55}, case['site'])
        self.assertEqual({(0x21 << 13): 0xA9, (0x21 << 13) + 1: 0x55}, dict(case['init']['ram']))
        self.assertEqual(2, case['length'])

    def test_the_mapping_is_kept_by_window_not_by_page(self):
        case, _ = selftest.canonical_case(vector(pc=0x6000, mpr=(0xF8, 0x80, 9, 8, 7, 6, 5, 4)), FakeIsa)
        self.assertEqual({(0x23 << 13), (0x23 << 13) + 1}, set(case['site']))

    def test_each_reason_for_leaving_a_vector_out(self):
        for item, reason in ((vector(opcode=0x43), selftest.REASONS[0]),
                             (vector(final_mpr=(9, 2, 3, 4, 5, 6, 7, 8)), selftest.REASONS[0]),
                             (vector(recorded=selftest.CORPUS_CAP), selftest.REASONS[1]),
                             (vector(mpr=(1, 1, 3, 4, 5, 6, 7, 8)), selftest.REASONS[2]),
                             (vector(ram=[(0x7FFFF, 1)]), selftest.REASONS[3]),
                             (vector(ram=[(1 << 13, 0xA9)]), selftest.REASONS[3])):
            case, why = selftest.canonical_case(item, FakeIsa)
            self.assertIsNone(case)
            self.assertEqual(reason, why)

    def test_a_branch_into_its_own_bytes_is_not_a_site(self):
        base = 3 << 13                       # logical 0x4000 is window 2, page 3
        item = vector(opcode=0xD0, ram=[(base, 0xD0), (base + 1, 0xFF)], pc=0x4000)
        self.assertEqual(selftest.REASONS[3], selftest.canonical_case(item, FakeIsa)[1])

    def test_the_first_vectors_are_kept_and_the_rest_counted(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(selftest, 'vectors') as source, mock.patch.object(selftest, 'PER_OPCODE', 2):
            items = [vector(), vector(opcode=0x43), vector(recorded=500), vector(), vector(), vector()]
            source.side_effect = lambda path: iter(items if path.name == 'a9.json.bin' else [])
            isa = SimpleNamespace(NATIVE={0xA9}, decode=FakeIsa.decode)
            cases, counts = selftest.select(Path(folder), isa)
        self.assertEqual(2, len(cases))
        self.assertEqual(1, counts['native_opcodes'])
        self.assertEqual(255, counts['reserved_opcodes_skipped'])
        self.assertEqual({selftest.REASONS[0]: 1, selftest.REASONS[1]: 1, selftest.REASONS[2]: 0, selftest.REASONS[3]: 0},
                         counts['excluded'])
        self.assertEqual(4, counts['read'])


class GroupingTests(unittest.TestCase):
    def case(self, pc, opcode=0xA9):
        item, _ = selftest.canonical_case(vector(opcode=opcode, pc=pc), FakeIsa)
        return item

    def test_sites_that_overlap_or_flow_into_each_other_go_to_different_modules(self):
        modules = selftest.group([self.case(0x2000), self.case(0x2001), self.case(0x2002), self.case(0x4000)])
        self.assertEqual([2, 1, 1], [len(items) for items in modules])
        for items in modules:
            spans = [set(range(case['init']['pc'], case['init']['pc'] + case['length'])) for case in items]
            self.assertFalse(any(a & b for index, a in enumerate(spans) for b in spans[index + 1:]))

    def test_the_cap_opens_a_new_module(self):
        with mock.patch.object(selftest, 'MODULE_SITES', 2):
            modules = selftest.group([self.case(0x2000 + 0x10 * index) for index in range(5)])
        self.assertEqual([2, 2, 1], [len(items) for items in modules])

    def test_the_grouping_is_deterministic(self):
        cases = [self.case(0x2000 + 3 * index) for index in range(20)]
        first = [[case['name'] + str(case['init']['pc']) for case in items] for items in selftest.group(cases)]
        second = [[case['name'] + str(case['init']['pc']) for case in items] for items in selftest.group(list(cases))]
        self.assertEqual(first, second)

    def test_the_cases_file_has_one_line_per_vector_and_its_counts_agree(self):
        item = self.case(0x2000)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cases.txt'
            selftest.write_cases(path, [item, self.case(0x4000)])
            data = path.read_bytes()
        self.assertNotIn(b'\r', data)
        lines = data.decode('ascii').splitlines()
        self.assertEqual(2, len(lines))
        fields = lines[0].split()
        self.assertEqual('A9_#0', fields[0])
        self.assertEqual('169', fields[1])                 # the opcode
        sites = int(fields[15])
        self.assertEqual(2, sites)
        before = int(fields[16 + sites])
        after = int(fields[17 + sites + 2 * before])
        self.assertEqual(len(fields), 18 + sites + 2 * before + 2 * after)


def row(opcode, **extra):
    """An opcode of 40 cases, all executed and equal to the vectors and to the interpreter."""
    base = {'opcode': opcode, 'cases': 40, 'executed': 40, 'not_executed': 0, 'state_equal': 40, 'both_equal': 40,
            **dict.fromkeys(selftest.CLASSES, 0), 'cycles_different': 0, 'interpreter_not_executed': 0,
            'interpreter': {**dict.fromkeys(selftest.CLASSES, 0), 'cycles_different': 0},
            'native_vs_interpreter_different': 0, 'first_difference': ''}
    base.update(extra)
    return base


def known_row(opcode):
    known = {('cycles_different' if key == 'cycles' else key): number
             for key, number in selftest.KNOWN[opcode].items() if key != 'reason'}
    both = 40 - sum(known.values())
    state = 40 - sum(number for key, number in known.items() if key != 'cycles_different')
    return row(opcode, both_equal=both, state_equal=state, interpreter=dict(row(opcode)['interpreter'], **known), **known)


class JudgementTests(unittest.TestCase):
    def clean(self):
        """The rows of the pinned selection: the known differences in, every other opcode equal."""
        opcodes = set(selftest.KNOWN) | set(selftest.EXPECTED_SHORT)
        value = 0
        while len(opcodes) < selftest.EXPECTED_OPCODES:
            code = f'{value:02X}'
            if code not in selftest.interpreter.REFUSED and code not in ('43', '53'):
                opcodes.add(code)
            value += 1
        rows = []
        for opcode in sorted(opcodes):
            item = known_row(opcode) if opcode in selftest.KNOWN else row(opcode)
            if opcode in selftest.EXPECTED_SHORT:
                count = selftest.EXPECTED_SHORT[opcode]
                item.update(cases=count, executed=count, state_equal=count, both_equal=count)
            rows.append(item)
        return rows

    def judge(self, rows, selection=None, modules=None):
        totals = {key: sum(item[key] for item in rows) for key in selftest.EXPECTED}
        with mock.patch.dict(selftest.EXPECTED, totals):
            return selftest.judge(rows, selftest.EXPECTED_SELECTION if selection is None else selection,
                                  selftest.EXPECTED_MODULES if modules is None else modules)

    def test_the_pinned_differences_alone_are_explained(self):
        _, unexplained = self.judge(self.clean())
        self.assertEqual([], unexplained)

    def test_the_pinned_totals_are_the_rows_of_the_pinned_selection(self):
        totals, unexplained = selftest.judge(self.clean(), selftest.EXPECTED_SELECTION, selftest.EXPECTED_MODULES)
        self.assertEqual(selftest.EXPECTED, totals)
        self.assertEqual([], unexplained)

    def test_a_new_difference_is_not_explained(self):
        rows = self.clean()
        index = next(i for i, item in enumerate(rows) if item['opcode'] not in selftest.KNOWN)
        rows[index] = row(rows[index]['opcode'], flags=1, both_equal=39, state_equal=39,
                          interpreter=dict(row('00')['interpreter'], flags=1))
        _, unexplained = self.judge(rows)
        self.assertTrue(any(message.startswith(rows[index]['opcode'] + ':') for message in unexplained), unexplained)

    def test_a_changed_count_on_a_known_difference_is_not_explained(self):
        rows = self.clean()
        index = next(i for i, item in enumerate(rows) if item['opcode'] == '04')
        rows[index] = row('04', flags=2, both_equal=38, state_equal=38, interpreter=dict(row('04')['interpreter'], flags=2))
        _, unexplained = self.judge(rows)
        self.assertTrue(any(message.startswith('04:') for message in unexplained), unexplained)

    def test_a_known_difference_that_disappears_is_reported(self):
        rows = self.clean()
        index = next(i for i, item in enumerate(rows) if item['opcode'] == '0C')
        rows[index] = row('0C')
        _, unexplained = self.judge(rows)
        self.assertIn('0C: known difference not seen', unexplained)

    def test_a_difference_from_the_interpreter_is_not_explained(self):
        rows = self.clean()
        rows[0] = dict(rows[0], native_vs_interpreter_different=1, tier_fields={'ticks': 1})
        _, unexplained = self.judge(rows)
        self.assertTrue(any('differ from the interpreter' in message for message in unexplained), unexplained)

    def test_a_native_difference_the_interpreter_does_not_have_is_not_explained(self):
        rows = self.clean()
        index = next(i for i, item in enumerate(rows) if item['opcode'] == '04')
        rows[index] = dict(rows[index], interpreter=dict(row('04')['interpreter']))
        _, unexplained = self.judge(rows)
        self.assertTrue(any(message.startswith('04:') and 'interpreter' in message for message in unexplained), unexplained)

    def test_a_guard_miss_a_refusal_or_a_fault_is_never_counted_as_equal(self):
        rows = self.clean()
        rows[0] = dict(rows[0], executed=39, not_executed=1, state_equal=39, both_equal=39, stops={'miss': 1})
        _, unexplained = self.judge(rows)
        self.assertTrue(any(message.startswith(rows[0]['opcode'] + ': not executed') for message in unexplained), unexplained)

    def test_a_changed_selection_or_module_count_is_reported(self):
        _, unexplained = self.judge(self.clean(), dict(selftest.EXPECTED_SELECTION, read=selftest.EXPECTED_SELECTION['read'] + 1))
        self.assertTrue(any(message.startswith('selection') for message in unexplained), unexplained)
        _, unexplained = self.judge(self.clean(), modules=selftest.EXPECTED_MODULES + 1)
        self.assertTrue(any('modules' in message for message in unexplained), unexplained)

    def test_a_missing_opcode_or_a_short_opcode_is_reported(self):
        _, unexplained = self.judge(self.clean()[:-1])
        self.assertTrue(any('opcodes with cases' in message for message in unexplained), unexplained)
        rows = self.clean()
        index = next(i for i, item in enumerate(rows) if item['opcode'] not in selftest.EXPECTED_SHORT and item['opcode'] not in selftest.KNOWN)
        rows[index] = row(rows[index]['opcode'], cases=39, executed=39, state_equal=39, both_equal=39)
        _, unexplained = self.judge(rows)
        self.assertTrue(any('fewer than' in message for message in unexplained), unexplained)

    def test_the_case_lines_of_the_checks_are_added_up_per_opcode(self):
        def line(opcode, name, native='executed', n_vs_v=(), i_vs_v=(), n_vs_i=()):
            return {'vector': name, 'opcode': opcode, 'native': native, 'interpreter': 'executed',
                    'native_vs_vector': list(n_vs_v) if native == 'executed' else None, 'interpreter_vs_vector': list(i_vs_v),
                    'native_vs_interpreter': list(n_vs_i) if native == 'executed' else None}
        rows = selftest.aggregate([
            line('03', '03_#0', n_vs_v=['cycles'], i_vs_v=['cycles']), line('03', '03_#1'),
            line('04', '04_#0', n_vs_v=['flags'], i_vs_v=['flags']), line('04', '04_#1', native='miss'),
            line('04', '04_#2', n_vs_i=['ticks'])])
        self.assertEqual(['03', '04'], [item['opcode'] for item in rows])
        three, four = rows
        self.assertEqual((2, 2, 1, 2, 1, 0), (three['cases'], three['executed'], three['both_equal'], three['state_equal'],
                                              three['cycles_different'], three['not_executed']))
        self.assertEqual({'cycles_different': 1}, {key: value for key, value in three['interpreter'].items() if value})
        self.assertEqual((3, 2, 1, 1, 1), (four['cases'], four['executed'], four['not_executed'], four['flags'],
                                           four['native_vs_interpreter_different']))
        self.assertEqual({'miss': 1}, four['stops'])
        self.assertEqual({'ticks': 1}, four['tier_fields'])
        self.assertEqual('04_#0', four['first_difference'])


if __name__ == '__main__':
    unittest.main()
