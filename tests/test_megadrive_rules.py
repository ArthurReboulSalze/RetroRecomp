"""The Mega Drive's instruction rules on the pinned 68000 interpreter text (no compiler, no ROM).

The rules themselves are replayed against independent vectors by tools/megadrive_groups_selftest.py (BUILDING.md)."""
from pathlib import Path
import unittest

from retrorecomp import m68000, megadrive_bus_rules, megadrive_rules
from retrorecomp.core import ConversionError

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps/segagenesisrecomp/runner/m68k_interp.c'


@unittest.skipUnless(PINNED.is_file(), 'pinned segagenesisrecomp sources are not cached')
class InstructionRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = PINNED.read_text(encoding='utf-8')
        cls.shared = m68000.adapt_semantics(cls.raw)
        cls.rules_only = megadrive_rules.adapt_instruction_rules(cls.shared)
        cls.adapted = megadrive_bus_rules.adapt_bus_order_rules(cls.rules_only)

    def test_every_rule_replaces_exactly_one_pinned_line(self):
        for old, new in (*megadrive_rules.ESTIMATE_RULES, *megadrive_rules.STATE_RULES, *megadrive_bus_rules.BUS_ORDER_RULES,
                         *megadrive_rules.CLOCK_RULES):
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


    def test_the_bus_order_rules_write_low_word_first_and_leave_the_state_rules_alone(self):
        text = self.adapted
        self.assertIn('static int s_low_first;', text)
        self.assertIn('s_low_first = rmw && sz == M68K_SIZE_L;', text)
        self.assertLess(text.index('m68k_write16(a + 2u, (uint16_t)v);'), text.index('m68k_write16(a, (uint16_t)(v >> 16));'))
        split = text[text.index('static void mem_write_split'):][:300]
        self.assertLess(split.index('m68k_write16(a + 2u'), split.index('rr_md_prefetch_release();'))
        self.assertLess(split.index('rr_md_prefetch_release();'), split.index('m68k_write16(a, (uint16_t)(v >> 16));'))
        # m68000_state_rules reads STATE_RULES by position: the bus order rules are a tuple of their own.
        self.assertEqual(len(megadrive_rules.STATE_RULES), 9)
        for other in ('m68000_state_rules',):
            self.assertNotIn('BUS_ORDER', (ROOT / 'retrorecomp' / (other + '.py')).read_text(encoding='utf-8'))


class PrefetchPlanTests(unittest.TestCase):
    """The static bus setup of a few forms (the live preparation and the plan are replayed against each other by
    tools/megadrive_prefetch_plan_selftest.py)."""

    @staticmethod
    def plan(name, **fields):
        from retrorecomp import megadrive_codegen
        instruction = {'word_count': 1, 'src_ea': 0, 'dst_ea': 0, 'size': 1, 'dst_is_ea': 0, 'predec_mem_form': 0,
                       'words': [0, 0, 0], **fields}
        return [int(value) for value in megadrive_codegen.prefetch_plan(instruction, name).strip('{}').split(',')]

    def test_the_predecrement_forms_calculate_the_first_address_before_the_first_read(self):
        kind, count, advance, idle, tail, flags, dst_advance, dst_idle = self.plan('MN_ADDX', predec_mem_form=1, src_ea=11)
        self.assertEqual(idle, 2)
        self.assertEqual(self.plan('MN_ADDX', predec_mem_form=0, src_ea=11)[3], 0)       # the register form has no calculation

    def test_a_byte_immediate_with_a_memory_destination_reads_the_next_word_before_the_calculation(self):
        row = self.plan('MN_ADDI', size=0, word_count=3, src_ea=0x34)                      # ADDI.B #,(d8,A4,Xn)
        self.assertEqual((row[3], row[5] & 128), (2, 128))
        self.assertEqual(self.plan('MN_ADDI', size=2, word_count=4, src_ea=0x34)[5] & 128, 0)   # the long forms are not proved
        self.assertEqual(self.plan('MN_BCLR', size=0, word_count=2, src_ea=0x24, words=[0x08a0, 0])[5] & 128, 128)
        self.assertEqual(self.plan('MN_BCLR', size=0, word_count=1, src_ea=0x24, words=[0x01a0, 0])[5] & 128, 0)   # by data register

    def test_link_and_movep_fetch_their_last_word_after_their_writes(self):
        for name in ('MN_LINK', 'MN_MOVEP'):
            self.assertEqual(self.plan(name, word_count=2)[5] & 4, 0, name)
        self.assertEqual(self.plan('MN_ADD', word_count=1)[5] & 4, 4)


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
        # megadrive_static.py is the second Mega Drive-only module that asks (the static discovery of 1.7.3).
        self.assertEqual({name for name, n in users.items() if n}, {'megadrive_codegen.py', 'megadrive_static.py'})
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
