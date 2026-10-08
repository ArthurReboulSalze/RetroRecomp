from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
from smsrecomp import megadrive_z80 as z80


class MegaDriveZ80Tests(unittest.TestCase):
    def test_guards_opcode_structure_and_retains_mutable_operands(self):
        cases = [('218fff00', 1, '21000000'), ('dd36fa85', 3, 'dd360000'),
                 ('fdcbff46', 11, 'fdcb0046'), ('dded43ff', 7, 'dded4300'),
                 ('ddfd213f', 7, 'ddfd2100'), ('ddfdcb00', None, None)]
        for raw, mask, expected in cases:
            key = z80.opcode_key(bytes.fromhex(raw))
            self.assertEqual(key, (mask, bytes.fromhex(expected)) if mask else None)

    def test_memory_is_exact_rom_scoped_and_merges_opcode_variants(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'knowledge.json'
            rom = SimpleNamespace(sha256='a' * 64)
            with patch.object(z80, 'memory_file', return_value=path):
                checks = [{'z80_variants': [{'address': 0x102, 'bytes': '21112200'},
                                           {'address': 0x102, 'bytes': '21889900'},
                                           {'address': 0x102, 'bytes': '22112200'}]}]
                self.assertEqual(z80.learn_variants(rom, checks), 2)
                self.assertEqual(z80.learn_variants(rom, checks), 0)
                self.assertEqual(z80.read_variants(rom), [{'address': 258, 'bytes': '21000000'},
                                                         {'address': 258, 'bytes': '22000000'}])
                self.assertEqual(z80.read_variants(SimpleNamespace(sha256='b' * 64)), [])

    def test_malformed_and_io_code_observations_are_not_imported(self):
        for item in (None, {}, {'address': True, 'bytes': '00000000'},
                     {'address': -1, 'bytes': '00000000'}, {'address': 0x4000, 'bytes': '00000000'},
                     {'address': 0x10000, 'bytes': '00000000'}, {'address': 0, 'bytes': 'DDDDDDDD'},
                     {'address': 0, 'bytes': 'XYZ'}, {'address': 0, 'bytes': '0a'}):
            self.assertFalse(z80.valid_variant(item))

    def test_uploaded_driver_extends_coverage_and_reuses_ram_mirror(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'knowledge.json'
            rom = SimpleNamespace(sha256='a' * 64)
            image = bytearray(8192)
            image[0x1fff] = 0xdd
            image[:3] = bytes.fromhex('cbff46')
            with patch.object(z80, 'memory_file', return_value=path):
                self.assertEqual(z80.learn_variants(rom, [{'z80_driver_images': [image.hex()]}]), 8192)
                entries = z80.read_variants(rom)
                self.assertIn({'address': 0x1fff, 'bytes': 'ddcb0046'}, entries)
                self.assertEqual(z80.normalize([{'address': 0x2100, 'bytes': '21889900'}]),
                                 [(0x100, 1, '21000000')])

    def test_prefix_operations_are_resolved_at_conversion(self):
        engine = Path(__file__).resolve().parents[1] / '.deps/segagenesisrecomp'
        source = engine / 'runner/external/superzazu/z80.c'
        if not source.exists():
            self.skipTest('Pinned engine not downloaded.')
        emitter = z80.Emitter(source.read_text(encoding='utf-8'))
        for raw in ('dded4300', 'ddfd2100', 'fdcb0046', 'ddcb0016', 'edb00000', 'dd760000'):
            self.assertNotIn('exec_opcode', emitter.instruction(bytes.fromhex(raw)))


if __name__ == '__main__':
    unittest.main()
