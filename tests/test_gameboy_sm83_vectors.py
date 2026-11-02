"""The SM83 vector fetch tool (tools/fetch_sm83_vectors.py) and the pins of its self-test, on synthetic vectors: no network, no compiler."""
import importlib.util
import re
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
import fetch_sm83_vectors as corpus  # noqa: E402

SPEC = importlib.util.spec_from_file_location('gameboy_sm83_vector_selftest', TOOLS / 'gameboy_sm83_vector_selftest.py')
selftest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(selftest)


def vector(pc=0xC000, ram=((0xC000, 0x0A), (0xC100, 0x55)), cycles=((0xC000, 0x0A, 'r-m'), (0xC100, 0x55, 'r-m')), **extra):
    start = {'pc': pc, 'sp': 0xDFF0, 'a': 1, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 0xF0, 'h': 6, 'l': 7, 'ime': 0, 'ie': 1,
             'ram': [list(item) for item in ram]}
    end = {'a': 0x55, 'b': 2, 'c': 3, 'd': 4, 'e': 5, 'f': 0xF0, 'h': 6, 'l': 7, 'pc': pc + 1, 'sp': 0xDFF0, 'ime': 0,
           'ram': [list(item) for item in ram], **extra}
    return {'name': 'x', 'initial': start, 'final': end, 'cycles': [list(item) for item in cycles]}


class PinTests(unittest.TestCase):
    def test_the_revision_and_the_digest_are_pinned(self):
        self.assertRegex(corpus.REVISION, r'^[0-9a-f]{40}$')
        self.assertRegex(corpus.CORPUS_SHA256, r'^[0-9a-f]{64}$')
        self.assertNotEqual(corpus.CORPUS_SHA256, '0' * 64)
        self.assertEqual(corpus.FILES, 500)

    def test_the_cache_stays_below_deps(self):
        self.assertEqual(corpus.CACHE, corpus.ROOT / '.deps' / 'sm83-vectors')


class PlainMemoryTests(unittest.TestCase):
    def test_the_regions_the_runtime_bus_models_flatly_are_plain(self):
        for address in (0x0000, 0x7FFF, 0x8000, 0xA000, 0xDFFF, 0xFE00, 0xFE9F, 0xFF80, 0xFFFE):
            self.assertTrue(corpus.plain_address(address), hex(address))

    def test_echo_unusable_io_and_the_enable_register_are_not(self):
        for address in (0xE000, 0xFDFF, 0xFEA0, 0xFEFF, 0xFF00, 0xFF0F, 0xFF40, 0xFF7F, 0xFFFF):
            self.assertFalse(corpus.plain_address(address), hex(address))

    def test_a_write_to_rom_is_a_mapper_write_and_not_plain(self):
        self.assertFalse(corpus.plain_address(0x4000, write=True))
        self.assertTrue(corpus.plain_address(0x4000))

    def test_a_vector_is_plain_only_when_every_address_is(self):
        self.assertTrue(corpus.touches_only_plain_memory(vector()))
        self.assertFalse(corpus.touches_only_plain_memory(vector(ram=((0xC000, 0x0A), (0xFF0F, 0)))))
        self.assertFalse(corpus.touches_only_plain_memory(vector(cycles=((0xC000, 0x0A, 'r-m'), (0xE123, 1, '-wm')))))
        self.assertFalse(corpus.touches_only_plain_memory(vector(cycles=((0xC000, 0x0A, 'r-m'), (0x1234, 1, '-wm')))))

    def test_an_idle_cycle_does_not_count_as_a_bus_access(self):
        self.assertTrue(corpus.touches_only_plain_memory(vector(cycles=((0xC000, 0x0A, 'r-m'), (0xFF0F, None, '---')))))


class LineTests(unittest.TestCase):
    def test_a_line_has_the_fields_the_c_check_reads(self):
        numbers = list(map(int, corpus.line(7, 3, vector()).split(' ')))
        self.assertEqual(numbers[:3], [7, 3, 1])                         # family, index, plain
        self.assertEqual(numbers[3:17], [0xC000, 0xDFF0, 1, 2, 3, 4, 5, 0xF0, 6, 7, 0, 0, 1, 2][:14])
        self.assertEqual(numbers[17:21], [0xC000, 0x0A, 0xC100, 0x55])    # two (address, value) pairs
        final = numbers[21:21 + 13]
        self.assertEqual(final[:8], [0x55, 2, 3, 4, 5, 0xF0, 6, 7])
        self.assertEqual(final[8:12], [0xC001, 0xDFF0, 0, 0])             # pc, sp, ime, ei
        self.assertEqual(final[12], 2)                                    # the final list has two pairs
        self.assertEqual(numbers[-1], 2)                                  # two machine cycles

    def test_ei_and_ie_that_a_vector_lacks_are_zero_and_ei_is_kept_when_given(self):
        text = corpus.line(0, 0, vector(ei=1))
        numbers = list(map(int, text.split(' ')))
        self.assertEqual(numbers[3 + 11], 0)                              # initial ei absent
        self.assertEqual(numbers[21 + 11], 1)                             # final ei given
        self.assertEqual(len(text.splitlines()), 1)

    def test_a_vector_off_plain_memory_is_marked(self):
        self.assertEqual(corpus.line(0, 0, vector(ram=((0xFF0F, 1),)))[:6], '0 0 0 ')


class SelftestPinTests(unittest.TestCase):
    def test_each_known_family_says_why_and_counts_every_path(self):
        for name, row in selftest.KNOWN.items():
            self.assertTrue(re.fullmatch(r'[0-9a-f]{2}|cb [0-9a-f]{2}', name), name)
            self.assertGreater(len(row['reason']), 80, name)
            self.assertTrue({'interpreter', 'ram_executor', 'ram_dispatch'} <= set(row), name)

    def test_only_stop_and_halt_remain_and_ei_is_not_excused(self):
        # EI was a real difference until 1.6.7 (IME set when EI completed); it is fixed in the runtime and must not be excused again.
        self.assertEqual(set(selftest.KNOWN), {'10', '76'})
        for row in selftest.KNOWN.values():
            self.assertIn('vector', row['reason'].lower())       # each is said to be a matter of the vector model

    def test_the_dispatch_leaves_only_halt_stop_and_rst_to_the_interpreter(self):
        self.assertEqual(selftest.LEFT_TO_THE_INTERPRETER, {'10', '76', 'c7', 'cf', 'd7', 'df', 'e7', 'ef', 'f7', 'ff'})


if __name__ == '__main__':
    unittest.main()
