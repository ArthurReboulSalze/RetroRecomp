"""The corrections of the pinned Geolith Z80 (`neogeo_z80.FIXES`): each applies once to the pinned text and a changed pin fails loudly.

Their effect on behaviour is measured by tools/cps1_z80_vector_selftest.py (independent vectors, needs a compiler)."""
from pathlib import Path
import unittest

from retrorecomp import neogeo_z80
from retrorecomp.core import ConversionError

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps/geolith-libretro/src/z80/z80.c'


@unittest.skipUnless(PINNED.is_file(), 'pinned Geolith sources are not cached')
class FixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PINNED.read_text(encoding='utf-8')

    def test_the_names_are_unique_and_every_fix_changes_the_text(self):
        names = [name for name, _, _ in neogeo_z80.FIXES]
        self.assertEqual(len(names), len(set(names)))
        for name, before, after in neogeo_z80.FIXES:
            self.assertNotEqual(before, after, name)

    def test_the_adapted_text_holds_every_correction_once(self):
        adapted = neogeo_z80.adapt_source(self.source)
        for name, _, after in neogeo_z80.FIXES:
            self.assertEqual(adapted.count(after), 1, name)
        self.assertEqual(adapted.count('static inline void block_repeat('), 1)
        self.assertEqual(adapted.count('block_repeat(z, '), 8)    # ldir, lddr, otir, otdr, inir, indr, cpir, cpdr

    def test_a_changed_pin_refuses_the_adaptation(self):
        for name, before, _ in neogeo_z80.FIXES:
            with self.subTest(fix=name):
                broken = self.source.replace(before, before.replace('z->', 'q->'), 1)
                if broken == self.source:      # a fix whose text is only produced by an earlier one
                    continue
                with self.assertRaises(ConversionError):
                    neogeo_z80.adapt_source(broken)

    def test_the_translated_bodies_never_call_the_runtime_dispatch(self):
        emitter = neogeo_z80.Emitter(neogeo_z80.adapt_source(self.source))
        for raw in (bytes([0xed, 0x78, 0, 0]), bytes([0xed, 0xb3, 0, 0]), bytes([0xdd, 0x22, 0, 0]), bytes([0xed, 0x4e, 0, 0]),
                    bytes([0xed, 0x77, 0, 0]), bytes([0xed, 0x4d, 0, 0])):
            self.assertNotIn('exec_opcode', emitter.emit(raw), raw.hex())


if __name__ == '__main__':
    unittest.main()
