import tempfile
import tomllib
import unittest
import zlib
from pathlib import Path

from smsrecomp.core import ConversionError, read_rom, set_video_standard, slug, video_standard
from smsrecomp.systems import MASTER_SYSTEM, get_profile, profile_for_path


class RomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "cartouche.sms"
        self.data = bytearray(32768)
        self.data[0x7FF0:0x7FF8] = b"TMR SEGA"
        self.data[0x7FFF] = 0x4C

    def test_copier_header_and_raw_rom_have_same_identity(self):
        self.path.write_bytes(self.data)
        raw = read_rom(self.path)
        self.path.write_bytes(b"x" * 512 + self.data)
        copier = read_rom(self.path)
        self.assertEqual(raw.sha256, copier.sha256)
        self.assertEqual(raw.crc32, copier.crc32)
        self.assertEqual(raw.crc32, zlib.crc32(self.data))
        self.assertTrue(copier.copier_header)

    def test_game_gear_does_not_silently_become_master_system(self):
        self.data[0x7FFF] = 0x6C
        self.path.write_bytes(self.data)
        with self.assertRaisesRegex(ConversionError, "Game Gear"):
            read_rom(self.path)

    def test_truncated_dump_is_rejected(self):
        self.path.write_bytes(self.data[:-1])
        with self.assertRaises(ConversionError):
            read_rom(self.path)

    def test_output_name_cannot_escape_directory(self):
        self.assertEqual(slug("../../été : / test"), "ete_test")
        self.assertNotIn("/", slug("../test"))

    def test_europe_only_uses_pal_without_treating_export_header_as_timing(self):
        for suffix, expected in (("(Europe)", "pal"), ("[Europe]", "pal"),
                                 ("(USA, Europe)", "ntsc"), ("(World)", "ntsc")):
            with self.subTest(suffix=suffix):
                path = self.path.with_name(f"Fixture {suffix}.sms")
                path.write_bytes(self.data)
                rom = read_rom(path)
                self.assertEqual(rom.region, 4)
                self.assertEqual(video_standard(rom), expected)

    def test_master_system_is_registered_without_claiming_other_consoles(self):
        self.assertIs(get_profile('sms'), MASTER_SYSTEM)
        self.assertIs(profile_for_path(self.path), MASTER_SYSTEM)
        self.assertEqual(MASTER_SYSTEM.video_modes, ('ntsc', 'pal'))
        with self.assertRaises(ValueError):
            profile_for_path(self.path.with_suffix('.nes'))
        with self.assertRaises(ValueError):
            get_profile('nes')

    def test_video_choice_is_written_once_and_preserves_other_profile_sections(self):
        profile = '[game]\nplatform = "sms"\n\n[video]\nstandard = "ntsc"\n\n[mapper]\nkind = "sega"\n'
        updated = set_video_standard(profile, 'pal')
        self.assertEqual(tomllib.loads(updated)['video']['standard'], 'pal')
        self.assertEqual(tomllib.loads(updated)['mapper']['kind'], 'sega')
        self.assertEqual(updated.count('standard ='), 1)
        self.assertEqual(set_video_standard(updated, 'pal'), updated)
        self.assertEqual(tomllib.loads(set_video_standard('[game]\nplatform = "sms"\n', 'ntsc'))['video']['standard'], 'ntsc')
        with self.assertRaises(ConversionError):
            set_video_standard(profile, 'secam')


if __name__ == "__main__":
    unittest.main()
