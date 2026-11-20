"""The key of an Internet room, and its typed form (Arthur, 19 November 2026: « une seule phrase … une clé qui permet de
filer l'adresse IP et le code du salon »; « légèrement encodé »). Pure: no socket, nothing resolved, nothing fetched.

    RR2-XXXXX-XXXXX-...      Crockford base 32 of:
        version u8 (1) | flags u8 (bit 0: an IPv4 address follows, bit 1: an IPv6 address follows)
        | IPv4 4 | port u16 | secret 16 | IPv6 16 | check 2 (BLAKE2b of everything before it)

The address is encoded, not hidden: whoever reads this format (it is public) reads the address. What protects the room is
the 128-bit secret and the encryption of protocol 4; whoever holds the key is invited. The check catches a typing error
before anything connects.

The typed form is the host's address, the port (24611 by default) and the code: the same 128-bit secret in 26 Crockford
characters, shown 5-5-5-5-6, followed by Crockford's check symbol (the number mod 37), so a typing error is caught too.
Crockford's alphabet has no I, L, O or U, and reads O as 0 and I or L as 1; case, dashes and spaces do not matter.

Errors are `invitation.InvitationError` with a fixed sentence and `.code` in ('typo', 'other_version', 'bad'), never the text
(the secret is in it).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress

from .invitation import DEFAULT_PORT, MAX_PORT, MIN_PORT, SECRET_BYTES, InvitationError

PREFIX = 'RR2'
VERSION = 1
HAS_V4, HAS_V6 = 1, 2
CHECK_BYTES = 2
MAX_KEY_LENGTH = 120
ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'
CHECK_SYMBOLS = ALPHABET + '*~$=U'               # Crockford's check symbols: the 32 digits, then five more (37 values)
CODE_CHARS = 26
_READ = {**{c: i for i, c in enumerate(ALPHABET)}, 'O': 0, 'I': 1, 'L': 1}


@dataclass(frozen=True)
class NetInvitation:
    """An Internet room: the host's addresses (IPv4 first when there is one), its port and the room's secret."""
    addresses: tuple
    port: int
    secret: bytes = field(repr=False)
    kind: str = 'net'

    @property
    def address(self) -> str:
        return self.addresses[0]


def _error(code: str) -> InvitationError:
    sentence = {'typo': 'this key or code has a typing error', 'other_version': 'this key is from another version of Retro-Recomp',
                'bad': 'this is not a key'}[code]
    return InvitationError(sentence, code)


def _base32(data: bytes) -> str:
    number, bits = int.from_bytes(data, 'big'), len(data) * 8
    pad = -bits % 5
    number <<= pad
    return ''.join(ALPHABET[(number >> shift) & 31] for shift in range(bits + pad - 5, -1, -5))


def _unbase32(text: str, size: int) -> bytes | None:
    """`size` bytes from Crockford characters, or None when a character is not one or the padding bits are not zero."""
    number = 0
    for character in text:
        value = _READ.get(character)
        if value is None:
            return None
        number = number << 5 | value
    pad = len(text) * 5 - size * 8
    if pad < 0 or pad >= 5 or number & ((1 << pad) - 1):
        return None
    return (number >> pad).to_bytes(size, 'big')


def _clean(text) -> str:
    if not isinstance(text, str) or not text.isascii() or len(text) > MAX_KEY_LENGTH:
        raise _error('bad')
    return ''.join(character for character in text.upper() if character not in ' -\t\r\n')


def _address(text, allow_loopback: bool):
    """A usable unicast address of either family, or None."""
    try:
        ip = ipaddress.ip_address(text.strip() if isinstance(text, str) else text)
    except ValueError:
        return None
    if ip.is_multicast or ip.is_unspecified or ip.is_reserved or (ip.is_loopback and not allow_loopback):
        return None
    if isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.is_link_local):
        return None
    if isinstance(ip, ipaddress.IPv4Address) and ip == ipaddress.IPv4Address('255.255.255.255'):
        return None
    return ip


def _group(text: str, size: int = 5) -> str:
    return '-'.join(text[index:index + size] for index in range(0, len(text), size))


def format_key(port: int, secret: bytes, ipv4: str | None = None, ipv6: str | None = None, tests: bool = False) -> str:
    """The key of a room reachable at `ipv4` and/or `ipv6` on `port`; ValueError for anything that could not be joined."""
    if len(secret) != SECRET_BYTES or not MIN_PORT <= port <= MAX_PORT or not (ipv4 or ipv6):
        raise ValueError('a key needs an address, a port and the secret')
    v4 = _address(ipv4, tests) if ipv4 else None
    v6 = _address(ipv6, tests) if ipv6 else None
    if (ipv4 and not isinstance(v4, ipaddress.IPv4Address)) or (ipv6 and not isinstance(v6, ipaddress.IPv6Address)):
        raise ValueError('not an address a player can join')
    payload = bytes((VERSION, (HAS_V4 if v4 else 0) | (HAS_V6 if v6 else 0)))
    payload += (v4.packed if v4 else b'') + port.to_bytes(2, 'big') + secret + (v6.packed if v6 else b'')
    payload += hashlib.blake2b(payload, digest_size=CHECK_BYTES).digest()
    return PREFIX + '-' + _group(_base32(payload))


def parse_key(text, tests: bool = False) -> NetInvitation:
    """The room of a key, or InvitationError with `.code`."""
    cleaned = _clean(text)
    if not cleaned.startswith(PREFIX):
        raise _error('other_version' if len(cleaned) > 3 and cleaned[:2] == 'RR' and cleaned[2:3].isdigit() else 'bad')
    body = cleaned[len(PREFIX):]
    for flags, size in ((HAS_V4, 2 + 4 + 2 + SECRET_BYTES), (HAS_V6, 2 + 2 + SECRET_BYTES + 16),
                        (HAS_V4 | HAS_V6, 2 + 4 + 2 + SECRET_BYTES + 16)):
        size += CHECK_BYTES
        if len(body) == -(-size * 8 // 5):
            break
    else:
        raise _error('typo' if 30 <= len(body) <= 80 else 'bad')
    data = _unbase32(body, size)
    if data is None:
        raise _error('typo')
    payload, check = data[:-CHECK_BYTES], data[-CHECK_BYTES:]
    if hashlib.blake2b(payload, digest_size=CHECK_BYTES).digest() != check:
        raise _error('typo')
    if payload[0] != VERSION:
        raise _error('other_version')
    if payload[1] != flags:
        raise _error('bad')
    offset, addresses = 2, []
    if flags & HAS_V4:
        addresses.append(ipaddress.IPv4Address(payload[offset:offset + 4]))
        offset += 4
    port = int.from_bytes(payload[offset:offset + 2], 'big')
    secret = payload[offset + 2:offset + 2 + SECRET_BYTES]
    offset += 2 + SECRET_BYTES
    if flags & HAS_V6:
        addresses.append(ipaddress.IPv6Address(payload[offset:offset + 16]))
    if not MIN_PORT <= port <= MAX_PORT or any(_address(str(ip), tests) is None for ip in addresses):
        raise _error('bad')
    return NetInvitation(tuple(str(ip) for ip in addresses), port, secret)


def parse_any(text, tests: bool = False):
    """A pasted text: an Internet room's key (RR2-...) or a local room's invitation (rr1:lan:...), or InvitationError."""
    head = text.strip()[:3].upper() if isinstance(text, str) else ''
    if head[:2] == 'RR' and head[2:3].isdigit() and head != 'RR1':      # RR2 now; a later RRn says "another version"
        return parse_key(text, tests)
    from .invitation import parse
    return parse(text, tests)


def format_code(secret: bytes) -> str:
    """The typed code of a secret: 26 characters in groups of 5-5-5-5-6, then the check symbol."""
    if len(secret) != SECRET_BYTES:
        raise ValueError('a code is made of the 16 bytes of a secret')
    body = _base32(secret)
    check = CHECK_SYMBOLS[int.from_bytes(secret, 'big') % 37]
    return '-'.join((body[0:5], body[5:10], body[10:15], body[15:20], body[20:26] + check))


def parse_code(text) -> bytes:
    """The secret of a typed code, or InvitationError with `.code`."""
    cleaned = _clean(text)
    if len(cleaned) != CODE_CHARS + 1:
        raise _error('typo' if 20 <= len(cleaned) <= 32 else 'bad')
    secret = _unbase32(cleaned[:CODE_CHARS], SECRET_BYTES)
    check = {'O': '0', 'I': '1', 'L': '1'}.get(cleaned[-1], cleaned[-1])        # read as Crockford reads its digits
    if secret is None or CHECK_SYMBOLS[int.from_bytes(secret, 'big') % 37] != check:
        raise _error('typo')
    return secret


def parse_manual(address, port, code, tests: bool = False) -> NetInvitation:
    """The room of the typed form: an address (IPv4 or IPv6, never a name), a port (empty: the default) and the code."""
    ip = _address(address, tests) if isinstance(address, str) else None
    if ip is None:
        raise _error('bad')
    if port in (None, ''):
        port = DEFAULT_PORT
    try:
        number = int(str(port).strip())
    except ValueError:
        raise _error('bad') from None
    if not MIN_PORT <= number <= MAX_PORT:
        raise _error('bad')
    return NetInvitation((str(ip),), number, parse_code(code))
