"""The room's encryption, kept to the minimum (Arthur, 19 November 2026: « vas-y doucement … un minimum »): an X25519
exchange in the handshake and ChaCha20-Poly1305 on every control frame and match datagram, from `cryptography` (PyCA,
Apache-2.0 OR BSD-3-Clause). Nothing else of its own.

Every key here is used in one direction only (the handshake derives one per direction, per match and per seat), and the
nonce is that direction's counter (frames: the count of frames sent; datagrams: the datagram's counter), so a nonce is never
used twice with one key. The tag is 16 bytes, where the keyed BLAKE2b tag of protocol 3 was: the sizes do not change.
"""
from __future__ import annotations

from functools import lru_cache
import struct

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

KEY_SIZE = 32
TAG_SIZE = 16


def keypair(private: bytes) -> tuple[X25519PrivateKey, bytes]:
    """An X25519 key from 32 random bytes (the caller's generator, so a test can fix it) and its public half."""
    key = X25519PrivateKey.from_private_bytes(private)
    return key, key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def shared(key: X25519PrivateKey, peer_public: bytes) -> bytes | None:
    """The shared secret with a peer's public key, or None for a key that is not one (wrong size, or a low-order point
    that gives the all-zero secret)."""
    if len(peer_public) != KEY_SIZE:
        return None
    try:
        secret = key.exchange(X25519PublicKey.from_public_bytes(peer_public))
    except ValueError:
        return None
    return None if secret == bytes(KEY_SIZE) else secret


@lru_cache(maxsize=256)
def _cipher(key: bytes) -> ChaCha20Poly1305:
    return ChaCha20Poly1305(key)


def _nonce(counter: int) -> bytes:
    return struct.pack('<QI', counter, 0)


def seal(key: bytes, counter: int, data: bytes, associated: bytes) -> bytes:
    """`data` encrypted, followed by its 16-byte tag; `associated` (a header sent in clear) is covered by the tag."""
    return _cipher(key).encrypt(_nonce(counter), data, associated)


def open_(key: bytes, counter: int, sealed: bytes, associated: bytes) -> bytes | None:
    """The plain bytes of `sealed` (data then tag), or None when the tag does not verify."""
    if len(sealed) < TAG_SIZE:
        return None
    try:
        return _cipher(key).decrypt(_nonce(counter), sealed, associated)
    except InvalidTag:
        return None
