"""The Mega Drive's instruction rules on the pinned 68000 interpreter text (no compiler, no ROM).

The rules themselves are replayed against independent vectors by tools/megadrive_groups_selftest.py (BUILDING.md)."""
from pathlib import Path
import unittest

from retrorecomp import m68000, megadrive_rules
from retrorecomp.core import ConversionError

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps/segagenesisrecomp/runner/m68k_interp.c'


@unittest.skipUnless(PINNED.is_file(), 'pinned segagenesisrecomp sources are not cached')
class InstructionRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = PINNED.read_text(encoding='utf-8')
        cls.shared = m68000.adapt_semantics(cls.raw)
        cls.adapted = megadrive_rules.adapt_instruction_rules(cls.shared)

    def test_every_rule_replaces_exactly_one_pinned_line(self):
        for old, new in (*megadrive_rules.ESTIMATE_RULES, *megadrive_rules.STATE_RULES, *megadrive_rules.CLOCK_RULES):
            self.assertEqual(self.shared.count(old), 1, old.splitlines()[0])
            self.assertEqual(self.adapted.count(new), 1, new.splitlines()[0])

    def test_a_rule_applied_twice_or_to_a_changed_upstream_fails_loudly(self):
        with self.assertRaises(ConversionError):
            megadrive_rules.adapt_instruction_rules(self.adapted)
        old = megadrive_rules.STATE_RULES[0][0]
        with self.assertRaises(ConversionError):
            megadrive_rules.adapt_instruction_rules(self.shared.replace(old, old.replace('0xFFu', '0xFEu'), 1))

    def test_the_state_rules_read_as_the_manual(self):
        self.assertIn('(ccr & 0x1Fu)', self.adapted)                    # RTR: five condition code bits
        self.assertNotIn('(ccr & 0xFFu)', self.adapted)
        link = self.adapted[self.adapted.index('    case MN_LINK:'):][:400]
        self.assertLess(link.index('uint32_t pushed = g_cpu.A[ar];'), link.index('g_cpu.A[7] -= 4;'))
        unlk = self.adapted[self.adapted.index('    case MN_UNLK:'):][:400]
        self.assertLess(unlk.index('g_cpu.A[7] = frame + 4;'), unlk.index('g_cpu.A[ar] = popped;'))   # the load wins for A7

    def test_the_estimate_rules_leave_cmp_and_the_word_forms_alone(self):
        # CMP and CMPA do not take the two clocks; ADDA.W and SUBA.W keep their 8; the memory sources keep their costs.
        text = self.adapted[self.adapted.index('    case MN_ADD: case MN_SUB: case MN_AND: case MN_OR:\n'
                                               '    case MN_EOR: case MN_CMP:'):][:900]
        self.assertIn('instr->mnemonic != MN_CMP &&', text)
        self.assertIn('(ea_src == 0 || instr->src_ea == 0x3c)', text)
        self.assertIn('(instr->mnemonic == MN_CMPA || is_long ? 6 : 8)', self.adapted)

    def test_the_decoder_estimate_takes_the_same_static_rules(self):
        decoder = megadrive_rules.adapt_estimate_rules(m68000.adapt_cycle_estimates(self.raw))
        for old, new in megadrive_rules.ESTIMATE_RULES:
            self.assertEqual(decoder.count(new), 1)
        for token in ('rr_md_arithmetic_phase', 'uint32_t pushed =', 'kept_z'):
            self.assertNotIn(token, decoder)          # the data-dependent clocks and the state rules are executor text only

    def test_the_other_machines_text_is_untouched(self):
        for prefix in ('rr_ng', 'rr_cps1', 'rr_x68k'):
            other = m68000.adapt_semantics(self.raw, hook_prefix=prefix)
            self.assertNotIn('(ccr & 0x1Fu)', other, prefix)
            self.assertNotIn('uint32_t pushed', other, prefix)
        for name in ('retrorecomp/neogeo_codegen.py', 'retrorecomp/cps1_codegen.py', 'tools/x68000_native.py'):
            self.assertNotIn('megadrive_rules', (ROOT / name).read_text(encoding='utf-8'), name)


if __name__ == '__main__':
    unittest.main()
