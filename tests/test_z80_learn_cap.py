"""Nothing the interpreter ran from RAM is dropped on the banked Z80 chain: the anchors of tools/z80_learn_cap_selftest.py that need no
compiler (the bound of 4,096 windows is gone from the emitter and from the glue, the set is staged for every machine, the report counts
the windows and the bodies apart)."""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp import z80_chain_build  # noqa: E402


def native(name: str) -> str:
    return (ROOT / 'native' / name).read_text(encoding='utf-8')


class NoBoundTests(unittest.TestCase):
    def test_the_emitter_reads_every_line_of_native_patterns(self):
        text = native('banked_emitter.inc')
        body = text[text.index('static void banked_learn('):text.index('/* game_layout.c')]
        self.assertNotIn('4096', body)
        self.assertIn('while (fgets(line, sizeof line, learned))', body)

    def test_the_pool_grows_and_the_guard_tables_do_not_depend_on_its_size(self):
        text = native('banked_emitter.inc')
        self.assertIn('static void banked_hash_grow(', text)
        self.assertIn('banked_hash_grow(pool);', text)
        tables = text[text.index('static size_t banked_write_tables('):]
        self.assertIn('pool->mask + 1', tables.split('qsort(')[0])      # the slots now in use, not the size it was opened with
        self.assertIn('qsort(guards', tables)                            # sorted by key: the size never shows in the output

    def test_the_glue_keeps_every_window_a_run_learns(self):
        glue = native('z80_chain_glue.inc')
        self.assertNotIn('4096', glue[glue.index('Learning (--learn FILE)'):glue.index('static void smsrecomp_state_service')])
        self.assertIn('#include "z80_learned_set.h"', glue)
        self.assertIn('rr_learned_add(&learned_set, word)', glue)
        header = native('z80_learned_set.h')
        self.assertNotIn('4096', header.split('*/', 1)[1])               # the comment says what the old bound was; the code has none

    def test_the_set_is_staged_for_every_machine_of_the_chain(self):
        from retrorecomp import coleco_build, cpc_build, msx_build, sg1000_build, zxs_build
        for module in (coleco_build, cpc_build, msx_build, sg1000_build, zxs_build):
            self.assertIn('z80_learned_set.h', module.CHAIN_FILES, module.__name__)
            self.assertTrue((ROOT / 'native' / 'z80_learned_set.h').is_file())

    def test_the_machines_that_learn_all_report_the_windows_and_the_bodies_apart(self):
        for name in ('msx', 'zxs', 'coleco', 'sg1000', 'cpc'):
            text = (ROOT / 'retrorecomp' / f'{name}_conversion.py').read_text(encoding='utf-8')
            self.assertIn('learning_record(work)', text, name)
            self.assertNotIn("len((work / 'native.patterns')", text, name)


class RecordTests(unittest.TestCase):
    def test_words_bodies_and_unsupported_windows_are_three_numbers(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            (work / 'generated').mkdir()
            (work / 'native.patterns').write_text('21000000\n21010000\n21010000\n', encoding='utf-8')
            (work / 'generated' / 'banked-coverage.json').write_text(json.dumps(
                {'profile_windows_loaded': 3, 'profile_added_native_bodies': 2, 'profile_unsupported_windows': 0}), encoding='utf-8')
            record = z80_chain_build.learning_record(work)
            self.assertEqual(record, {'learned_patterns': 3, 'learned_pattern_bodies': 2, 'learned_windows_loaded': 3,
                                      'learned_windows_unsupported': 0, 'learned_windows_dropped': 0})
            (work / 'generated' / 'banked-coverage.json').write_text(json.dumps({'profile_windows_loaded': 2}), encoding='utf-8')
            self.assertEqual(z80_chain_build.learning_record(work)['learned_windows_dropped'], 1)

    def test_a_conversion_that_learned_nothing_says_so(self):
        with tempfile.TemporaryDirectory() as folder:
            record = z80_chain_build.learning_record(Path(folder))
            self.assertEqual(record['learned_patterns'], 0)
            self.assertIsNone(record['learned_pattern_bodies'])


if __name__ == '__main__':
    unittest.main()
