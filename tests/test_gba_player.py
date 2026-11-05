"""The Game Boy Advance player, stage 4: what is staged for its build and what the seam of the engine looks like (no ROM, no BIOS,
no compiler: authored bytes stand in for both images)."""
import re
import tempfile
import unittest
from pathlib import Path

from retrorecomp import gba_engine, gba_patches, gba_player, hostkit
from retrorecomp.paths import ASSETS
from retrorecomp.systems import get_profile


class PlayerProjectTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def prepare(self, title='An Authored Game'):
        (self.root / 'stage/engine').mkdir(parents=True, exist_ok=True)
        (self.root / 'stage/external/arm-recomp-core').mkdir(parents=True, exist_ok=True)
        (self.root / 'stage/external/arm-recomp-core/LICENSE').write_text('MIT authored', encoding='utf-8')
        (self.root / 'rom.gba').write_bytes(b'\x01' * 64)
        (self.root / 'bios.bin').write_bytes(b'\x02' * 64)
        player = self.root / 'player'
        gba_player.prepare(player, self.root / 'stage', self.root / 'generated', self.root / 'bios_code', self.root / 'rom.gba',
                           self.root / 'bios.bin', title=title, name='An Authored Game', sha1='ab' * 20, sha256='cd' * 32,
                           version='1.7.0')
        return player

    def test_the_project_holds_the_kit_the_machine_and_the_resources(self):
        player = self.prepare()
        for name in ('hostkit/shell/rrhk_main.c', 'hostkit/adapters/rrhk_gba.c', 'gba_machine.cpp', 'gba_machine.h',
                     'retro_menu.c', 'platform_io.c', 'runtime_feedback.c', 'gba_game.h', 'content.rc', 'CMakeLists.txt',
                     'notices.txt', 'export-identity.bin', 'game_resources.rc'):
            self.assertTrue((player / name).is_file(), name)
        header = (player / 'gba_game.h').read_text(encoding='utf-8')
        self.assertIn('#define RR_GBA_TITLE "An Authored Game"', header)
        self.assertIn('#define RR_GBA_ROM_SHA1 "' + 'ab' * 20 + '"', header)
        rc = (player / 'content.rc').read_text(encoding='utf-8')
        for number in (gba_player.ROM_RESOURCE, gba_player.BIOS_RESOURCE, gba_player.NOTICES_RESOURCE, gba_player.IDENTITY_RESOURCE):
            self.assertRegex(rc, rf'(?m)^{number} RCDATA ')
        self.assertIn('MIT authored', (player / 'notices.txt').read_text(encoding='utf-8'))
        self.assertIn('PolyForm', (player / 'notices.txt').read_text(encoding='utf-8'))

    def test_the_cmake_file_links_the_engine_to_the_kit_without_leftover_markers(self):
        cmake = (self.prepare() / 'CMakeLists.txt').read_text(encoding='utf-8')
        self.assertNotRegex(cmake, r'@[A-Z]+@')
        for source in hostkit.sources('gba'):
            self.assertIn(source, cmake)
        self.assertIn('gbarecomp_add_runtime_target(game', cmake)
        self.assertIn('SDL_MAIN_HANDLED', cmake)

    def test_the_icon_of_a_first_preparation_has_its_folder(self):
        # The player folder does not exist yet at the first conversion of a game: the icon step must not need it.
        (self.root / 'stage/engine').mkdir(parents=True, exist_ok=True)
        (self.root / 'rom.gba').write_bytes(b'' * 64)
        (self.root / 'bios.bin').write_bytes(b'' * 64)
        player = self.root / 'fresh' / 'player'
        art = gba_player.prepare(player, self.root / 'stage', self.root / 'generated', self.root / 'bios_code', self.root / 'rom.gba',
                                 self.root / 'bios.bin', title='A Game', name='A Game', sha1='ab' * 20, sha256='cd' * 32,
                                 version='1.7.0', presentation={'rom_path': self.root / 'rom.gba', 'online_cover': False,
                                                                'cover': ASSETS / 'assets/Retro-Recomp-icon-256.png',
                                                                'emit': lambda text: None})
        self.assertTrue(art['embedded'])
        self.assertTrue((player / 'game.ico').is_file())

    def test_a_second_preparation_touches_nothing(self):
        player = self.prepare()
        before = {path: path.stat().st_mtime_ns for path in player.rglob('*') if path.is_file()}
        self.prepare()
        self.assertEqual(before, {path: path.stat().st_mtime_ns for path in player.rglob('*') if path.is_file()})

    def test_the_profile_names_its_adapter_and_the_adapter_is_the_one_the_kit_stages(self):
        self.assertEqual(get_profile('gba').host_adapter, 'adapters/rrhk_gba.c')
        self.assertIn('hostkit/adapters/rrhk_gba.c', hostkit.sources('gba'))
        text = (ASSETS / 'native/hostkit/adapters/rrhk_gba.c').read_text(encoding='utf-8')
        self.assertIn('rrhk_adapter', text)
        self.assertEqual(len(re.findall(r'\{"[A-Za-z]+", L"[A-Za-z]+", 0x[0-9A-Fa-f]+,', text)), 10)   # ten buttons

    def test_the_buttons_are_the_ten_bits_of_keyinput_once_each(self):
        text = (ASSETS / 'native/hostkit/adapters/rrhk_gba.c').read_text(encoding='utf-8')
        bits = [int(value, 16) for value in re.findall(r'\{"[A-Za-z]+", L"[A-Za-z]+", (0x[0-9A-Fa-f]+),', text)]
        self.assertEqual(sorted(bits), [1 << index for index in range(10)])


class EngineSeamTests(unittest.TestCase):
    def test_the_driver_header_is_the_file_the_engine_gains(self):
        self.assertEqual(gba_patches.ADDED_FILES, (('src/runtime/rr_driver.h', 'gba_driver.h'),))
        self.assertIn(b'g_rr_driver', gba_engine.added_text('gba_driver.h'))
        self.assertNotIn(b'\r', gba_engine.added_text('gba_driver.h'))

    def test_the_digest_follows_the_added_files(self):
        base = gba_engine.patch_digest(gba_patches.PATCHES)
        self.assertNotEqual(base, gba_engine.patch_digest(gba_patches.PATCHES, gba_patches.ADDED_FILES))

    def test_the_seam_patches_name_the_two_engine_files_they_touch(self):
        files = {file for file, _old, new, _note in gba_patches.PATCHES if 'g_rr_' in new or 'rr_driver' in new}
        self.assertEqual(files, {'src/runtime/runtime.cpp', 'src/runtime/asset_picker.cpp'})


if __name__ == '__main__':
    unittest.main()
