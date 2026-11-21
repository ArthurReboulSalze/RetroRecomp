"""The SG-1000's routes (MIT): what a conversion plays on the reference and on the native check.

The names and lengths are the MSX's and the PC Engine's: `attract` (no input: the baseline a start is judged against), `play` (a start,
then a walk), and at the extended and thorough levels `long-1`, `long-2` of `scan_levels.LONG_ROUTE_FRAMES` frames. A route drives pad 1
(the D-pad and buttons 1 and 2) and never the Pause button: a script that wants it adds a `pause` event by hand (`script`).

There is no firmware to wait for, so the first press comes early; how `play` reaches play is chosen per conversion on the reference
(route_start.choose_start, as the MSX): button 1, button 2 or both pressed 1, 2 or 3 times, one press every PRESS_SPACING frames. Then a
deterministic walk seeded by the cartridge (computer_routes.long_events, its mouse dropped; its menu keys are the two buttons); its first
QUIET_WALK frames are directions only, so `reach` counts what the D-pad moved, not what a button pressed.

A script is text, one event per line, `FRAME pad PORT HEX` (the buttons held on pad PORT, the SG_PAD_* bits of native/sg1000_machine) or
`FRAME pause`, frames not decreasing: the format native/sg1000_machine/sg1000_headless.inc reads. Everything here is numbers about
inputs; nothing reads a ROM.
"""
from __future__ import annotations

from .computer_routes import long_events
from .scan_levels import LONG_ROUTE_FRAMES, LONG_ROUTES

FIRST_PRESS = 180          # frames: a cartridge boots at once, its title is up in about three seconds
PRESS_SPACING = 180        # frames between two presses of the start
PRESS_FRAMES = 6           # frames a press of the start is held
WALK_SETTLE = 180          # frames between the last press and the walk
QUIET_WALK = 900           # frames of walk with directions only
PLAY_FRAMES = 1800         # the shortest play route
START_PRESSES = (1, 2, 3)

# The pad bits, as native/sg1000_machine/sg1000_machine.h holds them (a set bit is a held button).
UP, DOWN, LEFT, RIGHT, B1, B2 = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
START_BUTTONS = (B1, B2, B1 | B2)
MOVES = (UP, DOWN, LEFT, RIGHT)                   # computer_routes' joystick codes 0 to 3
MENU_KEYS = (B1, B2)                              # the walk's menu keys: the two buttons


def walk_start(presses: int) -> int:
    return max(900, FIRST_PRESS + PRESS_SPACING * presses + WALK_SETTLE)


def candidates(frames: int) -> list[tuple[int, int]]:
    """The start variants, (buttons held, presses), that leave a route of `frames` at least ten seconds of walk."""
    return [(buttons, presses) for presses in START_PRESSES for buttons in START_BUTTONS if walk_start(presses) + 600 <= frames]


def variant_name(variant: tuple[int, int]) -> str:
    buttons, presses = variant
    return f'{"1" if buttons & B1 else ""}{"2" if buttons & B2 else ""}x{presses}'


def variant_order(variant: tuple[int, int]) -> tuple:
    """The tie-break of route_start.choose_start: the fewest presses, then the fewest buttons, then button 1 first."""
    buttons, presses = variant
    return presses, bin(buttons).count('1'), buttons


def route_seed(identity: str, name: str) -> int:
    """The walk's seed: the cartridge's, one more step per long route (as the PC Engine's and the MSX's)."""
    seed = int(identity[:8], 16)
    return seed + 7919 * int(name.split('-')[1]) if name.startswith('long-') else seed


def _intervals(frames: int, seed: int, variant: tuple[int, int]) -> list[tuple[int, int, int]]:
    """(first frame, end frame, buttons) with the buttons held over [first, end)."""
    buttons, presses = variant
    held = [(FIRST_PRESS + PRESS_SPACING * index, FIRST_PRESS + PRESS_SPACING * index + PRESS_FRAMES, buttons)
            for index in range(presses)]
    start = walk_start(presses)
    for first, last, kind, code, _value in long_events(str(seed), frames, MENU_KEYS, start=start):
        quiet = first < start + QUIET_WALK
        if kind == 'joy' and code < len(MOVES):
            held.append((first, min(last, frames), MOVES[code]))
        elif kind == 'joy' and not quiet:
            held.append((first, min(last, frames), B1))
        elif kind == 'key' and not quiet:
            held.append((first, min(last, frames), code))
    return [interval for interval in held if interval[0] < interval[1] <= frames]


def events(frames: int, seed: int, variant: tuple[int, int]) -> list[tuple]:
    """The route's events, in frame order: ('pad', frame, port, bits) at each frame where what pad 1 holds changes."""
    intervals = _intervals(frames, seed, variant)
    changes = sorted({first for first, _, _ in intervals} | {end for _, end, _ in intervals})
    out, held_now = [], 0
    for frame in changes:
        if frame >= frames:
            break
        bits = 0
        for first, end, buttons in intervals:
            if first <= frame < end:
                bits |= buttons
        if bits != held_now:
            out.append(('pad', frame, 0, bits))
            held_now = bits
    return out


def script(route_events: list[tuple]) -> str:
    """The text the headless programs read (`--script FILE`), in frame order: ('pad', frame, port, bits) or ('pause', frame)."""
    lines = []
    for event in sorted(route_events, key=lambda event: event[1]):
        lines.append(f'{event[1]} pause\n' if event[0] == 'pause' else f'{event[1]} pad {event[2]} {event[3]:02X}\n')
    return ''.join(lines)


def routes(identity: str, *, frames: int, level: str, variant: tuple[int, int] = (B1, 1)) -> list[tuple[str, int, str]]:
    """(name, frames, script) of a conversion at `level`: attract and play (play alone at the quick level), then the long routes.
    `variant` is the chosen start."""
    rows = [] if level == 'quick' else [('attract', frames, '')]
    play = max(frames, PLAY_FRAMES)
    rows.append(('play', play, script(events(play, route_seed(identity, 'play'), variant))))
    for index in range(LONG_ROUTES[level]):
        name = f'long-{index + 1}'
        rows.append((name, LONG_ROUTE_FRAMES, script(events(LONG_ROUTE_FRAMES, route_seed(identity, name), variant))))
    return rows
