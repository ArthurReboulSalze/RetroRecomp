"""The worker of a room (multiplayer stage 2): its life is the room's life, and a game is something that happens in it.

A worker whose CONFIG has a `room` opens the room's endpoint itself (`lan_transport`) and holds it until the converter
says `close_room` or goes away. There is no game in CONFIG: a host's converter sends a `launch` call (the game, resolved
from its own library, and the settings of the match); a guest's worker receives the host's LAUNCH over the room, checks
it with `launch.launch_settings`, **asks its converter** (a `launch_request` event) which executable is that game on this PC,
and gets a `launch` call back. No path, no file name and no command line ever crosses the network.

    CONFIG  {"room": {"role": "host", "address", "port", "secret": hex, "capacity", "name", "log"},
             "tests": bool, "test_settings": {...}}                       the secret is here and nowhere else
            {"room": {"role": "guest", "invitation": "rr1:lan:...", "name", "version": [a, b, c]}, ...}
    CALL    {"call": "launch", "game": {exe, cwd, env, stdout, stderr}, "identity": {machine, stamp, rom},
             "settings": {delay, digest_every, redundancy, options, tier, rollback, ...test hooks when tests}}   host
            {"call": "launch", "match_id": n, "game": {...} [, "test_settings": {...}]}                 guest
            {"call": "launch_refused", "match_id": n, "status": 1 | 2 | 3}                              guest
            {"call": "kick", "guest": n}   {"call": "close_room"}   stop, resume, close_game_pipe (tests)
    CALL    the lobby (`lobby.py`, `lobby_check.py`; the fields are in LOBBY.md):
            {"call": "lobby_chat", "text": s}                                                 host, guest
            {"call": "lobby_select", "game": {lobby.game_dict fields} | null}                 host: the pick
            {"call": "lobby_move", "guest": n, "seat": n}                                     host
            {"call": "lobby_sharing", "mode": "per_player" | "everyone" | "turns"}            host: the input mode (room CONFIG may say it too)
            {"call": "pass_token", "to": n | absent}     {"call": "share_mode", "mode": 1 | 2}      a match: the turn, the mode
            {"call": "lobby_launch", "game": {exe, cwd, ...}, "settings": {...}, "need_ready": bool}   host
            {"call": "lobby_ready", "ready": bool}                                            guest
            {"call": "lobby_answer", "selection": n, "status": n, "reasons": n, "version": [a, b, c]}  guest: its library's word
    EVENT   room_open, joined_room, joined, left, launching, launch_request, launch_failed, launch_error,
            launch_refused, slow_link, seat_dropped, host_gone, match_over, room_error, room_closed, and the lobby's
            (`lobby.EVENTS`): lobby_roster, lobby_selection, lobby_check_request, lobby_check, lobby_chat, lobby_notice,
            lobby_launch, lobby_back, lobby_error

The tier (`tier`: "auto" the default, "delay" or "rollback"; `rollback`: the prediction cap, 1 to 8, default 8) is the host's
decision and rides the LAUNCH as one byte. Unless it is "delay", the host starts its own game before it sends the LAUNCH and
decides from that game's HELLO (`rollback.choose_tier`): the games of a match are the same build (the launch names the stamp and
the guests answered "same"), so their HELLOs say the same; a guest whose game does not (`Settings.rollback_required`) refuses the
match with a reason. The game switch is a new launch, decided again for the game it names.

The converter's EVENT stream is data for its window: the names in it were cleaned by the host (`control.display_name`),
the machine id is a short plain word, the digests are hex. Nothing in it is ever run, opened or used as a path.
Test hooks (`local_source`, `words_filter`, `clock_ppm`, `keep_history`, `last_frame`, ...) are taken from
`test_settings` / the launch call only when CONFIG says `"tests": true`, and can never come from the network.
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
import queue
import threading

from . import control, invitation, scripted_inputs, seat_map
from . import session_pipe as pipe
from . import worker_channel as channel
from .lan_transport import RoomError, RoomGuest, RoomHost
from .launch import Refusal, launch_settings
from .lobby import game_from_dict
from .lockstep import LockstepDriver, Settings
from .lag_link import LagLink
from .rollback import DEFAULT_PREDICTION, TIER_AUTO, TIER_DELAY, check_tier, choose_tier, driver_for
from .room_log import RoomLog
from .session_game import SessionGame
from .worker import result_message

STATUS_EVERY = 0.1
END_WAIT = 20.0
HELLO_WAIT = 20.0                # seconds the host waits for its own game's HELLO before it launches (a game that starts slowly)
SLOW_LINK = 8                    # a measured delay above this on a local room is applied with a lobby line (decision of 17 Nov)
TEST_FIELDS = ('local_source', 'words_filter', 'clock_ppm', 'keep_history', 'last_frame', 'waiting_after', 'drop_after',
               'packet_rate', 'probe_seconds', 'pace', 'desync_confirm')


def test_settings(settings: Settings, values: dict, tests: bool) -> Settings:
    """`settings` with the test hooks `values` names, taken only under `tests` (a worker not under test refuses them)."""
    if not values:
        return settings
    if not tests:
        raise ValueError('test settings without "tests": true')
    fields = {name: values[name] for name in values if name in TEST_FIELDS}
    if len(fields) != len(values):
        raise ValueError('a test setting this worker does not know')
    if 'local_source' in fields:
        fields['local_source'] = scripted_inputs.local_source(fields['local_source'])
    if 'words_filter' in fields:
        fields['words_filter'] = scripted_inputs.words_filter(fields['words_filter'])
    return dataclasses.replace(settings, **fields)


def _tier_name(rollback: int) -> str:
    return 'rollback' if rollback else 'delay'


class _Match:
    def __init__(self, match_id: int, driver: LockstepDriver, session: SessionGame, host: bool):
        self.match_id, self.driver, self.session, self.host = match_id, driver, session, host
        self.finished = threading.Event()
        self.slow_told = False


class RoomWorker:
    def __init__(self, config: dict, reader: channel.Reader, writer: channel.Writer, fd_in: int):
        room = config['room']
        self.config, self.reader, self.writer, self.fd_in = config, reader, writer, fd_in
        self.tests = config.get('tests') is True
        self.role = room['role']
        if self.role not in ('host', 'guest'):
            raise ValueError('a room is hosted or joined')
        self.room_config = room
        self.test_values = dict(config.get('test_settings') or {})
        self.lock = threading.RLock()
        self.room: RoomHost | RoomGuest | None = None
        self.match: _Match | None = None
        self.pending: dict | None = None        # a host's launch waiting for every guest, or a guest's waiting for its converter
        self.inbox: queue.Queue = queue.Queue()
        self.finished = threading.Event()       # the room is over: the converter said so, or went away
        self.exit_code = 0

    # ---- what goes to the converter ----

    def emit(self, event: dict) -> None:
        self.writer.send(channel.EVENT, json.dumps(event).encode('utf-8'))

    def _room_event(self, event: dict) -> None:         # the room's thread: only a hand-over
        self.inbox.put(('event', event))

    def _room_launch(self, launch: control.Launch) -> None:
        self.inbox.put(('launch', launch))

    # ---- the room ----

    def open_room(self) -> bool:
        room = self.room_config
        try:
            if self.role == 'host':
                log = RoomLog(Path(room['log']) if room.get('log') else None)
                host = RoomHost(room['address'], room.get('port', invitation.DEFAULT_PORT), bytes.fromhex(room['secret']),
                                room.get('capacity', 4), name=room.get('name', 'Host'), tests=self.tests, log=log,
                                on_event=self._room_event, seat_rate=room.get('seat_rate') if self.tests else None,
                                sharing=seat_map.BY_NAME.get(room.get('sharing', 'per_player'), -1))
                port = host.open()
                self.room = host
                self.emit({'event': 'room_open', 'role': 'host', 'address': host.address, 'port': port, 'capacity': host.capacity})
            else:
                invited = invitation.parse(room['invitation'], self.tests)
                guest = RoomGuest(invited, room.get('name', 'Guest'), tests=self.tests, version=tuple(room.get('version', (0, 0, 0))),
                                  on_event=self._room_event, on_launch=self._room_launch)
                guest.connect()
                self.room = guest
        except (RoomError, invitation.InvitationError) as error:
            self.emit({'event': 'room_error', 'detail': error.reason,
                       'code': error.code if isinstance(error, RoomError) else 'bad_invitation'})
            return False
        except (KeyError, ValueError, TypeError):
            self.emit({'event': 'room_error', 'detail': 'the room settings are not what they should be', 'code': 'other'})
            return False
        return True

    def handle_inbox(self) -> None:
        """The thread that reacts to the room: slow things (a game starting) never run on the room's own thread."""
        while True:
            kind, item = self.inbox.get()
            if kind == 'stop':
                return
            try:
                if kind == 'event':
                    self._on_event(item)
                else:
                    self._on_launch(item)
            except Exception as error:      # said, never hidden; the room goes on
                self.emit({'event': 'room_error', 'detail': f'{type(error).__name__} while handling the room'})

    def _chat_from_game(self, phrase: int, text: str) -> None:
        """A line the player typed in the game (the driver's thread): into the room's lobby, as one typed in the window."""
        room = self.room
        if room is not None:
            room.lobby_say(text, phrase)

    def _chat_to_game(self, event: dict) -> None:
        """The room's chat during a match reaches the game too: every line (this player's own included, in the host's order),
        and "too many lines" when this player's was refused."""
        with self.lock:
            match = self.match
        if match is None:
            return
        name = event.get('event')
        if name == 'lobby_chat':
            phrase = event.get('phrase') or 0
            if not isinstance(phrase, int) or not 0 <= phrase <= pipe.PHRASE_COUNT:
                phrase = 0                      # (the lobby never makes one: its text is then shown as it is)
            match.driver.chat_show(phrase, str(event.get('name', '?')), '' if phrase else str(event.get('ascii', '')))
        elif name == 'lobby_notice' and event.get('code') == 'chat_too_fast':
            match.driver.chat_slow()

    def _on_event(self, event: dict) -> None:
        self.emit(event)
        name = event.get('event')
        if name in ('lobby_chat', 'lobby_notice'):
            self._chat_to_game(event)
        if name == 'all_launched' and self.role == 'host':
            self._start_host_match()
        elif name in ('launch_failed',) and self.role == 'host':
            with self.lock:
                pending, self.pending = self.pending, None
            self._drop_game(pending.get('session') if pending else None)

    def _on_launch(self, launch: control.Launch) -> None:
        """A guest: the host's LAUNCH, checked; then the converter is asked which game that is on this PC."""
        message = {'seat': launch.seat, 'seats': launch.seats, 'names': list(launch.names), 'delay': launch.delay or None,
                   'digest_every': launch.digest_every, 'redundancy': launch.redundancy, 'options': launch.options,
                   'sharing': launch.sharing, 'rollback': launch.rollback}
        settings = launch_settings(message, guest=True, machine=launch.machine, rollback_max=control.MAX_ROLLBACK)
        if isinstance(settings, Refusal):
            self.room.launched(launch.match_id, control.LAUNCHED_FAILED)
            self.emit({'event': 'launch_refused', 'match_id': launch.match_id, 'detail': settings.reason})
            return
        if settings.rollback:       # the host decided from its game's HELLO: this game must keep snapshots too, or it refuses
            settings = dataclasses.replace(settings, rollback_required=True)
        with self.lock:
            if self.match is not None or self.pending is not None:
                self.room.launched(launch.match_id, control.LAUNCHED_FAILED)
                return
            self.pending = {'match_id': launch.match_id, 'settings': settings}
        self.emit({'event': 'launch_request', 'match_id': launch.match_id, 'machine': launch.machine,
                   'stamp': launch.stamp.hex(), 'rom': launch.rom_sha.hex(), 'seat': launch.seat, 'seats': launch.seats,
                   'names': list(settings.names), 'tier': _tier_name(settings.rollback), 'prediction': settings.rollback})

    # ---- a match ----

    def _game_config(self, call: dict) -> dict:
        game = call['game']
        if not isinstance(game, dict) or not isinstance(game.get('exe'), str):
            raise ValueError('the launch names no game')
        return game

    def _open_game(self, game: dict) -> SessionGame:
        return SessionGame(Path(game['exe']), cwd=Path(game['cwd']) if game.get('cwd') else None, env=game.get('env'),
                           stdout=Path(game['stdout']) if game.get('stdout') else None,
                           stderr=Path(game['stderr']) if game.get('stderr') else None)

    def _link(self):
        """The match's link; with the room command's `--lag-ms` (a test of a far player), what this PC sends is held that long."""
        link = self.room.link()
        lag, jitter = float(self.room_config.get('lag_ms') or 0), float(self.room_config.get('jitter_ms') or 0)
        return LagLink(link, lag, jitter) if lag or jitter else link

    def _run_match(self, match_id: int, game: dict, settings: Settings, link, host: bool,
                   session: SessionGame | None = None) -> _Match:
        session = session or self._open_game(game)
        driver = driver_for(session, link, settings)
        driver.on_chat = self._chat_from_game
        match = _Match(match_id, driver, session, host)
        with self.lock:
            self.match = match
        driver.start()
        threading.Thread(target=self._report, args=(match,), name='netplay-room-status', daemon=True).start()
        threading.Thread(target=self._watch, args=(match,), name='netplay-room-match', daemon=True).start()
        return match

    def _report(self, match: _Match) -> None:
        last = None
        while not match.finished.wait(STATUS_EVERY):
            status = match.driver.snapshot()
            status['match_id'] = match.match_id
            if status != last:
                last = status
                self.writer.send(channel.STATUS, json.dumps(status).encode('utf-8'))
            delay = match.driver.delay
            if match.host and not match.slow_told and delay is not None and delay > SLOW_LINK and match.driver.settings.delay is None:
                match.slow_told = True        # applied automatically; the lobby says so (the owner's decision of 17 November)
                self.emit({'event': 'slow_link', 'match_id': match.match_id, 'delay': delay,
                           'detail': f'Slow link: delay of {delay} frames'})

    def _watch(self, match: _Match) -> None:
        match.driver.join()
        match.finished.set()
        result = match.driver.result()
        result['match_id'] = match.match_id
        self.writer.send(channel.RESULT, result_message(result))
        with self.lock:
            if self.match is match:
                self.match = None
        if self.role == 'host' and self.room is not None:
            self.room.end_match(match.driver.outcome or 'ended')       # and every guest is back in the lobby
        self.emit({'event': 'match_over', 'match_id': match.match_id, 'outcome': match.driver.outcome,
                   'detail': match.driver.detail, 'counters': self.room.counters if self.room is not None else {}})

    def _start_host_match(self) -> None:
        with self.lock:
            pending, self.pending = self.pending, None
        if pending is None:
            return
        info = pending['info']
        try:
            settings = test_settings(Settings(seat=0, seats=info.seats, names=tuple(info.names), **pending['net']),
                                     pending['values'], self.tests)
            self._run_match(info.match_id, pending['game'], settings, self._link(), True, pending.get('session'))
        except Exception as error:
            self._drop_game(pending.get('session'))
            self.room.abort('the host could not start its game')
            self.emit({'event': 'launch_error', 'match_id': info.match_id,
                       'detail': f'the game could not be started: {type(error).__name__}'})

    # ---- the converter's calls ----

    def call(self, message: dict) -> None:
        name = message.get('call')
        match = self.match
        if name == 'stop' and match is not None:
            match.driver.stop()
        elif name == 'resume' and match is not None:
            match.driver.resume()
        elif name == 'pass_token' and match is not None:
            to = message.get('to')
            match.driver.pass_token(to if isinstance(to, int) and not isinstance(to, bool) else None)
        elif name == 'share_mode' and match is not None:
            mode = message.get('mode')
            match.driver.set_sharing(mode if isinstance(mode, int) and not isinstance(mode, bool) else -1)
        elif name == 'close_game_pipe' and self.tests and match is not None:
            match.driver.close_game_pipe()
        elif name == 'launch':
            (self._host_launch if self.role == 'host' else self._guest_launch)(message)
        elif isinstance(name, str) and name.startswith('lobby_'):
            self._lobby_call(name, message)
        elif name == 'launch_refused' and self.role == 'guest':
            with self.lock:
                pending, self.pending = self.pending, None
            if pending is not None and pending['match_id'] == message.get('match_id'):
                status = message.get('status')
                self.room.launched(pending['match_id'], status if status in (1, 2, 3) else control.LAUNCHED_FAILED)
        elif name == 'kick' and self.role == 'host':
            self.room.kick(int(message.get('guest', 0)))
        elif name == 'close_room':
            self.finished.set()

    def _host_launch(self, message: dict) -> None:
        try:
            game = self._game_config(message)
            identity = message['identity']
            values = dict(message.get('settings') or {})
            net = {name: values.pop(name) for name in ('delay', 'digest_every', 'redundancy', 'options', 'sharing') if name in values}
            tier = {name: values.pop(name) for name in ('tier', 'rollback') if name in values}
            check = launch_settings({'seat': 1, 'seats': 2, 'names': ['a', 'b'], 'delay': net.get('delay'),
                                     'digest_every': net.get('digest_every', Settings.digest_every),
                                     'redundancy': net.get('redundancy', Settings.redundancy),
                                     'options': net.get('options', ''), 'sharing': net.get('sharing', seat_map.PER_PLAYER)},
                                    guest=True, machine=identity['machine'])
            if isinstance(check, Refusal):
                raise ValueError(check.reason)
        except (KeyError, ValueError, TypeError) as error:
            self.emit({'event': 'launch_error', 'detail': f'the launch is not what it should be ({type(error).__name__})'})
            return
        session = None
        try:
            session, rollback = self._decide_tier(game, tier)
            with self.lock:         # held until `pending` is set: a guest that answers at once finds it there
                if self.match is not None or self.pending is not None:
                    raise RoomError('a match is already running')
                info = self.room.launch(machine=identity['machine'], stamp=bytes.fromhex(identity['stamp']),
                                        rom_sha=bytes.fromhex(identity['rom']), delay=net.get('delay') or 0,
                                        digest_every=net.get('digest_every', Settings.digest_every),
                                        redundancy=net.get('redundancy', Settings.redundancy), options=net.get('options', ''),
                                        sharing=net.get('sharing', seat_map.PER_PLAYER), rollback=rollback)
                self.pending = {'info': info, 'game': game, 'values': values, 'session': session,
                                'net': {**net, **self._tier_settings(rollback)}}
        except RoomError as error:
            self._drop_game(session)
            self.emit({'event': 'launch_error', 'detail': error.reason})
            return
        except (KeyError, ValueError, TypeError) as error:
            self._drop_game(session)
            self.emit({'event': 'launch_error', 'detail': f'the launch is not what it should be ({type(error).__name__})'})
            return
        self.emit({'event': 'launching', 'match_id': info.match_id, 'seats': info.seats, 'names': list(info.names),
                   'tier': _tier_name(rollback), 'prediction': rollback})

    # ---- the tier ----

    @staticmethod
    def _tier_settings(rollback: int) -> dict:
        return {'rollback': rollback, 'rollback_required': bool(rollback)}

    def _decide_tier(self, game: dict, asked: dict) -> tuple[SessionGame | None, int]:
        """The host's tier for this launch: (its game, started and held, or None for the delay tier; the tier byte). Unless the
        host asked for the delay tier, its own game is started now to read its HELLO (`rollback.choose_tier` decides from it);
        the driver takes the game over at the start of the match. A `RoomError` says why the launch cannot be made."""
        mode, cap = asked.get('tier', TIER_AUTO), asked.get('rollback', DEFAULT_PREDICTION)
        bad = check_tier(mode, cap)
        if bad is not None:                 # refused before any game is started
            raise RoomError(bad.reason)
        if mode == TIER_DELAY:
            return None, 0
        session = self._open_game(game)
        try:
            session.hold()
            verdict = choose_tier(mode, [session.wait_hello(HELLO_WAIT)], cap)
            if isinstance(verdict, Refusal):
                raise RoomError(verdict.reason)
        except BaseException:
            self._drop_game(session)
            raise
        return session, verdict

    def _drop_game(self, session: SessionGame | None) -> None:
        """A game started for a launch that did not happen: its pipe is closed and it is ended."""
        if session is None:
            return
        session.close_pipe()
        try:
            session.process.kill()
        except OSError:
            pass

    # ---- the lobby's calls ----

    def _lobby_call(self, name: str, message: dict) -> None:
        """The window's calls on the lobby. A call that is not what it should be is said (`lobby_error`) and changes nothing."""
        try:
            if name == 'lobby_chat':
                self.room.lobby_say(str(message.get('text', '')))
            elif self.role == 'host' and name == 'lobby_select':
                refusal = self.room.lobby_select(None if message.get('game') is None else game_from_dict(message['game']))
                if refusal is not None:
                    self.emit({'event': 'lobby_error', 'call': name, 'detail': refusal.reason})
            elif self.role == 'host' and name == 'lobby_sharing':
                refusal = self.room.lobby_sharing(seat_map.BY_NAME.get(message.get('mode'), -1))
                if refusal is not None:
                    self.emit({'event': 'lobby_error', 'call': name, 'detail': refusal.reason})
            elif self.role == 'host' and name == 'lobby_move':
                refusal = self.room.lobby_move(int(message['guest']), int(message['seat']))
                if refusal is not None:
                    self.emit({'event': 'lobby_error', 'call': name, 'detail': refusal.reason})
            elif self.role == 'host' and name == 'lobby_launch':
                self._lobby_launch(message)
            elif self.role == 'guest' and name == 'lobby_ready':
                self.room.lobby_ready(bool(message.get('ready')))
            elif self.role == 'guest' and name == 'lobby_answer':
                self.room.lobby_answer(int(message['selection']), int(message['status']), int(message.get('reasons', 0)),
                                       tuple(int(number) for number in message.get('version', (0, 0, 0))))
            else:
                self.emit({'event': 'lobby_error', 'call': name, 'detail': 'a lobby call this seat does not take'})
        except (KeyError, ValueError, TypeError) as error:
            self.emit({'event': 'lobby_error', 'call': name, 'detail': f'the call is not what it should be ({type(error).__name__})'})

    def _lobby_launch(self, message: dict) -> None:
        """The host starts the match of its pick with the guests who have the game: the lobby says who and what the launch's
        options are (the host's pick pushes them; `settings` cannot)."""
        game = self._game_config(message)
        values = dict(message.get('settings') or {})
        if 'options' in values or 'sharing' in values:
            raise ValueError('the options of a lobby launch are the pick\'s')
        net = {name: values.pop(name) for name in ('delay', 'digest_every', 'redundancy') if name in values}
        tier = {name: values.pop(name) for name in ('tier', 'rollback') if name in values}
        check = launch_settings({'seat': 1, 'seats': 2, 'names': ['a', 'b'], 'delay': net.get('delay'),
                                 'digest_every': net.get('digest_every', Settings.digest_every),
                                 'redundancy': net.get('redundancy', Settings.redundancy), 'options': ''}, guest=True)
        if isinstance(check, Refusal):
            raise ValueError(check.reason)
        need_ready = bool(message.get('need_ready'))
        refusal = self.room.lobby_can_launch(need_ready)       # before the host's game is started for nothing
        if refusal is not None:
            self.emit({'event': 'launch_error', 'detail': refusal.reason})
            return
        session = None
        try:
            session, rollback = self._decide_tier(game, tier)
            with self.lock:             # held until `pending` is set: a guest that answers at once finds it there
                if self.match is not None or self.pending is not None:
                    self._drop_game(session)
                    self.emit({'event': 'launch_error', 'detail': 'a match is already running'})
                    return
                options = self.room.lobby.game.game_options if self.room.lobby.game is not None else ''
                info = self.room.lobby_launch(need_ready=need_ready, delay=net.get('delay') or 0,
                                              digest_every=net.get('digest_every', Settings.digest_every),
                                              redundancy=net.get('redundancy', Settings.redundancy), rollback=rollback)
                if isinstance(info, Refusal):
                    self._drop_game(session)
                    self.emit({'event': 'launch_error', 'detail': info.reason})
                    return
                self.pending = {'info': info, 'game': game, 'values': values, 'session': session,
                                'net': {**net, 'options': options, 'sharing': info.sharing, **self._tier_settings(rollback)}}
        except RoomError as error:
            self._drop_game(session)
            self.emit({'event': 'launch_error', 'detail': error.reason})
            return
        except BaseException:
            self._drop_game(session)
            raise
        self.emit({'event': 'launching', 'match_id': info.match_id, 'seats': info.seats, 'names': list(info.names),
                   'tier': _tier_name(rollback), 'prediction': rollback})

    def _guest_launch(self, message: dict) -> None:
        with self.lock:
            pending = self.pending
            if pending is None or pending['match_id'] != message.get('match_id'):
                return
            self.pending = None
        try:
            game = self._game_config(message)
            settings = test_settings(pending['settings'], {**self.test_values, **(message.get('test_settings') or {})}, self.tests)
            self._run_match(pending['match_id'], game, settings, self._link(), False)
        except Exception as error:
            self.room.launched(pending['match_id'], control.LAUNCHED_FAILED)
            self.emit({'event': 'launch_error', 'match_id': pending['match_id'],
                       'detail': f'the game could not be started: {type(error).__name__}'})
            return
        self.room.launched(pending['match_id'], control.LAUNCHED_READY)

    # ---- running ----

    def from_converter(self) -> None:
        try:
            for kind, payload in self.reader.leftover:
                self._channel_message(kind, payload)
            while True:
                chunk = os.read(self.fd_in, 65536)
                if not chunk:
                    break
                for kind, payload in self.reader.feed(chunk):
                    self._channel_message(kind, payload)
        except Exception:       # a closed channel, a broken one, a message that is not what it should be: the converter is gone
            pass
        self.finished.set()

    def _channel_message(self, kind: int, payload: bytes) -> None:
        if kind == channel.CALL:
            message = json.loads(payload.decode('utf-8'))
            if isinstance(message, dict):
                self.call(message)

    def run(self) -> int:
        if not self.open_room():
            return 2
        threading.Thread(target=self.handle_inbox, name='netplay-room-inbox', daemon=True).start()
        threading.Thread(target=self.from_converter, name='netplay-room-channel', daemon=True).start()
        self.finished.wait()
        match = self.match
        if match is not None:           # the converter is gone or the room was closed: this seat leaves, its game stops by itself
            match.driver.stop()
            if not match.finished.wait(END_WAIT):
                match.session.process.kill()
        with self.lock:
            pending, self.pending = self.pending, None
        self._drop_game(pending.get('session') if pending else None)         # a game started for a launch that never happened
        self.room.close()
        self.inbox.put(('stop', None))
        self.emit({'event': 'room_closed'})
        return self.exit_code


def run_room(config: dict, reader: channel.Reader, writer: channel.Writer, fd_in: int) -> int:
    try:
        worker = RoomWorker(config, reader, writer, fd_in)
    except (KeyError, ValueError, TypeError):
        writer.send(channel.EVENT, json.dumps({'event': 'room_error', 'detail': 'the room settings are not what they should be'}).encode('utf-8'))
        return 2
    return worker.run()
