"""What two lockstep drivers send each other, as bytes: input records and the little that goes with them.

Version 1 of stage 1, for the in-memory link only. It carries no authentication tag and no match number: both
come with the real network (the study's protocol sketch, section 7.2), and `PROTO` is raised then.

Every packet, little-endian, at most MAX_PACKET bytes:

    magic 'RRNG' (4) | proto u8 | type u8 | seat u8 (the sender) | flags u8 (0) | body

    INPUT    sender_frame u32   the frame the sender's game is about to run (time sync)
             ack_frame u32      "I hold YOUR records up to this frame" (NONE: none yet)
             delay u8           the match's input delay, said by the host (0: not said)
             hold_ms u16        the host's worst one-way time: a nearer guest starts that much later
             resume_frame u32   "resume the pause that began at this frame" (NONE: no request)
             digest_frame u32, digest u64      the sender's latest digest (digest_frame NONE: none yet)
             sections u8 (<= 4), each: seat u8, first_frame u32, count u8 (<= 32), count x (word u16, system u16)
    PING     time u32           the sender's clock, microseconds, wrapped
    PONG     time u32           the PING's value, sent back
    MEASURE  one_way_ms u16, jitter_ms u16     a guest's worst link, for the host's choice of the delay
    BYE      reason u8 (BYE_*), frame u32

A record is one seat's controls for one frame: the pad word and the system bits (pause request). Records are
indexed by frame and the first one received wins; a packet repeats records until the peer acknowledged them, and
at least the last `redundancy` ones, so one lost packet is invisible. A packet that breaks these rules is dropped
whole (`decode` returns None): nothing is ever sized by a number read from a packet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import struct

MAGIC = b'RRNG'
PROTO = 1
MAX_PACKET = 508             # no IP fragmentation later, on IPv4 or IPv6
MAX_RECORDS = 32
MAX_SECTIONS = 4
MAX_DELAY = 15
NONE = 0xffffffff
INPUT, PING, PONG, MEASURE, BYE = 1, 2, 3, 4, 5
BYE_HOST_CLOSED, BYE_DESYNC, BYE_ENDED, BYE_LEFT = 1, 2, 3, 4

_HEAD = struct.Struct('<4sBBBB')
_INPUT = struct.Struct('<IIBHIIQB')
_SECTION = struct.Struct('<BIB')


@dataclass(frozen=True)
class Section:
    seat: int
    first_frame: int
    records: tuple          # of (word, system)


@dataclass(frozen=True)
class Packet:
    kind: int
    seat: int
    sender_frame: int = 0
    ack_frame: int = NONE
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


def _head(kind: int, seat: int) -> bytes:
    return _HEAD.pack(MAGIC, PROTO, kind, seat, 0)


def encode_input(seat: int, sender_frame: int, ack_frame: int, sections, *, delay: int = 0, hold_ms: int = 0,
                 resume_frame: int = NONE, digest_frame: int = NONE, digest: int = 0) -> bytes:
    """`sections`: (seat, first_frame, [(word, system), ...]) each. Too many records is the caller's error."""
    parts = [_head(INPUT, seat), _INPUT.pack(sender_frame, ack_frame, delay, min(hold_ms, 0xffff), resume_frame,
                                             digest_frame, digest, len(sections))]
    for owner, first, records in sections:
        if len(records) > MAX_RECORDS:
            raise ValueError('more than MAX_RECORDS records in a section')
        parts.append(_SECTION.pack(owner, first, len(records)))
        parts.extend(struct.pack('<HH', word, system) for word, system in records)
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


def encode_bye(seat: int, reason: int, frame: int) -> bytes:
    return _head(BYE, seat) + struct.pack('<BI', reason, frame & 0xffffffff)


def decode(data: bytes, seats: int = MAX_SECTIONS) -> Packet | None:
    """The packet, or None when anything in it is out of the rules (it is then ignored whole)."""
    if not _HEAD.size <= len(data) <= MAX_PACKET:
        return None
    magic, proto, kind, seat, _flags = _HEAD.unpack_from(data)
    if magic != MAGIC or proto != PROTO or seat >= seats:
        return None
    body = data[_HEAD.size:]
    if kind in (PING, PONG):
        return Packet(kind, seat, time=struct.unpack('<I', body)[0]) if len(body) == 4 else None
    if kind == MEASURE:
        if len(body) != 4:
            return None
        one_way, jitter = struct.unpack('<HH', body)
        return Packet(kind, seat, one_way_ms=one_way, jitter_ms=jitter)
    if kind == BYE:
        if len(body) != 5:
            return None
        reason, frame = struct.unpack('<BI', body)
        return Packet(kind, seat, reason=reason, frame=frame) if BYE_HOST_CLOSED <= reason <= BYE_LEFT else None
    if kind != INPUT or len(body) < _INPUT.size:
        return None
    sender_frame, ack, delay, hold, resume, digest_frame, digest, count = _INPUT.unpack_from(body)
    if delay > MAX_DELAY or count > MAX_SECTIONS:
        return None
    offset = _INPUT.size
    sections = []
    for _ in range(count):
        if len(body) < offset + _SECTION.size:
            return None
        owner, first, records = _SECTION.unpack_from(body, offset)
        offset += _SECTION.size
        if owner >= seats or records > MAX_RECORDS or len(body) < offset + 4 * records:
            return None
        values = struct.unpack_from(f'<{2 * records}H', body, offset)
        offset += 4 * records
        sections.append(Section(owner, first, tuple(zip(values[0::2], values[1::2]))))
    if offset != len(body):
        return None
    return Packet(kind, seat, sender_frame=sender_frame, ack_frame=ack, delay=delay, hold_ms=hold, resume_frame=resume,
                  digest_frame=digest_frame, digest=digest, sections=tuple(sections))


def choose_delay(one_way_ms: float, jitter_ms: float, frame_ms: float) -> int:
    """The input delay D, in frames, that covers the worst link: clamp(ceil((one_way + jitter) / T) + 1, 1, 15).

    The floor of one frame is the price of a driver outside the game. Above 15 the link is not covered: frames
    then wait for inputs (a slower game, never a guessed input)."""
    return max(1, min(MAX_DELAY, math.ceil((one_way_ms + jitter_ms) / frame_ms) + 1))


def covers(delay: int, one_way_ms: float, jitter_ms: float, frame_ms: float) -> bool:
    """Whether D frames of delay cover that link (the condition `choose_delay` solves, before its clamp)."""
    return delay >= math.ceil((one_way_ms + jitter_ms) / frame_ms) + 1


def pace_for(advantage_frames: float) -> int:
    """Time sync: parts per million to add to this game's frame period when it is `advantage_frames` ahead of the
    slowest other seat. Half a frame ahead or less: nothing. Beyond: 1 % per frame ahead, at most 2 %, in steps of
    0.25 %. A game is only ever slowed, so two seats can never push each other faster."""
    if advantage_frames <= 0.5:
        return 0
    return min(20000, int((advantage_frames - 0.5) * 10000) // 2500 * 2500 + 2500)
