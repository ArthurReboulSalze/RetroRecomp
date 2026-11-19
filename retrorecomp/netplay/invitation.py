"""The invitation of a room, and which addresses a "local network" room may use. Pure: no socket, nothing resolved.

    rr1:lan:<IPv4 literal>:<port>:<26 characters of base 32>

The secret is 128 random bits from `secrets`, new for each room, kept in memory only. The invitation is a pasted text,
so it is untrusted: `parse` is a pure function, fuzzed by `tests/test_netplay_transport.py`, and its error never
repeats the text it was given (the secret is in it).

The ranges that count as local are written out here (`ipaddress.is_private` is wider and changed between Python
versions): 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, and 100.64.0.0/10, which is where the VPNs
between friends (Tailscale, ZeroTier) live, by the owner's decision of 17 November 2026. 127.0.0.1 is accepted only
when the caller says `tests=True`; the product never does.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import ipaddress
import secrets

PREFIX = 'rr1'
MAX_LENGTH = 64
MIN_PORT, MAX_PORT = 1024, 65535
SECRET_BYTES = 16
SECRET_CHARS = 26
DEFAULT_PORT = 24611             # one fixed default, shown in the room and changeable by the host
LAN_NETWORKS = tuple(ipaddress.IPv4Network(text) for text in
                     ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '100.64.0.0/10'))
LOOPBACK = ipaddress.IPv4Address('127.0.0.1')


class InvitationError(ValueError):
    """The text is not an invitation this version can use. `reason` is a fixed sentence, never the text; `code` the same in a
    word for the window: 'bad', 'typo' or 'other_version' (an Internet key, `internet_key`)."""

    def __init__(self, reason: str, code: str = 'bad'):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass(frozen=True)
class Invitation:
    address: str
    port: int
    secret: bytes = field(repr=False)          # never printed, not even by an f-string of the object
    kind: str = 'lan'


def new_secret() -> bytes:
    return secrets.token_bytes(SECRET_BYTES)


def encode_secret(secret: bytes) -> str:
    return base64.b32encode(secret).decode('ascii').rstrip('=')


def decode_secret(text: str) -> bytes | None:
    """The 16 bytes of 26 base-32 characters (case does not matter), or None; only the canonical spelling is taken."""
    if len(text) != SECRET_CHARS or not text.isascii():
        return None
    try:
        secret = base64.b32decode(text.upper() + '======', casefold=False)
    except ValueError:
        return None
    return secret if len(secret) == SECRET_BYTES and encode_secret(secret) == text.upper() else None


def is_lan_address(address, tests: bool = False) -> bool:
    """Whether an IPv4 address (text or object) is in a range a local room may use."""
    try:
        ip = address if isinstance(address, ipaddress.IPv4Address) else ipaddress.IPv4Address(address)
    except ValueError:
        return False
    return any(ip in network for network in LAN_NETWORKS) or (tests and ip == LOOPBACK)


def check_bind_address(address, tests: bool = False) -> str:
    """The address a room's sockets may be bound to, as text, or ValueError. Never '', 0.0.0.0, '::', a name or a
    public address; 127.0.0.1 only under `tests`. No socket is made here: this is what the transport asks first."""
    if not isinstance(address, str) or not address.isascii() or not address.strip() or address != address.strip():
        raise ValueError('a room is bound to one local IPv4 address')
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        raise ValueError('a room is bound to one local IPv4 address') from None
    if not is_lan_address(ip, tests):
        raise ValueError('the address is not on a local network')
    return str(ip)


def format_invitation(address: str, port: int, secret: bytes, tests: bool = False) -> str:
    return f'{PREFIX}:lan:{check_bind_address(address, tests)}:{port}:{encode_secret(secret)}'


def parse(text, tests: bool = False) -> Invitation:
    """The invitation in `text`, or `InvitationError`. Surrounding white space is removed; nothing else is repaired."""
    if not isinstance(text, str):
        raise InvitationError('this is not an invitation')
    text = text.strip()
    if not text or len(text) > MAX_LENGTH or not text.isascii():
        raise InvitationError('this is not an invitation')
    parts = text.split(':')
    if len(parts) != 5 or parts[0] != PREFIX:
        raise InvitationError('this is not an invitation')
    _prefix, kind, address, port, secret = parts
    if kind == 'net':
        raise InvitationError('this version has no Internet room')
    if kind != 'lan':
        raise InvitationError('this is not an invitation')
    if not (port.isdigit() and port.isascii() and str(int(port)) == port and MIN_PORT <= int(port) <= MAX_PORT):
        raise InvitationError('this is not an invitation')
    key = decode_secret(secret)
    if key is None:
        raise InvitationError('this is not an invitation')
    try:
        ip = ipaddress.IPv4Address(address)
    except ValueError:
        raise InvitationError('this is not an invitation') from None
    if str(ip) != address:
        raise InvitationError('this is not an invitation')
    if not is_lan_address(ip, tests):
        raise InvitationError('this invitation is not for a room on a local network')
    return Invitation(str(ip), int(port), key)
