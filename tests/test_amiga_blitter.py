"""The Amiga Blitter's specialised routines, the parts that need neither a compiler nor a ROM: which shapes get one, what the generator writes, how a run's counters read, and that the
shape header comes out of vAmiga's own text or fails loudly. `tools/amiga_blitter_selftest.py` runs the routines against vAmiga's microprogram."""
from pathlib import Path
import tempfile
import unittest

from retrorecomp import amiga_codegen, amiga_conversion, amiga_vamiga

ROOT = Path(__file__).resolve().parents[1]
PINNED = ROOT / '.deps' / 'vamiga' / 'Core'


def report(*shapes, left_midway=0):
    return {'blitter': {'left_midway': left_midway, 'shapes': [list(shape) for shape in shapes]}}


class ChosenShapesTests(unittest.TestCase):
    def test_copy_shapes_of_all_routes_get_a_routine_and_line_blits_never_do(self):
        first = report((0x9f0, 0, 0, 0, 0, 3, 300), (0xbca, 0x01, 0, 0, 0, 5, 50))
        second = report((0x9f0, 0, 1, 2, 20, 0, 0), (0xfca, 0x02, 0, 0, 0, 1, 10))
        self.assertEqual(amiga_codegen.blit_shapes([first, second]), [(0x9f0, 0), (0xfca, 0x02)])

    def test_the_rare_shapes_stay_on_vamiga_beyond_the_limit_the_most_words_first(self):
        shapes = [(0x100 + n, 0, 0, 0, 0, 1, n + 1) for n in range(5)]
        self.assertEqual(amiga_codegen.blit_shapes([report(*shapes)], limit=2), [(0x103, 0), (0x104, 0)])

    def test_a_run_without_a_blit_has_no_shape(self):
        self.assertEqual(amiga_codegen.blit_shapes([{}, report()]), [])


class GeneratedSourceTests(unittest.TestCase):
    def test_one_routine_per_shape_and_nothing_to_compile_without_one(self):
        self.assertNotIn('#include', amiga_codegen._blitter_source('rr_amiga_', []))
        source = amiga_codegen._blitter_source('rr_amiga_', [(0xfca, 0x02), (0x9f0, 0)])
        self.assertIn('rr_amiga_blit_fca_02(void *blitter)', source)
        self.assertIn('rrRun<0xfca, 0x02>()', source)
        self.assertIn('rrRun<0x9f0, 0x00>()', source)

    def test_a_line_blit_or_a_shift_field_is_not_a_shape(self):
        for shape in ((0x9f0, 1), (0x1f0, 0x20), (0x19f0, 0)):
            with self.subTest(shape=shape), self.assertRaises(ValueError):
                amiga_codegen._blitter_source('rr_amiga_', [shape])

    def test_the_table_names_every_routine(self):
        table = amiga_codegen._blit_table('rr_amiga_', [(0x9f0, 0)])
        self.assertIn('{0x9f0,0x00,rr_amiga_blit_9f0_00}', table)
        self.assertIn('rr_amiga_blit_shape_count=1;', table)
        self.assertIn('rr_amiga_blit_shape_count=0;', amiga_codegen._blit_table('rr_amiga_', []))


class CountsTests(unittest.TestCase):
    def test_native_interpreted_and_line_blits_are_counted_apart_by_shape(self):
        counts = amiga_conversion.blitter_counts(report((0x9f0, 0, 1, 10, 100, 0, 0), (0xbca, 0x00, 0, 0, 0, 2, 20), (0xb4a, 0x01, 0, 0, 0, 3, 30), (0xfca, 0, 1, 0, 0, 0, 0), left_midway=4))
        self.assertEqual((counts['native_blits'], counts['native_words']), (10, 100))
        self.assertEqual((counts['interpreted_blits'], counts['interpreted_words']), (2, 20))
        self.assertEqual((counts['line_blits'], counts['line_steps']), (3, 30))
        self.assertEqual(counts['left_midway'], 4)
        # A routine no blit used this run is not a row of it.
        self.assertEqual([shape['bltcon0'] for shape in counts['shapes']], ['9f0', 'bca', 'b4a'])
        self.assertTrue(counts['shapes'][2]['line'])

    def test_a_report_without_the_field_counts_nothing(self):
        self.assertEqual(amiga_conversion.blitter_counts({})['native_blits'], 0)


class ShapeHeaderTests(unittest.TestCase):
    def test_a_changed_upstream_text_fails_loudly(self):
        with self.assertRaises(ValueError):
            amiga_vamiga._between('nothing here', 'start', 'end', 'file')
        with self.assertRaises(ValueError):
            amiga_vamiga._rewrite('one two', [('three', '3', 1)], 'file')
        with self.assertRaises(ValueError):
            amiga_vamiga._rewrite('one one', [('one', '1', 1)], 'file')
        with tempfile.TemporaryDirectory() as folder:
            blitter = Path(folder) / 'Components/Agnus/Blitter'
            blitter.mkdir(parents=True)
            (blitter / 'SlowBlitter.cpp').write_text('nothing here', encoding='utf-8')
            (blitter / 'Blitter.cpp').write_text('nothing here', encoding='utf-8')
            with self.assertRaises(ValueError):
                amiga_vamiga.blitter_shape_header(Path(folder))

    @unittest.skipUnless(PINNED.is_dir(), 'the pinned vAmiga is not in this tree')
    def test_the_pinned_blitter_gives_the_whole_microprogram(self):
        with tempfile.TemporaryDirectory() as folder:
            core = amiga_vamiga.adapt(PINNED.parent, Path(folder))
            header = (core / amiga_vamiga.BLITTER_SHAPE_HEADER).read_text(encoding='utf-8')
        self.assertIn('rrCopyProgram[16][2][6]', header)
        self.assertEqual(header.count('case 254:'), 1)      # minterm 255 is the switch's `default`, in vAmiga's text too
        self.assertIn('default:  return 0xFFFF;', header)
        self.assertNotIn('doMintermLogic(', header)
        self.assertNotIn('bltconDESC()', header)


if __name__ == '__main__':
    unittest.main()
