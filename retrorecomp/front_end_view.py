"""Front-end: the window shows the compiled games as a wall of box art, one console at a time.

Another presentation of the Compiled Games inventory (compiled_games.py): the same games, the same covers (the game
cards, game_details.Cards), the same launch (CompiledGamesView.launch) and the same box-art window (gui_covers). Only
the visible rows are drawn; covers are read and scaled off Tk, the visible ones first, and only a bounded number of
them is kept in memory. Mouse, keyboard and gamepad (front_end.GridPad) all work.
"""
from __future__ import annotations

from collections import OrderedDict
from io import BytesIO
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import font as tkfont, ttk

from PIL import Image, ImageTk

from .branding import COLORS
from .compiled_games_view import stars
from .front_end import (DEFAULT_ASPECT, FOCUS_GROWTH, ORDERS, SCALE_TV, SCALE_WINDOW, GridPad, Memory, cell_aspect,
                        fit, game_key, grid, move, shelves, sort_games, step_columns)
from .platforms import open_local
from .systems import available_profiles

KEEP_THUMBNAILS = 360        # covers kept scaled in memory (about 40 MB at the default size)
KEEP_PHOTOS = 160            # Tk pictures kept for the tiles drawn or just scrolled out


class CoverLoader:
    """One worker thread: reads each wanted game's cover through the game cards and scales it to `box`. The view
    gives it the games in the order it wants them (the visible ones first) and gets ('cover', key, image|None, ratio)
    back on `events`. Pillow only; no Tk call happens here."""
    def __init__(self, events, cards):
        self.events, self.cards = events, cards
        self.wanted, self.box, self.generation = [], (160, 220), 0
        self.done = set()
        self.condition = threading.Condition()
        self.closed = False
        threading.Thread(target=self.run, daemon=True).start()

    def want(self, games, box, *, reset=False):
        with self.condition:
            if reset or box != self.box:
                self.done.clear()
                self.generation += 1
            self.box = box
            self.wanted = [game for game in games if game_key(game) not in self.done]
            self.condition.notify()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify()

    def run(self):
        while True:
            with self.condition:
                while not self.closed and not self.wanted:
                    self.condition.wait()
                if self.closed:
                    return
                game = self.wanted.pop(0)
                key, box, generation = game_key(game), self.box, self.generation
                if key in self.done:
                    continue
                self.done.add(key)
            image, ratio = None, None
            try:
                payload = self.cards.cover(game)
                if payload:
                    with Image.open(BytesIO(payload)) as source:
                        ratio = source.width / source.height if source.height else None
                        picture = source.convert('RGBA')
                    picture.thumbnail((max(1, round(box[0] * FOCUS_GROWTH)), max(1, round(box[1] * FOCUS_GROWTH))),
                                      Image.Resampling.LANCZOS)
                    image = Image.new('RGB', picture.size, COLORS['background'])
                    image.paste(picture, mask=picture.getchannel('A'))
            except Exception:
                image, ratio = None, None
            self.events.put(('cover', generation, key, image, ratio))


class FrontEndView(tk.Frame):
    def __init__(self, owner, parent, *, memory=None, cards=None):
        super().__init__(parent, bg=COLORS['background'])
        self.owner, self.tr = owner, owner.tr
        self.memory = memory or owner.played_memory()
        from .game_details import Cards
        self.cards = cards or Cards()
        self.events = queue.Queue()
        self.loader = CoverLoader(self.events, self.cards)
        self.profiles = available_profiles()
        self.shelves, self.shelf, self.games = [], 0, []
        self.focus_index = 0
        self.aspects = {}
        self.ratios = {}                  # system -> {key: width / height of its cover}
        self.thumbnails = OrderedDict()   # key -> PIL image at the focused size
        self.no_cover = set()
        self.photos = OrderedDict()       # (key, width, height) -> PhotoImage
        self.layout = None
        self.menu_items, self.menu_index = None, 0
        self.menu_heading = None   # a question in place of the game's title (« Leave the front-end? »)
        # Games chosen with Ctrl / Shift + click (or Ctrl+A) on the console shown: the menu then acts on all of them.
        self.selected, self.anchor = set(), 0
        self.searching = None      # (done, total, found) while covers are searched online
        self.controller, self.pad = None, GridPad()
        self.pad_seen = False
        self.force_pad_hints = False
        self.scale = self.wanted_scale()
        self.fonts()

        self.tabs = tk.Canvas(self, bg=COLORS['background'], highlightthickness=0, height=self.cx(38))
        self.tabs.pack(fill='x', padx=12, pady=(4, 0))
        self.details = tk.Canvas(self, bg=COLORS['header'], highlightthickness=0, height=self.cx(44))
        self.details.pack(side='bottom', fill='x')
        middle = tk.Frame(self, bg=COLORS['background'])
        middle.pack(fill='both', expand=True)
        self.wall = tk.Canvas(middle, bg=COLORS['background'], highlightthickness=0, yscrollincrement=1,
                              takefocus=True)
        self.scrollbar = ttk.Scrollbar(middle, orient='vertical', command=self.scroll_to)
        self.wall.configure(yscrollcommand=self.scrolled)
        self.scrollbar.pack(side='right', fill='y')
        self.wall.pack(side='left', fill='both', expand=True)
        self.wall.bind('<Configure>', lambda event: self.relayout())
        self.tabs.bind('<Configure>', lambda event: self.draw_tabs())
        self.details.bind('<Configure>', lambda event: self.draw_details())
        self.tabs.bind('<Button-1>', self.tab_clicked)
        self.wall.bind('<Button-1>', self.clicked)
        self.wall.bind('<Double-1>', lambda event: self.play())
        self.wall.bind('<Button-3>', self.context_menu)
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.wall.bind(sequence, self.wheel)
        # Ctrl + wheel: more or fewer covers per row, like a zoom.
        for sequence in ('<Control-MouseWheel>', '<Control-Button-4>', '<Control-Button-5>'):
            self.wall.bind(sequence, self.zoom_wheel)
        for sequence, action in (('<Left>', lambda: self.step(-1, 0)), ('<Right>', lambda: self.step(1, 0)),
                                 ('<Up>', lambda: self.step(0, -1)), ('<Down>', lambda: self.step(0, 1)),
                                 ('<Prior>', lambda: self.page(-1)), ('<Next>', lambda: self.page(1)),
                                 ('<Home>', lambda: self.go(0)), ('<End>', lambda: self.go(len(self.games) - 1)),
                                 ('<Return>', self.accept), ('<KP_Enter>', self.accept),
                                 ('<Escape>', self.back), ('<BackSpace>', self.back),
                                 ('<Tab>', lambda: self.switch(1)), ('<Shift-Tab>', lambda: self.switch(-1)),
                                 ('<ISO_Left_Tab>', lambda: self.switch(-1)),
                                 ('<space>', self.open_menu), ('<App>', self.open_menu),
                                 ('<minus>', lambda: self.change_columns(-1)),
                                 ('<KP_Subtract>', lambda: self.change_columns(-1)),
                                 ('<plus>', lambda: self.change_columns(1)), ('<equal>', lambda: self.change_columns(1)),
                                 ('<KP_Add>', lambda: self.change_columns(1)),
                                 ('<Control-a>', self.select_all), ('<Control-A>', self.select_all),
                                 ('<Shift-F10>', self.open_menu), ('<F11>', self.toggle_tv)):
            self.wall.bind(sequence, lambda event, action=action: (action(), 'break')[1])
        self.wall.bind('<Key>', self.letter)
        self.after(30, self.drain)

    # ---- sizes and fonts
    def px(self, value):
        return max(1, round(value * self.scale))

    def cx(self, value):
        """Sizes of the two bars: in full screen they grow far less than the covers, so they stay thin (Arthur)."""
        return max(1, round(value * (1.15 if self.scale > 1 else 1.0)))

    def fonts(self):
        family = self.owner.ui_font
        self.font_title = tkfont.Font(root=self, family=family, size=self.px(9))
        self.font_focus = tkfont.Font(root=self, family=family, size=self.px(9), weight='bold')
        self.font_tab = tkfont.Font(root=self, family=family, size=self.px(11))
        self.font_tab_bold = tkfont.Font(root=self, family=family, size=self.px(11), weight='bold')
        self.font_small = tkfont.Font(root=self, family=family, size=self.px(8))
        self.font_strip = tkfont.Font(root=self, family=family, size=self.cx(10))
        self.font_strip_bold = tkfont.Font(root=self, family=family, size=self.cx(10), weight='bold')
        self.font_count = tkfont.Font(root=self, family=family, size=self.cx(8))
        self.font_detail = tkfont.Font(root=self, family=family, size=self.cx(11), weight='bold')
        self.font_hint = tkfont.Font(root=self, family=family, size=self.cx(9))
        self.font_glyph = tkfont.Font(root=self, family=family, size=self.cx(8), weight='bold')

    def wanted_scale(self):
        return SCALE_TV if getattr(self.owner, 'front_end_fullscreen', False) else SCALE_WINDOW

    def apply_scale(self):
        self.scale = self.wanted_scale()
        self.fonts()
        self.tabs.configure(height=self.cx(38))
        self.details.configure(height=self.cx(44))
        self.photos.clear()
        self.relayout(reload=True)
        self.draw_tabs()

    # ---- data
    def show(self):
        """Read the inventory again (the view may have been away while games were converted) and draw."""
        current = self.shelves[self.shelf][0].id if self.shelves else self.memory.console
        self.shelves = shelves(self.owner.compiled_inventory.snapshot(), self.profiles)
        ids = [profile.id for profile, _ in self.shelves]
        self.select_shelf(ids.index(current) if current in ids else 0, keep_focus=True)
        self.start_controller()
        self.wall.focus_set()

    def select_shelf(self, index, keep_focus=False):
        if not self.shelves:
            self.games = []
            self.relayout()
            self.draw_tabs()
            return
        index %= len(self.shelves)
        previous = self.games[self.focus_index] if keep_focus and self.games else None
        self.shelf = index
        profile, games = self.shelves[index]
        self.memory.console = profile.id
        self.memory.save()
        self.selected.clear()
        self.games = sort_games(games, self.memory.order, self.memory.played)
        keys = [game_key(game) for game in self.games]
        self.focus_index = keys.index(game_key(previous)) if previous and game_key(previous) in keys else 0
        self.close_menu(draw=False)
        self.wall.yview_moveto(0)
        self.relayout(reload=True)
        self.draw_tabs()

    def focused(self):
        return self.games[self.focus_index] if self.games else None

    def set_order(self, order):
        self.memory.order = order
        self.memory.save()
        game = self.focused()
        self.games = sort_games(self.games, order, self.memory.played)
        if game:
            self.focus_index = self.games.index(game)
        self.relayout(reload=True)
        self.see(self.focus_index)

    # ---- layout and drawing
    def relayout(self, reload=False):
        width = max(1, self.wall.winfo_width())
        system = self.shelves[self.shelf][0].id if self.shelves else ''
        aspect = self.aspects.get(system) or DEFAULT_ASPECT
        line = self.font_title.metrics('linespace')
        layout = grid(width, aspect, self.scale, line, self.memory.columns.get(system))
        changed = layout != self.layout
        self.layout = layout
        self.wall.configure(scrollregion=(0, 0, width, max(layout.height(len(self.games)), self.wall.winfo_height())))
        if changed or reload:
            self.request_covers(reset=changed)
        self.draw_wall()
        self.draw_details()
        if changed:
            self.draw_tabs()

    def change_columns(self, change):
        """More (+1) or fewer (-1) covers per row, for the console shown only; remembered."""
        if not self.shelves or not self.layout or self.menu_items is not None:
            return
        system = self.shelves[self.shelf][0].id
        columns = step_columns(self.layout.columns, change)
        if columns == self.layout.columns:
            return
        self.memory.columns[system] = columns
        self.memory.save()
        self.relayout()
        self.see(self.focus_index)
        self.draw_wall()

    def visible_range(self):
        top = self.wall.canvasy(0)
        return self.layout.visible(top, self.wall.winfo_height(), len(self.games))

    def request_covers(self, reset=False):
        if not self.layout or not self.games:
            return
        shown = self.visible_range()
        around = list(shown) + [i for i in range(len(self.games)) if i not in shown]
        self.loader.want([self.games[i] for i in around], (self.layout.cover_width, self.layout.cover_height),
                         reset=reset)

    def draw_wall(self):
        canvas = self.wall
        canvas.delete('tile')
        if not self.layout:
            return
        if not self.games:
            canvas.create_text(canvas.winfo_width() // 2, canvas.winfo_height() // 2, text=self.tr('front_end_empty'),
                               fill=COLORS['muted'], font=self.font_tab, width=canvas.winfo_width() - 80,
                               justify='center', tags='tile')
            return
        focused = None
        for index in self.visible_range():
            if index == self.focus_index:
                focused = index
                continue
            self.draw_tile(index, False)
        if focused is not None:
            self.draw_tile(focused, True)
        if self.menu_items is not None:
            self.draw_menu()

    def draw_tile(self, index, focus):
        canvas, layout, game = self.wall, self.layout, self.games[index]
        key = game_key(game)
        x, y = layout.origin(index)
        x += layout.gap // 2
        width, height = layout.cover_width, layout.cover_height
        if focus:
            grown_w, grown_h = round(width * FOCUS_GROWTH), round(height * FOCUS_GROWTH)
            x -= (grown_w - width) // 2
            y -= grown_h - height
            width, height = grown_w, grown_h
        bottom = y + height
        thumbnail = self.thumbnails.get(key)
        if thumbnail is not None:
            self.thumbnails.move_to_end(key)
            size = fit(thumbnail.size, (width, height))
            photo = self.photo(key, thumbnail, size)
            left = x + (width - size[0]) // 2
            canvas.create_image(left, bottom, image=photo, anchor='sw', tags='tile')
            box = (left, bottom - size[1], left + size[0], bottom)
        elif key in self.no_cover:
            box = (x, y, x + width, bottom)
            self.placeholder(game, box, focus)
        else:
            box = (x, y, x + width, bottom)
            canvas.create_rectangle(*box, fill=COLORS['field'], outline=COLORS['subtle_border'], tags='tile')
        if key in self.selected:
            # A chosen game: dimmed a little, a gold frame and a check mark in its corner.
            canvas.create_rectangle(*box, outline=COLORS['gold_hover'], width=self.px(3), tags='tile')
            r = self.px(11)
            cx, cy = box[0] + r + self.px(4), box[1] + r + self.px(4)
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=COLORS['gold'], outline=COLORS['gold_text'],
                               width=self.px(1.5), tags='tile')
            canvas.create_line(cx - r * 0.45, cy, cx - r * 0.1, cy + r * 0.4, cx + r * 0.5, cy - r * 0.35,
                               fill=COLORS['gold_text'], width=self.px(2.5), tags='tile')
        if focus:
            pad = self.px(4)
            canvas.create_rectangle(box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad, outline=COLORS['gold'],
                                    width=self.px(3), tags='tile')
        if game.favorite:
            canvas.create_text(box[2] - self.px(6), box[1] + self.px(4), text='★', anchor='ne',
                               fill=COLORS['gold'], font=self.font_tab_bold, tags='tile')
        if not layout.title_lines:
            return
        font = self.font_focus if focus else self.font_title
        lines = clamp_lines(font, game.title, layout.cover_width + layout.gap // 2, layout.title_lines)
        canvas.create_text(layout.origin(index)[0] + layout.tile_width // 2,
                           layout.origin(index)[1] + layout.cover_height + self.px(10) + (self.px(4) if focus else 0),
                           text='\n'.join(lines), anchor='n', justify='center', font=font,
                           fill=COLORS['gold_hover'] if focus else COLORS['text'], tags='tile')

    def placeholder(self, game, box, focus):
        canvas = self.wall
        canvas.create_rectangle(*box, fill=COLORS['panel'], outline=COLORS['subtle_border'], tags='tile')
        x0, y0, x1, y1 = box
        inner = x1 - x0 - self.px(16)
        system = self.shelves[self.shelf][0].name if self.shelves else ''
        canvas.create_text((x0 + x1) // 2, y0 + self.px(12), text=system.upper(), anchor='n', fill=COLORS['gold'],
                           font=self.font_small, width=inner, justify='center', tags='tile')
        lines = clamp_lines(self.font_tab_bold, game.title, inner, 4)
        canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2, text='\n'.join(lines), fill=COLORS['text'],
                           font=self.font_tab_bold, justify='center', tags='tile')
        canvas.create_text((x0 + x1) // 2, y1 - self.px(12), text='+ ' + self.tr('front_end_add_cover'), anchor='s',
                           fill=COLORS['gold_hover'] if focus else COLORS['muted'], font=self.font_small,
                           width=inner, justify='center', tags='tile')

    def photo(self, key, thumbnail, size):
        name = (key, *size)
        photo = self.photos.get(name)
        if photo is None:
            image = thumbnail if thumbnail.size == size else thumbnail.resize(size, Image.Resampling.BILINEAR)
            photo = self.photos[name] = ImageTk.PhotoImage(image, master=self)
            while len(self.photos) > KEEP_PHOTOS:
                self.photos.popitem(last=False)
        else:
            self.photos.move_to_end(name)
        return photo

    def draw_tabs(self):
        canvas = self.tabs
        canvas.delete('all')
        width, height = canvas.winfo_width(), int(canvas['height'])
        if not self.shelves:
            return
        glyph = self.cx(30)
        # Full screen and back: a labelled button at the right end, always there (Arthur, 16 Nov 2026).
        restore = self.draw_screen_button(width, height // 2 - self.cx(2))
        width -= restore
        spacing = self.cx(26)
        items = []
        for index, (profile, games) in enumerate(self.shelves):
            font = self.font_strip_bold if index == self.shelf else self.font_strip
            name = profile.name
            count = f'  {len(games)}'
            items.append((index, name, count, font, font.measure(name) + self.font_count.measure(count)))
        total = sum(item[4] for item in items) + spacing * (len(items) - 1)
        density = self.draw_density(width - glyph - self.cx(14), height // 2 - self.cx(2))
        room = width - 2 * (glyph + self.cx(14)) - density
        start = glyph + self.cx(14)
        if total > room:
            # Keep the chosen console in view: scroll the strip so it sits near the middle.
            before = sum(item[4] + spacing for item in items[:self.shelf])
            offset = min(max(0, before - room // 2 + items[self.shelf][4] // 2), total - room)
            start -= offset
        self.tab_boxes = []
        x = start
        middle = height // 2 - self.cx(2)
        for index, name, count, font, size in items:
            chosen = index == self.shelf
            # Only whole names: a console cut by the edge waits for the strip to scroll to it.
            if x >= glyph + self.cx(8) and x + size <= width - glyph - self.cx(8) - density:
                canvas.create_text(x, middle, text=name, anchor='w', font=font,
                                   fill=COLORS['gold_hover'] if chosen else COLORS['muted'])
                canvas.create_text(x + font.measure(name), middle + self.cx(1), text=count, anchor='w',
                                   font=self.font_count, fill=COLORS['gold'] if chosen else COLORS['disabled'])
                if chosen:
                    canvas.create_rectangle(x, height - self.cx(6), x + size, height - self.cx(3), fill=COLORS['gold'],
                                            outline='')
            self.tab_boxes.append((x, x + size, index))
            x += size + spacing
        self.pill(canvas, 0, middle, 'LB')
        self.pill(canvas, width - glyph, middle, 'RB')
        canvas.create_line(0, height - 1, width + restore, height - 1, fill=COLORS['subtle_border'])

    def draw_screen_button(self, right, middle):
        """« Full screen » (one frame) in the window, « Window » (two frames) in full screen, at the right end of the
        strip; returns the room it takes."""
        canvas = self.tabs
        full = getattr(self.owner, 'front_end_fullscreen', False)
        label = self.tr('front_end_windowed' if full else 'front_end_fullscreen')
        unit, pad, height = self.cx(4), self.cx(10), self.cx(26)
        width = pad * 2 + unit * 3 + self.cx(8) + self.font_hint.measure(label)
        left = right - width
        self.restore_box = (left, right)
        canvas.create_rectangle(left, middle - height // 2, right, middle + height // 2, fill=COLORS['button'],
                                outline=COLORS['gold'])
        x, y, line = left + pad + unit, middle, max(1, self.cx(1.2))
        if full:
            canvas.create_rectangle(x - unit, y - unit + 2, x + unit - 2, y + unit + 2, outline=COLORS['text'],
                                    width=line)
            canvas.create_line(x - unit + 2, y - unit - 1, x + unit + 1, y - unit - 1, x + unit + 1, y + unit - 1,
                               fill=COLORS['text'], width=line)
        else:
            canvas.create_rectangle(x - unit, y - unit, x + unit + 1, y + unit, outline=COLORS['text'], width=line)
        canvas.create_text(x + unit * 2 + self.cx(6), middle, text=label, anchor='w', font=self.font_hint,
                           fill=COLORS['text'])
        return width + self.cx(10)

    def draw_density(self, right, middle):
        """Right of the consoles: the covers per row of this console between a minus and a plus button; returns
        the room it takes."""
        canvas = self.tabs
        if not self.layout:
            self.density_boxes = []
            return 0
        label = self.tr('front_end_per_row', count=self.layout.columns)
        button = self.cx(22)
        width = button * 2 + self.font_hint.measure(label) + self.cx(20)
        left = right - width
        self.density_boxes = [(left, left + button, -1), (right - button, right, 1)]
        for x0, x1, change in self.density_boxes:
            canvas.create_rectangle(x0, middle - button // 2, x1, middle + button // 2, fill=COLORS['button'],
                                    outline=COLORS['subtle_border'])
            half = self.cx(5)
            centre = (x0 + x1) // 2
            canvas.create_line(centre - half, middle, centre + half + 1, middle, fill=COLORS['text'], width=self.cx(2))
            if change > 0:
                canvas.create_line(centre, middle - half, centre, middle + half + 1, fill=COLORS['text'],
                                   width=self.cx(2))
        canvas.create_text((left + right) // 2, middle, text=label, font=self.font_hint, fill=COLORS['muted'])
        return width + self.cx(18)

    def pill(self, canvas, x, y, text, color=None):
        """A gamepad button drawn as a small rounded label (letters only: every interface font has them)."""
        font = self.font_glyph
        width = self.cx(26) if text == 'MENU' else max(font.measure(text) + self.cx(12), self.cx(22))
        height = self.cx(20)
        color = color or COLORS['border']
        r = height // 2
        canvas.create_oval(x, y - r, x + height, y + r, fill=color, outline='')
        canvas.create_oval(x + width - height, y - r, x + width, y + r, fill=color, outline='')
        canvas.create_rectangle(x + r, y - r, x + width - r, y + r, fill=color, outline='')
        if text == 'MENU':
            # The Start / Menu button: three short lines rather than a glyph some fonts lack.
            for dy in (-4, 0, 4):
                canvas.create_line(x + width // 2 - self.cx(5), y + self.cx(dy), x + width // 2 + self.cx(5),
                                   y + self.cx(dy), fill=COLORS['text'], width=max(1, self.cx(1.5)))
        else:
            canvas.create_text(x + width // 2, y, text=text, font=font, fill=COLORS['text'])
        return width

    def draw_details(self):
        canvas = self.details
        canvas.delete('all')
        width, height = canvas.winfo_width(), int(canvas['height'])
        canvas.create_line(0, 0, width, 0, fill=COLORS['subtle_border'])
        game = self.focused()
        pads = self.controller is not None or self.force_pad_hints
        screen = 'front_end_windowed' if getattr(self.owner, 'front_end_fullscreen', False) else 'front_end_fullscreen'
        if pads:
            hints = [(('A',), 'play'), (('B',), 'front_end_back'), (('X',), screen), (('Y',), 'front_end_actions'),
                     (('L2', 'R2'), 'front_end_density')]
        else:
            hints = [((self.tr('front_end_key_enter'),), 'play'), ((self.tr('front_end_key_escape'),), 'front_end_back'),
                     (('F11',), screen), ((self.tr('front_end_key_space'),), 'front_end_actions'),
                     (('\u2212', '+'), 'front_end_density')]
        colors = {'A': '#3c7d4a', 'B': '#8a3b3b', 'X': '#365f8f', 'Y': '#8a7a2e'}
        x = width - self.cx(14)
        for glyphs, key in reversed(hints):
            label = self.tr(key)
            x -= self.font_hint.measure(label)
            canvas.create_text(x, height // 2, text=label, anchor='w', font=self.font_hint, fill=COLORS['muted'])
            x -= self.cx(6)
            for glyph in reversed(glyphs):
                size = self.cx(26) if glyph == 'MENU' else max(self.font_glyph.measure(glyph) + self.cx(12), self.cx(22))
                self.pill(canvas, x - size, height // 2, glyph, colors.get(glyph))
                x -= size + self.cx(3)
            x -= self.cx(13)
        hints_left = x
        if not game:
            return
        order = self.tr('front_end_order_' + self.memory.order)
        played = self.memory.played.get(game_key(game))
        facts = [self.shelves[self.shelf][0].name, self.played_text(played)]
        # The saved card, when there is one (Compiled Games' « Fetch details »): its year and developer.
        facts[1:1] = self.card_facts(game)
        if stars(game.level):
            facts.append(stars(game.level))
        if game.status == 'fallback':
            facts.append(self.tr('front_end_fallback'))
        facts.append(self.tr('front_end_sorted', order=order))
        if self.searching:
            facts.insert(0, self.tr('front_end_searching', done=self.searching[0], total=self.searching[1]))
        elif getattr(self, 'search_result', None):
            facts.insert(0, self.tr('front_end_search_done', found=self.search_result[2], total=self.search_result[1]))
        if self.selected:
            facts.insert(0, self.tr('front_end_selected', count=len(self.selected)))
        left = self.cx(16)
        room = max(40, hints_left - left - self.cx(20))
        title = clamp_lines(self.font_detail, game.title, room, 1)[0]
        canvas.create_text(left, height // 2 - self.cx(8), text=title, anchor='w', font=self.font_detail,
                           fill=COLORS['text'])
        canvas.create_text(left, height // 2 + self.cx(10), text=clamp_lines(self.font_hint, '  ·  '.join(facts),
                           room, 1)[0], anchor='w', font=self.font_hint, fill=COLORS['muted'])

    def card_facts(self, game):
        try:
            data = self.cards.metadata(game, self.owner.language)
        except (OSError, ValueError):
            return []
        release = str(data.get('release') or '')[:4]
        return [value for value in (release if release.isdigit() else '', str(data.get('developer') or '')) if value]

    def played_text(self, stamp):
        if not stamp:
            return self.tr('front_end_never_played')
        days = int((time.time() - stamp) // 86400)
        if days <= 0:
            return self.tr('front_end_played_today')
        if days == 1:
            return self.tr('front_end_played_yesterday')
        return self.tr('front_end_played_days', days=days)

    # ---- moving
    def step(self, dx, dy):
        if self.menu_items is not None:
            step = dy or dx
            if step:
                self.menu_index = (self.menu_index + step) % len(self.menu_items)
                while not self.menu_items[self.menu_index][2]:
                    self.menu_index = (self.menu_index + step) % len(self.menu_items)
                self.draw_wall()
            return
        if self.layout and self.games:
            self.go(move(self.focus_index, len(self.games), self.layout.columns, dx, dy))

    def page(self, direction):
        if self.layout and self.games:
            rows = max(1, self.wall.winfo_height() // self.layout.tile_height)
            self.go(min(len(self.games) - 1, max(0, self.focus_index + direction * rows * self.layout.columns)))

    def go(self, index):
        if not self.games:
            return
        index = min(max(index, 0), len(self.games) - 1)
        if index != self.focus_index:
            self.focus_index = index
            self.see(index)
            self.draw_wall()
            self.draw_details()

    def see(self, index):
        if not self.layout:
            return
        _, top = self.layout.origin(index)
        top -= round(self.layout.cover_height * (FOCUS_GROWTH - 1)) + self.px(8)
        bottom = top + self.layout.tile_height + self.px(8)
        view_top = self.wall.canvasy(0)
        view_height = self.wall.winfo_height()
        total = max(1, self.layout.height(len(self.games)))
        if top < view_top:
            self.wall.yview_moveto(max(0, top) / total)
        elif bottom > view_top + view_height:
            self.wall.yview_moveto(max(0, bottom - view_height) / total)
        self.request_covers()

    def switch(self, direction):
        if self.menu_items is None and self.shelves:
            self.select_shelf(self.shelf + direction)

    def letter(self, event):
        """A letter or digit jumps to the next game whose title starts with it."""
        char = event.char.casefold() if event.char and event.char.isprintable() and not event.char.isspace() else ''
        if not char or self.menu_items is not None or not self.games:
            return None
        count = len(self.games)
        for step in range(1, count + 1):
            index = (self.focus_index + step) % count
            if self.games[index].title.casefold().startswith(char):
                self.go(index)
                break
        return 'break'

    # ---- mouse
    def scroll_to(self, *args):
        self.wall.yview(*args)

    def scrolled(self, first, last):
        self.scrollbar.set(first, last)
        if self.layout:
            pending = getattr(self, '_scroll_pending', None)
            if pending is None:
                self._scroll_pending = self.after(15, self.after_scroll)

    def after_scroll(self):
        self._scroll_pending = None
        self.draw_wall()
        self.request_covers()

    def zoom_wheel(self, event):
        self.change_columns(1 if getattr(event, 'num', 0) == 5 or getattr(event, 'delta', 0) < 0 else -1)
        return 'break'

    def wheel(self, event):
        if self.menu_items is not None:
            return 'break'
        delta = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
        self.wall.yview_scroll(delta * max(40, (self.layout.tile_height // 3) if self.layout else 60), 'units')
        return 'break'

    def clicked(self, event):
        self.wall.focus_set()
        if self.menu_items is not None:
            hit = self.menu_hit(event.x, event.y)
            if hit is None:
                self.close_menu()
            else:
                self.menu_index = hit
                self.accept()
            return
        index = self.layout.at(self.wall.canvasx(event.x), self.wall.canvasy(event.y), len(self.games)) \
            if self.layout else None
        if index is None:
            return
        control, shift = bool(event.state & 0x4), bool(event.state & 0x1)
        if control or shift:
            if not self.selected and not shift:
                self.selected.add(game_key(self.games[self.focus_index]))
            if shift:
                low, high = sorted((self.anchor, index))
                self.selected.update(game_key(game) for game in self.games[low:high + 1])
            else:
                key = game_key(self.games[index])
                self.selected.symmetric_difference_update({key})
                self.anchor = index
        else:
            if self.selected:
                self.selected.clear()
                self.draw_wall()
            self.anchor = index
        self.go(index)
        self.draw_wall()
        self.draw_details()

    def chosen(self):
        """The games the menu acts on: the selection, else the focused game."""
        if self.selected:
            return [game for game in self.games if game_key(game) in self.selected]
        return [self.focused()] if self.games else []

    def select_all(self):
        if self.menu_items is None and self.games:
            self.selected = {game_key(game) for game in self.games}
            self.draw_wall()
            self.draw_details()

    def tab_clicked(self, event):
        box = getattr(self, 'restore_box', None)
        if box and box[0] <= event.x <= box[1]:
            self.toggle_tv()
            return
        for left, right, change in getattr(self, 'density_boxes', []):
            if left <= event.x <= right:
                self.change_columns(change)
                return
        for left, right, index in getattr(self, 'tab_boxes', []):
            if left <= event.x <= right:
                self.select_shelf(index)
                return

    def context_menu(self, event):
        """Right-click: on a chosen game the selection stays (the menu acts on all of them); elsewhere it is that game."""
        index = self.layout.at(self.wall.canvasx(event.x), self.wall.canvasy(event.y), len(self.games)) \
            if self.layout and self.menu_items is None else None
        if index is not None and game_key(self.games[index]) in self.selected:
            self.go(index)
        elif self.menu_items is None:
            self.clicked(event)
        if self.games:
            self.open_menu()

    # ---- actions
    def accept(self):
        if self.menu_items is not None:
            key, action, enabled = self.menu_items[self.menu_index]
            if enabled:
                self.close_menu()
                action()
            return
        self.play()

    def play(self):
        game = self.focused()
        if game:
            self.owner.launch_compiled_game(game)
            self.draw_details()

    def back(self):
        if self.menu_items is not None:
            self.close_menu()
        elif self.selected:
            self.selected.clear()
            self.draw_wall()
            self.draw_details()
        elif getattr(self.owner, 'front_end_fullscreen', False):
            self.owner.set_front_end_fullscreen(False)
        else:
            self.confirm_leave()

    def confirm_leave(self):
        """« Leave the front-end? » with Yes and No, in the same overlay as the menu: up/down or left/right choose,
        A / Enter / a click confirm, B / Esc answer No. Yes is chosen first, so B then A leaves."""
        self.close_menu(draw=False)
        self.menu_heading = self.tr('front_end_leave_question')
        self.menu_items = [('front_end_yes', self.leave, True), ('front_end_no', lambda: None, True)]
        self.menu_index = 0
        self.draw_wall()

    def leave(self):
        self.owner.toggle_front_end()

    def actions(self):
        """The actions of the chosen game, in the order of the menu: (key, action, enabled)."""
        game = self.focused()
        idle = not (self.owner.busy or self.owner.updating)
        order = ORDERS[(ORDERS.index(self.memory.order) + 1) % len(ORDERS)]
        games = self.chosen()
        if len(games) > 1:
            favorite = all(g.favorite for g in games)
            return [('front_end_find_covers', lambda: self.find_covers(games), not self.searching),
                    ('front_end_choose_covers', lambda: self.owner.choose_compiled_covers(games), True),
                    ('favorite_remove' if favorite else 'favorite_add', lambda: self.favorites(games, not favorite),
                     True),
                    ('reconvert', lambda: self.owner.reconvert_games(games), idle),
                    ('front_end_select_none', self.back, True),
                    ('front_end_tv_leave' if self.owner.front_end_fullscreen else 'front_end_tv', self.toggle_tv,
                     True),
                    ('front_end_leave', self.confirm_leave, True)]
        items = [('play', self.play, True),
                 ('card_choose_cover', lambda: self.owner.choose_compiled_covers([game]), True),
                 ('front_end_find_cover', lambda: self.find_covers([game]), not self.searching),
                 ('favorite_remove' if game.favorite else 'favorite_add', lambda: self.favorite(game), True),
                 # Network play will join here once it exists: host and join from the chosen game.
                 ('front_end_network_later', lambda: None, False),
                 ('front_end_next_order', lambda: self.set_order(order), True),
                 ('front_end_more_covers', lambda: self.change_columns(1), True),
                 ('front_end_fewer_covers', lambda: self.change_columns(-1), True),
                 ('front_end_tv_leave' if self.owner.front_end_fullscreen else 'front_end_tv', self.toggle_tv, True),
                 ('open_folder', lambda: open_local(Path(game.executable).parent), True),
                 ('reconvert', lambda: self.owner.reconvert_games([game]), idle),
                 ('front_end_leave', self.confirm_leave, True)]
        return items

    def open_menu(self):
        if not self.games:
            return
        if self.menu_items is not None:
            self.close_menu()
            return
        self.menu_items, self.menu_index = self.actions(), 0
        self.draw_wall()

    def close_menu(self, draw=True):
        self.menu_heading = None
        if self.menu_items is not None:
            self.menu_items = None
            if draw:
                self.draw_wall()

    def menu_geometry(self):
        canvas = self.wall
        line = self.font_tab.metrics('linespace') + self.px(12)
        labels = [self.menu_label(key) for key, _, _ in self.menu_items]
        heading = self.menu_heading or ''
        width = max(max(self.font_tab.measure(label) for label in labels), self.font_focus.measure(heading),
                    self.px(160)) + self.px(56)
        height = line * len(labels) + self.px(56)
        left = (canvas.winfo_width() - width) // 2
        top = canvas.canvasy(0) + max(self.px(12), (canvas.winfo_height() - height) // 2)
        return left, top, width, height, line, labels

    def menu_label(self, key):
        if key in ('front_end_find_covers', 'front_end_choose_covers'):
            return self.tr(key, count=len(self.selected))
        if key == 'front_end_next_order':
            following = ORDERS[(ORDERS.index(self.memory.order) + 1) % len(ORDERS)]
            return self.tr(key, order=self.tr('front_end_order_' + following))
        return self.tr(key)

    def draw_menu(self):
        canvas = self.wall
        left, top, width, height, line, labels = self.menu_geometry()
        canvas.create_rectangle(left + 6, top + 6, left + width + 6, top + height + 6, fill='#0f0f0f', outline='',
                                tags='tile')
        canvas.create_rectangle(left, top, left + width, top + height, fill=COLORS['panel'], outline=COLORS['gold'],
                                width=self.px(2), tags='tile')
        heading = self.menu_heading or (self.tr('front_end_selected', count=len(self.selected))
                                        if len(self.selected) > 1 else self.focused().title)
        title = clamp_lines(self.font_focus, heading, width - self.px(32), 1)[0]
        canvas.create_text(left + self.px(20), top + self.px(18), text=title, anchor='w', font=self.font_focus,
                           fill=COLORS['gold_hover'], tags='tile')
        y = top + self.px(40)
        for index, ((key, _, enabled), label) in enumerate(zip(self.menu_items, labels)):
            if index == self.menu_index:
                canvas.create_rectangle(left + self.px(8), y, left + width - self.px(8), y + line,
                                        fill=COLORS['selected'], outline='', tags='tile')
            canvas.create_text(left + self.px(20), y + line // 2, text=label, anchor='w', font=self.font_tab,
                               fill=(COLORS['gold_hover'] if index == self.menu_index else COLORS['text'])
                               if enabled else COLORS['disabled'], tags='tile')
            y += line

    def menu_hit(self, x, y):
        left, top, width, height, line, labels = self.menu_geometry()
        y = self.wall.canvasy(y)
        if not (left <= x <= left + width and top <= y <= top + height):
            return None
        index = int((y - top - self.px(40)) // line)
        return index if 0 <= index < len(self.menu_items) and self.menu_items[index][2] else None

    def favorite(self, game):
        self.favorites([game], not game.favorite)

    def favorites(self, games, value):
        for game in games:
            self.owner.compiled_inventory.set_favorite(game, value)
        self.draw_wall()

    def find_covers(self, games):
        """Search each game's box art online, one after the other off Tk (game_details.Cards.online_cover: the
        image becomes the game card's cover); the details line follows the count, the wall shows each new cover."""
        if self.searching or not games:
            return
        self.searching = (0, len(games), 0)
        def worker():
            found = 0
            for done, game in enumerate(games, 1):
                try:
                    payload = self.cards.online_cover(game)
                except Exception:
                    payload = None
                found += bool(payload)
                self.events.put(('found', (done, len(games), found), game_key(game), payload, None))
        threading.Thread(target=worker, daemon=True).start()
        self.draw_details()

    def cover_changed(self, game):
        """A new cover was given (the box-art window or a search): read it again."""
        key = game_key(game)
        self.thumbnails.pop(key, None)
        self.no_cover.discard(key)
        for name in [name for name in self.photos if name[0] == key]:
            del self.photos[name]
        with self.loader.condition:
            self.loader.done.discard(key)
        self.request_covers()

    def toggle_tv(self):
        self.owner.set_front_end_fullscreen(not self.owner.front_end_fullscreen)

    def take_focus(self):
        """After a switch to or from full screen, Windows may give the foreground to another window (the console that
        started the converter, say): the gamepad only drives the front-end while its window is in front, so it seemed
        lost (Arthur, 16 Nov 2026). Take the foreground and the keyboard back."""
        if not self.winfo_exists() or not self.winfo_viewable():
            return
        try:
            self.owner.app.focus_force()
            self.wall.focus_set()
        except tk.TclError:
            pass

    # ---- the gamepad and the loader's results
    def start_controller(self):
        if self.controller is not None:
            return
        try:
            from .player_gamepad import Controller
            self.controller = Controller()
        except (OSError, AttributeError):
            self.controller = None
            return
        self.pad = GridPad()
        self.draw_details()
        self.after(40, self.poll_controller)

    def close_controller(self):
        if self.controller is not None:
            self.controller.close()
            self.controller = None

    def poll_controller(self):
        if not self.winfo_exists() or self.controller is None:
            return
        # The next poll first: an error in one action must never stop the gamepad for the rest of the session.
        self.after(40, self.poll_controller)
        compiled = self.owner.compiled_view
        running = compiled is not None and compiled.game_process is not None and compiled.game_process.poll() is None
        focus = self.focus_displayof()
        enabled = (self.winfo_viewable() and not running and not self.owner.busy and focus is not None
                   and focus.winfo_toplevel() is self.owner.app and self.grab_current() is None)
        try:
            events = self.pad.update(self.controller.poll(), time.monotonic(), enabled)
        except OSError:
            self.close_controller()
            return
        for event in events:
            try:
                self.pad_event(event)
            except Exception:
                import traceback
                traceback.print_exc()

    def pad_event(self, event):
        if isinstance(event, tuple):
            self.step(event[1], event[2])
        elif event == 'a':
            self.accept()
        elif event == 'b':
            self.back()
        elif event in ('l2', 'r2'):
            # L2: fewer, larger covers; R2: more covers per row (this console only, remembered).
            self.change_columns(-1 if event == 'l2' else 1)
        elif event in ('start', 'y'):
            self.open_menu()
        elif event == 'x' and self.menu_items is None:
            # X: full screen and back (Arthur: on one of the four main buttons, like the actions on Y).
            self.toggle_tv()
        elif event in ('lb', 'rb'):
            self.switch(-1 if event == 'lb' else 1)
        elif event == 'back':
            self.set_order(ORDERS[(ORDERS.index(self.memory.order) + 1) % len(ORDERS)])

    def drain(self):
        if not self.winfo_exists():
            return
        changed = False
        try:
            while True:
                kind, generation, key, image, ratio = self.events.get_nowait()
                if kind == 'found':
                    game = next((g for g in self.games if game_key(g) == key), None)
                    if game is not None and image:
                        self.cover_changed(game)
                    done, total, found = generation
                    self.searching = None if done >= total else generation
                    self.search_result = generation if done >= total else None
                    self.draw_details()
                    continue
                if image is None:
                    self.no_cover.add(key)
                else:
                    self.thumbnails[key] = image
                    self.thumbnails.move_to_end(key)
                    while len(self.thumbnails) > KEEP_THUMBNAILS:
                        old, _ = self.thumbnails.popitem(last=False)
                        with self.loader.condition:
                            self.loader.done.discard(old)
                    if ratio:
                        self.ratios.setdefault(key.partition(':')[0], {})[key] = ratio
                changed = True
        except queue.Empty:
            pass
        if changed:
            self.update_aspect()
            self.draw_wall()
        self.after(30, self.drain)

    def update_aspect(self):
        """Once a dozen covers of the console are read, the slots take their shape (once per console)."""
        if not self.shelves:
            return
        system = self.shelves[self.shelf][0].id
        found = self.ratios.get(system, {})
        if system in self.aspects or len(found) < min(12, len(self.games)):
            return
        self.aspects[system] = cell_aspect(list(found.values()))
        self.relayout(reload=True)

    def destroy(self):
        self.loader.close()
        self.close_controller()
        super().destroy()


def clamp_lines(font, text, width, lines):
    """`text` broken into at most `lines` lines of `width` pixels, the last one cut with an ellipsis if needed."""
    words, result, current = str(text).split(), [], ''
    for word in words:
        candidate = f'{current} {word}' if current else word
        if font.measure(candidate) <= width or not current:
            current = candidate
        else:
            result.append(current)
            current = word
    if current or not result:
        result.append(current)
    if len(result) > lines:
        result = result[:lines]
        result[-1] += ' ' + ' '.join(words[len(' '.join(result).split()):])
    last = result[-1]
    if font.measure(last) > width:
        while last and font.measure(last + '…') > width:
            last = last[:-1]
        result[-1] = last.rstrip() + '…'
    return result
