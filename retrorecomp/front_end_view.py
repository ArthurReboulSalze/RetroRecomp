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
from .front_end import (DEFAULT_ASPECT, FOCUS_GROWTH, KEYBOARD, MAX_COLUMNS, MIN_COLUMNS, ORDERS, SCALE_TV,
                        SCALE_WINDOW, GridPad, Memory, carousel, cell_aspect, favorites, fit, game_key, grid,
                        keyboard_move, move, search, shelves, sort_games, step_columns, type_key)
from .platforms import open_local
from .systems import available_profiles

KEEP_THUMBNAILS = 360        # covers kept scaled in memory (about 40 MB at the default size)
KEEP_PHOTOS = 160            # Tk pictures kept for the tiles drawn or just scrolled out


class CoverLoader:
    """One worker thread: reads each wanted game's saved cover through the game cards and scales it to `box`. The view
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
                # Only what is already saved (Cards.cached_cover): nothing is searched or read from the executable,
                # so hundreds of games stay quick; a game without one shows its placeholder until the player asks
                # for the missing covers online.
                payload = self.cards.cached_cover(game)
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


FAVORITES, SEARCH = 'favorites', 'search'
# Menu entries with a short note shown under the menu while they are chosen (the labels stay short).
MENU_NOTES = {'front_end_find_cover': 'front_end_only_note', 'front_end_find_covers': 'front_end_only_note',
              'front_end_find_missing': 'front_end_only_note'}


class Shelf:
    """An entry of the strip that is not a console: the favourites and the search, both over every console. It gives
    the strip what a console profile gives it (an id and a name)."""
    def __init__(self, id, name):
        self.id, self.name = id, name


def rounded(canvas, x0, y0, x1, y1, radius, **options):
    """A rectangle with round corners (one smoothed polygon)."""
    r = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    points = (x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
              x0, y1 - r, x0, y0 + r, x0, y0)
    return canvas.create_polygon(points, smooth=True, **options)


def star_points(x, y, radius):
    import math
    points = []
    for step in range(10):
        angle = math.radians(-90 + step * 36)
        r = radius if step % 2 == 0 else radius * 0.45
        points += [x + r * math.cos(angle), y + r * math.sin(angle)]
    return points


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
        self.aspects = {}                 # shelf id -> the shape of its cover slots
        self.ratio_of = {}                # game key -> width / height of its cover
        self.all_games, self.console_names = [], {}
        # The search over every console: its entry in the strip exists while `search_open`; `editing` while the
        # on-screen keyboard is up. `return_shelf`: the console to go back to from the search or the favourites.
        self.query, self.search_open, self.editing, self.kb = '', False, False, (0, 0)
        self.return_shelf = ''
        self.strip_offset, self.strip_timer, self.hover_tool = 0.0, None, None
        self.thumbnails = OrderedDict()   # key -> PIL image at the focused size
        self.no_cover = set()
        self.photos = OrderedDict()       # (key, width, height) -> PhotoImage
        self.layout = None
        self.menu_items, self.menu_index = None, 0
        self.menu_heading = None   # a question in place of the game's title (« Leave the front-end? »)
        # Games chosen with Ctrl / Shift + click (or Ctrl+A) on the console shown: the menu then acts on all of them.
        self.selected, self.anchor = set(), 0
        self.searching = None      # (done, total, found) while covers are searched online
        self.search_result = None  # (total, total, found) once the last search of covers ended
        self.controller, self.pad = None, GridPad()
        self.jobs = {}                 # the view's own `after` jobs, cancelled when it is destroyed
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
        self.tabs.bind('<Motion>', self.tab_motion)
        self.tabs.bind('<Leave>', self.tab_motion)
        from .tooltips import Tooltip
        self.hints = [Tooltip(self.tabs, text, item=tag) for tag, text in (
            ('tool_favorites', lambda: self.tr('front_end_tip_favorites')),
            ('tool_search', lambda: self.tr('front_end_tip_search')),
            ('tool_fewer', lambda: self.tr('front_end_fewer_covers')),
            ('tool_more', lambda: self.tr('front_end_more_covers')),
            ('tool_count', lambda: self.tr('front_end_per_row', count=self.layout.columns if self.layout else 0)),
            ('tool_screen', lambda: self.tr('front_end_tv_leave' if self.owner.front_end_fullscreen
                                            else 'front_end_tv')))]
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
                                 ('<Control-f>', self.open_search), ('<Control-F>', self.open_search),
                                 ('<F3>', self.open_search),
                                 ('<Shift-F10>', self.open_menu), ('<F11>', self.toggle_tv)):
            self.wall.bind(sequence, lambda event, action=action: self.key(event, action))
        self.wall.bind('<Key>', self.letter)
        self.later('drain', 30, self.drain)

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
        self.font_chosen = tkfont.Font(root=self, family=family, size=self.cx(12), weight='bold')
        self.font_count = tkfont.Font(root=self, family=family, size=self.cx(8))
        self.font_detail = tkfont.Font(root=self, family=family, size=self.cx(11), weight='bold')
        self.font_hint = tkfont.Font(root=self, family=family, size=self.cx(9))
        self.font_glyph = tkfont.Font(root=self, family=family, size=self.cx(8), weight='bold')

    def wanted_scale(self):
        return SCALE_TV if getattr(self.owner, 'front_end_fullscreen', False) else SCALE_WINDOW

    def relocalize(self):
        """The interface language changed: names of the favourites and the search, fonts, every text drawn."""
        current = self.shelf_id()
        if self.shelves:
            self.build_shelves()
            self.shelf = self.index_of(current)
        self.apply_scale()

    def apply_scale(self):
        self.scale = self.wanted_scale()
        self.fonts()
        self.tabs.configure(height=self.cx(38))
        self.details.configure(height=self.cx(44))
        self.photos.clear()
        self.relayout(reload=True)
        self.draw_tabs()

    # ---- data
    def build_shelves(self):
        """The strip's entries: the search (while it is open) and the favourites, both over every console, then the
        consoles that have games."""
        consoles = shelves(self.owner.compiled_inventory.snapshot(), self.profiles)
        self.all_games = [game for _, games in consoles for game in games]
        self.console_names = {profile.id: profile.name for profile in self.profiles}
        virtual = [(Shelf(FAVORITES, self.tr('front_end_favorites')), favorites(self.all_games))]
        if self.search_open:
            virtual.insert(0, (Shelf(SEARCH, self.tr('front_end_search')), search(self.all_games, self.query)))
        self.shelves = virtual + consoles

    def shelf_id(self):
        return self.shelves[self.shelf][0].id if self.shelves else ''

    def index_of(self, shelf_id):
        """The strip index of a shelf id; the first console when it is not there (the favourites when there is
        no console at all)."""
        ids = [entry.id for entry, _ in self.shelves]
        if shelf_id in ids:
            return ids.index(shelf_id)
        return next((i for i, name in enumerate(ids) if name not in (FAVORITES, SEARCH)), 0)

    def show(self):
        """Read the inventory again (the view may have been away while games were converted) and draw."""
        current = self.shelf_id() or self.memory.console
        self.build_shelves()
        self.select_shelf(self.index_of(current), keep_focus=True, slide=False)
        self.start_controller()
        self.wall.focus_set()

    def select_shelf(self, index, keep_focus=False, slide=True):
        if not self.shelves:
            self.games = []
            self.relayout()
            self.draw_tabs()
            return
        index %= len(self.shelves)
        previous = self.games[self.focus_index] if keep_focus and self.games else None
        if slide and index != self.shelf:
            # The band slides under the centre: the new entry comes from the side it was on.
            count = len(self.shelves)
            forward = (index - self.shelf) % count
            self.slide(1 if forward <= count - forward else -1)
        self.shelf = index
        entry, games = self.shelves[index]
        if entry.id != SEARCH:
            self.memory.console = entry.id
            self.memory.save()
        self.selected.clear()
        self.games = sort_games(games, self.memory.order, self.memory.played)
        keys = [game_key(game) for game in self.games]
        self.focus_index = keys.index(game_key(previous)) if previous and game_key(previous) in keys else 0
        self.close_menu(draw=False)
        self.wall.yview_moveto(0)
        self.relayout(reload=True)
        self.draw_tabs()

    def slide(self, direction):
        self.strip_offset = direction * self.cx(110)
        if self.strip_timer is None:
            self.strip_timer = self.later('slide', 16, self.slide_step)

    def slide_step(self):
        self.strip_timer = None
        if not self.winfo_exists():
            return
        self.strip_offset *= 0.55
        if abs(self.strip_offset) < 1.5:
            self.strip_offset = 0.0
        else:
            self.strip_timer = self.later('slide', 16, self.slide_step)
        self.draw_tabs()

    # ---- the favourites and the search, over every console
    def toggle_favorites(self):
        """The star: the favourites of every console, and back to the console it was opened from."""
        if self.editing:
            self.finish_editing()
        if self.shelf_id() == FAVORITES:
            self.select_shelf(self.index_of(self.return_shelf))
        else:
            if self.shelf_id() != SEARCH:
                self.return_shelf = self.shelf_id()
            self.select_shelf(self.index_of(FAVORITES))

    def open_search(self):
        """The search of a title over every console: its entry joins the strip and the keyboard comes up."""
        self.close_menu(draw=False)
        if not self.search_open:
            if self.shelf_id() != FAVORITES:
                self.return_shelf = self.shelf_id()
            self.search_open = True
        self.editing, self.kb = True, (0, 0)
        self.refresh_search()

    def refresh_search(self):
        self.build_shelves()
        self.aspects.pop(SEARCH, None)
        self.select_shelf(self.index_of(SEARCH), slide=False)

    def finish_editing(self):
        """The keyboard goes; the results stay (an empty search closes)."""
        self.editing = False
        if not self.query.strip():
            self.close_search()
        else:
            self.draw_tabs()
            self.draw_wall()
            self.draw_details()

    def close_search(self):
        self.editing, self.search_open, self.query = False, False, ''
        self.build_shelves()
        self.select_shelf(self.index_of(self.return_shelf), slide=False)

    def type(self, key):
        """One key of the search: a character, 'space', 'delete' or 'done'."""
        if key == 'done':
            self.finish_editing()
            return
        query = type_key(self.query, key)
        if query != self.query:
            self.query = query
            self.refresh_search()

    def key(self, event, action):
        """A bound key: while the search is typed it goes to the search (F11 still switches the screen)."""
        if self.editing and event.keysym != 'F11':
            self.edit_key(event)
        else:
            action()
        return 'break'

    def edit_key(self, event):
        symbol = event.keysym
        if symbol in ('Return', 'KP_Enter'):
            self.finish_editing()
        elif symbol == 'Escape':
            self.close_search()
        elif symbol == 'BackSpace':
            self.type('delete')
        elif symbol in ('Left', 'Right', 'Up', 'Down'):
            dx = {'Left': -1, 'Right': 1}.get(symbol, 0)
            dy = {'Up': -1, 'Down': 1}.get(symbol, 0)
            self.kb = keyboard_move(*self.kb, dx, dy)
            self.draw_wall()
        elif event.char and event.char.isprintable():
            self.type(event.char)

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
        shelf = self.shelf_id()
        aspect = self.aspects.get(shelf) or DEFAULT_ASPECT
        line = self.font_title.metrics('linespace')
        layout = grid(width, aspect, self.scale, line, self.memory.columns.get(shelf))
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
        system = self.shelf_id()
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
            shelf = self.shelf_id()
            message = (self.tr('front_end_empty') if not self.all_games
                       else self.tr('front_end_favorites_empty') if shelf == FAVORITES
                       else self.tr('front_end_search_hint') if not self.query.strip()
                       else self.tr('front_end_search_none', query=self.query.strip()))
            canvas.create_text(canvas.winfo_width() // 2, canvas.canvasy(0) + canvas.winfo_height() // (4 if self.editing
                               else 2), text=message, fill=COLORS['muted'], font=self.font_tab,
                               width=canvas.winfo_width() - 80, justify='center', tags='tile')
        focused = None
        for index in self.visible_range():
            if index == self.focus_index:
                focused = index
                continue
            self.draw_tile(index, False)
        if focused is not None:
            self.draw_tile(focused, not self.editing)
        if self.editing:
            self.draw_keyboard()
        if self.menu_items is not None:
            self.draw_menu()

    def keyboard_geometry(self):
        canvas = self.wall
        cell_w, cell_h, pad = self.px(46), self.px(40), self.px(14)
        width = cell_w * len(KEYBOARD[0]) + pad * 2
        height = cell_h * len(KEYBOARD) + pad * 2 + self.px(34)
        left = (canvas.winfo_width() - width) // 2
        top = canvas.canvasy(0) + canvas.winfo_height() - height - self.px(16)
        return left, top, width, height, cell_w, cell_h, pad

    def draw_keyboard(self):
        """The search's keyboard, at the bottom of the wall: the gamepad moves on it, the mouse clicks it, and a
        real keyboard just types."""
        canvas = self.wall
        left, top, width, height, cell_w, cell_h, pad = self.keyboard_geometry()
        canvas.create_rectangle(left + 6, top + 6, left + width + 6, top + height + 6, fill='#0f0f0f', outline='',
                                tags='tile')
        canvas.create_rectangle(left, top, left + width, top + height, fill=COLORS['panel'], outline=COLORS['gold'],
                                width=self.px(2), tags='tile')
        text = self.query or self.tr('front_end_search_hint')
        shown = clamp_lines(self.font_tab, text, width - pad * 2 - self.px(90), 1)[0]
        canvas.create_text(left + pad, top + pad + self.px(8), text=shown, anchor='w', font=self.font_tab,
                           fill=COLORS['gold_hover'] if self.query else COLORS['disabled'], tags='tile')
        if self.query:
            caret = left + pad + self.font_tab.measure(shown) + self.px(3)
            canvas.create_line(caret, top + pad - self.px(2), caret, top + pad + self.px(18), fill=COLORS['gold'],
                               width=self.px(2), tags='tile')
        canvas.create_text(left + width - pad, top + pad + self.px(8), anchor='e', font=self.font_title,
                           text=self.tr('games_count', count=len(self.games)), fill=COLORS['muted'], tags='tile')
        self.kb_boxes = []
        chosen = KEYBOARD[self.kb[0]][self.kb[1]]
        y = top + pad + self.px(34)
        for row, keys in enumerate(KEYBOARD):
            column = 0
            while column < len(keys):
                key = keys[column]
                span = 1
                while column + span < len(keys) and keys[column + span] == key:
                    span += 1
                x0, x1 = left + pad + column * cell_w + 2, left + pad + (column + span) * cell_w - 2
                active = row == self.kb[0] and key == chosen
                rounded(canvas, x0, y + 2, x1, y + cell_h - 2, self.px(7), tags='tile',
                        fill=COLORS['selected'] if active else COLORS['button'],
                        outline=COLORS['gold'] if active else COLORS['subtle_border'])
                color = COLORS['gold_hover'] if active else COLORS['text']
                cx, cy, unit = (x0 + x1) // 2, y + cell_h // 2, self.px(5)
                if key == 'space':
                    canvas.create_line(cx - unit * 3, cy - unit // 2, cx - unit * 3, cy + unit, cx + unit * 3, cy + unit,
                                       cx + unit * 3, cy - unit // 2, fill=color, width=self.px(2), tags='tile')
                elif key == 'delete':
                    canvas.create_line(cx + unit * 2, cy, cx - unit * 2, cy, fill=color, width=self.px(2), tags='tile')
                    canvas.create_line(cx - unit, cy - unit, cx - unit * 2, cy, cx - unit, cy + unit, fill=color,
                                       width=self.px(2), tags='tile')
                else:
                    canvas.create_text(cx, cy, text='OK' if key == 'done' else key, font=self.font_tab_bold
                                       if key == 'done' else self.font_tab, fill=color, tags='tile')
                self.kb_boxes.append((x0, y, x1, y + cell_h, row, column))
                column += span
            y += cell_h

    def keyboard_hit(self, x, y):
        y = self.wall.canvasy(y)
        for x0, y0, x1, y1, row, column in getattr(self, 'kb_boxes', []):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return row, column
        return None

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
        system = self.console_names.get(game.system, '')
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

    def entry_width(self, index, chosen):
        entry, games = self.shelves[index]
        font = self.font_chosen if chosen else self.font_strip
        icon = self.cx(20) if entry.id in (FAVORITES, SEARCH) else 0
        caret = self.cx(6) if entry.id == SEARCH and self.editing else 0
        return icon + font.measure(self.entry_label(entry)) + caret + self.font_count.measure(f'  {len(games)}')

    def entry_label(self, entry):
        return (self.query or entry.name) if entry.id == SEARCH else entry.name

    def draw_entry(self, x, middle, index, distance):
        """One entry of the strip from `x`: its picture (favourites, search), its name and its number of games."""
        canvas = self.tabs
        entry, games = self.shelves[index]
        chosen = distance == 0
        font = self.font_chosen if chosen else self.font_strip
        color = (COLORS['gold_hover'] if chosen else COLORS['muted'] if distance == 1 else '#8f8f8f' if distance == 2
                 else COLORS['disabled'])
        if entry.id == FAVORITES:
            canvas.create_polygon(star_points(x + self.cx(7), middle, self.cx(7)), fill=color, outline='')
            x += self.cx(20)
        elif entry.id == SEARCH:
            self.draw_loupe(x + self.cx(7), middle, color)
            x += self.cx(20)
        label = self.entry_label(entry)
        canvas.create_text(x, middle, text=label, anchor='w', font=font, fill=color)
        x += font.measure(label)
        if entry.id == SEARCH and self.editing and chosen:
            canvas.create_line(x + self.cx(3), middle - self.cx(8), x + self.cx(3), middle + self.cx(8),
                               fill=COLORS['gold'], width=self.cx(2))
            x += self.cx(6)
        canvas.create_text(x, middle + self.cx(1), text=f'  {len(games)}', anchor='w', font=self.font_count,
                           fill=COLORS['gold'] if chosen else COLORS['disabled'])

    def draw_loupe(self, x, y, color, canvas=None, tags=()):
        canvas = canvas or self.tabs
        r = self.cx(5)
        canvas.create_oval(x - r - 1, y - r - 2, x + r - 1, y + r - 2, outline=color, width=self.cx(2), tags=tags)
        canvas.create_line(x + r - 2, y + r - 3, x + r + self.cx(3), y + r + self.cx(2), fill=color, width=self.cx(2),
                           tags=tags)

    def draw_tabs(self):
        """The strip: the chosen entry stays in the middle and the band of consoles slides under it (LB / RB, a
        click on a name); right of it the favourites, the search, the covers per row and the full screen."""
        canvas = self.tabs
        canvas.delete('all')
        width, height = canvas.winfo_width(), int(canvas['height'])
        middle = height // 2 - self.cx(1)
        tools_left = self.draw_tools(width, middle)
        self.tab_boxes = []
        canvas.create_line(0, height - 1, width, height - 1, fill=COLORS['subtle_border'])
        if not self.shelves:
            return
        glyph = self.cx(30)
        zone_left, zone_right = glyph + self.cx(10), tools_left - glyph - self.cx(18)
        # The middle of the screen, not of the room left by the buttons: the chosen entry sits under the eye.
        centre = min(width // 2, zone_right - self.entry_width(self.shelf, True) // 2) + round(self.strip_offset)
        spacing = self.cx(30)
        size = self.entry_width(self.shelf, True)
        x = centre - size // 2
        self.draw_entry(x, middle, self.shelf, 0)
        canvas.create_rectangle(x, height - self.cx(5), x + size, height - self.cx(2), fill=COLORS['gold'], outline='')
        self.tab_boxes.append((x, x + size, self.shelf))
        left, right = carousel(len(self.shelves), self.shelf)
        edge = x + size + spacing
        for distance, index in enumerate(right, 1):
            size = self.entry_width(index, False)
            if edge + size > zone_right:
                break
            self.draw_entry(edge, middle, index, distance)
            self.tab_boxes.append((edge, edge + size, index))
            edge += size + spacing
        edge = x - spacing
        for distance, index in enumerate(left, 1):
            size = self.entry_width(index, False)
            if edge - size < zone_left:
                break
            self.draw_entry(edge - size, middle, index, distance)
            self.tab_boxes.append((edge - size, edge, index))
            edge -= size + spacing
        self.pill(canvas, 0, middle, 'LB')
        self.pill(canvas, zone_right + self.cx(8), middle, 'RB')

    def draw_tools(self, right, middle):
        """Right of the strip, one family of round buttons: favourites, search, covers per row (minus, the number,
        plus) and full screen. Returns where they start."""
        canvas = self.tabs
        height, gap, radius = self.cx(26), self.cx(7), self.cx(9)
        top, bottom = middle - height // 2, middle + height - height // 2
        self.tool_boxes = []

        def chip(x0, x1, name, active=False):
            hover = self.hover_tool == name
            rounded(canvas, x0, top, x1, bottom, radius, tags=('tool_' + name,),
                    fill=COLORS['selected'] if active else COLORS['hover'] if hover else COLORS['button'],
                    outline=COLORS['gold'] if active or hover else COLORS['subtle_border'])
            self.tool_boxes.append((x0, x1, name))
            return COLORS['gold_hover'] if active else COLORS['text']

        icon_w = self.cx(34)
        full = getattr(self.owner, 'front_end_fullscreen', False)
        # Full screen: four corners pointing out; back to the window: pointing in.
        x1 = right
        x0 = x1 - icon_w
        color = chip(x0, x1, 'screen')
        cx, cy, far, arm, line = (x0 + x1) // 2, middle, self.cx(6), self.cx(4), self.cx(2)
        for sx in (-1, 1):
            for sy in (-1, 1):
                if full:
                    near = self.cx(2)
                    points = (cx + sx * near, cy + sy * (near + arm), cx + sx * near, cy + sy * near,
                              cx + sx * (near + arm), cy + sy * near)
                else:
                    points = (cx + sx * far, cy + sy * (far - arm), cx + sx * far, cy + sy * far,
                              cx + sx * (far - arm), cy + sy * far)
                canvas.create_line(*points, fill=color, width=line, tags=('tool_screen',))
        # Covers per row: one pill, minus | a small grid and the number | plus.
        x1 = x0 - gap
        side = self.cx(26)
        columns = self.layout.columns if self.layout else 0
        number = str(columns)
        inner = self.cx(18) + self.font_strip_bold.measure(number) + self.cx(10)
        x0 = x1 - side * 2 - inner
        hover = self.hover_tool in ('fewer', 'more', 'count')
        rounded(canvas, x0, top, x1, bottom, radius, fill=COLORS['button'], tags=('tool_count',),
                outline=COLORS['gold'] if hover else COLORS['subtle_border'])
        for name, a, b in (('fewer', x0, x0 + side), ('more', x1 - side, x1)):
            if self.hover_tool == name:
                rounded(canvas, a + 2, top + 2, b - 2, bottom - 2, radius - 2, fill=COLORS['hover'], outline='',
                        tags=('tool_' + name,))
            enabled = columns > MIN_COLUMNS if name == 'fewer' else columns < MAX_COLUMNS
            color = COLORS['text'] if enabled else COLORS['disabled']
            centre, half = (a + b) // 2, self.cx(4)
            canvas.create_line(centre - half, middle, centre + half + 1, middle, fill=color, width=self.cx(2),
                               tags=('tool_' + name,))
            if name == 'more':
                canvas.create_line(centre, middle - half, centre, middle + half + 1, fill=color, width=self.cx(2),
                                   tags=('tool_' + name,))
            # A clear zone over the whole side, so the hint and the click do not depend on hitting the thin sign.
            canvas.create_rectangle(a, top, b, bottom, fill='', outline='', tags=('tool_' + name,))
            self.tool_boxes.append((a, b, name))
        gx, cell = x0 + side + self.cx(3), self.cx(4)
        for row in (0, 1):
            for column in (0, 1):
                canvas.create_rectangle(gx + column * (cell + 2), middle - cell - 1 + row * (cell + 2),
                                        gx + column * (cell + 2) + cell, middle - 1 + row * (cell + 2),
                                        fill=COLORS['gold'], outline='', tags=('tool_count',))
        canvas.create_text(gx + self.cx(16), middle, text=number, anchor='w', font=self.font_strip_bold,
                           fill=COLORS['text'], tags=('tool_count',))
        # The search, then the favourites.
        x1 = x0 - gap
        x0 = x1 - icon_w
        color = chip(x0, x1, 'search', self.search_open)
        self.draw_loupe((x0 + x1) // 2, middle + 1, color, tags=('tool_search',))
        x1 = x0 - gap
        x0 = x1 - icon_w
        active = self.shelf_id() == FAVORITES
        color = chip(x0, x1, 'favorites', active)
        canvas.create_polygon(star_points((x0 + x1) // 2, middle, self.cx(8)), tags=('tool_favorites',),
                              fill=COLORS['gold'] if active else '', outline=color, width=self.cx(1.5))
        return x0 - self.cx(4)

    def tool_at(self, x):
        return next((name for x0, x1, name in getattr(self, 'tool_boxes', []) if x0 <= x <= x1), None)

    def tab_motion(self, event):
        """The round button under the pointer lights up; a hand over what can be clicked."""
        inside = str(event.type) == 'Motion' or getattr(event.type, 'name', '') == 'Motion'
        tool = self.tool_at(event.x) if inside else None
        entry = inside and any(x0 <= event.x <= x1 for x0, x1, _ in getattr(self, 'tab_boxes', []))
        self.tabs.configure(cursor='hand2' if tool or entry else '')
        if tool != self.hover_tool:
            self.hover_tool = tool
            self.draw_tabs()

    def pill(self, canvas, x, y, text, color=None):
        """A gamepad button drawn as a small rounded label (letters only: every interface font has them)."""
        font = self.font_glyph
        width = self.cx(26) if text in ('MENU', 'VIEW') else max(font.measure(text) + self.cx(12), self.cx(22))
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
        elif text == 'VIEW':
            # The Back / View button: two small frames.
            mid, unit = x + width // 2, self.cx(3)
            canvas.create_rectangle(mid - unit - 2, y - unit, mid + unit - 2, y + unit + 1, outline=COLORS['text'])
            canvas.create_rectangle(mid - unit + 2, y - unit - 2, mid + unit + 2, y + unit - 1, outline=COLORS['text'],
                                    fill=color)
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
        if self.editing and pads:
            hints = [(('A',), 'front_end_kb_type'), (('B',), 'front_end_cancel'), (('X',), 'front_end_kb_delete'),
                     (('Y',), 'front_end_key_space'), (('MENU',), 'front_end_kb_done')]
        elif self.editing:
            hints = [((self.tr('front_end_key_enter'),), 'front_end_kb_done'),
                     ((self.tr('front_end_key_escape'),), 'front_end_cancel')]
        elif pads:
            hints = [(('A',), 'play'), (('B',), 'front_end_back'), (('X',), screen), (('Y',), 'front_end_actions'),
                     (('L2', 'R2'), 'front_end_density'), (('VIEW',), 'front_end_search')]
        else:
            hints = [((self.tr('front_end_key_enter'),), 'play'), ((self.tr('front_end_key_escape'),), 'front_end_back'),
                     (('F11',), screen), ((self.tr('front_end_key_space'),), 'front_end_actions'),
                     (('-', '+'), 'front_end_density'), (('Ctrl+F',), 'front_end_search')]
        colors = {'A': '#3c7d4a', 'B': '#8a3b3b', 'X': '#365f8f', 'Y': '#8a7a2e'}
        x = width - self.cx(14)
        for glyphs, key in reversed(hints):
            label = self.tr(key)
            x -= self.font_hint.measure(label)
            canvas.create_text(x, height // 2, text=label, anchor='w', font=self.font_hint, fill=COLORS['muted'])
            x -= self.cx(6)
            for glyph in reversed(glyphs):
                size = (self.cx(26) if glyph in ('MENU', 'VIEW')
                        else max(self.font_glyph.measure(glyph) + self.cx(12), self.cx(22)))
                self.pill(canvas, x - size, height // 2, glyph, colors.get(glyph))
                x -= size + self.cx(3)
            x -= self.cx(13)
        hints_left = x
        if not game:
            return
        order = self.tr('front_end_order_' + self.memory.order)
        played = self.memory.played.get(game_key(game))
        facts = [self.console_names.get(game.system, ''), self.played_text(played)]
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
        if self.editing:
            self.kb = keyboard_move(*self.kb, dx, dy)
            self.draw_wall()
            return
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
        if self.menu_items is None and self.shelves and not self.editing:
            self.select_shelf(self.shelf + direction)

    def letter(self, event):
        """A letter or digit jumps to the next game whose title starts with it (it types while the search is)."""
        if self.editing:
            self.edit_key(event)
            return 'break'
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
                self._scroll_pending = self.later('scroll', 15, self.after_scroll)

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
        if self.editing:
            hit = self.keyboard_hit(event.x, event.y)
            if hit is not None:
                self.kb = hit
                self.type(KEYBOARD[hit[0]][hit[1]])
                if self.editing:
                    self.draw_wall()
                return
            self.finish_editing()
            if self.shelf_id() != SEARCH:
                return
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
        tool = self.tool_at(event.x)
        if tool == 'screen':
            self.toggle_tv()
        elif tool == 'favorites':
            self.toggle_favorites()
        elif tool == 'search':
            self.finish_editing() if self.editing else self.open_search()
        elif tool in ('fewer', 'more'):
            self.change_columns(-1 if tool == 'fewer' else 1)
        elif not self.editing:
            for left, right, index in getattr(self, 'tab_boxes', []):
                if left <= event.x <= right:
                    self.select_shelf(index)
                    break
        self.wall.focus_set()

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
        elif self.search_open and (self.editing or self.shelf_id() == SEARCH):
            self.close_search()        # Back leaves the search first, then asks to leave the front-end
        else:
            # Full screen or not, Back asks to leave the front-end (Arthur, 16 Nov 2026); X, F11 and the corner button
            # are the ways back to the window.
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
        # The shelf's games still without a cover once their saved image was looked for: searched online on demand,
        # for the front-end only (the executables keep their icon).
        missing = [g for g in self.games if game_key(g) in self.no_cover]
        find_missing = ('front_end_find_missing', lambda: self.find_covers(missing), bool(missing) and not self.searching)
        if len(games) > 1:
            favorite = all(g.favorite for g in games)
            return [('front_end_find_covers', lambda: self.find_covers(games), not self.searching), find_missing,
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
                 ('front_end_find_cover', lambda: self.find_covers([game]), not self.searching), find_missing,
                 ('favorite_remove' if game.favorite else 'favorite_add', lambda: self.favorite(game), True),
                 # Network play will join here once it exists: host and join from the chosen game.
                 ('front_end_network_later', lambda: None, False),
                 ('front_end_search_open', self.open_search, True),
                 ('front_end_next_order', lambda: self.set_order(order), True),
                 ('front_end_more_covers', lambda: self.change_columns(1), True),
                 ('front_end_fewer_covers', lambda: self.change_columns(-1), True),
                 ('front_end_tv_leave' if self.owner.front_end_fullscreen else 'front_end_tv', self.toggle_tv, True),
                 ('open_folder', lambda: open_local(Path(game.executable).parent), True),
                 ('reconvert', lambda: self.owner.reconvert_games([game]), idle),
                 ('front_end_leave', self.confirm_leave, True)]
        return items

    def open_menu(self):
        if not self.games or self.editing:
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
        notes = [MENU_NOTES[key] for key, _, _ in self.menu_items if key in MENU_NOTES]
        if notes:
            # The room of the longest note, wrapped to the menu's width, kept still while the choice moves.
            lines = max(len(clamp_lines(self.font_title, self.tr(note), width - self.px(40), 3)) for note in notes)
            height += lines * self.font_title.metrics('linespace') + self.px(14)
        left = (canvas.winfo_width() - width) // 2
        top = canvas.canvasy(0) + max(self.px(12), (canvas.winfo_height() - height) // 2)
        return left, top, width, height, line, labels

    def menu_label(self, key):
        if key in ('front_end_find_covers', 'front_end_choose_covers'):
            return self.tr(key, count=len(self.selected))
        if key == 'front_end_find_missing':
            return self.tr(key, count=sum(game_key(g) in self.no_cover for g in self.games))
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
        note = MENU_NOTES.get(self.menu_items[self.menu_index][0])
        if note:
            canvas.create_text(left + self.px(20), y + self.px(8), anchor='nw', font=self.font_title,
                               text='\n'.join(clamp_lines(self.font_title, self.tr(note), width - self.px(40), 3)),
                               fill=COLORS['muted'], tags='tile')

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
        # The favourites' entry follows: its number everywhere, its games when it is the one shown.
        current, focus = self.shelf_id(), self.focus_index
        self.build_shelves()
        if current == FAVORITES:
            self.select_shelf(self.index_of(FAVORITES), slide=False)
            self.go(min(focus, max(0, len(self.games) - 1)))
        else:
            self.shelf = self.index_of(current)
        self.draw_tabs()
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
        self.later('pad', 40, self.poll_controller)

    def close_controller(self):
        if self.controller is not None:
            self.controller.close()
            self.controller = None

    def poll_controller(self):
        if not self.winfo_exists() or self.controller is None:
            return
        # The next poll first: an error in one action must never stop the gamepad for the rest of the session.
        self.later('pad', 40, self.poll_controller)
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
        if self.editing and not isinstance(event, tuple):
            # The search's keyboard: A types the key, X deletes, Y is a space, Start (or Back) keeps the results,
            # B gives the search up.
            if event == 'a':
                self.type(KEYBOARD[self.kb[0]][self.kb[1]])
                if self.editing:
                    self.draw_wall()
            elif event in ('x', 'y'):
                self.type('delete' if event == 'x' else 'space')
            elif event in ('start', 'back'):
                self.finish_editing()
            elif event == 'b':
                self.close_search()
            return
        if isinstance(event, tuple):
            self.step(event[1], event[2])
        elif event == 'a':
            self.accept()
        elif event == 'b':
            self.back()
        elif event in ('l2', 'r2'):
            # L2: more covers per row; R2: fewer, larger covers (this console only, remembered; Arthur, 16 Nov 2026).
            self.change_columns(1 if event == 'l2' else -1)
        elif event in ('start', 'y'):
            self.open_menu()
        elif event == 'x' and self.menu_items is None:
            # X: full screen and back (Arthur: on one of the four main buttons, like the actions on Y).
            self.toggle_tv()
        elif event in ('lb', 'rb'):
            self.switch(-1 if event == 'lb' else 1)
        elif event == 'back' and self.menu_items is None:
            self.open_search()         # Back / View: the search; the order is in the actions

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
                        self.ratio_of[key] = ratio
                changed = True
        except queue.Empty:
            pass
        if changed:
            self.update_aspect()
            self.draw_wall()
        self.later('drain', 30, self.drain)

    def update_aspect(self):
        """Once a dozen covers of the shelf are read, its slots take their shape (once per console; again for
        each new search)."""
        shelf = self.shelf_id()
        if not shelf or shelf in self.aspects:
            return
        found = [self.ratio_of[key] for key in map(game_key, self.games) if key in self.ratio_of]
        if not found or len(found) < min(12, len(self.games)):
            return
        self.aspects[shelf] = cell_aspect(found)
        self.relayout(reload=True)

    def later(self, name, delay, callback):
        """`after`, remembered by name, so that destroying the view cancels what is still waiting."""
        job = self.after(delay, callback)
        self.jobs[name] = job
        return job

    def destroy(self):
        self.loader.close()
        self.close_controller()
        for job in getattr(self, 'jobs', {}).values():
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
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
