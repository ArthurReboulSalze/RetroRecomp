import unittest
from retrorecomp.snes_chips import identify
from retrorecomp.snes_cart import layout_bytes,ram_offset
from retrorecomp.snes_codegen import native_source
from retrorecomp.supernintendo import validate_cartridge,support_stage
from retrorecomp.cartridge16 import snes_header
from retrorecomp.core import ConversionError
from tools.snes_scheduler_selftest import cartridge
from tests.test_snes import source_fixture
from types import SimpleNamespace

class ChipTests(unittest.TestCase):
    def rom(self,mode,kind,sub=0,ram=0):
        data=cartridge(bytes.fromhex('40'));data.extend(bytes(0x10000-len(data)))
        mapping='hirom' if mode in (0x21,0x31,0x3a) else 'lorom';offset=0xffc0 if mapping=='hirom' else 0x7fc0
        if mapping=='hirom':
            data[0xffc0:0x10000]=data[0x7fc0:0x8000];data[0x7fc0:0x8000]=bytes(64)
        data[offset+21:offset+25]=bytes((mode,kind,6,ram));data[offset-1]=sub
        return SimpleNamespace(data=bytes(data),mapping=mapping)
    def test_header_support_is_circuit_scoped_and_not_title_scoped(self):
        for mode,kind,sub,want in ((0x20,3,0,'dsp1-lo'),(0x31,5,0,'dsp1-hi'),(0x20,0xf3,0x10,'cx4')):
            rom=self.rom(mode,kind,sub);self.assertEqual(identify(rom.data),want)
            validate_cartridge(rom)
        for mode,kind,sub in ((0x30,3,0),(0x20,5,0),(0x30,5,0),(0x20,0xf3,0),(0x20,0x16,0),(0x21,0x13,0),(0x20,0x43,0)):
            with self.subTest(mode=mode,kind=kind):
                with self.assertRaises(ConversionError):identify(self.rom(mode,kind,sub).data)
    def test_support_remains_scoped_to_qualified_circuits(self):
        for mode in (0x20,0x21,0x30,0x31):
            for kind in (0,1,2):
                with self.subTest(mode=mode,kind=kind):
                    self.assertEqual(support_stage(self.rom(mode,kind,ram=int(kind!=0))),'supported')
        for mode,kind,sub in ((0x20,3,0),(0x31,5,0),(0x20,0xf3,0x10)):
            self.assertEqual(support_stage(self.rom(mode,kind,sub)),'supported')
        for mode,kind in ((0x23,0x35),(0x20,0x16),(0x20,0x43)):
            with self.assertRaises(ConversionError):support_stage(self.rom(mode,kind))
    def test_exlorom_mode_byte_without_a_chip_is_an_ordinary_lorom_but_no_circuit_board_is(self):
        # Duel: Test Drive II and a Popeye translation carry $32 with chip type 0 and no RAM.
        for kind in (0, 1, 2):
            with self.subTest(kind=kind):
                rom = self.rom(0x32, kind, ram=int(kind != 0))
                self.assertEqual(identify(rom.data), 'none')
                self.assertEqual((rom.mapping, support_stage(rom)), ('lorom', 'supported'))
        # The S-DD1 boards (Star Ocean $45, Street Fighter Alpha 2 $43) and every other chip type stay refused,
        # as does an image above 4 MiB.
        for kind in (0x43, 0x45, 0x03, 0x05, 0x13, 0x35, 0xf6, 0xf9, 0xe3):
            with self.subTest(kind=kind):
                with self.assertRaises(ConversionError):
                    support_stage(self.rom(0x32, kind))
        big = self.rom(0x32, 0)
        big.data = big.data + bytes(0x400000)
        with self.assertRaises(ConversionError):
            support_stage(big)
        # Other mode bytes that were refused before are still refused.
        for mode in (0x22, 0x23, 0x33, 0x3a):
            with self.subTest(mode=mode):
                with self.assertRaises(ConversionError):
                    support_stage(self.rom(mode, 0))
    def test_dsp1_battery_window_does_not_become_code_or_overlap_ports(self):
        rom=self.rom(0x31,5,ram=1);memory=layout_bytes(rom.data,rom.mapping)
        self.assertEqual((memory['bytes'],memory['battery']),(2048,True))
        self.assertEqual(ram_offset(memory,0x206000),0)
        for addr in (0x006000,0x007000,0x708000,0x700000):self.assertIsNone(ram_offset(memory,addr))
        self.assertEqual(ram_offset(memory,0xa067ff),2047)
    def test_native_lookup_still_guards_exact_chip_size_and_fetched_opcode(self):
        for mode,kind,sub,cart in ((0x20,3,0,'CART_DSP1'),(0x31,5,0,'CART_DSP1_HIROM'),(0x20,0xf3,0x10,'CART_CX4')):
            rom=self.rom(mode,kind,sub)
            source=native_source(source_fixture(),rom.data,mapping=rom.mapping)
            self.assertIn('cart->type == '+cart,source)
            self.assertIn('cart->romImageSize == 65536u',source)
            self.assertIn('fetched==operation->opcode',source)
            self.assertIn('cart_getRomPtr',source)
            self.assertNotIn('CART_SUPERFX',source)
    def test_superfx_boards_are_supported_with_their_game_pak_ram(self):
        for kind,battery in ((0x13,False),(0x14,False),(0x15,True),(0x1a,True)):
            with self.subTest(kind=kind):
                rom=self.rom(0x20,kind)
                self.assertEqual(identify(rom.data),'superfx')
                self.assertEqual(support_stage(rom),'supported')
                memory=layout_bytes(rom.data,rom.mapping)
                # Without a version-3 header ($33 maker) the loader's 64 KiB default applies.
                self.assertEqual((memory['bytes'],memory['battery']),(0x10000,battery))
                # Game Pak RAM shared with the GSU never becomes guarded 65816 code.
                for addr in (0x700000,0x710000,0x006000,0x7fe000):self.assertIsNone(ram_offset(memory,addr))
        data=bytearray(self.rom(0x20,0x15).data);data[0x7fda]=0x33;data[0x7fbd]=5
        self.assertEqual(layout_bytes(bytes(data),'lorom')['bytes'],0x8000)
        source=native_source(source_fixture(),self.rom(0x20,0x14).data,mapping='lorom')
        self.assertIn('cart->type == CART_SUPERFX',source)
        self.assertIn('rr_sn_rom_ptr',source)
        self.assertNotIn('cart_getRomPtr',source)
        self.assertIn('fetched==operation->opcode',source)
    def test_sa1_header_is_identified_before_explicit_hardware_refusal(self):
        rom=self.rom(0x23,0x35)
        self.assertEqual(snes_header(rom.data),(0x7fc0,'lorom'))
        with self.assertRaisesRegex(ConversionError,'SA-1'):
            validate_cartridge(rom)
if __name__=='__main__':unittest.main()
