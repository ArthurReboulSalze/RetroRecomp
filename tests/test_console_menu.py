"""The console menu of the window: every machine has a short, unique label that fits the closed field whole,
and the drop-down list is as wide as its longest entry. Labels are interface data: no stamp moves."""
import tkinter as tk
from tkinter import font as tkfont, ttk
import unittest
from unittest.mock import Mock

from retrorecomp import stamp_inputs
from retrorecomp.console_menu import (FIELD_CHARACTERS, LIST_PADDING, MENU_LABELS, field_characters,
                                      menu_label, popdown_extra, profile_for_label)
from retrorecomp.gui import Application
from retrorecomp.gui_common import PROFILES
from retrorecomp.i18n import tr
from retrorecomp.languages import LANGUAGES, LANGUAGE_NAMES
from retrorecomp.systems import ALL_PROFILES


def entries(language='en'):
    return [tr('automatic', language), *(menu_label(profile) for profile in PROFILES)]


class MenuLabels(unittest.TestCase):
    def test_every_label_is_unique_and_the_two_amigas_differ(self):
        labels = [menu_label(profile) for profile in PROFILES]
        self.assertEqual(len(labels), len(set(labels)))
        for language in LANGUAGES:
            self.assertEqual(len(entries(language)), len(set(entries(language))))
        by_id = {profile.id: menu_label(profile) for profile in PROFILES}
        self.assertEqual((by_id['amiga'], by_id['a1200']), ('Amiga 500', 'Amiga 1200'))
        self.assertNotIn('Commodore', ' '.join(labels))

    def test_labels_are_data_keyed_by_real_profile_ids(self):
        self.assertLessEqual(set(MENU_LABELS), {profile.id for profile in ALL_PROFILES})
        for profile in PROFILES:
            self.assertEqual(profile_for_label(PROFILES, menu_label(profile)), profile)
        self.assertIsNone(profile_for_label(PROFILES, tr('automatic')))

    def test_the_full_names_are_unchanged(self):
        names = {profile.id: profile.name for profile in ALL_PROFILES}
        self.assertEqual(names['amiga'], 'Commodore Amiga')
        self.assertEqual(names['a1200'], 'Commodore Amiga 1200')
        self.assertEqual(names['pce'], 'PC Engine / TurboGrafx-16')

    def test_the_menu_moves_no_stamp(self):
        self.assertIn('console_menu', stamp_inputs.INTERFACE_MODULES)


class Selection(unittest.TestCase):
    def window(self, **attributes):
        app = Application.__new__(Application)
        app.language, app.busy, app.reload_queue = 'en', False, Mock()
        app.tr = lambda key, **values: tr(key, 'en', **values)
        app.system_name = Mock()
        for name, value in attributes.items():
            setattr(app, name, value)
        return app

    def test_a_chosen_label_selects_its_profile_and_back(self):
        for profile in PROFILES:
            app = self.window(system_mode='auto')
            app.system_name.get.return_value = menu_label(profile)
            app.change_system()
            self.assertEqual(app.system_mode, profile.id)
            app.reload_queue.assert_called_once()
            self.assertEqual(app.system_display(), menu_label(profile))
        app = self.window(system_mode='a1200')
        app.system_name.get.return_value = tr('automatic')
        app.change_system()
        self.assertEqual(app.system_mode, 'auto')
        self.assertEqual(app.system_choices()[0], tr('automatic'))


class FieldAndList(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f'no Tk display: {error}')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def test_every_label_shows_whole_in_the_closed_field(self):
        # A ttk combobox's `width` is the text area, in characters of its font ('0'); the arrow is extra.
        # Nothing is mapped (no window is shown), so the text area is computed rather than read from the screen.
        for family in ('Segoe UI', 'TkDefaultFont'):
            font = tkfont.Font(root=self.root, font=(family, 8)) if family != 'TkDefaultFont' else tkfont.nametofont(family)
            labels = (*entries('en'), *entries('fr'), *entries('ru'), *LANGUAGE_NAMES)
            area = field_characters(font, labels) * font.measure('0')
            for label in labels:
                self.assertGreaterEqual(area, font.measure(label) + 8, f'{label!r} is cut in {family}')
            # The real widget carries that width (the text area leaves the arrow out).
            field = ttk.Combobox(self.root, values=labels, state='readonly', font=font,
                                 width=field_characters(font, labels))
            self.assertGreaterEqual(int(field.cget('width')) * font.measure('0'), area)

    def test_the_old_width_cut_the_long_names_and_the_new_one_does_not(self):
        # Positive control: the 14 characters of before could not show these whole.
        font = tkfont.Font(root=self.root, font=('Segoe UI', 8))
        zero = font.measure('0')
        for name in ('Commodore Amiga 1200', 'Game Boy Advance'):
            self.assertLess(FIELD_CHARACTERS * zero, font.measure(name) + 8)
        self.assertGreater(field_characters(font, ['Game Boy Advance']), FIELD_CHARACTERS)

    def test_the_list_covers_its_longest_entry(self):
        font = tkfont.Font(root=self.root, font=('Segoe UI', 8))
        full = [profile.name for profile in ALL_PROFILES]
        for field_pixels in (60, 84, 130):
            extra = popdown_extra(font, full, field_pixels)
            widest = max(font.measure(name) for name in full)
            self.assertGreaterEqual(field_pixels + extra, widest + LIST_PADDING)
        self.assertEqual(popdown_extra(font, ['Neo Geo'], 400), 0)


if __name__ == '__main__':
    unittest.main()
