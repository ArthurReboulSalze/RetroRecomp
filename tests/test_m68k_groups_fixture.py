"""The m68k-groups vector fixture and the sorting of its replay (gate G10): no compiler, no ROM.

The replay itself builds C and takes a few minutes: `python -B tools/megadrive_groups_selftest.py` (BUILDING.md)."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load('build_m68000_groups_fixture')
selftest = load('megadrive_groups_selftest')


class FixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((FIXTURES / 'm68k-groups/cases.json').read_text(encoding='utf-8'))

    def test_the_groups_are_the_builders_and_new_to_the_other_fixtures(self):
        groups = {test['group'] for test in self.fixture['tests']}
        self.assertEqual(groups, set(builder.GROUPS))
        self.assertEqual(sum(self.fixture['counts'].values()), len(self.fixture['tests']))
        for name in ('md-prefetch', 'md-exceptions', 'm68k-shifts'):
            other = json.loads((FIXTURES / name / 'cases.json').read_text(encoding='utf-8'))['source_sha256']
            self.assertFalse(set(other) & groups, name)

    def test_the_vectors_are_the_pinned_revisions_and_leave_out_what_the_harness_does_not_replay(self):
        self.assertEqual(self.fixture['revision'], builder.REVISION)
        self.assertEqual(self.fixture['revision'], json.loads(
            (FIXTURES / 'md-prefetch/cases.json').read_text(encoding='utf-8'))['revision'])
        self.assertTrue((FIXTURES / 'm68k-groups/LICENSE').is_file())
        for test in self.fixture['tests']:
            self.assertFalse(test['initial']['sr'] & 0x8000, test['name'])                     # no trace bit
            self.assertFalse(any(row[0] in ('re', 'we') for row in test['transactions']), test['name'])
            start = test['initial']['pc'] - 4
            self.assertTrue(0x200 <= start and start + 16 <= 0x400000, test['name'])         # inside the replay image

    def test_the_code_of_every_vector_agrees_with_the_others(self):
        image = {}
        for test in self.fixture['tests']:
            start = test['initial']['pc'] - 4
            for address, value in test['initial']['ram']:
                if start <= address < start + 16:
                    self.assertEqual(image.setdefault(address, value), value, test['name'])

    def test_only_the_decimal_instructions_mask_a_flag_and_only_the_undefined_one(self):
        masked = {test['group'] for test in self.fixture['tests'] if 'sr_mask' in test}
        self.assertEqual(masked, set(builder.UNDEFINED_V))
        for test in self.fixture['tests']:
            if 'sr_mask' in test:
                self.assertEqual(test['sr_mask'], 0xFFFD)


class DeviationTests(unittest.TestCase):
    LINES = '\n'.join((
        'FAIL ADD.l: 527 ADD.l D4, D5 da84 native audio cycles expected=00000008 actual=00000006',
        'FAIL ADD.l: 527 ADD.l D4, D5 da84 reference audio cycles expected=00000008 actual=00000006',
        'FAIL RTR: 008 RTR 4e77 native register[17] expected=0000220e actual=000022ae',
        'FAIL CLR.l: 140 CLR.l -(A4) 42a4 native bus[3].field[3] expected=00e10368 actual=00e10366',
        'FAIL ANDItoCCR: 001 ANDItoCCR # 023c native transaction count expected=00000003 actual=00000002',
        'FAIL LINK: 287 LINK A7, # 4e57 native memory[436f2d] expected=0000002e actual=0000002a',
        'not a failure line'))

    def test_a_failing_vector_is_sorted_by_the_first_thing_that_differed(self):
        found = selftest.failures(self.LINES)
        self.assertEqual(found['native'], {('ADD.l', '527'): 'clocks', ('RTR', '008'): 'state', ('CLR.l', '140'): 'bus',
                                           ('ANDItoCCR', '001'): 'bus', ('LINK', '287'): 'state'})
        self.assertEqual(found['reference'], {('ADD.l', '527'): 'clocks'})
        self.assertEqual(selftest.counts(found['native'])['LINK'], {'state': 1})

    def test_the_list_must_be_exact_in_both_directions(self):
        observed = {'ADD.l': {'clocks': 5}}
        self.assertEqual(selftest.problems(observed, dict(observed), True), [])
        self.assertTrue(selftest.problems(observed, {'ADD.l': {'clocks': 6}}, True))      # a fix has to shrink the list
        self.assertTrue(selftest.problems(observed, {}, True))                              # a new group is refused
        self.assertTrue(selftest.problems({}, observed, True))                              # a stale entry is refused
        self.assertTrue(selftest.problems(observed, dict(observed), False))                 # native and reference must agree

    def test_the_recorded_list_names_groups_of_the_fixture_with_known_kinds(self):
        recorded = json.loads((FIXTURES / 'm68k-groups/deviations.json').read_text(encoding='utf-8'))
        self.assertTrue(set(recorded) <= set(builder.GROUPS))
        for row in recorded.values():
            self.assertTrue(row and set(row) <= set(selftest.KINDS))
        total = sum(sum(row.values()) for row in recorded.values())
        self.assertEqual(total, 474)


if __name__ == '__main__':
    unittest.main()
