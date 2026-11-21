"""The ZX Spectrum's routes (MIT): what a conversion plays on the reference, the native check and the delivered game.

The names and lengths are the MSX's (retrorecomp/msx_routes.py, after the PC Engine's): `attract` (no input: the baseline a start
is judged against), `play` (a start, then a walk), and at the extended and thorough levels `long-1`, `long-2` of
`scan_levels.LONG_ROUTE_FRAMES` frames. A route drives what the player's default mapping drives (native/hostkit/adapters/rrhk_zxs.inc):
the directions and fire of pad 1 on the controls the snapshot was saved for (its joystick byte: the cursor keys 5-8 and 0, the
Kempston port, or one of the Sinclair Interface 2's two sets of keys), the start keys of the keyboard.

A snapshot is taken after its game loaded: most show a title or a menu at once, some a pause of their BASIC loader first. How `play`
reaches play is chosen per conversion on the reference (route_start.choose_start) among the start variants: ENTER, SPACE, 0, 1, 5
or pad 1's fire pressed 1, 2, 3 or 4 times, or one of these keys then fire (« press any key », then « press fire to start »), from
FIRST_PRESS, one press every PRESS_SPACING frames. A snapshot whose start no variant finds has reviewed start data instead
(retrorecomp/zxs_starts.py, keyed by its SHA-256). A variant is the presses themselves: (frame, key name) pairs. Then a
deterministic walk seeded by the snapshot (computer_routes.long_events); its first QUIET_WALK frames are directions only.

A script is text, one event per line, `FRAME key ROW BIT DOWN` or `FRAME kempston HEX` (native/zxs_machine/zxs_headless.inc), frames
not decreasing. Everything here is numbers about inputs; nothing reads a ROM.
"""
from __future__ import annotations

from .computer_routes import long_events
from .scan_levels import LONG_ROUTE_FRAMES, LONG_ROUTES

FIRST_PRESS = 150          # frames: three seconds, after the snapshot's first picture
PRESS_SPACING = 240        # frames between two presses of the start
# Frames a press is held: half a second. Some games read their start key only between two notes of a tune (Manic Miner's title
# misses a press of 6 frames and starts on one of 12); it stays under the ROM's key repeat delay (REPDEL, 35 frames), so a menu
# that reads keys through the ROM sees one press.
PRESS_FRAMES = 25
WALK_SETTLE = 180          # frames between the last press and the walk
QUIET_WALK = 900           # frames of walk with directions only
PLAY_FRAMES = 2100         # the shortest play route: four presses and the walk after them fit (Match Day II starts on the fourth)
START_PRESSES = (1, 2, 3, 4)

# The keyboard's half-rows (zxs_machine.h, keys[]): 0 FEFE (CAPS SHIFT Z X C V), 1 FDFE (A-G), 2 FBFE (Q-T), 3 F7FE (1-5), 4 EFFE
# (0 9 8 7 6), 5 DFFE (P O I U Y), 6 BFFE (ENTER L K J H), 7 7FFE (SPACE SYMBOL SHIFT M N B); bit 0 is the outer key of the row.
# Every key of the keyboard by its name, (row, bit) as above.
KEYS = {name: (row, bit) for row, names in enumerate((('CAPS', 'Z', 'X', 'C', 'V'), ('A', 'S', 'D', 'F', 'G'), ('Q', 'W', 'E', 'R', 'T'),
                                                     ('1', '2', '3', '4', '5'), ('0', '9', '8', '7', '6'), ('P', 'O', 'I', 'U', 'Y'),
                                                     ('ENTER', 'L', 'K', 'J', 'H'), ('SPACE', 'SYMBOL', 'M', 'N', 'B')))
        for bit, name in enumerate(names)}
ENTER, SPACE, ZERO, ONE, FIVE = KEYS['ENTER'], KEYS['SPACE'], KEYS['0'], KEYS['1'], KEYS['5']
UP, DOWN, LEFT, RIGHT, FIRE = 'up', 'down', 'left', 'right', 'fire'
# The start candidates: four keys of menus, 5 (Ultimate's « 5 START GAME » and its followers), and pad 1's fire on the controls the
# snapshot was saved for (« press fire to start »: the Kempston port, or the fire key of the cursor or Interface 2 set). FIRE is
# also the name of pad 1's fire in a variant or in start data; every other name is a key of KEYS.
START_KEYS = ('ENTER', 'SPACE', '0', '1', '5', 'FIRE')
MENU_KEYS = (ENTER, SPACE, ZERO, ONE)                 # the walk's keys
MOVES = (UP, DOWN, LEFT, RIGHT)                       # computer_routes' joystick codes 0 to 3

# Pad 1 by the snapshot's joystick byte (zxs_snapshot.JOYSTICKS; a .sna does not say: the cursor keys). The same table as the player's
# default mapping (rrhk_zxs.inc).
PAD_KEYS = {
    'cursor': {LEFT: (3, 4), DOWN: (4, 4), UP: (4, 3), RIGHT: (4, 2), FIRE: (4, 0)},           # 5 6 7 8 and 0
    'sinclair-left': {LEFT: (3, 0), RIGHT: (3, 1), DOWN: (3, 2), UP: (3, 3), FIRE: (3, 4)},    # 1 2 3 4 5
    'sinclair-right': {LEFT: (4, 4), RIGHT: (4, 3), DOWN: (4, 2), UP: (4, 1), FIRE: (4, 0)},   # 6 7 8 9 0
}
KEMPSTON_BIT = {RIGHT: 0x01, LEFT: 0x02, DOWN: 0x04, UP: 0x08, FIRE: 0x10}


def repeated(presses: int, key: str) -> tuple:
    """The variant that presses `key` `presses` times, one press every PRESS_SPACING frames from FIRST_PRESS."""
    return tuple((FIRST_PRESS + PRESS_SPACING * index, key) for index in range(presses))


def then_fire(key: str) -> tuple:
    """The variant that presses `key`, then pad 1's fire."""
    return (FIRST_PRESS, key), (FIRST_PRESS + PRESS_SPACING, 'FIRE')


def walk_start(variant) -> int:
    """The first frame of the walk after the variant's presses."""
    return max(900, variant[-1][0] + PRESS_SPACING + WALK_SETTLE)


def candidates(frames: int) -> list:
    """The start variants that leave a route of `frames` at least ten seconds of walk."""
    variants = [repeated(presses, key) for key in START_KEYS for presses in START_PRESSES]
    variants += [then_fire(key) for key in START_KEYS if key != 'FIRE']
    return [variant for variant in variants if walk_start(variant) + 600 <= frames]


def variant_name(variant) -> str:
    """`2xENTER` for a key pressed twice, `ENTER+FIRE` for different keys in turn."""
    keys = [key for _, key in variant]
    return f'{len(keys)}x{keys[0]}' if len(set(keys)) == 1 else '+'.join(keys)


def variant_order(variant) -> tuple:
    """The tie-break of route_start.choose_start: the fewest presses, then ENTER, SPACE, 0, 1, 5, fire (in press order)."""
    return len(variant), tuple(START_KEYS.index(key) if key in START_KEYS else len(START_KEYS) for _, key in variant)


def route_seed(identity: str, name: str) -> int:
    """The walk's seed: the snapshot's, one more step per long route (as the MSX's)."""
    seed = int(identity[:8], 16)
    return seed + 7919 * int(name.split('-')[1]) if name.startswith('long-') else seed


def press_input(key: str):
    """What a press of `key` holds: pad 1's fire, or a key (row, bit)."""
    if key == 'FIRE':
        return FIRE
    if key not in KEYS:
        raise ValueError(f'not a ZX Spectrum key: {key!r}')
    return KEYS[key]


def _intervals(frames: int, seed: int, variant) -> list[tuple[int, int, object]]:
    """(first frame, end frame, input) with the input held over [first, end): a direction or fire, or a key (row, bit)."""
    held = [(at, at + PRESS_FRAMES, press_input(key)) for at, key in variant]
    start = walk_start(variant)
    for first, last, kind, code, _value in long_events(str(seed), frames, MENU_KEYS, start=start):
        quiet = first < start + QUIET_WALK
        if kind == 'joy' and code < len(MOVES):
            held.append((first, min(last, frames), MOVES[code]))
        elif kind == 'joy' and not quiet:
            held.append((first, min(last, frames), FIRE))
        elif kind == 'key' and not quiet:
            held.append((first, min(last, frames), code))
    return [interval for interval in held if interval[0] < interval[1] <= frames]


def events(frames: int, seed: int, variant, joystick: str | None) -> list[tuple]:
    """The route's events, in frame order: ('key', frame, row, bit, down) and ('kempston', frame, bits) at each frame where what is
    held changes. `joystick` is the snapshot's (zxs_snapshot.JOYSTICKS, None for a .sna)."""
    pad = None if joystick == 'kempston' else PAD_KEYS.get(joystick or 'cursor', PAD_KEYS['cursor'])
    intervals = _intervals(frames, seed, variant)
    changes = sorted({first for first, _, _ in intervals} | {end for _, end, _ in intervals})
    out = []
    kempston, keys = 0, set()
    for frame in changes:
        if frame >= frames:
            break
        held = [what for first, end, what in intervals if first <= frame < end]
        directions = [what for what in held if what in KEMPSTON_BIT]
        bits = sum({KEMPSTON_BIT[what] for what in directions}) if pad is None else 0
        now = {what for what in held if isinstance(what, tuple)}
        if pad is not None:
            now |= {pad[what] for what in directions}
        for row, bit in sorted(keys - now):
            out.append(('key', frame, row, bit, 0))
        for row, bit in sorted(now - keys):
            out.append(('key', frame, row, bit, 1))
        if bits != kempston:
            out.append(('kempston', frame, bits))
        kempston, keys = bits, now
    return out


def script(route_events: list[tuple]) -> str:
    """The text the headless programs read (`--script FILE`), in frame order."""
    lines = []
    for event in sorted(route_events, key=lambda event: event[1]):
        if event[0] == 'key':
            lines.append(f'{event[1]} key {event[2]} {event[3]} {event[4]}\n')
        else:
            lines.append(f'{event[1]} kempston {event[2]:02X}\n')
    return ''.join(lines)


def routes(identity: str, *, frames: int, level: str, variant=None, joystick: str | None = 'cursor') -> list:
    """(name, frames, script) of a conversion at `level`: attract and play (play alone at the quick level), then the long routes."""
    variant = variant or repeated(1, 'ENTER')
    rows = [] if level == 'quick' else [('attract', frames, '')]
    play = max(frames, PLAY_FRAMES)
    rows.append(('play', play, script(events(play, route_seed(identity, 'play'), variant, joystick))))
    for index in range(LONG_ROUTES[level]):
        name = f'long-{index + 1}'
        rows.append((name, LONG_ROUTE_FRAMES, script(events(LONG_ROUTE_FRAMES, route_seed(identity, name), variant, joystick))))
    return rows
