"""Authored play routes of the X68000: bounded inputs that take a game's delivered file from the title into the game.

Evidence for gate G8 (liveness) of docs/QUALIFICATION.md, never a product feature: a conversion uses the main route of the
qualification (4,000 frames of keys and the joystick) and the exploration routes of its scan level, and the converter does not
read this file. `python tools/x68000_play_route.py <disk or playlist> --ipl ... --cgrom ...` converts one game with its route as
the main route, so that every check of a conversion (the fresh reference, the compressed copy, the F9 continuation, the
liveness record) runs on a route that reaches play, and keeps the last picture of the delivered file.

A route belongs to one exact disk set (the identity the report calls `rom.sha256`) and holds the numbers of an input script,
never bytes of the game: (first frame, last frame, kind, code, value). Kinds and codes are those of the converter's own
qualification inputs (`retrorecomp.x68000_conversion.valid_qualification_events`): "mouse" codes 0 and 1 move the pointer by
`value` counts a frame (the guest sees one count as one pixel of the game's own screen), 2 is the left button, 3 the right one;
"joy" codes are the libretro joypad ids; "key" codes are X68000 scan codes.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PlayRoute:
    title: str
    frames: int
    events: tuple
    reaches: str


def _lemmings():
    # The intro ends at a click (frames 1700 to 2100: the clicks are spread because the intro's own timing varies);
    # the pointer is then taken to the top-left corner of the picture, moved 32 counts right and 152 down onto the
    # "1 PLAYER" button of the title menu, and clicked; one more click dismisses the level's briefing.
    intro = [(frame, frame + 6, 'mouse', 2, 1) for frame in (1700, 1760, 1900, 2100)]
    to_corner = [(2200, 2230, 'mouse', 0, -64), (2200, 2230, 'mouse', 1, -64)]
    to_button = [(2300, 2304, 'mouse', 0, 8), (2300, 2319, 'mouse', 1, 8)]
    return tuple(intro + to_corner + to_button + [(2340, 2346, 'mouse', 2, 1), (2900, 2906, 'mouse', 2, 1)])


ROUTES = {
    # Lemmings (Imagineer), one disk, mouse game
    '608506d617e0ecf9b416081cd520c66a2424ba5bd005f1077e4311e5197089fc': PlayRoute(
        'Lemmings (Imagineer)', 4000, _lemmings(),
        'Level 1 ("Just dig!") with its lemmings walking out and the time running, from about frame 3,000'),
}
