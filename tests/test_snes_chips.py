import unittest
from smsrecomp.snes_chips import identify
from smsrecomp.snes_cart import layout_bytes,ram_offset
from smsrecomp.snes_codegen import native_source
from smsrecomp.supernintendo import validate_cartridge,support_stage
from smsrecomp.cartridge16 import snes_header
from smsrecomp.core import ConversionError
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
        for mode,kind,sub in ((0x30,3,0),(0x20,5,0),(0x30,5,0),(0x20,0xf3,0),(0x20,0x13,0),(0x20,0x43,0)):
            with self.subTest(mode=mode,kind=kind):
                with self.assertRaises(ConversionError):identify(self.rom(mode,kind,sub).data)
    def test_support_remains_scoped_to_qualified_circuits(self):
        for mode in (0x20,0x21,0x30,0x31):
            for kind in (0,1,2):
                with self.subTest(mode=mode,kind=kind):
                    self.assertEqual(support_stage(self.rom(mode,kind,ram=int(kind!=0))),'supported')
        for mode,kind,sub in ((0x20,3,0),(0x31,5,0),(0x20,0xf3,0x10)):
            self.assertEqual(support_stage(self.rom(mode,kind,sub)),'supported')
        for mode,kind in ((0x23,0x35),(0x20,0x13),(0x20,0x43)):
            with self.assertRaises(ConversionError):support_stage(self.rom(mode,kind))
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
            self.assertIn('g_snes->cart->type != '+cart,source)
            self.assertIn('g_snes->cart->romImageSize != 65536u',source)
            self.assertIn('fetched==operation->opcode',source)
            self.assertIn('cart_getRomPtr',source)
    def test_sa1_header_is_identified_before_explicit_hardware_refusal(self):
        rom=self.rom(0x23,0x35)
        self.assertEqual(snes_header(rom.data),(0x7fc0,'lorom'))
        with self.assertRaisesRegex(ConversionError,'SA-1'):
            validate_cartridge(rom)
if __name__=='__main__':unittest.main()
