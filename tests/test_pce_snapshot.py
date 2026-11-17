"""The PC Engine's snapshot for multiplayer (native/pce_snapshot.cpp): what a test with no compiler can say. The probe itself (build, then every frame a save point,
compared with the engine's own full checkpoint) is `tools/pce_snapshot_selftest.py`; set RR_SNAPSHOT_PROBE=1 to run it from here."""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from retrorecomp import hostkit
from retrorecomp.systems import get_profile


class RomTests(unittest.TestCase):
    def test_the_authored_card_is_a_whole_standard_hucard_and_the_same_every_time(self):
        import pce_snapshot_rom
        rom = pce_snapshot_rom.build_rom()
        self.assertEqual(len(rom), 16 * 0x2000)
        self.assertEqual(rom, pce_snapshot_rom.build_rom())
        self.assertGreaterEqual(rom[0x1FFE] | rom[0x1FFF] << 8, 0xE000)       # the reset vector points into bank 0 ($E000-$FFFF)

    def test_the_street_fighter_board_image_is_2_5_mib_with_a_program_and_a_vector_in_bank_0(self):
        import pce_snapshot_selftest
        image = pce_snapshot_selftest.sf2_rom()
        self.assertEqual(len(image), 0x280000)
        self.assertEqual(image[0], 0x78)                       # SEI
        self.assertEqual(image[0x1FFE:0x2000], bytes([0x00, 0xE0]))
        self.assertEqual(image, pce_snapshot_selftest.sf2_rom())
        # the bank latch is written through $FFF0 + X, whose four values are the four quarters of the window
        self.assertIn(bytes([0x9D, 0xF0, 0xFF]), image[:0x20])


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.adapter = (ROOT / 'native/hostkit/adapters/rrhk_pce.c').read_text(encoding='utf-8')
        self.main = (ROOT / 'native/pce_main.c').read_text(encoding='utf-8')
        self.snapshot = (ROOT / 'native/pce_snapshot.cpp').read_text(encoding='utf-8')

    def test_the_adapter_hands_the_host_kit_the_snapshot_the_digest_and_the_side_effects_switch(self):
        for field in ('.snap_bound = rr_pce_snap_bound', '.snap_save = rr_pce_snap_save', '.snap_load = rr_pce_snap_load', '.digest = rr_pce_digest',
                      '.side_effects = rr_pce_side_effects'):
            self.assertIn(field, self.adapter)
        self.assertNotIn('.driven', self.adapter)          # the machine owns no loop: silent frames after a load are ordinary run_frame calls

    def test_a_frame_with_no_effects_writes_no_backup_file_and_no_record(self):
        self.assertIn('if (effects_allowed) rr_pce_backup_flush(SDL_GetTicks64(), false);', self.main)
        self.assertIn('if (effects_allowed) rr_pce_backup_flush(SDL_GetTicks64(), true);', self.main)
        self.assertIn('static int record_enabled(void) { return effects_allowed && rr_feedback_enabled(); }', self.main)
        self.assertIn('pce_machine_set_recorder(record_instruction, record_enabled)', self.main)

    def test_the_host_frame_counter_travels_with_the_snapshot(self):
        # the inputs of a session are keyed by it: a load that leaves it behind would replay the wrong frames
        self.assertIn('put32(bytes, frame);', self.main)
        self.assertIn('frame = get32(bytes);', self.main)

    def test_the_snapshot_holds_no_rom_and_the_digest_leaves_out_how_the_code_ran(self):
        self.assertNotIn('hucard_mapper_rom, ', re.sub(r'//.*', '', self.snapshot).split('template <class A, class B, class C> void core')[1].split('uint64_t hash_bytes')[0])
        digest = self.snapshot.split('uint64_t pce_snapshot_digest(void)')[1]
        self.assertIn('core(out, *bus, *cpu);', digest)
        self.assertNotIn('cpu_counters', digest)
        self.assertNotIn('generation', digest)

    def test_the_snapshot_is_refused_for_a_machine_it_does_not_describe(self):
        self.assertIn('!bus.arcade_card && !bus.cd.enabled && !bus.adpcm.enabled', self.snapshot)

    def test_the_game_builds_with_the_snapshot_and_the_stamps_list_it(self):
        from retrorecomp import compilation_inputs, pce_build
        for name in ('pce_snapshot.cpp', 'pce_snapshot.h', 'pce_machine_internal.hpp'):
            self.assertIn(name, pce_build.GAME_FILES)
        self.assertIn('pce_snapshot.cpp', pce_build.game_cmake(None, '1.0'))
        names = compilation_inputs.manifest_names('pce')
        for name in ('native/pce_snapshot.cpp', 'native/pce_snapshot.h', 'native/pce_machine_internal.hpp'):
            self.assertIn(name, names)

    def test_the_machine_is_offered_in_multiplayer_and_seats_four_through_the_multitap(self):
        profile = get_profile('pce')
        self.assertTrue(profile.netplay_session)
        self.assertEqual(profile.netplay_seats, 4)
        self.assertTrue(profile.netplay_seats_ceiling)         # the game's own count is what its report and HELLO say
        self.assertFalse(profile.netplay_portable)           # the mixed-build gate has not been run for this machine
        self.assertEqual('adapters/rrhk_pce.c', hostkit.ADAPTERS['pce'])


class MultitapTests(unittest.TestCase):
    """The console has one pad port: the second player is the multitap's. A session plugs it for every seat; the converter plugs it for the games it knows take more
    than two players (a reviewed table keyed by the dump)."""

    def setUp(self):
        self.adapter = (ROOT / 'native/hostkit/adapters/rrhk_pce.c').read_text(encoding='utf-8')

    def test_the_session_plugs_the_multitap_from_two_ports(self):
        begin = self.adapter.split('static void session_begin(uint64_t clock) {')[1].split('}')[0]
        self.assertIn('rrhk_session_ports() >= 2', begin)
        self.assertIn('pce_machine_plug_multitap(1)', begin)
        self.assertIn('.session_begin = session_begin', self.adapter)

    def test_players_3_and_4_are_read_inside_run_frame_so_a_silent_frame_sees_them(self):
        run = self.adapter.split('static bool run_frame(uint16_t p1, uint16_t p2) {')[1].split('\n}\n')[0]
        self.assertIn('rrhk_pad_word(2, at)', run)
        self.assertIn('rrhk_pad_word(3, at)', run)
        self.assertIn('rrhk_session_active() ? rrhk_session_ports() : players()', run)
        # nothing that decides the run is set in before_frame (silent frames never call it)
        self.assertNotIn('before_frame', re.sub(r'/\*.*?\*/', '', self.adapter, flags=re.S))

    def test_the_hosts_backup_ram_travels_in_memory_only(self):
        self.assertIn('.session_save = session_save', self.adapter)
        self.assertIn('.session_save_put = session_save_put', self.adapter)
        self.assertIn('size != PCE_BACKUP_BYTES', self.adapter)
        self.assertIn('pce_machine_set_backup(in)', self.adapter)

    def test_the_bridge_plugs_the_multitap_now_and_after_a_reset(self):
        bridge = (ROOT / 'native/pce_machine.cpp').read_text(encoding='utf-8')
        plug = bridge.split('void pce_machine_plug_multitap(int plugged) {')[1].split('\n}\n')[0]
        self.assertIn('recipe.multitap = plugged != 0;', plug)                   # the recipe is what a reset builds from
        self.assertIn('machine->bus.joypad.set_multitap(recipe.multitap)', plug)

    def test_the_games_that_take_more_than_two_players_are_a_table_keyed_by_the_dump(self):
        from types import SimpleNamespace
        from retrorecomp import pce_build
        bomberman = '678a097de779f3b24fc535e1de55448b754be6abe203a060e8f43c5c78899c8e'
        self.assertEqual(pce_build.players_of(SimpleNamespace(sha256=bomberman)), 4)
        self.assertEqual(pce_build.players_of(SimpleNamespace(sha256='00' * 32)), 2)
        for sha, players in pce_build.MULTITAP_PLAYERS.items():
            self.assertRegex(sha, r'^[0-9a-f]{64}$')
            self.assertIn(players, (3, 4))                                       # a room seats four at most; the console takes five
        # a four-player game is built with the multitap plugged and four players in its header
        self.assertIn('RR_PCE_MULTITAP {int(seats > 1)}', (ROOT / 'retrorecomp/pce_build.py').read_text(encoding='utf-8'))   # alone as well: pad II needs the tap
        self.assertIn('players=pce_build.players_of(card)', (ROOT / 'retrorecomp/pce_conversion.py').read_text(encoding='utf-8'))


@unittest.skipUnless(os.environ.get('RR_SNAPSHOT_PROBE'), 'the probe builds the engine and takes minutes: RR_SNAPSHOT_PROBE=1 runs it')
class ProbeTests(unittest.TestCase):
    def test_the_probe_passes_on_both_boards(self):
        import pce_snapshot_selftest
        self.assertEqual(pce_snapshot_selftest.main(), 0)


if __name__ == '__main__':
    unittest.main()
