"""SNES native-map and converter memory guards using authored data only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp.core import ConversionError
from retrorecomp import snes_cart, snes_codegen, supernintendo


def source_fixture():
    return ('static const int cyclesPerOpcode[256] = {' + ','.join(['2'] * 256) + '};\n' +
        'static void interp816_doOpcode(Interp816* cpu, uint8_t opcode) { switch(opcode) {\n' +
        '\n'.join(f'case 0x{opcode:02x}: {{ cpu->a += {opcode}; break; }}' for opcode in range(256)) +
        '\n} }\n')


class SnesNativeTests(unittest.TestCase):
    def test_all_operations_selected_at_conversion_and_no_opcode_switch_in_native_source(self):
        source = snes_codegen.native_source(source_fixture(), bytes(range(256)))
        self.assertNotIn('switch(opcode)', source)
        self.assertNotIn('interp816_doOpcode(', source)
        self.assertIn('rr_sn_pages[offset >> 8][offset & 255u]', source)
        self.assertIn('*mapped == operation->opcode', source)
        self.assertIn('rr_snes_native_lookup_fetched', source)
        self.assertNotIn('interp816_readOpcode(cpu)', source)
        self.assertEqual(source.count('static void rr_sn_op_'), 256)

    def test_the_sa1_boards_memory_pointer_is_range_checked_before_it_is_subtracted_from_the_rom(self):
        # sa1_cpu_memory_ptr may aim at the SA-1's I-RAM or BW-RAM: subtracting it from the ROM base is undefined, so the
        # SA-1 board's lookup compares the addresses first. Other boards keep the plain subtraction (no cost on the hot path).
        sa1 = snes_codegen.native_source(source_fixture(), bytes(0x8000), mapping='lorom')
        self.assertNotIn('uintptr_t', sa1)
        header = bytearray(0x8000)
        header[0x7fd5:0x7fd7] = bytes((0x23, 0x35))
        header[0x7fdc:0x7fe0] = bytes.fromhex('cb ed 34 12')
        header[0x7fc0:0x7fd5] = b'RR SA1 FIXTURE'.ljust(21, b' ')
        header[0x7ffc:0x7ffe] = bytes((0, 0x80))
        header[0x7fd7] = 5
        text = snes_codegen.native_source(source_fixture(), bytes(header), mapping='lorom')
        self.assertIn('CART_SA1', text)
        self.assertIn('if (rr_at < rr_base || rr_at - rr_base >= 32768u) return NULL;', text)
        self.assertNotIn('(size_t)(mapped - rr_sn_cart->rom)', text)

    def test_the_rom_remainder_is_a_mask_or_a_constant_on_the_hot_path(self):
        # cart_getRomPtr ended in a division by the ROM size on every ROM byte read; the Super FX board's code lookup did too.
        header = bytearray(0x10000)
        header[0x7fd5:0x7fd7] = bytes((0x20, 0x13))
        header[0x7fdc:0x7fe0] = bytes.fromhex('cb ed 34 12')
        header[0x7fc0:0x7fd5] = b'RR SUPERFX FIXTURE'.ljust(21, b' ')
        header[0x7ffc:0x7ffe] = bytes((0, 0x80))
        text = snes_codegen.native_source(source_fixture(), bytes(header), mapping='lorom')
        self.assertIn('CART_SUPERFX', text)
        self.assertIn('% 65536u]', text)
        self.assertNotIn('% rr_sn_cart->romSize', text)
        pinned = self.PINNED / 'runner/src/snes/cart.c'
        if pinned.is_file():
            raw = pinned.read_text(encoding='utf-8')
            adapted = snes_cart.adapt_cart(raw)
            self.assertEqual(adapted.count('(rom_size & (rom_size - 1)) ? off % rom_size : off & (rom_size - 1)'), 1)
            with self.assertRaises(ConversionError):
                snes_cart.adapt_cart(raw.replace('  return &cart->rom[off % cart->romSize];'+chr(10)+'}', '  return 0;'+chr(10)+'}'))

    def test_missing_operation_rejected(self):
        text = source_fixture().replace('case 0xff:', 'case 0xfe:')
        with self.assertRaises(ConversionError):
            snes_codegen.operation_bodies(text)

    def test_wrong_cycle_table_rejected(self):
        with self.assertRaises(ConversionError):
            snes_codegen.cycle_costs(source_fixture().replace('2,2,2', '2,2', 1))

    PINNED = Path(__file__).resolve().parents[1] / '.deps/snesrecomp'
    BRK_CYCLE = 'if(!cpu->e) cpu->cyclesUsed++; // native mode: K is stacked, 8 cycles'

    @unittest.skipUnless((PINNED / 'runner/src/snes/interp816.c').is_file(), 'pinned engine checkout not present')
    def test_brk_and_cop_cost_the_extra_cycle_in_native_mode_in_both_readers(self):
        raw = (self.PINNED / 'runner/src/snes/interp816.c').read_text(encoding='utf-8')
        self.assertNotIn(self.BRK_CYCLE, snes_codegen.operation_bodies(raw)[0x00])
        source = snes_codegen.read_core(self.PINNED)
        self.assertEqual(snes_codegen.cycle_costs(source)[0x00], 7)
        bodies = snes_codegen.operation_bodies(source)
        # Native body (what generate() compiles) and adapted copy (what console16 writes).
        self.assertEqual(bodies[0x00].count(self.BRK_CYCLE), 1)
        self.assertEqual(bodies[0x02].count(self.BRK_CYCLE), 1)
        self.assertIn('if(!cpu->e) interp816_pushByte(cpu, cpu->k);', bodies[0x02])
        self.assertIn('0xfff4', bodies[0x02])
        adapted = snes_codegen.adapt_core(source)
        self.assertEqual(adapted.count(self.BRK_CYCLE), 2)
        compiled = snes_codegen.native_source(source, bytes(range(256)))
        self.assertEqual(compiled.count(self.BRK_CYCLE), 2)

    def test_software_interrupt_correction_fails_loudly_when_the_engine_moves(self):
        brk = ('        interp816_pushByte(cpu, interp816_getFlags(cpu) | (cpu->e ? 0x10 : 0));\n')
        for source in ('', 'changed', brk, brk * 2):
            with self.subTest(source=source[:12], copies=source.count(brk)):
                with self.assertRaises(ConversionError):
                    snes_codegen.correct_software_interrupts(source)

    def test_mirroring_repeats_the_last_block_without_modifying_the_source(self):
        blocks = [bytes([n]) * 0x8000 for n in range(7)]
        for count, expected in ((1, [0]), (3, [0, 1, 2, 2]),
                                (5, [0, 1, 2, 3, 4, 4, 4, 4]),
                                (6, [0, 1, 2, 3, 4, 5, 4, 5]),
                                (7, [0, 1, 2, 3, 4, 5, 6, 6])):
            original = b''.join(blocks[:count])
            with self.subTest(blocks=count):
                self.assertEqual(snes_codegen.mirrored_rom(original),
                                 b''.join(blocks[n] for n in expected))
                self.assertEqual(original, b''.join(blocks[:count]))

    def test_mapping_and_actual_image_size_are_guarded(self):
        rom = bytes(0x18000)
        for mapping, cart in (('lorom', 'CART_LOROM'), ('hirom', 'CART_HIROM')):
            with self.subTest(mapping=mapping):
                text = snes_codegen.native_source(source_fixture(), rom, mapping=mapping)
                # Checked once, when the loaded cartridge is bound, not at every instruction.
                self.assertIn('cart->type == ' + cart, text)
                self.assertIn('cart->romSize == 131072u', text)
                self.assertIn('cart->romImageSize == 98304u', text)
                self.assertIn('bool rr_snes_native_bind(void)', text)
                self.assertNotIn('g_snes->cart->type', text.split('static const RrSnesNativeOp *rr_sn_lookup')[1])
        # The ExHiROM board uses the HiROM bus type (its second half is selected by the bank's top bit, in cart_getRomPtr).
        self.assertIn('cart->type == CART_HIROM', snes_codegen.native_source(source_fixture(), rom, mapping='exhirom'))
        with self.assertRaises(ConversionError):
            snes_codegen.native_source(source_fixture(), rom, mapping='unknown')

    # The two fast-forwards the pinned bridge carries for single cartridges, each with the text of its on/off switch.
    D9FF_SWITCH = ('        const char *_e = getenv("SNESRECOMP_NO_D9FF");\n'
                   "        s_d9ff = (_e && _e[0] && _e[0] != '0') ? 0 : 1;\n")
    VFF_SWITCH = ('                const char *_e = getenv("SNESRECOMP_NO_VBLANK_FF");\n'
                  "                s_vff_ok = (_e && _e[0] && _e[0] != '0') ? 0 : 1;\n")

    def bridge_fixture(self):
        return ('if (bounce_ok && has_body) { }\n'
                'if (auto_quiescent && steps && !in.i && g_snes && irq) { }\n'
                '        if (auto_quiescent && s_lle_master_deadline &&\n'
                '            cpu->master_cycles >= s_lle_master_deadline) { }\n'
                'if (auto_quiescent || yield_pc) {\n'
                '                lle_resume_set(((uint32_t)in.k << 16) | in.pc, INTERP_RESUME_SITE_WAI, in.sp); }\n'
                '        if (stop_on_rti && op == 0x40) {\n            sync_interp_to_cpu(&in, cpu); }\n'
                + self.D9FF_SWITCH + self.VFF_SWITCH)

    def test_the_per_game_fast_forwards_of_the_pinned_bridge_are_off_in_every_build(self):
        # Arthur's decision of 1 November 2026: no per-game code. The pinned bridge fast-forwards a Super Mario RPG wait
        # loop (SNESRECOMP_NO_D9FF) and a vblank wait at fixed addresses of Star Ocean and Super Mario RPG
        # (SNESRECOMP_NO_VBLANK_FF); the adapter fixes both switches off, whatever the environment says.
        adapted = snes_codegen.adapt_bridge(self.bridge_fixture())
        self.assertIn('s_d9ff = 0;', adapted)
        self.assertIn('s_vff_ok = 0;', adapted)
        self.assertNotIn('SNESRECOMP_NO_D9FF', adapted)
        self.assertNotIn('SNESRECOMP_NO_VBLANK_FF', adapted)
        self.assertNotIn('getenv', adapted)
        for switch in (self.D9FF_SWITCH, self.VFF_SWITCH):
            with self.subTest(switch=switch[-40:]):
                with self.assertRaises(ConversionError):
                    snes_codegen.adapt_bridge(self.bridge_fixture().replace(switch, ''))

    @unittest.skipUnless((PINNED / 'runner/src/snes/interp_bridge.c').is_file(), 'pinned engine checkout not present')
    def test_the_pinned_bridge_has_the_switches_the_adapter_turns_off(self):
        source = (self.PINNED / 'runner/src/snes/interp_bridge.c').read_text(encoding='utf-8')
        self.assertEqual(source.count(self.D9FF_SWITCH), 1)
        self.assertEqual(source.count(self.VFF_SWITCH), 1)
        adapted = snes_codegen.adapt_bridge(source)
        self.assertIn('s_d9ff = 0;', adapted)
        self.assertIn('s_vff_ok = 0;', adapted)
        self.assertNotIn('getenv("SNESRECOMP_NO_D9FF")', adapted)
        self.assertNotIn('getenv("SNESRECOMP_NO_VBLANK_FF")', adapted)

    def test_interrupts_keep_the_armed_deadline_and_wai_scheduler_handoff(self):
        bridge = self.bridge_fixture()
        adapted = snes_codegen.adapt_bridge(bridge)
        self.assertIn('(auto_quiescent || stop_on_rti) && s_lle_master_deadline', adapted)
        self.assertIn('(stop_on_rti && s_lle_master_deadline)', adapted)
        self.assertIn('(auto_quiescent || (stop_on_rti && s_lle_master_deadline)) && steps && !in.i',adapted)
        self.assertIn('in.pc, INTERP_RESUME_SITE_EXTERNAL, in.sp);', adapted)
        for old in ('if (bounce_ok && has_body) {',
                    'if (auto_quiescent && steps && !in.i && g_snes &&',
                    'if (auto_quiescent && s_lle_master_deadline &&\n',
                    'if (auto_quiescent || yield_pc) {',
                    'if (stop_on_rti && op == 0x40) {'):
            with self.subTest(boundary=old):
                with self.assertRaises(ConversionError):
                    snes_codegen.adapt_bridge(bridge.replace(old, 'changed'))
        frame = '  update_resume_pc();\n}\n\nvoid snes_beam_frame_driver_run_frame(void) {'
        self.assertIn('if (interp_bridge_lle_took_wai()) s_wai_halted = true;',
                      snes_codegen.adapt_frame_driver(frame))
        with self.assertRaises(ConversionError):
            snes_codegen.adapt_frame_driver('changed')

    def test_ram_code_guards_exact_pc_opcode_and_fetch_with_live_operands(self):
        source = snes_codegen.native_source(source_fixture(), bytes(range(256)),
            [{'address': 0x7e0100, 'bytes': 'a93412ea'},{'address':0x7e0100,'bytes':'a97856ea'}],
            ram_opcodes=[(0x7e0100,0xa9),(0x002100,0xea)])
        self.assertIn('bytes[0] == rr_sn_ram[i].op->opcode', source)
        self.assertIn('rr_sn_ram[i].pc == pc',source)
        self.assertIn('rr_sn_ram[i].op->opcode==fetched',source)
        self.assertEqual(source.count('{8257792,&rr_sn_entry_a9}'),1)
        self.assertNotIn('{8448,&rr_sn_entry_ea}',source)

    def test_wram_code_has_a_direct_table_and_keeps_the_search_for_shared_bytes(self):
        guarded = snes_codegen.native_source(source_fixture(), bytes(range(256)),
            [{'address': 0x7e0100, 'bytes': 'a93412ea'}])
        # One load for the ordinary case; another bank or a second opcode on the same WRAM byte,
        # and cartridge RAM, go to the exact (PC, opcode) search.
        self.assertIn('rr_sn_wram_entry[offset]', guarded)
        self.assertIn('const RrSnesNativeOp *found = rr_sn_ram_search(pc, fetched);', guarded)
        self.assertIn('return rr_sn_unobserved(pc, fetched);', guarded)
        self.assertIn('((entry >> 8) & 0xffu) == (pc >> 16)', guarded)
        self.assertIn('rr_sn_ram_mapped(pc)', guarded)
        plain = snes_codegen.native_source(source_fixture(), bytes(range(256)))
        self.assertNotIn('rr_sn_wram_entry', plain)
        self.assertNotIn('rr_sn_ram_search', plain)
        # Without any observation RAM code still runs through the body of its live opcode, counted apart.
        self.assertIn('if (!mapped) return rr_sn_unobserved(pc, fetched);', plain)

    def test_ram_code_nobody_has_seen_runs_through_the_body_of_its_live_opcode_and_is_counted_apart(self):
        source = snes_codegen.native_source(source_fixture(), bytes(range(256)), [{'address': 0x7e0100, 'bytes': 'a93412ea'}])
        # The table of unobserved bodies has one entry per opcode, each recording the position before its body runs
        # (the code may overwrite itself) and counting after it.
        self.assertEqual(source.count('rr16_snes_note_compiled_unobserved();'), 256)
        self.assertIn('rr_sn_unobserved_ops[256]', source)
        wrapper = source.split('static void rr_sn_uop_a9(Interp816 *cpu) {')[1].split('}')[0]
        self.assertLess(wrapper.index('rr16_snes_observe_fallback(g_interp816_cur_pc)'), wrapper.index('rr_sn_op_a9(cpu)'))
        self.assertLess(wrapper.index('rr_sn_op_a9(cpu)'), wrapper.index('rr16_snes_note_compiled_unobserved()'))
        # Only RAM is reached by it: a fetch from device registers has no live byte to read and stays interpreted.
        function = source.split('static const RrSnesNativeOp *rr_sn_unobserved(')[1].split('static const RrSnesNativeOp *rr_sn_lookup')[0]
        self.assertIn('cpu_wram_offset', function)
        self.assertIn('rr_snes_cart_ram_offset', function)
        self.assertIn('if (offset < 0) return NULL;', function)
        self.assertIn('fetched < 0 || live == fetched', function)
        # The ROM path is the one of 1.6.6: a ROM position never reaches the unobserved table.
        lookup = source.split('static const RrSnesNativeOp *rr_sn_lookup(')[1]
        self.assertLess(lookup.index('rr_sn_pages[offset >> 8]'), len(lookup))
        self.assertEqual(lookup.count('rr_sn_unobserved('), 1)


class EmulationModeCorrectionTests(unittest.TestCase):
    """RTI, TCS, TXS and the indexed direct-page wrap of emulation mode (1.6.7), from the independent vectors."""
    PINNED = Path(__file__).resolve().parents[1] / '.deps/snesrecomp/runner/src/snes/interp816.c'

    @unittest.skipUnless(PINNED.is_file(), 'pinned engine checkout not present')
    def test_the_corrected_core_has_each_correction_once_and_fails_closed(self):
        raw = self.PINNED.read_text(encoding='utf-8')
        text = snes_codegen.correct_emulation_mode(snes_codegen.correct_software_interrupts(raw))
        self.assertIn('if(!cpu->e) cpu->k = interp816_pullByte(cpu);', text)           # RTI pulls the bank in native mode only
        self.assertEqual(text.count('if(!cpu->e) cpu->cyclesUsed++; // native mode: 1 extra cycle (the program bank is pulled)'), 1)
        self.assertIn('cpu->sp = cpu->e ? (uint16_t)(0x100 | (cpu->a & 0xff)) : cpu->a;', text)   # TCS
        self.assertIn('cpu->sp = cpu->e ? (uint16_t)(0x100 | (cpu->x & 0xff)) : cpu->x;', text)   # TXS
        self.assertEqual(text.count('the index wraps within the page'), 2)                          # dp,X and dp,Y
        self.assertIn('if(cpu->e && ((from ^ cpu->pc) & 0xff00)) cpu->cyclesUsed++;', text)         # a branch across a page
        self.assertIn('cpu->cyclesUsed++; // emulation mode: across a page, one more cycle', text)     # BRA
        self.assertIn('cpu->dp | ((adr + cpu->x + 1) & 0xff)', text)                                 # (dp,X) too
        self.assertIn('interp816_readWord(cpu, cpu->dp | adr, cpu->dp | ((adr + 1) & 0xff))', text)  # (dp),Y: the pointer's second byte
        # Every anchor is checked: a pinned text that changed is refused, not patched around.
        corrected = snes_codegen.correct_software_interrupts(raw)
        for anchor in ('case 0x1b: { // tcs imp', 'case 0x9a: { // txs imp', 'interp816_setFlags(cpu, interp816_pullByte(cpu));',
                       '  bool crossed = (pointer >> 8)'):
            with self.subTest(anchor=anchor):
                with self.assertRaises(ConversionError):
                    snes_codegen.correct_emulation_mode(corrected.replace(anchor, anchor.replace('imp', 'changed')
                                                                          if 'imp' in anchor else 'X'))
        # Native mode keeps the pinned text for what it did right.
        self.assertIn('interp816_pushWord(cpu, cpu->pc - 1);', text)

class StackPageCorrectionTests(unittest.TestCase):
    """The stack of the instructions the 65816 added, in emulation mode (1.6.8), from the independent vectors."""
    PINNED = Path(__file__).resolve().parents[1] / '.deps/snesrecomp/runner/src/snes/interp816.c'

    @unittest.skipUnless(PINNED.is_file(), 'pinned engine checkout not present')
    def test_the_eight_instructions_step_the_stack_without_wrapping_and_fail_closed(self):
        raw = self.PINNED.read_text(encoding='utf-8')
        text = snes_codegen.correct_stack_pages(raw)
        self.assertEqual(text.count('interp816_stackPage(cpu);'), 8 + 0)
        for call in ('interp816_pushWordNew(cpu, cpu->dp);', 'cpu->dp = interp816_pullWordNew(cpu);', 'interp816_pushWordNew(cpu, w);',
                     'interp816_pushWordNew(cpu, interp816_readWord(cpu, low, high));',
                     'interp816_pushWordNew(cpu, cpu->pc + (int16_t) value);', 'interp816_pushByteNew(cpu, cpu->k);',
                     'cpu->pc = interp816_pullWordNew(cpu) + 1;', 'interp816_pushWordNew(cpu, cpu->pc - 1);'):
            self.assertIn(call, text, call)
        # The 6502 instructions keep the wrapping functions.
        self.assertIn('interp816_pushByte(cpu, cpu->db);', text)     # PHB
        # Every anchor is checked: a pinned text that changed is refused, not patched around.
        for anchor in ('case 0x0b: { // phd imp', 'case 0x2b: { // pld imp', 'interp816_pushWord(cpu, w);',
                       'interp816_pushWord(cpu, cpu->pc + (int16_t) value);', 'cpu->k = interp816_pullByte(cpu);',
                       'uint16_t value = interp816_adrIax(cpu);'):
            with self.subTest(anchor=anchor):
                self.assertEqual(raw.count(anchor) >= 1, True)
                with self.assertRaises(ConversionError):
                    snes_codegen.correct_stack_pages(raw.replace(anchor, 'X' + anchor))

class SnesCopierFileTests(unittest.TestCase):
    """The Pro Fighter .fig format: a 512-byte copier header before whole 32 KiB blocks, like .smc."""
    def setUp(self):
        from tools.snes_scheduler_selftest import cartridge
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.plain = bytes(cartridge(bytes.fromhex('40')))
        hirom = bytearray(0x10000)
        hirom[0xffc0:0x10000] = self.plain[0x7fc0:0x8000]
        hirom[0xffc0 + 21] = 0x31
        self.hirom = bytes(hirom)
        interleaved = bytearray(0x10000)
        interleaved[0x7fc0:0x8000] = self.plain[0x7fc0:0x8000]
        interleaved[0x7fc0 + 21] = 0x31
        self.interleaved = bytes(interleaved)

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_a_fig_file_reads_like_the_same_image_in_a_smc_and_leaves_the_file_alone(self):
        from retrorecomp.cartridge16 import read_snes_rom
        header = bytes(range(256)) * 2
        fig = self.write('game.fig', header + self.plain)
        smc = self.write('game.smc', header + self.plain)
        before = fig.read_bytes()
        rom = read_snes_rom(fig)
        self.assertEqual((rom.mapping, rom.copier_header, rom.data), ('lorom', True, self.plain))
        self.assertEqual(rom.sha256, read_snes_rom(smc).sha256)
        self.assertEqual(fig.read_bytes(), before)
        zipped = self.root / 'game.zip'
        import zipfile
        with zipfile.ZipFile(zipped, 'w') as archive:
            archive.writestr('Game (J).fig', header + self.hirom)
        self.assertEqual(read_snes_rom(zipped).mapping, 'hirom')

    def test_a_fig_file_that_is_not_blocks_of_32_kib_after_512_bytes_is_refused(self):
        from retrorecomp.cartridge16 import read_snes_rom
        for name, data in (('bare.fig', self.plain), ('short.fig', bytes(512) + self.plain[:-1]),
                           ('long.fig', bytes(513) + self.plain)):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ConversionError, '32 KiB'):
                    read_snes_rom(self.write(name, data))
        # The other extensions keep their own rule: a bare image is fine.
        self.assertEqual(read_snes_rom(self.write('bare.sfc', self.plain)).copier_header, False)

    def test_an_interleaved_hirom_image_is_refused_with_its_own_message(self):
        from retrorecomp.cartridge16 import read_snes_rom, interleaved_hirom
        self.assertTrue(interleaved_hirom(self.interleaved))
        self.assertFalse(interleaved_hirom(self.plain))
        self.assertFalse(interleaved_hirom(self.hirom))
        for name, data in (('swapped.fig', bytes(512) + self.interleaved), ('swapped.sfc', self.interleaved)):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ConversionError, 'interleaved'):
                    read_snes_rom(self.write(name, data))
        # An image with no credible header keeps the generic message.
        with self.assertRaisesRegex(ConversionError, 'header could not be validated'):
            read_snes_rom(self.write('blank.fig', bytes(512) + bytes(0x8000)))


class SnesMemoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        env = patch.dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(self.root / 'library'))
        env.start(); self.addCleanup(env.stop)
        self.rom = SimpleNamespace(sha256=hashlib.sha256(b'authored cartridge').hexdigest())

    def test_wram_aliases_and_io_boundaries(self):
        for address, expected in ((0x7e1234, 0x1234), (0x7f1234, 0x11234),
                                  (0x800100, 0x100), (0x3f0100, 0x100),
                                  (0x002000, None), (0x708000, None), (0x406000, None)):
            with self.subTest(address=address):
                self.assertEqual(supernintendo.wram_offset(address), expected)

    def test_ram_may_wrap_inside_bank_but_must_not_cross_io(self):
        self.assertTrue(supernintendo.valid_ram_variant({'address': 0x7effff, 'bytes': 'a93412ea'}))
        self.assertFalse(supernintendo.valid_ram_variant({'address': 0x001ffe, 'bytes': 'a93412ea'}))
        for raw in ('a934', 'a93412eaff', 'xxxxxxxx'):
            self.assertFalse(supernintendo.valid_ram_variant({'address': 0x7e0100, 'bytes': raw}))

    def test_library_merge_deduplicates_variants_and_normalizes_bytes(self):
        first = {'address': 0x7e0100, 'bytes': 'A93412EA'}
        second = {'address': 0x7e0100, 'bytes': 'a97856ea'}
        self.assertEqual(supernintendo.learn_ram_variants(self.rom, [{'ram_variants': [first, first]}]), 1)
        self.assertEqual(supernintendo.learn_ram_variants(self.rom, [{'ram_variants': [second]}]), 1)
        self.assertEqual(len(supernintendo.read_ram_variants(self.rom)), 2)
        self.assertTrue(all(v['bytes'].islower() for v in supernintendo.read_ram_variants(self.rom)))

    def test_different_rom_identity_rejected(self):
        supernintendo.learn_ram_variants(self.rom, [{'ram_variants': [{'address': 0x7e0100, 'bytes': 'a93412ea'}]}])
        path = supernintendo.memory_file(self.rom)
        record = json.loads(path.read_text()); record['rom_sha256'] = '0' * 64
        path.write_text(json.dumps(record))
        self.assertEqual(supernintendo.read_ram_variants(self.rom), [])

    def test_unknown_rom_and_empty_checks_create_no_memory(self):
        self.assertEqual(supernintendo.read_ram_variants(self.rom), [])
        self.assertEqual(supernintendo.learn_ram_variants(self.rom, []), 0)
        self.assertFalse(self.root.joinpath('library').exists())


class SnesQualificationTests(unittest.TestCase):
    def test_exact_profile_identity_mapping_and_region_are_required(self):
        profiles = {'authored': {'id': 'fixture', 'title': 'Authored',
                                'legacy_functions': False, 'mapping': 'hirom'}}
        with patch.dict(supernintendo.PROFILES, profiles, clear=True):
            self.assertEqual(supernintendo.profile_for(SimpleNamespace(
                sha256='authored', mapping='hirom', standard='ntsc'))['id'], 'fixture')
            other = supernintendo.profile_for(SimpleNamespace(
                sha256='other', mapping='hirom', standard='ntsc', title='Another cartridge'))
            self.assertEqual(other['source'], 'cartridge')
            self.assertFalse(other['legacy_functions'])
            self.assertNotEqual(other['id'], 'fixture')
            for sha, mapping, standard in (('authored', 'lorom', 'ntsc'),
                                         ('authored', 'hirom', 'pal')):
                with self.subTest(sha=sha, mapping=mapping, standard=standard):
                    with self.assertRaises(ConversionError):
                        supernintendo.profile_for(SimpleNamespace(
                            sha256=sha, mapping=mapping, standard=standard))


if __name__ == '__main__':
    unittest.main()
