"""The delay-lockstep driver: one per player, between that player's game (a pipe) and the other seats (a link).

The rule of the delay tier: the controls a player's game reports before frame F are stamped for frame F + D, sent
to every other seat, and frame F runs, on every PC, only when every seat's record for F is known. A frame never
runs on a guess: a record that is late makes the game wait ("Waiting for <name>" after a moment), and it resumes
by itself when the record arrives. D is at least 1, the price of a driver outside the game.

Topology (stage 1b): a **star**. Guests talk only to the host; the host forwards every seat's records to the
others (its packets carry one section per other seat), so a room needs one listening endpoint. `Settings.topology
= 'mesh'` keeps the old direct links, for tests. The host is the reference clock, the one that compares digests of
every guest, and the one that decides the start, the delay and what a departure means.

What one driver does, in one thread that sleeps on a queue (the game's messages, the link's packets, a tick):

* start: reads HELLO, refuses what stage 1 cannot do, sends SETUP (seat, ports, no snapshot ring, the host's
  options), then asks its game for the **boot digest** (state after SETUP, before frame 0). A guest sends it to the
  host; the host compares them all with its own and refuses the launch, with a reason, if one differs. With no
  delay given, the seats also measure their links (PING/PONG), each guest tells the host its worst one, and the
  host chooses D for everyone (`input_records.choose_delay`; through the host a guest's records travel two links)
  and says it in its input packets, which is also its word to start;
* frames: one record per LOCAL, RUN for the next frame as soon as it is complete; every `digest_every` frames it
  asks the game for its digest and puts it in its packets; two seats whose digests of one frame differ are out
  of step, and the match stops for everyone (`_desync`, the one place that decides what a desync does);
* pause: a pause bit that appears in a seat's record of frame G (it was clear at G - 1) pauses every seat before
  G runs, since every seat holds the same records. The seat that paused, or the host, resumes: its packets say
  "resume the pause of frame G" until frames move on;
* time sync: packets carry the sender's frame; `time_sync.PaceController` turns them into a steady advantage over
  the slowest seat it hears and slows its own game with PACE (small steps, at most 2 %, never negative);
* the end: the host stops (BYE to all, STOP to every game), a seat's game or pipe goes (the match ends for all:
  stage 1 has no "continue without him"; in a star the host tells the others who went), a seat stays silent past
  `drop_after`, or `last_frame` is reached.

The seat mapper (`seat_map`) turns the records of every confirmed frame into the port words the game is told to run: seat N plays
port N ("one controller per player", the default) or the seats share the controls of port 0 ("everyone" OR-merged, or "turns" with
a token that records pass: `Settings.sharing`). Every PC maps the same records, so every game gets the same words.
Nothing here measures speed: `stats` counts events (late frames, waits, packets), never durations.

What a seat that is not honest can do (`.build/multiplayer/SECURITY_REVIEW.md`, "Security fixes before the transport"):
the seat of a packet is decided in one place (`_proven_seat`: the transport must give the *proven* seat as `source`);
a record is taken only inside a window ahead of the match (`RECORD_WINDOW`), the event queue and every seat's packet
rate are bounded (`_net_in`), a seat that talks but gives no record is dropped as a silent one (`_stalled`), a PONG is
taken only for a PING of ours and a measure is checked against the host's own, a guest's BYE_DESYNC is a claim the host
checks with its own digests (`_claim_desync`), and records, history and digests are trimmed behind the match.

The rollback tier (`rollback.RollbackDriver`, for games that keep snapshots, when `Settings.rollback` asks for it) is a
subclass: it replaces how frames are given (`_step`) and which frame a digest is of, through the few hooks marked
"rollback tier" below. Everything else, the comparison of digests and what a desync does included, is this class's.
"""
from __future__ import annotations

from dataclasses import dataclass
import collections
import queue
import statistics
import threading
import time
from typing import Callable

from . import input_records as wire
from . import seat_map
from . import session_pipe as pipe
from .session_game import SessionGame
from .limits import TokenBucket
from .session_transport import SeatLink
from .time_sync import PaceController

HOST = 0
TICK = 0.01                  # the longest sleep of the loop, seconds
KEEP_ALIVE = 0.02            # a packet at least this often once the match runs (records repeated, link measured)
PROBE_EVERY = 0.025
PING_EVERY = 0.25
PACE_EVERY = 0.25
HELLO_WITHIN = 15.0
GATE_WITHIN = 20.0           # from SETUP to the start: boot digests, measures, the host's word
CLOSE_WITHIN = 12.0          # a stopped game shows its message about 3.5 s, then closes
RESTART_FOLD = 0x9e3779b97f4a7c15      # what a restart adds to the history digest's fold
STATE_SAVE_FOLD = 0xc2b2ae3d27d4eb4f   # and a save of the match's state (the host's F8)
STATE_LOAD_FOLD = 0x165667b19e3779f9   # and a load of it (the host's F9)
STICKS_FOLD = 0x27d4eb2f165667c5       # the sticks of a frame fold in with this multiplier (session ABI 7)
ACTION_FOLDS = {pipe.RUN_RESET: RESTART_FOLD, pipe.RUN_STATE_SAVE: STATE_SAVE_FOLD, pipe.RUN_STATE_LOAD: STATE_LOAD_FOLD}
def link_estimate(samples) -> tuple[float, float]:
    """(one way, jitter) in ms of a link from its round trips: half the median, and half the spread from the median to the
    90th percentile. A lone spike (a Wi-Fi hiccup, a busy PC during the probe) moves neither: on 17 Nov 2026 the worst of a
    few samples made a LAN room with 150 ms of simulated round trip choose a delay of 10 frames instead of 2."""
    ordered = sorted(samples)
    middle = statistics.median(ordered)
    high = ordered[min(len(ordered) - 1, int(0.9 * (len(ordered) - 1)))]
    return middle / 2, max(0.0, high - middle) / 2


LINGER = 3.0                 # after the last frame: time left to the others to get the last records and digest
CLOSING_MIN = 0.5            # a seat that ended well goes on sending this long: its last digest may have been lost
BYE_COPIES = 3
EVENT_QUEUE_MAX = 2048       # packets waiting for the loop; the newest beyond this are dropped and counted
EVENT_QUEUE_HEADROOM = 256   # room above it for the game's messages and the caller's calls, which are never dropped
PACKET_RATE_MIN = 240.0      # packets a second one seat may send before its excess is dropped (see `_packet_rate`)
FRAME_WINDOW = 2 * wire.MAX_DELAY + 60      # a peer's frame further than this from ours is not believed (time sync)
RECORD_WINDOW = 2 * wire.MAX_RECORDS        # records are taken up to next_run + delay + this: an honest seat is never further
DIGEST_WINDOW = 64           # a digest is taken for a frame up to next_run + delay + this
TRIM_BEHIND = 64             # frames kept behind the one every seat holds, for repeats and for the pause rule
MAX_PREDICTION = 30          # the rollback tier: the most frames a game may be ahead of the confirmed ones (`Settings.rollback`)
ACK_LAG_MAX = 1024           # a peer that acknowledges nothing for this many frames does not hold records back any longer
DIGESTS_KEPT = 64            # without `keep_history`: the digests of this driver's last frames
MAX_RTT_MS = 2000.0          # a round trip above this is not a measure of a link (the PONG is refused)
MEASURE_SLACK_MS = 10.0      # a guest's measure of its link may exceed the host's own by half as much again (twice for the jitter), plus this
MAX_MEASURE_MS = 1000.0      # no measure counts above this
PING_MEMORY = 64             # the PING values sent to a peer that a PONG may still answer
STALL_GRACE = 3.0            # a guest waits this much longer for a seat it hears of only through the host (the host decides first)


@dataclass
class Settings:
    seat: int                           # 0 is the host
    seats: int
    names: tuple = ()                   # per seat, for the notices ("Paused by <name>")
    delay: int | None = None            # frames; None: measured and chosen by the host
    digest_every: int = 60
    redundancy: int = 3                 # records repeated in every packet, acknowledged or not
    options: str = ''                   # the host's run-changing options, "key=value" lines
    sharing: int = seat_map.PER_PLAYER  # seat_map: one controller per player, or the seats share port 0 (everyone / turns)
    rollback: int = 0                   # 0: the delay tier. k (1 to MAX_PREDICTION): the rollback tier with at most k frames run on a
                                        # prediction, for a game that keeps snapshots; any other game stays on the delay tier (`rollback.py`)
    rollback_required: bool = False     # a room's launch said rollback: a game that reports no snapshot refuses the match (it is never
                                        # quietly kept on the delay tier, since the host decided from its own game's HELLO)
    opposites: tuple = ()               # tests: (mask, mask) pairs of opposite directions the mapper cancels itself (the kit always does)
    waiting_after: float = 1.0          # seconds a game waits for a record before "Waiting for <name>"
    drop_after: float = 10.0            # seconds of silence after which a seat is gone
    probe_seconds: float = 0.5
    last_frame: int | None = None       # the match ends for every seat once this many frames ran
    topology: str = 'star'              # 'star': guests talk to the host only; 'mesh': every seat to every seat
    pace: bool = True                   # time sync on (a test turns it off to see what it prevents)
    keep_history: bool = False          # tests: keep every frame's words and every digest (else a rolling digest and the last few)
    packet_rate: float | None = None    # packets a second one seat may send (None: derived from the game's frame rate)
    desync_confirm: float = 2.0         # seconds the host waits for its own digests to confirm a guest's "out of step"
    clock_ppm: int = 0                  # tests: this game's clock is that many ppm off (negative: runs fast)
    # Test input sources. `local_source(frame, word, system)` gives the (word, system bits) recorded in place of
    # what the game reported (a hidden game has no player); `words_filter(frame, words)` changes what this seat's
    # game is told to run, which is how a test forces two games out of step.
    local_source: Callable | None = None
    words_filter: Callable | None = None


class RecordLog:
    """One seat's records by frame. `len` and `[frame]` speak in frames of the match; the frames far behind the one every
    seat holds are dropped (`trim`), so a long match does not grow."""
    __slots__ = ('_items', 'base')

    def __init__(self, items=()):
        self._items = list(items)
        self.base = 0

    def __len__(self) -> int:
        return self.base + len(self._items)

    def __getitem__(self, frame: int):
        index = frame - self.base
        if index < 0 or index >= len(self._items):
            raise IndexError(frame)
        return self._items[index]

    def append(self, record) -> None:
        self._items.append(record)

    def span(self, first: int, count: int) -> list:
        """The records from frame `first` (or the oldest kept, when that was trimmed), at most `count`."""
        start = max(first, self.base) - self.base
        return self._items[start:start + count]

    def trim(self, before: int) -> None:
        drop = min(before, len(self)) - self.base
        if drop >= TRIM_BEHIND:                 # in chunks: a list is cut rarely
            del self._items[:drop]
            self.base += drop


class LockstepDriver:
    def __init__(self, game: SessionGame, link: SeatLink, settings: Settings):
        self.game, self.link, self.settings = game, link, settings
        self.seat, self.seats = settings.seat, settings.seats
        self.star = settings.topology == 'star'
        if self.star and self.seat != HOST:
            self.peers = [HOST]                 # a guest talks to the host only
        else:
            self.peers = [seat for seat in range(self.seats) if seat != self.seat]
        self.guests = [seat for seat in range(self.seats) if seat != HOST]
        self._relays = self.star and self.seat == HOST      # the host forwards every seat's records
        given = list(settings.names)
        given += [f'Player {seat + 1}' for seat in range(len(given), self.seats)]
        # names are cleaned once, where they enter: what the notices, the details and the game get is printable ASCII, 16 characters
        self.names = tuple(pipe.clean_name(str(name)[:64]).decode('ascii') for name in given[:self.seats])
        self._preset = settings.delay if self.seat == HOST else None     # a guest takes the host's word
        self.delay: int | None = None
        self.hello: pipe.Hello | None = None
        self.outcome: str | None = None         # why the match ended, once it has
        self.detail = ''
        self.exit_reason: int | None = None     # the game's EXIT (RRHK_EXIT_*)
        self.exit_code: int | None = None
        if not seat_map.valid(settings.sharing):
            raise ValueError('a sharing mode that does not exist')
        self._seat_state = seat_map.start(settings.sharing, self.seats)
        self._turn_told: int | None = None      # the seat this game was last told holds the shared controls (turns)
        self.on_chat: Callable[[int, str], None] | None = None     # a line the player typed in the game: (phrase, text)
        self.chat_lines = 0                     # lines this game sent (counts only)
        self._request = 0                       # the control bits (a pass of the turn, a change of mode) the next record carries
        self.history: list[tuple] = []          # the port words of every frame this game was told to run (`keep_history`)
        self.history_frames = 0                 # how many frames it was told to run
        self.history_digest = 0                 # a running fold of all their words: two seats that ran the same have the same
        self.digests: dict[int, int] = {}       # frame -> this game's digest after it
        self.boot_digest: int | None = None     # this game's digest after SETUP, before frame 0
        self.desync: tuple | None = None        # (frame, seat, mine, theirs)
        self.pauses: list[tuple] = []           # (frame, seat that paused, seat that resumed or None)
        self.measured: tuple | None = None      # (one way ms, jitter ms) of this seat's worst link, when probed
        self.pace_trace: list[tuple] = []       # (next frame, median advantage, pace ppm), every time-sync round
        self.stats = {'runs': 0, 'late_frames': 0, 'waits': 0, 'packets_sent': 0, 'packets_received': 0,
                      'packets_ignored': 0, 'records_repeated': 0, 'records_forwarded': 0, 'pace_changes': 0,
                      'pace_ppm_max': 0, 'resumes_refused': 0, 'final_compared': False, 'packets_dropped_rate': 0,
                      'packets_dropped_queue': 0, 'records_beyond_window': 0, 'sections_refused': 0, 'pongs_refused': 0,
                      'measures_clamped': 0, 'desync_claims': 0, 'stalls': 0, 'requests_refused': 0}
        self.next_run = 0
        self.game_frame = -1                    # the frame of the game's latest LOCAL
        self.paused: tuple | None = None        # (frame, [seats that paused])
        self._events: queue.Queue = queue.Queue(maxsize=EVENT_QUEUE_MAX + EVENT_QUEUE_HEADROOM)
        self._admit = threading.Lock()          # the link's thread(s) against the counters and buckets of `_net_in`
        self._buckets: dict[int, TokenBucket] = {}
        self._desync_claims: dict[int, float] = {}      # the host: guest -> when it said the games were out of step
        self._progress = threading.Condition()
        self._thread: threading.Thread | None = None
        self._phase = 'hello'                   # hello, gate, play, linger, closing, done
        self._records: list[RecordLog] = [RecordLog() for _ in range(self.seats)]
        self._pending_locals: list = []
        self._start_at = 0.0
        self._holding = True                    # until the start: LOCALs are kept, no frame is given
        self._hold_ms = 0
        self._game_system = 0
        self._game_restart = False              # the game's restart bit in its latest LOCAL (a request on its rising edge)
        self.restarts: list[int] = []           # the frames this game was told to restart before (verified ones on rollback)
        self.sticks = False                     # the game reads sticks (its HELLO's CAP_AXES): the records carry them
        self._game_state = 0                    # the game's state bits in its latest LOCAL (a request on a rising edge)
        self._state_wanted = 0                  # the host's save or load waiting for a record (seat_map.SYS_STATE_*)
        self._state_record: int | None = None   # the record that carried the last one
        self.states: list = []                  # (frame, 'save' | 'load'): what this game was told to do with the match's state
        self._host_saw_pause = False
        self._resumed: set[int] = set()
        self._my_resume = wire.NONE
        self._peer_resume = {seat: wire.NONE for seat in self.peers}
        self._holds: dict[int, list] = {}       # peer -> per owner, the last frame of that owner's records it holds
        self._peer_frame = {seat: None for seat in self.peers}
        self._peer_digests = {seat: {} for seat in self.peers}
        self._peer_gone: set[int] = set()
        self._boots: dict[int, int] = {}        # the host: seat -> that seat's boot digest
        self._latest_digest: tuple | None = None
        self._rtt = {seat: [] for seat in self.peers}
        self._pings_sent = {seat: collections.deque(maxlen=PING_MEMORY) for seat in self.peers}
        self._one_way_ms = {seat: 0.0 for seat in self.peers}
        self._measures: dict[int, tuple] = {}
        self._last_heard: dict[int, float] = {}
        self._last_sent = self._last_ping = self._last_probe = self._last_pace = 0.0
        self._pace = PaceController()
        self._blocked_since: float | None = None
        self._blocked_on = 0
        self._waiting_noticed = False
        self._byes: list = []
        self._bye_at = 0.0
        self._game_gone = False
        self._stop_sent = False
        self._deadline = 0.0
        self._linger_until = 0.0
        self._boot_culprit = wire.NO_SEAT
        self._closing_not_before = 0.0
        self._local_at = 0.0                    # when the game's latest LOCAL (the start of its frame) came

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

    def pass_token(self, to: int | None = None) -> None:
        """Asks to pass the turn (input sharing): the token holder passes it to the next seat, the host may name any seat with
        `to`. The request travels in this seat's next record, so it takes effect on the same frame on every PC (`seat_map`)."""
        self._events.put(('call', lambda: self._ask(seat_map.request(self.settings.sharing, self.seat, target=to))))

    def set_sharing(self, mode: int) -> None:
        """The host only: a shared match goes to SHARED_ALL ("everyone") or SHARED_TURNS ("turns") on a confirmed frame."""
        self._events.put(('call', lambda: self._ask(seat_map.request(self.settings.sharing, self.seat, mode=mode))))

    def _ask(self, bits: int) -> None:
        if bits:
            self._request |= bits
        else:
            self.stats['requests_refused'] += 1

    def close_game_pipe(self) -> None:
        """Tests: this seat's worker loses its game (its end of the pipe closes)."""
        self.game.close_pipe()

    def wait_for(self, predicate: Callable[['LockstepDriver'], bool], timeout: float) -> bool:
        """Sleeps until `predicate(driver)` holds or the driver is done; False when `timeout` passed first."""
        with self._progress:
            return self._progress.wait_for(lambda: predicate(self) or self._phase == 'done', timeout) and predicate(self)

    def reached(self, frame: int, timeout: float) -> bool:
        return self.wait_for(lambda driver: driver.next_run >= frame, timeout)

    @property
    def done(self) -> bool:
        return self._phase == 'done'

    def snapshot(self) -> dict:
        """What a caller outside this thread may read now (the worker sends it to the converter), JSON-ready."""
        hello = self.hello
        return {
            'seat': self.seat, 'phase': self._phase, 'done': self._phase == 'done', 'outcome': self.outcome,
            'detail': self.detail, 'delay': self.delay, 'next_run': self.next_run, 'game_frame': self.game_frame,
            'paused': list(self.paused) if self.paused else None, 'stats': dict(self.stats),
            'sharing': seat_map.NAMES[self._seat_state.sharing], 'token': self._seat_state.token, 'tier': 'delay',
            'pauses': [list(item) for item in self.pauses], 'desync': list(self.desync) if self.desync else None,
            'measured': list(self.measured) if self.measured else None, 'boot_digest': self.boot_digest,
            'exit_code': self.exit_code, 'exit_reason': self.exit_reason, 'history_frames': self.history_frames,
            'restarts': list(self.restarts[-64:]), 'states': [list(item) for item in self.states[-64:]],
            'history_digest': f'{self.history_digest:016x}',
            'pace': {'ppm': self._pace.ppm, 'median': round(self._pace.median, 3), 'changes': self._pace.changes},
            'hello': None if hello is None else {'name': hello.name, 'players': hello.players, 'caps': hello.caps,
                                                 'millihertz': hello.frame_rate_millihertz},
        }

    def result(self) -> dict:
        """The snapshot with the history, the digests and the time-sync trace: what a finished match leaves."""
        return {**self.snapshot(), 'history': [list(words) for words in self.history],
                'digests': {str(frame): value for frame, value in self.digests.items()},
                'pace_trace': [list(item) for item in self.pace_trace]}

    # ---- the loop ----

    def _loop(self):
        started = time.monotonic()
        self._last_heard = {seat: started for seat in self.peers}
        self._deadline = started + HELLO_WITHIN
        self.link.open(self._net_in)
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

    def _packet_rate(self) -> float:
        """Packets a second one seat may send: what an honest seat sends is about one per frame for every seat it speaks
        for, plus the keep-alive and the pings; the floor is the review's 240."""
        if self.settings.packet_rate is not None:
            return self.settings.packet_rate
        hello = self.hello
        frames = 1.0 / hello.frame_seconds if hello is not None else 60.0
        return max(PACKET_RATE_MIN, (self.seats + 1) * frames)

    def _net_in(self, source: int, data: bytes) -> None:
        """The link's sink (any thread): one seat's packet rate and the queue's size are bounded here, before anything is
        queued. The excess is dropped and counted; this never blocks and never raises."""
        now = time.monotonic()
        with self._admit:
            if source not in self.peers:
                self.stats['packets_ignored'] += 1
                return
            rate = self._packet_rate()
            bucket = self._buckets.get(source)
            if bucket is None:
                bucket = self._buckets[source] = TokenBucket(rate, max(60.0, rate / 4), now)
            bucket.rate = rate
            if not bucket.take(now):
                self.stats['packets_dropped_rate'] += 1
                return
            if self._events.qsize() >= EVENT_QUEUE_MAX:
                self.stats['packets_dropped_queue'] += 1
                return
        try:
            self._events.put_nowait(('net', source, data))
        except queue.Full:
            self.stats['packets_dropped_queue'] += 1

    def _dispatch(self, event):
        if event[0] == 'game':
            self._from_game(event[1])
        elif event[0] == 'net':
            self._from_link(event[1], event[2])
        else:
            event[1]()

    def _tell_turn(self) -> None:
        """Shared controls taken in turns: when the token moved (on real records only), this game is told who has them now
        ("Your turn" for its own seat); nothing in the other modes."""
        state = self._seat_state
        if state.sharing != seat_map.SHARED_TURNS:
            self._turn_told = None
            return
        if state.token == self._turn_told:
            return
        self._turn_told = state.token
        if state.token == self.seat:
            self._tell(pipe.notice(pipe.NOTICE_YOUR_TURN))
        elif state.token < len(self.names):
            self._tell(pipe.notice(pipe.NOTICE_TURN, self.names[state.token]))

    def chat_show(self, phrase: int, name: str, text: str) -> None:
        """A line of the room for this game (from any thread: it goes through the driver's own loop, after the SETUP)."""
        data = pipe.chat_show(phrase, name, text)
        self._events.put(('call', lambda: self._chat_tell(data)))

    def chat_slow(self) -> None:
        """This player's line was refused: too many lines."""
        self._events.put(('call', lambda: self._chat_tell(pipe.notice(pipe.NOTICE_CHAT_SLOW))))

    def _chat_tell(self, data: bytes) -> None:
        # A game hears nothing before its SETUP (the kit ends the session on any other message then): a line said in the
        # lobby while the match starts is shown in the window only. After the match nothing is sent either.
        if self._phase in ('gate', 'play', 'linger'):
            self._tell(data)

    def _tell(self, data: bytes) -> None:
        if not self._game_gone:
            self.game.send(data)

    def _self_leaving(self) -> tuple:
        """The BYE of this seat ending the match for a reason of its own (its game or its pipe went)."""
        return (wire.BYE_HOST_CLOSED if self.seat == HOST else wire.BYE_LEFT), wire.NO_SEAT

    def _other_leaving(self, seat: int) -> tuple:
        """The BYE of this seat ending the match because `seat` went (silent, or said so)."""
        if self._relays:
            return wire.BYE_SEAT_GONE, seat     # the host tells the others who
        return self._self_leaving()

    # ---- the game's messages ----

    def _from_game(self, message):
        if message is None:
            self._game_gone = True
            if self.outcome is None:
                closed = self.exit_reason == pipe.EXIT_CLOSED
                self.detail = self.detail or (self.game.broken or 'the game closed its pipe')
                self._end('game_closed' if closed else 'pipe_lost', None, *self._self_leaving())
            return
        kind, payload = message
        if kind == pipe.MSG_HELLO:
            self._hello(pipe.parse_hello(payload))
        elif kind == pipe.MSG_LOCAL:
            self._local(*pipe.parse_local(payload))
        elif kind == pipe.MSG_DIGEST_OF:
            frame, value = pipe.parse_digest_of(payload)
            if self._phase == 'gate' and self.boot_digest is None:
                self.boot_digest = value        # the answer to the DIGEST asked right after SETUP: no frame ran yet
                return
            frame = self._digest_frame(frame)
            if frame is None:
                return
            self.digests[frame] = value
            self._latest_digest = (frame, value)
            self._compare(frame)
        elif kind == pipe.MSG_REFUSED:
            code, text = pipe.parse_refused(payload)
            self.detail = f'the game refused ({code}): {text}'
            self._end('refused', None, *self._self_leaving())
        elif kind == pipe.MSG_EXIT:
            self.exit_reason = pipe.parse_exit(payload)
        elif kind == pipe.MSG_CHAT_OUT:
            # The in-game chat: the line goes to the room's lobby (cleaned, limited, stamped by the host there) and comes back
            # to every game, this one included, as CHAT_SHOW in the host's order. The match itself never waits for it.
            phrase, text = pipe.parse_chat_out(payload)
            self.chat_lines += 1
            if self.on_chat is not None:
                self.on_chat(phrase, text)
        elif kind == pipe.MSG_DONE:
            frame, cost_us = pipe.parse_done(payload)
            self._frame_cost(frame, cost_us)

    def _frame_cost(self, frame: int, cost_us: int) -> None:
        """What the game's live frame cost it (its run_frame alone, in microseconds). The delay tier does not use it; the
        rollback tier keeps it for its safety floor. Never a speed or latency figure for the player."""

    def _hello(self, hello: pipe.Hello):
        if self.hello is not None:
            return
        self.hello = hello
        self.sticks = bool(hello.caps & pipe.CAP_AXES)     # every record of this match carries the sticks
        try:
            pipe.check_hello(hello, self.seats, shared=seat_map.shared(self.settings.sharing))
            reason = self._tier_refusal(hello)
            if reason:
                raise pipe.Refused(reason)
        except pipe.Refused as error:
            self.detail = str(error)
            self._end('refused', None, *self._self_leaving())
            self.game.close_pipe()              # the game sees its pipe close and ends by itself
            return
        self._tell(pipe.setup(self.seat, seat_map.ports(self.settings.sharing, self.seats), self._ring_depth(hello),
                              guest=self.seat != HOST, options=self.settings.options))
        if self.settings.clock_ppm:
            self._tell(pipe.pace(self.settings.clock_ppm))
        self._tell(pipe.digest())               # the boot digest: the state after SETUP, before any frame
        self._phase = 'gate'
        self._deadline = time.monotonic() + GATE_WITHIN

    def _tier_refusal(self, hello: pipe.Hello) -> str | None:
        """A sentence when this game cannot play the tier the launch named (the rollback tier overrides it); None otherwise."""
        return None

    def _ring_depth(self, hello: pipe.Hello) -> int:
        """The snapshots the game is asked to keep (rollback tier); the delay tier asks for none."""
        return 0

    def _digest_frame(self, frame: int) -> int | None:
        """The frame a DIGEST_OF is the digest of: the last one the game ran (the rollback tier asks for older ones)."""
        return frame

    def _delay_for(self, one_way_ms: float, jitter_ms: float) -> int:
        """The host's choice of the input delay from the measured worst path (the rollback tier has its own rule)."""
        return wire.choose_delay(one_way_ms, jitter_ms, self.hello.frame_seconds * 1000.0)

    def _preset_hold(self) -> int | None:
        """With a delay given, the host starts at once: the records it waits for align the seats (the rollback tier, which
        does not wait, measures its links first and holds its start as a measured delay does; None: not measured yet)."""
        return 0

    def _set_delay(self, delay: int, start_at: float):
        self.delay = max(1, min(wire.MAX_DELAY, delay))
        for seat in range(self.seats):          # nobody's controls exist before frame D: neutral for every seat
            self._records[seat] = RecordLog([(0, 0)] * self.delay)
        self._holds = {peer: [self.delay - 1] * self.seats for peer in self.peers}
        self._start_at = start_at
        self._holding = True
        self._phase = 'play'
        self._pace = PaceController()

    def _local(self, frame: int, word: int, system: int, axes=None):
        if self._phase in ('hello', 'gate') or self._holding:
            self._pending_locals.append((frame, word, system, axes))     # kept in order until the match starts
            return
        # The host's restart (Shift+F1, the pad combination): the rising edge of the game's bit is a request that rides the
        # next record of this seat, so every game restarts at that frame. A guest's game never asks (the kit refuses it);
        # ignored if it did. Read before a test's script replaces the system bits, so a scripted seat can restart too.
        asked = bool(system & pipe.SYS_RESTART)
        if asked and not self._game_restart and self.seat == HOST:
            self._request |= seat_map.SYS_RESTART
        self._game_restart = asked
        # The host's F8 / F9 (the match's state, for everyone): the same, on the rising edge of the game's bit; a load wins over
        # a save asked in the same LOCAL. It waits for a record at least `_state_spacing` after the last one (below).
        state = system & (pipe.SYS_STATE_SAVE | pipe.SYS_STATE_LOAD)
        if self.seat == HOST:
            rising = state & ~self._game_state
            if rising & pipe.SYS_STATE_LOAD:
                self._state_wanted = seat_map.SYS_STATE_LOAD
            elif rising & pipe.SYS_STATE_SAVE:
                self._state_wanted = seat_map.SYS_STATE_SAVE
        self._game_state = state
        if self.settings.local_source is not None:
            scripted = self.settings.local_source(frame, word, system)
            word, system = scripted[0] & 0xffff, scripted[1] & 0xffff
            if len(scripted) > 2:
                axes = tuple(scripted[2])
        else:
            system &= seat_map.SYS_GAME_MASK     # a game can only ask for a pause; the other control bits come from the worker's requests
        if frame > self.game_frame:
            self._local_at = time.monotonic()
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
            record = len(mine)
            if self._state_wanted and (self._state_record is None or record - self._state_record >= self._state_spacing()):
                self._request |= self._state_wanted
                self._state_wanted, self._state_record = 0, record
            if self.sticks:             # a game with sticks: every record carries them (centred when the game said none)
                mine.append((word, system | self._request, tuple(axes) if axes else pipe.NO_AXES))
            else:
                mine.append((word, system | self._request))
            self._request = 0                   # a request rides one record: the mapper acts on its rising edge
            self._send_inputs(time.monotonic())

    # ---- the link's packets ----

    def _proven_seat(self, source: int, data: bytes):
        """THE place a packet's seat is decided: (seat, packet), or None. In stage 1 `source` is what the link says; the
        transport of stage 2 hands over a seat its keys proved, and nothing else here changes. The header's seat byte
        must agree with it and is never believed on its own."""
        packet = wire.decode(data, self.seats)
        if packet is None or packet.seat != source or source == self.seat or source not in self.peers:
            return None
        return source, packet

    def _from_link(self, source: int, data: bytes):
        proven = self._proven_seat(source, data)
        if proven is None:
            self.stats['packets_ignored'] += 1
            return
        source, packet = proven
        self.stats['packets_received'] += 1
        now = time.monotonic()
        self._last_heard[source] = now
        if packet.kind == wire.PING:
            self._send(source, wire.encode_pong(self.seat, packet.time))
        elif packet.kind == wire.PONG:
            self._pong(source, packet, now)
        elif packet.kind == wire.MEASURE:
            if self.seat == HOST and self._phase == 'gate' and source in self.guests:     # only the host reads them, only before the start
                self._measures[source] = (packet.one_way_ms, packet.jitter_ms)
        elif packet.kind == wire.BOOT:
            if self.seat == HOST:
                if self._phase in ('hello', 'gate'):
                    self._boots[source] = packet.digest
                elif self.outcome == 'boot_mismatch':   # the verdict may have been lost on the way: say it again
                    self._send(source, wire.encode_bye(self.seat, wire.BYE_BOOT, 0, self._boot_culprit))
        elif packet.kind == wire.BYE:
            self._peer_left(source, packet.reason, packet.who)
        elif packet.kind == wire.INPUT:
            self._input(source, packet, now)

    def _pong(self, source: int, packet: wire.Packet, now: float):
        """A round trip, only for a PING this driver sent to that seat (answered once) and not above MAX_RTT_MS: a seat
        cannot make the links look slow by sending PONGs nobody asked for."""
        sent = self._pings_sent[source]
        rtt = ((int(now * 1e6) - packet.time) & 0xffffffff) / 1000.0
        if packet.time not in sent or rtt > MAX_RTT_MS:
            self.stats['pongs_refused'] += 1
            return
        sent.remove(packet.time)
        self._rtt[source].append(rtt)
        del self._rtt[source][:-64]
        # The middle of the last 64 round trips, halved: a late answer or two does not move it (the time
        # sync reads it once per packet and the delay rule once; a jittery link must not make it jump).
        self._one_way_ms[source] = statistics.median(self._rtt[source]) / 2

    def _send_ping(self, seat: int, now: float):
        value = int(now * 1e6) & 0xffffffff
        self._pings_sent[seat].append(value)
        self._send(seat, wire.encode_ping(self.seat, value))

    def _input(self, source: int, packet: wire.Packet, now: float):
        if self.delay is None:
            # A guest in the gate: the host's first input packet is its word to start. The host decided the delay;
            # it started when it sent this, so a guest nearer than the farthest one waits the difference.
            if self.seat == HOST or source != HOST or not packet.delay or self._phase != 'gate' or self.boot_digest is None:
                return
            hold = min(packet.hold_ms, wire.MAX_HOLD_MS)
            self._set_delay(packet.delay, now + max(0.0, hold - self._one_way_ms[HOST]) / 1000.0)
        near = abs(packet.sender_frame - self.next_run) <= FRAME_WINDOW     # a frame far from ours is not believed
        if near:
            self._peer_frame[source] = (packet.sender_frame, now)
        if (near and self.settings.pace and self._phase == 'play' and not self._holding and self.paused is None
                and self.next_run >= 2 and self.game_frame >= 0 and self.hello is not None):
            # Where this game is: the frame its latest LOCAL reported, plus the part of it that has passed (a frame at most;
            # a game that waits for records stays at the end of its frame). The peer reported its frame when it began it,
            # and the packet took one way to come. Counting whole frames only would make the estimate move by steps of a
            # frame, which hides a slow drift until it is a frame wide.
            period_ms = self.hello.frame_seconds * 1000.0
            mine = self.game_frame + min(1.0, (now - self._local_at) * 1000.0 / period_ms)
            self._pace.observe(source, now, mine - (packet.sender_frame + self._one_way_ms[source] / period_ms))
        for owner in self._owners_for(source):      # what the peer holds of the records it is to get from me
            held = packet.acks[owner]
            if held != wire.NONE:
                self._holds[source][owner] = max(self._holds[source][owner], min(held, len(self._records[owner]) - 1))
        self._peer_resume[source] = packet.resume_frame
        fresh = False
        # An honest seat is never further ahead than its game's frame plus the delay: a record beyond the window is
        # dropped and counted, so it is neither kept nor forwarded (the host forwards only what it took).
        window = self.next_run + self.delay + RECORD_WINDOW
        for section in packet.sections:
            if not self._accepts(source, section.seat):
                self.stats['sections_refused'] += 1
                continue
            known = self._records[section.seat]
            for offset, record in enumerate(section.records):
                frame = section.first_frame + offset
                if frame > window:
                    self.stats['records_beyond_window'] += len(section.records) - offset
                    break
                if frame == len(known):
                    known.append(record)
                    fresh = True
                elif frame < len(known):
                    self.stats['records_repeated'] += 1     # first write wins
        if fresh and self._relays:
            # The host forwards at once what a guest said to the others (and says nothing new to that guest).
            self.stats['records_forwarded'] += 1
            self._send_inputs(now, only=[peer for peer in self.peers if peer != source])
        if packet.digest_frame != wire.NONE and packet.digest_frame <= window - RECORD_WINDOW + DIGEST_WINDOW:
            digests = self._peer_digests[source]
            if packet.digest_frame not in digests:
                digests[packet.digest_frame] = packet.digest
                for frame in sorted(digests)[:-16]:
                    del digests[frame]
                self._compare(packet.digest_frame)

    def _owners_for(self, peer: int) -> list[int]:
        """The seats whose records this driver sends to `peer`: its own, and in a star the host's all the others'."""
        if self._relays:
            return [seat for seat in range(self.seats) if seat != peer]
        return [self.seat]

    def _accepts(self, source: int, owner: int) -> bool:
        """Whether a section about `owner` is believed from `source`: a seat speaks for itself, and in a star the host
        speaks for everyone but the one who listens."""
        if owner == self.seat:
            return False
        if self.star and self.seat != HOST:
            return source == HOST
        return owner == source

    def _send(self, seat: int, data: bytes):
        self.stats['packets_sent'] += 1
        self.link.send(seat, data)

    def _send_inputs(self, now: float, only=None):
        digest_frame, digest = self._latest_digest or (wire.NONE, 0)
        acks = [len(records) - 1 if records else wire.NONE for records in self._records]
        for peer in only if only is not None else self.peers:
            sections = []
            for owner in self._owners_for(peer):
                held = self._records[owner]
                # from the first record the peer did not acknowledge, and at least the last `redundancy` ones
                first = max(held.base, min(self._holds[peer][owner] + 1, len(held) - self.settings.redundancy))
                records = held.span(first, wire.records_that_fit(len(self._owners_for(peer)), self.sticks))
                if records:
                    sections.append((owner, first, records))
            self._send(peer, wire.encode_input(
                self.seat, max(self.game_frame, 0), acks, sections,
                delay=self.delay if self.seat == HOST else 0, hold_ms=self._hold_ms, resume_frame=self._my_resume,
                digest_frame=digest_frame, digest=digest))
        self._last_sent = now

    # ---- frames ----

    def _step(self, now: float):
        if self._phase != 'play' or not self._started(now):
            return
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
            records = [self._records[seat][frame] for seat in range(self.seats)]
            action = seat_map.action(records)
            axes = seat_map.sticks(self._seat_state, records) if self.sticks else None
            words, self._seat_state = seat_map.step(self._seat_state, records, self.settings.opposites)
            self._tell_turn()
            if self.settings.words_filter is not None:
                words = tuple(self.settings.words_filter(frame, words))
            if frame and self.game_frame >= frame:
                self.stats['late_frames'] += 1      # the game had asked for this frame before it could be given
            if self._waiting_noticed:
                self._tell(pipe.notice(pipe.NOTICE_RESUMED))
                self._waiting_noticed = False
            self._blocked_since = None
            self._tell(pipe.run(frame, words, action=action, axes=axes))
            self._remember(frame, words, action, axes)
            self.stats['runs'] += 1
            self.next_run = frame + 1
            if self.next_run % self.settings.digest_every == 0 or self.next_run == self.settings.last_frame:
                self._tell(pipe.digest())           # answered after this frame ran, before the next one
            if self.next_run % 32 == 0:
                self._trim()

    def _started(self, now: float) -> bool:
        """False before the start the host set; at the start, the LOCALs kept until then become records."""
        if self._holding:
            if now < self._start_at:
                return False
            self._holding = False
            self._pace.forget()
            pending, self._pending_locals = self._pending_locals, []
            for local in pending:
                self._local(*local)
        return True

    def _state_spacing(self) -> int:
        """Records between two saves or loads of the match's state: any on the delay tier, where no frame is run again (the
        rollback driver keeps them a snapshot ring apart, so a correction never runs a load after the save that follows it)."""
        return 1

    def _remember(self, frame: int, words: tuple, action: int = 0, axes=None):
        """What this game was told to run: kept whole only for tests (`keep_history`); always as a running fold (what was done
        before the frame, a restart or the match's state saved or loaded, folds in too)."""
        value = frame
        for port, word in enumerate(words):
            value ^= word << (16 * port + 7)
        if axes:
            for port, sticks in enumerate(axes):
                for index, stick in enumerate(sticks):
                    value ^= (((stick & 0xff) << (8 * ((port * pipe.AXES + index) % 8))) * STICKS_FOLD) & 0xffffffffffffffff
        action = pipe.RUN_RESET if action is True else int(action or 0)
        if action:
            value ^= ACTION_FOLDS[action]
            if action == pipe.RUN_RESET:
                self.restarts.append(frame)
            else:
                self.states.append((frame, 'save' if action == pipe.RUN_STATE_SAVE else 'load'))
        self.history_digest = ((self.history_digest * 0x100000001b3) ^ value) & 0xffffffffffffffff
        self.history_frames += 1
        if self.settings.keep_history:
            self.history.append(words)

    def _trim(self):
        """Memory stays bounded over a long match: the records every peer holds (or, for a peer that acknowledges
        nothing, the ones older than ACK_LAG_MAX frames) and a margin behind the frame being run are dropped, and so are
        the oldest digests and pauses."""
        for owner in range(self.seats):
            floor = self.next_run
            for peer in self.peers:
                if peer not in self._peer_gone and owner in self._owners_for(peer):
                    floor = min(floor, self._holds[peer][owner] + 1)
            self._records[owner].trim(max(floor, self.next_run - ACK_LAG_MAX) - TRIM_BEHIND)
        if not self.settings.keep_history and len(self.digests) > DIGESTS_KEPT:
            for frame in sorted(self.digests)[:-DIGESTS_KEPT]:
                del self.digests[frame]
        del self.pauses[:-256]

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
        if self._relays:
            self._my_resume = frame                 # the host says it to the others, whoever asked
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
        """The seat this one believes found the games out of step (the same decision point as `_desync`): in a star a
        guest believes the host, which compared the digests of every seat itself."""
        self.detail = self.detail or f'seat {seat + 1} reported the games out of step'
        self._end('desync', pipe.STOP_DESYNC, None)

    def _claim_desync(self, seat: int, now: float):
        """A guest says the games are out of step. The host does not take its word: the digests are in the host's own
        hands, and it says "out of step" only when its own comparison finds it (`_desync`). Without that, within
        `desync_confirm` seconds, the claim is a departure (`_timers`)."""
        self.stats['desync_claims'] += 1
        self._desync_claims.setdefault(seat, now)

    # ---- the end ----

    def _stop_asked(self):
        if self.seat == HOST:
            self._end('ended', pipe.STOP_ENDED, wire.BYE_ENDED)
        else:
            self._end('left', pipe.STOP_ENDED, wire.BYE_LEFT)

    def _peer_left(self, seat: int, reason: int, who: int):
        self._peer_gone.add(seat)
        if self.outcome is not None or self._phase in ('linger', 'closing'):
            return
        if reason == wire.BYE_DESYNC:
            if self._relays:
                self._claim_desync(seat, time.monotonic())
            else:
                self._desync_reported(seat)
        elif reason == wire.BYE_BOOT and seat == HOST:
            if who == self.seat:        # the culprit is told so, in its game; the others get a neutral reason
                self.detail = 'your game does not start from the same state as the host\'s (another save, an option, a damaged export)'
                self._end('boot_mismatch', pipe.STOP_BOOT_MISMATCH, None)
            else:
                culprit = self.names[who] if who < self.seats else 'a seat'
                self.detail = f'the launch was refused: the game of {culprit} differs from the host\'s'
                self._end('boot_mismatch', pipe.STOP_ENDED, None)
        elif seat == HOST and reason == wire.BYE_ENDED:
            self._end('ended', pipe.STOP_ENDED, None)
        elif seat == HOST and reason == wire.BYE_SEAT_GONE:
            if who < self.seats:
                self._tell(pipe.notice(pipe.NOTICE_LEFT, self.names[who]))
            self.detail = f'{self.names[who] if who < self.seats else "a seat"} left'
            self._end('seat_left', pipe.STOP_ENDED, None)
        elif seat == HOST:
            self._end('host_closed', pipe.STOP_HOST_CLOSED, None)
        else:
            self._tell(pipe.notice(pipe.NOTICE_LEFT, self.names[seat]))
            self._end('seat_left', pipe.STOP_ENDED, *(self._other_leaving(seat) if self._relays else (None, wire.NO_SEAT)))

    def _end(self, outcome: str, stop_reason: int | None, bye_reason: int | None, who: int = wire.NO_SEAT):
        if self.outcome is not None:
            return
        self.outcome = outcome
        now = time.monotonic()
        if bye_reason is not None:
            packet = wire.encode_bye(self.seat, bye_reason, self.next_run, who)
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
                self._end('pipe_lost', None, *self._self_leaving())
            self._ping(now)
            return
        if self._phase == 'gate':
            self._gate(now)
        if self._phase in ('play', 'linger', 'closing') and self.delay is not None and self.outcome in (None, 'ended'):
            if now - self._last_sent >= KEEP_ALIVE:
                self._send_inputs(now)          # also while paused, waiting or closing: records repeated, link heard
        if self._phase == 'play':
            self._ping(now)
            self._waiting(now)
            self._silence(now)
            self._stalled(now)
            self._claims(now)
            self._pace_round(now)
        elif self._phase == 'linger':
            final = self.settings.last_frame - 1
            served = all(self._holds[peer][owner] >= final for peer in self.peers if peer not in self._peer_gone
                         for owner in self._owners_for(peer))
            if (served and self.stats['final_compared']) or now >= self._linger_until:
                self.outcome = 'ended'
                self._closing_not_before = now + CLOSING_MIN
                self._close_game(pipe.STOP_ENDED, now)
        if self._phase == 'closing':
            if self._byes and now >= self._bye_at:
                for seat in self.peers:
                    self._send(seat, self._byes[-1])
                self._byes.pop()
                self._bye_at = now + 0.02
            if not self._byes and (self._game_gone or now >= self._deadline) and now >= self._closing_not_before:
                self._finalize()

    def _ping(self, now: float):
        if now - self._last_ping >= PING_EVERY:
            self._last_ping = now
            for seat in self.peers:
                self._send_ping(seat, now)

    def _own_measure(self):
        """(one way, jitter) of this seat's worst link in ms, once every link has been probed long enough."""
        if self.measured is None:
            enough = all(len(self._rtt[seat]) >= 5 for seat in self.peers)
            first = min((len(samples) for samples in self._rtt.values()), default=0)
            if enough and first * PROBE_EVERY >= self.settings.probe_seconds:
                estimates = [link_estimate(samples) for samples in self._rtt.values()]
                self.measured = (max(one_way for one_way, _jitter in estimates), max(jitter for _one_way, jitter in estimates))
        return self.measured

    def _gate(self, now: float):
        """Before frame 0: the boot digests are compared (the host decides), and with no delay given the links are
        measured; then the host says the delay, which is its word to start."""
        if now >= self._deadline:
            if self.seat == HOST:
                missing = [seat + 1 for seat in self.guests if seat not in self._boots]
                self.detail = f'seats {missing} did not report their game ready' if missing else 'the seats could not measure their links'
            else:
                self.detail = 'no word to start from the host'
            self._end('seat_silent', pipe.STOP_ENDED, *self._self_leaving())
            return
        if now - self._last_probe < PROBE_EVERY:
            return
        self._last_probe = now
        for seat in self.peers:
            self._send_ping(seat, now)
        if self.boot_digest is None:
            return
        needs_measure = self.seat != HOST or self._preset is None
        measured = self._own_measure() if needs_measure else None
        if self.seat != HOST:
            self._send(HOST, wire.encode_boot(self.seat, self.boot_digest))
            if measured is not None:
                self._send(HOST, wire.encode_measure(self.seat, *measured))
            return
        if not all(seat in self._boots for seat in self.guests):
            return
        differs = [seat for seat in self.guests if self._boots[seat] != self.boot_digest]
        if differs:
            self._refuse_launch(differs[0])
            return
        if self._preset is not None:
            hold = self._preset_hold()
            if hold is None:
                return
            self._hold_ms = hold
            self._set_delay(self._preset, now + self._hold_ms / 1000.0)
        else:
            if measured is None or not all(seat in self._measures for seat in self.guests):
                return
            self._hold_ms = min(wire.MAX_HOLD_MS, int(max(self._one_way_ms.values())))
            one_way, jitter = self._worst_path()
            # the host starts once its word reached the farthest guest
            self._set_delay(self._delay_for(one_way, jitter), now + self._hold_ms / 1000.0)
        self._send_inputs(now)

    def _refuse_launch(self, seat: int):
        self._boot_culprit = seat
        self.detail = (f'the game of {self.names[seat]} does not start from the same state as the host\'s: boot digest '
                       f'{self._boots[seat]:016x} against {self.boot_digest:016x} (another save, an option, a damaged export)')
        self._end('boot_mismatch', pipe.STOP_ENDED, wire.BYE_BOOT, seat)     # the host's own game is not the culprit


    def _worst_path(self) -> tuple[float, float]:
        """(one way ms, jitter ms) the delay must cover. Through the host a guest's records travel two links, so the
        worst path is the two farthest guests' links added (the host's own link counts for nothing)."""
        if not self.star:
            worst = [self.measured, *self._measures.values()]
            return max(item[0] for item in worst), max(item[1] for item in worst)
        legs = [(0.0, 0.0)]
        for guest in self.guests:
            mine = link_estimate(self._rtt[guest])
            # The guest measured the same link the host did: what it says above the host's own measure (by more than
            # half again, and a little) is not believed, and no measure counts above MAX_MEASURE_MS.
            claimed = self._measures[guest]
            theirs = (min(claimed[0], 1.5 * mine[0] + MEASURE_SLACK_MS, MAX_MEASURE_MS),
                      min(claimed[1], 2 * mine[1] + MEASURE_SLACK_MS, MAX_MEASURE_MS))
            if theirs != claimed:
                self.stats['measures_clamped'] += 1
            legs.append((max(mine[0], theirs[0]), max(mine[1], theirs[1])))
        pairs = [(a[0] + b[0], a[1] + b[1]) for index, a in enumerate(legs) for b in legs[index + 1:]]
        return max(pairs, key=lambda pair: pair[0] + pair[1])

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
                self._end('seat_silent', pipe.STOP_ENDED, *self._other_leaving(seat))
                return

    def _stalled(self, now: float):
        """A seat that talks but gives no record is a silent seat: `_silence` looks at packets, which pings keep coming.
        The game has waited for that seat's record for `drop_after` seconds (and is not paused): it is gone."""
        if self.outcome is not None or self._blocked_since is None or self.paused is not None or self._holding:
            return
        seat = self._blocked_on
        grace = STALL_GRACE if self.seat != HOST and seat != HOST else 0.0     # a guest lets the host decide about a guest
        if now - self._blocked_since < self.settings.drop_after + grace:
            return
        self.stats['stalls'] += 1
        self.detail = f'seat {seat + 1} gave no input for {self.settings.drop_after:g} s'
        self._tell(pipe.notice(pipe.NOTICE_LEFT, self.names[seat]))
        self._end('seat_silent', pipe.STOP_ENDED, *self._other_leaving(seat))

    def _claims(self, now: float):
        """The guests' "out of step" the host's own digests did not confirm in time: that guest left."""
        if self.outcome is not None:
            return
        for seat, since in list(self._desync_claims.items()):
            if now - since >= self.settings.desync_confirm:
                name = self.names[seat]
                self.detail = f'{name} left, reporting the games out of step'
                self._tell(pipe.notice(pipe.NOTICE_LEFT, name))
                self._end('seat_left', pipe.STOP_ENDED, *self._other_leaving(seat))
                return

    def _pace_round(self, now: float):
        if now - self._last_pace < PACE_EVERY:
            return
        self._last_pace = now
        if not self.settings.pace or self.hello is None:
            return
        if self.paused is not None or self._holding:
            self._pace.forget()                 # the frames did not move while paused: what was seen would lie
            return
        new = self._pace.update(now)
        self.pace_trace.append((self.next_run, round(self._pace.median, 2), self._pace.ppm))
        del self.pace_trace[:-600]
        if new is not None:
            self._tell(pipe.pace(self.settings.clock_ppm + new))
            self.stats['pace_changes'] = self._pace.changes
            self.stats['pace_ppm_max'] = max(self.stats['pace_ppm_max'], new)
