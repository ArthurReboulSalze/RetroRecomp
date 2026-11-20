"""The closing card: what the player sees when closing Retro-Recomp while games on sharing consoles have new paths that are
not recompiled yet (Arthur's pick of 19 Nov 2026, proposal B « Deux chemins »).

A glowing route leads from « Your PC » to the « Shared base »: one pulse leaves per game (five at most; the last carries
the hints of the others), and the gold counter in the middle adds the discoveries of each game as its pulse lands. The
animation lasts about two seconds, in Tk `after()` steps computed from the clock, then the card stands still. Under the
route, two cards say what each way of sending does (recompile first: qualified paths; send now: raw observations), then
« Close without sending » and « Cancel ».

The four choices are those of the card it replaces and return the same: 'recompile', 'send', 'skip' or None (cancel).
« Recompile » opens the shared « New paths » list (`new_paths_dialog`) with the card's games; the ticked games are kept in
`selected`, and cancelling that list brings the player back to the card. The pictures are drawn with Pillow (rounded_ui)."""
from __future__ import annotations

import math
import time
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageFilter, ImageTk

from .branding import COLORS
from .paths import APP_NAME
from .rounded_ui import Look, S, draw_icon, rgb

BG = COLORS['background']
CARD, DEEP = '#2b2b2b', COLORS['field']
GOLD, GOLD_HOVER, TEXT, MUTED = COLORS['gold'], COLORS['gold_hover'], COLORS['text'], COLORS['muted']

W, H = 600, 120                  # the route's picture
X0, X1, Y = 108, 492, 46         # the route: from the PC node's edge to the base node's edge
NODE_L, NODE_R = 72, 528         # far enough from the edges for a two-line label of 130 px
CHIP = (92, 50)                  # the counter's chip
FLY, GAP, FIRST, RING = 0.8, 0.2, 0.1, 0.45     # seconds: a pulse's flight, between departures, the first one, a ring
COUNT_ROLL = 0.3                 # seconds a game's hints take to add to the counter once its pulse has landed
MAX_PULSES = 5
DURATION = 2.0
TICK_MS = 33


def clamp01(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def ease_out(p):
    return 1 - (1 - clamp01(p)) ** 3


def ease_io(p):
    return 0.5 - 0.5 * math.cos(math.pi * clamp01(p))


def flights(games):
    """[(departure, landing, hints)] in seconds: one pulse per game, the last carrying the hints of the games beyond the
    fifth. No game: no pulse."""
    out = []
    for index, game in enumerate(games[:MAX_PULSES]):
        depart = FIRST + GAP * index
        out.append((depart, depart + FLY, game.hints))
    rest = sum(game.hints for game in games[MAX_PULSES:])
    if rest and out:
        depart, land, hints = out[-1]
        out[-1] = (depart, land, hints + rest)
    return out


def counter_value(plan, t, count):
    """What the counter shows at `t` seconds: each pulse adds its hints as it lands; never above `count`."""
    return min(count, sum(round(hints * ease_out((t - land) / COUNT_ROLL)) for _depart, land, hints in plan))


def cartridge_image(w, h, accent):
    """A small cartridge (RGBA, drawn large and reduced): grip lines, a coloured sticker, contacts."""
    image = Image.new('RGBA', (w * S, h * S), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, w * S - 1, h * S - 1), radius=8 * S, fill=rgb('#3f3f3f'), outline=rgb(accent), width=2 * S)
    for y in (6, 10, 14):
        draw.line([(9 * S, y * S), ((w - 9) * S, y * S)], fill=rgb('#262626'), width=2 * S)
    draw.rounded_rectangle((7 * S, 22 * S, (w - 7) * S, 48 * S), radius=5 * S, fill=rgb(accent))
    draw.rectangle((10 * S, (h - 11) * S, (w - 10) * S, (h - 5) * S), fill=rgb('#181818'))
    for x in range(14, w - 12, 4):
        draw.line([(x * S, (h - 10) * S), (x * S, (h - 6) * S)], fill=rgb('#d4a737'), width=S)
    return image.resize((w, h), Image.LANCZOS)


class Route:
    """The route's pictures: the still layers are made once, a frame is composed per tick (glow, pulses, rings)."""

    def __init__(self, plan):
        self.plan = plan
        big = (W * 2, H * 2)
        base = Image.new('RGBA', big, rgb(DEEP) + (255,))
        draw = ImageDraw.Draw(base)
        x = X0
        while x < X1:                                              # the faint dashed route
            draw.line([(x * 2, Y * 2), (min(x + 10, X1) * 2, Y * 2)], fill=rgb(COLORS['subtle_border']), width=4)
            x += 18
        over = Image.new('RGBA', big, (0, 0, 0, 0))
        draw = ImageDraw.Draw(over)
        for cx in (NODE_L, NODE_R):                                # the two nodes
            draw.rounded_rectangle(((cx - 32) * 2, (Y - 32) * 2, (cx + 32) * 2, (Y + 32) * 2), radius=20, fill=rgb(CARD),
                                   outline=rgb('#4a4a4a'), width=3)
        over.alpha_composite(cartridge_image(32, 42, GOLD).resize((64, 84), Image.LANCZOS), ((NODE_L - 16) * 2, (Y - 21) * 2))
        draw_icon(draw, 'globe', NODE_R * 2, Y * 2, 38, rgb(GOLD_HOVER), 5)
        draw.rounded_rectangle(((W // 2 - CHIP[0] // 2) * 2, (Y - CHIP[1] // 2) * 2, (W // 2 + CHIP[0] // 2) * 2,
                                (Y + CHIP[1] // 2) * 2), radius=24, fill=rgb(CARD), outline=rgb(GOLD), width=4)
        self.base, self.over, self.big = base, over, big

    def image(self, t):
        big = self.big
        core, ring = Image.new('L', big, 0), Image.new('L', big, 0)
        core_draw, ring_draw = ImageDraw.Draw(core), ImageDraw.Draw(ring)
        landed = 0
        for depart, land, _hints in self.plan:
            p = (t - depart) / FLY
            if 0 < p < 1:
                head = X0 + (X1 - X0) * ease_io(p)
                for k in range(14):                                 # a fading tail behind the head
                    a, b = head - (k + 1) * 9, head - k * 9
                    core_draw.line([(max(a, X0) * 2, Y * 2), (max(b, X0) * 2, Y * 2)], fill=int(255 * (1 - k / 14) ** 1.3),
                                   width=6)
                core_draw.ellipse(((head - 6) * 2, (Y - 6) * 2, (head + 6) * 2, (Y + 6) * 2), fill=255)
            if t >= land:
                landed += 1
                q = (t - land) / RING
                if q < 1:                                           # a ring leaves the base node on each arrival
                    r = 36 + 16 * ease_out(q)
                    ring_draw.ellipse(((NODE_R - r) * 2, (Y - r) * 2, (NODE_R + r) * 2, (Y + r) * 2),
                                      outline=int(255 * (1 - q)), width=5)
        charge = landed / max(1, len(self.plan))                    # the base node's rim fills in as the paths arrive
        ring_draw.rounded_rectangle(((NODE_R - 34) * 2, (Y - 34) * 2, (NODE_R + 34) * 2, (Y + 34) * 2), radius=24,
                                    outline=int(215 * charge), width=5)
        glow = core.filter(ImageFilter.GaussianBlur(11)).point(lambda v: min(255, int(v * 1.7)))
        halo = ring.filter(ImageFilter.GaussianBlur(5)).point(lambda v: min(255, int(v * 1.4)))
        frame = self.base.copy()
        for colour, mask in ((GOLD, glow), (GOLD_HOVER, halo), ('#fff3c4', core), (GOLD, ring)):
            frame.paste(Image.new('RGBA', big, rgb(colour) + (255,)), (0, 0), mask)
        frame.alpha_composite(self.over)
        return frame.convert('RGB').resize((W, H), Image.LANCZOS)


class Styles:
    """The card's rounded ttk styles, made once per window root and font (their pictures live as long as this object)."""

    def __init__(self, root, font):
        c = COLORS
        look = self.look = Look(root, c, font)
        look.card('CcCard', CARD, BG, 16)
        look.card('CcDeep', DEEP, BG, 16)
        look.card('CcOutlined', CARD, BG, 16, outline=c['gold'])
        for bg, tag in ((BG, 'Bg'), (CARD, 'Card')):
            look.pill_button(f'CcGold{tag}', GOLD, GOLD_HOVER, c['gold_text'], bg, 12, bold=True, size=11, padding=(18, 8),
                             ring=TEXT)
            look.pill_button(f'CcSoft{tag}', c['button'], c['hover'], TEXT, bg, 12, bold=True, padding=(14, 6),
                             ring=GOLD_HOVER)
            look.pill_button(f'CcGhost{tag}', bg, c['hover'], MUTED, bg, 12, outline=c['border'], padding=(14, 6),
                             ring=GOLD_HOVER)


def styles_for(app):
    cache = app.__dict__.setdefault('closing_styles', {})
    if app.ui_font not in cache:
        cache[app.ui_font] = Styles(app.app, app.ui_font)
    return cache[app.ui_font]


class ClosingCard:
    """The card as a window. `app` is the converter's Application (tr, ui_font, the Tk root as app.app); `games` are the
    games with new paths; `sending` is the existing rule for sending (SENDING_AVAILABLE): when it is false the Send button is
    greyed and the texts say that sending is coming. `checklist(games)` is the shared « New paths » list: it returns the
    ticked games, none when cancelled (default: app.new_paths_dialog)."""

    def __init__(self, app, games, *, sending=True, checklist=None):
        self.app, self.games, self.sending = app, list(games), sending
        self.checklist = checklist
        self.count = sum(game.hints for game in self.games)
        self.plan = flights(self.games)
        self.choice, self.selected = None, list(self.games)
        self.destroyed = self.done = False
        self.started = self.job = None
        self.picture = None
        self.font = app.ui_font
        window = self.win = tk.Toplevel(app.app)
        window.withdraw()
        window.title(APP_NAME)
        window.configure(bg=BG)
        window.resizable(False, False)
        window.transient(app.app)
        self.styles = styles_for(app)
        self.body = tk.Frame(window, bg=BG, padx=16, pady=14)
        self.body.pack(fill='both', expand=True)
        self.build()
        window.bind('<Escape>', self.on_escape)
        for key in ('<Return>', '<KP_Enter>'):
            window.bind(key, self.on_return)
        window.bind('<Destroy>', self.on_destroy)
        window.protocol('WM_DELETE_WINDOW', lambda: self.pick(None))
        self.frame(0.0)

    # ---- building ----

    def label(self, parent, text, *, size=9, bold=False, colour=MUTED, bg=BG, wrap=0, anchor='w', justify='left'):
        return tk.Label(parent, text=text, bg=bg, fg=colour, font=(self.font, size, 'bold' if bold else 'normal'),
                        wraplength=wrap, justify=justify, anchor=anchor)

    def card(self, parent, style, padding):
        return ttk.Frame(parent, style=f'{style}.TFrame', padding=padding)

    def build(self):
        tr, count = self.app.tr, self.count
        soon = '' if self.sending else '_soon'
        hero = self.card(self.body, 'CcDeep', 14)
        hero.pack(fill='x')
        self.label(hero, tr('closing_title').upper(), bold=True, colour=GOLD_HOVER, bg=DEEP).pack(anchor='w')
        art = self.art = tk.Canvas(hero, width=W, height=H, bg=DEEP, highlightthickness=0)
        art.pack(pady=(4, 0))
        self.route = Route(self.plan)
        self.picture_item = art.create_image(0, 0, anchor='nw')
        self.number = art.create_text(W // 2, Y, text='0', font=(self.font, 22, 'bold'), fill=GOLD_HOVER)
        art.create_text(W // 2, Y + 34, text=tr('closing_count_one' if count == 1 else 'closing_count'), fill=MUTED,
                        font=(self.font, 9), width=220, justify='center', anchor='n')
        for x, key in ((NODE_L, 'closing_route_pc'), (NODE_R, 'closing_route_base')):
            art.create_text(x, Y + 40, text=tr(key), fill=TEXT, font=(self.font, 9, 'bold'), width=130, anchor='n',
                            justify='center')
        # what is sent, and why it is safe
        self.label(self.body, tr('closing_body' + soon, games=len(self.games)), wrap=W + 20).pack(fill='x', pady=(10, 0),
                                                                                                    padx=4)
        # the two ways of sending, each with its consequence; they are built in the Tab order: recompile, send, skip, cancel
        cards = tk.Frame(self.body, bg=BG)
        cards.pack(fill='x', pady=(10, 0))
        cards.columnconfigure(0, weight=3)          # the recommended card is a little wider (its button is the longest)
        cards.columnconfigure(1, weight=2)
        left, right = self.card(cards, 'CcOutlined', 14), self.card(cards, 'CcCard', 14)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        right.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        self.go = ttk.Button(left, text=tr('closing_recompile', games=len(self.games)), style='CcGoldCard.TButton',
                             command=self.recompile)
        self.label(left, tr('closing_card_recompile' if self.sending else 'closing_recompile_note_soon'), wrap=300,
                   bg=CARD).pack(anchor='n', fill='x', expand=True)
        self.go.pack(fill='x', pady=(12, 0))
        self.send = ttk.Button(right, text=tr('closing_send'), style='CcSoftCard.TButton', command=lambda: self.pick('send'))
        if not self.sending:
            self.send.state(['disabled'])
        self.label(right, tr('closing_card_send' if self.sending else 'tip_closing_send'), wrap=230,
                   bg=CARD).pack(anchor='n', fill='x', expand=True)
        self.send.pack(fill='x', pady=(12, 0))
        bottom = tk.Frame(self.body, bg=BG)
        bottom.pack(fill='x', pady=(10, 0))
        self.skip = ttk.Button(bottom, text=tr('closing_skip'), style='CcGhostBg.TButton', command=lambda: self.pick('skip'))
        self.cancel = ttk.Button(bottom, text=tr('knowledge_cancel'), style='CcGhostBg.TButton',
                                 command=lambda: self.pick(None))
        self.skip.pack(side='left')
        self.cancel.pack(side='left', padx=(8, 0))

    # ---- choices ----

    def pick(self, value):
        """Close the card with a choice (None: cancel). Pending animation steps are cancelled first."""
        if self.destroyed:
            return
        self.destroyed = True
        self.choice = value
        self.stop()
        self.win.destroy()

    def on_escape(self, event=None):
        self.pick(None)

    def on_destroy(self, event):
        if event.widget is self.win:                # the window went away by other means (the converter closing)
            self.destroyed = True
            self.stop()

    def recompile(self):
        """« Recompile »: the shared list of games opens; the ticked ones are kept. Cancel there: back on this card."""
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        chosen = (self.checklist or self.app.new_paths_dialog)(self.games)
        if self.destroyed:
            return
        self.regrab()
        if not chosen:
            return
        self.selected = list(chosen)
        self.pick('recompile')

    def regrab(self):
        try:
            self.win.grab_set()
        except tk.TclError:
            pass
        self.go.focus_set()

    def on_return(self, event=None):
        """Return presses the focused button (a ttk button answers space only); elsewhere, the recommended one."""
        widget = self.win.focus_get()
        if isinstance(widget, ttk.Button) and 'disabled' not in widget.state():
            widget.invoke()
        else:
            self.go.invoke()

    def focus_order(self):
        """The labels of the buttons the Tab key visits, in its order (tests): Tk walks the widgets depth first in the order
        they were made and skips the greyed ones (it also skips windows not on screen, so the walk is made here)."""
        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, ttk.Button) and 'disabled' not in child.state():
                    yield str(child.cget('text'))
                yield from walk(child)
        return list(walk(self.win))

    # ---- animation ----

    def frame(self, t):
        """The route and the counter at `t` seconds."""
        self.picture = ImageTk.PhotoImage(self.route.image(t), master=self.win)
        self.art.itemconfigure(self.picture_item, image=self.picture)
        self.art.itemconfigure(self.number, text=str(counter_value(self.plan, t, self.count) if self.plan else self.count))
        self.art.tag_raise(self.number)

    def play(self):
        """`after()` steps for DURATION seconds, then still; no other loop."""
        self.started = time.monotonic()
        self.done = False
        self.tick()

    def tick(self):
        self.job = None
        if self.destroyed or not self.win.winfo_exists():
            return
        elapsed = time.monotonic() - self.started
        self.frame(min(elapsed, DURATION))
        if elapsed >= DURATION:
            self.done = True
            return
        self.job = self.win.after(TICK_MS, self.tick)

    def stop(self):
        """Cancel the pending animation step (the card closes mid-animation)."""
        if self.job is not None:
            try:
                self.win.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    # ---- showing ----

    def run(self):
        """Show the card above the converter, wait for the choice and return it."""
        window, root = self.win, self.app.app
        window.update_idletasks()
        x = root.winfo_rootx() + (root.winfo_width() - window.winfo_reqwidth()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - window.winfo_reqheight()) // 3
        window.geometry(f'+{max(0, x)}+{max(0, y)}')
        window.deiconify()
        self.play()
        self.regrab()
        root.wait_window(window)
        return self.choice
