"""The Amstrad CPC conversion's routes (retrorecomp/cpc_conversion.py): what the headless programs play after the start command.
MIT, Retro-Recomp.

A CPC game is started by typing its command (the boot keys, cpc_keys.py). The `boot` route plays nothing else: the firmware, the
loader and whatever the game shows by itself. The `play` route then presses what CPC games ask for once loaded, from PLAY_FROM on:
SPACE, N (the « Y/N » questions of the trainers many disks carry: no, the game as it was), J (« J - Joystick » of the control
menus), 1, the joystick's fire, RETURN and 2 (the usual « press fire / space / 1 to start » of a title screen), between
runs of the joystick held a few frames in one direction (fire sometimes), all from a seed of the disk's SHA-256, so the same disk
plays the same route on every PC. The script is native/cpc_machine/cpc_headless.inc's --script (`FRAME key CPCKEY 0|1`,
`FRAME joy PORT HEX`).

Game role, the cpc group of retrorecomp/stamp_inputs.py.
"""
from __future__ import annotations

import hashlib
import random

PLAY_FROM = 900                  # frames: the start command typed at 60, most disks loaded within 15 seconds
# CPC keys (native/cpc_machine/cpc_ppi.h: row * 8 + bit)
KEY_SPACE, KEY_RETURN, KEY_1, KEY_2, KEY_N, KEY_J = 5 * 8 + 7, 2 * 8 + 2, 8 * 8 + 0, 8 * 8 + 1, 5 * 8 + 6, 5 * 8 + 5
JOY_UP, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_FIRE2, JOY_FIRE1 = 0x01, 0x02, 0x04, 0x08, 0x10, 0x20
DIRECTIONS = (JOY_UP, JOY_DOWN, JOY_LEFT, JOY_RIGHT, JOY_UP | JOY_LEFT, JOY_UP | JOY_RIGHT, JOY_DOWN | JOY_LEFT,
              JOY_DOWN | JOY_RIGHT)
START_KEYS = (('key', KEY_SPACE), ('key', KEY_N), ('key', KEY_J), ('key', KEY_1), ('joy', JOY_FIRE1), ('key', KEY_RETURN),
              ('key', KEY_2))
START_FOR = 2400                 # frames after PLAY_FROM during which the start keys come back every 150 frames


def seed(disk_sha256: str) -> int:
    return int(hashlib.sha256(('cpc-play-2:' + disk_sha256).encode('ascii')).hexdigest()[:16], 16)


def play_events(frames: int, disk_sha256: str) -> list[tuple[int, str, int, int]]:
    """(frame, kind, code, value) in order: a start key every 150 frames for START_FOR frames after PLAY_FROM, and
    between them, and after, the joystick held 6 to 40 frames in a direction (with fire one time in three), then released."""
    rng = random.Random(seed(disk_sha256))
    events: list[tuple[int, str, int, int]] = []
    frame = PLAY_FROM
    start_until = PLAY_FROM + START_FOR
    next_start = PLAY_FROM
    while frame < frames - 2:
        if frame >= next_start and frame < start_until:
            kind, code = START_KEYS[(next_start - PLAY_FROM) // 150 % len(START_KEYS)]
            if kind == 'key':
                events += [(frame, 'key', code, 1), (frame + 4, 'key', code, 0)]
            else:
                events += [(frame, 'joy', 0, code), (frame + 4, 'joy', 0, 0)]
            frame += 8
            next_start += 150
            continue
        held = rng.randint(6, 40)
        bits = rng.choice(DIRECTIONS) | (JOY_FIRE1 if rng.random() < 1 / 3 else 0)
        end = min(frame + held, frames - 1, next_start if frame < start_until else frames - 1)
        if end <= frame:
            frame += 1
            continue
        events += [(frame, 'joy', 0, bits), (end, 'joy', 0, 0)]
        frame = end + rng.randint(1, 8)
    return [event for event in events if event[0] < frames]


def script(events) -> str:
    """The --script text of `events`."""
    lines = []
    for frame, kind, code, value in events:
        lines.append(f'{frame} {kind} {code} {value:x}' if kind == 'joy' else f'{frame} key {code} {value}')
    return ''.join(line + '\n' for line in lines)
