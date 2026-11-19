"""The toolbar's and the queue's pictures that need more detail than the shared set of branding.py: our own drawings, as
polylines on the same 16 x 16 grid (make_icon draws them at 18 px, one pixel wide), registered in ICON_PATHS when this
module is imported. Interface only: branding.py, a compiler input, is not touched.

Each picture says what its button does without its text (the text stays set on the button, and the hover hint is
translated): here, arrows going out to the corners of a frame for the full screen, and in from them to restore."""
from __future__ import annotations

from .branding import ICON_PATHS


def _rectangle(x1, y1, x2, y2):
    return (x1, y1, x2, y1, x2, y2, x1, y2, x1, y1)


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
    # Full screen: arrows out to the corners of a frame, and in from them to restore the window.
    'fullscreen_enter': (_rectangle(1, 1, 15, 15),) + _expand_arrows(False),
    'fullscreen_exit': (_rectangle(1, 1, 15, 15),) + _expand_arrows(True),
}

for _name, _paths in ICONS.items():
    ICON_PATHS.setdefault(_name, _paths)
