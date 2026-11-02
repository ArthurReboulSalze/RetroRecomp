"""The ROM-free, MAME-free parts of tools/x68000_mame_compare.py: authored pictures only."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('x68000_mame_compare', ROOT / 'tools' / 'x68000_mame_compare.py')
compare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare)

try:
    import numpy
    from PIL import Image
except ImportError:                                        # the comparison itself needs both
    numpy = Image = None


def picture(rows, palette, width=None):
    """An RGB picture from rows of palette indices."""
    width = width or len(rows[0])
    image = Image.new('RGB', (width, len(rows)))
    image.putdata([palette[index] for row in rows for index in row])
    return image


@unittest.skipIf(Image is None, 'numpy and Pillow are needed')
class ShapeTests(unittest.TestCase):
    ROWS = [[0, 0, 0, 0, 0, 0], [0, 1, 1, 2, 0, 0], [0, 1, 3, 2, 0, 0], [0, 0, 0, 0, 0, 0]]

    def test_a_one_to_one_change_of_colours_keeps_the_shape_and_a_merge_does_not(self):
        base = picture(self.ROWS, [(0, 0, 0), (200, 10, 10), (10, 200, 10), (10, 10, 200)])
        recoloured = picture(self.ROWS, [(0, 0, 0), (166, 4, 4), (4, 166, 4), (30, 30, 255)])
        merged = picture(self.ROWS, [(0, 0, 0), (200, 10, 10), (10, 200, 10), (10, 200, 10)])
        self.assertEqual(compare.canonical(base), compare.canonical(recoloured))
        self.assertNotEqual(compare.canonical(base)[0], compare.canonical(merged)[0])

    def test_the_same_picture_in_another_frame_has_the_same_shape(self):
        palette = [(0, 0, 0), (200, 10, 10), (10, 200, 10), (10, 10, 200)]
        small = picture(self.ROWS, palette)
        big = Image.new('RGB', (12, 9))
        big.paste(small, (3, 4))
        self.assertEqual(compare.shape_key(small), compare.shape_key(big))
        self.assertEqual(compare.content(big).size, (3, 2))
        flipped = picture([row[::-1] for row in self.ROWS], palette)
        self.assertNotEqual(compare.shape_key(small), compare.shape_key(flipped))

    def test_a_blank_picture_has_no_content(self):
        self.assertEqual(compare.content(Image.new('RGB', (8, 8))).size, (1, 1))

    def test_a_picture_shown_on_twice_the_rows_matches_through_its_even_rows(self):
        palette = [(0, 0, 0), (200, 10, 10), (10, 200, 10), (10, 10, 200)]
        original = picture(self.ROWS, palette)
        doubled = Image.new('RGB', (original.width, 2 * original.height))
        for row in range(original.height):
            band = original.crop((0, row, original.width, row + 1))
            doubled.paste(band, (0, 2 * row))
            doubled.paste(band.point(lambda value: value // 2), (0, 2 * row + 1))   # the odd rows are dimmer in MAME
        self.assertEqual(list(compare.variants(doubled)), ['as-is', 'even-rows'])
        self.assertEqual(compare.shape_key(compare.variants(doubled)['even-rows']), compare.shape_key(original))
        results = compare.match_runs([(100, 140, doubled)], {compare.shape_key(original): [(5, 90)]})
        self.assertEqual(results[0]['variant'], 'even-rows')
        self.assertEqual(results[0]['game_runs'], [(5, 90)])


class RunTests(unittest.TestCase):
    def test_runs_of_the_game_that_stand_still(self):
        rows = [(0, 'a', 0), (1, 'a', 0), (2, 'b', 768), (3, 'b', 768), (4, 'b', 768), (5, 'c', 768), (6, 'd', 768), (7, 'd', 768)]
        self.assertEqual(compare.still_runs(rows, 3), [(2, 4, 'b')])
        self.assertEqual(compare.still_runs(rows, 2), [(2, 4, 'b'), (6, 7, 'd')])     # frames without a picture (width 0) never count

    def test_pictures_of_mame_that_stand_still_need_three_captures(self):
        captures = [(0, 'x'), (10, 'x'), (20, 'y'), (30, 'y'), (40, 'y'), (50, 'z'), (60, 'x')]
        self.assertEqual(compare.mame_runs(captures), [(20, 40, 'y')])

    def test_the_summary_counts_matches_and_names_the_others(self):
        results = [{'mame_first': 10, 'mame_last': 200, 'variant': 'as-is', 'game_runs': [(1, 166)]},
                   {'mame_first': 300, 'mame_last': 380, 'variant': None, 'game_runs': None}]
        summary = compare.summarize(results, 12, 4500, 4600)
        self.assertEqual((summary['mame_still_pictures'], summary['matched'], summary['unmatched_mame_runs']), (2, 1, [[300, 380]]))

    def test_the_lua_script_is_filled_without_a_stray_placeholder(self):
        text = compare.LUA % {'out': 'C:/work/mame', 'step': 10, 'last': 4500}
        self.assertIn('local step = 10', text)
        self.assertIn('screen:frame_number()', text)
        self.assertNotIn('%%', text)
        self.assertNotIn('%(', text)


if __name__ == '__main__':
    unittest.main()
