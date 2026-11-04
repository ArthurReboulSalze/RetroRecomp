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

from retrorecomp import snes_spc
from retrorecomp.core import ConversionError


def fixture():
    return ('static const int cyclesPerOpcode[256] = {' + ','.join(['2'] * 256) + '};\n' +
        'static void spc_doOpcode(Spc* spc, uint8_t opcode) { switch(opcode) {\n' +
        'case 0x00: // first shared label\ncase 0x01: { spc->a += opcode; break; }\n' +
        '\n'.join((snes_spc.DIVISION if op == 0x9e else f'case 0x{op:02x}: {{ spc->a += opcode; break; }}') for op in range(2, 256)) +
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


    def test_a_position_no_run_has_seen_runs_the_body_of_its_live_opcode_and_is_counted_apart(self):
        masks = bytearray(snes_spc.MASK_BYTES)
        masks[0x2000 * 32] = 3
        text, _ = snes_spc.native_source(fixture(), bytes(64), masks)
        # Every opcode has an unobserved wrapper: the position is taken before the body (which moves the program counter)
        # and counted after it (the cycles are known by then).
        self.assertEqual(text.count('rr_spc_note_unobserved(spc, pc, 0x'), 256)
        wrapper = text.split('static void rr_spc_uop_a9(Spc *spc) {')[1].split('}')[0]
        self.assertLess(wrapper.index('uint16_t pc = spc->pc;'), wrapper.index('rr_spc_op_a9(spc);'))
        self.assertLess(wrapper.index('rr_spc_op_a9(spc);'), wrapper.index('rr_spc_note_unobserved'))
        lookup = text.split('const RrSpcNativeOp *rr_spc_native_lookup(Spc *spc) {')[1]
        # Device registers are still never peeked, and the boot ROM and the observed table are asked first.
        self.assertLess(lookup.index('spc->pc >= 0xf0 && spc->pc <= 0xff) return NULL'), lookup.index('rr_spc_pc_sets[spc->pc]'))
        self.assertLess(lookup.index('ops[n].opcode == opcode'), lookup.index('return rr_spc_unobserved + opcode;'))
        self.assertNotIn('if (!id) return NULL;', lookup)

    def test_the_division_is_the_chips_and_is_corrected_once(self):
        text = snes_spc.corrected(fixture())
        self.assertIn('hardware division', text)
        self.assertNotIn('TODO: proper division algorithm', text)
        self.assertEqual(snes_spc.corrected(text), text)           # idempotent: adapt_core and native_source both apply it
        self.assertIn('spc->a = 255 - (value - (spc->x << 9)) / (256 - spc->x);', text)
        with self.assertRaises(ConversionError):
            snes_spc.corrected(fixture().replace('TODO: proper division algorithm', 'changed'))
        generated, _ = snes_spc.native_source(fixture(), bytes(64), bytearray(snes_spc.MASK_BYTES))
        self.assertIn('spc->v = spc->y >= spc->x;', generated)

    def test_ei_and_di_take_three_cycles_and_nothing_else_changes(self):
        from retrorecomp.snes_codegen import cycle_costs
        before, after = cycle_costs(fixture()), cycle_costs(snes_spc.corrected(fixture()))
        self.assertEqual([op for op in range(256) if before[op] != after[op]], [0xa0, 0xc0])
        self.assertEqual((after[0xa0], after[0xc0]), (3, 3))
        self.assertEqual(snes_spc.interrupt_flag_cycles(snes_spc.corrected(fixture())), snes_spc.corrected(fixture()))
        # A table that holds another value at EI or DI, or another size, is refused.
        wrong = fixture().replace('= {' + ','.join(['2'] * 256), '= {' + ','.join(['2'] * 160 + ['9'] + ['2'] * 95), 1)
        with self.assertRaises(ConversionError):
            snes_spc.corrected(wrong)
        with self.assertRaises(ConversionError):
            snes_spc.corrected(fixture().replace('cyclesPerOpcode[256]', 'cyclesPerOpcode[255]'))
        # The compiled operations carry the same count.
        generated, _ = snes_spc.native_source(fixture(), bytes(64), bytearray(snes_spc.MASK_BYTES))
        self.assertIn('spc->cyclesUsed = 3;', generated.split('static void rr_spc_op_a0(Spc *spc)')[1].split('}')[0])

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
