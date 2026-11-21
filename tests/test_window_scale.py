"""Window sizes follow the screen's Tk scaling (retrorecomp/ui_fonts.scaled, dialogs.center_dialog and fit_screen, the main
window, the Multiplayer window). At 96 dpi (Tk scaling 96/72, what Windows reports at every scale) every size is the constant it
was before; at 144 and 192 dpi (1.5 and 2.0, Linux) it grows with the factor and stays on the screen. `tk scaling` belongs to the
display: every test puts it back. A simulated screen is Tk's screen size with the monitor's own work area switched off
(`simulated_screen`), so the room is the fallback's (dialogs.work_area); 20 Nov 2026: the room always wins, at 96 dpi too."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from retrorecomp import dialogs
from retrorecomp.dialogs import center_dialog, fit_screen
from retrorecomp.gui import Application
from retrorecomp.ui_fonts import scaled, ui_scale
from tests import test_multiplayer_view as multiplayer_tests
from tools.gui_patching import keep_window_data_in, patch_gui

FACTORS = (1.0, 1.5, 2.0)


def tk_rounding(root):
    """How far the `tk scaling` Tk applied may be from the one a test set, relatively. Tk keeps it as the screen's width in
    whole millimetres (tkCmds.c, ScalingCmd): on a 1024 px screen 2.0 reads back as 2.0069 (1024 / 135 mm, GitHub's
    Windows runner, 21 Nov 2026), on a wide screen nearly exact. Half a millimetre over the screen's width, as it is now."""
    return 0.5 / max(1, root.winfo_screenmmwidth()) + 1e-9
BIG = (3840, 2160)          # a screen that holds every scaled size
SMALL = (1366, 768)         # a small laptop: the scaled sizes must still fit


def simulated_screen(test, size):
    """Tk reports a `size` screen and dialogs reads no monitor of its own (tests/test_window_fit.py covers that part)."""
    patcher = patch.multiple(tk.Misc, winfo_screenwidth=lambda widget: size[0], winfo_screenheight=lambda widget: size[1])
    patcher.start()
    test.addCleanup(patcher.stop)
    monitor = patch.object(dialogs, '_monitor_work_area', return_value=None)
    monitor.start()
    test.addCleanup(monitor.stop)


def size_of(geometry):
    """(width, height) of a Tk geometry string 'WxH+X+Y'."""
    width, rest = geometry.split('x', 1)
    return int(width), int(rest.replace('-', '+').split('+', 1)[0])


def geometry_of(window):
    """The size Tk holds for a window: read back (the main window), or, for a Toplevel kept withdrawn (Tk reports 200x200 until it is
    mapped, and no window is shown here), the last size asked of it by a geometry request, recorded by `Requests`."""
    requested = Requests.last.get(str(window))
    if requested:
        return size_of(requested)
    window.update()
    return size_of(window.wm_geometry())


class Requests:
    """Records every `wm geometry WxH+X+Y` request of every window, and passes it on."""
    last = {}

    @classmethod
    def start(cls, test):
        cls.last = {}
        original = tk.Wm.wm_geometry

        def record(window, newGeometry=None):
            if newGeometry and 'x' in newGeometry:
                cls.last[str(window)] = newGeometry
            return original(window, newGeometry)
        patcher = patch.multiple(tk.Wm, wm_geometry=record, geometry=record)
        patcher.start()
        test.addCleanup(patcher.stop)


class ScaledWindowSizes(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        Requests.start(self)
        original = float(self.root.tk.call('tk', 'scaling'))
        self.addCleanup(self.destroy_root)
        self.addCleanup(lambda: self.root.tk.call('tk', 'scaling', original))      # first: the cleanups run last in, first out

    def destroy_root(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def force(self, factor):
        self.root.tk.call('tk', 'scaling', factor * 96 / 72)

    def screen(self, size):
        simulated_screen(self, size)

    def test_scaled_is_the_old_constant_at_96_dpi(self):
        self.force(1.0)
        self.assertEqual(ui_scale(self.root), 1.0)
        for pixels in (1, 300, 520, 900, 1120, 1060, 640):
            self.assertEqual(scaled(self.root, pixels), pixels)

    def test_scaled_follows_the_factor_and_is_one_definition(self):
        for factor in FACTORS[1:]:
            self.force(factor)
            for pixels in (300, 900, 1120):
                self.assertEqual(scaled(self.root, pixels), round(pixels * ui_scale(self.root)))     # what Tk applied
                # The factor asked for, within what Tk's whole millimetres keep of it (tk_rounding), plus the rounding.
                self.assertAlmostEqual(scaled(self.root, pixels), pixels * factor,
                                       delta=pixels * factor * tk_rounding(self.root) + 1)

    def test_fit_screen_scales_and_stops_at_the_room(self):
        self.force(1.0)
        for room in (1200, 5000):
            self.assertEqual(fit_screen(self.root, 1120, room), 1120)       # the old constant on a screen that holds it
        self.assertEqual(fit_screen(self.root, 1120, 900), 900)             # 20 Nov 2026: a smaller screen wins at 96 dpi too
        self.force(1.5)
        self.assertEqual(fit_screen(self.root, 1120, 3000), scaled(self.root, 1120))
        self.assertEqual(fit_screen(self.root, 1120, 1500), 1500)           # clamped to the room

    def test_center_dialog_scales_constants_and_clamps_to_the_screen(self):
        for factor in FACTORS:
            for screen in (BIG, SMALL):
                with self.subTest(factor=factor, screen=screen):
                    self.force(factor)
                    with patch.multiple(tk.Misc, winfo_screenwidth=lambda widget: screen[0],
                                        winfo_screenheight=lambda widget: screen[1]),                             patch.object(dialogs, '_monitor_work_area', return_value=None):
                        room_width, room_height = dialogs.screen_room(self.root)
                        panel = tk.Toplevel(self.root)
                        panel.withdraw()
                        center_dialog(panel, self.root, 900, 660)
                        shown = geometry_of(panel)
                        panel.destroy()
                    self.assertEqual(shown, (min(scaled(self.root, 900), room_width), min(scaled(self.root, 660), room_height)))
                    if factor == 1.0 and screen == BIG:
                        self.assertEqual(shown, (900, 660))                  # Windows: the old constants

    def test_center_dialog_leaves_a_measured_size_alone(self):
        for factor in FACTORS:
            with self.subTest(factor=factor):
                self.force(factor)
                self.screen(BIG)
                panel = tk.Toplevel(self.root)
                panel.withdraw()
                center_dialog(panel, self.root, 640, 480, measured=True)
                self.assertEqual(geometry_of(panel), (640, 480))
                panel.destroy()

    def main_window(self, factor, screen):
        self.force(factor)
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__('shutil').rmtree(folder, ignore_errors=True))
        keep_window_data_in(self, folder / 'datas')
        self.screen(screen)
        with patch_gui('load_preferences', return_value={'language': 'en'}), \
                patch_gui('preferred_games_root', return_value=(folder / 'exports', False)):
            app = Application(self.root)
        self.root.update_idletasks()
        self.addCleanup(self.cancel_timers)
        return app

    def cancel_timers(self):
        """Every pending timer is cancelled through the widget that owns its command (as test_toolbar does), so that destroying the
        window finds none still scheduled."""
        def widgets(widget):
            yield widget
            for child in widget.winfo_children():
                yield from widgets(child)
        try:
            owners = {name: widget for widget in widgets(self.root) for name in (widget._tclCommands or [])}
            for job in self.root.tk.call('after', 'info'):
                command = self.root.tk.call('after', 'info', job)[0]
                owners.get(command, self.root).after_cancel(job)
        except tk.TclError:
            pass

    def test_main_window_is_the_old_geometry_at_96_dpi(self):
        app = self.main_window(1.0, BIG)
        old_height = max(640, min(940, BIG[1] - 80))
        self.assertEqual(geometry_of(app.app), (1120, old_height))
        self.assertEqual(app.app.wm_minsize(), (max(1060, app.toolbar.winfo_reqwidth() + 72), 640))

    def test_main_window_fits_a_screen_smaller_than_it_at_96_dpi(self):
        app = self.main_window(1.0, (1024, 600))            # smaller than the window: 20 Nov 2026, the room wins (it was not clamped)
        room_width, room_height = dialogs.screen_room(self.root)
        self.assertEqual((room_width, room_height), (1024 - 40, 600 - dialogs.PANEL - 64))
        self.assertEqual(geometry_of(app.app), (room_width, room_height))
        self.assertEqual(app.app.wm_minsize(), (room_width, room_height))

    def check_main_window_scaled(self, factor):
        app = self.main_window(factor, BIG)
        self.assertEqual(geometry_of(app.app), (scaled(self.root, 1120), min(scaled(self.root, 940), dialogs.screen_room(self.root)[1])))
        minimum = app.app.wm_minsize()
        self.assertEqual(minimum[1], scaled(self.root, 640))
        self.assertGreaterEqual(minimum[0], scaled(self.root, 1060))

    def test_main_window_scales_at_1_5(self):
        self.check_main_window_scaled(1.5)

    def test_main_window_scales_at_2_0(self):
        self.check_main_window_scaled(2.0)

    def test_main_window_scaled_still_fits_a_small_screen(self):
        app = self.main_window(1.5, SMALL)
        room_width, room_height = dialogs.screen_room(self.root)
        width, height = geometry_of(app.app)
        self.assertLessEqual(width, room_width)
        self.assertLessEqual(height, room_height)
        self.assertLessEqual(app.app.wm_minsize()[0], room_width)
        self.assertLessEqual(app.app.wm_minsize()[1], room_height)


class ScaledMultiplayerWindow(unittest.TestCase):
    """The Multiplayer window: 900x660 and a minimum of 820x600 at 96 dpi, scaled above, clamped to the screen."""
    setUp = multiplayer_tests.MultiplayerWindowTest.setUp

    def tearDown(self):
        try:
            self.root.tk.call('tk', 'scaling', self.original_scaling)             # before the window goes
            for job in self.root.tk.call('after', 'info'):                        # the window's poll timers
                self.root.after_cancel(job)
        except (tk.TclError, AttributeError):
            pass
        multiplayer_tests.MultiplayerWindowTest.tearDown(self)

    window = multiplayer_tests.MultiplayerWindowTest.window
    settle = multiplayer_tests.MultiplayerWindowTest.settle

    def open_at(self, factor, screen):
        Requests.start(self)
        if not hasattr(self, 'original_scaling'):
            self.original_scaling = float(self.root.tk.call('tk', 'scaling'))
        self.root.tk.call('tk', 'scaling', factor * 96 / 72)
        simulated_screen(self, screen)
        view = self.window()
        self.last_view = view
        return view.window

    def open_at_view(self, factor, screen):
        self.open_at(factor, screen)
        return self.last_view

    def test_windows_keeps_900_by_660(self):
        window = self.open_at(1.0, BIG)
        self.assertEqual(geometry_of(window), (900, 660))
        self.assertEqual(window.wm_minsize(), (820, 600))

    def test_linux_scales_it(self):
        for factor in FACTORS[1:]:
            with self.subTest(factor=factor):
                window = self.open_at(factor, BIG)
                self.assertEqual(geometry_of(window), (scaled(self.root, 900), scaled(self.root, 660)))
                self.assertEqual(window.wm_minsize(), (scaled(self.root, 820), scaled(self.root, 600)))
                window.destroy()

    def test_lobby_right_column_and_wraps_follow_the_factor(self):
        for factor in FACTORS:
            with self.subTest(factor=factor):
                view = self.open_at_view(factor, BIG)
                right = view.lobby_columns.winfo_children()[0]
                self.assertEqual(int(right.cget('width')), scaled(self.root, 300))
                self.assertEqual(int(view.link_line.cget('wraplength')), scaled(self.root, 240))
                if factor == 1.0:
                    self.assertEqual((int(right.cget('width')), int(view.link_line.cget('wraplength'))), (300, 240))
                view.close()

    def test_scaled_window_stays_on_a_small_screen(self):
        window = self.open_at(2.0, SMALL)
        width, height = geometry_of(window)
        self.assertLessEqual(width, SMALL[0] - 40)
        self.assertLessEqual(height, SMALL[1] - 90)
        minimum = window.wm_minsize()
        self.assertLessEqual(minimum[0], SMALL[0] - 40)
        self.assertLessEqual(minimum[1], SMALL[1] - 90)


if __name__ == '__main__':
    unittest.main()
