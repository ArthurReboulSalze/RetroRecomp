"""The options window and its pages."""
from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from . import online
from .paths import APP_NAME, save_preferences, selected_bios_path
from .languages import language_code
from .cover_settings import (
    FIELDS as COVER_FIELDS, load_settings as load_cover_settings, save_settings as save_cover_settings,
)
from .cover_keyring import KeyringError
from .cover_sources import PROVIDERS as COVER_PROVIDERS
from .branding import COLORS
from .gui_common import PROFILES, SENDING_AVAILABLE


class OptionsMixin:
    """The options window and its pages."""

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
                ('scan_frames', self.scan_frames, 10000, self.frames.get()),
                ('scan_jobs', self.scan_jobs, 8, self.jobs.get())), start=1):
            ttk.Label(row, text=self.tr(key, default=shared)).grid(row=0, column=column, sticky='w', padx=(0, 22))
            control = ttk.Spinbox(row, textvariable=variables[console], from_=1, to=limit, width=8)
            control.grid(row=1, column=column, sticky='w', padx=(0, 22), pady=(5, 0))
            self.option_controls.append((control, 'normal'))
            self.hint(control, 'tip_' + key)

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
                                     ('use_shared_base', self.use_shared_base, 'tip_use_shared_base'),
                                     ('startup_update_check', self.check_at_startup, 'tip_startup_update_check'),
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
            command=self.open_account_site)
        self.account_site_button.pack(side='left', padx=(8, 0))
        # Signed in: the RR coins, spent in the site's shop (titles, name
        # styles, badges, pins, frames, header themes); the converter only
        # draws what the account equips.
        self.account_rewards = ttk.Frame(page)
        self.account_balance = tk.StringVar()
        ttk.Label(self.account_rewards, textvariable=self.account_balance).pack(side='left')
        shop = ttk.Button(self.account_rewards, text=self.tr('account_shop_site'),
                          command=self.open_account_shop)
        shop.pack(side='left', padx=(12, 0))
        self.hint(shop, 'tip_account_shop')
        items = ttk.Button(self.account_rewards, text=self.tr('account_items_site'),
                           command=self.open_account_items)
        items.pack(side='left', padx=(8, 0))
        self.hint(items, 'tip_account_items')
        # Signed in: this player's discoveries sent after each batch. Using the
        # published base needs no account: its option is in Options > Common.
        self.account_sync = ttk.Frame(page)
        for key, variable in (('send_after_batch', self.send_after_batch),):
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
                text = self.tr('account_balance', coins='–' if coins is None else self.count_text(coins))
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
        # The build tools and compiler caches of a packaged installation: the
        # documented way to leave nothing behind before removing Retro-Recomp
        # (or its Debian package, which cannot ask).
        self.tools_row = tools = ttk.Frame(page)
        self.tools_note = ttk.Label(tools, text=self.tr('tools_space_note'), style='Muted.TLabel',
                                    wraplength=600, justify='left')
        self.tools_note.pack(anchor='w', pady=(0, 8))
        tools_line = ttk.Frame(tools)
        tools_line.pack(anchor='w', fill='x')
        self.tools_button = ttk.Button(tools_line, command=self.remove_tool_space)
        self.tools_button.pack(side='left')
        self.hint(self.tools_button, 'tip_tools_space')
        self.tools_status = tk.StringVar()
        ttk.Label(tools_line, textvariable=self.tools_status, style='Muted.TLabel',
                  wraplength=460, justify='left').pack(side='left', padx=(12, 0))
        if getattr(self, 'tools_state', {}).get('phase') == 'working':
            self.render_disk_space()
        else:
            self.measure_tool_space()
        # The count of each game's discoveries is cached; emptying it loses
        # nothing (the next count reads every game again).
        cache = ttk.Frame(page)
        cache.pack(anchor='w', fill='x', pady=(14, 0))
        ttk.Label(cache, text=self.tr('discoveries_cache_note'), style='Muted.TLabel',
                  wraplength=600, justify='left').pack(anchor='w', pady=(0, 8))
        cache_line = ttk.Frame(cache)
        cache_line.pack(anchor='w', fill='x')
        button = ttk.Button(cache_line, text=self.tr('discoveries_cache_clear'),
                            command=self.clear_discoveries_cache)
        button.pack(side='left')
        self.hint(button, 'tip_discoveries_cache')
        self.cache_status = tk.StringVar()
        ttk.Label(cache_line, textvariable=self.cache_status, style='Muted.TLabel',
                  wraplength=460, justify='left').pack(side='left', padx=(12, 0))

    def clear_discoveries_cache(self):
        """Options › Common › Disk space: forget the cached count of each game's
        discoveries, after a confirmation; never while a count or send runs."""
        if self.busy or getattr(self, 'sending_count', 0):
            self.cache_status.set(self.tr('discoveries_cache_busy'))
            return
        if not messagebox.askyesno(APP_NAME, self.tr('discoveries_cache_confirm'), parent=self.app):
            return
        from .knowledge_exchange import clear_discoveries_cache
        try:
            removed = clear_discoveries_cache()
        except OSError as error:
            self.cache_status.set(self.tr('discoveries_cache_error', error=error))
            return
        self.cache_status.set(self.tr('discoveries_cache_done' if removed else 'discoveries_cache_empty'))

    def measure_tool_space(self):
        """Measure datas/tools, .deps and .build off Tk; the section only
        exists for a packaged installation."""
        from . import build_cleanup
        root = build_cleanup.managed_root()
        self.tools_root = root
        cancel = self.tools_cancel = threading.Event()
        self.tools_state = {'phase': 'measuring'} if root is not None else {'phase': 'unavailable'}
        self.render_disk_space()
        if root is None:
            return
        def worker():
            try:
                self.messages.put(('tools_space_measured', cancel, build_cleanup.tool_folders(root, cancel=cancel), None))
            except InterruptedError:
                pass
            except Exception as exc:
                self.messages.put(('tools_space_measured', cancel, None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def remove_tool_space(self):
        state = getattr(self, 'tools_state', {})
        folders = state.get('folders') or []
        root = getattr(self, 'tools_root', None)
        if self.busy or self.updating or state.get('phase') != 'measured' or not folders or root is None:
            return
        size = self.size_text(sum(folder.size for folder in folders))
        if not messagebox.askyesno(APP_NAME, self.tr('tools_space_confirm', size=size),
                                   icon='warning', default='no', parent=self.app):
            return
        # No conversion starts while the folders are removed.
        self.busy = True
        self.set_controls(False)
        self.stop_button.configure(state='disabled')
        self.tools_state = {'phase': 'working'}
        self.render_disk_space()
        def worker():
            from .build_cleanup import remove_tool_folders
            try:
                outcome = remove_tool_folders(root, emit=lambda text: self.messages.put(('log', text)))
                self.messages.put(('tools_space_removed', outcome, None))
            except Exception as exc:
                self.messages.put(('tools_space_removed', None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

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
        self.render_tool_space()

    def render_tool_space(self):
        """The build tools and caches line and button (hidden outside a
        packaged installation), from self.tools_state."""
        button, state = getattr(self, 'tools_button', None), getattr(self, 'tools_state', None)
        try:
            if button is None or state is None or not button.winfo_exists():
                return
            if state['phase'] == 'unavailable':
                self.tools_row.pack_forget()
                return
            if not self.tools_row.winfo_manager():
                self.tools_row.pack(anchor='w', fill='x', pady=(14, 0))
        except tk.TclError:
            return
        phase = state['phase']
        folders = state.get('folders') or []
        total = sum(folder.size for folder in folders)
        if phase == 'measured':
            text = self.tr('tools_space_found', size=self.size_text(total)) if folders else self.tr('tools_space_none')
        elif phase == 'done':
            outcome = state['outcome']
            text = self.tr('tools_space_done', size=self.size_text(outcome['freed']))
            if outcome['kept'] or outcome['errors']:
                text += ' ' + self.tr('disk_space_not_removed', count=outcome['kept'] + len(outcome['errors']))
        elif phase == 'error':
            text = self.tr('tools_space_error', error=state['error'])
        else:
            text = self.tr('tools_space_measuring' if phase == 'measuring' else 'tools_space_working')
        try:
            self.tools_status.set(text)
            ready = phase == 'measured' and bool(folders)
            button.configure(text=self.tr('tools_space_remove_size', size=self.size_text(total)) if ready
                             else self.tr('tools_space_remove'),
                             state='normal' if ready and not self.busy and not self.updating else 'disabled')
            self.tools_note.configure(text=self.tr('tools_space_note'))
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
