"""The pipe between the netplay worker and a game in a session: its messages, encoded and decoded.

The specification is `native/hostkit/hostkit_session.h` (RRHK_SESSION_ABI). Every message, both ways, is
`u16 type, u16 payload length, payload`, little-endian, at most MAX_PAYLOAD bytes. The numbers below repeat the
header's; `tests/test_netplay_lockstep.py` compares each of them with the header, so the two cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
import unicodedata

ABI = 7                      # 2: restart for everyone (SYS_RESTART in LOCAL, RUN_RESET in RUN); 3: the chat and the turn notices;
                             # 4: the host's quick save and load for everyone (SYS_STATE_*, RUN_STATE_*); 5: a driven machine with
                             # snapshots takes silent RUNs (rollback for every machine); 6: HELLO carries the game's run-changing
                             # options (the host's go to every seat); 7: the sticks travel (LOCAL and RUN carry AXES int8 values)
MAX_PAYLOAD = 4096
MAX_RING = 64
MAX_OPTIONS = 1024           # RRHK_SESSION_MAX_OPTIONS: the run-changing options a HELLO may carry
ENV = 'RETRORECOMP_NETPLAY_PIPE'
MAX_PLAYERS = 4              # RRHK_MAX_PLAYERS: the port words a RUN may carry

# game -> worker
MSG_HELLO, MSG_LOCAL, MSG_DONE, MSG_DIGEST_OF, MSG_REFUSED, MSG_EXIT, MSG_CHAT_OUT = 1, 2, 3, 4, 5, 6, 7
# worker -> game
MSG_SETUP, MSG_RUN, MSG_SAVE, MSG_LOAD, MSG_DIGEST, MSG_PAUSE, MSG_NOTICE, MSG_PACE, MSG_STOP, MSG_CHAT_SHOW = range(32, 42)

CAP_SNAPSHOT, CAP_DIGEST, CAP_POINTER, CAP_AXES, CAP_KEYBOARD, CAP_DRIVEN = 1, 2, 4, 8, 16, 32
SETUP_GUEST = 1
RUN_SILENT, RUN_RESET, RUN_STATE_SAVE, RUN_STATE_LOAD, RUN_AXES = 1, 2, 4, 8, 16
AXES = 4                     # RRHK_AXES: LX, LY, RX, RY per player, int8 (-127..127) in LOCAL and RUN
NO_AXES = (0,) * AXES
RUN_ACTIONS = (0, RUN_RESET, RUN_STATE_SAVE, RUN_STATE_LOAD)       # at most one of them before a frame
SYS_PAUSE, SYS_RESTART, SYS_STATE_SAVE, SYS_STATE_LOAD = 1, 2, 4, 8
REFUSED_OPTION, REFUSED_SNAPSHOT, REFUSED_COMMAND = 1, 2, 3
EXIT_CLOSED, EXIT_LOST, EXIT_STOPPED, EXIT_FAILED = 1, 2, 3, 4
NOTICE_WAITING, NOTICE_RESUMED, NOTICE_LEFT, NOTICE_TURN, NOTICE_YOUR_TURN, NOTICE_CHAT_SLOW = 1, 2, 3, 4, 5, 6
CHAT_MAX_TEXT, CHAT_MAX_NAME = 80, 16
PHRASE_GG, PHRASE_READY, PHRASE_AGAIN, PHRASE_PAUSE, PHRASE_MOMENT, PHRASE_THANKS = 1, 2, 3, 4, 5, 6
PHRASE_COUNT = 6
# The phrases a player sends with one press, by number (every game shows them in its own language; the lobby too).
PHRASES = {PHRASE_GG: 'GG', PHRASE_READY: 'Ready?', PHRASE_AGAIN: 'Again?', PHRASE_PAUSE: 'Pause please',
           PHRASE_MOMENT: 'One moment', PHRASE_THANKS: 'Thanks!'}
STOP_HOST_CLOSED, STOP_DESYNC, STOP_ENDED, STOP_BOOT_MISMATCH = 1, 2, 3, 4
PACE_LIMIT = 20000           # parts per million, either way

# The header's names, for the test that compares the two.
HEADER_NAMES = {
    'RRHK_MSG_HELLO': MSG_HELLO, 'RRHK_MSG_LOCAL': MSG_LOCAL, 'RRHK_MSG_DONE': MSG_DONE,
    'RRHK_MSG_DIGEST_OF': MSG_DIGEST_OF, 'RRHK_MSG_REFUSED': MSG_REFUSED, 'RRHK_MSG_EXIT': MSG_EXIT,
    'RRHK_MSG_CHAT_OUT': MSG_CHAT_OUT, 'RRHK_MSG_CHAT_SHOW': MSG_CHAT_SHOW,
    'RRHK_MSG_SETUP': MSG_SETUP, 'RRHK_MSG_RUN': MSG_RUN, 'RRHK_MSG_SAVE': MSG_SAVE, 'RRHK_MSG_LOAD': MSG_LOAD,
    'RRHK_MSG_DIGEST': MSG_DIGEST, 'RRHK_MSG_PAUSE': MSG_PAUSE, 'RRHK_MSG_NOTICE': MSG_NOTICE,
    'RRHK_MSG_PACE': MSG_PACE, 'RRHK_MSG_STOP': MSG_STOP,
    'RRHK_CAP_SNAPSHOT': CAP_SNAPSHOT, 'RRHK_CAP_DIGEST': CAP_DIGEST, 'RRHK_CAP_POINTER': CAP_POINTER,
    'RRHK_CAP_AXES': CAP_AXES, 'RRHK_CAP_KEYBOARD': CAP_KEYBOARD, 'RRHK_CAP_DRIVEN': CAP_DRIVEN,
    'RRHK_SETUP_GUEST': SETUP_GUEST, 'RRHK_RUN_SILENT': RUN_SILENT, 'RRHK_RUN_RESET': RUN_RESET,
    'RRHK_RUN_STATE_SAVE': RUN_STATE_SAVE, 'RRHK_RUN_STATE_LOAD': RUN_STATE_LOAD, 'RRHK_RUN_AXES': RUN_AXES,
    'RRHK_SYS_PAUSE': SYS_PAUSE, 'RRHK_SYS_RESTART': SYS_RESTART,
    'RRHK_SYS_STATE_SAVE': SYS_STATE_SAVE, 'RRHK_SYS_STATE_LOAD': SYS_STATE_LOAD,
    'RRHK_REFUSED_OPTION': REFUSED_OPTION, 'RRHK_REFUSED_SNAPSHOT': REFUSED_SNAPSHOT,
    'RRHK_REFUSED_COMMAND': REFUSED_COMMAND,
    'RRHK_EXIT_CLOSED': EXIT_CLOSED, 'RRHK_EXIT_LOST': EXIT_LOST, 'RRHK_EXIT_STOPPED': EXIT_STOPPED,
    'RRHK_EXIT_FAILED': EXIT_FAILED,
    'RRHK_NOTICE_WAITING': NOTICE_WAITING, 'RRHK_NOTICE_RESUMED': NOTICE_RESUMED, 'RRHK_NOTICE_LEFT': NOTICE_LEFT,
    'RRHK_NOTICE_TURN': NOTICE_TURN, 'RRHK_NOTICE_YOUR_TURN': NOTICE_YOUR_TURN, 'RRHK_NOTICE_CHAT_SLOW': NOTICE_CHAT_SLOW,
    'RRHK_PHRASE_GG': PHRASE_GG, 'RRHK_PHRASE_READY': PHRASE_READY, 'RRHK_PHRASE_AGAIN': PHRASE_AGAIN,
    'RRHK_PHRASE_PAUSE': PHRASE_PAUSE, 'RRHK_PHRASE_MOMENT': PHRASE_MOMENT, 'RRHK_PHRASE_THANKS': PHRASE_THANKS,
    'RRHK_PHRASE_COUNT': PHRASE_COUNT,
    'RRHK_STOP_HOST_CLOSED': STOP_HOST_CLOSED, 'RRHK_STOP_DESYNC': STOP_DESYNC, 'RRHK_STOP_ENDED': STOP_ENDED,
    'RRHK_STOP_BOOT_MISMATCH': STOP_BOOT_MISMATCH,
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
    options: str = ''           # this PC's run-changing options, "key=value" lines (the host's go to every seat)

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


def printable(raw: bytes) -> str:
    """Bytes 32 to 126 only: a text that came through the game (a name, an option line it refused) never carries a
    control character into the converter's window or log."""
    return bytes(b for b in raw if 32 <= b < 127).decode('ascii')


# ---- game -> worker ----

def parse_hello(payload: bytes) -> Hello:
    if len(payload) < 13:
        raise Broken('a short HELLO')
    abi, players, caps, bound, rate, length = struct.unpack_from('<HBBIIB', payload)
    if len(payload) < 13 + length:
        raise Broken('a HELLO of the wrong length')
    name, rest = printable(payload[13:13 + length]), payload[13 + length:]
    options = ''
    if rest:                     # session ABI 6: u16 length, the options (absent: none)
        if len(rest) < 2 or len(rest) != 2 + struct.unpack_from('<H', rest)[0] or len(rest) - 2 > MAX_OPTIONS:
            raise Broken('a HELLO of the wrong length')
        raw = rest[2:]
        if any(not (32 <= byte < 127 or byte == 10) for byte in raw):
            raise Broken('HELLO options that are not plain text')
        options = raw.decode('ascii')
    return Hello(abi, players, caps, bound, rate, name, options)


def check_hello(hello: Hello, seats: int, shared: bool = False) -> None:
    """Refuses what the delay tier of stage 1 cannot do; the reason is a sentence for the lobby. In input sharing the seats
    all drive the same controls, so the game's own players only have to be one: the seats are bounded by the room, not by it."""
    if hello.abi != ABI:
        raise Refused(f'the game speaks session ABI {hello.abi}, this Retro-Recomp speaks {ABI}')
    if not hello.caps & CAP_DIGEST:
        raise Refused('the game gives no digest: two copies could not be compared')
    for bit, what in ((CAP_POINTER, 'a pointer or light gun'), (CAP_KEYBOARD, "a computer's keyboard")):
        if hello.caps & bit:
            raise Refused(f'the game reads {what}, which the pad words do not carry yet')
    if shared:
        if not (1 <= seats <= MAX_PLAYERS and hello.players >= 1):
            raise Refused(f'{seats} seats asked, a room seats 1 to {MAX_PLAYERS}')
    elif not 1 <= seats <= min(hello.players, MAX_PLAYERS):
        raise Refused(f'{seats} seats asked, the game has {hello.players} players')
    if not hello.frame_rate_millihertz:
        raise Refused('the game gives no frame rate')


def parse_local(payload: bytes) -> tuple[int, int, int, tuple | None]:
    """(frame about to run, word, system bits, sticks): the sticks are this PC's AXES int8 values for a game with sticks
    (CAP_AXES), None otherwise."""
    if len(payload) == 8:
        return (*struct.unpack('<IHH', payload), None)
    if len(payload) == 8 + AXES:
        frame_number, word, system, *axes = struct.unpack(f'<IHH{AXES}b', payload)
        return frame_number, word, system, tuple(max(-127, value) for value in axes)
    raise Broken('a LOCAL of the wrong length')


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
    return struct.unpack_from('<H', payload)[0], printable(payload[3:])


def parse_chat_out(payload: bytes) -> tuple[int, str]:
    """(phrase, text) of a line the player typed in the game: a phrase number (1 to PHRASE_COUNT) with no text, or 0 with 1 to
    CHAT_MAX_TEXT printable ASCII characters. Anything else breaks the rules (the kit never sends it)."""
    if len(payload) < 2 or len(payload) != 2 + payload[1]:
        raise Broken('a CHAT_OUT of the wrong length')
    phrase, text = payload[0], payload[2:]
    if phrase > PHRASE_COUNT or (phrase and text) or (not phrase and not 1 <= len(text) <= CHAT_MAX_TEXT):
        raise Broken('a CHAT_OUT out of its bounds')
    if any(not 32 <= b < 127 for b in text):
        raise Broken('a CHAT_OUT that is not printable ASCII')
    return phrase, text.decode('ascii')


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


def run(frame_number: int, words, silent: bool = False, reset: bool = False, action: int = 0, axes=None) -> bytes:
    """`reset`: the machine restarts before this frame runs (the host's restart, on every seat at this frame). `action`: one of
    `RUN_ACTIONS`, done before the frame runs (the host's restart, or its save or load of the match's state)."""
    if action not in RUN_ACTIONS or (reset and action not in (0, RUN_RESET)):
        raise ValueError('one action at most before a frame')
    flags = (RUN_SILENT if silent else 0) | (RUN_RESET if reset else 0) | action
    payload = struct.pack(f'<IBB{len(words)}H', frame_number, flags, len(words), *words)
    if axes is not None:         # `axes`: one AXES-tuple per port, after the words (session ABI 7)
        if len(axes) != len(words) or any(len(port) != AXES for port in axes):
            raise ValueError('one set of sticks per port')
        payload = payload[:4] + bytes([flags | RUN_AXES]) + payload[5:] + struct.pack(
            f'<{AXES * len(words)}b', *(max(-127, min(127, value)) for port in axes for value in port))
    return frame(MSG_RUN, payload)


def save(frame_number: int) -> bytes:
    """A snapshot of the state before `frame_number` runs, into the game's own ring (rollback tier)."""
    return frame(MSG_SAVE, struct.pack('<I', frame_number))


def load(frame_number: int) -> bytes:
    """Back to the snapshot taken before `frame_number`; the frames from it on are then run again."""
    return frame(MSG_LOAD, struct.pack('<I', frame_number))


def digest() -> bytes:
    return frame(MSG_DIGEST)


def pause(on: bool, name: str = '') -> bytes:
    text = clean_name(name) if on else b''
    return frame(MSG_PAUSE, bytes([1 if on else 0, len(text)]) + text)


def notice(code: int, name: str = '') -> bytes:
    text = clean_name(name) if name else b''
    return frame(MSG_NOTICE, struct.pack('<HB', code, len(text)) + text)


def chat_show(phrase: int, name: str, text: str = '') -> bytes:
    """A line of the room for this game: a phrase by its number, or free text already made ASCII by the lobby (`ascii_chat`),
    kept printable and at most CHAT_MAX_TEXT here too; the sender's name as `clean_name` makes it."""
    if not 0 <= phrase <= PHRASE_COUNT:
        raise ValueError('a phrase of 0 to PHRASE_COUNT')
    name_bytes = clean_name(name)[:CHAT_MAX_NAME]
    body = b'' if phrase else (bytes(b for b in text.encode('ascii', 'replace') if 32 <= b < 127)[:CHAT_MAX_TEXT] or b'?')
    return frame(MSG_CHAT_SHOW, bytes([phrase, len(name_bytes)]) + name_bytes + bytes([len(body)]) + body)


def pace(ppm: int) -> bytes:
    return frame(MSG_PACE, struct.pack('<i', max(-PACE_LIMIT, min(PACE_LIMIT, int(ppm)))))


def stop(reason: int) -> bytes:
    return frame(MSG_STOP, struct.pack('<H', reason))
