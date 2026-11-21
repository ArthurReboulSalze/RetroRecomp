"""Every converter window fits the screen it opens on (retrorecomp/dialogs.py; Arthur, 20 Nov 2026: on a 1280-wide screen the Help
window opened half off it). The work area (taskbar excluded) of the monitor the window is on bounds its frame: sized to the room,
centred on its parent or on the work area, and checked again once shown (keep_on_screen, installed by watch_windows). No window is
shown here: the shown-window check runs on a stand-in that answers like a Tk window."""
import os
import tkinter as tk
import unittest
from unittest.mock import patch

from retrorecomp import dialogs
from retrorecomp.dialogs import FRAME, MARGIN, keep_on_screen, place_window, screen_room, watch_windows, work_area
from tests.test_window_scale import Requests, size_of

# Work areas of small laptops (a 48 px taskbar at the bottom), and a second monitor on the left of the first.
LAPTOP_720 = (0, 0, 1280, 672)
LAPTOP_768 = (0, 0, 1366, 720)
LEFT_MONITOR = (-1920, 0, 0, 1040)


def position_of(geometry):
    """(x, y) of a Tk geometry string 'WxH+X+Y' (X or Y may be '+-1280')."""
    rest = geometry.split('+', 1)[1]
    x, y = rest.split('+')
    return int(x), int(y)


class Base(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        Requests.start(self)

    def monitor(self, area):
        patcher = patch.object(dialogs, '_monitor_work_area', return_value=area)
        patcher.start()
        self.addCleanup(patcher.stop)

    def placed(self, width, height, parent=None):
        window = tk.Toplevel(self.root)
        window.withdraw()
        self.addCleanup(window.destroy)
        place_window(window, width, height, parent)
        geometry = Requests.last[str(window)]
        return size_of(geometry), position_of(geometry)

    def assertInside(self, area, size, position):
        left, top, right, bottom = area
        (width, height), (x, y) = size, position
        self.assertGreaterEqual(x, left + MARGIN)
        self.assertGreaterEqual(y, top + MARGIN)                                  # the title bar
        self.assertLessEqual(x + width + FRAME[0], right - MARGIN)
        self.assertLessEqual(y + height + FRAME[1], bottom - MARGIN)              # the bottom, above the taskbar


class PlaceWindow(Base):
    def test_a_window_larger_than_a_small_screen_is_clamped_and_centred(self):
        for area in (LAPTOP_720, LAPTOP_768):
            with self.subTest(area=area):
                self.monitor(area)
                size, position = self.placed(1600, 1000)
                self.assertEqual(size, screen_room(self.root))
                self.assertInside(area, size, position)

    def test_a_window_that_fits_is_centred_on_the_work_area(self):
        self.monitor(LAPTOP_720)
        (width, height), (x, y) = self.placed(600, 400)
        self.assertEqual((width, height), (600, 400))
        self.assertAlmostEqual(x + (width + FRAME[0]) / 2, 640, delta=1)
        self.assertAlmostEqual(y + (height + FRAME[1]) / 2, 336, delta=1)

    def test_the_room_is_the_work_area_less_the_margins_and_the_frame(self):
        self.monitor(LAPTOP_720)
        self.assertEqual(screen_room(self.root), (1280 - 2 * MARGIN - FRAME[0], 672 - 2 * MARGIN - FRAME[1]))

    def test_a_monitor_left_of_the_first_keeps_negative_positions(self):
        self.monitor(LEFT_MONITOR)
        size, position = self.placed(800, 600)
        self.assertLess(position[0], 0)                                           # '+-1160', not '-1160' (from the right edge)
        self.assertInside(LEFT_MONITOR, size, position)

    def test_a_dialog_centred_on_a_parent_near_the_edge_stays_inside(self):
        self.monitor(LAPTOP_720)
        parent = tk.Toplevel(self.root)
        self.addCleanup(parent.destroy)
        with patch.object(tk.Misc, 'winfo_ismapped', return_value=True), \
                patch.object(tk.Misc, 'winfo_rootx', return_value=1100), patch.object(tk.Misc, 'winfo_rooty', return_value=500), \
                patch.object(tk.Misc, 'winfo_width', return_value=900), patch.object(tk.Misc, 'winfo_height', return_value=600):
            size, position = self.placed(700, 650, parent)
        self.assertInside(LAPTOP_720, size, position)

    def test_without_a_monitor_the_screen_less_a_panel_is_the_work_area(self):
        self.monitor(None)
        with patch.multiple(tk.Misc, winfo_screenwidth=lambda widget: 1280, winfo_screenheight=lambda widget: 720):
            self.assertEqual(work_area(self.root), (0, 0, 1280, 720 - dialogs.PANEL))

    @unittest.skipUnless(os.name == 'nt', 'Windows reads its monitors')
    def test_windows_reads_a_real_work_area(self):
        left, top, right, bottom = dialogs._monitor_work_area(self.root)
        self.assertGreaterEqual(right - left, 200)
        self.assertGreaterEqual(bottom - top, 200)


class StandIn:
    """Answers like a shown Tk window whose frame is 8 px borders and a 31 px title bar, and records what it is asked."""
    def __init__(self, geometry, minimum=(200, 200), state='normal', override=False):
        self.size_and_place = geometry
        self.minimum, self.state, self.override, self.asked = minimum, state, override, []

    def winfo_exists(self): return True
    def winfo_ismapped(self): return True
    def wm_overrideredirect(self): return self.override
    def update_idletasks(self): pass
    def wm_state(self): return self.state
    def wm_geometry(self): return self.size_and_place
    def winfo_rootx(self): return position_of(self.size_and_place)[0] + 8
    def winfo_rooty(self): return position_of(self.size_and_place)[1] + 31
    def winfo_vrootx(self): return 0
    def winfo_vrooty(self): return 0
    def winfo_screenwidth(self): return 1280
    def winfo_screenheight(self): return 720

    def wm_minsize(self, width=None, height=None):
        if width is None:
            return self.minimum
        self.minimum = (width, height)
        self.asked.append(('minsize', width, height))

    def geometry(self, value):
        self.size_and_place = value
        self.asked.append(('geometry', value))


class KeepOnScreen(Base):
    def outer(self, window):
        (width, height), (x, y) = size_of(window.size_and_place), position_of(window.size_and_place)
        return x, y, x + width + 16, y + height + 39

    def test_help_half_off_a_1280_screen_comes_back_whole(self):
        self.monitor(LAPTOP_720)
        window = StandIn('900x669+700+50')
        keep_on_screen(window)
        left, top, right, bottom = self.outer(window)
        self.assertGreaterEqual(left, MARGIN)
        self.assertLessEqual(right, 1280 - MARGIN)
        self.assertGreaterEqual(top, MARGIN)
        self.assertLessEqual(bottom, 672 - MARGIN)

    def test_a_window_larger_than_the_room_shrinks_and_its_minimum_follows(self):
        self.monitor(LAPTOP_720)
        window = StandIn('1300x800+0+0', minimum=(1250, 700))
        keep_on_screen(window)
        width, height = size_of(window.size_and_place)
        self.assertEqual((width, height), (1280 - 2 * MARGIN - 16, 672 - 2 * MARGIN - 39))
        self.assertLessEqual(window.minimum[0], width)
        self.assertLessEqual(window.minimum[1], height)
        self.assertEqual(window.asked[0][0], 'minsize')                          # before the size, or Tk keeps the minimum

    def test_a_window_that_fits_is_left_alone(self):
        self.monitor(LAPTOP_768)
        window = StandIn('800x500+100+60')
        keep_on_screen(window)
        self.assertEqual(window.asked, [])

    def test_maximised_tooltips_and_menus_are_left_alone(self):
        self.monitor(LAPTOP_720)
        for window in (StandIn('1300x800+0+0', state='zoomed'), StandIn('300x40+1200+700', override=True)):
            keep_on_screen(window)
            self.assertEqual(window.asked, [])

    def test_the_watch_is_bound_once_for_every_window(self):
        watch_windows(self.root)
        watch_windows(self.root)
        for window_class in ('Toplevel', 'Tk'):
            script = self.root.bind_class(window_class, '<Map>')
            self.assertEqual(script.count('== "break"} break'), 1, (window_class, script))   # one Python command

    def test_the_check_is_scheduled_on_the_main_window_not_on_the_dialog(self):
        dialog = tk.Toplevel(self.root)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        with patch.object(self.root, 'after_idle') as on_root, patch.object(dialog, 'after_idle') as on_dialog:
            dialogs.window_shown(self.root, dialog)
            dialogs.window_shown(self.root, dialog)                       # once per window
        on_root.assert_called_once_with(keep_on_screen, dialog)
        on_dialog.assert_not_called()

    def test_a_dialog_closed_before_its_check_ran_presses_no_button_of_the_next_one(self):
        """The Stop dialog answered « Stop now » by itself (gui_smoke, 21 Nov 2026): the first dialog's pending idle check,
        orphaned by its destroy, ran the next dialog's button command that had taken its freed name."""
        from tkinter import ttk
        pressed, checked = [], []
        with patch.object(dialogs, 'keep_on_screen', side_effect=lambda window: checked.append(str(window))):
            for _ in range(20):
                first = tk.Toplevel(self.root)
                dialogs.window_shown(self.root, first)
                first.destroy()                                           # before Tk is idle
                second = tk.Toplevel(self.root)
                for value in ('now', 'wait'):
                    ttk.Button(second, command=lambda value=value: pressed.append(value)).pack()
                self.root.update_idletasks()
                second.destroy()
        self.assertEqual(pressed, [])
        self.assertEqual(len(checked), 20)                               # the check ran, on the closed dialog: a no-op


if __name__ == '__main__':
    unittest.main()
