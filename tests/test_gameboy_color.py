"""The Game Boy Color profile (retrorecomp/systems/game_boy_color.py, the variant of retrorecomp/gameboy.py): how a file reaches the Game Boy or the Game Boy Color,
what each reader refuses, the settings that keep the two machines apart. No ROM, no compiler: every cartridge is built here from an authored header."""
import inspect
import tempfile
import unittest
import zipfile
from pathlib import Path

from retrorecomp import gameboy
from retrorecomp.core import ConversionError
from retrorecomp.paths import ASSETS
from retrorecomp.systems import get_profile, profile_for_path


def cartridge(flag: int, banks: int = 2) -> bytes:
    """A valid-looking header (checksum, size, title) and nothing else: 32 KiB, the Color flag as given."""
    data = bytearray(banks * 0x4000)
    data[0x134:0x13E] = b'TEST CART\x00'[:10]
    data[0x143] = flag
    data[0x147] = 0
    data[0x148] = 0 if banks == 2 else {4: 1, 8: 2}[banks]
    checksum = 0
    for value in data[0x134:0x14D]:
        checksum = (checksum - value - 1) & 0xFF
    data[0x14D] = checksum
    return bytes(data)


class WhereAFileGoes(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)

    def tearDown(self):
        self._folder.cleanup()

    def write(self, name: str, flag: int) -> Path:
        path = self.folder / name
        path.write_bytes(cartridge(flag))
        return path

    def test_a_gbc_file_is_the_colors_whatever_its_flag_says(self):
        self.assertEqual(profile_for_path(self.write('A.gbc', 0xC0)).id, 'gbc')
        self.assertEqual(profile_for_path(self.write('B.gbc', 0x80)).id, 'gbc')

    def test_a_gb_file_is_the_game_boys_unless_it_is_color_only(self):
        self.assertEqual(profile_for_path(self.write('A.gb', 0x00)).id, 'gb')
        self.assertEqual(profile_for_path(self.write('B.gb', 0x80)).id, 'gb')          # Pokémon Yellow's case: Color-enhanced, kept monochrome
        self.assertEqual(profile_for_path(self.write('C.gb', 0xC0)).id, 'gbc')

    def test_a_zip_follows_the_same_rule_through_its_cartridge(self):
        for name, flag, expected in (('A.gbc', 0xC0, 'gbc'), ('B.gb', 0xC0, 'gbc'), ('C.gb', 0x80, 'gb')):
            archive = self.folder / (name + '.zip')
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr(name, cartridge(flag))
            self.assertEqual(profile_for_path(archive).id, expected, name)

    def test_a_headerless_dump_is_told_by_its_flag(self):
        self.assertEqual(profile_for_path(self.write('A.bin', 0xC0)).id, 'gbc')
        self.assertEqual(profile_for_path(self.write('B.bin', 0x00)).id, 'gb')
        self.assertEqual(profile_for_path(self.write('C.rom', 0x80)).id, 'gb')

    def test_the_two_content_sniffers_never_both_say_yes(self):
        gb, gbc = get_profile('gb'), get_profile('gbc')
        for flag in (0x00, 0x80, 0xC0):
            data = cartridge(flag)
            self.assertEqual(sum(profile.identify_content(data) is not None for profile in (gb, gbc)), 1, flag)

    def test_each_reader_refuses_the_others_cartridge(self):
        color_only = self.write('A.gb', 0xC0)
        with self.assertRaises(ConversionError):
            gameboy.read_game_boy_rom(color_only, gameboy.DMG)
        monochrome = self.write('B.gbc', 0x00)
        with self.assertRaises(ConversionError) as caught:
            gameboy.read_game_boy_rom(monochrome, gameboy.COLOR)
        self.assertIn('Game Boy profile', str(caught.exception))
        with self.assertRaises(ConversionError):
            gameboy.read_game_boy_rom(self.write('C.gbc', 0xC0), gameboy.DMG)           # a .gbc is not a Game Boy file name

    def test_the_rom_knows_its_machine(self):
        rom = gameboy.read_game_boy_rom(self.write('A.gbc', 0x80), gameboy.COLOR)
        self.assertEqual((rom.system_id, rom.metadata()['system_id'], rom.cgb_flag), ('gbc', 'gbc', 0x80))
        self.assertEqual(gameboy.read_game_boy_rom(self.write('B.gb', 0x00)).system_id, 'gb')


class TheProfile(unittest.TestCase):
    def test_it_is_experimental_and_its_own_machine(self):
        profile = get_profile('gbc')
        self.assertEqual((profile.status, profile.linux, profile.export_folder, profile.video_modes),
                         ('experimental', 'pending', 'Game Boy Color', ('cgb',)))
        self.assertEqual(profile.library_layout.folder, 'gbc')
        self.assertEqual(profile.path_spec.sections, (('sm83', 'gbc'),))
        self.assertEqual(profile.quick_state_family, 'gbc')
        self.assertEqual(profile.host_adapter, get_profile('gb').host_adapter)        # one adapter, built with RR_GB_COLOR for the Color
        self.assertEqual(profile.feedback_kinds, get_profile('gb').feedback_kinds)    # one record format

    def test_its_options_are_its_own_names_and_reach_the_gameboy_converter_as_the_gameboys(self):
        profile = get_profile('gbc')
        self.assertEqual(profile.option_key_names, {'gbc_deep_validation', 'gbc_parallel_games'})
        source = inspect.getsource(type(profile).convert)
        self.assertIn('variant=COLOR', source)

    def test_the_variants_say_what_differs(self):
        self.assertEqual((gameboy.DMG.system_id, gameboy.DMG.model), ('gb', 'dmg'))
        self.assertEqual((gameboy.COLOR.system_id, gameboy.COLOR.model), ('gbc', 'cgb'))
        self.assertNotEqual(gameboy.DMG.box_art, gameboy.COLOR.box_art)

    def test_the_runtime_is_told_the_model_and_the_kit_the_machine(self):
        from retrorecomp import gameboy_runtime
        self.assertIn('variant', inspect.signature(gameboy_runtime.adapt_generated_project).parameters)
        source = inspect.getsource(gameboy_runtime.adapt_generated_project)
        self.assertIn('{model}', source)
        self.assertIn('RR_GB_COLOR=1', source)
        self.assertIn('stage(project, system_id,', source)


class TheAdapter(unittest.TestCase):
    ADAPTER = (ASSETS / 'native/hostkit/adapters/rrhk_gb.inc').read_text(encoding='utf-8')

    def test_the_color_has_its_own_name_and_settings_section(self):
        self.assertIn('#ifdef RR_GB_COLOR', self.ADAPTER)
        self.assertIn('L"GameBoyColor"', self.ADAPTER)
        self.assertIn('"Game Boy Color"', self.ADAPTER)
        self.assertIn('L"GameBoy"', self.ADAPTER)


class WhatAColorGameShows(unittest.TestCase):
    def test_the_f1_help_offers_the_palette_key_only_where_the_options_do(self):
        # F5 chooses the classic green or the monochrome of the Game Boy; a Color game keeps its own colours, so neither the options row
        # nor the F1 help may offer it.
        source = (ASSETS / 'native/hostkit/adapters/rrhk_gb.inc').read_text(encoding='utf-8')
        helps = source[source.index('static void rr_gb_help_lines'):source.index('static void rr_gb_help_controls')]
        rows = source[source.index('static void rr_gb_option_rows'):source.index('static void rr_gb_help_lines')]
        self.assertIn('!rr_gb_color_game()', rows)
        line = next(text for text in helps.splitlines() if 'Monochrome / classic green' in text)
        self.assertIn('if (!rr_gb_color_game())', line)


if __name__ == '__main__':
    unittest.main()
