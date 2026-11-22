"""The Amstrad CPC's build on the banked Z80 chain (retrorecomp/cpc_build.py): the sources it gives the generator and the files it
stages, with stand-in firmware (no ROM)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from retrorecomp import cpc_build, z80_chain_build
from retrorecomp.paths import ASSETS


class BuildTests(unittest.TestCase):
    def test_the_sources_are_the_system_rom_then_amsdos(self):
        system, amsdos = bytes([1]) * 0x8000, bytes([2]) * 0x4000
        first, others = cpc_build.sources(system, amsdos)
        self.assertEqual((first, others), (system, (('amsdos.rom', amsdos),)))
        for bad in ((system[:-1], amsdos), (system, amsdos + b'\0')):
            with self.assertRaises(cpc_build.CpcBuildError):
                cpc_build.sources(*bad)

    def test_generate_hands_the_chain_the_cpcs_machine_and_its_costs(self):
        from retrorecomp.systems.amstrad_cpc import CPC_MACHINE
        with mock.patch.object(z80_chain_build, 'generate_bodies') as generate:
            cpc_build.generate(Path('work'), bytes(0x8000), bytes(0x4000))
        args, kwargs = generate.call_args
        self.assertIs(args[1], CPC_MACHINE)
        self.assertEqual((kwargs['loop_name'], kwargs['accept']), ('cpc_banked_loop.inc', 'cpc_reference_accept'))
        self.assertIsNotNone(CPC_MACHINE.costs)

    def test_the_chain_passes_the_costs_to_the_reference_copy(self):
        source = (ASSETS / 'retrorecomp' / 'z80_chain_build.py').read_text(encoding='utf-8')
        self.assertIn('costs=machine.costs', source)

    def test_every_staged_file_exists_and_is_listed_for_the_stamps(self):
        from retrorecomp import compilation_inputs
        names = set(compilation_inputs.manifest_names('cpc'))
        for folder, files in (('native/cpc_machine', cpc_build.MACHINE_FILES), ('native/upd765', cpc_build.DISK_FILES)):
            for name in files:
                with self.subTest(name=name):
                    self.assertTrue((ASSETS / folder / name).is_file())
                    self.assertIn(f'{folder}/{name}', names)
        with tempfile.TemporaryDirectory() as folder:
            cpc_build.stage_sources(Path(folder))
            self.assertTrue((Path(folder) / 'cpc_glue.inc').is_file() and (Path(folder) / 'upd765.c').is_file()
                            and (Path(folder) / 'z80_chain_glue.inc').is_file() and (Path(folder) / 'ay38910.c').is_file())
        names = set(compilation_inputs.manifest_names('cpc'))
        self.assertTrue({'native/ay38910/ay38910.c', 'native/z80_chain_glue.inc'} <= names)

    def test_the_game_folder_has_the_player_the_kit_and_the_adapters_files(self):
        from retrorecomp import compilation_inputs
        names = set(compilation_inputs.manifest_names('cpc'))
        for name in cpc_build.MAINS:
            with self.subTest(name=name):
                self.assertIn(f'native/cpc_machine/{name}', names)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            cpc_build.stage_sources(work, game=True)
            for name in (*cpc_build.MAINS, 'retro_menu.c', 'platform_io.c', 'hostkit/adapters/rrhk_cpc.inc',
                         *(f'hostkit/adapters/{name}' for name in cpc_build.ADAPTER_FILES)):
                with self.subTest(name=name):
                    self.assertTrue((work / name).is_file())
            self.assertFalse((work / 'hostkit' / 'adapters' / 'rrhk_msx.inc').exists())

    def test_the_game_project_links_the_player_on_the_same_bodies(self):
        check = cpc_build.project_cmake('9.9.9', game=False)
        game = cpc_build.project_cmake('9.9.9', game=True)
        self.assertNotIn('add_executable(game', check)
        self.assertTrue(game.startswith(check.split('if(WIN32)')[0]))
        self.assertIn('add_executable(game cpc_player.c', game)
        self.assertIn('$<TARGET_OBJECTS:cpc_bodies>)', game)
        self.assertIn('"${CMAKE_CURRENT_SOURCE_DIR}/hostkit/adapters"', game)
        self.assertIn('RR_RECOMP_VERSION="9.9.9"', game)

    def test_the_sound_is_mono_by_default_and_the_jack_stereo_an_option_in_five_languages(self):
        adapter = (ASSETS / 'native' / 'hostkit' / 'adapters' / 'rrhk_cpc.inc').read_text(encoding='utf-8')
        self.assertIn('static bool c_stereo;', adapter)                     # false: the built-in speaker's mono
        self.assertIn('stereo[2 * i] = stereo[2 * i + 1] = mono;', adapter)
        table = adapter[adapter.index('static const char *const c_texts[][4]'):adapter.index('static const char *c_text(int which)')]
        self.assertEqual(sorted(code for code in ('en', 'fr', 'de', 'es', 'it') if f'{{"{code}",' in table),
                         ['de', 'en', 'es', 'fr', 'it'])
        self.assertTrue(table.isascii())
        self.assertIn('t->option_rows = c_option_rows; t->key_event = c_key_event;', adapter)

    def test_the_players_resources_and_its_game_header(self):
        player = (ASSETS / 'native' / 'cpc_machine' / 'cpc_player.c').read_text(encoding='utf-8')
        for resource in (cpc_build.RESOURCE_DISKS, cpc_build.RESOURCE_SYSTEM, cpc_build.RESOURCE_AMSDOS):
            self.assertIn(f'rr_resource({resource},', player)
        for name in ('RR_CPC_TITLE', 'RR_CPC_IDENTITY', 'RR_CPC_CRTC', 'RR_CPC_DISKS', 'RR_CPC_DISK_MAX', 'RR_CPC_DISK_SIZES'):
            self.assertIn(name, player)
        source = (ASSETS / 'retrorecomp' / 'cpc_build.py').read_text(encoding='utf-8')
        for name in ('RR_CPC_TITLE', 'RR_CPC_IDENTITY', 'RR_CPC_CRTC', 'RR_CPC_DISKS', 'RR_CPC_DISK_MAX', 'RR_CPC_DISK_SIZES'):
            self.assertIn(f'#define {name} ', source)


if __name__ == '__main__':
    unittest.main()
