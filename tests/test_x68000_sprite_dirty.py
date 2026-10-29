"""A moved X68000 sprite marks every screen line it covered or covers for redraw (x68k/bg.c as adapted).

tests/x68000_sprite_dirty_harness.c asks the real BG_DrawLine which lines show the authored sprite before and after
it moves, and checks that the real register write marked all of them. The pinned base marked the wrong lines when the
background's vertical start differs from the display's, and too few lines when their line counts differ, so a part of
a moved sprite stayed on screen. No ROM, disk or firmware is involved.
"""
import unittest

from tests.x68000_base_harness import build_and_run


class SpriteRedrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build, cls.cases = build_and_run('x68000_sprite_dirty_harness.c', ['x68k/bg.c', 'x68k/tvram.c'])

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def test_every_covered_line_is_marked_whatever_the_vertical_registers(self):
        self.assertEqual(len(self.cases), 9)
        for name, case in self.cases.items():
            with self.subTest(name):
                self.assertGreater(int(case['covered']), 0)
                self.assertEqual((case['missing_old'], case['missing_new']), ('0', '0'))

    def test_the_covered_lines_follow_the_line_counts(self):
        covered = {name: int(case['covered']) for name, case in self.cases.items()}
        self.assertEqual(covered['aligned_256'], 32)
        self.assertEqual(covered['bg_256_on_display_512'], 64)
        self.assertEqual(covered['bg_512_on_display_256'], 16)


if __name__ == '__main__':
    unittest.main()
