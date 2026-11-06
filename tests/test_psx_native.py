"""PlayStation native steps (retrorecomp/psx_native.py): observations, Beetle's handler table, runs and the C they become.
No disc and no Beetle checkout: a small cpu.c of the same shape stands for the prepared one."""
from pathlib import Path
import tempfile
import unittest

from retrorecomp import psx_native

ORDER = ['SLL', 'ILL', 'SRL', 'SRA'] + ['ILL'] * 4 + ['JR'] + ['ILL'] * 24 + ['ADDU'] + ['ILL'] * 30
UPPER = ['ILL', 'ILL', 'J', 'ILL'] + ['ILL'] * 5 + ['ADDIU'] + ['ILL'] * 5 + ['LUI'] + ['ILL'] * 19 + ['LW'] + ['ILL'] * 28
CPU = ('static int32_t CPU_RunReal(PS_CPU *self, int32_t timestamp_in)\n{\n'
       '   CGBEGIN\n' + ''.join(f'    CGE(op_{n})\n' for n in ORDER + UPPER + ['INTERRUPT'] * 128) + '   CGEND\n'
       + ''.join(f'    BEGIN_OPF({n});\n\tRTYPE; // {n}\n\tDO_LDS(); /* body */ GPR[rd] = GPR[rs];\n    END_OPF;\n'
                 for n in ('SLL', 'SRL', 'SRA', 'ADDU', 'ADDIU', 'LUI', 'LW', 'ILL'))
       + '    BEGIN_OPF(JR);\n\tRTYPE;\n\tDO_BRANCH(true, GPR[rs], 0, false, 0);\n    END_OPF;\n'
       + '    BEGIN_OPF(J);\n\tJTYPE;\n\tDO_BRANCH(true, target << 2, 0xF0000000, false, 0);\n    END_OPF;\n'
       + '    BEGIN_OPF(INTERRUPT);\n\tif(Halted) { goto SkipNPCStuff; }\n    END_OPF;\n'
       '}\n\nint32_t CPU_Run(PS_CPU *self, int32_t timestamp_in)\n{\n}\n')
# The handler macros of the prepared cpu.c, as the slices' header copies them (one definition each).
MACROS = ('#define GPR_DEPRES_BEGIN { uint8_t back = ReadAbsorb[0];\n#define GPR_DEPRES_BEGIN_X 1\n'
          '#define GPR_DEP(n) { ReadAbsorb[n] = 0; }\n#define GPR_RES(n) { ReadAbsorb[n] = 0; }\n'
          '#define GPR_DEPRES_END ReadAbsorb[0] = back; }\n'
          '   #define DO_LDS() { GPR[LDWhich] = LDValue; }\n'
          '   #define DO_BRANCH(arg_cond, arg_offset)\\\n\t{ PC = new_PC; \\\n\t BRANCH_DISPATCH }\n'
          '   #define ITYPE uint32_t rs = (instr >> 21) & 0x1F;\n   #define ITYPE_ZE uint32_t rs = (instr >> 21) & 0x1F;\n'
          '   #define JTYPE uint32_t target = instr & ((1 << 26) - 1);\n   #define RTYPE uint32_t rs = (instr >> 21) & 0x1F;\n')
ADDIU, LUI, ADDU, JR, NOP, LW =0x24420001, 0x3C028001, 0x00431021, 0x03E00008, 0x00000000, 0x8C420000


class NativeStepsTest(unittest.TestCase):
    def test_decode_follows_the_interpreter(self):
        table = psx_native.handlers(CPU)
        self.assertEqual(table.name(ADDIU), 'ADDIU')
        self.assertEqual(table.name(LUI), 'LUI')
        self.assertEqual(table.name(ADDU), 'ADDU')
        self.assertEqual(table.name(JR), 'JR')
        self.assertEqual(table.name(NOP), 'SLL')
        self.assertEqual(psx_native.opf(LW), 0x40 | 0x23)
        self.assertNotIn('//', table.bodies['ADDU'])
        self.assertNotIn('/*', table.bodies['ADDU'])

    def test_a_handler_that_leaves_its_body_is_refused(self):
        bad = CPU.replace('GPR[rd] = GPR[rs];\n    END_OPF;\n    BEGIN_OPF(SRL)', 'goto OpDone;\n    END_OPF;\n    BEGIN_OPF(SRL)')
        with self.assertRaises(psx_native.NativeError):
            psx_native.handlers(bad)

    def test_runs_cut_at_entered_addresses_and_gaps(self):
        table = psx_native.handlers(CPU)
        seen = psx_native.Observed
        pairs = {(0x1000, LUI): seen(5, True), (0x1004, ADDIU): seen(5), (0x1008, JR): seen(5), (0x100C, NOP): seen(5),
                 (0x1010, ADDU): seen(2, True), (0x1014, NOP): seen(2),
                 (0x1020, ADDU): seen(1, True),
                 # overlay: other words ran at 0x1004 less often: ranks 1 to 3 get their own steps, a fifth word does not
                 (0x1004, ADDU): seen(4), (0x1004, NOP): seen(3), (0x1004, LW): seen(2), (0x1004, JR): seen(1),
                 # outside RAM and the BIOS (scratchpad), never a step
                 (0x1F800000, ADDU): seen(9, True)}
        p = psx_native.plan(pairs, table)
        self.assertEqual([(start, rank) for start, rank, _ in p.steps],
                         [(0x1000, 0), (0x1010, 0), (0x1020, 0), (0x1004, 1), (0x1004, 2), (0x1004, 3)])
        self.assertEqual(p.steps[0][2], [(0x1000, LUI), (0x1004, ADDIU), (0x1008, JR), (0x100C, NOP)])
        self.assertEqual(p.steps[3][2], [(0x1004, ADDU)])
        self.assertEqual(p.instructions, 10)
        self.assertEqual(p.addresses, 7)
        self.assertEqual(p.variants_left, 1)
        self.assertEqual(p.observed_runs, 5 * 4 + 2 * 2 + 1 + 4 + 3 + 2 + 1 + 9)
        self.assertEqual(p.covered_runs, 5 * 4 + 2 * 2 + 1 + 4 + 3 + 2)

    def test_runtime_hints_join_the_observations(self):
        from retrorecomp.feedback import Observation
        pairs = {(0x1000, LUI): psx_native.Observed(5, True)}
        def block(*words):
            return b''.join(w.to_bytes(4, 'little') for w in words)
        rows = [Observation(23, 0x1000, 0b0011, block(LUI, ADDIU, JR, 0)),     # 0x1000 already observed, 0x1004 joins; the
                                                                             # words of 0x1008 and 0x100C did not run
                Observation(23, 0x1F800000, 1, block(ADDU, 0, 0, 0)),        # scratchpad: never a step
                Observation(23, 0x1004, 1, block(ADDU, 0, 0, 0)),            # not a block's address
                Observation(23, 0x2000, 1, ADDU.to_bytes(4, 'little')),      # not a block
                Observation(20, 0x2000, 1, block(ADDU, 0, 0, 0))]            # another machine's kind
        self.assertEqual(psx_native.add_hints(pairs, rows), 1)
        self.assertEqual(pairs[(0x1004, ADDIU)], psx_native.Observed(1, False))
        self.assertEqual(pairs[(0x1000, LUI)].count, 5)
        p = psx_native.plan(pairs, psx_native.handlers(CPU))
        self.assertEqual(p.steps[0][2], [(0x1000, LUI), (0x1004, ADDIU)])

    def test_long_runs_are_split(self):
        table = psx_native.handlers(CPU)
        pairs = {(0x2000 + 4 * n, NOP): psx_native.Observed(1, n == 0) for n in range(psx_native.MAX_RUN + 3)}
        p = psx_native.plan(pairs, table)
        self.assertEqual([len(run) for _, _, run in p.steps], [psx_native.MAX_RUN, 3])

    def test_observation_files_merge(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / 'a.observe', Path(folder) / 'b.observe'
            a.write_text('RRPSX-OBSERVE 1\n00001000 3c028001 4 1\n00001004 24420001 4 0\n', encoding='ascii')
            b.write_text('RRPSX-OBSERVE 1\noverflow\n00001004 24420001 3 1\n', encoding='ascii')
            pairs, overflow = psx_native.read_observations([a, b])
            self.assertTrue(overflow)
            self.assertEqual(pairs[(0x1004, ADDIU)].count, 7)
            self.assertTrue(pairs[(0x1004, ADDIU)].entered)
            (Path(folder) / 'c.observe').write_text('something else\n', encoding='ascii')
            with self.assertRaises(psx_native.NativeError):
                psx_native.read_observations([Path(folder) / 'c.observe'])

    def test_the_steps_written(self):
        seen = psx_native.Observed
        pairs = {(0x1000, LUI): seen(5, True), (0x1004, JR): seen(5), (0x1008, NOP): seen(5),
                 (0x1FC00000, LW): seen(1, True), (0x1008, ADDU): seen(2)}
        with tempfile.TemporaryDirectory() as folder:
            cpu = Path(folder) / 'cpu.c'
            cpu.write_text(MACROS + CPU, encoding='utf-8')
            out = Path(folder) / 'game'
            (out / 'rr_psx_steps_07.c').parent.mkdir()
            (out / 'rr_psx_steps_07.c').write_text('stale', encoding='utf-8')
            summary = psx_native.write(cpu, pairs, out)
            steps = (out / 'rr_psx_steps_00.c').read_text(encoding='utf-8')
            table = (out / 'rr_psx_native_table.c').read_text(encoding='utf-8')
            header = (out / 'rr_psx_shard.h').read_text(encoding='utf-8')
            self.assertFalse((out / 'rr_psx_steps_07.c').exists())
        text = steps + table
        self.assertEqual(summary['sources'], ['rr_psx_steps_00.c', 'rr_psx_native_table.c'])
        self.assertEqual(summary['steps'], 3)
        self.assertEqual(summary['instructions'], 5)
        self.assertEqual(summary['addresses_with_variants'], 1)
        self.assertEqual(summary['handlers'], ['ADDU', 'JR', 'LUI', 'LW', 'SLL'])
        # the slices compile cpu.c's head, the header holds the interpreter's macros, continuation lines included
        self.assertTrue(steps.split('*/\n', 1)[1].startswith('#define RR_PSX_SHARD 1\n#include "mednafen/psx/cpu.c"\n'))
        self.assertIn('#define DO_BRANCH(arg_cond, arg_offset)\\\n\t{ PC = new_PC; \\\n\t BRANCH_DISPATCH }\n', header)
        self.assertIn('#define GPR_DEP(n) { ReadAbsorb[n] = 0; }\n', header)
        self.assertNotIn('GPR_DEPRES_BEGIN_X', header)
        self.assertIn('int rr_psx_step_00001000(RrPsxRegs *rr);', table)
        self.assertIn('int rr_psx_step_00001000(RrPsxRegs *rr)\n{', steps)
        self.assertIn('rr_e0: RR_GUARD(0x3c028001u)', text)
        self.assertIn('RR_FETCH(0x00001004u)', text)
        self.assertIn('#define BRANCH_DISPATCH goto rr_b1;', text)
        self.assertIn('rr_b1: ;', text)
        self.assertIn('{0x1fc00000u, 1, rr_psx_step_1fc00000}', text)
        self.assertNotIn('RR_OP_SRA', text)        # only the handlers the steps use are expanded
        # the overlaid address goes through the variant table, its words in order
        self.assertIn('int rr_psx_step_00001008_1(RrPsxRegs *rr)\n{', text)
        self.assertIn('{0x00001008u, 0x00000000u, rr_psx_step_00001000},\n   {0x00001008u, 0x00431021u, '
                      'rr_psx_step_00001008_1},', text)
        # every line of a handler macro but its last continues
        macro = text[text.index('#define RR_OP_LUI'):].split('\n\n')[0].splitlines()
        self.assertTrue(all(line.endswith('\\') for line in macro))


if __name__ == '__main__':
    unittest.main()
