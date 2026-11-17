"""The keys of a room and the handshake that opens a TCP connection, as pure state machines: bytes in, bytes out.

No socket, no clock of its own (the caller passes `now`), no thread. The transport (`lan_transport`) feeds what it
reads and sends what these return. `SECURITY_REVIEW.md` section 2.3 and 2.4 are the specification.

    S        the 16 bytes of the invitation (never sent)
    K_auth   = mac(S, 'rr1 auth')                                   for the handshake's tags
    K_sess   = mac(S, 'rr1 session', proto | nonce_g | nonce_h)     one per connection
    K_tcp    one key per direction, from K_sess;  K_udp one per direction, per match and per seat, from K_sess

    1  guest to host, 38 bytes   'RRNP' | proto u16 | nonce_g 16 | tag 16         the guest proves first
    2  host to guest, 32 bytes   nonce_h 16 | proof_h 16                          only to a peer that proved
    3  guest to host, 16 bytes   proof_g                                         over the host's fresh nonce

A host that is not satisfied closes **without sending a byte**. A guest that is not satisfied closes silently too.
Every comparison is constant-time (`hmac.compare_digest`).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
import struct
from typing import Callable

from .limits import HANDSHAKE_SECONDS, NonceMemory

MAGIC = b'RRNP'
PROTO = 3
NONCE, TAG = 16, 16
FIRST_SIZE = len(MAGIC) + 2 + NONCE + TAG        # 38
SECOND_SIZE = NONCE + TAG                        # 32
THIRD_SIZE = TAG                                 # 16


def mac(key: bytes, *parts: bytes, n: int = 16) -> bytes:
    """Keyed BLAKE2b over parts that are each length-prefixed, so that no two lists of parts give the same input."""
    digest = hashlib.blake2b(key=key, digest_size=n)
    for part in parts:
        digest.update(len(part).to_bytes(2, 'little'))
        digest.update(part)
    return digest.digest()


def auth_key(secret: bytes) -> bytes:
    return mac(secret, b'rr1 auth', n=32)


def session_key(secret: bytes, proto: int, nonce_g: bytes, nonce_h: bytes) -> bytes:
    transcript = struct.pack('<H', proto) + nonce_g + nonce_h
    return mac(secret, b'rr1 session', transcript, n=32)


def tcp_keys(session: bytes) -> tuple[bytes, bytes]:
    """(guest to host, host to guest)."""
    return mac(session, b'tcp g>h', n=32), mac(session, b'tcp h>g', n=32)


def udp_keys(session: bytes, match_id: int, seat: int) -> tuple[bytes, bytes]:
    """(guest to host, host to guest) for one match and one seat: nothing of another match or seat verifies."""
    scope = struct.pack('<IB', match_id, seat)
    return mac(session, b'udp g>h', scope, n=32), mac(session, b'udp h>g', scope, n=32)


def _first(key: bytes, proto: int, nonce_g: bytes) -> bytes:
    return mac(key, b'C1', MAGIC, struct.pack('<H', proto), nonce_g)


def _proof_host(key: bytes, proto: int, nonce_g: bytes, nonce_h: bytes) -> bytes:
    return mac(key, b'H1', struct.pack('<H', proto), nonce_g, nonce_h)


def _proof_guest(key: bytes, proto: int, nonce_g: bytes, nonce_h: bytes) -> bytes:
    return mac(key, b'C2', struct.pack('<H', proto), nonce_g, nonce_h)


@dataclass(frozen=True)
class Session:
    """What a finished handshake leaves: the key of this connection and the protocol number the guest spoke."""
    key: bytes
    proto: int


@dataclass
class Step:
    """What a handshake machine gives back for the bytes fed to it: `send` goes to the peer, `closed` means close the
    connection now (silently), `done` means the handshake is over and `leftover` are the bytes that came after it."""
    send: bytes = b''
    closed: bool = False
    done: bool = False
    leftover: bytes = b''
    reason: str = ''


class HostHandshake:
    """The host's end. A stranger gets no byte: every failure is `closed` with nothing to send."""

    def __init__(self, secret: bytes, now: float, nonces: NonceMemory, rng: Callable[[int], bytes] = secrets.token_bytes):
        self._key = auth_key(secret)
        self._secret = secret
        self._nonces, self._rng = nonces, rng
        self.deadline = now + HANDSHAKE_SECONDS
        self._buffer = bytearray()
        self._stage = 1
        self._proto = 0
        self._nonce_g = self._nonce_h = b''
        self.session: Session | None = None

    def expired(self, now: float) -> bool:
        return self.session is None and now >= self.deadline

    def feed(self, data: bytes, now: float) -> Step:
        if self.session is not None:
            return Step(done=True, leftover=bytes(data))
        if now >= self.deadline:
            return Step(closed=True, reason='deadline')
        self._buffer += data
        if self._stage == 1:
            if len(self._buffer) >= len(MAGIC) and bytes(self._buffer[:len(MAGIC)]) != MAGIC:
                return Step(closed=True, reason='magic')
            if len(self._buffer) < FIRST_SIZE:
                return Step()
            if len(self._buffer) > FIRST_SIZE:      # nothing can follow message 1 before the host has answered
                return Step(closed=True, reason='size')
            proto, = struct.unpack_from('<H', self._buffer, len(MAGIC))
            nonce_g = bytes(self._buffer[len(MAGIC) + 2:len(MAGIC) + 2 + NONCE])
            tag = bytes(self._buffer[len(MAGIC) + 2 + NONCE:])
            if not hmac.compare_digest(tag, _first(self._key, proto, nonce_g)):
                return Step(closed=True, reason='tag')
            if self._nonces.seen(nonce_g):
                return Step(closed=True, reason='replay')
            self._nonces.remember(nonce_g)
            self._proto, self._nonce_g, self._nonce_h = proto, nonce_g, self._rng(NONCE)
            self._buffer.clear()
            self._stage = 3
            return Step(send=self._nonce_h + _proof_host(self._key, proto, nonce_g, self._nonce_h))
        if len(self._buffer) < THIRD_SIZE:
            return Step()
        proof, leftover = bytes(self._buffer[:THIRD_SIZE]), bytes(self._buffer[THIRD_SIZE:])
        if not hmac.compare_digest(proof, _proof_guest(self._key, self._proto, self._nonce_g, self._nonce_h)):
            return Step(closed=True, reason='proof')
        self.session = Session(session_key(self._secret, self._proto, self._nonce_g, self._nonce_h), self._proto)
        return Step(done=True, leftover=leftover)


class GuestHandshake:
    """The guest's end: `first()` is what it sends on connecting; `feed` takes what the host answers."""

    def __init__(self, secret: bytes, now: float, rng: Callable[[int], bytes] = secrets.token_bytes, proto: int = PROTO):
        self._key = auth_key(secret)
        self._secret, self._proto = secret, proto
        self._nonce_g = rng(NONCE)
        self.deadline = now + HANDSHAKE_SECONDS
        self._buffer = bytearray()
        self.session: Session | None = None

    def first(self) -> bytes:
        return MAGIC + struct.pack('<H', self._proto) + self._nonce_g + _first(self._key, self._proto, self._nonce_g)

    def expired(self, now: float) -> bool:
        return self.session is None and now >= self.deadline

    def feed(self, data: bytes, now: float) -> Step:
        if self.session is not None:
            return Step(done=True, leftover=bytes(data))
        if now >= self.deadline:
            return Step(closed=True, reason='deadline')
        self._buffer += data
        if len(self._buffer) < SECOND_SIZE:
            return Step()
        nonce_h, proof = bytes(self._buffer[:NONCE]), bytes(self._buffer[NONCE:SECOND_SIZE])
        leftover = bytes(self._buffer[SECOND_SIZE:])
        if not hmac.compare_digest(proof, _proof_host(self._key, self._proto, self._nonce_g, nonce_h)):
            return Step(closed=True, reason='proof')       # the host does not hold the secret: no word to it
        self.session = Session(session_key(self._secret, self._proto, self._nonce_g, nonce_h), self._proto)
        return Step(send=_proof_guest(self._key, self._proto, self._nonce_g, nonce_h), done=True, leftover=leftover)
