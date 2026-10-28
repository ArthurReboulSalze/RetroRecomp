"""The leaderboard, the achievement card and the closing card."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk

from . import online
from .paths import ASSETS, APP_NAME
from .tooltips import Tooltip
from .branding import COLORS
from .dialogs import center_dialog
from .gui_common import SENDING_AVAILABLE
from .gui_drawing import (
    CARTRIDGE, CLOUD, PIN_SIZE, TROPHY, badges_width, compact_number, draw_badges, draw_pin, draw_styled_text, elide,
    name_colours, _font, _scaled_photo, _tint,
)


class LeaderboardMixin:
    """The leaderboard, the achievement card and the closing card."""

    # The ranking's columns: key, caption, width (0: the player's, the rest) and alignment.
    BOARD_COLUMNS = (('rank', 'leaderboard_rank', 50, 'e'), ('player', 'leaderboard_player', 0, 'w'),
                     ('games', 'leaderboard_games', 64, 'e'), ('gold', 'class_gold', 84, 'e'),
                     ('platinum', 'class_platinum', 96, 'e'), ('diamond', 'class_diamond', 96, 'e'),
                     ('points', 'leaderboard_points', 84, 'e'))
    BOARD_ROW = 26
    BOARD_HEADING = 26

    def board_columns(self, width):
        """{key: (left, right)} of the ranking's columns for a list `width` wide."""
        fixed = sum(size for _, _, size, _ in self.BOARD_COLUMNS)
        spans, left = {}, 0
        for key, _, size, _ in self.BOARD_COLUMNS:
            size = size or max(160, width - fixed)
            spans[key] = (left, left + size)
            left += size
        return spans

    def draw_board_heading(self, canvas, width, pictures):
        canvas.delete('all')
        spans = self.board_columns(width)
        font = (self.ui_font, 9, 'bold')
        measure = _font(canvas, font)
        middle = self.BOARD_HEADING // 2
        for key, caption, _, anchor in self.BOARD_COLUMNS:
            left, right = spans[key]
            text = self.tr(caption)
            if anchor == 'e':
                canvas.create_text(right - 8, middle, text=text, anchor='e', fill=COLORS['text'], font=font)
                picture = pictures.get('gem-' + key)
                if picture:
                    canvas.create_image(right - 8 - measure.measure(text) - 12, middle, image=picture)
            else:
                canvas.create_text(left + 8, middle, text=text, anchor='w', fill=COLORS['text'], font=font)
            if left:
                canvas.create_line(left, 4, left, self.BOARD_HEADING - 4, fill=COLORS['subtle_border'])

    def draw_board_rows(self, canvas, rows, width, mine, catalog):
        """The ranking's lines on a canvas: rank, the pseudonym in its shop
        style, the console badge shown (a first place's one with its mark), the
        pin and the title, then games, class counts and points. The player's
        own line is highlighted."""
        canvas.delete('all')
        canvas._sparkle = []
        spans = self.board_columns(width)
        font, small, badge_font = (self.ui_font, 9), (self.ui_font, 8), (self.ui_font, 7, 'bold')
        name_font = (self.ui_font, 9, 'bold')
        measure, small_measure = _font(canvas, name_font), _font(canvas, small)
        row_height = self.BOARD_ROW
        for index, (entry, counts) in enumerate(rows):
            top, middle = index * row_height, index * row_height + row_height // 2
            name = entry.get('pseudonym') or self.tr('leaderboard_anonymous')
            you = bool(mine) and name == mine
            if you:
                canvas.create_rectangle(0, top, width, top + row_height, fill=COLORS['selected'], outline='')
            elif index % 2:
                canvas.create_rectangle(0, top, width, top + row_height, outline='',
                                        fill=_tint(COLORS['field'], '#ffffff', 0.03))
            colour = COLORS['gold'] if you else COLORS['text']
            canvas.create_text(spans['rank'][1] - 8, middle, text=str(entry.get('rank', '')), anchor='e',
                               fill=colour, font=font)
            look = online.looks(catalog, online.equipped(entry))
            title = self.title_name(entry.get('title'))
            left, right = spans['player'][0] + 8, spans['player'][1] - 8
            badges = look['badges']
            badge_room = badges_width(canvas, badges, badge_font) + 6 if badges else 0
            extra = PIN_SIZE + 4 if look['pin'] else 0
            tail = min(140, extra + small_measure.measure(title) + 10) if (title or extra) else 0
            shown = elide(measure, name, max(40, right - left - badge_room - tail))
            items, used = draw_styled_text(canvas, left, middle, shown, name_font, look['name_style'],
                                           anchor='w', fill=colour, tags=('board_name',))
            x = left + used + 6
            if badges:
                x += draw_badges(canvas, x, middle, badges, badge_font, tags=('board_badge',),
                                 top=online.top_badges(entry)) + 4
            if title or look['pin']:
                x += 6
                if look['pin']:
                    draw_pin(canvas, x, middle - PIN_SIZE // 2, look['pin'], tags=('board_pin',))
                    x += PIN_SIZE + 4
                if title:
                    canvas.create_text(x, middle, text=elide(small_measure, title, right - x), anchor='w',
                                       fill=COLORS['muted'], font=small, tags=('board_title',))
            for key, value in (('games', entry.get('games', 0)), ('gold', counts.get('gold', 0)),
                               ('platinum', counts.get('platinum', 0)), ('diamond', counts.get('diamond', 0)),
                               ('points', entry.get('total', 0))):
                canvas.create_text(spans[key][1] - 8, middle, text=self.count_text(value), anchor='e',
                                   fill=colour, font=font)
        canvas.configure(scrollregion=(0, 0, width, max(1, len(rows)) * row_height))

    def show_leaderboard(self):
        """The shared base's ranking in a window: podium order, pseudonyms,
        games and points, all time or this month, with the player's own line.
        What players equip in the site's shop shows as there: name styles, the
        console badge shown (with its "1" for a first place), pins (titles as
        before); nothing without the shop's catalog."""
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
        from tkinter import font as tkfont
        count_font = tkfont.Font(window, family=self.ui_font, size=9)
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
        # The shop's catalog ({id: item}) once the board has answered.
        catalog = {}
        # Podium: second, first, third, on steps of different heights.
        podium = tk.Canvas(body, height=196, bg=background, highlightthickness=0)
        podium.pack(fill='x', pady=(10, 8))
        podium.rows = []
        podium.bind('<Configure>', lambda event: draw_podium(podium.rows))
        # The ranking: a canvas list, so a name can carry its style, badges and pin.
        listing = tk.Frame(body, bg=COLORS['field'], highlightthickness=1, highlightbackground=COLORS['border'])
        heading = tk.Canvas(listing, height=self.BOARD_HEADING, bg=COLORS['button'], highlightthickness=0)
        table = tk.Canvas(listing, height=self.BOARD_ROW * 9, bg=COLORS['field'], highlightthickness=0,
                          yscrollincrement=self.BOARD_ROW)
        bar = ttk.Scrollbar(listing, orient='vertical', command=table.yview)
        table.configure(yscrollcommand=bar.set)
        heading.grid(row=0, column=0, sticky='ew')
        table.grid(row=1, column=0, sticky='nsew')
        bar.grid(row=0, column=1, rowspan=2, sticky='ns')
        listing.grid_columnconfigure(0, weight=1)
        listing.grid_rowconfigure(1, weight=1)
        listing.pack(fill='both', expand=True)
        table.rows, table.mine = [], None
        def draw_table(event=None):
            width = table.winfo_width()
            if width < 300:
                return
            self.draw_board_heading(heading, width, pictures)
            self.draw_board_rows(table, table.rows, width, table.mine, catalog)
        table.bind('<Configure>', draw_table)
        def scroll(event):
            steps = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
            table.yview_scroll(steps * max(1, abs(getattr(event, 'delta', 0)) // 120), 'units')
            return 'break'
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            table.bind(sequence, scroll)
        # The footer is reserved first: a longer note above never clips it.
        you_line = tk.Label(body, text='', bg=background, fg=COLORS['text'], font=(self.ui_font, 9))
        close = ttk.Button(body, text=self.tr('close'), command=window.destroy)
        close.pack(side='bottom', anchor='e', pady=(10, 0), before=listing)
        you_line.pack(side='bottom', anchor='w', pady=(8, 0), before=listing)

        # Opening animation: the steps rise one after the other (third, second,
        # first), carrying each player's crown, name, points and gems up.
        podium.started = time.monotonic()
        RISE, DELAYS = 0.6, {3: 0.0, 2: 0.18, 1: 0.36}
        GEMS_ROOM = 58   # the top of a step: gems, their counts and the badge

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
            podium._sparkle = []
            width, bottom = podium.winfo_width(), int(podium.cget('height'))
            if width < 300:
                return
            elapsed = time.monotonic() - podium.started
            step = 170
            inner = step - 16   # content stays inside each step's box
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
            name_font, title_font, badge_font = (self.ui_font, 10, 'bold'), (self.ui_font, 8), (self.ui_font, 7, 'bold')
            gem_font = (self.ui_font, 8, 'bold')
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
                # The place's number, under the gems and the badge (GEMS_ROOM).
                if height > GEMS_ROOM + 20:
                    podium.create_text(middle, bottom - (height - GEMS_ROOM) // 2, text=str(place),
                                       fill=shades[place], font=(self.ui_font, 16, 'bold'))
                if place > len(rows) or progress < 0.2:
                    continue
                top += shift
                entry, counts = rows[place - 1]
                look = online.looks(catalog, online.equipped(entry))
                name = entry.get('pseudonym') or self.tr('leaderboard_anonymous')
                crown(middle, top - 4, place, shades[place])
                if name_colours(look['name_style'], 1):
                    draw_styled_text(podium, middle, top + 9, elide(_font(podium, name_font), name, inner),
                                     name_font, look['name_style'], anchor='center', tags=('podium_name',))
                else:
                    podium.create_text(middle, top + 9, text=name, fill=COLORS['text'],
                                       font=name_font, width=inner)
                podium.create_text(middle, top + 28, text=f"{self.count_text(entry.get('total', 0))} pts",
                                   fill=shades[place], font=(self.ui_font, 9, 'bold'))
                # The title, its pin before it (alone without a title).
                title, pin = self.title_name(entry.get('title')), look['pin']
                if title or pin:
                    measure = _font(podium, title_font)
                    room = inner - (PIN_SIZE + 4 if pin else 0)
                    shown = elide(measure, title, room) if title else ''
                    spot = middle - (measure.measure(shown) + (PIN_SIZE + (4 if shown else 0) if pin else 0)) / 2
                    if pin:
                        draw_pin(podium, round(spot), top + 43 - PIN_SIZE // 2, pin, tags=('podium_pin',))
                        spot += PIN_SIZE + 4
                    if shown:
                        podium.create_text(spot, top + 43, text=shown, anchor='w', fill=COLORS['muted'],
                                           font=title_font)
                # The three class gems in fixed columns, each count under its gem
                # (0 included), so the layout never moves; counts from 1,000 shorten (1.2K).
                for column, kind in zip((-1, 0, 1), ('gold', 'platinum', 'diamond')):
                    centre = middle + column * (inner // 3)
                    picture = pictures.get(f'gem-{kind}')
                    if picture:
                        podium.create_image(centre, bottom - height + 15, image=picture)
                    podium.create_text(centre, bottom - height + 33,
                                       text=compact_number(counts.get(kind, 0), self.language, 1_000),
                                       fill=COLORS['text'], font=gem_font)
                # The console badge shown under the gems (a first place's one with
                # its mark), once the step is tall enough.
                if look['badges'] and height > GEMS_ROOM + 20:
                    wide = badges_width(podium, look['badges'], badge_font)
                    draw_badges(podium, middle - wide / 2, bottom - height + 49, look['badges'], badge_font,
                                tags=('podium_badge',), top=online.top_badges(entry))
            if moving or elapsed < DELAYS[1] + RISE + 0.05:
                pending = getattr(podium, 'frame', None)
                if pending:
                    podium.after_cancel(pending)
                podium.frame = podium.after(16, lambda: window.winfo_exists() and draw_podium(podium.rows))
            else:
                podium.frame = None

        def show(answer, error, shop=None):
            if not window.winfo_exists():return
            catalog.clear()
            catalog.update(shop or {})
            if error:
                note.configure(text=error)
                table.rows = []
                draw_table()
                draw_podium([])
                return
            entries = answer.get('entries', [])
            note.configure(text=self.tr('leaderboard_demo') if answer.get('demo')
                           else self.tr('leaderboard_empty') if not entries else self.tr('leaderboard_rules'))
            mine = (self.player.get('profile') or {}).get('pseudonym') or (self.player.get('account') or {}).get('pseudonym')
            rows = []
            for entry in entries:
                # The server counts classes per console: {console: {gold, platinum, diamond}}.
                counts = {}
                for console in (entry.get('counts') or {}).values():
                    for name, value in (console.items() if isinstance(console, dict) else ()):
                        if isinstance(value, (int, float)):
                            counts[name] = counts.get(name, 0) + int(value)
                rows.append((entry, counts))
            table.rows, table.mine = rows, mine
            table.yview_moveto(0)
            draw_table()
            draw_podium(rows[:3], animate=True)
            you = answer.get('you') or {}
            if you.get('rank'):
                you_line.configure(text=self.tr('leaderboard_you', rank=you['rank'], points=self.count_text(you.get('total', 0))))
            elif online.account():
                you_line.configure(text=self.tr('account_unranked', points=self.count_text(you.get('total', 0))))
            else:
                you_line.configure(text='')
        def load():
            note.configure(text=self.tr('leaderboard_loading'))
            wanted = period.get()
            result = []
            def worker():
                # No Tk call here: the window polls for the answer. The shop's
                # catalog comes from its cache (refreshed every 30 minutes at most).
                try:
                    board = online.board(wanted)
                except (online.ServiceError, online.ServiceConnectionError) as exc:
                    result.append((None, self.online_message(exc), {}))
                    return
                try:
                    shop = online.shop()
                except Exception:
                    shop = {}
                result.append((board, None, shop))
            def poll():
                if not window.winfo_exists():return
                if result:show(*result[0])
                else:window.after(50, poll)
            threading.Thread(target=worker, daemon=True).start()
            poll()
        window.bind('<Escape>', lambda event: window.destroy())
        window.update_idletasks()
        center_dialog(window, self.app, 760, 700)
        window.deiconify()
        load()

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
