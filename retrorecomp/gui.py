"""The Retro-Recomp window: the Application class assembled from its mixins, the single-instance
check, the start-up picture and the entry point (launch).

The code of the window lives in the gui_*.py modules, one responsibility each (docs/ARCHITECTURE.md).
Every name the module had before the split is still importable from here."""
from __future__ import annotations

import collections
import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import __version__, online
from .batch import BatchItem
from .paths import (
    ROOT, ASSETS, APP_NAME, load_preferences, save_preferences, preferred_games_root, selected_bios_path,
    feedback_search_paths,
)
from .i18n import tr, extended_default, game_boy_validation_default
from .languages import LANGUAGE_NAMES, language_code, language_name
from .tooltips import Tooltip
from .ui_fonts import load_fonts, family
from .windows import set_converter_identity
from .artwork import ICON_SIZES
from .systems import discover_roms
from .branding import COLORS, apply_theme, ICON_PATHS
# The helpers and constants of gui_common and gui_drawing, re-exported under their old names.
from .gui_common import (
    PROFILES, LOCAL_PLATFORM, PLATFORMS, HELP_URL, UPX_SOURCE_URL, update_error_text, UPSTREAM_CREDITS,
    typed_pseudonym, SENDING_AVAILABLE, SEND_EVERY, UPDATE_CHECK_EVERY, base_is_newer, CLOSING_SEND, BUSY_SEND_RETRY,
    INTERFACE_PREFERENCES,
)
from .gui_drawing import (
    HATCH_SPACING, HEADER_SCALE, HEADER_HEIGHT, PORTRAIT_SIZE, NUMBER_MARKS, compact_number, _scaled_photo,
    _portrait_photo, frame_side, _framed, _portrait_picture, _tint, _colour, NAME_GOLD, NAME_AMBER, NAME_LIGHT,
    SPARKLE_PERIOD, SPARKLE_FRAME, name_colours, _glyphs, _font, elide, draw_styled_text, sparkle_frame,
    start_sparkle, PIN, PIN_CELL, PIN_SIZE, PIN_COLOURS, draw_pin, _rounded, BADGE_HEIGHT, badges_width,
    _badge_label, draw_badges, HEADER_THEMES, header_theme, TROPHY, BADGE_COLOR, badged_icon, CARTRIDGE, CLOUD,
    _FOLDER_PLUS, _toolbar_styles,
)
from .gui_window import WindowMixin
from .gui_queue import QueueMixin
from .gui_conversion import ConversionMixin
from .gui_collection import CollectionMixin
from .gui_updates import UpdatesMixin
from .gui_options import OptionsMixin
from .gui_sharing import SharingMixin
from .gui_reports import ReportsMixin
from .gui_account import AccountMixin
from .gui_leaderboard import LeaderboardMixin


class Application(WindowMixin, QueueMixin, ConversionMixin, CollectionMixin, UpdatesMixin, OptionsMixin,
                 SharingMixin, ReportsMixin, AccountMixin, LeaderboardMixin):
    """The window. Its methods live in the mixins above, one responsibility each; no name is
    defined twice, so the order of the bases decides nothing."""
    def __init__(self, app: tk.Tk):
        self.app = app
        self.items: dict[str, BatchItem] = {}
        self.results: dict[str, dict] = {}
        self.busy = False
        self.close_when_idle = False
        self.closing_checked = self.closing_after_recompile = self.closing_send = False
        # A batch of the queue or a reconversion of Compiled Games is running
        # (`busy` also covers imports, exports, manual sends and ROM searches).
        self.converting = False
        self.collection_refreshing, self.collection_refreshed_at = False, 0.0
        self.updating = False
        self.cancel = threading.Event()
        self.stop_now = threading.Event()   # "Stop now" was chosen (not "wait for the running games")
        self.messages = queue.Queue()
        self.controls = []
        self.active_rows = []
        self.running_jobs: set[int] = set()
        self.completed_jobs = 0
        self.row_status, self.tooltips, self.library_panels = {}, [], []
        # Everything the log showed this session, for problem reports.
        self.session_log = collections.deque(maxlen=20000)
        self.reporting = False
        self.credits_panel = None
        self.options_panel = None
        self.output_field = None
        self.output_browse = None
        self.recovered_batch = None
        from .compiled_games import Inventory
        self.compiled_inventory = Inventory()
        self.compiled_view = None
        self.collection_visible = False
        self.library_view = None
        self.status_key, self.status_values = 'ready', {}
        preferences = load_preferences()
        self.language = language_code(preferences.get('language'))
        app.title(APP_NAME)
        app.geometry(f'1120x{max(640, min(940, app.winfo_screenheight() - 80))}')
        app.minsize(1060, 640)
        load_fonts()
        self.ui_font = family(self.language)
        self.style = apply_theme(app, self.ui_font)
        _toolbar_styles(self.style)
        self.button_images = {}
        self.status = tk.StringVar(value=self.tr('ready'))
        self.count = tk.StringVar(value='0 ROM')
        self.detail = tk.StringVar(value=self.tr('shared'))
        chosen_output, custom_output = preferred_games_root(preferences)
        self.output = tk.StringVar(value=str(chosen_output))
        self.custom_output = tk.BooleanVar(value=custom_output)
        self.custom_output_path = chosen_output if custom_output else None
        self.system_mode = preferences.get('system_mode', 'auto')
        if self.system_mode not in ('auto', *(profile.id for profile in PROFILES)):
            self.system_mode = 'auto'
        self.platform_id = preferences.get('platform', LOCAL_PLATFORM)
        if self.platform_id not in PLATFORMS:
            self.platform_id = LOCAL_PLATFORM
        self.extended = tk.BooleanVar(value=extended_default(preferences))
        self.gb_deep_validation = tk.BooleanVar(value=game_boy_validation_default(preferences))
        # One discovery scan level per console, with optional pass and frame
        # overrides. The Mega Drive / NES switches of releases before 1.6.0 are not read any more.
        from .scan_levels import CONSOLES as SCAN_CONSOLES, normalize as normalize_scan
        saved_scan = normalize_scan(preferences.get('console_scan'))
        self.scan_level = {console: tk.StringVar(value=saved_scan.get(console, {}).get('level', 'standard'))
                           for console in SCAN_CONSOLES}
        self.scan_passes = {console: tk.StringVar(value=str(saved_scan.get(console, {}).get('passes') or ''))
                            for console in SCAN_CONSOLES}
        self.scan_frames = {console: tk.StringVar(value=str(saved_scan.get(console, {}).get('frames') or ''))
                            for console in SCAN_CONSOLES}
        self.passes = tk.IntVar(value=preferences.get('passes', 3) if isinstance(preferences.get('passes', 3), int) else 3)
        self.frames = tk.IntVar(value=preferences.get('frames', 3600) if isinstance(preferences.get('frames', 3600), int) else 3600)
        default_jobs = 3 if os.name == 'nt' else 1
        saved_jobs = preferences.get('jobs', default_jobs)
        self.jobs = tk.IntVar(value=saved_jobs if isinstance(saved_jobs, int) and 1 <= saved_jobs <= 8 else default_jobs)
        # Games converted at once per console; empty follows the shared value above.
        from .queue_state import normalize_console_jobs
        saved_console_jobs = normalize_console_jobs(preferences.get('console_jobs'))
        self.scan_jobs = {console: tk.StringVar(value=str(saved_console_jobs.get(console) or ''))
                          for console in SCAN_CONSOLES}
        self.use_cover = tk.BooleanVar(value=bool(preferences.get('use_cover', True)))
        self.overwrite = tk.BooleanVar(value=bool(preferences.get('overwrite', True)))
        self.force = tk.BooleanVar(value=False)
        saved_bios = selected_bios_path(preferences.get('ng_bios'))
        self.ng_bios = tk.StringVar(value=str(saved_bios) if saved_bios else '')
        self.x68_ipl = tk.StringVar(value=preferences.get('x68_ipl', ''))
        self.x68_cgrom = tk.StringVar(value=preferences.get('x68_cgrom', ''))
        self.x68_ram = tk.IntVar(value=preferences.get('x68_ram', 2))
        self.ng_bios_status = tk.StringVar(value=self.tr('ng_bios_not_checked') if saved_bios else self.tr('ng_bios_missing'))
        feedback_folders = feedback_search_paths(preferences)
        self.feedback_paths = {profile.id: tk.StringVar(value=str(feedback_folders.get(profile.id, ''))) for profile in PROFILES}
        from .rom_sources import rom_folders
        rom_roots = rom_folders(preferences)
        self.rom_paths = {p.id:tk.StringVar(value=str(rom_roots.get(p.id,''))) for p in PROFILES}
        self.feedback_importing = set()
        self.feedback_import_buttons = {}
        self.feedback_status = {profile.id: tk.StringVar() for profile in PROFILES}
        self.icon_tags = tk.BooleanVar(value=bool(preferences.get('icon_tags', True)))
        self.online = tk.BooleanVar(value=bool(preferences.get('online_cover', True)))
        # Signed in to the shared base: its paths before each batch, and this
        # player's new discoveries sent after it (both on unless turned off).
        self.use_shared_base = tk.BooleanVar(value=preferences.get('use_shared_base', True) is not False)
        self.send_after_batch = tk.BooleanVar(value=preferences.get('send_after_batch', True) is not False)
        # Look for a new version of the software and of the base when the window
        # opens (on unless turned off); `last_update_check` spaces the looks.
        self.check_at_startup = tk.BooleanVar(value=preferences.get('startup_update_check', True) is not False)
        saved_check = preferences.get('last_update_check')
        self.last_update_check = (saved_check if isinstance(saved_check, (int, float))
                                  and not isinstance(saved_check, bool) else None)
        # What the looks found: the Update of the software, the check_base result.
        self.update_news = {'software': None, 'base': None}
        # Collecting and sending discoveries never run twice at once.
        self.knowledge_lock = threading.Lock()
        self.auto_sending = False
        # Sends are SEND_EVERY apart, between batches too: a batch that ends
        # sooner leaves its send waiting (and a send still waiting when the
        # window closes leaves then, or at the next start).
        self.last_sent_at = None
        self.deferred_send = None
        self.closing_send_deadline = None   # closing_send itself is the closing card's 'Send and close'
        self.discoveries_waiting = bool(preferences.get('discoveries_waiting'))
        self.send_after_batch.trace_add('write', self.send_option_changed)
        self.manual_sending = False   # Knowledge › Sync (or the closing card's) send is on its way
        self.syncing = False          # Knowledge › Sync: the base update chains the send
        self.sync_line = ''           # its base result, shown with the send's
        # The player's corner: one reading of the account at a time (refresh_player).
        self.player_checked = None     # when the last reading started; None before the start-up one
        self.player_refreshing = False
        self.player_generation = 0     # readings started so far
        self.player_refresh_queued = False   # a forced reading asked for while one was running
        # After a send's claims: the first reading started from this generation on
        # logs the converted games waiting for their reward (None: nothing to log).
        self.report_queued = None
        self.site_opened = -1.0        # when a page of the site was last opened from here

        header = tk.Canvas(app, height=HEADER_HEIGHT, bg=COLORS['header'], highlightthickness=0,
                           borderwidth=0)
        self.header = header
        header.pack(fill='x')
        banner_path = ASSETS / 'assets/Retro-Recomp-banner.png'
        try:
            self.banner = _scaled_photo(banner_path, app)
            header.create_image(24, 0, image=self.banner, anchor='nw', tags='banner')
        except (OSError, ValueError, tk.TclError):
            self.banner = None
        # The wordmark starts at x=172 of the banner; the tagline sits under it.
        self.brand_tagline = header.create_text(24 + round(172 * HEADER_SCALE), round(92 * HEADER_SCALE),
            text=self.tr('brand_tagline'),
            anchor='nw', fill=COLORS['text'], font=(self.ui_font, 8), tags='brand_tagline')
        if os.name != 'nt':
            self.app_icon = tk.PhotoImage(file=str(ASSETS / 'assets/Retro-Recomp-icon-64.png'))
            app.iconphoto(True, self.app_icon)
        try:
            icon_path = str(ASSETS / 'assets/Retro-Recomp.ico')
            app.iconbitmap(icon_path)
            app.iconbitmap(default=icon_path)
        except (OSError, tk.TclError):
            pass
        try:
            self.window_icons = [tk.PhotoImage(file=str(ASSETS / f'assets/Retro-Recomp-icon-{size}.png'))
                                 for size in ICON_SIZES]
            app.iconphoto(False, *self.window_icons)
            app.iconphoto(True, *self.window_icons)
        except (OSError, tk.TclError):
            self.window_icons = []
        # Console format and language: two small fields, one under the other,
        # at the right end. They speak for themselves; their hint names them.
        self.system_name = tk.StringVar(value=self.system_display())
        self.system_field = ttk.Combobox(header, textvariable=self.system_name, style='Header.TCombobox',
            values=self.system_choices(), width=14, state='readonly', font=(self.ui_font, 8))
        self.system_field.bind('<<ComboboxSelected>>', self.change_system)
        self.language_name = tk.StringVar(value=language_name(self.language))
        self.language_field = ttk.Combobox(header, textvariable=self.language_name, style='Header.TCombobox',
                                           values=LANGUAGE_NAMES, width=14, state='readonly', font=(self.ui_font, 8))
        self.language_field.bind('<<ComboboxSelected>>', self.change_language)
        for field, name, tip in ((self.system_field, 'console_format', 'tip_console_format'),
                                 (self.language_field, 'language', 'tip_language')):
            self.tooltips.append(Tooltip(field, lambda name=name, tip=tip: f'{self.tr(name)}\n{self.tr(tip)}'))
        self.header_fields = (self.system_field, self.language_field)
        self.header_windows = tuple(header.create_window(0, 28, window=field, anchor='ne')
                                    for field in self.header_fields)
        # The player's account: portrait, name, score and the board.
        self.player = {}
        self.portrait = None
        # A thin gold-tipped divider separates the account from the selectors.
        self.header_divider = header.create_line(0, 14, 0, HEADER_HEIGHT - 14, fill=COLORS['subtle_border'],
                                                 tags='divider')
        self.header_divider_tip = header.create_rectangle(0, 0, 0, 0, fill=COLORS['gold'], outline='',
                                                          tags='divider')
        # Centred: an equipped shop frame makes the picture larger than the
        # 44 px portrait, which stays in the same place.
        self.portrait_item = header.create_image(0, HEADER_HEIGHT // 2, anchor='center', tags='portrait')
        self.looks = online.looks({}, {})
        # The portrait opens the player's account page on the site, like the
        # Options button; signed out, it opens the sign-in instead.
        header.tag_bind('portrait', '<Button-1>', lambda event: self.portrait_clicked())
        header.tag_bind('portrait', '<Enter>', lambda event: header.configure(cursor='hand2' if SENDING_AVAILABLE else ''), add='+')
        header.tag_bind('portrait', '<Leave>', lambda event: header.configure(cursor=''), add='+')
        self.tooltips.append(Tooltip(header, lambda: self.tr('tip_portrait' if online.account() else 'tip_account')
                                     if SENDING_AVAILABLE else '', item='portrait'))
        self.player_name = header.create_text(0, 10, text='', anchor='ne', fill=COLORS['text'],
                                              font=(self.ui_font, 10, 'bold'), tags='player')
        # Right-click on the corner: the site's account page, the items, the pseudonym.
        for tag in ('portrait', 'player', 'player_extra'):
            header.tag_bind(tag, '<Button-3>', self.account_menu, add='+')
        # A generated pseudonym (none chosen yet): a click on the name asks for one.
        header.tag_bind('player', '<Button-1>', lambda event: self.pseudonym_clicked(), add='+')
        # The title chosen on the site, under the pseudonym.
        self.player_title = header.create_text(0, 24, text='', anchor='ne', fill=COLORS['gold'],
                                               font=(self.ui_font, 8), tags='player')
        self.player_score = header.create_text(0, 29, text='', anchor='ne', fill=COLORS['muted'], width=270,
                                               font=(self.ui_font, 8), justify='right', tags='player')
        self.player_actions = ttk.Frame(header)
        try:
            self.trophy_icon = _scaled_photo(ASSETS / 'assets/board-trophy.png', app, 17 / 72)
        except (OSError, ValueError, tk.TclError):
            self.trophy_icon = ''
        self.board_button = ttk.Button(self.player_actions, text=self.tr('leaderboard'), style='Header.TButton',
                                       image=self.trophy_icon, compound='left', command=self.show_leaderboard)
        self.hint(self.board_button, 'tip_leaderboard')
        self.sign_in_button = ttk.Button(self.player_actions, text=self.tr('account_sign_in'),
                                         style='Header.TButton', command=self.sign_in_from_header)
        self.hint(self.sign_in_button, 'tip_account')
        self.player_window = header.create_window(0, HEADER_HEIGHT // 2, window=self.player_actions, anchor='e')
        self.render_player()
        header.bind('<Configure>', self.layout_header)
        stripe = tk.Canvas(app, height=2, bg=COLORS['subtle_border'], highlightthickness=0)
        stripe.pack(fill='x')
        def gradient(event):
            stripe.delete('all')
            stripe.create_rectangle(24, 0, 174, 2, fill=COLORS['gold'], outline='')
        stripe.bind('<Configure>', gradient)

        body = tk.Canvas(app, bg=COLORS['background'], highlightthickness=0, borderwidth=0)
        self.body = body
        body.bind('<Configure>', self.draw_background)
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=4, minsize=100)
        body.rowconfigure(7, weight=2, minsize=52)
        toolbar = ttk.Frame(body)
        self.toolbar = toolbar
        toolbar.grid(row=0, column=0, sticky='ew', padx=24, pady=(16, 10))
        # The queue/collection switch never moves: it comes first, and the
        # buttons of the visible view follow it in their own frame.
        self.compiled_button = ttk.Button(toolbar, text=self.tr('compiled_games'),
            command=self.toggle_compiled_games, style='Compiled.Toolbar.TButton')
        self.decorate_button(self.compiled_button, 'gamepad', primary=True)
        self.hint(self.compiled_button, 'tip_compiled_games')
        self.compiled_button.pack(side='left')
        self.update_compiled_button()
        self.queue_actions = ttk.Frame(toolbar)
        self.queue_actions.pack(side='left', padx=(12, 0))
        self.collection_actions = ttk.Frame(toolbar)
        self.add_roms_button = self.button(self.queue_actions, self.tr('add_roms'), self.choose_roms, 'tip_add_roms',
                                           primary=True)
        self.add_roms_button.pack(side='left')
        # Pictures only, named by their hints, to leave room for New paths.
        self.icon_button(self.queue_actions, 'add_folder', 'tip_add_folder', self.choose_directory,
                         'add_rom_folder').pack(side='left', padx=(8, 0))
        # Removing rows lives in the table's right-click menu and on Delete;
        # only emptying the whole list keeps a toolbar button.
        self.icon_button(self.queue_actions, 'clear', 'tip_clear', self.clear, 'clear').pack(side='left', padx=(6, 0))
        # One button for both views, right after the visible view's buttons:
        # the same as recompiling at closing, for games with new paths only.
        self.new_paths_buttons = []
        self.new_paths_button(toolbar).pack(side='left', padx=(12, 0))
        self.count_label = ttk.Label(toolbar, textvariable=self.count, style='Muted.TLabel')
        self.count_label.pack(side='right')
        # Rarely used: icons with their hover hints, so the bar fits every language.
        self.credits_button = self.button(toolbar, self.tr('credits'), self.show_credits, 'tip_credits')
        self.credits_button.configure(compound='image')
        self.credits_button.pack(side='right', padx=(0, 12))
        # Help: how Retro-Recomp works, left of the credits and information.
        self.help_button = ttk.Button(toolbar, text='?', style='Help.Toolbar.TButton', command=self.show_help)
        self.hint(self.help_button, 'tip_help')
        self.help_button.pack(side='right', padx=(0, 8))
        self.update_button = self.button(toolbar, self.tr('check_updates'), self.check_updates, 'tip_check_updates')
        self.update_button.configure(compound='image')
        self.update_button.pack(side='right', padx=(0, 8))
        # What is new (if anything) comes first in its hint, with the usual tip below.
        for hint in self.tooltips:
            if hint.widget is self.update_button:
                hint.text = self.update_tip
                break
        self.options_button = self.button(toolbar, self.tr('options'), self.show_options, 'tip_options')
        self.options_button.pack(side='right', padx=(0, 8))
        # Shared discoveries: visible beside the queue and the collection.
        self.knowledge_button = self.button(toolbar, self.tr('knowledge') + ' \u25be', self.knowledge_menu,
                                            'tip_knowledge')
        self.knowledge_button.pack(side='right', padx=(0, 8))

        table_frame = ttk.Frame(body)
        table_frame.grid(row=1, column=0, sticky='nsew', padx=24)
        self.table = ttk.Treeview(table_frame, columns=('title', 'system', 'video', 'size', 'cover', 'status'), show='headings', selectmode='extended', height=3)
        for key, caption, width in [('title', self.tr('game'), 350), ('system', self.tr('console'), 125),
                                    ('video', self.tr('video_timing'), 115), ('size', 'ROM', 70),
                                    ('cover', self.tr('cover'), 100), ('status', self.tr('conversion'), 210)]:
            self.table.heading(key, text=caption)
            self.table.column(key, width=width, minwidth=60, stretch=key in ('title', 'status'))
        self.table.tag_configure('error', foreground=COLORS['error'])
        self.table.tag_configure('success', foreground=COLORS['success'])
        self.table.tag_configure('stopped', foreground=COLORS['muted'])
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side='left', fill='both', expand=True)
        self.hint(self.table, 'tip_table')
        scrollbar.pack(side='right', fill='y')
        self.table.bind('<<TreeviewSelect>>', lambda event: self.selection_changed())
        self.table.bind('<Double-1>', lambda event: self.play())
        self.table.bind('<Button-3>', self.queue_menu)
        self.table.bind('<Delete>', lambda event: self.remove_selected())
        self.table.bind('<Control-a>', lambda event: (self.select_all_rows(), 'break')[1])
        self.empty_state = tk.Frame(self.table, bg=COLORS['field'], cursor='hand2')
        self.empty_art = tk.Canvas(self.empty_state, width=72, height=48,
                                   bg=COLORS['field'], highlightthickness=0)
        self.empty_art.pack()
        for path in ICON_PATHS['gamepad']:
            self.empty_art.create_line(*(6+v*4 if i % 2 == 0 else 1+v*3 for i,v in enumerate(path)),
                                       fill=COLORS['disabled'], width=3)
        ttk.Label(self.empty_state, text=self.tr('empty_title'), style='EmptyTitle.TLabel').pack(pady=(8, 2))
        ttk.Label(self.empty_state, text=self.tr('empty_hint'), style='Empty.TLabel').pack()
        for widget in (self.empty_state, *self.empty_state.winfo_children()):
            widget.bind('<Button-1>', lambda event: self.choose_roms())
        self.update_empty_state()
        self.table.bind('<Configure>', self.layout_empty_state, add='+')

        selection = ttk.Frame(body)
        selection.grid(row=2, column=0, sticky='ew', padx=24, pady=(8, 12))
        self.cover_button = self.button(selection, self.tr('choose_cover'), self.choose_cover, 'tip_choose_cover')
        self.cover_button.pack(side='left')
        self.auto_cover_button = self.button(selection, self.tr('auto_cover'), self.automatic_cover, 'tip_auto_cover')
        self.auto_cover_button.pack(side='left', padx=8)
        self.play_button = ttk.Button(selection, text=self.tr('play'), command=self.play, state='disabled')
        self.decorate_button(self.play_button, 'play')
        self.play_button.pack(side='left')
        self.hint(self.play_button, 'tip_play')
        ttk.Label(selection, text=self.tr('video_timing')).pack(side='left', padx=(18, 6))
        self.video_name = tk.StringVar(value=self.tr('auto'))
        self.video_field = ttk.Combobox(selection, textvariable=self.video_name,
                                        values=(self.tr('auto'), 'PAL', 'NTSC'), width=8, state='disabled')
        self.video_field.pack(side='left')
        self.video_field.bind('<<ComboboxSelected>>', self.change_video)
        self.controls.append(self.video_field)
        self.hint(self.video_field, 'tip_video_timing')
        self.memory_button = ttk.Button(selection, text=self.tr('memory'), command=self.show_library)
        self.decorate_button(self.memory_button, 'gamepad')
        self.memory_button.pack(side='right')
        self.hint(self.memory_button, 'tip_memory')
        ttk.Label(body, textvariable=self.detail, style='Muted.TLabel', wraplength=850).grid(row=3, column=0, sticky='ew', padx=24, pady=(0, 12))

        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, sticky='ew', padx=24, pady=(0, 8))
        self.start_button = ttk.Button(actions, text=self.tr('start'), command=self.start, style='Primary.TButton')
        self.decorate_button(self.start_button, 'refresh', primary=True)
        self.start_button.pack(side='left')
        self.hint(self.start_button, 'tip_start')
        self.selected_button = ttk.Button(actions, text=self.tr('start_selected'),
                                          command=lambda: self.start(selected=True), state='disabled')
        self.selected_button.pack(side='left', padx=(8, 0))
        self.hint(self.selected_button, 'tip_start_selected')
        self.stop_button = ttk.Button(actions, text=self.tr('stop'), command=self.stop, state='disabled')
        self.decorate_button(self.stop_button, 'stop')
        self.stop_button.pack(side='left', padx=8)
        self.hint(self.stop_button, 'tip_stop')
        # Retry: the rows that failed or were stopped, as one more batch.
        self.retry_button = ttk.Button(actions, text=self.tr('retry'), command=self.retry_failed, state='disabled')
        self.decorate_button(self.retry_button, 'refresh')
        self.retry_button.pack(side='left')
        self.hint(self.retry_button, 'tip_retry')
        open_button = ttk.Button(actions, text=self.tr('open_folder'), command=self.open_output)
        self.decorate_button(open_button, 'folder')
        open_button.pack(side='right')
        self.hint(open_button, 'tip_open_folder')
        self.progress = ttk.Progressbar(body, mode='determinate')
        self.progress.grid(row=5, column=0, sticky='ew', padx=24, pady=(0, 8))
        ttk.Label(body, textvariable=self.status, wraplength=850).grid(row=6, column=0, sticky='ew', padx=24, pady=(0, 8))
        log_frame = tk.Frame(body, bg=COLORS['field'], highlightthickness=1, highlightbackground=COLORS['border'])
        log_frame.grid(row=7, column=0, sticky='nsew', padx=24)
        self.log = tk.Text(log_frame, height=2, font=('Consolas', 9), bg=COLORS['field'],
                           fg=COLORS['muted'], relief='flat', padx=10, pady=9,
                           state='disabled', wrap='word', insertbackground=COLORS['gold'])
        log_scroll = ttk.Scrollbar(log_frame, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        # A thin status line: one row of small text, tight margins, so the
        # queue and the log keep the height.
        footer = ttk.Frame(body)
        footer.grid(row=8, column=0, sticky='ew', padx=24, pady=(4, 5))
        status_dot = self.status_dot = tk.Canvas(footer, width=12, height=12, bg=COLORS['background'],
                                                 highlightthickness=0)
        status_dot.create_oval(2, 3, 8, 9, fill=COLORS['green'], outline='', tags='dot')
        status_dot.pack(side='left', padx=(0, 5))
        self.sending_count = 0
        self.footer_label = ttk.Label(footer, text=self.tr('footer'), style='Muted.TLabel',
                                      font=(self.ui_font, 8), padding=0)
        self.footer_label.pack(side='left')
        # Bottom right: the two gold squares in the corner, the version and
        # platform, then the motto.
        squares = tk.Canvas(footer, width=18, height=12, bg=COLORS['background'], highlightthickness=0)
        for x, y, size in ((11, 6, 6), (3, 0, 7)):
            squares.create_rectangle(x, y, x + size, y + size, fill=COLORS['gold'], outline='')
        squares.pack(side='right')
        self.version_label = ttk.Label(footer, text=f'v{__version__} · {PLATFORMS[self.platform_id]}',
                                       style='Muted.TLabel', font=(self.ui_font, 8), padding=0)
        self.version_label.pack(side='right', padx=(0, 10))
        self.tagline = ttk.Label(footer, text=self.tr('tagline'), style='Muted.TLabel',
                                 font=(self.ui_font, 8), padding=0)
        self.tagline.pack(side='right', padx=(12, 14))
        app.protocol('WM_DELETE_WINDOW', self.close)
        # Games played or converted elsewhere: rows re-read only if changed.
        app.after(1500, self.quiet_refresh_collection)
        app.after(2500, self.refresh_player)
        if self.discoveries_waiting:   # left waiting when the window last closed
            app.after(6000, self.send_new_discoveries)
        app.bind('<FocusIn>', lambda event: self.quiet_refresh_collection(every=20), add='+')
        app.bind('<FocusIn>', lambda event: self.focus_player(), add='+')
        self.file_drop = None
        app.after_idle(self.enable_drops)
        app.after_idle(self.fit_minimum_width)
        app.after(100, self.drain)
        self.compiler_widgets = [w for w in body.grid_slaves() if 1 <= int(w.grid_info()['row']) <= 7]

    def tr(self, key, **values):
        return tr(key, self.language, **values)

    def close(self):
        if self.updating:
            messagebox.showinfo(APP_NAME, self.tr('wait_update'))
            return
        if self.busy:
            # A recompile chosen on the closing card runs to its end first;
            # otherwise closing means stopping now, once confirmed.
            if not self.closing_after_recompile and not self.cancel.is_set() and not self.stop():
                return
            self.close_when_idle = True
            return
        if not self.closing_checked and self.offer_closing_card():
            return
        if self.send_before_closing():
            return
        try:
            save_preferences(self.preferences())
        except (OSError, tk.TclError, ValueError):
            pass
        if self.recovered_batch is not None:self.recovered_batch.close()
        self.app.destroy()

    def send_before_closing(self):
        """A send left waiting by the 15-minute spacing leaves with the window:
        it closes once the send ends, or after CLOSING_SEND seconds (then the
        next start sends it). True while the window waits for it."""
        if getattr(self, 'closing_send_deadline', None) is not None:
            if self.auto_sending and time.monotonic() < self.closing_send_deadline:
                self.app.after(200, self.close)
                return True
            return False
        if getattr(self, 'deferred_send', None) is None:
            return False
        self.app.after_cancel(self.deferred_send)
        self.deferred_send = None
        self.send_new_discoveries()
        if not self.auto_sending:
            return False
        self.closing_send_deadline = time.monotonic() + CLOSING_SEND
        self.app.after(200, self.close)
        return True


def instance_token():
    """One converter per installation folder; two installations may run."""
    import hashlib
    digest = hashlib.sha256(str(ROOT.resolve()).lower().encode('utf-8')).hexdigest()
    return digest[:16], 49152 + int(digest[:4], 16) % 16000


def claim_instance():
    """The first converter of an installation listens on a local port; a later
    start finds it, asks it to come to the front, and leaves. Returns the
    listening socket, None when another converter answered, or False when the
    port belongs to something else (then both run, as before)."""
    import socket
    token, port = instance_token()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.bind(('127.0.0.1', port))
        server.listen(2)
        return server
    except OSError:
        server.close()
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1) as peer:
            peer.settimeout(1)
            peer.sendall(token.encode('ascii') + b'\n')
            if peer.recv(32).startswith(b'RR ' + token.encode('ascii')):
                return None
    except OSError:
        pass
    return False


def serve_instance(server, application):
    """Answer later starts: the token proves it is Retro-Recomp, the window is
    raised from the Tk thread through the message queue."""
    import socket
    token, _ = instance_token()
    def listen():
        while True:
            try:
                peer, _ = server.accept()
            except OSError:
                return
            with peer:
                try:
                    peer.settimeout(1)
                    if peer.recv(64).strip() == token.encode('ascii'):
                        peer.sendall(b'RR ' + token.encode('ascii'))
                        application.messages.put(('raise', None))
                except OSError:
                    pass
    threading.Thread(target=listen, daemon=True, name='retro-recomp-instance').start()


def close_splash():
    """The start-up picture shown by the packaged converter while it unpacks."""
    try:
        import pyi_splash
        if pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass


SPLASH_STEPS = 4
SPLASH_KEY = '#ff00ff'   # Windows: the colour the start-up window shows as transparent


def startup_picture(step, text, version, transparent, language='en'):
    """The start-up picture: the logo with its own outline, gold segments that
    light up one by one, the current step and the version. The packaged
    converter's unpacking picture (tools/build_splash.py) is step 1 of it.
    Where the window can be transparent (Windows), edges are kept sharp: a
    pixel is either fully shown or keyed out, so no tinted fringe appears."""
    from PIL import Image, ImageDraw, ImageFont
    gold = (212, 167, 55, 255)
    width, height = 300, 290
    image = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if not transparent:   # Linux: no transparent windows, a dark card instead
        draw.rounded_rectangle((0, 0, width - 1, height - 1), 22, fill=(24, 24, 24, 255), outline=gold, width=2)
    logo = Image.open(ASSETS / 'assets/Retro-Recomp-icon-256.png').convert('RGBA').resize((230, 230), Image.LANCZOS)
    image.alpha_composite(logo, ((width - 230) // 2, 8))
    left, top, segment, gap = 60, 226, 40, 6
    for index in range(SPLASH_STEPS):
        if index < step or not transparent:
            x = left + index * (segment + gap)
            draw.rounded_rectangle((x, top, x + segment, top + 5), 2, fill=gold if index < step else (70, 70, 70, 255))
    face = 'SC' if language_code(language) == 'zh' else 'JP'
    font = ImageFont.truetype(str(ASSETS / f'assets/RetroRecomp-UI-{face}.otf'), 13)
    if text:
        draw.text((width // 2, top + 20), text, font=font, fill=(235, 235, 235, 255), anchor='mm')
    small = ImageFont.truetype(str(ASSETS / f'assets/RetroRecomp-UI-{face}.otf'), 12)
    draw.text((width // 2, top + 40), 'v' + version, font=small, fill=(196, 158, 62, 255), anchor='mm')
    if transparent:
        # Half-covered pixels are laid on the dark logo colour and made opaque.
        dark = Image.new('RGBA', image.size, (20, 20, 20, 255))
        solid = Image.alpha_composite(dark, image)
        mask = image.getchannel('A').point(lambda alpha: 255 if alpha >= 110 else 0)
        image = Image.new('RGBA', image.size, (0, 0, 0, 0))
        image.paste(solid, (0, 0), mask)
    return image


class StartupSplash:
    """The start-up window once Python runs: the same picture as the unpacking
    one, its segments moving on while the interface loads."""
    def __init__(self, app, language):
        self.app, self.language = app, language
        self.transparent = os.name == 'nt'
        window = self.window = tk.Toplevel(app)
        window.overrideredirect(True)
        window.attributes('-topmost', True)
        background = SPLASH_KEY if self.transparent else '#000000'
        window.configure(bg=background)
        if self.transparent:
            window.attributes('-transparentcolor', SPLASH_KEY)
        self.canvas = tk.Canvas(window, width=300, height=290, bg=background, highlightthickness=0, borderwidth=0)
        self.canvas.pack()
        x = (window.winfo_screenwidth() - 300) // 2
        y = (window.winfo_screenheight() - 290) // 2
        window.geometry(f'300x290+{x}+{y}')

    def step(self, step, key):
        from PIL import ImageTk
        picture = startup_picture(step, tr(key, self.language), __version__, self.transparent, self.language)
        self.photo = ImageTk.PhotoImage(picture, master=self.window)
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        self.window.update()

    def close(self):
        try:
            self.window.destroy()
        except tk.TclError:
            pass


def launch(update_error: str | None = None):
    from .updater import use_installed_tools
    use_installed_tools()
    server = claim_instance()
    if server is None:
        close_splash()
        return
    set_converter_identity()
    load_fonts()
    # The class name is what Linux desktops match the launcher's
    # StartupWMClass against, to stop their "starting" cursor.
    app = tk.Tk(className='Retro-Recomp')
    app.withdraw()
    splash = None
    try:
        splash = StartupSplash(app, load_preferences().get('language', 'en'))
        splash.step(2, 'splash_starting')
    except Exception:
        splash = None
    # Our own picture is up at the same place: the unpacking one can go.
    close_splash()
    if splash:
        splash.step(3, 'splash_interface')
    application = Application(app)
    if server:
        serve_instance(server, application)
    roms = ROOT / 'ROMS'
    if not application.restore_queue() and roms.is_dir():
        application.add_paths(discover_roms(roms))
    app._retro_application = application
    # A few seconds after the window opens, never before: the look for something new.
    app.after(4000, application.startup_update_check)
    if update_error:
        app.after(200, lambda: messagebox.showerror(APP_NAME,
            application.tr('update_failed', error=update_error)))
    if splash:
        splash.step(4, 'splash_ready')
        app.after(250, lambda: (splash.close(), app.deiconify()))
    else:
        app.deiconify()
    app.mainloop()
