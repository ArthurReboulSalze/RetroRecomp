"""The redraw marks of the X68000 background and sprites equal a full redraw (x68k/bg.c and tvram.c as adapted).

tests/x68000_redraw_marks_harness.c draws random authored scenes line after line in two ways with the real BG_DrawLine:
one redraws a line only when the marks say so (as WinDraw_DrawLine does), the other redraws every line. They must be
identical after every line, while random writes to the tile maps, the patterns, the sprite registers and the scroll
registers change the scene between lines. Marks that are exact redraw far fewer lines than a full redraw, which the
second test shows. No ROM, disk or firmware is involved.
"""
import unittest

from tests.x68000_base_harness import build_and_run


class RedrawMarksTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build, cls.cases = build_and_run('x68000_redraw_marks_harness.c', ['x68k/bg.c', 'x68k/tvram.c'])

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def test_the_marked_lines_give_the_same_picture_as_a_full_redraw(self):
        self.assertEqual(len(self.cases), 9)
        for name, case in self.cases.items():
            with self.subTest(name):
                self.assertEqual(case['mismatches'], '0')
                self.assertGreater(int(case['writes']), 300)

    def test_most_lines_are_not_redrawn_when_few_things_change(self):
        for name in ('tiles16_aligned', 'tiles16_aligned_ng', 'tiles16_bg_early', 'tiles16_bg_512_on_display_256'):
            case = self.cases[name]
            with self.subTest(name):
                self.assertLess(int(case['redrawn']) * 3, int(case['lines']))


if __name__ == '__main__':
    unittest.main()
