"""The one door through which settings that came from another PC become a `Settings`.

A guest receives its launch (seat, seats, delay, digest period, redundancy, the host's options, the names) from the
host. Those values are a stranger's: they are checked here, field by field, and a bad one gives a `Refusal` with a
sentence for the lobby, never an exception and never a half-built `Settings`. Everything the host cannot say
(the test sources, a clock offset, a last frame, the mesh topology, the timers) is refused when present, and the
guest's own defaults apply. `tests/test_netplay_security.py` holds each bound, one inside and one past.

No socket here: this is the pure function the transport of stage 2 will call with the decoded LAUNCH.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from . import input_records as wire
from . import seat_map
from . import session_pipe as pipe
from .lockstep import Settings

MIN_SEATS, MAX_SEATS = 2, wire.MAX_SEATS
MIN_DIGEST_EVERY, MAX_DIGEST_EVERY = 10, 600
MAX_REDUNDANCY = 8
MAX_OPTION_LINES = 32
MAX_NAME_INPUT = 64                 # characters read of a name before it is cleaned (the game draws 16)
_OPTION_LINE = re.compile(r'[a-z0-9_]{1,32}=[A-Za-z0-9_.-]{0,32}')
FIELDS = ('seat', 'seats', 'names', 'delay', 'digest_every', 'redundancy', 'options', 'sharing')


@dataclass(frozen=True)
class Refusal:
    """A launch that was not accepted, and why (one sentence, free of anything the host sent)."""
    reason: str


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def clean_names(names, seats: int) -> tuple[str, ...] | Refusal:
    """One name per seat as the game will draw it: printable ASCII, at most 16 characters."""
    if not isinstance(names, (list, tuple)) or len(names) != seats:
        return Refusal('the names do not match the seats')
    cleaned = []
    for name in names:
        if not isinstance(name, str):
            return Refusal('a name is not text')
        cleaned.append(pipe.clean_name(name[:MAX_NAME_INPUT]).decode('ascii'))
    return tuple(cleaned)


def clean_options(options) -> str | Refusal:
    """The host's run-changing options: `key=value` lines of the plain alphabet, few and short."""
    if not isinstance(options, str):
        return Refusal('the options are not text')
    if len(options) > MAX_OPTION_LINES * 70 or not options.isascii():
        return Refusal('the options are too long or not plain text')
    lines = [line for line in options.split('\n') if line]
    if len(lines) > MAX_OPTION_LINES:
        return Refusal('too many options')
    if not all(_OPTION_LINE.fullmatch(line) for line in lines):
        return Refusal('an option is not of the form key=value in the plain alphabet')
    return '\n'.join(lines)


def launch_settings(message, *, guest: bool = True, machine: str | None = None) -> Settings | Refusal:
    """The `Settings` of a launch `message` (a dict of the fields in `FIELDS`), or the `Refusal` that says why not.
    `guest`: the receiver is a guest, so seat 0 (the host's) is not one it can be given. `machine`: when the caller knows it,
    a handheld is refused in any mode but input sharing (the rule of `seat_map.HANDHELDS`, held on both ends of a launch)."""
    if not isinstance(message, dict):
        return Refusal('the launch is not a set of settings')
    unknown = sorted(str(key) for key in message if key not in FIELDS)
    if unknown:
        return Refusal('the launch carries a setting this version does not take')
    seats, seat = message.get('seats'), message.get('seat')
    if not _integer(seats) or not MIN_SEATS <= seats <= MAX_SEATS:
        return Refusal(f'a match of {MIN_SEATS} to {MAX_SEATS} seats')
    if not _integer(seat) or not (1 if guest else 0) <= seat < seats:
        return Refusal('a seat the match does not have')
    sharing = message.get('sharing', seat_map.PER_PLAYER)
    if not seat_map.valid(sharing):
        return Refusal('an input mode this version does not have')
    if not seat_map.allowed(machine, sharing):
        return Refusal('this machine plays in input sharing only: one controller per player is not offered')
    delay = message.get('delay')
    if delay is not None and not (_integer(delay) and 1 <= delay <= wire.MAX_DELAY):
        return Refusal(f'an input delay of 1 to {wire.MAX_DELAY} frames, or none')
    digest_every = message.get('digest_every', Settings.digest_every)
    if not _integer(digest_every) or not MIN_DIGEST_EVERY <= digest_every <= MAX_DIGEST_EVERY:
        return Refusal(f'a digest every {MIN_DIGEST_EVERY} to {MAX_DIGEST_EVERY} frames')
    redundancy = message.get('redundancy', Settings.redundancy)
    if not _integer(redundancy) or not 1 <= redundancy <= MAX_REDUNDANCY:
        return Refusal(f'a redundancy of 1 to {MAX_REDUNDANCY}')
    names = clean_names(message.get('names', [f'Player {index + 1}' for index in range(seats)]), seats)
    if isinstance(names, Refusal):
        return names
    options = clean_options(message.get('options', ''))
    if isinstance(options, Refusal):
        return options
    return Settings(seat=seat, seats=seats, names=names, delay=delay, digest_every=digest_every, redundancy=redundancy,
                    options=options, sharing=sharing)
