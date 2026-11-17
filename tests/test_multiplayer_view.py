"""The Multiplayer window (retrorecomp/multiplayer_view.py) driven in a withdrawn Tk window: no socket, no worker process, a
stand-in controller that records the calls and a real `LobbyModel` fed with the room's events."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp.i18n import tr
from retrorecomp.netplay import invitation
from retrorecomp.netplay.lobby_client import LobbyModel

SECRET = bytes(range(16))
INVITE = invitation.format_invitation('192.168.1.20', invitation.DEFAULT_PORT, SECRET)


class Controller:
    """What the window calls on a `LobbyController`, recorded; the model is the real one."""
    made = []

    def __init__(self, library):
        self.library, self.model, self.calls, self.worker = library, LobbyModel(), [], None
        Controller.made.append(self)

    def on_event(self, event):
        self.model.apply(event)

    def pick(self, entry, game_options=''):
        self.calls.append(('pick', entry.title))
        return ''

    def say(self, text):
        self.calls.append(('say', text))

    def ready(self, ready):
        self.calls.append(('ready', ready))

    def move(self, guest, seat):
        self.calls.append(('move', guest, seat))

    def set_sharing(self, mode):
        self.calls.append(('sharing', mode))

    def launch(self, settings=None, need_ready=False):
        self.calls.append(('launch', need_ready))
        return ''

    def link(self):
        with self.model.lock:
            line = dict(self.model.link) if self.model.link else None
        if line is not None:
            line['delay'] = self.delay
        return line

    delay = None


class Library:
    def __init__(self, entries):
        self.entries = entries

    def hostable(self):
        return [(entry, SimpleNamespace(title=entry.title, machine=entry.system)) for entry in self.entries]


def entry(title, system='nes'):
    return SimpleNamespace(title=title, system=system, executable=f'C:/games/{title}.exe')


class MultiplayerWindowTest(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.started, self.closed = [], []
        Controller.made.clear()

    def tearDown(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def window(self, games=('Contra', 'Bomberman II'), language='fr'):
        from retrorecomp.multiplayer_view import MultiplayerWindow
        app = SimpleNamespace(tr=lambda key, **values: tr(key, language, **values), ui_font='Segoe UI', app=self.root,
                              language=language)

        def host_config(address, port, name, sharing, log_dir):
            return {'room': {'role': 'host', 'address': address, 'port': port, 'name': name, 'sharing': sharing}}, INVITE

        def guest_config(text, name, log_dir):
            invitation.parse(text)
            return {'room': {'role': 'guest', 'invitation': text, 'name': name}}

        configs = (host_config, guest_config, lambda controller, config, log=None: self.started.append(config),
                   lambda controller: self.closed.append(controller))
        view = MultiplayerWindow(app, Library([entry(title) for title in games]), name='Arthur', configs=configs,
                                 controller_class=Controller, addresses=lambda: ['192.168.1.20'], hidden=True)
        self.addCleanup(lambda: view.close())
        self.settle(view)
        return view

    def settle(self, view):
        """Let the games' thread answer and the window take the model's changes (its poll, called by hand)."""
        import time
        deadline = time.monotonic() + 10
        while not view.loaded and time.monotonic() < deadline:
            view.poll()
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertTrue(view.loaded)

    def feed(self, view, *events):
        for event in events:
            view.controller.on_event(event)
        view.poll()
        self.root.update()

    @staticmethod
    def roster(players, me=None, phase='lobby', sharing='per_player'):
        return {'event': 'lobby_roster', 'revision': 1, 'phase': phase, 'seats_max': 2, 'sharing': sharing, 'selection': 1,
                'players': players, 'me': me}

    def test_host_opens_a_room_picks_and_launches_when_every_guest_is_ready(self):
        view = self.window()
        view.show('host')
        self.assertEqual(view.game_choice.get(), view.game_label(view.games[0][0]))      # sorted: Bomberman II first
        self.assertEqual(view.address.get(), '192.168.1.20')
        view.open_room()
        self.assertEqual(self.started[0]['room']['name'], 'Arthur')
        self.assertEqual(self.started[0]['room']['port'], invitation.DEFAULT_PORT)
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611})
        self.assertEqual(view.current, 'lobby')
        self.assertIn(('pick', 'Bomberman II'), view.controller.calls)
        self.assertEqual(view.invite_shown.get(), INVITE)
        game = {'title': 'Bomberman II', 'machine': 'nes'}
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        guest = {'seat': 1, 'guest': 1, 'name': 'Karl', 'ready': False, 'in_match': False, 'check': 'same'}
        self.feed(view, {'event': 'lobby_selection', 'selection': 1, 'game': game}, self.roster([host, guest]))
        rows = [view.seat_table.item(row, 'values') for row in view.seat_table.get_children()]
        self.assertEqual([row[0] for row in rows], ['P1', 'P2'])
        self.assertEqual(rows[1][3], tr('mp_check_same', 'fr'))
        self.assertTrue(view.launch_button.instate(['disabled']))
        self.assertEqual(view.launch_hint.cget('text'), tr('mp_launch_wait_ready', 'fr'))
        self.feed(view, self.roster([host, dict(guest, ready=True)]))
        self.assertFalse(view.launch_button.instate(['disabled']))
        view.launch()
        self.assertIn(('launch', True), view.controller.calls)
        # the match: the banner, then how it ended
        self.feed(view, self.roster([dict(host, in_match=True), dict(guest, in_match=True)], phase='playing'))
        self.assertEqual(view.banner.cget('text'), tr('mp_match_running', 'fr'))
        self.feed(view, {'event': 'lobby_back', 'match_id': 1, 'reason': 'desync'}, self.roster([host, guest]))
        self.assertEqual(view.banner.cget('text'), tr('mp_back_desync', 'fr'))

    def test_other_version_names_what_differs(self):
        view = self.window()
        view.show('host')
        view.open_room()
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        guest = {'seat': 1, 'guest': 1, 'name': 'Karl', 'ready': False, 'in_match': False, 'check': 'other'}
        from retrorecomp.netplay import lobby_check
        bits = next(bit for bit, name in lobby_check.REASONS.items() if name == 'engine')
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611},
                  {'event': 'lobby_selection', 'selection': 1, 'game': {'title': 'Contra', 'machine': 'nes'}},
                  {'event': 'lobby_check', 'guest': 1, 'selection': 1, 'status': 1, 'reasons': bits}, self.roster([host, guest]))
        row = view.seat_table.item(view.seat_table.get_children()[1], 'values')
        self.assertEqual(row[3], tr('mp_check_other', 'fr', parts=tr('mp_reason_engine', 'fr')))
        self.assertEqual(view.launch_hint.cget('text'), tr('mp_launch_wait_guest', 'fr'))

    def test_guest_pastes_an_invitation_joins_and_is_told_when_the_host_closes(self):
        view = self.window()
        view.show('join')
        view.invite.set(INVITE)
        self.assertEqual((view.join_address.get(), view.join_port.get()), ('192.168.1.20', str(invitation.DEFAULT_PORT)))
        self.assertEqual(invitation.decode_secret(view.join_code.get()), SECRET)
        view.join_port.set('24612')                     # the fields stay editable: the invitation follows them
        view.join_room()
        self.assertIn(':24612:', self.started[0]['room']['invitation'])
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        me = {'seat': 1, 'guest': 2, 'name': 'Karl', 'ready': False, 'in_match': False, 'check': 'same'}
        self.feed(view, {'event': 'joined_room', 'guest': 2}, self.roster([host, me], me=2),
                  {'event': 'lobby_selection', 'selection': 1, 'game': {'title': 'Contra', 'machine': 'nes'}})
        self.assertEqual(view.current, 'lobby')
        self.assertEqual(view.room_line.cget('text'), tr('mp_room_joined', 'fr', host='Arthur'))
        self.assertEqual(view.lobby_game_text.cget('text'), 'Contra')
        # the big Ready button: gold « I'm ready », then green « Ready! » at once; a second click takes it back
        self.assertTrue(view.ready_row.winfo_manager())
        self.assertFalse(view.ready_button.instate(['disabled']))
        self.assertEqual(view.ready_button.cget('text'), tr('mp_ready_go', 'fr'))
        self.assertEqual(view.ready_hint.cget('text'), tr('mp_ready_note', 'fr'))
        view.ready_button.invoke()
        self.assertEqual(view.controller.calls[-1], ('ready', True))
        self.assertEqual((view.ready_button.cget('text'), str(view.ready_button.cget('style'))),
                         (tr('mp_ready_on', 'fr'), 'MultiplayerReadyOn.TButton'))
        self.feed(view, self.roster([host, dict(me, ready=True)], me=2))
        self.assertEqual(view.ready_hint.cget('text'), tr('mp_ready_cancel_note', 'fr'))
        view.ready_button.invoke()
        self.assertEqual(view.controller.calls[-1], ('ready', False))
        self.assertEqual(view.ready_button.cget('text'), tr('mp_ready_go', 'fr'))
        # another version of the game: greyed, and the line says why
        calls = len(view.controller.calls)
        self.feed(view, self.roster([host, dict(me, check='other')], me=2))
        self.assertTrue(view.ready_button.instate(['disabled']))
        self.assertEqual(view.ready_hint.cget('text'), tr('mp_ready_blocked', 'fr'))
        view.ready_button.invoke()
        self.assertEqual(len(view.controller.calls), calls)
        self.feed(view, {'event': 'host_gone', 'detail': 'the host closed the room', 'code': 'closed'})
        self.assertEqual(view.current, 'join')
        self.assertEqual(view.join_status.cget('text'), tr('mp_host_closed_room', 'fr'))
        self.assertEqual(len(self.closed), 1)
        self.assertIsNone(view.role)

    def test_a_host_gone_silent_and_a_join_with_no_answer_are_said_in_the_language(self):
        view = self.window()
        view.show('join')
        view.invite.set(INVITE)
        view.join_room()
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        self.feed(view, {'event': 'joined_room', 'guest': 1}, self.roster([host], me=1))
        self.feed(view, {'event': 'host_gone', 'detail': 'host silent for ten seconds', 'code': 'timeout'})
        self.assertEqual(view.join_status.cget('text'), tr('mp_room_lost', 'fr', detail=tr('mp_error_timeout', 'fr')))
        self.assertFalse(view.firewall_row.winfo_manager())          # it was in the room: not a firewall question
        view.join_room()
        self.feed(view, {'event': 'room_error', 'detail': 'no answer', 'code': 'unreachable'})
        self.assertEqual(view.join_status.cget('text'), tr('mp_join_failed', 'fr', detail=tr('mp_error_unreachable', 'fr')))
        self.assertTrue(view.firewall_row.winfo_manager())

    def test_the_invitation_shown_is_the_rooms_and_the_link_line_follows_the_match(self):
        view = self.window()
        view.show('host')
        view.open_room()
        bound = invitation.format_invitation('192.168.1.20', 24612, SECRET)
        view.controller.model.secret = SECRET
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24612})
        self.assertEqual(view.invite_shown.get(), bound)          # the port the room really bound
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_unknown', 'fr'))
        self.feed(view, {'event': 'launching', 'match_id': 1, 'tier': 'delay', 'prediction': 0})
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_unknown', 'fr'))
        view.controller.delay = 3                                  # the driver chose it: no event, the poll reads it
        view.poll()
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_delay', 'fr', frames=3))
        self.feed(view, {'event': 'slow_link', 'delay': 9})
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_slow', 'fr', frames=9))
        self.feed(view, {'event': 'launch_failed', 'detail': 'seat 2 did not start'})
        self.assertIn(tr('mp_errnote_launch_failed', 'fr'), view.chat_text.get('1.0', 'end'))

    def test_a_phrase_is_shown_in_the_windows_language(self):
        view = self.window(language='fr')
        view.show('host')
        view.open_room()
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611},
                  {'event': 'lobby_chat', 'sender': 1, 'name': 'Karl', 'text': 'Again?', 'phrase': 3})
        self.assertIn('Karl : On rejoue ?', view.chat_text.get('1.0', 'end'))

    def test_a_bad_invitation_is_said_and_nothing_starts(self):
        view = self.window()
        view.show('join')
        view.invite.set('rr1:lan:not-an-invitation')
        self.assertEqual(view.join_status.cget('text'), tr('mp_bad_invitation', 'fr'))
        view.join_room()
        self.assertEqual(self.started, [])

    def test_chat_lines_notices_and_the_80_character_limit(self):
        view = self.window()
        view.show('host')
        view.open_room()
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611},
                  {'event': 'lobby_chat', 'sender': 1, 'name': 'Karl', 'text': 'Salut !'},
                  {'event': 'lobby_notice', 'code': 'chat_too_fast'})
        shown = view.chat_text.get('1.0', 'end')
        self.assertIn('Karl : Salut !', shown)
        self.assertIn(tr('mp_notice_chat_too_fast', 'fr'), shown)
        view.chat_entry.set('x' * 100)
        self.assertEqual(len(view.chat_entry.get()), 80)
        view.chat_entry.set('  On   y va  ')
        view.send_chat()
        self.assertIn(('say', 'On y va'), view.controller.calls)
        self.assertEqual(view.chat_entry.get(), '')

    def test_closing_with_a_room_open_asks_first(self):
        view = self.window()
        view.show('host')
        view.open_room()
        with patch('retrorecomp.multiplayer_view.messagebox.askyesno', return_value=False) as asked:
            self.assertFalse(view.ask_close())
        asked.assert_called_once()
        self.assertEqual(self.closed, [])
        with patch('retrorecomp.multiplayer_view.messagebox.askyesno', return_value=True):
            self.assertTrue(view.ask_close())
        self.assertEqual(len(self.closed), 1)

    def test_no_game_to_host(self):
        view = self.window(games=())
        self.assertEqual(view.game_choice.get(), tr('mp_games_none', 'fr'))
        self.assertTrue(view.open_button.instate(['disabled']))

    def test_every_language_builds_the_pages(self):
        for language in ('en', 'fr', 'it', 'es', 'de', 'ja', 'zh', 'ru'):
            with self.subTest(language=language):
                view = self.window(language=language)
                for page in ('entry', 'host', 'join', 'lobby'):
                    view.show(page)
                    self.root.update()
                view.close()


if __name__ == '__main__':
    unittest.main()
