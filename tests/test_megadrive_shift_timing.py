"""Mega Drive clocks of Dx,Dy shifts and rotates (no compiler, no ROM)."""
from pathlib import Path
import json
import unittest

from retrorecomp import m68000, megadrive_codegen
from retrorecomp.core import ConversionError

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps/segagenesisrecomp/runner/m68k_interp.c'
ANCHOR = '        int reg_count = (ins->src_ea >= 0);\n'
HOOK = 'rr_md_arithmetic_phase((sz == M68K_SIZE_L ? 8u : 6u) + 2u * (g_cpu.D[ins->src_ea] & 63u), 0, 1);'


@unittest.skipUnless(PINNED.is_file(), 'pinned segagenesisrecomp sources are not cached')
class ShiftTimingAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = m68000.adapt_semantics(PINNED.read_text(encoding='utf-8'))

    def test_the_hook_is_added_once_before_the_shift_and_only_for_a_register_count(self):
        adapted = megadrive_codegen.adapt_shift_timing(self.source)
        self.assertEqual(adapted.count(HOOK), 1)
        start = adapted.index(ANCHOR)
        self.assertLess(start, adapted.index(HOOK))
        self.assertLess(adapted.index(HOOK), adapted.index('do_shift(ins->mnemonic', start))
        self.assertIn('if (reg_count)\n            ' + HOOK, adapted)

    def test_the_other_machines_text_is_untouched(self):
        for prefix in ('rr_ng', 'rr_cps1', 'rr_x68k'):
            self.assertNotIn('2u * (g_cpu.D[ins->src_ea] & 63u)',
                             m68000.adapt_semantics(PINNED.read_text(encoding='utf-8'), hook_prefix=prefix))

    def test_a_changed_upstream_fails_loudly(self):
        with self.assertRaises(ConversionError):
            megadrive_codegen.adapt_shift_timing(self.source.replace(ANCHOR, ANCHOR.replace('>= 0', '> 0'), 1))


class ShiftFixtureClockTests(unittest.TestCase):
    def test_every_register_count_vector_is_replayed_with_its_clocks(self):
        fixture = json.loads((ROOT / 'tests/fixtures/m68k-shifts/cases.json').read_text(encoding='utf-8'))
        self.assertFalse([t['name'] for t in fixture['tests'] if 'timing_unchecked' in t])
        counted = 0
        for test in fixture['tests']:
            opcode = int(test['name'].split()[-1], 16)
            if not opcode & 0x20:
                continue
            count = test['initial'][f'd{(opcode >> 9) & 7}'] & 63
            expected = (8 if test['group'].endswith('.l') else 6) + 2 * count
            self.assertEqual(test['length'], expected, test['name'])
            counted += 1
        self.assertGreater(counted, 400)


if __name__ == '__main__':
    unittest.main()
