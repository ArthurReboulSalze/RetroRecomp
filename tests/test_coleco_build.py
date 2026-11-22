"""The ColecoVision's build on the banked Z80 chain (retrorecomp/coleco_build.py): what both runners report, the generator's input, the project
text and the comparison, with synthetic data (no toolchain, no ROM)."""
import hashlib
import json
import re
import tempfile
import unittest
from pathlib import Path

from retrorecomp import coleco_build as build, stamp_inputs, z80_chain_build
from retrorecomp.systems.coleco import COLECO, COLECO_MACHINE

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'native'
HEADLESS = (NATIVE / 'coleco_machine/coleco_headless.inc').read_bytes().decode('utf-8')
MACHINE_C = (NATIVE / 'coleco_machine/coleco_machine.c').read_bytes().decode('utf-8')


def report_keys(text: str) -> list[str]:
    """The keys of the JSON the headless programs print, in the order of the C format strings."""
    return re.findall(r'\\"([a-z_0-9]+)\\":', text)


class ComparedTests(unittest.TestCase):
    def test_every_compared_field_is_printed_by_both_runners(self):
        printed = set(report_keys(HEADLESS)) | set(report_keys(MACHINE_C))
        for field in build.COMPARED:
            self.assertIn(field, printed, field)

    def test_every_common_member_is_compared_but_the_engine(self):
        printed = set(report_keys(HEADLESS)) | set(report_keys(MACHINE_C))
        self.assertEqual(printed - set(build.COMPARED) - {'native_steps', 'halt_steps', 'fallback_steps', 'guarded_steps',
                                                            'fallback_cycles', 'fallback_at'}, {'engine'})

    def test_the_native_only_counts_are_printed_by_the_native_check_only(self):
        # The native counters are printed by the shared headless file, behind CV_HEADLESS_NATIVE: the native check and the player define it.
        native = (NATIVE / 'coleco_machine/coleco_headless.inc').read_bytes().decode('utf-8')
        self.assertIn('CV_HEADLESS_NATIVE', native)
        reference = (NATIVE / 'coleco_machine/coleco_reference_main.c').read_bytes().decode('utf-8')
        for key in ('native_steps', 'halt_steps', 'fallback_steps', 'guarded_steps', 'fallback_cycles', 'fallback_at'):
            self.assertIn(f'\\"{key}\\"', native, key)
            self.assertNotIn(f'\\"{key}\\"', reference, key)
            self.assertNotIn(key, build.COMPARED)

    def test_the_rows_have_the_columns_frame_rows_reads(self):
        self.assertIn('frame,cpu,ram,picture,sound,samples,audible,pc', HEADLESS)
        with tempfile.TemporaryDirectory() as folder:
            rows = Path(folder) / 'rows.csv'
            rows.write_text('frame,cpu,ram,picture,sound,samples,audible,pc\n1,aa,bb,cc,dd,735,1,0100\n2,aa,bb,ce,dd,735,0,0101\n',
                            encoding='ascii')
            read = build.frame_rows(rows)
            self.assertEqual([(r.frame, r.picture, r.audible, r.pc) for r in read], [(1, 'cc', True, '0100'), (2, 'ce', False, '0101')])


class DifferencesTests(unittest.TestCase):
    def test_equal_reports_do_not_differ(self):
        report = {key: 1 for key in build.COMPARED}
        self.assertEqual(build.differences(dict(report, native_steps=5), dict(report, engine='reference')), {})

    def test_a_field_that_differs_or_is_missing_is_named(self):
        native = {key: 1 for key in build.COMPARED}
        reference = dict(native, pc=2)
        del reference['psg']
        self.assertEqual(build.differences(native, reference), {'pc': (1, 2), 'psg': (1, None)})

    def test_a_field_outside_the_list_is_not_compared(self):
        native = {key: 1 for key in build.COMPARED}
        self.assertEqual(build.differences(dict(native, audio_ticks=1), dict(native, audio_ticks=2)), {})


class GeneratorInputTests(unittest.TestCase):
    def test_game_toml_has_the_cartridge_as_its_rom_and_the_bios_comes_by_banked_sources(self):
        self.assertIn('rom = "rom.sms"', build.GAME_TOML)
        self.assertIn('platform = "sms"', build.GAME_TOML)
        self.assertNotIn('sources =', build.GAME_TOML)         # the BIOS is named in banked.sources, written by generate_bodies

    def test_the_bios_is_the_second_source_of_the_generator(self):
        from unittest import mock
        calls = []
        with mock.patch.object(z80_chain_build, 'generate_bodies', lambda *a, **k: calls.append((a, k))):
            build.generate(Path('w'), b'cart', b'bios')
        (args, kwargs), = calls
        self.assertEqual((args[1], args[2], args[3]), (COLECO_MACHINE, b'cart', (('bios.rom', b'bios'),)))
        self.assertEqual((kwargs['loop_name'], kwargs['accept']), ('coleco_banked_loop.inc', 'coleco_reference_accept'))

    def test_the_cartridge_is_padded_to_whole_regions_with_ff(self):
        image = build.padded(b'\x01' * 0x800)
        self.assertEqual(len(image), 0x2000)
        self.assertEqual(image[:0x800], b'\x01' * 0x800)
        self.assertEqual(set(image[0x800:]), {0xFF})
        self.assertEqual(len(build.padded(bytes(0xC000))), 0xC000)
        self.assertEqual(len(build.padded(bytes(0x2001))), 0x4000)
        self.assertEqual(len(build.padded(b'x')), 0x2000)

    def test_the_machine_has_the_cartridge_then_the_bios_as_sources(self):
        self.assertEqual(COLECO_MACHINE.regions.sources, ('cartridge', 'bios'))
        self.assertTrue(COLECO_MACHINE.nmi)


class ProjectTests(unittest.TestCase):
    def test_every_file_the_project_names_exists_in_native(self):
        for name in build.MACHINE_FILES:
            self.assertTrue((NATIVE / 'coleco_machine' / name).is_file(), name)
        for folder, sources, files in build.SHARED_MODULES:
            for name in (*sources, *files):
                self.assertTrue((NATIVE / folder / name).is_file(), f'{folder}/{name}')
        for name in build.CHAIN_FILES:
            self.assertTrue((NATIVE / name).is_file(), name)

    def test_the_shared_modules_are_the_video_and_the_sound_chip(self):
        self.assertEqual([folder for folder, _, _ in build.SHARED_MODULES], ['tms9918', 'sn76489'])
        self.assertEqual(build.SHARED_SOURCES, ('tms9918.c', 'sn76489.c'))

    def test_the_files_staged_are_the_files_the_stamps_hash(self):
        owned = stamp_inputs.INPUTS[('coleco',)]
        for name in build.MACHINE_FILES:
            self.assertIn(f'native/coleco_machine/{name}', owned, name)
        for module in ('coleco_build', 'coleco_conversion', 'coleco_rom', 'coleco_routes'):
            self.assertIn(f'retrorecomp.{module}', owned, module)

    def test_the_project_builds_the_reference_the_check_and_the_bodies(self):
        text = build.project_cmake()
        self.assertIn('add_executable(coleco_reference coleco_reference_main.c coleco_machine.c tms9918.c sn76489.c runtime_reference.c)', text)
        self.assertIn('add_library(coleco_bodies OBJECT generated/game_banked_index.c ${bodies})', text)
        self.assertIn('add_executable(coleco_check coleco_native_main.c coleco_machine.c tms9918.c sn76489.c runtime_reference.c '
                      '$<TARGET_OBJECTS:coleco_bodies>)', text)
        self.assertIn('foreach(target coleco_reference coleco_check)', text)
        self.assertIn('SMSRECOMP_BANKED_AOT', text)
        self.assertNotIn('add_executable(game', text)
        self.assertNotIn('\r', text)

    def test_the_reference_alone_has_no_bodies(self):
        text = build.project_cmake(bodies=False)
        self.assertIn('foreach(target coleco_reference)', text)
        self.assertNotIn('coleco_check', text)
        self.assertNotIn('coleco_bodies', text)

    def test_the_game_target_is_the_player_with_the_kit_and_the_bodies(self):
        text = build.project_cmake(game=True, version='9.8.7')
        self.assertIn('add_executable(game coleco_player.c coleco_machine.c tms9918.c sn76489.c runtime_reference.c retro_menu.c platform_io.c '
                      'runtime_feedback.c ', text)
        self.assertIn('$<TARGET_OBJECTS:coleco_bodies>)', text)
        self.assertIn('hostkit/shell/rrhk_main.c', text)
        self.assertIn('target_link_libraries(game PRIVATE SDL2::SDL2-static)', text)
        self.assertIn('target_sources(game PRIVATE content.rc)', text)
        self.assertIn('embedded_resources.c embedded_resources.S', text)
        self.assertIn('SDL_MAIN_HANDLED SMSRECOMP_BANKED_AOT', text)
        self.assertIn('[[RR_RECOMP_VERSION="9.8.7"]]', text)
        self.assertIn('/SUBSYSTEM:WINDOWS', text)
        self.assertIn('-Wl,--subsystem,windows', text)
        self.assertIn('foreach(target coleco_reference coleco_check)', text)     # the check is built with the game: the same bodies
        self.assertNotIn('\r', text)

    def test_without_the_game_the_project_has_no_sdl(self):
        for text in (build.project_cmake(), build.project_cmake(bodies=False)):
            self.assertNotIn('SDL2', text)
            self.assertNotIn('add_executable(game', text)

    def test_every_player_and_kit_file_exists_and_is_staged(self):
        for name in build.PLAYER_FILES:
            self.assertTrue((NATIVE / 'coleco_machine' / name).is_file(), name)
            self.assertIn(f'native/coleco_machine/{name}', stamp_inputs.INPUTS[('coleco',)], name)
        self.assertEqual(build.PLAYER_SOURCES, ('coleco_player.c',))
        for name in build.KIT_FILES:
            self.assertTrue((NATIVE / name).is_file(), name)
        self.assertFalse({'media_request.h', 'cart_save.c', 'cart_save.h'} & set(build.KIT_FILES))   # no media, no battery

    def test_the_header_names_the_game_the_player_reads(self):
        header = build.game_header('Flicky "Test"', 'ab' * 32, 'pal', 0x8000, 'cd' * 32)
        self.assertIn('#define RR_CV_TITLE "Flicky \\"Test\\""', header)
        self.assertIn(f'#define RR_CV_IDENTITY "{"ab" * 32}"', header)
        self.assertIn('#define RR_CV_PAL 1', header)
        self.assertIn('#define RR_CV_PAL 0', build.game_header('x', 'ab' * 32, 'ntsc', 0x2000, 'cd' * 32))
        abi = [int(v, 16) for v in re.search(r'RR_CV_STATE_ABI \{([^}]*)\}', header).group(1).split(',')]
        self.assertEqual(bytes(abi), build.state_binding('pal', 0x8000, 'cd' * 32))
        self.assertEqual(len(abi), 32)
        for line in header.splitlines():                                  # every symbol the player reads is defined
            self.assertTrue(line.startswith(('#pragma', '#define RR_CV_')), line)
        player = (NATIVE / 'coleco_machine/coleco_player.c').read_text(encoding='utf-8')
        for symbol in ('RR_CV_TITLE', 'RR_CV_IDENTITY', 'RR_CV_PAL', 'RR_CV_STATE_ABI'):
            self.assertIn(symbol, player)
            self.assertIn(f'#define {symbol} ', header)

    def test_the_binding_follows_the_layout_the_standard_the_size_and_the_bios(self):
        base = build.state_binding('ntsc', 0x2000, 'cd' * 32)
        self.assertEqual(len(base), 32)
        self.assertNotEqual(base, build.state_binding('pal', 0x2000, 'cd' * 32))
        self.assertNotEqual(base, build.state_binding('ntsc', 0x4000, 'cd' * 32))
        self.assertNotEqual(base, build.state_binding('ntsc', 0x2000, 'ce' * 32))
        self.assertEqual(base, hashlib.sha256(('coleco-state-1\nntsc\n8192\n' + 'cd' * 32).encode('ascii')).digest())
        self.assertIn(build.STATE_LAYOUT, (NATIVE / 'coleco_machine/coleco_state_file.inc').read_text(encoding='utf-8'))

    def test_staging_copies_what_changed_beside_the_bodies(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            build.stage_sources(work)
            for name in ('coleco_machine.c', 'coleco_glue.inc', 'coleco_player.c', 'coleco_state_file.inc', 'tms9918.c', 'tms_tiles.inc',
                         'sn76489.h', 'z80_chain_glue.inc', 'retro_menu.c', 'state_envelope.h'):
                self.assertEqual((work / name).read_bytes(), next(NATIVE.rglob(name)).read_bytes(), name)
            self.assertEqual((work / 'hostkit/adapters/rrhk_keypad.inc').read_bytes(),
                             (NATIVE / 'hostkit/adapters/rrhk_keypad.inc').read_bytes())      # the adapter includes it
            self.assertTrue((work / 'hostkit/adapters/rrhk_coleco.inc').is_file())
            marked = work / 'coleco_machine.c'
            before = marked.stat().st_mtime_ns
            build.stage_sources(work)
            self.assertEqual(marked.stat().st_mtime_ns, before)       # a rebuild touches nothing that did not change

    def test_the_profile_converts_with_this_modules_conversion(self):
        self.assertIs(COLECO.z80_machine, COLECO_MACHINE)
        self.assertEqual(build.ColecoBuildError.__mro__[1], RuntimeError)


class RunTests(unittest.TestCase):
    def test_a_program_that_fails_is_a_build_error_with_its_message(self):
        import sys
        with self.assertRaisesRegex(build.ColecoBuildError, 'boom'):
            build.run(Path(sys.executable), ['-c', 'import sys; sys.stderr.write("boom"); sys.exit(3)'])

    def test_the_report_is_read_as_json_and_the_cartridge_reaches_standard_input(self):
        import sys
        code = 'import sys, json; print(json.dumps({"bytes": len(sys.stdin.buffer.read())}))'
        # run_program appends `--cart -`: python ignores it after -c.
        self.assertEqual(build.run(Path(sys.executable), ['-c', code], b'abc'), {'bytes': 3})
        self.assertEqual(json.loads('{"a": 1}'), {'a': 1})


class ChainTests(unittest.TestCase):
    def test_the_build_is_on_the_shared_helpers(self):
        self.assertIs(build.frame_rows, z80_chain_build.frame_rows)
        source = (ROOT / 'retrorecomp/coleco_build.py').read_text(encoding='utf-8')
        for helper in ('generate_bodies', 'stage_files', 'build_project', 'run_program', 'run_game', 'game_exit_code', 'learn_passes',
                       'differences'):
            self.assertIn(f'z80_chain_build.{helper}', source, helper)


if __name__ == '__main__':
    unittest.main()
