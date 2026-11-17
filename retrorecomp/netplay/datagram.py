"""The match datagrams (UDP) of a room, and what a receiver does with one, as pure code: no socket, no thread.

    magic 'RRNG' 4 | proto u8 = 3 | type u8 | seat u8 | flags u8 = 0 | match_id u32 | counter u64 | body | tag 16

40 to 508 bytes. `tag = blake2b(datagram without tag, key = K_udp_dir(match, seat), digest_size 16)`. The body is the
body of a driver packet of `input_records` (INPUT, PING, PONG, MEASURE, BYE, BOOT) without its 8-byte head: the
transport takes that head off on the way out and rebuilds it, with the seat the key proved, on the way in, so the
driver does not change (`split_inner`, `join_inner`). `seat` is the sender's seat (the key to try); from the host it is
0 and the key is the recipient's.

What a receiver does with a datagram, in this order, each failure being a silent drop and one count
(`SECURITY_REVIEW.md` 2.6):

1. the source address is that of an authenticated TCP peer (host), or the host's exact address and port (guest);
2. 40 <= size <= 508;
3. magic, proto, flags 0, the running match, a seat of that peer;
4. the per-address bucket and the all-sources bucket;
5. the tag, in constant time;
6. the counter: not 0, not seen, not more than 63 behind the highest (a 64-packet window per seat and direction);
7. the seat's bucket, then the driver's own `decode` of the body.

Nothing is hashed before step 5: a stranger's datagram costs a dictionary look-up and a few comparisons.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import struct

from . import input_records as wire
from .limits import (ADDRESS_BURST, ADDRESS_RATE, TOTAL_BURST, TOTAL_RATE, Counters, SeatLimit, TokenBucket,
                     SEAT_BURST, SEAT_RATE)

MAGIC = b'RRNG'
PROTO = 3
MIN_SIZE, MAX_SIZE = 40, 508
HEAD_SIZE, TAG_SIZE = 20, 16
READ_SIZE = 1024                 # the transport reads this much: a longer datagram is seen as longer and dropped
MAX_BODY = MAX_SIZE - HEAD_SIZE - TAG_SIZE
KINDS = frozenset((wire.INPUT, wire.PING, wire.PONG, wire.MEASURE, wire.BYE, wire.BOOT))
WINDOW = 64
_HEAD = struct.Struct('<4sBBBBIQ')
_INNER = struct.Struct('<4sBBBB')


def _tag(key: bytes, data: bytes) -> bytes:
    return hashlib.blake2b(data, key=key, digest_size=TAG_SIZE).digest()


def seal(key: bytes, kind: int, seat: int, match_id: int, counter: int, body: bytes) -> bytes:
    if kind not in KINDS or len(body) > MAX_BODY or not 0 < counter < 1 << 64:
        raise ValueError('a datagram outside the rules')
    data = _HEAD.pack(MAGIC, PROTO, kind, seat, 0, match_id, counter) + body
    if len(data) + TAG_SIZE < MIN_SIZE:
        raise ValueError('a datagram below the smallest size')
    return data + _tag(key, data)


@dataclass(frozen=True)
class Head:
    kind: int
    seat: int
    match_id: int
    counter: int


def parse_head(datagram: bytes) -> Head | None:
    """The head, or None when the size, the magic, the protocol, the flags or the type are wrong. No hashing."""
    if not MIN_SIZE <= len(datagram) <= MAX_SIZE:
        return None
    magic, proto, kind, seat, flags, match_id, counter = _HEAD.unpack_from(datagram)
    if magic != MAGIC or proto != PROTO or flags or kind not in KINDS:
        return None
    return Head(kind, seat, match_id, counter)


def verify(datagram: bytes, key: bytes) -> bool:
    return hmac.compare_digest(datagram[-TAG_SIZE:], _tag(key, datagram[:-TAG_SIZE]))


def body_of(datagram: bytes) -> bytes:
    return datagram[HEAD_SIZE:-TAG_SIZE]


def open_(datagram: bytes, key_for) -> tuple | None:
    """`(seat, kind, counter, body)` of a datagram whose tag verifies, or None. `key_for(seat, match_id)` gives the key
    to try (or None: no hashing is done). The counter's window is the caller's (`ReplayWindow`)."""
    head = parse_head(datagram)
    if head is None:
        return None
    key = key_for(head.seat, head.match_id)
    if key is None or not verify(datagram, key):
        return None
    return head.seat, head.kind, head.counter, body_of(datagram)


class ReplayWindow:
    """The counters of one direction of one seat: a counter is taken once, and none more than 63 behind the highest."""

    def __init__(self):
        self.highest = 0
        self._seen = 0                   # bit i: the counter `highest - i` was taken

    def accept(self, counter: int) -> bool:
        if counter <= 0 or counter >= 1 << 64:
            return False
        if counter > self.highest:
            shift = counter - self.highest
            self._seen = ((self._seen << shift) | 1) & ((1 << WINDOW) - 1) if shift < WINDOW else 1
            self.highest = counter
            return True
        age = self.highest - counter
        if age >= WINDOW or self._seen >> age & 1:
            return False
        self._seen |= 1 << age
        return True


class Sender:
    """Seals the datagrams one direction of one seat sends: the counter goes 1, 2, 3, ... (the caller serialises)."""

    def __init__(self, key: bytes, match_id: int, seat_field: int):
        self.key, self.match_id, self.seat_field = key, match_id, seat_field
        self.counter = 0

    def pack(self, kind: int, body: bytes) -> bytes:
        self.counter += 1
        return seal(self.key, kind, self.seat_field, self.match_id, self.counter, body)


# ---- the driver's packet and the datagram's body ----

def split_inner(data: bytes, seat: int) -> tuple[int, bytes] | None:
    """(kind, body) of a packet the driver gave the link, or None. The packet must be of this seat and of the driver's
    own version; its 8-byte head is not sent (the datagram carries the type and the seat)."""
    if len(data) < _INNER.size or len(data) - _INNER.size > MAX_BODY:
        return None
    magic, proto, kind, source, flags = _INNER.unpack_from(data)
    if magic != wire.MAGIC or proto != wire.PROTO or flags or source != seat or kind not in KINDS:
        return None
    return kind, bytes(data[_INNER.size:])


def join_inner(kind: int, seat: int, body: bytes) -> bytes:
    """The driver's packet again, with the seat the key proved in its head."""
    return _INNER.pack(wire.MAGIC, wire.PROTO, kind, seat, 0) + body


# ---- receivers ----

@dataclass(frozen=True)
class Accepted:
    seat: int
    packet: bytes            # a driver packet: the head rebuilt with the proven seat
    address: tuple           # (ip, port) it came from


class SeatChannel:
    """One seat's receiving state in one match: its key, its replay window, its bucket, and where its UDP comes from."""

    def __init__(self, seat: int, ip: str, key: bytes, now: float, rate: float = SEAT_RATE, burst: float = SEAT_BURST):
        self.seat, self.ip, self.key = seat, ip, key
        self.window = ReplayWindow()
        self.limit = SeatLimit(now, rate, burst)
        self.port: int | None = None          # where this seat's datagrams come from (learned)
        self.port_counter = 0


class HostReceiver:
    """The host's steps 1 to 7 for the datagrams of a running match. `begin_match` names the seats; `receive` gives back
    an `Accepted` or None (the reason is counted). The clock is the caller's, hashing is `verify` (so a test counts it)."""

    def __init__(self, counters: Counters, now: float, seats: int = wire.MAX_SEATS):
        self.counters, self.seats = counters, seats
        self.match_id: int | None = None
        self._by_ip: dict[str, list[SeatChannel]] = {}
        self._buckets: dict[str, TokenBucket] = {}
        self._total = TokenBucket(TOTAL_RATE, TOTAL_BURST, now)
        self.channels: dict[int, SeatChannel] = {}

    def begin_match(self, match_id: int, seats: dict, now: float, seat_count: int | None = None,
                    rate: float = SEAT_RATE, burst: float = SEAT_BURST) -> None:
        """`seats`: seat -> (ip, key of guest-to-host datagrams)."""
        self.match_id = match_id
        self.seats = seat_count or self.seats
        self.channels = {seat: SeatChannel(seat, ip, key, now, rate, burst) for seat, (ip, key) in seats.items()}
        self._by_ip = {}
        for channel in self.channels.values():
            self._by_ip.setdefault(channel.ip, []).append(channel)
        self._buckets = {ip: TokenBucket(ADDRESS_RATE, ADDRESS_BURST, now) for ip in self._by_ip}

    def end_match(self) -> None:
        self.match_id, self.channels, self._by_ip, self._buckets = None, {}, {}, {}

    def drop_seat(self, seat: int) -> None:
        channel = self.channels.pop(seat, None)
        if channel is not None and channel in self._by_ip.get(channel.ip, []):
            self._by_ip[channel.ip].remove(channel)
            if not self._by_ip[channel.ip]:
                del self._by_ip[channel.ip]
                self._buckets.pop(channel.ip, None)

    def over(self, now: float) -> list[int]:
        """The seats that have been above their limit for too long."""
        return [seat for seat, channel in self.channels.items() if channel.limit.over(now)]

    def receive(self, source: tuple, data: bytes, now: float) -> Accepted | None:
        ip, port = source
        candidates = self._by_ip.get(ip)
        if not candidates:                                                  # 1: an authenticated peer's address
            self.counters.count('source', ip)
            return None
        if not MIN_SIZE <= len(data) <= MAX_SIZE:                           # 2
            self.counters.count('size', ip)
            return None
        head = parse_head(data)                                             # 3
        if head is None or head.match_id != self.match_id:
            self.counters.count('format', ip)
            return None
        channel = next((item for item in candidates if item.seat == head.seat), None)
        if channel is None:
            self.counters.count('format', ip)
            return None
        if not self._buckets[ip].take(now) or not self._total.take(now):    # 4
            self.counters.count('address_rate', ip)
            return None
        if not verify(data, channel.key):                                   # 5
            self.counters.count('tag', ip)
            return None
        if not channel.window.accept(head.counter):                         # 6
            self.counters.count('replay', ip)
            return None
        if channel.port is None or head.counter > channel.port_counter:
            channel.port, channel.port_counter = port, head.counter
        if not channel.limit.take(now):                                     # 7
            self.counters.count('seat_rate', ip)
            return None
        packet = join_inner(head.kind, head.seat, body_of(data))
        if wire.decode(packet, self.seats) is None:
            self.counters.count('body', ip)
            return None
        return Accepted(head.seat, packet, (ip, channel.port))


class GuestReceiver:
    """The guest's steps 2 to 7 with the host's key, and step 1 as the host's exact address and port."""

    def __init__(self, counters: Counters, host: tuple, match_id: int, seat: int, key: bytes, seats: int, now: float,
                 rate: float = 600.0, burst: float = 120.0):
        self.counters, self.host, self.match_id, self.seat, self.key, self.seats = counters, host, match_id, seat, key, seats
        self.window = ReplayWindow()
        self.limit = SeatLimit(now, rate, burst)
        self._address = TokenBucket(ADDRESS_RATE, ADDRESS_BURST, now)

    def receive(self, source: tuple, data: bytes, now: float) -> Accepted | None:
        if tuple(source) != tuple(self.host):
            self.counters.count('source', source[0])
            return None
        if not MIN_SIZE <= len(data) <= MAX_SIZE:
            self.counters.count('size', source[0])
            return None
        head = parse_head(data)
        if head is None or head.match_id != self.match_id or head.seat != 0:
            self.counters.count('format', source[0])
            return None
        if not self._address.take(now):
            self.counters.count('address_rate', source[0])
            return None
        if not verify(data, self.key):
            self.counters.count('tag', source[0])
            return None
        if not self.window.accept(head.counter):
            self.counters.count('replay', source[0])
            return None
        if not self.limit.take(now):
            self.counters.count('seat_rate', source[0])
            return None
        packet = join_inner(head.kind, 0, body_of(data))
        if wire.decode(packet, self.seats) is None:
            self.counters.count('body', source[0])
            return None
        return Accepted(0, packet, tuple(source))
