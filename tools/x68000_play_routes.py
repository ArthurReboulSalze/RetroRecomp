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


def _super_hang_on():
    # The title counts down from 99 about once a second while the game loads and sets its sound module up (it sends a long run of MIDI
    # notes and SysEx): it takes no start before the counter is at 0, about frame 8,500. Then each input is tried in turn, a hundred and
    # fifty frames apart: Enter, Space, the A and B buttons, Start and the 1 key, which brings the game to its first stage.
    inputs = (('key', 13), ('key', 32), ('joy', 8), ('joy', 0), ('joy', 3), ('key', 49))
    return tuple((8900 + 150 * n, 8906 + 150 * n, kind, code, 1) for n, (kind, code) in enumerate(inputs))


ROUTES = {
    # Lemmings (Imagineer), one disk, mouse game
    '608506d617e0ecf9b416081cd520c66a2424ba5bd005f1077e4311e5197089fc': PlayRoute(
        'Lemmings (Imagineer)', 4000, _lemmings(),
        'Level 1 ("Just dig!") with its lemmings walking out and the time running, from about frame 3,000'),
    # Super Hang-On (Sharp / SPS), two disks (the playlist of the set)
    '01679c4b5df27b4e8aa76cd5adf7b18018f41e867cb2516193c91dcfece02270': PlayRoute(
        'Super Hang-On (Sharp - SPS)', 10000, _super_hang_on(),
        'The first stage, course Africa, with the bike running (score 4,310 and speed 93 km at frame 10,000)'),
}
