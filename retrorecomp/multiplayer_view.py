"""The converter's Multiplayer window (stage 3 of the network play, STAGE3_WINDOW.md section 1): host or join a room on the
local network, the lobby (seats, each player's check, the input mode, the chat), the launch, the match in progress and its end.

A `tk.Toplevel` of its own like the Credits, one at a time. Everything the room does goes through a `LobbyController` and
its worker (retrorecomp/netplay/lobby_client.py): the window never opens a socket, never reads a report itself, never changes a
firewall or any system setting (at most a button that opens Windows' own firewall page). The worker's events arrive on its
reader thread and are folded into `controller.model`; the window reads that model on Tk's thread, every POLL_MS, when its
version changed.

What the netplay package gives, the window takes as it is: `lobby_client.host_config` / `guest_config` and the controller's
`start` / `close` / `link` for the room, `invitation.parse` / `DEFAULT_PORT` for the join fields, `local_addresses` for the
host's interfaces, `LocalLibrary.hostable` for the games a host can pick. Every reason the room gives comes as a code
(`room_code`, the errors' `code`) and is said in the interface language; the English detail is only for the logs.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .branding import COLORS, ICON_PATHS, make_icon
from .dialogs import center_dialog

# A thick tick for the guest's Ready button: three parallel strokes, so it stays bold at the button's size.
ICON_PATHS.setdefault('ready', tuple((2, 8 + d, 6, 12 + d, 14, 3 + d) for d in (-0.6, 0, 0.6)))
READY_GREEN, READY_GREEN_HOVER = '#45c565', '#5fd47c'

POLL_MS = 150
CHAT_MAX = 80                    # the lobby's own limit (LOBBY.md section 2); the entry stops there
SHARINGS = ('per_player', 'everyone', 'turns')
CHECKS = ('none', 'asking', 'same', 'other', 'missing', 'failed')
BACKS = ('ended', 'game_closed', 'pipe_lost', 'left', 'seat_left', 'seat_silent', 'host_closed', 'desync', 'boot_mismatch',
         'error', 'launch_failed')
NOTICES = ('chat_too_fast', 'bad_text', 'busy', 'bad_pick')
REASONS = {'converter version': 'mp_reason_converter', 'engine': 'mp_reason_engine', 'options': 'mp_reason_options',
           'learned paths': 'mp_reason_paths', 'firmware': 'mp_reason_firmware', 'identity rules': 'mp_reason_rules',
           'no simulation identity': 'mp_reason_old'}
ERRORS = ('launch_error', 'launch_failed', 'launch_refused', 'lobby_error')
PHRASES = ('GG', 'Ready?', 'Again?', 'Pause please', 'One moment', 'Thanks!')   # RRHK_PHRASE_GG..THANKS (hostkit_session.h)
JOIN_WAIT_S = 20                 # a guest's room that has not answered by then: the firewall line


def room_configs():
    """(host_config, guest_config, start, close): lobby_client's (a gallery or a test passes its own)."""
    from .netplay import lobby_client
    return (lobby_client.host_config, lobby_client.guest_config, lobby_client.LobbyController.start,
            lobby_client.LobbyController.close)


def open_firewall_settings():
    """Windows' own firewall page; the converter changes nothing there (the lead's rule). Nothing elsewhere."""
    if sys.platform == 'win32':
        subprocess.Popen(['control.exe', 'firewall.cpl'], creationflags=subprocess.CREATE_NO_WINDOW)


class MultiplayerWindow:
    """One room at most. `app` is the converter's Application (tr, ui_font, the Tk root as app.app); `library` is this PC's
    `LocalLibrary`; `configs` (host_config, guest_config, start, close), `controller_class` and `addresses()` can be replaced
    (galleries, tests)."""

    def __init__(self, app, library, *, name='', addresses=None, configs=None, controller_class=None, pick=None,
                 hidden=False):
        from .netplay.lobby_client import LobbyController
        self.app, self.library, self.tr = app, library, app.tr
        self.font = app.ui_font
        self.addresses = addresses
        self.configs = configs or room_configs()
        self.controller_class = controller_class or LobbyController
        self.controller = None
        self.role = None                    # 'host' or 'guest' while a room is open or opening
        self.invitation_text = ''
        self.version = -1
        self.games = []                     # (inventory entry, control.Game) a host can pick
        self.loaded = False                 # the games and the addresses were read
        self.chat_seen = 0
        self.joined_at = None
        self.seats_max = 0
        self.notices_seen = 0
        self.errors_seen = 0
        self.current = 'entry'
        self.closing = False
        self.first_pick = pick              # an inventory entry chosen before the window opened (Compiled Games, right-click)
        self.log_dir = Path(tempfile.gettempdir()) / 'retro-recomp-netplay'
        window = self.window = tk.Toplevel(app.app)
        if hidden:                          # tests: built and driven, never mapped
            window.withdraw()
        window.title(self.tr('mp_title'))
        window.configure(bg=COLORS['background'])
        center_dialog(window, app.app, 760, 640)
        window.minsize(min(620, window.winfo_screenwidth() - 40), min(520, window.winfo_screenheight() - 90))
        window.protocol('WM_DELETE_WINDOW', self.ask_close)
        style = ttk.Style(window)
        style.configure('Multiplayer.TRadiobutton', background=COLORS['background'], foreground=COLORS['text'],
                        indicatorbackground=COLORS['field'], indicatorforeground=COLORS['gold'], focuscolor=COLORS['gold'])
        style.map('Multiplayer.TRadiobutton', background=[('active', COLORS['background']), ('disabled', COLORS['background'])],
                  foreground=[('disabled', COLORS['disabled'])], indicatorbackground=[('selected', COLORS['gold'])])
        # the guest's Ready button: big, gold while not ready, green once ready (Arthur, 17 Nov 2026, after the two-PC test:
        # « il faut un gros bouton avec un icône… que le joueur ne loupe pas »)
        for style_name, colour, hover in (('MultiplayerReady.TButton', COLORS['gold'], COLORS['gold_hover']),
                                    ('MultiplayerReadyOn.TButton', READY_GREEN, READY_GREEN_HOVER)):
            style.configure(style_name, background=colour, foreground=COLORS['gold_text'], bordercolor=colour,
                            lightcolor=colour, darkcolor=colour, focuscolor=COLORS['gold_text'],
                            font=(self.font, 14, 'bold'), padding=(22, 10))
            style.map(style_name, background=[('disabled', COLORS['panel']), ('active', hover)],
                      foreground=[('disabled', COLORS['disabled'])],
                      bordercolor=[('disabled', COLORS['subtle_border'])],
                      lightcolor=[('disabled', COLORS['panel'])], darkcolor=[('disabled', COLORS['panel'])])
        self.ready_images = (make_icon(window, 'ready', COLORS['gold_text'], 30), make_icon(window, 'ready', COLORS['disabled'], 30))
        self.body = tk.Frame(window, bg=COLORS['background'], padx=18, pady=16)
        self.body.pack(fill='both', expand=True)
        self.name = tk.StringVar(value=name)
        self.pages = {}
        self.build_entry()
        self.build_host()
        self.build_join()
        self.build_lobby()
        self.show('host' if pick is not None else 'entry')
        self.load_games()
        self.window.after(POLL_MS, self.poll)

    # ---- small builders ----

    def label(self, parent, key='', *, text=None, size=10, bold=False, muted=False, gold=False, wrap=0, **grid):
        widget = tk.Label(parent, text=self.tr(key) if text is None else text, bg=COLORS['background'],
                          fg=COLORS['gold_hover'] if gold else COLORS['muted'] if muted else COLORS['text'],
                          font=(self.font, size, 'bold' if bold else 'normal'), justify='left', anchor='w',
                          wraplength=wrap)
        return widget

    def page(self, name):
        frame = tk.Frame(self.body, bg=COLORS['background'])
        self.pages[name] = frame
        return frame

    def show(self, name):
        for key, frame in self.pages.items():
            if key != name:
                frame.pack_forget()
        self.pages[name].pack(fill='both', expand=True)
        self.current = name

    def title(self, parent, key):
        self.label(parent, key, size=16, bold=True).pack(anchor='w', pady=(0, 4))

    def field(self, parent, row, key, widget, sticky='ew'):
        self.label(parent, key).grid(row=row, column=0, sticky='w', padx=(0, 12), pady=5)
        widget.grid(row=row, column=1, sticky=sticky, pady=5)
        return widget

    def buttons(self, parent):
        row = tk.Frame(parent, bg=COLORS['background'])
        row.pack(side='bottom', fill='x', pady=(12, 0))
        return row

    # ---- entry: host or join ----

    def build_entry(self):
        page = self.page('entry')
        self.title(page, 'mp_title')
        self.label(page, 'mp_intro', muted=True, wrap=680).pack(anchor='w', pady=(0, 18))
        choices = tk.Frame(page, bg=COLORS['background'])
        choices.pack(fill='x')
        for column, (key, note, command) in enumerate((('mp_host', 'mp_host_note', lambda: self.show('host')),
                                                       ('mp_join', 'mp_join_note', lambda: self.show('join')))):
            card = tk.Frame(choices, bg=COLORS['panel'], padx=16, pady=16, highlightthickness=1,
                            highlightbackground=COLORS['subtle_border'])
            card.grid(row=0, column=column, sticky='nsew', padx=(0, 12) if column == 0 else 0)
            choices.columnconfigure(column, weight=1, uniform='choice')
            button = ttk.Button(card, text=self.tr(key), command=command, style='Primary.TButton')
            button.pack(fill='x')
            tk.Label(card, text=self.tr(note), bg=COLORS['panel'], fg=COLORS['muted'], font=(self.font, 9),
                     justify='left', anchor='w', wraplength=300).pack(anchor='w', fill='x', pady=(10, 0))
        self.label(page, 'mp_lan_only', muted=True, wrap=680, size=9).pack(anchor='w', pady=(18, 0))
        row = self.buttons(page)
        ttk.Button(row, text=self.tr('mp_close'), command=self.ask_close).pack(side='right')

    # ---- host setup ----

    def build_host(self):
        page = self.page('host')
        self.title(page, 'mp_host_title')
        form = tk.Frame(page, bg=COLORS['background'])
        form.pack(fill='x', pady=(8, 0))
        form.columnconfigure(1, weight=1)
        kind = tk.Frame(form, bg=COLORS['background'])
        self.room_kind = tk.StringVar(value='lan')
        ttk.Radiobutton(kind, text=self.tr('mp_kind_lan'), value='lan', variable=self.room_kind,
                        style='Multiplayer.TRadiobutton').pack(side='left')
        internet = ttk.Radiobutton(kind, text=self.tr('mp_kind_internet'), value='internet', variable=self.room_kind,
                                   style='Multiplayer.TRadiobutton')
        internet.state(['disabled'])
        internet.pack(side='left', padx=(16, 0))
        self.field(form, 0, 'mp_kind', kind)
        self.address = tk.StringVar()
        self.address_box = self.field(form, 1, 'mp_address', ttk.Combobox(form, textvariable=self.address, state='readonly'))
        self.port = tk.StringVar(value='')
        self.field(form, 2, 'mp_port', ttk.Entry(form, textvariable=self.port, width=8), sticky='w')
        self.sharing = tk.StringVar(value='per_player')
        modes = tk.Frame(form, bg=COLORS['background'])
        for mode in SHARINGS:
            ttk.Radiobutton(modes, text=self.tr('mp_sharing_' + mode), value=mode, variable=self.sharing,
                            style='Multiplayer.TRadiobutton').pack(anchor='w')
        self.field(form, 3, 'mp_sharing', modes)
        self.game_choice = tk.StringVar(value=self.tr('mp_games_loading'))
        self.game_box = self.field(form, 4, 'mp_game', ttk.Combobox(form, textvariable=self.game_choice, state='readonly'))
        self.field(form, 5, 'mp_name', ttk.Entry(form, textvariable=self.name, width=24), sticky='w')
        self.host_status = self.label(page, text='', muted=True, wrap=680)
        self.host_status.pack(anchor='w', pady=(12, 0))
        row = self.buttons(page)
        self.open_button = ttk.Button(row, text=self.tr('mp_open_room'), command=self.open_room, style='Primary.TButton')
        self.open_button.pack(side='right')
        ttk.Button(row, text=self.tr('mp_back'), command=lambda: self.show('entry')).pack(side='right', padx=(0, 8))
        from .netplay import invitation
        self.port.set(str(invitation.DEFAULT_PORT))

    def load_games(self):
        """The host's games and this PC's addresses, read on a thread (reports, a host name lookup); `poll` shows them."""
        def work():
            try:
                games = self.library.hostable()
            except Exception:                   # a library this PC cannot read: no game to offer, said on the page
                games = []
            try:
                if self.addresses is not None:
                    found = self.addresses()
                else:
                    from .netplay.lan_transport import local_addresses
                    found = local_addresses()
            except OSError:
                found = []
            self.found = (games, found)         # taken by `poll` on Tk's thread (Tk is never called from here)
        self.found = None
        threading.Thread(target=work, name='multiplayer-games', daemon=True).start()

    def game_label(self, entry, game=None):
        from .systems import get_profile
        try:
            console = get_profile(entry.system).name
        except (KeyError, ValueError):
            console = entry.system
        return f'{entry.title}  ({console})'

    def games_loaded(self, games, found):
        if not self.window.winfo_exists():
            return
        self.loaded = True
        self.games = sorted(games, key=lambda item: item[0].title.casefold())
        labels = [self.game_label(entry) for entry, _game in self.games]
        self.game_box.configure(values=labels)
        self.lobby_game_box.configure(values=labels)
        chosen = 0
        if self.first_pick is not None:
            for index, (entry, _game) in enumerate(self.games):
                if entry.executable == self.first_pick.executable:
                    chosen = index
        self.game_choice.set(labels[chosen] if labels else self.tr('mp_games_none'))
        self.address_box.configure(values=found)
        if found:
            self.address.set(found[0])
        self.host_status.configure(text='' if found else self.tr('mp_no_address'))
        self.update_open_button()

    def update_open_button(self):
        ready = bool(self.games) and bool(self.address.get()) and self.role is None
        self.open_button.state(['!disabled'] if ready else ['disabled'])

    def chosen_entry(self, variable):
        labels = [self.game_label(entry) for entry, _game in self.games]
        try:
            return self.games[labels.index(variable.get())][0]
        except ValueError:
            return None

    def open_room(self):
        try:
            port = int(self.port.get())
            if not 1024 <= port <= 65535:
                raise ValueError
        except ValueError:
            self.host_status.configure(text=self.tr('mp_bad_port'), fg=COLORS['error'])
            return
        entry = self.chosen_entry(self.game_choice)
        if entry is None:
            return
        host_config, _guest, start, _close_room = self.configs
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            config, self.invitation_text = host_config(self.address.get(), port, self.player_name(), self.sharing.get(),
                                                       self.log_dir)
        except (OSError, ValueError):               # host_config refuses an address off the local network
            self.host_status.configure(text=self.tr('mp_room_failed', detail=self.tr('mp_error_not_local')), fg=COLORS['error'])
            return
        self.role, self.pending_pick = 'host', entry
        self.host_status.configure(text=self.tr('mp_opening'), fg=COLORS['muted'])
        self.update_open_button()
        self.start_room(config)

    def player_name(self):
        name = ' '.join(self.name.get().split())[:16]
        return name or self.tr('mp_default_host' if self.role == 'host' or self.current == 'host' else 'mp_default_guest')

    # ---- join ----

    def build_join(self):
        page = self.page('join')
        self.title(page, 'mp_join_title')
        self.label(page, 'mp_join_intro', muted=True, wrap=680).pack(anchor='w', pady=(0, 8))
        form = tk.Frame(page, bg=COLORS['background'])
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)
        self.invite = tk.StringVar()
        self.invite.trace_add('write', lambda *unused: self.invite_changed())
        self.field(form, 0, 'mp_invitation', ttk.Entry(form, textvariable=self.invite))
        self.join_address, self.join_port, self.join_code = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.field(form, 1, 'mp_host_address', ttk.Entry(form, textvariable=self.join_address, width=18), sticky='w')
        self.field(form, 2, 'mp_port', ttk.Entry(form, textvariable=self.join_port, width=8), sticky='w')
        self.field(form, 3, 'mp_code', ttk.Entry(form, textvariable=self.join_code, show='•'))
        self.field(form, 4, 'mp_name', ttk.Entry(form, textvariable=self.name, width=24), sticky='w')
        self.join_status = self.label(page, text='', muted=True, wrap=680)
        self.join_status.pack(anchor='w', pady=(12, 0))
        self.firewall_row = tk.Frame(page, bg=COLORS['background'])
        self.label(self.firewall_row, 'mp_firewall_note', muted=True, wrap=520, size=9).pack(side='left', anchor='w')
        if sys.platform == 'win32':
            ttk.Button(self.firewall_row, text=self.tr('mp_firewall_open'), command=open_firewall_settings).pack(
                side='right', anchor='n')
        row = self.buttons(page)
        self.join_button = ttk.Button(row, text=self.tr('mp_join'), command=self.join_room, style='Primary.TButton')
        self.join_button.pack(side='right')
        ttk.Button(row, text=self.tr('mp_back'), command=self.leave_join).pack(side='right', padx=(0, 8))

    def leave_join(self):
        if self.role is not None:
            self.leave_room()
        self.show('entry')

    def invite_changed(self):
        from .netplay import invitation
        text = self.invite.get().strip()
        if not text:
            return
        try:
            found = invitation.parse(text)
        except invitation.InvitationError:
            self.join_status.configure(text=self.tr('mp_bad_invitation'), fg=COLORS['error'])
            return
        self.join_address.set(found.address)
        self.join_port.set(str(found.port))
        self.join_code.set(invitation.encode_secret(found.secret))
        self.join_status.configure(text='', fg=COLORS['muted'])

    def join_text(self):
        """The invitation the three fields say (they stay editable after a paste)."""
        from .netplay import invitation
        secret = invitation.decode_secret(self.join_code.get().strip())
        if secret is None:
            raise invitation.InvitationError('bad code')
        return invitation.format_invitation(self.join_address.get().strip(), int(self.join_port.get()), secret)

    def join_room(self):
        from .netplay import invitation
        _host, guest_config, _start_room, _close_room = self.configs
        try:
            text = self.join_text()
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.role = 'guest'
            config = guest_config(text, self.player_name(), self.log_dir)
        except (invitation.InvitationError, ValueError, OSError):
            self.role = None
            self.join_status.configure(text=self.tr('mp_bad_invitation'), fg=COLORS['error'])
            return
        self.join_status.configure(text=self.tr('mp_joining'), fg=COLORS['muted'])
        self.firewall_row.pack_forget()
        self.join_button.state(['disabled'])
        self.joined_at = self.window.tk.call('clock', 'seconds')
        self.start_room(config)

    # ---- the room ----

    def start_room(self, config):
        self.controller = self.controller_class(self.library)
        self.version, self.chat_seen, self.notices_seen, self.errors_seen = -1, 0, 0, 0
        self.chat_text.configure(state='normal')
        self.chat_text.delete('1.0', 'end')
        self.chat_text.configure(state='disabled')
        _host, _guest, start, _close_room = self.configs
        try:
            start(self.controller, config, log=self.log_dir / 'worker.txt')
        except OSError as error:
            self.room_failed(str(error))

    def leave_room(self):
        """Close this PC's room (a host closes it for everyone; a guest leaves it). The worker stops on a thread."""
        controller, self.controller, self.role = self.controller, None, None
        self.invitation_text = ''
        if controller is not None:
            close_room = self.configs[3]
            threading.Thread(target=close_room, args=(controller,), name='multiplayer-close', daemon=True).start()
        if not self.closing:
            self.join_button.state(['!disabled'])
            self.update_open_button()

    def room_failed(self, detail, code=None, gone=False):
        """The room did not open, could not be joined, or the host closed it: back to the page it came from, with why.
        A reason the window knows (`code`) is said in the interface language; else the room's own words."""
        from .i18n import STRINGS
        page = 'host' if self.role == 'host' else 'join'
        was_in = self.current == 'lobby'
        self.leave_room()
        reason = self.tr('mp_error_' + code) if code and 'mp_error_' + code in STRINGS else detail or self.tr('mp_error_other')
        if gone and code == 'closed':
            text = self.tr('mp_host_closed_room')
        elif gone or was_in:
            text = self.tr('mp_room_lost', detail=reason)
        else:
            text = self.tr('mp_room_failed' if page == 'host' else 'mp_join_failed', detail=reason)
        (self.host_status if page == 'host' else self.join_status).configure(text=text, fg=COLORS['error'])
        if page == 'join' and not was_in and code in ('unreachable', 'timeout'):
            self.firewall_row.pack(fill='x', pady=(8, 0))
        self.show(page)

    def poll(self):
        """Tk's thread: redraw from the model when it changed; the room's own moves (open, joined, error, gone)."""
        if self.closing or not self.window.winfo_exists():
            return
        try:
            if self.found is not None and not self.loaded:
                self.games_loaded(*self.found)
            controller = self.controller
            if controller is not None:
                model = controller.model
                if model.version != self.version:
                    self.version = model.version
                    self.model_changed(model)
                elif self.current == 'lobby' and model.link:
                    self.draw_link()            # the delay comes from the worker's status, not from an event
                elif self.role == 'guest' and model.room == 'connecting' and self.joined_at is not None:
                    if self.window.tk.call('clock', 'seconds') - self.joined_at > JOIN_WAIT_S:
                        self.room_failed('', 'unreachable')
        finally:
            self.window.after(POLL_MS, self.poll)

    def model_changed(self, model):
        with model.lock:
            room, code, detail = model.room, model.room_code, model.room_detail
        if room == 'error':
            self.room_failed(detail, code)
            return
        if room in ('open', 'joined') and self.current != 'lobby':
            self.show('lobby')
            if self.role == 'host' and getattr(self, 'pending_pick', None) is not None:
                self.pick(self.pending_pick)
                self.pending_pick = None
        if room in ('host_gone', 'closed') and self.role == 'guest':
            self.room_failed(detail, code if room == 'host_gone' else 'closed', gone=True)
            return
        if self.current == 'lobby':
            self.draw_lobby(model)

    # ---- the lobby ----

    def build_lobby(self):
        page = self.page('lobby')
        top = tk.Frame(page, bg=COLORS['background'])
        top.pack(fill='x')
        self.room_line = self.label(top, text='', size=13, bold=True)
        self.room_line.pack(anchor='w')
        self.invite_row = tk.Frame(top, bg=COLORS['background'])
        self.invite_shown = tk.StringVar()
        ttk.Entry(self.invite_row, textvariable=self.invite_shown, state='readonly', font=('Consolas', 10)).pack(
            side='left', fill='x', expand=True)
        ttk.Button(self.invite_row, text=self.tr('mp_copy'), command=self.copy_invitation).pack(side='left', padx=(8, 0))
        self.invite_note = self.label(top, 'mp_invite_note', muted=True, size=9, wrap=700)
        # the game, the input mode (the host chooses, a guest reads)
        settings = tk.Frame(page, bg=COLORS['background'])
        settings.pack(fill='x', pady=(10, 0))
        settings.columnconfigure(1, weight=1)
        self.lobby_game = tk.StringVar()
        self.lobby_game_box = ttk.Combobox(settings, textvariable=self.lobby_game, state='readonly')
        self.lobby_game_box.bind('<<ComboboxSelected>>', lambda event: self.pick(self.chosen_entry(self.lobby_game)))
        self.lobby_game_text = self.label(settings, text='')
        self.label(settings, 'mp_game').grid(row=0, column=0, sticky='w', padx=(0, 12), pady=3)
        self.lobby_mode = tk.StringVar()
        self.lobby_mode_box = ttk.Combobox(settings, state='readonly', width=38,
                                           values=[self.tr('mp_sharing_' + m) for m in SHARINGS])
        self.lobby_mode_box.bind('<<ComboboxSelected>>', lambda event: self.set_sharing(self.lobby_mode_box.current()))
        self.lobby_mode_text = self.label(settings, text='')
        self.label(settings, 'mp_sharing').grid(row=1, column=0, sticky='w', padx=(0, 12), pady=3)
        self.settings = settings
        # the seats
        seats = tk.Frame(page, bg=COLORS['background'])
        seats.pack(fill='x', pady=(10, 0))
        self.seat_table = ttk.Treeview(seats, columns=('seat', 'name', 'state', 'check'), show='headings', height=4,
                                       selectmode='browse')
        for column, key, width in (('seat', 'mp_col_seat', 90), ('name', 'mp_col_name', 150), ('state', 'mp_col_state', 110),
                                   ('check', 'mp_col_check', 330)):
            self.seat_table.heading(column, text=self.tr(key))
            self.seat_table.column(column, width=width, stretch=column == 'check')
        self.seat_table.pack(side='left', fill='x', expand=True)
        moves = tk.Frame(seats, bg=COLORS['background'])
        moves.pack(side='left', fill='y', padx=(8, 0))
        self.move_up = ttk.Button(moves, text='▲', width=3, command=lambda: self.move_selected(-1))
        self.move_down = ttk.Button(moves, text='▼', width=3, command=lambda: self.move_selected(1))
        self.move_up.pack()
        self.move_down.pack(pady=(4, 0))
        self.moves = moves
        # a guest's Ready: one big toggle button with its tick, and why it is greyed when it is
        self.ready = tk.BooleanVar()
        self.ready_row = tk.Frame(page, bg=COLORS['background'])
        normal, disabled = self.ready_images
        self.ready_button = ttk.Button(self.ready_row, text=self.tr('mp_ready_go'), image=(normal, 'disabled', disabled),
                                       compound='left', style='MultiplayerReady.TButton', command=self.toggle_ready,
                                       cursor='hand2')
        self.ready_button.pack(side='left')
        self.ready_hint = self.label(self.ready_row, text='', muted=True, size=9, wrap=380)
        self.ready_hint.pack(side='left', padx=(14, 0))
        self.link_line = self.label(page, text='', muted=True, size=9)
        self.link_line.pack(anchor='w', pady=(6, 0))
        # the chat
        chat = tk.Frame(page, bg=COLORS['background'])
        chat.pack(fill='both', expand=True, pady=(8, 0))
        self.chat_text = tk.Text(chat, height=7, wrap='word', bg=COLORS['field'], fg=COLORS['text'], relief='flat',
                                 padx=8, pady=6, font=(self.font, 10), state='disabled', highlightthickness=1,
                                 highlightbackground=COLORS['subtle_border'])
        self.chat_text.tag_configure('name', foreground=COLORS['gold_hover'], font=(self.font, 10, 'bold'))
        self.chat_text.tag_configure('note', foreground=COLORS['muted'], font=(self.font, 9, 'italic'))
        self.chat_text.pack(fill='both', expand=True)
        say = tk.Frame(chat, bg=COLORS['background'])
        say.pack(fill='x', pady=(6, 0))
        self.chat_entry = tk.StringVar()
        self.chat_entry.trace_add('write', lambda *unused: self.bound_chat())
        entry = ttk.Entry(say, textvariable=self.chat_entry)
        entry.pack(side='left', fill='x', expand=True)
        entry.bind('<Return>', lambda event: self.send_chat())
        ttk.Button(say, text=self.tr('mp_send'), command=self.send_chat).pack(side='left', padx=(8, 0))
        # the state of the room and the actions
        self.banner = tk.Label(page, text='', bg=COLORS['selected'], fg=COLORS['text'], font=(self.font, 10, 'bold'),
                               anchor='w', padx=10, pady=6)
        row = self.buttons(page)
        self.launch_button = ttk.Button(row, text=self.tr('mp_launch'), command=self.launch, style='Primary.TButton')
        ttk.Button(row, text=self.tr('mp_leave'), command=self.ask_leave).pack(side='right')
        self.launch_hint = self.label(row, text='', muted=True, size=9)
        self.launch_hint.pack(side='left')

    def toggle_ready(self):
        """The Ready button: the other state at once (the roster confirms it), the same controller.ready(bool) call."""
        if self.controller is None or self.ready_button.instate(['disabled']):
            return
        self.ready.set(not self.ready.get())
        self.show_ready()
        self.controller.ready(self.ready.get())

    def show_ready(self):
        on = self.ready.get()
        self.ready_button.configure(text=self.tr('mp_ready_on' if on else 'mp_ready_go'),
                                    style='MultiplayerReadyOn.TButton' if on else 'MultiplayerReady.TButton')

    def bound_chat(self):
        text = self.chat_entry.get()
        if len(text) > CHAT_MAX:
            self.chat_entry.set(text[:CHAT_MAX])

    def copy_invitation(self):
        self.window.clipboard_clear()
        self.window.clipboard_append(self.invite_shown.get())

    def pick(self, entry):
        if entry is None or self.controller is None:
            return
        refusal = self.controller.pick(entry)
        if refusal:
            self.note_line(self.tr('mp_pick_refused'))

    def set_sharing(self, index):
        if self.controller is not None and 0 <= index < len(SHARINGS):
            self.controller.set_sharing(SHARINGS[index])

    def move_selected(self, step):
        chosen = self.seat_table.selection()
        if not chosen or self.controller is None:
            return
        seat, guest = (int(part) for part in chosen[0].split(':'))
        target = seat + step
        if guest and 1 <= target < max(2, self.seats_max):
            self.controller.move(guest, target)

    def send_chat(self):
        text = ' '.join(self.chat_entry.get().split())[:CHAT_MAX]
        if text and self.controller is not None:
            self.controller.say(text)
            self.chat_entry.set('')

    def launch(self):
        if self.controller is None:
            return
        refusal = self.controller.launch({}, need_ready=True)
        if refusal:
            self.note_line(self.tr('mp_launch_refused'))

    def note_line(self, text):
        self.chat_text.configure(state='normal')
        self.chat_text.insert('end', text + '\n', 'note')
        self.chat_text.configure(state='disabled')
        self.chat_text.see('end')

    def phrase(self, number):
        """A ready-made chat phrase (the games' six, RRHK_PHRASE_*) in the window's language, from the games' catalogue."""
        from .i18n import catalog
        english = PHRASES[number - 1]
        language = getattr(self.app, 'language', 'en')
        return english if language == 'en' else catalog(language).get('runtime', {}).get(english, english)

    def check_text(self, check, detail=None):
        """One player's check, worded from the fields (status, reason bits), never from the English log line."""
        if check == 'other':
            from .netplay.lobby_check import reason_names
            names = [self.tr(REASONS[name]) for name in reason_names((detail or {}).get('reasons') or 0) if name in REASONS]
            return self.tr('mp_check_other', parts=', '.join(names)) if names else self.tr('mp_check_other_plain')
        return self.tr('mp_check_' + check) if check in CHECKS else ''

    def draw_lobby(self, model):
        with model.lock:
            players, me, seats_max = [dict(p) for p in model.players], model.me, model.seats_max
            game, sharing, phase = model.game, model.sharing, model.phase
            checks = {guest: dict(value) for guest, value in model.checks.items()}
            chat = list(model.chat)
            notices = list(model.notices)
            address, back = model.address, model.last_back
            invite = model.invitation or self.invitation_text
            errors = list(model.errors)
        host = self.role == 'host'
        self.seats_max = seats_max
        # the room line and the invitation
        if host:
            where = f'{address[0]}:{address[1]}' if address else ''
            self.room_line.configure(text=self.tr('mp_room_open', where=where))
            self.invite_shown.set(invite)
            self.invite_row.pack(fill='x', pady=(6, 0))
            self.invite_note.pack(anchor='w', pady=(4, 0))
        else:
            host_name = next((p.get('name', '') for p in players if p.get('seat', -1) == 0), '')
            self.room_line.configure(text=self.tr('mp_room_joined', host=host_name))
            self.invite_row.pack_forget()
            self.invite_note.pack_forget()
        # the game and the mode
        title = (game or {}).get('title') or self.tr('mp_no_game')
        if host:
            self.lobby_game_text.grid_forget()
            self.lobby_game_box.grid(row=0, column=1, sticky='ew', pady=3)
            if game:
                for entry, picked in self.games:
                    if picked.title == game.get('title') and picked.machine == game.get('machine'):
                        self.lobby_game.set(self.game_label(entry))
            self.lobby_mode_text.grid_forget()
            self.lobby_mode_box.grid(row=1, column=1, sticky='w', pady=3)
            self.lobby_mode_box.current(SHARINGS.index(sharing) if sharing in SHARINGS else 0)
            self.lobby_mode_box.state(['!disabled'] if phase == 'lobby' else ['disabled'])
            self.lobby_game_box.state(['!disabled'] if phase == 'lobby' else ['disabled'])
        else:
            self.lobby_game_box.grid_forget()
            self.lobby_game_text.configure(text=title)
            self.lobby_game_text.grid(row=0, column=1, sticky='w', pady=3)
            self.lobby_mode_box.grid_forget()
            self.lobby_mode_text.configure(text=self.tr('mp_sharing_' + sharing) if sharing in SHARINGS else '')
            self.lobby_mode_text.grid(row=1, column=1, sticky='w', pady=3)
        # the seats: one row per player, the host first; the seats a game takes are numbered P1..
        chosen = self.seat_table.selection()
        self.seat_table.delete(*self.seat_table.get_children())
        for player in sorted(players, key=lambda p: p.get('seat', 0)):
            seat, guest = player.get('seat', 0), player.get('guest', 0)
            state = (self.tr('mp_state_playing') if player.get('in_match') else self.tr('mp_state_host') if seat == 0
                     else self.tr('mp_state_ready') if player.get('ready') else self.tr('mp_state_waiting'))
            check = '' if seat == 0 else self.check_text(player.get('check'), checks.get(guest))
            name = player.get('name', '') + ('  ' + self.tr('mp_you') if guest == me or (host and seat == 0) else '')
            seat_text = f'P{seat + 1}' if not seats_max or seat < seats_max else self.tr('mp_seat_spare')
            self.seat_table.insert('', 'end', iid=f'{seat}:{guest}', values=(seat_text, name, state, check))
        if chosen and self.seat_table.exists(chosen[0]):
            self.seat_table.selection_set(chosen[0])
        if host:
            self.moves.pack(side='left', fill='y', padx=(8, 0))
            self.ready_row.pack_forget()
        else:
            self.moves.pack_forget()
            self.ready_row.pack(fill='x', pady=(10, 2), before=self.link_line)
            mine = next((p for p in players if p.get('guest') == me), {})
            self.ready.set(bool(mine.get('ready')))
            self.show_ready()
            usable = phase == 'lobby' and mine.get('check') == 'same'
            self.ready_button.state(['!disabled'] if usable else ['disabled'])
            self.ready_hint.configure(text='' if phase != 'lobby' else self.tr(
                'mp_ready_blocked' if not usable else 'mp_ready_cancel_note' if self.ready.get() else 'mp_ready_note'))
        self.draw_link()
        # the room's refusals (a launch that failed, a call refused): one line each in the chat
        self.chat_text.configure(state='normal')
        for error in errors[self.errors_seen:]:
            code = error.get('code')
            self.chat_text.insert('end', self.tr('mp_errnote_' + code if code in ERRORS else 'mp_launch_refused') + '\n', 'note')
        self.errors_seen = len(errors)
        self.chat_text.configure(state='disabled')
        # the chat: the lines not shown yet, and the notices
        self.chat_text.configure(state='normal')
        for line in chat[self.chat_seen:] if len(chat) >= self.chat_seen else chat:
            self.chat_text.insert('end', (line.get('name') or '') + ' : ', 'name')
            phrase = line.get('phrase') or 0
            self.chat_text.insert('end', (self.phrase(phrase) if 1 <= phrase <= len(PHRASES) else line.get('text') or '') + '\n')
        self.chat_seen = len(chat)
        for notice in notices[self.notices_seen:]:
            code = notice.get('code')
            if code in NOTICES:
                self.chat_text.insert('end', self.tr('mp_notice_' + code) + '\n', 'note')
        self.notices_seen = len(notices)
        self.chat_text.configure(state='disabled')
        self.chat_text.see('end')
        # the match: in progress, or how the last one ended
        if phase in ('launching', 'playing'):
            self.banner.configure(text=self.tr('mp_match_running'), bg=COLORS['selected'])
            self.banner.pack(fill='x', pady=(8, 0), before=self.launch_button.master)
        elif back:
            reason = back.get('reason')
            self.banner.configure(text=self.tr('mp_back_' + reason) if reason in BACKS else self.tr('mp_back_error'),
                                  bg=COLORS['panel'])
            self.banner.pack(fill='x', pady=(8, 0), before=self.launch_button.master)
        else:
            self.banner.pack_forget()
        # Launch: the host, a game, every guest who has it ready, at least one
        if host:
            # the launch takes the guests who have the game, in seat order, up to the game's seats: those must be ready
            having = sorted((p for p in players if p.get('seat', 0) and p.get('check') == 'same'), key=lambda p: p['seat'])
            having = having[:max(1, seats_max - 1)]
            ready = bool(game) and bool(having) and all(p.get('ready') for p in having) and phase == 'lobby'
            self.launch_button.pack(side='right', padx=(0, 8))
            self.launch_button.state(['!disabled'] if ready else ['disabled'])
            self.launch_hint.configure(text='' if ready or phase != 'lobby' else self.tr(
                'mp_launch_wait_game' if not game else 'mp_launch_wait_guest' if not having else 'mp_launch_wait_ready'))
        else:
            self.launch_button.pack_forget()
            self.launch_hint.configure(text=self.tr('mp_wait_host') if phase == 'lobby' else '')

    def draw_link(self):
        """« Link: … » from the controller: the tier and cap of the launch, the delay the match applies (None until the
        driver chose it), and a slow link the host applied."""
        link = (self.controller.link() if self.controller is not None else None) or {}
        if link.get('slow'):
            text = self.tr('mp_link_slow', frames=link['slow'])
        elif link.get('tier') == 'rollback':
            text = self.tr('mp_link_rollback', frames=link.get('prediction') or 0)
        elif link.get('tier') and link.get('delay') is not None:
            text = self.tr('mp_link_delay', frames=link['delay'])
        else:
            text = self.tr('mp_link_unknown')
        if self.link_line.cget('text') != text:
            self.link_line.configure(text=text)

    # ---- leaving and closing ----

    def ask_leave(self):
        if messagebox.askyesno(self.tr('mp_title'), self.tr('mp_ask_leave_host' if self.role == 'host' else 'mp_ask_leave'),
                               parent=self.window):
            self.leave_room()
            self.show('entry')

    def ask_close(self):
        if self.role is not None and not messagebox.askyesno(
                self.tr('mp_title'), self.tr('mp_ask_leave_host' if self.role == 'host' else 'mp_ask_leave'), parent=self.window):
            return False
        self.close()
        return True

    def close(self):
        if self.closing:
            return
        self.closing = True
        self.leave_room()
        try:
            self.window.destroy()
        except tk.TclError:
            pass
