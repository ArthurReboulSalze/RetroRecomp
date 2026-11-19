"""The converter's toolbar (retrorecomp/gui.py, gui_collection.py, gui_window.py): the buttons that show only their
picture, the New paths button (its red dot and its list of games), the problem report button, and the way Front-end and
Multiplayer stand apart. The real window is built withdrawn, its data in a temporary folder: no ROM, no game."""
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from retrorecomp import gui_welcome
from retrorecomp.compiled_games import Game
from retrorecomp.gui import Application
from tools.gui_patching import keep_window_data_in, patch_gui


def game(title, system='gb', index=0):
    return Game(f'C:/games/{system}/{title}.exe', system, f'{index:02x}' * 32, title, status='new_hints', hints=2)


GAMES = [game('Sonic 2', 'md', 1), game('Super Mario Land', 'gb', 2), game('Contra', 'nes', 3),
         game('Alex Kidd', 'sms', 4), game('Street Fighter II', 'snes', 5)]


class ToolbarWindow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name).resolve()
        keep_window_data_in(self, folder / 'datas')
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        with patch_gui('load_preferences', return_value={'language': 'en'}), \
                patch_gui('preferred_games_root', return_value=(folder / 'exports', False)):
            self.app = Application(self.root)
        self.root.update_idletasks()
        self.addCleanup(self.close_window)

    def close_window(self):
        # Every pending timer is cancelled through the widget that owns its command (as test_dropfiles does), so that
        # destroying the window finds no command still scheduled.
        owners = {name: widget for widget in all_widgets(self.root) for name in (widget._tclCommands or [])}
        for job in self.root.tk.call('after', 'info'):
            command = self.root.tk.call('after', 'info', job)[0]
            owners.get(command, self.root).after_cancel(job)
        self.root.destroy()

    def with_games(self, games):
        """The collection holds `games` as games with new paths (the button counts them)."""
        patcher = patch.object(self.app.compiled_inventory, 'snapshot', return_value=games)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.app.update_new_paths()

    def dialog(self, act, games=GAMES):
        """Open the list for `games`; `act(window, boxes)` plays the user's part before the window closes (it must close
        it, as a button does). Returns what the dialog returned."""
        def wait(window):
            self.root.update()
            act(window, [w for w in all_widgets(window) if w.winfo_class() == 'TCheckbutton'])
            self.assertFalse(window.winfo_exists())
        with patch.object(self.root, 'wait_window', side_effect=wait):
            return self.app.new_paths_dialog(games)


def all_widgets(widget):
    yield widget
    for child in widget.winfo_children():
        yield from all_widgets(child)


def pressed(window, text):
    button = next(w for w in all_widgets(window) if w.winfo_class() == 'TButton' and w.cget('text') == text)
    button.invoke()
    return button


class PicturesOnly(ToolbarWindow):
    def test_options_knowledge_and_front_end_show_only_their_picture_and_keep_text_and_hint(self):
        app = self.app
        hints = {id(hint.widget): hint.text() for hint in app.tooltips}
        for button, name, tip in ((app.options_button, 'options', 'tip_options'),
                                  (app.knowledge_button, 'knowledge', 'tip_knowledge'),
                                  (app.front_end_button, 'front_end', 'tip_front_end'),
                                  (app.report_button, 'report_title', 'tip_report_problem')):
            self.assertEqual(str(button.cget('compound')), 'image', name)
            self.assertTrue(button.cget('text'), name)               # kept for the screen reader
            self.assertEqual(hints[id(button)], app.tr(name) + '\n' + app.tr(tip))

    def test_front_end_and_multiplayer_stand_in_the_middle_with_the_accent_style(self):
        app = self.app
        self.root.deiconify()
        self.root.geometry('1300x700+0+0')
        self.root.update()
        self.root.withdraw()
        centre = app.toolbar_centre
        self.assertIn(centre, app.toolbar.pack_slaves())
        self.assertIs(app.front_end_button.master, centre)
        self.assertIs(app.multiplayer_button.master, centre)
        for button in (app.front_end_button, app.multiplayer_button):
            self.assertEqual(str(button.cget('style')), 'Feature.Toolbar.TButton')
        self.assertEqual(str(app.options_button.cget('style')), 'Toolbar.TButton')
        # Left of the rarely used buttons, right of the view's, not stuck to either side.
        left = app.new_paths_buttons[0].winfo_rootx() + app.new_paths_buttons[0].winfo_width()
        right = app.knowledge_button.winfo_rootx()
        self.assertGreater(app.multiplayer_button.winfo_rootx(), left + 20)
        self.assertLess(app.front_end_button.winfo_rootx() + app.front_end_button.winfo_width(), right - 20)
        self.assertLess(app.multiplayer_button.winfo_rootx(), app.front_end_button.winfo_rootx())

    def test_the_switch_shows_a_picture_of_the_view_it_leads_to_in_both_views(self):
        from retrorecomp.branding import ICON_PATHS
        app = self.app
        for name in ('switch_compiled', 'switch_queue'):
            self.assertIn(name, ICON_PATHS)
        button = app.compiled_button
        hint = next(h for h in app.tooltips if h.widget is button)
        self.assertEqual(str(button.cget('compound')), 'image')
        self.assertEqual(button.cget('image')[0], str(app.button_images[('switch_compiled', True)][0]))
        self.assertEqual(button.cget('text'), app.tr('compiled_games'))          # the name stays on the widget
        self.assertEqual(hint.text(), app.tr('compiled_games') + '\n' + app.tr('tip_compiled_games'))
        with patch('retrorecomp.compiled_games_view.CompiledGamesView.scan'):
            app.toggle_compiled_games()
        self.assertEqual(button.cget('image')[0], str(app.button_images[('switch_queue', True)][0]))
        self.assertEqual(button.cget('text'), app.tr('conversion_queue'))
        self.assertEqual(hint.text(), app.tr('conversion_queue') + '\n' + app.tr('tip_conversion_queue'))
        self.assertEqual(str(button.cget('style')), 'Compiled.Toolbar.TButton')   # the gold emphasis stays

    def test_the_queue_buttons_show_only_their_picture_and_keep_name_hint_and_a_readable_disabled_state(self):
        app = self.app
        hints = {id(hint.widget): hint.text() for hint in app.tooltips}
        pictures = {}
        for button, name, tip, symbol in (
                (app.add_roms_button, 'add_roms', 'tip_add_roms', 'add_roms'),
                (app.cover_button, 'choose_cover', 'tip_choose_cover', 'cover_choose'),
                (app.auto_cover_button, 'auto_cover', 'tip_auto_cover', 'cover_auto'),
                (app.play_button, 'play', 'tip_play', 'play_game'),
                (app.memory_button, 'memory', 'tip_memory', 'memory_chip'),
                (app.start_button, 'start', 'tip_start', 'convert_all'),
                (app.selected_button, 'start_selected', 'tip_start_selected', 'convert_selected'),
                (app.stop_button, 'stop', 'tip_stop', 'stop'),
                (app.retry_button, 'retry', 'tip_retry', 'retry_failed')):
            self.assertEqual(str(button.cget('compound')), 'image', name)
            self.assertEqual(button.cget('text'), app.tr(name))
            self.assertEqual(hints[id(button)], app.tr(name).rstrip('…') + '\n' + app.tr(tip))
            normal, disabled = (str(image) for image in next(v for k, v in app.button_images.items()
                                                             if k[0] == symbol and k[1] in (False, True)))
            image = button.cget('image')
            self.assertEqual((str(image[0]), str(image[1]), str(image[2])), (normal, 'disabled', disabled), name)  # greyed, never hidden
            pictures[name] = normal
        # Every item of the queue against the selected rows: two different pictures.
        self.assertNotEqual(pictures['start'], pictures['start_selected'])
        self.assertEqual(str(app.start_button.cget('style')), 'Toolbar.Primary.TButton')   # gold
        self.assertEqual(str(app.add_roms_button.cget('style')), 'Toolbar.Primary.TButton')
        self.assertEqual(str(app.play_button.cget('state')), 'disabled')

    def test_the_video_word_is_a_small_screen_with_its_hint(self):
        app = self.app
        label = app.video_label
        self.assertEqual(str(label.cget('compound')), 'image')
        self.assertEqual(label.cget('text'), app.tr('video_timing'))
        hint = next(h for h in app.tooltips if h.widget is label)
        self.assertEqual(hint.text(), app.tr('video_timing') + '\n' + app.tr('tip_video_timing'))
        self.assertTrue(app.video_icon.width() > 0)                              # held, so Tk keeps it

    def test_the_names_follow_the_language_even_when_another_string_shares_the_text(self):
        # « Stop » is also the text of another string in some language: the reverse map of refresh_language could take it.
        app = self.app
        for code in ('ru', 'fr', 'de', 'en'):
            app.language = code
            app.refresh_language()
            self.assertEqual(app.stop_button.cget('text'), app.tr('stop'), code)
            self.assertEqual(app.start_button.cget('text'), app.tr('start'), code)
            self.assertEqual(app.video_label.cget('text'), app.tr('video_timing'), code)

    def test_the_full_screen_button_is_a_picture_whose_hint_follows_its_state(self):
        app = self.app
        button = app.front_end_screen_button
        self.assertEqual(button.master, app.toolbar)                        # not in the middle pair
        self.assertEqual(button.winfo_manager(), '')                        # only while the front-end is open
        self.assertEqual(str(button.cget('compound')), 'image')
        hint = next(h for h in app.tooltips if h.widget is button)
        self.assertEqual(hint.text(), app.tr('front_end_fullscreen') + '\n' + app.tr('tip_front_end_fullscreen'))
        enter = str(button.cget('image')[0])
        app.front_end_fullscreen = True
        app.front_end_screen_picture()
        self.assertEqual(hint.text(), app.tr('front_end_window') + '\n' + app.tr('tip_front_end_fullscreen'))
        self.assertNotEqual(str(button.cget('image')[0]), enter)
        self.assertEqual(button.cget('text'), app.tr('front_end_window'))

    def test_the_welcome_message_types_at_140_characters_a_second(self):
        self.assertEqual(gui_welcome.MESSAGE_RATE, 140)


class NewPathsButton(ToolbarWindow):
    def button(self):
        return self.app.new_paths_buttons[0]

    def test_a_red_dot_shows_while_games_have_new_paths_and_goes_away_with_them(self):
        app, button = self.app, self.button()
        plain = app.button_images[('new_paths', False)][0]
        self.assertEqual(str(button.cget('image')[0]), str(plain))
        self.assertEqual(str(button.cget('state')), 'disabled')
        self.with_games(GAMES)
        badge = app.button_images[('new_paths', 'badge')][0]
        self.assertEqual(str(button.cget('image')[0]), str(badge))
        self.assertNotEqual(str(badge), str(plain))
        self.assertEqual(str(button.cget('state')), 'normal')
        self.assertEqual(str(button.cget('compound')), 'image')
        # The count is in the text kept on the widget and in the hint.
        self.assertIn('(5)', button.cget('text'))
        hint = next(h for h in app.tooltips if h.widget is button).text()
        self.assertTrue(hint.startswith(app.tr('recompile_new_paths', count=5) + '\n'))
        self.with_games([])
        self.assertEqual(str(button.cget('image')[0]), str(plain))
        self.assertEqual(str(button.cget('state')), 'disabled')
        # The same mechanism as the update button's dot (one helper, one cache).
        self.assertIs(app.button_images[('new_paths', 'badge')][0], badge)

    def test_the_dot_is_really_drawn_in_the_badge_colour(self):
        from retrorecomp.gui_drawing import BADGE_COLOR
        self.with_games(GAMES)
        image = self.app.button_images[('new_paths', 'badge')][0]
        corner = image.get(14, 3)
        self.assertEqual('#%02x%02x%02x' % tuple(corner), BADGE_COLOR)
        plain = self.app.button_images[('new_paths', False)][0]
        self.assertNotEqual('#%02x%02x%02x' % tuple(plain.get(14, 3)), BADGE_COLOR)

    def test_the_update_button_still_uses_the_same_dot(self):
        app = self.app
        app.update_news = {'software': object(), 'base': None}
        app.refresh_update_badge()
        self.assertIn(('download', 'badge'), app.button_images)
        self.assertEqual(str(app.update_button.cget('image')[0]), str(app.button_images[('download', 'badge')][0]))
        self.assertEqual(str(app.update_button.cget('compound')), 'image')
        app.update_news = {}
        app.refresh_update_badge()
        self.assertEqual(str(app.update_button.cget('image')[0]), str(app.button_images[('download', False)][0]))

    def test_the_button_opens_the_list_and_reconverts_only_what_was_ticked(self):
        app = self.app
        self.with_games(GAMES)
        seen = []

        def act(window, boxes):
            seen.append([box.cget('text') for box in boxes])
            boxes[1].invoke()
            boxes[3].invoke()
            pressed(window, app.tr('reconvert'))
        with patch.object(app, 'reconvert_games') as reconvert, patch.object(app, 'toggle_compiled_games'), \
                patch.object(self.root, 'wait_window', side_effect=lambda w: act(w, [x for x in all_widgets(w)
                                                                                    if x.winfo_class() == 'TCheckbutton'])):
            self.button().invoke()
        self.assertEqual(seen, [[g.title for g in GAMES]])
        reconvert.assert_called_once()
        self.assertEqual([g.title for g in reconvert.call_args.args[0]], ['Sonic 2', 'Contra', 'Street Fighter II'])
        self.assertEqual(reconvert.call_args.kwargs, {'skip_missing': True})

    def test_cancel_reconverts_nothing(self):
        app = self.app
        self.with_games(GAMES)
        with patch.object(app, 'reconvert_games') as reconvert:
            with patch.object(self.root, 'wait_window', side_effect=lambda w: pressed(w, app.tr('knowledge_cancel'))):
                self.button().invoke()
        reconvert.assert_not_called()

    def test_escape_and_closing_the_window_reconvert_nothing(self):
        app = self.app
        self.with_games(GAMES)
        with patch.object(app, 'reconvert_games') as reconvert:
            with patch.object(self.root, 'wait_window', side_effect=lambda w: w.event_generate('<Escape>')):
                self.button().invoke()
            with patch.object(self.root, 'wait_window', side_effect=lambda w: w.destroy()):
                self.button().invoke()
        reconvert.assert_not_called()

    def test_the_list_has_every_game_ticked_and_unticking_excludes_it(self):
        def act(window, boxes):
            self.assertEqual(len(boxes), 5)
            self.assertTrue(all(box.instate(['selected']) for box in boxes))
            boxes[2].invoke()
            self.assertFalse(boxes[2].instate(['selected']))
            pressed(window, self.app.tr('reconvert'))
        chosen = self.dialog(act)
        self.assertEqual([g.title for g in chosen], ['Sonic 2', 'Super Mario Land', 'Alex Kidd', 'Street Fighter II'])

    def test_with_nothing_ticked_reconvert_is_off(self):
        def act(window, boxes):
            go = next(w for w in all_widgets(window) if w.winfo_class() == 'TButton'
                      and w.cget('text') == self.app.tr('reconvert'))
            self.assertEqual(str(go.cget('state')), 'normal')
            for box in boxes:
                box.invoke()
            self.assertEqual(str(go.cget('state')), 'disabled')
            boxes[0].invoke()
            self.assertEqual(str(go.cget('state')), 'normal')
            pressed(window, self.app.tr('knowledge_cancel'))
        self.assertEqual(self.dialog(act), [])

    def test_many_games_scroll(self):
        many = [game(f'Game {index}', 'gb', index) for index in range(20)]

        def act(window, boxes):
            self.assertEqual(len(boxes), 20)
            self.assertTrue(any(w.winfo_class() == 'TScrollbar' for w in all_widgets(window)))
            pressed(window, self.app.tr('reconvert'))
        self.assertEqual(len(self.dialog(act, many)), 20)

    def test_the_closing_card_and_the_leaderboard_reconvert_the_games_they_chose_without_the_list(self):
        app = self.app
        with patch.object(app, 'new_paths_dialog') as listing, patch.object(app, 'reconvert_games') as reconvert, \
                patch.object(app, 'toggle_compiled_games'):
            app.recompile_new_paths(GAMES[:2])
        listing.assert_not_called()
        self.assertEqual([g.title for g in reconvert.call_args.args[0]], ['Sonic 2', 'Super Mario Land'])

    def test_nothing_opens_while_busy_or_without_games(self):
        app = self.app
        with patch.object(app, 'new_paths_dialog') as listing:
            app.choose_new_paths()                     # no game with new paths
            self.with_games(GAMES)
            app.busy = True
            app.choose_new_paths()
        listing.assert_not_called()


class ReportButton(ToolbarWindow):
    def test_it_is_the_last_button_after_credits_and_opens_the_report_flow(self):
        app = self.app
        with patch.object(app, 'report_problem') as report:
            app.report_button.invoke()
        report.assert_called_once_with('manual')
        slaves = app.toolbar.pack_slaves()
        if app.report_button.winfo_manager():
            self.assertLess(slaves.index(app.report_button), slaves.index(app.credits_button))   # packed first: more right
        self.assertEqual(str(app.report_button.cget('compound')), 'image')

    def test_the_report_button_stays_available_while_a_conversion_runs(self):
        app = self.app
        app.set_controls(False)
        self.assertEqual(str(app.report_button.cget('state')), 'normal')
        app.set_controls(True)

    def test_the_count_comes_back_after_the_report_button(self):
        with patch('retrorecomp.gui_window.SENDING_AVAILABLE', True):
            app = self.app
            app.report_button.pack(side='right', padx=(0, 12))
            app.count_label.pack_forget()
            app.place_count_label()
            slaves = app.toolbar.pack_slaves()
            self.assertLess(slaves.index(app.count_label), slaves.index(app.report_button))


if __name__ == '__main__':
    unittest.main()
