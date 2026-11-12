"""The MSX's routes (MIT): what a conversion plays on the reference, the native check and the delivered game.

The names and lengths are the PC Engine's (`pce_conversion.routes`): `attract` (no input: the baseline a start is judged
against), `play` (a start, then a walk), and at the extended and thorough levels `long-1`, `long-2` of
`scan_levels.LONG_ROUTE_FRAMES` frames. A route drives what a player's default mapping drives (rrhk_msx.inc): a direction is
joystick 1's bit and the cursor key together, fire is trigger A and SPACE together; F1 and STOP are never pressed.

How `play` reaches play is chosen per conversion on the reference, as the PC Engine chooses (route_start.choose_start): fire
pressed 1, 2, 3, 4 or 6 times from frame 480 (after the C-BIOS logo), one press every 240 frames, or 1, 2 or 3 times each
followed by RETURN (a keyboard menu). Then a deterministic walk seeded by the cartridge (computer_routes.long_events, its mouse
dropped); its first QUIET_WALK frames are directions only, so `reach` counts what the pad moved, not what a key typed.

A script is text, one event per line, `FRAME key ROW BIT DOWN` or `FRAME joy PORT HEX` (msx_route.inc), frames not decreasing.
Everything here is numbers about inputs; nothing reads a ROM.
"""
from __future__ import annotations

from .computer_routes import long_events
from .scan_levels import LONG_ROUTE_FRAMES, LONG_ROUTES

FIRST_PRESS = 480          # frames: after the C-BIOS logo (about 6 s on a 60 Hz set)
PRESS_SPACING = 240        # frames between two presses of the start
PRESS_FRAMES = 6           # frames a press of the start is held
CONFIRM_DELAY = 60         # frames from a fire press to the RETURN that follows it
WALK_SETTLE = 180          # frames between the last press and the walk
QUIET_WALK = 900           # frames of walk with directions only
PLAY_FRAMES = 1800         # the shortest play route
START_PRESSES = (1, 2, 3, 4, 6)
CONFIRM_PRESSES = (1, 2, 3)

# The keyboard matrix (row, bit): the cursor keys and SPACE share row 8; RETURN is row 7 bit 7; '1' and '2' row 0.
UP, DOWN, LEFT, RIGHT, FIRE = 'up', 'down', 'left', 'right', 'fire'
CURSOR = {UP: (8, 5), DOWN: (8, 6), LEFT: (8, 4), RIGHT: (8, 7), FIRE: (8, 0)}
JOY_BIT = {UP: 0x01, DOWN: 0x02, LEFT: 0x04, RIGHT: 0x08, FIRE: 0x10}
RETURN, ONE, TWO = (7, 7), (0, 1), (0, 2)
MENU_KEYS = (RETURN, (8, 0), ONE, TWO)            # the walk's menu keys: RETURN, SPACE, 1, 2
MOVES = (UP, DOWN, LEFT, RIGHT)                   # computer_routes' joystick codes 0 to 3


def walk_start(presses: int) -> int:
    return max(900, FIRST_PRESS + PRESS_SPACING * presses + WALK_SETTLE)


def candidates(frames: int) -> list:
    """The start variants that leave a route of `frames` at least ten seconds of walk: an int (presses of fire) or
    (presses, 'RETURN')."""
    plain = [presses for presses in START_PRESSES if walk_start(presses) + 600 <= frames]
    confirm = [(presses, 'RETURN') for presses in CONFIRM_PRESSES if walk_start(presses) + 600 <= frames]
    return [*plain, *confirm]


def presses_of(variant) -> int:
    return variant[0] if isinstance(variant, tuple) else variant


def variant_name(variant) -> str:
    return f'{variant[0]}+{variant[1]}' if isinstance(variant, tuple) else str(variant)


def variant_order(variant) -> tuple:
    """The tie-break of route_start.choose_start: the fewest presses, then the plain variant."""
    return presses_of(variant), isinstance(variant, tuple)


def route_seed(identity: str, name: str) -> int:
    """The walk's seed: the cartridge's, one more step per long route (as the PC Engine's)."""
    seed = int(identity[:8], 16)
    return seed + 7919 * int(name.split('-')[1]) if name.startswith('long-') else seed


def _intervals(frames: int, seed: int, variant) -> list[tuple[int, int, object]]:
    """(first frame, end frame, input) with the input held over [first, end): a direction or fire, or a key (row, bit)."""
    presses = presses_of(variant)
    held = []
    for index in range(presses):
        at = FIRST_PRESS + PRESS_SPACING * index
        held.append((at, at + PRESS_FRAMES, FIRE))
        if isinstance(variant, tuple):
            held.append((at + CONFIRM_DELAY, at + CONFIRM_DELAY + PRESS_FRAMES, RETURN))
    start = walk_start(presses)
    for first, last, kind, code, _value in long_events(str(seed), frames, MENU_KEYS, start=start):
        quiet = first < start + QUIET_WALK
        if kind == 'joy' and code < len(MOVES):
            held.append((first, min(last, frames), MOVES[code]))
        elif kind == 'joy' and not quiet:
            held.append((first, min(last, frames), FIRE))
        elif kind == 'key' and not quiet:
            held.append((first, min(last, frames), code))
    return [interval for interval in held if interval[0] < interval[1] <= frames]


def events(frames: int, seed: int, variant) -> list[tuple]:
    """The route's events, in frame order: ('key', frame, row, bit, down) and ('joy', frame, port, bits) at each frame where
    what is held changes."""
    intervals = _intervals(frames, seed, variant)
    changes = sorted({first for first, _, _ in intervals} | {end for _, end, _ in intervals})
    out = []
    joy, keys = 0x3F, set()
    for frame in changes:
        if frame >= frames:
            break
        held = [what for first, end, what in intervals if first <= frame < end]
        bits = 0x3F & ~sum({JOY_BIT[what] for what in held if what in JOY_BIT})
        now = {CURSOR[what] for what in held if what in CURSOR} | {what for what in held if isinstance(what, tuple)}
        for row, bit in sorted(keys - now):
            out.append(('key', frame, row, bit, 0))
        for row, bit in sorted(now - keys):
            out.append(('key', frame, row, bit, 1))
        if bits != joy:
            out.append(('joy', frame, 0, bits))
        joy, keys = bits, now
    return out


def script(route_events: list[tuple]) -> str:
    """The text the headless programs read (`--script FILE`)."""
    lines = []
    for event in route_events:
        if event[0] == 'key':
            lines.append(f'{event[1]} key {event[2]} {event[3]} {event[4]}\n')
        else:
            lines.append(f'{event[1]} joy {event[2]} {event[3]:02X}\n')
    return ''.join(lines)


def routes(identity: str, *, frames: int, level: str, variant=1) -> list[tuple[str, int, str]]:
    """(name, frames, script) of a conversion at `level`: attract and play (play alone at the quick level), then the long
    routes. `variant` is the chosen start (an int, or (presses, 'RETURN'))."""
    rows = [] if level == 'quick' else [('attract', frames, '')]
    play = max(frames, PLAY_FRAMES)
    rows.append(('play', play, script(events(play, route_seed(identity, 'play'), variant))))
    for index in range(LONG_ROUTES[level]):
        name = f'long-{index + 1}'
        rows.append((name, LONG_ROUTE_FRAMES, script(events(LONG_ROUTE_FRAMES, route_seed(identity, name), variant))))
    return rows
