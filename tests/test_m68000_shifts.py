"""MC68000 shift/rotate adaptations of the pinned interpreter (no compiler, no ROM)."""
from pathlib import Path
import json
import unittest

from retrorecomp import m68000

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps/segagenesisrecomp/runner/m68k_interp.c'

ROX_ZERO_COUNT = '        if ((mn == MN_ROXL || mn == MN_ROXR) && (g_cpu.SR & SR_X)) g_cpu.SR |= SR_C;\n'
MASK_64 = 'uint32_t allm = (uint32_t)((UINT64_C(1) << (cnt + 1)) - 1u);'
MASK_32 = 'uint32_t allm = (uint32_t)((1u << (cnt + 1)) - 1u);'


@unittest.skipUnless(PINNED.is_file(), 'pinned segagenesisrecomp sources are not cached')
class ShiftAdaptationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PINNED.read_text(encoding='utf-8')

    def adapted(self, prefix):
        return m68000.adapt_semantics(self.source, hook_prefix=prefix)

    def test_pinned_source_still_has_both_anchors(self):
        self.assertEqual(self.source.count(MASK_32), 1)
        self.assertEqual(self.source.count('} else if (reg_count && cnt == 0) {'), 1)

    def test_rox_count_zero_loads_c_from_x_once(self):
        for prefix in ('rr_md', 'rr_ng', 'rr_cps1', 'rr_x68k'):
            adapted = self.adapted(prefix)
            self.assertEqual(adapted.count(ROX_ZERO_COUNT), 1, prefix)
            # The line belongs to the zero-count branch, after C is cleared.
            branch = adapted.index('} else if (reg_count && cnt == 0) {')
            self.assertLess(branch, adapted.index(ROX_ZERO_COUNT))
            self.assertLess(adapted.index(ROX_ZERO_COUNT), adapted.index('g_cpu.SR &= ~0x1Fu;', branch))

    def test_asl_overflow_mask_is_64_bit_once(self):
        for prefix in ('rr_md', 'rr_ng', 'rr_cps1', 'rr_x68k'):
            adapted = self.adapted(prefix)
            self.assertEqual(adapted.count(MASK_64), 1, prefix)
            self.assertNotIn(MASK_32, adapted)

    def test_a_changed_upstream_fails_loudly(self):
        from retrorecomp.core import ConversionError
        for old, new in ((MASK_32, MASK_32.replace('1u <<', '2u <<')),
                         ('} else if (reg_count && cnt == 0) {', '} else if (reg_count && cnt == 1) {')):
            with self.assertRaises(ConversionError):
                m68000.adapt_semantics(self.source.replace(old, new, 1))


class ShiftFixtureTests(unittest.TestCase):
    def test_fixture_is_the_pinned_revision_and_covers_the_edges(self):
        fixture = json.loads((ROOT / 'tests/fixtures/m68k-shifts/cases.json').read_text(encoding='utf-8'))
        self.assertEqual(fixture['revision'], '64b253116a3de04aaac4346c43680960dc9b67e5')
        self.assertEqual(set(fixture['counts']), {'ROXL.b', 'ROXL.w', 'ROXL.l', 'ROXR.b', 'ROXR.w', 'ROXR.l', 'ASL.l'})
        self.assertEqual(sum(fixture['counts'].values()), len(fixture['tests']))
        zero_with_x = [t for t in fixture['tests'] if 'ROX' in t['group'] and int(t['name'].split()[-1], 16) & 0x20
                       and t['initial'][f"d{(int(t['name'].split()[-1], 16) >> 9) & 7}"] & 63 == 0
                       and t['initial']['sr'] & 0x10]
        self.assertTrue(zero_with_x)
        for test in zero_with_x:                              # PRM: C = X, X unchanged
            self.assertEqual(test['final']['sr'] & 1, 1, test['name'])
            self.assertEqual(test['final']['sr'] & 0x10, 0x10, test['name'])


if __name__ == '__main__':
    unittest.main()
