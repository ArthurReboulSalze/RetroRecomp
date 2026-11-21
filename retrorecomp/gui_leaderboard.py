"""The leaderboard, the achievement card and the closing card."""
from __future__ import annotations

import threading
import time
import tkinter as tk
from tkinter import ttk

from . import online
from .paths import ASSETS, APP_NAME
from .branding import COLORS
from .dialogs import center_dialog
from .gui_common import SENDING_AVAILABLE
from .gui_drawing import (
    HOVER_EFFECTS, PIN_SIZE, TROPHY, badges_width, compact_number, draw_badges, draw_pin, draw_styled_text, elide,
    frame_side, hover_effect_picture, name_colours, _font, _podium_picture, _rounded, _scaled_photo, _tint,
)
from .ui_fonts import ui_scale
from . import tk_later

# Design « Marches » (Arthur's pick, 20 Nov 2026): the Multiplayer window's colours and the podium's three medals. The
# podium shows its players' real portraits; the ranking rows show none (Arthur, 21 Nov 2026: the initial said nothing,
# and portraits there would cost bandwidth).
BOARD_BG, BOARD_CARD, BOARD_ROW_FILL, BOARD_DEEP = COLORS['background'], '#2b2b2b', '#323232', COLORS['field']
MEDALS = {1: COLORS['gold'], 2: '#c9ced6', 3: '#c58a4a'}
# The podium portraits' radius at 96 dpi, by place (Arthur, 21 Nov 2026: clearly larger than the old 20 px letter
# circle; the first larger, as on the site's podium), and the room between a portrait and its step.
PODIUM_PORTRAIT = {1: 36, 2: 30, 3: 30}
PODIUM_GAP = 6
# What the first three bought in the site's shop shows on their portraits too, as on the site's podium (Arthur, 21 Nov
# 2026): the frame they equip, in a box FRAMED_BOX times the portrait's width (the site's 124 / 88), the portrait inside
# it at the frame's hole (hole x box x 1.04, the site's rule), and the portrait animation they equip (the `hover` slot,
# HOVER_EFFECTS), played while the pointer is on the player. A frame's picture is the shop's own (online.frame_picture:
# the corner's cache in datas/, 1 MB at most), downloaded for the first three only, with the portraits' short timeout;
# the podium's map of pictures holds it under FRAME_KEY + the item's id.
FRAMED_BOX = 1.4
FRAME_KEY = 'frame:'


def next_place(rows, mine):
    """Where the player stands against the place above, from the ranking's own rows: None when the player is not in them;
    {'state': 'first'} when first; else {'state': 'behind', 'gap': points to pass the player above, 'above': that entry,
    'share': how far from the one below to the one above (0..1)}."""
    index = next((i for i, (entry, _) in enumerate(rows) if mine and entry.get('pseudonym') == mine), None)
    if index is None:
        return None
    entry = rows[index][0]
    if index == 0 or entry.get('rank') == 1:
        return {'state': 'first', 'index': index}
    above = rows[index - 1][0]
    below = rows[index + 1][0].get('total', 0) if index + 1 < len(rows) else 0
    mine_total, above_total = entry.get('total', 0), above.get('total', 0)
    share = (mine_total - below) / max(1, above_total - below)
    return {'state': 'behind', 'index': index, 'gap': max(1, above_total - mine_total + 1), 'above': above,
            'share': min(1.0, max(0.0, share))}


# Where a board entry names its portrait on the site: the uploaded one (`avatar`), else the one the site generates for a
# player who uploaded none (`avatar_generated`, asked of the site on 21 Nov 2026; absent until the site serves it). The
# converter never draws a generated portrait itself (Arthur, 21 Nov 2026): without either, the quiet silhouette.
PORTRAIT_FIELDS = ('avatar', 'avatar_generated')


def portrait_path(entry):
    """The public path of an entry's portrait on the site, or None."""
    for field in PORTRAIT_FIELDS:
        value = entry.get(field)
        if isinstance(value, str) and value:
            return value
    return None


def podium_paths(entries):
    """The public portraits of the first three (portrait_path), the only ones downloaded; none for the rows."""
    return [path for path in (portrait_path(entry) for entry in entries[:3]) if path]


def podium_frame(entry, catalog):
    """The frame item an entry equips, when the catalog can draw it (a picture and a usable hole); None otherwise."""
    item = online.looks(catalog, online.equipped(entry))['frame']
    data = item.get('data') if isinstance(item, dict) else None
    if not isinstance(data, dict) or not data.get('image') or frame_side(data.get('hole'), 100) is None:
        return None
    return item


def podium_frames(entries, catalog):
    """{FRAME_KEY + id: item} of the frames the first three equip (podium_frame), the only frames downloaded."""
    return {FRAME_KEY + item['id']: item for item in (podium_frame(entry, catalog) for entry in entries[:3]) if item}


def podium_frame_bytes(item, download):
    """online.frame_picture with the portraits' timeout, never raising: a frame is decoration."""
    try:
        return online.frame_picture(item, download=download, timeout=online.BOARD_PORTRAIT_TIMEOUT)
    except Exception:
        return None


def framed_face(box, hole):
    """The portrait's diameter inside a frame `box` px wide with that `hole` (the site's rule: hole x box x 1.04)."""
    return round(float(hole) * box * 1.04)


def podium_portrait_bytes(path, download):
    """online.board_portrait, never raising: a portrait is decoration."""
    try:
        return online.board_portrait(path, download=download)
    except Exception:
        return None


def board_messages(period, online_message):
    """What the leaderboard's loader sends the window, in order (run in a thread, no Tk call):
    ('board', (answer, error, shop), {path: portrait}) first, with the podium's portraits already in datas/, then, only
    when some are not, ('portraits', {path: portrait}) once they are downloaded: the board never waits for a picture,
    and a podium player without a portrait (or a failed download) keeps the quiet fallback. The frames the first three
    equip come the same way, under FRAME_KEY + their id (a frame not there yet: the medal's ring). The shop's catalog
    comes from its cache (refreshed every 30 minutes at most)."""
    try:
        board = online.board(period)
    except (online.ServiceError, online.ServiceConnectionError) as exc:
        yield 'board', (None, online_message(exc), {}), {}
        return
    try:
        shop = online.shop()
    except Exception:
        shop = {}
    entries = board.get('entries', [])
    frames = podium_frames(entries, shop)

    def picture(key, download):
        return podium_frame_bytes(frames[key], download) if key in frames else podium_portrait_bytes(key, download)
    known = {key: picture(key, False) for key in [*podium_paths(entries), *frames]}
    yield 'board', (board, None, shop), {key: raw for key, raw in known.items() if raw}
    missing = [key for key, raw in known.items() if raw is None]
    if missing:
        found = {key: picture(key, True) for key in missing}
        yield 'portraits', {key: raw for key, raw in found.items() if raw}


class LeaderboardMixin:
    """The leaderboard, the achievement card and the closing card."""

    # The ranking's columns: key, caption, width (0: the player's, the rest) and alignment (the headings).
    BOARD_COLUMNS = (('rank', 'leaderboard_rank', 50, 'w'), ('player', 'leaderboard_player', 0, 'w'),
                     ('games', 'leaderboard_games', 64, 'e'), ('gold', 'class_gold', 70, 'w'),
                     ('platinum', 'class_platinum', 70, 'w'), ('diamond', 'class_diamond', 70, 'w'),
                     ('points', 'leaderboard_points', 84, 'e'))
    BOARD_ROW = 32
    BOARD_HEADING = 24

    def board_columns(self, width, scale=1.0):
        """{key: (left, right)} of the ranking's columns for a list `width` wide (columns written for 96 dpi, times `scale`)."""
        fixed = sum(round(size * scale) for _, _, size, _ in self.BOARD_COLUMNS)
        spans, left = {}, 0
        for key, _, size, _ in self.BOARD_COLUMNS:
            size = round(size * scale) or max(round(160 * scale), width - fixed)
            spans[key] = (left, left + size)
            left += size
        return spans

    @staticmethod
    def board_scale(widget):
        try:
            return ui_scale(widget)
        except Exception:
            return 1.0

    def draw_board_heading(self, canvas, width, pictures):
        """The ranking's column captions, quiet above the rows (the gems' pictures before their classes)."""
        canvas.delete('all')
        k = self.board_scale(canvas)
        spans = self.board_columns(width, k)
        font = (self.ui_font, 8, 'bold')
        middle = round(self.BOARD_HEADING * k) // 2
        for key, caption, _, anchor in self.BOARD_COLUMNS:
            left, right = spans[key]
            text = self.tr(caption)
            if key in ('gold', 'platinum', 'diamond'):
                picture = pictures.get('gem-' + key)
                x = left + round(8 * k)
                if picture:
                    canvas.create_image(x + round(7 * k), middle, image=picture)
                    x += round(17 * k)
                canvas.create_text(x, middle, text=text, anchor='w', fill=COLORS['muted'], font=font)
            elif anchor == 'e':
                canvas.create_text(right - round(10 * k), middle, text=text, anchor='e', fill=COLORS['muted'], font=font)
            else:
                canvas.create_text(left + round(10 * k), middle, text=text, anchor='w', fill=COLORS['muted'], font=font)

    def podium_portrait(self, canvas, x, y, radius, place, raw, key=None, tags=(), frame=None):
        """A podium player's portrait, ringed in the medal's colour: the picture `raw` (bytes) the site serves (uploaded,
        or generated by the site for a player who uploaded none), or a quiet head-and-shoulders on a disc tinted by the
        medal while there is none (the site names none, it is downloading, or the download failed). With the shop
        `frame` the player equips (picture bytes, hole, id), the frame instead of the ring, in a box FRAMED_BOX times
        the portrait, the portrait inside at framed_face. The pictures are kept on the canvas by (key, frame, place,
        size): the opening animation redraws the podium every frame."""
        from PIL import ImageTk
        medal = MEDALS[place]
        size = 2 * radius
        drawn = (frame[0], frame[1]) if frame else None
        if frame:
            size = framed_face(2 * round(radius * FRAMED_BOX), frame[1])
        cache = canvas.__dict__.setdefault('_portraits', {})
        wanted = (key if raw else None, frame[2] if frame else None, place, size)
        photo = cache.get(wanted)
        if photo is None:
            try:
                photo = ImageTk.PhotoImage(_podium_picture(raw, size, medal, _tint(BOARD_CARD, medal, 0.16),
                                                           _tint(BOARD_CARD, medal, 0.42), frame=drawn), master=canvas)
            except (OSError, ValueError, tk.TclError):
                return None
            cache[wanted] = photo
        return canvas.create_image(x, y, image=photo, tags=('podium_portrait', *tags))

    def draw_board_pill(self, canvas, top, width, index, entry, counts, mine, catalog, pictures=None, tags=()):
        """One ranking row as a pill: the rank chip (the medal's colour for the first three), the pseudonym in its shop style
        (no portrait: those are the podium's), the console badge shown (a first place's one with its mark), the pin and the title, then games, the
        three class counts and the points. The player's own row is gold-rimmed."""
        k = self.board_scale(canvas)
        spans = self.board_columns(width, k)
        font, small, badge_font = (self.ui_font, 9), (self.ui_font, 8), (self.ui_font, 7, 'bold')
        name_font = (self.ui_font, 9, 'bold')
        measure, small_measure = _font(canvas, name_font), _font(canvas, small)
        height = round(self.BOARD_ROW * k)
        pad = round(3 * k)
        middle = top + height // 2
        name = entry.get('pseudonym') or self.tr('leaderboard_anonymous')
        you = bool(mine) and name == mine
        pill = (round(4 * k), top + pad, width - round(4 * k), top + height - pad)
        if you:
            _rounded(canvas, *pill, (height - 2 * pad) / 2, fill=COLORS['selected'], outline=COLORS['gold'], tags=tags)
        elif index % 2:
            _rounded(canvas, *pill, (height - 2 * pad) / 2, fill=BOARD_ROW_FILL, outline='', tags=tags)
        colour = COLORS['gold_hover'] if you else COLORS['text']
        rank = entry.get('rank', '')
        medal = MEDALS.get(rank)
        chip_left, chip_width, chip_height = spans['rank'][0] + round(8 * k), round(34 * k), round(20 * k)
        _rounded(canvas, chip_left, middle - chip_height / 2, chip_left + chip_width, middle + chip_height / 2, chip_height / 2,
                 fill=medal or (COLORS['selected'] if you else BOARD_CARD),
                 outline=COLORS['gold'] if you and not medal else '', tags=tags)
        canvas.create_text(chip_left + chip_width / 2, middle, text=str(rank), font=(self.ui_font, 9, 'bold'), tags=tags,
                           fill=COLORS['gold_text'] if medal else colour)
        # The name starts where the column's caption does, a clear step after the rank chip.
        left, right = spans['player'][0] + round(10 * k), spans['player'][1] - round(8 * k)
        look = online.looks(catalog, online.equipped(entry))
        title = self.title_name(entry.get('title'))
        badges = look['badges']
        badge_room = badges_width(canvas, badges, badge_font) + 6 if badges else 0
        extra = PIN_SIZE + 4 if look['pin'] else 0
        tail = min(round(140 * k), extra + small_measure.measure(title) + 10) if (title or extra) else 0
        shown = elide(measure, name, max(40, right - left - badge_room - tail))
        _items, used = draw_styled_text(canvas, left, middle, shown, name_font, look['name_style'],
                                        anchor='w', fill=colour, tags=('board_name', *tags))
        x = left + used + 6
        if badges:
            x += draw_badges(canvas, x, middle, badges, badge_font, tags=('board_badge', *tags),
                             top=online.top_badges(entry)) + 4
        if title or look['pin']:
            x += 6
            if look['pin']:
                draw_pin(canvas, x, middle - PIN_SIZE // 2, look['pin'], tags=('board_pin', *tags))
                x += PIN_SIZE + 4
            if title:
                canvas.create_text(x, middle, text=elide(small_measure, title, right - x), anchor='w',
                                   fill=COLORS['muted'], font=small, tags=('board_title', *tags))
        canvas.create_text(spans['games'][1] - round(10 * k), middle, text=self.count_text(entry.get('games', 0)), anchor='e',
                           fill=colour, font=font, tags=tags)
        for kind in ('gold', 'platinum', 'diamond'):
            x = spans[kind][0] + round(8 * k)
            picture = (pictures or {}).get('gem-' + kind)
            if picture:
                canvas.create_image(x + round(7 * k), middle, image=picture, tags=tags)
                x += round(17 * k)
            canvas.create_text(x, middle, text=compact_number(counts.get(kind, 0), self.language, 10_000), anchor='w',
                               fill=colour, font=font, tags=tags)
        canvas.create_text(spans['points'][1] - round(10 * k), middle, text=self.count_text(entry.get('total', 0)),
                           anchor='e', fill=colour, font=(self.ui_font, 10, 'bold'), tags=tags)

    def draw_board_rows(self, canvas, rows, width, mine, catalog, pictures=None):
        """The ranking's lines on a canvas, as pills (draw_board_pill); the player's own one gold-rimmed."""
        canvas.delete('all')
        canvas._sparkle = []
        height = round(self.BOARD_ROW * self.board_scale(canvas))
        for index, (entry, counts) in enumerate(rows):
            self.draw_board_pill(canvas, index * height, width, index, entry, counts, mine, catalog, pictures)
        canvas.configure(scrollregion=(0, 0, width, max(1, len(rows)) * height))

    def draw_board_pinned(self, canvas, rows, width, mine, catalog, pictures=None, visible=True):
        """The foot of the ranking: the player's own row pinned there while its line is out of view, and how far the next
        place is (« 141 pts more to pass LoRaster (rank 8) », or the first place). Returns the next_place() answer, None
        (nothing drawn) when the player is not in the rows."""
        canvas.delete('all')
        canvas._sparkle = []
        place = next_place(rows, mine)
        if place is None:
            return None
        k = self.board_scale(canvas)
        top = 0
        if not visible:
            # a thin rule, then the row: it stands apart from the half-scrolled line above it
            canvas.create_line(round(8 * k), 1, width - round(8 * k), 1, fill=COLORS['subtle_border'], tags=('pinned_row',))
            entry, counts = rows[place['index']]
            self.draw_board_pill(canvas, round(4 * k), width, 1, entry, counts, mine, catalog, pictures, tags=('pinned_row',))
            top = round(self.BOARD_ROW * k) + round(4 * k)
        middle = top + round(12 * k)
        left = self.board_columns(width, k)['player'][0] + round(10 * k)       # under the names
        if place['state'] == 'first':
            text, share = self.tr('leaderboard_first'), 1.0
        else:
            above = place['above']
            text = self.tr('leaderboard_next', points=self.count_text(place['gap']),
                           name=above.get('pseudonym') or self.tr('leaderboard_anonymous'), rank=above.get('rank', ''))
            share = place['share']
        bar, h = round(170 * k), round(6 * k)
        _rounded(canvas, left, middle - h / 2, left + bar, middle + h / 2, h / 2, fill=BOARD_DEEP, outline='',
                 tags=('next_place',))
        _rounded(canvas, left, middle - h / 2, left + max(h, bar * share), middle + h / 2, h / 2, fill=COLORS['gold'],
                 outline='', tags=('next_place',))
        canvas.create_text(left + bar + round(12 * k), middle, text=text, anchor='w', fill=COLORS['muted'],
                           font=(self.ui_font, 8), tags=('next_place', 'next_place_text'))
        return place

    def show_leaderboard(self):
        """The shared base's ranking in a window (design « Marches », Arthur's pick of 20 Nov 2026): the first three on
        rounded steps that rise one after the other, each with the player's portrait and a crown; the others as pill rows; the player's
        own row pinned at the foot while it is out of view, with how far the next place is. All time or this month (one
        segmented switch). What players equip in the site's shop shows as there: name styles, the console badge shown
        (with its "1" for a first place), pins and titles; nothing without the shop's catalog. The rules stay one hover
        away (« The rules »)."""
        if not SENDING_AVAILABLE or self.raise_existing('board_window'):return
        from .rounded_ui import Look
        from .tooltips import Tooltip
        from .branding import make_icon
        background = BOARD_BG
        window = tk.Toplevel(self.app)
        self.board_window = window
        window.withdraw()
        window.title(f"{APP_NAME} — {self.tr('leaderboard')}")
        window.configure(bg=background)
        window.transient(self.app)
        k = self.board_scale(window)
        look = window.look = Look(window, COLORS, self.ui_font)
        look.card('BoardCard', BOARD_CARD, background, 16)
        look.card('BoardTrack', BOARD_DEEP, background, 6)
        look.segment('BoardSeg', BOARD_DEEP, COLORS['gold'], COLORS['hover'], radius=9, size=9)
        body = tk.Frame(window, bg=background, padx=18, pady=14,
                        highlightthickness=1, highlightbackground=COLORS['gold'])
        body.pack(fill='both', expand=True)
        # The site's trophy and class gems, as converter pictures.
        pictures = window.pictures = {}
        for name, size in (('trophy', 52), ('gem-gold', 15), ('gem-platinum', 15), ('gem-diamond', 15)):
            try:
                pictures[name] = _scaled_photo(ASSETS / f'assets/board-{name}.png', window,
                                               size * k / 40 if name.startswith('gem') else size * k / 72)
            except (OSError, ValueError, tk.TclError):
                pictures[name] = ''
        top = tk.Frame(body, bg=background)
        top.pack(fill='x')
        tk.Label(top, image=pictures['trophy'], bg=background).pack(side='left', padx=(0, 10))
        titles = tk.Frame(top, bg=background)
        titles.pack(side='left', fill='y')
        tk.Label(titles, text=self.tr('leaderboard').upper(), bg=background, fg=COLORS['gold'],
                 font=(self.ui_font, 15, 'bold')).pack(anchor='w', pady=(4, 0))
        # The rules, one hover (or click) away: the same text as before, no longer above the podium.
        window.info_picture = make_icon(window, 'info', COLORS['muted'], size=round(14 * k))
        rules = tk.Label(titles, text=self.tr('leaderboard_rules_link'), image=window.info_picture, compound='left',
                         bg=background, fg=COLORS['muted'], font=(self.ui_font, 9, 'underline'), cursor='hand2', padx=0)
        rules.pack(anchor='w')
        # A click toggles the rules and keeps them up; a click elsewhere or Esc closes them; opened by hovering, they
        # close when the pointer leaves the link (Tooltip.toggle; a second show() used to leave the first one up).
        rules_hint = Tooltip(rules, lambda: self.tr('leaderboard_rules'))
        rules.bind('<Button-1>', rules_hint.toggle)
        window.rules_link, window.rules_hint = rules, rules_hint
        # A state the service sends (loading, an error, the preview, an empty board); empty otherwise.
        note = tk.Label(titles, text=self.tr('leaderboard_loading'), bg=background, fg=COLORS['muted'],
                        font=(self.ui_font, 9), wraplength=round(420 * k), justify='left')
        note.pack(anchor='w')
        window.board_note = note
        period = tk.StringVar(value='all')
        track = ttk.Frame(top, style='BoardTrack.TFrame', padding=3)
        track.pack(side='right', anchor='n', pady=(6, 0))
        for value, key in (('month', 'leaderboard_month'), ('all', 'leaderboard_all')):
            ttk.Radiobutton(track, text=self.tr(key), value=value, variable=period, style='BoardSeg.TRadiobutton',
                            command=lambda: load()).pack(side='left')
        window.board_period = period
        # The shop's catalog ({id: item}) once the board has answered; the podium's portraits ({public path: bytes}),
        # read from datas/ with the answer, downloaded after it (the board shows first).
        catalog = {}
        portraits = window.board_portraits = {}
        STEP = {1: 134, 2: 112, 3: 96}           # the steps' heights at 96 dpi; above the tallest: name, badge, crown, portrait
        ABOVE = 114 + 2 * (PODIUM_PORTRAIT[1] - 20)       # the room the larger portraits take, the steps unchanged
        podium = tk.Canvas(body, height=round((STEP[1] + ABOVE + 14) * k), bg=background, highlightthickness=0)
        podium.pack(fill='x', pady=(8, 6))
        podium.rows = []
        podium.bind('<Configure>', lambda event: draw_podium(podium.rows))
        # The ranking in a rounded card: the column captions, the rows (a canvas list, so a name can carry its style,
        # badges and pin), then the pinned foot.
        listing = ttk.Frame(body, style='BoardCard.TFrame', padding=(8, 6))
        heading = tk.Canvas(listing, height=round(self.BOARD_HEADING * k), bg=BOARD_CARD, highlightthickness=0)
        table = tk.Canvas(listing, height=round(self.BOARD_ROW * k) * 8, bg=BOARD_CARD, highlightthickness=0,
                          yscrollincrement=round(self.BOARD_ROW * k))
        bar = ttk.Scrollbar(listing, orient='vertical', command=table.yview)
        pinned = tk.Canvas(listing, height=1, bg=BOARD_CARD, highlightthickness=0)
        heading.grid(row=0, column=0, sticky='ew')
        table.grid(row=1, column=0, sticky='nsew')
        bar.grid(row=1, column=1, sticky='ns')
        pinned.grid(row=2, column=0, columnspan=2, sticky='ew')
        listing.grid_columnconfigure(0, weight=1)
        listing.grid_rowconfigure(1, weight=1)
        listing.pack(fill='both', expand=True)
        table.rows, table.mine = [], None
        window.board_table, window.board_pinned = table, pinned

        def mine_visible():
            place = next_place(table.rows, table.mine)
            if place is None:
                return True
            first, last = table.yview()
            total = max(1, len(table.rows)) * round(self.BOARD_ROW * k)
            row_top = place['index'] * round(self.BOARD_ROW * k)
            return first * total <= row_top and row_top + round(self.BOARD_ROW * k) <= last * total + 1

        def draw_pinned():
            width = table.winfo_width()
            if width < 300:
                return
            visible = mine_visible()
            place = self.draw_board_pinned(pinned, table.rows, width, table.mine, catalog, pictures, visible=visible)
            rows = 0 if place is None else (1 if visible else 2)
            height = 1 if place is None else (round(self.BOARD_ROW * k) + round(4 * k)) * (rows - 1) + round(26 * k)
            if int(pinned.cget('height')) != height:
                pinned.configure(height=height)

        def scrolled(first, last):
            bar.set(first, last)
            draw_pinned()
        table.configure(yscrollcommand=scrolled)

        def draw_table(event=None):
            width = table.winfo_width()
            if width < 300:
                return
            self.draw_board_heading(heading, width, pictures)
            self.draw_board_rows(table, table.rows, width, table.mine, catalog, pictures)
            draw_pinned()
        table.bind('<Configure>', draw_table)
        def scroll(event):
            steps = -1 if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0 else 1
            table.yview_scroll(steps * max(1, abs(getattr(event, 'delta', 0)) // 120), 'units')
            return 'break'
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            table.bind(sequence, scroll)
        # The footer is reserved first: a longer note above never clips it.
        foot = tk.Frame(body, bg=background)
        foot.pack(side='bottom', fill='x', pady=(10, 0), before=listing)
        you_line = tk.Label(foot, text='', bg=background, fg=COLORS['text'], font=(self.ui_font, 9))
        you_line.pack(side='left')
        window.board_you = you_line
        ttk.Button(foot, text=self.tr('close'), command=window.destroy).pack(side='right')

        # Opening animation: the steps rise one after the other (third, second, first), carrying each player's
        # portrait, crown, name and badge up.
        podium.started = time.monotonic()
        RISE, DELAYS = 0.6, {3: 0.0, 2: 0.18, 1: 0.36}

        def crown(middle, base, place, colour):
            """Gold: five points; silver: three; bronze: a low band with two points."""
            shapes = {
                1: (-14, 0, -14, -12, -7, -5, 0, -14, 7, -5, 14, -12, 14, 0),
                2: (-12, 0, -12, -10, -5, -5, 0, -11, 5, -5, 12, -10, 12, 0),
                3: (-11, 0, -11, -7, -5, -4, 0, -8, 5, -4, 11, -7, 11, 0)}
            podium.create_polygon(*[middle + v * k if i % 2 == 0 else base + v * k for i, v in enumerate(shapes[place])],
                                  fill=colour, outline='', tags=('crown',))

        def podium_framed(entry):
            """(picture bytes, hole, id) of the frame the entry equips, once its picture is here; None otherwise."""
            item = podium_frame(entry, catalog)
            raw = portraits.get(FRAME_KEY + item['id']) if item else None
            return (raw, item['data']['hole'], item['id']) if raw else None

        def draw_podium(rows, animate=False):
            podium.rows = rows
            if animate:
                podium.started = time.monotonic()
            podium.delete('all')
            podium._sparkle = []
            podium.hot = []
            # A framed portrait is larger: the canvas grows by the largest frame's extra room (the list keeps the rest).
            extra = max((2 * (round(PODIUM_PORTRAIT[place] * FRAMED_BOX) - PODIUM_PORTRAIT[place])
                         for place, (entry, _) in enumerate(rows[:3], 1) if podium_framed(entry)), default=0)
            wanted = round((STEP[1] + ABOVE + 14 + extra) * k)
            if int(podium.cget('height')) != wanted:
                podium.configure(height=wanted)
            width, bottom = podium.winfo_width(), wanted
            if width < 300:
                return
            if not rows:
                podium.create_text(width // 2, bottom // 2, text=self.tr('leaderboard_empty'),
                                   fill=COLORS['muted'], font=(self.ui_font, 9))
                return
            elapsed = time.monotonic() - podium.started
            step = round(178 * k)
            left = (width - 3 * step) // 2
            base = bottom - round(4 * k)
            moving = False
            name_font, title_font, badge_font = (self.ui_font, 10, 'bold'), (self.ui_font, 8), (self.ui_font, 7, 'bold')
            gem_font = (self.ui_font, 8, 'bold')
            for slot, place in ((0, 2), (2, 3), (1, 1)):     # drawn second, third, then the first in the middle
                x0 = left + slot * step + round(5 * k)
                x1 = x0 + step - round(10 * k)
                middle = (x0 + x1) / 2
                medal = MEDALS[place]
                progress = min(1.0, max(0.0, (elapsed - DELAYS[place]) / RISE))
                moving |= progress < 1.0
                eased = 1 - (1 - progress) ** 3
                height = max(2, round(STEP[place] * k * eased))
                top = base - height
                _rounded(podium, x0, top, x1, base, round(14 * k), fill=_tint(BOARD_CARD, medal, 0.10), outline=medal)
                _rounded(podium, x0, top, x1, top + round(8 * k), round(4 * k), fill=medal, outline='')
                podium.create_text(middle, base - round(2 * k), text=str(place), anchor='s',
                                   fill=_tint(medal, BOARD_CARD, 0.45), font=(self.ui_font, 18, 'bold'))
                if place > len(rows) or progress < 0.2:
                    continue
                entry, counts = rows[place - 1]
                # the step's own content: the gems and their counts, then the points
                if height > round(52 * k):
                    for column, kind in zip((-1, 0, 1), ('gold', 'platinum', 'diamond')):
                        centre = middle + column * round(48 * k)
                        picture = pictures.get(f'gem-{kind}')
                        if picture:
                            podium.create_image(centre - round(10 * k), top + round(24 * k), image=picture)
                        podium.create_text(centre + round(1 * k), top + round(24 * k), anchor='w', font=gem_font,
                                           text=compact_number(counts.get(kind, 0), self.language, 1_000),
                                           fill=COLORS['text'])
                    podium.create_text(middle, top + round(48 * k), text=f"{self.count_text(entry.get('total', 0))} pts",
                                       fill=medal, font=(self.ui_font, 11, 'bold'))
                # standing on the step: the portrait, its crown, the badge (pin and title) and the name above
                name = entry.get('pseudonym') or self.tr('leaderboard_anonymous')
                look = online.looks(catalog, online.equipped(entry))
                path = portrait_path(entry)
                radius = PODIUM_PORTRAIT[place]
                framed = podium_framed(entry)
                outer = round(radius * FRAMED_BOX) if framed else radius
                centre = top - round((PODIUM_GAP + outer) * k)
                self.podium_portrait(podium, middle, centre, round(radius * k), place,
                                     portraits.get(path) if path else None, key=path, frame=framed)
                # Where the portrait animation plays (the player's column above the step) and over what.
                face = (framed_face(2 * round(round(radius * k) * FRAMED_BOX), framed[1]) if framed
                        else 2 * round(radius * k))
                effect = ((look['hover'] or {}).get('data') or {}).get('effect')
                podium.hot.append({'place': place, 'x0': x0, 'x1': x1, 'bottom': top, 'x': middle, 'y': centre,
                                   'face': face, 'effect': effect if effect in HOVER_EFFECTS else None})
                crown_base = top - round((PODIUM_GAP + 2 * outer + 4) * k)
                crown(middle, crown_base, place, medal)
                inner = x1 - x0 - round(12 * k)
                line = crown_base - round(28 * k)
                title, pin = self.title_name(entry.get('title')), look['pin']
                parts = badges_width(podium, look['badges'], badge_font) if look['badges'] else 0
                measure = _font(podium, title_font)
                pin_room = PIN_SIZE + 4 if pin else 0
                shown = elide(measure, title, max(0, inner - parts - pin_room - 8)) if title else ''
                total = parts + (6 if parts and (pin or shown) else 0) + pin_room + measure.measure(shown)
                x = middle - total / 2
                if parts:
                    x += draw_badges(podium, x, line, look['badges'], badge_font, tags=('podium_badge',),
                                     top=online.top_badges(entry)) + (6 if (pin or shown) else 0)
                if pin:
                    draw_pin(podium, round(x), line - PIN_SIZE // 2, pin, tags=('podium_pin',))
                    x += PIN_SIZE + 4
                if shown:
                    podium.create_text(x, line, text=shown, anchor='w', fill=COLORS['muted'], font=title_font)
                name_y = line - round(19 * k) if (parts or pin or shown) else line
                if name_colours(look['name_style'], 1):
                    draw_styled_text(podium, middle, name_y, elide(_font(podium, name_font), name, inner),
                                     name_font, look['name_style'], anchor='center', tags=('podium_name',))
                else:
                    podium.create_text(middle, name_y, text=elide(_font(podium, name_font), name, inner),
                                       fill=COLORS['text'], font=name_font)
            podium.tag_raise('crown')     # nothing of the podium is ever drawn over a crown
            if moving or elapsed < DELAYS[1] + RISE + 0.05:
                pending = getattr(podium, 'frame', None)
                if pending:
                    tk_later.cancel(podium, pending)
                podium.frame = tk_later.later(podium, 16, lambda: draw_podium(podium.rows))
            else:
                podium.frame = None

        # The portrait animation a podium player equips, while the pointer is on them (their column above the step):
        # « shine » sweeps once per visit, « spin » turns until the pointer leaves, as on the site.
        podium.hot, podium.effect = [], None

        def effect_photo(effect, face, index):
            from PIL import ImageTk
            cache = podium.__dict__.setdefault('_effects', {})
            wanted = (effect, face, index)
            if wanted not in cache:
                try:
                    picture = hover_effect_picture(effect, face, index)
                    cache[wanted] = ImageTk.PhotoImage(picture, master=podium) if picture else None
                except (OSError, ValueError, tk.TclError):
                    cache[wanted] = None
            return cache[wanted]

        def effect_step():
            state = podium.effect
            if state is None or not podium.winfo_exists():
                return
            state['job'] = None
            podium.delete('podium_effect')
            spot = next((spot for spot in podium.hot if spot['place'] == state['place']), None)
            if spot is None or spot['effect'] != state['effect']:
                podium.effect = None
                return
            seconds, count = HOVER_EFFECTS[state['effect']]
            elapsed = time.monotonic() - state['started']
            if state['effect'] == 'shine' and elapsed >= seconds:
                return                              # once per visit
            photo = effect_photo(state['effect'], spot['face'], int(elapsed / seconds * count) % count)
            if photo:
                # disabled: the overlay never takes the pointer's events
                podium.create_image(spot['x'], spot['y'], image=photo, state='disabled', tags=('podium_effect',))
            state['job'] = tk_later.later(podium, 40, effect_step)

        def effect_stop(event=None):
            state, podium.effect = podium.effect, None
            if state and state.get('job'):
                tk_later.cancel(podium, state['job'])
            podium.delete('podium_effect')

        def effect_pointer(event):
            spot = next((spot for spot in podium.hot if spot['x0'] <= event.x <= spot['x1'] and event.y <= spot['bottom']),
                        None)
            place = spot['place'] if spot and spot['effect'] else None
            if place == (podium.effect or {}).get('place'):
                return
            effect_stop()
            if place:
                podium.effect = {'place': place, 'effect': spot['effect'], 'started': time.monotonic(), 'job': None}
                effect_step()
        podium.bind('<Motion>', effect_pointer)
        podium.bind('<Leave>', effect_stop)
        window.podium_pointer, window.podium_effect_stop = effect_pointer, effect_stop

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
            # The rules no longer stand above the podium (« The rules », one hover away): only a state is said here.
            note.configure(text=self.tr('leaderboard_demo') if answer.get('demo')
                           else self.tr('leaderboard_empty') if not entries else '')
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
            # The player's line in the rows is the pinned foot; outside them, the line under the card says the rank.
            if next_place(rows, mine) is not None:
                you_line.configure(text='')
            elif you.get('rank'):
                you_line.configure(text=self.tr('leaderboard_you', rank=you['rank'], points=self.count_text(you.get('total', 0))))
            elif online.account():
                you_line.configure(text=self.tr('account_unranked', points=self.count_text(you.get('total', 0))))
            else:
                you_line.configure(text='')
        window.board_show = show

        def load():
            note.configure(text=self.tr('leaderboard_loading'))
            wanted = period.get()
            messages, finished = [], []
            window.board_load = token = object()        # a newer load (the period switch) wins over this one
            def worker():
                # No Tk call here: the window polls for the messages.
                try:
                    for message in board_messages(wanted, self.online_message):
                        messages.append(message)
                finally:
                    finished.append(True)
            def poll():
                if not window.winfo_exists() or window.board_load is not token:return
                while messages:
                    kind, *data = messages.pop(0)
                    if kind == 'board':
                        portraits.update(data[1])
                        show(*data[0])
                    elif data[0]:
                        portraits.update(data[0])
                        draw_podium(podium.rows)
                if not finished or messages:
                    tk_later.later(window, 50, poll)
            threading.Thread(target=worker, daemon=True).start()
            poll()
        # Esc closes the rules first when they show, then the window.
        window.bind('<Escape>', lambda event: None if Tooltip.close_shown() else window.destroy())
        window.update_idletasks()
        center_dialog(window, self.app, 800, 780 + 2 * (PODIUM_PORTRAIT[1] - 20))     # the list keeps its rows
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
            tk_later.later(window, 40, animate, frame + 1)
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

    def closing_card(self, games):
        """Before closing: the discoveries of `games` wait to be sent. Returns 'recompile', 'send', 'skip' or None
        (cancel); see offer_closing_card. The card is retrorecomp/closing_card_view.py; when it returns 'recompile',
        `closing_selection` holds the games ticked in the shared « New paths » list."""
        from .closing_card_view import ClosingCard
        card = ClosingCard(self, games, sending=SENDING_AVAILABLE)
        choice = card.run()
        self.closing_selection = card.selected if choice == 'recompile' else None
        return choice

    def offer_closing_card(self):
        """Before closing: games whose new paths are not recompiled yet, on the
        consoles that share discoveries. True keeps the window open."""
        self.closing_checked = True
        from .compiled_games import refresh_changed
        try:refresh_changed(self.compiled_inventory, self.preferences(), budget=2.0)
        except Exception:pass
        games = self.games_with_new_paths(shared_only=True)
        if not games:return False
        self.closing_selection = None
        choice = self.closing_card(games)
        if choice is None:
            self.closing_checked = False
            return True
        if choice == 'send':
            self.send_knowledge(closing=True)
            return True
        if choice != 'recompile':return False
        self.closing_after_recompile = self.close_when_idle = True
        self.recompile_new_paths(self.closing_selection or games)   # the games ticked in the list
        return True
