"""Synthetic cartridge checks; no commercial ROM is required."""
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
from smsrecomp.cartridge16 import read_megadrive_rom, read_snes_rom
from smsrecomp.console16 import qualified_rom, reference_differences
from smsrecomp.core import ConversionError
from smsrecomp.systems import profile_for_path, discover_roms
from smsrecomp.batch import identify, system_output
from smsrecomp.metadata import game_metadata


def md(region=b'JUE'):
    data = bytearray(32768)
    data[0x100:0x104] = b'SEGA'
    data[0x150:0x158] = b'TEST ROM'
    data[0x1f0:0x1f0 + len(region)] = region
    return bytes(data)


def snes(region=1, mapping='lorom', fast=False):
    data = bytearray(65536)
    offset = 0x7fc0 if mapping == 'lorom' else 0xffc0
    data[offset:offset + 21] = b'TEST ROM'.ljust(21, b' ')
    data[offset + 21] = (0x20 if mapping == 'lorom' else 0x21) | (0x10 if fast else 0)
    data[offset + 23] = 6
    data[offset + 25] = region
    data[offset + 28:offset + 32] = bytes.fromhex('cbed3412')
    data[offset + 60:offset + 62] = bytes.fromhex('0080')
    return bytes(data)


class Console16Tests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def source(self, name, payload):
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_md_header_identifies_linear_bin_and_region(self):
        for region, expected in ((b'J', 'ntsc'), (b'U', 'ntsc'), (b'E', 'pal'), (b'JUE', 'multi')):
            path = self.source('Game.bin', md(region))
            self.assertEqual(profile_for_path(path).id, 'md')
            self.assertEqual(read_megadrive_rom(path).standard, expected)

    def test_snes_header_identifies_pal_ntsc_and_fastrom(self):
        for mapping in ('lorom', 'hirom'):
            for region, expected in ((1, 'ntsc'), (2, 'pal')):
                path = self.source('Game.rom', snes(region, mapping, fast=True))
                self.assertEqual(profile_for_path(path).id, 'snes')
                self.assertEqual(read_snes_rom(path).standard, expected)
                self.assertEqual(read_snes_rom(path).mapping, mapping)

    def test_copier_header_removed_only_in_memory(self):
        payload = bytes(512) + snes()
        path = self.source('Game.smc', payload)
        rom = read_snes_rom(path)
        self.assertTrue(rom.copier_header)
        self.assertEqual(rom.data, snes())
        self.assertEqual(path.read_bytes(), payload)

    def test_corrupt_or_ambiguous_snes_header_rejected(self):
        broken = bytearray(snes())
        broken[0x7fde] ^= 1
        ambiguous = bytearray(snes())
        ambiguous[0xffc0:0x10000] = snes(mapping='hirom')[0xffc0:0x10000]
        for payload in (broken, ambiguous, bytes(65536)):
            with self.assertRaises(ConversionError):
                read_snes_rom(self.source('Invalid.sfc', payload))

    def test_archive_identifies_without_extraction_or_writes(self):
        for suffix, payload, expected in (('.md', md(), 'md'), ('.sfc', snes(), 'snes')):
            path = self.root / (expected + '.zip')
            with ZipFile(path, 'w') as archive:
                archive.writestr('folder/Game' + suffix, payload)
            before = path.read_bytes()
            self.assertEqual(identify(path).system, expected)
            self.assertEqual(profile_for_path(path).read_rom(path).data, payload)
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(list(self.root.iterdir())), 2)

    def test_wrong_console_override_does_not_compile_foreign_rom(self):
        path = self.source('Game.bin', md())
        with self.assertRaises(ValueError):
            profile_for_path(path, 'snes')

    def test_unqualified_rom_is_rejected_before_dependencies(self):
        for system, path in (('md', self.source('Game.md', md())),
                             ('snes', self.source('Game.sfc', snes()))):
            with self.assertRaisesRegex(ConversionError, 'identified, but will not be compiled'):
                qualified_rom(path, system)

    def test_unsupported_md_formats_not_silently_deinterleaved(self):
        path = self.source('Game.smd', bytes(32768))
        with self.assertRaises(ConversionError):
            read_megadrive_rom(path)

    def test_mixed_folder_scans_roms_and_ignores_markdown(self):
        self.source('README.md', b'Documentation')
        first = self.source('Game.md', md())
        second = self.source('Game.sfc', snes())
        self.assertEqual(set(discover_roms(self.root)), {first, second})

    def test_export_names_and_metadata_are_console_specific(self):
        self.assertEqual(system_output(self.root, 'md').name, 'Mega Drive')
        self.assertEqual(system_output(self.root, 'snes').name, 'Super Nintendo')
        for system, console in (('md', 'Mega Drive'), ('snes', 'Super Nintendo')):
            metadata = game_metadata('Game', False, 'ntsc', system)
            self.assertEqual(metadata['Console'], console)
            self.assertIn(console + ' NTSC', metadata['FileDescription'])

    def test_empty_reports_cannot_validate_native_execution(self):
        for system in ('md', 'snes'):
            differences = reference_differences(system, {}, {})
            self.assertIn('cpu_hash', differences)
            self.assertIn('sequence_hash', differences)
            self.assertIn('retired_instruction_count', differences)

    def test_validation_rejects_memory_timing_and_retired_count_differences(self):
        fields = ('frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash',
                  'cpu_pc', 'vsram_hash', 'vdp_register_hash', 'oam_hash', 'high_oam_hash',
                  'apu_ram_hash', 'cpu_cycles', 'master_cycles', 'apu_cycles')
        native = dict.fromkeys(fields, 1) | {'native_entries': 100, 'interpreted_opcodes': 0}
        reference = native | {'native_entries': 0, 'interpreted_opcodes': 100}
        for system, key in (('md', 'vdp_register_hash'), ('snes', 'master_cycles'), ('snes', 'oam_hash')):
            self.assertEqual(reference_differences(system, native, reference), [])
            self.assertIn(key, reference_differences(system, native, reference | {key: 2}))
            self.assertIn(key, reference_differences(system, native, reference | {key: None}))
            self.assertIn('retired_instruction_count', reference_differences(system, native,
                reference | {'interpreted_opcodes': 99}))
