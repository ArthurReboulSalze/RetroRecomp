"""The authored Super FX checks: the independent model and the case table it generates.

The native run (tools/snes_superfx_selftest.py) needs the toolchain and builds the real
engine; these tests cover the Python side, so a change to the model or the library that
breaks a documented value is caught without a compiler."""
import unittest
from pathlib import Path

from retrorecomp.snes_chips import cart, cart_header, cart_header_sync, superfx, superfx_header
from tools.snes_superfx_case import Case
from tools.snes_superfx_library import (F_FMULT_R4, F_HIGH_NIBBLE, build_cases)
from tools.snes_superfx_model import (ALT1, ALT2, ALT3, Gsu, ModelError, ROM_SIZE, STOP, branch, frm, ibt,
                                      iwt, to, with_)
from tools.snes_superfx_selftest import generate_header


def run_code(code, regs=None, sfr=0, scmr=0x18, cfgr=0):
    rom = bytearray(ROM_SIZE)
    rom[:len(code)] = code
    gsu = Gsu(bytes(rom))
    gsu.scmr, gsu.cfgr = scmr, cfgr
    gsu.set_sfr_flags(sfr)
    for n, v in (regs or {}).items():
        gsu.cpu_write_reg(n, v)
    gsu.start()
    gsu.run()
    return gsu


class ModelDocumentedValues(unittest.TestCase):
    """Values worked out by hand from the fullsnes opcode tables."""

    def test_add_flags(self):
        g = run_code(frm(1) + to(2) + b'\x53' + STOP, {1: 0x7FFF, 3: 1})
        self.assertEqual((g.r[2], g.ov, g.cy, g.s, g.z), (0x8000, 1, 0, 1, 0))
        g = run_code(frm(1) + to(2) + b'\x53' + STOP, {1: 0xFFFF, 3: 1})
        self.assertEqual((g.r[2], g.ov, g.cy, g.s, g.z), (0, 0, 1, 0, 1))

    def test_sub_carry_means_no_borrow(self):
        g = run_code(frm(1) + to(2) + b'\x63' + STOP, {1: 5, 3: 6})
        self.assertEqual((g.r[2], g.cy, g.s), (0xFFFF, 0, 1))
        g = run_code(frm(1) + to(2) + b'\x63' + STOP, {1: 6, 3: 6})
        self.assertEqual((g.r[2], g.cy, g.z), (0, 1, 1))

    def test_sbc_and_cmp(self):
        g = run_code(frm(1) + to(2) + ALT1 + b'\x63' + STOP, {1: 6, 3: 6}, sfr=0)   # carry clear: borrow 1
        self.assertEqual(g.r[2], 0xFFFF)
        g = run_code(frm(1) + to(2) + ALT3 + b'\x63' + STOP, {1: 6, 3: 6, 2: 0x1234})
        self.assertEqual((g.r[2], g.z, g.cy), (0x1234, 1, 1))

    def test_merge_flags_follow_the_table(self):
        g = run_code(b'\x70' + STOP, {7: 0x1234, 8: 0x5678})
        self.assertEqual(g.r[0], 0x1256)
        self.assertEqual((g.s, g.ov, g.cy, g.z), (0, 1, 1, 1))      # 1256 & C0C0, E0E0, F0F0 are all non-zero
        g = run_code(b'\x70' + STOP, {7: 0x8000, 8: 0x0000})
        self.assertEqual((g.s, g.ov, g.cy, g.z), (1, 1, 1, 1))

    def test_div2_maps_minus_one_to_zero(self):
        g = run_code(frm(1) + to(2) + ALT1 + b'\x96' + STOP, {1: 0xFFFF})
        self.assertEqual(g.r[2], 0)
        g = run_code(frm(1) + to(2) + b'\x96' + STOP, {1: 0xFFFF})
        self.assertEqual(g.r[2], 0xFFFF)

    def test_multipliers(self):
        g = run_code(frm(1) + to(2) + b'\x83' + STOP, {1: 0x00FF, 3: 0x0002})            # -1 * 2
        self.assertEqual(g.r[2], 0xFFFE)
        g = run_code(frm(1) + to(2) + ALT1 + b'\x83' + STOP, {1: 0x00FF, 3: 0x0002})     # 255 * 2
        self.assertEqual(g.r[2], 0x01FE)
        g = run_code(frm(1) + to(2) + ALT1 + b'\x9f' + STOP, {1: 0x4000, 6: 0x4000})     # LMULT
        self.assertEqual((g.r[4], g.r[2]), (0, 0x1000))
        g = run_code(frm(1) + to(2) + b'\x9f' + STOP, {1: 0x8000, 6: 0x8000})
        self.assertEqual(g.r[2], 0x4000)

    def test_multiplier_clock_extras(self):
        g = run_code(frm(1) + to(2) + b'\x9f' + STOP, {1: 1, 6: 1})
        self.assertEqual(g.mult_extra, 7)
        g = run_code(frm(1) + to(2) + b'\x9f' + STOP, {1: 1, 6: 1}, cfgr=0x20)
        self.assertEqual(g.mult_extra, 3)

    def test_branch_delay_slot_and_target(self):
        # BRA +2: the delay slot INC R1 runs, INC R2 is skipped, INC R3 is the target
        g = run_code(branch(5, 2) + b'\xd1\xd2\xd3' + STOP)
        self.assertEqual((g.r[1], g.r[2], g.r[3]), (1, 0, 1))
        # stop leaves R15 at the address of STOP plus two
        self.assertEqual(g.r[15], 7)

    def test_link_uses_the_next_opcode_address(self):
        g = run_code(b'\x94' + STOP)
        self.assertEqual(g.r[11], 1 + 4)

    def test_rom_buffer_keeps_the_old_bank_after_romb(self):
        rom = bytearray(ROM_SIZE)
        code = iwt(14, 0x2000) + ibt(5, 1) + frm(5) + ALT3 + b'\xdf' + to(6) + b'\xef' + STOP
        rom[:len(code)] = code
        rom[0x2000] = 0xA5
        rom[0x8000 + 0x2000 - 0x2000] = 0x11
        g = Gsu(bytes(rom))
        g.start()
        g.run()
        self.assertEqual(g.r[6], 0xA5)

    def test_pixel_layout_and_tiles(self):
        g = run_code(ibt(6, 1) + frm(6) + b'\x4e' + ibt(1, 9) + ibt(2, 10) + b'\x4c' + STOP, scmr=0x19)
        # 4bpp, 128 high: tile (9/8)*16 + 10/8 = 17, row 10 & 7 = 2, plane 0 byte, bit 7-(9&7)=6
        self.assertEqual(g.ram[17 * 32 + 2 * 2], 0x40)
        self.assertEqual(g.r[1], 10)
        g = run_code(ibt(6, 1) + frm(6) + b'\x4e' + ibt(1, 0x81) + ibt(2, 0x82) + b'\x4c' + STOP, scmr=0x3D)
        # OBJ layout: (y/80h)*200h + (x/80h)*100h + (y/8 & F)*10h + (x/8 & F)
        self.assertEqual(g.ram[0x300 * 32 + 2 * 2], 0x40)

    def test_dither_and_transparency(self):
        code = ibt(6, 0x30) + frm(6) + b'\x4e' + ibt(5, 3) + frm(5) + ALT1 + b'\x4e' + ibt(1, 0) + ibt(2, 0) + b'\x4c\x4c' + STOP
        g = run_code(code, scmr=0x19)
        # POR 3 = dither + plot colour 0: pixel 0 (XOR 0) uses COLOR & F = 0, pixel 1 (XOR 1) uses COLOR/10h = 3
        self.assertEqual((g.ram[0], g.ram[1]), (0x40, 0x40))

    def test_untimed_opcodes_are_refused_for_timed_cases(self):
        with self.assertRaises(ModelError):
            Case('x', b'\x4c' + STOP, mode='warm', timed=True).expect()


class LibraryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = build_cases()

    def test_names_are_unique_and_the_suite_is_substantial(self):
        names = [case.name for case in self.cases]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreater(len(names), 2500)

    def test_every_case_runs_in_the_model(self):
        for case in self.cases:
            case.expect()
            self.assertFalse(case.exp.running, case.name)

    def test_findings_are_tied_to_the_cases_that_expose_them(self):
        by_finding = {}
        for case in self.cases:
            if case.finding:
                by_finding.setdefault(case.finding, []).append(case.name)
        self.assertEqual(sorted(by_finding), [1, 2, 3, 4, 5, 7, 8, 9])
        self.assertTrue(all(n.startswith('plot_highnibble') for n in by_finding[F_HIGH_NIBBLE]))
        self.assertTrue(all(n.startswith('mul_fmult_r4') for n in by_finding[F_FMULT_R4]))

    def test_regimes_are_all_present(self):
        modes = {case.mode for case in self.cases}
        self.assertEqual(modes, {'cold', 'warm', 'rom'})
        self.assertTrue(any(case.timed == 1 for case in self.cases))
        self.assertTrue(any(case.timed == 2 for case in self.cases))
        self.assertTrue(any(case.resume for case in self.cases))
        self.assertTrue(any(case.clsr for case in self.cases))

    def test_header_generation_is_deterministic(self):
        first, _ = generate_header(build_cases())
        second, _ = generate_header(build_cases())
        self.assertEqual(first, second)
        self.assertIn('static const RrGsuCase rr_gsu_cases[]', first)


class EngineAdaptation(unittest.TestCase):
    SOURCE = Path(__file__).resolve().parents[1] / '.deps/snesrecomp/runner/src/snes/superfx.c'

    @unittest.skipUnless(SOURCE.is_file(), 'pinned engine checkout not present')
    def test_code_cache_window_follows_fullsnes(self):
        text = self.SOURCE.read_text(encoding='utf-8')
        adapted = superfx(text)
        self.assertEqual(adapted.count('(uint16_t)(a - f->cbr) & 511'), 2)
        self.assertNotIn('(uint16_t)(a + f->cbr) & 511', adapted)

    @unittest.skipUnless(SOURCE.is_file(), 'pinned engine checkout not present')
    def test_catch_up_shortcuts_are_the_exact_ones(self):
        """The shortcuts that make a sync call cheap: banked credit, the stopped GSU's remainder,
        the inline clock charge, the instruction ring behind a macro. Anchors only; the
        behaviour is checked natively (selftest invariance runs) and by identical game hashes."""
        text = self.SOURCE.read_text(encoding='utf-8')
        adapted = superfx(text)
        self.assertIn('f->clock_credit-=(f->clock_credit/6)*6;', adapted)
        self.assertIn('!(f->sfr&SFR_G) && !f->romcl && !f->ramcl', adapted)
        self.assertIn('f->clock_credit/6<=2000000', adapted)
        self.assertIn('static void step_clocks_slow(SuperFx *f, unsigned clocks) {\n  if (f->romcl) {', adapted)
        self.assertIn('if (f->romcl | f->ramcl) { step_clocks_slow(f, clocks); return; }', adapted)
        self.assertEqual(adapted.count('#ifdef RR_GSU_TRACE'), 1)
        self.assertNotIn('trace->sequence=sequence;\n  trace->r15', adapted)
        header = superfx_header(self.SOURCE.with_suffix('.h').read_text(encoding='utf-8'))
        self.assertIn('static inline void superfx_sync_credit(SuperFx *fx, uint64_t master_clock) {', header)
        self.assertIn('if (credit < 6)', header)
        cart_h = (self.SOURCE.parent / 'cart.h').read_text(encoding='utf-8')
        sync = cart_header_sync(cart_header(cart_h))
        self.assertIn('cart_sync_coprocessors_device', sync)
        self.assertIn('if (cart && cart->superfx) superfx_sync_credit(cart->superfx, master_clock);', sync)
        self.assertIn('#include "superfx.h"', sync)
        cart_c = cart((self.SOURCE.parent / 'cart.c').read_text(encoding='utf-8'))
        self.assertEqual(cart_c.count('void cart_sync_coprocessors_device(Cart *cart, uint64_t master_clock) {'), 1)
        self.assertNotIn('\nvoid cart_sync_coprocessors(Cart *cart', cart_c)


if __name__ == '__main__':
    unittest.main()
