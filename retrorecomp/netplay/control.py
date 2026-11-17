"""The room's control stream (TCP, after the handshake): framed, tagged messages, and the display names. Pure.

    length u16 (payload only, <= 1024) | type u8 | payload | tag 16
    tag = mac(K_tcp_dir, seq u64, length u16, type u8, payload)      seq counts from 0 per direction and is never sent

A wrong tag, a length above the limit, an unknown or unexpected type, a payload of the wrong size for its type or
bytes left over: `FrameError`, and the transport closes the connection with no detail to the peer. The reader keeps
at most 2,048 bytes. Every message is of a fixed size or has each variable field length-prefixed and bounded, and
`decode` accepts only the canonical form: a message that decodes encodes back to the same bytes (the fuzz test holds it).
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import re
import struct
import unicodedata

from .handshake import mac

MAX_PAYLOAD = 1024
READ_BUFFER = 2048
WELCOME, REJECT, HELLO, LAUNCH, LAUNCHED, END, PING, PONG, BYE = range(1, 10)
REJECT_FULL, REJECT_VERSION, REJECT_BUSY, REJECT_KICKED = 1, 2, 3, 4
LAUNCHED_READY, LAUNCHED_NOT_OWNED, LAUNCHED_OTHER_STAMP, LAUNCHED_FAILED = 0, 1, 2, 3
BYE_REASONS = range(1, 5)       # the control BYE: 1 left, 2 room closed, 3 kicked, 4 error
MAX_NAME_BYTES = 48
MAX_NAME_CHARS = 16
MAX_SEATS = 4
MAX_OPTIONS = 512
MAX_MACHINE = 16
_MACHINE = re.compile(r'[A-Za-z0-9_.+-]{1,16}')
_FROM_GUEST = frozenset((HELLO, LAUNCHED, END, PING, PONG, BYE))
_FROM_HOST = frozenset((WELCOME, REJECT, LAUNCH, END, PING, PONG, BYE))
FROM_GUEST, FROM_HOST = _FROM_GUEST, _FROM_HOST


class FrameError(ValueError):
    """The stream broke the rules: the connection is closed."""


# ---- the messages ----

@dataclass(frozen=True)
class Welcome:
    guest_id: int
    capacity: int


@dataclass(frozen=True)
class Reject:
    reason: int


@dataclass(frozen=True)
class Hello:
    version: tuple
    name: str


@dataclass(frozen=True)
class Launch:
    match_id: int
    seat: int
    seats: int
    delay: int
    digest_every: int
    redundancy: int
    machine: str
    stamp: bytes
    rom_sha: bytes
    names: tuple
    options: str


@dataclass(frozen=True)
class Launched:
    match_id: int
    status: int


@dataclass(frozen=True)
class End:
    match_id: int
    reason: int
    who: int


@dataclass(frozen=True)
class Ping:
    time_ms: int


@dataclass(frozen=True)
class Pong:
    time_ms: int


@dataclass(frozen=True)
class Bye:
    reason: int


def encode(message) -> tuple[int, bytes]:
    """(type, payload) of a message."""
    if isinstance(message, Welcome):
        return WELCOME, struct.pack('<BB', message.guest_id, message.capacity)
    if isinstance(message, Reject):
        return REJECT, struct.pack('<B', message.reason)
    if isinstance(message, Hello):
        name = message.name.encode('utf-8')
        if not 0 < len(name) <= MAX_NAME_BYTES:
            raise ValueError('a name outside the rules')
        return HELLO, struct.pack('<3HB', *message.version, len(name)) + name
    if isinstance(message, Launch):
        if (not _MACHINE.fullmatch(message.machine) or len(message.names) > MAX_SEATS or len(message.options) > MAX_OPTIONS
                or len(message.stamp) != 32 or len(message.rom_sha) != 32 or not message.options.isascii()
                or any(not 0 < len(name.encode('utf-8')) <= MAX_NAME_BYTES for name in message.names)):
            raise ValueError('a launch outside the rules')
        machine = message.machine.encode('ascii')
        names = b''.join(struct.pack('<B', len(raw)) + raw for raw in (name.encode('utf-8') for name in message.names))
        options = message.options.encode('ascii')
        return LAUNCH, b''.join((struct.pack('<IBBBHB', message.match_id, message.seat, message.seats, message.delay,
                                             message.digest_every, message.redundancy),
                                 struct.pack('<B', len(machine)), machine, message.stamp, message.rom_sha,
                                 struct.pack('<B', len(message.names)), names, struct.pack('<H', len(options)), options))
    if isinstance(message, Launched):
        return LAUNCHED, struct.pack('<IB', message.match_id, message.status)
    if isinstance(message, End):
        return END, struct.pack('<IBB', message.match_id, message.reason, message.who)
    if isinstance(message, Ping):
        return PING, struct.pack('<I', message.time_ms & 0xffffffff)
    if isinstance(message, Pong):
        return PONG, struct.pack('<I', message.time_ms & 0xffffffff)
    if isinstance(message, Bye):
        return BYE, struct.pack('<B', message.reason)
    raise TypeError('not a control message')


def _decode_name(raw: bytes) -> str:
    if not raw or len(raw) > MAX_NAME_BYTES:
        raise FrameError('a name of the wrong size')
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        raise FrameError('a name that is not UTF-8') from None


def decode(kind: int, payload: bytes):
    """The message of a frame, or `FrameError` (a wrong size, a field out of its range, bytes left over)."""
    try:
        return _decode(kind, payload)
    except (struct.error, IndexError):
        raise FrameError('a message cut short') from None


def _decode(kind: int, payload: bytes):
    size = len(payload)
    if kind == WELCOME and size == 2:
        guest_id, capacity = struct.unpack('<BB', payload)
        if 1 <= guest_id < capacity <= MAX_SEATS:
            return Welcome(guest_id, capacity)
    elif kind == REJECT and size == 1:
        if payload[0] in (REJECT_FULL, REJECT_VERSION, REJECT_BUSY, REJECT_KICKED):
            return Reject(payload[0])
    elif kind == HELLO and size >= 7:
        major, minor, patch, length = struct.unpack_from('<3HB', payload)
        if size == 7 + length:
            return Hello((major, minor, patch), _decode_name(payload[7:]))
    elif kind == LAUNCH:
        return _decode_launch(payload)
    elif kind == LAUNCHED and size == 5:
        match_id, status = struct.unpack('<IB', payload)
        if status <= LAUNCHED_FAILED:
            return Launched(match_id, status)
    elif kind == END and size == 6:
        match_id, reason, who = struct.unpack('<IBB', payload)
        if reason in BYE_REASONS_WIRE and (who < MAX_SEATS or who == 0xff):
            return End(match_id, reason, who)
    elif kind in (PING, PONG) and size == 4:
        return (Ping if kind == PING else Pong)(struct.unpack('<I', payload)[0])
    elif kind == BYE and size == 1:
        if payload[0] in BYE_REASONS:
            return Bye(payload[0])
    raise FrameError('a message the rules do not allow')


BYE_REASONS_WIRE = range(1, 7)       # the datagram BYE reasons (input_records.BYE_*): an END carries one of them


def _decode_launch(payload: bytes) -> Launch:
    match_id, seat, seats, delay, digest_every, redundancy = struct.unpack_from('<IBBBHB', payload)
    offset = 10
    length = payload[offset]
    offset += 1
    machine_raw = payload[offset:offset + length]
    offset += length
    if length > MAX_MACHINE or len(machine_raw) != length:
        raise FrameError('a launch with a machine id of the wrong size')
    try:
        machine = machine_raw.decode('ascii')
    except UnicodeDecodeError:
        raise FrameError('a launch with a machine id that is not ASCII') from None
    if not _MACHINE.fullmatch(machine):
        raise FrameError('a launch with a machine id that is not plain')
    stamp, rom_sha = payload[offset:offset + 32], payload[offset + 32:offset + 64]
    offset += 64
    count = payload[offset]
    offset += 1
    if len(stamp) != 32 or len(rom_sha) != 32 or count > MAX_SEATS:
        raise FrameError('a launch cut short')
    names = []
    for _ in range(count):
        size = payload[offset]
        raw = payload[offset + 1:offset + 1 + size]
        if len(raw) != size:
            raise FrameError('a launch cut short')
        names.append(_decode_name(raw))
        offset += 1 + size
    options_size, = struct.unpack_from('<H', payload, offset)
    offset += 2
    options_raw = payload[offset:offset + options_size]
    offset += options_size
    if options_size > MAX_OPTIONS or len(options_raw) != options_size or offset != len(payload):
        raise FrameError('a launch with options of the wrong size')
    try:
        options = options_raw.decode('ascii')
    except UnicodeDecodeError:
        raise FrameError('a launch with options that are not ASCII') from None
    return Launch(match_id, seat, seats, delay, digest_every, redundancy, machine, stamp, rom_sha, tuple(names), options)


# ---- frames ----

def _tag(key: bytes, seq: int, length: int, kind: int, payload: bytes) -> bytes:
    return mac(key, struct.pack('<Q', seq), struct.pack('<H', length), bytes((kind,)), payload)


class FrameWriter:
    """Seals messages in order: the sequence number is the count of frames sent, never put on the wire."""

    def __init__(self, key: bytes):
        self._key, self._seq = key, 0

    def seal(self, message) -> bytes:
        kind, payload = encode(message)
        if len(payload) > MAX_PAYLOAD:
            raise ValueError('a control message above the limit')
        tag = _tag(self._key, self._seq, len(payload), kind, payload)
        self._seq += 1
        return struct.pack('<HB', len(payload), kind) + payload + tag


class FrameReader:
    """Whole, verified messages out of the bytes read so far. `allowed`: the types the peer may send."""

    def __init__(self, key: bytes, allowed: frozenset):
        self._key, self._allowed, self._seq = key, allowed, 0
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list:
        """The messages now complete, in order; `FrameError` for anything that breaks the rules."""
        self._buffer += data
        messages = []
        while len(self._buffer) >= 3:
            length, kind = struct.unpack_from('<HB', self._buffer)
            if length > MAX_PAYLOAD or kind not in self._allowed:
                raise FrameError('a frame outside the rules')     # refused on its header, before the payload is read
            total = 3 + length + 16
            if len(self._buffer) < total:
                break
            payload, tag = bytes(self._buffer[3:3 + length]), bytes(self._buffer[3 + length:total])
            if not hmac.compare_digest(tag, _tag(self._key, self._seq, length, kind, payload)):
                raise FrameError('a frame that does not verify')
            self._seq += 1
            del self._buffer[:total]
            messages.append(decode(kind, payload))
        if len(self._buffer) > READ_BUFFER:
            raise FrameError('too many bytes waiting')
        return messages


# ---- names (the review's 2.8) ----

_REMOVED = frozenset(('Cc', 'Cf', 'Cs', 'Co', 'Cn'))


def display_name(raw, fallback: str = '') -> str:
    """A name as everyone sees it: strict UTF-8 (rejected, not repaired), NFC, control, format, surrogate, private-use
    and unassigned characters removed, runs of white space made one space, trimmed, at most 16 characters and 48 bytes.
    `fallback` when nothing is left (or the bytes were not UTF-8)."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw[:MAX_NAME_BYTES * 2]).decode('utf-8')
        except UnicodeDecodeError:
            return fallback
    else:
        text = str(raw)[:MAX_NAME_BYTES * 2]
    text = unicodedata.normalize('NFC', text)
    spaced = ''.join(' ' if char.isspace() else char for char in text)
    kept = ''.join(char for char in spaced if unicodedata.category(char) not in _REMOVED)
    name = ' '.join(kept.split())[:MAX_NAME_CHARS].rstrip()
    while len(name.encode('utf-8')) > MAX_NAME_BYTES:
        name = name[:-1].rstrip()
    return name or fallback


def unique_name(name: str, taken) -> str:
    """`name`, or "name (2)", "name (3)"... the first that nobody has, still within 16 characters."""
    taken = {item.casefold() for item in taken}
    if name.casefold() not in taken:
        return name
    for number in range(2, 100):
        suffix = f' ({number})'
        candidate = name[:MAX_NAME_CHARS - len(suffix)].rstrip() + suffix
        if candidate.casefold() not in taken:
            return candidate
    return name[:MAX_NAME_CHARS - 4] + f'#{len(taken) % 1000}'
