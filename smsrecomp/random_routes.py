"""Reproducible pseudo-random controller routes for long discovery scans.

Host inputs only: no guest memory or game code is ever patched. Seeds derive
from the console and the exact ROM identity, so every conversion of the same
game replays the same routes, and the same script drives both the native
export and its reference run. The model is the X68000 long route generator
(``x68000_scan.long_routes``): long movement phases, often with a held button,
short button taps, paired Start presses and neutral pauses between phases.

A route is an abstract timeline of controller states. Every route boots the
game afresh by default. On request (``long_routes(chain=True)``) routes after
the first one *continue* from the saved end state of the previous route
(``Route.continues_from``): the host saves the machine state at the last frame
of one route and restores it before the first frame of the next. A chained
route emits no opening (no credit, Start presses or confirmations) and its
pseudo-random body is the same as the standalone route's, starting after a
short neutral pause. Measured on 23 October 2026 (Sonic, Donkey Kong Country),
chaining found no new opcode variant because the routes do not progress past
the first screen, so it stays off until the route body does. Console adapters
turn a route into the text format each headless host already reads:

* Mega Drive / Super Nintendo: ``frame p1 p2`` decimal masks (``--input-script``,
  at most 4,096 lines, strictly increasing frames);
* NES: ``frame BUTTON+BUTTON`` names, ``-`` for release, ``2:`` for player 2
  (``--input``);
* Neo Geo: ``frame p1 p2 coin start`` hexadecimal (``--script``, at most
  8,192 lines, non-decreasing frames).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import random

LONG_ROUTE_COUNT = 2
LONG_ROUTE_FRAMES = 18000
# Neutral frames at the start of a route that continues from a saved state.
CHAIN_SETTLE_FRAMES = 60
CONSOLE16_LINE_LIMIT = 4096
NEOGEO_LINE_LIMIT = 8192

DIRECTIONS = ('up', 'down', 'left', 'right')
# Side-scrollers progress to the right; keep every direction reachable.
DIRECTION_WEIGHTS = (1, 1, 1, 2)

# Buttons a route may press, per console. ``main`` buttons are held during
# movement and tapped; ``extra`` buttons are only used when the game declares
# a six-button pad (Mega Drive) and are always available on the SNES pad.
CONSOLES = {
    'md': {'main': ('a', 'b', 'c'), 'extra': ('x', 'y', 'z'), 'select': None, 'opening': 240},
    'snes': {'main': ('a', 'b', 'x', 'y'), 'extra': ('l', 'r'), 'select': 'select', 'opening': 240},
    'nes': {'main': ('a', 'b'), 'extra': (), 'select': 'select', 'opening': 180},
    'ng': {'main': ('a', 'b', 'c', 'd'), 'extra': (), 'select': None, 'opening': 2400},
}

MD_BITS = {'up': 0x01, 'down': 0x02, 'left': 0x04, 'right': 0x08, 'b': 0x10, 'c': 0x20,
           'a': 0x40, 'start': 0x80, 'x': 0x100, 'y': 0x200, 'z': 0x400}
SNES_BITS = {'b': 0x01, 'y': 0x02, 'select': 0x04, 'start': 0x08, 'up': 0x10, 'down': 0x20,
             'left': 0x40, 'right': 0x80, 'a': 0x100, 'x': 0x200, 'l': 0x400, 'r': 0x800}
NEOGEO_BITS = {'up': 0x01, 'down': 0x02, 'left': 0x04, 'right': 0x08,
               'a': 0x10, 'b': 0x20, 'c': 0x40, 'd': 0x80}
NES_NAMES = {'a': 'A', 'b': 'B', 'select': 'SELECT', 'start': 'START',
             'up': 'UP', 'down': 'DOWN', 'left': 'LEFT', 'right': 'RIGHT'}


@dataclass(frozen=True)
class Step:
    frame: int
    p1: frozenset
    p2: frozenset
    coin: int = 0  # Neo Geo only: 1 = player 1 coin switch held


@dataclass(frozen=True)
class Route:
    name: str
    console: str
    seed: str
    index: int
    frames: int
    steps: tuple
    continues_from: str | None = None  # previous route whose saved end state starts this one

    def metadata(self) -> dict:
        return {'scenario': self.name, 'seed': self.seed, 'index': self.index,
                'frames': self.frames, 'steps': len(self.steps),
                'continues_from': self.continues_from,
                'generator': 'random_routes.long_route'}


def route_seed(console: str, identity: str, index: int) -> str:
    return f'{console}-long:{identity}:{index}'


def long_route(console: str, identity: str, index: int, *, frames: int = LONG_ROUTE_FRAMES,
               six_buttons: bool = False, two_players: bool = True,
               continues_from: str | None = None) -> Route:
    """One long varied route, fully determined by (console, identity, index).

    With ``continues_from`` (the name of the previous route) the route starts
    from that route's saved end state: the opening is not emitted and the body
    begins after ``CHAIN_SETTLE_FRAMES`` neutral frames. The body draws the
    same random numbers as the standalone route, so both play the same phases;
    only the opening and the start time differ, and the chained route keeps
    playing new phases where the standalone one would have ended.
    """
    if console not in CONSOLES:
        raise ValueError(f'No random route vocabulary for console {console!r}.')
    if frames < 600:
        raise ValueError('Long routes need at least 600 frames.')
    layout = CONSOLES[console]
    main = layout['main'] + (layout['extra'] if six_buttons or console == 'snes' else ())
    seed = route_seed(console, identity, index)
    rng = random.Random(seed)
    last = frames - 1
    timeline: dict[int, Step] = {}
    state = {'p1': frozenset(), 'p2': frozenset(), 'coin': 0}

    def emit(frame: int, p1=None, p2=None, coin=None) -> None:
        frame = min(max(frame, 0), last)
        if p1 is not None:
            state['p1'] = frozenset(p1)
        if p2 is not None:
            state['p2'] = frozenset(p2)
        if coin is not None:
            state['coin'] = coin
        timeline[frame] = Step(frame, state['p1'], state['p2'], state['coin'])

    def tap(frame: int, buttons, length: int, player: str = 'p1', pressed: bool = True) -> int:
        if pressed:
            emit(frame, **{player: set(buttons)})
            emit(frame + length, **{player: set()})
        return frame + length

    opening = continues_from is None
    emit(0)
    frame = layout['opening'] + rng.randint(0, 120)
    if console == 'ng':
        # Arcade boards need a credit before Start does anything.
        if opening:
            emit(frame, coin=1)
            emit(frame + 8, coin=0)
        frame += 60 + rng.randint(0, 60)
    # Leave title and menu screens: a few spaced Start presses, then one to
    # three confirmations with a main button for games that want A/B/C. A
    # chained route is already in the game: it draws the same numbers so the
    # body below stays identical, but presses nothing before the body.
    for _ in range(rng.randint(2, 4)):
        frame = tap(frame, {'start'}, 4, pressed=opening) + rng.randint(120, 240)
    for _ in range(rng.randint(1, 3)):
        frame = tap(frame, {rng.choice(main)}, 6, pressed=opening) + rng.randint(60, 150)
    if not opening:
        frame = CHAIN_SETTLE_FRAMES
    while frame < frames - 200:
        roll = rng.random()
        if roll < 0.45:                               # move, often holding a button
            length = rng.randint(20, 160)
            held = {rng.choices(DIRECTIONS, DIRECTION_WEIGHTS)[0]}
            if rng.random() < 0.7:
                held.add(rng.choice(main))
            emit(frame, p1=held)
            if length > 40 and rng.random() < 0.5:    # jump or fire while moving
                press = frame + rng.randint(8, length - 20)
                emit(press, p1=held | {rng.choice(main)})
                emit(press + rng.randint(3, 10), p1=held)
            emit(frame + length, p1=set())
            frame += length
        elif roll < 0.70:                             # short button taps
            frame = tap(frame, {rng.choice(main)}, rng.randint(3, 12))
        elif roll < 0.78:                             # Start twice: pause and resume, or a menu step
            gap = rng.randint(20, 60)
            tap(frame, {'start'}, 4)
            frame = tap(frame + gap, {'start'}, 4)
        elif roll < 0.84 and layout['select']:        # Select: item or mode switches
            frame = tap(frame, {layout['select']}, 6)
        elif roll < 0.90 and two_players:             # player 2 wakes two-player paths
            frame = tap(frame, {rng.choice(main + ('start',))}, 6, 'p2')
        # otherwise an idle pause
        frame += rng.randint(30, 120)
    emit(last, p1=set(), p2=set(), coin=0)
    steps = tuple(timeline[key] for key in sorted(timeline))
    return Route(f'long-{index + 1}', console, seed, index, frames, steps, continues_from)


def long_routes(console: str, identity: str, *, count: int = LONG_ROUTE_COUNT,
                frames: int = LONG_ROUTE_FRAMES, chain: bool = False, **options) -> tuple:
    """``count`` independent routes; with ``chain`` every route after the first
    continues from the saved end state of the previous one instead of a fresh boot."""
    routes = []
    for index in range(count):
        previous = routes[-1].name if chain and routes else None
        routes.append(long_route(console, identity, index, frames=frames,
                                 continues_from=previous, **options))
    return tuple(routes)


def _mask(buttons, bits: dict) -> int:
    value = 0
    for name in buttons:
        value |= bits.get(name, 0)
    return value


def console16_script(route: Route) -> str:
    """``frame p1 p2`` lines for console16_main.c (Mega Drive and SNES)."""
    bits = MD_BITS if route.console == 'md' else SNES_BITS
    lines = [f'{step.frame} {_mask(step.p1, bits)} {_mask(step.p2, bits)}\n' for step in route.steps]
    if len(lines) > CONSOLE16_LINE_LIMIT:
        raise ValueError(f'Route {route.name} has {len(lines)} lines; the 16-bit replay holds {CONSOLE16_LINE_LIMIT}.')
    return ''.join(lines)


def nes_script(route: Route) -> str:
    """``frame BUTTONS`` lines for the NES host; player 2 lines carry ``2:``."""
    def keys(buttons) -> str:
        names = [NES_NAMES[name] for name in NES_NAMES if name in buttons]
        return '+'.join(names) if names else '-'
    lines, previous = [], (frozenset(), frozenset())
    for step in route.steps:
        if step.p1 != previous[0] or step.frame == 0:
            lines.append(f'{step.frame} {keys(step.p1)}\n')
        if step.p2 != previous[1]:
            lines.append(f'{step.frame} 2:{keys(step.p2)}\n')
        previous = (step.p1, step.p2)
    return ''.join(lines)


def neogeo_script(route: Route) -> str:
    """``frame p1 p2 coin start`` hexadecimal lines for neogeo_main.c."""
    lines = []
    for step in route.steps:
        start = (1 if 'start' in step.p1 else 0) | (2 if 'start' in step.p2 else 0)
        lines.append(f'{step.frame} {_mask(step.p1, NEOGEO_BITS):02x} {_mask(step.p2, NEOGEO_BITS):02x} '
                     f'{step.coin:x} {start:x}\n')
    if len(lines) > NEOGEO_LINE_LIMIT:
        raise ValueError(f'Route {route.name} has {len(lines)} lines; the Neo Geo script holds {NEOGEO_LINE_LIMIT}.')
    return ''.join(lines)


def script_text(route: Route) -> str:
    if route.console in ('md', 'snes'):
        return console16_script(route)
    if route.console == 'nes':
        return nes_script(route)
    if route.console == 'ng':
        return neogeo_script(route)
    raise ValueError(route.console)


def write_route(route: Route, directory: Path) -> Path:
    """Write the route's script beside the other probe scripts (ASCII, LF)."""
    suffix = '.input' if route.console == 'nes' else '.inputs' if route.console == 'ng' else '-inputs.txt'
    path = Path(directory) / f'{route.name}{suffix}'
    path.write_text(script_text(route), encoding='ascii', newline='\n')
    return path
