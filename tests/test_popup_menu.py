"""Context menus: one helper for every menu of the window, which keeps the menu's grab on X11 (Linux) so that a click
elsewhere closes it (Arthur, 13 Nov 2026: on a Linux laptop the menu stayed open), and releases it elsewhere."""
from pathlib import Path
import re
import unittest
from unittest import mock

from retrorecomp.dialogs import popup_menu

ROOT = Path(__file__).resolve().parents[1]


def fake_menu(windowing):
    menu = mock.Mock()
    menu.tk.call.return_value = windowing
    return menu


class PopupMenuTests(unittest.TestCase):
    def test_x11_keeps_the_grab_so_an_outside_click_closes_the_menu(self):
        menu = fake_menu('x11')
        popup_menu(menu, 10, 20)
        menu.tk_popup.assert_called_once_with(10, 20)
        menu.grab_release.assert_not_called()

    def test_windows_and_macos_release_the_grab_after_the_native_menu(self):
        for windowing in ('win32', 'aqua'):
            menu = fake_menu(windowing)
            popup_menu(menu, 3, 4)
            menu.tk_popup.assert_called_once_with(3, 4)
            menu.grab_release.assert_called_once_with()

    def test_the_grab_is_released_even_when_the_popup_fails_off_x11(self):
        menu = fake_menu('win32')
        menu.tk_popup.side_effect = RuntimeError('no display')
        with self.assertRaises(RuntimeError):
            popup_menu(menu, 0, 0)
        menu.grab_release.assert_called_once_with()

    def test_no_module_posts_a_menu_by_itself(self):
        # A new menu goes through dialogs.popup_menu, never a copy of the tk_popup / grab_release pair.
        offenders = [path.name for path in (ROOT / 'retrorecomp').glob('*.py')
                     if path.name != 'dialogs.py' and re.search(r'\.tk_popup\(', path.read_text(encoding='utf-8'))]
        self.assertEqual(offenders, [])


if __name__ == '__main__':
    unittest.main()
