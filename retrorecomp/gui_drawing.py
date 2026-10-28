"""Drawing helpers of the interface: portraits, styled names, pins, badges, header themes and icons."""
from __future__ import annotations

import os
import time
import tkinter as tk

from . import online
from .branding import COLORS, make_icon, ICON_PATHS


HATCH_SPACING = 4
# The header artwork is drawn smaller than its 600 x 132 source.
HEADER_SCALE = 0.6
HEADER_HEIGHT = round(132 * HEADER_SCALE)
PORTRAIT_SIZE = 44


# Thousands separator and decimal mark of each interface language.
NUMBER_MARKS = {'en': (',', '.'), 'fr': ('\u00a0', ','), 'it': ('.', ','), 'es': ('.', ','),
                'de': ('.', ','), 'ru': ('\u00a0', ','), 'ja': (',', '.'), 'zh': (',', '.')}


def compact_number(value, language='en', threshold=100_000):
    """A score for the header and the board: grouped digits below 100,000 (12,345),
    then thousands (110.9K) and millions (1.2M) with one decimal, cut rather
    than rounded so a figure is never shown above what it is. A tight place
    can lower the threshold."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return str(value)
    group, mark = NUMBER_MARKS.get(language, NUMBER_MARKS['en'])
    sign, number = ('-' if number < 0 else ''), abs(number)
    if number < threshold:
        return sign + f'{number:,}'.replace(',', group)
    unit, divisor = ('K', 1_000) if number < 1_000_000 else ('M', 1_000_000)
    tenths = number * 10 // divisor
    whole, tenth = divmod(tenths, 10)
    return f"{sign}{whole}{mark + str(tenth) if tenth else ''}{unit}"


def _scaled_photo(path, master, scale=HEADER_SCALE):
    """Header artwork at its displayed size, resampled smoothly."""
    from PIL import Image, ImageTk
    with Image.open(path) as image:
        size = (round(image.width * scale), round(image.height * scale))
        return ImageTk.PhotoImage(image.convert('RGBA').resize(size, Image.Resampling.LANCZOS), master=master)


def _portrait_photo(master, raw=None, initial='', frame=None):
    """The header's portrait as a Tk picture (see _portrait_picture)."""
    from PIL import ImageTk
    return ImageTk.PhotoImage(_portrait_picture(raw, initial, frame), master=master)


def frame_side(hole, portrait=PORTRAIT_SIZE):
    """The side of a shop frame drawn around a `portrait` px portrait: the
    portrait covers the frame's hole and a little of its inner rim, so the
    frame is portrait / (hole x 1.04), rounded down to the portrait's parity
    (both stay centred on whole pixels). None for an unusable hole."""
    try:
        hole = float(hole)
    except (TypeError, ValueError):
        return None
    if not 0.2 <= hole <= 1.0:
        return None
    side = int(portrait / (hole * 1.04))
    if (side - portrait) % 2:
        side -= 1
    return max(side, portrait)


def _framed(picture, frame, portrait=PORTRAIT_SIZE):
    """The frame image (bytes, hole) at its larger size with the round
    portrait (a PIL picture drawn at 4x) composited ON TOP, centred; None
    when the frame cannot be drawn."""
    from PIL import Image
    import io
    raw, hole = frame
    side = frame_side(hole, portrait)
    if not raw or side is None:
        return None
    scale = picture.width // portrait
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if max(image.size) > 4096:
                return None
            ring = image.convert('RGBA').resize((side * scale, side * scale), Image.Resampling.LANCZOS)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    offset = (side - portrait) * scale // 2
    ring.alpha_composite(picture, (offset, offset))
    return ring.resize((side, side), Image.Resampling.LANCZOS)


def _portrait_picture(raw=None, initial='', frame=None):
    """A round player portrait: the server's WebP when there is one, else a
    quiet disc with the player's initial, ringed in gold. With an equipped
    shop `frame` (image bytes, hole ratio) the portrait keeps its 44 px and
    the frame is drawn larger behind it, in one picture."""
    from PIL import Image, ImageDraw
    import io
    size = PORTRAIT_SIZE * 4
    if raw:
        try:
            with Image.open(io.BytesIO(raw)) as image:
                picture = image.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            raw = None
    if not raw:
        picture = Image.new('RGBA', (size, size), COLORS['button'])
        if not initial:
            # Nobody signed in: a pixel-art question mark in gold.
            mark = ('.XXXXX.', 'XX...XX', '.....XX', '....XX.', '...XX..', '...XX..', '.......', '...XX..')
            # Blocks of 3 display pixels, aligned to the 4x drawing grid so
            # the final downscale keeps them sharp.
            cell = 12
            left = (size - cell * len(mark[0])) // 8 * 4
            top = (size - cell * len(mark)) // 8 * 4
            draw = ImageDraw.Draw(picture)
            for y, row in enumerate(mark):
                for x, pixel in enumerate(row):
                    if pixel == 'X':
                        draw.rectangle((left + x * cell, top + y * cell, left + (x + 1) * cell - 1,
                                        top + (y + 1) * cell - 1), fill=COLORS['gold'])
        if initial:
            from PIL import ImageFont
            try:
                font = ImageFont.truetype('segoeuib.ttf' if os.name == 'nt' else 'DejaVuSans-Bold.ttf', size // 2)
            except OSError:
                font = ImageFont.load_default()
            ImageDraw.Draw(picture).text((size / 2, size / 2), initial.upper(), fill=COLORS['gold'],
                                         font=font, anchor='mm')
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    picture.putalpha(mask)
    framed = _framed(picture, frame) if frame else None
    if framed is not None:
        return framed
    ImageDraw.Draw(picture).ellipse((2, 2, size - 3, size - 3), outline=COLORS['gold'], width=6)
    return picture.resize((PORTRAIT_SIZE, PORTRAIT_SIZE), Image.Resampling.LANCZOS)


def _tint(base: str, foreground: str, visibility: float = 0.50) -> str:
    """Blend a procedural decoration over the canvas background."""
    channel = lambda color, at: int(color[at:at + 2], 16)
    values = [round(channel(base, at) * (1 - visibility) +
                    channel(foreground, at) * visibility) for at in (1, 3, 5)]
    return '#{:02x}{:02x}{:02x}'.format(*values)


# --- RR coin shop: what the converter draws of the equipped items -----------
# (bought and equipped on the site; the catalog's `data` says how to draw.)
def _colour(value, fallback):
    """A '#rrggbb' colour from the catalog, else the fallback."""
    if isinstance(value, str) and len(value) == 7 and value[0] == '#':
        try:
            int(value[1:], 16)
            return value.lower()
        except ValueError:
            pass
    return fallback


NAME_GOLD, NAME_AMBER, NAME_LIGHT = '#ffd24a', '#ff9a1f', '#fff4c2'
# The sparkling name: a light band sweeps slowly across the gold, a few
# frames a second, and only while the window is shown.
SPARKLE_PERIOD = 3.2
SPARKLE_FRAME = 150


def name_colours(style, count, phase=None):
    """Per-character colours of a pseudonym in its shop style (gold, gold to
    amber gradient, sparkling gold at `phase` in [0, 1)); None when the name
    keeps the interface colour."""
    data = style.get('data') if isinstance(style, dict) else None
    kind = data.get('style') if isinstance(data, dict) else None
    if kind not in ('gold', 'gradient', 'sparkle') or count <= 0:
        return None
    colours = data.get('colors') if isinstance(data.get('colors'), list) else []
    first = _colour(colours[0] if colours else None, NAME_GOLD)
    second = _colour(colours[1] if len(colours) > 1 else None, NAME_AMBER if kind == 'gradient' else NAME_LIGHT)
    if kind == 'gold':
        return [first] * count
    if kind == 'gradient':
        return [_tint(first, second, index / (count - 1) if count > 1 else 0.0) for index in range(count)]
    if phase is None:
        return [first] * count
    # The band crosses the name in the first part of the period, then rests.
    centre = -0.3 + 2.2 * (phase % 1.0)
    return [_tint(first, second, 0.85 * max(0.0, 1 - abs((index + 0.5) / count - centre) / 0.3))
            for index in range(count)]


def _glyphs(text):
    """Characters as drawn, combining marks kept with their letter."""
    import unicodedata
    glyphs = []
    for character in text:
        if glyphs and (unicodedata.combining(character) or character in '‍︎️'):
            glyphs[-1] += character
        else:
            glyphs.append(character)
    return glyphs


def _font(canvas, spec):
    """A measurable Tk font for a font tuple, kept on the canvas."""
    from tkinter import font as tkfont
    fonts = canvas.__dict__.setdefault('_shop_fonts', {})
    key = tuple(spec)
    if key not in fonts:
        family_name, size, *rest = spec
        fonts[key] = tkfont.Font(canvas, family=family_name, size=size,
                                 weight='bold' if 'bold' in rest else 'normal')
    return fonts[key]


def elide(font, text, width):
    """`text` shortened with an ellipsis to fit `width` pixels."""
    if width <= 0 or font.measure(text) <= width:
        return text
    while text and font.measure(text + '…') > width:
        text = text[:-1]
    return text + '…' if text else ''


def draw_styled_text(canvas, x, y, text, font, style, anchor='nw', tags=(), fill=None):
    """Draw a pseudonym on a canvas in its shop style: one item per character
    for a coloured style (a sparkling one is animated by start_sparkle), one
    plain item otherwise. `anchor`: 'nw', 'ne', 'n' (y = top) or 'w', 'e',
    'center' (y = middle). Returns (items, width)."""
    measure = _font(canvas, font)
    width = measure.measure(text)
    glyphs = _glyphs(text)
    colours = name_colours(style, len(glyphs))
    if not colours:
        item = canvas.create_text(x, y, text=text, anchor=anchor, font=font, tags=tags,
                                  fill=fill or COLORS['text'])
        return [item], width
    left = x if anchor in ('nw', 'w') else x - width if anchor in ('ne', 'e') else x - width / 2
    vertical = 'nw' if anchor in ('n', 'nw', 'ne') else 'w'
    items, done = [], ''
    sparkle = (style.get('data') or {}).get('style') == 'sparkle'
    entries = canvas.__dict__.setdefault('_sparkle', [])
    for index, glyph in enumerate(glyphs):
        item = canvas.create_text(left + measure.measure(done), y, text=glyph, anchor=vertical, font=font,
                                  fill=colours[index], tags=tags)
        items.append(item)
        done += glyph
        if sparkle:
            entries.append((item, index, len(glyphs), style))
    if sparkle:
        start_sparkle(canvas)
    return items, width


def sparkle_frame(canvas, now=None):
    """Recolour the sparkling names of a canvas once; False when nothing is
    left to animate or the window is hidden (the animation then stops)."""
    entries = [entry for entry in getattr(canvas, '_sparkle', ()) if canvas.type(entry[0])]
    canvas._sparkle = entries
    if not entries or not canvas.winfo_viewable():
        return False
    phase = ((time.monotonic() if now is None else now) % SPARKLE_PERIOD) / SPARKLE_PERIOD
    palettes = {}
    for item, index, count, style in entries:
        key = (id(style), count)
        if key not in palettes:
            palettes[key] = name_colours(style, count, phase)
        canvas.itemconfigure(item, fill=palettes[key][index])
    return True


def start_sparkle(canvas):
    """Animate the canvas's sparkling names at a few frames a second; hidden
    (minimised or withdrawn), the animation stops and resumes once shown."""
    if getattr(canvas, '_sparkle_job', None):
        return
    top = canvas.winfo_toplevel()
    if not getattr(canvas, '_sparkle_resume', False):
        canvas._sparkle_resume = True
        top.bind('<Map>', lambda event: start_sparkle(canvas)
                 if event.widget is top and canvas.winfo_exists() else None, add='+')
    def tick():
        canvas._sparkle_job = None
        try:
            if canvas.winfo_exists() and sparkle_frame(canvas):
                canvas._sparkle_job = canvas.after(SPARKLE_FRAME, tick)
        except tk.TclError:
            pass
    canvas._sparkle_job = canvas.after(SPARKLE_FRAME, tick)


# The site's pin: a small pixel trophy in its tier's colour.
PIN = ('X.XXX.X', 'X.XXX.X', '.XXXXX.', '..XXX..', '...X...', '..XXX..', '.XXXXX.')
PIN_CELL = 2
PIN_SIZE = len(PIN) * PIN_CELL
PIN_COLOURS = {'bronze': '#cd7f32', 'silver': '#c0c7d1', 'gold': '#ffd24a'}


def draw_pin(canvas, x, y, pin, tags=()):
    """The equipped pin with its top-left corner at (x, y); its width."""
    data = pin.get('data') if isinstance(pin, dict) else None
    if not isinstance(data, dict):
        return 0
    colour = _colour(data.get('color'), PIN_COLOURS.get(data.get('tier'), COLORS['gold']))
    for row, line in enumerate(PIN):
        for column, cell in enumerate(line):
            if cell == 'X':
                canvas.create_rectangle(x + column * PIN_CELL, y + row * PIN_CELL, x + (column + 1) * PIN_CELL,
                                        y + (row + 1) * PIN_CELL, fill=colour, outline='', tags=tags)
    return PIN_SIZE


def _rounded(canvas, x0, y0, x1, y1, radius, **options):
    points = (x0 + radius, y0, x1 - radius, y0, x1, y0, x1, y0 + radius, x1, y1 - radius, x1, y1,
              x1 - radius, y1, x0 + radius, y1, x0, y1, x0, y1 - radius, x0, y0 + radius, x0, y0)
    return canvas.create_polygon(points, smooth=True, **options)


BADGE_HEIGHT = 14


def badges_width(canvas, badges, font):
    measure = _font(canvas, font)
    labels = [_badge_label(badge) for badge in badges[:online.SHOP_BADGES]]
    return sum(measure.measure(label) + 8 for label in labels) + 3 * max(0, len(labels) - 1)


def _badge_label(badge):
    data = badge.get('data') or {}
    label = data.get('label') if isinstance(data.get('label'), str) else data.get('console')
    return str(label or badge.get('id', ''))[:6].upper()


def draw_badges(canvas, x, middle, badges, font, tags=(), top=()):
    """The console badge shown (online.SHOP_BADGES, one since 26 October
    2026), a small rounded label in the console's colour, from x at the height
    `middle`; their total width. A badge whose id is in `top` (online.top_badges:
    the player is first on that console's all-time board) gets a gold rim and a
    small "1", the same mark in the header, the ranking and the podium."""
    measure = _font(canvas, font)
    start = x
    for badge in badges[:online.SHOP_BADGES]:
        label = _badge_label(badge)
        width = measure.measure(label) + 8
        colour = _colour((badge.get('data') or {}).get('color'), COLORS['button'])
        _rounded(canvas, x, middle - BADGE_HEIGHT / 2, x + width, middle + BADGE_HEIGHT / 2, 4,
                 fill=colour, outline=_tint(colour, '#ffffff', 0.25), tags=tags)
        canvas.create_text(x + width / 2, middle, text=label, fill='#ffffff', font=font, tags=tags)
        if badge.get('id') in top:
            _rounded(canvas, x - 1, middle - BADGE_HEIGHT / 2 - 1, x + width + 1, middle + BADGE_HEIGHT / 2 + 1, 5,
                     fill='', outline=COLORS['gold'], width=1, tags=tags)
            canvas.create_text(x + width + 1, middle - BADGE_HEIGHT / 2 - 1, text='1', fill=COLORS['gold_hover'],
                               font=(font[0], 6, 'bold'), anchor='center', tags=tags)
        x += width + 3
    return max(0, x - 3 - start)


# Header band variants of the shop (classic is the interface's own): top
# and bottom of a vertical gradient, and an accent for the raster.
HEADER_THEMES = {'neon': ('#1a0b33', '#3a0f5c', '#ff3fd2'), 'night': ('#0a1022', '#18213d', '#7aa2ff'),
                 'gold': ('#3a2a06', '#6b4c0c', '#ffd24a')}


def header_theme(item):
    """(theme, top, bottom, accent) of an equipped header theme; None for the
    classic band (or without one)."""
    data = item.get('data') if isinstance(item, dict) else None
    kind = data.get('theme') if isinstance(data, dict) else None
    if not isinstance(kind, str) or kind == 'classic':
        return None
    known = HEADER_THEMES.get(kind)
    colours = data.get('colors') if isinstance(data.get('colors'), list) else []
    if len(colours) < 3 and not known:
        return None
    known = known or (COLORS['header'], COLORS['header'], COLORS['gold'])
    return (kind, *(_colour(colours[index] if index < len(colours) else None, known[index]) for index in range(3)))


# Pixel trophy of the knowledge 'achievement' card ('o': highlight).
TROPHY = ('..XXXXXXXX..', 'XXXoXXXXXXXX', 'X.XoXXXXXX.X', 'X.XoXXXXXX.X',
          '.XXXXXXXXXX.', '..XXXXXXXX..', '...XXXXXX...', '.....XX.....',
          '.....XX.....', '....XXXX....', '...XXXXXX...', '...XXXXXX...')


BADGE_COLOR = '#e5484d'


def badged_icon(master, symbol, color, size=18):
    """The picture of `symbol` with a small dot at its top right corner: the
    update button's way of saying that something is new."""
    image = make_icon(master, symbol, color, size)
    centre_x, centre_y = size - 4, 3
    for dy in range(-3, 4):
        reach = round((9.5 - dy * dy) ** 0.5 - 0.5)
        left, right = max(0, centre_x - reach), min(size - 1, centre_x + reach)
        if 0 <= centre_y + dy < size and left <= right:
            image.put(BADGE_COLOR, to=(left, centre_y + dy, right + 1, centre_y + dy + 1))
    return image


# The closing card: a cartridge sends its discoveries to the shared base.
CARTRIDGE = ('XXXXXXX.', 'X.....XX', 'X.ooo..X', 'X.ooo..X', 'X.ooo..X',
             'X......X', 'XXXXXXXX', 'X.X.X.XX')
CLOUD = ('....XXX.....', '..XXoooXX...', '.XooooooXXX.', 'XoooooooooXX',
         'XooooooooooX', '.XXXXXXXXXX.')


# Interface-only icons: branding.py is a shared compiler input.
ICON_PATHS.setdefault('download', ((8, 1, 8, 10), (4, 6, 8, 10, 12, 6), (1, 10, 1, 14, 15, 14, 15, 10)))
# Adding a folder of ROMs (a cartridge) or of converted games (a play sign),
# and New paths (a rising route, distinct from the refresh arrows).
_FOLDER_PLUS = ((1, 4, 6, 4, 8, 6, 15, 6, 15, 15, 1, 15, 1, 4), (11, 0, 11, 4), (9, 2, 13, 2))
ICON_PATHS.setdefault('add_rom_folder', _FOLDER_PLUS + ((5, 8, 11, 8, 11, 13, 5, 13, 5, 8), (6, 10, 10, 10),
                                                        (7, 13, 7, 14), (9, 13, 9, 14)))
ICON_PATHS.setdefault('add_exe_folder', _FOLDER_PLUS + ((6, 8, 11, 11, 6, 14, 6, 8),))
ICON_PATHS.setdefault('new_paths', ((1, 14, 5, 9, 9, 11, 14, 4), (10, 4, 14, 4, 14, 8)))


def _toolbar_styles(style):
    """Collection navigation stays within interface-only compiler inputs."""
    c = COLORS
    # Toolbar buttons take their natural width instead of the theme's
    # eleven-character minimum, so the bar fits every language.
    for name in ('Toolbar.TButton', 'Toolbar.Primary.TButton'):
        style.configure(name, width=-1)
    # The header's small controls: selectors and the account's two buttons.
    style.configure('Header.TButton', width=-1, padding=(7, 2))
    style.configure('Help.Toolbar.TButton', width=-1, padding=(11, 5), foreground=c['gold'],
                    font=('TkDefaultFont', 10, 'bold'))
    style.configure('Header.TCombobox', padding=(4, 1))
    style.configure('Compiled.Toolbar.TButton', background=c['gold'], foreground=c['gold_text'],
                    bordercolor=c['gold_hover'], lightcolor=c['gold'], darkcolor=c['gold'],
                    focuscolor=c['gold_text'], relief='raised')
    style.map('Compiled.Toolbar.TButton',
              background=[('disabled', c['panel']), ('selected', c['gold_hover']),
                          ('pressed', c['gold_hover']), ('active', c['gold_hover'])],
              foreground=[('disabled', c['disabled']), ('!disabled', c['gold_text'])],
              bordercolor=[('disabled', c['border']), ('!disabled', c['gold_hover'])],
              lightcolor=[('disabled', c['panel']), ('selected', c['gold_hover']), ('active', c['gold_hover'])],
              darkcolor=[('disabled', c['panel']), ('selected', c['gold_hover']), ('active', c['gold_hover'])],
              relief=[('selected', 'sunken'), ('pressed', 'sunken')])
