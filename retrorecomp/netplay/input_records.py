"""What two lockstep drivers send each other, as bytes: input records and the little that goes with them.

Version 2 (stage 1b), for a link that is not yet the real network. It carries no authentication tag and no match
number: both come with the real network (the study's protocol sketch, section 7.2), and `PROTO` is raised then.

Every packet, little-endian, at most MAX_PACKET bytes:

    magic 'RRNG' (4) | proto u8 | type u8 | seat u8 (the sender) | flags u8 (0) | body

    INPUT    sender_frame u32   the frame the sender's game is about to run (time sync)
             acks 4 x u32       "I hold seat s's records up to this frame" (NONE: none yet), one per seat
             delay u8           the match's input delay, said by the host (0: not said)
             hold_ms u16        the host's worst one-way time: a nearer guest starts that much later (at most MAX_HOLD_MS)
             resume_frame u32   "resume the pause that began at this frame" (NONE: no request)
             digest_frame u32, digest u64      the sender's latest digest (digest_frame NONE: none yet)
             sections u8 (<= 4), each: seat u8, first_frame u32, count u8 (<= 32), count x (word u16, system u16), and
             with the header's FLAG_AXES each record also carries 4 x i8 sticks (LX, LY, RX, RY) after its system bits,
             with FLAG_KEYS 16 bytes of keys after them (a computer: only the host's are ever typed, PROTO 3)
    PING     time u32           the sender's clock, microseconds, wrapped
    PONG     time u32           the PING's value, sent back
    MEASURE  one_way_ms u16, jitter_ms u16     a guest's worst link, for the host's choice of the delay
    BYE      reason u8 (BYE_*), frame u32, who u8 (the seat the reason is about, 0xff none)
    BOOT     digest u64         a guest's game state after its setup and before frame 0, for the host to compare

A record is one seat's controls for one frame: the pad word and the system bits (pause request). Records are
indexed by frame and the first one received wins; a packet repeats records until the peer acknowledged them, and
at least the last `redundancy` ones, so one lost packet is invisible. In a star the host's packets carry the
sections of every other seat (it forwards them); a guest's carry its own. A packet that breaks these rules is
dropped whole (`decode` returns None): nothing is ever sized by a number read from a packet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import struct

MAGIC = b'RRNG'
PROTO = 3                    # 3: FLAG_KEYS and BYE_RELAUNCH (session ABI 9)
MAX_PACKET = 508             # no IP fragmentation later, on IPv4 or IPv6
MAX_RECORDS = 32
MAX_SECTIONS = 4
MAX_SEATS = 4
MAX_DELAY = 15
MAX_HOLD_MS = 500            # the longest start hold a packet may ask for (a forged value must not hold every game)
NONE = 0xffffffff
NO_SEAT = 0xff
INPUT, PING, PONG, MEASURE, BYE, BOOT = 1, 2, 3, 4, 5, 6
FLAG_AXES = 1                # an INPUT whose records carry the sticks (a game with sticks: session ABI 7)
FLAG_KEYS = 2                # an INPUT whose records carry the keys typed (a computer: session ABI 9)
AXES = 4
KEY_BYTES = 16
BYE_HOST_CLOSED, BYE_DESYNC, BYE_ENDED, BYE_LEFT, BYE_SEAT_GONE, BYE_BOOT, BYE_RELAUNCH = 1, 2, 3, 4, 5, 6, 7

_HEAD = struct.Struct('<4sBBBB')
_INPUT = struct.Struct('<I4IBHIIQB')
_SECTION = struct.Struct('<BIB')
_NO_ACKS = (NONE,) * MAX_SEATS


@dataclass(frozen=True)
class Section:
    seat: int
    first_frame: int
    records: tuple          # of (word, system), (word, system, sticks) with FLAG_AXES, (word, system, sticks or None, keys)
                            # with FLAG_KEYS


@dataclass(frozen=True)
class Packet:
    kind: int
    seat: int
    sender_frame: int = 0
    acks: tuple = _NO_ACKS
    delay: int = 0
    hold_ms: int = 0
    resume_frame: int = NONE
    digest_frame: int = NONE
    digest: int = 0
    sections: tuple = field(default=())
    time: int = 0
    one_way_ms: int = 0
    jitter_ms: int = 0
    reason: int = 0
    frame: int = 0
    who: int = NO_SEAT


def _head(kind: int, seat: int, flags: int = 0) -> bytes:
    return _HEAD.pack(MAGIC, PROTO, kind, seat, flags)


def records_that_fit(sections: int, sticks: bool, keys: bool = False) -> int:
    """How many records each of `sections` sections may carry so that the packet stays within MAX_PACKET."""
    if sections <= 0:
        return MAX_RECORDS
    room = MAX_PACKET - _HEAD.size - _INPUT.size - sections * _SECTION.size
    return max(1, min(MAX_RECORDS, room // (sections * (4 + (AXES if sticks else 0) + (KEY_BYTES if keys else 0)))))


def encode_input(seat: int, sender_frame: int, acks, sections, *, delay: int = 0, hold_ms: int = 0,
                 resume_frame: int = NONE, digest_frame: int = NONE, digest: int = 0) -> bytes:
    """`acks`: per seat, the last frame of that seat's records this sender holds (NONE or missing: none).
    `sections`: (seat, first_frame, [(word, system), ...]) each, or (word, system, sticks) records for a game with sticks
    (every record then has them). Too many records is the caller's error (`records_that_fit`)."""
    held = (list(acks) + [NONE] * MAX_SEATS)[:MAX_SEATS]
    sticks = any(len(record) > 2 and record[2] is not None for _owner, _first, records in sections for record in records)
    keys = any(len(record) > 3 for _owner, _first, records in sections for record in records)
    parts = [_head(INPUT, seat, (FLAG_AXES if sticks else 0) | (FLAG_KEYS if keys else 0)),
             _INPUT.pack(sender_frame, *held, delay, min(hold_ms, MAX_HOLD_MS), resume_frame, digest_frame, digest,
                         len(sections))]
    for owner, first, records in sections:
        if len(records) > MAX_RECORDS:
            raise ValueError('more than MAX_RECORDS records in a section')
        parts.append(_SECTION.pack(owner, first, len(records)))
        for record in records:
            parts.append(struct.pack('<HH', record[0], record[1]))
            if sticks:
                axes = record[2] if len(record) > 2 and record[2] is not None else (0,) * AXES
                parts.append(struct.pack(f'<{AXES}b', *(max(-127, min(127, value)) for value in axes)))
            if keys:
                typed = bytes(record[3]) if len(record) > 3 and record[3] is not None else bytes(KEY_BYTES)
                if len(typed) != KEY_BYTES:
                    raise ValueError('the keys of a record are KEY_BYTES bytes')
                parts.append(typed)
    data = b''.join(parts)
    if len(data) > MAX_PACKET or len(sections) > MAX_SECTIONS:
        raise ValueError('an input packet above the limits')
    return data


def encode_ping(seat: int, time: int) -> bytes:
    return _head(PING, seat) + struct.pack('<I', time & 0xffffffff)


def encode_pong(seat: int, time: int) -> bytes:
    return _head(PONG, seat) + struct.pack('<I', time & 0xffffffff)


def encode_measure(seat: int, one_way_ms: float, jitter_ms: float) -> bytes:
    return _head(MEASURE, seat) + struct.pack('<HH', min(0xffff, math.ceil(one_way_ms)), min(0xffff, math.ceil(jitter_ms)))


def encode_bye(seat: int, reason: int, frame: int, who: int = NO_SEAT) -> bytes:
    return _head(BYE, seat) + struct.pack('<BIB', reason, frame & 0xffffffff, who)


def encode_boot(seat: int, digest: int) -> bytes:
    return _head(BOOT, seat) + struct.pack('<Q', digest & 0xffffffffffffffff)


def decode(data: bytes, seats: int = MAX_SEATS) -> Packet | None:
    """The packet, or None when anything in it is out of the rules (it is then ignored whole)."""
    if not _HEAD.size <= len(data) <= MAX_PACKET:
        return None
    magic, proto, kind, seat, flags = _HEAD.unpack_from(data)
    if magic != MAGIC or proto != PROTO or seat >= seats or flags & ~(FLAG_AXES | FLAG_KEYS) or (flags and kind != INPUT):
        return None                     # an unknown flag: a later meaning cannot be pre-sent
    size = 4 + (AXES if flags & FLAG_AXES else 0) + (KEY_BYTES if flags & FLAG_KEYS else 0)
    body = data[_HEAD.size:]
    if kind in (PING, PONG):
        return Packet(kind, seat, time=struct.unpack('<I', body)[0]) if len(body) == 4 else None
    if kind == MEASURE:
        if len(body) != 4:
            return None
        one_way, jitter = struct.unpack('<HH', body)
        return Packet(kind, seat, one_way_ms=one_way, jitter_ms=jitter)
    if kind == BOOT:
        return Packet(kind, seat, digest=struct.unpack('<Q', body)[0]) if len(body) == 8 else None
    if kind == BYE:
        if len(body) != 6:
            return None
        reason, frame, who = struct.unpack('<BIB', body)
        if not BYE_HOST_CLOSED <= reason <= BYE_RELAUNCH or not (who < seats or who == NO_SEAT):
            return None
        return Packet(kind, seat, reason=reason, frame=frame, who=who)
    if kind != INPUT or len(body) < _INPUT.size:
        return None
    sender_frame, *rest = _INPUT.unpack_from(body)
    acks, (delay, hold, resume, digest_frame, digest, count) = tuple(rest[:MAX_SEATS]), rest[MAX_SEATS:]
    if delay > MAX_DELAY or hold > MAX_HOLD_MS or count > MAX_SECTIONS:
        return None
    offset = _INPUT.size
    sections = []
    for _ in range(count):
        if len(body) < offset + _SECTION.size:
            return None
        owner, first, records = _SECTION.unpack_from(body, offset)
        offset += _SECTION.size
        if owner >= seats or records > MAX_RECORDS or len(body) < offset + size * records:
            return None
        items = []
        for _ in range(records):
            word, system = struct.unpack_from('<HH', body, offset)
            axes = tuple(max(-127, value) for value in struct.unpack_from(f'<{AXES}b', body, offset + 4)) \
                if flags & FLAG_AXES else None
            if flags & FLAG_KEYS:
                items.append((word, system, axes, bytes(body[offset + size - KEY_BYTES:offset + size])))
            elif axes is not None:
                items.append((word, system, axes))
            else:
                items.append((word, system))
            offset += size
        sections.append(Section(owner, first, tuple(items)))
    if offset != len(body):
        return None
    return Packet(kind, seat, sender_frame=sender_frame, acks=acks, delay=delay, hold_ms=hold, resume_frame=resume,
                  digest_frame=digest_frame, digest=digest, sections=tuple(sections))


def choose_delay(one_way_ms: float, jitter_ms: float, frame_ms: float) -> int:
    """The input delay D, in frames, that covers the worst link: clamp(ceil((one_way + jitter) / T) + 1, 1, 15).

    The floor of one frame is the price of a driver outside the game. Above 15 the link is not covered: frames
    then wait for inputs (a slower game, never a guessed input)."""
    return max(1, min(MAX_DELAY, math.ceil((one_way_ms + jitter_ms) / frame_ms) + 1))


def covers(delay: int, one_way_ms: float, jitter_ms: float, frame_ms: float) -> bool:
    """Whether D frames of delay cover that link (the condition `choose_delay` solves, before its clamp)."""
    return delay >= math.ceil((one_way_ms + jitter_ms) / frame_ms) + 1


PACE_PER_FRAME = 5000        # parts per million per frame of advantage beyond the dead band
PACE_STEP = 2500             # the pace moves in steps of 0.25 %
PACE_LIMIT = 20000           # 2 %


def pace_for(advantage_frames: float, deadband: float = 0.5) -> int:
    """Time sync: parts per million to add to this game's frame period when it is `advantage_frames` ahead of the
    slowest other seat. Inside the dead band (half a frame by default): nothing. Beyond: 0.5 % per frame ahead, in steps of 0.25 %, at most 2 %. A game is only ever slowed, so
    two seats can never push each other faster. This is the rule on a steady estimate; `time_sync.PaceController`
    makes the estimate steady and moves by one step at a time."""
    if advantage_frames <= deadband:
        return 0
    return min(PACE_LIMIT, int((advantage_frames - deadband) * PACE_PER_FRAME) // PACE_STEP * PACE_STEP + PACE_STEP)
