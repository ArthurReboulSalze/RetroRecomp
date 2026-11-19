"""Scripted controls for hidden games, chosen by name so that a worker process can be told them in its config.

A game that runs hidden (a test, a smoke run) has no player: its seat's controls come from a script instead of from
the pad the game reports. The scripts are pure functions of the frame, so every run of a seat is the same and a
frame run on a guessed input would show in the history. They are for tests and smoke runs only; a real match never
sets them.

    {"kind": "pad", "seat": n [, "pause_from": frame] [, "system": "game"] [, "system_at": {"frame": bits, ...}] [, "hold": frames]}
                                                         a word that differs per seat and per frame (with `hold`: kept
                                                         that many frames, as a player holds a button); from `pause_from`
                                                         on, the seat also asks for a pause (its menu is open). The
                                                         system bits are the script's alone (a stray gamepad or key on
                                                         the PC running the test cannot pause the match) unless
                                                         "system" is "game": then the game's own are passed on.
                                                         `system_at` adds control bits on the LOCAL of a frame, as the worker's
                                                         request would (`seat_map.request`: a pass of the turn, a mode change)
    {"kind": "random", "seat": n [, "hold": frames] [, "system_at": {...}] [, "sticks": true] [, "keys": true]}
                                                         pseudo-random words held `hold` frames (default 12), the
                                                         script of the real-game smoke: it leaves a title screen;
                                                         `system_at` as above (the smoke's host restart); `keys`: the
                                                         seat types too, a letter or none held as the buttons are (a
                                                         computer, session ABI 9: only the host's keys are ever typed)
    {"kind": "xor", "frame": f, "port": p, "mask": m}    (a words filter) tells this seat's game another word for
                                                         port p at frame f: two games forced out of step
"""
from __future__ import annotations

import random

from . import session_pipe as pipe


def pad(seat: int, frame: int) -> int:
    """A seat's scripted pad word: different for every seat, different on every frame."""
    return (frame * (7 + 6 * seat) + 0x31 * (seat + 1)) & 0xff


def local_source(spec: dict | None):
    """`Settings.local_source` for a spec, or None."""
    if not spec:
        return None
    kind = spec.get('kind')
    if kind == 'pad':
        seat, pause_from, from_game = int(spec['seat']), spec.get('pause_from'), spec.get('system') == 'game'
        at = {int(frame): int(bits) for frame, bits in (spec.get('system_at') or {}).items()}
        hold = max(1, int(spec.get('hold', 1)))

        def source(frame, _word, system):
            if not from_game:
                system = 0
            if pause_from is not None and frame >= pause_from:
                system |= pipe.SYS_PAUSE
            return pad(seat, frame // hold), system | at.get(frame, 0)
        return source
    if kind == 'route':
        # A recorded route ("frame p1 p2" lines, the pads' hex words held from that frame, as the conversions' routes): the
        # seat plays its own column (the host p1, the first guest p2), so a game reaches a screen a test needs (a save).
        seat = int(spec['seat'])
        at = {int(frame): int(bits) for frame, bits in (spec.get('system_at') or {}).items()}
        events = sorted((int(row[0]), int(row[1 + seat]) if 1 + seat < len(row) else 0) for row in spec['events'])

        def source(frame, _word, system):
            word = 0
            for start, value in events:
                if start > frame:
                    break
                word = value
            return word & 0xffff, system | at.get(frame, 0)
        return source
    if kind == 'random':
        seat, hold = int(spec['seat']), int(spec.get('hold', 12))
        at = {int(frame): int(bits) for frame, bits in (spec.get('system_at') or {}).items()}

        sticks, typing = bool(spec.get('sticks')), bool(spec.get('keys'))

        def source(frame, _word, system):
            chooser = random.Random(seat * 100003 + frame // hold)
            word = chooser.getrandbits(8)
            axes = tuple(chooser.randint(-127, 127) for _ in range(4)) if sticks else None
            if typing:                  # a letter key (scancodes 4-29: bits 0-25) on two holds of three, none on the third
                keys = bytearray(pipe.KEY_BYTES)
                letter = chooser.randrange(39)
                if letter < 26:
                    keys[letter >> 3] |= 1 << (letter & 7)
                return word, system | at.get(frame, 0), axes, bytes(keys)
            if sticks:                  # a game with sticks: four int8 values held as the buttons are (session ABI 7)
                return word, system | at.get(frame, 0), axes
            return word, system | at.get(frame, 0)
        return source
    raise ValueError(f'an unknown local source: {kind!r}')


def words_filter(spec: dict | None):
    """`Settings.words_filter` for a spec, or None."""
    if not spec:
        return None
    if spec.get('kind') == 'xor':
        at, port, mask = int(spec['frame']), int(spec['port']), int(spec['mask'])

        def tamper(frame, words):
            if frame != at:
                return words
            changed = list(words)
            changed[port] ^= mask
            return tuple(changed)
        return tamper
    raise ValueError(f'an unknown words filter: {spec.get("kind")!r}')
