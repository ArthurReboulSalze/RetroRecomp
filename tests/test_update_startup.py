"""The start-up look for something new, the dot on the update button and what a click offers.

The base API (online.check_base / online.update_base) is replaced by mocks:
nothing here reaches the network, and no window is ever shown.
"""
from queue import Queue
import os
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from retrorecomp import online
from retrorecomp.gui import Application, UPDATE_CHECK_EVERY, base_is_newer
from retrorecomp.i18n import tr
from retrorecomp.languages import LANGUAGES
from retrorecomp.updater import Update, UpdateConnectionError
from tools.gui_patching import patch_gui

NOW = 1_800_000_000.0
UPDATE = Update('1.5.5', 'https://example.test/Retro-Recomp.exe', 'https://example.test/tag', 'a' * 64, 1000)
NEWER_BASE = {'local': 413, 'latest': 414, 'newer': True, 'error': None}
CURRENT_BASE = {'local': 414, 'latest': 414, 'newer': False, 'error': None}


class Flag:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class SameThread:
    """threading.Thread that runs its target when started, so a worker's message is there at once."""
    def __init__(self, target=None, daemon=None, **kwargs):
        self.target = target

    def start(self):
        self.target()


def application(startup=True, last=None):
    window = Application.__new__(Application)
    window.language = 'en'
    window.messages = Queue()
    window.busy = window.updating = False
    window.update_button, window.start_button, window.app = Mock(), Mock(), Mock()
    window.set_status = Mock()
    window.button_images = {('download', False): ('plain', 'plain-off')}
    window.check_at_startup = Flag(startup)
    window.last_update_check = last
    window.update_news = {'software': None, 'base': None}
    return window


def queued(window):
    events = []
    while not window.messages.empty():
        events.append(window.messages.get_nowait())
    return events


class StartupLookTests(unittest.TestCase):
    def look(self, window, software=UPDATE, base=NEWER_BASE, now=NOW):
        """Run the start-up look; the mocks it called, and the message it sent."""
        software_call = Mock(side_effect=software) if isinstance(software, BaseException) else Mock(return_value=software)
        base_call = Mock(side_effect=base) if isinstance(base, BaseException) else Mock(return_value=base)
        with patch('threading.Thread', SameThread), \
                patch('retrorecomp.updater.check_for_update', software_call), \
                patch('retrorecomp.online.check_base', base_call, create=True), \
                patch('time.time', return_value=now):
            window.startup_update_check()
        return software_call, base_call, queued(window)

    def test_the_option_is_what_decides_and_nothing_is_sent_when_it_is_off(self):
        software, base, events = self.look(application(startup=False))
        self.assertFalse(software.called or base.called)
        self.assertEqual(events, [])

    def test_a_recent_look_is_not_repeated_but_an_old_or_missing_one_is(self):
        for last, expected in ((None, True), (NOW - UPDATE_CHECK_EVERY + 60, False), (NOW - UPDATE_CHECK_EVERY, True),
                               (NOW - 7 * 3600, True), (NOW + 3600, True), ('junk', True)):
            window = application(last=last)
            software, base, events = self.look(window)
            self.assertEqual(software.called and base.called, expected, last)
            self.assertEqual(len(events), 1 if expected else 0, last)

    def test_the_look_sends_both_results_through_the_queue(self):
        software, base, events = self.look(application())
        base.assert_called_once_with()           # not forced: the start-up look may use the cache
        self.assertEqual(events, [('update_news', True, UPDATE, True, NEWER_BASE)])

    def test_offline_is_silent_and_remembers_nothing(self):
        window = application()
        with patch_gui('messagebox') as boxes:
            software, base, events = self.look(window, software=UpdateConnectionError(), base=OSError('offline'))
            self.assertEqual(events, [('update_news', False, None, False, None)])
            window.apply_update_news(*events[0][1:])
            boxes.showerror.assert_not_called()
            boxes.showinfo.assert_not_called()
        self.assertIsNone(window.last_update_check)
        self.assertEqual(window.update_news, {'software': None, 'base': None})

    def test_a_base_reported_in_error_or_missing_counts_as_not_reached(self):
        for base in ({'local': 1, 'latest': None, 'newer': False, 'error': 'offline'}, None, 'junk'):
            _, _, events = self.look(application(), base=base)
            self.assertEqual(events[0][3:], (False, None), base)
        window = application()
        with patch_gui('online', SimpleNamespace()):        # before the base API exists
            self.assertIsNone(window.look_at_base())

    def test_the_software_half_alone_is_enough_to_space_the_next_look(self):
        window = application()
        window.apply_update_news(True, UPDATE, False, None)
        self.assertEqual(window.update_news['software'], UPDATE)
        self.assertIsNotNone(window.last_update_check)

    def test_a_side_that_could_not_be_reached_keeps_what_it_showed(self):
        window = application()
        window.update_news.update(software=UPDATE, base=NEWER_BASE)
        window.apply_update_news(False, None, True, CURRENT_BASE)
        self.assertEqual(window.update_news, {'software': UPDATE, 'base': None})

    def test_base_newer_needs_a_published_base_beyond_the_local_one(self):
        self.assertTrue(base_is_newer(NEWER_BASE))
        self.assertFalse(base_is_newer(CURRENT_BASE))
        self.assertFalse(base_is_newer(dict(NEWER_BASE, latest=None)))
        self.assertFalse(base_is_newer(dict(NEWER_BASE, error='offline')))
        self.assertFalse(base_is_newer(None))


class BadgeTextTests(unittest.TestCase):
    def test_the_hint_names_what_is_new(self):
        window = application()
        usual = tr('tip_check_updates', 'en')
        self.assertEqual(window.update_tip(), usual)
        window.update_news.update(software=UPDATE)
        self.assertEqual(window.update_news_lines(), ['New version 1.5.5'])
        window.update_news.update(base=NEWER_BASE)
        self.assertEqual(window.update_news_lines(), ['New version 1.5.5', 'New base 414'])
        self.assertTrue(window.update_tip().startswith('New version 1.5.5\nNew base 414\n\n'))
        window.update_news.update(software=None)
        self.assertEqual(window.update_news_lines(), ['New base 414'])
        window.update_news.update(base=None)
        self.assertEqual(window.update_news_lines(), [])

    def test_every_language_has_its_lines(self):
        window = application()
        window.update_news.update(software=UPDATE, base=NEWER_BASE)
        for code in LANGUAGES:
            window.language = code
            lines = window.update_news_lines()
            self.assertTrue(all('1.5.5' in lines[0] and '414' in lines[1] for _ in [0]), (code, lines))
            self.assertNotEqual(lines[0].replace('1.5.5', ''), lines[1].replace('414', ''), code)


class ClickTests(unittest.TestCase):
    def click(self, window, choice=None, software=None, base=None):
        window.update_news.update(software=software, base=base)
        with patch.object(Application, '_offer_update') as offer, \
                patch.object(Application, 'update_base_now') as update_base, \
                patch.object(Application, 'update_choice_dialog', return_value=choice) as dialog:
            window.check_updates()
        return offer, update_base, dialog

    def test_a_new_software_alone_goes_to_the_existing_question(self):
        offer, update_base, dialog = self.click(application(), software=UPDATE)
        offer.assert_called_once_with(UPDATE)
        dialog.assert_not_called()
        update_base.assert_not_called()

    def test_a_new_base_alone_offers_the_base_or_later(self):
        offer, update_base, dialog = self.click(application(), choice='base', base=NEWER_BASE)
        dialog.assert_called_once_with(None, NEWER_BASE)
        update_base.assert_called_once_with()
        offer.assert_not_called()
        offer, update_base, dialog = self.click(application(), choice=None, base=NEWER_BASE)
        self.assertFalse(offer.called or update_base.called)

    def test_both_new_offer_three_choices_that_call_the_right_functions(self):
        for choice, expected_offer, expected_base in (
                ('software', [((UPDATE,), {})], []), ('base', [], [((), {})]),
                ('both', [], [((), {'then': UPDATE})]), (None, [], [])):
            offer, update_base, dialog = self.click(application(), choice, UPDATE, NEWER_BASE)
            dialog.assert_called_once_with(UPDATE, NEWER_BASE)
            self.assertEqual([tuple(call) for call in offer.call_args_list], expected_offer, choice)
            self.assertEqual([tuple(call) for call in update_base.call_args_list], expected_base, choice)

    def test_a_click_while_busy_or_updating_does_nothing(self):
        for flag in ('busy', 'updating'):
            window = application()
            setattr(window, flag, True)
            offer, update_base, dialog = self.click(window, software=UPDATE, base=NEWER_BASE)
            self.assertFalse(offer.called or update_base.called or dialog.called)

    def test_with_nothing_known_it_checks_the_software_and_the_base_by_hand(self):
        window = application()
        with patch('threading.Thread', SameThread), \
                patch('retrorecomp.updater.check_for_update', return_value=UPDATE) as software, \
                patch('retrorecomp.online.check_base', return_value=NEWER_BASE, create=True) as base:
            window.check_updates()
        software.assert_called_once_with()
        base.assert_called_once_with(force=True)
        self.assertEqual(queued(window), [('update_check', UPDATE, NEWER_BASE)])
        self.assertTrue(window.updating)
        window.update_button.configure.assert_called_with(state='disabled')

    def test_a_software_check_that_fails_is_still_reported_as_before(self):
        window = application()
        error = UpdateConnectionError()
        with patch('threading.Thread', SameThread), \
                patch('retrorecomp.updater.check_for_update', side_effect=error), \
                patch('retrorecomp.online.check_base', return_value=NEWER_BASE, create=True):
            window.check_updates()
        self.assertEqual(queued(window), [('update_error', error)])

    def test_a_manual_check_that_finds_nothing_says_up_to_date_and_clears_the_dot(self):
        window = application()
        window.update_news.update(software=UPDATE, base=NEWER_BASE)
        with patch_gui('messagebox') as boxes, patch.object(Application, 'refresh_update_badge') as badge:
            window.manual_check_done(None, CURRENT_BASE)
        boxes.showinfo.assert_called_once_with('Retro-Recomp', 'RetroRecomp is up to date.')
        self.assertEqual(window.update_news, {'software': None, 'base': None})
        self.assertTrue(badge.called)
        self.assertFalse(window.updating)

    def test_a_manual_check_finding_only_a_base_offers_it(self):
        window = application()
        with patch.object(Application, 'update_choice_dialog', return_value='base') as dialog, \
                patch.object(Application, 'update_base_now') as update_base, \
                patch.object(Application, 'refresh_update_badge'):
            window.manual_check_done(None, NEWER_BASE)
        dialog.assert_called_once_with(None, NEWER_BASE)
        update_base.assert_called_once_with()
        self.assertEqual(window.update_news['base'], NEWER_BASE)

    def test_a_manual_check_whose_base_cannot_be_reached_still_answers_for_the_software(self):
        window = application()
        with patch_gui('messagebox') as boxes, patch.object(Application, 'refresh_update_badge'):
            window.manual_check_done(None, None)
        boxes.showinfo.assert_called_once()


class BaseUpdateTests(unittest.TestCase):
    def test_the_worker_updates_the_base_and_reports_the_short_result(self):
        window = application()
        result = {'version': 414, 'previous': 413, 'downloaded_bytes': 2048, 'source': 'delta', 'error': None}
        with patch('threading.Thread', SameThread), \
                patch('retrorecomp.online.update_base', return_value=result, create=True) as update:
            window.update_base_now(then=UPDATE)
        update.assert_called_once_with()
        self.assertEqual(queued(window), [('base_updated', result, UPDATE)])
        self.assertTrue(window.updating)
        window.start_button.configure.assert_called_with(state='disabled')
        window.set_status.assert_called_with('updating_base')

    def test_a_worker_that_raises_or_has_no_base_api_reports_an_error(self):
        window = application()
        with patch('threading.Thread', SameThread), \
                patch('retrorecomp.online.update_base', side_effect=OSError('refused'), create=True):
            window.update_base_now()
        with patch('threading.Thread', SameThread), patch_gui('online', SimpleNamespace()):
            window.update_base_now()
        first, second = queued(window)
        self.assertEqual(first[1]['error'], 'refused')
        self.assertTrue(second[1]['error'])

    def done(self, result, then=None, frozen=True):
        window = application()
        window.update_news.update(software=then, base=NEWER_BASE)
        window.updating = True
        with patch_gui('messagebox') as boxes, patch.object(Application, 'download_update') as download, \
                patch.object(Application, 'refresh_update_badge') as badge, \
                patch('sys.frozen', frozen, create=True):
            window.base_update_done(result, then)
        return window, boxes, download, badge

    def test_success_clears_the_base_dot_and_says_the_version(self):
        window, boxes, download, badge = self.done({'version': 414, 'previous': 413, 'downloaded_bytes': 99, 'error': None})
        self.assertIsNone(window.update_news['base'])
        self.assertTrue(badge.called)
        boxes.showinfo.assert_called_once_with('Retro-Recomp', 'The shared base is now at version 414.')
        download.assert_not_called()
        self.assertFalse(window.updating)

    def test_a_base_that_was_already_current_is_said_so(self):
        _, boxes, _, _ = self.done({'version': 414, 'previous': 414, 'downloaded_bytes': 0, 'error': None})
        self.assertIn('already up to date', boxes.showinfo.call_args.args[1])

    def test_an_error_keeps_the_dot_and_shows_the_error(self):
        window, boxes, download, _ = self.done({'error': 'The site could not be reached'}, then=UPDATE)
        self.assertEqual(window.update_news['base'], NEWER_BASE)
        self.assertIn('The site could not be reached', boxes.showerror.call_args.args[1])
        download.assert_not_called()          # both were chosen, but the software waits for a new click
        self.assertFalse(window.updating)

    def test_both_chosen_goes_on_to_the_software_download_without_asking_again(self):
        window, boxes, download, _ = self.done({'version': 414, 'previous': 413, 'downloaded_bytes': 9, 'error': None},
                                               then=UPDATE)
        download.assert_called_once_with(UPDATE)
        boxes.showinfo.assert_not_called()
        boxes.askyesno.assert_not_called()

    def test_a_source_run_only_names_the_page_of_the_software(self):
        _, boxes, download, _ = self.done({'version': 414, 'previous': 413, 'downloaded_bytes': 9, 'error': None},
                                          then=UPDATE, frozen=False)
        download.assert_not_called()
        self.assertIn(UPDATE.page, boxes.showinfo.call_args.args[1])


class DrainTests(unittest.TestCase):
    def test_the_queue_events_reach_their_handlers(self):
        window = application()
        window.results = {}
        with patch.object(Application, 'apply_update_news') as news, \
                patch.object(Application, 'manual_check_done') as manual, \
                patch.object(Application, 'base_update_done') as done, \
                patch.object(Application, '_offer_update') as offer:
            for event in (('update_news', True, UPDATE, True, NEWER_BASE), ('update_check', UPDATE, NEWER_BASE),
                          ('update_check', None), ('base_updated', {'version': 1}, None)):
                window.messages.put(event)
            window.drain()
        news.assert_called_once_with(True, UPDATE, True, NEWER_BASE)
        manual.assert_called_once_with(UPDATE, NEWER_BASE)
        offer.assert_called_once_with(None)
        done.assert_called_once_with({'version': 1}, None)


@unittest.skipUnless(os.environ.get('DISPLAY') or os.name == 'nt', 'needs a Tk display (kept hidden)')
class RealWindowTests(unittest.TestCase):
    """The real widgets, in a window that is never shown."""
    def open(self, preferences=None):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        for item in (patch_gui('load_preferences', return_value=preferences or {}),
                     patch_gui('preferred_games_root', return_value=(folder / 'exports', False)),
                     patch_gui('data_directory', return_value=folder),
                     patch('retrorecomp.compiled_games.data_directory', return_value=folder),
                     patch_gui('save_preferences'),
                     patch_gui('save_cover_settings')):
            item.start()
            self.addCleanup(item.stop)
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        root.withdraw()
        window = Application(root)
        self.addCleanup(self.close, root)
        root.update_idletasks()
        # Dialogs are built and answered but never mapped on the screen.
        for name in ('deiconify', 'grab_set'):
            patcher = patch.object(tk.Toplevel, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        return root, window

    @staticmethod
    def close(root):
        """Cancel the window's timers through their owners, then destroy it."""
        def widgets(parent):
            yield parent
            for child in parent.winfo_children():
                yield from widgets(child)
        owners = {name: widget for widget in widgets(root) for name in (widget._tclCommands or [])}
        for job in root.tk.call('after', 'info'):
            command = root.tk.call('after', 'info', job)[0]
            owners.get(command, root).after_cancel(job)
        root.destroy()

    def test_the_option_is_on_by_default_and_saved_with_the_preferences(self):
        _, window = self.open({})
        self.assertTrue(window.check_at_startup.get())
        self.assertIsNone(window.last_update_check)
        saved = window.preferences()
        self.assertIs(saved['startup_update_check'], True)
        self.assertIsNone(saved['last_update_check'])

    def test_a_saved_choice_and_look_time_come_back(self):
        _, window = self.open({'startup_update_check': False, 'last_update_check': NOW})
        self.assertFalse(window.check_at_startup.get())
        self.assertEqual(window.preferences()['startup_update_check'], False)
        self.assertEqual(window.preferences()['last_update_check'], NOW)
        self.assertFalse(window.startup_update_due())
        window.check_at_startup.set(True)
        self.assertEqual(window.preferences()['startup_update_check'], True)

    def test_a_damaged_look_time_is_ignored(self):
        for junk in ('yesterday', True, [1]):
            _, window = self.open({'last_update_check': junk})
            self.assertIsNone(window.last_update_check)
            self.assertTrue(window.startup_update_due())

    def test_the_option_sits_in_options_common_and_never_reaches_a_conversion(self):
        root, window = self.open({})
        window.show_options()
        root.update_idletasks()
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        boxes = [w for w in descendants(window.options_panel) if isinstance(w, ttk.Checkbutton)
                 and w.cget('text') == window.tr('startup_update_check')]
        self.assertEqual(len(boxes), 1)
        boxes[0].invoke()
        self.assertFalse(window.check_at_startup.get())
        window.close_options()

    def test_use_shared_base_is_a_common_option_even_signed_out(self):
        """The published base needs no account: its option is outside the account frame."""
        for account in (None, {'email': 'pat@example.test'}):
            with patch('retrorecomp.online.account', return_value=account):
                root, window = self.open({'use_shared_base': False})
                window.show_options()
                window.update_account_options()
                root.update_idletasks()
            def boxes(parent, text):
                return [w for w in self.walk(parent) if isinstance(w, ttk.Checkbutton) and w.cget('text') == text]
            shared = boxes(window.options_panel, window.tr('use_shared_base'))
            self.assertEqual(len(shared), 1, account)
            self.assertFalse(any(w in self.walk(window.account_frame) for w in shared))
            self.assertTrue(shared[0].winfo_ismapped() or shared[0].winfo_manager(), account)
            self.assertFalse(window.use_shared_base.get())          # the saved choice, same key
            self.assertIs(window.preferences()['use_shared_base'], False)
            # The sending option stays with the account.
            sending = boxes(window.account_frame, window.tr('send_after_batch'))
            self.assertEqual(len(sending), 1)
            self.assertEqual(bool(window.account_sync.winfo_manager()), account is not None)
            self.assertEqual(boxes(window.account_frame, window.tr('use_shared_base')), [])
            window.close_options()

    def test_the_dot_and_the_hint_follow_what_is_new(self):
        root, window = self.open({})
        plain = str(window.update_button.cget('image'))
        pictures = {}
        for name, software, base in (('software', UPDATE, None), ('base', None, NEWER_BASE),
                                     ('both', UPDATE, NEWER_BASE), ('none', None, None)):
            window.update_news.update(software=software, base=base)
            window.refresh_update_badge()
            pictures[name] = str(window.update_button.cget('image'))
        self.assertEqual(pictures['none'], plain)
        self.assertEqual(pictures['software'], pictures['base'])
        self.assertEqual(pictures['software'], pictures['both'])
        self.assertNotEqual(pictures['software'], plain)
        hint = next(h for h in window.tooltips if h.widget is window.update_button)
        window.update_news.update(software=UPDATE, base=NEWER_BASE)
        self.assertTrue(hint.text().startswith('New version 1.5.5\nNew base 414'))
        window.update_news.update(software=None, base=None)
        self.assertEqual(hint.text(), window.tr('tip_check_updates'))

    def test_the_dot_is_a_red_pixel_block_at_the_top_right_of_the_picture(self):
        _, window = self.open({})
        window.update_news.update(software=UPDATE)
        window.refresh_update_badge()
        normal = window.button_images[('download', 'badge')][0]
        plain = window.button_images[('download', False)][0]
        self.assertEqual(normal.get(14, 3), (0xe5, 0x48, 0x4d))
        self.assertNotEqual(plain.get(14, 3), (0xe5, 0x48, 0x4d))

    def test_the_choice_dialog_offers_exactly_what_is_new(self):
        root, window = self.open({})
        # Each dialog is answered by its primary button (the first one after "Later").
        results = {}
        for name, software, base, expected_labels in (
                ('both', UPDATE, NEWER_BASE, ['Later', 'Update both', 'Update the base', 'Update the software']),
                ('base', None, NEWER_BASE, ['Later', 'Update the base'])):
            seen = []
            def look(seen=seen):
                grab = self.dialog(root)
                if grab is None:
                    root.after(20, look)
                    return
                found = [w for w in self.walk(grab) if w.winfo_class() == 'TButton']
                seen.extend(w.cget('text') for w in found)
                found[1].invoke()
            window.update_news.update(software=software, base=base)
            root.after(20, look)
            results[name] = (window.update_choice_dialog(software, base), seen)
            self.assertEqual(results[name][1], expected_labels, name)
        self.assertEqual(results['both'][0], 'both')
        self.assertEqual(results['base'][0], 'base')

    @staticmethod
    def dialog(root):
        return next((w for w in root.winfo_children() if isinstance(w, tk.Toplevel)), None)

    @staticmethod
    def walk(widget):
        for child in widget.winfo_children():
            yield child
            yield from RealWindowTests.walk(child)

    def test_the_dialog_answers_none_when_closed_or_later(self):
        root, window = self.open({})
        window.update_news.update(software=UPDATE, base=NEWER_BASE)
        def close():
            grab = self.dialog(root)
            if grab is None:
                root.after(20, close)
            else:
                grab.destroy()
        root.after(20, close)
        self.assertIsNone(window.update_choice_dialog(UPDATE, NEWER_BASE))

    def test_the_startup_look_is_scheduled_only_by_launch(self):
        root, window = self.open({})
        with patch('threading.Thread') as thread:
            root.update()
            time.sleep(0.05)
            root.update()
        thread.assert_not_called()          # building the window starts no look by itself


if __name__ == '__main__':
    unittest.main()
