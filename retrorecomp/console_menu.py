"""The console menu at the top right of the window: short labels and the size of its list.

A profile's `name` is the machine's full name (reports, folders, covers, stamps); it is too long for the
small header field, so the menu shows a short label instead. The labels are data keyed by the profile id and
belong to the interface: this module moves no stamp. A machine without an entry shows its `name`.
"""
from __future__ import annotations

# Only the machines whose full name is long or ambiguous; the others show their name.
MENU_LABELS = {
    'amiga': 'Amiga 500',
    'a1200': 'Amiga 1200',
    'pce': 'PC Engine',
    'psx': 'PlayStation',
    'scummvm': 'ScummVM',
}

# Width of the closed field, in characters of its font; a label that needs more makes the field wider.
FIELD_CHARACTERS = 14
# The list's border and scrollbar room around the longest entry, in pixels.
LIST_PADDING = 28


def menu_label(profile) -> str:
    return MENU_LABELS.get(profile.id, profile.name)


def profile_for_label(profiles, label: str):
    """The profile a menu label stands for, or None (the 'automatic' entry)."""
    return next((profile for profile in profiles if menu_label(profile) == label), None)


def field_characters(font, labels, minimum: int = FIELD_CHARACTERS) -> int:
    """The `width` (in characters of `font`) a closed field needs to show every label whole."""
    zero = max(1, font.measure('0'))
    widest = max((font.measure(label) for label in labels), default=0)
    # The arrow button and the field's inner margin take about two characters.
    return max(minimum, -(-widest // zero) + 2)


def popdown_extra(font, entries, field_pixels: int) -> int:
    """How many pixels the drop-down list must be wider than its field to show its longest entry whole."""
    widest = max((font.measure(entry) for entry in entries), default=0)
    return max(0, widest + LIST_PADDING - field_pixels)
