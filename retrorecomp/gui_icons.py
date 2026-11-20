"""The toolbar's and the queue's pictures that need more detail than the shared set of branding.py: our own drawings, as
polylines on the same 16 x 16 grid (make_icon draws them at 18 px, one pixel wide), registered in ICON_PATHS when this
module is imported. Interface only: branding.py, a compiler input, is not touched.

Each picture says what its button does without its text (the text stays set on the button, and the hover hint is
translated): where the queue / Compiled Games switch leads, a cartridge with a plus to add ROMs, all the rows against
the selected rows to convert, a screen for the video timing, arrows going out or in for the full screen."""
from __future__ import annotations

import math

from .branding import ICON_PATHS


def _rectangle(x1, y1, x2, y2):
    return (x1, y1, x2, y1, x2, y2, x1, y2, x1, y1)


def _filled(x1, y1, x2, y2, step=0.5):
    """Horizontal lines a half pixel apart: a solid bar at any size."""
    return tuple((x1, y1 + index * step, x2, y1 + index * step) for index in range(int(round((y2 - y1) / step)) + 1))


def _cartridge(x, y, width, height, notch=2):
    """A cartridge's outline: the top right corner cut."""
    return (x, y, x + width - notch, y, x + width, y + notch, x + width, y + height, x, y + height, x, y)


def _gear(cx, cy, outer, inner, teeth):
    points = []
    for index in range(teeth * 2 + 1):
        radius = outer if index % 2 == 0 else inner
        angle = index * math.pi / teeth
        points += [round(cx + radius * math.cos(angle), 2), round(cy + radius * math.sin(angle), 2)]
    return tuple(points)


# "Go there" badge of the queue / Compiled Games switch, at the bottom right.
_GO = ((11, 13.5, 15.5, 13.5), (13, 11.5, 15.5, 13.5, 13, 15.5))
# What the convert buttons start.
_RUN = (11, 4.5, 15, 8, 11, 11.5, 11, 4.5)


def _expand_arrows(inwards):
    """Four arrows in the corners of a frame, pointing out to the corners (or in, from them to the centre)."""
    arrows = []
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        corner = (8 - sx * 5, 8 - sy * 5)
        inner = (8 - sx * 2, 8 - sy * 2)
        tail, tip = (corner, inner) if inwards else (inner, corner)
        # The head: two short strokes back from the tip along the axes.
        back = -1 if inwards else 1
        arrows.append((*tail, *tip))
        arrows.append((tip[0] + back * sx * 2.5, tip[1], *tip, tip[0], tip[1] + back * sy * 2.5))
    return tuple(arrows)


ICONS = {
    # Where the switch leads: from the queue to the Compiled Games (cartridges, one with a play mark), and back to the
    # conversion queue (a list and a gear).
    'switch_compiled': (_cartridge(1, 6, 8, 8, 2), (3, 3, 10, 3, 11, 4, 11, 9), (3, 3, 3, 6),
                        (3.5, 8.5, 3.5, 12, 6.5, 10.2, 3.5, 8.5)) + _GO,
    'switch_queue': ((1, 3, 7, 3), (1, 7, 7, 7), (1, 11, 7, 11), _gear(11.5, 5, 3.6, 2.6, 8), (11.5, 4.5, 11.5, 5.5)) + _GO,
    # Add ROMs: a cartridge with a plus.
    'add_roms': (_cartridge(1, 4, 10, 11, 2), _rectangle(3, 6, 8, 9), (3, 12, 3, 14), (5, 12, 5, 14), (7, 12, 7, 14),
                 (9, 12, 9, 14), (13, 1, 13, 7), (10, 4, 16, 4)),
    # A box art to choose (a plus) and the automatic one (a spark).
    'cover_choose': (_rectangle(1, 1, 10, 12), (2, 10, 4.5, 6.5, 6, 8.5, 8, 5, 9, 7), (3, 3, 3, 3),
                     (13, 9, 13, 15), (10, 12, 16, 12)),
    'cover_auto': (_rectangle(1, 1, 10, 12), (2, 10, 4.5, 6.5, 6, 8.5, 8, 5, 9, 7), (3, 3, 3, 3),
                   (13, 9, 13, 15), (10, 12, 16, 12), (10.8, 9.8, 15.2, 14.2), (15.2, 9.8, 10.8, 14.2)),
    # Play the game: a cartridge with a play mark.
    'play_game': (_cartridge(3, 1, 9, 14, 2), (5.5, 5, 5.5, 11, 9.5, 8, 5.5, 5)),
    # The hollow play triangle of the hero Play button: this polyline is only the fallback, hero_picture draws it.
    'play_hollow_double': ((3, 1.5, 14.5, 8, 3, 14.5, 3, 1.5),),
    # Game memory: a memory chip.
    'memory_chip': (_rectangle(3.5, 3.5, 12.5, 12.5), _rectangle(6, 6, 10, 10),
                    (1, 5.5, 3.5, 5.5), (1, 8, 3.5, 8), (1, 10.5, 3.5, 10.5),
                    (12.5, 5.5, 15, 5.5), (12.5, 8, 15, 8), (12.5, 10.5, 15, 10.5),
                    (5.5, 1, 5.5, 3.5), (8, 1, 8, 3.5), (10.5, 1, 10.5, 3.5),
                    (5.5, 12.5, 5.5, 15), (8, 12.5, 8, 15), (10.5, 12.5, 10.5, 15)),
    # Convert / regenerate: every row, solid; Convert the selection: only the middle row solid, the others outlined.
    'convert_all': _filled(1, 1.5, 9, 4) + _filled(1, 6.5, 9, 9) + _filled(1, 11.5, 9, 14) + (_RUN,),
    'convert_selected': (_rectangle(1, 1.5, 9, 4),) + _filled(1, 6.5, 9, 9) + (_rectangle(1, 11.5, 9, 14), _RUN),
    # Retry the failures: the refresh arrows around an exclamation mark.
    'retry_failed': ((13, 5, 11, 2, 5, 2, 2, 5, 2, 8), (1, 5, 2, 8, 5, 7), (3, 11, 5, 14, 11, 14, 14, 11, 14, 8),
                     (11, 9, 14, 8, 15, 11), (8, 5.5, 8, 9), (8, 11, 8, 11)),
    # The video timing: a screen.
    'screen': (_rectangle(1, 2, 15, 11), (8, 11, 8, 14), (5, 14, 11, 14)),
    # Full screen: arrows out to the corners of a frame, and in from them to restore the window.
    'fullscreen_enter': (_rectangle(1, 1, 15, 15),) + _expand_arrows(False),
    'fullscreen_exit': (_rectangle(1, 1, 15, 15),) + _expand_arrows(True),
}

for _name, _paths in ICONS.items():
    ICON_PATHS.setdefault(_name, _paths)


# ---- The hero buttons' pictures: drawn with Pillow, at the size of the screen --------------------------------------
# A polyline one pixel wide cannot carry a gear or a bevelled triangle at the size of the main buttons, so these are
# drawn from our own shapes on a 26 x 26 grid, four times larger, then reduced (smooth edges, transparent background:
# the button's gold or grey shows through). No image file: they are rebuilt at start, for the scaling of the screen.
HERO_GRID = 26
SUPERSAMPLE = 4
# The picture of the hero Play button of Compiled Games: a big hollow play triangle, an outer and a thin inner outline
# with rounded corners (Arthur's pick of 19 Nov 2026, « a, double trait »; the bevel and pixel takes were dropped).
HERO_PLAY = 'play_hollow_double'
# The hero Convert / regenerate button: a gear and a play triangle (convert_all keeps its polylines as the fallback).
HERO_CONVERT = 'convert_all'

_TRIANGLE = ((5.0, 2.5), (23.0, 13.0), (5.0, 23.5))      # top left, tip, bottom left of the play triangle


def _mix(colour, other, amount):
    """`colour` moved `amount` of the way to `other` (both '#rrggbb')."""
    a, b = (tuple(int(value[index:index + 2], 16) for index in (1, 3, 5)) for value in (colour, other))
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def _scaled(points, factor, about=None):
    centre = about or (sum(x for x, _ in points) / len(points), sum(y for _, y in points) / len(points))
    return tuple((centre[0] + (x - centre[0]) * factor, centre[1] + (y - centre[1]) * factor) for x, y in points)


def _stroke(draw, points, width, colour, scale, closed=True):
    """A polyline of `width` grid units with round corners (a disc at each vertex)."""
    count = len(points)
    for index in range(count if closed else count - 1):
        a, b = points[index], points[(index + 1) % count]
        draw.line([(a[0] * scale, a[1] * scale), (b[0] * scale, b[1] * scale)], fill=colour, width=round(width * scale))
    radius = width * scale / 2
    for x, y in points:
        draw.ellipse([x * scale - radius, y * scale - radius, x * scale + radius, y * scale + radius], fill=colour)


def _gear(draw, centre, scale, colour, clear, body=5.2, tip=7.6, teeth=8, hole=2.1):
    import math
    cx, cy = centre
    draw.ellipse([(cx - body) * scale, (cy - body) * scale, (cx + body) * scale, (cy + body) * scale], fill=colour)
    for index in range(teeth):
        angle = index * 2 * math.pi / teeth
        ux, uy = math.cos(angle), math.sin(angle)
        vx, vy = -uy, ux
        inner, outer = body - 0.6, tip
        wide_in, wide_out = 1.8, 1.3
        corners = [(cx + ux * inner + vx * wide_in, cy + uy * inner + vy * wide_in),
                   (cx + ux * outer + vx * wide_out, cy + uy * outer + vy * wide_out),
                   (cx + ux * outer - vx * wide_out, cy + uy * outer - vy * wide_out),
                   (cx + ux * inner - vx * wide_in, cy + uy * inner - vy * wide_in)]
        draw.polygon([(x * scale, y * scale) for x, y in corners], fill=colour)
    draw.ellipse([(cx - hole) * scale, (cy - hole) * scale, (cx + hole) * scale, (cy + hole) * scale],
                 fill=clear)


def _convert(draw, scale, colour, highlight, clear):
    _gear(draw, (8.6, 13.0), scale, colour, clear)
    tip = [(18.0, 6.4), (25.4, 13.0), (18.0, 19.6)]
    draw.polygon([(x * scale, y * scale) for x, y in tip], fill=colour)


def _play_double(draw, scale, colour, highlight, clear):
    outer = _TRIANGLE
    _stroke(draw, outer, 2.5, colour, scale)
    _stroke(draw, _scaled(outer, 0.56, (9.5, 13.0)), 1.1, colour, scale)


DRAWERS = {HERO_CONVERT: _convert, 'play_hollow_double': _play_double}


# ---- The switch between the queue and Compiled Games: « la chaîne » (Arthur's pick of 19 Nov 2026, proposal A) ----
# A wide picture that tells the whole way: a cartridge, an arrow into the converter's gear, an arrow out to a game ready to
# play. The end the button leads to is lit and framed: the game in the queue (variant 'games'), the cartridge in Compiled
# Games (variant 'queue'); the other end is dim. A 52 x 24 grid drawn at 65 x 30 px at 100 % (SWITCH_GROW), on the dark
# button with its gold dashed border (gui_drawing: Compiled.Toolbar.TButton).
SWITCH_GRID = (52, 24)
SWITCH_GROW = 1.25
SWITCH_DIM, SWITCH_DARK = '#7d7d7d', '#191919'


class _Pen:
    """Shapes on the switch's grid, in pixels of the supersampled image (`k` pixels a grid unit)."""

    def __init__(self, draw, k):
        self.draw, self.k = draw, k

    def p(self, points):
        return [(x * self.k, y * self.k) for x, y in points]

    def poly(self, points, colour):
        self.draw.polygon(self.p(points), fill=colour)

    def line(self, points, colour, width):
        self.draw.line(self.p(points), fill=colour, width=max(1, round(width * self.k)))

    def box(self, x1, y1, x2, y2, radius, fill=None, outline=None, width=1.0):
        self.draw.rounded_rectangle(self.p([(x1, y1), (x2, y2)]), radius=radius * self.k, fill=fill, outline=outline,
                                    width=round(width * self.k) if outline else 0)

    def disc(self, cx, cy, r, colour):
        self.draw.ellipse(self.p([(cx - r, cy - r), (cx + r, cy + r)]), fill=colour)


def _switch_cartridge(pen, x, y, colour, w=7, h=9):
    pen.poly([(x, y), (x + w - 2, y), (x + w, y + 2), (x + w, y + h), (x, y + h)], colour)
    pen.box(x + 1.3, y + 1.6, x + w - 1.6, y + h * 0.55, 0.4, fill=SWITCH_DARK)
    for index in range(3):
        pen.box(x + 1.2 + index * 1.8, y + h - 1.6, x + 2.2 + index * 1.8, y + h - 0.2, 0, fill=SWITCH_DARK)


def _switch_gear(pen, cx, cy, colour, r=5.0, teeth=8):
    pen.disc(cx, cy, r * 0.72, colour)
    for index in range(teeth):
        angle = index * 2 * math.pi / teeth
        ux, uy = math.cos(angle), math.sin(angle)
        vx, vy = -uy, ux
        pen.poly([(cx + ux * r * 0.6 + vx * 1.1, cy + uy * r * 0.6 + vy * 1.1), (cx + ux * r + vx * 0.8, cy + uy * r + vy * 0.8),
                  (cx + ux * r - vx * 0.8, cy + uy * r - vy * 0.8), (cx + ux * r * 0.6 - vx * 1.1, cy + uy * r * 0.6 - vy * 1.1)],
                 colour)
    pen.disc(cx, cy, r * 0.3, SWITCH_DARK)


def _switch_arrow(pen, x1, x2, y, colour, width=1.3, head=2.4):
    pen.line([(x1, y), (x2 - head * 0.6, y)], colour, width)
    pen.poly([(x2 - head, y - head * 0.8), (x2, y), (x2 - head, y + head * 0.8)], colour)


def draw_switch(variant, scale=1.0, lit='#d4a737', frame='#f2d27a', dim=SWITCH_DIM):
    """The switch's picture for `variant` ('games': it leads to Compiled Games; 'queue': back to the queue) as a Pillow RGBA
    image, `scale` times its 100 % size. A greyed button passes `lit` and `frame` grey."""
    from PIL import Image, ImageDraw
    k = scale * SWITCH_GROW * SUPERSAMPLE
    width, height = (round(side * k) for side in SWITCH_GRID)
    clear = tuple(int(lit[index:index + 2], 16) for index in (1, 3, 5)) + (0,)
    image = Image.new('RGBA', (width, height), clear)
    pen = _Pen(ImageDraw.Draw(image), k)
    games = variant == 'games'
    near, far = (dim, lit) if games else (lit, dim)
    _switch_cartridge(pen, 1, 7.5, near)
    _switch_arrow(pen, 9.2, 15.5, 12, near)
    _switch_gear(pen, 21, 12, lit)
    _switch_arrow(pen, 27.5, 34.5, 12, far)
    pen.box(36.5, 6.5, 47.5, 17.5, 1.6, fill=far)
    pen.poly([(42 - 1.8, 12 - 2.6), (42 + 2.6, 12), (42 - 1.8, 12 + 2.6)], SWITCH_DARK)
    if games:
        pen.box(35.5, 5.5, 48.5, 18.5, 2.2, outline=frame, width=0.8)
    else:
        pen.box(0, 6.5, 9, 17.5, 1.6, outline=frame, width=0.8)
    return image.resize((round(width / SUPERSAMPLE), round(height / SUPERSAMPLE)), Image.Resampling.LANCZOS)


# ---- The two buttons in the middle of the bar (FEATURE_SIZE, 24 px at 100 %): richer pictures (Arthur, 20 Nov 2026) ----

def _feature_front_end(pen, colour):
    """Front-end, Arthur's pick « F3 »: a frame of four covers, the chosen one lit with its play mark, a small pad under it
    (the front-end played from the sofa)."""
    pen.box(1, 0.8, 23, 16.8, 2.0, outline=colour, width=1.5)
    for row in range(2):
        for col in range(2):
            x, y = 4.0 + col * 8.4, 3.6 + row * 6.4
            if (row, col) == (0, 1):
                pen.box(x - 0.3, y - 0.3, x + 7.5, y + 5.5, 0.9, fill=colour)
                cx, cy, size = x + 3.7, y + 2.6, 3.4
                pen.poly([(cx - size * 0.45, cy - size * 0.6), (cx + size * 0.6, cy), (cx - size * 0.45, cy + size * 0.6)],
                         SWITCH_DARK)
            else:
                pen.box(x, y, x + 7.2, y + 5.2, 0.8, outline=colour, width=1.1)
    pen.box(6.5, 18.6, 17.5, 23.4, 2.4, fill=colour)
    pen.box(8.3, 20.6, 11.1, 21.4, 0, fill=SWITCH_DARK)
    pen.box(9.3, 19.6, 10.1, 22.4, 0, fill=SWITCH_DARK)
    pen.disc(14.6, 20.3, 0.75, SWITCH_DARK)
    pen.disc(15.9, 21.8, 0.75, SWITCH_DARK)


def _feature_player(draw, k, cx, top, size, colour, outline=None):
    """A player: a round head over rounded shoulders (the top half of an ellipse), solid or in outline."""
    head = 3.9 * size
    hy = top + head
    sy = hy + head + 1.0 * size
    sw, sh = 7.6 * size, 14.0 * size
    width = round(outline * k) if outline else 0
    body = [(cx - sw) * k, sy * k, (cx + sw) * k, (sy + sh) * k]
    disc = [(cx - head) * k, (hy - head) * k, (cx + head) * k, (hy + head) * k]
    if outline:
        draw.chord(body, 180, 360, outline=colour, width=width)
        draw.ellipse(disc, outline=colour, width=width)
    else:
        draw.chord(body, 180, 360, fill=colour)
        draw.ellipse(disc, fill=colour)
    return head, hy, sy, sw, sh


def _feature_players(image, k, colour):
    """Multiplayer, Arthur's pick of 20 Nov 2026 (« P2, inversé »): two players, the one in front on the left and solid, the
    one behind on the right in outline. A clear gap around the one in front (transparent: right on the button's grey, its
    hover and its greyed look), a lighter rim on it from the top left."""
    from PIL import Image, ImageChops, ImageDraw
    behind = Image.new('RGBA', image.size, (0, 0, 0, 0))
    _feature_player(ImageDraw.Draw(behind), k, 16.0, 1.2, 0.86, colour, outline=1.3)
    gap = Image.new('L', image.size, 0)
    gap_draw = ImageDraw.Draw(gap)
    cx, top, size = 9.0, 5.2, 0.92
    head = 3.9 * size
    hy = top + head
    sy = hy + head + 1.0 * size
    sw, sh = 7.6 * size, 14.0 * size
    gap_draw.ellipse([(cx - head - 1.4) * k, (hy - head - 1.4) * k, (cx + head + 1.4) * k, (hy + head + 1.4) * k], fill=255)
    gap_draw.chord([(cx - sw - 1.4) * k, (sy - 1.4) * k, (cx + sw + 1.4) * k, (sy + sh + 1.4) * k], 180, 360, fill=255)
    alpha = ImageChops.subtract(behind.getchannel('A'), gap)
    behind.putalpha(alpha)
    image.alpha_composite(behind)
    draw = ImageDraw.Draw(image)
    _feature_player(draw, k, cx, top, size, colour)
    rim = _mix(colour, '#ffffff', 0.45)
    draw.arc([(cx - head + 0.7) * k, (hy - head + 0.7) * k, (cx + head - 0.7) * k, (hy + head - 0.7) * k], 195, 285, fill=rim,
             width=round(0.9 * k))
    draw.arc([(cx - sw + 0.8) * k, (sy + 0.8) * k, (cx + sw - 0.8) * k, (sy + sh - 0.8) * k], 190, 245, fill=rim,
             width=round(0.9 * k))


# A drawer takes a _Pen and the colour, or (an `image` drawer, listed in FEATURE_IMAGE) the image itself, `k` and the colour.
FEATURE_DRAWERS = {'front_end': _feature_front_end, 'players': _feature_players}
FEATURE_IMAGE = {'players'}


def feature_picture(master, symbol, colour):
    """The picture of a button in the middle of the bar as a Tk image, at FEATURE_SIZE times the toolbar's scale: drawn with
    Pillow when it has a drawing here, else its polylines two pixels thick (gui_drawing.hero_icon)."""
    from .gui_drawing import FEATURE_SIZE, hero_icon
    from .ui_fonts import toolbar_scale
    size = round(FEATURE_SIZE * toolbar_scale(master))
    if symbol not in FEATURE_DRAWERS:
        return hero_icon(master, symbol, colour, size=size)
    from PIL import Image, ImageDraw, ImageTk
    k = size / FEATURE_SIZE * SUPERSAMPLE
    clear = tuple(int(colour[index:index + 2], 16) for index in (1, 3, 5)) + (0,)
    image = Image.new('RGBA', (size * SUPERSAMPLE, size * SUPERSAMPLE), clear)
    if symbol in FEATURE_IMAGE:
        FEATURE_DRAWERS[symbol](image, k, colour)
    else:
        FEATURE_DRAWERS[symbol](_Pen(ImageDraw.Draw(image), k), colour)
    return ImageTk.PhotoImage(image.resize((size, size), Image.Resampling.LANCZOS), master=master)


def switch_picture(master, variant, greyed=False):
    """The switch's picture as a Tk image, sized for the screen's scaling up to 125 % (96 dpi: 65 x 30 px)."""
    from PIL import ImageTk
    from .ui_fonts import toolbar_scale
    colours = {'lit': '#6a6a6a', 'frame': '#7a7a7a', 'dim': '#4a4a4a'} if greyed else {}
    return ImageTk.PhotoImage(draw_switch(variant, toolbar_scale(master), **colours), master=master)


def draw_picture(name, colour, size=HERO_GRID, highlight=None):
    """The hero picture `name` as a Pillow RGBA image of `size` px: `colour` for the drawing, `highlight` for the lighter
    edge of the bevelled take (a lighter shade of `colour` when not given)."""
    from PIL import Image, ImageDraw
    big = size * SUPERSAMPLE
    # Transparent, but in the drawing's own colour: reducing the picture then leaves no dark fringe round it.
    clear = tuple(int(colour[index:index + 2], 16) for index in (1, 3, 5)) + (0,)
    image = Image.new('RGBA', (big, big), clear)
    DRAWERS[name](ImageDraw.Draw(image), big / HERO_GRID, colour, highlight or _mix(colour, '#ffffff', 0.45), clear)
    return image.reduce(SUPERSAMPLE)                    # an exact average of 4 x 4 samples: no ringing


# ---- Convert, after Arthur's mock-up (20 Nov 2026): gold line art on the dark button, on a 124 x 30 grid ------------------
CONVERT_GRID = (124, 30)


def _convert_gear(pen, cx, cy, r, colour, clear, phase):
    pen.disc(cx, cy, r * 0.74, colour)
    for i in range(8):
        a = phase + i * math.pi / 4
        ux, uy, vx, vy = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
        pen.poly([(cx + ux * r * 0.6 + vx * r * 0.25, cy + uy * r * 0.6 + vy * r * 0.25),
                  (cx + ux * r + vx * r * 0.17, cy + uy * r + vy * r * 0.17),
                  (cx + ux * r - vx * r * 0.17, cy + uy * r - vy * r * 0.17),
                  (cx + ux * r * 0.6 - vx * r * 0.25, cy + uy * r * 0.6 - vy * r * 0.25)], colour)
    pen.disc(cx, cy, r * 0.40, clear)


def _convert_arrow(pen, x, cy, colour, w=8.0):
    pen.line([(x, cy), (x + w - 1.4, cy)], colour, 2.0)
    pen.poly([(x + w - 3.8, cy - 3.6), (x + w, cy), (x + w - 3.8, cy + 3.6), (x + w - 5.1, cy + 2.3), (x + w - 2.6, cy),
              (x + w - 5.1, cy - 2.3)], colour)


def _convert_digit(pen, x, y, char, colour, clear, w=4.6, h=7.0, t=1.5):
    if char == '0':
        pen.box(x, y, x + w, y + h, 1.0, fill=colour)
        pen.box(x + t, y + t, x + w - t, y + h - t, 0.3, fill=clear)
    else:
        mid = x + w / 2
        pen.box(mid - t / 2, y, mid + t / 2, y + h, 0, fill=colour)
        pen.poly([(mid - t / 2, y), (mid + t / 2 - 0.1, y), (mid - t / 2, y + 2.0), (x + 0.4, y + 2.0), (x + 0.4, y + 1.2)],
                 colour)
        pen.box(x + 0.3, y + h - t, x + w - 0.3, y + h, 0, fill=colour)


def draw_convert(colour, scale=1.0):
    """Convert's picture, from left to right: a cartridge (its outline, its label, the edge at its foot), an arrow, two
    meshing gears (a big one up left, a small one down right), an arrow, the game as bits (010 / 101 / 010) and a solid play
    mark; in `colour`, the rest transparent (the button's dark face shows through the gears' holes)."""
    from PIL import Image, ImageDraw
    k = scale * SUPERSAMPLE
    width, height = (round(side * k) for side in CONVERT_GRID)
    clear = tuple(int(colour[index:index + 2], 16) for index in (1, 3, 5)) + (0,)
    image = Image.new('RGBA', (width, height), clear)
    pen = _Pen(ImageDraw.Draw(image), k)              # ImageDraw writes, never blends: `clear` cuts the holes
    pen.box(0.8, 3.5, 19.2, 26.5, 2.6, outline=colour, width=1.7)
    pen.box(4.0, 6.6, 16.0, 20.0, 0.6, outline=colour, width=1.3)
    pen.line([(4.6, 9.2), (15.4, 9.2)], colour, 1.0)
    pen.box(3.4, 21.6, 16.6, 24.0, 0.6, fill=colour)
    _convert_arrow(pen, 24.0, 15.0, colour)
    _convert_gear(pen, 46.0, 11.2, 10.4, colour, clear, math.pi / 8)
    pen.disc(58.6, 22.0, 8.6, clear)                 # a dark gap round the small gear
    _convert_gear(pen, 58.6, 22.0, 7.4, colour, clear, 0.0)
    _convert_arrow(pen, 70.0, 15.0, colour)
    for row, bits in enumerate(('010', '101', '010')):
        for col, char in enumerate(bits):
            _convert_digit(pen, 84.0 + col * 6.6, 3.6 + row * 8.2, char, colour, clear)
    pen.poly([(110.5, 4.5), (123.2, 15.0), (110.5, 25.5)], colour)
    return image.resize((round(width / SUPERSAMPLE), round(height / SUPERSAMPLE)), Image.Resampling.LANCZOS)


def hero_picture(master, symbol, colour, highlight=None):
    """The picture of `symbol` for a hero button, as a Tk image: drawn with Pillow when it has a drawing here, else its
    polylines drawn larger and thicker (gui_drawing.hero_icon). Sized for the screen's scaling (96 dpi: HERO_SIZE, 30 px)."""
    from PIL import ImageTk
    from .ui_fonts import toolbar_scale
    if symbol == HERO_CONVERT:                      # Convert's wide line art, after Arthur's mock-up
        return ImageTk.PhotoImage(draw_convert(colour, toolbar_scale(master)), master=master)
    if symbol not in DRAWERS:
        from .gui_drawing import hero_icon
        return hero_icon(master, symbol, colour)
    from .gui_drawing import HERO_SIZE
    return ImageTk.PhotoImage(draw_picture(symbol, colour, round(HERO_SIZE * toolbar_scale(master)), highlight), master=master)
