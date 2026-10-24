"""Converter memory and cartridge isolation checks with authored data."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from retrorecomp import megadrive
from retrorecomp.megadrive_codegen import translated_body, operation_name, jump_table_entries
from retrorecomp.core import ConversionError


class MegaDriveMemoryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        env = patch.dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(self.root / 'library'))
        env.start(); self.addCleanup(env.stop)
        data = bytearray(range(256)) * 16
        for offset, value in ((0, 0xffc000), (4, 0x200), (0x70, 0x220), (0x78, 0x240)):
            data[offset:offset + 4] = value.to_bytes(4, 'big')
        self.rom = SimpleNamespace(data=data, sha256=hashlib.sha256(data).hexdigest())
        profiles = patch.dict(megadrive.PROFILES, {self.rom.sha256:
            {'id': 'authored', 'title': 'Authored test', 'prefix': 'game', 'sonic': False}})
        profiles.start(); self.addCleanup(profiles.stop)

    def test_library_filters_misaligned_outside_and_stale_rom_entries(self):
        check = {'rom_entries': [0x200, 0x220, 0x221, 0xff0000, len(self.rom.data)]}
        self.assertEqual(megadrive.learn_entries(self.rom, [check]), 2)
        self.assertEqual(megadrive.read_entries(self.rom), {0x200, 0x220})
        self.rom.data[0x220] ^= 1
        self.assertEqual(megadrive.read_entries(self.rom), {0x200})

    def test_library_isolated_by_exact_rom_hash(self):
        megadrive.learn_entries(self.rom, [{'rom_entries': [0x200]}])
        record = megadrive.memory_file(self.rom)
        data = json.loads(record.read_text()); data['rom_sha256'] = '0' * 64
        record.write_text(json.dumps(data))
        self.assertEqual(megadrive.read_entries(self.rom), set())

    def test_ram_variants_merge_without_losing_previous_rom_observations(self):
        megadrive.learn_entries(self.rom, [{'rom_entries': [0x200]}])
        first = {'address': 0xff8000, 'bytes': '7001'}
        second = {'address': 0xff8000, 'bytes': '70ff'}
        invalid = [{'address': 0x200, 'bytes': '7001'}, {'address': 0xff8001, 'bytes': '7001'},
                   {'address': 0xff8000, 'bytes': 'zzzz'}, {'address': 0xff8000, 'bytes': '700'}]
        self.assertEqual(megadrive.learn_entries(self.rom, [{'ram_variants': [first, *invalid]}]), 1)
        self.assertEqual(megadrive.learn_entries(self.rom, [{'ram_variants': [first, second]}]), 1)
        self.assertEqual(megadrive.read_ram_variants(self.rom), [first, second])
        self.assertEqual(megadrive.read_entries(self.rom), {0x200})

    def test_observed_interior_pcs_are_not_made_function_entries(self):
        megadrive.write_profile(self.root, self.root, self.rom, {0x208, 0x20a, 0x20c})
        import tomllib
        profile = tomllib.loads((self.root / 'game.toml').read_text())
        self.assertNotIn(0x208, profile['functions']['extra'])
        self.assertEqual(profile['ram_layout']['initial_ssp'], 0xffc000)

    def test_ram_instruction_extent_includes_final_words_without_bus_wrap(self):
        variants = [{'address': 0xfffff4, 'bytes': '4ef900000800'},
                    {'address': 0xfffffa, 'bytes': '4ef900000800'},
                    {'address': 0xfffffe, 'bytes': '4e71'}]
        rejected = [{'address': 0xfffffc, 'bytes': '4ef900000800'},
                    {'address': 0xfffffe, 'bytes': '4e710000'},
                    {'address': 0xffffff, 'bytes': '4e71'},
                    {'address': 0x1000000, 'bytes': '4e71'}]
        self.assertEqual(megadrive.learn_entries(self.rom, [{'ram_variants': variants + rejected}]), 3)
        self.assertEqual(megadrive.read_ram_variants(self.rom), variants)

    def test_other_cartridge_is_not_compiled_as_a_known_title(self):
        self.rom.sha256 = '0' * 64
        self.rom.title = 'Another cartridge'
        profile = megadrive.profile_for(self.rom)
        self.assertEqual(profile['title'], self.rom.title)
        self.assertEqual(profile['source'], 'cartridge')
        self.assertFalse(profile['sonic'])
        megadrive.write_profile(self.root, self.root, self.rom, set())
        self.assertIn('output_prefix="game"', (self.root / 'game.toml').read_text())

    def test_invalid_stack_and_odd_interrupt_vectors_rejected(self):
        self.rom.data[0:4] = (0x80000).to_bytes(4, 'big')
        with self.assertRaises(ConversionError):
            megadrive.vectors(self.rom)

    def test_known_eeprom_board_support_without_save_header_or_known_rom(self):
        self.rom.data[0x180:0x18e] = b'GM T-81406 -00'.ljust(14, b' ')
        self.rom.data[0x1b0:0x1bc] = b' ' * 12
        self.assertEqual(megadrive.profile_for(self.rom)['limitations'], [])
        self.assertTrue(megadrive.eeprom_device(self.rom)['implemented'])
        self.assertEqual(megadrive.eeprom_device(self.rom)['chip'], '24C04')

    def test_large_rom_requires_explicit_mapper_identity_and_mapped_vectors(self):
        self.rom.data=bytearray(b'\xff'*0x500000)
        for offset,value in ((0,0xffc000),(4,0x200),(0x70,0x220),(0x78,0x240)):
            self.rom.data[offset:offset+4]=value.to_bytes(4,'big')
        self.rom.data[0x100:0x110]=b'SEGA MEGA DRIVE '.ljust(16,b' ')
        with self.assertRaises(ConversionError):megadrive.validate_cartridge(self.rom)
        self.rom.data[0x180:0x18e]=b'GM MK-12056-00'
        megadrive.validate_cartridge(self.rom)
        self.assertEqual(megadrive.bank_mapper(self.rom)['kind'],'sega_512k')
        self.rom.data[4:8]=(0x400200).to_bytes(4,'big')
        with self.assertRaises(ConversionError):megadrive.vectors(self.rom)
        self.rom.data[0x180:0x18e]=b' '*14
        self.rom.data[0x100:0x110]=b'SEGA SSF'.ljust(16,b' ')
        megadrive.validate_cartridge(self.rom)
        self.rom.data.extend(b'\xff'*0x400000)
        with self.assertRaises(ConversionError):megadrive.validate_cartridge(self.rom)
        self.rom.sha256 = '0' * 64
        self.rom.title = 'Renamed cartridge'
        self.assertEqual(megadrive.profile_for(self.rom)['limitations'], [])

    def test_parallel_sram_patch_overrides_original_sega_eeprom_identity(self):
        self.rom.data[0x180:0x18e] = b'GM T-12053 -00'.ljust(14, b' ')
        self.rom.data[0x1b0:0x1bc] = bytes.fromhex('5241f8200020000100203fff')
        self.assertIsNone(megadrive.eeprom_device(self.rom))
        self.assertEqual(megadrive.profile_for(self.rom)['limitations'], [])
        self.rom.data[0x1b0:0x1bc] = bytes.fromhex('5241e8400020000100200001')
        self.assertEqual(megadrive.eeprom_device(self.rom)['chip'], 'X24C01')

    def test_unlisted_declared_eeprom_keeps_limitation_without_guessing_circuit(self):
        self.rom.data[0x180:0x18e] = b'GM T-99999 -00'.ljust(14, b' ')
        self.rom.data[0x1b0:0x1bc] = bytes.fromhex('5241e8400020000100200001')
        device = megadrive.eeprom_device(self.rom)
        self.assertIsNone(device['chip'])
        self.assertIsNone(device['wiring'])
        self.assertFalse(device['implemented'])
        self.assertIn('EEPROM', megadrive.profile_for(self.rom)['limitations'][0])
        self.rom.data[0:4] = (0xffc000).to_bytes(4, 'big')
        self.rom.data[0x78:0x7c] = (0x241).to_bytes(4, 'big')
        with self.assertRaises(ConversionError):
            megadrive.vectors(self.rom)

    def test_all_work_ram_aliases_accept_stack_irq_and_guarded_observations(self):
        for base in range(0xe00000, 0x1000000, 0x10000):
            with self.subTest(base=base):
                self.rom.data[:4] = (0xff000000 | base | 0xc000).to_bytes(4, 'big')
                self.rom.data[0x78:0x7c] = (base | 0x8000).to_bytes(4, 'big')
                values = megadrive.vectors(self.rom)
                self.assertEqual(values['ssp'], 0xff000000 | base | 0xc000)
                self.assertEqual(values['vblank'], base | 0x8000)
                self.assertTrue(megadrive.valid_ram_variant({'address': base | 0x8000, 'bytes': '4e71'}))
        self.assertFalse(megadrive.valid_ram_variant({'address': 0xdffffe, 'bytes': '4e71'}))

    def test_svp_hardware_marker_rejects_without_relying_on_title(self):
        self.rom.data[0x1c8:0x1ca] = b'SV'
        self.rom.title = 'Renamed cartridge'
        with self.assertRaisesRegex(ConversionError, 'SVP coprocessor'):
            megadrive.validate_cartridge(self.rom)
        self.rom.data[0x1c8:0x1ca] = b'  '
        self.rom.title = 'Virtua Racing'
        megadrive.validate_cartridge(self.rom)

    def test_empty_stack_at_bus_wrap_preserves_full_address_register(self):
        for stack in (0, 0x1000000, 0xffff0000, 0xfffffffe):
            with self.subTest(stack=stack):
                self.rom.data[:4] = stack.to_bytes(4, 'big')
                self.assertEqual(megadrive.vectors(self.rom)['ssp'], stack)
        for stack in (1, 2, 0x1000001, 0xffff0001):
            with self.subTest(invalid_stack=stack):
                self.rom.data[:4] = stack.to_bytes(4, 'big')
                with self.assertRaises(ConversionError):
                    megadrive.vectors(self.rom)

    def test_unused_horizontal_interrupt_vector_is_preserved_without_becoming_code(self):
        self.rom.crc32 = 0x12345678
        for vector in (0, 0xffffffff):
            with self.subTest(vector=vector):
                self.rom.data[0x70:0x74] = vector.to_bytes(4, 'big')
                vectors = megadrive.vectors(self.rom)
                self.assertEqual(vectors['hblank'], vector & 0xffffff)
                self.assertNotIn(vectors['hblank'], vectors['roots'])
                megadrive.write_spec(self.root, self.rom, 'Authored test')
                self.assertIn(f'#define RR_MD_HBLANK 0x{vector & 0xffffff:06x}u',
                              (self.root / 'retro_md_game.h').read_text())
        # The required vertical interrupt keeps its normal validity checks.
        self.rom.data[0x78:0x7c] = (0xffffffff).to_bytes(4, 'big')
        with self.assertRaises(ConversionError):
            megadrive.vectors(self.rom)

    def test_console_region_uses_header_and_not_game_title(self):
        self.rom.crc32 = 0x12345678
        for header, overseas in ((b'J', 0), (b'U', 1), (b'JUE', 1), (b'1', 0),
                                  (b'4', 1), (b'9', 0), (b'F', 1)):
            with self.subTest(header=header):
                self.rom.data[0x1f0:0x200] = header.ljust(16, b' ')
                megadrive.write_spec(self.root, self.rom, 'Unrelated title')
                spec = (self.root / 'retro_md_game.h').read_text()
                self.assertIn(f'#define RR_MD_OVERSEAS {overseas}\n', spec)

    def test_native_body_contains_selected_operation_and_literal_operands(self):
        instruction = {'addr': 0xff8000, 'mnemonic': 2, 'size': 2,
            'words': [0x7001] + [0] * 7, 'word_count': 1, 'byte_length': 2, 'src_ea': -1,
            'dst_ea': -1, 'reg': 0, 'imm32': 1, 'target_addr': 0, 'has_target': 0,
            'dst_is_ea': 0, 'predec_mem_form': 0, 'mem_shift': 0}
        body = translated_body(instruction, 'MN_MOVEQ', 'g_cpu.D[ins->reg] = ins->imm32; return M68KI_OK;')
        self.assertIn('g_cpu.D[(0)] = (1)', body)
        self.assertNotIn('m68k_decode(', body)
        self.assertNotIn('exec_one(', body)
        self.assertEqual(operation_name(instruction), 'rr_md_op_ff8000_7001')
        instruction['words'][0] = 0x70ff
        self.assertEqual(operation_name(instruction), 'rr_md_op_ff8000_70ff')


class JumpTableDiscoveryTests(unittest.TestCase):
    def test_reached_slot_expands_siblings_but_arbitrary_pointers_do_not(self):
        data = bytearray(b'\xff' * 4096)
        for pc, target in ((0x400, 0x500), (0x404, 0x510), (0x408, 0x520)):
            data[pc:pc+4] = b'\x4e\xfa' + (target - pc - 2).to_bytes(2, 'big', signed=True)
        self.assertEqual(jump_table_entries(data, {0x404}), {0x400, 0x404, 0x408})
        self.assertEqual(jump_table_entries(data, set()), set())
        self.assertEqual(jump_table_entries(data, {0x403, 0x1000, 0xff0000}), set())
        for pc, target in ((0x600, 0x500), (0x604, 0x510), (0x608, 0x520)):
            data[pc:pc+4] = target.to_bytes(4, 'big')
        self.assertEqual(jump_table_entries(data, {0x604}), set())

    def test_short_invalid_truncated_and_negative_displacement_runs(self):
        data = bytearray(b'\xff' * 4096)
        for pc, target in ((0x600, 0x200), (0x604, 0x210), (0x608, 0x220)):
            data[pc:pc+4] = b'\x60\x00' + (target - pc - 2).to_bytes(2, 'big', signed=True)
        self.assertEqual(jump_table_entries(data, {0x604}), {0x600, 0x604, 0x608})
        data[0x608:0x60c] = b'\xff' * 4
        self.assertEqual(jump_table_entries(data, {0x604}), set())
        for target in (0x201, 0x1000, 0):
            data[0x608:0x60c] = b'\x60\x00' + (target - 0x60a).to_bytes(2, 'big', signed=True)
            self.assertEqual(jump_table_entries(data, {0x604}), set())
        data[0xffc:0x1000] = bytes.fromhex('4ef90000')
        self.assertEqual(jump_table_entries(data, {0xffc}), set())


if __name__ == '__main__':
    unittest.main()
