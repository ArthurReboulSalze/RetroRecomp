"""The multiplayer lobby's rules (no socket, no window, no clock of its own): who sits where, who is ready, what the host chose,
what each guest's library answered, the chat, and when a match starts and ends. Pure.

Two state machines, one for the host (`HostLobby`, the authority) and one for each guest (`GuestLobby`, which only follows).
Neither touches the network: they take what arrived (a decoded `control` message, or a call of the converter's window) and the
time the caller gives, and return what is to be done as a list of `Send` (a control message for one guest, or for all of them
from the host; to the host from a guest) and `Event` (a dict for the converter's window: `EVENTS` below). The transport
(`lan_transport`) carries the messages and hands the events to the worker, which sends them to the converter.

The host's rules, each held by a test:

* the seats are an order: the host is seat 0 and stays there (the driver's seat 0 is the host's game); the host moves the
  guests among the others; the game takes `seats_max` players (up to four in input sharing, whose seats all drive the same
  controls), the guests beyond them stay in the lobby;
* the input mode (`seat_map`: one controller per player, "everyone" or "turns") is the host's choice, made when the room is
  created and changeable in the lobby only; a handheld game (profile `netplay_shared_only`) is played in input sharing whatever was
  chosen, and the roster and the launch carry the mode that is in force;
* the chat: a line is strict UTF-8 (the wire checks it), NFC, control, format, surrogate, private-use and unassigned
  characters removed, white space made one space, at most 80 characters; at most 5 lines in any 5 seconds from one sender, the
  host's own lines included; the host stamps the sender's name, a guest never says it; `ascii_chat` is the copy a game can
  draw (the rule of `tools/build_languages.py ascii_text`, never an assertion: a character it cannot fold becomes `?`);
* a ready flag changes at most 4 times in 2 seconds and only in the lobby;
* a pick (`select`) numbers itself (1.. in 16 bits); a guest's answer names the number it answers, and an answer to another
  number is ignored; a pick resets every ready flag and asks every guest again; a check not answered for `CHECK_WAIT` seconds
  is a failed one ("no answer");
* the options the host pushes for the game are validated with `launch.clean_options` (the rule of every launch) and applied to
  everyone's launch: they are the launch's options, the guests cannot change them;
* a launch takes the guests who answered "same game" (and, if the host asks for it, are ready), in seat order, up to the
  game's seats; the others stay in the lobby with the chat. A match that ends for any reason brings everyone back to the
  lobby (BACK), ready flags cleared, the pick kept: the host may start it again or pick another game, which re-runs the check;
* the roster goes out when it changed, at most ten times a second, so that a guest cannot make the room write to the others
  faster than the control stream's own limit (20 frames a second to a peer).

What the lobby does not do: pause, desync and the events of the game stay the driver's. A lobby message never reaches the
driver and the driver never reaches the lobby; the worker holds both.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
import unicodedata

from . import control
from . import seat_map
from .control import (CHECK_ASKING, CHECK_FAILED, CHECK_NONE, CHECK_SAME, MODE_FULL, PHASE_LAUNCHING, PHASE_LOBBY, PHASE_PLAYING,
                      MAX_CHAT_CHARS)
from .launch import Refusal, clean_options
from .session_pipe import PHRASES

CHAT_LINES, CHAT_SECONDS = 5, 5.0          # at most this many lines from one sender in any window of this many seconds
READY_CHANGES, READY_SECONDS = 4, 2.0
CHECK_WAIT = 15.0                          # seconds a guest has to answer the host's pick
ROSTER_EVERY = 0.1                         # the roster goes out at most this often
NOTICE_EVERY = 0.5                         # a guest is told "no" at most this often (a flood of refused lines costs it nothing)
MIN_PLAYERS = 2
PHASE_NAMES = {PHASE_LOBBY: 'lobby', PHASE_LAUNCHING: 'launching', PHASE_PLAYING: 'playing'}
CHECK_NAMES = {CHECK_NONE: 'none', CHECK_ASKING: 'asking', CHECK_SAME: 'same', control.CHECK_OTHER: 'other',
               control.CHECK_MISSING: 'missing', CHECK_FAILED: 'failed'}
NOTICE_NAMES = {control.NOTICE_CHAT_FAST: 'chat_too_fast', control.NOTICE_BAD_TEXT: 'bad_text', control.NOTICE_BUSY: 'busy'}
# Why a match ended, as the host saw it (the driver's outcomes, `lockstep.py`), as the number BACK carries.
BACK_NAMES = {1: 'ended', 2: 'game_closed', 3: 'pipe_lost', 4: 'left', 5: 'seat_left', 6: 'seat_silent', 7: 'host_closed',
              8: 'desync', 9: 'boot_mismatch', 10: 'error', 11: 'launch_failed',
              12: 'relaunch'}         # the host changed an option in the match: it starts again at once (session ABI 9)
BACK_CODES = {name: code for code, name in BACK_NAMES.items()} | {'refused': 10}

_REMOVED = control._REMOVED
_PUNCTUATION = str.maketrans({'«': '"', '»': '"', '“': '"', '”': '"', '‘': "'", '’': "'", '–': '-', '—': '-', '…': '...',
                              ' ': ' ', ' ': ' '})
_FOLDED = str.maketrans({'ß': 'ss', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ø': 'o', 'Ø': 'O', 'ł': 'l', 'Ł': 'L',
                         'đ': 'd', 'Đ': 'D'})


# ---- the chat's text ----

def clean_chat(raw, max_chars: int = MAX_CHAT_CHARS) -> str:
    """A line of chat as everyone sees it: NFC, control, format, surrogate, private-use and unassigned characters removed,
    white-space runs made one space, trimmed, at most `max_chars` characters. Bytes must be strict UTF-8 (else ''). A line
    with nothing left is ''."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw[:control.MAX_CHAT_BYTES * 2]).decode('utf-8')
        except UnicodeDecodeError:
            return ''
    else:
        text = str(raw)[:control.MAX_CHAT_BYTES * 2]
    text = unicodedata.normalize('NFC', text)
    spaced = ''.join(' ' if char.isspace() else char for char in text)
    kept = ''.join(char for char in spaced if unicodedata.category(char) not in _REMOVED)
    line = ' '.join(kept.split())[:max_chars].rstrip()
    while len(line.encode('utf-8')) > control.MAX_CHAT_BYTES:
        line = line[:-1].rstrip()
    return line


def ascii_chat(text: str) -> str:
    """The copy of a line that a game can draw: accents dropped, typographic punctuation made plain, the usual ligatures and
    barred letters folded, and `?` for anything else. The rule of `tools/build_languages.py ascii_text` without its assertion."""
    folded = unicodedata.normalize('NFKD', text.translate(_PUNCTUATION).translate(_FOLDED))
    return ''.join(char if char.isascii() else '?' for char in folded if not unicodedata.combining(char))


class SlidingLimit:
    """At most `count` events in any window of `seconds` on the clock the caller gives; memory: `count` times."""

    def __init__(self, count: int, seconds: float):
        self.count, self.seconds = count, seconds
        self._times: deque = deque(maxlen=count)

    def take(self, now: float) -> bool:
        if len(self._times) == self.count and now - self._times[0] < self.seconds:
            return False
        self._times.append(now)
        return True


# ---- what the lobby asks to be done ----

@dataclass(frozen=True)
class Send:
    """A control message. From the host: `to` is a guest id, or None for every guest in the room. From a guest: for the host."""
    to: int | None
    message: object


@dataclass(frozen=True)
class Event:
    """A dict for the converter's window. The names and fields are `EVENTS`."""
    data: dict


EVENTS = {
    'lobby_roster': 'revision, phase, seats_max, sharing (per_player / everyone / turns), selection, players [seat, guest, name, ready, in_match, check], me (a guest: its own guest id)',
    'lobby_selection': 'selection (the number), game (see game_dict) or None',
    'lobby_check_request': 'a guest: selection, game: this PC must look in its own library and answer (call lobby_answer)',
    'lobby_check': 'the host: guest, name, selection, status, reasons, version, text (the English line for a log)',
    'lobby_chat': 'sender, name, text, ascii',
    'lobby_notice': 'code (a name of NOTICE_NAMES), detail',
    'lobby_launch': 'the host: match_id, seats, names, left_out [guest, name, reason], sharing',
    'lobby_back': 'match_id, reason (a name of BACK_NAMES)',
}


def game_dict(game: control.Game | None) -> dict | None:
    """The host's pick as an event shows it: digests in hex ('' for none), the mode and the stamp a launch will carry."""
    if game is None:
        return None
    zero = bytes(32)
    return {'machine': game.machine, 'mode': 'full' if game.mode == MODE_FULL else 'portable', 'schema': game.schema,
            'seats_max': game.seats_max, 'converter': list(game.converter), 'rom': game.rom.hex(), 'engine': game.engine.hex(),
            'options': game.options.hex(), 'sources': '' if game.sources == zero else game.sources.hex(),
            'firmware': '' if game.firmware == zero else game.firmware.hex(), 'title': game.title,
            'game_options': game.game_options, 'digest': game.digest().hex()}


def game_from_dict(data) -> control.Game:
    """The inverse of `game_dict`: the pick the host's window gives the worker. Raises ValueError for anything out of the rules."""
    if not isinstance(data, dict):
        raise ValueError('a game is a record')

    def digest(name: str, optional: bool = False) -> bytes:
        value = data.get(name, '')
        if optional and value in ('', None):
            return bytes(32)
        if not isinstance(value, str) or len(value) != 64:
            raise ValueError(f'{name} is not a SHA-256')
        return bytes.fromhex(value)
    mode = {'portable': control.MODE_PORTABLE, 'full': MODE_FULL}.get(data.get('mode'))
    converter = data.get('converter')
    if mode is None or not isinstance(converter, (list, tuple)) or len(converter) != 3:
        raise ValueError('the mode or the converter version is not what it should be')
    ints = [data.get('schema'), data.get('seats_max'), *converter]
    if not all(isinstance(number, int) and not isinstance(number, bool) for number in ints):
        raise ValueError('a number is not a number')
    machine, title, options = data.get('machine'), data.get('title'), data.get('game_options', '')
    if not all(isinstance(text, str) for text in (machine, title, options)):
        raise ValueError('a text is not text')
    game = control.Game(mode, data['schema'], data['seats_max'], machine, tuple(converter), digest('rom'), digest('engine'),
                        digest('options'), digest('sources', True), digest('firmware', True), title, options)
    control.encode(control.Select(1, game))         # the wire's own rules, so that nothing the wire would refuse is accepted here
    return game


@dataclass(frozen=True)
class LaunchPlan:
    """Who a launch takes (guest ids in seat order, after the host), who stays in the lobby and why, and what is launched."""
    guests: tuple
    left_out: tuple                 # ((guest id, name, reason), ...)
    game: control.Game
    stamp: bytes
    rom: bytes
    options: str
    sharing: int = seat_map.PER_PLAYER      # the input mode in force when the plan was made


class _Member:
    def __init__(self, name: str, now: float):
        self.name = name
        self.ready = False
        self.check = CHECK_NONE
        self.reasons = 0
        self.version = (0, 0, 0)
        self.asked_at = now
        self.in_match = False
        self.chat = SlidingLimit(CHAT_LINES, CHAT_SECONDS)
        self.changes = SlidingLimit(READY_CHANGES, READY_SECONDS)
        self.noticed_at = -1e9


def check_text(game: control.Game | None, status: int, reasons: int = 0, version=(0, 0, 0)) -> str:
    """The English line of one player's check, for logs and tests (the window words it itself, from the fields)."""
    if status == control.CHECK_SAME:
        return 'same game'
    if status == control.CHECK_OTHER:
        from .lobby_check import reason_names
        return f'same game, other version (reconvert: {", ".join(reason_names(reasons)) or "unknown"})'
    if status == control.CHECK_MISSING:
        title = game.title if game is not None else '?'
        return f'not found (needs {title}, SHA-256 {game.rom.hex() if game is not None else "?"})'
    return {CHECK_ASKING: 'asking', CHECK_NONE: 'no game chosen'}.get(status, 'could not check')


class HostLobby:
    """The host's lobby. `name` is the host's own display name; guests are named by the transport (cleaned, unique)."""

    def __init__(self, name: str, capacity: int = 4, sharing: int = seat_map.PER_PLAYER):
        if not seat_map.valid(sharing):
            raise ValueError('an input mode that does not exist')
        self.name, self.capacity = name, capacity
        self.chosen = sharing              # the host's own choice of input mode; `sharing` is the one in force for the pick
        self.phase = PHASE_LOBBY
        self.game: control.Game | None = None
        self.ident = 0                     # the number of the current pick (0: none yet)
        self.revision = 0
        self.match_id = 0
        self._members: dict[int, _Member] = {}
        self._order: list[int] = []        # guest ids in seat order, seat 1 first
        self._host = _Member(name, 0.0)
        self._host.check = CHECK_SAME
        self._dirty = False
        self._last_roster = -1e9
        self._ignored = 0                  # messages dropped for being stale or out of place (a counter, never a log line per message)

    # ---- the picture of the lobby ----

    @property
    def sharing(self) -> int:
        """The input mode in force: the host's choice, or input sharing when the picked game is a handheld's."""
        return seat_map.effective(self.game.machine if self.game is not None else None, self.chosen)

    def seat_limit(self) -> int:
        """The seats the picked game takes in the mode in force (0 when nothing is picked)."""
        return seat_map.seat_limit(self.game.seats_max, self.sharing) if self.game is not None else 0

    def set_sharing(self, sharing: int) -> Refusal | None:
        """The host's choice of input mode. Only in the lobby; nobody has to answer again (the mode is not part of the game)."""
        if self.phase != PHASE_LOBBY:
            return Refusal('the input mode cannot change while a match is starting or running')
        if not seat_map.valid(sharing):
            return Refusal('an input mode that does not exist')
        if not seat_map.allowed(self.game.machine if self.game is not None else None, sharing):
            return Refusal('this game plays in input sharing only')
        if sharing != self.chosen:
            self.chosen = sharing
            self._touch()
        return None

    def guests(self) -> list[int]:
        return list(self._order)

    def has(self, guest: int) -> bool:
        return guest in self._members

    def roster(self) -> control.Roster:
        playing = self.phase != PHASE_LOBBY
        players = [control.Player(0, self.name, True, playing, CHECK_SAME if self.game is not None else CHECK_NONE)]
        players += [control.Player(guest, member.name, member.ready, member.in_match, member.check)
                    for guest, member in ((guest, self._members[guest]) for guest in self._order)]
        return control.Roster(self.revision, self.phase, self.seat_limit(), self.ident, tuple(players), self.sharing)

    def select_message(self) -> control.Select | None:
        return control.Select(self.ident, self.game) if self.ident else None

    def roster_event(self, me: int | None = None) -> Event:
        return Event(roster_dict(self.roster(), me))

    def _touch(self) -> None:
        self.revision = (self.revision + 1) & 0xffff
        self._dirty = True

    def _notice(self, guest: int, code: int, now: float) -> list:
        member = self._members.get(guest)
        if member is None or now - member.noticed_at < NOTICE_EVERY:
            self._ignored += 1
            return []
        member.noticed_at = now
        return [Send(guest, control.Notice(code))]

    # ---- the room's comings and goings ----

    def joined(self, guest: int, name: str, now: float) -> list:
        """A guest said HELLO: it gets the roster and the pick at once, the others in the next roster."""
        if guest in self._members or len(self._order) + 1 >= self.capacity:
            return []
        member = self._members[guest] = _Member(name, now)
        member.check = CHECK_ASKING if self.game is not None else CHECK_NONE
        self._order.append(guest)
        self._touch()
        actions = [Send(guest, self.roster())]
        if self.game is not None:
            actions.append(Send(guest, self.select_message()))
        return actions

    def left(self, guest: int) -> list:
        if guest not in self._members:
            return []
        del self._members[guest]
        self._order.remove(guest)
        self._touch()
        return []

    def move(self, guest: int, seat: int) -> Refusal | None:
        """The host puts a guest at `seat` (1 is the first after the host). Only in the lobby."""
        if self.phase != PHASE_LOBBY:
            return Refusal('seats cannot change while a match is starting or running')
        if guest not in self._members or not 1 <= seat <= len(self._order):
            return Refusal('a seat the room does not have')
        self._order.remove(guest)
        self._order.insert(seat - 1, guest)
        self._touch()
        return None

    # ---- the pick ----

    def select(self, game: control.Game | None, now: float) -> tuple[list, Refusal | None]:
        """The host picks a game (None: none). Everyone is asked again, ready flags are cleared."""
        if self.phase != PHASE_LOBBY:
            return [], Refusal('the game cannot change while a match is starting or running')
        if game is not None:
            if game.seats_max < MIN_PLAYERS and not seat_map.forced(game.machine):
                return [], Refusal('this game has no second player')
            options = clean_options(game.game_options)
            if isinstance(options, Refusal) or options != game.game_options:
                return [], Refusal('the options of the game are not of the plain form')
        self.game = game
        self.ident = self.ident % 0xffff + 1
        for member in self._members.values():
            member.ready = False
            member.check = CHECK_ASKING if game is not None else CHECK_NONE
            member.reasons, member.version, member.asked_at = 0, (0, 0, 0), now
        self._touch()
        return [Send(None, control.Select(self.ident, game)),
                Event({'event': 'lobby_selection', 'selection': self.ident, 'game': game_dict(game)})], None

    # ---- what the guests say ----

    def on_message(self, guest: int, message, now: float) -> list:
        member = self._members.get(guest)
        if member is None:
            return []
        if isinstance(message, control.Say):
            return self.say(guest, message.text, now, message.phrase)
        if isinstance(message, control.Ready):
            return self._ready(guest, member, message.ready, now)
        if isinstance(message, control.Answer):
            return self._answer(guest, member, message, now)
        self._ignored += 1
        return []

    def say(self, sender: int, raw, now: float, phrase: int = 0) -> list:
        """A line of chat from a guest, or from the host (sender 0): free text, or a ready-made phrase by its number (from a
        game's chat). Cleaned, limited (a phrase counts as a line), stamped with the sender's name."""
        member = self._host if sender == 0 else self._members.get(sender)
        if member is None:
            return []
        if not isinstance(phrase, int) or not 0 <= phrase <= control.MAX_PHRASE:
            phrase = -1
        text = '' if phrase > 0 else clean_chat(raw) if phrase == 0 else ''
        if not text and phrase <= 0:
            return self._notice(sender, control.NOTICE_BAD_TEXT, now) if sender else [self._own_notice('bad_text')]
        if not member.chat.take(now):
            return self._notice(sender, control.NOTICE_CHAT_FAST, now) if sender else [self._own_notice('chat_too_fast')]
        shown = PHRASES.get(phrase, text)
        return [Send(None, control.Chat(sender, member.name, text, phrase)),
                Event({'event': 'lobby_chat', 'sender': sender, 'name': member.name, 'text': shown, 'ascii': ascii_chat(shown),
                       'phrase': phrase})]

    @staticmethod
    def _own_notice(name: str) -> Event:
        return Event({'event': 'lobby_notice', 'code': name, 'detail': ''})

    def _ready(self, guest: int, member: _Member, ready: bool, now: float) -> list:
        if self.phase != PHASE_LOBBY:
            return self._notice(guest, control.NOTICE_BUSY, now)
        if not member.changes.take(now):
            self._ignored += 1
            return []
        if member.ready != ready:
            member.ready = ready
            self._touch()
        return []

    def _answer(self, guest: int, member: _Member, answer: control.Answer, now: float) -> list:
        if self.game is None or answer.selection != self.ident or self.phase != PHASE_LOBBY:
            self._ignored += 1
            return []
        member.check, member.reasons, member.version = answer.status, answer.reasons, answer.version
        self._touch()
        return [Event({'event': 'lobby_check', 'guest': guest, 'name': member.name, 'selection': answer.selection,
                       'status': CHECK_NAMES[answer.status], 'reasons': answer.reasons, 'version': list(answer.version),
                       'text': check_text(self.game, answer.status, answer.reasons, answer.version)})]

    # ---- time ----

    def tick(self, now: float) -> list:
        """Checks that nobody answered, then the roster if it changed."""
        actions: list = []
        if self.game is not None:
            for guest, member in self._members.items():
                if member.check == CHECK_ASKING and now - member.asked_at >= CHECK_WAIT:
                    member.check = CHECK_FAILED
                    self._touch()
                    actions.append(Event({'event': 'lobby_check', 'guest': guest, 'name': member.name, 'selection': self.ident,
                                          'status': 'failed', 'reasons': 0, 'version': [0, 0, 0], 'text': 'no answer'}))
        if self._dirty and now - self._last_roster >= ROSTER_EVERY:
            self._dirty, self._last_roster = False, now
            actions += [Send(None, self.roster()), self.roster_event()]
        return actions

    # ---- launching and ending ----

    def plan_launch(self, need_ready: bool = False) -> LaunchPlan | Refusal:
        """Who a launch would take now. Nothing changes."""
        if self.phase != PHASE_LOBBY:
            return Refusal('a match is already starting or running')
        game = self.game
        if game is None:
            return Refusal('no game is chosen')
        chosen, left_out = [], []
        for guest in self._order:
            member = self._members[guest]
            reason = ('has not answered yet' if member.check == CHECK_ASKING else
                      'does not have the game' if member.check != CHECK_SAME else
                      'is not ready' if need_ready and not member.ready else
                      'the game has no more seats' if len(chosen) + 1 >= self.seat_limit() else None)
            if reason is None:
                chosen.append(guest)
            else:
                left_out.append((guest, member.name, reason))
        if not chosen:
            return Refusal('nobody who has the game is ready' if need_ready else 'nobody has the game')
        return LaunchPlan(tuple(chosen), tuple(left_out), game, game.digest(), game.rom, game.game_options, self.sharing)

    def begin(self, guests, match_id: int) -> list:
        """A launch started (`guests`: the seated guests in order; the host's own game follows): they are in the match."""
        self.phase, self.match_id = PHASE_LAUNCHING, match_id
        for guest, member in self._members.items():
            member.in_match = guest in guests
        self._touch()
        names = [self.name] + [self._members[guest].name for guest in guests]
        left_out = [{'guest': guest, 'name': member.name, 'reason': self._why_left_out(member)}
                    for guest, member in self._members.items() if guest not in guests]
        return [Event({'event': 'lobby_launch', 'match_id': match_id, 'seats': len(names), 'names': names, 'left_out': left_out,
                       'sharing': seat_map.NAMES[self.sharing]})]

    def _why_left_out(self, member: _Member) -> str:
        return CHECK_NAMES[member.check] if member.check != CHECK_SAME else 'not seated'

    def playing(self) -> None:
        if self.phase == PHASE_LAUNCHING:
            self.phase = PHASE_PLAYING
            self._touch()

    def finished(self, match_id: int, reason: str) -> list:
        """The match is over (or the launch failed): everyone is in the lobby again, ready flags cleared, the pick kept."""
        if self.phase == PHASE_LOBBY:
            return []
        self.phase = PHASE_LOBBY
        for member in self._members.values():
            member.in_match, member.ready = False, False
        self._touch()
        code = BACK_CODES.get(reason, BACK_CODES['error'])
        return [Send(None, control.Back(match_id, code)),
                Event({'event': 'lobby_back', 'match_id': match_id, 'reason': BACK_NAMES[code]})]

    # ---- reading ----

    def member_status(self, guest: int) -> dict | None:
        member = self._members.get(guest)
        if member is None:
            return None
        return {'name': member.name, 'ready': member.ready, 'check': CHECK_NAMES[member.check], 'reasons': member.reasons,
                'version': list(member.version), 'in_match': member.in_match}

    @property
    def ignored(self) -> int:
        return self._ignored


def roster_dict(roster: control.Roster, me: int | None = None) -> dict:
    """A roster as an event shows it."""
    data = {'event': 'lobby_roster', 'revision': roster.revision, 'phase': PHASE_NAMES[roster.phase], 'seats_max': roster.seats_max,
            'sharing': seat_map.NAMES[roster.sharing], 'selection': roster.selection,
            'players': [{'seat': seat, 'guest': player.guest, 'name': player.name, 'ready': player.ready, 'in_match': player.in_match,
                         'check': CHECK_NAMES[player.check]} for seat, player in enumerate(roster.players)]}
    if me is not None:
        data['me'] = me
    return data


class GuestLobby:
    """A guest's lobby: it follows the host's roster and pick, says its own lines and its own ready flag, and has its library
    answer the pick (the converter does the looking: `check_request` event, `answer` call)."""

    def __init__(self, name: str):
        self.name = name
        self.me: int | None = None         # this guest's id, from WELCOME
        self.phase = PHASE_LOBBY
        self.revision: int | None = None
        self.ident = 0
        self.game: control.Game | None = None
        self.status = CHECK_NONE           # this PC's own answer to the current pick
        self.rejected = False              # the current pick is one this guest will not look up (its options are not valid)
        self._chat = SlidingLimit(CHAT_LINES, CHAT_SECONDS)
        self._changes = SlidingLimit(READY_CHANGES, READY_SECONDS)
        self.broken = ''                   # set when the host's lobby cannot be followed (the transport leaves the room)

    def on_message(self, message, now: float) -> list:
        if isinstance(message, control.Roster):
            if message.revision == self.revision:
                return []
            self.revision, self.phase = message.revision, message.phase
            # what a window is shown is cleaned here again: a host's names are the host's word
            players = tuple(replace(player, name=control.display_name(player.name, '?')) for player in message.players)
            return [Event(roster_dict(replace(message, players=players), self.me))]
        if isinstance(message, control.Chat):
            text = PHRASES.get(message.phrase) or clean_chat(message.text)
            if not text:
                return []
            return [Event({'event': 'lobby_chat', 'sender': message.sender, 'name': control.display_name(message.name, '?'),
                           'text': text, 'ascii': ascii_chat(text), 'phrase': message.phrase})]
        if isinstance(message, control.Select):
            game = message.game
            self.ident, self.game, self.rejected = message.ident, game, False
            if game is None:
                self.status = CHECK_NONE
                return [Event({'event': 'lobby_selection', 'selection': message.ident, 'game': None})]
            options = clean_options(game.game_options)
            if isinstance(options, Refusal) or options != game.game_options:
                # a pick whose options are not of the plain form is not looked up and not launched: the host is told, once
                self.status, self.rejected = CHECK_FAILED, True
                return [Event({'event': 'lobby_selection', 'selection': message.ident, 'game': None}),
                        Event({'event': 'lobby_notice', 'code': 'bad_pick', 'detail': "the options of the host's game are not valid"}),
                        Send(None, control.Answer(message.ident, CHECK_FAILED, 0, (0, 0, 0)))]
            game = self.game = replace(game, title=clean_chat(game.title, 64) or game.machine)     # the title is the host's word too
            self.status = CHECK_ASKING
            return [Event({'event': 'lobby_selection', 'selection': message.ident, 'game': game_dict(game)}),
                    Event({'event': 'lobby_check_request', 'selection': message.ident, 'game': game_dict(game)})]
        if isinstance(message, control.Notice):
            return [Event({'event': 'lobby_notice', 'code': NOTICE_NAMES[message.code], 'detail': ''})]
        if isinstance(message, control.Back):
            self.phase = PHASE_LOBBY
            return [Event({'event': 'lobby_back', 'match_id': message.match_id, 'reason': BACK_NAMES[message.reason]})]
        return []

    def say(self, raw, now: float, phrase: int = 0) -> list:
        if not isinstance(phrase, int) or not 0 <= phrase <= control.MAX_PHRASE:
            return [Event({'event': 'lobby_notice', 'code': 'bad_text', 'detail': ''})]
        text = '' if phrase else clean_chat(raw)
        if not text and not phrase:
            return [Event({'event': 'lobby_notice', 'code': 'bad_text', 'detail': ''})]
        if not self._chat.take(now):
            return [Event({'event': 'lobby_notice', 'code': 'chat_too_fast', 'detail': ''})]
        return [Send(None, control.Say(text, phrase))]

    def ready(self, ready: bool, now: float) -> list:
        if not self._changes.take(now):
            return []
        return [Send(None, control.Ready(bool(ready)))]

    def answer(self, selection: int, status: int, reasons: int = 0, version=(0, 0, 0)) -> list:
        """This PC's answer to the pick `selection` (the window got it from `lobby_check_request`)."""
        if selection != self.ident or self.game is None or self.rejected or status not in control.ANSWER_STATUSES:
            return []
        self.status = status
        return [Send(None, control.Answer(selection, status, reasons, tuple(version)))]

    def launch_status(self, launch: control.Launch) -> int:
        """What a guest says to a LAUNCH: ready only for the game it answered "same" to. With no pick (a launch made by the
        host without the lobby) the launch's own identity decides, as before."""
        game = self.game
        if game is None:
            return control.LAUNCHED_READY
        if (launch.machine, launch.stamp, launch.rom_sha) != (game.machine, game.digest(), game.rom):
            return control.LAUNCHED_OTHER_STAMP
        if self.status == control.CHECK_SAME:
            return control.LAUNCHED_READY
        return {control.CHECK_MISSING: control.LAUNCHED_NOT_OWNED, control.CHECK_OTHER: control.LAUNCHED_OTHER_STAMP}.get(
            self.status, control.LAUNCHED_FAILED)
