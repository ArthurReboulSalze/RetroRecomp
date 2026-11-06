"""The HuC6280 vector fetch tool (tools/fetch_huc6280_vectors.py) and the judgement of its self-test, on synthetic rows: no network, no compiler."""
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import fetch_huc6280_vectors as corpus  # noqa: E402

SPEC = importlib.util.spec_from_file_location('pce_huc6280_vector_selftest', TOOLS / 'pce_huc6280_vector_selftest.py')
selftest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selftest)


def row(opcode, **extra):
    """A clean opcode file of 2,500 vectors, all executed and equal."""
    base = {'opcode': opcode, 'vectors': 2500, 'executed': 2500, 'refused': 0, 'faulted': 0, 'not_comparable': 0,
            'state_equal': 2500, 'both_equal': 2500, 'registers': 0, 'flags': 0, 'pc': 0, 'mpr': 0, 'memory': 0,
            'cycles_equal': 2500, 'cycles_different': 0}
    base.update(extra)
    return base


def refused(opcode):
    return row(opcode, executed=0, refused=2500, state_equal=0, both_equal=0, cycles_equal=0)


class PinTests(unittest.TestCase):
    def test_the_revision_and_the_digest_are_pinned(self):
        self.assertRegex(corpus.REVISION, r'^[0-9a-f]{40}$')
        self.assertRegex(corpus.CORPUS_SHA256, r'^[0-9a-f]{64}$')
        self.assertEqual(corpus.FILES, 256)

    def test_the_cache_stays_below_deps(self):
        self.assertEqual(corpus.CACHE, corpus.ROOT / '.deps' / 'huc6280-vectors')

    def test_the_digest_does_not_depend_on_the_order_the_files_arrive_in(self):
        hashes = {'00.json.bin': 'a' * 64, '01.json.bin': 'b' * 64}
        self.assertEqual(corpus.corpus_digest(hashes), corpus.corpus_digest(dict(reversed(list(hashes.items())))))
        self.assertNotEqual(corpus.corpus_digest(hashes), corpus.corpus_digest({**hashes, '01.json.bin': 'c' * 64}))

    def test_the_known_differences_and_the_refused_list_are_the_pinned_corpus(self):
        self.assertEqual(22, len(selftest.REFUSED))
        self.assertEqual(8, len(selftest.KNOWN))
        self.assertEqual(640000, selftest.EXPECTED['vectors'])
        self.assertEqual(selftest.EXPECTED['vectors'],
                         selftest.EXPECTED['executed'] + selftest.EXPECTED['refused'] + selftest.EXPECTED['faulted'])
        for opcode, known in selftest.KNOWN.items():
            self.assertIn('reason', known, opcode)
            self.assertTrue(set(known) - {'reason'}, opcode)


class JudgementTests(unittest.TestCase):
    def full_corpus(self):
        rows = []
        for value in range(256):
            opcode = f'{value:02X}'
            if opcode in selftest.REFUSED:
                rows.append(refused(opcode))
            elif opcode in selftest.KNOWN:
                known = {('cycles_different' if key == 'cycles' else key): number
                         for key, number in selftest.KNOWN[opcode].items() if key != 'reason'}
                rows.append(row(opcode, **known))
            else:
                rows.append(row(opcode))
        return rows

    def test_the_pinned_differences_alone_are_explained(self):
        rows = self.full_corpus()
        # The block transfers are cut by the corpus cap: 12,481 vectors whose state cannot be compared.
        for opcode, cut in (('73', 2500), ('C3', 2500), ('D3', 2500), ('E3', 2500), ('F3', 2481)):
            index = int(opcode, 16)
            rows[index] = row(opcode, not_comparable=cut, state_equal=2500 - cut, both_equal=2500 - cut)
        totals, unexplained = selftest.judge(rows)
        self.assertEqual(640000, totals['vectors'])
        self.assertEqual(55000, totals['refused'])
        self.assertEqual(12481, totals['not_comparable'])
        self.assertEqual([m for m in unexplained if 'expected' not in m], [], unexplained)

    def test_a_new_difference_is_not_explained(self):
        rows = self.full_corpus()
        rows[0x10] = row('10', flags=1)
        _, unexplained = selftest.judge(rows)
        self.assertTrue(any(message.startswith('10:') for message in unexplained), unexplained)

    def test_a_changed_count_on_a_known_difference_is_not_explained(self):
        rows = self.full_corpus()
        rows[0x04] = row('04', flags=253)
        _, unexplained = selftest.judge(rows)
        self.assertTrue(any(message.startswith('04:') for message in unexplained), unexplained)

    def test_a_known_difference_that_disappears_is_reported(self):
        rows = self.full_corpus()
        rows[0x43] = row('43')
        _, unexplained = selftest.judge(rows)
        self.assertIn('43: known difference not seen', unexplained)

    def test_an_opcode_the_engine_stops_on_that_is_not_listed_is_reported(self):
        rows = self.full_corpus()
        rows[0x20] = refused('20')
        _, unexplained = selftest.judge(rows)
        self.assertTrue(any(message.startswith('20:') for message in unexplained), unexplained)

    def test_a_missing_file_is_reported(self):
        _, unexplained = selftest.judge(self.full_corpus()[:-1])
        self.assertTrue(any('opcode files' in message for message in unexplained), unexplained)


if __name__ == '__main__':
    unittest.main()
