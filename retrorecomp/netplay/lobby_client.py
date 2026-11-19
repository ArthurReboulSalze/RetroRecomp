"""The converter's side of the lobby: what the future Multiplayer window will hold and call (no window here).

* `LobbyModel` folds the events of a room's worker (`lobby.EVENTS` and the room's own) into the state a window draws: the
  roster, the host's pick, each player's check, the chat (bounded), the notices, the last launch and the last match end. It is
  pure: `apply(event)` is its only input, so a test (or the window) can replay a list of events.
* `LobbyController` ties a `WorkerProcess` to this PC's library: it answers the host's pick by looking in the converter's own
  compiled games (`lobby_check.LocalLibrary`), keeps the executable it found for the launch, resolves the host's launch to that
  executable (a guest never runs anything the host named), and gives the host's window the calls it needs (pick, move, chat,
  launch). Nothing here opens a socket or a window; it runs on the converter's threads, and the library is read on a thread of
  its own so that a big report never holds the worker's event stream.

    controller = LobbyController(LocalLibrary(inventory))
    worker = WorkerProcess(config, resolve=controller.resolve, on_event=controller.on_event)
    controller.attach(worker)
    worker.start()
    ...
    controller.model            # what to draw; `controller.model.version` changes with every event it took
"""
from __future__ import annotations

import collections
from pathlib import Path
import threading
from typing import Callable

from . import control, internet_key, invitation
from .lobby import game_dict, game_from_dict
from .lobby_check import LocalLibrary, game_config
from .worker_client import WorkerProcess

# The Internet room (INTERNET_PLAN.md): False until a room really works over the Internet (the box's port, the window's
# warnings, the security review); the window greys its Internet choice with « bientôt » while it is False.
INTERNET = False
CHAT_KEPT = 200
NOTICES_KEPT = 50
ROOM_CAPACITY = 4                  # the host and up to three guests


def host_config(address: str, port: int, name: str, sharing: str, log_dir, tests: bool = False, internet: bool = False,
                public_address: str | None = None) -> tuple[dict, str]:
    """A host's worker config and the invitation for the port asked (the room may bind another one if it is taken: the
    model's `invitation`, made when the room opened, is the one to show). Raises ValueError for an address that is not
    on a local network. The secret is new for every room and lives only in this config and the invitation.

    `internet`: an Internet room, still bound to this local address (the box's port leads to it). Its invitation is the RR2
    key, made with `public_address` (what the host typed, or what was found); '' until an address is known."""
    invitation.check_bind_address(address, tests)
    secret = invitation.new_secret()
    log = Path(log_dir)
    config = {'room': {'role': 'host', 'address': address, 'port': int(port), 'secret': secret.hex(), 'capacity': ROOM_CAPACITY,
                       'name': name, 'log': str(log / 'room.log'), 'sharing': sharing, 'internet': bool(internet)},
              'tests': tests}
    if internet:
        return config, (_key(public_address, int(port), secret, tests) if public_address else '')
    return config, invitation.format_invitation(address, int(port), secret, tests)


def _key(public: str | None, port: int, secret: bytes, tests: bool) -> str:
    """The RR2 key of a public address (IPv4 or IPv6), or '' when it is not one a player can join."""
    if not public:
        return ''
    try:
        if ':' in public:
            return internet_key.format_key(port, secret, ipv6=public.strip(), tests=tests)
        return internet_key.format_key(port, secret, ipv4=public.strip(), tests=tests)
    except ValueError:
        return ''


def guest_config(invitation_text: str, name: str, log_dir, tests: bool = False) -> dict:
    """A guest's worker config; raises `invitation.InvitationError` (a sentence) when the text is not an invitation. A guest
    keeps no room log (`log_dir` is taken for the same call as the host's; the worker's own text goes to `start(log=...)`)."""
    del log_dir
    from .. import __version__
    from .room_cli import version_numbers
    text = invitation_text.strip() if isinstance(invitation_text, str) else invitation_text
    internet_key.parse_any(text, tests)          # a local invitation or an Internet key; InvitationError with its code
    return {'room': {'role': 'guest', 'invitation': text, 'name': name, 'version': list(version_numbers(__version__))},
            'tests': tests}


def guest_config_manual(address: str, port, code: str, name: str, log_dir, tests: bool = False) -> dict:
    """The typed form of an Internet room (address, port, code): the same worker config as its key."""
    room = internet_key.parse_manual(address, port, code, tests)
    ip = room.address
    text = internet_key.format_key(room.port, room.secret, ipv6=ip, tests=tests) if ':' in ip else \
        internet_key.format_key(room.port, room.secret, ipv4=ip, tests=tests)
    return guest_config(text, name, log_dir, tests)


class LobbyModel:
    def __init__(self):
        self.lock = threading.Lock()
        self.version = 0                    # counts the events taken: a window redraws when it changed
        self.room: str = 'connecting'       # connecting, open (a host), joined (a guest), error, closed, host_gone
        self.room_detail: str = ''
        self.room_code: str = ''            # the same in a word, for the window's own language (`lan_transport.room_code`)
        self.secret: bytes | None = None    # a host's: the invitation is made with the port the room really bound
        self.tests = False
        self.invitation: str = ''
        # An Internet room's host (the window's contract of 19 November 2026): the key and the typed code, the public address
        # in them, and how it was found (`reach`: probing, upnp, ipv6, site, typed, forward_needed, cgnat, waiting).
        self.internet = False
        self.key: str = ''
        self.code: str = ''
        self.public: str | None = None
        self.reach: str | None = None
        self.link: dict | None = None       # {tier, prediction, delay, slow, path} of the match being launched or played
        self.address: tuple | None = None   # a host's address and port, for its invitation text
        self.phase = 'lobby'
        self.revision: int | None = None
        self.seats_max = 0
        self.sharing = 'per_player'         # the input mode in force: per_player, everyone or turns (`seat_map.NAMES`)
        self.me: int | None = None
        self.players: list[dict] = []
        self.selection = 0
        self.game: dict | None = None
        self.checks: dict[int, dict] = {}   # guest -> {status, reasons, version, text}, the host's view of each answer
        self.chat: collections.deque = collections.deque(maxlen=CHAT_KEPT)
        self.notices: collections.deque = collections.deque(maxlen=NOTICES_KEPT)
        self.last_launch: dict | None = None
        self.last_back: dict | None = None
        self.matches: list[dict] = []       # match_over events, in order (bounded by the worker's event list)
        self.errors: collections.deque = collections.deque(maxlen=NOTICES_KEPT)

    def apply(self, event: dict) -> None:
        name = event.get('event') if isinstance(event, dict) else None
        with self.lock:
            self.version += 1
            handler = getattr(self, '_on_' + str(name), None)
            if handler is not None:
                handler(event)

    # ---- the lobby's events ----

    def _on_lobby_roster(self, event: dict) -> None:
        self.revision, self.phase, self.seats_max = event.get('revision'), event.get('phase', 'lobby'), event.get('seats_max', 0)
        self.sharing = event.get('sharing', 'per_player')
        self.selection, self.players, self.me = event.get('selection', 0), list(event.get('players', [])), event.get('me', self.me)

    def _on_lobby_selection(self, event: dict) -> None:
        self.selection, self.game = event.get('selection', 0), event.get('game')
        self.checks = {}

    def _on_lobby_check(self, event: dict) -> None:
        if event.get('selection') == self.selection:
            self.checks[event.get('guest')] = {key: event.get(key) for key in ('name', 'status', 'reasons', 'version', 'text')}

    def _on_lobby_chat(self, event: dict) -> None:
        line = {key: event.get(key) for key in ('sender', 'name', 'text', 'ascii')}
        line['phrase'] = event.get('phrase') or 0     # 1-6: a ready-made phrase, shown in the window's language
        self.chat.append(line)

    def _on_lobby_notice(self, event: dict) -> None:
        self.notices.append({'code': event.get('code'), 'detail': event.get('detail', '')})

    def _on_lobby_launch(self, event: dict) -> None:
        self.last_launch = {key: event.get(key) for key in ('match_id', 'seats', 'names', 'left_out', 'sharing')}

    def _on_lobby_back(self, event: dict) -> None:
        self.last_back = {'match_id': event.get('match_id'), 'reason': event.get('reason')}
        self.phase = 'lobby'
        self.link = None

    def _on_lobby_error(self, event: dict) -> None:
        self.errors.append({'call': event.get('call'), 'code': 'lobby_error', 'detail': event.get('detail', '')})

    # ---- the room's own events ----

    def _on_room_open(self, event: dict) -> None:
        self.room, self.address = 'open', (event.get('address'), event.get('port'))
        if self.secret is not None and self.internet:
            self.code = internet_key.format_code(self.secret)
            self.key = self.invitation = _key(self.public, event.get('port'), self.secret, self.tests)
        elif self.secret is not None:
            self.invitation = invitation.format_invitation(event.get('address'), event.get('port'), self.secret, self.tests)

    def set_public(self, address: str | None, reach: str) -> None:
        """The public address of an Internet room's host (found, or typed: `reach` says which); the key follows it."""
        with self.lock:
            self.version += 1
            self.public, self.reach = (address.strip() if isinstance(address, str) and address.strip() else None), reach
            if self.secret is not None and self.address is not None:
                self.key = self.invitation = _key(self.public, self.address[1], self.secret, self.tests)

    def _on_joined_room(self, event: dict) -> None:
        self.room, self.me = 'joined', event.get('guest')

    def _on_room_error(self, event: dict) -> None:
        self.room, self.room_detail, self.room_code = 'error', event.get('detail', ''), event.get('code', 'other')

    def _on_room_closed(self, event: dict) -> None:
        self.room = 'closed'

    def _on_host_gone(self, event: dict) -> None:
        self.room, self.room_detail, self.room_code = 'host_gone', event.get('detail', ''), event.get('code', 'other')

    def _on_match_over(self, event: dict) -> None:
        self.matches.append({key: event.get(key) for key in ('match_id', 'outcome', 'detail')})
        del self.matches[:-NOTICES_KEPT]
        self.link = None

    # The link line: the tier and cap the launch says, the delay the match applies (from the worker's status, `controller
    # .link()`), and `slow` when the host applied a delay above the slow-link threshold (the owner's decision: applied, said).
    def _on_launching(self, event: dict) -> None:
        self.link = {'tier': event.get('tier', 'delay'), 'prediction': event.get('prediction'), 'delay': None, 'slow': None,
                     'path': 'ipv4' if self.internet else 'lan'}

    def _on_launch_request(self, event: dict) -> None:
        self.link = {'tier': event.get('tier', 'delay'), 'prediction': event.get('prediction'), 'delay': None, 'slow': None,
                     'path': 'ipv4' if self.internet else 'lan'}

    def _on_slow_link(self, event: dict) -> None:
        if self.link is None:
            self.link = {'tier': None, 'prediction': None, 'delay': None, 'slow': None, 'path': 'ipv4' if self.internet else 'lan'}
        self.link['slow'] = event.get('delay')

    # Launch errors: `code` is the event's name (launch_error: this PC could not start it; launch_failed: a seat did not start;
    # launch_refused: this guest's game cannot play it), the detail an English sentence for a log.
    def _on_launch_error(self, event: dict) -> None:
        self.errors.append({'call': 'launch', 'code': 'launch_error', 'detail': event.get('detail', '')})

    def _on_launch_failed(self, event: dict) -> None:
        self.errors.append({'call': 'launch', 'code': 'launch_failed', 'detail': event.get('detail', '')})

    def _on_launch_refused(self, event: dict) -> None:
        self.errors.append({'call': 'launch', 'code': 'launch_refused', 'detail': event.get('detail', '')})


class LobbyController:
    """One per room. `library` is this PC's `LocalLibrary`; `game_for(entry)` gives the worker's `game` record of an inventory
    entry (`lobby_check.game_config` unless the window adds its environment and log files)."""

    def __init__(self, library: LocalLibrary, *, game_for: Callable = game_config, model: LobbyModel | None = None,
                 on_answer: Callable[[dict], None] | None = None):
        self.library, self.game_for, self.model = library, game_for, model or LobbyModel()
        self.on_answer = on_answer
        self.worker = None
        self._lock = threading.Lock()
        self._game: control.Game | None = None      # the host's current pick, as this PC checked it
        self._selection = 0
        self._found = None                          # the inventory entry this PC would launch for it
        self._entry = None                          # the host: the entry it picked
        self.answers: list[dict] = []               # this PC's answers, in order (tests, the window's own check line)

    def attach(self, worker) -> None:
        self.worker = worker

    def set_public_address(self, text: str) -> None:
        """The public address the host typed for its Internet room (always taken over a found one): the key follows it."""
        self.model.set_public(text, 'typed')

    def start(self, config: dict, log=None) -> WorkerProcess:
        """Starts the room's worker for `config` (`host_config` / `guest_config`), wired to this controller."""
        room = config.get('room', {})
        with self.model.lock:
            self.model.secret = bytes.fromhex(room['secret']) if room.get('role') == 'host' else None
            self.model.tests = config.get('tests') is True
            text = room.get('invitation', '')
            self.model.internet = room.get('internet') is True or (isinstance(text, str) and text.strip()[:3].upper() == 'RR2')
            if self.model.internet and room.get('role') == 'host' and self.model.reach is None:
                self.model.reach = 'probing'
        worker = WorkerProcess(config, log=Path(log) if log else None, on_event=self.on_event, resolve=self.resolve)
        self.attach(worker)
        self._closed = False
        return worker.start()

    def close(self, timeout: float = 15.0) -> None:
        """Leaves (a guest) or closes (the host) the room and ends its worker. Any thread, any number of times."""
        with self._lock:
            worker, closed = self.worker, getattr(self, '_closed', False)
            self._closed = True
        if worker is None or closed:
            return
        try:
            worker.call('close_room')
            worker.join(timeout)
        finally:
            worker.cleanup()

    def link(self) -> dict | None:
        """The link line of the match: the model's, with the delay the driver applies now (None before it is chosen)."""
        with self.model.lock:
            line = dict(self.model.link) if self.model.link else None
        if line is not None and self.worker is not None:
            status = getattr(self.worker, 'status', None) or {}
            line['delay'] = status.get('delay')
        return line

    # ---- the worker's events ----

    def on_event(self, event: dict) -> None:
        self.model.apply(event)
        if event.get('event') == 'lobby_check_request':
            threading.Thread(target=self._check, args=(event,), name='lobby-check', daemon=True).start()

    def _check(self, event: dict) -> None:
        """A guest: look for the host's pick in this PC's library and answer it. Never raises: a pick this PC cannot read is
        answered as one it could not check."""
        selection = event.get('selection')
        try:
            game = game_from_dict(event['game'])
            answer = self.library.check(game)
            status, reasons, version, found = answer.status, answer.reasons, answer.version, answer.found
        except Exception as error:      # said to the host as "could not check"; the converter goes on
            game, found, status, reasons, version = None, None, control.CHECK_FAILED, 0, (0, 0, 0)
            answer_text = f'could not check ({type(error).__name__})'
        else:
            answer_text = answer.text
        with self._lock:
            self._game, self._selection, self._found = game, selection, found if status == control.CHECK_SAME else None
        record = {'selection': selection, 'status': status, 'reasons': reasons, 'version': list(version), 'text': answer_text}
        self.answers.append(record)
        del self.answers[:-NOTICES_KEPT]
        if self.worker is not None:
            self.worker.call('lobby_answer', selection=selection, status=status, reasons=reasons, version=list(version))
        if self.on_answer is not None:
            self.on_answer(record)

    def recheck(self) -> None:
        """A guest reconverted (or added) its game: the same pick is looked up again and answered again."""
        game = self.model.game
        if game is not None:
            self._check({'event': 'lobby_check_request', 'selection': self.model.selection, 'game': game})

    def resolve(self, event: dict):
        """The host's LAUNCH reached this guest's worker: the executable is the one found for the pick, or the launch is refused."""
        with self._lock:
            game, found = self._game, self._found
        if (found is None or game is None or event.get('machine') != game.machine or event.get('rom') != game.rom.hex()
                or event.get('stamp') != game.digest().hex()):
            return {'call': 'launch_refused', 'match_id': event.get('match_id'), 'status': control.LAUNCHED_NOT_OWNED}
        return {'call': 'launch', 'match_id': event.get('match_id'), 'game': self.game_for(found)}

    # ---- what the host's window calls ----

    def pick(self, entry, game_options: str = '') -> str:
        """The host picks one of its compiled games. '' when sent, else why not (a sentence for a log)."""
        candidate = self.library.game_of(entry, game_options)
        if candidate.game is None:
            return candidate.reason or 'this game cannot be picked'
        with self._lock:
            self._entry = entry
        self.worker.call('lobby_select', game=game_dict(candidate.game))
        return ''

    def clear_pick(self) -> None:
        with self._lock:
            self._entry = None
        self.worker.call('lobby_select', game=None)

    def say(self, text: str) -> None:
        self.worker.call('lobby_chat', text=text)

    def ready(self, ready: bool) -> None:
        self.worker.call('lobby_ready', ready=bool(ready))

    def move(self, guest: int, seat: int) -> None:
        self.worker.call('lobby_move', guest=guest, seat=seat)

    def set_sharing(self, mode: str) -> None:
        """The host's input mode: 'per_player', 'everyone' or 'turns' (a handheld's game is played in input sharing whatever is
        chosen; the roster says the mode in force)."""
        self.worker.call('lobby_sharing', mode=mode)

    def pass_token(self, to: int | None = None) -> None:
        """In a match shared in "turns": pass the turn to the next seat (the holder), or to seat `to` (the host)."""
        self.worker.pass_token(to)

    def set_share_mode(self, mode: int) -> None:
        """In a shared match, the host: `seat_map.SHARED_ALL` ("everyone") or `seat_map.SHARED_TURNS`."""
        self.worker.share_mode(mode)

    def launch(self, settings: dict | None = None, need_ready: bool = False) -> str:
        """The host starts the match of its pick with the guests who have it. '' when asked, else why not."""
        with self._lock:
            entry = self._entry
        if entry is None:
            return 'no game is picked'
        self.worker.call('lobby_launch', game=self.game_for(entry), settings=settings or {}, need_ready=need_ready)
        return ''
