"""The Multiplayer window (retrorecomp/multiplayer_view.py) driven in a withdrawn Tk window: no socket, no worker process, a
stand-in controller that records the calls and a real `LobbyModel` fed with the room's events."""
import tkinter as tk
from tkinter import ttk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp.i18n import tr
from retrorecomp.netplay import invitation
from retrorecomp.netplay.lobby_client import LobbyModel

SECRET = bytes(range(16))
INVITE = invitation.format_invitation('192.168.1.20', invitation.DEFAULT_PORT, SECRET)
KEY = 'RR2-7H3QK-M9XPA-2ZD4R-V8N1C-QF6TW-K0BHS-E5MJY-4RXGT-9C'      # a stand-in Internet key (its format is the room's)
CODE = '7H3QK-M9XPA-2ZD4R-V8N1C-QF6TWK-0'


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

    def window(self, games=('Contra', 'Bomberman II'), language='fr', internet=False, guest_manual=None):
        from retrorecomp.multiplayer_view import MultiplayerWindow
        app = SimpleNamespace(tr=lambda key, **values: tr(key, language, **values), ui_font='Segoe UI', app=self.root,
                              language=language)

        def host_config(address, port, name, sharing, log_dir, **internet_fields):
            return {'room': {'role': 'host', 'address': address, 'port': port, 'name': name, 'sharing': sharing,
                             **internet_fields}}, KEY if internet_fields.get('internet') else INVITE

        def guest_config(text, name, log_dir):
            if text.startswith('RR2'):
                if text != KEY:
                    error = invitation.InvitationError('typo')
                    error.code = 'typo'
                    raise error
            else:
                invitation.parse(text)
            return {'room': {'role': 'guest', 'invitation': text, 'name': name}}

        configs = (host_config, guest_config, lambda controller, config, log=None: self.started.append(config),
                   lambda controller: self.closed.append(controller))
        view = MultiplayerWindow(app, Library([entry(*title) if isinstance(title, tuple) else entry(title) for title in games]), name='Arthur', configs=configs,
                                 controller_class=Controller, addresses=lambda: ['192.168.1.20'], hidden=True,
                                 internet=internet, guest_manual=guest_manual)
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
        rows = view.seat_values()
        self.assertEqual([row[0] for row in rows], ['P1', 'P2'])
        self.assertEqual(rows[1][3], tr('mp_check_same', 'fr'))
        # the round button: grey while Karl is not ready (a press does nothing), gold Launch once he is
        self.assertFalse(view.action.pressable)
        self.assertEqual(view.action.texts()[1], tr('mp_wait_for', 'fr', names='Karl'))
        view.action.press()
        self.assertNotIn(('launch', True), view.controller.calls)
        self.feed(view, self.roster([host, dict(guest, ready=True)]))
        self.assertTrue(view.action.pressable)
        self.assertEqual(view.action.texts(), (tr('mp_launch', 'fr').upper(), tr('mp_go_note', 'fr')))
        view.action.event_generate('<Return>')          # the keyboard (and the gamepad's focus) press it too
        view.action.focus_force()
        view.action.press()
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
        row = view.seat_values()[1]
        self.assertEqual(row[3], tr('mp_check_other', 'fr', parts=tr('mp_reason_engine', 'fr')))
        self.assertEqual(view.action.texts()[1], tr('mp_launch_wait_guest', 'fr'))

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
        # the round Ready button: gold « I'm ready », then green « Ready! » at once; a second press takes it back
        self.assertEqual((view.action.state_['look'], view.action.texts()),
                         ('gold', (tr('mp_ready_go', 'fr').upper(), tr('mp_ready_note', 'fr'))))
        self.assertEqual(view.launch_hint.cget('text'), tr('mp_wait_host', 'fr'))
        view.action.press()
        self.assertEqual(view.controller.calls[-1], ('ready', True))
        self.assertEqual((view.action.state_['look'], view.action.texts()[0]), ('green', tr('mp_ready_on', 'fr').upper()))
        self.feed(view, self.roster([host, dict(me, ready=True)], me=2))
        self.assertEqual(view.action.texts()[1], tr('mp_ready_cancel_note', 'fr'))
        view.action.press()
        self.assertEqual(view.controller.calls[-1], ('ready', False))
        self.assertEqual(view.action.state_['look'], 'gold')
        # another version of the game: blocked, and the caption says why; a press does nothing
        calls = len(view.controller.calls)
        self.feed(view, self.roster([host, dict(me, check='other')], me=2))
        self.assertEqual((view.action.state_['look'], view.action.texts()),
                         ('refused', (tr('mp_blocked', 'fr'), tr('mp_ready_blocked', 'fr'))))
        view.action.press()
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
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_unknown', 'fr') + ' · ' + tr('mp_path_lan', 'fr'))
        self.feed(view, {'event': 'launching', 'match_id': 1, 'tier': 'delay', 'prediction': 0})
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_unknown', 'fr') + ' · ' + tr('mp_path_lan', 'fr'))
        view.controller.delay = 3                                  # the driver chose it: no event, the poll reads it
        view.poll()
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_delay', 'fr', frames=3) + ' · ' + tr('mp_path_lan', 'fr'))
        self.feed(view, {'event': 'slow_link', 'delay': 9})
        self.assertEqual(view.link_line.cget('text'), tr('mp_link_slow', 'fr', frames=9) + ' · ' + tr('mp_path_lan', 'fr'))
        self.feed(view, {'event': 'launch_failed', 'detail': 'seat 2 did not start'})
        self.assertIn(tr('mp_errnote_launch_failed', 'fr'), view.chat_text.get('1.0', 'end'))

    def test_a_game_that_refused_a_host_setting_says_what_to_change(self):
        view = self.window()
        view.show('join')
        view.invite.set(INVITE)
        view.join_room()
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        me = {'seat': 1, 'guest': 2, 'name': 'Karl', 'ready': True, 'in_match': False, 'check': 'same'}
        self.feed(view, {'event': 'joined_room', 'guest': 2}, self.roster([host, me], me=2),
                  {'event': 'match_over', 'match_id': 1, 'outcome': 'refused', 'detail': 'the game refused (1): system'},
                  {'event': 'lobby_back', 'match_id': 1, 'reason': 'error'})
        self.assertEqual(view.banner.cget('text'), tr('mp_refused_system', 'fr'))         # the Neo Geo's AES / MVS: F11
        self.assertEqual(view.chat_text.get('1.0', 'end').count(tr('mp_refused_system', 'fr')), 1)
        self.feed(view, self.roster([host, me], me=2))                                    # once per match, not per redraw
        self.assertEqual(view.chat_text.get('1.0', 'end').count(tr('mp_refused_system', 'fr')), 1)
        self.feed(view, {'event': 'launch_error', 'detail': 'the game refused (1): region'})
        self.assertIn(tr('mp_refused_setting', 'fr', setting='region'), view.chat_text.get('1.0', 'end'))
        self.assertIn('« region »', tr('mp_refused_setting', 'fr', setting='region'))
        # a later match that ended otherwise: the banner says that one
        self.feed(view, {'event': 'match_over', 'match_id': 2, 'outcome': 'ended', 'detail': ''},
                  {'event': 'lobby_back', 'match_id': 2, 'reason': 'ended'})
        self.assertEqual(view.banner.cget('text'), tr('mp_back_ended', 'fr'))

    def test_internet_needs_the_three_warnings_confirmed_and_is_local_again_at_every_opening(self):
        view = self.window(internet=True)
        self.assertEqual(view.mode.get(), 'local')
        self.assertFalse(view.warn_card.winfo_manager())
        view.mode.set('internet')
        self.root.update()
        self.assertTrue(view.warn_card.winfo_manager())
        self.assertTrue(all(button.instate(['disabled']) for button in view.choice_buttons))
        view.confirm_internet()
        self.assertFalse(view.warn_card.winfo_manager())
        self.assertFalse(any(button.instate(['disabled']) for button in view.choice_buttons))
        view.close()
        again = self.window(internet=True)
        self.assertEqual((again.mode.get(), again.internet_confirmed), ('local', False))

    def test_internet_is_offered_only_when_the_room_supports_it(self):
        view = self.window(internet=False)
        self.assertTrue(view.mode_buttons['internet'].instate(['disabled']))
        view.mode.set('internet')
        self.assertEqual(view.mode.get(), 'local')

    def test_the_internet_host_shows_its_key_how_it_is_reached_and_hides_the_code(self):
        view = self.window(internet=True)
        view.mode.set('internet')
        view.confirm_internet()
        view.show('host')
        view.typed_public.set('86.214.33.17')
        self.assertFalse(view.public_field.winfo_manager())               # a fallback, folded: found by itself
        view.toggle_public()
        self.assertTrue(view.public_field.winfo_manager())
        view.open_room()
        room = self.started[0]['room']
        self.assertEqual((room['internet'], room['public_address']), (True, '86.214.33.17'))
        model = view.controller.model
        model.key, model.code, model.public, model.reach = KEY, CODE, '86.214.33.17', 'site'
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611})
        self.assertEqual(view.invite_shown.get(), KEY)
        self.assertEqual(view.reach_line.cget('text'), tr('mp_reach_site', 'fr'))
        self.assertNotIn(CODE, view.detail_code.cget('text'))            # hidden like a password
        view.toggle_code()
        self.assertIn(CODE, view.detail_code.cget('text'))
        self.assertIn('86.214.33.17', view.detail_address.cget('text'))
        self.assertIn('86.214.33.17', view.public_line.cget('text'))
        model.reach = 'forward_needed'
        self.feed(view, {'event': 'lobby_notice', 'code': 'wrong_key_attempts'})
        self.assertEqual(view.reach_line.cget('text'), tr('mp_reach_forward', 'fr', port=24611))
        self.assertIn(tr('mp_notice_wrong_key_attempts', 'fr'), view.chat_text.get('1.0', 'end'))

    def test_the_internet_guest_joins_by_key_or_by_address_and_code(self):
        manual = []
        view = self.window(internet=True, guest_manual=lambda *values: manual.append(values) or {'room': {'role': 'guest'}})
        view.mode.set('internet')
        view.confirm_internet()
        view.show('join')
        view.invite.set(KEY[:-1] + 'X')
        view.join_room()
        self.assertEqual(view.join_status.cget('text'), tr('mp_error_key_typo', 'fr'))
        self.assertEqual(self.started, [])
        view.invite.set(KEY)
        view.join_room()
        self.assertEqual(self.started[-1]['room']['invitation'], KEY)
        view.leave_room()
        view.join_by.set('address')
        view.draw_join_form()
        view.join_address.set('86.214.33.17')
        view.join_port.set('24611')
        view.join_code.set(CODE)
        view.join_room()
        self.assertEqual(manual[0][:3], ('86.214.33.17', 24611, CODE))
        self.assertTrue(view.privacy_line.winfo_manager())

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

    def test_the_console_first_then_its_games_in_the_form_and_in_the_lobby(self):
        # Arthur, 19 Nov 2026: « on est censé pouvoir choisir la console. Ça évitera de lister tous les jeux »
        view = self.window(games=(('Tetris', 'gb'), ('Contra', 'nes'), ('Tetris', 'nes'), ('Sonic 2', 'md')))
        names = list(view.console_box.cget('values'))
        self.assertEqual(names, sorted(names, key=str.casefold))
        self.assertEqual(len(names), 3)                                     # one line per console that has a game
        nes = view.console_name('nes')
        view.console_choice.set(nes)
        view.console_box.event_generate('<<ComboboxSelected>>')
        self.assertEqual(list(view.game_box.cget('values')), ['Contra', 'Tetris'])
        self.assertEqual(view.game_choice.get(), 'Contra')                  # a console chosen shows its first game
        view.game_choice.set('Tetris')
        self.assertEqual((view.chosen_entry(view.game_choice).title, view.chosen_entry(view.game_choice).system),
                         ('Tetris', 'nes'))                                 # the Tetris of the console chosen
        view.open_room()
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611})
        self.assertEqual(view.controller.calls[-1], ('pick', 'Tetris'))
        self.feed(view, {'event': 'lobby_selection', 'selection': 1, 'game': {'title': 'Tetris', 'machine': 'nes'}})
        self.assertEqual((view.lobby_console.get(), view.lobby_game.get()), (nes, 'Tetris'))
        # the lobby: another console lists its games and leaves the room's game; a chat line does not undo the choice
        view.lobby_console.set(view.console_name('md'))
        view.lobby_console_box.event_generate('<<ComboboxSelected>>')
        self.assertEqual(list(view.lobby_game_box.cget('values')), ['Sonic 2'])
        self.assertEqual(view.lobby_game.get(), tr('mp_pick_game', 'fr'))
        self.assertEqual(view.controller.calls[-1], ('pick', 'Tetris'))
        self.feed(view, {'event': 'lobby_chat', 'sender': 0, 'name': 'Arthur', 'text': 'Salut'})
        self.assertEqual(view.lobby_console.get(), view.console_name('md'))
        view.lobby_game.set('Sonic 2')
        view.lobby_game_box.event_generate('<<ComboboxSelected>>')
        self.assertEqual(view.controller.calls[-1], ('pick', 'Sonic 2'))

    def test_paste_the_key_and_one_grid_with_examples_on_the_join_page(self):
        # Arthur, 19 Nov 2026: a Paste button; « le nom est décalé »; empty fields looked like blank cells
        view = self.window(internet=True)
        view.show('join')
        self.root.update()
        self.assertTrue(view.key_field.hint.winfo_manager() == 'place')                 # an example while it is empty
        self.root.clipboard_clear()
        self.root.clipboard_append('  ' + INVITE + '\n')
        view.paste_key()
        self.assertEqual(view.invite.get(), INVITE)
        self.assertEqual(view.join_address.get(), '192.168.1.20')          # an invitation fills the fields, as typed
        self.root.update()
        self.assertFalse(view.key_field.hint.winfo_manager() == 'place')
        self.root.clipboard_clear()
        view.paste_key()
        self.assertEqual(view.join_status.cget('text'), tr('mp_clipboard_empty', 'fr'))
        self.assertEqual(view.invite.get(), INVITE)
        view.join_by.set('address')
        view.draw_join_form()
        view.join_address.set('')
        self.root.update()
        labels = [label for number, (label, _widget) in sorted(view.join_rows.items()) if label.winfo_manager()]
        self.assertEqual([label.cget('text') for label in labels],
                         [tr(key, 'fr') for key in ('mp_host_address', 'mp_port', 'mp_code', 'mp_name')])
        self.assertEqual({int(label.grid_info()['column']) for label in labels}, {0})      # one column of labels
        self.assertEqual({int(view.join_rows[n][1].grid_info()['column']) for n in (1, 2, 3, 4)}, {1})  # and of fields
        self.assertEqual(view.join_address_field.hint.cget('text'), '192.168.1.20')
        self.assertTrue(view.join_address_field.hint.winfo_manager() == 'place')
        view.mode.set('internet')
        view.confirm_internet()
        self.assertEqual(view.join_address_field.hint.cget('text'), '203.0.113.7')

    def test_the_mode_chip_goes_back_to_the_choice_and_asks_with_a_room_open(self):
        view = self.window()
        view.show('host')
        self.assertTrue(view.change_mode())
        self.assertEqual(view.current, 'entry')
        view.show('host')
        view.open_room()
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611})
        self.assertEqual(view.current, 'lobby')
        with patch('retrorecomp.multiplayer_view.messagebox.askyesno', return_value=False) as asked:
            self.assertFalse(view.change_mode())
        asked.assert_called_once()
        self.assertEqual((view.current, self.closed), ('lobby', []))
        with patch('retrorecomp.multiplayer_view.messagebox.askyesno', return_value=True):
            self.assertTrue(view.change_mode())
        self.assertEqual((view.current, len(self.closed), view.role), ('entry', 1, None))

    def test_the_internet_lobby_says_the_address_found_or_not_and_offers_typing_only_then(self):
        view = self.window(internet=True)
        view.mode.set('internet')
        view.confirm_internet()
        view.show('host')
        view.open_room()
        model = view.controller.model
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611})
        model.set_public(None, 'probing')
        self.feed(view)
        self.assertIn(tr('mp_public_searching', 'fr'), view.public_line.cget('text'))
        self.assertFalse(view.manual_row.winfo_manager())
        model.set_public('86.214.33.17', 'upnp')
        self.feed(view)
        self.assertIn('86.214.33.17', view.public_line.cget('text'))
        self.assertFalse(view.manual_row.winfo_manager())                 # found: typing stays behind the fold
        self.assertTrue(view.manual_fold.winfo_manager())
        view.toggle_manual()
        self.assertTrue(view.manual_row.winfo_manager())
        view.toggle_manual()
        model.set_public(None, 'waiting')
        self.feed(view)
        self.assertIn(tr('mp_public_not_found', 'fr'), view.public_line.cget('text'))
        self.assertEqual(view.reach_line.cget('text'), tr('mp_reach_none', 'fr'))
        self.assertTrue(view.manual_row.winfo_manager())                  # not found: offered at once

    def test_the_hosts_control_choice_is_always_shown(self):
        view = self.window()
        view.show('host')
        view.open_room()
        guests = [{'seat': 1, 'guest': 1, 'name': 'Karl', 'ready': False, 'in_match': False, 'check': 'same'},
                  {'seat': 2, 'guest': 2, 'name': 'Léa', 'ready': False, 'in_match': False, 'check': 'same'}]
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611},
                  dict(self.roster([host] + guests), seats_max=4))
        self.assertTrue(view.mode_frame.winfo_manager())
        self.assertFalse(hasattr(view, 'more_link'))
        view.lobby_sharing_buttons['everyone'].invoke()
        self.assertEqual(view.controller.calls[-1], ('sharing', 'everyone'))
        moves = [w for row in view.seat_rows for w in row.winfo_children() for b in w.winfo_children()
                 if isinstance(b, ttk.Button)]
        self.assertEqual(len(moves), 4)                                   # two guests: up and down on each row

    def test_a_handheld_greys_one_controller_per_player_with_why(self):
        # Arthur, 19 Nov 2026: visible, greyed, « arrive avec le câble link, dans la prochaine version »
        view = self.window(games=(('Tetris', 'gb'), ('Contra', 'nes')))
        view.show('host')
        view.console_choice.set(view.console_name('gb'))
        view.console_box.event_generate('<<ComboboxSelected>>')
        self.assertTrue(view.sharing_buttons['per_player'].instate(['disabled']))
        self.assertTrue(view.sharing_note.winfo_manager())
        self.assertEqual(view.sharing.get(), 'everyone')
        self.assertEqual(view.sharing_note.cget('text'), tr('mp_sharing_handheld', 'fr'))
        view.console_choice.set(view.console_name('nes'))
        view.console_box.event_generate('<<ComboboxSelected>>')
        self.assertFalse(view.sharing_buttons['per_player'].instate(['disabled']))
        self.assertFalse(view.sharing_note.winfo_manager())
        # the lobby: a handheld picked with « per player » in the room moves it to « Everyone » once, greyed with why
        view.open_room()
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611},
                  {'event': 'lobby_selection', 'selection': 1, 'game': {'title': 'Tetris', 'machine': 'gb'}},
                  self.roster([host]))
        self.assertTrue(view.lobby_sharing_buttons['per_player'].instate(['disabled']))
        self.assertTrue(view.lobby_sharing_note.winfo_manager())
        self.assertEqual(view.controller.calls.count(('sharing', 'everyone')), 1)
        self.feed(view, {'event': 'lobby_chat', 'sender': 0, 'name': 'Arthur', 'text': 'Salut'})
        self.assertEqual(view.controller.calls.count(('sharing', 'everyone')), 1)

    def test_a_firewall_that_blocks_guests_is_said_to_the_host_while_it_lasts(self):
        view = self.window()
        view.show('host')
        view.open_room()
        self.feed(view, {'event': 'room_open', 'address': '192.168.1.20', 'port': 24611})
        self.assertFalse(view.firewall_host.winfo_manager())
        view.controller.model.set_firewall('blocked', 'no inbound rule')
        self.feed(view)
        self.assertTrue(view.firewall_host.winfo_manager())
        self.assertIn(tr('mp_notice_firewall_blocked', 'fr'), view.chat_text.get('1.0', 'end'))
        view.controller.model.set_firewall('open')
        self.feed(view)
        self.assertFalse(view.firewall_host.winfo_manager())

    def test_a_guest_ready_automatically_once_per_pick(self):
        remembered = []
        view = self.window()
        view.app.remember_multiplayer = lambda **values: remembered.append(values)
        view.show('join')
        view.invite.set(INVITE)
        view.join_room()
        host = {'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': False, 'in_match': False, 'check': 'none'}
        me = {'seat': 1, 'guest': 2, 'name': 'Karl', 'ready': False, 'in_match': False, 'check': 'same'}
        self.feed(view, {'event': 'joined_room', 'guest': 2}, self.roster([host, me], me=2),
                  {'event': 'lobby_selection', 'selection': 1, 'game': {'title': 'Contra', 'machine': 'nes'}})
        self.assertTrue(view.auto_ready_box.winfo_manager())
        self.assertNotIn(('ready', True), view.controller.calls)
        view.auto_ready.set(True)
        view.auto_ready_changed()
        self.assertEqual(remembered, [{'auto_ready': True}])
        self.feed(view)
        self.assertEqual(view.controller.calls.count(('ready', True)), 1)  # ticked with a pick this PC has: ready now
        self.feed(view, self.roster([host, dict(me, ready=True)], me=2))
        view.action.press()                                                # the player takes it back for this pick
        self.feed(view, self.roster([host, me], me=2))
        self.assertEqual(view.controller.calls.count(('ready', True)), 1)
        self.feed(view, {'event': 'lobby_selection', 'selection': 2, 'game': {'title': 'Contra', 'machine': 'nes'}},
                  dict(self.roster([host, dict(me, check='asking')], me=2), selection=2))
        self.assertEqual(view.controller.calls.count(('ready', True)), 1)  # not before this PC found the game
        self.feed(view, dict(self.roster([host, me], me=2), selection=2))
        self.assertEqual(view.controller.calls.count(('ready', True)), 2)  # a new pick: ready again by itself

    def test_no_game_to_host(self):
        view = self.window(games=())
        self.assertEqual(view.console_choice.get(), tr('mp_games_none', 'fr'))
        self.assertEqual(view.game_choice.get(), '')
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
