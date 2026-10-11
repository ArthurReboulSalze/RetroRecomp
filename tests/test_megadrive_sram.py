"""Cartridge RAM capability checks with authored headers."""
from types import SimpleNamespace
import unittest
from smsrecomp.core import ConversionError
from smsrecomp.megadrive_sram import layout


def rom(ram_type=0xf8, start=0x200001, end=0x203fff, device=0x20):
    data=bytearray(0x100000)
    data[0x1b0:0x1bc]=b'RA'+bytes((ram_type,device))+start.to_bytes(4,'big')+end.to_bytes(4,'big')
    return SimpleNamespace(data=data)


class CartridgeRamTests(unittest.TestCase):
    def test_all_declared_lanes_and_battery_types(self):
        for ram_type in (0xa0,0xb0,0xb8,0xe0,0xf0,0xf8):
            stride=2 if ram_type&0x10 else 1
            lane=(ram_type>>3)&1
            start=0x200000+(lane if stride==2 else 0)
            end=0x203fff-(not lane if stride==2 else 0)
            with self.subTest(ram_type=ram_type):
                actual=layout(rom(ram_type,start,end))
                self.assertEqual(actual['bytes'],8192 if stride==2 else 16384)
                self.assertEqual(actual['stride'],stride)
                self.assertEqual(actual['battery'],bool(ram_type&0x40))
                self.assertFalse(actual['overlays_rom'])

    def test_overlapping_and_one_byte_geometry(self):
        self.assertTrue(layout(rom(start=0x80001,end=0x803ff))['overlays_rom'])
        self.assertEqual(layout(rom(end=0x200001))['bytes'],1)
        self.assertEqual(layout(rom(end=0x21ffff))['bytes'],65536)

    def test_invalid_geometry_is_explained_before_building(self):
        for cartridge in (rom(start=0x200000),rom(end=0x203ffe),rom(end=0x220001),
                          rom(end=0x1fffff),rom(end=0x400001),rom(0xe0,0x200001),
                          rom(0xe8),rom(device=0x30)):
            with self.subTest(header=cartridge.data[0x1b0:0x1bc].hex()):
                with self.assertRaises(ConversionError):layout(cartridge)

    def test_eeprom_is_not_parallel_ram(self):
        actual=layout(rom(0xe8,end=0x200001,device=0x40))
        self.assertEqual(actual['kind'],'eeprom')
        self.assertFalse(actual['implemented'])
        self.assertEqual(actual['bytes'],0)


if __name__=='__main__':unittest.main()
