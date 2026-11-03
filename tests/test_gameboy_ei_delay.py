"""The delay of EI (retrorecomp/gameboy_runtime.py: adapt_ei_delay and its two companions) on synthetic sources, and the reproducer
authored in tools/gameboy_ei_check.py. No ROM, no compiler: the behaviour itself is checked by the vectors
(tools/gameboy_sm83_vector_selftest.py) and by the reproducer on a converted cartridge."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from retrorecomp import gameboy_runtime as runtime
from retrorecomp.core import ConversionError

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location('gameboy_ei_check', TOOLS / 'gameboy_ei_check.py')
check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check)

TICK = '        ' + runtime.EI_PROMOTE + '\n        return;\n'
HEAD = 'void gb_tick(GBContext* ctx, uint32_t cycles) {\n    static uint32_t last_log = 0;\n#ifdef X\n'
STUBS = ('        case 0xF3: /* DI */\n            ctx->ime = 0;\n            ctx->pc = (uint16_t)(addr + 1);\n'
         '        case 0xFB: /* EI */\n            ctx->ime = 1;\n            ctx->pc = (uint16_t)(addr + 1);\n'
         'void gbrt_execute_halt(GBContext* ctx, uint16_t next_pc, uint32_t cycles) {\n    ctx->pc = next_pc;\n'
         '    if (!ctx->ime &&\n        (gb_read8(ctx, 0xFFFF) & gb_read8(ctx, 0xFF0F) & 0x1F)) {\n        ctx->halted = 0;\n        ctx->halt_bug = 1;\n    }\n}\n'
         'void gb_handle_interrupts(GBContext* ctx) {\n    if (pending) {\n'
         '        ctx->ime = 0; ctx->halted = 0; ctx->stop_mode_active = 0;\n        const uint16_t return_pc = ctx->pc;\n    }\n}\n')


class RuntimePatchTests(unittest.TestCase):
    def test_the_promotion_moves_from_the_three_ends_to_the_start_and_the_two_stub_cases_are_rewritten(self):
        out = runtime.adapt_ei_delay(HEAD + TICK * 3 + STUBS)
        self.assertEqual(out.count(runtime.EI_PROMOTE_FIRST), 1)
        self.assertNotIn(runtime.EI_PROMOTE, out)
        self.assertLess(out.index(runtime.EI_PROMOTE_FIRST), out.index('#ifdef X'))     # before anything else in the tick
        self.assertEqual(out.count('        return;\n'), 3)
        self.assertIn('case 0xF3: /* DI */\n            ctx->ime = 0;\n            ctx->ime_pending = 0;\n', out)
        self.assertIn('case 0xFB: /* EI */\n            ' + runtime.EI_ARM_ONCE + '\n', out)
        self.assertNotIn('ctx->ime = 1;\n            ctx->pc', out)

    def test_ei_then_halt_is_not_the_halt_bug_and_the_dispatch_clears_the_armed_flag(self):
        out = runtime.adapt_ei_delay(HEAD + TICK * 3 + STUBS)
        # the HALT bug needs IME off with nothing about to turn it on: an armed EI (2) is about to
        self.assertIn('if (!ctx->ime && ctx->ime_pending != 2 &&\n        (gb_read8(ctx, 0xFFFF)', out)
        # an interrupt taken with the flag armed must not see IME switched back on in the middle of the dispatch
        self.assertIn('ctx->ime = 0; ctx->ime_pending = 0; ctx->halted = 0; ctx->stop_mode_active = 0;', out)
        with self.assertRaises(Exception):
            runtime.adapt_ei_delay((HEAD + TICK * 3 + STUBS).replace('ctx->halt_bug = 1;', 'ctx->halt_bug = 2;'))    # a changed upstream is refused

    def test_a_changed_upstream_is_refused_not_guessed(self):
        with self.assertRaises(ConversionError):
            runtime.adapt_ei_delay(HEAD + TICK * 2 + STUBS)               # two promotions: the runtime is not the pinned one
        with self.assertRaises(Exception):
            runtime.adapt_ei_delay(HEAD + TICK * 3 + STUBS.replace('/* EI */', '/* EI! */'))

    def test_the_promotion_takes_two_ticks_and_a_di_cancels_it(self):
        # the rule the C text states, run on its own: 1 -> 2 on EI's tick, 2 -> IME on the next
        state = {'ime': 0, 'pending': 0}

        def tick():
            if state['pending']:
                if state['pending'] == 1:
                    state['pending'] = 2
                else:
                    state['ime'], state['pending'] = 1, 0

        def ei():
            if not state['pending']:
                state['pending'] = 1
        ei(); tick()
        self.assertEqual(state, {'ime': 0, 'pending': 2})                 # after EI: no IME yet
        tick()
        self.assertEqual(state, {'ime': 1, 'pending': 0})                 # after the next instruction's tick
        state.update(ime=0, pending=0)
        ei(); tick(); ei(); tick()                                        # EI ; EI: the second leaves the armed flag alone
        self.assertEqual(state['ime'], 1)
        state.update(ime=0, pending=0)
        ei(); tick(); state['pending'] = 0                                # EI ; DI
        tick()
        self.assertEqual(state['ime'], 0)

    def test_the_interpreter_case_is_rewritten(self):
        out = runtime.adapt_ei_delay_interpreter('x\n            case 0xFB: ctx->ime_pending = 1; break; /* EI */\ny')
        self.assertIn('case 0xFB: ' + runtime.EI_ARM_ONCE + ' break; /* EI */', out)
        with self.assertRaises(Exception):
            runtime.adapt_ei_delay_interpreter('no such case')


class GeneratedSourceTests(unittest.TestCase):
    def test_every_arming_is_guarded_and_a_second_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder)
            (project / 'game_funcs_0.c').write_text('/* 042c */     ctx->ime_pending = 1;\n/* 0781 */     ctx->ime_pending = 1;\n', encoding='utf-8')
            (project / 'game_funcs_1.c').write_text('no EI here\n', encoding='utf-8')
            (project / 'game.c').write_text('ctx->ime_pending = 1;\n', encoding='utf-8')      # not a generated body: left alone
            self.assertEqual(runtime.adapt_ei_delay_generated(project), 2)
            text = (project / 'game_funcs_0.c').read_text(encoding='utf-8')
            self.assertEqual(text.count(runtime.EI_ARM_ONCE), 2)
            self.assertEqual((project / 'game.c').read_text(encoding='utf-8'), 'ctx->ime_pending = 1;\n')
            self.assertEqual(runtime.adapt_ei_delay_generated(project), 2)
            self.assertEqual((project / 'game_funcs_0.c').read_text(encoding='utf-8'), text)


class ReproducerTests(unittest.TestCase):
    def test_the_program_fits_before_its_interrupt_routine(self):
        code, extra = check.program()
        self.assertLess(0x150 + len(code), 0x200)
        self.assertEqual(sorted(extra), [0x40, 0x200, 0x2FF, 0x300, 0x400, 0x1000])

    def test_the_cartridge_has_a_valid_header_and_no_mapper(self):
        rom = check.authored_rom()
        self.assertEqual((len(rom), rom[0x147], rom[0x149]), (0x8000, 0, 0))
        checksum = 0
        for index in range(0x134, 0x14D):
            checksum = (checksum - rom[index] - 1) & 0xFF
        self.assertEqual(rom[0x14D], checksum)

    def test_the_cases_say_what_the_console_does(self):
        self.assertEqual({index: expected for _text, index, expected in check.CASES},
                         {0: 1, 1: 1, 2: 0, 3: 2, 4: 1, 5: 1, 6: 5, 7: 1, 8: 6, 9: 0xFC, 10: 0xFF})


if __name__ == '__main__':
    unittest.main()
