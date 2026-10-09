"""Anthracite/gold desktop identity and original procedural UI symbols."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

COLORS = {
    'background': '#232323', 'header': '#181818', 'field': '#181818',
    'panel': '#292929', 'button': '#343434', 'hover': '#444444',
    'border': '#626262', 'subtle_border': '#3b3b3b', 'text': '#f5f5f4',
    'muted': '#b7b7b7', 'disabled': '#777777', 'gold': '#d4a737',
    'gold_hover': '#efc64f', 'gold_text': '#191919', 'selected': '#51442a',
    'success': '#9bc7a6', 'error': '#efa2a0', 'green': '#45c565',
}

# Small, original pixel lettering; no font download or external font dependency.
GLYPHS = {
    'R': ('11110', '11011', '11011', '11110', '11100', '11010', '11011'),
    'e': ('00000', '00000', '01110', '11011', '11111', '11000', '01111'),
    't': ('0110', '0110', '1111', '0110', '0110', '0110', '0011'),
    'r': ('0000', '0000', '1101', '1111', '1100', '1100', '1100'),
    'o': ('00000', '00000', '01110', '11011', '11011', '11011', '01110'),
    '-': ('0000', '0000', '0000', '1111', '1111', '0000', '0000'),
    'c': ('00000', '00000', '01111', '11000', '11000', '11000', '01111'),
    'm': ('0000000', '0000000', '1111110', '1101101', '1101101', '1101101', '1101101'),
    'p': ('00000', '00000', '11110', '11011', '11011', '11110', '11000', '11000'),
}


def wordmark_rectangles(x=0, y=0, scale=1):
    """Geometry shared by the reproducible banner renderer and native canvases."""
    for character in 'Retro-Recomp':
        glyph = GLYPHS[character]
        color = COLORS['gold'] if character == '-' else COLORS['text']
        for row, line in enumerate(glyph):
            for column, pixel in enumerate(line):
                if pixel == '1':
                    yield (x + column*scale, y + row*scale,
                           x + (column+1)*scale, y + (row+1)*scale), color
        x += (len(glyph[0]) + 1)*scale


def apply_theme(app):
    c = COLORS
    app.configure(bg=c['background'])
    app.option_add('*TCombobox*Listbox.background', c['field'])
    app.option_add('*TCombobox*Listbox.foreground', c['text'])
    app.option_add('*TCombobox*Listbox.selectBackground', c['selected'])
    app.option_add('*TCombobox*Listbox.selectForeground', c['text'])
    style = ttk.Style(app)
    style.theme_use('clam')
    style.configure('.', font=('Segoe UI', 10), background=c['background'], foreground=c['text'])
    style.configure('TButton', padding=(10, 7), background=c['button'], bordercolor=c['border'],
                    lightcolor=c['button'], darkcolor=c['button'], focuscolor=c['gold'],
                    focusthickness=1, anchor='center')
    style.map('TButton', background=[('disabled', c['panel']), ('pressed', c['selected']), ('active', c['hover'])],
              foreground=[('disabled', c['disabled'])], bordercolor=[('focus', c['gold']), ('active', c['muted'])])
    style.configure('Primary.TButton', background=c['gold'], foreground=c['gold_text'],
                    bordercolor=c['gold_hover'], lightcolor=c['gold'], darkcolor=c['gold'],
                    padding=(14, 8), font=('Segoe UI', 10, 'bold'))
    style.map('Primary.TButton', background=[('disabled', c['panel']), ('active', c['gold_hover'])],
              foreground=[('disabled', c['disabled']), ('!disabled', c['gold_text'])],
              lightcolor=[('active', c['gold_hover'])], darkcolor=[('active', c['gold_hover'])])
    style.configure('TCheckbutton', background=c['background'], foreground=c['text'],
                    indicatorbackground=c['field'], indicatorforeground=c['gold'], focuscolor=c['gold'])
    style.map('TCheckbutton', background=[('active', c['background'])],
              foreground=[('disabled', c['disabled'])], indicatorbackground=[('selected', c['gold'])])
    for name in ('TEntry', 'TCombobox', 'TSpinbox'):
        style.configure(name, fieldbackground=c['field'], foreground=c['text'],
                        background=c['button'], bordercolor=c['border'],
                        lightcolor=c['field'], darkcolor=c['field'],
                        insertcolor=c['text'], arrowcolor=c['gold'], padding=3)
        style.map(name, fieldbackground=[('disabled', c['panel']), ('readonly', c['field'])],
                  foreground=[('disabled', c['disabled']), ('readonly', c['text'])],
                  bordercolor=[('focus', c['gold'])])
    style.configure('Horizontal.TProgressbar', background=c['gold'], troughcolor=c['field'],
                    bordercolor=c['subtle_border'], lightcolor=c['gold'], darkcolor=c['gold'], thickness=5)
    for name in ('TScrollbar', 'Vertical.TScrollbar'):
        style.configure(name, background=c['button'], troughcolor=c['field'],
                        arrowcolor=c['muted'], bordercolor=c['subtle_border'],
                        lightcolor=c['button'], darkcolor=c['button'])
        style.map(name, background=[('active', c['hover'])])
    style.configure('TNotebook', background=c['background'], bordercolor=c['border'])
    style.configure('TNotebook.Tab', padding=(12, 8), background=c['field'], foreground=c['muted'])
    style.map('TNotebook.Tab', background=[('selected', c['button']), ('active', c['hover'])],
              foreground=[('selected', c['gold_hover'])])
    style.configure('Treeview', background=c['field'], fieldbackground=c['field'], foreground=c['text'],
                    rowheight=31, borderwidth=1, bordercolor=c['border'],
                    lightcolor=c['border'], darkcolor=c['border'])
    style.configure('Treeview.Heading', background=c['button'], foreground=c['text'],
                    padding=(8, 8), font=('Segoe UI', 10, 'bold'), bordercolor=c['border'],
                    lightcolor=c['button'], darkcolor=c['button'])
    style.map('Treeview.Heading', background=[('active', c['hover'])])
    style.map('Treeview', background=[('selected', c['selected'])], foreground=[('selected', c['text'])])
    style.configure('Muted.TLabel', foreground=c['muted'])
    style.configure('Empty.TLabel', background=c['field'], foreground=c['muted'], font=('Segoe UI', 10))
    style.configure('EmptyTitle.TLabel', background=c['field'], foreground=c['muted'], font=('Segoe UI', 10, 'bold'))
    style.configure('Toolbar.TButton', font=('Segoe UI', 9), padding=(6, 7))
    style.configure('Toolbar.Primary.TButton', font=('Segoe UI', 9, 'bold'), padding=(8, 7))
    style.configure('TLabelframe', bordercolor=c['subtle_border'])
    style.configure('TLabelframe.Label', foreground=c['gold_hover'])
    return style


# Normalized polylines are rendered as small solid UI glyphs. These are drawn
# afresh, not extracted from the presentation sheet or a game controller photo.
ICON_PATHS = {
    'folder': ((1, 5, 1, 13, 13, 13, 15, 6, 5, 6, 3, 9), (1, 5, 1, 3, 6, 3, 8, 5, 13, 5)),
    'add_folder': ((1, 5, 1, 13, 13, 13, 15, 6, 5, 6, 3, 9), (1, 5, 1, 3, 6, 3, 8, 5), (10, 1, 10, 5), (8, 3, 12, 3)),
    'remove': ((4, 5, 4, 14, 12, 14, 12, 5), (2, 4, 14, 4), (6, 4, 6, 2, 10, 2, 10, 4), (7, 7, 7, 11), (10, 7, 10, 11)),
    'clear': ((2, 3, 14, 3), (2, 6, 11, 6), (2, 9, 7, 9), (2, 12, 7, 12), (10, 9, 14, 13), (14, 9, 10, 13)),
    'refresh': ((13, 5, 11, 2, 5, 2, 2, 5, 2, 8), (1, 5, 2, 8, 5, 7),
                (3, 11, 5, 14, 11, 14, 14, 11, 14, 8), (11, 9, 14, 8, 15, 11)),
    'info': ((8, 1, 12, 2, 15, 6, 15, 10, 12, 14, 8, 15, 4, 14, 1, 10, 1, 6, 4, 2, 8, 1), (8, 7, 8, 12), (8, 4, 8, 4)),
    'image': ((1, 2, 15, 2, 15, 14, 1, 14, 1, 2), (2, 12, 6, 8, 9, 11, 12, 7, 14, 10), (5, 5, 5, 5)),
    'auto': ((3, 13, 12, 4), (2, 3, 2, 6), (1, 5, 4, 5), (12, 10, 12, 14), (10, 12, 14, 12), (8, 1, 8, 3)),
    'play': ((4, 2, 13, 8, 4, 14, 4, 2),),
    'stop': ((5, 3, 5, 13), (11, 3, 11, 13)),
    'gamepad': ((4, 4, 12, 4, 14, 6, 15, 12, 13, 14, 10, 11, 6, 11, 3, 14, 1, 12, 2, 6, 4, 4),
                (5, 6, 5, 10), (3, 8, 7, 8), (11, 7, 11, 7), (13, 9, 13, 9)),
}


def icon_paths(name):
    if name == 'options':
        ring = tuple(v for i in range(33) for v in
                     (8 + (7 if (i // 2) % 2 else 5)*math.cos(i*math.pi/16),
                      8 + (7 if (i // 2) % 2 else 5)*math.sin(i*math.pi/16)))
        hole = tuple(v for i in range(17) for v in (8+2*math.cos(i*math.pi/8), 8+2*math.sin(i*math.pi/8)))
        return ring, hole
    return ICON_PATHS[name]


def make_icon(master, name, color, size=18):
    image = tk.PhotoImage(master=master, width=size, height=size)
    scale = (size-2)/16
    for path in icon_paths(name):
        for at in range(0, len(path)-2, 2):
            x1, y1, x2, y2 = (path[at]+1)*scale, (path[at+1]+1)*scale, (path[at+2]+1)*scale, (path[at+3]+1)*scale
            steps = max(1, round(max(abs(x2-x1), abs(y2-y1))*2))
            for step in range(steps+1):
                x, y = round(x1+(x2-x1)*step/steps), round(y1+(y2-y1)*step/steps)
                image.put(color, to=(min(x,size-1), min(y,size-1)))
    return image
