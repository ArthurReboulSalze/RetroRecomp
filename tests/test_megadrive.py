"""Converter memory and cartridge isolation checks with authored data."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from smsrecomp import megadrive
from smsrecomp.megadrive_codegen import translated_body, operation_name
from smsrecomp.core import ConversionError


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
        self.rom.data[0:4] = (0xffc000).to_bytes(4, 'big')
        self.rom.data[0x78:0x7c] = (0x241).to_bytes(4, 'big')
        with self.assertRaises(ConversionError):
            megadrive.vectors(self.rom)

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


if __name__ == '__main__':
    unittest.main()
