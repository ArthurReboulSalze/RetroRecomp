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
