"""The unused-bits patch of the Game Boy runtime (retrorecomp/gameboy_runtime.py: adapt_unused_io_bits), on a synthetic source: no ROM, no build.
The behaviour itself is proved by Mooneye's unused_hwio-GS (tools/gameboy_testroms.py)."""
import unittest

from retrorecomp.core import ConversionError
from retrorecomp.gameboy_runtime import adapt_unused_io_bits

PALETTE = '        if (addr >= 0xFF68 && addr <= 0xFF6B) {\n            gb_sync(ctx);\n            return ppu_read_register((GBPPU*)ctx->ppu, addr);\n        }\n'
TAIL = ('            return gb_audio_read(ctx, addr);\n        }\n        return ctx->io[addr - 0xFF00];\n    }\n'
        '    if (addr < 0xFFFF) return ctx->hram[addr - 0xFF80];')


class UnusedIoBitsTests(unittest.TestCase):
    def test_the_unwired_bits_read_one_outside_colour_mode(self):
        source = adapt_unused_io_bits(PALETTE + TAIL)
        self.assertIn('ctx->io[0x07] | 0xF8u', source)                       # timer control, bits 7 to 3
        self.assertIn('ctx->io[0x02] | (gb_is_cgb_hardware(ctx) ? 0x7Cu : 0x7Eu)', source)   # serial control
        self.assertIn('addr == 0xFF03 || (addr >= 0xFF08 && addr <= 0xFF0E)) return 0xFF;', source)
        self.assertIn('if (!gb_is_cgb_mode(ctx)) return 0xFF;\n            gb_sync(ctx);', source)   # the palette registers

    def test_only_the_last_fall_through_reads_the_mask(self):
        source = adapt_unused_io_bits(PALETTE + TAIL)
        self.assertEqual(source.count('return ctx->io[addr - 0xFF00];'), 1)   # the one after the masks, no other path changed

    def test_a_moved_upstream_marker_is_refused(self):
        with self.assertRaises(ConversionError):
            adapt_unused_io_bits(PALETTE + TAIL.replace('hram', 'hram2'))
        with self.assertRaises(ConversionError):
            adapt_unused_io_bits(PALETTE.replace('0xFF68', '0xFF69') + TAIL)


if __name__ == '__main__':
    unittest.main()
