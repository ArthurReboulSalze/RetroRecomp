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
from retrorecomp import snes_codegen, supernintendo


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
        with self.assertRaises(ConversionError):
            snes_codegen.native_source(source_fixture(), rom, mapping='exhirom')

    def test_interrupts_keep_the_armed_deadline_and_wai_scheduler_handoff(self):
        bridge = ('if (bounce_ok && has_body) { }\n'
                  'if (auto_quiescent && steps && !in.i && g_snes && irq) { }\n'
                  '        if (auto_quiescent && s_lle_master_deadline &&\n'
                  '            cpu->master_cycles >= s_lle_master_deadline) { }\n'
                  'if (auto_quiescent || yield_pc) {\n'
                  '                lle_resume_set(((uint32_t)in.k << 16) | in.pc, INTERP_RESUME_SITE_WAI, in.sp); }\n'
                  '        if (stop_on_rti && op == 0x40) {\n            sync_interp_to_cpu(&in, cpu); }')
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
        self.assertIn('return rr_sn_ram_search(pc, fetched);', guarded)
        self.assertIn('((entry >> 8) & 0xffu) == (pc >> 16)', guarded)
        self.assertIn('rr_sn_ram_mapped(pc)', guarded)
        plain = snes_codegen.native_source(source_fixture(), bytes(range(256)))
        self.assertNotIn('rr_sn_wram_entry', plain)
        self.assertNotIn('rr_sn_ram_search', plain)
        self.assertIn('if (!mapped) return NULL;', plain)


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
