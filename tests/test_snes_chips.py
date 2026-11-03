import unittest
from pathlib import Path
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
        for mode,kind,sub,want in ((0x20,3,0,'dsp1-lo'),(0x31,5,0,'dsp1-hi'),(0x31,3,0,'dsp1-hi'),(0x20,0xf3,0x10,'cx4')):
            rom=self.rom(mode,kind,sub);self.assertEqual(identify(rom.data),want)
            validate_cartridge(rom)
        for mode,kind,sub in ((0x30,3,0),(0x20,5,0),(0x30,5,0),(0x20,0xf3,0),(0x20,0x16,0),(0x21,0x13,0),(0x20,0x43,0),(0x21,3,0),(0x21,5,0),(0x30,5,0)):
            with self.subTest(mode=mode,kind=kind):
                with self.assertRaises(ConversionError):identify(self.rom(mode,kind,sub).data)
    def test_support_remains_scoped_to_qualified_circuits(self):
        for mode in (0x20,0x21,0x30,0x31):
            for kind in (0,1,2):
                with self.subTest(mode=mode,kind=kind):
                    self.assertEqual(support_stage(self.rom(mode,kind,ram=int(kind!=0))),'supported')
        for mode,kind,sub in ((0x20,3,0),(0x31,5,0),(0x31,3,0),(0x20,0xf3,0x10)):
            self.assertEqual(support_stage(self.rom(mode,kind,sub)),'supported')
        for mode,kind in ((0x20,0x16),(0x20,0x43),(0x23,0x33),(0x23,0x36),(0x33,0x35),(0x21,0x35)):
            with self.assertRaises(ConversionError):support_stage(self.rom(mode,kind))
    def test_exlorom_mode_byte_without_a_chip_is_an_ordinary_lorom_but_no_circuit_board_is(self):
        # Duel: Test Drive II and a Popeye translation carry $32 with chip type 0 and no RAM.
        for kind in (0, 1, 2):
            with self.subTest(kind=kind):
                rom = self.rom(0x32, kind, ram=int(kind != 0))
                self.assertEqual(identify(rom.data), 'none')
                self.assertEqual((rom.mapping, support_stage(rom)), ('lorom', 'supported'))
        # Every other chip type stays refused under mode $32 (the S-DD1 types $43/$45 are boards of their own, below),
        # as does an image above 4 MiB.
        for kind in (0x03, 0x05, 0x13, 0x35, 0xf6, 0xf9, 0xe3, 0x44, 0x46, 0x53):
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
    def test_sdd1_boards_are_recognised_by_map_and_type_and_stay_within_4_mib(self):
        # Street Fighter Alpha 2 ($32 / $43, no RAM) and Star Ocean ($32 / $45, RAM and a battery).
        for kind,battery,ram in ((0x43,False,0),(0x45,True,3)):
            with self.subTest(kind=kind):
                rom=self.rom(0x32,kind,ram=ram)
                self.assertEqual(identify(rom.data),'sdd1')
                self.assertEqual(support_stage(rom),'supported')
                memory=layout_bytes(rom.data,rom.mapping)
                self.assertEqual((memory['bytes'],memory['battery'],memory['chip']),((0x2000 if ram else 0),battery,'sdd1'))
        # Another mode byte with an S-DD1 type, or another type with the ExLoROM byte, is not an S-DD1 board.
        for mode,kind in ((0x31,0x45),(0x20,0x43),(0x32,0x44),(0x32,0x46)):
            with self.subTest(mode=mode,kind=kind):
                with self.assertRaises(ConversionError):
                    support_stage(self.rom(mode,kind))
        # Star Ocean is 6 MiB: the S-DD1's pages reach 8 MiB (1.6.7), nothing else goes above 4 MiB.
        big=self.rom(0x32,0x45,ram=3)
        big.data=big.data+bytes(0x500000)
        self.assertEqual(support_stage(big),'supported')
        huge=self.rom(0x32,0x45,ram=3)
        huge.data=huge.data+bytes(0x900000)
        with self.assertRaisesRegex(ConversionError,'4 MiB'):
            support_stage(huge)
        ordinary=self.rom(0x20,2,ram=3)
        ordinary.data=ordinary.data+bytes(0x500000)
        with self.assertRaisesRegex(ConversionError,'4 MiB'):
            support_stage(ordinary)
    def test_hirom_dsp1_board_without_ram_has_the_dsp_window_and_no_battery_window(self):
        # Lock On, Suzuka 8 Hours, Super Air Diver 2... carry $31 / $03: the HiROM DSP-1 board of Super Mario Kart
        # ($31 / $05) without its battery RAM.
        rom=self.rom(0x31,3);memory=layout_bytes(rom.data,rom.mapping)
        self.assertEqual((memory['bytes'],memory['battery'],memory['chip']),(0,False,'dsp1-hi'))
        for addr in (0x206000,0x207fff,0x006000,0x007000):self.assertIsNone(ram_offset(memory,addr))
        self.assertEqual(support_stage(rom),'supported')
    def test_dsp1_battery_window_does_not_become_code_or_overlap_ports(self):
        rom=self.rom(0x31,5,ram=1);memory=layout_bytes(rom.data,rom.mapping)
        self.assertEqual((memory['bytes'],memory['battery']),(2048,True))
        self.assertEqual(ram_offset(memory,0x206000),0)
        for addr in (0x006000,0x007000,0x708000,0x700000):self.assertIsNone(ram_offset(memory,addr))
        self.assertEqual(ram_offset(memory,0xa067ff),2047)
    def test_native_lookup_still_guards_exact_chip_size_and_fetched_opcode(self):
        for mode,kind,sub,cart in ((0x20,3,0,'CART_DSP1'),(0x31,5,0,'CART_DSP1_HIROM'),(0x31,3,0,'CART_DSP1_HIROM'),(0x20,0xf3,0x10,'CART_CX4')):
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
    def test_sa1_boards_are_recognised_by_map_and_type_and_the_other_sa1_types_stay_refused(self):
        # Map $23 with type $34 (SA-1 and BW-RAM) or $35 (with a battery): the 15 SA-1 cartridges of the library.
        for kind,battery in ((0x34,False),(0x35,True)):
            with self.subTest(kind=kind):
                rom=self.rom(0x23,kind,ram=5)
                self.assertEqual(snes_header(rom.data),(0x7fc0,'lorom'))
                self.assertEqual(identify(rom.data),'sa1')
                self.assertEqual(support_stage(rom),'supported')
                memory=layout_bytes(rom.data,rom.mapping)
                # BW-RAM: the header exponent gives its size; it is never a guarded 65816 code window.
                self.assertEqual((memory['bytes'],memory['battery'],memory['chip']),(0x8000,battery,'sa1'))
                for addr in (0x006000,0x406000,0x400000,0x606000,0x7e0000):self.assertIsNone(ram_offset(memory,addr))
        # A board without BW-RAM size in the header has no RAM; type $33 (SA-1 alone) and the other map bytes are refused.
        self.assertEqual(layout_bytes(self.rom(0x23,0x35).data,'lorom')['bytes'],0)
        for mode,kind in ((0x23,0x33),(0x23,0x36),(0x33,0x35),(0x21,0x35)):
            with self.subTest(mode=mode,kind=kind):
                with self.assertRaisesRegex(ConversionError,'SA-1|custom'):
                    validate_cartridge(self.rom(mode,kind))
    PINNED_CART = Path(__file__).resolve().parents[1] / '.deps/snesrecomp/runner/src/snes/cart.c'
    @unittest.skipUnless(PINNED_CART.is_file(), 'pinned engine checkout not present')
    def test_the_s_cpu_reaches_the_sa1_at_the_clock_of_its_own_bus_cycle(self):
        # The pinned cart_read/cart_write synchronise the SA-1 to the clock of the end of the previous instruction;
        # the S-CPU then saw the coprocessor up to thousands of master clocks behind. The adapter uses the clock of
        # the bus cycle itself and records how late the SA-1 still is (reported per run).
        from retrorecomp.snes_cart import adapt_cart
        adapted = adapt_cart(self.PINNED_CART.read_text(encoding='utf-8'))
        sa1 = adapted[adapted.index('case CART_SA1:'):]
        self.assertEqual(adapted.count('cart_sync_coprocessors(cart, g_cpu.master_cycles);'), 2)
        # The lateness is measured before the synchronisation (the catch-up the access forces) and the lead after it.
        self.assertEqual(adapted.count('rr_snes_sa1_before('), 2)
        self.assertEqual(adapted.count('rr_snes_sa1_after('), 2)
        for body in (sa1[:sa1.index('sa1_cpu_read')], sa1[sa1.index('case CART_SA1:', 10):]):
            self.assertLess(body.index('rr_snes_sa1_before('), body.index('cart_sync_coprocessors(cart, g_cpu.master_cycles)'))
        self.assertIn('sa1_cpu_read(cart->sa1, bank, adr, 0xff)', sa1)
    PINNED_SA1 = Path(__file__).resolve().parents[1] / '.deps/snesrecomp/runner/src/snes/sa1.c'
    @unittest.skipUnless(PINNED_SA1.is_file(), 'pinned engine checkout not present')
    def test_the_sa1_irq_request_follows_its_flags_like_a_level(self):
        # The pinned core latched irqWanted and never withdrew it: after the handler cleared the flag, the RTI
        # took a second IRQ with no vector kind, read from the ROM ($FFEE, the S-CPU's), and the SA-1 ran the S-CPU's
        # handler. Found with the authored cartridge of tools/snes_sa1_selftest.py.
        from retrorecomp.snes_chips import sa1
        source = self.PINNED_SA1.read_text(encoding='utf-8')
        adapted = sa1(source)
        self.assertIn('sa1->cpu->irqWanted = irq;', adapted)
        self.assertIn('if (irq) sa1->interrupt_vector_kind = 2;', adapted)
        self.assertEqual(adapted.count('irqWanted = true'), 0)
        # The NMI is an edge: requested when the (enabled, flagged) line rises, flagged when CCNT bit 4 rises.
        self.assertIn('rr_nmi_edge = rr_nmi_line && !sa1->io.rr_nmi_line;', adapted)
        self.assertIn('if (sa1->io.sa1_nmi && !rr_was_nmi) sa1->io.sa1_nmi_flag = true;', adapted)
        self.assertIn('bool rr_nmi_line;', adapted)
        self.assertEqual(adapted.count('nmiWanted = true'), 1)
        with self.assertRaises(ConversionError):
            sa1(source.replace('sa1->cpu->irqWanted = true;', 'changed'))
if __name__=='__main__':unittest.main()

class SdDdOneRamWindowTests(unittest.TestCase):
    """The S-DD1 board's RAM sits in banks $70-$73 only; $C0-$FF are its ROM windows, whatever the address (1.6.7)."""
    def test_the_ram_is_in_banks_70_to_73_only(self):
        from retrorecomp.snes_cart import ram_offset
        memory = {'chip': 'sdd1', 'mapping': 'lorom', 'bytes': 0x2000}
        self.assertEqual(ram_offset(memory, 0x700000), 0)
        self.assertEqual(ram_offset(memory, 0x701234), 0x1234)
        self.assertEqual(ram_offset(memory, 0x731234), 0x1234)       # 8 KiB, mirrored
        for address in (0xc00000, 0xf00000, 0xf05000, 0xff7fff, 0x740000, 0x70ffff):
            self.assertIsNone(ram_offset(memory, address), hex(address))

    def test_the_native_header_has_the_same_clause(self):
        text = (Path(__file__).resolve().parents[1] / 'native/snes_cart.h').read_text(encoding='utf-8')
        self.assertIn('if (cart->type==CART_SDD1) {', text)
        self.assertIn('bank>=0x70 && bank<0x74 && address<0x8000', text)
        self.assertNotIn('|| cart->type==CART_SDD1', text)    # the LoROM clause (banks $F0-$FF) no longer covers the S-DD1


class ExHiRomTests(unittest.TestCase):
    """The ExHiROM board (map $25/$35, an image above 4 MiB, the header at $40FFC0): accepted, with its own half-selecting map (1.6.7)."""
    PINNED_CART = Path(__file__).resolve().parents[1] / '.deps/snesrecomp/runner/src/snes/cart.c'
    PINNED_LOADER = Path(__file__).resolve().parents[1] / '.deps/snesrecomp/runner/src/snes/snes_other.c'

    def image(self, mode=0x25, kind=0, size=0x410000):
        from tools.snes_exhirom_selftest import cartridge
        data = bytearray(cartridge()[0][:size])
        header = 0x40ffc0
        data[header + 21:header + 23] = bytes((mode, kind))
        total = (sum(data) - sum(data[header + 28:header + 32]) + 0x1fe) & 0xffff
        data[header + 28:header + 32] = (total ^ 0xffff).to_bytes(2, 'little') + total.to_bytes(2, 'little')
        return bytes(data)

    def test_the_header_is_read_at_40ffc0_and_the_board_is_accepted(self):
        data = self.image()
        self.assertEqual(snes_header(data), (0x40ffc0, 'exhirom'))
        validate_cartridge(SimpleNamespace(data=data, mapping='exhirom'))
        validate_cartridge(SimpleNamespace(data=self.image(0x35, 1), mapping='exhirom'))

    def test_a_chip_or_a_foreign_map_byte_is_still_refused(self):
        for mode, kind in ((0x25, 3), (0x25, 0x13), (0x23, 0)):
            with self.subTest(mode=mode, kind=kind):
                with self.assertRaises(ConversionError):
                    validate_cartridge(SimpleNamespace(data=self.image(mode, kind), mapping='exhirom'))

    def test_lorom_and_hirom_stay_at_4_mib(self):
        for mapping in ('lorom', 'hirom'):
            with self.assertRaises(ConversionError):
                validate_cartridge(SimpleNamespace(data=bytes(0x410000), mapping=mapping))

    def test_the_cartridge_ram_is_the_hirom_window(self):
        memory = {'chip': 'none', 'mapping': 'exhirom', 'bytes': 0x2000, 'rom_bytes': 0x600000}
        self.assertEqual(ram_offset(memory, 0x206000), 0)
        self.assertEqual(ram_offset(memory, 0xa07123), 0x1123)
        self.assertIsNone(ram_offset(memory, 0x406000))

    def test_the_map_picks_the_half_by_the_top_address_line(self):
        if not self.PINNED_CART.is_file():
            self.skipTest('the pinned engine is not downloaded')
        from retrorecomp.snes_cart import adapt_cart
        adapted = adapt_cart(self.PINNED_CART.read_text(encoding='utf-8'))
        line = 'if (cart->romImageSize > 0x400000 && !(bank & 0x80)) off += 0x400000;'
        self.assertEqual(adapted.count(line), 1)
        hirom = adapted[adapted.index('case CART_HIROM: {'):]
        self.assertLess(hirom.index(line), hirom.index('break;'))

    def test_the_loader_reads_the_header_at_40ffc0_only_for_this_board(self):
        if not self.PINNED_LOADER.is_file():
            self.skipTest('the pinned engine is not downloaded')
        from retrorecomp.snes_cart import adapt_loader
        adapted = adapt_loader(self.PINNED_LOADER.read_text(encoding='utf-8'))
        self.assertEqual(adapted.count('readHeader(data, length, 0x40ffc0, &headers[2]);'), 1)
        self.assertLess(adapted.index('#if RR_SN_EXHIROM'), adapted.index('used=RR_SN_HIROM ? 2 : 0;'))
