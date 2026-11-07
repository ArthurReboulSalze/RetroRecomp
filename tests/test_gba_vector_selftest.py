"""The pure parts of the Game Boy Advance vector self-test (gate G10): classification, aggregation, baseline comparison, the command
line, the fetch tool's pins. Authored records only: no vector of the suite, no compiler, no network, no ROM."""
import hashlib
import io
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import fetch_gba_vectors as fetch  # noqa: E402
import gba_vector_selftest as tool  # noqa: E402


def fail_line(name, index, opcode, thumb=0, mode=0x10, kind='ran', xor=0, causes='R0'):
    return f'FAIL {name} {index} {opcode:08X} {thumb} {mode:02X} {kind} {xor:08X} {causes}'


def file_line(name, ran, passed):
    return f'FILE {name} {ran} {passed}'


class ClassificationTests(unittest.TestCase):
    def record(self, opcode, thumb=False, causes=('R0',), xor=0):
        return {'opcode': opcode, 'thumb': thumb, 'causes': list(causes), 'cpsr_xor': xor}

    def test_lines_are_parsed(self):
        record = tool.parse_line(fail_line('arm_mrs', 7, 0xE10F0000, kind='ran', xor=0x20000000, causes='CPSR,R3'))
        self.assertEqual((record['name'], record['index'], record['opcode'], record['thumb'], record['mode']),
                         ('arm_mrs', 7, 0xE10F0000, False, 0x10))
        self.assertEqual((record['cpsr_xor'], record['causes']), (0x20000000, ['CPSR', 'R3']))
        self.assertEqual(tool.parse_line('FAIL x 1 00000000 0 10 ran 00000000 -')['causes'], [])
        self.assertEqual(tool.parse_line(file_line('a', 5, 4)), {'type': 'FILE', 'name': 'a', 'ran': 5, 'passed': 4})
        self.assertIsNone(tool.parse_line('ran 5 passed 4'))
        self.assertIsNone(tool.parse_line('FAIL too short'))

    def test_the_coprocessor_families_are_recognised_by_the_opcode(self):
        for opcode in (0xEE000010, 0xEE000000, 0xEC000000, 0xED000000, 0x0E123456):    # MCR, CDP, LDC/STC (both forms)
            self.assertEqual(tool.classify(self.record(opcode, causes=('STEP',))), tool.COPROCESSOR, hex(opcode))
        self.assertNotEqual(tool.classify(self.record(0xEF000001)), tool.COPROCESSOR)           # SWI is bits 27:24 = 1111
        self.assertNotEqual(tool.classify(self.record(0xEE00, thumb=True)), tool.COPROCESSOR)   # no such family in Thumb

    def test_a_multiply_that_differs_only_by_carry_is_the_multiply_category(self):
        for opcode, thumb in ((0xE0100291, False), (0xE0300291, False), (0xE0900291, False), (0xE0F00291, False), (0x4350, True)):
            self.assertEqual(tool.classify(self.record(opcode, thumb, ('CPSR',), tool.CARRY_BIT)), tool.MULTIPLY_CARRY, hex(opcode))
        self.assertEqual(tool.classify(self.record(0xE0100291, False, ('CPSR',), 0x40000000)), tool.OTHER)       # another flag
        self.assertEqual(tool.classify(self.record(0xE0100291, False, ('CPSR', 'R1'), tool.CARRY_BIT)), tool.OTHER)  # a value too
        self.assertEqual(tool.classify(self.record(0xE2100001, False, ('CPSR',), tool.CARRY_BIT)), tool.OTHER)    # not a multiply

    def test_r15_as_an_operand_is_by_the_register_fields_of_arm_opcodes(self):
        self.assertEqual(tool.classify(self.record(0xE1A0F001)), tool.R15_OPERAND)         # MOV PC, R1 (Rd)
        self.assertEqual(tool.classify(self.record(0xE08F1000)), tool.R15_OPERAND)         # ADD R1, PC, R0 (Rn)
        self.assertEqual(tool.classify(self.record(0xE880A001)), tool.R15_OPERAND)         # STMIA R0, {R0, PC...}: bit 15 of the list
        self.assertEqual(tool.classify(self.record(0xE0801002)), tool.OTHER)
        self.assertEqual(tool.classify(self.record(0xE0801F02, thumb=True)), tool.OTHER)   # Thumb has no such test
        # the two classes decoded on 6 November 2026 from the failures that were unexplained
        self.assertEqual(tool.classify(self.record(0x08EE2A14, False, ('R14', 'fiq6'))), tool.BLOCK_USER_WRITEBACK)     # STMIA Rn!, {..}^
        self.assertEqual(tool.classify(self.record(0x08CE2A14, False, ('R14', 'fiq6'))), tool.OTHER)                   # same without write-back
        self.assertEqual(tool.classify(self.record(0x08EE8A14, False, ('R15',))), tool.R15_OPERAND)                   # PC in the list comes first
        for opcode in (0xC300, 0xCB00, 0xB400, 0xBC00):                                                              # empty Thumb register list
            self.assertEqual(tool.classify(self.record(opcode, True, ('R15',))), tool.THUMB_EMPTY_LIST)
        self.assertEqual(tool.classify(self.record(0xC301, True, ('R15',))), tool.OTHER)                              # a list that is not empty
        self.assertEqual(tool.classify(self.record(0xB500, True, ('R15',))), tool.OTHER)                              # PUSH {LR} is not empty

    def test_the_first_category_that_applies_wins(self):
        self.assertEqual(tool.classify(self.record(0xEE0F0010, causes=('STEP',))), tool.COPROCESSOR)   # also names R15
        self.assertEqual(tool.classify(self.record(0xE000F291, False, ('CPSR',), tool.CARRY_BIT)), tool.MULTIPLY_CARRY)


class AggregationTests(unittest.TestCase):
    LINES = [fail_line('arm_cdp', 1, 0xEE000000, causes='STEP', kind='undefined'),
             fail_line('arm_cdp', 2, 0xEE000010, causes='STEP', kind='undefined'),
             file_line('arm_cdp', 10, 8),
             file_line('thumb_b', 10, 10),
             fail_line('arm_mul_mla', 3, 0xE0100291, causes='CPSR', xor=0x20000000),
             fail_line('arm_mul_mla', 4, 0xE0100291, causes='R0,CPSR'),
             fail_line('arm_mul_mla', 5, 0xE0100291, causes='R0'),
             fail_line('arm_mul_mla', 6, 0xE0100291, causes='R0'),
             fail_line('arm_mul_mla', 7, 0xE0100291, causes='R0'),
             fail_line('arm_mul_mla', 8, 0xE0100291, causes='TRANS'),
             file_line('arm_mul_mla', 20, 14), 'a stray line of output']

    def test_a_file_is_counted_by_category(self):
        files = tool.read_output(self.LINES)
        self.assertEqual(files['arm_cdp']['failures'][tool.COPROCESSOR], 2)
        self.assertEqual(files['thumb_b']['failed'], 0)
        mul = files['arm_mul_mla']
        self.assertEqual((mul['failures'][tool.MULTIPLY_CARRY], mul['failures'][tool.OTHER], mul['failed']), (1, 5, 6))
        self.assertEqual(mul['causes'], {'R0': 4, 'TRANS': 1})
        self.assertEqual(len(mul['examples']), tool.EXAMPLES_PER_FILE)

    def test_totals_and_the_report(self):
        files = tool.read_output(self.LINES)
        totals = tool.summarise(files)
        self.assertEqual((totals['files'], totals['ran'], totals['passed'], totals['failed']), (3, 40, 32, 8))
        self.assertEqual(totals['failures'], {tool.COPROCESSOR: 2, tool.MULTIPLY_CARRY: 1, tool.R15_OPERAND: 0, tool.BLOCK_USER_WRITEBACK: 0, tool.THUMB_EMPTY_LIST: 0, tool.OTHER: 5})
        self.assertEqual(totals['passed_percent'], 80.0)
        meta = {'vectors': {'corpus_sha256': 'x'}, 'engine': {}, 'sample': {'interpreter': {}, 'generated': {}}}
        report = tool.build_report({'interpreter': files, 'generated': files}, meta)
        self.assertEqual(set(report), {'schema', 'statement', 'categories', 'vectors', 'engine', 'sample', 'interpreter', 'generated'})
        self.assertIn('not recorded from hardware', report['statement'])
        self.assertIn('not hardware fidelity', report['statement'])
        json.dumps(report)                                                              # the report is plain JSON

    def test_an_incomplete_output_is_an_error(self):
        with self.assertRaises(ValueError):                                              # a crash before the FILE line
            tool.read_output([fail_line('arm_b_bl', 1, 0xEA000000)])
        with self.assertRaises(ValueError):                                              # failures that do not add up
            tool.read_output([fail_line('arm_b_bl', 1, 0xEA000000), file_line('arm_b_bl', 10, 10)])


class BaselineTests(unittest.TestCase):
    def report(self, other=5, mul_ran=20, stride=50):
        lines = [file_line('arm_cdp', 10, 10), file_line('arm_mul_mla', mul_ran, mul_ran - other)]
        lines += [fail_line('arm_mul_mla', index, 0xE0100291) for index in range(other)]
        files = tool.read_output(lines)
        meta = {'vectors': {'corpus_sha256': 'x'}, 'engine': {'revision': 'e'},
                'sample': {'interpreter': {'stride': 1, 'max_per_file': None}, 'generated': {'stride': stride, 'max_per_file': 1000}}}
        return tool.build_report({'interpreter': files, 'generated': files}, meta)

    def test_a_run_like_the_baseline_holds(self):
        baseline = tool.baseline_from_report(self.report())
        self.assertEqual(tool.compare_baseline(self.report(), baseline), ([], []))
        self.assertEqual(baseline['paths']['interpreter']['arm_cdp']['failures'], {})                         # zero counts are omitted

    def test_more_failures_in_a_file_is_a_regression(self):
        regressions, improvements = tool.compare_baseline(self.report(other=6), tool.baseline_from_report(self.report()))
        self.assertEqual(len(regressions), 2)                                           # both paths
        self.assertIn('arm_mul_mla other: 6 failures, the baseline has 5', regressions[0])
        self.assertEqual(improvements, [])

    def test_fewer_failures_is_an_improvement_not_a_regression(self):
        regressions, improvements = tool.compare_baseline(self.report(other=3), tool.baseline_from_report(self.report()))
        self.assertEqual(regressions, [])
        self.assertEqual(len(improvements), 2)

    def test_a_failure_in_a_file_with_none_is_a_regression(self):
        before = tool.baseline_from_report(self.report(other=0))
        regressions, _ = tool.compare_baseline(self.report(other=1), before)
        self.assertEqual(len(regressions), 2)

    def test_a_category_the_baseline_does_not_hold_counts_from_zero(self):
        baseline = tool.baseline_from_report(self.report())
        report = self.report()
        for path in tool.PATHS:
            report[path]['files']['arm_cdp']['failures'][tool.COPROCESSOR] = 1
        regressions, _ = tool.compare_baseline(report, baseline)
        self.assertEqual(len(regressions), 2)
        self.assertIn('arm_cdp coprocessor', regressions[0])

    def test_runs_that_cannot_be_compared_are_refused(self):
        baseline = tool.baseline_from_report(self.report())
        self.assertTrue(any('sample' in line for line in tool.compare_baseline(self.report(stride=10), baseline)[0]))
        self.assertTrue(any('vectors run' in line for line in tool.compare_baseline(self.report(mul_ran=30), baseline)[0]))
        other_suite = tool.baseline_from_report(self.report())
        other_suite['vectors']['corpus_sha256'] = 'y'
        self.assertTrue(any('corpus' in line for line in tool.compare_baseline(self.report(), other_suite)[0]))
        self.assertTrue(tool.compare_baseline(self.report(), {'schema': 99})[0])

    def test_the_baseline_is_recorded_then_compared_through_a_file(self):
        class Args:
            baseline = None
            record_baseline = False
            only = None
        with tempfile.TemporaryDirectory() as folder:
            args = Args()
            args.baseline = Path(folder) / 'baseline.json'
            with contextlib_redirect():
                self.assertEqual(tool.apply_baseline(self.report(), args), 0)           # recorded
                self.assertTrue(args.baseline.is_file())
                self.assertEqual(tool.apply_baseline(self.report(), args), 0)           # holds
                self.assertEqual(tool.apply_baseline(self.report(other=9), args), 1)    # regressed
                args.only = ['arm']
                args.record_baseline = True
                self.assertEqual(tool.apply_baseline(self.report(), args), 2)           # a partial run is never recorded


def contextlib_redirect():
    import contextlib
    return contextlib.redirect_stdout(io.StringIO())


class CommandLineTests(unittest.TestCase):
    def test_run_is_the_default_command(self):
        args = tool.parse_args(['--vectors', 'somewhere'])
        self.assertEqual((args.command, args.stride, args.max_per_file), ('run', 50, 1000))
        self.assertEqual(tool.parse_args(['run', '--vectors', 'v', '--stride', '7', '--max-per-file', '9']).stride, 7)

    def test_the_other_commands(self):
        self.assertEqual(tool.parse_args(['build']).command, 'build')
        self.assertEqual(tool.parse_args(['report', '--baseline', 'b.json']).baseline, Path('b.json'))
        args = tool.parse_args(['compare', 'r.json', 'b.json'])
        self.assertEqual((args.report, args.baseline_file), (Path('r.json'), Path('b.json')))

    def test_bad_values_are_refused(self):
        for argv in (['--vectors', 'v', '--stride', '0'], ['--vectors', 'v', '--max-per-file', '0'], ['run']):
            with self.assertRaises(SystemExit), contextlib_redirect_stderr():
                tool.parse_args(argv)

    def test_the_cmake_project_names_the_sources(self):
        text = tool.cmake_project(Path('/c'), Path('/e'), Path('/b/libgbarecomp_armv4t.a'))
        for name in ('ss_interp.cpp', 'ss_gen.cpp', 'ss_run.cpp', 'gba_waitstates.cpp', 'ss_funcs.cpp', '/b/libgbarecomp_armv4t.a'):
            self.assertIn(name, text)

    def test_the_library_is_found_in_a_build_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(SystemExit):
                tool.find_library(Path(folder))
            (Path(folder) / 'sub').mkdir()
            library = Path(folder) / 'sub' / 'libgbarecomp_armv4t.a'
            library.write_bytes(b'!<arch>\n')
            self.assertEqual(tool.find_library(Path(folder)), library)

    def test_the_native_sources_are_in_the_repository(self):
        for name in tool.SOURCES:
            self.assertTrue((ROOT / 'native' / 'gba_vector_checks' / name).is_file(), name)


def contextlib_redirect_stderr():
    import contextlib
    return contextlib.redirect_stderr(io.StringIO())


class FetchToolTests(unittest.TestCase):
    def test_the_pins_are_complete_and_agree(self):
        self.assertEqual(len(fetch.FILES), 45)
        self.assertEqual(len({name for name, _size, _digest in fetch.FILES}), 45)
        self.assertEqual([name for name, *_ in fetch.FILES], sorted(name for name, *_ in fetch.FILES))
        self.assertTrue(all(len(digest) == 64 and size > 0 for _name, size, digest in fetch.FILES))
        self.assertEqual(fetch.pinned_digest(), fetch.CORPUS_SHA256)
        self.assertEqual(len(fetch.REVISION), 40)
        self.assertIn(fetch.REVISION, fetch.file_url('arm_b_bl'))
        self.assertTrue(fetch.file_url('arm_b_bl').endswith('/v1/arm_b_bl.json.bin'))

    def test_the_corpus_digest_depends_on_content_and_not_on_order(self):
        one = {'a': 'x' * 64, 'b': 'y' * 64}
        self.assertEqual(fetch.corpus_digest(one), fetch.corpus_digest(dict(reversed(list(one.items())))))
        self.assertNotEqual(fetch.corpus_digest(one), fetch.corpus_digest({'a': 'x' * 64, 'b': 'z' * 64}))

    def test_a_folder_is_inspected_against_the_pins(self):
        with tempfile.TemporaryDirectory() as folder, unittest.mock.patch.object(fetch, 'FILES', self.authored(folder)):
            good, missing, wrong = fetch.inspect(folder)
            self.assertEqual((good, missing, wrong), (['one'], ['three'], ['two']))
            self.assertEqual(fetch.inspect(folder, check_hashes=False)[0], ['one', 'two'])                    # by size alone
            nested = Path(folder) / 'clone'
            (nested / 'v1').mkdir(parents=True)
            (nested / 'v1' / 'one.json.bin').write_bytes(b'authored one')
            self.assertEqual(fetch.vector_dir(nested), nested / 'v1')                  # a clone: its v1 directory
            self.assertEqual(fetch.vector_dir(folder), Path(folder))

    def authored(self, folder):
        (Path(folder) / 'one.json.bin').write_bytes(b'authored one')
        (Path(folder) / 'two.json.bin').write_bytes(b'authored TWO')
        pin = lambda data: hashlib.sha256(data).hexdigest()
        return (('one', len(b'authored one'), pin(b'authored one')), ('two', len(b'authored two'), pin(b'authored two')),
                ('three', 5, pin(b'three')))

    def test_a_download_is_kept_only_when_it_matches_its_pin(self):
        data = b'authored vector bytes' * 100

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        asked = []

        def opener(url, timeout):
            asked.append(url)
            return Response(data)
        with tempfile.TemporaryDirectory() as folder:
            fetch.download('arm_b_bl', len(data), hashlib.sha256(data).hexdigest(), folder, opener)
            self.assertEqual((Path(folder) / 'arm_b_bl.json.bin').read_bytes(), data)
            self.assertEqual(asked, [fetch.file_url('arm_b_bl')])
            with self.assertRaises(SystemExit):
                fetch.download('arm_bx', len(data), '0' * 64, folder, opener)
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ['arm_b_bl.json.bin'])     # nothing partial kept

    def test_the_record_lists_every_file(self):
        with tempfile.TemporaryDirectory() as folder:
            fetch.record(folder)
            lines = (Path(folder) / fetch.RECORD).read_text(encoding='ascii').splitlines()
            self.assertEqual(len(lines), 45)
            self.assertEqual(json.loads((Path(folder) / (fetch.RECORD + '.json')).read_text(encoding='ascii'))['corpus_sha256'],
                             fetch.CORPUS_SHA256)



if __name__ == '__main__':
    unittest.main()
