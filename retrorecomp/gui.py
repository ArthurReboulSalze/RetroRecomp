from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import __version__, online
from .batch import BatchItem, identify, convert_batch, system_output
from .publishing import is_pending
from .library import list_games, library_root
from .paths import ROOT, ASSETS, APP_NAME, load_preferences, save_preferences, save_game_language, games_root, preferred_games_root, selected_bios_path, feedback_search_paths, data_directory
from .i18n import STRINGS, tr, extended_default, game_boy_validation_default, log_text
from .languages import LANGUAGES, LANGUAGE_NAMES, language_code, language_name
from .tooltips import Tooltip
from .ui_fonts import load_fonts, family
from .windows import set_converter_identity
from .dropfiles import enable_file_drop
from .artwork import ICON_SIZES
from .cover_settings import FIELDS as COVER_FIELDS, load_settings as load_cover_settings, save_settings as save_cover_settings
from .cover_keyring import KeyringError
from .cover_sources import PROVIDERS as COVER_PROVIDERS
from .systems import available_profiles, discover_roms, get_profile
PROFILES = available_profiles()
from .updater import UpdateConnectionError, UpdateServiceError
from .branding import COLORS, apply_theme, make_icon, ICON_PATHS
from .dialogs import center_dialog


from .platforms import target_id, open_local
LOCAL_PLATFORM = 'windows-x64' if os.name == 'nt' else target_id()
PLATFORMS = {LOCAL_PLATFORM: 'Windows version' if os.name == 'nt' else 'Linux version'}
HELP_URL = 'https://github.com/ArthurReboulSalze/RetroRecomp/blob/main/docs/INDEX.md'
UPX_SOURCE_URL = ('https://github.com/ArthurReboulSalze/RetroRecomp/blob/'
                  'e522cbde7ca6e7e6eccc0c901389a4178492e6d7/'
                  'licenses/upx-5.2.1-src.tar.xz')


def update_error_text(error: Exception | str, language: str) -> str:
    """Keep network diagnostics out of the player-facing update dialog."""
    if isinstance(error, UpdateConnectionError):
        return tr('update_connection_failed', language)
    if isinstance(error, UpdateServiceError):
        return tr('update_service_failed', language)
    return tr('update_failed', language, error=str(error))


UPSTREAM_CREDITS = (
    ('Master System', (
        ('mstan/smsggrecomp', 'https://github.com/mstan/smsggrecomp', 'credits_sms_recompiler'),
        ('mstan/z80-recomp-core', 'https://github.com/mstan/z80-recomp-core', 'credits_native_core'),
        ('superzazu/z80', 'https://github.com/superzazu/z80', 'credits_reference_cpu'),
    )),
    ('Game Gear', (
        ('mstan/smsggrecomp', 'https://github.com/mstan/smsggrecomp', 'credits_sms_recompiler'),
        ('mstan/z80-recomp-core', 'https://github.com/mstan/z80-recomp-core', 'credits_native_core'),
        ('superzazu/z80', 'https://github.com/superzazu/z80', 'credits_reference_cpu'),
    )),
    ('Game Boy', (
        ('arcanite24/gb-recompiled', 'https://github.com/arcanite24/gb-recompiled', 'credits_recompiler'),
    )),
    ('Nintendo NES', (
        ('mstan/nesrecomp', 'https://github.com/mstan/nesrecomp', 'credits_recompiler'),
    )),
    ('Mega Drive', (
        ('mstan/segagenesisrecomp', 'https://github.com/mstan/segagenesisrecomp', 'credits_recompiler'),
        ('mstan/m68k-recomp-core', 'https://github.com/mstan/m68k-recomp-core', 'credits_native_core'),
    )),
    ('Super Nintendo', (
        ('RetroPortingToolKit/snesrecomp', 'https://github.com/RetroPortingToolKit/snesrecomp', 'credits_recompiler'),
    )),
    ('Neo Geo', (
        ('libretro/geolith-libretro', 'https://github.com/libretro/geolith-libretro', 'credits_hardware'),
        ('carmiker/lithogen', 'https://github.com/carmiker/lithogen', 'credits_cartridge_loader'),
        ('mstan/segagenesisrecomp', 'https://github.com/mstan/segagenesisrecomp', 'credits_68000'),
    )),
    ('Capcom CPS-1', (
        ('mamedev/mame', 'https://github.com/mamedev/mame', 'credits_cps1_board'),
        ('aaronsgiles/ymfm', 'https://github.com/aaronsgiles/ymfm', 'credits_cps1_sound'),
        ('libretro/geolith-libretro', 'https://github.com/libretro/geolith-libretro', 'credits_cps1_cpu'),
        ('mstan/m68k-recomp-core', 'https://github.com/mstan/m68k-recomp-core', 'credits_68000'),
    )),
    ('Sharp X68000', (
        ('hissorii/px68k', 'https://github.com/hissorii/px68k', 'credits_x68_hardware'),
        ('libretro/geolith-libretro', 'https://github.com/libretro/geolith-libretro', 'credits_x68_cpu'),
        ('mstan/segagenesisrecomp', 'https://github.com/mstan/segagenesisrecomp', 'credits_68000'),
        ('mstan/m68k-recomp-core', 'https://github.com/mstan/m68k-recomp-core', 'credits_68000'),
        ('libretro/px68k-libretro', 'https://github.com/libretro/px68k-libretro', 'credits_x68_reference'),
    )),
)


HATCH_SPACING = 4
# The header artwork is drawn smaller than its 600 x 132 source.
HEADER_SCALE = 0.6
HEADER_HEIGHT = round(132 * HEADER_SCALE)
PORTRAIT_SIZE = 44


def _scaled_photo(path, master, scale=HEADER_SCALE):
    """Header artwork at its displayed size, resampled smoothly."""
    from PIL import Image, ImageTk
    with Image.open(path) as image:
        size = (round(image.width * scale), round(image.height * scale))
        return ImageTk.PhotoImage(image.convert('RGBA').resize(size, Image.Resampling.LANCZOS), master=master)


def _portrait_photo(master, raw=None, initial=''):
    """A round player portrait: the server's WebP when there is one, else a
    quiet disc with the player's initial, ringed in gold."""
    from PIL import Image, ImageDraw, ImageTk
    import io
    size = PORTRAIT_SIZE * 4
    if raw:
        try:
            with Image.open(io.BytesIO(raw)) as image:
                picture = image.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            raw = None
    if not raw:
        picture = Image.new('RGBA', (size, size), COLORS['button'])
        if not initial:
            # Nobody signed in: a pixel-art question mark in gold.
            mark = ('.XXXXX.', 'XX...XX', '.....XX', '....XX.', '...XX..', '...XX..', '.......', '...XX..')
            # Blocks of 3 display pixels, aligned to the 4x drawing grid so
            # the final downscale keeps them sharp.
            cell = 12
            left = (size - cell * len(mark[0])) // 8 * 4
            top = (size - cell * len(mark)) // 8 * 4
            draw = ImageDraw.Draw(picture)
            for y, row in enumerate(mark):
                for x, pixel in enumerate(row):
                    if pixel == 'X':
                        draw.rectangle((left + x * cell, top + y * cell, left + (x + 1) * cell - 1,
                                        top + (y + 1) * cell - 1), fill=COLORS['gold'])
        if initial:
            from PIL import ImageFont
            try:
                font = ImageFont.truetype('segoeuib.ttf' if os.name == 'nt' else 'DejaVuSans-Bold.ttf', size // 2)
            except OSError:
                font = ImageFont.load_default()
            ImageDraw.Draw(picture).text((size / 2, size / 2), initial.upper(), fill=COLORS['gold'],
                                         font=font, anchor='mm')
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    picture.putalpha(mask)
    ImageDraw.Draw(picture).ellipse((2, 2, size - 3, size - 3), outline=COLORS['gold'], width=6)
    return ImageTk.PhotoImage(picture.resize((PORTRAIT_SIZE, PORTRAIT_SIZE), Image.Resampling.LANCZOS), master=master)


def _tint(base: str, foreground: str, visibility: float = 0.50) -> str:
    """Blend a procedural decoration over the canvas background."""
    channel = lambda color, at: int(color[at:at + 2], 16)
    values = [round(channel(base, at) * (1 - visibility) +
                    channel(foreground, at) * visibility) for at in (1, 3, 5)]
    return '#{:02x}{:02x}{:02x}'.format(*values)


# Pixel trophy of the knowledge 'achievement' card ('o': highlight).
TROPHY = ('..XXXXXXXX..', 'XXXoXXXXXXXX', 'X.XoXXXXXX.X', 'X.XoXXXXXX.X',
          '.XXXXXXXXXX.', '..XXXXXXXX..', '...XXXXXX...', '.....XX.....',
          '.....XX.....', '....XXXX....', '...XXXXXX...', '...XXXXXX...')


# Sending discoveries needs the Retro-Recomp web service (online.py); until it
# opens, the closing card offers to recompile and its Send button stays off.
SENDING_AVAILABLE = online.sending_available()
# The closing card: a cartridge sends its discoveries to the shared base.
CARTRIDGE = ('XXXXXXX.', 'X.....XX', 'X.ooo..X', 'X.ooo..X', 'X.ooo..X',
             'X......X', 'XXXXXXXX', 'X.X.X.XX')
CLOUD = ('....XXX.....', '..XXoooXX...', '.XooooooXXX.', 'XoooooooooXX',
         'XooooooooooX', '.XXXXXXXXXX.')


# Interface-only icons: branding.py is a shared compiler input.
ICON_PATHS.setdefault('download', ((8, 1, 8, 10), (4, 6, 8, 10, 12, 6), (1, 10, 1, 14, 15, 14, 15, 10)))
# Adding a folder of ROMs (a cartridge) or of converted games (a play sign),
# and New paths (a rising route, distinct from the refresh arrows).
_FOLDER_PLUS = ((1, 4, 6, 4, 8, 6, 15, 6, 15, 15, 1, 15, 1, 4), (11, 0, 11, 4), (9, 2, 13, 2))
ICON_PATHS.setdefault('add_rom_folder', _FOLDER_PLUS + ((5, 8, 11, 8, 11, 13, 5, 13, 5, 8), (6, 10, 10, 10),
                                                        (7, 13, 7, 14), (9, 13, 9, 14)))
ICON_PATHS.setdefault('add_exe_folder', _FOLDER_PLUS + ((6, 8, 11, 11, 6, 14, 6, 8),))
ICON_PATHS.setdefault('new_paths', ((1, 14, 5, 9, 9, 11, 14, 4), (10, 4, 14, 4, 14, 8)))


def _toolbar_styles(style):
    """Collection navigation stays within interface-only compiler inputs."""
    c = COLORS
    # Toolbar buttons take their natural width instead of the theme's
    # eleven-character minimum, so the bar fits every language.
    for name in ('Toolbar.TButton', 'Toolbar.Primary.TButton'):
        style.configure(name, width=-1)
    # The header's small controls: selectors and the account's two buttons.
    style.configure('Header.TButton', width=-1, padding=(7, 2))
    style.configure('Help.Toolbar.TButton', width=-1, padding=(11, 5), foreground=c['gold'],
                    font=('TkDefaultFont', 10, 'bold'))
    style.configure('Header.TCombobox', padding=(4, 1))
    style.configure('Compiled.Toolbar.TButton', background=c['gold'], foreground=c['gold_text'],
                    bordercolor=c['gold_hover'], lightcolor=c['gold'], darkcolor=c['gold'],
                    focuscolor=c['gold_text'], relief='raised')
    style.map('Compiled.Toolbar.TButton',
              background=[('disabled', c['panel']), ('selected', c['gold_hover']),
                          ('pressed', c['gold_hover']), ('active', c['gold_hover'])],
              foreground=[('disabled', c['disabled']), ('!disabled', c['gold_text'])],
              bordercolor=[('disabled', c['border']), ('!disabled', c['gold_hover'])],
              lightcolor=[('disabled', c['panel']), ('selected', c['gold_hover']), ('active', c['gold_hover'])],
              darkcolor=[('disabled', c['panel']), ('selected', c['gold_hover']), ('active', c['gold_hover'])],
              relief=[('selected', 'sunken'), ('pressed', 'sunken')])


class Application:
    def __init__(self, app: tk.Tk):
        self.app = app
        self.items: dict[str, BatchItem] = {}
        self.results: dict[str, dict] = {}
        self.busy = False
        self.close_when_idle = False
        self.closing_checked = self.closing_after_recompile = self.skip_missing_sources = self.closing_send = False
        self.collection_refreshing, self.collection_refreshed_at = False, 0.0
        self.updating = False
        self.cancel = threading.Event()
        self.messages = queue.Queue()
        self.controls = []
        self.active_rows = []
        self.running_jobs: set[int] = set()
        self.completed_jobs = 0
        self.row_status, self.tooltips, self.library_panels = {}, [], []
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
        # overrides. The former Mega Drive / NES switches become their levels.
        from .scan_levels import CONSOLES as SCAN_CONSOLES, legacy_level, normalize as normalize_scan
        saved_scan = normalize_scan(preferences.get('console_scan'))
        if not saved_scan and 'console_scan' not in preferences:
            for console in SCAN_CONSOLES:
                level = legacy_level(console, md_advanced_scan=preferences.get('md_advanced_scan') is True,
                                     nes_advanced_scan=preferences.get('nes_advanced_scan') is True)
                if level != 'standard':
                    saved_scan[console] = {'level': level}
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
        # Collecting and sending discoveries never run twice at once.
        self.knowledge_lock = threading.Lock()
        self.auto_sending = False

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
        self.portrait_item = header.create_image(0, 12, anchor='ne', tags='portrait')
        self.player_name = header.create_text(0, 10, text='', anchor='ne', fill=COLORS['text'],
                                              font=(self.ui_font, 10, 'bold'), tags='player')
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
        self.compiled_button.pack(side='left')
        self.update_compiled_button()
        self.queue_actions = ttk.Frame(toolbar)
        self.queue_actions.pack(side='left', padx=(12, 0))
        self.collection_actions = ttk.Frame(toolbar)
        self.button(self.queue_actions, self.tr('add_roms'), self.choose_roms, primary=True).pack(side='left')
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
        self.credits_button = self.button(toolbar, self.tr('credits'), self.show_credits)
        self.credits_button.configure(compound='image')
        self.credits_button.pack(side='right', padx=(0, 12))
        # Help: how Retro-Recomp works, left of the credits and information.
        self.help_button = ttk.Button(toolbar, text='?', style='Help.Toolbar.TButton', command=self.show_help)
        self.hint(self.help_button, 'tip_help')
        self.help_button.pack(side='right', padx=(0, 8))
        self.update_button = self.button(toolbar, self.tr('check_updates'), self.check_updates)
        self.update_button.configure(compound='image')
        self.update_button.pack(side='right', padx=(0, 8))
        self.options_button = self.button(toolbar, self.tr('options'), self.show_options)
        self.options_button.pack(side='right', padx=(0, 8))
        # Shared discoveries: visible beside the queue and the collection.
        self.knowledge_button = self.button(toolbar, self.tr('knowledge') + ' \u25be', self.knowledge_menu)
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
        self.button(selection, self.tr('choose_cover'), self.choose_cover).pack(side='left')
        self.button(selection, self.tr('auto_cover'), self.automatic_cover).pack(side='left', padx=8)
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
        app.bind('<FocusIn>', lambda event: self.quiet_refresh_collection(every=20), add='+')
        self.file_drop = None
        app.after_idle(self.enable_drops)
        app.after_idle(self.fit_minimum_width)
        app.after(100, self.drain)
        self.compiler_widgets = [w for w in body.grid_slaves() if 1 <= int(w.grid_info()['row']) <= 7]

    def tr(self, key, **values):
        return tr(key, self.language, **values)

    def restore_queue(self):
        from .queue_state import recover
        journal=recover(data_directory()/'pending-batches')
        if journal is None:return False
        self.recovered_batch=journal
        self.output.set(journal.definition['output']);self.custom_output.set(True)
        self.custom_output_path=Path(journal.definition['output'])
        for item in journal.pending_items():
            status='invalid' if item.error else 'waiting'
            row=self.table.insert('','end',values=(item.title,
                get_profile(item.system).name if item.system else self.tr('unknown_console'),
                self.video_display(item),self.tr('size',value=item.size//1024) if item.size else '-',
                self.tr('auto'),self.tr(status)))
            self.items[row]=item;self.row_status[row]=status
        self.count.set(f'{len(self.items)} ROM'+('s' if len(self.items)!=1 else ''))
        self.update_empty_state();self.update_output_controls()
        self.set_status('queue_restored',count=len(self.items))
        return True

    def enable_drops(self):
        try:
            self.file_drop = enable_file_drop(self.app, self.queue_drop,
                lambda error: self.messages.put(('drop_error', str(error))))
        except OSError as error:
            self.messages.put(('drop_error', str(error)))

    def queue_drop(self, paths):
        # No Tk calls or ROM reads inside the native window procedure.
        kind = 'drop_blocked' if self.busy or self.updating else 'drop'
        self.messages.put((kind, paths))

    def drop_paths(self, paths):
        if self.busy or self.updating or getattr(self, 'importing', False):
            self.messages.put(('log', self.tr('drop_blocked')))
            return
        try:
            self.import_paths(paths)
        except OSError:
            self.messages.put(('log', self.tr('drop_unreadable')))

    def fit_minimum_width(self):
        # French labels and a large ROM count must keep every action visible.
        self.app.minsize(max(1060, self.toolbar.winfo_reqwidth() + 72), 640)

    def layout_empty_state(self, event):
        # Keep the empty-list hint below the heading even on small screens.
        if event.height < 170:
            self.empty_art.pack_forget()
        elif not self.empty_art.winfo_manager():
            self.empty_art.pack(before=self.empty_state.winfo_children()[1])

    def layout_header(self, event=None):
        header_width = event.width if event is not None else self.header.winfo_width()
        self.queue_background(self.header)
        right = header_width - 24
        # The two selector rows keep the right end, each label above its
        # field; the player's account sits just left of them.
        field_height = self.system_field.winfo_reqheight()
        first = (HEADER_HEIGHT - 2 * field_height - 6) // 2
        for row, window in enumerate(self.header_windows):
            self.header.coords(window, right, first + row * (field_height + 6))
        divider = right - max(field.winfo_reqwidth() for field in self.header_fields) - 18
        self.header.coords(self.header_divider, divider, 14, divider, HEADER_HEIGHT - 14)
        self.header.coords(self.header_divider_tip, divider - 1, 14, divider + 2, 26)
        # Right to left: the two account buttons, the portrait, name and score.
        self.header.coords(self.player_window, divider - 16, HEADER_HEIGHT // 2)
        account = divider - 16 - self.player_actions.winfo_reqwidth() - 12
        self.header.coords(self.portrait_item, account, (HEADER_HEIGHT - PORTRAIT_SIZE) // 2)
        text = account - PORTRAIT_SIZE - 12
        # Name, title (when one is chosen) and score, centred as one block.
        lines = [item for item in (self.player_name, self.player_title, self.player_score)
                 if self.header.itemcget(item, 'text')]
        heights = {item: (lambda box: box[3] - box[1])(self.header.bbox(item) or (0, 0, 0, 0)) for item in lines}
        top = max(4, (HEADER_HEIGHT - sum(heights.values()) - 2 * max(0, len(lines) - 1)) // 2)
        for item in (self.player_name, self.player_title, self.player_score):
            self.header.coords(item, text, top)
            if item in heights:
                top += heights[item] + 2


    def draw_background(self, event):
        canvas = event.widget
        self.queue_background(canvas)

    def queue_background(self, canvas):
        pending = getattr(canvas, '_background_pending', None)
        if pending is not None:
            canvas.after_cancel(pending)
        # Tk lays out the nested controls on its idle pass. A short delay also
        # coalesces resize events before we measure the text bounds.
        canvas._background_pending = canvas.after(20, lambda: self.paint_background(canvas))

    def protected_square_areas(self, canvas):
        padding = 10
        areas = []
        if canvas is self.header:
            for label in (self.player_name, self.player_title, self.player_score):
                box = canvas.bbox(label)
                if box:
                    areas.append((box[0]-padding, box[1]-padding,
                                  box[2]+padding, box[3]+padding))
        else:
            stack = list(canvas.winfo_children())
            origin_x, origin_y = canvas.winfo_rootx(), canvas.winfo_rooty()
            while stack:
                widget = stack.pop()
                stack.extend(widget.winfo_children())
                if widget.winfo_class() not in ('TLabel', 'TCheckbutton', 'TButton',
                                               'TCombobox', 'TSpinbox', 'TEntry'):
                    continue
                if widget.winfo_width() < 2 or widget.winfo_height() < 2:
                    continue
                left = widget.winfo_rootx() - origin_x
                top = widget.winfo_rooty() - origin_y
                areas.append((left-padding, top-padding,
                              left+widget.winfo_width()+padding,
                              top+widget.winfo_height()+padding))
        return tuple(areas)

    def paint_background(self, canvas):
        canvas._background_pending = None
        if not canvas.winfo_exists():
            return
        width, height = canvas.winfo_width(), canvas.winfo_height()
        protected = self.protected_square_areas(canvas)
        extent = (width, height, protected)
        if extent == getattr(canvas, '_background_extent', None):
            return
        canvas._background_extent = extent
        canvas.delete('background_motif')
        base = canvas.cget('bg')
        # Continuous, very quiet diagonal texture. The opaque table and terminal
        # keep their own flat surfaces, like the supplied identity board.
        hatch = _tint(base, '#bdbdbd', 0.035 if canvas is self.header else 0.012)
        first_offset = -((height + HATCH_SPACING - 1) // HATCH_SPACING) * HATCH_SPACING
        for offset in range(first_offset, width + HATCH_SPACING, HATCH_SPACING):
            canvas.create_line(offset, 0, offset + height, height,
                               fill=hatch, width=1,
                               tags=('background_motif', 'background_hatch'))
        canvas.tag_lower('background_motif')

    def hint(self, widget, key):
        self.tooltips.append(Tooltip(widget, lambda: self.tr(key)))

    def set_status(self, key, **values):
        self.status_key, self.status_values = key, values
        self.status.set(self.tr(key, **values))

    def announce_finished(self, record):
        """Make the end of a batch unmistakable: a framed log line with the
        totals and the elapsed time, the system bell and the window title."""
        minutes, seconds = divmod(int(record.get('elapsed_seconds') or 0), 60)
        line = self.tr('batch_finished', total=record.get('requested', 0),
                       succeeded=record.get('succeeded', 0), failed=record.get('failed', 0),
                       minutes=minutes, seconds=seconds)
        for text in ('', '=' * 72, line, '=' * 72):
            self.messages.put(('log', text))
        try:
            self.app.bell()
            self.app.title(APP_NAME + ' - ' + self.tr('finished_title'))
            self.app.after(20000, lambda: self.app.title(APP_NAME))
        except tk.TclError:
            pass

    def system_choices(self):
        return (self.tr('automatic'), *(profile.name for profile in PROFILES))

    def system_display(self):
        return self.tr('automatic') if self.system_mode == 'auto' else get_profile(self.system_mode).name

    def change_system(self, event=None):
        if self.busy:
            return
        selected = self.system_name.get()
        self.system_mode = next((profile.id for profile in PROFILES if profile.name == selected), 'auto')
        self.reload_queue()

    def update_output_controls(self):
        if self.output_field is None or not self.output_field.winfo_exists():
            return
        state = 'normal' if self.custom_output.get() and not self.busy else 'disabled'
        self.output_field.configure(state=state)
        self.output_browse.configure(state=state)

    def change_output_mode(self):
        if self.busy:
            return
        if self.custom_output.get():
            self.output.set(str(self.custom_output_path or games_root()))
        else:
            self.custom_output_path = Path(self.output.get()).expanduser()
            self.output.set(str(games_root()))
        self.update_output_controls()
        self.reload_queue()

    def reload_queue(self):
        if self.busy or not self.items:
            return
        previous = [(item.path, item.cover, item.standard_override, item.system)
                    for item in self.items.values()]
        selected = {self.items[row].path for row in self.table.selection()}
        self.table.delete(*self.table.get_children())
        self.items.clear(); self.results.clear(); self.row_status.clear()
        self.add_paths(path for path, _, _, _ in previous)
        remembered = {path: (cover, override, system) for path, cover, override, system in previous}
        for row, item in self.items.items():
            cover, override, system = remembered[item.path]
            item.cover = cover
            if not item.error and item.system == system:
                item.standard_override = override
            self.table.set(row, 'cover', self.tr('chosen' if cover else 'auto'))
            self.table.set(row, 'video', self.video_display(item, self.results.get(row)))
            if item.path in selected:
                self.table.selection_add(row)
        self.selection_changed()

    def refresh_language(self):
        previous_font = self.ui_font
        self.ui_font = family(self.language)
        if self.ui_font != previous_font:
            self.style = apply_theme(self.app, self.ui_font)
            _toolbar_styles(self.style)
        self.language_name.set(language_name(self.language))
        self.system_field.configure(values=self.system_choices())
        self.system_name.set(self.system_display())
        self.version_label.configure(text=f'v{__version__} · {PLATFORMS[self.platform_id]}')
        self.header.itemconfigure(self.brand_tagline, text=self.tr('brand_tagline'))
        self.board_button.configure(text=self.tr('leaderboard'))
        self.render_player()
        reverse = {tr(key, code): key for key in STRINGS for code in LANGUAGES if '{' not in STRINGS[key][0]}
        def update(widget):
            if not widget.winfo_exists(): return
            if self.ui_font != previous_font:
                try:
                    spec = self.app.tk.splitlist(widget.cget('font'))
                    if spec and spec[0] == previous_font:
                        widget.configure(font=(self.ui_font, *spec[1:]))
                except tk.TclError: pass
                if isinstance(widget, tk.Canvas):
                    for item in widget.find_all():
                        if widget.type(item) == 'text':
                            spec = self.app.tk.splitlist(widget.itemcget(item, 'font'))
                            if spec and spec[0] == previous_font:
                                widget.itemconfigure(item, font=(self.ui_font, *spec[1:]))
            try:
                caption = widget.cget('text')
                if caption in reverse: widget.configure(text=self.tr(reverse[caption]))
            except tk.TclError: pass
            if isinstance(widget, ttk.Treeview):
                for column in widget['columns']:
                    caption = widget.heading(column, 'text')
                    if caption in reverse: widget.heading(column, text=self.tr(reverse[caption]))
            if isinstance(widget, ttk.Notebook):
                for page, key in getattr(widget, '_retro_tab_keys', {}).items():
                    widget.tab(page, text=self.tr(key))
            for child in widget.winfo_children(): update(child)
        update(self.app)
        # Section titles whose English text another key shares ("Box art").
        for name, key in (('account_frame', 'options_account'), ('covers_frame', 'options_boxart'),
                          ('disk_frame', 'options_disk_space')):
            frame = getattr(self, name, None)
            try:
                if frame is not None and frame.winfo_exists():
                    frame.configure(text=self.tr(key))
            except tk.TclError:
                pass
        self.update_account_options()
        self.render_disk_space()
        for panel in self.library_panels:
            if panel.winfo_exists(): panel.title(APP_NAME + ' - ' + self.tr('memory'))
        if self.credits_panel is not None and self.credits_panel.winfo_exists():
            self.credits_panel.title(APP_NAME + ' - ' + self.tr('credits'))
        for row, item in self.items.items():
            self.table.set(row, 'system', get_profile(item.system).name if item.system else self.tr('unknown_console'))
            self.table.set(row, 'video', self.video_display(item, self.results.get(row)))
            self.table.set(row, 'size', self.tr('size', value=item.size//1024) if item.size else '-')
            self.table.set(row, 'cover', self.tr('chosen' if item.cover else 'auto'))
            result = self.results.get(row, {})
            self.table.set(row, 'status', self.tr('same_rom', title=result['duplicate_of'])
                if self.row_status[row] == 'duplicate' and result.get('duplicate_of')
                else self.tr(self.row_status[row]))
        self.status.set(self.tr(self.status_key, **self.status_values))
        self.selection_changed()
        self.queue_background(self.header)
        self.queue_background(self.body)
        self.app.after_idle(self.layout_header)
        self.app.after_idle(self.fit_minimum_width)
        self.knowledge_button.configure(text=self.tr('knowledge') + ' \u25be')
        self.update_compiled_button()
        self.update_new_paths()
        if self.compiled_view is not None:
            self.compiled_view.localize()
            self.compiled_view.render()

    def change_language(self, event=None):
        self.language = next((code for code, name in zip(LANGUAGES, LANGUAGE_NAMES)
                              if name == self.language_name.get()), 'en')
        for hint in self.tooltips: hint.hide()
        self.refresh_language()
        try:
            save_preferences(self.preferences())
            output = Path(self.output.get()).expanduser()
            for profile in PROFILES:
                folder = system_output(output, profile.id)
                if folder.is_dir():
                    save_game_language(folder, self.language)
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def decorate_button(self, button, symbol, primary=False):
        key = (symbol, primary)
        if key not in self.button_images:
            self.button_images[key] = (
                make_icon(self.app, symbol, COLORS['gold_text'] if primary else COLORS['text']),
                make_icon(self.app, symbol, COLORS['disabled']))
        normal, disabled = self.button_images[key]
        button.configure(image=(normal, 'disabled', disabled), compound='left')

    def button(self, parent, text, command, primary=False):
        style = 'Primary.TButton' if primary else 'TButton'
        if str(parent).startswith(str(self.toolbar)):
            style = 'Toolbar.' + style
        button = ttk.Button(parent, text=text, command=command, style=style)
        symbol = {'choose_roms': 'folder', 'choose_directory': 'add_folder',
                  'remove_selected': 'remove', 'clear': 'clear', 'check_updates': 'download',
                  'show_options': 'options', 'show_credits': 'info',
                  'choose_cover': 'image', 'automatic_cover': 'auto'}.get(command.__name__)
        if symbol:
            self.decorate_button(button, symbol, primary)
        self.controls.append(button)
        key = next((key for key, pair in STRINGS.items() if text in pair and 'tip_'+key in STRINGS), None)
        if key: self.hint(button, 'tip_'+key)
        elif command == self.choose_output: self.hint(button, 'tip_output')
        return button

    def update_empty_state(self):
        if self.items:
            self.empty_state.place_forget()
        else:
            self.empty_state.place(relx=0.5, rely=0.5, y=18, anchor='center')

    def video_display(self, item: BatchItem, result: dict | None = None) -> str:
        if item.error or not item.video_hint:
            return '-'
        if item.system == 'cps1':
            return 'Arcade 59.64 Hz'
        if item.system == 'ng':
            return 'MVS Â· Europe'
        if item.standard_override:
            return self.tr('video_selected', standard=item.standard_override.upper())
        if result and result.get('video_standard'):
            return result['video_standard'].upper()
        return self.tr('video_guess', standard=item.video_hint.upper())

    def change_video(self, event=None):
        rows = self.table.selection()
        if self.busy or len(rows) != 1:
            return
        row = rows[0]
        item = self.items[row]
        selected = self.video_name.get().lower()
        item.standard_override = selected if selected in get_profile(item.system).video_modes else None
        result = self.results.get(row)
        if result and item.standard_override and result.get('video_standard') != item.standard_override:
            self.results.pop(row)
            self.row_status[row] = 'waiting'
            self.table.set(row, 'status', self.tr('waiting'))
            self.table.item(row, tags=())
        self.table.set(row, 'video', self.video_display(item, self.results.get(row)))
        self.selection_changed()

    def add_paths(self, paths):
        """Add ROMs, folders or disk sets to the queue. Once the whole addition
        is in, games that already have an export are offered for removal."""
        outer = not getattr(self, 'adding_depth', 0)
        if outer:
            self.compiled_added = []
        self.adding_depth = getattr(self, 'adding_depth', 0) + 1
        try:
            self._add_paths(paths)
        finally:
            self.adding_depth -= 1
        if outer:
            self.offer_compiled(self.compiled_added)

    def offer_compiled(self, rows):
        """Ask once whether games already compiled in the output folder stay in
        the list for a reconversion; otherwise leave them out, so the user
        need not sort a mixed folder by hand. Nothing is asked before the
        window shows (ROMs given on the command line)."""
        rows = [row for row in rows if self.table.exists(row)]
        if not rows or not self.app.winfo_viewable():
            return
        examples = ', '.join(self.items[row].title for row in rows[:3]) + ('…' if len(rows) > 3 else '')
        if self.confirm_compiled(len(rows), examples):
            return
        for row in rows:
            self.table.delete(row)
            self.items.pop(row, None)
            self.results.pop(row, None)
            self.row_status.pop(row, None)
        self.count.set(f'{len(self.items)} ROM' + ('s' if len(self.items) != 1 else ''))
        self.messages.put(('log', self.tr('already_compiled_left_out', count=len(rows))))
        self.selection_changed()

    def confirm_compiled(self, count, examples):
        return messagebox.askyesno(APP_NAME, self.tr('already_compiled', count=count, examples=examples),
                                   default='no', parent=self.app)

    def _expand_paths(self, paths, found=lambda count: None, cancel=None):
        """Files to queue from files, folders and disk sets, without Tk calls.
        A multi-disk X68000 game is one entry: its disks become one playlist."""
        from .rom_sources import disk_sets
        files, logs = [], []
        def walk(entries):
            sets = disk_sets(entries)
            if sets.grouped:
                logs.append(self.tr('x68_sets_grouped', count=sets.grouped))
            for title, missing, total in sets.incomplete:
                logs.append(self.tr('x68_set_incomplete', title=title,
                                    missing=', '.join(map(str, missing)), total=total))
            for path in sets.paths:
                if cancel is not None and cancel.is_set():
                    return
                path = Path(path)
                if path.is_dir():
                    try:
                        walk(discover_roms(path))
                    except OSError:
                        logs.append(self.tr('drop_unreadable'))
                    continue
                files.append(path)
                found(len(files))
        walk(list(paths))
        return files, logs

    def _prepare_path(self, path, mode, output):
        """Identify one ROM and read its existing export, without Tk calls."""
        item = identify(path, None if mode == 'auto' else mode)
        status = ('skipped' if item.skipped else 'unrecognized' if item.unknown
                  else 'invalid' if item.error else 'waiting')
        prepared = {'item': item, 'status': status, 'result': None}
        if item.error:
            return prepared
        folder = system_output(output, item.system)
        report_path = folder / 'datas/reports' / item.key / 'conversion-report.json'
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
            filename = report['executable']
            if Path(filename).name != filename:
                raise ValueError('Invalid executable filename in report')
            target = folder / filename
            if target.is_file() and report.get('rom', {}).get('sha256') == item.sha256:
                measured = [c.get('interpreter_percent') for c in report['final_checks']]
                pending = is_pending(target)
                prepared['result'] = dict(status='success', executable=str(target.resolve()), report=str(report_path),
                    conversion_stage=report.get('status'),
                    main_interpreted_opcodes=max((c.get('interpreted_opcodes', 0) for c in report['final_checks']), default=0),
                    audio_cpu=report.get('audio_cpu'),
                    audio_interpreted_opcodes=max((c.get('audio_interpreted_opcodes', 0) for c in report['final_checks']), default=0),
                    pending_install=pending,
                    interpreter_percent=max((p for p in measured if p is not None), default=None),
                    interpreter_cycles=max((c.get('interpreter_cycles', 0) for c in report['final_checks']), default=0),
                    reference_vdp_trace_match=report.get('reference_vdp_trace_match'),
                    video_standard=report.get('video_model', {}).get('standard', item.video_hint))
                prepared['status'] = ('pending_install' if pending else
                                      'created_experimental' if report.get('status') == 'experimental' else 'created')
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        return prepared

    def _insert_prepared(self, prepared):
        item, status, result = prepared['item'], prepared['status'], prepared['result']
        row = self.table.insert('', 'end', values=(item.title,
            get_profile(item.system).name if item.system else self.tr('unknown_console'),
            self.video_display(item, result),
            self.tr('size', value=item.size//1024) if item.size else '-',
            self.tr('auto'), self.tr(status)),
            tags=('error',) if item.error else ('success',) if result else ())
        self.items[row] = item
        self.row_status[row] = status
        if result:
            self.results[row] = result
            self.compiled_added.append(row)
        return row

    def _finish_adding(self):
        self.count.set(f'{len(self.items)} ROM' + ('s' if len(self.items) != 1 else ''))
        self.update_empty_state()
        self.app.after_idle(self.fit_minimum_width)

    def _add_paths(self, paths):
        files, logs = self._expand_paths(paths)
        for line in logs:
            self.messages.put(('log', line))
        existing = {item.path for item in self.items.values()}
        output = Path(self.output.get()).expanduser()
        for path in files:
            if path.resolve() in existing:
                continue
            prepared = self._prepare_path(path, self.system_mode, output)
            self._insert_prepared(prepared)
            existing.add(prepared['item'].path)
        self._finish_adding()

    def import_paths(self, paths):
        """Add files or folders from the window: folders are walked and ROMs
        read in a worker, with a progress bar, so a slow computer never looks
        frozen. A few plain files are added at once."""
        paths = [Path(path) for path in paths]
        if not paths:
            return
        if len(paths) <= 8 and not any(path.is_dir() for path in paths):
            before = len(self.items)
            self.add_paths(paths)
            self.set_status('drop_added', count=len(self.items) - before)
            return
        self.importing = True
        self.cancel.clear()
        self.set_controls(False)
        self.compiled_added = []
        before = len(self.items)
        mode, output = self.system_mode, Path(self.output.get()).expanduser()
        existing = {item.path for item in self.items.values()}
        state = {'found': 0, 'total': 0, 'done': 0, 'ready': [], 'logs': [], 'finished': False}
        self.progress.configure(mode='indeterminate', value=0)
        self.progress.start(12)
        self.set_status('import_scanning', count=0)

        def worker():
            try:
                files, logs = self._expand_paths(paths, lambda count: state.update(found=count), self.cancel)
                state['logs'] = logs
                state['total'] = len(files)
                for path in files:
                    if self.cancel.is_set():
                        break
                    try:
                        if path.resolve() not in existing:
                            prepared = self._prepare_path(path, mode, output)
                            existing.add(prepared['item'].path)
                            state['ready'].append(prepared)
                    except OSError:
                        pass
                    state['done'] += 1
            finally:
                state['finished'] = True

        def poll():
            ready, state['ready'] = state['ready'], []
            for prepared in ready:
                self._insert_prepared(prepared)
            if state['total']:
                if str(self.progress.cget('mode')) != 'determinate':
                    self.progress.stop()
                    self.progress.configure(mode='determinate', maximum=state['total'])
                self.progress.configure(value=state['done'])
                self.set_status('import_reading', done=state['done'], total=state['total'])
            else:
                self.set_status('import_scanning', count=state['found'])
            if ready:
                self._finish_adding()
            if not state['finished'] or state['ready']:
                self.app.after(80, poll)
                return
            self.progress.stop()
            self.progress.configure(mode='determinate', value=0)
            for line in state['logs']:
                self.messages.put(('log', line))
            self._finish_adding()
            self.importing = False
            self.set_controls(True)
            self.set_status('drop_added', count=len(self.items) - before)
            self.offer_compiled(self.compiled_added)

        threading.Thread(target=worker, daemon=True).start()
        poll()

    def choose_roms(self):
        paths = filedialog.askopenfilenames(title=self.tr('pick_roms'), initialdir=ROOT / 'ROMS',
            filetypes=[('ROM files', '*.sms *.gg *.gb *.zip *.bin *.rom *.gbc *.gba *.nes *.sfc *.smc *.md *.gen *.pce *.dim *.xdf *.m3u'),
                       ('All files', '*.*')])
        self.import_paths(paths)

    def choose_directory(self):
        path = filedialog.askdirectory(title=self.tr('pick_folder'), initialdir=ROOT / 'ROMS')
        if path:
            self.import_paths([Path(path)])

    def select_all_rows(self):
        self.table.selection_set(self.table.get_children())

    def queue_menu(self, event):
        """Right-click on the queue: the row's actions, then list housekeeping.
        Removing rows never touches the ROM files, and the label says so."""
        row = self.table.identify_row(event.y)
        if row and row not in self.table.selection():
            self.table.selection_set(row)
            self.table.focus(row)
        rows = self.table.selection()
        if not rows:
            return
        one = len(rows) == 1
        item = self.items.get(rows[0]) if one else None
        result = self.results.get(rows[0], {}) if one else {}
        free = not self.busy and not self.updating
        def state(enabled):
            return 'normal' if enabled else 'disabled'
        colors = dict(bg=COLORS['button'], fg=COLORS['text'], activebackground=COLORS['selected'],
                      activeforeground=COLORS['gold_hover'])
        menu = tk.Menu(self.app, tearoff=False, **colors)
        playable = (one and free and result.get('status') in ('success', 'existing', 'current')
                    and not result.get('pending_install'))
        menu.add_command(label=self.tr('play'), command=self.play, state=state(playable))
        menu.add_command(label=self.tr('start_selected'), command=lambda: self.start(selected=True), state=state(free))
        if any(self.row_status.get(row) in ('error', 'stopped') for row in rows):
            menu.add_command(label=self.tr('retry'), command=self.retry_failed, state=state(free))
        menu.add_separator()
        menu.add_command(label=self.tr('choose_cover'), command=self.choose_cover, state=state(one and free))
        menu.add_command(label=self.tr('auto_cover'), command=self.automatic_cover, state=state(free))
        if item is not None and not item.error:
            video = tk.Menu(menu, tearoff=False, **colors)
            for label in (self.tr('auto'), *(mode.upper() for mode in get_profile(item.system).video_modes)):
                video.add_radiobutton(label=label, variable=self.video_name, value=label, command=self.change_video)
            menu.add_cascade(label=self.tr('video_timing'), menu=video, state=state(free))
        menu.add_separator()
        menu.add_command(label=self.tr('open_rom_folder'), state=state(item is not None),
                         command=lambda: item and open_local(item.path.parent))
        executable = result.get('executable')
        menu.add_command(label=self.tr('open_game_folder'), state=state(bool(executable)),
                         command=lambda: executable and open_local(Path(executable).parent))
        menu.add_separator()
        menu.add_command(label=self.tr('remove_from_list', count=len(rows)), command=self.remove_selected,
                         state=state(free))
        menu.add_command(label=self.tr('clear'), command=self.clear, state=state(free))
        menu.add_command(label=self.tr('select_all'), command=self.select_all_rows)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def remove_selected(self):
        if self.busy:
            return
        for row in self.table.selection():
            if self.recovered_batch is not None:
                journal=self.recovered_batch
                for index,saved in enumerate(journal.definition['items']):
                    if saved['path']==str(self.items[row].path):
                        try:journal.result(index,{'status':'removed'})
                        except OSError:pass
            self.table.delete(row)
            self.items.pop(row, None)
            self.results.pop(row, None)
            self.row_status.pop(row, None)
        self.add_paths([])
        self.selection_changed()

    def clear(self):
        self.table.selection_set(self.table.get_children())
        self.remove_selected()

    def choose_output(self):
        path = filedialog.askdirectory(title=self.tr('pick_output'), initialdir=self.output.get())
        if path:
            self.output.set(path)
            self.custom_output_path = Path(path)
            self.reload_queue()

    def choose_cover(self):
        rows = self.table.selection()
        if len(rows) != 1:
            messagebox.showinfo(APP_NAME, self.tr('one_cover'))
            return
        path = filedialog.askopenfilename(title=self.tr('pick_cover'), initialdir=ROOT / 'BoxArt', filetypes=[(self.tr('images'), '*.png *.jpg *.jpeg *.webp *.bmp *.ico')])
        if path:
            self.items[rows[0]].cover = Path(path)
            self.table.set(rows[0], 'cover', self.tr('chosen'))
            self.use_cover.set(True)
            self.selection_changed()

    def automatic_cover(self):
        for row in self.table.selection():
            self.items[row].cover = None
            self.table.set(row, 'cover', self.tr('auto'))
        self.selection_changed()

    def selection_changed(self):
        rows = self.table.selection()
        self.selected_button.configure(state='normal' if rows and not self.busy and not self.updating else 'disabled')
        result = self.results.get(rows[0], {}) if len(rows) == 1 else {}
        self.play_button.configure(state='normal' if not self.busy and result.get('status') in ('success', 'existing', 'current') and not result.get('pending_install') else 'disabled')
        item = self.items[rows[0]] if len(rows) == 1 else None
        if item and not item.error:
            self.video_field.configure(values=(self.tr('auto'),
                *(mode.upper() for mode in get_profile(item.system).video_modes)))
        self.video_name.set((item.standard_override.upper() if item and item.standard_override
                             else self.tr('auto')))
        self.video_field.configure(state='readonly' if item and not item.error and not self.busy else 'disabled')
        if len(rows) == 1:
            text = log_text(item.error or result.get('message') or str(item.path), self.language)
            if result.get('status') == 'duplicate' and result.get('duplicate_of'):
                text = self.tr('same_rom', title=result['duplicate_of'])
            elif result.get('status') == 'existing':
                text = self.tr('existing')
            if item.cover:
                text += f" Â· {self.tr('cover')}: {item.cover.name}"
            if result.get('status') == 'success':
                comparison = result.get('reference_vdp_trace_match')
                if item.system in ('md', 'snes', 'ng', 'cps1'):
                    text = self.tr('fallback16', opcodes=result.get('main_interpreted_opcodes', 0),
                        audio_opcodes=result.get('audio_interpreted_opcodes', 0))
                elif result.get('interpreter_percent') is None or comparison is None:
                    text = self.tr('fallback_cycles', cycles=result.get('interpreter_cycles', 0))
                else:
                    text = self.tr('fallback', percent=result['interpreter_percent'],
                                   comparison=self.tr('vdp_equal' if comparison else 'vdp_different'))
            text += ' Â· ' + self.video_display(item, result)
            self.detail.set(text)
        else:
            self.detail.set(self.tr('shared'))

    def preferences(self):
        return dict(language=self.language, coverage_default_revision=2,
            gb_validation_default_revision=1,
            output=self.output.get(), custom_output=self.custom_output.get(),
            system_mode=self.system_mode, platform=self.platform_id,
            backend='banked' if self.extended.get() else 'functions',
            gb_deep_validation=self.gb_deep_validation.get(),
            console_scan=self.console_scan_preferences(),
            passes=self.passes.get(), frames=self.frames.get(), jobs=self.jobs.get(),
            use_cover=self.use_cover.get(),
            online_cover=self.online.get(), icon_tags=self.icon_tags.get(),
            use_shared_base=self.use_shared_base.get(), send_after_batch=self.send_after_batch.get(),
            overwrite=self.overwrite.get(), force=self.force.get(), ng_bios=self.ng_bios.get(),
            x68_ipl=self.x68_ipl.get(),x68_cgrom=self.x68_cgrom.get(),x68_ram=self.x68_ram.get(),
            feedback_paths={system: value.get().strip() for system, value in self.feedback_paths.items() if value.get().strip()},
            rom_paths={system:value.get().strip() for system,value in self.rom_paths.items() if value.get().strip()})

    def console_scan_preferences(self):
        """Per-console scan entries; empty pass/frame fields follow the shared values."""
        settings = {}
        for console, level in self.scan_level.items():
            entry = {}
            if level.get() != 'standard':
                entry['level'] = level.get()
            for key, variables, limit in (('passes', self.scan_passes, 10), ('frames', self.scan_frames, 10000)):
                text = variables[console].get().strip()
                if not text:
                    continue
                try:
                    value = int(text)
                except ValueError:
                    raise ValueError(self.tr('invalid_limits')) from None
                if not 1 <= value <= limit:
                    raise ValueError(self.tr('invalid_limits'))
                entry[key] = value
            if entry:
                settings[console] = entry
        return settings

    def build_scan_options(self, page, console):
        """Scan level, pass limit and frame budget for one console, with a short
        note on what is recommended and why."""
        from .scan_levels import LEVELS
        section = ttk.LabelFrame(page, text=self.tr('scan_section'), padding=10)
        section.pack(fill='x', pady=(0, 12))
        ttk.Label(section, text=self.tr('scan_note_' + console), style='Muted.TLabel',
                  wraplength=840, justify='left').pack(anchor='w', pady=(0, 8))
        row = ttk.Frame(section)
        row.pack(anchor='w')
        labels = {level: self.tr('scan_' + level) for level in LEVELS}
        shown = tk.StringVar(value=labels[self.scan_level[console].get()])
        ttk.Label(row, text=self.tr('scan_level')).grid(row=0, column=0, sticky='w', padx=(0, 22))
        level_box = ttk.Combobox(row, textvariable=shown, values=list(labels.values()), width=16, state='readonly')
        level_box.grid(row=1, column=0, sticky='w', padx=(0, 22), pady=(5, 0))

        def pick(_event=None, console=console, shown=shown, labels=labels):
            for level, label in labels.items():
                if label == shown.get():
                    self.scan_level[console].set(level)
        level_box.bind('<<ComboboxSelected>>', pick)
        self.option_controls.append((level_box, 'readonly'))
        self.hint(level_box, 'tip_scan_level')
        for column, (key, variables, limit, shared) in enumerate((
                ('scan_passes', self.scan_passes, 10, self.passes.get()),
                ('scan_frames', self.scan_frames, 10000, self.frames.get())), start=1):
            ttk.Label(row, text=self.tr(key, default=shared)).grid(row=0, column=column, sticky='w', padx=(0, 22))
            control = ttk.Spinbox(row, textvariable=variables[console], from_=1, to=limit, width=8)
            control.grid(row=1, column=column, sticky='w', padx=(0, 22), pady=(5, 0))
            self.option_controls.append((control, 'normal'))
            self.hint(control, 'tip_' + key)

    def start(self, selected=False):
        if self.busy or self.updating or getattr(self, 'importing', False):
            return
        if not self.ensure_build_tools(lambda: self.start(selected)):
            return
        chosen_rows = [row for row in self.table.get_children()
                       if not selected or row in self.table.selection()]
        if not chosen_rows:
            messagebox.showinfo(APP_NAME, self.tr('need_rom'))
            return
        try:
            options = self.preferences()
            if (not 1 <= options['passes'] <= 10 or not 1 <= options['frames'] <= 10000
                    or not 1 <= options['jobs'] <= 8):
                raise ValueError(self.tr('invalid_limits'))
            if not self.output.get().strip():
                raise ValueError(self.tr('need_output'))
            output = Path(options.pop('output')).expanduser().resolve()
            options.pop('coverage_default_revision')
            options.pop('gb_validation_default_revision')
            options.pop('custom_output')
            options.pop('system_mode')
            options.pop('platform')
            options.pop('feedback_paths')
            options.pop('rom_paths')
            use_shared = options.pop('use_shared_base', False)
            options.pop('send_after_batch', None)
            if any(self.items[row].system == 'ng' and not self.items[row].error for row in chosen_rows):
                from .neogeo import validate_bios
                bios = selected_bios_path(options.get('ng_bios'))
                if bios is None:
                    raise ValueError(self.tr('ng_bios_required'))
                try:
                    validate_bios(bios)
                except ValueError as exc:
                    raise ValueError(self.tr('ng_bios_invalid', error=str(exc))) from exc
            for row in chosen_rows:
                if self.items[row].system == 'x68' and not self.items[row].error:
                    from .x68000 import machine
                    machine(self.items[row].path,options.get('x68_ipl'),options.get('x68_cgrom'),options.get('x68_ram',2))
            save_preferences(self.preferences())
        except (ValueError, tk.TclError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.busy = True
        self.cancel.clear()
        self.active_rows = chosen_rows
        self.running_jobs.clear()
        self.completed_jobs = 0
        items = [self.items[row] for row in self.active_rows]
        for row in self.active_rows:
            self.table.set(row, 'status', self.tr('waiting'))
            self.row_status[row] = 'waiting'
        self.progress.configure(value=0, maximum=len(items))
        self.log.configure(state='normal')
        self.log.delete('1.0', 'end')
        self.log.configure(state='disabled')
        self.set_controls(False)
        self.set_status('starting', count=len(items))
        recovered=self.recovered_batch
        inventory_preferences=self.preferences()
        # A selected-only conversion must leave the other recovered rows
        # recoverable, including after a later window close or crash.
        recovered_indices={}
        if recovered is not None:
            for index,row in enumerate(recovered.definition['items']):
                if str(index) not in recovered.done:
                    recovered_indices.setdefault(row['path'],[]).append(index)
        def worker():
            journal=None
            try:
                from .queue_state import BatchJournal
                try:
                    journal=BatchJournal.create(data_directory()/'pending-batches',items,output)
                except (OSError,ValueError):
                    self.messages.put(('log',self.tr('queue_save_failed')))
                checkpoint_failed=False
                def event(kind,index,value):
                    nonlocal checkpoint_failed
                    if kind=='result' and not checkpoint_failed:
                        try:
                            if journal is not None:journal.result(index,value)
                            if recovered is not None:
                                for saved_index in recovered_indices.get(str(items[index].path),[]):
                                    recovered.result(saved_index,value)
                        except OSError:
                            checkpoint_failed=True
                            self.messages.put(('log',self.tr('queue_save_failed')))
                    if kind=='result':self.remember_export(value,inventory_preferences)
                    self.messages.put((kind,index,value))
                # The shared base's paths for these ROMs join the imported
                # banks first; each conversion checks them again.
                shared = self.prepare_shared_paths([f'{item.system}:{item.sha256}' for item in items
                                                    if item.system and item.sha256 and not item.error], use_shared)
                record = convert_batch(items, output, cancel=self.cancel, **options, shared_paths=shared,
                    emit=lambda text: self.messages.put(('log', text)),
                    on_event=event)
                self.forget_rejected_shared(shared, record['games'])
                if journal is not None:
                    try:journal.finish(record)
                    except OSError:self.messages.put(('log',self.tr('queue_save_failed')))
                if recovered is not None and not recovered.pending_items():
                    try:
                        recovered.discard();self.recovered_batch=None
                    except OSError:self.messages.put(('log',self.tr('queue_save_failed')))
                for folder in {Path(game['executable']).parent for game in record['games']
                               if game['status'] == 'success'}:
                    save_game_language(folder, self.language)
                self.messages.put(('done', record))
            except Exception as exc:
                self.messages.put(('fatal', str(exc)))
            finally:
                if journal is not None:journal.close()
        threading.Thread(target=worker, daemon=True).start()

    def set_controls(self, enabled):
        for control in self.controls:
            control.configure(state='normal' if enabled else 'disabled')
        if self.options_panel is not None and self.options_panel.winfo_exists():
            for control, active_state in self.option_controls:
                control.configure(state=active_state if enabled else 'disabled')
            for system in self.feedback_importing:
                self.feedback_import_buttons[system].configure(state='disabled')
        # The credits stay open to visitors during a batch; the compiled games,
        # the help, the leaderboard and the account are not managed here.
        self.credits_button.configure(state='normal')
        self.start_button.configure(state='normal' if enabled else 'disabled')
        self.stop_button.configure(state='disabled' if enabled else 'normal')
        self.update_retry_button()
        self.language_field.configure(state='readonly' if enabled else 'disabled')
        self.system_field.configure(state='readonly' if enabled else 'disabled')
        self.update_output_controls()
        self.selection_changed()
        self.update_new_paths()
        self.render_disk_space()

    def icon_button(self, parent, name, tip, command, symbol, *, managed=True):
        """A toolbar button showing only its picture; its hint starts with
        its name. Managed buttons follow set_controls like the others."""
        button = ttk.Button(parent, text=self.tr(name), command=command, style='Toolbar.TButton')
        self.decorate_button(button, symbol)
        button.configure(compound='image')
        if managed:
            self.controls.append(button)
        self.tooltips.append(Tooltip(button, lambda: self.tr(name).rstrip('…') + '\n' + self.tr(tip)))
        return button

    def new_paths_button(self, parent):
        button = ttk.Button(parent, command=self.recompile_new_paths, style='Toolbar.TButton')
        self.decorate_button(button, 'new_paths')
        self.hint(button, 'tip_recompile_new_paths')
        self.new_paths_buttons.append(button)
        self.update_new_paths()
        return button

    def games_with_new_paths(self, shared_only=False):
        """Games whose saved gameplay hints are newer than their conversion."""
        from .platforms import target_id
        from .knowledge_build import SYSTEMS as SHARED
        return [game for game in self.compiled_inventory.snapshot()
                if game.status == 'new_hints' and game.target in ('', target_id())
                and (not shared_only or game.system in SHARED)]

    def update_new_paths(self):
        count = len(self.games_with_new_paths())
        for button in getattr(self, 'new_paths_buttons', []):
            if button.winfo_exists():
                button.configure(text=self.tr('recompile_new_paths', count=count),
                                 state='normal' if count and not self.busy and not self.updating else 'disabled')

    def quiet_refresh_collection(self, games=None, every=0):
        """Re-read only collection rows whose files changed, in the background;
        Scan games stays available for new folders and moved games."""
        if (self.collection_refreshing or self.busy or self.updating
                or time.monotonic() - self.collection_refreshed_at < every):
            return
        self.collection_refreshing, self.collection_refreshed_at = True, time.monotonic()
        preferences = self.preferences()
        def worker():
            from .compiled_games import refresh_changed
            try:changed = refresh_changed(self.compiled_inventory, preferences, games)
            except Exception:changed = 0
            self.messages.put(('collection_quiet', changed))
        threading.Thread(target=worker, daemon=True).start()

    def recompile_new_paths(self, games=None):
        """Reconvert only the games with new paths (upgrading when nothing else
        changed); games whose ROM cannot be found are left for later."""
        if self.busy or self.updating:return
        games = self.games_with_new_paths() if games is None else games
        if not games:return
        self.skip_missing_sources = True
        if not self.collection_visible:self.toggle_compiled_games()
        self.reconvert_games(games)

    def stop(self):
        """Stop at once: no more games start, and the build or validation
        processes of the running conversions are killed. Nothing is published
        before a conversion ends, so earlier exports stay as they were."""
        if not self.busy or self.cancel.is_set():
            return False
        if not messagebox.askyesno(APP_NAME, self.tr('stop_confirm'), icon='warning', default='no', parent=self.app):
            return False
        if not self.busy:
            return False
        self.cancel.set()
        from .core import stop_processes
        stop_processes()
        self.stop_button.configure(state='disabled')
        self.set_status('stopping')
        return True

    def failed_rows(self):
        return [row for row in self.table.get_children() if self.row_status.get(row) in ('error', 'stopped')]

    def update_retry_button(self):
        self.retry_button.configure(state='normal' if self.failed_rows() and not self.busy and not self.updating
                                    else 'disabled')

    def retry_failed(self):
        rows = self.failed_rows()
        if not rows or self.busy:
            return
        self.table.selection_set(rows)
        self.start(selected=True)

    def check_updates(self):
        """Only the button starts a network request; startup never checks."""
        if self.busy or self.updating:
            return
        self.updating = True
        self.update_button.configure(state='disabled')
        self.set_status('checking_updates')
        def worker():
            try:
                from .updater import check_for_update
                self.messages.put(('update_check', check_for_update()))
            except Exception as exc:
                self.messages.put(('update_error', exc))
        threading.Thread(target=worker, daemon=True).start()

    def _offer_update(self, update):
        self.updating = False
        self.update_button.configure(state='normal')
        self.set_status('ready')
        if update is None:
            messagebox.showinfo(APP_NAME, self.tr('update_current'))
            return
        if not getattr(sys, 'frozen', False):
            messagebox.showinfo(APP_NAME, self.tr('update_source', version=update.version,
                                                 page=update.page))
            return
        question = self.tr('update_available', version=update.version,
                           megabytes=round(update.size / 1048576, 1))
        accepted = (self.update_dialog(update, question) if update.notes
                    else messagebox.askyesno(APP_NAME, question))
        if not accepted:
            return
        self.updating = True
        self.update_button.configure(state='disabled')
        self.start_button.configure(state='disabled')
        self.set_status('downloading_update', version=update.version)
        def worker():
            try:
                from .updater import prepare_update
                self.messages.put(('update_ready', *prepare_update(update, Path(sys.executable))))
            except Exception as exc:
                self.messages.put(('update_error', exc))
        threading.Thread(target=worker, daemon=True).start()

    def update_dialog(self, update, question):
        """The update question with what changed since the installed version.
        The notes are the published release notes, in English only; the two
        buttons answer the localized question. True when the download is chosen."""
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.transient(self.app)
        chosen = tk.BooleanVar(value=False)
        body = tk.Frame(window, bg=background, padx=18, pady=14,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=question, bg=background, fg=COLORS['text'], font=(self.ui_font, 10),
                 wraplength=560, justify='left').pack(anchor='w')
        tk.Label(body, text="What's new", bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).pack(anchor='w', pady=(12, 4))
        frame = tk.Frame(body, bg=background)
        frame.pack(fill='both', expand=True)
        text = tk.Text(frame, width=72, height=18, wrap='word', bg=COLORS['field'], fg=COLORS['text'],
                       font=(self.ui_font, 9), relief='flat', padx=10, pady=8,
                       highlightthickness=1, highlightbackground=COLORS['border'])
        bar = ttk.Scrollbar(frame, orient='vertical', command=text.yview)
        text.configure(yscrollcommand=bar.set)
        text.insert('1.0', update.notes)
        text.configure(state='disabled')
        text.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        buttons = tk.Frame(body, bg=background)
        buttons.pack(fill='x', pady=(12, 0))
        ttk.Button(buttons, text='Later', command=window.destroy).pack(side='right')
        go = ttk.Button(buttons, text='Download and restart', style='Primary.TButton',
                        command=lambda: (chosen.set(True), window.destroy()))
        go.pack(side='right', padx=(0, 8))
        window.bind('<Escape>', lambda event: window.destroy())
        window.bind('<Return>', lambda event: go.invoke())
        window.update_idletasks()
        center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        window.minsize(520, 360)
        window.deiconify()
        window.grab_set()
        go.focus_set()
        self.app.wait_window(window)
        return chosen.get()

    def _start_prepared_update(self, job_dir: Path, token: str):
        from .updater import discard_update, start_update_helper
        try:
            start_update_helper(job_dir, token)
        except Exception as exc:
            try:
                discard_update(job_dir, Path(sys.executable))
            except OSError:
                pass
            self._update_error(str(exc))
            return
        try:
            save_preferences(self.preferences())
        except (OSError, tk.TclError, ValueError):
            pass
        if self.recovered_batch is not None:self.recovered_batch.close()
        self.app.destroy()

    def _update_error(self, error: Exception | str):
        self.updating = False
        self.update_button.configure(state='normal')
        self.start_button.configure(state='normal')
        self.set_status('ready')
        messagebox.showerror(APP_NAME, update_error_text(error, self.language))

    def drain(self):
        try:
            while True:
                event = self.messages.get_nowait()
                kind = event[0]
                if kind == 'log':
                    self.log.configure(state='normal')
                    self.log.insert('end', event[1] + '\n')
                    self.log.see('end')
                    self.log.configure(state='disabled')
                    if self.compiled_view is not None:self.compiled_view.show_log(event[1])
                elif kind == 'drop':
                    self.drop_paths(event[1])
                elif kind == 'drop_blocked':
                    self.messages.put(('log', self.tr('drop_blocked')))
                elif kind == 'raise':
                    # A second start of this installation: show this window.
                    self.app.deiconify()
                    self.app.lift()
                    self.app.focus_force()
                    self.app.attributes('-topmost', True)
                    self.app.after(300, lambda: self.app.attributes('-topmost', False))
                elif kind == 'drop_error':
                    self.messages.put(('log', self.tr('drop_unavailable')))
                elif kind == 'start':
                    row = self.active_rows[event[1]]
                    self.running_jobs.add(event[1])
                    self.table.set(row, 'status', self.tr('converting'))
                    self.row_status[row] = 'converting'
                    self.table.see(row)
                    if not self.cancel.is_set():
                        self.set_status('batch_running', completed=self.completed_jobs,
                                        total=len(self.active_rows), active=len(self.running_jobs))
                elif kind == 'result':
                    row, result = self.active_rows[event[1]], event[2]
                    self.running_jobs.discard(event[1])
                    self.completed_jobs += 1
                    if result['status'] in ('existing', 'current') and self.results.get(row, {}).get('status') == 'success':
                        result = {**self.results[row], **result}
                    self.results[row] = result
                    self.table.set(row, 'video', self.video_display(self.items[row], result))
                    status_key = {'success': 'created', 'error': 'error', 'stopped': 'stopped',
                                  'duplicate': 'duplicate', 'unrecognized': 'unrecognized',
                                  'skipped': 'skipped', 'existing': 'existing', 'current': 'current'}[result['status']]
                    if result['status'] == 'success' and result.get('conversion_stage') == 'experimental':
                        status_key = 'created_experimental'
                    text = (self.tr('same_rom', title=result['duplicate_of'])
                            if result['status'] == 'duplicate' and result.get('duplicate_of')
                            else self.tr(status_key))
                    self.row_status[row] = status_key
                    if result.get('pending_install'):
                        self.row_status[row] = 'pending_install'
                        text = self.tr('pending_install')
                    self.table.set(row, 'status', text)
                    self.table.item(row, tags=('error',) if result['status'] in ('error', 'unrecognized', 'skipped') else (result['status'],))
                    self.progress.configure(value=self.completed_jobs)
                    if not self.cancel.is_set():
                        self.set_status('batch_running', completed=self.completed_jobs,
                                        total=len(self.active_rows), active=len(self.running_jobs))
                    self.selection_changed()
                elif kind in ('done', 'fatal'):
                    self.busy = False
                    from .core import reset_stop
                    reset_stop()
                    for index in self.running_jobs:
                        row = self.active_rows[index]
                        self.row_status[row] = 'waiting'
                        self.table.set(row, 'status', self.tr('waiting'))
                    self.running_jobs.clear()
                    if self.close_when_idle:
                        self.close()
                        return
                    self.set_controls(True)
                    if kind == 'fatal':
                        self.set_status('fatal', error=log_text(event[1], self.language))
                    else:
                        record = event[1]
                        self.set_status('summary', **record)
                        self.announce_finished(record)
                        self.send_new_discoveries()
                elif kind == 'update_check':
                    self._offer_update(event[1])
                elif kind == 'update_ready':
                    self._start_prepared_update(event[1], event[2])
                    return
                elif kind == 'update_error':
                    self._update_error(event[1])
                elif kind == 'feedback_import':
                    system, report, error = event[1:]
                    self.feedback_importing.discard(system)
                    button = self.feedback_import_buttons.get(system)
                    if button is not None and button.winfo_exists():
                        button.configure(state='disabled' if self.busy or self.updating else 'normal')
                    if error:
                        self.feedback_status[system].set(self.tr('feedback_import_error'))
                        self.messages.put(('log', f'Gameplay feedback ({system}): {error}'))
                    else:
                        self.feedback_status[system].set(self.tr('feedback_import_summary',
                            **report, kib=report['bytes']/1024))
                elif kind == 'disk_space_measured':
                    token, projects, error = event[1:]
                    # Only the latest measurement of the open options counts.
                    if token is getattr(self, 'disk_cancel', None) and not token.is_set():
                        self.disk_state = ({'phase': 'error', 'error': error} if error else
                                           {'phase': 'measured', 'projects': projects})
                        self.render_disk_space()
                elif kind == 'disk_space_freed':
                    outcome, error = event[1:]
                    self.busy = False
                    self.set_controls(True)
                    self.disk_state = ({'phase': 'error', 'error': error} if error else
                                       {'phase': 'done', 'outcome': outcome})
                    self.render_disk_space()
                elif kind == 'collection_changed':
                    if self.compiled_view is not None:self.compiled_view.render()
                elif kind == 'knowledge_done':
                    self.knowledge_done(event[1], event[2])
                elif kind == 'player':
                    self.render_player(event[1])
                elif kind == 'sources_ready':
                    self.finish_source_lookup(event[1])
                elif kind == 'collection_quiet':
                    self.collection_refreshing = False
                    if event[1] and self.compiled_view is not None:self.compiled_view.render()
                    self.update_new_paths()
                elif kind == 'collection_done':
                    self.busy = False
                    self.skip_missing_sources = False
                    self.set_controls(True)
                    if self.compiled_view is not None:
                        self.compiled_view.progress.stop()
                        self.compiled_view.render()
                        summary=self.tr('reconvert_summary', **event[1])
                        if event[1].get('detail'):summary+=' · '+event[1]['detail']
                        self.compiled_view.status.set(summary)
                    if self.close_when_idle:
                        self.close()
                        return
                    self.send_new_discoveries()
                elif kind == 'auto_sent':
                    self.auto_sent(event[1], event[2])
        except queue.Empty:
            pass
        for row, result in self.results.items():
            if result.get('pending_install') and not is_pending(Path(result['executable'])):
                result['pending_install'] = False
                self.row_status[row] = 'created'
                self.table.set(row, 'status', self.tr('created'))
                self.selection_changed()
        self.app.after(100, self.drain)

    def play(self):
        rows = self.table.selection()
        if self.busy or len(rows) != 1:
            return
        if self.results.get(rows[0], {}).get('pending_install'):
            self.set_status('pending_install')
            return
        executable = self.results.get(rows[0], {}).get('executable')
        if executable:
            path = Path(executable)
            try:
                subprocess.Popen([str(path)], cwd=path.parent)
            except OSError as exc:
                messagebox.showerror(APP_NAME, str(exc))

    def open_output(self):
        path = Path(self.output.get()).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        open_local(path)

    def show_options(self):
        if self.busy:
            return
        if self.options_panel is not None and self.options_panel.winfo_exists():
            self.close_options()
            return
        if self.collection_visible:
            self.toggle_compiled_games()
        # The options live inside the main window, in place of the queue, like
        # the compiled-games view: no second window to find or close.
        panel = ttk.Frame(self.body)
        self.options_panel = panel
        self.option_controls = []
        self.option_tooltips_start = len(self.tooltips)
        for widget in self.compiler_widgets:
            widget.grid_remove()
        self.queue_actions.pack_forget()
        self.body.rowconfigure(1, weight=1, minsize=100)
        self.body.rowconfigure(7, weight=0, minsize=0)
        # Same side margins as the queue table and the log below it.
        panel.grid(row=1, column=0, rowspan=7, sticky='nsew', padx=24, pady=(0, 12))
        try:
            self.options_button.state(['selected'])
        except (AttributeError, tk.TclError):
            pass

        notebook = ttk.Notebook(panel)
        notebook._retro_tab_keys = {}
        notebook.pack(fill='both', expand=True, padx=0, pady=(6, 4))

        # Every tab scrolls when the window is shorter than its content: a
        # light scrollbar appears, and the wheel scrolls anywhere on the page.
        self.option_scrollers = []
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            panel.bind_all(sequence, self.options_wheel)

        def tab(key):
            page = ttk.Frame(notebook)
            notebook.add(page, text=self.tr(key))
            notebook._retro_tab_keys[str(page)] = key
            return self.scrolled_page(page)

        def checkbox(parent, key, variable, hint):
            control = ttk.Checkbutton(parent, text=self.tr(key), variable=variable)
            control.pack(anchor='w', pady=(0, 8))
            self.option_controls.append((control, 'normal'))
            self.hint(control, hint)
            return control

        # Common holds the shared settings, the account and box art.
        common = tab('options_common')
        common.columnconfigure(0, weight=1)
        ttk.Label(common, text=self.tr('output')).grid(row=0, column=0, sticky='w', pady=(0, 8))
        self.custom_output_control = ttk.Checkbutton(common, text=self.tr('custom_output'),
            variable=self.custom_output, command=self.change_output_mode)
        self.custom_output_control.grid(row=1, column=0, sticky='w', pady=(0, 8))
        self.option_controls.append((self.custom_output_control, 'normal'))
        self.hint(self.custom_output_control, 'tip_custom_output')
        output_row = ttk.Frame(common)
        output_row.grid(row=2, column=0, sticky='ew', pady=(0, 16))
        output_row.columnconfigure(0, weight=1)
        self.output_field = ttk.Entry(output_row, textvariable=self.output)
        self.output_field.grid(row=0, column=0, sticky='ew')
        self.output_field.bind('<FocusOut>', lambda event: self.reload_queue())
        self.hint(self.output_field, 'tip_output')
        self.output_browse = ttk.Button(output_row, text=self.tr('browse'), command=self.choose_output)
        self.output_browse.grid(row=0, column=1, padx=(8, 0))
        self.hint(self.output_browse, 'tip_output')
        self.update_output_controls()

        shared = ttk.Frame(common)
        shared.grid(row=3, column=0, sticky='w')
        self.icon_tags_control = None
        for key, variable, hint in (('icon', self.use_cover, 'tip_icon'),
                                     ('icon_tags', self.icon_tags, 'tip_icon_tags'),
                                     ('online', self.online, 'tip_online'),
                                     ('overwrite', self.overwrite, 'tip_overwrite'),
                                     ('force', self.force, 'tip_force')):
            control = checkbox(shared, key, variable, hint)
            if key == 'icon_tags':
                self.icon_tags_control = control

        limits = ttk.Frame(common)
        limits.grid(row=4, column=0, sticky='w', pady=(12, 0))
        for column, (key, variable, hint, limit, kind) in enumerate((
                ('passes', self.passes, 'tip_passes', 10, 'combo'),
                ('frames', self.frames, 'tip_frames', 10000, 'spin'),
                ('jobs', self.jobs, 'tip_jobs', 8, 'spin'))):
            ttk.Label(limits, text=self.tr(key)).grid(row=0, column=column, sticky='w', padx=(0, 22))
            control = (ttk.Combobox(limits, textvariable=variable, values=list(range(1, limit + 1)),
                                     width=6, state='readonly') if kind == 'combo' else
                       ttk.Spinbox(limits, textvariable=variable, from_=1, to=limit, width=8))
            control.grid(row=1, column=column, sticky='w', padx=(0, 22), pady=(5, 0))
            self.option_controls.append((control, 'readonly' if kind == 'combo' else 'normal'))
            self.hint(control, hint)

        # The Retro-Recomp account, then box art, below the shared settings.
        account = self.account_frame = ttk.LabelFrame(common, text=self.tr('options_account'), padding=(12, 8))
        account.grid(row=5, column=0, sticky='ew', pady=(18, 0))
        self.build_account_options(account)
        covers = self.covers_frame = ttk.LabelFrame(common, text=self.tr('options_boxart'), padding=(12, 8))
        covers.grid(row=6, column=0, sticky='ew', pady=(14, 0))
        self.build_cover_options(covers, checkbox)
        # Disk space: the build folders that earlier conversions left.
        disk = self.disk_frame = ttk.LabelFrame(common, text=self.tr('options_disk_space'), padding=(12, 8))
        disk.grid(row=7, column=0, sticky='ew', pady=(14, 0))
        self.build_disk_options(disk)

        for key in ('sms', 'gg'):
            profile_page = tab('options_master_system' if key == 'sms' else 'options_game_gear')
            self.build_scan_options(profile_page, key)
            control = checkbox(profile_page, 'extended', self.extended, 'tip_extended')
            if key == 'sms':
                self.extended_control = control
            ttk.Label(profile_page, text=self.tr('options_sega_note'), style='Muted.TLabel').pack(anchor='w')
            self.build_feedback_options(profile_page, key)

        game_boy = tab('options_game_boy')
        self.build_scan_options(game_boy, 'gb')
        self.gb_deep_control = checkbox(game_boy, 'gb_deep_validation',
                                        self.gb_deep_validation, 'tip_gb_deep_validation')
        ttk.Label(game_boy, text=self.tr('options_gb_note'), style='Muted.TLabel').pack(anchor='w')
        self.build_feedback_options(game_boy, 'gb')

        nes = tab('options_nes')
        self.build_scan_options(nes, 'nes')
        ttk.Label(nes, text=self.tr('options_nes_note'), style='Muted.TLabel').pack(anchor='w')
        self.build_feedback_options(nes, 'nes')
        for console in ('md', 'snes'):
            page = tab('options_' + console)
            self.build_scan_options(page, console)
            ttk.Label(page, text=self.tr('options_' + console + '_note'),
                      style='Muted.TLabel', wraplength=590).pack(anchor='w')
            self.build_feedback_options(page, console)

        neo_geo = tab('options_ng')
        self.build_scan_options(neo_geo, 'ng')
        ttk.Label(neo_geo, text=self.tr('options_ng_note'), style='Muted.TLabel',
                  wraplength=880, justify='left').pack(anchor='w', pady=(0, 20))
        ttk.Label(neo_geo, text=self.tr('ng_bios_label')).pack(anchor='w', pady=(0, 8))
        bios_row = ttk.Frame(neo_geo)
        bios_row.pack(fill='x')
        self.ng_bios_field = ttk.Entry(bios_row, textvariable=self.ng_bios)
        self.ng_bios_field.pack(side='left', fill='x', expand=True)
        self.option_controls.append((self.ng_bios_field, 'normal'))
        browse = ttk.Button(bios_row, text=self.tr('browse'), command=self.choose_ng_bios)
        browse.pack(side='left', padx=(8, 0))
        self.option_controls.append((browse, 'normal'))
        check = ttk.Button(bios_row, text=self.tr('ng_bios_check'), command=self.check_ng_bios)
        check.pack(side='left', padx=(8, 0))
        self.option_controls.append((check, 'normal'))
        ttk.Label(neo_geo, textvariable=self.ng_bios_status, style='Muted.TLabel',
                  wraplength=880).pack(anchor='w', pady=(12, 0))
        self.build_feedback_options(neo_geo, 'ng')
        cps1 = tab('options_cps1')
        self.build_scan_options(cps1, 'cps1')
        ttk.Label(cps1, text=self.tr('options_cps1_note'), style='Muted.TLabel',
                  wraplength=880, justify='left').pack(anchor='w', pady=(0, 14))
        self.build_feedback_options(cps1, 'cps1')
        if any(p.id == 'x68' for p in PROFILES):
            x68 = tab('options_x68')
            self.build_scan_options(x68, 'x68')
            ttk.Label(x68,text=self.tr('options_x68_note'),style='Muted.TLabel',wraplength=840,justify='left').pack(anchor='w',pady=(0,14))
            for label,variable in (('x68_ipl',self.x68_ipl),('x68_cgrom',self.x68_cgrom)):
                ttk.Label(x68,text=self.tr(label)).pack(anchor='w',pady=(8,4))
                row=ttk.Frame(x68);row.pack(fill='x')
                field=ttk.Entry(row,textvariable=variable);field.pack(side='left',fill='x',expand=True)
                self.option_controls.append((field,'normal'))
                def choose(var=variable):
                    chosen=filedialog.askopenfilename(parent=self.options_panel,title=self.tr('browse'),filetypes=[('ROM / DAT','*.dat *.rom *.bin'),('All files','*.*')])
                    if chosen:var.set(chosen)
                browse=ttk.Button(row,text=self.tr('browse'),command=choose);browse.pack(side='left',padx=(8,0));self.option_controls.append((browse,'normal'))
            ttk.Label(x68,text='RAM (MiB)').pack(anchor='w',pady=(12,4))
            control=ttk.Combobox(x68,textvariable=self.x68_ram,values=(2,4),width=8,state='readonly');control.pack(anchor='w')
            self.option_controls.append((control,'readonly'))
            self.build_feedback_options(x68,'x68')

        # Over a list or a number field, the wheel scrolls the page rather
        # than changing the value under the pointer by accident.
        def guard(widget):
            for child in widget.winfo_children():
                if child.winfo_class() in ('TCombobox', 'TSpinbox'):
                    for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                        child.bind(sequence, lambda event: (self.options_wheel(event), 'break')[1])
                guard(child)
        guard(notebook)

        buttons = ttk.Frame(panel)
        # Reserve the footer first: Tk otherwise gives a tall notebook all
        # available height on Linux, clipping the Close button to a few pixels.
        buttons.pack(side='bottom',before=notebook,fill='x',padx=0,pady=(0,6))
        ttk.Button(buttons, text=self.tr('close_options'), width=-26,
                   command=self.close_options).pack(side='right', pady=(2, 0), ipady=2)
        self.queue_background(self.body)

    def build_feedback_options(self, page, system):
        section = ttk.LabelFrame(page,text=self.tr('rom_folder'),padding=10)
        section.pack(fill='x',pady=(12,0))
        ttk.Label(section,text=self.tr('rom_folder_note'),style='Muted.TLabel',
                  wraplength=840).pack(anchor='w',pady=(0,6))
        row = ttk.Frame(section)
        row.pack(fill='x')
        entry = ttk.Entry(row,textvariable=self.rom_paths[system])
        entry.pack(side='left',fill='x',expand=True)
        self.option_controls.append((entry,'normal'))
        def choose_roms():
            chosen=filedialog.askdirectory(parent=self.options_panel,title=self.tr('rom_folder'))
            if chosen:self.rom_paths[system].set(chosen)
        for label,command in (('browse',choose_roms),('feedback_default',lambda:self.rom_paths[system].set(''))):
            button=ttk.Button(row,text=self.tr(label),command=command)
            button.pack(side='left',padx=(8,0))
            self.option_controls.append((button,'normal'))
        section = ttk.LabelFrame(page, text=self.tr('feedback_folder'), padding=12)
        section.pack(fill='x', pady=(12, 0))
        ttk.Label(section, text=self.tr('feedback_folder_note'), style='Muted.TLabel',
                  wraplength=840, justify='left').pack(anchor='w', pady=(0, 10))
        row = ttk.Frame(section)
        row.pack(fill='x')
        entry = ttk.Entry(row, textvariable=self.feedback_paths[system])
        entry.pack(side='left', fill='x', expand=True)
        self.option_controls.append((entry, 'normal'))
        def choose():
            selected = filedialog.askdirectory(parent=self.options_panel, title=self.tr('feedback_folder'))
            if selected:
                self.feedback_paths[system].set(selected)
        for label, command in (('browse', choose), ('feedback_default', lambda: self.feedback_paths[system].set(''))):
            button = ttk.Button(row, text=self.tr(label), command=command)
            button.pack(side='left', padx=(8, 0))
            self.option_controls.append((button, 'normal'))
        actions = ttk.Frame(section)
        actions.pack(fill='x', pady=(12, 0))
        button = ttk.Button(actions, text=self.tr('feedback_import'),
                            command=lambda: self.import_feedback(system))
        button.pack(side='left')
        self.feedback_import_buttons[system] = button
        self.option_controls.append((button, 'normal'))
        if system in self.feedback_importing:
            button.configure(state='disabled')
        ttk.Label(actions, textvariable=self.feedback_status[system], style='Muted.TLabel',
                  wraplength=560, justify='left').pack(side='left', padx=(12, 0))

    def import_feedback(self, system):
        if self.busy or self.updating or system in self.feedback_importing:
            return
        # Capture Tk values on the UI thread. The worker never touches widgets.
        preferences = {'output': self.output.get(), 'custom_output': self.custom_output.get(),
            'feedback_paths': {key: value.get().strip() for key, value in self.feedback_paths.items()}}
        self.feedback_importing.add(system)
        self.feedback_import_buttons[system].configure(state='disabled')
        self.feedback_status[system].set(self.tr('feedback_import_busy'))
        def worker():
            from .feedback import import_saved_feedback
            try:
                report = import_saved_feedback(system, preferences,
                    emit=lambda message: self.messages.put(('log', message)))
                self.messages.put(('feedback_import', system, report, None))
            except Exception as exc:
                self.messages.put(('feedback_import', system, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def choose_ng_bios(self):
        path = filedialog.askopenfilename(parent=self.options_panel,
            title=self.tr('ng_bios_label'), filetypes=[('ZIP', '*.zip')])
        if path:
            self.ng_bios.set(path)
            self.check_ng_bios()

    def check_ng_bios(self):
        from .neogeo import validate_bios
        path = selected_bios_path(self.ng_bios.get())
        if path is None:
            self.ng_bios_status.set(self.tr('ng_bios_missing'))
            return False
        try:
            info = validate_bios(path)
            self.ng_bios_status.set(self.tr('ng_bios_dual' if 'aes' in info else 'ng_bios_valid'))
            return True
        except ValueError as exc:
            self.ng_bios_status.set(self.tr('ng_bios_invalid', error=str(exc)))
            return False

    def build_account_options(self, page):
        """The Retro-Recomp account in Options: who is signed in, sign in or
        out, and the account page of the site."""
        self.account_status = tk.StringVar()
        ttk.Label(page, textvariable=self.account_status, wraplength=600).pack(anchor='w', pady=(0, 8))
        row = self.account_buttons = ttk.Frame(page)
        row.pack(anchor='w')
        self.account_sign_button = ttk.Button(row, command=self.account_sign_toggle)
        self.account_sign_button.pack(side='left')
        self.account_site_button = ttk.Button(row, text=self.tr('account_open_site'),
            command=lambda: webbrowser.open_new_tab(online.service_url() + '/account'))
        self.account_site_button.pack(side='left', padx=(8, 0))
        # Signed in: the RR coins and the title, bought and chosen on the site.
        self.account_rewards = ttk.Frame(page)
        self.account_balance = tk.StringVar()
        ttk.Label(self.account_rewards, textvariable=self.account_balance).pack(side='left')
        titles = ttk.Button(self.account_rewards, text=self.tr('account_titles_site'),
                            command=lambda: webbrowser.open_new_tab(online.service_url() + '/account'))
        titles.pack(side='left', padx=(12, 0))
        self.hint(titles, 'tip_account_titles')
        # Signed in: the shared base before and after each batch.
        self.account_sync = ttk.Frame(page)
        for key, variable in (('use_shared_base', self.use_shared_base), ('send_after_batch', self.send_after_batch)):
            control = ttk.Checkbutton(self.account_sync, text=self.tr(key), variable=variable)
            control.pack(anchor='w', pady=(0, 6))
            self.option_controls.append((control, 'normal'))
            self.hint(control, 'tip_' + key)
        self.update_account_options()

    def update_account_options(self):
        if getattr(self, 'account_status', None) is None:
            return
        try:
            current = online.account() if SENDING_AVAILABLE else None
            if not SENDING_AVAILABLE:
                self.account_status.set(self.tr('account_coming'))
            elif current:
                self.account_status.set(self.tr('account_signed_as', email=current.get('email', '')))
            else:
                self.account_status.set(self.tr('account_invite'))
            self.account_sign_button.configure(text=self.tr('account_sign_out' if current else 'account_sign_in'),
                                               state='normal' if SENDING_AVAILABLE else 'disabled')
            self.account_site_button.configure(state='normal' if SENDING_AVAILABLE else 'disabled')
            if current:
                profile = (getattr(self, 'player', None) or {}).get('profile') or {}
                coins = self.coin_balance(profile)
                text = self.tr('account_balance', coins='–' if coins is None else coins)
                if self.title_name(profile.get('title')):
                    text += ' · ' + self.tr('account_title', title=self.title_name(profile.get('title')))
                self.account_balance.set(text)
                self.account_rewards.pack(anchor='w', pady=(0, 8), before=self.account_buttons)
                self.account_sync.pack(anchor='w', pady=(0, 4), before=self.account_buttons)
            else:
                self.account_rewards.pack_forget()
                self.account_sync.pack_forget()
        except tk.TclError:
            pass

    def build_disk_options(self, page):
        """Options › Common › Disk space: the per-game build folders earlier
        conversions left under .build (retrorecomp/build_cleanup.py), measured
        in a worker when the options open, removed only after a confirmation."""
        ttk.Label(page, text=self.tr('disk_space_note'), style='Muted.TLabel',
                  wraplength=600, justify='left').pack(anchor='w', pady=(0, 8))
        row = ttk.Frame(page)
        row.pack(anchor='w', fill='x')
        self.disk_button = ttk.Button(row, command=self.free_disk_space)
        self.disk_button.pack(side='left')
        self.hint(self.disk_button, 'tip_disk_space')
        self.disk_status = tk.StringVar()
        ttk.Label(row, textvariable=self.disk_status, style='Muted.TLabel',
                  wraplength=460, justify='left').pack(side='left', padx=(12, 0))
        if getattr(self, 'disk_state', {}).get('phase') == 'working':
            self.render_disk_space()      # a removal started earlier is still running
        else:
            self.measure_disk_space()

    def measure_disk_space(self):
        """Measure off Tk: a long-used workspace holds thousands of folders."""
        cancel = self.disk_cancel = threading.Event()
        self.disk_state = {'phase': 'measuring'}
        self.render_disk_space()
        def worker():
            from .build_cleanup import leftover_projects
            try:
                self.messages.put(('disk_space_measured', cancel, leftover_projects(cancel=cancel), None))
            except InterruptedError:
                pass
            except Exception as exc:
                self.messages.put(('disk_space_measured', cancel, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def size_text(self, count):
        """Megabytes under a gigabyte, else gigabytes, as the language writes them."""
        megabytes = count / 1048576
        if megabytes < 1024:
            return self.tr('size_megabytes', value=str(max(1, round(megabytes)) if count else 0))
        value = f'{megabytes / 1024:.1f}'
        if language_code(self.language) in ('fr', 'it', 'es', 'de', 'ru'):
            value = value.replace('.', ',')
        return self.tr('size_gigabytes', value=value)

    def render_disk_space(self):
        """The Disk space line and button, from self.disk_state (also after a
        language change)."""
        button, state = getattr(self, 'disk_button', None), getattr(self, 'disk_state', None)
        try:
            if button is None or state is None or not button.winfo_exists():
                return
        except tk.TclError:
            return
        phase = state['phase']
        projects = state.get('projects') or []
        removable = [project for project in projects if not project.in_use]
        kept = [project for project in projects if project.in_use]
        size = lambda chosen: self.size_text(sum(project.size for project in chosen))
        if phase == 'measured':
            text = (self.tr('disk_space_found', count=len(removable), size=size(removable)) if removable else
                    '' if kept else self.tr('disk_space_none'))
            if kept:
                text = (text + ' ' if text else '') + self.tr('disk_space_in_use', count=len(kept), size=size(kept))
        elif phase == 'done':
            outcome = state['outcome']
            text = self.tr('disk_space_done', size=self.size_text(outcome['freed']), count=outcome['removed'])
            if outcome['kept'] or outcome['errors']:
                text += ' ' + self.tr('disk_space_not_removed', count=outcome['kept'] + len(outcome['errors']))
        elif phase == 'error':
            text = self.tr('disk_space_error', error=state['error'])
        else:
            text = self.tr('disk_space_measuring' if phase == 'measuring' else 'disk_space_working')
        try:
            self.disk_status.set(text)
            ready = phase == 'measured' and bool(removable)
            button.configure(text=self.tr('disk_space_free_size', size=size(removable)) if ready
                             else self.tr('disk_space_free'),
                             state='normal' if ready and not self.busy and not self.updating else 'disabled')
        except tk.TclError:
            pass

    def free_disk_space(self):
        state = getattr(self, 'disk_state', {})
        removable = [project for project in state.get('projects') or [] if not project.in_use]
        if self.busy or self.updating or state.get('phase') != 'measured' or not removable:
            return
        size = self.size_text(sum(project.size for project in removable))
        if not messagebox.askyesno(APP_NAME, self.tr('disk_space_confirm', count=len(removable), size=size),
                                   icon='warning', default='no', parent=self.app):
            return
        # No conversion starts while folders are removed; there is nothing to stop.
        self.busy = True
        self.set_controls(False)
        self.stop_button.configure(state='disabled')
        self.disk_state = {'phase': 'working'}
        self.render_disk_space()
        def worker():
            from .build_cleanup import remove_projects
            try:
                outcome = remove_projects(removable, emit=lambda text: self.messages.put(('log', text)))
                self.messages.put(('disk_space_freed', outcome, None))
            except Exception as exc:
                self.messages.put(('disk_space_freed', None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def account_sign_toggle(self):
        if online.account():
            self.sign_out()
        else:
            self.sign_in_from_header()
        self.update_account_options()

    def build_cover_options(self, page, checkbox):
        self.cover_settings = load_cover_settings()
        self.cover_3d = tk.BooleanVar(value=self.cover_settings['box_3d'])
        checkbox(page, 'cover_box_3d', self.cover_3d, 'tip_cover_box_3d')
        ttk.Label(page, text=self.tr('cover_sources_note'), style='Muted.TLabel',
                  wraplength=610).pack(anchor='w', pady=(0, 12))
        providers = list(COVER_PROVIDERS)
        self.cover_source = tk.StringVar(value=COVER_PROVIDERS[providers[0]][0])
        selector = ttk.Combobox(page, textvariable=self.cover_source,
            values=[COVER_PROVIDERS[p][0] for p in providers], state='readonly', width=24)
        selector.pack(anchor='w', pady=(0, 8))
        self.option_controls.append((selector, 'readonly'))
        host = ttk.Frame(page)
        host.pack(fill='both', expand=True)
        self.cover_accounts = {}
        cards = {}
        for provider in providers:
            card = ttk.Frame(host)
            cards[provider] = card
            ttk.Label(card, text=self.tr('cover_note_' + provider), style='Muted.TLabel',
                      wraplength=610).pack(anchor='w', pady=(0, 10))
            fields = ttk.Frame(card)
            fields.pack(fill='x')
            fields.columnconfigure(1, weight=1)
            self.cover_accounts[provider] = {}
            for row, field in enumerate(COVER_FIELDS.get(provider, ())):
                variable = tk.StringVar(value=self.cover_settings['accounts'][provider][field])
                self.cover_accounts[provider][field] = variable
                ttk.Label(fields, text=self.tr('cover_field_' + field)).grid(
                    row=row, column=0, sticky='w', padx=(0, 14), pady=4)
                entry = ttk.Entry(fields, textvariable=variable,
                    show='' if field in ('devid', 'ssid', 'client_id') else 'â€¢')
                entry.grid(row=row, column=1, sticky='ew', pady=4)
                self.option_controls.append((entry, 'normal'))
            link = ttk.Button(card, text=self.tr('cover_api_link'),
                command=lambda url=COVER_PROVIDERS[provider][1]: webbrowser.open(url))
            link.pack(anchor='w', pady=(10, 0))
            self.option_controls.append((link, 'normal'))

        def select(_event=None):
            for provider, card in cards.items():
                card.pack_forget()
                if self.cover_source.get() == COVER_PROVIDERS[provider][0]:
                    card.pack(fill='both', expand=True)
        selector.bind('<<ComboboxSelected>>', select)
        select()
        ttk.Label(page, text=self.tr('cover_secrets_note'), style='Muted.TLabel',
                  wraplength=610).pack(anchor='w', pady=(8, 0))
        if self.cover_settings.get('credential_error'):
            ttk.Label(page, text=self.tr('cover_unlock_failed'), wraplength=610).pack(anchor='w')

    def close_options(self):
        panel = self.options_panel
        if panel is None or not panel.winfo_exists():
            return
        try:
            options = self.preferences()
            if (not 1 <= options['passes'] <= 10 or not 1 <= options['frames'] <= 10000
                    or not 1 <= options['jobs'] <= 8 or not options['output'].strip()):
                raise ValueError(self.tr('invalid_limits'))
            save_preferences(options)
            covers = {'box_3d': self.cover_3d.get(), 'accounts': {
                provider: {field: variable.get().strip() for field, variable in fields.items()}
                for provider, fields in self.cover_accounts.items() if fields}}
            previous = {key: self.cover_settings[key] for key in ('box_3d', 'accounts')}
            if covers != previous:
                covers['credential_error'] = self.cover_settings.get('credential_error', False)
                save_cover_settings(covers)
        except KeyringError:
            messagebox.showerror(APP_NAME, self.tr('cover_unlock_failed'), parent=panel)
            return
        except (ValueError, tk.TclError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=panel)
            return
        for hint in self.tooltips[self.option_tooltips_start:]:
            hint.hide()
        del self.tooltips[self.option_tooltips_start:]
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            panel.unbind_all(sequence)
        self.option_scrollers = []
        if getattr(self, 'disk_cancel', None) is not None:
            self.disk_cancel.set()      # a measurement still running stops
        self.disk_button = None
        panel.grid_remove()
        panel.destroy()
        self.options_panel = None
        self.output_field = self.output_browse = None
        self.option_controls = []
        self.body.rowconfigure(1, weight=4, minsize=100)
        self.body.rowconfigure(7, weight=2, minsize=52)
        for widget in self.compiler_widgets:
            widget.grid()
        self.queue_actions.pack(side='left', padx=(12, 0), after=self.compiled_button)
        try:
            self.options_button.state(['!selected'])
        except (AttributeError, tk.TclError):
            pass
        self.queue_background(self.body)

    def scrolled_page(self, parent, padding=18):
        """A frame inside parent that scrolls vertically once its content is
        taller than the room: a light scrollbar appears only then."""
        canvas = tk.Canvas(parent, bg=COLORS['background'], highlightthickness=0, borderwidth=0,
                           yscrollincrement=20)
        bar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview, style='Slim.Vertical.TScrollbar')
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side='left', fill='both', expand=True)
        inner = ttk.Frame(canvas, padding=padding)
        item = canvas.create_window(0, 0, window=inner, anchor='nw')
        def fit(event=None):
            width, height = canvas.winfo_width(), inner.winfo_reqheight()
            canvas.itemconfigure(item, width=width)
            canvas.configure(scrollregion=(0, 0, width, height))
            if height <= canvas.winfo_height():
                if bar.winfo_ismapped():
                    bar.pack_forget()
                canvas.yview_moveto(0)
            elif not bar.winfo_ismapped():
                bar.pack(side='right', fill='y', padx=(0, 2), pady=2, before=canvas)
        canvas.bind('<Configure>', fit)
        inner.bind('<Configure>', fit)
        canvas._retro_scroll_bar = bar
        self.option_scrollers.append(canvas)
        return inner

    def options_wheel(self, event):
        """The wheel scrolls the options page under the pointer, wherever it
        is on that page (labels, fields, frames), when the page overflows."""
        try:
            widget = self.app.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        while widget is not None and widget not in self.option_scrollers:
            widget = getattr(widget, 'master', None)
        if widget is None or not widget._retro_scroll_bar.winfo_ismapped():
            return
        if getattr(event, 'num', None) in (4, 5):
            step = -1 if event.num == 4 else 1
        else:
            step = -1 if event.delta > 0 else 1
        widget.yview_scroll(step * 3, 'units')

    def show_credits(self):
        if self.credits_panel is not None and self.credits_panel.winfo_exists():
            self.credits_panel.lift()
            self.credits_panel.focus_set()
            return

        from .credits_demo import CreditsDemo
        self.credits_demo = CreditsDemo(self, UPSTREAM_CREDITS)

    def show_legal_notices(self):
        """Show the complete bundled licenses without creating sidecar files."""
        parent = self.credits_panel if self.credits_panel and self.credits_panel.winfo_exists() else self.app
        resources = [ASSETS / 'LICENSE', ASSETS / 'THIRD_PARTY_NOTICES.md',
                     ASSETS / 'assets/credits/NOTICE.md']
        resources.extend(sorted((ASSETS / 'licenses').glob('*.md'), key=lambda path: path.name.lower()))
        resources = [path for path in resources if path.is_file()]
        panel = tk.Toplevel(parent)
        panel.title(APP_NAME + ' - ' + self.tr('credits_notices'))
        panel.configure(bg=COLORS['background'])
        center_dialog(panel, parent, 880, 630)
        panel.minsize(min(650, panel.winfo_screenwidth() - 40), min(420, panel.winfo_screenheight() - 90))
        panel.transient(parent)
        body = tk.Frame(panel, bg=COLORS['background'], padx=16, pady=16)
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('credits_notices'), bg=COLORS['background'], fg=COLORS['text'],
                 font=(self.ui_font, 16, 'bold')).pack(anchor='w', pady=(0, 10))
        row = tk.Frame(body, bg=COLORS['background'])
        row.pack(fill='both', expand=True)
        listing = tk.Listbox(row, width=29, exportselection=False, bg=COLORS['panel'],
                             fg=COLORS['text'], selectbackground=COLORS['border'],
                             selectforeground='#ffffff', relief='flat',
                             font=(self.ui_font, 10))
        listing.pack(side='left', fill='y', padx=(0, 10))
        for path in resources:
            listing.insert('end', path.name)
        scrollbar = ttk.Scrollbar(row, orient='vertical')
        scrollbar.pack(side='right', fill='y')
        viewer = tk.Text(row, wrap='word', bg=COLORS['panel'], fg=COLORS['text'],
                         insertbackground=COLORS['text'], relief='flat', padx=10, pady=10,
                         font=('Consolas', 10), yscrollcommand=scrollbar.set)
        viewer.pack(side='left', fill='both', expand=True)
        scrollbar.configure(command=viewer.yview)

        def show_selected(_event=None):
            if not listing.curselection():
                return
            content = resources[listing.curselection()[0]].read_text(encoding='utf-8-sig')
            viewer.configure(state='normal')
            viewer.delete('1.0', 'end')
            viewer.insert('1.0', content)
            viewer.configure(state='disabled')
            viewer.yview_moveto(0)

        listing.bind('<<ListboxSelect>>', show_selected)
        if resources:
            listing.selection_set(0)
            show_selected()

        actions = tk.Frame(body, bg=COLORS['background'])
        actions.pack(fill='x', pady=(12, 0))

        ttk.Button(actions, text=self.tr('upx_source_link'),
                   command=lambda: webbrowser.open_new_tab(UPX_SOURCE_URL)).pack(side='left')

        def close():
            panel.grab_release()
            panel.destroy()
            if parent is self.credits_panel and parent.winfo_exists():
                parent.grab_set()

        ttk.Button(actions, text=self.tr('close'), command=close).pack(side='right')
        panel.protocol('WM_DELETE_WINDOW', close)
        panel.bind('<Escape>', lambda _event: close())
        panel.grab_set()
        panel.focus_set()

    def show_library(self):
        if self.library_view is not None and self.library_view.panel.winfo_exists():
            self.library_view.panel.lift()
            return
        from .memory_view import MemoryView
        self.library_view = MemoryView(self)
        self.library_panels.append(self.library_view.panel)

    def toggle_compiled_games(self):
        if self.options_panel is not None and self.options_panel.winfo_exists():
            self.close_options()
            if self.options_panel is not None:
                return
        if self.compiled_view is None:
            from .compiled_games_view import CompiledGamesView
            self.compiled_view = CompiledGamesView(self, self.body)
        self.collection_visible = not self.collection_visible
        if self.collection_visible:
            for widget in self.compiler_widgets:widget.grid_remove()
            self.queue_actions.pack_forget()
            self.count_label.pack_forget()
            self.collection_actions.pack(side='left', padx=(12, 0), after=self.compiled_button)
            self.body.rowconfigure(1, weight=1, minsize=100)
            self.body.rowconfigure(7, weight=0, minsize=0)
            self.compiled_view.grid(row=1,column=0,rowspan=7,sticky='nsew')
            self.compiled_view.render()
            # Games played or converted elsewhere: re-read only what changed.
            self.compiled_view.after_idle(self.compiled_view.quiet_refresh)
        else:
            self.compiled_view.grid_remove()
            self.body.rowconfigure(1, weight=4, minsize=100)
            self.body.rowconfigure(7, weight=2, minsize=52)
            for widget in self.compiler_widgets:widget.grid()
            self.collection_actions.pack_forget()
            self.queue_actions.pack(side='left', padx=(12, 0), after=self.compiled_button)
            self.count_label.pack(side='right', before=self.credits_button)
        self.update_compiled_button()
        self.queue_background(self.body)

    def update_compiled_button(self):
        """One width for both captions, so the switch never changes size."""
        captions = (self.tr('compiled_games'), self.tr('conversion_queue'))
        # Width counts average characters ('0'); measure the real text so
        # wide scripts such as Cyrillic are not cut.
        from tkinter import font as tkfont
        measure = tkfont.Font(root=self.app, font=(self.ui_font, 9))
        zero = measure.measure('0') or 7
        widest = max(measure.measure(caption) for caption in captions)
        self.compiled_button.configure(text=captions[1] if self.collection_visible else captions[0],
                                       width=-(-widest // zero) + 1)

    def knowledge_menu(self):
        menu = tk.Menu(self.app, tearoff=False, bg=COLORS['button'], fg=COLORS['text'],
                       activebackground=COLORS['selected'], activeforeground=COLORS['gold_hover'])
        menu.add_command(label=self.tr('knowledge_import'), command=self.import_knowledge)
        menu.add_command(label=self.tr('knowledge_export'), command=self.export_knowledge)
        menu.add_separator()
        if not SENDING_AVAILABLE:
            # Sending arrives with the web service.
            menu.add_command(label=self.tr('knowledge_export_web'), state='disabled')
        else:
            menu.add_command(label=self.tr('knowledge_send'), command=self.send_knowledge)
            # Signing out lives in the header (and Options); signing in stays
            # here too, next to the send that needs it.
            if not online.account():
                menu.add_command(label=self.tr('knowledge_sign_in'), command=self.sign_in_dialog)
        button = self.knowledge_button
        try:menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:menu.grab_release()

    def knowledge_task(self, callback, status='knowledge_working'):
        """File work runs off Tk; the result comes back as one message."""
        self.busy = True
        self.set_controls(False)
        self.messages.put(('log', self.tr(status)))
        if self.compiled_view is not None:
            self.compiled_view.progress.start(15)
            self.compiled_view.status.set(self.tr(status))
        def worker():
            try:
                # An automatic send after a batch finishes first.
                with self.knowledge_lock:
                    outcome = callback()
                self.messages.put(('knowledge_done', outcome, None))
            except Exception as exc:self.messages.put(('knowledge_done', None, str(exc) or type(exc).__name__))
        threading.Thread(target=worker, daemon=True).start()

    def export_knowledge(self):
        """Count the discoveries first; ask where to save only if there are some."""
        if self.busy or self.updating:return
        self.collect_discoveries('collect')

    def collect_discoveries(self, kind):
        """Collect the shareable discoveries off Tk; `kind` tells knowledge_done
        whether they go to a file ('collect') or to the shared base ('send_collect')."""
        games = self.compiled_inventory.snapshot()
        if not games:
            messagebox.showinfo(APP_NAME, self.tr('knowledge_export_empty'), parent=self.app)
            if self.closing_send:self.close()
            return
        self.cancel.clear()
        collect = self.discoveries_collector(self.cancel)
        self.knowledge_task(lambda: (kind, collect()), 'knowledge_counting')

    def discoveries_collector(self, cancel):
        """A function collecting the shareable discoveries off Tk; the Tk
        values it needs are read now, on the Tk thread."""
        from .knowledge_exchange import collect_knowledge
        # Qualified games whose source moved are found like for Reconvert.
        options = self.preferences()
        from .compiled_games import Game
        known = [*self.compiled_inventory.snapshot(), *(Game('', i.system, i.sha256, i.title, source=str(i.path))
                                                        for i in self.items.values() if i.system and i.sha256)]
        def locate(pending):
            from .rom_sources import RomSources
            pairs = RomSources().resolve(pending, options, known=known, cancel=cancel)
            return {(game.system, game.identity): source for game, source in pairs if source}
        def collect():
            # Discoveries saved since the last look count without a full scan.
            from .compiled_games import refresh_changed
            refresh_changed(self.compiled_inventory, options)
            # Cached results stay valid while the ROM folders stay the same.
            context = json.dumps(options.get('rom_paths', {}), sort_keys=True)
            return collect_knowledge(self.compiled_inventory.snapshot(), locate, context)
        return collect

    def send_knowledge(self, closing=False):
        """Send the discoveries the shared base has not received from this
        account yet; with `closing`, the window closes once it is done."""
        if self.busy or self.updating:return
        self.closing_send = closing
        if not online.account() and not self.sign_in_dialog():
            if closing:self.close()
            return
        self.collect_discoveries('send_collect')

    def online_message(self, error):
        if isinstance(error, online.ServiceConnectionError):
            return self.tr('online_unreachable')
        known = {'invalid_code': 'online_invalid_code', 'invalid_email': 'online_invalid_email',
                 'rate_limited': 'online_rate_limited', 'quota': 'online_rate_limited',
                 'terms_required': 'online_terms_needed'}
        reason = getattr(error, 'reason', '') or type(error).__name__
        return self.tr(known[reason]) if reason in known else self.tr('online_refused', reason=reason)

    def upload_discoveries(self, pending):
        """Worker side of a send: a summary, or {'error': text} to report."""
        try:
            return online.send(pending)
        except (online.ServiceError, online.ServiceConnectionError) as error:
            return {'error': self.online_message(error)}

    def service_problem(self, error):
        """A service or file error in one short, translated phrase."""
        if isinstance(error, (online.ServiceError, online.ServiceConnectionError)):
            return self.online_message(error)
        return str(error) or type(error).__name__

    # --- The shared base around each batch -----------------------------------

    def prepare_shared_paths(self, keys, enabled):
        """Worker side, before a batch: one fetch of the shared base's paths
        for these ROMs ('system:sha256') into the imported banks, said in one
        log line. {} without the option, the service or an account (no request);
        a fetch that fails leaves the conversions as they would be offline."""
        if not enabled or not SENDING_AVAILABLE:
            return {}
        try:
            outcome = online.prepare_batch(keys, True)
        except Exception as exc:   # the batch goes on whatever happens here
            outcome = {'paths': {}, 'summary': None, 'error': exc}
        summary, error = outcome['summary'], outcome['error']
        if error is not None:
            self.messages.put(('log', self.tr('shared_unavailable', error=self.service_problem(error))))
        elif summary and summary['roms']:
            self.messages.put(('log', self.tr('shared_received', games=summary['roms'], records=summary['records'],
                                              observations=summary['observations'])))
        elif summary and summary['asked']:
            self.messages.put(('log', self.tr('shared_nothing')))
        return outcome['paths']

    def forget_rejected_shared(self, shared, results):
        """Shared paths a batch set aside after they broke a conversion no
        longer allow a quick check for that ROM."""
        rejected = [f"{result.get('system')}:{result.get('sha256')}" for result in results
                    if result.get('imported_hints_rejected')]
        if shared and rejected:
            try:
                online.forget_shared([key for key in rejected if key in shared])
            except OSError:
                pass

    def sending_started(self):
        """While discoveries travel to the server, the status line's green dot
        becomes a small turning gold circle and the line says so."""
        self.sending_count = getattr(self, 'sending_count', 0) + 1
        if self.sending_count > 1 or not hasattr(self, 'status_dot'):
            return
        self.footer_label.configure(text=self.tr('sending_discoveries'))
        def turn(angle=0):
            if self.sending_count <= 0:
                return
            dot = self.status_dot
            dot.delete('spinner')
            dot.itemconfigure('dot', state='hidden')
            dot.create_arc(1, 1, 11, 11, start=angle, extent=270, style='arc', outline=COLORS['gold'],
                           width=2, tags='spinner')
            self.spin_after = dot.after(60, turn, (angle - 30) % 360)
        turn()

    def sending_finished(self):
        self.sending_count = max(0, getattr(self, 'sending_count', 0) - 1)
        if self.sending_count or not hasattr(self, 'status_dot'):
            return
        try:
            self.status_dot.after_cancel(self.spin_after)
        except (AttributeError, tk.TclError, ValueError):
            pass
        self.status_dot.delete('spinner')
        self.status_dot.itemconfigure('dot', state='normal')
        self.footer_label.configure(text=self.tr('footer'))

    def send_new_discoveries(self):
        """After a batch, signed in with the option on: send the discoveries the
        shared base has not received from this account, then their claims, in
        a worker. Failures only reach the log; the games stay pending for the
        next batch. Never during an update; the window stays usable."""
        if (not SENDING_AVAILABLE or getattr(self, 'updating', False) or getattr(self, 'auto_sending', True)
                or not self.send_after_batch.get() or not online.account()):
            return
        collect = self.discoveries_collector(threading.Event())
        self.auto_sending = True
        self.sending_started()
        def worker():
            try:
                with self.knowledge_lock:
                    summary = online.send_after_batch(collect)
                self.messages.put(('auto_sent', summary, None))
            except Exception as exc:
                self.messages.put(('auto_sent', None, exc))
        threading.Thread(target=worker, daemon=True, name='retro-recomp-send').start()

    def auto_sent(self, summary, error):
        self.auto_sending = False
        self.sending_finished()
        if error is not None:
            self.messages.put(('log', self.tr('auto_send_failed', error=self.service_problem(error))))
            return
        claims = (summary or {}).get('claims') or {}
        if (summary or {}).get('games'):
            text = self.tr('auto_send_done', games=summary['games'])
            if claims.get('new'):
                text += ' ' + self.tr('knowledge_send_new', count=claims['new'])
            self.messages.put(('log', text))
        if (summary or {}).get('claims_refused'):
            self.messages.put(('log', self.tr('claims_refused', reason=', '.join(summary['claims_refused']))))
        if (summary or {}).get('games') or claims:
            self.refresh_player(force=True)   # new points (and coins) at once

    def sign_out(self):
        if self.busy or self.updating:return
        signed = online.account() or {}
        if not messagebox.askyesno(APP_NAME, self.tr('account_sign_out_confirm', email=signed.get('email', '')),
                                   icon='question', default='no', parent=self.app):
            return
        self.knowledge_task(lambda:(online.sign_out(), ('signed_out', None))[1], 'knowledge_working')

    # --- The player's corner of the header ---------------------------------

    def sign_in_from_header(self):
        """The header's second button: sign in, or sign out once signed in."""
        if self.busy or self.updating or not SENDING_AVAILABLE:return
        if online.account():
            self.sign_out()
        else:
            self.sign_in_dialog()

    def refresh_player(self, force=False):
        """Show the player's corner from the local cache at once, then, off Tk,
        refresh it from the site only when it is older than 30 minutes (or
        after a sign-in). Without an account, nothing is fetched."""
        if not SENDING_AVAILABLE or not online.account():
            self.render_player(None)
            return
        cached = online.cached_player()
        if cached:
            self.render_player(cached)
        def worker():
            try:
                data = online.player(force=force) or {'account': online.account()}
            except (online.ServiceError, online.ServiceConnectionError) as error:
                if cached:
                    return   # offline: the last known corner stays as it is
                data = {'account': online.account(), 'error': self.online_message(error)}
            self.messages.put(('player', data))
        threading.Thread(target=worker, daemon=True).start()

    def title_name(self, title):
        """A title from the site ({'id', 'name': {language: text}}) in the
        interface language, else English, else any; '' without one."""
        names = title.get('name') if isinstance(title, dict) else None
        if not isinstance(names, dict):
            return ''
        for code in (self.language, 'en', *sorted(names)):
            if isinstance(names.get(code), str) and names[code].strip():
                return names[code].strip()[:48]
        return ''

    @staticmethod
    def coin_balance(profile):
        """The RR coins balance of `GET account`, or None before the site says."""
        coins = profile.get('coins') if isinstance(profile, dict) else None
        balance = coins.get('balance') if isinstance(coins, dict) else None
        return balance if type(balance) is int else None

    def render_player(self, data=...):
        """Draw the account corner from the last answer: a portrait, the
        pseudonym (or the e-mail's user name), points and rank; or the
        invitation to sign in, disabled until the online service opens."""
        if data is not ...:
            self.player = data or {}
        self.update_account_options()
        player = self.player
        account = player.get('account') or (online.account() if SENDING_AVAILABLE else None)
        header = self.header
        for child in self.player_actions.winfo_children():
            child.pack_forget()
        if not account:
            self.portrait = _portrait_photo(self.app)
            header.itemconfigure(self.portrait_item, image=self.portrait)
            header.itemconfigure(self.player_name, text=self.tr('account_not_signed'))
            header.itemconfigure(self.player_title, text='')
            header.itemconfigure(self.player_score,
                                 text=self.tr('account_invite') if SENDING_AVAILABLE else self.tr('account_coming'))
            self.board_button.configure(state='normal' if SENDING_AVAILABLE else 'disabled')
            self.sign_in_button.configure(text=self.tr('account_sign_in'),
                                          state='normal' if SENDING_AVAILABLE else 'disabled')
            self.board_button.pack(side='top', fill='x')
            self.sign_in_button.pack(side='top', fill='x', pady=(4, 0))
            self.app.after_idle(self.layout_header)
            return
        profile = player.get('profile') or {}
        name = profile.get('pseudonym') or account.get('pseudonym') or str(account.get('email', '')).split('@')[0]
        self.portrait = _portrait_photo(self.app, player.get('avatar'), name[:1])
        header.itemconfigure(self.portrait_item, image=self.portrait)
        header.itemconfigure(self.player_name, text=name)
        header.itemconfigure(self.player_title, text=self.title_name(profile.get('title')))
        you = (player.get('board') or {}).get('you') or {}
        if player.get('error'):
            score = player['error']
        elif (player.get('board') or {}).get('demo'):
            score = self.tr('account_board_soon')
        elif you.get('rank'):
            score = self.tr('account_points', points=you.get('total', 0), rank=you['rank'])
        else:
            score = self.tr('account_unranked', points=you.get('total', 0))
        coins = self.coin_balance(profile)
        if coins is not None and not player.get('error'):
            score += ' · ' + self.tr('account_coins', coins=coins)
        if you.get('pending'):
            score += '\n' + self.tr('account_pending', count=you['pending'])
        header.itemconfigure(self.player_score, text=score)
        self.board_button.configure(state='normal')
        self.sign_in_button.configure(text=self.tr('account_sign_out'), state='normal')
        self.board_button.pack(side='top', fill='x')
        self.sign_in_button.pack(side='top', fill='x', pady=(4, 0))
        self.app.after_idle(self.layout_header)

    # --- Build tools ---------------------------------------------------------

    def ensure_build_tools(self, retry):
        """True when a conversion can start; otherwise offer to install what is
        missing and run `retry` once it is installed."""
        from .updater import missing_build_tools
        try:
            missing = missing_build_tools()
        except Exception:
            return True   # the conversion reports its own precise error
        from .core import dependencies_ready
        if not missing:
            if dependencies_ready():
                return True
            # Tools present, shared pieces not built yet: prepare them now,
            # behind the progress window, rather than inside the first game.
            if messagebox.askyesno(APP_NAME, self.tr('deps_intro') + '\n\n' + self.tr('deps_question'), parent=self.app):
                self.install_build_tools({}, retry)
            return False
        if os.name == 'nt':
            items = [self.tr(f'tools_item_{key}') for key in ('git', 'compiler') if missing.get(key)]
            text = self.tr('tools_intro', items='\n• ' + '\n• '.join(items))
        elif missing.get('packages'):
            text = self.tr('tools_intro_linux', count=len(missing['packages']),
                           packages=' '.join(missing['packages']))
        else:
            messagebox.showwarning(APP_NAME, self.tr('tools_manual_linux', commands=', '.join(missing['commands'])),
                                   parent=self.app)
            return False
        text += '\n\n' + self.tr('tools_deps_note')
        if messagebox.askyesno(APP_NAME, text + '\n\n' + self.tr('tools_question'), parent=self.app):
            self.install_build_tools(missing, retry)
        return False

    def install_build_tools(self, missing, retry):
        """Install in a worker; a small window follows the downloads and steps."""
        from . import updater
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(f"{APP_NAME} — {self.tr('tools_title')}")
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        window.protocol('WM_DELETE_WINDOW', lambda: None)   # the installer cannot be interrupted midway
        body = tk.Frame(window, bg=background, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('tools_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 10, 'bold')).pack(anchor='w')
        step = tk.Label(body, text=self.tr('tools_preparing'), bg=background, fg=COLORS['text'],
                        font=(self.ui_font, 9), wraplength=440, justify='left')
        step.pack(anchor='w', pady=(10, 6))
        bar = ttk.Progressbar(body, length=440, mode='determinate')
        bar.pack(fill='x')
        detail = tk.Label(body, text='', bg=background, fg=COLORS['muted'], font=(self.ui_font, 8),
                          wraplength=440, justify='left')
        detail.pack(anchor='w', pady=(6, 0))
        window.update_idletasks()
        center_dialog(window, self.app, window.winfo_reqwidth(), window.winfo_reqheight())
        window.deiconify()
        state = {'label': '', 'done': 0, 'total': 0, 'step': '', 'result': None}
        self.updating = True
        self.set_controls(False)
        # The shared pieces (engine sources, Z80 → C translator, static SDL2)
        # follow the tools, so the first conversion starts at once.
        steps = {'Téléchargement de smsggrecomp…': 'deps_step_engine', 'Téléchargement de SDL…': 'deps_step_sdl_fetch',
                 'Compilation du traducteur Z80 → C…': 'deps_step_translator',
                 'Compilation de SDL2 statique (première utilisation)…': 'deps_step_sdl'}

        def progress(label, done, total):
            state.update(label=label, done=done, total=total)

        def worker():
            try:
                if os.name == 'nt':
                    if missing.get('git'):
                        updater.install_git(progress)
                    if missing.get('compiler'):
                        updater.install_toolchain(progress)
                elif missing.get('packages'):
                    updater.install_linux_packages(missing['packages'], progress)
                from .core import dependencies, dependencies_ready, reset_stop
                if not dependencies_ready():
                    reset_stop()
                    state.update(label='', total=0, step='deps_step_start')
                    dependencies(emit=lambda text: state.update(step=steps.get(text, text)))
                state['result'] = ('ok', None)
            except updater.ToolInstallError as error:
                state['result'] = ('failed', str(error))
            except Exception as error:
                state['result'] = ('failed', str(error) or type(error).__name__)

        def poll():
            if not window.winfo_exists():
                return
            label, done, total = state['label'], state['done'], state['total']
            if label and total:
                if str(bar.cget('mode')) != 'determinate':
                    bar.stop()
                    bar.configure(mode='determinate')
                bar.configure(maximum=total, value=done)
                if label in ('Download', 'Install'):
                    step.configure(text=self.tr('tools_step_packages' if label == 'Install' else 'tools_step_fetch'))
                    detail.configure(text=f'{done * 100 // max(total, 1)} %')
                else:
                    step.configure(text=self.tr('tools_step_download', name=label))
                    detail.configure(text=f'{done / 1048576:.1f} / {total / 1048576:.1f} MB')
            elif state['step']:
                if str(bar.cget('mode')) != 'indeterminate':
                    bar.configure(mode='indeterminate')
                    bar.start(12)
                key = state['step']
                step.configure(text=self.tr(key) if key in STRINGS else log_text(key, self.language))
                detail.configure(text=self.tr('deps_step_hint'))
            if state['result'] is None:
                window.after(150, poll)
                return
            bar.stop()
            window.destroy()
            self.updating = False
            self.set_controls(True)
            outcome, error = state['result']
            if outcome == 'ok':
                self.messages.put(('log', self.tr('tools_done')))
                messagebox.showinfo(APP_NAME, self.tr('tools_done'), parent=self.app)
                retry()
            else:
                manual = (self.tr('tools_manual_windows') if os.name == 'nt' else
                          'sudo ' + ' '.join(updater.linux_install_command(missing.get('packages', ()))))
                messagebox.showerror(APP_NAME, self.tr('tools_failed', error=error) + '\n\n' + manual,
                                     parent=self.app)

        threading.Thread(target=worker, daemon=True).start()
        poll()

    def raise_existing(self, name):
        """One help page and one leaderboard at a time: a second click brings
        the open window to the front instead of opening another."""
        window = getattr(self, name, None)
        try:
            if window is not None and window.winfo_exists():
                window.deiconify()
                window.lift()
                window.focus_force()
                return True
        except tk.TclError:
            pass
        setattr(self, name, None)
        return False

    def show_help(self):
        """How Retro-Recomp works, in five steps and the keys every game
        shares; the full guides are one click away."""
        if self.raise_existing('help_window'):
            return
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        self.help_window = window
        window.withdraw()
        window.title(f"{APP_NAME} — {self.tr('help_title')}")
        window.configure(bg=background)
        window.transient(self.app)
        # The page scrolls when the screen is shorter than it (small laptops).
        frame = tk.Frame(window, bg=background, highlightthickness=1, highlightbackground=COLORS['gold'])
        frame.pack(fill='both', expand=True)
        scroller = tk.Canvas(frame, bg=background, highlightthickness=0, borderwidth=0)
        bar = ttk.Scrollbar(frame, orient='vertical', command=scroller.yview)
        scroller.configure(yscrollcommand=bar.set)
        scroller.pack(side='left', fill='both', expand=True)
        body = tk.Frame(scroller, bg=background, padx=24, pady=18)
        scroller.create_window(0, 0, window=body, anchor='nw')
        body.bind('<Configure>', lambda event: scroller.configure(scrollregion=scroller.bbox('all')))
        def wheel(event):
            if bar.winfo_ismapped():
                scroller.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        window.bind('<MouseWheel>', wheel)
        window.pictures = []
        if self.banner is not None:
            tk.Label(body, image=self.banner, bg=background).pack(anchor='w')
        tk.Label(body, text=self.tr('help_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 13, 'bold')).pack(anchor='w', pady=(10, 2))
        tk.Label(body, text=self.tr('help_intro'), bg=background, fg=COLORS['text'], font=(self.ui_font, 10),
                 wraplength=600, justify='left').pack(anchor='w', pady=(0, 12))
        steps = tk.Frame(body, bg=background)
        steps.pack(fill='x')
        icons = ('add_rom_folder', 'refresh', 'play', 'new_paths', None)
        rows = []
        for index, icon in enumerate(icons, 1):
            row = tk.Frame(steps, bg=background)
            badge = tk.Canvas(row, width=46, height=58, bg=background, highlightthickness=0)
            badge.pack(side='left', anchor='n')
            # A gold pixel tile with the step's picture; a dotted line joins the steps.
            badge.create_rectangle(4, 4, 42, 42, fill=COLORS['button'], outline=COLORS['gold'], width=2)
            badge.create_rectangle(4, 4, 12, 12, fill=COLORS['gold'], outline='')
            badge.create_text(8, 8, text=str(index), fill=COLORS['gold_text'], font=(self.ui_font, 7, 'bold'))
            if icon:
                picture = make_icon(window, icon, COLORS['gold'], size=22)
            else:
                try:
                    picture = _scaled_photo(ASSETS / 'assets/board-trophy.png', window, 26 / 72)
                except (OSError, ValueError, tk.TclError):
                    picture = ''
            window.pictures.append(picture)
            badge.create_image(24, 25, image=picture)
            if index < len(icons):
                for y in range(46, 58, 4):
                    badge.create_rectangle(22, y, 25, y + 2, fill=COLORS['subtle_border'], outline='')
            text = tk.Frame(row, bg=background)
            text.pack(side='left', fill='x', padx=(12, 0))
            tk.Label(text, text=self.tr(f'help_step{index}'), bg=background, fg=COLORS['text'],
                     font=(self.ui_font, 10, 'bold')).pack(anchor='w', pady=(4, 0))
            tk.Label(text, text=self.tr(f'help_step{index}_text'), bg=background, fg=COLORS['muted'],
                     font=(self.ui_font, 9), wraplength=540, justify='left').pack(anchor='w')
            rows.append(row)
        keys = tk.Frame(body, bg=COLORS['field'], highlightthickness=1, highlightbackground=COLORS['subtle_border'],
                        padx=12, pady=10)
        tk.Label(keys, text=self.tr('help_keys'), bg=COLORS['field'], fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).grid(row=0, column=0, columnspan=6, sticky='w', pady=(0, 6))
        for column, (key, label) in enumerate((('F1', 'help_key_help'), ('F2', 'help_key_menu'),
                                               ('F3', 'help_key_filters'), ('F4', 'help_key_fullscreen'),
                                               ('F8 F9', 'help_key_states'), ('F12', 'help_key_learning'))):
            cell = tk.Frame(keys, bg=COLORS['field'])
            cell.grid(row=1, column=column, sticky='w', padx=(0, 14))
            tk.Label(cell, text=key, bg=COLORS['button'], fg=COLORS['gold'], font=(self.ui_font, 8, 'bold'),
                     padx=6, pady=1, highlightthickness=1, highlightbackground=COLORS['border']).pack(anchor='w')
            tk.Label(cell, text=self.tr(label), bg=COLORS['field'], fg=COLORS['text'],
                     font=(self.ui_font, 8)).pack(anchor='w', pady=(3, 0))
        foot = tk.Frame(body, bg=background)
        tk.Label(foot, text=self.tr('help_private'), bg=background, fg=COLORS['muted'],
                 font=(self.ui_font, 8)).pack(side='left')
        ttk.Button(foot, text=self.tr('close'), command=window.destroy).pack(side='right')
        ttk.Button(foot, text=self.tr('help_guides'), command=lambda: webbrowser.open_new_tab(HELP_URL)).pack(
            side='right', padx=(0, 8))
        window.bind('<Escape>', lambda event: window.destroy())
        # The steps arrive one after the other, then the keys and the buttons.
        def reveal(index=0):
            if not window.winfo_exists():return
            if index < len(rows):
                rows[index].pack(fill='x', pady=(0, 2))
                window.after(110, reveal, index + 1)
            else:
                keys.pack(fill='x', pady=(12, 0))
                foot.pack(fill='x', pady=(14, 0))
        for row in rows:
            row.pack(fill='x', pady=(0, 2))
        keys.pack(fill='x', pady=(12, 0))
        foot.pack(fill='x', pady=(14, 0))
        window.update_idletasks()
        width, height = body.winfo_reqwidth() + 2, body.winfo_reqheight() + 2
        for widget in (*rows, keys, foot):
            widget.pack_forget()
        from .dialogs import screen_room
        room_width, room_height = screen_room(self.app)
        if height > room_height:
            bar.pack(side='right', fill='y')
            width += bar.winfo_reqwidth()
        scroller.configure(width=body.winfo_reqwidth(), height=min(height, room_height))
        center_dialog(window, self.app, width, height)
        window.minsize(min(width, 420), min(height, 320))
        window.deiconify()
        reveal()

    def show_leaderboard(self):
        """The shared base's ranking in a window: podium order, pseudonyms,
        games and points, all time or this month, with the player's own line."""
        if not SENDING_AVAILABLE or self.raise_existing('board_window'):return
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        self.board_window = window
        window.withdraw()
        window.title(f"{APP_NAME} — {self.tr('leaderboard')}")
        window.configure(bg=background)
        window.transient(self.app)
        body = tk.Frame(window, bg=background, padx=18, pady=14,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        # The site's trophy and class gems, as converter pictures.
        pictures = window.pictures = {}
        for name, size in (('trophy', 72), ('gem-gold', 20), ('gem-platinum', 20), ('gem-diamond', 20)):
            try:
                pictures[name] = _scaled_photo(ASSETS / f'assets/board-{name}.png',
                                               window, size / 40 if name.startswith('gem') else size / 72)
            except (OSError, ValueError, tk.TclError):
                pictures[name] = ''
        top = tk.Frame(body, bg=background)
        top.pack(fill='x')
        tk.Label(top, image=pictures['trophy'], bg=background).pack(side='left', padx=(0, 12))
        titles = tk.Frame(top, bg=background)
        titles.pack(side='left', fill='y')
        tk.Label(titles, text=self.tr('leaderboard').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 14, 'bold')).pack(anchor='w', pady=(6, 0))
        note = tk.Label(titles, text=self.tr('leaderboard_loading'), bg=background, fg=COLORS['muted'],
                        font=(self.ui_font, 9), wraplength=400, justify='left')
        note.pack(anchor='w')
        period = tk.StringVar(value='all')
        switches = tk.Frame(top, bg=background)
        switches.pack(side='right', anchor='n', pady=(8, 0))
        for value, key in (('month', 'leaderboard_month'), ('all', 'leaderboard_all')):
            ttk.Radiobutton(switches, text=self.tr(key), value=value, variable=period,
                            command=lambda: load()).pack(side='right', padx=(8, 0))
        # Podium: second, first, third, on steps of different heights.
        podium = tk.Canvas(body, height=196, bg=background, highlightthickness=0)
        podium.pack(fill='x', pady=(10, 8))
        podium.rows = []
        podium.bind('<Configure>', lambda event: draw_podium(podium.rows))
        columns = ('rank', 'player', 'games', 'gold', 'platinum', 'diamond', 'points')
        table = ttk.Treeview(body, columns=columns, show='headings', height=9, selectmode='none')
        for key, caption, width, anchor in (
                ('rank', self.tr('leaderboard_rank'), 50, 'e'), ('player', self.tr('leaderboard_player'), 220, 'w'),
                ('games', self.tr('leaderboard_games'), 60, 'e'), ('gold', self.tr('class_gold'), 80, 'e'),
                ('platinum', self.tr('class_platinum'), 90, 'e'), ('diamond', self.tr('class_diamond'), 90, 'e'),
                ('points', self.tr('leaderboard_points'), 80, 'e')):
            table.heading(key, text=caption, image=pictures.get('gem-' + key, ''))
            table.column(key, width=width, anchor=anchor, stretch=key == 'player')
        table.tag_configure('you', foreground=COLORS['gold'])
        table.pack(fill='both', expand=True)
        # The footer is reserved first: a longer note above never clips it.
        you_line = tk.Label(body, text='', bg=background, fg=COLORS['text'], font=(self.ui_font, 9))
        close = ttk.Button(body, text=self.tr('close'), command=window.destroy)
        close.pack(side='bottom', anchor='e', pady=(10, 0), before=table)
        you_line.pack(side='bottom', anchor='w', pady=(8, 0), before=table)

        # Opening animation: the steps rise one after the other (third, second,
        # first), carrying each player's crown, name, points and gems up.
        podium.started = time.monotonic()
        RISE, DELAYS = 0.6, {3: 0.0, 2: 0.18, 1: 0.36}

        def crown(middle, base, place, colour):
            """Gold: five points and a jewel; silver: three points; bronze: a
            low band with two points."""
            shapes = {
                1: (-20, 0, -20, -16, -10, -6, 0, -20, 10, -6, 20, -16, 20, 0),
                2: (-16, 0, -16, -13, -6, -6, 0, -15, 6, -6, 16, -13, 16, 0),
                3: (-15, 0, -15, -10, -7, -5, 0, -11, 7, -5, 15, -10, 15, 0)}
            podium.create_polygon(*[middle + v if i % 2 == 0 else base + v for i, v in enumerate(shapes[place])],
                                  fill=colour, outline='')
            # A darker band at the foot, and one jewel per rank's worth.
            podium.create_rectangle(middle + shapes[place][0], base - 3, middle - shapes[place][0], base,
                                    fill=_tint(colour, '#000000', 0.35), outline='')
            jewels = {1: (-10, 0, 10), 2: (-6, 6), 3: (0,)}[place]
            for offset in jewels:
                podium.create_oval(middle + offset - 2, base - 8, middle + offset + 2, base - 4,
                                   fill=COLORS['panel'], outline='')

        def draw_podium(rows, animate=False):
            podium.rows = rows
            if animate:
                podium.started = time.monotonic()
            podium.delete('all')
            width, bottom = podium.winfo_width(), int(podium.cget('height'))
            if width < 300:
                return
            elapsed = time.monotonic() - podium.started
            step = 170
            left = (width - 3 * step) // 2
            # Each place: its column, the top of its name, and its step's height.
            places = {2: (left, 38, 100), 1: (left + step, 16, 122), 3: (left + 2 * step, 56, 82)}
            shades = {1: COLORS['gold'], 2: '#c9ced6', 3: '#c58a4a'}
            if not rows:
                podium.create_text(width // 2, bottom // 2, text=self.tr('leaderboard_empty'),
                                   fill=COLORS['muted'], font=(self.ui_font, 9))
                return
            podium.create_line(left, bottom - 1, left + 3 * step, bottom - 1, fill=COLORS['border'])
            moving = False
            for place in (3, 2, 1):
                x, top, full = places[place]
                progress = min(1.0, max(0.0, (elapsed - DELAYS[place]) / RISE))
                moving |= progress < 1.0
                eased = 1 - (1 - progress) ** 3
                height = max(2, round(full * eased))
                shift = full - height
                middle = x + step // 2
                podium.create_rectangle(x + 8, bottom - height, x + step - 8, bottom - 1,
                                        fill=COLORS['button'], outline=shades[place])
                podium.create_rectangle(x + 8, bottom - height, x + step - 8, bottom - height + 3,
                                        fill=shades[place], outline='')
                if height > 44:
                    podium.create_text(middle, bottom - (height - 40) // 2 - 2, text=str(place),
                                       fill=shades[place], font=(self.ui_font, 16, 'bold'))
                if place > len(rows) or progress < 0.2:
                    continue
                top += shift
                entry, counts = rows[place - 1]
                name = entry.get('pseudonym') or self.tr('leaderboard_anonymous')
                crown(middle, top - 4, place, shades[place])
                podium.create_text(middle, top + 9, text=name, fill=COLORS['text'],
                                   font=(self.ui_font, 10, 'bold'), width=step_width - 16)
                podium.create_text(middle, top + 28, text=f"{entry.get('total', 0)} pts",
                                   fill=shades[place], font=(self.ui_font, 9, 'bold'))
                if self.title_name(entry.get('title')):
                    podium.create_text(middle, top + 43, text=self.title_name(entry.get('title')),
                                       fill=COLORS['muted'], font=(self.ui_font, 8), width=step_width - 16)
                # The three class gems with this player's counts, on the step.
                gems = [(pictures.get(f'gem-{kind}'), counts.get(kind, 0)) for kind in ('gold', 'platinum', 'diamond')]
                spot = middle - 66
                for picture, count in gems:
                    if picture:
                        podium.create_image(spot + 10, bottom - height + 22, image=picture)
                    podium.create_text(spot + 22, bottom - height + 22, text=str(count), anchor='w',
                                       fill=COLORS['text'], font=(self.ui_font, 9))
                    spot += 46
            if moving or elapsed < DELAYS[1] + RISE + 0.05:
                pending = getattr(podium, 'frame', None)
                if pending:
                    podium.after_cancel(pending)
                podium.frame = podium.after(16, lambda: window.winfo_exists() and draw_podium(podium.rows))
            else:
                podium.frame = None

        step_width = 170

        def show(answer, error):
            if not window.winfo_exists():return
            table.delete(*table.get_children())
            if error:
                note.configure(text=error)
                draw_podium([])
                return
            entries = answer.get('entries', [])
            note.configure(text=self.tr('leaderboard_demo') if answer.get('demo')
                           else self.tr('leaderboard_empty') if not entries else self.tr('leaderboard_rules'))
            mine = (self.player.get('profile') or {}).get('pseudonym') or (self.player.get('account') or {}).get('pseudonym')
            rows, lines = [], []
            for entry in entries:
                # The server counts classes per console: {console: {gold, platinum, diamond}}.
                counts = {}
                for console in (entry.get('counts') or {}).values():
                    for name, value in (console.items() if isinstance(console, dict) else ()):
                        if isinstance(value, (int, float)):
                            counts[name] = counts.get(name, 0) + int(value)
                rows.append((entry, counts))
                name = entry.get('pseudonym') or self.tr('leaderboard_anonymous')
                # The title the player chose on the site, after the pseudonym.
                shown = name + (' · ' + self.title_name(entry.get('title')) if self.title_name(entry.get('title')) else '')
                lines.append(((entry.get('rank', ''), shown, entry.get('games', 0), counts.get('gold', 0),
                               counts.get('platinum', 0), counts.get('diamond', 0), entry.get('total', 0)),
                              ('you',) if mine and name == mine else ()))
            for values, tags in lines:
                table.insert('', 'end', values=values, tags=tags)
            draw_podium(rows[:3], animate=True)
            you = answer.get('you') or {}
            if you.get('rank'):
                you_line.configure(text=self.tr('leaderboard_you', rank=you['rank'], points=you.get('total', 0)))
            elif online.account():
                you_line.configure(text=self.tr('account_unranked', points=you.get('total', 0)))
            else:
                you_line.configure(text='')
        def load():
            note.configure(text=self.tr('leaderboard_loading'))
            wanted = period.get()
            result = []
            def worker():
                # No Tk call here: the window polls for the answer.
                try:result.append((online.board(wanted), None))
                except (online.ServiceError, online.ServiceConnectionError) as exc:
                    result.append((None, self.online_message(exc)))
            def poll():
                if not window.winfo_exists():return
                if result:show(*result[0])
                else:window.after(50, poll)
            threading.Thread(target=worker, daemon=True).start()
            poll()
        window.bind('<Escape>', lambda event: window.destroy())
        window.update_idletasks()
        center_dialog(window, self.app, 720, 680)
        window.deiconify()
        load()

    def sign_in_dialog(self):
        """E-mail, then the e-mailed code; True once this converter has a token."""
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        body = tk.Frame(window, bg=background, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('signin_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
        tk.Label(body, text=self.tr('signin_intro'), bg=background, fg=COLORS['text'], font=(self.ui_font, 9),
                 wraplength=400, justify='left').grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 12))
        tk.Label(body, text=self.tr('signin_email'), bg=background, fg=COLORS['muted'],
                 font=(self.ui_font, 9)).grid(row=2, column=0, columnspan=2, sticky='w')
        email = tk.StringVar(value=(online.account() or {}).get('email', ''))
        email_field = ttk.Entry(body, textvariable=email, width=44)
        email_field.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(2, 8))
        terms = tk.BooleanVar(value=False)
        consent = tk.Frame(body, bg=background)
        consent.grid(row=4, column=0, columnspan=2, sticky='w')
        ttk.Checkbutton(consent, text=self.tr('signin_terms'), variable=terms).pack(side='left')
        privacy = tk.Label(consent, text=self.tr('signin_privacy'), bg=background, fg=COLORS['gold_hover'],
                           font=(self.ui_font, 9, 'underline'), cursor='hand2')
        privacy.pack(side='left', padx=(8, 0))
        privacy.bind('<Button-1>', lambda event:webbrowser.open_new_tab(online.service_url() + '/privacy'))
        code_label = tk.Label(body, text=self.tr('signin_code'), bg=background, fg=COLORS['muted'],
                              font=(self.ui_font, 9))
        code = tk.StringVar()
        code_field = ttk.Entry(body, textvariable=code, width=12)
        message = tk.StringVar()
        tk.Label(body, textvariable=message, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                 wraplength=400, justify='left').grid(row=7, column=0, columnspan=2, sticky='w', pady=(10, 0))
        buttons = tk.Frame(body, bg=background)
        buttons.grid(row=8, column=0, columnspan=2, sticky='e', pady=(14, 0))
        ttk.Button(buttons, text=self.tr('knowledge_cancel'), command=window.destroy).pack(side='right')
        go = ttk.Button(buttons, text=self.tr('signin_send_code'), style='Primary.TButton')
        go.pack(side='right', padx=(0, 8))
        state = {'stage': 'email', 'signed': False}
        def run(call, done):
            # The network call runs off Tk; the dialog polls for its answer.
            go.state(['disabled'])
            answer = {}
            def worker():
                try:answer['value'] = call()
                except Exception as error:answer['error'] = error
            threading.Thread(target=worker, daemon=True).start()
            def wait():
                if not window.winfo_exists():return
                if not answer:
                    window.after(100, wait)
                    return
                go.state(['!disabled'])
                if 'error' in answer:message.set(self.online_message(answer['error']))
                else:done(answer['value'])
            wait()
        def code_sent(_):
            state['stage'] = 'code'
            message.set(self.tr('signin_code_sent', email=email.get().strip()))
            code_label.grid(row=5, column=0, columnspan=2, sticky='w', pady=(10, 0))
            code_field.grid(row=6, column=0, sticky='w', pady=(2, 0))
            go.configure(text=self.tr('signin_submit'))
            code_field.focus_set()
        def signed_in(data):
            state['signed'] = True
            self.messages.put(('log', self.tr('signin_done', email=data['email'])))
            window.destroy()
            self.refresh_player(force=True)
        def submit():
            address = email.get().strip()
            if state['stage'] == 'email' or not code.get().strip():
                if not terms.get():
                    message.set(self.tr('online_terms_needed'))
                    return
                run(lambda:online.request_code(address, self.language), code_sent)
            else:
                from .platforms import target_id
                run(lambda:online.sign_in(address, code.get().strip(), f'Retro-Recomp {__version__} ({target_id()})'),
                    signed_in)
        go.configure(command=submit)
        window.bind('<Escape>', lambda event:window.destroy())
        window.bind('<Return>', lambda event:go.invoke())
        window.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - window.winfo_reqwidth()) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - window.winfo_reqheight()) // 3
        window.geometry(f'+{max(0, x)}+{max(0, y)}')
        window.deiconify()
        window.grab_set()
        email_field.focus_set()
        self.app.wait_window(window)
        return state['signed']

    def import_knowledge(self):
        """Check the chosen file first; import only unknown discoveries."""
        if self.busy or self.updating:return
        from .knowledge_exchange import SUFFIX, preview_import
        name = filedialog.askopenfilename(parent=self.app, title=self.tr('knowledge_import'),
            filetypes=[(self.tr('knowledge_file'), '*' + SUFFIX)])
        if name:self.knowledge_task(lambda:('preview', (Path(name), preview_import(Path(name)))),
                                    'knowledge_checking')

    def achievement(self, count, detail, action):
        """A small 'achievement unlocked' card; True when its action is chosen."""
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        chosen = tk.BooleanVar(value=False)
        body = tk.Frame(window, bg=background, padx=22, pady=18,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        art = tk.Canvas(body, width=72, height=72, bg=background, highlightthickness=0)
        art.grid(row=0, column=0, rowspan=2, sticky='n', padx=(0, 16))
        for y, row in enumerate(TROPHY):
            for x, mark in enumerate(row):
                if mark != '.':
                    art.create_rectangle(6 + 5*x, 6 + 5*y, 11 + 5*x, 11 + 5*y, outline='',
                                         fill=COLORS['gold_hover'] if mark == 'o' else COLORS['gold'])
        sparkles = [art.create_rectangle(x, y, x+3, y+3, fill=COLORS['gold_hover'], outline='', state='hidden')
                    for x, y in ((1, 3), (67, 9), (66, 60), (2, 48))]
        tk.Label(body, text=self.tr('knowledge_achievement').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).grid(row=0, column=1, sticky='w')
        line = tk.Frame(body, bg=background)
        line.grid(row=1, column=1, sticky='w')
        number = tk.Label(line, text='0', bg=background, fg=COLORS['gold_hover'], font=(self.ui_font, 26, 'bold'))
        number.pack(side='left')
        tk.Label(line, text=self.tr('knowledge_discovery' if count == 1 else 'knowledge_discoveries'),
                 bg=background, fg=COLORS['text'], font=(self.ui_font, 11)).pack(side='left', padx=(8, 0), pady=(12, 0))
        tk.Label(body, text=detail, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                 wraplength=380, justify='left').grid(row=2, column=0, columnspan=2, sticky='w', pady=(12, 16))
        buttons = tk.Frame(body, bg=background)
        buttons.grid(row=3, column=0, columnspan=2, sticky='e')
        ttk.Button(buttons, text=self.tr('knowledge_cancel'), command=window.destroy).pack(side='right')
        go = ttk.Button(buttons, text=action, style='Primary.TButton',
                        command=lambda:(chosen.set(True), window.destroy()))
        go.pack(side='right', padx=(0, 8))
        started = time.monotonic()
        def animate(frame=0):
            # The count rolls up for 0.8 s; the sparkles keep twinkling.
            if not window.winfo_exists():return
            progress = min(1.0, (time.monotonic() - started) / 0.8)
            number.configure(text=str(round(count * (1 - (1 - progress) ** 3))))
            for index, item in enumerate(sparkles):
                art.itemconfigure(item, state='normal' if (frame // 4 + index) % 3 else 'hidden')
            window.after(40, animate, frame + 1)
        window.bind('<Escape>', lambda event:window.destroy())
        window.bind('<Return>', lambda event:go.invoke())
        window.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - window.winfo_reqwidth()) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - window.winfo_reqheight()) // 3
        window.geometry(f'+{max(0, x)}+{max(0, y)}')
        window.deiconify()
        animate()
        window.grab_set()
        go.focus_set()
        self.app.wait_window(window)
        return chosen.get()

    def closing_card(self, games, count):
        """Before closing: discoveries wait to be sent. Returns 'recompile',
        'send', 'skip' or None (cancel); see offer_closing_card."""
        import math
        background = COLORS['panel']
        window = tk.Toplevel(self.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=background)
        window.resizable(False, False)
        window.transient(self.app)
        choice = tk.StringVar(value='')
        body = tk.Frame(window, bg=background, padx=22, pady=18)
        body.pack(fill='both', expand=True)
        art = tk.Canvas(body, width=320, height=82, bg=background, highlightthickness=0)
        art.grid(row=0, column=0, columnspan=2, pady=(0, 10))   # centred above the text
        def sprite(rows, left, top, cell, light):
            items = []
            for y, row in enumerate(rows):
                for x, mark in enumerate(row):
                    if mark != '.':
                        items.append((art.create_rectangle(left + cell*x, top + cell*y, left + cell*(x+1),
                            top + cell*(y+1), outline='', fill=light if mark == 'o' else COLORS['gold']), mark))
            return items
        sprite(CARTRIDGE, 8, 18, 6, COLORS['gold_hover'])
        cloud = sprite(CLOUD, 228, 16, 7, COLORS['header'])
        # A faint dotted arc; the discoveries travel along it.
        start, end, rise = (60, 40), (232, 38), 26
        point = lambda t: (start[0] + (end[0]-start[0])*t, start[1] + (end[1]-start[1])*t - math.sin(math.pi*t)*rise)
        for step in range(1, 24):
            x, y = point(step / 24)
            art.create_rectangle(x, y, x+2, y+2, outline='', fill=COLORS['border'])
        bits = [art.create_rectangle(0, 0, 8, 8, outline='', fill=COLORS['gold_hover'], state='hidden')
                for _ in range(4)]
        # On arrival each bit shrinks into the base and bursts into four sparks.
        sparks = [[art.create_rectangle(0, 0, 3, 3, outline='', fill=COLORS['gold_hover'], state='hidden')
                   for _ in range(4)] for _ in bits]
        tk.Label(body, text=self.tr('closing_title').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).grid(row=1, column=0, columnspan=2, sticky='w')
        line = tk.Frame(body, bg=background)
        line.grid(row=2, column=0, columnspan=2, sticky='w')
        number = tk.Label(line, text='0', bg=background, fg=COLORS['gold_hover'], font=(self.ui_font, 26, 'bold'))
        number.pack(side='left')
        tk.Label(line, text=self.tr('closing_count_one' if count == 1 else 'closing_count'), bg=background,
                 fg=COLORS['text'], font=(self.ui_font, 11)).pack(side='left', padx=(8, 0), pady=(12, 0))
        soon = '' if SENDING_AVAILABLE else '_soon'
        for row, text in enumerate((self.tr('closing_body' + soon, games=games),
                                    self.tr('closing_recompile_note' + soon)), start=3):
            tk.Label(body, text=text, bg=background, fg=COLORS['muted'], font=(self.ui_font, 9),
                     wraplength=420, justify='left').grid(row=row, column=0, columnspan=2, sticky='w', pady=(10, 0))
        buttons = tk.Frame(body, bg=background)
        buttons.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(16, 0))
        def pick(value):
            choice.set(value)
            window.destroy()
        go = ttk.Button(buttons, text=self.tr('closing_recompile', games=games), style='Primary.TButton',
                        command=lambda:pick('recompile'))
        go.pack(fill='x')
        others = tk.Frame(buttons, bg=background)
        others.pack(pady=(8, 0))   # centred under the main action
        send = ttk.Button(others, text=self.tr('closing_send'), command=lambda:pick('send'))
        send.pack(side='left')
        if not SENDING_AVAILABLE:
            send.state(['disabled'])
            self.tooltips.append(Tooltip(send, lambda: self.tr('tip_closing_send')))
        ttk.Button(others, text=self.tr('closing_skip'), command=lambda:pick('skip')).pack(side='left', padx=8)
        ttk.Button(others, text=self.tr('knowledge_cancel'), command=window.destroy).pack(side='left')
        started = time.monotonic()
        def animate(frame=0):
            # Bits leave the cartridge one after another and land in the base,
            # which glows briefly; the count rolls up meanwhile.
            if not window.winfo_exists():return
            elapsed = time.monotonic() - started
            number.configure(text=str(round(count * (1 - (1 - min(1.0, elapsed / 1.2)) ** 3))))
            landed = False
            for index, item in enumerate(bits):
                t = (elapsed / 1.6 - index * 0.25) % 1.0 if elapsed >= index * 0.4 else None
                if t is None:
                    continue
                x, y = point(min(t, 0.86))
                burst = max(0.0, (t - 0.86) / 0.14)
                half = 4 * (1 - burst)
                art.coords(item, x - half, y - half, x + half, y + half)
                art.itemconfigure(item, state='normal' if half >= 1 else 'hidden')
                for (dx, dy), spark in zip(((-1, -1), (1, -1), (-1, 1), (1, 1)), sparks[index]):
                    reach = 3 + 11 * burst
                    art.coords(spark, x + dx*reach - 1, y + dy*reach - 1, x + dx*reach + 2, y + dy*reach + 2)
                    art.itemconfigure(spark, state='normal' if 0 < burst < 1 else 'hidden',
                                      fill=COLORS['gold_hover'] if burst < 0.5 else COLORS['gold'])
                landed |= 0 < burst < 0.5   # a short glow per arrival
            for item, mark in cloud:
                if mark == 'o':
                    art.itemconfigure(item, fill=COLORS['gold'] if landed else COLORS['header'])
            window.after(40, animate, frame + 1)
        window.bind('<Escape>', lambda event:window.destroy())
        window.update_idletasks()
        x = self.app.winfo_rootx() + (self.app.winfo_width() - window.winfo_reqwidth()) // 2
        y = self.app.winfo_rooty() + (self.app.winfo_height() - window.winfo_reqheight()) // 3
        window.geometry(f'+{max(0, x)}+{max(0, y)}')
        window.deiconify()
        animate()
        window.grab_set()
        go.focus_set()
        self.app.wait_window(window)
        return choice.get() or None

    def knowledge_done(self, outcome, error):
        self.busy = False
        self.set_controls(True)
        if getattr(self, 'manual_sending', False):
            self.manual_sending = False
            self.sending_finished()
        if self.compiled_view is not None:self.compiled_view.progress.stop()
        if error:
            text = self.tr('knowledge_failed', error=error)
            self.messages.put(('log', text))
            if self.compiled_view is not None:self.compiled_view.status.set(text)
            messagebox.showerror(APP_NAME, text, parent=self.app)
            if self.closing_send:self.close()
            return
        kind, summary = outcome
        if kind == 'send_collect':
            pending = online.pending(summary)
            if not pending['games']:
                if self.closing_send:self.close()
                else:self.knowledge_report(self.tr('knowledge_send_none'))
                return
            detail = (self.tr('knowledge_send_found', games=pending['games'], consoles=len(pending['consoles']))
                      + '\n\n' + self.tr('knowledge_scope'))
            # On the closing card the player already chose to send.
            if self.closing_send or self.achievement(pending['discoveries'], detail, self.tr('knowledge_send_action')):
                self.sending_started()
                self.manual_sending = True
                self.knowledge_task(lambda:('sent', self.upload_discoveries(pending)), 'knowledge_sending')
            return
        if kind in ('sent', 'signed_out'):
            if kind == 'signed_out':
                text = self.tr('signed_out')
                self.render_player(None)
            elif 'error' in summary:
                text = summary['error']
            else:
                text = self.tr('knowledge_send_done', games=summary['games'], kib=summary.get('bytes', 0) / 1024)
                if (summary.get('claims') or {}).get('new'):
                    text += ' ' + self.tr('knowledge_send_new', count=summary['claims']['new'])
                if summary.get('claims'):
                    self.refresh_player(force=True)
                if summary.get('claims_refused'):
                    # Quietly, in the log only: the file itself was received.
                    self.messages.put(('log', self.tr('claims_refused', reason=', '.join(summary['claims_refused']))))
            self.messages.put(('log', text))
            if self.compiled_view is not None:self.compiled_view.status.set(text)
            if self.closing_send:
                if 'error' in (summary or {}):messagebox.showwarning(APP_NAME, text, parent=self.app)
                self.close()
            else:
                messagebox.showinfo(APP_NAME, text, parent=self.app)
            return
        if kind == 'collect':
            omitted = summary['omitted']
            if not summary['games']:
                text = self.tr('knowledge_export_none', known=omitted['already_known'],
                               missing=omitted['missing_rom'], unqualified=omitted['unqualified'])
                if omitted['missing_rom']:
                    text += ' ' + self.tr('knowledge_missing_hint')
                self.knowledge_report(text)
                return
            detail = (self.tr('knowledge_export_found', games=summary['games'], consoles=len(summary['consoles']))
                      + '\n\n' + self.tr('knowledge_scope'))
            if not self.achievement(summary['discoveries'], detail, self.tr('knowledge_export_action')):
                return
            from datetime import date
            from .knowledge_exchange import SUFFIX, write_knowledge
            name = filedialog.asksaveasfilename(parent=self.app, title=self.tr('knowledge_export'),
                defaultextension=SUFFIX, initialfile=f'Retro-Recomp-knowledge-{date.today():%Y-%m-%d}{SUFFIX}',
                filetypes=[(self.tr('knowledge_file'), '*' + SUFFIX)])
            if name:self.knowledge_task(lambda:('export', write_knowledge(summary, Path(name))))
            return
        if kind == 'preview':
            source, preview = summary
            if not preview['discoveries']:
                self.knowledge_report(self.tr('knowledge_import_nothing'))
                return
            detail = self.tr('knowledge_import_found', games=preview['games'], consoles=len(preview['consoles']))
            if self.achievement(preview['discoveries'], detail, self.tr('knowledge_import_action')):
                from .knowledge_exchange import import_knowledge
                self.knowledge_task(lambda:('import', import_knowledge(source)))
            return
        if kind == 'export':
            omitted = summary['omitted']
            text = self.tr('knowledge_export_done', games=summary['games'], consoles=len(summary['consoles']),
                           kib=summary['bytes'] / 1024, known=omitted['already_known'],
                           missing=omitted['missing_rom'], unqualified=omitted['unqualified'])
            if omitted['missing_rom']:
                text += ' ' + self.tr('knowledge_missing_hint')
        else:
            text = self.tr('knowledge_import_done', games=summary['new'] + summary['enriched'],
                           new=summary['new'], enriched=summary['enriched'], unchanged=summary['unchanged'])
        self.knowledge_report(text)

    def knowledge_report(self, text):
        self.messages.put(('log', text))
        if self.compiled_view is not None:self.compiled_view.status.set(text)
        messagebox.showinfo(APP_NAME, text, parent=self.app)

    def remember_export(self, result, preferences):
        if result.get('status') not in ('success','current','existing') or not result.get('report'):return
        from .compiled_games import game_from_report, refresh
        # Called by the conversion worker, before its result/done events. A
        # close-after-current-games cannot kill a late inventory writer.
        try:
            game = game_from_report(Path(result['report']),Path(result['executable']).parent,
                                    source=result.get('rom',''))
            self.compiled_inventory.remember(refresh(game,preferences))
            self.compiled_inventory.save()
            self.messages.put(('collection_changed',))
        except (OSError,ValueError,TypeError,KeyError):pass

    def reconvert_games(self, games):
        if self.busy or self.updating or not games:return
        if not self.ensure_build_tools(lambda: self.reconvert_games(games)):return
        from .platforms import target_id
        for game in games:
            if game.target and game.target != target_id():
                messagebox.showinfo(APP_NAME,self.tr('game_other_platform'))
                return
        options=self.preferences()
        from .compiled_games import Game
        known=[*self.compiled_inventory.snapshot(),*(Game('',i.system,i.sha256,i.title,source=str(i.path))
               for i in self.items.values() if i.system and i.sha256)]
        self.busy=True
        self.cancel.clear()
        self.set_controls(False)
        self.compiled_view.progress.start(15)
        self.compiled_view.status.set(self.tr('rom_searching'))
        def worker():
            from .rom_sources import RomSources
            try:pairs=RomSources().resolve(games,options,known=known,cancel=self.cancel)
            except Exception:pairs=[(game,None) for game in games]
            self.messages.put(('sources_ready',pairs))
        threading.Thread(target=worker,daemon=True).start()

    def finish_source_lookup(self, pairs):
        self.busy=False
        self.compiled_view.progress.stop()
        self.set_controls(True)
        if self.close_when_idle and (not self.closing_after_recompile or self.cancel.is_set()):
            self.close()
            return
        if self.cancel.is_set():return
        chosen=[]
        for game,source in pairs:
            if source is None:
                # While closing, or for new paths, a missing ROM waits for later.
                if self.closing_after_recompile or self.skip_missing_sources:continue
                name = filedialog.askopenfilename(parent=self.app,
                    title=self.tr('locate_source',title=game.title))
                if not name:return
                source = Path(name)
            chosen.append((game,source))
        if chosen:self.begin_reconvert(chosen)
        elif self.close_when_idle:self.close()

    def offer_closing_card(self):
        """Before closing: games whose new paths are not recompiled yet, on the
        consoles that share discoveries. True keeps the window open."""
        self.closing_checked = True
        from .compiled_games import refresh_changed
        try:refresh_changed(self.compiled_inventory, self.preferences(), budget=2.0)
        except Exception:pass
        games = self.games_with_new_paths(shared_only=True)
        if not games:return False
        choice = self.closing_card(len(games), sum(game.hints for game in games))
        if choice is None:
            self.closing_checked = False
            return True
        if choice == 'send':
            self.send_knowledge(closing=True)
            return True
        if choice != 'recompile':return False
        self.closing_after_recompile = self.close_when_idle = True
        self.recompile_new_paths(games)
        return True

    def begin_reconvert(self, chosen):
        options = self.preferences()
        use_shared = options.pop('use_shared_base', False)
        for key in ('coverage_default_revision','gb_validation_default_revision','output','custom_output',
                    'system_mode','platform','feedback_paths','rom_paths','jobs','overwrite','send_after_batch'):
            options.pop(key,None)
        # Always rebuild, but only the player shell when nothing else changed.
        options['force'] = True
        options['rediscover'] = False
        jobs = self.jobs.get()
        self.busy = True
        self.cancel.clear()
        self.set_controls(False)
        self.compiled_view.progress.start(15)
        self.compiled_view.clear_log()
        self.compiled_view.status.set(self.tr('reconverting_games'))
        def worker():
            from concurrent.futures import ThreadPoolExecutor, as_completed
            from .batch import _convert_in_budget, _embedded_export_identity, reported_owner
            from .freshness import digest
            from .compiled_games import game_from_report, refresh, read_json
            counts = {'success':0,'failed':0}
            errors, results = [], []
            cartridge_locks={(game.system,game.identity):threading.Lock() for game,_ in chosen}
            # Like a batch from the queue: the shared base's paths first.
            shared = self.prepare_shared_paths([f'{game.system}:{game.identity}' for game,_ in chosen], use_shared)
            def convert(pair):
                game,source = pair
                if self.cancel.is_set():return None
                item = identify(source,game.system)
                if item.error or item.sha256 != game.identity:
                    raise ValueError(self.tr('source_mismatch',title=game.title))
                game.source=str(source.resolve())
                self.compiled_inventory.remember(game)
                self.compiled_inventory.save()
                from .game_details import Cards
                item.cover=Cards().override(game)
                target = Path(game.executable)
                report = read_json(game.report) if game.report else {}
                # Old exports carry neither a receipt nor a marker: accept the
                # reports beside them, as a conversion from the queue does.
                if target.is_file() and not (report.get('export_receipt',{}).get('sha256') == digest(target)
                    or _embedded_export_identity(target)==game.identity
                    or reported_owner(target,game.identity)):
                    raise ValueError(self.tr('game_unverified'))
                item.title = game.title
                standard = report.get('video_model',{}).get('standard')
                if standard in get_profile(item.system).video_modes:item.standard_override = standard
                folder = target.parent/'datas/reports'/item.key
                folder.mkdir(parents=True,exist_ok=True)
                result = _convert_in_budget(jobs,0,item,len(chosen),get_profile(item.system),target.parent,
                    folder,target,[],lambda text:self.messages.put(('log',text)),
                    {**options,'gb_parallel_games':jobs,'ng_parallel_games':jobs,'shared_paths':shared})
                results.append({**result,'system':item.system,'sha256':item.sha256})
                if result['status'] in ('success','current'):
                    game = game_from_report(Path(result['report']),target.parent,source=str(source))
                    self.compiled_inventory.remember(refresh(game,{}))
                return result
            def guarded(pair):
                game,_=pair
                # Copies in different folders still share compiler work files.
                # Serialize an exact cartridge while unrelated games use the pool.
                with cartridge_locks[(game.system,game.identity)]:return convert(pair)
            try:
                with ThreadPoolExecutor(max_workers=jobs) as pool:
                    for future in as_completed([pool.submit(guarded,pair) for pair in chosen]):
                        try:
                            result = future.result()
                            if result is None:continue
                            counts['success' if result['status'] in ('success','current') else 'failed'] += 1
                            if result['status']=='error':errors.append(result.get('message',''))
                        except Exception as exc:
                            counts['failed'] += 1
                            errors.append(str(exc))
                            self.messages.put(('log',str(exc)))
                self.compiled_inventory.save()
            except Exception as exc:
                counts['failed'] += 1
                errors.append(str(exc))
                self.messages.put(('log',str(exc)))
            self.forget_rejected_shared(shared, results)
            if errors:counts['detail']=' · '.join(errors[:2])
            self.messages.put(('collection_done',counts))
        threading.Thread(target=worker,daemon=True).start()

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
        try:
            save_preferences(self.preferences())
        except (OSError, tk.TclError, ValueError):
            pass
        if self.recovered_batch is not None:self.recovered_batch.close()
        self.app.destroy()


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
    if update_error:
        app.after(200, lambda: messagebox.showerror(APP_NAME,
            application.tr('update_failed', error=update_error)))
    if splash:
        splash.step(4, 'splash_ready')
        app.after(250, lambda: (splash.close(), app.deiconify()))
    else:
        app.deiconify()
    app.mainloop()
