"""The pipe between the netplay worker and a game in a session: its messages, encoded and decoded.

The specification is `native/hostkit/hostkit_session.h` (RRHK_SESSION_ABI). Every message, both ways, is
`u16 type, u16 payload length, payload`, little-endian, at most MAX_PAYLOAD bytes. The numbers below repeat the
header's; `tests/test_netplay_lockstep.py` compares each of them with the header, so the two cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
import unicodedata

ABI = 1
MAX_PAYLOAD = 4096
MAX_RING = 64
ENV = 'RETRORECOMP_NETPLAY_PIPE'
MAX_PLAYERS = 4              # RRHK_MAX_PLAYERS: the port words a RUN may carry

# game -> worker
MSG_HELLO, MSG_LOCAL, MSG_DONE, MSG_DIGEST_OF, MSG_REFUSED, MSG_EXIT = 1, 2, 3, 4, 5, 6
# worker -> game
MSG_SETUP, MSG_RUN, MSG_SAVE, MSG_LOAD, MSG_DIGEST, MSG_PAUSE, MSG_NOTICE, MSG_PACE, MSG_STOP = range(32, 41)

CAP_SNAPSHOT, CAP_DIGEST, CAP_POINTER, CAP_AXES, CAP_KEYBOARD, CAP_DRIVEN = 1, 2, 4, 8, 16, 32
SETUP_GUEST = 1
RUN_SILENT = 1
SYS_PAUSE = 1
REFUSED_OPTION, REFUSED_SNAPSHOT, REFUSED_COMMAND = 1, 2, 3
EXIT_CLOSED, EXIT_LOST, EXIT_STOPPED, EXIT_FAILED = 1, 2, 3, 4
NOTICE_WAITING, NOTICE_RESUMED, NOTICE_LEFT = 1, 2, 3
STOP_HOST_CLOSED, STOP_DESYNC, STOP_ENDED = 1, 2, 3
PACE_LIMIT = 20000           # parts per million, either way

# The header's names, for the test that compares the two.
HEADER_NAMES = {
    'RRHK_MSG_HELLO': MSG_HELLO, 'RRHK_MSG_LOCAL': MSG_LOCAL, 'RRHK_MSG_DONE': MSG_DONE,
    'RRHK_MSG_DIGEST_OF': MSG_DIGEST_OF, 'RRHK_MSG_REFUSED': MSG_REFUSED, 'RRHK_MSG_EXIT': MSG_EXIT,
    'RRHK_MSG_SETUP': MSG_SETUP, 'RRHK_MSG_RUN': MSG_RUN, 'RRHK_MSG_SAVE': MSG_SAVE, 'RRHK_MSG_LOAD': MSG_LOAD,
    'RRHK_MSG_DIGEST': MSG_DIGEST, 'RRHK_MSG_PAUSE': MSG_PAUSE, 'RRHK_MSG_NOTICE': MSG_NOTICE,
    'RRHK_MSG_PACE': MSG_PACE, 'RRHK_MSG_STOP': MSG_STOP,
    'RRHK_CAP_SNAPSHOT': CAP_SNAPSHOT, 'RRHK_CAP_DIGEST': CAP_DIGEST, 'RRHK_CAP_POINTER': CAP_POINTER,
    'RRHK_CAP_AXES': CAP_AXES, 'RRHK_CAP_KEYBOARD': CAP_KEYBOARD, 'RRHK_CAP_DRIVEN': CAP_DRIVEN,
    'RRHK_SETUP_GUEST': SETUP_GUEST, 'RRHK_RUN_SILENT': RUN_SILENT, 'RRHK_SYS_PAUSE': SYS_PAUSE,
    'RRHK_REFUSED_OPTION': REFUSED_OPTION, 'RRHK_REFUSED_SNAPSHOT': REFUSED_SNAPSHOT,
    'RRHK_REFUSED_COMMAND': REFUSED_COMMAND,
    'RRHK_EXIT_CLOSED': EXIT_CLOSED, 'RRHK_EXIT_LOST': EXIT_LOST, 'RRHK_EXIT_STOPPED': EXIT_STOPPED,
    'RRHK_EXIT_FAILED': EXIT_FAILED,
    'RRHK_NOTICE_WAITING': NOTICE_WAITING, 'RRHK_NOTICE_RESUMED': NOTICE_RESUMED, 'RRHK_NOTICE_LEFT': NOTICE_LEFT,
    'RRHK_STOP_HOST_CLOSED': STOP_HOST_CLOSED, 'RRHK_STOP_DESYNC': STOP_DESYNC, 'RRHK_STOP_ENDED': STOP_ENDED,
}


class Refused(Exception):
    """This game cannot play in the session asked (another ABI, no digest, controls outside the pad words)."""


class Broken(Exception):
    """A message from the game broke the rules of the pipe."""


@dataclass(frozen=True)
class Hello:
    abi: int
    players: int
    caps: int
    snap_bound: int
    frame_rate_millihertz: int
    name: str

    @property
    def frame_seconds(self) -> float:
        return 1000.0 / self.frame_rate_millihertz if self.frame_rate_millihertz else 1.0 / 60.0


def frame(kind: int, payload: bytes = b'') -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError('a pipe message of more than MAX_PAYLOAD bytes')
    return struct.pack('<HH', kind, len(payload)) + payload


class MessageReader:
    """Whole messages out of the bytes read so far; a length above the limit or a type 0 breaks the pipe."""

    def __init__(self):
        self.buffer = b''

    def feed(self, chunk: bytes) -> list[tuple[int, bytes]]:
        self.buffer += chunk
        messages = []
        while len(self.buffer) >= 4:
            kind, size = struct.unpack_from('<HH', self.buffer)
            if size > MAX_PAYLOAD or not kind:
                raise Broken(f'message type {kind}, {size} bytes')
            if len(self.buffer) < 4 + size:
                break
            messages.append((kind, self.buffer[4:4 + size]))
            self.buffer = self.buffer[4 + size:]
        return messages


# ---- game -> worker ----

def parse_hello(payload: bytes) -> Hello:
    if len(payload) < 13:
        raise Broken('a short HELLO')
    abi, players, caps, bound, rate, length = struct.unpack_from('<HBBIIB', payload)
    if len(payload) != 13 + length:
        raise Broken('a HELLO of the wrong length')
    return Hello(abi, players, caps, bound, rate, payload[13:].decode('ascii', 'replace'))


def check_hello(hello: Hello, seats: int) -> None:
    """Refuses what the delay tier of stage 1 cannot do; the reason is a sentence for the lobby."""
    if hello.abi != ABI:
        raise Refused(f'the game speaks session ABI {hello.abi}, this Retro-Recomp speaks {ABI}')
    if not hello.caps & CAP_DIGEST:
        raise Refused('the game gives no digest: two copies could not be compared')
    for bit, what in ((CAP_POINTER, 'a pointer or light gun'), (CAP_AXES, 'analogue sticks'),
                      (CAP_KEYBOARD, "a computer's keyboard")):
        if hello.caps & bit:
            raise Refused(f'the game reads {what}, which the pad words do not carry yet')
    if not 1 <= seats <= min(hello.players, MAX_PLAYERS):
        raise Refused(f'{seats} seats asked, the game has {hello.players} players')
    if not hello.frame_rate_millihertz:
        raise Refused('the game gives no frame rate')


def parse_local(payload: bytes) -> tuple[int, int, int]:
    """(frame about to run, word, system bits)"""
    if len(payload) != 8:
        raise Broken('a LOCAL of the wrong length')
    return struct.unpack('<IHH', payload)


def parse_done(payload: bytes) -> tuple[int, int]:
    if len(payload) != 8:
        raise Broken('a DONE of the wrong length')
    return struct.unpack('<II', payload)


def parse_digest_of(payload: bytes) -> tuple[int, int]:
    """(last frame run, digest)"""
    if len(payload) != 12:
        raise Broken('a DIGEST_OF of the wrong length')
    return struct.unpack('<IQ', payload)


def parse_refused(payload: bytes) -> tuple[int, str]:
    if len(payload) < 3 or len(payload) != 3 + payload[2]:
        raise Broken('a REFUSED of the wrong length')
    return struct.unpack_from('<H', payload)[0], payload[3:].decode('ascii', 'replace')


def parse_exit(payload: bytes) -> int:
    if len(payload) != 2:
        raise Broken('an EXIT of the wrong length')
    return struct.unpack('<H', payload)[0]


# ---- worker -> game ----

def clean_name(name: str) -> bytes:
    """A player's name as a game can draw it: ASCII, accents folded, at most 16 characters."""
    folded = unicodedata.normalize('NFKD', name)
    text = ''.join(c if 32 <= ord(c) < 127 else '?' for c in folded if not unicodedata.combining(c))
    return text.strip()[:16].encode('ascii') or b'?'


def setup(seat: int, ports: int, ring_depth: int = 0, guest: bool = False, options: str = '') -> bytes:
    text = options.encode('ascii')
    return frame(MSG_SETUP, struct.pack('<BBBBH', seat, ports, ring_depth, SETUP_GUEST if guest else 0, len(text)) + text)


def run(frame_number: int, words, silent: bool = False) -> bytes:
    return frame(MSG_RUN, struct.pack(f'<IBB{len(words)}H', frame_number, RUN_SILENT if silent else 0, len(words), *words))


def digest() -> bytes:
    return frame(MSG_DIGEST)


def pause(on: bool, name: str = '') -> bytes:
    text = clean_name(name) if on else b''
    return frame(MSG_PAUSE, bytes([1 if on else 0, len(text)]) + text)


def notice(code: int, name: str = '') -> bytes:
    text = clean_name(name) if name else b''
    return frame(MSG_NOTICE, struct.pack('<HB', code, len(text)) + text)


def pace(ppm: int) -> bytes:
    return frame(MSG_PACE, struct.pack('<i', max(-PACE_LIMIT, min(PACE_LIMIT, int(ppm)))))


def stop(reason: int) -> bytes:
    return frame(MSG_STOP, struct.pack('<H', reason))
