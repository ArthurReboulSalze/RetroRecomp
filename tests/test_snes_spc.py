"""Authored SPC700 conversion/memory guards, without cartridge data."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from smsrecomp import snes_spc
from smsrecomp.core import ConversionError


def fixture():
    return ('static const int cyclesPerOpcode[256] = {' + ','.join(['2'] * 256) + '};\n' +
        'static void spc_doOpcode(Spc* spc, uint8_t opcode) { switch(opcode) {\n' +
        'case 0x00: // first shared label\ncase 0x01: { spc->a += opcode; break; }\n' +
        '\n'.join(f'case 0x{op:02x}: {{ spc->a += opcode; break; }}' for op in range(2, 256)) +
        '\n} }\n')


class SpcConversionTests(unittest.TestCase):
    def test_grouped_cases_are_specialized_and_never_call_the_decoder(self):
        bodies = snes_spc.operation_bodies(fixture())
        self.assertIn('spc->a += 0x00', bodies[0])
        self.assertIn('spc->a += 0x01', bodies[1])
        masks = bytearray(snes_spc.MASK_BYTES)
        masks[0x2000 * 32] = 3
        text, count = snes_spc.native_source(fixture(), bytes(64), masks)
        self.assertEqual(count, 2)
        self.assertNotIn('switch(opcode)', text)
        self.assertNotIn('spc_doOpcode', text)
        self.assertIn('rr_spc_pc_sets[spc->pc]', text)
        self.assertIn('ops[n].opcode == opcode', text)
        self.assertIn('(void)spc_readOpcode(spc)', text)

    def test_incomplete_or_duplicate_semantics_rejected(self):
        for text in (fixture().replace('case 0xfe:', 'case 0xff:'),
                     fixture().replace('case 0xff:', 'default:'), ''):
            with self.assertRaises(ConversionError):
                snes_spc.operation_bodies(text)

    def test_boot_and_volatile_io_have_distinct_mappings(self):
        masks = bytearray(snes_spc.MASK_BYTES)
        masks[0xf4 * 32] = 1
        text, count = snes_spc.native_source(fixture(), bytes(64), masks)
        self.assertEqual(count, 0)
        self.assertIn('romReadable && spc->pc >= 0xffc0', text)
        self.assertIn('return &rr_spc_boot[spc->pc - 0xffc0]', text)
        with self.assertRaises(ConversionError):
            snes_spc.boot_bytes('static const uint8_t bootRom[0x40] = {0x00};')


class SpcMemoryTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        env = patch.dict(os.environ, RETRO_RECOMP_LIBRARY_DIR=str(self.root))
        env.start(); self.addCleanup(env.stop)
        self.rom = SimpleNamespace(sha256=hashlib.sha256(b'authored snes cartridge').hexdigest())

    def test_opcode_variants_merge_without_operand_bytes(self):
        checks = [{'spc_variants': [{'address': 0x2000, 'opcode': 0xe8},
                                  {'address': 0x2000, 'opcode': 0xe8}]}]
        self.assertEqual(snes_spc.learn(self.rom, checks), 1)
        self.assertEqual(snes_spc.learn(self.rom, checks), 0)
        checks[0]['spc_variants'][0]['opcode'] = 0xcd
        self.assertEqual(snes_spc.learn(self.rom, checks), 1)
        masks = snes_spc.read_masks(self.rom)
        self.assertTrue(masks[0x2000 * 32 + 0xe8 // 8] & (1 << (0xe8 & 7)))
        self.assertTrue(masks[0x2000 * 32 + 0xcd // 8] & (1 << (0xcd & 7)))
        self.assertLess(snes_spc.memory_file(self.rom).stat().st_size, 4000)

    def test_driver_image_covers_unvisited_addresses_but_excludes_io(self):
        image = bytes([0xe8] * 65536)
        self.assertEqual(snes_spc.learn(self.rom, [{'spc_driver_images': [image.hex()]}]), 65520)
        masks = snes_spc.read_masks(self.rom)
        self.assertEqual(masks[0xf0 * 32:0x100 * 32], bytes(16 * 32))
        self.assertTrue(masks[0xffc0 * 32 + 0xe8 // 8])
        self.assertLess(snes_spc.memory_file(self.rom).stat().st_size, 10000)

    def test_invalid_observations_and_empty_checks_create_no_library(self):
        self.assertEqual(snes_spc.read_masks(self.rom), bytes(snes_spc.MASK_BYTES))
        for item in ({'address': True, 'opcode': 2}, {'address': 0xf4, 'opcode': 0},
                     {'address': 65536, 'opcode': 0}, {'address': 1, 'opcode': 256}):
            self.assertFalse(snes_spc.valid_variant(item))
        self.assertEqual(snes_spc.learn(self.rom, [{'spc_variants': [{'address': 0xf4, 'opcode': 0}]}]), 0)
        self.assertFalse((self.root / 'snes').exists())

    def test_wrong_identity_and_malformed_or_oversized_stream_rejected(self):
        snes_spc.learn(self.rom, [{'spc_variants': [{'address': 0x2000, 'opcode': 0xe8}]}])
        path = snes_spc.memory_file(self.rom)
        valid = json.loads(path.read_text())
        bad = dict(valid, rom_sha256='0' * 64)
        path.write_text(json.dumps(bad))
        self.assertEqual(snes_spc.read_masks(self.rom), bytes(snes_spc.MASK_BYTES))
        for raw in (b'bad', zlib.compress(bytes(3)),
                    zlib.compress(bytes(snes_spc.MASK_BYTES + 1)),
                    zlib.compress(bytes(snes_spc.MASK_BYTES)) + b'trailing'):
            path.write_text(json.dumps(dict(valid, opcode_masks=base64.b64encode(raw).decode())))
            self.assertEqual(snes_spc.read_masks(self.rom), bytes(snes_spc.MASK_BYTES))


if __name__ == '__main__':
    unittest.main()
