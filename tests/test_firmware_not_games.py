"""Firmware and add-on cartridges dropped by mistake are refused with their reason, not converted as games.

Authored headers only: the few bytes each image is known by, never ROM content. Audit of 27 November 2026 (1,503 files of a
player's bios folder): these were taken for games. Each class below belongs to one machine.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from retrorecomp.batch import identify


class FirmwareCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, name: str, data: bytes) -> Path:
        path = self.root / name
        path.write_bytes(data)
        return path

    def refused(self, path: Path, *words: str):
        item = identify(path)
        self.assertEqual(item.system, '', item)
        self.assertTrue(item.error, 'a refusal carries its reason')
        for word in words:
            self.assertIn(word, item.error)

    def accepted(self, path: Path, system: str):
        item = identify(path)
        self.assertEqual((item.system, item.error), (system, ''))


def megadrive_image(size: int, title: bytes) -> bytes:
    data = bytearray(size)
    data[0x100:0x110] = b'SEGA MEGA DRIVE '
    data[0x120:0x120 + len(title)] = title
    data[0x150:0x150 + len(title)] = title
    return bytes(data)


class MegaDriveFirmwareTests(FirmwareCase):
    def test_the_mega_cd_boot_rom_is_not_a_mega_drive_game(self):
        for name, title in (('bios_CD_U.bin', b'CD2 BOOT ROM'), ('bios_CD_J.md', b'MEGA-CD BOOT ROM')):
            with self.subTest(name):
                self.refused(self.make(name, megadrive_image(0x20000, title)), 'Mega-CD boot ROM', 'not a game')

    def test_a_cartridge_of_the_same_size_stays_a_game(self):
        self.accepted(self.make('game.bin', megadrive_image(0x20000, b'AUTHORED GAME')), 'md')
        self.accepted(self.make('big.bin', megadrive_image(0x40000, b'CD2 BOOT ROM')), 'md')   # the size is part of the rule


if __name__ == '__main__':
    unittest.main()
