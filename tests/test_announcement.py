"""Arthur's message to every player (announcement.py) and the log panel's welcome (gui_welcome.py).

The site is never reached: a fake service on this computer answers, and the welcome is driven in a withdrawn window
(nothing is ever shown on screen)."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from retrorecomp import announcement, online
from retrorecomp.i18n import tr


class QuietServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        pass    # a client that gave up (the timeout test) is not an error here


class FakeAnnouncement(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        server = self.server
        server.requests.append({'path': self.path, 'headers': dict(self.headers)})
        mode = server.mode
        if mode == 'slow':
            time.sleep(1.0)
        if mode in ('204', '404'):
            self.send_response(int(mode))
            self.end_headers()
            if mode == '404':
                self.wfile.write(b'{"error":"not_found"}')
            return
        body = server.body if mode != 'bad' else b'{"active": true, "messages": '
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def answer(active=True, **messages):
    return {'active': active, 'messages': messages, 'updated_utc': '2026-11-16T15:00:00Z'}


class Rules(unittest.TestCase):
    def test_the_players_language_then_english(self):
        both = answer(fr='Bonjour à tous', en='Hello everyone')
        self.assertEqual(announcement.pick(both, 'fr'), 'Bonjour à tous')
        self.assertEqual(announcement.pick(both, 'fr-FR'), 'Bonjour à tous')
        self.assertEqual(announcement.pick(both, 'en'), 'Hello everyone')
        # A language the site did not write (or wrote empty) reads English; nothing when English is missing too.
        self.assertEqual(announcement.pick(both, 'de'), 'Hello everyone')
        self.assertEqual(announcement.pick(answer(fr='  \n ', en='Hello'), 'fr'), 'Hello')
        self.assertEqual(announcement.pick(answer(fr='Bonjour'), 'ja'), '')
        self.assertEqual(announcement.pick(answer(fr='Bonjour'), 'fr'), 'Bonjour')

    def test_inactive_empty_or_invalid_answers_show_nothing(self):
        for value in (answer(False, fr='Bonjour', en='Hello'), answer(en=''), answer(), {'active': 'true', 'messages': {'en': 'x'}},
                      {'active': 1, 'messages': {'en': 'x'}}, {'active': True, 'messages': ['x']},
                      {'active': True, 'messages': {'en': 42}}, {'active': True}, None, [], 'Hello'):
            self.assertEqual(announcement.pick(value, 'en'), '', value)

    def test_plain_text_only_cut_at_the_limit(self):
        self.assertEqual(announcement.LIMIT, 200)
        self.assertEqual(announcement.clean('a' * 260), 'a' * 200)
        self.assertEqual(len(announcement.pick(answer(en='é' * 300), 'en')), 200)
        # Line breaks and tabs are spaces; controls, escapes, bidirectional overrides and zero-width marks are left out.
        self.assertEqual(announcement.clean('One\nTwo\r\n\tThree'), 'One Two Three')
        self.assertEqual(announcement.clean('Bell\x07\x1b[31mred\x1b[0m'), 'Bell[31mred[0m')
        self.assertEqual(announcement.clean('abc‮dcba​!'), 'abcdcba!')
        self.assertEqual(announcement.clean('\x00\x7f\x9b'), '')
        # Characters Tk 8.6 cannot draw everywhere (outside the Basic Multilingual Plane) are left out.
        self.assertEqual(announcement.clean('New \U0001F389 release'), 'New release')
        # Markup and links stay text: nothing is interpreted, the characters are shown as they are.
        self.assertEqual(announcement.clean('<b>1.7.9</b> https://example.test'), '<b>1.7.9</b> https://example.test')
        # A no-break space (French typography) is kept.
        self.assertEqual(announcement.clean('Bonjour !'), 'Bonjour !')
        for value in (None, 12, b'bytes', ['x']):
            self.assertEqual(announcement.clean(value), '')


class FakeService(unittest.TestCase):
    def setUp(self):
        self.server = QuietServer(('127.0.0.1', 0), FakeAnnouncement)
        self.server.requests, self.server.mode = [], 'ok'
        self.server.body = json.dumps(answer(fr='Bonjour', en='Hello')).encode('utf-8')
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        url = f'http://127.0.0.1:{self.server.server_address[1]}'
        service = patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': url})
        service.start()
        self.addCleanup(service.stop)

    def test_a_plain_get_with_nothing_about_the_player(self):
        self.assertEqual(announcement.fetch('fr'), 'Bonjour')
        self.assertEqual(announcement.fetch('it'), 'Hello')
        request = self.server.requests[0]
        self.assertEqual(request['path'], '/api/v1/announcement')    # no query
        headers = {name.lower(): value for name, value in request['headers'].items()}
        self.assertNotIn('authorization', headers)
        self.assertNotIn('cookie', headers)
        self.assertTrue(headers['user-agent'].startswith('RetroRecomp/'))

    def test_inactive_204_404_and_a_bad_answer_show_nothing(self):
        self.server.body = json.dumps(answer(False, fr='Bonjour', en='Hello')).encode('utf-8')
        self.assertEqual(announcement.fetch('fr'), '')
        for mode in ('204', '404', 'bad'):
            self.server.mode = mode
            self.assertIsNone(announcement.fetch_answer(), mode)
            self.assertEqual(announcement.fetch('fr'), '', mode)
        self.server.mode, self.server.body = 'ok', b'[1, 2]'
        self.assertEqual(announcement.fetch('fr'), '')
        self.server.body = b'x' * (online.ANNOUNCEMENT_BYTES + 10)
        self.assertEqual(announcement.fetch('fr'), '')

    def test_a_timeout_shows_nothing_and_returns_soon(self):
        self.server.mode = 'slow'
        started = time.monotonic()
        self.assertIsNone(announcement.fetch_answer(timeout=0.3))
        self.assertLess(time.monotonic() - started, 0.9)

    def test_an_answer_later_than_the_timeout_is_left_out(self):
        def late(timeout):
            time.sleep(0.25)
            return answer(en='Hello')
        with patch.object(online, 'announcement', late):
            self.assertIsNone(announcement.fetch_answer(timeout=0.1))
            self.assertEqual(announcement.fetch_answer(timeout=2)['messages']['en'], 'Hello')

    def test_no_service_no_request_and_no_network_nothing(self):
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': ''}):
            self.assertIsNone(announcement.fetch_answer())
        self.assertEqual(self.server.requests, [])
        # A local port nobody listens on: offline.
        closed = ThreadingHTTPServer(('127.0.0.1', 0), FakeAnnouncement)
        port = closed.server_address[1]
        closed.server_close()
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': f'http://127.0.0.1:{port}'}):
            self.assertIsNone(announcement.fetch_answer(timeout=2))


class Welcome(unittest.TestCase):
    """The welcome in a real Tk Text widget of a withdrawn window; the panel is said to be on screen by a patch."""

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.addCleanup(self.close)
        from retrorecomp.gui_welcome import WelcomeMixin
        root = self.root

        class Panel(WelcomeMixin):
            def __init__(self):
                import queue
                self.app, self.language, self.ui_font, self.platform_id = root, 'fr', 'TkDefaultFont', None
                self.messages = queue.Queue()
                self.log = tk.Text(root, font=('Consolas', 9), state='disabled', wrap='word')
                self.log.pack()
                self.check_at_startup = tk.BooleanVar(master=root, value=True)

            def tr(self, key, **values):
                return tr(key, self.language, **values)

        from retrorecomp import gui_welcome
        platforms = patch.dict(gui_welcome.PLATFORMS, {None: 'Test version'})
        platforms.start()
        self.addCleanup(platforms.stop)
        self.panel = Panel()
        self.visible = False
        self.panel.log.winfo_viewable = lambda: self.visible
        self.panel.start_welcome()

    def close(self):
        # Each waiting step is cancelled by the widget that holds its command (as in test_dropfiles).
        def widgets(parent):
            yield parent
            for child in parent.winfo_children():
                yield from widgets(child)
        owners = {name: widget for widget in widgets(self.root) for name in (widget._tclCommands or [])}
        for job in self.root.tk.call('after', 'info'):
            owners.get(self.root.tk.call('after', 'info', job)[0], self.root).after_cancel(job)
        self.root.destroy()

    def text(self):
        return self.panel.log.get('1.0', 'end-1c')

    def run_for(self, seconds, until=lambda: False):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not until():
            self.root.update()
            time.sleep(0.005)

    def test_the_logo_is_six_rows_of_plain_ascii(self):
        from retrorecomp.gui_welcome import WELCOME_LOGO
        self.assertEqual(len(WELCOME_LOGO), 6)
        self.assertEqual(len({len(row) for row in WELCOME_LOGO}), 1)
        self.assertTrue(all(row.isascii() and row.isprintable() for row in WELCOME_LOGO))

    def test_it_waits_for_the_panel_then_plays_in_about_two_seconds(self):
        self.root.update()
        self.assertEqual(self.panel.welcome['state'], 'waiting')
        self.assertEqual(self.text(), '')
        self.visible = True
        started = time.monotonic()
        self.panel.welcome_mapped()
        self.assertEqual(self.panel.welcome['state'], 'typing')
        self.run_for(1.0)
        self.assertNotEqual(self.panel.welcome['state'], 'typing')   # the logo is typed in under a second
        self.run_for(4, lambda: self.panel.welcome['state'] == 'still')
        self.assertEqual(self.panel.welcome['state'], 'still')
        self.assertLess(time.monotonic() - started, 2.0)            # about 1.5 s before a message
        lines = self.text().split('\n')
        from retrorecomp.gui_welcome import WELCOME_LOGO
        self.assertEqual(lines[:6], list(WELCOME_LOGO))
        self.assertIn(tr('ready', 'fr'), lines[6])
        self.assertIn('Test version', lines[6])
        self.assertEqual(self.panel.log.tag_ranges('welcome_hidden'), ())
        # The cursor blinks, one Tk step at a time.
        self.assertIsNotNone(self.panel.welcome['job'])

    def test_a_message_arriving_late_is_typed_in_under_the_subtitle(self):
        self.visible = True
        self.panel.welcome_mapped()
        self.run_for(4, lambda: self.panel.welcome['state'] == 'still')
        self.panel.welcome_announcement(answer(fr='Bonjour à toutes et à tous !', en='Hello all!'))
        self.assertEqual(self.panel.welcome['state'], 'message')
        self.run_for(4, lambda: self.panel.welcome['state'] == 'still')
        last = self.text().split('\n')[-1]
        self.assertEqual(last, tr('welcome_from_arthur', 'fr') + ' Bonjour à toutes et à tous ! ')

    def test_a_message_known_early_is_typed_after_the_subtitle(self):
        self.panel.welcome_announcement(answer(fr='', en='Hello all!'))
        self.visible = True
        self.panel.welcome_mapped()
        self.run_for(6, lambda: self.panel.welcome['state'] == 'still')
        self.assertTrue(self.text().endswith(tr('welcome_from_arthur', 'fr') + ' Hello all! '))

    def test_hidden_it_jumps_to_the_last_picture_and_stops(self):
        self.visible = True
        self.panel.welcome_announcement(answer(en='Hello all!'))
        self.panel.welcome_mapped()
        self.run_for(0.2)
        self.visible = False
        self.run_for(0.2)
        self.assertEqual(self.panel.welcome['state'], 'still')
        self.assertIsNone(self.panel.welcome['job'])        # nothing left waiting while hidden
        self.assertTrue(self.text().endswith(tr('welcome_from_arthur', 'fr') + ' Hello all! '))
        self.visible = True
        self.panel.welcome_mapped()                          # shown again: only the cursor blinks
        self.assertIsNotNone(self.panel.welcome['job'])

    def test_the_first_real_line_clears_it_for_good(self):
        self.visible = True
        self.panel.welcome_mapped()
        self.run_for(0.3)
        self.panel.end_welcome()
        self.assertEqual(self.panel.welcome['state'], 'gone')
        self.assertIsNone(self.panel.welcome['job'])
        self.assertEqual(self.text(), '')
        # Nothing comes back: a late message, the panel shown again, a language change.
        self.panel.welcome_announcement(answer(en='Hello'))
        self.panel.welcome_mapped()
        self.panel.welcome_language()
        self.run_for(0.3)
        self.assertEqual(self.text(), '')

    def test_never_shown_it_leaves_nothing_behind(self):
        self.panel.welcome_announcement(answer(en='Hello'))
        self.panel.end_welcome()
        self.assertEqual(self.text(), '')
        self.assertEqual(self.panel.welcome['state'], 'gone')

    def test_a_language_change_writes_it_again_at_once(self):
        self.panel.welcome_announcement(answer(fr='Bonjour', en='Hello'))
        self.visible = True
        self.panel.welcome_mapped()
        self.run_for(0.3)
        self.panel.language = 'de'
        self.panel.welcome_language()
        self.assertEqual(self.panel.welcome['state'], 'still')
        self.assertIn(tr('ready', 'de'), self.text())
        self.assertTrue(self.text().endswith(tr('welcome_from_arthur', 'de') + ' Hello '))

    def test_the_request_follows_the_start_up_look_and_the_service(self):
        with patch.object(announcement, 'fetch_answer', return_value=answer(en='Hello')) as fetch, \
                patch.object(online, 'service_url', return_value='https://example.test'):
            self.panel.check_at_startup.set(False)
            self.panel.fetch_announcement()
            self.assertFalse(fetch.called)
            self.panel.check_at_startup.set(True)
            self.panel.fetch_announcement()
            deadline = time.monotonic() + 5
            while self.panel.messages.empty() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(self.panel.messages.get_nowait(), ('announcement', answer(en='Hello')))
        with patch.object(announcement, 'fetch_answer') as fetch, patch.object(online, 'service_url', return_value=''):
            self.panel.fetch_announcement()
            self.assertFalse(fetch.called)


if __name__ == '__main__':
    unittest.main()
