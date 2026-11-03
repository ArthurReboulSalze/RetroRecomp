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


@unittest.skipUnless(PINNED.is_file(), 'pinned segagenesisrecomp sources are not cached')
class DecoderToolIsolationTests(unittest.TestCase):
    """The other 68000 machines keep the decoder they had: the Mega Drive's rules go to a decoder of its own."""

    def written(self, **options):
        from unittest import mock
        from retrorecomp import megadrive_codegen
        files = {}
        with mock.patch.object(megadrive_codegen, 'write_changed', lambda path, text: files.__setitem__(Path(path).name, (Path(path).parent, text))),                 mock.patch.object(megadrive_codegen, 'run', lambda *a, **k: ''),                 mock.patch.object(megadrive_codegen, 'toolchain', lambda: ('cmake', 'Ninja')),                 mock.patch.object(megadrive_codegen, 'build_executable', lambda folder, name: Path(folder) / name):
            megadrive_codegen.decoder_tool(ROOT / '.deps/segagenesisrecomp', **options)
        return files

    def test_the_default_decoder_is_the_one_of_the_previous_release(self):
        raw = PINNED.read_text(encoding='utf-8')
        source = m68000.adapt_cycle_estimates(raw)           # what the decoder tool wrote before 1.6.7
        expected = source[source.index('static int interp_popcount16('):source.index('static void interp_account_cycles(')]
        expected = expected[:expected.rfind('/* The emit_cycle_accounting')]
        folder, text = self.written()['md_cycle_estimate.h']
        self.assertEqual(text, expected)
        self.assertEqual(folder.name, 'megadrive-step-decoder')

    def test_the_mega_drive_decoder_has_its_own_folder_and_the_rules(self):
        folder, text = self.written(md_rules=True)['md_cycle_estimate.h']
        self.assertEqual(folder.name, 'megadrive-step-decoder-rules')
        self.assertIn('instr->mnemonic != MN_CMP &&', text)

    def test_only_the_mega_drive_generator_asks_for_the_rules(self):
        import re
        users = {}
        for path in (ROOT / 'retrorecomp').glob('*.py'):
            users[path.name] = len(re.findall(r'decoder_tool\([^)]*md_rules', path.read_text(encoding='utf-8')))
        self.assertEqual({name for name, n in users.items() if n}, {'megadrive_codegen.py'})
        for name in ('neogeo_codegen.py', 'cps1_codegen.py'):
            self.assertEqual(users[name], 0)
        self.assertNotIn('md_rules', (ROOT / 'tools/x68000_native.py').read_text(encoding='utf-8'))

    def test_decode_asks_for_the_rules_and_only_the_mega_drive_calls_it(self):
        # decode() hard-codes md_rules=True: a caller of another machine would get the Mega Drive's rules without knowing it.
        import re
        from unittest import mock
        from retrorecomp import megadrive_codegen
        asked = []
        def stop(engine, **options):
            asked.append(options)
            raise StopIteration
        with mock.patch.object(megadrive_codegen, 'decoder_tool', stop), self.assertRaises(StopIteration):
            megadrive_codegen.decode(Path('engine'), Path('project'), Path('rom'), set())
        self.assertEqual(asked, [{'md_rules': True}])
        callers = set()
        for path in list((ROOT / 'retrorecomp').rglob('*.py')) + list((ROOT / 'tools').glob('*.py')):
            text = path.read_text(encoding='utf-8')
            if re.search(r'megadrive_codegen\s+import[^\n]*\bdecode\b|megadrive_codegen\.decode\(', text):
                callers.add(path.name)
        self.assertEqual(callers - {'megadrive_native_selftest.py'}, set())


if __name__ == '__main__':
    unittest.main()
