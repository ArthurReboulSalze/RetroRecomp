"""Rounded shapes for the converter's windows (the Multiplayer window first, Arthur's proposal A of 19 Nov 2026).

Tk has no rounded corners. Here they are pictures drawn with Pillow at four times the size and reduced, so edges are smooth:
- `Look` makes rounded ttk styles (a card, a pill button, a segmented toggle) as 9-slice `image` elements. The widgets stay ttk
  widgets: focus, Tab and the gamepad's focus moves, any text length and every interface language work as for any button.
- `RoundButton` is the big round action button (an emergency-stop look): a Canvas with a Pillow face and its label in Tk
  text. It takes the focus; Return, space and a click press it; a dotted gold ring shows the focus.
- small pictures: a status dot, an avatar disc, signal bars, a few line icons.
ttk element names are global to the Tk interpreter, so each `Look` tags its elements; style names stay readable."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter, ImageTk

S = 4                    # supersampling


def rgb(colour):
    colour = colour.lstrip('#')
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def rounded_box(w, h, r, fill, bg, outline=None, width=1):
    image = Image.new('RGB', (w * S, h * S), rgb(bg))
    ImageDraw.Draw(image).rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=r * S, fill=rgb(fill),
                                            outline=rgb(outline) if outline else None, width=width * S if outline else 0)
    return image.resize((w, h), Image.LANCZOS)


class Look:
    """The rounded ttk styles of one window; keeps its pictures alive as long as the window."""
    count = 0

    def __init__(self, master, colours, font):
        self.master, self.c, self.font = master, colours, font
        self.images = []
        self.style = ttk.Style(master)
        Look.count += 1
        self.tag = f'rr{Look.count}'
        self.made = set()

    def photo(self, image):
        picture = ImageTk.PhotoImage(image, master=self.master)
        self.images.append(picture)
        return picture

    def _element(self, name, *specs, border, padding=None):
        element = f'{name}.{self.tag}.bg'
        options = {'border': border, 'sticky': 'nsew'}
        if padding is not None:
            options['padding'] = padding
        self.style.element_create(element, 'image', *specs, **options)
        self.made.add(name)
        return element

    def card(self, name, fill, bg, radius=14, outline=None):
        """A rounded frame style 'name.TFrame' (9-slice: any size)."""
        size = radius * 2 + 4
        element = self._element(name, self.photo(rounded_box(size, size, radius, fill, bg, outline)), border=radius + 1)
        self.style.layout(f'{name}.TFrame', [(element, {'sticky': 'nsew'})])
        return f'{name}.TFrame'

    def pill_button(self, name, fill, hover, text, bg, radius=12, *, disabled=None, outline=None, size=10, bold=False,
                    padding=(12, 5)):
        """A rounded button style 'name.TButton'; disabled is greyed."""
        edge = radius * 2 + 4
        normal = self.photo(rounded_box(edge, edge, radius, fill, bg, outline))
        active = self.photo(rounded_box(edge, edge, radius, hover, bg, outline))
        greyed = self.photo(rounded_box(edge, edge, radius, disabled or self.c['panel'], bg))
        element = self._element(name, normal, ('disabled', greyed), ('active', active), ('pressed', active),
                                border=radius + 1, padding=2)
        self.style.layout(f'{name}.TButton', [(element, {'sticky': 'nsew', 'children': [
            ('Button.padding', {'sticky': 'nsew', 'children': [('Button.label', {'sticky': 'nsew'})]})]})])
        self.style.configure(f'{name}.TButton', foreground=text, padding=padding, anchor='center',
                             font=(self.font, size, 'bold' if bold else 'normal'), focuscolor=self.c['gold'])
        self.style.map(f'{name}.TButton', foreground=[('disabled', self.c['disabled'])])
        return f'{name}.TButton'

    def segment(self, name, track, chosen, hover, radius=13, size=10):
        """A segmented toggle: Radiobuttons whose chosen one is a gold pill on a dark track (put them in a `track` card)."""
        edge = radius * 2 + 4
        off = self.photo(rounded_box(edge, edge, radius, track, track))
        on = self.photo(rounded_box(edge, edge, radius, chosen, track))
        over = self.photo(rounded_box(edge, edge, radius, hover, track))
        element = self._element(name, off, ('selected', on), ('active', over), border=radius + 1, padding=2)
        self.style.layout(f'{name}.TRadiobutton', [(element, {'sticky': 'nsew', 'children': [
            ('Radiobutton.padding', {'sticky': 'nsew', 'children': [('Radiobutton.label', {'sticky': 'nsew'})]})]})])
        self.style.configure(f'{name}.TRadiobutton', foreground=self.c['muted'], padding=(16, 5), anchor='center',
                             font=(self.font, size, 'bold'), focuscolor=self.c['gold'])
        self.style.map(f'{name}.TRadiobutton', foreground=[('disabled', self.c['disabled']),
                                                          ('selected', self.c['gold_text']), ('active', self.c['text'])])
        return f'{name}.TRadiobutton'

    # ---- small pictures ----

    def dot(self, colour, bg, size=12):
        image = Image.new('RGB', (size * S, size * S), rgb(bg))
        ImageDraw.Draw(image).ellipse((S, S, size * S - S, size * S - S), fill=rgb(colour))
        return self.photo(image.resize((size, size), Image.LANCZOS))

    def avatar(self, colour, bg, size=30):
        image = Image.new('RGB', (size * S, size * S), rgb(bg))
        ImageDraw.Draw(image).ellipse((0, 0, size * S - 1, size * S - 1), fill=rgb(colour))
        return self.photo(image.resize((size, size), Image.LANCZOS))

    def bars(self, level, on, off, bg, size=14):
        image = Image.new('RGB', (size * S, size * S), rgb(bg))
        draw = ImageDraw.Draw(image)
        for i in range(4):
            h, x = (i + 1) * size * S // 4, i * size * S // 4
            draw.rounded_rectangle((x + S, size * S - h, x + size * S // 4 - S, size * S - 1), radius=S,
                                   fill=rgb(on if i < level else off))
        return self.photo(image.resize((size, size), Image.LANCZOS))

    def icon(self, kind, colour, bg, size=16):
        image = Image.new('RGB', (size * S, size * S), rgb(bg))
        draw_icon(ImageDraw.Draw(image), kind, size * S / 2, size * S / 2, size * S * 0.42, rgb(colour), S * 1.6)
        return self.photo(image.resize((size, size), Image.LANCZOS))


def draw_icon(draw, kind, cx, cy, r, colour, width):
    w = max(1, round(width))
    thin = max(1, w // 2)
    if kind == 'tick':
        draw.line([(cx - r * 0.75, cy + r * 0.02), (cx - r * 0.2, cy + r * 0.55), (cx + r * 0.8, cy - r * 0.55)], fill=colour,
                  width=w, joint='curve')
    elif kind == 'play':
        draw.polygon([(cx - r * 0.5, cy - r * 0.75), (cx + r * 0.8, cy), (cx - r * 0.5, cy + r * 0.75)], fill=colour)
    elif kind == 'wait':           # an hourglass
        draw.line([(cx - r * 0.55, cy - r * 0.8), (cx + r * 0.55, cy - r * 0.8)], fill=colour, width=w)
        draw.line([(cx - r * 0.55, cy + r * 0.8), (cx + r * 0.55, cy + r * 0.8)], fill=colour, width=w)
        draw.polygon([(cx - r * 0.45, cy - r * 0.7), (cx + r * 0.45, cy - r * 0.7), (cx, cy)], outline=colour, width=thin)
        draw.polygon([(cx - r * 0.45, cy + r * 0.7), (cx + r * 0.45, cy + r * 0.7), (cx, cy)], fill=colour)
    elif kind == 'stop':           # refused: an exclamation mark
        draw.line([(cx, cy - r * 0.8), (cx, cy + r * 0.25)], fill=colour, width=round(w * 1.2))
        d = w * 0.8
        draw.ellipse((cx - d, cy + r * 0.6 - d, cx + d, cy + r * 0.6 + d), fill=colour)
    elif kind == 'copy':
        draw.rounded_rectangle((cx - r * 0.4, cy - r * 0.7, cx + r * 0.75, cy + r * 0.45), radius=r * 0.15, outline=colour,
                               width=thin)
        draw.rounded_rectangle((cx - r * 0.75, cy - r * 0.35, cx + r * 0.4, cy + r * 0.8), radius=r * 0.15, outline=colour,
                               width=thin)
    elif kind == 'globe':
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=colour, width=thin)
        draw.ellipse((cx - r * 0.45, cy - r, cx + r * 0.45, cy + r), outline=colour, width=thin)
        draw.line([(cx - r, cy), (cx + r, cy)], fill=colour, width=thin)
    elif kind == 'home':
        draw.polygon([(cx - r * 0.9, cy - r * 0.05), (cx, cy - r * 0.85), (cx + r * 0.9, cy - r * 0.05)], outline=colour,
                     width=thin)
        draw.rectangle((cx - r * 0.6, cy - r * 0.05, cx + r * 0.6, cy + r * 0.8), outline=colour, width=thin)
    elif kind == 'shield':
        draw.polygon([(cx, cy - r), (cx + r * 0.8, cy - r * 0.6), (cx + r * 0.65, cy + r * 0.3), (cx, cy + r),
                      (cx - r * 0.65, cy + r * 0.3), (cx - r * 0.8, cy - r * 0.6)], outline=colour, width=thin)
    elif kind == 'fold_closed':
        draw.polygon([(cx - r * 0.35, cy - r * 0.6), (cx + r * 0.45, cy), (cx - r * 0.35, cy + r * 0.6)], fill=colour)
    elif kind == 'fold_open':
        draw.polygon([(cx - r * 0.6, cy - r * 0.35), (cx + r * 0.6, cy - r * 0.35), (cx, cy + r * 0.45)], fill=colour)
    elif kind == 'up':
        draw.polygon([(cx - r * 0.6, cy + r * 0.3), (cx + r * 0.6, cy + r * 0.3), (cx, cy - r * 0.45)], fill=colour)
    elif kind == 'down':
        draw.polygon([(cx - r * 0.6, cy - r * 0.3), (cx + r * 0.6, cy - r * 0.3), (cx, cy + r * 0.45)], fill=colour)


# The round button's looks: face light, face dark, rim, label colour, icon colour.
LOOKS = {
    'gold': ('#f0c95a', '#b8891f', '#d4a737', '#191919', '#191919'),
    'green': ('#6fe08b', '#2f9a4c', '#45c565', '#10230f', '#10230f'),
    'grey': ('#585858', '#3a3a3a', '#626262', '#b7b7b7', '#9a9a9a'),
    'refused': ('#4a3a3a', '#332626', '#efa2a0', '#efa2a0', '#efa2a0'),
}
PRESSABLE = ('gold', 'green')


class RoundButton(tk.Canvas):
    """The big round action button. `set(look, icon, text, caption)` changes its state; only the gold and green looks can be
    pressed (grey: waiting, refused: blocked). The caption is drawn under it, wrapped to `caption_width`."""

    def __init__(self, parent, *, diameter, bg, font, command=None, caption_width=None, caption_colour='#b7b7b7'):
        self.d, self.bg, self.font, self.command = diameter, bg, font, command
        self.margin = 14
        self.caption_width = caption_width or diameter + 80
        self.caption_colour = caption_colour
        width = max(diameter + self.margin * 2, self.caption_width)
        super().__init__(parent, width=width, height=diameter + self.margin * 2 + 66, bg=bg, highlightthickness=0,
                         takefocus=1)
        self.picture = None
        self.fonts = {}                  # the label's bold fonts by point size (measured, made once)
        self.state_ = dict(look='grey', icon='wait', text='', caption='')
        self.focused = False
        for event in ('<Return>', '<KP_Enter>', '<space>'):
            self.bind(event, lambda e: self.press())
        self.bind('<Button-1>', self.click)
        self.bind('<FocusIn>', lambda e: self.focus_changed(True))
        self.bind('<FocusOut>', lambda e: self.focus_changed(False))
        self.draw()

    @property
    def pressable(self):
        return self.state_['look'] in PRESSABLE

    def click(self, event):
        centre = self.margin + self.d / 2
        if (event.x - int(self['width']) / 2) ** 2 + (event.y - centre) ** 2 <= (self.d / 2) ** 2:
            self.focus_set()
            self.press()

    def press(self):
        if self.pressable and self.command is not None:
            self.command()

    def focus_changed(self, focused):
        if focused != self.focused:
            self.focused = focused
            self.draw()

    def set(self, *, look, icon, text, caption=''):
        new = dict(look=look, icon=icon, text=text, caption=caption)
        if new != self.state_:
            self.state_ = new
            self.draw()

    def draw(self):
        self.delete('all')
        look, icon, text, caption = (self.state_[k] for k in ('look', 'icon', 'text', 'caption'))
        width = int(self['width'])
        self.picture = ImageTk.PhotoImage(face_image(self.d, self.margin, look, icon, self.bg, self.focused), master=self)
        cx = width // 2
        self.create_image(cx, 0, image=self.picture, anchor='n')
        label = LOOKS[look][3]
        centre = self.margin + self.d // 2
        shown = text.upper() if look in PRESSABLE else text
        self.create_text(cx, centre + self.d * 0.2, text=shown, fill=label, font=(self.font, self.label_size(shown), 'bold'),
                         width=self.d * 0.78, justify='center', tags=('label',))
        self.create_text(cx, self.d + self.margin * 2 + 4, text=caption, fill=self.caption_colour, font=(self.font, 9),
                         width=self.caption_width - 8, justify='center', anchor='n', tags=('caption',))
        self.configure(cursor='hand2' if self.pressable else '')

    def label_size(self, text):
        """The label's point size: the button's own, smaller until its longest word fits the face (« ЗАПУСТИТЬ »,
        « Заблокировано »), never under 9 points; a long label still wraps between words."""
        from tkinter import font as tkfont
        size = 15 if self.d >= 140 else 13 if self.d >= 120 else 12
        room = self.d * 0.72
        words = text.split() or ['']
        while size > 9:
            if size not in self.fonts:
                self.fonts[size] = tkfont.Font(root=self, family=self.font, size=size, weight='bold')
            if max(self.fonts[size].measure(word) for word in words) <= room:
                break
            size -= 1
        return size

    def texts(self):
        """(label, caption) as drawn (tests)."""
        return self.itemcget('label', 'text'), self.itemcget('caption', 'text')


def face_image(d, margin, look, icon, bg, focus):
    light, dark, rim, _label, icon_colour = LOOKS[look]
    size = d + margin * 2
    big = size * S
    image = Image.new('RGB', (big, big), rgb(bg))
    cx = cy = big / 2
    R = d * S / 2
    shadow = Image.new('L', (big, big), 0)
    ImageDraw.Draw(shadow).ellipse((cx - R, cy - R + 5 * S, cx + R, cy + R + 5 * S), fill=150)
    image.paste(Image.new('RGB', (big, big), (0, 0, 0)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(5 * S)))
    draw = ImageDraw.Draw(image)
    draw.ellipse((cx - R, cy - R, cx + R, cy + R), fill=rgb('#141414'), outline=rgb(rim), width=round(2.2 * S))
    face = R - 9 * S
    a, b = rgb(light), rgb(dark)
    steps = 48
    for i in range(steps):
        t = i / (steps - 1)
        r = face * (1 - t * 0.98)
        colour = tuple(round(b[k] + (a[k] - b[k]) * t) for k in range(3))
        ox, oy = -face * 0.18 * t, -face * 0.22 * t
        draw.ellipse((cx + ox - r, cy + oy - r, cx + ox + r, cy + oy + r), fill=colour)
    draw.ellipse((cx - face, cy - face, cx + face, cy + face), outline=tuple(max(0, v - 40) for v in b), width=round(1.5 * S))
    draw_icon(draw, icon, cx, cy - face * 0.28, face * 0.26, rgb(icon_colour), face * 0.075)
    if focus:
        f = R + 6 * S
        for start in range(0, 360, 20):
            draw.arc((cx - f, cy - f, cx + f, cy + f), start, start + 11, fill=rgb('#efc64f'), width=round(1.6 * S))
    return image.resize((size, size), Image.LANCZOS)
