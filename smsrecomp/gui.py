from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .batch import BatchItem, identify, convert_batch
from .publishing import is_pending
from .library import list_games, library_root
from .paths import ROOT, ASSETS, APP_NAME, load_preferences, save_preferences, save_game_language, games_directory
from .i18n import STRINGS, tr, extended_default, log_text
from .tooltips import Tooltip
from .windows import set_converter_identity
from .artwork import ICON_SIZES


class Application:
    def __init__(self, app: tk.Tk):
        self.app = app
        self.items: dict[str, BatchItem] = {}
        self.results: dict[str, dict] = {}
        self.busy = False
        self.cancel = threading.Event()
        self.messages = queue.Queue()
        self.controls = []
        self.active_rows = []
        self.row_status, self.tooltips, self.library_panels = {}, [], []
        self.status_key, self.status_values = 'ready', {}
        preferences = load_preferences()
        self.language = preferences.get('language') if preferences.get('language') in ('en', 'fr') else 'en'
        app.title(APP_NAME)
        app.geometry('1120x940')
        app.minsize(960, 840)
        app.configure(bg='#071732')
        style = ttk.Style(app)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 10), background='#071732', foreground='#eef6ff')
        style.configure('TButton', padding=(12, 7), background='#173763', bordercolor='#31568c', lightcolor='#173763', darkcolor='#173763')
        style.map('TButton', background=[('active', '#22518e'), ('disabled', '#122749')], foreground=[('disabled', '#7590b3')])
        style.configure('TCheckbutton', background='#071732', foreground='#eef6ff')
        style.map('TCheckbutton', background=[('active', '#102b52')], foreground=[('disabled', '#7590b3')])
        style.configure('TEntry', fieldbackground='#102b52', foreground='#eef6ff', bordercolor='#31568c', insertcolor='#eef6ff')
        style.configure('TCombobox', fieldbackground='#102b52', foreground='#eef6ff', background='#173763', arrowcolor='#26d7ff')
        style.map('TCombobox', fieldbackground=[('readonly', '#102b52')], foreground=[('readonly', '#eef6ff')])
        style.configure('TSpinbox', fieldbackground='#102b52', foreground='#eef6ff', arrowcolor='#26d7ff')
        style.configure('Horizontal.TProgressbar', background='#26d7ff', troughcolor='#102b52', bordercolor='#25456c')
        style.configure('TScrollbar', background='#173763', troughcolor='#0b2143', arrowcolor='#a9bcdc')
        style.configure('Vertical.TScrollbar', background='#173763', troughcolor='#0b2143', arrowcolor='#a9bcdc', bordercolor='#285896')
        style.map('Vertical.TScrollbar', background=[('active', '#22518e')])
        style.configure('Primary.TButton', background='#0879fa', foreground='white', padding=(18, 9))
        style.map('Primary.TButton', background=[('active', '#1265d0'), ('disabled', '#334a68')])
        style.configure('Treeview', background='#0b2143', fieldbackground='#0b2143', rowheight=31, borderwidth=0, bordercolor='#285896', lightcolor='#285896', darkcolor='#285896')
        style.configure('Treeview.Heading', background='#153461', padding=(8, 8), font=('Segoe UI', 10, 'bold'), bordercolor='#285896', lightcolor='#285896', darkcolor='#285896')
        style.map('Treeview.Heading', background=[('active', '#22518e')])
        style.map('Treeview', background=[('selected', '#164da2')], foreground=[('selected', '#eef6ff')])
        style.configure('Muted.TLabel', foreground='#a9bcdc')
        self.status = tk.StringVar(value=self.tr('ready'))
        self.count = tk.StringVar(value='0 ROM')
        self.detail = tk.StringVar(value=self.tr('shared'))
        self.output = tk.StringVar(value=str(games_directory(preferences.get('output'))))
        self.extended = tk.BooleanVar(value=extended_default(preferences))
        self.passes = tk.IntVar(value=preferences.get('passes', 3) if isinstance(preferences.get('passes', 3), int) else 3)
        self.frames = tk.IntVar(value=preferences.get('frames', 3600) if isinstance(preferences.get('frames', 3600), int) else 3600)
        self.use_cover = tk.BooleanVar(value=bool(preferences.get('use_cover', True)))
        self.online = tk.BooleanVar(value=bool(preferences.get('online_cover', True)))

        header = tk.Frame(app, bg='#04112b', padx=24, pady=0)
        header.pack(fill='x')
        header.columnconfigure(0, weight=1)
        branding = tk.Frame(header, bg='#04112b')
        branding.grid(row=0, column=0, sticky='w')
        banner_path = ASSETS / 'assets/Retro-Recomp-banner.png'
        try:
            self.banner = tk.PhotoImage(file=str(banner_path))
            self.banner_label = tk.Label(branding, image=self.banner, bg='#04112b', borderwidth=0, highlightthickness=0)
            self.banner_label.pack(anchor='w')
        except (OSError, tk.TclError):
            self.banner = None
            self.banner_label = None
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
        header_controls = tk.Frame(header, bg='#04112b')
        header_controls.grid(row=0, column=1, sticky='ne', padx=(24, 0), pady=(8, 0))
        badge = tk.Frame(header_controls, bg='#0e254b', padx=16, pady=10, highlightbackground='#285896', highlightthickness=1)
        badge.pack(anchor='e')
        tk.Label(badge, text='MASTER SYSTEM', bg='#0e254b', fg='#26d7ff', font=('Segoe UI', 10, 'bold')).pack()
        tk.Label(badge, text='Windows x64', bg='#0e254b', fg='#a9bcdc', font=('Segoe UI', 9)).pack()
        language_frame = tk.Frame(header_controls, bg='#04112b')
        language_frame.pack(anchor='e', pady=(16, 0))
        tk.Label(language_frame, text=self.tr('language'), bg='#04112b', fg='#a9bcdc', font=('Segoe UI', 9)).pack(anchor='w')
        self.language_name = tk.StringVar(value='Français' if self.language == 'fr' else 'English')
        self.language_field = ttk.Combobox(language_frame, textvariable=self.language_name, values=('English', 'Français'), width=10, state='readonly')
        self.language_field.pack(pady=(4, 0))
        self.language_field.bind('<<ComboboxSelected>>', self.change_language)
        self.hint(self.language_field, 'tip_language')
        stripe = tk.Canvas(app, height=3, bg='#0879fa', highlightthickness=0)
        stripe.pack(fill='x')
        def gradient(event):
            stripe.delete('all')
            colors = [(170, 102, 255), (8, 121, 250), (38, 215, 255)]
            for i in range(128):
                progress = i / 127 * 2
                segment = min(1, int(progress)); fraction = progress - segment
                color = '#%02x%02x%02x' % tuple(int(a*(1-fraction)+b*fraction) for a,b in zip(colors[segment], colors[segment+1]))
                stripe.create_rectangle(i*event.width/128, 0, (i+1)*event.width/128+1, 3, fill=color, outline=color)
        stripe.bind('<Configure>', gradient)

        body = ttk.Frame(app, padding=(24, 16))
        body.pack(fill='both', expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(1, weight=3, minsize=105)
        body.rowconfigure(10, weight=1, minsize=45)
        toolbar = ttk.Frame(body)
        toolbar.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        self.button(toolbar, self.tr('add_roms'), self.choose_roms).pack(side='left')
        self.button(toolbar, self.tr('add_folder'), self.choose_directory).pack(side='left', padx=8)
        self.button(toolbar, self.tr('remove'), self.remove_selected).pack(side='left')
        self.button(toolbar, self.tr('clear'), self.clear).pack(side='left', padx=8)
        ttk.Label(toolbar, textvariable=self.count, style='Muted.TLabel').pack(side='right')

        table_frame = ttk.Frame(body)
        table_frame.grid(row=1, column=0, sticky='nsew')
        self.table = ttk.Treeview(table_frame, columns=('title', 'size', 'cover', 'status'), show='headings', selectmode='extended', height=8)
        for key, caption, width in [('title', self.tr('game'), 430), ('size', 'ROM', 70), ('cover', self.tr('cover'), 100), ('status', self.tr('conversion'), 250)]:
            self.table.heading(key, text=caption)
            self.table.column(key, width=width, minwidth=60, stretch=key in ('title', 'status'))
        self.table.tag_configure('error', foreground='#ffb4c2')
        self.table.tag_configure('success', foreground='#81e7ba')
        scrollbar = ttk.Scrollbar(table_frame, orient='vertical', command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side='left', fill='both', expand=True)
        self.hint(self.table, 'tip_table')
        scrollbar.pack(side='right', fill='y')
        self.table.bind('<<TreeviewSelect>>', lambda event: self.selection_changed())
        self.table.bind('<Double-1>', lambda event: self.play())

        selection = ttk.Frame(body)
        selection.grid(row=2, column=0, sticky='ew', pady=(8, 12))
        self.button(selection, self.tr('choose_cover'), self.choose_cover).pack(side='left')
        self.button(selection, self.tr('auto_cover'), self.automatic_cover).pack(side='left', padx=8)
        self.play_button = ttk.Button(selection, text=self.tr('play'), command=self.play, state='disabled')
        self.play_button.pack(side='left')
        self.hint(self.play_button, 'tip_play')
        self.memory_button = ttk.Button(selection, text=self.tr('memory'), command=self.show_library)
        self.memory_button.pack(side='right')
        self.hint(self.memory_button, 'tip_memory')
        ttk.Label(body, textvariable=self.detail, style='Muted.TLabel', wraplength=850).grid(row=3, column=0, sticky='ew', pady=(0, 12))

        output_row = ttk.Frame(body)
        output_row.grid(row=4, column=0, sticky='ew', pady=(0, 12))
        ttk.Label(output_row, text=self.tr('output')).pack(side='left', padx=(0, 10))
        self.output_field = ttk.Entry(output_row, textvariable=self.output)
        self.output_field.pack(side='left', fill='x', expand=True)
        self.controls.append(self.output_field)
        self.hint(self.output_field, 'tip_output')
        self.button(output_row, self.tr('browse'), self.choose_output).pack(side='left', padx=(8, 0))

        options = ttk.Frame(body)
        options.grid(row=5, column=0, sticky='ew', pady=(0, 8))
        for text, variable, hint in [(self.tr('icon'), self.use_cover, 'tip_icon'), (self.tr('online'), self.online, 'tip_online'), (self.tr('extended'), self.extended, 'tip_extended')]:
            control = ttk.Checkbutton(options, text=text, variable=variable)
            control.pack(side='left', padx=(0, 16))
            self.controls.append(control)
            self.hint(control, hint)
            if variable is self.extended: self.extended_control = control
        tuning = ttk.Frame(body)
        tuning.grid(row=6, column=0, sticky='ew', pady=(0, 12))
        ttk.Label(tuning, text=self.tr('passes')).pack(side='left')
        self.pass_field = ttk.Combobox(tuning, textvariable=self.passes, values=list(range(1, 11)), width=4, state='readonly')
        self.pass_field.pack(side='left', padx=(6, 20))
        self.hint(self.pass_field, 'tip_passes')
        ttk.Label(tuning, text=self.tr('frames')).pack(side='left')
        self.frame_field = ttk.Spinbox(tuning, textvariable=self.frames, from_=1, to=10000, width=7)
        self.frame_field.pack(side='left', padx=6)
        self.hint(self.frame_field, 'tip_frames')
        ttk.Label(tuning, text=self.tr('sequential'), style='Muted.TLabel').pack(side='right')

        actions = ttk.Frame(body)
        actions.grid(row=7, column=0, sticky='ew', pady=(0, 8))
        self.start_button = ttk.Button(actions, text=self.tr('start'), command=self.start, style='Primary.TButton')
        self.start_button.pack(side='left')
        self.hint(self.start_button, 'tip_start')
        self.stop_button = ttk.Button(actions, text=self.tr('stop'), command=self.stop, state='disabled')
        self.stop_button.pack(side='left', padx=8)
        self.hint(self.stop_button, 'tip_stop')
        open_button = ttk.Button(actions, text=self.tr('open_folder'), command=self.open_output)
        open_button.pack(side='right')
        self.hint(open_button, 'tip_open_folder')
        self.progress = ttk.Progressbar(body, mode='determinate')
        self.progress.grid(row=8, column=0, sticky='ew', pady=(0, 8))
        ttk.Label(body, textvariable=self.status, wraplength=850).grid(row=9, column=0, sticky='ew', pady=(0, 8))
        self.log = tk.Text(body, height=12, font=('Consolas', 9), bg='#04112b', fg='#b8dbff', relief='flat', padx=12, pady=10, state='disabled', wrap='word')
        self.log.grid(row=10, column=0, sticky='nsew')
        footer = ttk.Frame(body)
        footer.grid(row=11, column=0, sticky='ew', pady=(10, 0))
        self.footer_label = ttk.Label(footer, text=self.tr('footer'), style='Muted.TLabel')
        self.footer_label.pack(side='left')
        self.tagline = ttk.Label(footer, text=self.tr('tagline'), style='Muted.TLabel', font=('Segoe UI', 9))
        self.tagline.pack(side='right', padx=(12, 0))
        app.protocol('WM_DELETE_WINDOW', self.close)
        app.after(100, self.drain)

    def tr(self, key, **values):
        return tr(key, self.language, **values)

    def hint(self, widget, key):
        self.tooltips.append(Tooltip(widget, lambda: self.tr(key)))

    def set_status(self, key, **values):
        self.status_key, self.status_values = key, values
        self.status.set(self.tr(key, **values))

    def refresh_language(self):
        self.language_name.set('Français' if self.language == 'fr' else 'English')
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
        for row, item in self.items.items():
            self.table.set(row, 'size', self.tr('size', value=item.size//1024) if item.size else '—')
            self.table.set(row, 'cover', self.tr('chosen' if item.cover else 'auto'))
            self.table.set(row, 'status', self.tr(self.row_status[row]))
        self.status.set(self.tr(self.status_key, **self.status_values))
        self.selection_changed()

    def change_language(self, event=None):
        self.language = 'fr' if self.language_name.get() == 'Français' else 'en'
        for hint in self.tooltips: hint.hide()
        self.refresh_language()
        try:
            save_preferences(self.preferences())
            save_game_language(Path(self.output.get()).expanduser(), self.language)
        except (OSError, ValueError, tk.TclError) as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.controls.append(button)
        key = next((key for key, pair in STRINGS.items() if text in pair and 'tip_'+key in STRINGS), None)
        if key: self.hint(button, 'tip_'+key)
        elif command == self.choose_output: self.hint(button, 'tip_output')
        return button

    def add_paths(self, paths):
        existing = {item.path for item in self.items.values()}
        for path in paths:
            if Path(path).resolve() in existing:
                continue
            item = identify(Path(path))
            row = self.table.insert('', 'end', values=(item.title, self.tr('size', value=item.size//1024) if item.size else '—', self.tr('auto'), self.tr('invalid') if item.error else self.tr('waiting')), tags=('error',) if item.error else ())
            self.items[row] = item
            self.row_status[row] = 'invalid' if item.error else 'waiting'
            folder = Path(self.output.get()).expanduser()
            report_path = folder / 'datas/reports' / item.key / 'conversion-report.json'
            try:
                report = json.loads(report_path.read_text(encoding='utf-8'))
                filename = report['executable']
                if Path(filename).name != filename:
                    raise ValueError('Invalid executable filename in report')
                target = folder / filename
                if not item.error and target.is_file() and report.get('rom', {}).get('sha256') == item.sha256:
                    self.results[row] = dict(status='success', executable=str(target.resolve()), report=str(report_path),
                        pending_install=is_pending(target),
                        interpreter_percent=max((c.get('interpreter_percent') or 0 for c in report['final_checks']), default=0),
                        reference_vdp_trace_match=report['reference_vdp_trace_match'])
                    self.row_status[row] = 'pending_install' if is_pending(target) else 'created'
                    self.table.set(row, 'status', self.tr(self.row_status[row]))
                    self.table.item(row, tags=('success',))
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                pass
            existing.add(item.path)
        self.count.set(f'{len(self.items)} ROM' + ('s' if len(self.items) != 1 else ''))

    def choose_roms(self):
        paths = filedialog.askopenfilenames(title=self.tr('pick_roms'), initialdir=ROOT / 'ROMS', filetypes=[('Master System', '*.sms')])
        self.add_paths(paths)

    def choose_directory(self):
        path = filedialog.askdirectory(title=self.tr('pick_folder'), initialdir=ROOT / 'ROMS')
        if path:
            self.add_paths(sorted(p for p in Path(path).rglob('*') if p.is_file() and p.suffix.lower() == '.sms'))

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
            try: save_game_language(Path(path), self.language)
            except OSError as exc: messagebox.showerror(APP_NAME, str(exc))

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
        self.play_button.configure(state='normal' if not self.busy and result.get('status') == 'success' and not result.get('pending_install') else 'disabled')
        if len(rows) == 1:
            item = self.items[rows[0]]
            text = log_text(item.error or result.get('message') or str(item.path), self.language)
            if item.cover:
                text += f" · {self.tr('cover')}: {item.cover.name}"
            if result.get('status') == 'success':
                text = self.tr('fallback', percent=result['interpreter_percent'], comparison=self.tr('vdp_equal' if result['reference_vdp_trace_match'] else 'vdp_different'))
            self.detail.set(text)
        else:
            self.detail.set(self.tr('shared'))

    def preferences(self):
        return dict(language=self.language, coverage_default_revision=2, output=self.output.get(), backend='banked' if self.extended.get() else 'functions', passes=self.passes.get(), frames=self.frames.get(), use_cover=self.use_cover.get(), online_cover=self.online.get())

    def start(self):
        if self.busy:
            return
        if not self.items:
            messagebox.showinfo(APP_NAME, self.tr('need_rom'))
            return
        try:
            options = self.preferences()
            if not 1 <= options['passes'] <= 10 or not 1 <= options['frames'] <= 10000:
                raise ValueError(self.tr('invalid_limits'))
            if not self.output.get().strip():
                raise ValueError(self.tr('need_output'))
            output = Path(options.pop('output')).expanduser().resolve()
            options.pop('coverage_default_revision')
            save_game_language(output, self.language)
            save_preferences(self.preferences())
        except (ValueError, tk.TclError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.busy = True
        self.cancel.clear()
        self.active_rows = list(self.table.get_children())
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
                self.messages.put(('done', record))
            except Exception as exc:
                self.messages.put(('fatal', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def set_controls(self, enabled):
        for control in self.controls:
            control.configure(state='normal' if enabled else 'disabled')
        self.pass_field.configure(state='readonly' if enabled else 'disabled')
        self.frame_field.configure(state='normal' if enabled else 'disabled')
        self.start_button.configure(state='normal' if enabled else 'disabled')
        self.stop_button.configure(state='disabled' if enabled else 'normal')
        self.language_field.configure(state='readonly' if enabled else 'disabled')
        self.selection_changed()

    def stop(self):
        self.cancel.set()
        self.stop_button.configure(state='disabled')
        self.set_status('stopping')

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
                    self.table.set(row, 'status', self.tr('converting'))
                    self.row_status[row] = 'converting'
                    self.table.see(row)
                    if not self.cancel.is_set():
                        self.status.set(f'{event[1]+1}/{len(self.active_rows)} · {event[2]}')
                elif kind == 'result':
                    row, result = self.active_rows[event[1]], event[2]
                    self.results[row] = result
                    text = {'success': self.tr('created'), 'error': self.tr('error'), 'duplicate': self.tr('duplicate')}[result['status']]
                    self.row_status[row] = {'success': 'created', 'error': 'error', 'duplicate': 'duplicate'}[result['status']]
                    if result.get('pending_install'):
                        self.row_status[row] = 'pending_install'
                        text = self.tr('pending_install')
                    self.table.set(row, 'status', text)
                    self.table.item(row, tags=(result['status'],))
                    self.progress.configure(value=event[1]+1)
                    self.selection_changed()
                elif kind in ('done', 'fatal'):
                    self.busy = False
                    self.set_controls(True)
                    if kind == 'fatal':
                        self.set_status('fatal', error=log_text(event[1], self.language))
                    else:
                        record = event[1]
                        self.set_status('summary', **record)
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

    def show_library(self):
        panel = tk.Toplevel(self.app)
        panel.title(APP_NAME + ' — ' + self.tr('memory'))
        self.library_panels.append(panel)
        panel.geometry('800x420')
        panel.configure(bg='#071732')
        body = ttk.Frame(panel, padding=18)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=self.tr('memory_intro')).pack(anchor='w', pady=(0, 12))
        table = ttk.Treeview(body, columns=('game', 'identity', 'entries'), show='headings', height=9)
        for column, caption, width in [('game', self.tr('game'), 390), ('identity', self.tr('identity'), 150), ('entries', self.tr('observations'), 110)]:
            table.heading(column, text=caption)
            table.column(column, width=width, stretch=column == 'game')
        for game in list_games():
            table.insert('', 'end', values=(game['title'], game['sha256'][:12], game['observations']))
        table.pack(fill='both', expand=True)
        def open_library():
            path = library_root()
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        ttk.Button(body, text=self.tr('open_memory'), command=open_library).pack(anchor='w', pady=(12, 0))

    def close(self):
        if self.busy:
            messagebox.showinfo(APP_NAME, self.tr('wait_close'))
            return
        try:
            save_preferences(self.preferences())
        except (OSError, tk.TclError, ValueError):
            pass
        self.app.destroy()


def launch():
    set_converter_identity()
    app = tk.Tk()
    application = Application(app)
    application.add_paths(sorted((ROOT / 'ROMS').glob('*.sms')))
    app._retro_application = application
    app.mainloop()
