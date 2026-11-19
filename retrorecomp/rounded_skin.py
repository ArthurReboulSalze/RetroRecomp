"""The converter's rounded look: one skin for every ttk button, field, check box, group frame and scrollbar (Arthur's pick of 19 Nov 2026,
« 8 px, recommandé »).

Tk has no rounded corners. This module re-skins the ttk styles the application already configures (branding.apply_theme, the toolbar's,
the cards', the Multiplayer window's) with pictures drawn by Pillow at four times the size and reduced, as 9-slice `image` elements.
The widgets stay ttk widgets: focus, Tab, the gamepad's focus moves, any text length and every interface language work as before.

- Colours are READ from the styles (`ttk::style lookup` with each state): change a colour in branding.py and the look follows. The one
  thing the skin adds is the shape and a 2 px focus ring in place of the dotted line (gold on the dark buttons, light on the gold ones).
- A style is skinned the first time a widget of it is built (a hook on the ttk constructors, `install`), so every window gets it, including
  the styles a window configures for itself.
- Corners are painted with the colour of the widget's PARENT: a ttk button's own window is filled with the style's background, so transparent
  corners would show the button's fill. A style that stands on one surface keeps its name; the same style on another surface gets a derived
  name (`Rs<colour>.<style>`), which inherits everything else.
- Two costs are guarded by tests (tests/test_rounded_skin.py): Tk TILES the stretched middle of a 9-slice picture, so the middle is
  `CENTER` pixels wide (a 2 px middle made a 130 px field cost 65 draws per edge); and Tk makes one image instance per state entry and per
  widget, so the entries that change no picture are pruned (`Skin.prune`).
- A check box or radio button is not a picture on its corners but draws its own background behind its label: on a panel or a card
  that is a dark patch, so one that just inherits the window's colour gets a derived name too (`follow_surface`).
- Pictures are pixel sizes: every size is multiplied by `Skin.scale`, the Tk scaling relative to 96 dpi.
- Not rounded (square, on purpose): tables and their headings, notebook tabs, tk.Text, progress bars, menus, the scrollbars' arrow buttons.

`rounded_ui.Look.pill_button` (the Multiplayer window and the closing card) is one way of asking this skin for a button with explicit colours
and radius: there is no second mechanism."""
from __future__ import annotations

import re
import weakref
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from .ui_fonts import ui_scale

RADIUS = 8                   # Arthur's pick, in pixels at 96 dpi
SS = 4                       # supersampling
CENTER = 24                  # width of the stretched middle of a 9-slice picture (Tk tiles it: a narrow one means many draws)
STATE_BITS = ('selected', 'pressed', 'active', 'focus')
DEFAULT_SURFACE = '#232323'


def rgb(colour):
    colour = colour.lstrip('#')
    return tuple(int(colour[i:i + 2], 16) for i in (0, 2, 4))


def is_gold(colour):
    r, g, b = rgb(colour)
    return r > 150 and g > 110 and b < 110


def box_image(w, h, layers, surface=None):
    """w x h picture from `layers`: (inset, radius, colour or None) from the outside in; None = hollow. With a `surface` colour the picture
    is opaque (its corners are the surface), without one it is RGBA with transparent corners."""
    base = next(rgb(colour) for _, _, colour in layers if colour)
    big = Image.new('RGBA', (w * SS, h * SS), base + (0,))
    draw = ImageDraw.Draw(big)
    for inset, radius, colour in layers:
        fill = rgb(colour) + (255,) if colour else base + (0,)
        draw.rounded_rectangle((inset * SS, inset * SS, (w - inset) * SS - 1, (h - inset) * SS - 1),
                               radius=max(0.0, radius) * SS, fill=fill)
    picture = big.resize((w, h), Image.BOX)
    if surface:
        flat = Image.new('RGBA', (w, h), rgb(surface) + (255,))
        flat.alpha_composite(picture)
        return flat.convert('RGB')
    return picture


def chevron_image(w, h, colour, direction='down', width=1.6):
    big = Image.new('RGBA', (w * SS, h * SS), rgb(colour) + (0,))
    draw = ImageDraw.Draw(big)
    cx, cy = w * SS / 2, h * SS / 2
    dx, dy = w * SS * 0.26, h * SS * 0.16
    sign = 1 if direction == 'down' else -1
    draw.line([(cx - dx, cy - sign * dy), (cx, cy + sign * dy), (cx + dx, cy - sign * dy)], fill=rgb(colour) + (255,),
              width=round(width * SS), joint='curve')
    return big.resize((w, h), Image.BOX)


def tick_image(box, colour):
    big = Image.new('RGBA', (box * SS, box * SS), rgb(colour) + (0,))
    s = box * SS
    ImageDraw.Draw(big).line([(s * 0.24, s * 0.52), (s * 0.43, s * 0.70), (s * 0.78, s * 0.30)], fill=rgb(colour) + (255,),
                             width=max(2, round(s * 0.13)), joint='curve')
    return big


class Skin:
    count = 0
    OPAQUE = ('button', 'entry', 'combobox', 'spinbox', 'scrollbar')

    def __init__(self, root, radius=RADIUS, scale=None):
        self.root, self.radius = root, radius
        self.style = ttk.Style(root)
        self.scale = scale if scale is not None else ui_scale(root)
        Skin.count += 1
        self.generation = Skin.count
        self.images: list = []           # kept alive: Tk frees a PhotoImage when its Python object goes
        self.cache: dict = {}
        self.done: dict = {}             # (style name, kind) -> True
        self.records: dict = {}          # (style name, kind) -> (surface, radius, ring): what rebuild() redoes
        self.originals: dict = {}        # style name -> its layout before this skin (own or inherited)
        self.skinned: dict = {}          # style name -> the layout this skin wrote for it
        self.surfaces: dict = {}         # style name -> the surface it was skinned for
        self.explicit: set = set()       # style names whose surface was given by their maker (Look.pill_button): never derived
        self.styled_surfaces: dict = {}  # a frame style's own fill (cards), for the corners of what stands on it
        self.looks: dict = {}            # style name -> function(states) -> (fill, border, ring) it draws (tests)
        self.derived_from: dict = {}     # derived style name -> the style it was derived from
        self.entries: dict = {}          # element -> number of pictures it holds after pruning (tests)
        self.sizes: dict = {}            # element -> (picture side, minimum size) (tests)
        self.pictures = 0
        self.fonts: dict = {}
        self.surface_cache = weakref.WeakKeyDictionary()

    # ---- helpers ----
    @property
    def tag(self):
        return f'rs{self.generation}'

    def px(self, value):
        return max(1, round(value * self.scale))

    def photo(self, key, make, surface):
        key = key + (surface,)
        if key not in self.cache:
            picture = ImageTk.PhotoImage(make(), master=self.root)
            self.images.append(picture)
            self.cache[key] = picture
            self.pictures += 1
        return self.cache[key]

    COLOUR_OPTIONS = ('background', 'bordercolor', 'fieldbackground', 'arrowcolor', 'foreground', 'focuscolor', 'indicatorbackground',
                      'troughcolor')

    def lookup(self, name, option, states=(), default=''):
        value = self.style.lookup(name, option, list(states))
        if value in ('', None):
            return default
        return self.hex(value) if option in self.COLOUR_OPTIONS else str(value)

    def cap(self, name, radius=None):
        """The radius a style can take: its smallest widget is a line of text and its padding tall, and the picture's two corners (2r+2)
        must fit in it (a 17 px combobox takes 8, a 12 px chip would take 6)."""
        font = self.lookup(name, 'font', default=self.lookup('.', 'font', default='TkDefaultFont'))
        if font not in self.fonts:
            try:
                self.fonts[font] = tkfont.Font(root=self.root, font=font).metrics('linespace')
            except tk.TclError:
                self.fonts[font] = 16
        numbers = re.findall(r'[\d.]+', self.lookup(name, 'padding', default='4 4')) or ['4']
        pady = int(float(numbers[1] if len(numbers) > 1 else numbers[0]))
        wanted = self.px(self.radius if radius is None else radius)
        return max(2, min(wanted, 14 * max(1, round(self.scale)), (self.fonts[font] + 2 * pady) // 2))

    def hex(self, colour):
        """'#rrggbb' of any Tk colour (a frame's default background is a system name)."""
        colour = str(colour)
        if len(colour) == 7 and colour[0] == '#':
            return colour.lower()
        red, green, blue = self.root.winfo_rgb(colour)
        return '#%02x%02x%02x' % (red >> 8, green >> 8, blue >> 8)

    def surface_of(self, master):
        """The colour a widget placed in `master` stands on (asked once per parent: a window builds hundreds of widgets in a few frames)."""
        try:
            return self.surface_cache[master]
        except (KeyError, TypeError):
            pass
        colour = self.surface_uncached(master)
        try:
            self.surface_cache[master] = colour
        except TypeError:
            pass
        return colour

    def surface_uncached(self, master):
        while master is not None:
            kind = str(master.winfo_class())
            try:
                if kind in ('TFrame', 'TLabelframe', 'TLabel', 'TNotebook', 'TPanedwindow'):
                    style = str(master.cget('style')) or kind
                    for candidate in self.chain(style):
                        if candidate in self.styled_surfaces:
                            return self.styled_surfaces[candidate]
                    value = self.style.lookup(style, 'background')
                    if value:
                        return self.hex(value)
                else:
                    return self.hex(master.cget('background'))
            except tk.TclError:
                pass
            master = getattr(master, 'master', None)
        return self.hex(self.lookup('.', 'background', default=DEFAULT_SURFACE))

    @staticmethod
    def chain(name):
        parts = name.split('.')
        return ['.'.join(parts[index:]) for index in range(len(parts))]

    def base_layout(self, name):
        for candidate in self.chain(name):
            if candidate in self.originals:
                return self.originals[candidate]
            layout = self.style.layout(candidate)
            # ttk answers a derived style with its parent's layout: when that is one we wrote, it is not this style's own
            if layout and layout not in self.skinned.values():
                return layout
        return []

    @staticmethod
    def rewrite(layout, rules):
        """Copy of a ttk layout with `rules` {old element: new element, or None to drop it (its children move up)}."""
        out = []
        for element, options in layout:
            options = dict(options)
            if element in rules and rules[element]:
                options.pop('border', None)
            children = Skin.rewrite(options['children'], rules) if 'children' in options else None
            if children is not None:
                options['children'] = children
            if element in rules:
                if rules[element] is None:
                    out.extend(children or [])
                    continue
                element = rules[element]
            out.append((element, options))
        return out

    @staticmethod
    def prune(default, specs):
        """Drop every (states..., image) entry that changes no state's picture. Tk makes one image instance per entry and per widget (about
        1 ms each), so 16 entries on 60 buttons cost a second; the few that matter cost nothing."""
        bits = sorted({bit for spec in specs for bit in spec[:-1]})
        subsets = [{bit for index, bit in enumerate(bits) if mask >> index & 1} for mask in range(1 << len(bits))]

        def pick(active, items):
            for spec in items:
                if all(bit in active for bit in spec[:-1]):
                    return spec[-1]
            return default
        specs = list(specs)
        index = 0
        while index < len(specs):
            rest = specs[:index] + specs[index + 1:]
            if all(pick(active, specs) is pick(active, rest) for active in subsets):
                specs = rest
            else:
                index += 1
        return specs

    def element(self, suffix, default, *specs, border, padding, **options):
        name = f'{self.tag}.{suffix}'
        specs = self.prune(default, specs)
        self.entries[name] = len(specs) + 1
        options.setdefault('width', 2 * border)         # the minimum size is the two corners, not the whole picture
        options.setdefault('height', 2 * border)
        self.style.element_create(name, 'image', default, *specs, border=border, padding=padding, sticky='nswe', **options)
        return name

    def side(self, r, extra=0):
        """A 9-slice picture's side: two corners and a CENTER wide middle."""
        return 2 * r + 2 + CENTER + extra

    # ---- one style ----
    def skin(self, name, kind, master=None, *, surface=None, radius=None, ring=None):
        """Skin the ttk style `name` of widget kind `kind` (once). `surface` is the colour its corners are painted with (default: what
        `master` stands on); an explicit surface is kept whatever the widget's parent says."""
        if (name, kind) in self.done:
            return
        if surface:
            self.explicit.add(name)
        surface = self.hex(surface) if surface else (self.surface_of(master) if master is not None else self.hex(self.lookup('.', 'background', default=DEFAULT_SURFACE)))
        self.done[(name, kind)] = True
        self.records[(name, kind)] = (surface, radius, ring)
        self.surfaces[name] = surface
        self.originals[name] = self.base_layout(name) if kind != 'combobox' else []
        getattr(self, 'skin_' + kind)(name, surface if kind in self.OPAQUE else None, radius, ring)
        self.skinned[name] = self.style.layout(name)

    def style_for(self, name, kind, master):
        """The style a new widget of style `name` should use: `name` itself, or a derived name when `master` is another surface than
        the one `name` was skinned for."""
        if kind not in self.OPAQUE:
            if kind != 'radiobutton':
                self.skin(name, kind, master)
            return self.follow_surface(name, kind, master)
        if (name, kind) not in self.done:
            self.skin(name, kind)                  # its own surface is the window's; another one gets a derived name below
        if name in self.explicit:
            return name
        surface = self.surface_of(master)
        if surface == self.surfaces.get(name):
            return name
        derived = f'Rs{surface.lstrip("#")}.{name}'
        self.skin(derived, kind, surface=surface)
        self.explicit.discard(derived)
        self.derived_from[derived] = name
        return derived

    def follow_surface(self, name, kind, master):
        """A check box or radio button draws its own background behind its label (the window's colour unless its style sets another):
        on a dialog's panel or a card that is a visible dark patch. A style that just inherits the window's colour gets a derived name
        (`Rs<colour>.<style>`) whose background is the surface it stands on. A style with a background of its own (the cards', the
        new-paths list's) and every custom radio style (the Multiplayer toggle) are left as they are."""
        if kind not in ('checkbutton', 'radiobutton') or (kind == 'radiobutton' and name != 'TRadiobutton'):
            return name
        window = self.hex(self.lookup('.', 'background', default=DEFAULT_SURFACE))
        if self.lookup(name, 'background') != window:
            return name
        surface = self.surface_of(master)
        if surface == window:
            return name
        derived = f'Rs{surface.lstrip("#")}.{name}'
        if derived not in self.derived_from:
            if kind == 'checkbutton':
                self.skin(derived, kind, surface=surface)
                self.explicit.discard(derived)
            self.style.configure(derived, background=surface)
            self.style.map(derived, background=[('active', surface), ('disabled', surface)])
            self.derived_from[derived] = name
        return derived

    def skin_button(self, name, surface, radius, ring):
        r = self.cap(name, radius)
        ow, ring_w, pad = self.px(1), max(2, self.px(2)), self.px(3)
        c = self.lookup
        side = self.side(r)

        def look(states):
            disabled = 'disabled' in states
            fill = c(name, 'background', states, '#343434')
            border = c(name, 'bordercolor', [s for s in states if s != 'focus'], '#626262')
            if disabled and is_gold(border):
                border = '#626262'
            elif is_gold(fill):
                border = fill
            ring_colour = None
            if 'focus' in states and not disabled:
                ring_colour = ring or ('#f5f5f4' if is_gold(fill) else c(name, 'focuscolor', [], '#d4a737'))
            return fill, border, ring_colour

        def picture(states):
            fill, border, ring_colour = look(states)
            key = ('btn', r, ow, ring_w, fill, border, ring_colour)

            def make():
                if ring_colour:
                    return box_image(side, side, [(0, r, ring_colour), (ring_w, r - ring_w, fill)], surface)
                return box_image(side, side, [(0, r, border), (ow, r - ow, fill)], surface)
            return self.photo(key, make, surface)

        self.looks[name] = look

        def subsets(bits):
            return [[bit for index, bit in enumerate(bits) if mask >> index & 1] for mask in range(1 << len(bits))]
        # Only the state bits that change a picture count (for most styles 'selected' changes none): fewer entries, same looks.
        relevant = [bit for bit in STATE_BITS if any(picture(rest + [bit]) is not picture(rest)
                                                      for rest in subsets([b for b in STATE_BITS if b != bit]))]
        specs = [(('disabled', 'selected'), picture(['disabled', 'selected'])), (('disabled',), picture(['disabled']))]
        for bits in sorted(subsets(relevant), key=lambda bits: -len(bits)):
            if bits:
                specs.append((tuple(bits), picture(bits)))
        element = self.element('btn.' + name, picture([]), *[spec + (image,) for spec, image in specs], border=r + 1, padding=pad)
        self.sizes[element] = (side, 2 * (r + 1))
        self.style.layout(name, self.rewrite(self.base_layout(name), {'Button.border': element, 'Button.focus': None}))

    def field_pictures(self, name, surface, family):
        r = self.cap(name)
        ow, ring_w, pad = self.px(1), max(2, self.px(2)), self.px(2)
        c = self.lookup
        side = self.side(r)

        def picture(states):
            fill = c(name, 'fieldbackground', states, '#181818')
            focus = 'focus' in states
            border = c(name, 'bordercolor', states if focus else [s for s in states if s != 'focus'], '#626262')
            width = ring_w if focus else ow
            return self.photo(('field', r, ow, ring_w, fill, border, focus),
                              lambda: box_image(side, side, [(0, r, border), (width, r - width, fill)], surface), surface)

        specs = [(('disabled',), picture(['disabled'])), (('focus', 'readonly'), picture(['focus', 'readonly'])),
                 (('focus',), picture(['focus'])), (('readonly',), picture(['readonly']))]
        element = self.element(f'field.{family}.{name}', picture([]), *[spec + (image,) for spec, image in specs],
                               border=r + 1, padding=pad)
        self.sizes[element] = (side, 2 * (r + 1))
        return element

    def skin_entry(self, name, surface, radius, ring):
        element = self.field_pictures(name, surface, 'entry')
        self.style.layout(name, self.rewrite(self.base_layout(name), {'Entry.field': element}))

    def skin_combobox(self, name, surface, radius, ring):
        element = self.field_pictures(name, surface, 'combo')
        arrow = self.chevron(name)
        self.style.layout(name, [(element, {'sticky': 'nswe', 'children': [
            (arrow, {'side': 'right', 'sticky': ''}),
            ('Combobox.padding', {'sticky': 'nswe', 'children': [('Combobox.textarea', {'sticky': 'nswe'})]})]})])

    def skin_spinbox(self, name, surface, radius, ring):
        element = self.field_pictures(name, surface, 'spin')
        size = (self.px(11), self.px(8))
        up, down = self.chevron(name, 'up', size), self.chevron(name, 'down', size)
        self.style.layout(name, self.rewrite(self.base_layout(name), {'Spinbox.field': element, 'Spinbox.uparrow': up,
                                                                      'Spinbox.downarrow': down}))

    def chevron(self, name, direction='down', size=None):
        w, h = size or (self.px(15), self.px(10))
        colour = self.lookup(name, 'arrowcolor', [], '#d4a737')
        off = self.lookup(name, 'foreground', ['disabled'], '#777777')
        normal = self.photo(('chev', w, h, colour, direction), lambda: chevron_image(w, h, colour, direction), None)
        grey = self.photo(('chev', w, h, off, direction), lambda: chevron_image(w, h, off, direction), None)
        element = f'{self.tag}.arrow.{direction}.{w}.{colour.lstrip("#")}.{off.lstrip("#")}'
        if element not in self.cache:
            self.style.element_create(element, 'image', normal, ('disabled', grey))
            self.cache[element] = element
        return element

    def skin_labelframe(self, name, surface, radius, ring):
        r = self.cap(name)
        ow, pad = self.px(1), self.px(2)
        border = self.lookup(name, 'bordercolor', [], '#3b3b3b')
        side = self.side(r)
        picture = self.photo(('frame', r, ow, border), lambda: box_image(side, side, [(0, r, border), (ow, r - ow, None)]), None)
        element = self.element('frame.' + name, picture, border=r + 1, padding=pad)
        self.sizes[element] = (side, 2 * (r + 1))
        self.style.layout(name, [(element, {'sticky': 'nswe'})])

    def skin_scrollbar(self, name, surface, radius, ring):
        slim = name.endswith('Slim.Vertical.TScrollbar') or name.startswith('Slim')
        surface = self.lookup(name, 'troughcolor', [], '#181818')
        inset = 1
        r = max(2, min(self.px(self.radius), self.px(3 if slim else 5)))
        side = self.side(r, 2 * inset)
        c = self.lookup
        images = {}
        for state in ('', 'active', 'pressed'):
            fill = c(name, 'background', [state] if state else [], '#343434')
            border = c(name, 'bordercolor', [], '#3b3b3b')
            outline = fill if slim else border
            images[state] = self.photo(('thumb', r, inset, fill, outline), lambda f=fill, o=outline: box_image(
                side, side, [(inset, r, o), (inset + (0 if slim else 1), r - (0 if slim else 1), f)], surface), surface)
        element = self.element('thumb.' + name, images[''], ('pressed', images['pressed']), ('active', images['active']),
                               border=r + 1 + inset, padding=0)
        self.sizes[element] = (side, 2 * (r + 1 + inset))
        self.style.layout(name, self.rewrite(self.base_layout(name), {'Vertical.Scrollbar.thumb': element,
                                                                      'Horizontal.Scrollbar.thumb': element}))

    def skin_checkbutton(self, name, surface, radius, ring):
        box = self.px(11)
        r = max(2, min(self.px(self.radius) // 3 + 1, 4))
        c = self.lookup
        W = H = box + self.px(4)

        def picture(states):
            fill = c(name, 'indicatorbackground', states, '#181818')
            on = 'selected' in states
            disabled = 'disabled' in states
            border = fill if on else '#626262'

            def make():
                image = Image.new('RGBA', (W, H), (0, 0, 0, 0))
                image.alpha_composite(box_image(box, box, [(0, r, border), (self.px(1), r - self.px(1), fill)]),
                                      (self.px(2), self.px(2)))
                if on:
                    tick = tick_image(box, c(name, 'foreground', ['disabled'], '#777777') if disabled else '#191919')
                    image.alpha_composite(tick.resize((box, box), Image.BOX), (self.px(2), self.px(2)))
                return image
            return self.photo(('check', box, r, fill, border, on, disabled), make, None)

        specs = [(('disabled', 'selected'), picture(['disabled', 'selected'])), (('disabled',), picture(['disabled'])),
                 (('selected',), picture(['selected']))]
        default = picture([])
        kept = self.prune(default, [spec + (image,) for spec, image in specs])
        element = f'{self.tag}.check.{name}'
        self.entries[element] = len(kept) + 1
        self.style.element_create(element, 'image', default, *kept)
        self.style.layout(name, self.rewrite(self.base_layout(name), {'Checkbutton.indicator': element}))

    # ---- the whole skin ----
    def rebuild(self):
        """Do everything again (fonts or Tk scaling changed, apply_theme ran again): new element names, same styles."""
        records = dict(self.records)
        Skin.count += 1
        self.generation = Skin.count
        self.scale = ui_scale(self.root)
        self.done.clear()
        self.records.clear()
        self.skinned.clear()
        self.entries.clear()
        self.sizes.clear()
        self.fonts.clear()
        self.surface_cache.clear()
        for (name, kind), (surface, radius, ring) in records.items():
            self.skin(name, kind, surface=surface, radius=radius, ring=ring)

    KINDS = (('combobox', ttk.Combobox), ('spinbox', ttk.Spinbox), ('entry', ttk.Entry), ('button', ttk.Button),
             ('checkbutton', ttk.Checkbutton), ('radiobutton', ttk.Radiobutton), ('labelframe', ttk.LabelFrame), ('scrollbar', ttk.Scrollbar))
    DEFAULTS = {'combobox': 'TCombobox', 'spinbox': 'TSpinbox', 'entry': 'TEntry', 'button': 'TButton',
                'checkbutton': 'TCheckbutton', 'radiobutton': 'TRadiobutton', 'labelframe': 'TLabelframe'}

    @classmethod
    def kind_of(cls, widget, orient='vertical'):
        for kind, widget_class in cls.KINDS:
            if isinstance(widget, widget_class):
                if kind == 'scrollbar':
                    return kind, 'Vertical.TScrollbar' if str(orient) == 'vertical' else 'Horizontal.TScrollbar'
                return kind, cls.DEFAULTS[kind]
        return None, None

    def scan(self, widget=None):
        """Skin every ttk widget under `widget` (the whole window by default) that is not yet: for widgets built before the skin."""
        widget = widget or self.root
        kind, default = self.kind_of(widget, widget.cget('orient') if isinstance(widget, ttk.Scrollbar) else 'vertical')
        if kind:
            self.restyle(widget)
        for child in widget.winfo_children():
            self.scan(child)

    def restyle(self, widget):
        """Give `widget` the skinned style of its current style (call it after `widget.configure(style=...)`)."""
        kind, default = self.kind_of(widget, widget.cget('orient') if isinstance(widget, ttk.Scrollbar) else 'vertical')
        if not kind:
            return
        name = str(widget.cget('style')) or default
        wanted = self.style_for(name, kind, widget.master)
        if wanted != str(widget.cget('style')):
            widget.configure(style=wanted)


_HOOKED = []


def skin_of(widget):
    """The skin of the Tk interpreter `widget` belongs to, or None."""
    try:
        root = widget._root() if widget is not None else tk._default_root
    except (AttributeError, tk.TclError):
        return None
    return getattr(root, '_rounded_skin', None)


def apply_rounded_theme(app, font_family='Segoe UI'):
    """The converter window's theme: branding.apply_theme, then this skin over it (it reads the styles apply_theme set, so it
    goes last; calling this again rebuilds it). The skin stays out of branding.py, a host module of every profile, so it
    moves no stamp: the games never draw these ttk widgets."""
    from .branding import apply_theme
    style = apply_theme(app, font_family)
    install(app)
    return style


def install(root, radius=RADIUS):
    """Skin `root`'s ttk styles from now on (and, with `refresh`, the widgets already built). Safe to call again: a second call rebuilds."""
    skin = getattr(root, '_rounded_skin', None)
    if skin is None:
        skin = root._rounded_skin = Skin(root, radius)
    else:
        skin.rebuild()
    _hook_constructors()
    return skin


def _hook_constructors():
    """New ttk widgets get their skin before they are built, so their first draw is already rounded (one hook, once per process)."""
    if _HOOKED:
        return
    _HOOKED.append(True)
    for kind, widget_class in Skin.KINDS:
        if kind in ('combobox', 'spinbox'):
            continue                      # built through ttk.Entry.__init__
        widget_class.__init__ = _hooked(widget_class.__init__)


def _hooked(original):
    def __init__(self, master=None, *args, **kw):
        skin = skin_of(master if master is not None else tk._default_root)
        if skin is not None:
            kind, default = Skin.kind_of(self, kw.get('orient', 'vertical'))
            if kind:
                kw['style'] = skin.style_for(str(kw.get('style') or default), kind, master if master is not None else skin.root)
        original(self, master, *args, **kw)
    __init__.__wrapped__ = original
    return __init__
