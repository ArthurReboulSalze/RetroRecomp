"""The cartridges authored by tools/gameboy_saves_check.py (gate G7), without converting anything: the header must be one the converter
accepts, the programs must fit their relative jumps, and the pattern the check expects must be the one the program writes."""
import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('gameboy_saves_check', Path(__file__).resolve().parents[1] / 'tools' / 'gameboy_saves_check.py')
saves = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(saves)


class AuthoredCartridgeTests(unittest.TestCase):
    def test_every_cartridge_has_a_valid_header(self):
        for name, (header_type, ram_code, _kind, _writes, _kept) in saves.CARTRIDGES.items():
            rom = saves.authored_rom(name)
            self.assertEqual(len(rom), 0x8000, name)
            self.assertEqual((rom[0x147], rom[0x149]), (header_type, ram_code), name)
            checksum = 0
            for index in range(0x134, 0x14D):
                checksum = (checksum - rom[index] - 1) & 0xFF
            self.assertEqual(rom[0x14D], checksum, name)
            self.assertEqual(rom[0x100:0x104], bytes.fromhex('00c35001'), name)

    def test_titles_are_distinct_and_ascii(self):
        titles = {bytes(saves.authored_rom(name)[0x134:0x143]).rstrip(b'\0').decode('ascii') for name in saves.CARTRIDGES}
        self.assertEqual(len(titles), len(saves.CARTRIDGES))

    def test_the_program_ends_in_a_spin_and_fits_the_first_bank(self):
        for name, (_type, _ram, kind, writes, _kept) in saves.CARTRIDGES.items():
            code = saves.program(kind, writes)
            self.assertLess(0x150 + len(code), 0x8000, name)
            self.assertEqual(code[-2:], bytes((0x18, 0xFE)), name)          # JR to itself

    def test_a_cartridge_that_does_not_write_is_shorter(self):
        self.assertLess(len(saves.program('mbc1', False)), len(saves.program('mbc1', True)))

    def test_only_the_clock_cartridge_touches_the_clock(self):
        self.assertIn(bytes((0xEA, 0x00, 0x60)), saves.program('mbc3'))     # the latch register
        self.assertNotIn(bytes((0xEA, 0x00, 0x60)), saves.program('mbc1'))

    def test_the_expected_copy_follows_the_program(self):
        full = saves.expected_copy('mbc1')
        self.assertEqual(len(full), 32)
        self.assertEqual(full[:4], [0x52, 0x52, 0x53, 0xC3])
        self.assertEqual(full[4:8], [7, 10, 13, 16])
        nibbles = saves.expected_copy('mbc2')
        self.assertTrue(all(value < 16 for value in nibbles))
        self.assertEqual(nibbles[:4], [2, 2, 3, 3])


if __name__ == '__main__':
    unittest.main()
