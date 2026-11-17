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
    controller.bind(worker)
    worker.start()
    ...
    controller.model            # what to draw; `controller.model.version` changes with every event it took
"""
from __future__ import annotations

import collections
import threading
from typing import Callable

from . import control
from .lobby import game_dict, game_from_dict
from .lobby_check import LocalLibrary, game_config

CHAT_KEPT = 200
NOTICES_KEPT = 50


class LobbyModel:
    def __init__(self):
        self.lock = threading.Lock()
        self.version = 0                    # counts the events taken: a window redraws when it changed
        self.room: str = 'connecting'       # connecting, open (a host), joined (a guest), error, closed, host_gone
        self.room_detail: str = ''
        self.address: tuple | None = None   # a host's address and port, for its invitation text
        self.phase = 'lobby'
        self.revision: int | None = None
        self.seats_max = 0
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
        self.selection, self.players, self.me = event.get('selection', 0), list(event.get('players', [])), event.get('me', self.me)

    def _on_lobby_selection(self, event: dict) -> None:
        self.selection, self.game = event.get('selection', 0), event.get('game')
        self.checks = {}

    def _on_lobby_check(self, event: dict) -> None:
        if event.get('selection') == self.selection:
            self.checks[event.get('guest')] = {key: event.get(key) for key in ('name', 'status', 'reasons', 'version', 'text')}

    def _on_lobby_chat(self, event: dict) -> None:
        self.chat.append({key: event.get(key) for key in ('sender', 'name', 'text', 'ascii')})

    def _on_lobby_notice(self, event: dict) -> None:
        self.notices.append({'code': event.get('code'), 'detail': event.get('detail', '')})

    def _on_lobby_launch(self, event: dict) -> None:
        self.last_launch = {key: event.get(key) for key in ('match_id', 'seats', 'names', 'left_out')}

    def _on_lobby_back(self, event: dict) -> None:
        self.last_back = {'match_id': event.get('match_id'), 'reason': event.get('reason')}
        self.phase = 'lobby'

    def _on_lobby_error(self, event: dict) -> None:
        self.errors.append({'call': event.get('call'), 'detail': event.get('detail', '')})

    # ---- the room's own events ----

    def _on_room_open(self, event: dict) -> None:
        self.room, self.address = 'open', (event.get('address'), event.get('port'))

    def _on_joined_room(self, event: dict) -> None:
        self.room, self.me = 'joined', event.get('guest')

    def _on_room_error(self, event: dict) -> None:
        self.room, self.room_detail = 'error', event.get('detail', '')

    def _on_room_closed(self, event: dict) -> None:
        self.room = 'closed'

    def _on_host_gone(self, event: dict) -> None:
        self.room, self.room_detail = 'host_gone', event.get('detail', '')

    def _on_match_over(self, event: dict) -> None:
        self.matches.append({key: event.get(key) for key in ('match_id', 'outcome', 'detail')})
        del self.matches[:-NOTICES_KEPT]

    def _on_launch_error(self, event: dict) -> None:
        self.errors.append({'call': 'launch', 'detail': event.get('detail', '')})

    def _on_launch_failed(self, event: dict) -> None:
        self.errors.append({'call': 'launch', 'detail': event.get('detail', '')})

    def _on_launch_refused(self, event: dict) -> None:
        self.errors.append({'call': 'launch', 'detail': event.get('detail', '')})


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

    def bind(self, worker) -> None:
        self.worker = worker

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

    def launch(self, settings: dict | None = None, need_ready: bool = False) -> str:
        """The host starts the match of its pick with the guests who have it. '' when asked, else why not."""
        with self._lock:
            entry = self._entry
        if entry is None:
            return 'no game is picked'
        self.worker.call('lobby_launch', game=self.game_for(entry), settings=settings or {}, need_ready=need_ready)
        return ''
