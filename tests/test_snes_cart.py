import unittest
import tempfile,json
from pathlib import Path
from types import SimpleNamespace
from smsrecomp import snes_cart, supernintendo
from smsrecomp.core import ConversionError
from tools.snes_scheduler_selftest import cartridge


class SnesCartridgeTests(unittest.TestCase):
    def rom(self, mapping='lorom', chip=2, exponent=3, size=0x10000):
        data = cartridge(bytes.fromhex('40'), False)
        data.extend(bytes(size-len(data)))
        if mapping == 'hirom':
            data[0xffc0:0x10000] = data[0x7fc0:0x8000]
            data[0x7fc0:0x8000] = bytes(64)
        offset = 0x7fc0 if mapping == 'lorom' else 0xffc0
        data[offset+21] = 0x20 if mapping == 'lorom' else 0x21
        data[offset+22] = chip
        data[offset+24] = exponent
        return SimpleNamespace(data=bytes(data), mapping=mapping)

    def test_ram_zero_and_battery_are_distinct(self):
        for chip, exponent, size, battery in ((0,3,0,False), (1,3,8192,False),
                                             (2,3,8192,True), (2,0,0,False)):
            memory=snes_cart.layout(self.rom(chip=chip,exponent=exponent))
            self.assertEqual((memory['bytes'],memory['battery']), (size,battery))

    def test_large_or_malformed_exponent_is_rejected_before_allocation(self):
        for exponent in (8,31,255):
            with self.assertRaises(ConversionError):
                snes_cart.layout(self.rom(exponent=exponent))

    def test_lorom_ram_windows_preserve_wram_and_rom(self):
        memory=snes_cart.layout(self.rom())
        for adr, offset in ((0x700000,0), (0xf00000,0), (0x708123,0x123),
                            (0xf0ffff,0x1fff), (0x7e0000,None), (0x7f0000,None),
                            (0x006000,None), (0x6f0000,None), (0x008000,None)):
            self.assertEqual(snes_cart.ram_offset(memory,adr),offset)
        large=snes_cart.layout(self.rom(size=0x400000))
        self.assertIsNone(snes_cart.ram_offset(large,0xf08000))

    def test_hirom_only_decodes_real_cartridge_windows(self):
        memory=snes_cart.layout(self.rom('hirom',exponent=7))
        for adr, offset in ((0x206000,0), (0xa06000,0), (0x216123,0x2123),
                            (0xbfffff,None), (0x1f6000,None), (0x806000,None),
                            (0x205fff,None), (0x208000,None), (0x406000,None)):
            self.assertEqual(snes_cart.ram_offset(memory,adr),offset)

    def test_code_guard_cannot_cross_a_ram_window_into_io_or_rom(self):
        rom=self.rom('hirom')
        valid=lambda adr: supernintendo.valid_ram_variant({'address':adr,'bytes':'a93412ea'},rom)
        self.assertTrue(valid(0xa06000))
        self.assertTrue(valid(0x207ffc))
        self.assertFalse(valid(0x207ffd))
        self.assertFalse(valid(0x1f6000))
        self.assertTrue(valid(0x7fffff))  # The 65816 operand wraps within its program bank.

    def test_sram_observation_is_rom_specific_and_requires_cartridge_ram(self):
        item={'address':0xf00000,'bytes':'a93412ea'}
        self.assertFalse(supernintendo.valid_ram_variant(item))
        self.assertFalse(supernintendo.valid_ram_variant(item,self.rom(chip=0)))
        self.assertTrue(supernintendo.valid_ram_variant(item,self.rom()))

    def test_pinned_cart_changes_fail_closed(self):
        with self.assertRaises(ConversionError):
            snes_cart.adapt_cart('#include "cart.h"\nchanged')
        with self.assertRaises(ConversionError):
            snes_cart.adapt_loader('changed')

    def test_short_build_names_keep_exact_identity_and_resolve_prefix_collisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rom=SimpleNamespace(sha256='a'*64)
            profile={'source':'cartridge','id':'rom-'+rom.sha256}
            first=supernintendo.project_path(root,rom,profile)
            self.assertEqual(first.name,'snes-rom-'+rom.sha256[:16])
            first.mkdir(parents=True);marker=first/'generation-identity.json'
            marker.write_text(json.dumps({'rom':'a'*16+'b'*48}))
            second=supernintendo.project_path(root,rom,profile)
            self.assertEqual(second.name,'snes-rom-'+rom.sha256[:32])
            marker.write_text(json.dumps({'rom':rom.sha256}))
            self.assertEqual(supernintendo.project_path(root,rom,profile),first)

    def test_incomplete_build_does_not_overwrite_another_cartridge(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rom=SimpleNamespace(sha256='a'*64)
            profile={'source':'cartridge','id':'rom-'+rom.sha256}
            first=supernintendo.project_path(root,rom,profile);first.mkdir(parents=True)
            cartridge=first/'cartridge.sfc';cartridge.write_bytes(b'another cartridge')
            self.assertNotEqual(supernintendo.project_path(root,rom,profile),first)
            self.assertEqual(cartridge.read_bytes(),b'another cartridge')


if __name__ == '__main__':
    unittest.main()
