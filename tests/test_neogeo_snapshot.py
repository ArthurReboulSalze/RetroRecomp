"""Neo Geo in a multiplayer match: the adapter's snapshot, digest and session hooks, and the probe on a game the player converted.

The determinism of the snapshot itself needs a converted game (never in the repository): `tools/neogeo_snapshot_probe.py`, run here
when RR_NG_PROBE_EXE names an export. Without one, the tests read the sources for what a snapshot must never do.
"""
import os
import re
import unittest
from pathlib import Path

from retrorecomp.systems import get_profile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'native'


def read(name):
    return (NATIVE / name).read_text(encoding='utf-8')


class AdapterTests(unittest.TestCase):
    def test_the_adapter_answers_a_session(self):
        adapter = read('hostkit/adapters/rrhk_ng.c')
        for field in ('.snap_bound', '.snap_save', '.snap_load', '.digest', '.side_effects', '.session_begin', '.session_option', '.session_options'):
            self.assertIn(field, adapter)
        self.assertTrue(get_profile('ng').netplay_session)
        self.assertFalse(get_profile('ng').netplay_portable)

    def test_the_clock_mode_and_the_machine_are_run_changing_rows(self):
        adapter = read('hostkit/adapters/rrhk_ng.c')
        self.assertIn('rrhk_option_row_run(rows, SDL_SCANCODE_F5', adapter)
        self.assertIn('rrhk_option_row_run(rows, SDL_SCANCODE_F11', adapter)
        # The host's values (session ABI 6): this PC's are written as key=value lines, the host's are applied at SETUP.
        self.assertIn(r'"clock=%s\nsystem=%s"', adapter)
        for key in ('"clock"', '"system"', '"enhanced"', '"standard"', '"mvs"', '"aes"'):
            self.assertIn(key, adapter)
        # A machine cannot change in the middle of a session: only the one running is honoured.
        self.assertIn('(value[0] == \'a\') == (rr_ng_aes() != 0)', adapter)
        self.assertNotIn('RETRORECOMP_NETPLAY_PIPE', adapter + read('neogeo_main.c'))

    def test_the_session_pipe_name_is_the_kits(self):
        session = (NATIVE / 'hostkit/hostkit_session.h').read_text(encoding='utf-8')
        self.assertIn('#define RRHK_SESSION_ENV "RETRORECOMP_NETPLAY_PIPE"', session)


class SnapshotSourceTests(unittest.TestCase):
    def snapshot_text(self):
        state = read('neogeo_state.c')
        return state[state.index('Multiplayer snapshot'):]

    def test_a_snapshot_allocates_nothing_and_leaves_the_picture_out(self):
        text = self.snapshot_text()
        for call in ('malloc', 'calloc', 'realloc', 'free(', 'rr_ng_visible_pixels', 'fopen', 'rr_fopen'):
            self.assertNotIn(call, text, call)

    def test_it_carries_the_latches_the_f8_state_carries(self):
        text = self.snapshot_text()
        for call in ('geo_state_save_raw', 'geo_state_load_raw', 'rr_ng_cpu_extra_save', 'rr_ng_ym_extra_save', 'rr_ng_board_extra_save',
                     'rr_ng_lspc_extra_save', 'rr_ng_cpu_extra_restore', 'rr_ng_ym_extra_restore', 'rr_ng_board_extra_restore',
                     'rr_ng_lspc_extra_restore', 'rr_ng_frame_index', 'rr_ng_snap_restore_frame'):
            self.assertIn(call, text, call)

    def test_a_load_validates_before_it_changes_the_machine(self):
        text = self.snapshot_text()
        load = text[text.index('bool rr_ng_snap_load'):]
        self.assertLess(load.index('rr_ng_core_state_valid'), load.index('geo_state_load_raw'))
        self.assertLess(load.index('rr_ng_lspc_extra_valid'), load.index('geo_state_load_raw'))
        self.assertIn('size!=core+SNAP_TAIL', load)

    def test_a_correction_does_not_reset_what_is_only_displayed(self):
        main = read('neogeo_main.c')
        helper = main[main.index('void rr_ng_snap_restore_frame'):]
        helper = helper[:helper.index('\n')]
        # The fix-layer mask latch, the boot cover and the audio chain go on across a correction, as across a live frame.
        for name in ('fixmask', 'boot_cover', 'discontinuity'):
            self.assertNotIn(name, helper)

    def test_the_digest_is_the_three_route_hashes_and_the_frame(self):
        main = read('neogeo_main.c')
        digest = main[main.index('uint64_t rr_ng_digest'):]
        digest = digest[:digest.index('\n}\n')]
        for name in ('extended_cpu_hash()', 'extended_hardware_hash()', 'rr_ng_z80_state_hash()', 'frame>>'):
            self.assertIn(name, digest)

    def test_a_guest_writes_no_save_and_no_record(self):
        main = read('neogeo_main.c')
        self.assertRegex(main, r'void rr_ng_side_effects\(bool allowed\) \{rr_ng_persist_writes\(allowed\);rr_ng_feedback_off=!allowed;\}')
        persistence = read('neogeo_persistence.c')
        self.assertRegex(persistence, r'if\(!enabled \|\| writes_off\)return true;')
        reference = read('neogeo_reference.c')
        self.assertEqual(len(re.findall(r'rr_ng_feedback_off', reference)), 3)    # its definition and the two records it gates


class SessionSaveTests(unittest.TestCase):
    """Session ABI 8: the host's NVRAM and memory card travel to every seat before the boot digest."""

    def test_the_adapter_carries_the_save(self):
        adapter = read('hostkit/adapters/rrhk_ng.c')
        self.assertIn('.session_save = rr_ng_session_save, .session_save_put = rr_ng_session_save_put', adapter)

    def test_the_image_is_a_header_and_the_two_memories_of_the_save_file(self):
        persistence = read('neogeo_persistence.c')
        body = persistence[persistence.index('enum { SESSION_HEADER'):]
        self.assertIn('SESSION_HEADER=12,SESSION_SAVE=SESSION_HEADER+PAYLOAD', body)
        self.assertIn('"RNG1"', body)
        # No size query writes anything, a small buffer gives nothing.
        self.assertIn('if(!out)return SESSION_SAVE;', body)
        self.assertIn('if(capacity<SESSION_SAVE)return 0;', body)

    def test_a_put_checks_the_size_and_the_header_before_it_changes_the_machine(self):
        persistence = read('neogeo_persistence.c')
        put = persistence[persistence.index('bool rr_ng_session_save_put'):]
        put = put[:put.index('\n}\n')]
        self.assertLess(put.index('memcmp(data,"RNG1",4)'), put.index('memcpy(ngsys.nvram'))
        self.assertLess(put.index('size!=SESSION_SAVE'), put.index('memcpy(ngsys.nvram'))
        # It never writes a file: the guest's flush stays stopped (rr_ng_persist_writes) and nothing is saved here.
        self.assertNotIn('write_atomic', put)

    def test_the_host_writes_its_save_back_once_atomically_with_a_backup(self):
        adapter = read('hostkit/adapters/rrhk_ng.c')
        self.assertIn('.session_save_commit = rr_ng_session_save_commit', adapter)
        persistence = read('neogeo_persistence.c')
        commit = persistence[persistence.index('bool rr_ng_session_save_commit'):]
        commit = commit[:commit.index('\n}\n')]
        # `writes_off` stops every write of a match, this one excepted; an unchanged memory writes nothing and returns true.
        self.assertNotIn('writes_off', commit)
        self.assertIn('flush_save(true)', commit)
        self.assertIn('if(!enabled)return false;', commit)
        self.assertIn('if(blocked)return false;', commit)
        # The write at exit and the commit share the lock, the check against another copy's file and the atomic write.
        self.assertIn('return flush_save(false);', persistence)
        flush = persistence[persistence.index('static bool flush_save'):]
        flush = flush[:flush.index('\n}\n')]
        for word in ('lock_save()', 'read_saved(previous,&checksum)', 'checksum==disk_hash', 'write_atomic(current,backup)'):
            self.assertIn(word, flush)
        # The previous file is copied to <file>.bak (temporary, then rename) before the new one replaces it.
        atomic = persistence[persistence.index('static bool write_atomic'):]
        atomic = atomic[:atomic.index('\n}\n')]
        self.assertLess(atomic.index('keep_backup()'), atomic.index('rr_replace(temporary,save_path)'))
        backup = persistence[persistence.index('static bool keep_backup'):persistence.index('static bool write_atomic')]
        self.assertIn('L"%ls.bak"', backup)
        self.assertIn('rr_replace(temporary,backup)', backup)

    def test_the_image_fits_the_kits_limit(self):
        session = (NATIVE / 'hostkit/hostkit_session.h').read_text(encoding='utf-8')
        self.assertIn('#define RRHK_SESSION_MAX_SAVE (2u * 1024u * 1024u)', session)
        self.assertLess(12 + 65536 + 2048, 2 * 1024 * 1024)


@unittest.skipUnless(os.environ.get('RR_NG_PROBE_EXE'), 'set RR_NG_PROBE_EXE to a converted Neo Geo game to run the determinism probe')
class ProbeTests(unittest.TestCase):
    def test_save_run_load_run_is_the_same_on_a_converted_game(self):
        from tools import neogeo_snapshot_probe as tool
        import tempfile
        exe = Path(os.environ['RR_NG_PROBE_EXE']).resolve()
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / 'play.inputs'
            script.write_text(tool.ROUTES['play'][1], encoding='ascii')
            for warm in (300, 3001):
                row = tool.probe(exe, warm, 60, script)
                self.assertTrue(row['passed'], row)
                self.assertEqual(row['different_digests'], 0)


if __name__ == '__main__':
    unittest.main()
