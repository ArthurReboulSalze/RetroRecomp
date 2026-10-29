"""The X68000 text line is copied in runs inside the plane's row and gives the same dots as the per-dot formula.

tests/x68000_text_line_harness.c calls the real Text_DrawLine (x68k/tvram.c as adapted by tools/x68000_base74.py) for
many horizontal scroll values, line widths up to 768 dots, both modes and the interlaced step, and compares
the line buffer and the transparency flags with the plain formula, including the dots a transparent line must keep.
No ROM, disk or firmware is involved.
"""
import unittest

from tests.x68000_base_harness import build_and_run


class TextLineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build, cls.cases = build_and_run('x68000_text_line_harness.c', ['x68k/tvram.c'])

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def test_every_scroll_and_width_gives_the_same_line_as_the_plain_formula(self):
        case = self.cases['text_line']
        self.assertEqual(case['mismatches'], '0')
        self.assertGreater(int(case['cases']), 1000)
        self.assertGreater(int(case['wrapping']), 100)


if __name__ == '__main__':
    unittest.main()
