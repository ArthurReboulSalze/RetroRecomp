import tempfile
import unittest
import zlib
from pathlib import Path

from smsrecomp.core import ConversionError, read_rom, slug


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


if __name__ == "__main__":
    unittest.main()
