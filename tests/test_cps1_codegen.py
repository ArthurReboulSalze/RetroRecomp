"""CPS-1 native code generation inputs and pinned-source adaptations."""
from pathlib import Path
import unittest

from smsrecomp import cps1_build, cps1_catalogue, cps1_codegen

ROOT = Path(__file__).resolve().parents[1]
GEOLITH = ROOT / '.deps/geolith-libretro'


class ProgramSizeTests(unittest.TestCase):
    def test_interleaved_and_continued_loads(self):
        game = {'regions': [{'tag': 'maincpu', 'loads': [
            {'op': 'load16_byte', 'name': 'a', 'offset': 0, 'bytes': 0x20000},
            {'op': 'load16_byte', 'name': 'b', 'offset': 1, 'bytes': 0x20000},
            {'op': 'load16_word_swap', 'name': 'c', 'offset': 0x80000, 'bytes': 0x40000},
            {'op': 'continue', 'offset': 0x100000, 'bytes': 0x20000}]},
            {'tag': 'gfx', 'loads': [{'op': 'load64_word', 'name': 'g', 'offset': 0, 'bytes': 0x80000}]}]}
        self.assertEqual(cps1_codegen.program_size(game), 0x120000)

    def test_final_fight_program_is_one_megabyte(self):
        self.assertEqual(cps1_codegen.program_size(cps1_catalogue.by_set()['ffight']), 0x100000)


class RamVariantTests(unittest.TestCase):
    def test_bounds_alignment_and_duplicates(self):
        records = [{'offset': 0x10, 'words': '4e75'}, {'offset': 0x10, 'words': '4e75'},
                   {'offset': 0x11, 'words': '4e75'}, {'offset': 0xfffe, 'words': '4e754e75'},
                   {'offset': 0x20, 'words': 'zz'}, {'offset': -2, 'words': '4e75'}]
        self.assertEqual(cps1_codegen.ram_variants(records), [(0x10, bytes.fromhex('4e75'))])


@unittest.skipUnless((GEOLITH / 'src/m68k/m68kcpu.c').is_file(), 'pinned Geolith sources are not cached')
class PinnedAdaptationTests(unittest.TestCase):
    def test_musashi_entry_and_native_dispatch(self):
        reference = cps1_build.musashi_core(GEOLITH, native=False)
        native = cps1_build.musashi_core(GEOLITH, native=True)
        for text in (reference, native):
            self.assertEqual(text.count('cps1_m68k_entry = 1;'), 1)
            self.assertIn('int cps1_m68k_instruction_cycles(void)', text)
        self.assertNotIn('rr_cps1_native_run', reference)
        self.assertEqual(native.count('if(!rr_cps1_native_run())'), 1)

    def test_z80_dispatch_only_in_native_builds(self):
        self.assertNotIn('rr_cps1_z80_try', cps1_build.z80_core(GEOLITH, native=False))
        native = cps1_build.z80_core(GEOLITH, native=True)
        self.assertIn('#include "cps1_z80_steps.inc"', native)
        self.assertEqual(native.count('if(!rr_cps1_z80_try(z,&cyc))'), 1)


if __name__ == '__main__':
    unittest.main()
