"""The pure parts of the PlayStation vector self-test (gate G10): the GTE file's parser, the suite's layout, the steps' addresses, the
log, the baseline comparison, the fetch tool's pins. Authored records only: no vector of the suites, no compiler, no network, no ROM."""
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fetch_psx_vectors as fetch  # noqa: E402
import psx_vector_selftest as tool  # noqa: E402


def gte_entry(first_in, opcode, first_out, comment='// No opcode'):
    body = ''.join(f'    0x{first_in + n:08x}, // r[{n}]\n' for n in range(64))
    result = ''.join(f'    0x{first_out + n:08x}, // r[{n}]\n' for n in range(64))
    return ('{ // test\n  .name = "test",\n  .input = { // Input registers\n' + body + '  },\n'
            f'  .opcode = 0x{opcode:08x}, {comment}\n  .output = {{ // Expected output\n' + result + '  },\n},\n')


def suite_file(opcodes, cycles=1):
    out = struct.pack('<i', len(opcodes))
    state = bytes(128 + 24 + 12 + 8)
    for word in opcodes:
        out += b'\x04name' + bytes(46) + struct.pack('<II', word, 0x1000) + state + state + struct.pack('<I', cycles) + bytes(24 * cycles)
    return out


class VectorSelftestTest(unittest.TestCase):
    def test_gte_vectors_parse(self):
        text = 'const struct test_t tests[] = {\n' + gte_entry(1, 0xFFFFFFFF, 100) + gte_entry(2, 0x4A180001, 200, '// RTPS') + '};\n'
        rows = tool.gte_records(text)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], tool.GTE_NO_COMMAND)
        self.assertEqual(rows[1][1], 0x4A180001)
        self.assertEqual(rows[1][0][63], 2 + 63)
        self.assertEqual(rows[1][2][0], 200)
        self.assertEqual(len(tool.GTE_RECORD.pack(*rows[0][0], rows[0][1], *rows[0][2])), (64 + 1 + 64) * 4)

    def test_a_short_gte_vector_is_refused(self):
        entry = gte_entry(1, 0xFFFFFFFF, 100).replace('    0x00000001, // r[0]\n', '')
        with self.assertRaises(ValueError):
            tool.gte_records(entry)

    def test_the_opcodes_of_a_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ADD.json.bin'
            path.write_bytes(suite_file([0x01234567, 0x89ABCDEF], cycles=2))
            self.assertEqual(tool.opcodes_of(path), [0x01234567, 0x89ABCDEF])

    def test_the_corrupted_copy_changes_five_vectors_only(self):
        data = suite_file([n + 1 for n in range(20)], cycles=1)
        wrong = tool.corrupted(data)
        offsets = tool.vector_offsets(data, 20) + [len(data)]
        changed = [n for n in range(20) if data[offsets[n]:offsets[n + 1]] != wrong[offsets[n]:offsets[n + 1]]]
        self.assertEqual(changed, [0, 1, 2, 3, 4])
        self.assertEqual(sum(a != b for a, b in zip(data, wrong)), 5)

    def test_the_corrupted_load_is_of_a_vector_with_a_load(self):
        data = bytearray(suite_file([n + 1 for n in range(20)], cycles=1))
        offsets = tool.vector_offsets(bytes(data), 20)
        load = 51 + 8 + 172 + 128 + 24 + 12
        struct.pack_into('<i', data, offsets[9] + load, 22)
        wrong = tool.corrupted(bytes(data))
        self.assertNotEqual(wrong[offsets[9] + load + 4], data[offsets[9] + load + 4])
        self.assertEqual(sum(a != b for a, b in zip(data, wrong)), 5)

    def test_each_step_holds_one_instruction(self):
        pairs = tool.step_pairs([5, 6, 5, 7])
        self.assertEqual(pairs, {5: 0, 6: 8, 7: 16})
        self.assertTrue(all(a % tool.STEP_SPACING == 0 for a in pairs.values()))

    def test_the_log(self):
        log = ('{"failure":"ADD","path":"native","name":"x","opcode":"0","pc":"0","fields":["r"]}\n'
               '{"file":"ADD","path":"interpreter","total":10,"passed":10,"skipped":1,"fields":{"r":0}}\n'
               '{"file":"ADD","path":"native","total":10,"passed":9,"skipped":1,"fields":{"r":1}}\n'
               '{"gte_failure":3,"opcode":"0","register":1,"got":"0","want":"1"}\n'
               '{"gte":{"total":5,"passed":4,"registers":{"1":1}}}\nnoise\n')
        report = tool.parse_log(log)
        self.assertEqual(report['native']['ADD']['passed'], 9)
        self.assertEqual(len(report['failures']), 1)
        self.assertEqual(report['gte']['passed'], 4)
        self.assertEqual(tool.summarise(report['native'])['fields'], {'r': 1})
        self.assertEqual(tool.summarise(report['interpreter'])['skipped'], 1)

    def test_a_regression_is_named(self):
        row = lambda passed: {'total': 10, 'passed': passed, 'skipped': 0, 'fields': {}}
        baseline = {'interpreter': {'ADD': row(9)}, 'native': {}, 'gte': {'total': 5, 'passed': 5}}
        self.assertEqual(tool.regressions({'interpreter': {'ADD': row(9)}, 'native': {}, 'gte': {'total': 5, 'passed': 5}}, baseline), [])
        self.assertEqual(tool.regressions({'interpreter': {'ADD': row(10)}, 'native': {}, 'gte': {'total': 5, 'passed': 5}}, baseline), [])
        self.assertEqual(len(tool.regressions({'interpreter': {'ADD': row(8)}, 'native': {}, 'gte': {'total': 5, 'passed': 4}}, baseline)), 2)
        self.assertIn('not in the baseline', tool.regressions({'interpreter': {'SUB': row(9)}, 'native': {}}, baseline)[0])

    def test_the_pins_hold_together(self):
        self.assertEqual(len(fetch.FILES), 55)
        self.assertEqual(fetch.corpus_digest((n, d) for n, _, d in fetch.FILES), fetch.CORPUS_SHA256)
        self.assertEqual([n for n, _, _ in fetch.FILES], sorted(n for n, _, _ in fetch.FILES))

    def test_a_changed_file_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            wrong = fetch.problems(Path(folder))
            self.assertEqual(len(wrong), 56)
            fetch.gte_file(folder).parent.mkdir(parents=True)
            fetch.gte_file(folder).write_text('changed', encoding='ascii')
            self.assertIn('gte/tests.c: differs from the pinned file', fetch.problems(Path(folder)))
            self.assertNotEqual(hashlib.sha256(b'changed').hexdigest(), fetch.GTE_SHA256)


if __name__ == '__main__':
    unittest.main()
