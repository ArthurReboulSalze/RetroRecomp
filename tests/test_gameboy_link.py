"""The Game Boy link cable (native/gb_link.h, the serial patches of retrorecomp/gameboy_runtime.py, the link part of native/hostkit/adapters/rrhk_gb.inc):
what the text of each part promises. No ROM, no compiler. The behaviour itself is checked by tools/gameboy_link_selftest.py (authored programs on two
consoles of one process) and by tools/gameboy_link_play.py (two consoles on a real game, scripted pads)."""
import unittest

from retrorecomp import gameboy_runtime as runtime
from retrorecomp.paths import ASSETS

LINK = (ASSETS / 'native/gb_link.h').read_text(encoding='utf-8')
ADAPTER = (ASSETS / 'native/hostkit/adapters/rrhk_gb.inc').read_text(encoding='utf-8')
SOURCE = (ASSETS / 'retrorecomp/gameboy_runtime.py').read_text(encoding='utf-8')

SERIAL_TICK = '''static void gb_serial_tick(GBContext* ctx, uint32_t cpu_cycles) {
    if (!ctx->serial_transfer.active) {
        return;
    }
    if (cpu_cycles >= ctx->serial_transfer.cycles_remaining) {
        uint8_t outgoing = ctx->io[0x01];
        ctx->serial_transfer.active = 0;
        ctx->serial_transfer.cycles_remaining = 0;
        ctx->io[0x02] &= (uint8_t)~0x80;
        ctx->io[0x01] = 0xFF;
        ctx->io[0x0F] |= 0x08;
    }
}
uint32_t gb_run_cycles(GBContext* ctx, uint32_t max_cycles) {
    uint32_t start = ctx->cycles;
    return 0;
}
'''


class RuntimePatchTests(unittest.TestCase):
    def test_the_end_of_a_master_transfer_reads_the_cable_and_nothing_else_moves(self):
        out = runtime.adapt_link_cable(SERIAL_TICK)
        self.assertIn('ctx->io[0x01] = rr_gb_link_exchange(ctx, outgoing);', out)
        self.assertNotIn('ctx->io[0x01] = 0xFF;', out)
        self.assertIn('ctx->io[0x0F] |= 0x08;', out)                         # the master's own interrupt is still raised there
        self.assertLess(out.index('static uint8_t rr_gb_link_exchange'), out.index('static void gb_serial_tick'))

    def test_gb_run_cycles_keeps_its_body_for_a_console_with_no_link(self):
        out = runtime.adapt_link_cable(SERIAL_TICK)
        self.assertIn('if (rr_gb_link_runs(ctx)) return rr_gb_link_run(ctx, max_cycles);', out)
        self.assertIn('return rr_gb_run_cycles_one(ctx, max_cycles);', out)
        self.assertTrue(out.rstrip().endswith('uint32_t start = ctx->cycles;\n    return 0;\n}'))   # the original body follows the new head unchanged

    def test_a_changed_upstream_is_refused(self):
        with self.assertRaises(Exception):
            runtime.adapt_link_cable('int x;\n')
        with self.assertRaises(Exception):
            runtime.adapt_link_cable(runtime.adapt_link_cable(SERIAL_TICK))      # a second application does not find its markers

    def test_the_runtime_part_is_copied_and_included_after_the_machine_state(self):
        self.assertIn("('gb_link.h', project / 'runtime/include/gb_link.h')", SOURCE)
        self.assertIn('#include "gb_machine_state.h"\\n#include "gb_link.h"', SOURCE)
        self.assertIn('gb_link_set_init(game_init);', SOURCE)                    # the generated init makes the satellites


class CableTextTests(unittest.TestCase):
    def test_the_cable_is_a_byte_swap_between_a_master_and_an_armed_slave(self):
        body = LINK[LINK.index('static uint8_t rr_gb_link_exchange('):LINK.index('/* Runs a satellite up to')]
        self.assertIn('(peer->io[0x02] & 0x81) != 0x80', body)               # armed: bit 7 set, external clock
        self.assertIn('return 0xFF', body)                                   # nobody armed: as with no cable
        self.assertIn('peer->io[0x0F] |= 0x08', body)                        # the slave's serial interrupt
        self.assertIn('peer->io[0x02] &= (uint8_t)~0x80', body)

    def test_the_interleave_is_fixed_and_depends_on_the_consoles_only(self):
        body = LINK[LINK.index('static uint32_t rr_gb_link_run('):]
        self.assertIn('RR_GB_LINK_CHUNK', body)
        self.assertIn('total_cycles', LINK)
        for forbidden in ('SDL_', 'clock(', 'time(', 'rand'):
            self.assertNotIn(forbidden, LINK)                                # nothing of this PC enters the schedule

    def test_a_satellite_reads_and_writes_no_file(self):
        body = LINK[LINK.index('bool gb_link_start('):LINK.index('static bool rr_gb_link_runs(')]
        self.assertIn('ignore_rtc_persistence = true', body)
        self.assertNotIn('save_id', body)


class AdapterTextTests(unittest.TestCase):
    def test_the_snapshot_and_the_digest_cover_every_console_in_seat_order(self):
        self.assertIn('one * (size_t)rr_gb_link_consoles_planned()', ADAPTER)
        save = ADAPTER[ADAPTER.index('static size_t rr_gb_snap_save_adapter('):ADAPTER.index('static bool rr_gb_snap_load_adapter(')]
        self.assertIn('rr_gb_one_save((int)i,', save)
        digest = ADAPTER[ADAPTER.index('static uint64_t rr_gb_digest_adapter('):ADAPTER.index('/* ---- the palette')]
        self.assertIn('for (int index = 1; index < gb_link_count(); ++index)', digest)

    def test_seat_i_drives_console_i_and_this_pc_shows_its_own_seat(self):
        self.assertIn('rr_gb_link_apply_pad(1, p2)', ADAPTER)
        self.assertIn('view = rrhk_session_seat()', ADAPTER)
        self.assertIn('if (!rr_gb_link_shown(ctx)) return;', ADAPTER)        # only the shown console is heard
        self.assertIn('gb_get_framebuffer(gb_link_context(g_rr_link_view))', ADAPTER)

    def test_a_link_is_the_setup_flag_with_a_port_per_seat_and_never_more_than_two_consoles(self):
        body = ADAPTER[ADAPTER.index('static int rr_gb_link_consoles_wanted('):ADAPTER.index('static int rr_gb_link_consoles_planned(void) {')]
        self.assertIn('rrhk_session_link()', body)                           # the SETUP flag, never the port count alone
        self.assertIn('rrhk_session_ports()', body)
        self.assertIn('ports >= 2 ? 2 : 0', body)
        self.assertIn('rr_gb_machine.link_consoles = 2;', ADAPTER)                # HELLO says RRHK_CAP_LINK

    def test_the_test_hooks_of_a_headless_run_are_never_read_by_a_window(self):
        self.assertIn('static bool rr_gb_link_headless(void) { return g_benchmark_mode || !rrhk_window(); }', ADAPTER)
        for name in ('RETRO_RECOMP_GB_LINK', 'RETRO_RECOMP_GB_LINK_VIEW', 'RETRO_RECOMP_GB_LINK_SCRIPT'):
            self.assertIn(name, ADAPTER)
        wanted = ADAPTER[ADAPTER.index('static int rr_gb_link_consoles_wanted('):ADAPTER.index('static int rr_gb_link_consoles_planned(void) {')]
        self.assertLess(wanted.index('rrhk_session_active()'), wanted.index('RETRO_RECOMP_GB_LINK'))
        self.assertIn('if (rr_gb_link_headless())', wanted)

    def test_every_console_starts_from_the_state_the_game_began_in(self):
        begin = ADAPTER[ADAPTER.index('static void rr_gb_session_begin('):ADAPTER.index("/* The match's cartridge RAM")]
        self.assertIn('rr_gb_link_begin()', begin)
        self.assertLess(begin.index('rr_gb_one_load(i, g_rr_pristine.data()'), begin.index('rr_gb_session_begin_console(rr_gb_console(i), clock)'))


if __name__ == '__main__':
    unittest.main()
