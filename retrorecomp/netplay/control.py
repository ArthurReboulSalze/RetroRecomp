"""The room's control stream (TCP, after the handshake): framed, tagged messages, and the display names. Pure.

    length u16 (payload only, <= 1024) | type u8 | payload | tag 16
    tag = mac(K_tcp_dir, seq u64, length u16, type u8, payload)      seq counts from 0 per direction and is never sent

A wrong tag, a length above the limit, an unknown or unexpected type, a payload of the wrong size for its type or
bytes left over: `FrameError`, and the transport closes the connection with no detail to the peer. The reader keeps
at most 2,048 bytes. Every message is of a fixed size or has each variable field length-prefixed and bounded, and
`decode` accepts only the canonical form: a message that decodes encodes back to the same bytes (the fuzz test holds it).

The lobby (types 10 to 17; `lobby.py` holds its rules) rides the same stream and has its own version, `LOBBY_VERSION`, in
the host's ROSTER: a host of another lobby version is a stream that breaks the rules and the guest leaves. Host to guests:
ROSTER (the seats in order, the host first), CHAT (already stamped with the sender's name), SELECT (the game the host chose,
with what a guest compares), NOTICE (one short code, to one guest), BACK (the match is over, everybody is in the lobby again).
Guest to host: SAY (a line of chat), READY, ANSWER (what the guest's own library says about the host's pick).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import re
import struct
import unicodedata

from .handshake import mac

MAX_PAYLOAD = 1024
READ_BUFFER = 2048
WELCOME, REJECT, HELLO, LAUNCH, LAUNCHED, END, PING, PONG, BYE = range(1, 10)
ROSTER, CHAT, SELECT, NOTICE, BACK, SAY, READY, ANSWER = range(10, 18)
LOBBY_VERSION = 3                           # 2: the LAUNCH carries the tier byte (the rollback cap); 3: a chat line may be a phrase
MAX_PHRASE = 6                              # the in-game chat's ready-made phrases (session_pipe.PHRASES), sent by number
PHASE_LOBBY, PHASE_LAUNCHING, PHASE_PLAYING = 0, 1, 2
LOBBY_PHASES = range(3)
CHECK_NONE, CHECK_ASKING, CHECK_SAME, CHECK_OTHER, CHECK_MISSING, CHECK_FAILED = range(6)
ANSWER_STATUSES = (CHECK_SAME, CHECK_OTHER, CHECK_MISSING, CHECK_FAILED)
SHARINGS = (0, 1, 2)                        # seat_map.SHARINGS: one controller per player, input sharing "everyone", "turns"
MODE_PORTABLE, MODE_FULL = 0, 1             # what a guest compares: the identity without the learned paths, or the full one
NOTICE_CHAT_FAST, NOTICE_BAD_TEXT, NOTICE_BUSY = 1, 2, 3
NOTICES = range(1, 4)
BACK_REASONS = range(1, 12)                 # lobby.BACK_CODES: why a match ended, as the host saw it
MAX_CHAT_CHARS = 80
MAX_CHAT_BYTES = 320
MAX_TITLE_BYTES = 96
MAX_REASONS = 0x7f                          # the check's reason bits (lobby_check)
REJECT_FULL, REJECT_VERSION, REJECT_BUSY, REJECT_KICKED = 1, 2, 3, 4
LAUNCHED_READY, LAUNCHED_NOT_OWNED, LAUNCHED_OTHER_STAMP, LAUNCHED_FAILED = 0, 1, 2, 3
BYE_REASONS = range(1, 5)       # the control BYE: 1 left, 2 room closed, 3 kicked, 4 error
MAX_NAME_BYTES = 48
MAX_NAME_CHARS = 16
MAX_SEATS = 4
MAX_OPTIONS = 512
MAX_ROLLBACK = 8                            # the tier byte of a LAUNCH: 0 the delay tier, 1 to 8 the rollback tier with that prediction cap
MAX_MACHINE = 16
_MACHINE = re.compile(r'[A-Za-z0-9_.+-]{1,16}')
_FROM_GUEST = frozenset((HELLO, LAUNCHED, END, PING, PONG, BYE, SAY, READY, ANSWER))
_FROM_HOST = frozenset((WELCOME, REJECT, LAUNCH, END, PING, PONG, BYE, ROSTER, CHAT, SELECT, NOTICE, BACK))
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
    sharing: int = 0                # the input mode of the match (`seat_map`): one controller per player, everyone, turns
    rollback: int = 0               # the tier byte: 0 the delay tier, 1 to MAX_ROLLBACK the rollback tier with that prediction cap


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


@dataclass(frozen=True)
class Player:
    """One seat of the roster, in seat order (the index is the seat; the host is seat 0, guest 0)."""
    guest: int
    name: str
    ready: bool = False
    in_match: bool = False
    check: int = CHECK_NONE


@dataclass(frozen=True)
class Roster:
    revision: int                   # counts the changes the host made (16 bits, wraps)
    phase: int
    seats_max: int                  # the players the chosen game takes (0 when no game is chosen)
    selection: int                  # the number of the host's current pick (0: none)
    players: tuple
    sharing: int = 0                # the input mode the room is set to (`seat_map`), as the host's pick makes it effective


@dataclass(frozen=True)
class Chat:
    sender: int                     # 0 the host, 1.. a guest
    name: str                       # stamped by the host
    text: str                       # '' for a phrase
    phrase: int = 0                 # 1..MAX_PHRASE: a ready-made phrase, each player reads it in their language


@dataclass(frozen=True)
class Game:
    """The host's pick as a guest compares it with its own library (`lobby_check`). Digests are 32 bytes, 32 zero bytes
    meaning "none". `mode` says what is compared: the identity without the learned paths (PORTABLE, for a machine whose
    mixed-build gate passed) or the full simulation identity (FULL: `sources` is compared as well)."""
    mode: int
    schema: int
    seats_max: int
    machine: str
    converter: tuple
    rom: bytes
    engine: bytes
    options: bytes
    sources: bytes
    firmware: bytes
    title: str
    game_options: str = ''

    def digest(self) -> bytes:
        """The identity the LAUNCH carries as its stamp: what is compared in this mode, never the title or the options the
        host pushes (they have their own field)."""
        parts = [str(self.mode).encode(), str(self.schema).encode(), self.machine.encode('ascii'),
                 '.'.join(str(number) for number in self.converter).encode(), self.rom, self.engine, self.options, self.firmware]
        if self.mode == MODE_FULL:
            parts.append(self.sources)
        value = hashlib.sha256(b'retro-recomp-lobby-game\0')
        for part in parts:
            value.update(len(part).to_bytes(2, 'little') + part)
        return value.digest()


@dataclass(frozen=True)
class Select:
    ident: int                      # the number of this pick (16 bits, from 1): an answer names it, an old answer is ignored
    game: Game | None               # None: the host chose nothing (any more)


@dataclass(frozen=True)
class Notice:
    code: int


@dataclass(frozen=True)
class Back:
    match_id: int
    reason: int


@dataclass(frozen=True)
class Say:
    text: str                       # '' for a phrase
    phrase: int = 0


@dataclass(frozen=True)
class Ready:
    ready: bool


@dataclass(frozen=True)
class Answer:
    selection: int
    status: int
    reasons: int
    version: tuple                  # the converter version of the guest's own export (0.0.0 when it has none)


def _text_field(text: str, limit: int, what: str) -> bytes:
    raw = text.encode('utf-8')
    if not 0 < len(raw) <= limit:
        raise ValueError(f'{what} outside the rules')
    return raw


def _line(text: str, phrase: int) -> bytes:
    """A chat line on the wire: u8 phrase, then the text (u16 size, UTF-8) only when the phrase is 0."""
    if not 0 <= phrase <= MAX_PHRASE or (phrase and text):
        raise ValueError('a chat line outside the rules')
    if phrase:
        return struct.pack('<B', phrase)
    raw = _text_field(text, MAX_CHAT_BYTES, 'a line')
    return struct.pack('<BH', 0, len(raw)) + raw


def _read_line(cursor) -> tuple[str, int]:
    phrase = cursor.unpack('<B')
    if phrase > MAX_PHRASE:
        raise FrameError('a phrase the rules do not allow')
    return ('' if phrase else cursor.text('<H', MAX_CHAT_BYTES)), phrase


def _encode_lobby(message) -> tuple[int, bytes]:
    if isinstance(message, Roster):
        if not (message.phase in LOBBY_PHASES and 0 <= message.seats_max <= MAX_SEATS and 0 <= message.selection <= 0xffff
                and 0 <= message.revision <= 0xffff and 1 <= len(message.players) <= MAX_SEATS and message.sharing in SHARINGS):
            raise ValueError('a roster outside the rules')
        body = b''
        for player in message.players:
            raw = _text_field(player.name, MAX_NAME_BYTES, 'a name')
            body += struct.pack('<BBBBB', player.guest, int(player.ready), int(player.in_match), player.check, len(raw)) + raw
        return ROSTER, struct.pack('<BHBBBHB', LOBBY_VERSION, message.revision, message.phase, message.seats_max, message.sharing,
                                   message.selection, len(message.players)) + body
    if isinstance(message, Chat):
        name = _text_field(message.name, MAX_NAME_BYTES, 'a name')
        return CHAT, struct.pack('<BB', message.sender, len(name)) + name + _line(message.text, message.phrase)
    if isinstance(message, Select):
        game = message.game
        if not 0 < message.ident <= 0xffff:
            raise ValueError('a selection number outside the rules')
        if game is None:
            return SELECT, struct.pack('<HB', message.ident, 0)
        if (not _MACHINE.fullmatch(game.machine) or game.mode not in (MODE_PORTABLE, MODE_FULL) or not 0 <= game.seats_max <= MAX_SEATS
                or not 0 <= game.schema <= 255 or len(game.converter) != 3 or not all(0 <= number <= 0xffff for number in game.converter)
                or any(len(digest) != 32 for digest in (game.rom, game.engine, game.options, game.sources, game.firmware))
                or len(game.game_options) > MAX_OPTIONS or not game.game_options.isascii()):
            raise ValueError('a game outside the rules')
        title, machine = _text_field(game.title, MAX_TITLE_BYTES, 'a title'), game.machine.encode('ascii')
        options = game.game_options.encode('ascii')
        return SELECT, b''.join((struct.pack('<HBBBB', message.ident, 1, game.mode, game.schema, game.seats_max),
                                 struct.pack('<B', len(machine)), machine, struct.pack('<3H', *game.converter),
                                 game.rom, game.engine, game.options, game.sources, game.firmware,
                                 struct.pack('<B', len(title)), title, struct.pack('<H', len(options)), options))
    if isinstance(message, Notice):
        return NOTICE, struct.pack('<B', message.code)
    if isinstance(message, Back):
        return BACK, struct.pack('<IB', message.match_id, message.reason)
    if isinstance(message, Say):
        return SAY, _line(message.text, message.phrase)
    if isinstance(message, Ready):
        return READY, struct.pack('<B', int(bool(message.ready)))
    if not (0 <= message.reasons <= MAX_REASONS and len(message.version) == 3 and all(0 <= number <= 0xffff for number in message.version)
            and 0 < message.selection <= 0xffff):
        raise ValueError('an answer outside the rules')
    return ANSWER, struct.pack('<HBB3H', message.selection, message.status, message.reasons, *message.version)


def valid_tier_byte(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_ROLLBACK


def encode(message) -> tuple[int, bytes]:
    """(type, payload) of a message."""
    if isinstance(message, (Roster, Chat, Select, Notice, Back, Say, Ready, Answer)):
        return _encode_lobby(message)
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
                or message.sharing not in SHARINGS or not valid_tier_byte(message.rollback)
                or len(message.stamp) != 32 or len(message.rom_sha) != 32 or not message.options.isascii()
                or any(not 0 < len(name.encode('utf-8')) <= MAX_NAME_BYTES for name in message.names)):
            raise ValueError('a launch outside the rules')
        machine = message.machine.encode('ascii')
        names = b''.join(struct.pack('<B', len(raw)) + raw for raw in (name.encode('utf-8') for name in message.names))
        options = message.options.encode('ascii')
        return LAUNCH, b''.join((struct.pack('<IBBBHBBB', message.match_id, message.seat, message.seats, message.delay,
                                             message.digest_every, message.redundancy, message.sharing, message.rollback),
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
    elif ROSTER <= kind <= ANSWER:
        return _decode_lobby(kind, payload)
    raise FrameError('a message the rules do not allow')


BYE_REASONS_WIRE = range(1, 7)       # the datagram BYE reasons (input_records.BYE_*): an END carries one of them


def _flag(value: int) -> bool:
    if value > 1:
        raise FrameError('a flag that is neither 0 nor 1')
    return bool(value)


class _Cursor:
    """Bounded reading of a payload: a field that goes past the end is a `FrameError`, and `done` demands that nothing is left."""

    def __init__(self, payload: bytes):
        self.payload, self.offset = payload, 0

    def take(self, size: int) -> bytes:
        raw = self.payload[self.offset:self.offset + size]
        if len(raw) != size:
            raise FrameError('a message cut short')
        self.offset += size
        return raw

    def unpack(self, form: str):
        values = struct.unpack(form, self.take(struct.calcsize(form)))
        return values if len(values) > 1 else values[0]

    def text(self, size_form: str, limit: int) -> str:
        size = self.unpack(size_form)
        if not 0 < size <= limit:
            raise FrameError('a text field of the wrong size')
        try:
            return self.take(size).decode('utf-8')
        except UnicodeDecodeError:
            raise FrameError('a text field that is not UTF-8') from None

    def done(self) -> None:
        if self.offset != len(self.payload):
            raise FrameError('bytes left over')


def _decode_lobby(kind: int, payload: bytes):
    cursor = _Cursor(payload)
    if kind == ROSTER:
        version, revision, phase, seats_max, sharing, selection, count = cursor.unpack('<BHBBBHB')
        if (version != LOBBY_VERSION or phase not in LOBBY_PHASES or seats_max > MAX_SEATS or sharing not in SHARINGS
                or not 1 <= count <= MAX_SEATS):
            raise FrameError('a roster the rules do not allow')
        players = []
        for _ in range(count):
            guest, ready, in_match, check = cursor.unpack('<BBBB')
            if guest >= MAX_SEATS or check > CHECK_FAILED:
                raise FrameError('a seat the rules do not allow')
            players.append(Player(guest, cursor.text('<B', MAX_NAME_BYTES), _flag(ready), _flag(in_match), check))
        cursor.done()
        return Roster(revision, phase, seats_max, selection, tuple(players), sharing)
    if kind == CHAT:
        sender, name_size = cursor.unpack('<BB')
        if sender >= MAX_SEATS or not 0 < name_size <= MAX_NAME_BYTES:
            raise FrameError('a chat line the rules do not allow')
        name = _decode_name(cursor.take(name_size))
        text, phrase = _read_line(cursor)
        cursor.done()
        return Chat(sender, name, text, phrase)
    if kind == SELECT:
        ident, present = cursor.unpack('<HB')
        if ident == 0 or present > 1:
            raise FrameError('a selection the rules do not allow')
        if not present:
            cursor.done()
            return Select(ident, None)
        mode, schema, seats_max, length = cursor.unpack('<BBBB')
        if mode not in (MODE_PORTABLE, MODE_FULL) or seats_max > MAX_SEATS or not 0 < length <= MAX_MACHINE:
            raise FrameError('a game the rules do not allow')
        try:
            machine = cursor.take(length).decode('ascii')
        except UnicodeDecodeError:
            raise FrameError('a machine id that is not ASCII') from None
        if not _MACHINE.fullmatch(machine):
            raise FrameError('a machine id that is not plain')
        converter = tuple(cursor.unpack('<3H'))
        digests = [cursor.take(32) for _ in range(5)]
        title = cursor.text('<B', MAX_TITLE_BYTES)
        options_size = cursor.unpack('<H')
        if options_size > MAX_OPTIONS:
            raise FrameError('options of the wrong size')
        try:
            options = cursor.take(options_size).decode('ascii')
        except UnicodeDecodeError:
            raise FrameError('options that are not ASCII') from None
        cursor.done()
        return Select(ident, Game(mode, schema, seats_max, machine, converter, *digests, title, options))
    if kind == NOTICE:
        code = cursor.unpack('<B')
        cursor.done()
        if code in NOTICES:
            return Notice(code)
    elif kind == BACK:
        match_id, reason = cursor.unpack('<IB')
        cursor.done()
        if reason in BACK_REASONS:
            return Back(match_id, reason)
    elif kind == SAY:
        text, phrase = _read_line(cursor)
        cursor.done()
        return Say(text, phrase)
    elif kind == READY:
        ready = _flag(cursor.unpack('<B'))
        cursor.done()
        return Ready(ready)
    elif kind == ANSWER:
        selection, status, reasons, *version = cursor.unpack('<HBB3H')
        cursor.done()
        if status in ANSWER_STATUSES and reasons <= MAX_REASONS and selection > 0:
            return Answer(selection, status, reasons, tuple(version))
    raise FrameError('a message the rules do not allow')


def _decode_launch(payload: bytes) -> Launch:
    match_id, seat, seats, delay, digest_every, redundancy, sharing, rollback = struct.unpack_from('<IBBBHBBB', payload)
    offset = 12
    if sharing not in SHARINGS:
        raise FrameError('a launch with an input mode that does not exist')
    if rollback > MAX_ROLLBACK:
        raise FrameError('a launch with a prediction cap beyond the bound')
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
    return Launch(match_id, seat, seats, delay, digest_every, redundancy, machine, stamp, rom_sha, tuple(names), options, sharing, rollback)


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
