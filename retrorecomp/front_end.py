"""Front-end: the compiled games as a wall of box art, one console at a time.

The logic only (no Tk): which consoles have games, their order, the shape of a console's covers, the grid's geometry,
moving in it, the gamepad's buttons, and the small file that remembers what was played last. The window part is
front_end_view.py; the games themselves are the Compiled Games inventory (compiled_games.py), never a second list.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import statistics
import time
from threading import Lock

from .compiled_games import SHA, read_json
from .library import atomic_json
from .paths import data_directory

ORDERS = ('last_played', 'title', 'converted')
# The shape of a console's cover slots (width / height): the median of its covers, kept between a tall box and a
# wide one, so one odd picture (a title screen, a 3:1 strip) never sets the slot of a whole console.
DEFAULT_ASPECT = 0.72
ASPECT_RANGE = (0.62, 1.45)
# Text and margins: the window, and TV mode (full screen, read from the sofa).
SCALE_WINDOW, SCALE_TV = 1.0, 1.6
# Covers per row, chosen per console (the density); until then, about 150 px wide covers fill the row.
MIN_COLUMNS, MAX_COLUMNS = 4, 12      # never fewer than 4 covers per row (Arthur, 16 Nov 2026)
# The chosen cover grows a little, around the middle of its bottom edge; the grid leaves it room above the first row.
FOCUS_GROWTH = 1.08
MAX_PLAYED = 5000
HIDDEN_STATUSES = {'missing'}


def game_key(game) -> str:
    """How the front-end names a game: by its console and ROM identity, so a game moved or reconverted keeps its
    last-played date."""
    return f'{game.system}:{game.identity}'


def shelves(games, profiles):
    """The consoles that have at least one game, in the registry's order, each with its games:
    [(profile, [games])]. Games whose executable is gone are left out (Compiled Games still lists them)."""
    found = {}
    for game in games:
        if game.status not in HIDDEN_STATUSES:
            found.setdefault(game.system, []).append(game)
    return [(profile, found[profile.id]) for profile in profiles if profile.id in found]


def searchable(text) -> str:
    """A title or a query as the search compares them: no case, no accents."""
    import unicodedata
    return ''.join(char for char in unicodedata.normalize('NFKD', str(text).casefold())
                   if not unicodedata.combining(char))


def search(games, query):
    """The games whose title holds every word of `query`, on every console (no case, no accents)."""
    words = searchable(query).split()
    if not words:
        return []
    return [game for game in games if all(word in searchable(game.title) for word in words)]


def favorites(games):
    return [game for game in games if game.favorite]


def carousel(count, chosen):
    """The console strip as a band around the chosen entry, which stays in the middle: (left, right), the indices
    drawn on each side from the nearest outwards. The band goes round, each entry appears once."""
    others = count - 1
    right = [(chosen + step) % count for step in range(1, others - others // 2 + 1)]
    left = [(chosen - step) % count for step in range(1, others // 2 + 1)]
    return left, right


# The on-screen keyboard of the search (gamepad, mouse): letters in order, digits, then space (two cells), delete
# and done. No layout to guess and no glyph outside the interface fonts.
KEYBOARD = (tuple('ABCDEFGHIJ'), tuple('KLMNOPQRST'), tuple('UVWXYZ0123'),
            ('4', '5', '6', '7', '8', '9', 'space', 'space', 'delete', 'done'))
MAX_QUERY = 40


def keyboard_move(row, column, dx, dy):
    """The cell reached on the on-screen keyboard; a key two cells wide is one stop, and the edges wrap."""
    rows, columns = len(KEYBOARD), len(KEYBOARD[0])
    if dy:
        return (row + dy) % rows, column
    key = KEYBOARD[row][column]
    for _ in range(columns):
        column = (column + dx) % columns
        if KEYBOARD[row][column] != key:
            break
    return row, column


def type_key(query, key):
    """`query` after one key of the keyboard: a character, 'space' or 'delete'."""
    if key == 'delete':
        return query[:-1]
    if key == 'space':
        key = ' '
    if len(key) != 1 or not key.isprintable() or len(query) >= MAX_QUERY or (key == ' ' and not query.strip()):
        return query
    return query + key.casefold()


def sort_games(games, order, played):
    """`order`: 'last_played' (the last played first, then never played games by title), 'title', or 'converted'
    (the newest export first)."""
    title = lambda game: (game.title.casefold(), game.executable)
    if order == 'title':
        return sorted(games, key=title)
    if order == 'converted':
        return sorted(games, key=lambda game: (-game.modified, *title(game)))
    return sorted(games, key=lambda game: (-played.get(game_key(game), 0), *title(game)))


def cell_aspect(ratios):
    """The slot shape for a console from its covers' width / height ratios."""
    ratios = [r for r in ratios if isinstance(r, (int, float)) and math.isfinite(r) and r > 0]
    if not ratios:
        return DEFAULT_ASPECT
    low, high = ASPECT_RANGE
    return min(high, max(low, statistics.median(ratios)))


def fit(size, box):
    """`size` (w, h) scaled to fit inside `box` (w, h) without distortion; never zero."""
    width, height = size
    if width <= 0 or height <= 0:
        return box
    scale = min(box[0] / width, box[1] / height)
    return max(1, round(width * scale)), max(1, round(height * scale))


@dataclass(frozen=True)
class Grid:
    columns: int
    cover_width: int
    cover_height: int
    tile_width: int
    tile_height: int
    gap: int
    margin: int
    title_lines: int
    top: int

    @property
    def rows_top(self):
        return self.top

    def rows(self, count):
        return -(-count // self.columns) if count else 0

    def height(self, count):
        return self.top + self.margin + self.rows(count) * self.tile_height

    def origin(self, index):
        """Top-left corner of tile `index` in the scrolled area."""
        row, column = divmod(index, self.columns)
        return self.margin + column * self.tile_width, self.top + row * self.tile_height

    def visible(self, top, height, count):
        """The tiles whose row shows between `top` and `top + height`, one row more on each side."""
        if not count:
            return range(0)
        first = max(0, int((top - self.top) // self.tile_height) - 1)
        last = min(self.rows(count), int((top + height - self.top) // self.tile_height) + 2)
        return range(first * self.columns, min(count, last * self.columns))

    def at(self, x, y, count):
        """The tile under a point of the scrolled area, or None."""
        column = int((x - self.margin) // self.tile_width)
        row = int((y - self.top) // self.tile_height)
        if x < self.margin or y < self.top or not 0 <= column < self.columns:
            return None
        index = row * self.columns + column
        return index if 0 <= index < count else None


def auto_columns(width, aspect, scale=1.0):
    """Covers per row before the player chooses: slots about 150 px wide for a tall box at scale 1 (wider for wide
    boxes, so every console shows about the same number of covers)."""
    gap, margin = round(22 * scale), round(16 * scale)
    target = min(250 * scale, max(140 * scale, 208 * scale * aspect))
    usable = max(1, width - 2 * margin)
    return min(MAX_COLUMNS, max(MIN_COLUMNS, int((usable + gap) // (target + gap))))


def grid(width, aspect, scale=1.0, line_height=16, columns=None):
    """The wall for a view `width` pixels wide: `columns` slots of the console's `aspect` per row (auto_columns when
    None), stretched to fill the width. Two lines of title under covers wide enough for them, one under narrower ones,
    none under the narrowest (the details line names the chosen game)."""
    columns = min(MAX_COLUMNS, max(MIN_COLUMNS, columns or auto_columns(width, aspect, scale)))
    gap = max(6, round(22 * scale * min(1.0, 6 / columns)))
    margin = round(16 * scale)
    usable = max(1, width - 2 * margin)
    tile_width = max(1, usable // columns)
    cover_width = max(16, tile_width - gap)
    cover_height = max(16, round(cover_width / aspect))
    title_lines = 2 if cover_width >= 110 * scale else 1 if cover_width >= 70 * scale else 0
    tile_height = cover_height + (round(10 * scale) + title_lines * line_height if title_lines else 0) + gap
    # Room above the first row for the chosen cover's growth and its gold frame.
    top = margin + math.ceil(cover_height * (FOCUS_GROWTH - 1)) + round(8 * scale)
    return Grid(columns, cover_width, cover_height, tile_width, tile_height, gap, margin, title_lines, top)


def move(index, count, columns, dx=0, dy=0):
    """The tile reached from `index` by one step: left and right go on to the row before or after, up and down stay in
    the column (down from the second-to-last row lands on the last tile)."""
    if count <= 0:
        return 0
    index = min(max(index, 0), count - 1)
    if dx:
        return min(max(index + dx, 0), count - 1)
    if dy:
        target = index + dy * columns
        if target < 0:
            return index
        if target >= count:
            return count - 1 if index // columns < (count - 1) // columns else index
        return target
    return index


def step_columns(current, change):
    """One more or one fewer cover per row, within MIN_COLUMNS..MAX_COLUMNS."""
    return min(MAX_COLUMNS, max(MIN_COLUMNS, current + change))


# SDL game controller buttons, as player_gamepad.Controller reports them (the bit of each button).
BUTTONS = {'a': 0, 'b': 1, 'x': 2, 'y': 3, 'back': 4, 'start': 6, 'lb': 9, 'rb': 10,
           'up': 11, 'down': 12, 'left': 13, 'right': 14,
           # L2 and R2 past half travel: two bits the bridge adds above the SDL buttons (native/player_gamepad.c).
           'l2': 29, 'r2': 30}
STICK = 16000


class GridPad:
    """The gamepad on the wall: four directions with a paced repeat (the d-pad or the left stick), and one event per
    press of A, B, X, Y, LB, RB, L2, R2, Back and Start. Like player_gamepad.Navigation it waits for every pad to be at rest
    before it acts, so the press that opened the front-end never acts in it."""
    def __init__(self):
        self.armed = False
        self.buttons = 0
        self.direction = (0, 0)
        self.repeat_at = 0.0
        self.repeats = 0

    @staticmethod
    def read(pads):
        buttons, direction = 0, (0, 0)
        for mask, x, y in pads:
            buttons |= mask
            dx = (-1 if mask & 1 << BUTTONS['left'] or x < -STICK else 1 if mask & 1 << BUTTONS['right'] or x > STICK
                  else 0)
            dy = -1 if mask & 1 << BUTTONS['up'] or y < -STICK else 1 if mask & 1 << BUTTONS['down'] or y > STICK else 0
            if dx or dy:
                # One axis at a time: the one pushed further wins on a diagonal of the stick.
                direction = (dx, 0) if dx and (not dy or abs(x) >= abs(y)) else (0, dy)
        return buttons, direction

    def update(self, pads, now, enabled=True):
        """The events of this poll: ('move', dx, dy) and button names."""
        buttons, direction = self.read(pads)
        if not enabled:
            self.armed = False
        if not self.armed:
            self.buttons, self.direction = buttons, direction
            self.armed = enabled and not buttons and direction == (0, 0)
            return []
        events = []
        if direction != (0, 0):
            if direction != self.direction:
                self.repeat_at, self.repeats = now + 0.35, 0
                events.append(('move', *direction))
            elif now >= self.repeat_at:
                # Faster the longer it is held, so a long console scrolls quickly.
                self.repeats += 1
                self.repeat_at = now + (0.10 if self.repeats < 8 else 0.05)
                events.append(('move', *direction))
        self.direction = direction
        pressed = buttons & ~self.buttons
        self.buttons = buttons
        for name in ('a', 'b', 'x', 'y', 'lb', 'rb', 'l2', 'r2', 'back', 'start'):
            if pressed & 1 << BUTTONS[name]:
                events.append(name)
        return events


class Memory:
    """What the front-end keeps between two sessions, in datas/front-end.json: the console shown, the order, the covers
    per row of each console, and when each game was last played (from the front-end or from Compiled Games). Never a
    ROM path or a title."""
    SCHEMA = 1

    def __init__(self, path=None):
        self.path = Path(path) if path else data_directory() / 'front-end.json'
        self.lock = Lock()
        self.console, self.order = '', ORDERS[0]
        self.columns, self.played = {}, {}
        try:
            data = read_json(self.path, 1024 * 1024)
        except (OSError, ValueError):
            return
        if data.get('schema') != self.SCHEMA:
            return
        if isinstance(data.get('console'), str) and re.fullmatch('[a-z0-9_]{1,24}', data['console']):
            self.console = data['console']
        if data.get('order') in ORDERS:
            self.order = data['order']
        columns = data.get('columns')
        if isinstance(columns, dict):
            for system, count in list(columns.items())[:64]:
                if (isinstance(system, str) and re.fullmatch('[a-z0-9_]{1,24}', system) and type(count) is int
                        and MIN_COLUMNS <= count <= MAX_COLUMNS):
                    self.columns[system] = count
        played = data.get('played')
        if isinstance(played, dict):
            for key, stamp in list(played.items())[:MAX_PLAYED]:
                system, _, identity = key.partition(':') if isinstance(key, str) else ('', '', '')
                if (re.fullmatch('[a-z0-9_]{1,24}', system) and SHA.fullmatch(identity)
                        and isinstance(stamp, (int, float)) and math.isfinite(stamp) and stamp > 0):
                    self.played[key] = float(stamp)

    def mark_played(self, game, now=None):
        with self.lock:
            self.played[game_key(game)] = time.time() if now is None else now
            if len(self.played) > MAX_PLAYED:
                for key in sorted(self.played, key=self.played.get)[:len(self.played) - MAX_PLAYED]:
                    del self.played[key]
        self.save()

    def save(self):
        with self.lock:
            data = {'schema': self.SCHEMA, 'console': self.console, 'order': self.order,
                    'columns': dict(self.columns), 'played': dict(self.played)}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.path, data)
        except OSError:
            pass
