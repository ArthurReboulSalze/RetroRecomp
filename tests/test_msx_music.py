"""MSX-MUSIC, the MSX2+'s YM2413 (native/msx_machine/msx_music.c on emu2413): the vendored files, the generated quick-state copy of
the chip, the BIOS source and the runners' options, the FM BIOS check, the profile; and the player's own kanji font. No ROM, no
compiler."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'native' / 'msx_machine' / 'emu2413'


class VendoredTests(unittest.TestCase):
    def test_emu2413_is_the_pinned_upstream_unmodified(self):
        revision = json.loads((VENDOR / 'revision.json').read_text(encoding='utf-8'))
        self.assertEqual(revision['repository'], 'https://github.com/digital-sound-antiques/emu2413')
        for name, digest in revision['sha256'].items():
            self.assertEqual(hashlib.sha256((VENDOR / name).read_bytes()).hexdigest(), digest, name)
        self.assertIn('emu2413 v1.5.9', (VENDOR / 'emu2413.c').read_text(encoding='utf-8')[:200])

    def test_a_silent_still_chip_takes_the_quiet_step(self):
        # 1.9.0 frame cost: the quiet step runs only what still moves in a silent, still chip; a write, a reset or a loaded state
        # asks again. msx_music_checks.c proves it sample by sample against OPLL_calc.
        music = (ROOT / 'native/msx_machine/msx_music.c').read_text(encoding='utf-8')
        self.assertIn('static bool music_quiet(const OPLL *opll)', music)
        self.assertIn('c->out = music_calc_quiet(c->opll);', music)
        quiet_step = music[music.index('static int16_t music_calc_quiet('):music.index('static void music_write(')]
        for call in ('update_ampm(opll);', 'update_short_noise(opll);', 'opll->eg_counter++;', 'update_noise(opll, 14);',
                     'mix_output(opll);'):
            self.assertIn(call, quiet_step)
        self.assertEqual(music.count('c->quiet = false;'), 3)          # a write, a reset, a loaded state

    def test_the_quiet_step_check_runs_with_the_msx_fixtures(self):
        import importlib
        reference = importlib.import_module('tools.msx_reference')
        self.assertIn('msx_music_checks', reference.CHECK_PROGRAMS)
        self.assertTrue((ROOT / 'native/msx_machine/msx_music_checks.c').is_file())

    def test_the_state_copy_is_generated_from_the_vendored_header(self):
        from retrorecomp import nes_state_layout
        known = nes_state_layout.parse((VENDOR / 'emu2413.h').read_text(encoding='utf-8'), {'OPLL_PATCH', 'OPLL_SLOT', 'OPLL'})
        fresh = nes_state_layout.generate(known, ['OPLL'])
        self.assertEqual((ROOT / 'native' / 'msx_machine' / 'msx_opll_state.inc').read_text(encoding='utf-8'), fresh)
        # The three host pointers are not written by it: msx_music.c saves the patch and wave table as indexes, and the chip runs
        # at its own rate, with no converter.
        skipped = {(row['struct'], row['member']) for row in nes_state_layout.audit(known, ['OPLL']) if not row['written']}
        self.assertEqual(skipped, {('OPLL_SLOT', 'patch'), ('OPLL_SLOT', 'wave_table'), ('OPLL', 'conv')})


class BiosSourceTests(unittest.TestCase):
    def test_the_fm_bios_ends_the_msx2plus_bios_source(self):
        from retrorecomp.msx_conversion import _bios_files
        image = bytes(range(256)) * 0x100 + b'\xFF' * 0x4000 + b'AB' + b'\x00' * 0x16 + b'APRLOPLL' + b'\x00' * (0x4000 - 0x20)
        self.assertEqual(len(image), 0x18000)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            args = _bios_files(work, image, True, 256, True)
            self.assertIn('--fmbios', args)
            self.assertNotIn('--diskrom', args)                      # a cartridge game: no disk interface
            self.assertEqual((work / 'bios_fm.rom').read_bytes(), image[0x14000:])
            disk = _bios_files(work, image, True, 256, True, disk=True)
            self.assertIn('--diskrom', disk)
            msx2 = _bios_files(work, image[:0x10000], True, 256, False)
            self.assertNotIn('--fmbios', msx2)                       # the MSX2 has no MSX-MUSIC

    def test_an_fm_bios_must_carry_its_signature(self):
        from retrorecomp.msx_conversion import ConversionError, own_fmbios
        with tempfile.TemporaryDirectory() as folder:
            good, bad = Path(folder) / 'fm.rom', Path(folder) / 'bad.rom'
            good.write_bytes(b'AB' + b'\x00' * 0x16 + b'APRLOPLL' + b'\x00' * (0x4000 - 0x20))
            bad.write_bytes(b'AB' + b'\x00' * (0x4000 - 2))
            self.assertEqual(len(own_fmbios(good)), 0x4000)
            with self.assertRaises(ConversionError):
                own_fmbios(bad)

    def test_c_bios_music_rom_is_pinned(self):
        from retrorecomp import msx_cbios
        self.assertEqual(msx_cbios.MEMBERS['cbios_music.rom'][0], 0x4000)


class BuildTests(unittest.TestCase):
    def test_only_an_msx2plus_work_folder_builds_msx_music(self):
        from retrorecomp import msx_build
        with_music = msx_build.project_cmake('0', True, True, music=True)
        without = msx_build.project_cmake('0', True, True, music=False)
        self.assertIn('msx_music.c', with_music)
        self.assertIn('RR_MSX_MUSIC=1', with_music)
        self.assertNotIn('msx_music', without)
        self.assertNotIn('RR_MSX_MUSIC', without)
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            msx_build.set_music(work, True)
            self.assertTrue((work / msx_build.MUSIC_MARK).is_file())
            msx_build.set_music(work, False)
            self.assertFalse((work / msx_build.MUSIC_MARK).exists())

    def test_the_profile_offers_the_fm_bios_and_names_emu2413(self):
        from retrorecomp.systems import get_profile
        plus = get_profile('msx2plus')
        self.assertIn('msx2plus_fmbios', [key.name for key in plus.option_keys])
        self.assertIn('licenses/emu2413.md', plus.notice_files)
        self.assertNotIn('licenses/emu2413.md', get_profile('msx2').notice_files)


class KanjiTests(unittest.TestCase):
    """The player's own kanji font (ports D8h-DBh, msx_set_kanji; the C checks are in msx_hardware_checks.c)."""

    def test_a_kanji_font_is_128_or_256_kib_of_glyphs(self):
        from retrorecomp.msx_conversion import ConversionError, own_kanji
        with tempfile.TemporaryDirectory() as folder:
            for size in (0x20000, 0x40000):
                font = Path(folder) / f'{size}.rom'
                font.write_bytes(bytes(range(256)) * (size // 256))
                self.assertEqual(len(own_kanji(font)), size)
            for name, data in (('short.rom', bytes(range(256)) * 0x100), ('blank.rom', b'\xFF' * 0x20000)):
                (Path(folder) / name).write_bytes(data)
                with self.assertRaises(ConversionError):
                    own_kanji(Path(folder) / name)

    def test_the_msx2plus_offers_the_kanji_font(self):
        from retrorecomp.systems import get_profile
        self.assertIn('msx2plus_kanji', [key.name for key in get_profile('msx2plus').option_keys])
        self.assertNotIn('msx2_kanji', [key.name for key in get_profile('msx2').option_keys])


if __name__ == '__main__':
    unittest.main()
