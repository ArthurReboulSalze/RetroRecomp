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


def snes_image(title: bytes, size: int = 0x80000, magic: bytes = b'') -> bytes:
    """A LoROM image with a header that passes the SNES checks: title, map mode 20h, size, reset vector, checksum pair."""
    data = bytearray(size)
    data[0:len(magic)] = magic
    data[0x20] = 0x78                                   # SEI where the reset vector points (8020h)
    data[0x7fc0:0x7fc0 + 21] = title.ljust(21)
    data[0x7fd5] = 0x20
    data[0x7fd7] = 9                                    # 512 KiB
    data[0x7ffc:0x7ffe] = (0x8020).to_bytes(2, 'little')
    checksum = sum(data) & 0xffff
    data[0x7fdc:0x7fde] = (checksum ^ 0xffff).to_bytes(2, 'little')
    data[0x7fde:0x7fe0] = checksum.to_bytes(2, 'little')
    return bytes(data)


class SnesFirmwareTests(FirmwareCase):
    def test_the_authored_game_is_a_game(self):
        self.accepted(self.make('game.sfc', snes_image(b'AUTHORED GAME')), 'snes')

    def test_the_satellaview_bios_is_firmware(self):
        self.refused(self.make('BS-X.bin', snes_image(b'Satellaview BS-X')), 'BS-X', 'not a game')

    def test_the_super_game_boy_cartridges_are_firmware(self):
        for name, title in (('SGB1.sfc', b'Super GAMEBOY'), ('SGB2.sfc', b'Super GAMEBOY2')):
            with self.subTest(name):
                self.refused(self.make(name, snes_image(title)), 'Super Game Boy', 'not a game')

    def test_the_sufami_turbo_base_is_firmware(self):
        self.refused(self.make('STBIOS.bin', snes_image(b'ADD-ON BASE CASSETE')), 'Sufami Turbo base', 'not a game')

    def test_a_sufami_turbo_game_is_not_supported_and_says_so(self):
        game = snes_image(b'AUTHORED MINI', magic=b'BANDAI SFC-ADX\0\0SFC-ADX BACKUP\0\0')
        self.refused(self.make('mini.smc', game), 'Sufami Turbo', 'not supported')


class PcEngineFirmwareTests(FirmwareCase):
    """The System Card is known by its SHA-1 (retrorecomp/pcecd_card.py, the table the firmware search reads too). An authored image
    cannot have that hash, so the table is patched with the authored image's own: the rule under test is the lookup."""

    def card_image(self) -> bytes:
        data = bytearray(256 * 1024)
        data[0x1FFE:0x2000] = (0xE000).to_bytes(2, 'little')   # bank 0's reset vector, on a SEI: it passes as a HuCard
        data[0] = 0x78
        return bytes(data)

    def test_a_known_system_card_dropped_as_a_pce_is_firmware(self):
        import hashlib
        from unittest.mock import patch
        from retrorecomp import pcecd_card
        image = self.card_image()
        known = pcecd_card.KnownCard(hashlib.sha1(image).hexdigest(), 'Super System Card', '3.0', 'japan', 'panel')
        with patch.dict(pcecd_card.BY_SHA1, {known.sha1: known}):
            self.refused(self.make('syscard3.pce', image), 'System Card of the PC Engine CD', 'not a game')

    def test_a_256_kib_cartridge_that_is_no_known_card_is_still_a_game(self):
        self.accepted(self.make('game.pce', self.card_image()), 'pce')

    def test_the_firmware_search_still_finds_the_card(self):
        import hashlib
        from unittest.mock import patch
        from retrorecomp import firmware_search, pcecd_card
        image = self.card_image()
        known = pcecd_card.KnownCard(hashlib.sha1(image).hexdigest(), 'Super System Card', '3.0', 'japan', 'panel')
        path = self.make('syscard3.pce', image)
        with patch.dict(pcecd_card.BY_SHA1, {known.sha1: known}):
            hits = firmware_search.CHECKS['pcecd'].identify(path)
        self.assertEqual([hit[0] for hit in hits], ['pcecd_system_card'])


if __name__ == '__main__':
    unittest.main()
