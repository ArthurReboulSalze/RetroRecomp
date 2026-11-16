"""The delay-lockstep driver: one per player, between that player's game (a pipe) and the other seats (a link).

The rule of the delay tier: the controls a player's game reports before frame F are stamped for frame F + D, sent
to every other seat, and frame F runs, on every PC, only when every seat's record for F is known. A frame never
runs on a guess: a record that is late makes the game wait ("Waiting for <name>" after a moment), and it resumes
by itself when the record arrives. D is at least 1, the price of a driver outside the game.

What one driver does, in one thread that sleeps on a queue (the game's messages, the link's packets, a tick):

* start: reads HELLO, refuses what stage 1 cannot do, sends SETUP (seat, ports, no snapshot ring, the host's
  options). With no delay given, the seats first measure their links (PING/PONG), each guest tells the host its
  worst one, and the host chooses D for everyone (`input_records.choose_delay`) and says it in its input packets;
* frames: one record per LOCAL, RUN for the next frame as soon as it is complete; every `digest_every` frames it
  asks the game for its digest and puts it in its packets; two seats whose digests of one frame differ are out
  of step, and the match stops for everyone (`_desync`, the one place that decides what a desync does);
* pause: a pause bit that appears in a seat's record of frame G (it was clear at G - 1) pauses every seat before
  G runs, since every seat holds the same records. The seat that paused, or the host, resumes: its packets say
  "resume the pause of frame G" until frames move on;
* time sync: packets carry the sender's frame; a game ahead of the slowest other seat by more than half a frame
  is slowed with PACE, by at most 2 %;
* the end: the host stops (BYE to all, STOP to every game), a seat's game or pipe goes (the match ends for all:
  stage 1 has no "continue without him"), a seat stays silent past `drop_after`, or `last_frame` is reached.

Seat N plays port N (one controller per player); the seat mapper for shared controls is a later stage.
Nothing here measures speed: `stats` counts events (late frames, waits, packets), never durations.
"""
from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import time
from typing import Callable

from . import input_records as wire
from . import session_pipe as pipe
from .session_game import SessionGame
from .session_transport import SeatLink

HOST = 0
TICK = 0.01                  # the longest sleep of the loop, seconds
KEEP_ALIVE = 0.02            # a packet at least this often once the match runs (records repeated, link measured)
PROBE_EVERY = 0.025
PING_EVERY = 0.25
PACE_EVERY = 0.25
HELLO_WITHIN = 15.0
CLOSE_WITHIN = 12.0          # a stopped game shows its message about 3.5 s, then closes
LINGER = 3.0                 # after the last frame: time left to the others to get the last records and digest
BYE_COPIES = 3


@dataclass
class Settings:
    seat: int                           # 0 is the host
    seats: int
    names: tuple = ()                   # per seat, for the notices ("Paused by <name>")
    delay: int | None = None            # frames; None: measured and chosen by the host
    digest_every: int = 60
    redundancy: int = 3                 # records repeated in every packet, acknowledged or not
    options: str = ''                   # the host's run-changing options, "key=value" lines
    waiting_after: float = 1.0          # seconds a game waits for a record before "Waiting for <name>"
    drop_after: float = 10.0            # seconds of silence after which a seat is gone
    probe_seconds: float = 0.5
    last_frame: int | None = None       # the match ends for every seat once this many frames ran
    # Test input sources. `local_source(frame, word, system)` gives the (word, system bits) recorded in place of
    # what the game reported (a hidden game has no player); `words_filter(frame, words)` changes what this seat's
    # game is told to run, which is how a test forces two games out of step.
    local_source: Callable | None = None
    words_filter: Callable | None = None


class LockstepDriver:
    def __init__(self, game: SessionGame, link: SeatLink, settings: Settings):
        self.game, self.link, self.settings = game, link, settings
        self.seat, self.seats = settings.seat, settings.seats
        self.peers = [seat for seat in range(self.seats) if seat != self.seat]
        self.names = tuple(settings.names) or tuple(f'Player {seat + 1}' for seat in range(self.seats))
        self.delay = settings.delay
        self.hello: pipe.Hello | None = None
        self.outcome: str | None = None         # why the match ended, once it has
        self.detail = ''
        self.exit_reason: int | None = None     # the game's EXIT (RRHK_EXIT_*)
        self.exit_code: int | None = None
        self.history: list[tuple] = []          # the port words of every frame this game was told to run
        self.digests: dict[int, int] = {}       # frame -> this game's digest after it
        self.desync: tuple | None = None        # (frame, seat, mine, theirs)
        self.pauses: list[tuple] = []           # (frame, seat that paused, seat that resumed or None)
        self.measured: tuple | None = None      # (one way ms, jitter ms) of this seat's worst link, when probed
        self.stats = {'runs': 0, 'late_frames': 0, 'waits': 0, 'packets_sent': 0, 'packets_received': 0,
                      'packets_ignored': 0, 'records_repeated': 0, 'pace_changes': 0, 'pace_ppm_max': 0,
                      'resumes_refused': 0, 'final_compared': False}
        self.next_run = 0
        self.game_frame = -1                    # the frame of the game's latest LOCAL
        self.paused: tuple | None = None        # (frame, [seats that paused])
        self._events: queue.Queue = queue.Queue()
        self._progress = threading.Condition()
        self._thread: threading.Thread | None = None
        self._phase = 'hello'                   # hello, probe, play, linger, closing, done
        self._records: list[list] = [[] for _ in range(self.seats)]
        self._pending_locals: list = []
        self._start_at = 0.0
        self._holding = True                    # until the start: LOCALs are kept, no frame is given
        self._hold_ms = 0
        self._game_system = 0
        self._host_saw_pause = False
        self._resumed: set[int] = set()
        self._my_resume = wire.NONE
        self._peer_resume = {seat: wire.NONE for seat in self.peers}
        self._peer_ack = {seat: -1 for seat in self.peers}
        self._peer_frame = {seat: None for seat in self.peers}
        self._peer_digests = {seat: {} for seat in self.peers}
        self._peer_gone: set[int] = set()
        self._latest_digest: tuple | None = None
        self._rtt = {seat: [] for seat in self.peers}
        self._one_way_ms = {seat: 0.0 for seat in self.peers}
        self._measures: dict[int, tuple] = {}
        self._last_heard: dict[int, float] = {}
        self._last_sent = self._last_ping = self._last_probe = self._last_pace = 0.0
        self._advantage = 0.0
        self._ppm = 0
        self._blocked_since: float | None = None
        self._blocked_on = 0
        self._waiting_noticed = False
        self._byes: list = []
        self._bye_at = 0.0
        self._game_gone = False
        self._stop_sent = False
        self._deadline = 0.0
        self._linger_until = 0.0

    # ---- for the caller (any thread) ----

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name=f'netplay-lockstep-{self.seat}', daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def stop(self) -> None:
        """Ends the match for everyone: the host closing the game, or this guest leaving."""
        self._events.put(('call', self._stop_asked))

    def resume(self) -> None:
        """Asks to resume a pause; honoured for the seat that paused and for the host (`stats['resumes_refused']`)."""
        self._events.put(('call', self._resume_asked))

    def wait_for(self, predicate: Callable[['LockstepDriver'], bool], timeout: float) -> bool:
        """Sleeps until `predicate(driver)` holds or the driver is done; False when `timeout` passed first."""
        with self._progress:
            return self._progress.wait_for(lambda: predicate(self) or self._phase == 'done', timeout) and predicate(self)

    def reached(self, frame: int, timeout: float) -> bool:
        return self.wait_for(lambda driver: driver.next_run >= frame, timeout)

    @property
    def done(self) -> bool:
        return self._phase == 'done'

    # ---- the loop ----

    def _loop(self):
        started = time.monotonic()
        self._last_heard = {seat: started for seat in self.peers}
        self._deadline = started + HELLO_WITHIN
        self.link.open(lambda source, data: self._events.put(('net', source, data)))
        self.game.attach(lambda message: self._events.put(('game', message)))
        try:
            while self._phase != 'done':
                try:
                    event = self._events.get(timeout=TICK)
                except queue.Empty:
                    event = None
                handled = 0
                while event is not None:
                    self._dispatch(event)
                    handled += 1
                    try:
                        event = self._events.get_nowait() if handled < 256 else None
                    except queue.Empty:
                        event = None
                now = time.monotonic()
                self._step(now)
                self._timers(now)
                with self._progress:
                    self._progress.notify_all()
        except Exception as error:      # a fault of the driver ends the match for everyone, it is not hidden
            self.outcome, self.detail = 'error', f'{type(error).__name__}: {error}'
            for seat in self.peers:
                self.link.send(seat, wire.encode_bye(self.seat, wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT, 0))
            self._finalize()
            raise
        finally:
            with self._progress:
                self._progress.notify_all()

    def _dispatch(self, event):
        if event[0] == 'game':
            self._from_game(event[1])
        elif event[0] == 'net':
            self._from_link(event[1], event[2])
        else:
            event[1]()

    def _tell(self, data: bytes) -> None:
        if not self._game_gone:
            self.game.send(data)

    # ---- the game's messages ----

    def _from_game(self, message):
        if message is None:
            self._game_gone = True
            if self.outcome is None:
                closed = self.exit_reason == pipe.EXIT_CLOSED
                self.detail = self.detail or (self.game.broken or 'the game closed its pipe')
                self._end('game_closed' if closed else 'pipe_lost', None,
                          wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT)
            return
        kind, payload = message
        if kind == pipe.MSG_HELLO:
            self._hello(pipe.parse_hello(payload))
        elif kind == pipe.MSG_LOCAL:
            self._local(*pipe.parse_local(payload))
        elif kind == pipe.MSG_DIGEST_OF:
            frame, value = pipe.parse_digest_of(payload)
            self.digests[frame] = value
            self._latest_digest = (frame, value)
            self._compare(frame)
        elif kind == pipe.MSG_REFUSED:
            code, text = pipe.parse_refused(payload)
            self.detail = f'the game refused ({code}): {text}'
            self._end('refused', None, wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT)
        elif kind == pipe.MSG_EXIT:
            self.exit_reason = pipe.parse_exit(payload)
        # DONE: the frame ran; its cost is not read here (nothing in this stage measures speed)

    def _hello(self, hello: pipe.Hello):
        if self.hello is not None:
            return
        self.hello = hello
        try:
            pipe.check_hello(hello, self.seats)
        except pipe.Refused as error:
            self.detail = str(error)
            self._end('refused', None, wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT)
            self.game.close_pipe()              # the game sees its pipe close and ends by itself
            return
        self._tell(pipe.setup(self.seat, self.seats, 0, guest=self.seat != HOST, options=self.settings.options))
        if self.delay is not None:
            self._set_delay(self.delay, time.monotonic())
        else:
            self._phase = 'probe'
            self._deadline = time.monotonic() + self.settings.drop_after + self.settings.probe_seconds

    def _set_delay(self, delay: int, start_at: float):
        self.delay = max(1, min(wire.MAX_DELAY, delay))
        for seat in range(self.seats):          # nobody's controls exist before frame D: neutral for every seat
            self._records[seat] = [(0, 0)] * self.delay
        self._peer_ack = {seat: self.delay - 1 for seat in self.peers}
        self._start_at = start_at
        self._holding = True
        self._phase = 'play'

    def _local(self, frame: int, word: int, system: int):
        if self._phase in ('hello', 'probe') or self._holding:
            self._pending_locals.append((frame, word, system))     # kept in order until the match starts
            return
        if self.settings.local_source is not None:
            word, system = self.settings.local_source(frame, word, system)
            word, system = word & 0xffff, system & 0xffff
        self.game_frame = max(self.game_frame, frame)
        self._game_system = system              # the latest LOCAL of a frame says where its system bits are now
        if self.paused is not None and self.seat == HOST and frame >= self.paused[0]:
            # The host did not pause: his own Pause pressed and released during the pause is his word to resume.
            if system & pipe.SYS_PAUSE:
                self._host_saw_pause = True
            elif self._host_saw_pause:
                self._my_resume = self.paused[0]
        mine = self._records[self.seat]
        if frame + self.delay == len(mine):     # first write wins: a repeated LOCAL of a frame never changes its record
            mine.append((word, system))
            self._send_inputs(time.monotonic())

    # ---- the link's packets ----

    def _from_link(self, source: int, data: bytes):
        packet = wire.decode(data, self.seats)
        if packet is None or packet.seat != source or source == self.seat:
            self.stats['packets_ignored'] += 1
            return
        self.stats['packets_received'] += 1
        now = time.monotonic()
        self._last_heard[source] = now
        if packet.kind == wire.PING:
            self._send(source, wire.encode_pong(self.seat, packet.time))
        elif packet.kind == wire.PONG:
            rtt = ((int(now * 1e6) - packet.time) & 0xffffffff) / 1000.0
            if rtt < 60000.0:
                self._rtt[source].append(rtt)
                del self._rtt[source][:-64]
                previous = self._one_way_ms[source]
                self._one_way_ms[source] = rtt / 2 if not previous else previous * 0.75 + rtt / 8
        elif packet.kind == wire.MEASURE:
            self._measures[source] = (packet.one_way_ms, packet.jitter_ms)
        elif packet.kind == wire.BYE:
            self._peer_left(source, packet.reason)
        elif packet.kind == wire.INPUT:
            self._input(source, packet, now)

    def _input(self, source: int, packet: wire.Packet, now: float):
        if self.delay is None:
            if source != HOST or not packet.delay or self._phase != 'probe':
                return
            # The host started when it sent this; a guest nearer than the farthest one waits the difference.
            self._set_delay(packet.delay, now + max(0.0, packet.hold_ms - self._one_way_ms[HOST]) / 1000.0)
        self._peer_frame[source] = (packet.sender_frame, now)
        if packet.ack_frame != wire.NONE:
            self._peer_ack[source] = max(self._peer_ack[source], min(packet.ack_frame, len(self._records[self.seat]) - 1))
        self._peer_resume[source] = packet.resume_frame
        for section in packet.sections:
            if section.seat != source:          # a seat speaks for itself only (no forwarding in stage 1)
                continue
            known = self._records[source]
            for offset, record in enumerate(section.records):
                frame = section.first_frame + offset
                if frame == len(known):
                    known.append(record)
                elif frame < len(known):
                    self.stats['records_repeated'] += 1     # first write wins
        if packet.digest_frame != wire.NONE:
            digests = self._peer_digests[source]
            if packet.digest_frame not in digests:
                digests[packet.digest_frame] = packet.digest
                for frame in sorted(digests)[:-16]:
                    del digests[frame]
                self._compare(packet.digest_frame)

    def _send(self, seat: int, data: bytes):
        self.stats['packets_sent'] += 1
        self.link.send(seat, data)

    def _send_inputs(self, now: float):
        mine = self._records[self.seat]
        digest_frame, digest = self._latest_digest or (wire.NONE, 0)
        for seat in self.peers:
            # from the first record the peer did not acknowledge, and at least the last `redundancy` ones
            first = max(0, min(self._peer_ack[seat] + 1, len(mine) - self.settings.redundancy))
            records = mine[first:first + wire.MAX_RECORDS]
            self._send(seat, wire.encode_input(
                self.seat, max(self.game_frame, 0), len(self._records[seat]) - 1, [(self.seat, first, records)],
                delay=self.delay if self.seat == HOST else 0, hold_ms=self._hold_ms, resume_frame=self._my_resume,
                digest_frame=digest_frame, digest=digest))
        self._last_sent = now

    # ---- frames ----

    def _step(self, now: float):
        if self._phase != 'play':
            return
        if self._holding:
            if now < self._start_at:
                return                              # no frame before the start the host set
            self._holding = False
            pending, self._pending_locals = self._pending_locals, []
            for local in pending:
                self._local(*local)
        while self._phase == 'play':
            self._check_resume()
            frame = self.next_run
            if self.settings.last_frame is not None and frame >= self.settings.last_frame:
                self._phase = 'linger'
                self._linger_until = now + LINGER
                return
            if self.paused is not None:
                return
            missing = [seat for seat in range(self.seats) if len(self._records[seat]) <= frame]
            if missing:
                if self.game_frame >= frame and self._blocked_since is None:     # the game is waiting for this frame
                    self._blocked_since, self._blocked_on = now, missing[0]
                return
            if frame not in self._resumed:
                pausers = [seat for seat in range(self.seats)
                           if self._records[seat][frame][1] & pipe.SYS_PAUSE
                           and not (frame and self._records[seat][frame - 1][1] & pipe.SYS_PAUSE)]
                if pausers:
                    self.paused = (frame, pausers)
                    self._host_saw_pause = False
                    self.pauses.append((frame, pausers[0], None))
                    self._tell(pipe.pause(True, self.names[pausers[0]]))
                    continue
            words = tuple(self._records[seat][frame][0] for seat in range(self.seats))
            if self.settings.words_filter is not None:
                words = tuple(self.settings.words_filter(frame, words))
            if frame and self.game_frame >= frame:
                self.stats['late_frames'] += 1      # the game had asked for this frame before it could be given
            if self._waiting_noticed:
                self._tell(pipe.notice(pipe.NOTICE_RESUMED))
                self._waiting_noticed = False
            self._blocked_since = None
            self._tell(pipe.run(frame, words))
            self.history.append(words)
            self.stats['runs'] += 1
            self.next_run = frame + 1
            if self.next_run % self.settings.digest_every == 0 or self.next_run == self.settings.last_frame:
                self._tell(pipe.digest())           # answered after this frame ran, before the next one

    def _check_resume(self):
        if self.paused is None:
            return
        frame, pausers = self.paused
        if self.seat in pausers and self.game_frame >= frame and not self._game_system & pipe.SYS_PAUSE:
            self._my_resume = frame                 # the one who paused closed his menu or released Pause
        by = self.seat if self._my_resume == frame else next(
            (seat for seat in self.peers if self._peer_resume[seat] == frame and (seat in pausers or seat == HOST)), None)
        if by is None:
            return
        self._resumed.add(frame)
        self.paused = None
        self.pauses[-1] = (frame, self.pauses[-1][1], by)
        self._tell(pipe.pause(False))
        self._send_inputs(time.monotonic())

    def _resume_asked(self):
        if self.paused is not None and (self.seat == HOST or self.seat in self.paused[1]):
            self._my_resume = self.paused[0]
        else:
            self.stats['resumes_refused'] += 1

    # ---- out of step ----

    def _compare(self, frame: int):
        mine = self.digests.get(frame)
        if mine is None or self.desync is not None:
            return
        for seat in self.peers:
            theirs = self._peer_digests[seat].get(frame)
            if theirs is not None and theirs != mine:
                self._desync(frame, seat, mine, theirs)
                return
        final = self.settings.last_frame
        if final is not None and frame == final - 1 and all(frame in self._peer_digests[seat] for seat in self.peers):
            self.stats['final_compared'] = True

    def _desync(self, frame: int, seat: int, mine: int, theirs: int):
        """Two seats computed different games. The one place that decides what follows: in stage 1 the match stops
        for everyone. A later stage tries first to recover here (pause everyone, resynchronise, and stop only if
        that fails)."""
        self.desync = (frame, seat, mine, theirs)
        self.detail = f'out of step at frame {frame}: seat {self.seat + 1} and seat {seat + 1} differ'
        self._end('desync', pipe.STOP_DESYNC, wire.BYE_DESYNC)

    def _desync_reported(self, seat: int):
        """Another seat found the games out of step (the same decision point as `_desync`)."""
        self.detail = self.detail or f'seat {seat + 1} reported the games out of step'
        self._end('desync', pipe.STOP_DESYNC, None)

    # ---- the end ----

    def _stop_asked(self):
        if self.seat == HOST:
            self._end('ended', pipe.STOP_ENDED, wire.BYE_ENDED)
        else:
            self._end('left', pipe.STOP_ENDED, wire.BYE_LEFT)

    def _peer_left(self, seat: int, reason: int):
        self._peer_gone.add(seat)
        if self.outcome is not None or self._phase in ('linger', 'closing'):
            return
        if reason == wire.BYE_DESYNC:
            self._desync_reported(seat)
        elif seat == HOST and reason == wire.BYE_ENDED:
            self._end('ended', pipe.STOP_ENDED, None)
        elif seat == HOST:
            self._end('host_closed', pipe.STOP_HOST_CLOSED, None)
        else:
            self._tell(pipe.notice(pipe.NOTICE_LEFT, self.names[seat]))
            self._end('seat_left', pipe.STOP_ENDED, None)

    def _end(self, outcome: str, stop_reason: int | None, bye_reason: int | None):
        if self.outcome is not None:
            return
        self.outcome = outcome
        now = time.monotonic()
        if bye_reason is not None:
            packet = wire.encode_bye(self.seat, bye_reason, self.next_run)
            self._byes = [packet] * BYE_COPIES
        self._close_game(stop_reason, now)

    def _close_game(self, stop_reason: int | None, now: float):
        if stop_reason is not None and not self._stop_sent:
            self._tell(pipe.stop(stop_reason))
            self._stop_sent = True
        self._phase = 'closing'
        self._deadline = now + CLOSE_WITHIN

    def _finalize(self):
        self.exit_code = self.game.finish(timeout=5.0)
        self.link.close()
        self._phase = 'done'

    # ---- time ----

    def _timers(self, now: float):
        if self._phase == 'done':
            return
        if self._phase == 'hello':
            if now >= self._deadline:
                self.detail = 'no HELLO from the game'
                self._end('pipe_lost', None, wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT)
            self._ping(now)
            return
        if self._phase == 'probe':
            self._probe(now)
        if self._phase in ('play', 'linger', 'closing') and self.delay is not None and self.outcome in (None, 'ended'):
            if now - self._last_sent >= KEEP_ALIVE:
                self._send_inputs(now)          # also while paused, waiting or closing: records repeated, link heard
        if self._phase == 'play':
            self._ping(now)
            self._waiting(now)
            self._silence(now)
            self._pace(now)
        elif self._phase == 'linger':
            final = self.settings.last_frame - 1
            served = all(self._peer_ack[seat] >= final or seat in self._peer_gone for seat in self.peers)
            if (served and self.stats['final_compared']) or now >= self._linger_until:
                self.outcome = 'ended'
                self._close_game(pipe.STOP_ENDED, now)
        if self._phase == 'closing':
            if self._byes and now >= self._bye_at:
                for seat in self.peers:
                    self._send(seat, self._byes[-1])
                self._byes.pop()
                self._bye_at = now + 0.02
            if not self._byes and (self._game_gone or now >= self._deadline):
                self._finalize()

    def _ping(self, now: float):
        if now - self._last_ping >= PING_EVERY:
            self._last_ping = now
            for seat in self.peers:
                self._send(seat, wire.encode_ping(self.seat, int(now * 1e6)))

    def _probe(self, now: float):
        """Before frame 0, with no delay given: measure, tell the host, and the host chooses for everyone."""
        if now - self._last_probe < PROBE_EVERY:
            return
        self._last_probe = now
        if now >= self._deadline:
            self.detail = 'the seats could not measure their links'
            self._end('seat_silent', pipe.STOP_ENDED, wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT)
            return
        for seat in self.peers:
            self._send(seat, wire.encode_ping(self.seat, int(now * 1e6)))
        if self.measured is None:
            enough = all(len(self._rtt[seat]) >= 5 for seat in self.peers)
            first = min((len(samples) for samples in self._rtt.values()), default=0)
            if not enough or first * PROBE_EVERY < self.settings.probe_seconds:
                return
            one_way = max(sum(samples) / len(samples) / 2 for samples in self._rtt.values())
            jitter = max((max(samples) - min(samples)) / 2 for samples in self._rtt.values())
            self.measured = (one_way, jitter)
        if self.seat != HOST:
            self._send(HOST, wire.encode_measure(self.seat, *self.measured))
            return
        if all(seat in self._measures for seat in self.peers):
            worst = [self.measured, *self._measures.values()]
            one_way, jitter = max(item[0] for item in worst), max(item[1] for item in worst)
            self._hold_ms = int(max(self._one_way_ms.values()))
            delay = wire.choose_delay(one_way, jitter, self.hello.frame_seconds * 1000.0)
            # The host starts once its word had the time to reach the farthest guest.
            self._set_delay(delay, now + self._hold_ms / 1000.0)
            self._send_inputs(now)

    def _waiting(self, now: float):
        if (self._blocked_since is not None and not self._waiting_noticed and self.paused is None
                and now - self._blocked_since >= self.settings.waiting_after):
            self._tell(pipe.notice(pipe.NOTICE_WAITING, self.names[self._blocked_on]))
            self._waiting_noticed = True
            self.stats['waits'] += 1

    def _silence(self, now: float):
        for seat in self.peers:
            if now - self._last_heard[seat] >= self.settings.drop_after:
                self.detail = f'nothing from seat {seat + 1} for {self.settings.drop_after:g} s'
                self._tell(pipe.notice(pipe.NOTICE_LEFT, self.names[seat]))
                self._end('seat_silent', pipe.STOP_ENDED, wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT)
                return

    def _pace(self, now: float):
        if now - self._last_pace < PACE_EVERY:
            return
        self._last_pace = now
        # Where each other seat's game is now: the frame its last packet said, plus the packet's way here and, for at
        # most one frame, the time since it came (a seat that waits sends no new frame).
        period = self.hello.frame_seconds
        frames = [self._peer_frame[seat][0] + self._one_way_ms[seat] / (period * 1000.0)
                  + min(1.0, (now - self._peer_frame[seat][1]) / period)
                  for seat in self.peers if self._peer_frame[seat] is not None]
        if not frames or self.paused is not None or self.game_frame < 0:
            return
        self._advantage = self._advantage * 0.5 + (self.game_frame - min(frames)) * 0.5
        ppm = wire.pace_for(self._advantage)
        if ppm != self._ppm:
            self._ppm = ppm
            self._tell(pipe.pace(ppm))
            self.stats['pace_changes'] += 1
            self.stats['pace_ppm_max'] = max(self.stats['pace_ppm_max'], ppm)
