"""The converter's Multiplayer window (stage 3 of the network play, STAGE3_WINDOW.md section 1): host or join a room on the
local network or over the Internet, the lobby (seats, each player's check, the input mode, the chat), the launch, the match
in progress and its end.

The layout is Arthur's proposal A, « Tableau de bord » (19 Nov 2026): rounded cards (retrorecomp/rounded_ui.py), the room's
game, players and chat on the left; on the right the big round action button (the host's Launch, a guest's Ready), the link
line, the invitation card and Leave. The first page asks where to play: Local (chosen at every opening) or Internet, which
shows three warnings to confirm first (Arthur's decision of 19 Nov 2026).

A `tk.Toplevel` of its own like the Credits, one at a time. Everything the room does goes through a `LobbyController` and
its worker (retrorecomp/netplay/lobby_client.py): the window never opens a socket, never reads a report itself, never changes a
firewall, a router or any system setting (at most a button that opens Windows' own firewall page). The worker's events arrive
on its reader thread and are folded into `controller.model`; the window reads that model on Tk's thread, every POLL_MS, when
its version changed.

What the netplay package gives, the window takes as it is: `lobby_client.host_config` / `guest_config` and the controller's
`start` / `close` / `link` for the room, `invitation.parse` / `DEFAULT_PORT` for the join fields, `local_addresses` for the
host's interfaces, `LocalLibrary.hostable` for the games a host can pick. The Internet room's fields (agreed with the
multiplayer specialist, 19 Nov 2026) are read with defaults, so the window runs before they exist: `lobby_client.INTERNET`
(Internet offered only when True), `host_config(..., internet=, public_address=)`, `guest_config_manual`, the model's `key`,
`code`, `public` and `reach`, `controller.set_public_address`, the link's `path`. Every reason the room gives comes as a code
(`room_code`, the errors' `code`, an InvitationError's `code`) and is said in the interface language; the English detail is
only for the logs.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .branding import COLORS
from .dialogs import center_dialog
from .rounded_ui import Look, RoundButton

POLL_MS = 150
CHAT_MAX = 80                    # the lobby's own limit (LOBBY.md section 2); the entry stops there
SHARINGS = ('per_player', 'everyone', 'turns')
CHECKS = ('none', 'asking', 'same', 'other', 'missing', 'failed')
BACKS = ('ended', 'game_closed', 'pipe_lost', 'left', 'seat_left', 'seat_silent', 'host_closed', 'desync', 'boot_mismatch',
         'error', 'launch_failed')
NOTICES = ('chat_too_fast', 'bad_text', 'busy', 'bad_pick', 'wrong_key_attempts')
# A game that refused one of the host's options (RRHK_REFUSED_OPTION, its text the option key), as the match driver says it
# (lockstep.py: « the game refused (1): <key> »), in a match_over or a launch event's detail.
REFUSED_OPTION = re.compile(r'the game refused \(1\): (\S+)')
REASONS = {'converter version': 'mp_reason_converter', 'engine': 'mp_reason_engine', 'options': 'mp_reason_options',
           'learned paths': 'mp_reason_paths', 'firmware': 'mp_reason_firmware', 'identity rules': 'mp_reason_rules',
           'no simulation identity': 'mp_reason_old'}
ERRORS = ('launch_error', 'launch_failed', 'launch_refused', 'lobby_error')
PHRASES = ('GG', 'Ready?', 'Again?', 'Pause please', 'One moment', 'Thanks!')   # RRHK_PHRASE_GG..THANKS (hostkit_session.h)
JOIN_WAIT_S = 20                 # a guest's room that has not answered by then: the firewall line
# How the Internet host is reached (the model's `reach`), its line and the colour of its dot.
REACH = {'probing': ('mp_reach_probing', 'muted'), 'upnp': ('mp_reach_upnp', 'green'), 'ipv6': ('mp_reach_ipv6', 'green'),
         'site': ('mp_reach_site', 'gold'), 'typed': ('mp_reach_typed', 'green'),
         'forward_needed': ('mp_reach_forward', 'gold'), 'cgnat': ('mp_reach_cgnat', 'error'),
         'waiting': ('mp_reach_waiting', 'green')}
PATHS = ('lan', 'ipv4', 'ipv6')
KEY_ERRORS = {'typo': 'mp_error_key_typo', 'other_version': 'mp_error_key_version', 'code_typo': 'mp_error_code_typo'}

WIDTH, HEIGHT = 900, 660
CARD, CARD2, DEEP, WARN = '#2b2b2b', '#323232', COLORS['field'], '#3a3122'
BG = COLORS['background']
SEAT_COLOURS = ('#d4a737', '#5aa9e6', '#45c565', '#d77fd0')
STATE_DOTS = {'host': COLORS['gold'], 'ready': COLORS['green'], 'waiting': COLORS['disabled'], 'other': COLORS['error'],
              'playing': COLORS['gold_hover']}


def room_configs():
    """(host_config, guest_config, start, close): lobby_client's (a gallery or a test passes its own)."""
    from .netplay import lobby_client
    return (lobby_client.host_config, lobby_client.guest_config, lobby_client.LobbyController.start,
            lobby_client.LobbyController.close)


def internet_ready():
    """True once the netplay package says its Internet room works (`lobby_client.INTERNET`)."""
    from .netplay import lobby_client
    return getattr(lobby_client, 'INTERNET', False) is True


def open_firewall_settings():
    """Windows' own firewall page; the converter changes nothing there (the lead's rule). Nothing elsewhere."""
    if sys.platform == 'win32':
        subprocess.Popen(['control.exe', 'firewall.cpl'], creationflags=subprocess.CREATE_NO_WINDOW)


def refused_setting(detail):
    """The host's option key a game refused, or None."""
    found = REFUSED_OPTION.search(detail or '')
    return found.group(1) if found else None


class MultiplayerWindow:
    """One room at most. `app` is the converter's Application (tr, ui_font, the Tk root as app.app); `library` is this PC's
    `LocalLibrary`; `configs` (host_config, guest_config, start, close), `controller_class`, `addresses()` and `internet`
    (None: ask lobby_client) can be replaced (galleries, tests)."""

    def __init__(self, app, library, *, name='', addresses=None, configs=None, controller_class=None, pick=None,
                 hidden=False, internet=None, guest_manual=None):
        from .netplay.lobby_client import LobbyController
        self.app, self.library, self.tr = app, library, app.tr
        self.font = app.ui_font
        self.addresses = addresses
        self.configs = configs or room_configs()
        self.guest_manual = guest_manual
        self.controller_class = controller_class or LobbyController
        self.internet_ready = internet_ready() if internet is None else internet
        self.controller = None
        self.role = None                    # 'host' or 'guest' while a room is open or opening
        self.room_mode = 'local'            # the mode of the room open or opening
        self.invitation_text = ''
        self.version = -1
        self.games = []                     # (inventory entry, control.Game) a host can pick
        self.loaded = False                 # the games and the addresses were read
        self.lan_addresses = []
        self.chat_seen = 0
        self.joined_at = None
        self.seats_max = 0
        self.notices_seen = 0
        self.errors_seen = 0
        self.refusals_seen = set()          # the matches whose refused option is already in the chat
        self.current = 'entry'
        self.closing = False
        self.internet_confirmed = False     # the three warnings, confirmed in this window (Local again at every opening)
        self.code_shown = False
        self.details_open = False
        self.more_open = False
        self.help_open = False
        self.last_players = []
        self.pictures = {}
        self.action_role = None
        self.first_pick = pick              # an inventory entry chosen before the window opened (Compiled Games, right-click)
        self.hidden = hidden
        self.log_dir = Path(tempfile.gettempdir()) / 'retro-recomp-netplay'
        window = self.window = tk.Toplevel(app.app)
        if hidden:                          # tests: built and driven, never mapped
            window.withdraw()
        window.title(self.tr('mp_title'))
        window.configure(bg=BG)
        center_dialog(window, app.app, WIDTH, HEIGHT)
        window.minsize(min(820, window.winfo_screenwidth() - 40), min(600, window.winfo_screenheight() - 90))
        window.protocol('WM_DELETE_WINDOW', self.ask_close)
        self.make_styles()
        self.mode = tk.StringVar(value='local')
        self.mode.trace_add('write', lambda *unused: self.mode_changed())
        self.body = tk.Frame(window, bg=BG, padx=16, pady=14)
        self.body.pack(fill='both', expand=True)
        self.name = tk.StringVar(value=name)
        self.pages = {}
        self.chips = []
        self.build_entry()
        self.build_host()
        self.build_join()
        self.build_lobby()
        self.show('host' if pick is not None else 'entry')
        self.load_games()
        self.window.after(POLL_MS, self.poll)

    # ---- the look ----

    def make_styles(self):
        c = COLORS
        look = self.look = Look(self.window, c, self.font)
        look.card('MpCard', CARD, BG, 16)
        look.card('MpDeep', DEEP, CARD, 12)
        look.card('MpDeepBg', DEEP, BG, 16, outline=c['gold'])
        look.card('MpSeat', CARD2, CARD, 14)
        look.card('MpWarn', WARN, BG, 16, outline=c['gold'])
        look.card('MpBanner', c['selected'], BG, 12)
        look.card('MpChip', DEEP, BG, 12)
        look.pill_button('MpGold', c['gold'], c['gold_hover'], c['gold_text'], CARD, 12, bold=True)
        look.pill_button('MpGoldBg', c['gold'], c['gold_hover'], c['gold_text'], BG, 14, bold=True, size=11,
                         padding=(20, 7))
        look.pill_button('MpGoldWarn', c['gold'], c['gold_hover'], c['gold_text'], WARN, 12, bold=True)
        look.pill_button('MpGhostWarn', WARN, c['hover'], c['muted'], WARN, 12, outline=c['border'])
        look.pill_button('MpSoft', c['button'], c['hover'], c['text'], CARD, 12)
        look.pill_button('MpSeatButton', CARD, c['hover'], c['text'], CARD2, 9, padding=(4, 2))
        look.pill_button('MpGhostBg', BG, c['hover'], c['muted'], BG, 12, outline=c['border'])
        look.segment('MpSeg', DEEP, c['gold'], c['hover'])
        style = look.style
        style.configure('MpCard.TRadiobutton', background=CARD, foreground=c['text'], indicatorbackground=DEEP,
                        indicatorforeground=c['gold'], focuscolor=c['gold'])
        style.map('MpCard.TRadiobutton', background=[('active', CARD), ('disabled', CARD)],
                  foreground=[('disabled', c['disabled'])], indicatorbackground=[('selected', c['gold'])])

    def picture(self, kind, *args):
        """A small picture, made once (dots, avatars, bars, icons)."""
        key = (kind,) + args
        if key not in self.pictures:
            self.pictures[key] = getattr(self.look, kind)(*args)
        return self.pictures[key]

    # ---- small builders ----

    def label(self, parent, key='', *, text=None, size=10, bold=False, muted=False, gold=False, wrap=0, bg=BG, colour=None):
        return tk.Label(parent, text=self.tr(key) if text is None else text, bg=bg,
                        fg=colour or (COLORS['gold_hover'] if gold else COLORS['muted'] if muted else COLORS['text']),
                        font=(self.font, size, 'bold' if bold else 'normal'), justify='left', anchor='w', wraplength=wrap)

    def card(self, parent, style='MpCard', padding=14):
        return ttk.Frame(parent, style=f'{style}.TFrame', padding=padding)

    def heading(self, parent, key=None, *, text=None, icon=None, bg=CARD):
        row = tk.Frame(parent, bg=bg)
        if icon:
            tk.Label(row, image=self.picture('icon', icon, COLORS['gold_hover'], bg, 16), bg=bg).pack(side='left', padx=(0, 6))
        label = tk.Label(row, text=(self.tr(key) if text is None else text).upper(), bg=bg, fg=COLORS['gold_hover'],
                         font=(self.font, 9, 'bold'))
        label.pack(side='left')
        row.text = label
        return row

    def fold(self, parent, key, command, bg=CARD):
        """A « ▸ More » link that opens a fold (its arrow drawn, so every font shows it)."""
        row = tk.Frame(parent, bg=bg, cursor='hand2')
        arrow = tk.Label(row, image=self.picture('icon', 'fold_closed', COLORS['muted'], bg, 12), bg=bg)
        arrow.pack(side='left')
        text = tk.Label(row, text=self.tr(key), bg=bg, fg=COLORS['muted'], font=(self.font, 9, 'underline'))
        text.pack(side='left', padx=(3, 0))
        for widget in (row, arrow, text):
            widget.bind('<Button-1>', lambda event: command())
        row.arrow, row.bg = arrow, bg
        return row

    def fold_state(self, row, opened):
        row.arrow.configure(image=self.picture('icon', 'fold_open' if opened else 'fold_closed', COLORS['muted'], row.bg, 12))

    def deep_entry(self, parent, variable, *, show='', width=0, bg=CARD, mono=False):
        """An entry on a dark rounded field."""
        frame = ttk.Frame(parent, style='MpDeep.TFrame' if bg == CARD else 'MpChip.TFrame', padding=(10, 5))
        entry = tk.Entry(frame, textvariable=variable, bg=DEEP, fg=COLORS['text'], insertbackground=COLORS['text'],
                         relief='flat', highlightthickness=0, font=('Consolas', 11) if mono else (self.font, 10), show=show,
                         width=width or 20, disabledbackground=DEEP, readonlybackground=DEEP)
        entry.pack(fill='x', expand=True)
        frame.entry = entry
        return frame

    def page(self, name):
        frame = tk.Frame(self.body, bg=BG)
        self.pages[name] = frame
        return frame

    def show(self, name):
        for key, frame in self.pages.items():
            if key != name:
                frame.pack_forget()
        self.pages[name].pack(fill='both', expand=True)
        self.current = name
        self.draw_chips()

    def head(self, page, key=None, *, text=None):
        """A page's title row with the room mode on the right (a chip on the pages after the first)."""
        row = tk.Frame(page, bg=BG)
        row.pack(fill='x')
        title = tk.Label(row, text=self.tr(key) if text is None else text, bg=BG, fg=COLORS['text'],
                         font=(self.font, 16, 'bold'), anchor='w')
        title.pack(side='left')
        chip = ttk.Frame(row, style='MpChip.TFrame', padding=(10, 4))
        chip.pack(side='right')
        chip.icon = tk.Label(chip, bg=DEEP)
        chip.icon.pack(side='left')
        chip.text = tk.Label(chip, bg=DEEP, fg=COLORS['gold_hover'], font=(self.font, 9, 'bold'))
        chip.text.pack(side='left', padx=(5, 0))
        self.chips.append(chip)
        return row, title

    def draw_chips(self):
        mode = self.room_mode if self.role is not None else self.mode.get()
        for chip in self.chips:
            chip.icon.configure(image=self.picture('icon', 'globe' if mode == 'internet' else 'home', COLORS['gold_hover'],
                                                   DEEP, 14))
            chip.text.configure(text=self.tr('mp_mode_' + mode))

    def bottom(self, parent):
        row = tk.Frame(parent, bg=BG)
        row.pack(side='bottom', fill='x', pady=(12, 0))
        return row

    # ---- entry: where, then host or join ----

    def build_entry(self):
        page = self.page('entry')
        tk.Label(page, text=self.tr('mp_title'), bg=BG, fg=COLORS['text'], font=(self.font, 18, 'bold')).pack(anchor='w')
        self.intro = self.label(page, 'mp_intro', muted=True, wrap=840)
        self.intro.pack(anchor='w', pady=(4, 0))
        where = tk.Frame(page, bg=BG)
        where.pack(fill='x', pady=(14, 0))
        self.where_row = where
        self.label(where, 'mp_where', muted=True).pack(side='left', padx=(0, 12))
        track = ttk.Frame(where, style='MpDeepBg.TFrame', padding=3)
        track.pack(side='left')
        self.mode_buttons = {}
        for mode, icon in (('local', 'home'), ('internet', 'globe')):
            button = ttk.Radiobutton(track, text=self.tr('mp_mode_' + mode), value=mode, variable=self.mode,
                                     style='MpSeg.TRadiobutton', compound='left')
            button.pack(side='left')
            self.mode_buttons[mode] = button
        if not self.internet_ready:
            self.mode_buttons['internet'].state(['disabled'])
            self.label(where, 'mp_internet_soon', muted=True, size=9).pack(side='left', padx=(12, 0))
        # the three warnings, confirmed before Internet is on (Arthur, 19 Nov 2026)
        warn = self.warn_card = ttk.Frame(page, style='MpWarn.TFrame', padding=16)
        tk.Label(warn, text=self.tr('mp_warn_title'), bg=WARN, fg=COLORS['gold_hover'], font=(self.font, 11, 'bold')).pack(
            anchor='w')
        for key in ('mp_warn_address', 'mp_warn_port', 'mp_warn_trust'):
            line = tk.Frame(warn, bg=WARN)
            line.pack(fill='x', pady=(6, 0))
            tk.Label(line, image=self.picture('icon', 'shield', COLORS['gold_hover'], WARN, 14), bg=WARN).pack(
                side='left', anchor='n', pady=(2, 0))
            self.label(line, key, bg=WARN, wrap=780).pack(side='left', padx=(8, 0))
        actions = tk.Frame(warn, bg=WARN)
        actions.pack(fill='x', pady=(12, 0))
        self.warn_ok = ttk.Button(actions, text=self.tr('mp_warn_ok'), style='MpGoldWarn.TButton', command=self.confirm_internet)
        self.warn_ok.pack(side='left')
        ttk.Button(actions, text=self.tr('mp_warn_stay'), style='MpGhostWarn.TButton',
                   command=lambda: self.mode.set('local')).pack(side='left', padx=(8, 0))
        # host or join
        cards = self.choice_cards = tk.Frame(page, bg=BG)
        cards.pack(fill='x', pady=(16, 0))
        self.choice_buttons = []
        for column, (title, note, button, icon, command) in enumerate((
                ('mp_host_card', 'mp_host_card_note', 'mp_host', 'home', lambda: self.show('host')),
                ('mp_join_card', 'mp_join_card_note', 'mp_join', 'globe', lambda: self.show('join')))):
            cards.columnconfigure(column, weight=1, uniform='choice')
            card = self.card(cards, padding=20)
            card.grid(row=0, column=column, sticky='nsew', padx=(0, 10) if column == 0 else 0)
            tk.Label(card, image=self.picture('icon', icon, COLORS['gold_hover'], CARD, 34), bg=CARD).pack(anchor='w')
            self.label(card, title, size=14, bold=True, bg=CARD).pack(anchor='w', pady=(10, 4))
            self.label(card, note, muted=True, bg=CARD, wrap=370).pack(anchor='w')
            action = ttk.Button(card, text=self.tr(button), style='MpGold.TButton', command=command)
            action.pack(anchor='w', pady=(14, 0))
            self.choice_buttons.append(action)
        row = self.bottom(page)
        ttk.Button(row, text=self.tr('mp_close'), style='MpGhostBg.TButton', command=self.ask_close).pack(side='right')
        self.mode_changed()

    def mode_changed(self):
        """Local or Internet on the first page: Internet shows the warnings until they are confirmed."""
        internet = self.mode.get() == 'internet'
        if internet and not self.internet_ready:
            self.mode.set('local')
            return
        asking = internet and not self.internet_confirmed
        if asking:
            self.warn_card.pack(fill='x', pady=(14, 0), after=self.where_row)
        else:
            self.warn_card.pack_forget()
        for button in self.choice_buttons:
            button.state(['disabled'] if asking else ['!disabled'])
        if internet:
            self.intro.pack_forget()
        else:
            self.intro.pack(anchor='w', pady=(4, 0), before=self.where_row)
        icons = {'local': 'home', 'internet': 'globe'}
        for mode, button in self.mode_buttons.items():
            chosen = mode == self.mode.get()
            button.configure(image=self.picture('icon', icons[mode], COLORS['gold_text'] if chosen else COLORS['muted'],
                                                COLORS['gold'] if chosen else DEEP, 14))
        if hasattr(self, 'host_form'):
            self.draw_host_form()
            self.draw_join_form()
        self.draw_chips()

    def confirm_internet(self):
        self.internet_confirmed = True
        self.mode_changed()

    # ---- host setup ----

    def build_host(self):
        page = self.page('host')
        self.head(page, 'mp_host_title')
        card = self.card(page, padding=18)
        card.pack(fill='x', pady=(14, 0))
        form = self.host_form = tk.Frame(card, bg=CARD)
        form.pack(fill='x')
        form.columnconfigure(1, weight=1)

        def row(number, key, widget, sticky='ew'):
            label = self.label(form, key, bg=CARD, muted=True)
            label.grid(row=number, column=0, sticky='w', padx=(0, 14), pady=5)
            widget.grid(row=number, column=1, sticky=sticky, pady=5)
            return label, widget

        self.game_choice = tk.StringVar(value=self.tr('mp_games_loading'))
        _label, self.game_box = row(0, 'mp_game', ttk.Combobox(form, textvariable=self.game_choice, state='readonly'))
        self.sharing = tk.StringVar(value='per_player')
        modes = tk.Frame(form, bg=CARD)
        for mode in SHARINGS:
            ttk.Radiobutton(modes, text=self.tr('mp_sharing_' + mode), value=mode, variable=self.sharing,
                            style='MpCard.TRadiobutton').pack(anchor='w')
        row(1, 'mp_sharing', modes)
        row(2, 'mp_name', self.deep_entry(form, self.name, width=24), sticky='w')
        self.address = tk.StringVar()
        self.address_row = row(3, 'mp_address', ttk.Combobox(form, textvariable=self.address, state='readonly'))
        self.address_box = self.address_row[1]
        self.port = tk.StringVar(value='')
        row(4, 'mp_port', self.deep_entry(form, self.port, width=8, mono=True), sticky='w')
        self.typed_public = tk.StringVar()
        self.public_row = row(5, 'mp_type_address', self.deep_entry(form, self.typed_public, width=24, mono=True), sticky='w')
        self.host_status = self.label(page, text='', muted=True, wrap=840)
        self.host_status.pack(anchor='w', pady=(12, 0))
        bar = self.bottom(page)
        ttk.Button(bar, text=self.tr('mp_back'), style='MpGhostBg.TButton', command=lambda: self.show('entry')).pack(side='left')
        self.open_button = ttk.Button(bar, text=self.tr('mp_open_room'), style='MpGoldBg.TButton', command=self.open_room)
        self.open_button.pack(side='right')
        from .netplay import invitation
        self.port.set(str(invitation.DEFAULT_PORT))
        self.draw_host_form()

    def draw_host_form(self):
        """The Internet room's own field: an address typed by hand (the box, IPv6 or the site find it otherwise)."""
        label, widget = self.public_row
        if self.mode.get() == 'internet':
            label.grid()
            widget.grid()
        else:
            label.grid_remove()
            widget.grid_remove()

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
        return f'{entry.title}  ({self.console_name(entry.system)})'

    @staticmethod
    def console_name(system):
        from .systems import get_profile
        try:
            return get_profile(system).name
        except (KeyError, ValueError):
            return system or ''

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
        self.lan_addresses = list(found)
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
        internet = self.mode.get() == 'internet' and self.internet_confirmed
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            arguments = (self.address.get(), port, self.player_name(), self.sharing.get(), self.log_dir)
            if internet:
                typed = self.typed_public.get().strip() or None
                config, self.invitation_text = host_config(*arguments, internet=True, public_address=typed)
            else:
                config, self.invitation_text = host_config(*arguments)
        except (OSError, ValueError):               # host_config refuses an address off the local network
            self.host_status.configure(text=self.tr('mp_room_failed', detail=self.tr('mp_error_not_local')), fg=COLORS['error'])
            return
        self.role, self.pending_pick = 'host', entry
        self.room_mode = 'internet' if internet else 'local'
        self.host_status.configure(text=self.tr('mp_opening'), fg=COLORS['muted'])
        self.update_open_button()
        self.start_room(config)

    def player_name(self):
        name = ' '.join(self.name.get().split())[:16]
        return name or self.tr('mp_default_host' if self.role == 'host' or self.current == 'host' else 'mp_default_guest')

    # ---- join ----

    def build_join(self):
        page = self.page('join')
        self.head(page, 'mp_join_title')
        card = self.card(page, padding=18)
        card.pack(fill='x', pady=(14, 0))
        self.join_by = tk.StringVar(value='key')
        track = ttk.Frame(card, style='MpDeep.TFrame', padding=3)
        track.pack(anchor='w')
        self.join_by_buttons = {}
        for value, key in (('key', 'mp_by_key'), ('address', 'mp_by_address')):
            button = ttk.Radiobutton(track, text=self.tr(key), value=value, variable=self.join_by, style='MpSeg.TRadiobutton',
                                     command=self.draw_join_form)
            button.pack(side='left')
            self.join_by_buttons[value] = button
        self.key_panel = tk.Frame(card, bg=CARD)
        self.label(self.key_panel, 'mp_paste_key', muted=True, bg=CARD).pack(anchor='w', pady=(12, 6))
        self.invite = tk.StringVar()
        self.invite.trace_add('write', lambda *unused: self.invite_changed())
        self.deep_entry(self.key_panel, self.invite, mono=True).pack(fill='x')
        self.manual_panel = tk.Frame(card, bg=CARD)
        self.manual_panel.columnconfigure(1, weight=1)
        self.join_address, self.join_port, self.join_code = tk.StringVar(), tk.StringVar(), tk.StringVar()
        for number, key, variable, width, show in ((0, 'mp_host_address', self.join_address, 26, ''),
                                                   (1, 'mp_port', self.join_port, 8, ''),
                                                   (2, 'mp_code', self.join_code, 34, '•')):
            self.label(self.manual_panel, key, muted=True, bg=CARD).grid(row=number, column=0, sticky='w', padx=(0, 14), pady=5)
            field = self.deep_entry(self.manual_panel, variable, width=width, mono=True, show=show)
            field.grid(row=number, column=1, sticky='w', pady=5)
            if number == 2:
                self.join_code_entry = field.entry
        self.join_code_toggle = ttk.Button(self.manual_panel, text=self.tr('mp_show'), style='MpSoft.TButton',
                                           command=self.toggle_join_code)
        self.join_code_toggle.grid(row=2, column=2, padx=(8, 0))
        name_row = tk.Frame(card, bg=CARD)
        name_row.pack(fill='x', side='bottom', pady=(12, 0))
        self.label(name_row, 'mp_name', muted=True, bg=CARD).pack(side='left', padx=(0, 14))
        self.deep_entry(name_row, self.name, width=24).pack(side='left')
        self.join_status = self.label(page, text='', muted=True, wrap=840)
        self.join_status.pack(anchor='w', pady=(12, 0))
        self.privacy_line = self.label(page, 'mp_privacy', muted=True, size=9)
        self.firewall_row = tk.Frame(page, bg=BG)
        self.label(self.firewall_row, 'mp_firewall_note', muted=True, wrap=640, size=9).pack(side='left', anchor='w')
        if sys.platform == 'win32':
            ttk.Button(self.firewall_row, text=self.tr('mp_firewall_open'), style='MpGhostBg.TButton',
                       command=open_firewall_settings).pack(side='right', anchor='n')
        bar = self.bottom(page)
        ttk.Button(bar, text=self.tr('mp_back'), style='MpGhostBg.TButton', command=self.leave_join).pack(side='left')
        self.join_button = ttk.Button(bar, text=self.tr('mp_join'), style='MpGoldBg.TButton', command=self.join_room)
        self.join_button.pack(side='right')
        self.draw_join_form()

    def draw_join_form(self):
        by_key = self.join_by.get() == 'key'
        self.join_by_buttons['key'].configure(text=self.tr('mp_by_key' if self.mode.get() == 'internet' else 'mp_invitation'))
        if by_key:
            self.manual_panel.pack_forget()
            self.key_panel.pack(fill='x')
        else:
            self.key_panel.pack_forget()
            self.manual_panel.pack(fill='x', pady=(12, 0))
        if self.mode.get() == 'internet':
            self.privacy_line.pack(anchor='w', pady=(6, 0), after=self.join_status)
        else:
            self.privacy_line.pack_forget()

    def toggle_join_code(self):
        shown = self.join_code_entry.cget('show') == ''
        self.join_code_entry.configure(show='•' if shown else '')
        self.join_code_toggle.configure(text=self.tr('mp_show' if shown else 'mp_hide'))

    def leave_join(self):
        if self.role is not None:
            self.leave_room()
        self.show('entry')

    def invite_changed(self):
        """A LAN invitation pasted fills the three fields (they stay editable). An Internet key is kept as it is."""
        from .netplay import invitation
        text = self.invite.get().strip()
        if not text or text.upper().startswith('RR2'):
            self.join_status.configure(text='', fg=COLORS['muted'])
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
        internet = self.mode.get() == 'internet' and self.internet_confirmed
        key = self.invite.get().strip()
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self.role = 'guest'
            if self.join_by.get() == 'key' and key.upper().startswith('RR2'):
                config = guest_config(key, self.player_name(), self.log_dir)
            elif internet and self.join_by.get() == 'address':
                manual = self.guest_manual or self.lobby_hook('guest_config_manual')
                if manual is None:
                    raise invitation.InvitationError('no manual form')
                config = manual(self.join_address.get().strip(), int(self.join_port.get() or 0), self.join_code.get().strip(),
                                self.player_name(), self.log_dir)
            else:
                config = guest_config(self.join_text(), self.player_name(), self.log_dir)
        except (invitation.InvitationError, ValueError, OSError) as error:
            self.role = None
            code = getattr(error, 'code', None)
            self.join_status.configure(text=self.tr(KEY_ERRORS[code]) if code in KEY_ERRORS else self.tr('mp_bad_invitation'),
                                       fg=COLORS['error'])
            return
        self.room_mode = 'internet' if internet else 'local'
        self.join_status.configure(text=self.tr('mp_joining'), fg=COLORS['muted'])
        self.firewall_row.pack_forget()
        self.join_button.state(['disabled'])
        self.joined_at = self.window.tk.call('clock', 'seconds')
        self.start_room(config)

    @staticmethod
    def lobby_hook(name):
        from .netplay import lobby_client
        return getattr(lobby_client, name, None)

    # ---- the room ----

    def start_room(self, config):
        self.controller = self.controller_class(self.library)
        self.version, self.chat_seen, self.notices_seen, self.errors_seen = -1, 0, 0, 0
        self.refusals_seen = set()
        self.code_shown = False
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
        if page == 'join' and not was_in and code in ('unreachable', 'timeout', 'port_closed'):
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

    # ---- the lobby: proposal A ----

    def build_lobby(self):
        page = self.page('lobby')
        _row, self.room_line = self.head(page, text='')
        self.banner_card = ttk.Frame(page, style='MpBanner.TFrame', padding=(14, 8))
        self.banner = tk.Label(self.banner_card, text='', bg=COLORS['selected'], fg=COLORS['text'],
                               font=(self.font, 10, 'bold'), anchor='w', justify='left', wraplength=820)
        self.banner.pack(fill='x')
        columns = self.lobby_columns = tk.Frame(page, bg=BG)
        columns.pack(fill='both', expand=True, pady=(12, 0))
        right = tk.Frame(columns, bg=BG, width=300)
        right.pack(side='right', fill='y', padx=(14, 0))
        right.pack_propagate(False)
        left = tk.Frame(columns, bg=BG)
        left.pack(side='left', fill='both', expand=True)
        self.build_game_card(left)
        self.build_players_card(left)
        self.build_chat_card(left)
        self.build_action_card(right)
        self.build_invite_card(right)
        ttk.Button(right, text=self.tr('mp_leave'), style='MpGhostBg.TButton', command=self.ask_leave).pack(
            side='bottom', fill='x')

    def build_game_card(self, parent):
        card = self.card(parent)
        card.pack(fill='x')
        self.heading(card, 'mp_game').pack(anchor='w')
        row = tk.Frame(card, bg=CARD)
        row.pack(fill='x', pady=(6, 0))
        self.lobby_game = tk.StringVar()
        self.lobby_game_box = ttk.Combobox(row, textvariable=self.lobby_game, state='readonly', width=34)
        self.lobby_game_box.bind('<<ComboboxSelected>>', lambda event: self.pick(self.chosen_entry(self.lobby_game)))
        self.lobby_game_text = self.label(row, text='', size=13, bold=True, bg=CARD)
        self.game_machine = self.label(row, text='', muted=True, size=9, bg=CARD)
        self.game_row = row
        line = tk.Frame(card, bg=CARD)
        line.pack(fill='x', pady=(6, 0))
        self.lobby_mode_text = self.label(line, text='', muted=True, size=9, bg=CARD)
        self.lobby_mode_text.pack(side='left')
        self.more_link = self.fold(line, 'mp_more', self.toggle_more)
        self.more_frame = tk.Frame(card, bg=CARD)
        self.label(self.more_frame, 'mp_sharing', muted=True, bg=CARD).pack(side='left', padx=(0, 10))
        self.lobby_mode_box = ttk.Combobox(self.more_frame, state='readonly', width=38,
                                           values=[self.tr('mp_sharing_' + m) for m in SHARINGS])
        self.lobby_mode_box.bind('<<ComboboxSelected>>', lambda event: self.set_sharing(self.lobby_mode_box.current()))
        self.lobby_mode_box.pack(side='left')

    def build_players_card(self, parent):
        card = self.card(parent)
        card.pack(fill='x', pady=(10, 0))
        self.players_heading = self.heading(card, 'mp_players')
        self.players_heading.pack(anchor='w', pady=(0, 6))
        self.seat_box = tk.Frame(card, bg=CARD)
        self.seat_box.pack(fill='x')
        self.seat_rows = []

    def build_chat_card(self, parent):
        card = self.card(parent)
        card.pack(fill='both', expand=True, pady=(10, 0))
        self.heading(card, 'mp_chat').pack(anchor='w', pady=(0, 6))
        say = tk.Frame(card, bg=CARD)
        say.pack(side='bottom', fill='x', pady=(8, 0))
        self.chat_entry = tk.StringVar()
        self.chat_entry.trace_add('write', lambda *unused: self.bound_chat())
        field = self.deep_entry(say, self.chat_entry)
        field.pack(side='left', fill='x', expand=True, padx=(0, 8))
        field.entry.bind('<Return>', lambda event: self.send_chat())
        ttk.Button(say, text=self.tr('mp_send'), style='MpSoft.TButton', command=self.send_chat).pack(side='left')
        box = ttk.Frame(card, style='MpDeep.TFrame', padding=(10, 8))
        box.pack(fill='both', expand=True)
        self.chat_text = tk.Text(box, height=3, width=10, wrap='word', bg=DEEP, fg=COLORS['text'], relief='flat',
                                 font=(self.font, 10), state='disabled', highlightthickness=0, padx=2, pady=2)
        self.chat_text.tag_configure('name', foreground=COLORS['gold_hover'], font=(self.font, 10, 'bold'))
        self.chat_text.tag_configure('note', foreground=COLORS['muted'], font=(self.font, 9, 'italic'))
        self.chat_text.pack(fill='both', expand=True)

    def build_action_card(self, parent):
        card = self.card(parent, padding=(10, 10))
        card.pack(fill='x')
        self.ready = tk.BooleanVar()
        self.action = RoundButton(card, diameter=150, bg=CARD, font=self.font, caption_width=270, command=self.press_action)
        self.action.pack()
        row = tk.Frame(card, bg=CARD)
        row.pack(anchor='w', fill='x', pady=(2, 0))
        self.link_bars = tk.Label(row, bg=CARD)
        self.link_bars.pack(side='left', anchor='n', pady=(2, 0))
        self.link_line = self.label(row, text='', muted=True, size=9, bg=CARD, wrap=240)
        self.link_line.pack(side='left', padx=(6, 0))

    def build_invite_card(self, parent):
        card = self.invite_card = self.card(parent)
        card.pack(fill='x', pady=(10, 0))
        # the host: the invitation (the LAN text or the Internet key), Copy, the address and code fold
        host = self.invite_host = tk.Frame(card, bg=CARD)
        self.invite_heading = self.heading(host, 'mp_key', icon='shield')
        self.invite_heading.pack(anchor='w')
        box = ttk.Frame(host, style='MpDeep.TFrame', padding=(10, 8))
        box.pack(fill='x', pady=(8, 6))
        self.invite_shown = tk.StringVar()
        tk.Label(box, textvariable=self.invite_shown, bg=DEEP, fg=COLORS['gold_hover'], font=('Consolas', 10, 'bold'),
                 wraplength=240, justify='left', anchor='w').pack(fill='x')
        row = self.invite_actions = tk.Frame(host, bg=CARD)
        row.pack(fill='x')
        ttk.Button(row, text=self.tr('mp_copy'), style='MpGold.TButton', compound='left', command=self.copy_invitation,
                   image=self.picture('icon', 'copy', COLORS['gold_text'], COLORS['gold'], 14)).pack(side='left')
        self.details_link = self.fold(row, 'mp_by_address', self.toggle_details)
        self.details_link.pack(side='right')
        self.reach_row = tk.Frame(host, bg=CARD)
        self.reach_dot = tk.Label(self.reach_row, bg=CARD)
        self.reach_dot.pack(side='left', anchor='n', pady=(3, 0))
        self.reach_line = self.label(self.reach_row, text='', size=9, bg=CARD, wrap=240)
        self.reach_line.pack(side='left', padx=(6, 0))
        self.build_details(host)
        # a guest: the room's mode and where it is, what happens next
        guest = self.invite_guest = tk.Frame(card, bg=CARD)
        self.heading(guest, 'mp_kind', icon='home').pack(anchor='w')
        self.guest_room = self.label(guest, text='', muted=True, size=9, bg=CARD, wrap=250)
        self.guest_room.pack(anchor='w', pady=(6, 0))
        self.launch_hint = self.label(guest, text='', muted=True, size=9, bg=CARD, wrap=250)
        self.launch_hint.pack(anchor='w', pady=(6, 0))

    def build_details(self, parent):
        """« Address and code »: a small window of its own over the room (the right column has no room for it): the address
        (public on the Internet), a hand-typed one, the port, the code hidden like a password (Show / Copy), the port-forward
        help. Built once, hidden; the link under the invitation shows it."""
        dialog = self.details = tk.Toplevel(self.window)
        dialog.withdraw()
        dialog.title(self.tr('mp_by_address'))
        dialog.configure(bg=BG)
        dialog.transient(self.window)
        dialog.protocol('WM_DELETE_WINDOW', self.toggle_details)
        card = self.card(dialog, padding=18)
        card.pack(fill='both', expand=True, padx=14, pady=14)
        self.heading(card, 'mp_by_address', icon='shield').pack(anchor='w')
        self.detail_address = self.label(card, text='', bg=CARD)
        self.detail_address.pack(anchor='w', pady=(10, 0))
        self.manual_label = self.label(card, 'mp_type_address', muted=True, size=9, bg=CARD)
        self.manual_row = tk.Frame(card, bg=CARD)
        self.typed_live = tk.StringVar()
        self.deep_entry(self.manual_row, self.typed_live, width=22, mono=True).pack(side='left', fill='x', expand=True)
        ttk.Button(self.manual_row, text=self.tr('mp_use'), style='MpSoft.TButton', command=self.use_typed_address).pack(
            side='left', padx=(8, 0))
        code = tk.Frame(card, bg=CARD)
        code.pack(fill='x', pady=(12, 0))
        self.detail_code = self.label(code, text='', bg=CARD, colour=COLORS['text'])
        self.detail_code.configure(font=('Consolas', 11))
        self.detail_code.pack(side='left')
        buttons = tk.Frame(card, bg=CARD)
        buttons.pack(fill='x', pady=(6, 0))
        self.code_toggle = ttk.Button(buttons, text=self.tr('mp_show'), style='MpSoft.TButton', command=self.toggle_code)
        self.code_toggle.pack(side='left')
        ttk.Button(buttons, text=self.tr('mp_copy'), style='MpSoft.TButton', command=self.copy_code).pack(side='left',
                                                                                                         padx=(6, 0))
        self.label(card, 'mp_code_note', muted=True, size=9, bg=CARD, wrap=440).pack(anchor='w', pady=(6, 0))
        self.help_link = self.fold(card, 'mp_port_help', self.toggle_help)
        self.help_text = self.label(card, text='', muted=True, size=9, bg=CARD, wrap=440)
        ttk.Button(dialog, text=self.tr('mp_close'), style='MpGhostBg.TButton', command=self.toggle_details).pack(
            side='bottom', anchor='e', padx=14, pady=(0, 14))

    # ---- the lobby's actions ----

    def press_action(self):
        """The round button: the host's Launch, a guest's Ready (the button refuses a press in its grey or blocked looks)."""
        if self.role == 'host':
            self.launch()
        elif self.role == 'guest':
            self.toggle_ready()

    def toggle_ready(self):
        """Ready: the other state at once (the roster confirms it), the same controller.ready(bool) call."""
        if self.controller is None or self.role != 'guest' or not self.action.pressable:
            return
        self.ready.set(not self.ready.get())
        self.draw_guest_action(phase='lobby', usable=True, check='same')
        self.controller.ready(self.ready.get())

    def toggle_more(self):
        self.more_open = not self.more_open
        self.fold_state(self.more_link, self.more_open)
        if self.more_open:
            self.more_frame.pack(fill='x', pady=(8, 0))
            self.lobby_mode_text.configure(text='')
        else:
            self.more_frame.pack_forget()
        self.draw_seats(self.last_players, *self.last_seat_args) if self.last_players else None

    def toggle_details(self):
        self.details_open = not self.details_open
        self.fold_state(self.details_link, self.details_open)
        if not self.details_open:
            self.details.withdraw()
        elif not self.hidden:                   # tests build it and read it, never show it
            self.details.update_idletasks()
            center_dialog(self.details, self.window, max(500, self.details.winfo_reqwidth()), self.details.winfo_reqheight())
            self.details.deiconify()
            self.details.lift()

    def fit_details(self):
        """The window of « Address and code » is as tall as its content (the port-forward help, or a longer language, opens it
        up): a fixed 400 px cut the Close button off. Same place, new size."""
        if not self.details_open or self.hidden:
            return
        self.details.update_idletasks()
        self.details.geometry(f'{max(500, self.details.winfo_reqwidth())}x{self.details.winfo_reqheight()}')

    def toggle_help(self):
        self.help_open = not self.help_open
        self.fold_state(self.help_link, self.help_open)
        if self.help_open:
            self.help_text.pack(anchor='w', pady=(4, 0))
        else:
            self.help_text.pack_forget()
        self.fit_details()

    def toggle_code(self):
        self.code_shown = not self.code_shown
        self.code_toggle.configure(text=self.tr('mp_hide' if self.code_shown else 'mp_show'))
        self.draw_details()
        self.fit_details()

    def use_typed_address(self):
        text = self.typed_live.get().strip()
        hook = getattr(self.controller, 'set_public_address', None)
        if text and hook is not None:
            hook(text)

    def bound_chat(self):
        text = self.chat_entry.get()
        if len(text) > CHAT_MAX:
            self.chat_entry.set(text[:CHAT_MAX])

    def clip(self, text):
        self.window.clipboard_clear()
        self.window.clipboard_append(text)

    def copy_invitation(self):
        self.clip(self.invite_shown.get())

    def copy_code(self):
        self.clip(self.room_code_text())

    def pick(self, entry):
        if entry is None or self.controller is None:
            return
        refusal = self.controller.pick(entry)
        if refusal:
            self.note_line(self.tr('mp_pick_refused'))

    def set_sharing(self, index):
        if self.controller is not None and 0 <= index < len(SHARINGS):
            self.controller.set_sharing(SHARINGS[index])

    def move_seat(self, guest, target):
        if self.controller is not None and guest and 1 <= target < max(2, self.seats_max):
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

    # ---- drawing the lobby ----

    def draw_lobby(self, model):
        with model.lock:
            players, me, seats_max = [dict(p) for p in model.players], model.me, model.seats_max
            game, sharing, phase = model.game, model.sharing, model.phase
            checks = {guest: dict(value) for guest, value in model.checks.items()}
            chat = list(model.chat)
            notices = list(model.notices)
            address, back = model.address, model.last_back
            invite = getattr(model, 'key', None) or model.invitation or self.invitation_text
            errors = list(model.errors)
            matches = [dict(match) for match in model.matches]
            self.room_fields = {'address': address, 'public': getattr(model, 'public', None),
                                'code': getattr(model, 'code', None), 'reach': getattr(model, 'reach', None),
                                'invitation': model.invitation or self.invitation_text}
        host = self.role == 'host'
        self.seats_max = seats_max
        host_name = next((p.get('name', '') for p in players if p.get('seat', -1) == 0), '')
        self.room_line.configure(text=self.tr('mp_your_room') if host else self.tr('mp_room_joined', host=host_name))
        self.draw_game(game, sharing, phase, seats_max, host)
        self.last_seat_args = (me, seats_max, checks, host, phase)
        self.last_players = players
        self.draw_seats(players, me, seats_max, checks, host, phase)
        # the invitation card: the host's key and details, or a guest's room
        if host:
            self.invite_guest.pack_forget()
            self.invite_host.pack(fill='x')
            self.invite_heading.text.configure(text=self.tr('mp_key' if self.room_mode == 'internet' else 'mp_invitation').upper())
            self.invite_shown.set(invite)
            self.draw_details()
        else:
            self.invite_host.pack_forget()
            self.invite_guest.pack(fill='x')
            where = f'{address[0]}:{address[1]}' if address else ''
            mode = self.tr('mp_mode_' + self.room_mode)
            self.guest_room.configure(text=f'{mode} · {where}' if where else mode)
        self.draw_link()
        # the room's refusals (a launch that failed, a call refused): one line each in the chat
        self.chat_text.configure(state='normal')
        for error in errors[self.errors_seen:]:
            code, key = error.get('code'), refused_setting(error.get('detail'))
            self.chat_text.insert('end', (self.refusal_text(key) if key else self.tr(
                'mp_errnote_' + code if code in ERRORS else 'mp_launch_refused')) + '\n', 'note')
        self.errors_seen = len(errors)
        # a match a game ended because it refused one of the host's settings: what to change, once per match
        for match in matches:
            key = refused_setting(match.get('detail')) if match.get('outcome') == 'refused' else None
            if key and match.get('match_id') not in self.refusals_seen:
                self.refusals_seen.add(match.get('match_id'))
                self.chat_text.insert('end', self.refusal_text(key) + '\n', 'note')
        last = matches[-1] if matches else {}
        refusal = refused_setting(last.get('detail')) if last.get('outcome') == 'refused' else None
        # the chat: the lines not shown yet, and the notices
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
            self.show_banner(self.tr('mp_match_running'), COLORS['selected'])
        elif refusal:
            self.show_banner(self.refusal_text(refusal), COLORS['selected'])
        elif back:
            reason = back.get('reason')
            self.show_banner(self.tr('mp_back_' + reason) if reason in BACKS else self.tr('mp_back_error'), COLORS['selected'])
        else:
            self.banner_card.pack_forget()
        # the round button
        if host:
            self.draw_host_action(players, game, seats_max, phase)
        else:
            mine = next((p for p in players if p.get('guest') == me), {})
            self.ready.set(bool(mine.get('ready')))
            check = mine.get('check')
            self.draw_guest_action(phase=phase, usable=phase == 'lobby' and check == 'same', check=check,
                                   detail=checks.get(me))
            self.launch_hint.configure(text=self.tr('mp_wait_host') if phase == 'lobby' else '')

    def show_banner(self, text, colour):
        self.banner.configure(text=text)
        self.banner_card.pack(fill='x', pady=(10, 0), before=self.lobby_columns)

    def draw_game(self, game, sharing, phase, seats_max, host):
        title = (game or {}).get('title') or self.tr('mp_no_game')
        machine = (game or {}).get('machine')
        self.game_machine.configure(text=self.tr('mp_machine_seats', machine=self.console_name(machine), seats=seats_max)
                                    if machine and seats_max and not host else '')
        if host:
            self.lobby_game_text.pack_forget()
            self.lobby_game_box.pack(side='left')
            if game:
                for entry, picked in self.games:
                    if picked.title == game.get('title') and picked.machine == game.get('machine'):
                        self.lobby_game.set(self.game_label(entry))
            self.lobby_game_box.state(['!disabled'] if phase == 'lobby' else ['disabled'])
            self.lobby_mode_box.current(SHARINGS.index(sharing) if sharing in SHARINGS else 0)
            self.lobby_mode_box.state(['!disabled'] if phase == 'lobby' else ['disabled'])
            self.more_link.pack(side='right')
        else:
            self.lobby_game_box.pack_forget()
            self.lobby_game_text.configure(text=title)
            self.lobby_game_text.pack(side='left')
            self.more_link.pack_forget()
            self.more_frame.pack_forget()
        self.game_machine.pack(side='left', padx=(10, 0), pady=(3, 0))
        self.lobby_mode_text.configure(text='' if host and self.more_open else self.tr('mp_sharing') + ' : ' +
                                       self.tr('mp_sharing_' + sharing) if sharing in SHARINGS else '')

    def draw_seats(self, players, me, seats_max, checks, host, phase):
        """One rounded row per player: a coloured disc, P1.., the name, the check, the state; the host's moves in the fold."""
        for row in self.seat_rows:
            row.destroy()
        self.seat_rows = []
        count = len(players)
        self.players_heading.text.configure(text=(self.tr('mp_players') + (f'  {count} / {seats_max}' if seats_max else '')).upper())
        ordered = sorted(players, key=lambda p: p.get('seat', 0))
        guests = [p.get('seat', 0) for p in ordered if p.get('seat', 0)]
        for player in ordered:
            seat, guest = player.get('seat', 0), player.get('guest', 0)
            if player.get('in_match'):
                state, kind = self.tr('mp_state_playing'), 'playing'
            elif seat == 0:
                state, kind = self.tr('mp_state_host'), 'host'
            elif player.get('check') in ('other', 'missing', 'failed'):
                state, kind = self.tr('mp_state_waiting'), 'other'
            elif player.get('ready'):
                state, kind = self.tr('mp_state_ready'), 'ready'
            else:
                state, kind = self.tr('mp_state_waiting'), 'waiting'
            check = '' if seat == 0 else self.check_text(player.get('check'), checks.get(guest))
            name = player.get('name', '') + ('  ' + self.tr('mp_you') if guest == me or (host and seat == 0) else '')
            seat_text = f'P{seat + 1}' if not seats_max or seat < seats_max else self.tr('mp_seat_spare')
            row = ttk.Frame(self.seat_box, style='MpSeat.TFrame', padding=(10, 6))
            row.pack(fill='x', pady=2)
            row.values = (seat_text, name, state, check)
            row.key = f'{seat}:{guest}'
            disc = tk.Canvas(row, width=30, height=30, bg=CARD2, highlightthickness=0)
            disc.create_image(15, 15, image=self.picture('avatar', SEAT_COLOURS[seat % len(SEAT_COLOURS)], CARD2, 30))
            disc.create_text(15, 15, text=(player.get('name') or '?')[:1].upper(), fill='#191919', font=(self.font, 11, 'bold'))
            disc.pack(side='left')
            text = tk.Frame(row, bg=CARD2)
            text.pack(side='left', fill='x', expand=True, padx=(10, 0))
            top = tk.Frame(text, bg=CARD2)
            top.pack(anchor='w')
            tk.Label(top, text=seat_text, bg=CARD2, fg=COLORS['muted'], font=(self.font, 9, 'bold')).pack(side='left')
            tk.Label(top, text=name, bg=CARD2, fg=COLORS['text'], font=(self.font, 10, 'bold')).pack(side='left', padx=(6, 0))
            if check:
                tk.Label(text, text=check, bg=CARD2, fg=COLORS['error'] if kind == 'other' else COLORS['muted'],
                         font=(self.font, 9), justify='left', anchor='w', wraplength=330).pack(anchor='w')
            chip = tk.Frame(row, bg=CARD2)
            chip.pack(side='right')
            tk.Label(chip, image=self.picture('dot', STATE_DOTS[kind], CARD2, 12), bg=CARD2).pack(side='left')
            tk.Label(chip, text=state, bg=CARD2, fg=COLORS['muted'] if kind == 'waiting' else COLORS['text'],
                     font=(self.font, 9, 'bold')).pack(side='left', padx=(5, 0))
            if host and self.more_open and seat and phase == 'lobby':
                moves = tk.Frame(row, bg=CARD2)
                moves.pack(side='right', padx=(0, 10))
                for icon, step in (('up', -1), ('down', 1)):
                    button = ttk.Button(moves, style='MpSeatButton.TButton', command=lambda g=guest, t=seat + step:
                                        self.move_seat(g, t),
                                        image=self.picture('icon', icon, COLORS['text'], CARD, 12))
                    button.pack(side='left', padx=(0, 2))
                    if (step < 0 and seat <= 1) or (step > 0 and seat >= max(guests)):
                        button.state(['disabled'])
            self.seat_rows.append(row)

    def seat_values(self):
        """The rows as (seat, name, state, check), in seat order (tests)."""
        return [row.values for row in self.seat_rows]

    def draw_host_action(self, players, game, seats_max, phase):
        # the launch takes the guests who have the game, in seat order, up to the game's seats: those must be ready
        having = sorted((p for p in players if p.get('seat', 0) and p.get('check') == 'same'), key=lambda p: p['seat'])
        having = having[:max(1, seats_max - 1)]
        ready = bool(game) and bool(having) and all(p.get('ready') for p in having) and phase == 'lobby'
        if phase in ('launching', 'playing'):
            self.action.set(look='grey', icon='play', text=self.tr('mp_state_playing'), caption=self.tr('mp_match_running'))
        elif ready:
            self.action.set(look='gold', icon='play', text=self.tr('mp_launch'), caption=self.tr('mp_go_note'))
        else:
            waiting = [p.get('name', '') for p in having if not p.get('ready')]
            caption = (self.tr('mp_launch_wait_game') if not game else self.tr('mp_launch_wait_guest') if not having
                       else self.tr('mp_wait_for', names=', '.join(waiting)) if waiting else self.tr('mp_launch_wait_ready'))
            self.action.set(look='grey', icon='wait', text=self.tr('mp_launch'), caption=caption)

    def draw_guest_action(self, *, phase, usable, check, detail=None):
        if phase in ('launching', 'playing'):
            self.action.set(look='grey', icon='play', text=self.tr('mp_state_playing'), caption=self.tr('mp_match_running'))
        elif check in ('other', 'missing', 'failed'):
            self.action.set(look='refused', icon='stop', text=self.tr('mp_blocked'), caption=self.tr('mp_ready_blocked'))
        elif not usable:
            self.action.set(look='grey', icon='wait', text=self.tr('mp_ready_go'), caption=self.check_text(check, detail))
        elif self.ready.get():
            self.action.set(look='green', icon='tick', text=self.tr('mp_ready_on'), caption=self.tr('mp_ready_cancel_note'))
        else:
            self.action.set(look='gold', icon='tick', text=self.tr('mp_ready_go'), caption=self.tr('mp_ready_note'))

    def room_code_text(self):
        """The room's code: the Internet room's own, or the LAN invitation's secret in the same alphabet."""
        fields = getattr(self, 'room_fields', {})
        if fields.get('code'):
            return fields['code']
        from .netplay import invitation
        try:
            return invitation.encode_secret(invitation.parse(fields.get('invitation') or '').secret)
        except (invitation.InvitationError, ValueError, AttributeError):
            return ''

    def draw_details(self):
        fields = getattr(self, 'room_fields', {})
        internet = self.room_mode == 'internet'
        address = fields.get('address')
        port = address[1] if address else ''
        where = fields.get('public') if internet else (address[0] if address else '')
        label = self.tr('mp_public_address' if internet else 'mp_address')
        self.detail_address.configure(text=f'{label} : {where or "-"}   ·   {self.tr("mp_port")} : {port}')
        code = self.room_code_text()
        self.detail_code.configure(text=self.tr('mp_code') + ' : ' + (code if self.code_shown else '•' * min(len(code), 27)))
        reach = fields.get('reach')
        if internet:
            self.manual_label.pack(anchor='w', pady=(12, 4), after=self.detail_address)
            self.manual_row.pack(fill='x', after=self.manual_label)
            self.help_link.pack(anchor='w', pady=(8, 0))
            lan = self.lan_addresses[0] if self.lan_addresses else (address[0] if address else '')
            self.help_text.configure(text=self.tr('mp_port_help_text', address=lan, port=port))
        else:
            self.manual_label.pack_forget()
            self.manual_row.pack_forget()
            self.help_link.pack_forget()
            self.help_text.pack_forget()
        if internet and reach in REACH:
            key, colour = REACH[reach]
            self.reach_dot.configure(image=self.picture('dot', COLORS[colour] if colour != 'muted' else COLORS['muted'], CARD, 10))
            self.reach_line.configure(text=self.tr(key, port=port), fg=COLORS['error'] if colour == 'error' else
                                      COLORS['success'] if colour == 'green' else COLORS['gold_hover'] if colour == 'gold'
                                      else COLORS['muted'])
            self.reach_row.pack(fill='x', pady=(8, 0), after=self.invite_actions)
        else:
            self.reach_row.pack_forget()

    def refusal_text(self, key):
        """What to change when a game refused the host's option `key`: the Neo Geo's AES / MVS system has its own line."""
        return self.tr('mp_refused_system') if key == 'system' else self.tr('mp_refused_setting', setting=key)

    def draw_link(self):
        """« Link: … » from the controller: the tier and cap of the launch, the delay the match applies (None until the
        driver chose it), a slow link the host applied, and the path (LAN, Internet IPv4 or IPv6); bars beside it."""
        link = (self.controller.link() if self.controller is not None else None) or {}
        level = 0
        if link.get('slow'):
            text, level = self.tr('mp_link_slow', frames=link['slow']), 1
        elif link.get('tier') == 'rollback':
            text, level = self.tr('mp_link_rollback', frames=link.get('prediction') or 0), 3
        elif link.get('tier') and link.get('delay') is not None:
            delay = link['delay']
            text, level = self.tr('mp_link_delay', frames=delay), 4 if delay <= 2 else 3 if delay <= 4 else 2
        else:
            text = self.tr('mp_link_unknown')
        path = link.get('path') or (None if self.controller is None else 'lan' if self.room_mode == 'local' else None)
        if path in PATHS:
            text += ' · ' + self.tr('mp_path_' + path)
        if self.link_line.cget('text') != text:
            self.link_line.configure(text=text)
        self.link_bars.configure(image=self.picture('bars', level, COLORS['green'], COLORS['subtle_border'], CARD, 14))

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
