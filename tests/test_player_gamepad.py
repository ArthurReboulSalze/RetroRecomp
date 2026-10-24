"""Converter navigation edges are independent of controller polling frequency."""
import unittest
from retrorecomp.player_gamepad import Navigation


class NavigationTests(unittest.TestCase):
    def test_launch_once_per_press_and_only_after_neutral(self):
        nav=Navigation()
        self.assertIsNone(nav.update([(1,0,0)],0))
        self.assertIsNone(nav.update([(0,0,0)],.1))
        self.assertEqual(nav.update([(1,0,0)],.2),'play')
        self.assertIsNone(nav.update([(1,0,0)],.3))
        nav.update([(0,0,0)],.4)
        self.assertEqual(nav.update([(1,0,0)],.5),'play')

    def test_no_background_modal_or_held_launch_after_game_closes(self):
        nav=Navigation();nav.update([(0,0,0)],0)
        self.assertIsNone(nav.update([(1,0,0)],.1,False))
        self.assertIsNone(nav.update([(1,0,0)],.2,True))
        nav.update([(0,0,0)],.3)
        self.assertEqual(nav.update([(1,0,0)],.4),'play')

    def test_directional_repeat_and_axis_threshold(self):
        nav=Navigation();nav.update([(0,0,0)],0)
        self.assertEqual(nav.update([(1<<12,0,0)],.1),1)
        self.assertIsNone(nav.update([(1<<12,0,0)],.44))
        self.assertEqual(nav.update([(1<<12,0,0)],.46),1)
        self.assertIsNone(nav.update([(1<<12,0,0)],.50))
        self.assertEqual(nav.update([(0,0,-20000)],.51),-1)
        self.assertIsNone(nav.update([(0,0,-1000)],.52))
        self.assertEqual(nav.update([(0,0,20000)],.53),1)

    def test_any_connected_pad_and_empty_list(self):
        nav=Navigation();nav.update([],0)
        self.assertEqual(nav.update([(0,0,0),(1<<11,0,0)],.1),-1)
        nav.update([], .2)
        self.assertEqual(nav.update([(0,0,0),(1,0,0)],.3),'play')


if __name__=='__main__':unittest.main()
