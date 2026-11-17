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
        app = SimpleNamespace(tr=lambda key, **values: tr(key, language, **values), ui_font='Segoe UI', app=self.root)

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
        self.assertFalse(view.ready_box.instate(['disabled']))
        view.ready.set(True)
        view.ready_box.invoke()
        self.assertIn(('ready', False), view.controller.calls)       # invoke toggles: the call follows the box
        self.feed(view, {'event': 'host_gone', 'detail': 'the host closed the room'})
        self.assertEqual(view.current, 'join')
        self.assertEqual(view.join_status.cget('text'), tr('mp_host_closed_room', 'fr'))
        self.assertEqual(len(self.closed), 1)
        self.assertIsNone(view.role)

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
