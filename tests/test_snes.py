"""SNES native-map and converter memory guards using authored data only."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from smsrecomp.core import ConversionError
from smsrecomp import snes_codegen, supernintendo


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
        self.assertIn('(void)interp816_readOpcode(cpu)', source)
        self.assertEqual(source.count('static void rr_sn_op_'), 256)

    def test_missing_operation_rejected(self):
        text = source_fixture().replace('case 0xff:', 'case 0xfe:')
        with self.assertRaises(ConversionError):
            snes_codegen.operation_bodies(text)

    def test_wrong_cycle_table_rejected(self):
        with self.assertRaises(ConversionError):
            snes_codegen.cycle_costs(source_fixture().replace('2,2,2', '2,2', 1))

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
                self.assertIn('g_snes->cart->type != ' + cart, text)
                self.assertIn('g_snes->cart->romSize != 131072u', text)
                self.assertIn('g_snes->cart->romImageSize != 98304u', text)
        with self.assertRaises(ConversionError):
            snes_codegen.native_source(source_fixture(), rom, mapping='exhirom')

    def test_interrupts_keep_the_armed_deadline_and_wai_scheduler_handoff(self):
        bridge = ('if (bounce_ok && has_body) { }\n'
                  '        if (auto_quiescent && s_lle_master_deadline &&\n'
                  '            cpu->master_cycles >= s_lle_master_deadline) { }\n'
                  'if (auto_quiescent || yield_pc) {\n'
                  '                lle_resume_set(((uint32_t)in.k << 16) | in.pc, INTERP_RESUME_SITE_WAI, in.sp); }\n'
                  '        if (stop_on_rti && op == 0x40) {\n            sync_interp_to_cpu(&in, cpu); }')
        adapted = snes_codegen.adapt_bridge(bridge)
        self.assertIn('(auto_quiescent || stop_on_rti) && s_lle_master_deadline', adapted)
        self.assertIn('(stop_on_rti && s_lle_master_deadline)', adapted)
        self.assertIn('in.pc, INTERP_RESUME_SITE_EXTERNAL, in.sp);', adapted)
        for old in ('if (bounce_ok && has_body) {',
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

    def test_ram_code_requires_all_four_live_bytes_and_exact_pc(self):
        source = snes_codegen.native_source(source_fixture(), bytes(range(256)),
            [{'address': 0x7e0100, 'bytes': 'a93412ea'}])
        self.assertIn('rr_sn_ram[i].pc == pc && !memcmp(bytes, rr_sn_ram[i].bytes, 4)', source)
        self.assertIn('{8257792,{169,52,18,234},&rr_sn_entry_a9}', source)


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
