from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .batch import BatchItem, identify, convert_batch, system_output
from .publishing import is_pending
from .library import list_games, library_root
from .paths import ROOT, ASSETS, APP_NAME, load_preferences, save_preferences, save_game_language, games_root, preferred_games_root
from .i18n import STRINGS, tr, extended_default, game_boy_validation_default, log_text
from .tooltips import Tooltip
from .windows import set_converter_identity
from .artwork import ICON_SIZES
from .cover_settings import FIELDS as COVER_FIELDS, load_settings as load_cover_settings, save_settings as save_cover_settings
from .cover_sources import PROVIDERS as COVER_PROVIDERS
from .systems import PROFILES, discover_roms, get_profile
from .updater import UpdateConnectionError, UpdateServiceError
from .branding import COLORS, apply_theme, make_icon, ICON_PATHS


PLATFORMS = {'windows-x64': 'Windows x64'}
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
        ('mstan/smsggrecomp', 'https://github.com/mstan/smsggrecomp', 'credits_recompiler'),
        ('mstan/z80-recomp-core', 'https://github.com/mstan/z80-recomp-core', 'credits_native_core'),
        ('superzazu/z80', 'https://github.com/superzazu/z80', 'credits_reference_cpu'),
    )),
    ('Game Gear', (
        ('mstan/smsggrecomp', 'https://github.com/mstan/smsggrecomp', 'credits_recompiler'),
        ('mstan/z80-recomp-core', 'https://github.com/mstan/z80-recomp-core', 'credits_native_core'),
        ('superzazu/z80', 'https://github.com/superzazu/z80', 'credits_reference_cpu'),
    )),
    ('Game Boy', (
        ('arcanite24/gb-recompiled', 'https://github.com/arcanite24/gb-recompiled', 'credits_recompiler'),
    )),
    ('Nintendo NES', (
        ('mstan/nesrecomp', 'https://github.com/mstan/nesrecomp', 'credits_recompiler'),
    )),
    ('Mega Drive (experimental)', (
        ('mstan/segagenesisrecomp', 'https://github.com/mstan/segagenesisrecomp', 'credits_recompiler'),
        ('mstan/m68k-recomp-core', 'https://github.com/mstan/m68k-recomp-core', 'credits_native_core'),
    )),
    ('Super Nintendo (experimental)', (
        ('RetroPortingToolKit/snesrecomp', 'https://github.com/RetroPortingToolKit/snesrecomp', 'credits_recompiler'),
        ('mstan/SuperMarioWorldRecomp', 'https://github.com/mstan/SuperMarioWorldRecomp', 'credits_recompiler'),
    )),
)


HATCH_SPACING = 4


def _tint(base: str, foreground: str, visibility: float = 0.50) -> str:
    """Blend a procedural decoration over the canvas background."""
    channel = lambda color, at: int(color[at:at + 2], 16)
    values = [round(channel(base, at) * (1 - visibility) +
                    channel(foreground, at) * visibility) for at in (1, 3, 5)]
    return '#{:02x}{:02x}{:02x}'.format(*values)


class Application:
    def __init__(self, app: tk.Tk):
        self.app = app
        self.items: dict[str, BatchItem] = {}
        self.results: dict[str, dict] = {}
        self.busy = False
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
        self.status_key, self.status_values = 'ready', {}
        preferences = load_preferences()
        self.language = preferences.get('language') if preferences.get('language') in ('en', 'fr') else 'en'
        app.title(APP_NAME)
        app.geometry('1120x940')
        app.minsize(1060, 780)
        self.style = apply_theme(app)
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
        self.platform_id = preferences.get('platform', 'windows-x64')
        if self.platform_id not in PLATFORMS:
            self.platform_id = 'windows-x64'
        self.extended = tk.BooleanVar(value=extended_default(preferences))
        self.gb_deep_validation = tk.BooleanVar(value=game_boy_validation_default(preferences))
        self.md_advanced_scan = tk.BooleanVar(value=preferences.get('md_advanced_scan', False) is True)
        self.passes = tk.IntVar(value=preferences.get('passes', 3) if isinstance(preferences.get('passes', 3), int) else 3)
        self.frames = tk.IntVar(value=preferences.get('frames', 3600) if isinstance(preferences.get('frames', 3600), int) else 3600)
        saved_jobs = preferences.get('jobs', 3)
        self.jobs = tk.IntVar(value=saved_jobs if isinstance(saved_jobs, int) and 1 <= saved_jobs <= 8 else 3)
        self.use_cover = tk.BooleanVar(value=bool(preferences.get('use_cover', True)))
        self.overwrite = tk.BooleanVar(value=bool(preferences.get('overwrite', True)))
        self.icon_tags = tk.BooleanVar(value=bool(preferences.get('icon_tags', True)))
        self.online = tk.BooleanVar(value=bool(preferences.get('online_cover', True)))

        header = tk.Canvas(app, height=132, bg=COLORS['header'], highlightthickness=0,
                           borderwidth=0)
        self.header = header
        header.pack(fill='x')
        banner_path = ASSETS / 'assets/Retro-Recomp-banner.png'
        try:
            self.banner = tk.PhotoImage(file=str(banner_path))
            header.create_image(24, 0, image=self.banner, anchor='nw', tags='banner')
        except (OSError, tk.TclError):
            self.banner = None
        try:
            self.console_art = tk.PhotoImage(file=str(ASSETS / 'assets/Retro-Recomp-consoles.png'))
        except (OSError, tk.TclError):
            self.console_art = None
        self.brand_tagline = header.create_text(196, 96, text=self.tr('brand_tagline'),
            anchor='nw', fill=COLORS['text'], font=('Segoe UI', 8), tags='brand_tagline')
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
        self.system_name = tk.StringVar(value=self.system_display())
        self.system_field = ttk.Combobox(header, textvariable=self.system_name,
            values=self.system_choices(), width=15, state='readonly')
        self.system_field.bind('<<ComboboxSelected>>', self.change_system)
        self.hint(self.system_field, 'tip_console_format')

        self.platform_name = tk.StringVar(value=PLATFORMS[self.platform_id])
        self.platform_field = ttk.Combobox(header, textvariable=self.platform_name,
            values=tuple(PLATFORMS.values()), width=12, state='readonly')
        self.platform_field.bind('<<ComboboxSelected>>', self.change_platform)
        self.hint(self.platform_field, 'tip_platform')

        self.language_name = tk.StringVar(value='Français' if self.language == 'fr' else 'English')
        self.language_field = ttk.Combobox(header, textvariable=self.language_name,
                                           values=('English', 'Français'), width=9, state='readonly')
        self.language_field.bind('<<ComboboxSelected>>', self.change_language)
        self.hint(self.language_field, 'tip_language')
        self.header_fields = (self.system_field, self.platform_field, self.language_field)
        self.header_labels = {
            key: header.create_text(0, 10, text=self.tr(key), anchor='nw',
                                    fill=COLORS['muted'], font=('Segoe UI', 9), tags='selector_label')
            for key in ('console_format', 'platform', 'language')
        }
        self.header_windows = tuple(header.create_window(0, 28, window=field, anchor='nw')
                                    for field in self.header_fields)
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
        body.rowconfigure(1, weight=4, minsize=240)
        body.rowconfigure(7, weight=2, minsize=110)
        toolbar = ttk.Frame(body)
        self.toolbar = toolbar
        toolbar.grid(row=0, column=0, sticky='ew', padx=24, pady=(16, 10))
        self.button(toolbar, self.tr('add_roms'), self.choose_roms, primary=True).pack(side='left')
        self.button(toolbar, self.tr('add_folder'), self.choose_directory).pack(side='left', padx=8)
        self.button(toolbar, self.tr('remove'), self.remove_selected).pack(side='left')
        self.button(toolbar, self.tr('clear'), self.clear).pack(side='left', padx=8)
        ttk.Label(toolbar, textvariable=self.count, style='Muted.TLabel').pack(side='right')
        self.button(toolbar, self.tr('credits'), self.show_credits).pack(side='right', padx=(0, 12))
        self.update_button = self.button(toolbar, self.tr('check_updates'), self.check_updates)
        self.update_button.pack(side='right', padx=(0, 8))
        self.options_button = self.button(toolbar, self.tr('options'), self.show_options)
        self.options_button.pack(side='right', padx=(0, 8))
        ttk.Label(toolbar, text=f'v{__version__}', style='Muted.TLabel',
                  font=('Segoe UI', 9)).pack(side='right', padx=(0, 12))

        table_frame = ttk.Frame(body)
        table_frame.grid(row=1, column=0, sticky='nsew', padx=24)
        self.table = ttk.Treeview(table_frame, columns=('title', 'system', 'video', 'size', 'cover', 'status'), show='headings', selectmode='extended', height=8)
        for key, caption, width in [('title', self.tr('game'), 350), ('system', self.tr('console'), 125),
                                    ('video', self.tr('video_timing'), 115), ('size', 'ROM', 70),
                                    ('cover', self.tr('cover'), 100), ('status', self.tr('conversion'), 210)]:
            self.table.heading(key, text=caption)
            self.table.column(key, width=width, minwidth=60, stretch=key in ('title', 'status'))
        self.table.tag_configure('error', foreground=COLORS['error'])
        self.table.tag_configure('success', foreground=COLORS['success'])
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side='left', fill='both', expand=True)
        self.hint(self.table, 'tip_table')
        scrollbar.pack(side='right', fill='y')
        self.table.bind('<<TreeviewSelect>>', lambda event: self.selection_changed())
        self.table.bind('<Double-1>', lambda event: self.play())
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
        self.stop_button = ttk.Button(actions, text=self.tr('stop'), command=self.stop, state='disabled')
        self.decorate_button(self.stop_button, 'stop')
        self.stop_button.pack(side='left', padx=8)
        self.hint(self.stop_button, 'tip_stop')
        open_button = ttk.Button(actions, text=self.tr('open_folder'), command=self.open_output)
        self.decorate_button(open_button, 'folder')
        open_button.pack(side='right')
        self.hint(open_button, 'tip_open_folder')
        self.progress = ttk.Progressbar(body, mode='determinate')
        self.progress.grid(row=5, column=0, sticky='ew', padx=24, pady=(0, 8))
        ttk.Label(body, textvariable=self.status, wraplength=850).grid(row=6, column=0, sticky='ew', padx=24, pady=(0, 8))
        log_frame = tk.Frame(body, bg=COLORS['field'], highlightthickness=1, highlightbackground=COLORS['border'])
        log_frame.grid(row=7, column=0, sticky='nsew', padx=24)
        self.log = tk.Text(log_frame, height=10, font=('Consolas', 9), bg=COLORS['field'],
                           fg=COLORS['muted'], relief='flat', padx=10, pady=9,
                           state='disabled', wrap='word', insertbackground=COLORS['gold'])
        log_scroll = ttk.Scrollbar(log_frame, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side='right', fill='y')
        self.log.pack(side='left', fill='both', expand=True)
        footer = ttk.Frame(body)
        footer.grid(row=8, column=0, sticky='ew', padx=24, pady=(10, 16))
        status_dot = tk.Canvas(footer, width=12, height=14, bg=COLORS['background'], highlightthickness=0)
        status_dot.create_oval(1, 3, 9, 11, fill=COLORS['green'], outline='')
        status_dot.pack(side='left', padx=(0, 6))
        self.footer_label = ttk.Label(footer, text=self.tr('footer'), style='Muted.TLabel', font=('Segoe UI', 9))
        self.footer_label.pack(side='left')
        self.tagline = ttk.Label(footer, text=self.tr('tagline'), style='Muted.TLabel', font=('Segoe UI', 9))
        self.tagline.pack(side='right', padx=(12, 0))
        app.protocol('WM_DELETE_WINDOW', self.close)
        app.after_idle(self.fit_minimum_width)
        app.after(100, self.drain)

    def tr(self, key, **values):
        return tr(key, self.language, **values)

    def fit_minimum_width(self):
        # French labels and a large ROM count must keep every action visible.
        self.app.minsize(max(1060, self.toolbar.winfo_reqwidth() + 72), 780)

    def layout_header(self, event):
        self.draw_background(event)
        widths = [field.winfo_reqwidth() for field in self.header_fields]
        left = max(24, event.width - 24 - sum(widths) - 16)
        for key, window, width in zip(self.header_labels, self.header_windows, widths):
            self.header.coords(self.header_labels[key], left, 10)
            self.header.coords(window, left, 29)
            left += width + 8

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
            for label in self.header_labels.values():
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
        if canvas is self.header:
            if self.console_art is not None:
                canvas.create_image(max(550, width-555), 56, image=self.console_art,
                                    anchor='nw', tags=('background_motif', 'hardware'))
            for x, y, size in ((width-80, 104, 10), (width-67, 91, 12)):
                if any(x < x2 and x+size > x1 and y < y2 and y+size > y1
                       for x1, y1, x2, y2 in protected):
                    continue
                canvas.create_rectangle(x, y, x+size, y+size, fill=COLORS['gold'],
                                        outline='', tags=('background_motif', 'background_square'))
        canvas.tag_lower('background_motif')

    def hint(self, widget, key):
        self.tooltips.append(Tooltip(widget, lambda: self.tr(key)))

    def set_status(self, key, **values):
        self.status_key, self.status_values = key, values
        self.status.set(self.tr(key, **values))

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

    def change_platform(self, event=None):
        self.platform_id = next((key for key, name in PLATFORMS.items()
                                 if name == self.platform_name.get()), 'windows-x64')

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
        self.language_name.set('Français' if self.language == 'fr' else 'English')
        self.system_field.configure(values=self.system_choices())
        self.system_name.set(self.system_display())
        self.platform_name.set(PLATFORMS[self.platform_id])
        self.header.itemconfigure(self.brand_tagline, text=self.tr('brand_tagline'))
        for key, item in self.header_labels.items():
            self.header.itemconfigure(item, text=self.tr(key))
        reverse = {value: key for key, pair in STRINGS.items() for value in pair if '{' not in value}
        def update(widget):
            if not widget.winfo_exists(): return
            try:
                caption = widget.cget('text')
                if caption in reverse: widget.configure(text=self.tr(reverse[caption]))
            except tk.TclError: pass
            if isinstance(widget, ttk.Treeview):
                for column in widget['columns']:
                    caption = widget.heading(column, 'text')
                    if caption in reverse: widget.heading(column, text=self.tr(reverse[caption]))
            for child in widget.winfo_children(): update(child)
        update(self.app)
        for panel in self.library_panels:
            if panel.winfo_exists(): panel.title(APP_NAME + ' — ' + self.tr('memory'))
        if self.credits_panel is not None and self.credits_panel.winfo_exists():
            self.credits_panel.title(APP_NAME + ' — ' + self.tr('credits'))
        for row, item in self.items.items():
            self.table.set(row, 'system', get_profile(item.system).name if item.system else self.tr('unknown_console'))
            self.table.set(row, 'video', self.video_display(item, self.results.get(row)))
            self.table.set(row, 'size', self.tr('size', value=item.size//1024) if item.size else '—')
            self.table.set(row, 'cover', self.tr('chosen' if item.cover else 'auto'))
            result = self.results.get(row, {})
            self.table.set(row, 'status', self.tr('same_rom', title=result['duplicate_of'])
                if self.row_status[row] == 'duplicate' and result.get('duplicate_of')
                else self.tr(self.row_status[row]))
        self.status.set(self.tr(self.status_key, **self.status_values))
        self.selection_changed()
        self.queue_background(self.header)
        self.queue_background(self.body)
        self.app.after_idle(self.fit_minimum_width)

    def change_language(self, event=None):
        self.language = 'fr' if self.language_name.get() == 'Français' else 'en'
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
        if parent is self.toolbar:
            style = 'Toolbar.' + style
        button = ttk.Button(parent, text=text, command=command, style=style)
        symbol = {'choose_roms': 'folder', 'choose_directory': 'add_folder',
                  'remove_selected': 'remove', 'clear': 'clear', 'check_updates': 'refresh',
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
            return '—'
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
        existing = {item.path for item in self.items.values()}
        for path in paths:
            path = Path(path)
            if path.is_dir():
                self.add_paths(discover_roms(path))
                existing = {item.path for item in self.items.values()}
                continue
            if path.resolve() in existing:
                continue
            item = identify(path, None if self.system_mode == 'auto' else self.system_mode)
            status = ('skipped' if item.skipped else 'unrecognized' if item.unknown
                      else 'invalid' if item.error else 'waiting')
            row = self.table.insert('', 'end', values=(item.title,
                get_profile(item.system).name if item.system else self.tr('unknown_console'),
                self.video_display(item),
                self.tr('size', value=item.size//1024) if item.size else '—',
                self.tr('auto'), self.tr(status)),
                tags=('error',) if item.error else ())
            self.items[row] = item
            self.row_status[row] = status
            if item.error:
                existing.add(item.path)
                continue
            folder = system_output(Path(self.output.get()).expanduser(), item.system)
            report_path = folder / 'datas/reports' / item.key / 'conversion-report.json'
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
                filename = report['executable']
                if Path(filename).name != filename:
                    raise ValueError('Invalid executable filename in report')
                target = folder / filename
                if not item.error and target.is_file() and report.get('rom', {}).get('sha256') == item.sha256:
                    measured = [c.get('interpreter_percent') for c in report['final_checks']]
                    self.results[row] = dict(status='success', executable=str(target.resolve()), report=str(report_path),
                        conversion_stage=report.get('status'),
                        main_interpreted_opcodes=max((c.get('interpreted_opcodes', 0) for c in report['final_checks']), default=0),
                        audio_cpu=report.get('audio_cpu'),
                        audio_interpreted_opcodes=max((c.get('audio_interpreted_opcodes', 0) for c in report['final_checks']), default=0),
                        pending_install=is_pending(target),
                        interpreter_percent=max((p for p in measured if p is not None), default=None),
                        interpreter_cycles=max((c.get('interpreter_cycles', 0) for c in report['final_checks']), default=0),
                        reference_vdp_trace_match=report.get('reference_vdp_trace_match'))
                    self.row_status[row] = 'pending_install' if is_pending(target) else 'created'
                    if report.get('status') == 'experimental' and not is_pending(target):
                        self.row_status[row] = 'created_experimental'
                    self.table.set(row, 'status', self.tr(self.row_status[row]))
                    self.results[row]['video_standard'] = report.get('video_model', {}).get('standard', item.video_hint)
                    self.table.set(row, 'video', self.video_display(item, self.results[row]))
                    self.table.item(row, tags=('success',))
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                pass
            existing.add(item.path)
        self.count.set(f'{len(self.items)} ROM' + ('s' if len(self.items) != 1 else ''))
        self.update_empty_state()
        self.app.after_idle(self.fit_minimum_width)

    def choose_roms(self):
        paths = filedialog.askopenfilenames(title=self.tr('pick_roms'), initialdir=ROOT / 'ROMS',
            filetypes=[('ROM files', '*.sms *.gg *.gb *.zip *.bin *.rom *.gbc *.gba *.nes *.sfc *.smc *.md *.gen *.pce'),
                       ('All files', '*.*')])
        self.add_paths(paths)

    def choose_directory(self):
        path = filedialog.askdirectory(title=self.tr('pick_folder'), initialdir=ROOT / 'ROMS')
        if path:
            self.add_paths([Path(path)])

    def remove_selected(self):
        if self.busy:
            return
        for row in self.table.selection():
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
        result = self.results.get(rows[0], {}) if len(rows) == 1 else {}
        self.play_button.configure(state='normal' if not self.busy and result.get('status') in ('success', 'existing') and not result.get('pending_install') else 'disabled')
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
                text += f" · {self.tr('cover')}: {item.cover.name}"
            if result.get('status') == 'success':
                comparison = result.get('reference_vdp_trace_match')
                if item.system in ('md', 'snes'):
                    text = self.tr('fallback16', opcodes=result.get('main_interpreted_opcodes', 0),
                        audio_opcodes=result.get('audio_interpreted_opcodes', 0))
                elif result.get('interpreter_percent') is None or comparison is None:
                    text = self.tr('fallback_cycles', cycles=result.get('interpreter_cycles', 0))
                else:
                    text = self.tr('fallback', percent=result['interpreter_percent'],
                                   comparison=self.tr('vdp_equal' if comparison else 'vdp_different'))
            text += ' · ' + self.video_display(item, result)
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
            md_advanced_scan=self.md_advanced_scan.get(),
            passes=self.passes.get(), frames=self.frames.get(), jobs=self.jobs.get(),
            use_cover=self.use_cover.get(),
            online_cover=self.online.get(), icon_tags=self.icon_tags.get(),
            overwrite=self.overwrite.get())

    def start(self):
        if self.busy or self.updating:
            return
        if not self.items:
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
            save_preferences(self.preferences())
        except (ValueError, tk.TclError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.busy = True
        self.cancel.clear()
        self.active_rows = list(self.table.get_children())
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
        def worker():
            try:
                record = convert_batch(items, output, cancel=self.cancel, **options,
                    emit=lambda text: self.messages.put(('log', text)),
                    on_event=lambda kind, index, value: self.messages.put((kind, index, value)))
                for folder in {Path(game['executable']).parent for game in record['games']
                               if game['status'] == 'success'}:
                    save_game_language(folder, self.language)
                self.messages.put(('done', record))
            except Exception as exc:
                self.messages.put(('fatal', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def set_controls(self, enabled):
        for control in self.controls:
            control.configure(state='normal' if enabled else 'disabled')
        if self.options_panel is not None and self.options_panel.winfo_exists():
            for control, active_state in self.option_controls:
                control.configure(state=active_state if enabled else 'disabled')
        self.start_button.configure(state='normal' if enabled else 'disabled')
        self.stop_button.configure(state='disabled' if enabled else 'normal')
        self.language_field.configure(state='readonly' if enabled else 'disabled')
        self.system_field.configure(state='readonly' if enabled else 'disabled')
        self.platform_field.configure(state='readonly' if enabled else 'disabled')
        self.update_output_controls()
        self.selection_changed()

    def stop(self):
        self.cancel.set()
        self.stop_button.configure(state='disabled')
        self.set_status('stopping')

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
        if not messagebox.askyesno(APP_NAME, self.tr('update_available',
                                                    version=update.version,
                                                    megabytes=round(update.size / 1048576, 1))):
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
                    if result['status'] == 'existing' and self.results.get(row, {}).get('status') == 'success':
                        result = {**self.results[row], **result}
                    self.results[row] = result
                    self.table.set(row, 'video', self.video_display(self.items[row], result))
                    status_key = {'success': 'created', 'error': 'error',
                                  'duplicate': 'duplicate', 'unrecognized': 'unrecognized',
                                  'skipped': 'skipped', 'existing': 'existing'}[result['status']]
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
                    self.set_controls(True)
                    if kind == 'fatal':
                        self.set_status('fatal', error=log_text(event[1], self.language))
                    else:
                        record = event[1]
                        self.set_status('summary', **record)
                elif kind == 'update_check':
                    self._offer_update(event[1])
                elif kind == 'update_ready':
                    self._start_prepared_update(event[1], event[2])
                    return
                elif kind == 'update_error':
                    self._update_error(event[1])
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
        os.startfile(path)

    def show_options(self):
        if self.busy:
            return
        if self.options_panel is not None and self.options_panel.winfo_exists():
            self.options_panel.lift()
            self.options_panel.focus_set()
            return

        panel = tk.Toplevel(self.app)
        self.options_panel = panel
        self.option_controls = []
        self.option_tooltips_start = len(self.tooltips)
        panel.title(APP_NAME + ' — ' + self.tr('options'))
        panel.configure(bg=COLORS['background'])
        panel.transient(self.app)
        panel.geometry('900x510')
        panel.minsize(860, 460)

        notebook = ttk.Notebook(panel)
        notebook.pack(fill='both', expand=True, padx=18, pady=(18, 8))

        def tab(key):
            page = ttk.Frame(notebook, padding=18)
            notebook.add(page, text=self.tr(key))
            return page

        def checkbox(parent, key, variable, hint):
            control = ttk.Checkbutton(parent, text=self.tr(key), variable=variable)
            control.pack(anchor='w', pady=(0, 8))
            self.option_controls.append((control, 'normal'))
            self.hint(control, hint)
            return control

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
                                     ('overwrite', self.overwrite, 'tip_overwrite')):
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

        for key in ('sms', 'gg'):
            profile_page = tab('options_master_system' if key == 'sms' else 'options_game_gear')
            control = checkbox(profile_page, 'extended', self.extended, 'tip_extended')
            if key == 'sms':
                self.extended_control = control
            ttk.Label(profile_page, text=self.tr('options_sega_note'), style='Muted.TLabel').pack(anchor='w')

        game_boy = tab('options_game_boy')
        self.gb_deep_control = checkbox(game_boy, 'gb_deep_validation',
                                        self.gb_deep_validation, 'tip_gb_deep_validation')
        ttk.Label(game_boy, text=self.tr('options_gb_note'), style='Muted.TLabel').pack(anchor='w')

        nes = tab('options_nes')
        ttk.Label(nes, text=self.tr('options_nes_note'), style='Muted.TLabel').pack(anchor='w')
        for console in ('md', 'snes'):
            page = tab('options_' + console)
            if console == 'md':
                self.md_scan_control = checkbox(page, 'md_advanced_scan',
                                                self.md_advanced_scan, 'tip_md_advanced_scan')
            ttk.Label(page, text=self.tr('options_' + console + '_note'),
                      style='Muted.TLabel', wraplength=590).pack(anchor='w')

        self.build_cover_options(tab('options_boxart'), checkbox)

        buttons = ttk.Frame(panel)
        buttons.pack(fill='x', padx=18, pady=(0, 18))
        ttk.Button(buttons, text=self.tr('close'), command=self.close_options).pack(side='right')
        panel.protocol('WM_DELETE_WINDOW', self.close_options)
        panel.bind('<Escape>', lambda _event: self.close_options())
        panel.grab_set()
        panel.focus_set()

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
                    show='' if field in ('devid', 'ssid', 'client_id') else '•')
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
                save_cover_settings(covers)
        except (ValueError, tk.TclError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc), parent=panel)
            return
        for hint in self.tooltips[self.option_tooltips_start:]:
            hint.hide()
        del self.tooltips[self.option_tooltips_start:]
        panel.grab_release()
        panel.destroy()
        self.options_panel = None
        self.output_field = self.output_browse = None
        self.option_controls = []

    def show_credits(self):
        if self.credits_panel is not None and self.credits_panel.winfo_exists():
            self.credits_panel.lift()
            self.credits_panel.focus_set()
            return

        panel = tk.Toplevel(self.app)
        self.credits_panel = panel
        panel.title(APP_NAME + ' — ' + self.tr('credits'))
        panel.configure(bg=COLORS['background'])
        panel.resizable(True, True)
        panel.transient(self.app)
        self.app.update_idletasks()
        width, height = 760, 700
        x = self.app.winfo_rootx() + max(0, (self.app.winfo_width() - width) // 2)
        y = self.app.winfo_rooty() + max(0, (self.app.winfo_height() - height) // 2)
        panel.geometry(f'{width}x{height}+{x}+{y}')
        panel.minsize(650, 550)

        content = tk.Frame(panel, bg=COLORS['background'], padx=24, pady=18)
        content.pack(fill='both', expand=True)
        try:
            panel.credits_logo = tk.PhotoImage(
                file=str(ASSETS / 'assets/Retro-Recomp-icon-64.png'), master=panel)
            tk.Label(content, image=panel.credits_logo, bg=COLORS['background']).pack(
                anchor='center', pady=(0, 2))
        except (OSError, tk.TclError):
            pass
        tk.Label(content, text=self.tr('credits'), bg=COLORS['background'], fg=COLORS['text'],
                 font=('Segoe UI', 23, 'bold')).pack(anchor='center', pady=(0, 3))
        tk.Label(content, text=self.tr('credits_intro'), bg=COLORS['background'], fg=COLORS['muted'],
                 font=('Segoe UI', 10), justify='center',
                 wraplength=630).pack(anchor='center', pady=(0, 13))

        tk.Frame(content, bg=COLORS['border'], height=1).pack(fill='x', padx=120, pady=(0, 11))
        tk.Label(content, text=self.tr('credits_repositories'), bg=COLORS['background'],
                 fg=COLORS['text'], font=('Segoe UI', 10, 'bold')).pack(anchor='center')
        tk.Label(content, text=self.tr('credits_open_link'), bg=COLORS['background'],
                 fg=COLORS['muted'], font=('Segoe UI', 9)).pack(anchor='center', pady=(1, 9))

        scroll_area = tk.Frame(content, bg=COLORS['background'])
        scroll_area.pack(fill='both', expand=True)
        scrollbar = ttk.Scrollbar(scroll_area, orient='vertical')
        scrollbar.pack(side='right', fill='y')
        canvas = tk.Canvas(scroll_area, bg=COLORS['background'], highlightthickness=0,
                           yscrollcommand=scrollbar.set)
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.configure(command=canvas.yview)
        cards = tk.Frame(canvas, bg=COLORS['background'])
        cards_window = canvas.create_window((0, 0), window=cards, anchor='nw')
        cards.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event: canvas.itemconfigure(cards_window, width=event.width))
        panel.bind('<MouseWheel>', lambda event: canvas.yview_scroll(
            -1 if event.delta > 0 else 1, 'units') if event.delta else None)
        panel.bind('<Button-4>', lambda _event: canvas.yview_scroll(-1, 'units'))
        panel.bind('<Button-5>', lambda _event: canvas.yview_scroll(1, 'units'))
        cards.grid_columnconfigure(0, weight=1)
        for index, (system, repositories) in enumerate(UPSTREAM_CREDITS):
            card = tk.Frame(cards, bg=COLORS['panel'], highlightthickness=1,
                            highlightbackground=COLORS['border'])
            card.grid(row=index, column=0, sticky='ew', padx=48, pady=(0, 13))
            accent = COLORS['gold']
            tk.Frame(card, height=3, bg=accent).pack(fill='x')
            tk.Label(card, text=system.upper(), bg=COLORS['panel'], fg=COLORS['text'],
                     font=('Segoe UI', 12, 'bold')).pack(anchor='center', pady=(11, 6))
            for repository, url, role in repositories:
                link = tk.Label(card, text=repository, bg=COLORS['panel'], fg=COLORS['gold'],
                                activeforeground=COLORS['gold_hover'], cursor='hand2',
                                font=('Segoe UI', 10, 'underline'))
                link.pack(anchor='center')
                link.bind('<Button-1>', lambda _event, address=url: webbrowser.open_new_tab(address))
                tk.Label(card, text=self.tr(role), bg=COLORS['panel'], fg=COLORS['muted'],
                         font=('Segoe UI', 9)).pack(anchor='center', pady=(0, 7))

        bottom = tk.Frame(content, bg=COLORS['background'])
        bottom.pack(fill='x', pady=(9, 0))
        tk.Label(bottom, text=self.tr('credits_license'), bg=COLORS['background'],
                 fg=COLORS['muted'], font=('Segoe UI', 9),
                 wraplength=650, justify='center').pack(anchor='center')
        notices = tk.Label(bottom, text=self.tr('credits_notices'), bg=COLORS['background'],
                           fg=COLORS['gold'], cursor='hand2',
                           font=('Segoe UI', 9, 'underline'))
        notices.pack(anchor='center', pady=(3, 0))
        notices.bind('<Button-1>', lambda _event: self.show_legal_notices())

        def close_credits():
            panel.grab_release()
            panel.destroy()
            self.credits_panel = None

        actions = tk.Frame(bottom, bg=COLORS['background'], height=38)
        actions.pack(fill='x', pady=(10, 0))
        actions.pack_propagate(False)
        ttk.Button(actions, text=self.tr('close'), command=close_credits).place(
            relx=0.5, rely=0.5, anchor='center')
        author = tk.Frame(actions, bg=COLORS['background'])
        author.place(relx=1.0, rely=0.5, anchor='e')
        tk.Label(author, text=self.tr('credits_author'), bg=COLORS['background'], fg=COLORS['disabled'],
                 font=('Segoe UI', 8)).pack(side='left', padx=(0, 4))
        author_link = tk.Label(author, text='Arthur Reboul Salze', bg=COLORS['background'],
                               fg=COLORS['muted'], cursor='hand2',
                               font=('Segoe UI', 8, 'underline'))
        author_link.pack(side='left')
        author_link.bind('<Button-1>', lambda _event: webbrowser.open_new_tab(
            'https://github.com/ArthurReboulSalze'))
        panel.protocol('WM_DELETE_WINDOW', close_credits)
        panel.bind('<Escape>', lambda _event: close_credits())
        panel.grab_set()
        panel.focus_set()

    def show_legal_notices(self):
        """Show the complete bundled licenses without creating sidecar files."""
        parent = self.credits_panel if self.credits_panel and self.credits_panel.winfo_exists() else self.app
        resources = [ASSETS / 'LICENSE', ASSETS / 'THIRD_PARTY_NOTICES.md']
        resources.extend(sorted((ASSETS / 'licenses').glob('*.md'), key=lambda path: path.name.lower()))
        resources = [path for path in resources if path.is_file()]
        panel = tk.Toplevel(parent)
        panel.title(APP_NAME + ' — ' + self.tr('credits_notices'))
        panel.configure(bg=COLORS['background'])
        panel.geometry('880x630')
        panel.minsize(650, 420)
        panel.transient(parent)
        body = tk.Frame(panel, bg=COLORS['background'], padx=16, pady=16)
        body.pack(fill='both', expand=True)
        tk.Label(body, text=self.tr('credits_notices'), bg=COLORS['background'], fg=COLORS['text'],
                 font=('Segoe UI', 16, 'bold')).pack(anchor='w', pady=(0, 10))
        row = tk.Frame(body, bg=COLORS['background'])
        row.pack(fill='both', expand=True)
        listing = tk.Listbox(row, width=29, exportselection=False, bg=COLORS['panel'],
                             fg=COLORS['text'], selectbackground=COLORS['border'],
                             selectforeground='#ffffff', relief='flat',
                             font=('Segoe UI', 10))
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
        panel = tk.Toplevel(self.app)
        panel.title(APP_NAME + ' — ' + self.tr('memory'))
        self.library_panels.append(panel)
        panel.geometry('800x420')
        panel.configure(bg=COLORS['background'])
        body = ttk.Frame(panel, padding=18)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=self.tr('memory_intro')).pack(anchor='w', pady=(0, 12))
        table = ttk.Treeview(body, columns=('game', 'identity', 'entries'), show='headings', height=9)
        for column, caption, width in [('game', self.tr('game'), 390), ('identity', self.tr('identity'), 150), ('entries', self.tr('observations'), 110)]:
            table.heading(column, text=caption)
            table.column(column, width=width, stretch=column == 'game')
        for game in [*list_games(), *list_games(library_root('gg'))]:
            table.insert('', 'end', values=(game['title'], game['sha256'][:12], game['observations']))
        from .gameboy import list_memory
        for game in list_memory():
            table.insert('', 'end', values=(f"Game Boy · {game['title']}", game['sha256'][:12],
                                            f"{game['trace_bytes']} B trace"))
        from .nes import list_memory as list_nes_memory
        for game in list_nes_memory():
            table.insert('', 'end', values=(f"Nintendo NES · {game['sha256'][:12]}",
                                            game['sha256'][:12], game['entries']))
        table.pack(fill='both', expand=True)
        def open_library():
            path = library_root()
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        ttk.Button(body, text=self.tr('open_memory'), command=open_library).pack(anchor='w', pady=(12, 0))

    def close(self):
        if self.updating:
            messagebox.showinfo(APP_NAME, self.tr('wait_update'))
            return
        if self.busy:
            messagebox.showinfo(APP_NAME, self.tr('wait_close'))
            return
        try:
            save_preferences(self.preferences())
        except (OSError, tk.TclError, ValueError):
            pass
        self.app.destroy()


def launch(update_error: str | None = None):
    set_converter_identity()
    app = tk.Tk()
    application = Application(app)
    roms = ROOT / 'ROMS'
    if roms.is_dir():
        application.add_paths(discover_roms(roms))
    app._retro_application = application
    if update_error:
        app.after(200, lambda: messagebox.showerror(APP_NAME,
            application.tr('update_failed', error=update_error)))
    app.mainloop()
