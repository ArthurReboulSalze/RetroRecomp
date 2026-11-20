"""The leaderboard « Marches » (Arthur's pick, 20 Nov 2026): the player's row pinned at the foot while out of view, and how far
the next place is (none, first, behind). Made-up rows; a withdrawn window, nothing shown."""
import tkinter as tk
import unittest

from retrorecomp.gui import Application
from retrorecomp.gui_leaderboard import next_place
from tests.tk_cleanup import release_tk


def rows(*totals):
    return [({'rank': index, 'pseudonym': f'P{index}', 'total': total, 'games': 3}, {'gold': 1})
            for index, total in enumerate(totals, 1)]


class NextPlace(unittest.TestCase):
    def test_a_player_not_in_the_rows_gets_nothing(self):
        self.assertIsNone(next_place(rows(900, 800), 'Someone'))
        self.assertIsNone(next_place(rows(900, 800), None))

    def test_the_first_player_leads(self):
        self.assertEqual(next_place(rows(900, 800), 'P1')['state'], 'first')

    def test_a_player_in_the_middle_is_told_the_points_to_pass_the_one_above(self):
        place = next_place(rows(900, 800, 700), 'P2')
        self.assertEqual((place['state'], place['gap'], place['above']['pseudonym']), ('behind', 101, 'P1'))
        self.assertAlmostEqual(place['share'], (800 - 700) / (900 - 700))

    def test_the_last_one_measures_from_zero(self):
        place = next_place(rows(900, 300), 'P2')
        self.assertEqual(place['gap'], 601)
        self.assertAlmostEqual(place['share'], 300 / 900)


class PinnedFoot(unittest.TestCase):
    def setUp(self):
        release_tk(self)
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.canvas = tk.Canvas(self.root, width=760, height=80)
        self.app = Application.__new__(Application)
        self.app.language, self.app.ui_font = 'fr', 'TkDefaultFont'

    def texts(self, tag):
        return [self.canvas.itemcget(item, 'text') for item in self.canvas.find_withtag(tag)
                if self.canvas.type(item) == 'text']

    def test_out_of_view_the_player_s_row_is_pinned_with_the_way_to_the_next_place(self):
        board = rows(900, 800, 700)
        place = self.app.draw_board_pinned(self.canvas, board, 760, 'P3', {}, visible=False)
        self.assertEqual(place['state'], 'behind')
        self.assertIn('P3', ''.join(self.texts('pinned_row')))
        self.assertEqual(self.texts('next_place_text'),
                         [self.app.tr('leaderboard_next', points=self.app.count_text(101), name='P2', rank=2)])
        self.assertIn('101', self.texts('next_place_text')[0])

    def test_in_view_only_the_way_to_the_next_place_is_shown(self):
        self.app.draw_board_pinned(self.canvas, rows(900, 800), 760, 'P2', {}, visible=True)
        self.assertFalse(self.canvas.find_withtag('pinned_row'))
        self.assertTrue(self.texts('next_place_text'))

    def test_the_first_player_is_told_they_lead(self):
        self.app.draw_board_pinned(self.canvas, rows(900, 800), 760, 'P1', {}, visible=False)
        self.assertEqual(self.texts('next_place_text'), [self.app.tr('leaderboard_first')])

    def test_a_player_outside_the_rows_gets_no_foot(self):
        self.assertIsNone(self.app.draw_board_pinned(self.canvas, rows(900, 800), 760, 'Someone', {}, visible=False))
        self.assertFalse(self.canvas.find_all())

    def test_the_player_s_own_row_is_gold_rimmed_in_the_list(self):
        self.app.draw_board_rows(self.canvas, rows(900, 800, 700), 760, 'P2', {})
        outlines = {self.canvas.itemcget(item, 'outline') for item in self.canvas.find_all()
                    if self.canvas.type(item) == 'polygon'}
        self.assertIn('#d4a737', outlines)


if __name__ == '__main__':
    unittest.main()
