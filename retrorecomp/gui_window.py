"""The main window: header, background, buttons, language, help, credits and legal notices."""
from __future__ import annotations

from pathlib import Path
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import __version__, online
from .batch import system_output
from .paths import ASSETS, APP_NAME, save_preferences, save_game_language
from .i18n import STRINGS, tr
from .languages import LANGUAGES, LANGUAGE_NAMES, language_name
from .tooltips import Tooltip
from .ui_fonts import family
from .systems import get_profile
from .branding import COLORS, apply_theme, make_icon
from .dialogs import center_dialog
from .gui_common import HELP_URL, PLATFORMS, PROFILES, SENDING_AVAILABLE, UPSTREAM_CREDITS, UPX_SOURCE_URL
from .gui_drawing import (
    HATCH_SPACING, HEADER_HEIGHT, PIN_SIZE, PORTRAIT_SIZE, badges_width, draw_badges, draw_pin, draw_styled_text,
    header_theme, name_colours, _scaled_photo, _tint, _toolbar_styles,
)


class WindowMixin:
    """The main window: header, background, buttons, language, help, credits and legal notices."""

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
        # A shop frame is wider than the portrait: its ring takes room on both sides.
        try:
            ring = max(0, (self.portrait.width() - PORTRAIT_SIZE) // 2) if self.portrait else 0
        except (AttributeError, tk.TclError):
            ring = 0
        account = divider - 16 - self.player_actions.winfo_reqwidth() - 12 - ring
        self.header.coords(self.portrait_item, account - PORTRAIT_SIZE / 2, HEADER_HEIGHT / 2)
        text = account - PORTRAIT_SIZE - 12 - ring
        # Name, title (when one is chosen) and score, centred as one block
        # (a styled name is measured on its plain item, drawn again after).
        self.header.itemconfigure(self.player_name, fill=COLORS['text'])
        lines = [item for item in (self.player_name, self.player_title, self.player_score)
                 if self.header.itemcget(item, 'text')]
        heights = {item: (lambda box: box[3] - box[1])(self.header.bbox(item) or (0, 0, 0, 0)) for item in lines}
        top = max(4, (HEADER_HEIGHT - sum(heights.values()) - 2 * max(0, len(lines) - 1)) // 2)
        for item in (self.player_name, self.player_title, self.player_score):
            self.header.coords(item, text, top)
            if item in heights:
                top += heights[item] + 2
        self.draw_player_extras()

    def draw_player_extras(self):
        """The equipped shop items around the account's text: the pseudonym in
        its name style and the pin beside the title (beside the name without
        a title). Nothing without a catalog or an equipped item."""
        header = self.header
        header.delete('player_extra')
        looks = getattr(self, 'looks', None) or {}
        name = header.itemcget(self.player_name, 'text')
        style = looks.get('name_style')
        header.itemconfigure(self.player_name, fill=COLORS['text'])
        target = self.player_title if header.itemcget(self.player_title, 'text') else self.player_name
        box = header.bbox(target)
        if name and name_colours(style, 1):
            # The plain item keeps its place (an empty fill hides it); the glyphs draw it.
            header.itemconfigure(self.player_name, fill='')
            x, y = header.coords(self.player_name)
            draw_styled_text(header, x, y, name, (self.ui_font, 10, 'bold'), style, anchor='ne',
                             tags=('player_extra',))
        # The badge shown (one; a first place's badge with its mark), left of the name.
        badges = looks.get('badges') or []
        name_box = header.bbox('player_extra') if name and name_colours(style, 1) else header.bbox(self.player_name)
        badge_left = None
        if badges and name and name_box:
            font = (self.ui_font, 7, 'bold')
            width = badges_width(header, badges[:1], font)
            badge_left = name_box[0] - 6 - width
            middle = (name_box[1] + name_box[3]) / 2
            draw_badges(header, badge_left, middle, badges[:1], font, tags=('player_extra', 'player_badge'),
                        top=online.top_badges((self.player or {}).get('profile')))
        pin = looks.get('pin')
        if pin and name and box:
            # Beside the title; beside the name without one, left of the badge.
            right = badge_left if badge_left is not None and target == self.player_name else box[0]
            draw_pin(header, right - 4 - PIN_SIZE, (box[1] + box[3]) // 2 - PIN_SIZE // 2, pin,
                     tags=('player_extra',))

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
            for label in (self.player_name, self.player_title, self.player_score, 'player_extra'):
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
        theme = header_theme((getattr(self, 'looks', None) or {}).get('header_theme')) if canvas is self.header else None
        extent = (width, height, protected, theme)
        if extent == getattr(canvas, '_background_extent', None):
            return
        canvas._background_extent = extent
        canvas.delete('background_motif')
        if canvas is self.header:
            canvas.configure(bg=theme[1] if theme else COLORS['header'])
            canvas.itemconfigure(self.header_divider_tip, fill=theme[3] if theme else COLORS['gold'])
            if theme:
                self.paint_header_theme(canvas, width, height, protected, *theme)
                return
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

    @staticmethod
    def paint_header_theme(canvas, width, height, protected, kind, top, bottom, accent):
        """A shop header band: a vertical gradient and the theme's raster
        (neon grid, night stars, gold hatching), kept faint and away from the
        account's text so everything stays readable."""
        tags = ('background_motif', 'header_theme')
        for y in range(height):
            colour = _tint(top, bottom, y / max(1, height - 1))
            canvas.create_line(0, y, width, y, fill=colour, tags=tags)
        def clear(x, y):
            return not any(left <= x <= right and upper <= y <= lower for left, upper, right, lower in protected)
        if kind == 'neon':
            line = _tint(bottom, accent, 0.12)
            for x in range(0, width, 18):
                canvas.create_line(x, 0, x, height, fill=line, tags=tags)
            for y in range(6, height, 12):
                canvas.create_line(0, y, width, y, fill=line, tags=tags)
            canvas.create_line(0, height - 1, width, height - 1, fill=_tint(bottom, accent, 0.7), tags=tags)
        elif kind == 'night':
            import random
            stars = random.Random(7)
            for _ in range(max(1, width // 10)):
                x, y = stars.randrange(width), stars.randrange(height)
                if clear(x, y):
                    size = 2 if stars.random() < 0.15 else 1
                    canvas.create_rectangle(x, y, x + size, y + size, outline='', tags=tags,
                                            fill=_tint(top, accent if stars.random() < 0.5 else '#ffffff',
                                                       stars.uniform(0.3, 0.75)))
        else:
            hatch = _tint(bottom, accent, 0.08)
            first = -((height + HATCH_SPACING - 1) // HATCH_SPACING) * HATCH_SPACING
            for offset in range(first, width + HATCH_SPACING, HATCH_SPACING * 2):
                canvas.create_line(offset, 0, offset + height, height, fill=hatch, tags=tags)
            canvas.create_line(0, height - 1, width, height - 1, fill=_tint(bottom, accent, 0.6), tags=tags)
        canvas.tag_lower('background_motif')

    def hint(self, widget, key):
        self.tooltips.append(Tooltip(widget, lambda: self.tr(key)))

    def set_status(self, key, **values):
        self.status_key, self.status_values = key, values
        self.status.set(self.tr(key, **values))

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
            self.table.set(row, 'status', self.same_rom_text(row, result)
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

    def button(self, parent, text, command, tip, primary=False):
        """A text button with its picture and its hover hint `tip` (a key of
        the strings: the hint follows the interface language)."""
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
        self.hint(button, tip)
        return button

    def update_empty_state(self):
        if self.items:
            self.empty_state.place_forget()
        else:
            self.empty_state.place(relx=0.5, rely=0.5, y=18, anchor='center')

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
        # The credits page's look: its dark scene behind, '#202020' cards, the same gold.
        background, card, edge, tile = '#141414', '#202020', '#33302a', '#584b2a'
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
        style = ttk.Style(window)
        style.configure('Help.Vertical.TScrollbar', background='#2b2b2b', troughcolor=background,
                        bordercolor=background, arrowcolor=COLORS['gold'])
        bar.configure(style='Help.Vertical.TScrollbar')
        icons = ('add_rom_folder', 'refresh', 'play', 'new_paths', None)
        rows = []
        for index, icon in enumerate(icons, 1):
            row = tk.Frame(steps, bg=card, padx=10, pady=8, highlightthickness=1, highlightbackground=edge)
            badge = tk.Canvas(row, width=46, height=46, bg=card, highlightthickness=0)
            badge.pack(side='left', anchor='n')
            # A gold pixel tile with the step's picture, on a card.
            badge.create_rectangle(4, 4, 42, 42, fill='#141414', outline=COLORS['gold'], width=2)
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
            text = tk.Frame(row, bg=card)
            text.pack(side='left', fill='x', padx=(12, 0))
            tk.Label(text, text=self.tr(f'help_step{index}'), bg=card, fg=COLORS['text'],
                     font=(self.ui_font, 10, 'bold')).pack(anchor='w', pady=(2, 0))
            tk.Label(text, text=self.tr(f'help_step{index}_text'), bg=card, fg=COLORS['muted'],
                     font=(self.ui_font, 9), wraplength=500, justify='left').pack(anchor='w')
            rows.append(row)
        keys = tk.Frame(body, bg=card, highlightthickness=1, highlightbackground=tile, padx=12, pady=10)
        tk.Label(keys, text=self.tr('help_keys'), bg=card, fg=COLORS['gold'],
                 font=(self.ui_font, 9, 'bold')).grid(row=0, column=0, columnspan=6, sticky='w', pady=(0, 6))
        for column, (key, label) in enumerate((('F1', 'help_key_help'), ('F2', 'help_key_menu'),
                                               ('F3', 'help_key_filters'), ('F4', 'help_key_fullscreen'),
                                               ('F8 F9', 'help_key_states'), ('F12', 'help_key_learning'))):
            cell = tk.Frame(keys, bg=card)
            cell.grid(row=1, column=column, sticky='w', padx=(0, 14))
            tk.Label(cell, text=key, bg=background, fg=COLORS['gold'], font=(self.ui_font, 8, 'bold'),
                     padx=6, pady=1, highlightthickness=1, highlightbackground=tile).pack(anchor='w')
            tk.Label(cell, text=self.tr(label), bg=card, fg=COLORS['text'],
                     font=(self.ui_font, 8)).pack(anchor='w', pady=(3, 0))
        foot = tk.Frame(body, bg=background)
        tk.Label(foot, text=self.tr('help_private'), bg=background, fg=COLORS['muted'],
                 font=(self.ui_font, 8)).pack(side='left')
        ttk.Button(foot, text=self.tr('close'), command=window.destroy).pack(side='right')
        ttk.Button(foot, text=self.tr('help_guides'), command=lambda: webbrowser.open_new_tab(HELP_URL)).pack(
            side='right', padx=(0, 8))
        # A free-text report to the maintainer (needs the shared base's account).
        if SENDING_AVAILABLE:
            ttk.Button(foot, text=self.tr('report_title'), command=lambda: self.report_problem('manual')).pack(
                side='right', padx=(0, 8))
        window.bind('<Escape>', lambda event: window.destroy())
        # The steps arrive one after the other, then the keys and the buttons.
        def reveal(index=0):
            if not window.winfo_exists():return
            if index < len(rows):
                rows[index].pack(fill='x', pady=(0, 6))
                window.after(110, reveal, index + 1)
            else:
                keys.pack(fill='x', pady=(12, 0))
                foot.pack(fill='x', pady=(14, 0))
        for row in rows:
            row.pack(fill='x', pady=(0, 6))
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
