"""The Game Boy machine's snapshot and digest (native/gb_machine_state.h, native/gb_digest.h): the patch that adds the sound unit's digest, and what the
text of the runtime part promises. No ROM, no compiler. The behaviour itself is checked by tools/gameboy_machine_selftest.py (authored cartridges
replayed from snapshots, whole-state hashes, refusals, sensitivity of the digest)."""
import unittest

from retrorecomp import gameboy_hardware as hardware
from retrorecomp import gameboy_runtime as runtime
from retrorecomp.paths import ASSETS

STATE = (ASSETS / 'native/gb_machine_state.h').read_text(encoding='utf-8')
DIGEST = (ASSETS / 'native/gb_digest.h').read_text(encoding='utf-8')
AUDIO = 'int x;\nsize_t gb_audio_state_size(void) {\n    return sizeof(GBAudio);\n}\n'


class AudioDigestPatchTests(unittest.TestCase):
    def test_the_digest_is_added_before_the_state_size_function_and_nothing_else_moves(self):
        out = hardware.adapt_audio_digest(AUDIO)
        self.assertTrue(out.startswith('int x;\n#include "gb_digest.h"'))
        self.assertIn('void rr_gb_audio_digest(const void* audio, RrGbDigest* d) {', out)
        self.assertTrue(out.endswith('size_t gb_audio_state_size(void) {\n    return sizeof(GBAudio);\n}\n'))

    def test_every_field_of_every_channel_is_named(self):
        text = hardware.AUDIO_DIGEST
        for field in ('ch1.sweep_timer', 'ch1.shadow_freq', 'ch2.wave_pos', 'ch3.wave_ram', 'ch4.lfsr', 'ch4.accum', 'fs_timer', 'fs_step',
                      'sample_phase', 'hp_prev_out_r', 'last_output_left'):
            self.assertIn('apu->' + field, text, field)
        self.assertNotIn('memcpy', text)          # never the raw struct

    def test_a_changed_upstream_is_refused(self):
        with self.assertRaises(Exception):
            hardware.adapt_audio_digest('int x;\n')
        with self.assertRaises(Exception):
            hardware.adapt_audio_digest(hardware.adapt_audio_digest(AUDIO))       # a second application does not find its marker


class MachineStateTextTests(unittest.TestCase):
    def test_the_runtime_part_is_appended_last_and_copied_with_its_header(self):
        source = (ASSETS / 'retrorecomp/gameboy_runtime.py').read_text(encoding='utf-8')
        self.assertIn("('gb_digest.h', project / 'runtime/include/gb_digest.h')", source)
        self.assertIn("('gb_machine_state.h', project / 'runtime/include/gb_machine_state.h')", source)
        self.assertIn("source += '\\n#include \"gb_machine_state.h\"\\n#include \"gb_link.h\"\\n'", source)
        for prototype in ('size_t rr_gb_snap_bound(', 'size_t rr_gb_snap_save(', 'bool rr_gb_snap_load(', 'uint64_t rr_gb_digest('):
            self.assertIn(prototype, source)

    def test_the_digest_is_by_named_fields_never_a_raw_struct(self):
        body = STATE[STATE.index('uint64_t rr_gb_digest('):]
        self.assertNotIn('memcpy', body)
        self.assertNotIn('sizeof(GBContext)', body)
        for field in ('ctx->af', 'ctx->total_cycles', 'ctx->dma.cycles_remaining', 'ctx->hdma.blocks_remaining', 'ctx->rtc.last_time',
                      'ctx->audio_pending_cpu_cycles', 'ctx->rom_bank', 'ctx->wram', 'ctx->eram'):
            self.assertIn(field, body, field)
        for left_out in ('performance_counters', 'total_interpreter', 'interpreter_hotspots', 'rgb_framebuffer'):
            self.assertNotIn(left_out, body, left_out)

    def test_a_snapshot_does_not_synchronise_the_sound_unit(self):
        save = STATE[STATE.index('size_t rr_gb_snap_save('):STATE.index('bool rr_gb_snap_load(')]
        self.assertNotIn('gbrt_audio_sync', save)         # taking a snapshot never changes the future
        self.assertIn('audio_pending_cpu_cycles', save)   # the unit's lazy bookkeeping is part of the snapshot instead

    def test_the_digest_helpers_are_little_endian_and_one_value_at_a_time(self):
        self.assertIn('rr_gb_dg_u8(d, (uint8_t)v); rr_gb_dg_u8(d, (uint8_t)(v >> 8))', DIGEST)
        self.assertIn('0xcbf29ce484222325ull', DIGEST)


class SessionAdapterTextTests(unittest.TestCase):
    """What the adapter promises the host kit's session (rrhk_gb.inc and the patch of the persistence in gameboy_host.py)."""
    ADAPTER = (ASSETS / 'native/hostkit/adapters/rrhk_gb.inc').read_text(encoding='utf-8')
    HOST = (ASSETS / 'retrorecomp/gameboy_host.py').read_text(encoding='utf-8')

    def test_the_machine_announces_its_snapshot_digest_clock_and_effects(self):
        for field in ('snap_bound = rr_gb_snap_bound_adapter', 'snap_save = rr_gb_snap_save_adapter', 'snap_load = rr_gb_snap_load_adapter',
                      'digest = rr_gb_digest_adapter', 'side_effects = rr_gb_side_effects', 'session_begin = rr_gb_session_begin'):
            self.assertIn(field, self.ADAPTER, field)

    def test_the_session_clock_replaces_the_hosts_time(self):
        body = self.ADAPTER[self.ADAPTER.index('static void rr_gb_session_begin_console('):self.ADAPTER.index('static void rr_gb_side_effects(')]
        self.assertIn('rtc_unix_time_override_enabled = true', body)
        self.assertIn('rtc_unix_time_override = clock', body)
        self.assertNotIn('time(', body)           # never this PC's time

    def test_a_silent_frame_has_no_sound_and_no_picture_and_a_session_frame_is_one_whole_frame(self):
        self.assertIn('rrhk_session_silent() || g_rr_pcm.size()', self.ADAPTER)
        self.assertIn('!rrhk_window() || rrhk_session_silent()) return;', self.ADAPTER)
        self.assertIn('g_smooth_lcd_transitions && !rrhk_session_active()', self.ADAPTER)

    def test_the_cartridge_files_are_written_only_when_effects_are_allowed(self):
        self.assertIn('if (!g_rr_effects) return true;', self.HOST)
        self.assertLess(self.HOST.index('if (!g_rr_effects) return true;'), self.HOST.index('if (!ensure_parent_directory(destination)) return false;'))

    def test_the_snapshot_has_one_size_for_every_game_so_the_session_can_ask_it_before_the_context_exists(self):
        self.assertIn('RR_GB_ERAM_MAX', STATE)
        bound = STATE[STATE.index('size_t rr_gb_snap_bound('):STATE.index('static bool rr_gb_snap_ready(')]
        self.assertNotIn('ctx->eram_size', bound)

    def test_the_profile_is_in_the_session_in_input_sharing_only(self):
        from retrorecomp.systems import get_profile
        profile = get_profile('gb')
        self.assertTrue(profile.netplay_session)
        self.assertTrue(profile.netplay_shared_only)


class SessionSaveTextTests(unittest.TestCase):
    """The host's cartridge RAM travels to every seat (session ABI 8): rrhk_gb.inc."""
    ADAPTER = (ASSETS / 'native/hostkit/adapters/rrhk_gb.inc').read_text(encoding='utf-8')

    def test_the_machine_announces_the_save_pair(self):
        self.assertIn('session_save = rr_gb_session_save', self.ADAPTER)
        self.assertIn('session_save_put = rr_gb_session_save_put', self.ADAPTER)

    def test_the_host_save_is_read_from_its_file_because_the_kit_asks_before_the_game_has_loaded(self):
        body = self.ADAPTER[self.ADAPTER.index('static size_t rr_gb_session_save('):self.ADAPTER.index('static bool rr_gb_session_save_put(')]
        self.assertIn('g_persistence_dir', body)
        self.assertIn('".sav"', body)
        self.assertNotIn('g_registered_ctx', body)         # the context has no cartridge RAM yet at that moment
        for size in ('512', '2048', '8192', '32768', '65536', '131072'):
            self.assertIn(size, self.ADAPTER[self.ADAPTER.index('static bool rr_gb_save_size_valid('):self.ADAPTER.index('static size_t rr_gb_session_save(')])

    def test_every_seat_starts_again_from_the_state_the_game_began_in(self):
        begin = self.ADAPTER[self.ADAPTER.index('static void rr_gb_session_begin_console('):self.ADAPTER.index('static void rr_gb_side_effects(')]
        self.assertLess(begin.index('g_rr_session_image'), begin.index('rtc_unix_time_override_enabled'))   # the match's save, then the clock
        self.assertLess(begin.index('rr_gb_one_load(i, g_rr_pristine'), begin.index('rr_gb_session_begin_console(rr_gb_console(i)'))   # the power-on first
        begin = begin[begin.index('static void rr_gb_session_begin_console('):]
        self.assertIn('memset(ctx->eram, 0, ctx->eram_size)', begin)                               # no save: every seat blank
        wait = self.ADAPTER[self.ADAPTER.index('bool gb_platform_wait_while_menu('):]
        self.assertIn('rrhk_session_active()', wait)
        self.assertIn('rr_gb_one_save(0, g_rr_pristine.data()', wait)


    def test_the_host_writes_its_save_back_once_at_a_clean_end_with_a_backup_and_an_atomic_transaction(self):
        self.assertIn('session_save_commit = rr_gb_session_save_commit', self.ADAPTER)
        body = self.ADAPTER[self.ADAPTER.index('static bool rr_gb_session_save_commit('):self.ADAPTER.index('/* What a frame may do outside the machine:')]
        self.assertLess(body.index('".bak"'), body.index('write_persistence_transaction(file'))     # the previous file is kept first
        self.assertIn('copy_options::overwrite_existing', body)
        self.assertIn('return false; }', body[body.index('.bak'):])                              # no backup, no write
        self.assertIn('g_rr_effects = true', body)                                                 # the one write the gate lets through
        self.assertIn('g_rr_effects = before', body)
        self.assertNotIn('rtc', body.lower())                                                      # the clock stays the session's


if __name__ == '__main__':
    unittest.main()
