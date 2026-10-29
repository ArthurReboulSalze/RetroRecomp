"""CPS-1 independent Z80 vector replay (gate G10): the compiler-free parts of tools/cps1_z80_vector_selftest.py.

The replay itself builds C and runs a cached sample of the pinned corpus: `python -B tools/cps1_z80_vector_selftest.py`."""
import copy
import importlib.util
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cps1_z80_vector_selftest', ROOT / 'tools' / 'cps1_z80_vector_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


def case(pc, code, family='00'):
    state = dict.fromkeys(selftest.FIELDS, 0)
    state['pc'] = pc
    final = dict(state, pc=pc + 1)
    return {'name': 'n', 'family': family, 'initial': dict(state, ram=[[pc + n, byte] for n, byte in enumerate(code)]),
            'final': dict(final, ram=[[pc + n, byte] for n, byte in enumerate(code)]), 'cycles': [[0, None, '----']] * 4}


class PrepareTests(unittest.TestCase):
    def test_one_slot_per_opcode_form_and_ram_variants_for_sound_ram(self):
        cases = [case(0x100, [0x00]), case(0x2000, [0x00]), case(0x9000, [0xed, 0x44]), case(0xd010, [0x3e, 0x12]),
                 case(0xd010, [0x3e, 0x34]), case(0xe000, [0x00])]
        image, ram, slots, forms = selftest.prepare(cases)
        self.assertEqual(len(image), selftest.IMAGE_BYTES)
        self.assertEqual(slots[0], slots[1])                          # the same opcode form shares a slot
        self.assertNotEqual(slots[0], slots[2])
        self.assertEqual(slots[3:], [selftest.NO_SLOT] * 3)            # sound RAM and out-of-map code have no ROM slot
        self.assertEqual(forms, 2)
        self.assertEqual(sorted(item['bytes'][:4] for item in ram), ['3e12', '3e34'])
        self.assertEqual(image[slots[2]:slots[2] + 2], bytes([0xed, 0x44]))

    def test_the_vector_file_is_a_flat_word_stream(self):
        cases = [case(0x100, [0x00])]
        cases[0]['ports'] = [[0x7f, 5, 'w']]
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'v.bin'
            selftest.vectors_file(cases, [0], path)
            words = struct.unpack('<' + 'I' * (path.stat().st_size // 4), path.read_bytes())
        self.assertEqual(words[0], 1)
        self.assertEqual(words[1:3], (0, 4))                           # slot, expected clock count
        self.assertEqual(words[-4:], (1, 0x7f, 5, ord('w')))           # one port: address, value, direction


class ProblemTests(unittest.TestCase):
    GOOD = {'cases': 10, 'rom_mapped': 6, 'ram_mapped': 1, 'outside_code_map': 3, 'native_as_expected': 7,
            'interpreted_and_counted_as_expected': 3, 'corpus_revision': 'other', 'samples_per_family': 1,
            'totals': {'paths_equal': 10, 'paths_clock_equal': 10, 'native_state': 9, 'native_clock': 10},
            'field_failures': {'native': {}, 'reference': {}}}

    def test_a_clean_run_has_no_problem(self):
        self.assertEqual(selftest.problems(self.GOOD), [])

    def test_each_requirement_is_checked(self):
        for change in ({'native_as_expected': 6}, {'interpreted_and_counted_as_expected': 2}):
            self.assertTrue(selftest.problems(dict(copy.deepcopy(self.GOOD), **change)), change)
        broken = copy.deepcopy(self.GOOD)
        broken['totals']['paths_equal'] = 9
        self.assertTrue(selftest.problems(broken))
        broken = copy.deepcopy(self.GOOD)
        broken['totals']['paths_clock_equal'] = 9
        self.assertTrue(selftest.problems(broken))

    def test_the_pinned_baseline_is_enforced_only_for_its_corpus(self):
        pinned = selftest.BASELINE
        result = copy.deepcopy(self.GOOD)
        result.update(corpus_revision=pinned['corpus_revision'], samples_per_family=pinned['samples_per_family'], cases=pinned['cases'],
                      rom_mapped=0, ram_mapped=0, outside_code_map=0, native_as_expected=0, interpreted_and_counted_as_expected=0)
        result['totals'] = {'paths_equal': pinned['cases'], 'paths_clock_equal': pinned['cases'],
                            'native_state': pinned['native_state'], 'native_clock': pinned['native_clock']}
        result['field_failures'] = {'native': dict(pinned['field_failures']), 'reference': dict(pinned['field_failures'])}
        self.assertEqual(selftest.problems(result), [])
        result['totals']['native_state'] += 1
        self.assertTrue(selftest.problems(result))


if __name__ == '__main__':
    unittest.main()
