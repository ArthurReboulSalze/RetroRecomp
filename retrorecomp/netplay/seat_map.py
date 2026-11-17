"""The seat mapper: how the seats' controls of one confirmed frame become the words of the machine's ports. Pure.

Every participant is a seat that sends one record a frame (`input_records`: a pad word and the system bits). What differs between
"one controller per player" and "input sharing" is only this function, applied by every driver to the records of the frame it is
about to run, which every seat holds the same: so every PC gets the same words and nothing extra travels (`LockstepDriver._step`
calls `step` once per frame, in order, on confirmed frames only: a frame never runs before every seat's record for it is known).

Modes (`Settings.sharing`, chosen by the host at room creation, carried by the LAUNCH):

* `PER_PLAYER` (0): seat i drives port i. The words are the seats' words, exactly as before this module existed.
* `SHARED_ALL` (1) "everyone": all the seats are on the controls of port 0; the word is the OR of the seats' words. Opposite
  directions held together (left with right, up with down, which no pad can make) are cancelled when the caller says which bits
  they are (`opposites`); the host kit does the same on every word it receives (`rrhk_session.inc` `clean_word`), so on a real
  game the merged word is cleaned either way and the same on every PC.
* `SHARED_TURNS` (2) "turns": only the token holder's word reaches port 0, the others' are read as neutral. The token starts at
  the host (seat 0) and moves only by records (below).

A match is in one of the two families for its whole life (the number of ports a game is set up with cannot change); a shared match
can move between "everyone" and "turns" while it runs (the host's record).

Control bits, in the SYSTEM word of a seat's record next to the game's own pause bit (`session_pipe.SYS_PAUSE`). **The game can
set only the pause bit**: the driver masks what a game reports to it and adds these from its worker side (`LockstepDriver.pass_token`,
`.set_sharing`), because the pipe has no bit for them yet (a key of the kit that passes the turn needs a header change, `native/hostkit`,
which is not ours). Whatever a remote peer's record says is checked here against who sent it, so a forged bit does nothing:

    SYS_PASS  (0x0002)   a rising edge (the bit was clear in that seat's previous record):
                         - from the token holder: the token goes to the next seat in order (wrapping);
                         - from the host with SYS_TO (a target seat + 1 in bits 8-10): the token goes to that seat, whoever held it
                           (the host can give it to any seat; it wins over the holder's own pass in the same frame);
                         - from anyone else: nothing.
    SYS_SET_ALL (0x1000) / SYS_SET_TURNS (0x2000), host only, rising edge, one of them: the shared match goes to "everyone" or to "turns".

A change decided by the records of frame F is in force from frame F + 1: frame F itself is mapped with the token and mode it had
before, so what the holder presses on the frame he passes still counts. `step` never looks at a frame twice and never at an
unconfirmed one, and the state it returns is all it remembers (the previous control bits of every seat for the edge rule).
"""
from __future__ import annotations

from typing import NamedTuple

PER_PLAYER, SHARED_ALL, SHARED_TURNS = 0, 1, 2
SHARINGS = (PER_PLAYER, SHARED_ALL, SHARED_TURNS)
NAMES = {PER_PLAYER: 'per_player', SHARED_ALL: 'everyone', SHARED_TURNS: 'turns'}
BY_NAME = {name: value for value, name in NAMES.items()}

SYS_PAUSE = 0x0001           # the game's (session_pipe.SYS_PAUSE); the only bit a game may set
SYS_PASS = 0x0002
SYS_TO_SHIFT, SYS_TO_MASK = 8, 0x0700
SYS_SET_ALL, SYS_SET_TURNS = 0x1000, 0x2000
SYS_RESTART = 0x4000         # host only: every game restarts before this frame runs (one record = one restart; a guest's is ignored)
SYS_STATE_SAVE = 0x0800      # host only: every game saves the match's state before this frame runs (the host's F8)
SYS_STATE_LOAD = 0x8000      # host only: every game loads it back before this frame runs (the host's F9)
SYS_GAME_MASK = SYS_PAUSE
SYS_CONTROL_MASK = SYS_PASS | SYS_TO_MASK | SYS_SET_ALL | SYS_SET_TURNS

MAX_SEATS = 4
HOST = 0
# The handhelds have one set of controls and no second pad: they play in input sharing only (the owner's rule, 17 November 2026).
# It is their profile's `netplay_shared_only`.


def _profile(machine):
    if not isinstance(machine, str):
        return None
    from ..systems import find_profile
    return find_profile(machine)


class SeatState(NamedTuple):
    """All the mapper remembers from one frame to the next."""
    sharing: int             # the family of the match: PER_PLAYER or shared (SHARED_ALL / SHARED_TURNS: the current one)
    token: int               # the seat whose word reaches port 0 in "turns"
    previous: tuple          # per seat, the control bits of its previous record (a request counts on its rising edge)


def valid(sharing) -> bool:
    return isinstance(sharing, int) and not isinstance(sharing, bool) and sharing in SHARINGS


def shared(sharing: int) -> bool:
    return sharing != PER_PLAYER


def forced(machine: str | None) -> bool:
    """A machine that plays in input sharing only (its profile's `netplay_shared_only`)."""
    profile = _profile(machine)
    return bool(profile is not None and profile.netplay_shared_only)


def effective(machine: str | None, chosen: int) -> int:
    """The mode a game of `machine` is played in when the host chose `chosen`: a handheld is shared whatever was chosen
    ("everyone" when the host's choice was one controller per player)."""
    return SHARED_ALL if forced(machine) and chosen == PER_PLAYER else chosen


def allowed(machine: str | None, sharing: int) -> bool:
    return valid(sharing) and (sharing != PER_PLAYER or not forced(machine))


def seat_limit(machine_players: int, sharing: int) -> int:
    """The seats a room can seat for a game of a machine with `machine_players` players in `sharing`: the players in "one
    controller per player", up to four seats in input sharing (they all drive the same controls)."""
    return MAX_SEATS if shared(sharing) else min(MAX_SEATS, machine_players)


def ports(sharing: int, seats: int) -> int:
    """The number of port words a RUN carries in `sharing` with `seats` seats."""
    return 1 if shared(sharing) else seats


def start(sharing: int, seats: int) -> SeatState:
    if not valid(sharing):
        raise ValueError('a sharing mode that does not exist')
    return SeatState(sharing, HOST, (0,) * seats)


def request(sharing: int, seat: int, *, target: int | None = None, mode: int | None = None) -> int:
    """The system bits a seat's worker adds to its next record to ask for something: a pass of the turn (`target`: the host
    gives it to that seat) or, from the host, the shared match going to `mode` (SHARED_ALL or SHARED_TURNS). 0 when the
    request means nothing here (a match that does not share, a target given by a guest, a mode that is not shared)."""
    if not shared(sharing):
        return 0
    if mode is not None:
        return {SHARED_ALL: SYS_SET_ALL, SHARED_TURNS: SYS_SET_TURNS}.get(mode, 0) if seat == HOST else 0
    bits = SYS_PASS
    if target is not None:
        if seat != HOST or not 0 <= target < MAX_SEATS:
            return 0
        bits |= (target + 1) << SYS_TO_SHIFT
    return bits


def merge(words, opposites=()) -> int:
    """The OR of the seats' words, with each pair of opposite directions (two masks) held together cancelled."""
    word = 0
    for part in words:
        word |= part
    for first, second in opposites:
        if word & first and word & second:
            word &= ~(first | second) & 0xffff
    return word


def sticks(state: SeatState, records) -> tuple:
    """The sticks of this frame's ports (session ABI 7), with the state as it was before the frame, as `step` maps the words:
    one controller per player, each port its seat's; in turns the holder's; with everyone on the shared controls the first seat
    whose sticks are off centre (sticks cannot be merged as buttons are). A record without sticks counts as centred."""
    centred = (0, 0, 0, 0)
    of = [record[2] if len(record) > 2 else centred for record in records]
    if not shared(state.sharing):
        return tuple(of)
    if state.sharing == SHARED_TURNS:
        return (of[state.token if state.token < len(of) else HOST],)
    return (next((axes for axes in of if any(axes)), centred),)


def action(records) -> int:
    """What every game does before this frame runs, from the host's record (a guest's bits are ignored): the restart, else the
    load of the match's state, else its save, as the RUN flag (`session_pipe.RUN_RESET`, `RUN_STATE_LOAD`, `RUN_STATE_SAVE`),
    or 0. A predicted record has no system bit, so none of them is ever guessed."""
    from . import session_pipe as pipe
    if not records:
        return 0
    host = records[HOST][1]
    if host & SYS_RESTART:
        return pipe.RUN_RESET
    if host & SYS_STATE_LOAD:
        return pipe.RUN_STATE_LOAD
    return pipe.RUN_STATE_SAVE if host & SYS_STATE_SAVE else 0


def restart(records) -> bool:
    """Whether the machines restart before this frame: the host's record of it carries SYS_RESTART. Only the host's counts,
    whatever the mode; a guest's bit is ignored. A predicted record has no system bit, so a restart is never guessed."""
    return bool(records) and bool(records[HOST][1] & SYS_RESTART)


def step(state: SeatState, records, opposites=()) -> tuple[tuple, SeatState]:
    """(the port words of this frame, the state for the next one) from `records`, the (word, system) of every seat of the
    frame, in seat order. The words use the state as it was before this frame."""
    seats = len(records)
    if not shared(state.sharing):
        return tuple(record[0] for record in records), state
    token = state.token if state.token < seats else HOST
    if state.sharing == SHARED_TURNS:
        words = (records[token][0],)
    else:
        words = (merge((record[0] for record in records), opposites),)
    controls = tuple(record[1] & SYS_CONTROL_MASK for record in records)
    previous = state.previous if len(state.previous) == seats else (0,) * seats
    rising = tuple(now & ~before for now, before in zip(controls, previous))
    sharing, after = state.sharing, token
    host = rising[HOST]
    both = host & (SYS_SET_ALL | SYS_SET_TURNS)
    if both == SYS_SET_ALL:
        sharing = SHARED_ALL
    elif both == SYS_SET_TURNS:
        sharing = SHARED_TURNS
    target = (host & SYS_TO_MASK) >> SYS_TO_SHIFT
    if host & SYS_PASS and 1 <= target <= seats:
        after = target - 1                              # the host gives it, whoever has it
    elif rising[token] & SYS_PASS:
        after = (token + 1) % seats                     # the holder passes it on
    return words, SeatState(sharing, after, controls)
