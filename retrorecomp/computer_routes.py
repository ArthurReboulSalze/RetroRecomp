"""A long varied route for a computer with a joystick, a mouse and a keyboard (MIT): joystick phases with the fire held at times, taps, menu keys, mouse moves and clicks.

Fully determined by its seed, so every conversion of the same game replays the same route. The model is the X68000's and the Atari ST's (`x68000_scan.long_routes`, `atarist_conversion.long_route`), which keep their
own for now so that their stamps do not move; `tests/test_computer_routes.py` shows this body draws the same route as the Atari ST's. A route does not finish a game. Events are (first frame, last frame, kind, code, value).
"""
from __future__ import annotations

import random

MOVES = (0, 1, 2, 3, 3)
FIRE = 4
MOUSE_STEPS = (-6, -2, 2, 6)


def long_events(seed: str, frames: int, keys: tuple, *, start: int = 300) -> list:
    """The route of this seed; `keys` are the menu keys in the host's own codes, chosen from when a key is due."""
    rng = random.Random(seed)
    events = []
    frame = start
    while frame < frames - 200:
        roll = rng.random()
        if roll < 0.5:                             # move, often firing
            length = rng.randint(20, 160)
            events.append((frame, frame + length, 'joy', rng.choice(MOVES), 1))
            if rng.random() < 0.6:
                events.append((frame, frame + length, 'joy', FIRE, 1))
        elif roll < 0.72:                          # fire taps
            events.append((frame, frame + rng.randint(3, 12), 'joy', FIRE, 1))
        elif roll < 0.84:                          # menu keys
            events.append((frame, frame + 6, 'key', rng.choice(keys), 1))
        else:                                      # mouse move and click
            events.append((frame, frame + 20, 'mouse', rng.choice((0, 1)), rng.choice(MOUSE_STEPS)))
            if rng.random() < 0.5:
                events.append((frame + 22, frame + 28, 'mouse', 2, 1))
        frame += rng.randint(30, 120)
    return sorted(events)
