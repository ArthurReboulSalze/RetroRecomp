"""The "local network" room of multiplayer stage 2: the only module of the package that imports `socket`.

One host (`RoomHost`) and up to three guests (`RoomGuest`) on one LAN. TCP carries the control stream (the handshake,
the roster, the launch, the end), UDP carries the match, both on one port number and both bound to the **one local IPv4
address** the room was given: a private range, or 100.64.0.0/10 (the VPNs between friends). Never `''`, `0.0.0.0` or
`::`; 127.0.0.1 only when the constructor is told `tests=True`, which the product never does. A host name is never
resolved, no router port is asked for, nothing is broadcast, nothing is discovered, and no firewall or system setting is
touched. The specification is `SECURITY_REVIEW.md` section 2; the pure parts it is made of are `invitation`,
`handshake`, `control`, `datagram`, `limits` and `room_log`, tested without a socket.

What a stranger gets: nothing. A TCP connection that does not show a valid tag within five seconds is closed without a
byte (three failures a minute from one address and it is refused for five minutes); a datagram from an address that
is not an authenticated peer's is dropped before any hashing. What the seat is: the key that verified, never a header
byte or an address. The driver (`lockstep.LockstepDriver`) is not changed: `link()` gives it the `SeatLink` it already
knows, and it is handed the seat the key proved.

Threads: one I/O thread per room or guest (a selector with a short timeout: no busy loop), the driver's own thread for
`send`. Everything the transport tells the caller (events, the driver's sink) is handed over after the lock is released.
"""
from __future__ import annotations

from dataclasses import dataclass
import collections
import hashlib
import itertools
import secrets
import selectors
import socket
import struct
import sys
import threading
import time
from typing import Callable

from . import control, datagram, handshake, invitation, lobby as lobbies, seat_map
from . import input_records as wire
from .launch import Refusal
from .limits import FRAME_BURST, FRAME_RATE, Admission, Counters, NonceMemory, TokenBucket
from .room_log import RoomLog

PING_EVERY = 2.0
SILENCE = 10.0                      # an authenticated peer that sent nothing for this long is gone
HELLO_WITHIN = 10.0
LAUNCH_WITHIN = 30.0                # every guest says LAUNCHED within this, or the launch fails
IDLE_ASK = 1800.0                   # no guest and no match for this long: the host's window is asked whether to keep the room
BUSY_TICK, IDLE_TICK = 0.02, 0.1    # the selector's timeout: short only while some bytes wait to be sent
CAPACITY_MIN, CAPACITY_MAX = 2, 4
NO_ANSWER = 'no answer: check the invitation, or the host\'s firewall'
REJECTIONS = {control.REJECT_FULL: 'the room is full', control.REJECT_VERSION: 'update Retro-Recomp on both PCs',
              control.REJECT_BUSY: 'a match is running in that room', control.REJECT_KICKED: 'the host removed you'}
BYE_LEFT, BYE_CLOSED, BYE_KICKED = 1, 2, 3          # the control stream's BYE reasons
PENDING_LIMIT = 64 * 1024           # bytes waiting on one control connection: past this the peer does not read, it is closed (N4)
CLOSING_SECONDS = 2.0               # a peer being turned away keeps its place this long, whatever waits to be sent (N4)


def room_code(reason: str) -> str:
    """A short code for a room's sentence (`RoomError.reason`, a host_gone detail), for a window that says it in its own
    language: unreachable, full, other_version, match_running, kicked, bad_invitation, not_local, port, closed, timeout,
    lost, other."""
    if reason.startswith('the room could not open a port') or reason == 'this PC could not open a datagram port':
        return 'port'
    known = {NO_ANSWER: 'unreachable', REJECTIONS[control.REJECT_FULL]: 'full',
             REJECTIONS[control.REJECT_VERSION]: 'other_version', REJECTIONS[control.REJECT_BUSY]: 'match_running',
             REJECTIONS[control.REJECT_KICKED]: 'kicked', 'this invitation is not for a room on a local network': 'bad_invitation',
             'this PC reaches that room through an address that is not on a local network': 'not_local',
             'the host closed the room': 'closed', 'the host closed the connection': 'closed',
             'the host was silent for ten seconds': 'timeout'}
    if reason in known:
        return known[reason]
    return 'lost' if 'connection' in reason or 'control frame' in reason or 'did not read' in reason else 'other'


class RoomError(Exception):
    """The room could not be opened or joined; `reason` is a sentence for the player, free of anything secret, and `code`
    the same in a word (`room_code`)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason
        self.code = room_code(reason)


# ---- this PC's addresses ----

def local_addresses(tests: bool = False) -> list[str]:
    """This PC's IPv4 addresses that a local room may use, found locally: the addresses of the PC's own name, and the
    local address a UDP socket would use towards a few private targets (`connect` on UDP sends nothing)."""
    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    for target in ('192.168.0.1', '10.0.0.1', '172.16.0.1', '100.64.0.1'):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect((target, 9))
            found.append(probe.getsockname()[0])
        except OSError:
            pass
        finally:
            probe.close()
    return [address for address in dict.fromkeys(found) if invitation.is_lan_address(address, tests)]


def _exclusive(sock: socket.socket, reuse: bool) -> None:
    """Windows: `SO_EXCLUSIVEADDRUSE` and no `SO_REUSEADDR` (there it would let another local process take the port).
    Elsewhere: `SO_REUSEADDR` on the TCP listener only."""
    if sys.platform == 'win32':
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    elif reuse:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)


class _Stream:
    """One TCP connection: its socket, the bytes waiting to be sent, and the frames' keys once the handshake is done."""

    def __init__(self, sock: socket.socket, ip: str, port: int, now: float):
        self.sock, self.ip, self.port = sock, ip, port
        self.lock = threading.Lock()
        self.pending = bytearray()
        self.closing = False                     # close once everything is sent (or after `CLOSING_SECONDS`)
        self.closing_since = now
        self.closed = False
        self.overflow = False                    # closed because too many bytes waited: the peer did not read
        self.writer: control.FrameWriter | None = None
        self.reader: control.FrameReader | None = None
        self.bucket = TokenBucket(FRAME_RATE, FRAME_BURST, now)
        self.last_heard = self.last_ping = now
        self.dead = False                        # `_close` has run for it

    def write(self, data: bytes) -> bool:
        """Sent now if the socket takes it, else kept for the loop to send. Never waits."""
        with self.lock:
            if self.closed:
                return False
            if not self.pending:
                try:
                    sent = self.sock.send(data)
                except (BlockingIOError, InterruptedError):
                    sent = 0
                except OSError:
                    self.closed = True
                    return False
                data = data[sent:]
            self.pending += data
            if len(self.pending) > PENDING_LIMIT:
                self.pending.clear()
                self.closed = self.overflow = True
                return False
            return True

    def flush(self) -> bool:
        with self.lock:
            while self.pending and not self.closed:
                try:
                    sent = self.sock.send(self.pending)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    self.closed = True
                    return False
                del self.pending[:sent]
            return not self.closed

    def send(self, message) -> bool:
        return self.write(self.writer.seal(message))

    def waiting(self) -> bool:
        return bool(self.pending)


def _frame_error_text(error: Exception) -> str:
    return f'a control frame broke the rules ({error})'


# =====================================================================================================================
# the host
# =====================================================================================================================

class _Peer(_Stream):
    """An authenticated or still-shaking-hands connection of the host's room."""

    def __init__(self, sock, ip, port, now, shake):
        super().__init__(sock, ip, port, now)
        self.shake: handshake.HostHandshake | None = shake
        self.session: handshake.Session | None = None
        self.guest_id: int | None = None
        self.name: str | None = None
        self.version: tuple = (0, 0, 0)
        self.seat: int | None = None
        self.joined_at = now
        self.status: int | None = None           # its LAUNCHED status, in the running launch


@dataclass
class LaunchInfo:
    match_id: int
    seats: int
    names: tuple
    sharing: int = 0
    rollback: int = 0               # the tier byte the guests were sent (0 the delay tier, else the prediction cap)


class _HostMatch:
    def __init__(self, match_id: int, seats: dict, names: tuple, now: float):
        self.match_id, self.seats, self.names = match_id, seats, names      # seats: seat -> _Peer
        self.senders: dict[int, datagram.Sender] = {}
        self.sink: Callable | None = None
        self.deadline = now + LAUNCH_WITHIN
        self.ready = False
        self.failed = False
        self.mirrored: set[int] = set()


class _HostLink:
    """The driver's `SeatLink` for the host's seat of one match."""
    seat = 0

    def __init__(self, room: 'RoomHost', match: _HostMatch):
        self._room, self._match = room, match

    def open(self, sink) -> None:
        self._match.sink = sink

    def send(self, to_seat: int, data: bytes) -> None:
        self._room._send_datagram(self._match, to_seat, data)

    def close(self) -> None:
        self._match.sink = None
        self._room._link_closed(self._match)


class RoomHost:
    def __init__(self, address: str, port: int = invitation.DEFAULT_PORT, secret: bytes | None = None, capacity: int = 4, *,
                 name: str = 'Host', tests: bool = False, log: RoomLog | None = None,
                 on_event: Callable[[dict], None] | None = None, clock: Callable[[], float] = time.monotonic,
                 rng: Callable[[int], bytes] = secrets.token_bytes, seat_rate: float | None = None,
                 sharing: int = seat_map.PER_PLAYER):
        self.address = invitation.check_bind_address(address, tests)      # before any socket: nothing else is ever bound
        if not CAPACITY_MIN <= capacity <= CAPACITY_MAX:
            raise ValueError('a room of 2 to 4 seats')
        if not isinstance(port, int) or isinstance(port, bool) or not (0 <= port <= 65535) or (port and port < 1024) \
                or (port == 0 and not tests):
            raise ValueError('a port from 1024 to 65535')
        self._secret = secret if secret is not None else invitation.new_secret()
        if len(self._secret) != invitation.SECRET_BYTES:
            raise ValueError('a secret of 16 bytes')
        self.port, self.capacity, self.tests = port, capacity, tests
        self.name = control.display_name(name, 'Host')
        self.lobby = lobbies.HostLobby(self.name, capacity, sharing)         # the room's lobby (pure rules, carried by this transport); `sharing`: the host's input mode
        self.log = log or RoomLog(None)
        self._on_event, self._clock, self._rng = on_event, clock, rng
        self._seat_rate = seat_rate
        self._lock = threading.RLock()
        self._counters = Counters()
        self._admission = Admission()
        self._nonces = NonceMemory()
        self._receiver = datagram.HostReceiver(self._counters, clock())
        self._peers: list[_Peer] = []
        self._outbox: list = []
        self._counts_due: tuple | None = None
        self._match: _HostMatch | None = None
        self._match_counter = 0
        self._idle_since = clock()
        self._idle_asked = False
        self._tcp = self._udp = None
        self._selector: selectors.BaseSelector | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.stats: collections.Counter = collections.Counter()

    # ---- opening and closing ----

    def invitation(self) -> str:
        """The invitation text of this room: the secret is in it, so it is shown to the player and never logged."""
        return invitation.format_invitation(self.address, self.port, self._secret, self.tests)

    def _bind(self) -> tuple[socket.socket, socket.socket]:
        last: Exception | None = None
        for attempt in range(8):
            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                _exclusive(tcp, True)
                _exclusive(udp, False)
                tcp.bind((self.address, self.port if attempt == 0 else 0))
                udp.bind((self.address, tcp.getsockname()[1]))
                tcp.listen(16)
                return tcp, udp
            except OSError as error:
                last = error
                tcp.close()
                udp.close()
        raise RoomError(f'the room could not open a port on {self.address}: {last.strerror or type(last).__name__}')

    def open(self) -> int:
        """Binds the room's two sockets and starts its thread; returns the port (the invitation carries it)."""
        with self._lock:
            if self._thread is not None:
                raise RoomError('the room is already open')
            tcp, udp = self._bind()
            tcp.setblocking(False)
            udp.setblocking(False)
            self._tcp, self._udp = tcp, udp
            self.port = tcp.getsockname()[1]
            self._selector = selectors.DefaultSelector()
            self._selector.register(tcp, selectors.EVENT_READ, 'accept')
            self._selector.register(udp, selectors.EVENT_READ, 'datagram')
            self._thread = threading.Thread(target=self._run, name='netplay-room-host', daemon=True)
            self._thread.start()
            self._act([self.lobby.roster_event()])
        self.log.room('opened', self.address, self.port)
        self._flush()
        return self.port

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(5)

    # ---- the loop ----

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                waiting = any(peer.waiting() for peer in self._peers)
                events = self._selector.select(BUSY_TICK if waiting else IDLE_TICK)
                self._tick(events, self._clock())
        except Exception as error:      # a fault of the transport ends the room visibly, it is not hidden
            self.log.note(f'the room stopped: {type(error).__name__}')
            self._emit({'event': 'room_error', 'detail': f'the room stopped: {type(error).__name__}'})
            self._flush()
        finally:
            self._shutdown()

    def _tick(self, events: list, now: float) -> None:
        """One turn of the loop: what the selector reported, then the timers, under the lock; then, outside it, the log's
        counts and what is handed to the caller."""
        with self._lock:
            for key, _mask in events:
                if key.data == 'accept':
                    self._accept(now)
                elif key.data == 'datagram':
                    self._receive_datagrams(now)
                else:
                    self._readable(key.data, now)
            self._timers(now)
        self._write_counts()
        self._flush()

    def _shutdown(self) -> None:
        with self._lock:
            for peer in list(self._peers):
                if peer.writer is not None and not peer.closed:
                    peer.send(control.Bye(BYE_CLOSED))
                self._close(peer, 'the room closed', quiet=True)
            for sock in (self._tcp, self._udp):
                if sock is not None:
                    try:
                        self._selector.unregister(sock)
                    except (KeyError, ValueError):
                        pass
                    sock.close()
            self._selector.close()
        self.log.counts(self._counters.take_window(), force=True)
        self.log.room('closed', self.address, self.port)
        self._emit({'event': 'room_closed'})
        self._flush()

    # ---- accepting and the handshake ----

    def _accept(self, now: float) -> None:
        for _ in range(16):
            try:
                sock, (ip, port) = self._tcp.accept()
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                self._counters.count('accept_error')
                return
            if not invitation.is_lan_address(ip, self.tests):       # a source outside the ranges: closed before any work
                self._counters.count('source_refused', ip)
                sock.close()
                continue
            if not self._admission.may_accept(ip, now):
                self._counters.count('admission', ip)
                sock.close()
                continue
            try:         # nothing the network does to one new socket may end the room for the others (N5)
                sock.setblocking(False)
                try:
                    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                peer = _Peer(sock, ip, port, now, handshake.HostHandshake(self._secret, now, self._nonces, self._rng))
                self._selector.register(sock, selectors.EVENT_READ, peer)
            except (OSError, ValueError, KeyError):
                self._counters.count('accept_error', ip)
                try:
                    sock.close()
                except OSError:
                    pass
                continue
            self._admission.opened(ip)
            self._peers.append(peer)

    def _readable(self, peer: _Peer, now: float) -> None:
        if peer.closed:
            return
        try:
            data = peer.sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._ended(peer, 'the connection broke', now)
            return
        if not data:
            self._ended(peer, 'the connection closed', now)
            return
        if peer.shake is not None:
            self._shaking(peer, data, now)
        else:
            self._frames(peer, data, now)

    def _ended(self, peer: _Peer, reason: str, now: float) -> None:
        """The peer ended its connection. Before the handshake was done that is a failure like any other: a stranger who
        connects, sends part of message 1 and closes must not be free to do it again at once (N1)."""
        if peer.shake is not None:
            self._failed(peer, 'closed', now)
        else:
            self._close(peer, reason)

    def _shaking(self, peer: _Peer, data: bytes, now: float) -> None:
        step = peer.shake.feed(data, now)
        if step.closed:
            self._failed(peer, step.reason, now)
            return
        if step.send:
            peer.write(step.send)
        if step.done:
            self._joined(peer, step, now)

    def _failed(self, peer: _Peer, reason: str, now: float) -> None:
        """A handshake that did not show the secret: closed with no byte, one failure for that address."""
        self._counters.count(f'handshake_{reason}', peer.ip)
        if self._admission.failed(peer.ip, now):
            self.log.note(f'address {peer.ip} refused for five minutes after three failed handshakes')
        self._close(peer, f'handshake {reason}', quiet=True)

    def _joined(self, peer: _Peer, step: handshake.Step, now: float) -> None:
        self._admission.closed(peer.ip)
        session = peer.shake.session
        peer.shake, peer.session = None, session
        if not self._admission.joined(peer.ip, now):       # a guest that joins and leaves in a loop (N2): nothing sent, no event
            self._counters.count('join_rate', peer.ip)
            self.log.note(f'address {peer.ip} refused for five minutes: it joined the room too often')
            self._close(peer, 'joined too often', quiet=True)
            return
        to_host, to_guest = handshake.tcp_keys(session.key)
        peer.writer = control.FrameWriter(to_guest)
        peer.reader = control.FrameReader(to_host, control.FROM_GUEST)
        peer.joined_at = peer.last_heard = peer.last_ping = now
        guests = [other for other in self._peers if other.guest_id is not None]
        if session.proto != handshake.PROTO:
            self._reject(peer, control.REJECT_VERSION)
        elif self._match is not None:
            self._reject(peer, control.REJECT_BUSY)
        elif len(guests) >= self.capacity - 1:
            self._reject(peer, control.REJECT_FULL)
        else:
            taken = {other.guest_id for other in guests}
            peer.guest_id = next(number for number in itertools.count(1) if number not in taken)
            peer.send(control.Welcome(peer.guest_id, self.capacity))
        if step.leftover:
            self._frames(peer, step.leftover, now)

    def _reject(self, peer: _Peer, reason: int) -> None:
        peer.send(control.Reject(reason))
        peer.closing, peer.closing_since = True, self._clock()
        self.log.note(f'{peer.ip} was turned away: {REJECTIONS[reason]}')

    # ---- the control stream ----

    def _frames(self, peer: _Peer, data: bytes, now: float) -> None:
        if peer.closing:
            return
        try:
            messages = peer.reader.feed(data)
        except control.FrameError as error:
            self._close(peer, _frame_error_text(error))
            return
        for message in messages:
            if not peer.bucket.take(now):
                self._close(peer, 'too many control frames')
                return
            peer.last_heard = now
            self._message(peer, message, now)
            if peer.closed:
                return

    def _message(self, peer: _Peer, message, now: float) -> None:
        if peer.guest_id is None:
            return
        if isinstance(message, control.Hello):
            if peer.name is not None:
                self._close(peer, 'a second HELLO')
                return
            others = [other.name for other in self._peers if other.name] + [self.name]
            fallback = f'Player {peer.guest_id + 1}'
            peer.name = control.unique_name(control.display_name(message.name, fallback), others)
            peer.version = message.version
            self.log.joined(peer.name, peer.ip)
            self._emit({'event': 'joined', 'guest': peer.guest_id, 'name': peer.name, 'address': peer.ip,
                        'version': list(peer.version)})
            self._act(self.lobby.joined(peer.guest_id, peer.name, now))
        elif isinstance(message, (control.Say, control.Ready, control.Answer)):
            self._act(self.lobby.on_message(peer.guest_id, message, now))
        elif isinstance(message, control.Launched):
            self._launched(peer, message)
        elif isinstance(message, control.End):
            match = self._match
            if match is not None and match.match_id == message.match_id and peer.seat is not None:
                self._inject(match, peer.seat, message.reason, message.who)
        elif isinstance(message, control.Ping):
            peer.send(control.Pong(message.time_ms))
        elif isinstance(message, control.Bye):
            self._close(peer, 'left the room')

    def _launched(self, peer: _Peer, message: control.Launched) -> None:
        match = self._match
        if match is None or match.match_id != message.match_id or peer.seat is None or peer.status is not None:
            self._counters.count('launched_ignored', peer.ip)
            return
        peer.status = message.status
        if message.status != control.LAUNCHED_READY:
            texts = {control.LAUNCHED_NOT_OWNED: 'does not have the game', control.LAUNCHED_OTHER_STAMP: 'has another version of the game',
                     control.LAUNCHED_FAILED: 'could not start the game'}
            self._fail_launch(match, f'{peer.name} {texts.get(message.status, "could not start the game")}')
        elif all(seat_peer.status == control.LAUNCHED_READY for seat_peer in match.seats.values()):
            match.ready = True
            self.lobby.playing()
            self.log.match(match.match_id, 'every guest has its game ready')
            self._emit({'event': 'all_launched', 'match_id': match.match_id})

    def _fail_launch(self, match: _HostMatch, reason: str) -> None:
        if match.failed:
            return
        match.failed = True
        self.log.match(match.match_id, f'launch failed: {reason}')
        for peer in match.seats.values():
            if not peer.closed:
                peer.send(control.End(match.match_id, wire.BYE_HOST_CLOSED, wire.NO_SEAT))
        self._emit({'event': 'launch_failed', 'match_id': match.match_id, 'detail': reason})
        self._end_match(match, 'launch_failed')

    # ---- launching and ending a match ----

    def launch(self, *, machine: str, stamp: bytes, rom_sha: bytes, delay: int = 0, digest_every: int = 60,
               redundancy: int = 3, options: str = '', guests=None, sharing: int = seat_map.PER_PLAYER,
               rollback: int = 0, save: bytes | None = None) -> LaunchInfo:
        """Starts a match: seats are given in the order of `guests` (guest ids, the lobby's seat order) or, without it, in
        the order the guests joined; `rollback` is the tier byte (0 the delay tier, 1 to `control.MAX_ROLLBACK` the rollback tier with that
        prediction cap), the host's decision (`rollback.choose_tier`); keys are derived for this match and this seat, and each of them gets its LAUNCH. A guest
        not named stays in the room and is not part of the match. Raises `RoomError` when that cannot be done."""
        with self._lock:
            if self._thread is None or self._stop.is_set():
                raise RoomError('the room is not open')
            if self._match is not None:
                raise RoomError('a match is already running')
            named = [peer for peer in self._peers if peer.name is not None and not peer.closed and peer.guest_id is not None]
            if guests is None:
                ready = sorted(named, key=lambda peer: peer.guest_id)
            else:
                by_id = {peer.guest_id: peer for peer in named}
                if len(set(guests)) != len(guests) or any(guest not in by_id for guest in guests):
                    raise RoomError('a seated guest is not in the room')
                ready = [by_id[guest] for guest in guests]
            if not ready:
                raise RoomError('nobody has joined the room')
            if not (isinstance(stamp, bytes) and len(stamp) == 32 and isinstance(rom_sha, bytes) and len(rom_sha) == 32):
                raise RoomError('the game is not identified')
            if not seat_map.allowed(machine, sharing):
                raise RoomError('this machine plays in input sharing only' if seat_map.valid(sharing) else 'an input mode that does not exist')
            if not control.valid_tier_byte(rollback):
                raise RoomError(f'a prediction cap of 1 to {control.MAX_ROLLBACK} frames, or the delay tier')
            if save is not None and len(save) > control.MAX_SAVE:
                raise RoomError('the host game\'s save is larger than a room carries')
            self._match_counter += 1
            match_id, now = self._match_counter, self._clock()
            names = (self.name,) + tuple(peer.name for peer in ready)
            seats = {index + 1: peer for index, peer in enumerate(ready)}
            keys = {}
            for seat, peer in seats.items():
                peer.seat, peer.status = seat, None
                keys[seat] = handshake.udp_keys(peer.session.key, match_id, seat)
            kwargs = {} if self._seat_rate is None else {'rate': self._seat_rate, 'burst': max(60.0, self._seat_rate / 4)}
            self._receiver.begin_match(match_id, {seat: (seats[seat].ip, keys[seat][0]) for seat in seats}, now,
                                       seat_count=len(names), **kwargs)
            match = self._match = _HostMatch(match_id, seats, names, now)
            self._act(self.lobby.begin([peer.guest_id for peer in ready], match_id))
            for seat, peer in seats.items():
                match.senders[seat] = datagram.Sender(keys[seat][1], match_id, 0)
                # The host's save first (lobby version 4): every seat plays on it, in memory, for this match.
                data = save or b''
                peer.send(control.SaveHead(len(data), hashlib.sha256(data).digest()))
                for offset in range(0, len(data), control.SAVE_CHUNK):
                    peer.send(control.SaveData(offset, data[offset:offset + control.SAVE_CHUNK]))
                peer.send(control.Launch(match_id, seat, len(names), delay, digest_every, redundancy, machine, stamp,
                                         rom_sha, names, options, sharing, rollback))
        self.log.launch(match_id, machine, stamp, len(names), delay)
        self._flush()
        return LaunchInfo(match_id, len(names), names, sharing, rollback)

    def link(self) -> _HostLink:
        """The `SeatLink` of the host's seat for the running match."""
        with self._lock:
            if self._match is None:
                raise RoomError('no match is running')
            return _HostLink(self, self._match)

    def abort(self, reason: str) -> None:
        """The launch in progress is called off (the host's own game did not start): the guests are told."""
        with self._lock:
            if self._match is not None:
                self._fail_launch(self._match, reason)
        self._flush()

    def end_match(self, reason: str = 'ended') -> None:
        """The match is over for this room (its driver finished, for `reason`: a driver outcome): the datagram state of it is
        dropped and every guest is brought back to the lobby."""
        with self._lock:
            if self._match is not None:
                self._end_match(self._match, reason)
        self._flush()

    def _link_closed(self, match: _HostMatch) -> None:
        with self._lock:
            if self._match is match:
                self._end_match(match)

    def _end_match(self, match: _HostMatch, reason: str = 'ended') -> None:
        if self._match is not match:
            return
        self._match = None
        self._receiver.end_match()
        for peer in match.seats.values():
            peer.seat = None
        self._act(self.lobby.finished(match.match_id, reason))

    def kick(self, guest_id: int) -> bool:
        with self._lock:
            for peer in self._peers:
                if peer.guest_id == guest_id and not peer.closed:
                    peer.send(control.Reject(control.REJECT_KICKED))
                    peer.closing, peer.closing_since = True, self._clock()
                    return True
        return False

    def roster(self) -> list[dict]:
        with self._lock:
            return [{'guest': peer.guest_id, 'name': peer.name, 'address': peer.ip, 'version': list(peer.version)}
                    for peer in sorted((item for item in self._peers if item.name and not item.closed),
                                       key=lambda item: item.guest_id)]

    # ---- the lobby ----

    def _act(self, actions: list) -> None:
        """What the lobby asked for: control messages to the guests (named, still here) and events for the caller."""
        for action in actions:
            if isinstance(action, lobbies.Event):
                self._emit(action.data)
                continue
            for peer in self._peers:
                if (peer.guest_id is not None and peer.name is not None and not peer.closed and not peer.closing
                        and (action.to is None or action.to == peer.guest_id)):
                    peer.send(action.message)

    def lobby_select(self, game: control.Game | None) -> Refusal | None:
        """The host picks a game (None: none): everyone is asked again. A `Refusal` says why not."""
        with self._lock:
            actions, refusal = self.lobby.select(game, self._clock())
            self._act(actions)
        self._flush()
        return refusal

    def lobby_sharing(self, sharing: int) -> Refusal | None:
        """The host's input mode (`seat_map`): one controller per player, or input sharing "everyone" / "turns". In the lobby only."""
        with self._lock:
            refusal = self.lobby.set_sharing(sharing)
        self._flush()
        return refusal

    def lobby_move(self, guest: int, seat: int) -> Refusal | None:
        with self._lock:
            refusal = self.lobby.move(guest, seat)
        self._flush()
        return refusal

    def lobby_say(self, text: str, phrase: int = 0) -> None:
        """A line of chat from the host (free text, or a phrase by number)."""
        with self._lock:
            self._act(self.lobby.say(0, text, self._clock(), phrase))
        self._flush()

    def lobby_can_launch(self, need_ready: bool = False) -> Refusal | None:
        """Why a lobby launch would be refused now, or None (nothing changes: the host asks before it starts its own game)."""
        with self._lock:
            plan = self.lobby.plan_launch(need_ready)
        return plan if isinstance(plan, Refusal) else None

    def lobby_launch(self, *, need_ready: bool = False, delay: int = 0, digest_every: int = 60,
                     redundancy: int = 3, rollback: int = 0, options: str | None = None,
                     save: bytes | None = None) -> LaunchInfo | Refusal:
        """Starts the match of the host's pick with the guests who have the game (and are ready, if `need_ready`). `options`:
        the run-changing options every seat plays with (the pick's merged with the host game's own); None: the pick's."""
        try:
            with self._lock:
                plan = self.lobby.plan_launch(need_ready)
                if isinstance(plan, Refusal):
                    return plan
                try:
                    return self.launch(machine=plan.game.machine, stamp=plan.stamp, rom_sha=plan.rom, delay=delay,
                                       digest_every=digest_every, redundancy=redundancy,
                                       options=plan.options if options is None else options, guests=plan.guests, save=save,
                                       sharing=plan.sharing, rollback=rollback)
                except RoomError as error:
                    return Refusal(error.reason)
        finally:
            self._flush()

    # ---- datagrams ----

    def _receive_datagrams(self, now: float) -> None:
        for _ in range(64):
            try:
                data, source = self._udp.recvfrom(datagram.READ_SIZE)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:         # ConnectionResetError after a datagram sent to a closed port; 10040 for a long one
                self._counters.count('receive_error')
                continue
            accepted = self._receiver.receive(source, data, now)
            if accepted is not None:
                self.stats['datagrams_in'] += 1
                self._outbox.append(('sink', self._match, accepted.seat, accepted.packet))

    def _send_datagram(self, match: _HostMatch, to_seat: int, data: bytes) -> None:
        with self._lock:
            if match is not self._match or self._udp is None:
                return
            peer, sender, channel = match.seats.get(to_seat), match.senders.get(to_seat), self._receiver.channels.get(to_seat)
            if peer is None or sender is None or channel is None or channel.port is None:
                self._counters.count('no_address')         # a seat's UDP address is learned from its first datagram
                return
            split = datagram.split_inner(data, 0)
            if split is None:
                self._counters.count('bad_outgoing')
                return
            kind, body, flags = split
            try:
                packet = sender.pack(kind, body, flags)
                self._udp.sendto(packet, (channel.ip, channel.port))
                self.stats['datagrams_out'] += 1
            except (OSError, ValueError):
                self._counters.count('send_error')
                return
            if kind == wire.BYE and to_seat not in match.mirrored and len(body) == 6:
                match.mirrored.add(to_seat)          # the control stream says it too, reliably
                reason, _frame, who = struct.unpack('<BIB', body)
                if reason in control.BYE_REASONS_WIRE and (who < control.MAX_SEATS or who == wire.NO_SEAT):
                    peer.send(control.End(match.match_id, reason, who))

    def _inject(self, match: _HostMatch, seat: int, reason: int, who: int) -> None:
        """What the control stream proved (an END, said reliably): the driver is told with the BYE of that seat."""
        self._outbox.append(('sink', match, seat, wire.encode_bye(seat, reason, 0, who)))

    # ---- time ----

    def _timers(self, now: float) -> None:
        for peer in list(self._peers):
            if peer.closed:
                if not peer.dead:        # a write that failed or overflowed marked it closed: its socket and place go now
                    self._close(peer, 'the peer did not read what was sent' if peer.overflow else 'the connection broke')
                continue
            if peer.shake is not None:
                if peer.shake.expired(now):
                    self._failed(peer, 'deadline', now)
                continue
            if peer.closing:
                if not peer.waiting() or now - peer.closing_since >= CLOSING_SECONDS:
                    self._close(peer, 'turned away', quiet=True)
                continue
            if now - peer.last_heard >= SILENCE:
                self._close(peer, 'silent for ten seconds')
            elif peer.guest_id is not None and peer.name is None and now - peer.joined_at >= HELLO_WITHIN:
                self._close(peer, 'no HELLO')
            elif now - peer.last_ping >= PING_EVERY:
                peer.last_ping = now
                peer.send(control.Ping(int(now * 1000) & 0xffffffff))
        for peer in list(self._peers):
            if peer.waiting() and not peer.closed and not peer.flush():
                self._close(peer, 'the connection broke')
        match = self._match
        if match is not None:
            if not match.ready and not match.failed and now >= match.deadline:
                self._fail_launch(match, 'a guest did not answer the launch')
            for seat in self._receiver.over(now):
                peer = match.seats.get(seat)
                self._receiver.drop_seat(seat)
                if peer is not None and not peer.closed:
                    self.log.note(f'seat {seat + 1} ({peer.name}) is dropped: it sent more datagrams than the limit for five seconds')
                    self._emit({'event': 'seat_dropped', 'seat': seat, 'detail': 'sent more than the packet limit for five seconds'})
                    self._close(peer, 'above the datagram limit')
        if self._match is not None or any(peer.guest_id is not None for peer in self._peers):
            self._idle_since, self._idle_asked = now, False
        elif not self._idle_asked and now - self._idle_since >= IDLE_ASK:
            self._idle_asked = True      # the window asks; the sockets close when the converter says `close_room`
            self.log.note('the room has been empty for thirty minutes')
            self._emit({'event': 'room_idle', 'detail': 'nobody has been in the room for thirty minutes'})
        if self._counts_due is None and self.log.due(now):
            self._counts_due = (self._counters.take_window(), now)      # written after the lock is released (N3)
        self._act(self.lobby.tick(now))

    def _write_counts(self) -> None:
        """The ten-second lines of counts, outside the room's lock: the file is the slow part, and the driver needs the
        lock to send (N3). Only the I/O thread calls this."""
        due, self._counts_due = self._counts_due, None
        if due is not None:
            self.log.counts(due[0], due[1])

    def _close(self, peer: _Peer, reason: str, quiet: bool = False) -> None:
        if peer.dead:
            return
        peer.dead = True
        with peer.lock:
            peer.closed = True
        try:
            self._selector.unregister(peer.sock)
        except (KeyError, ValueError):
            pass
        try:
            peer.sock.close()
        except OSError:
            pass
        if peer.shake is not None:
            self._admission.closed(peer.ip)
        if peer in self._peers:
            self._peers.remove(peer)
        if peer.name is not None and peer.guest_id is not None:
            self.lobby.left(peer.guest_id)
        if peer.name is not None and not quiet:
            self.log.left(peer.name, peer.ip, reason)
            self._emit({'event': 'left', 'guest': peer.guest_id, 'name': peer.name, 'detail': reason})
        match = self._match
        if match is not None and peer.seat is not None and match.seats.get(peer.seat) is peer:
            self._outbox.append(('sink', match, peer.seat, wire.encode_bye(peer.seat, wire.BYE_LEFT, 0)))
            self._receiver.drop_seat(peer.seat)
            if not match.ready:         # a guest went before the match began: the launch is off for everyone
                self._fail_launch(match, f'{peer.name or "a guest"} left before the match began')

    # ---- handing over, outside the lock ----

    def _emit(self, event: dict) -> None:
        self._outbox.append(('event', event))

    def _flush(self) -> None:
        with self._lock:
            items, self._outbox = self._outbox, []
        for item in items:
            try:
                if item[0] == 'event':
                    if self._on_event is not None:
                        self._on_event(item[1])
                else:
                    _tag, match, seat, packet = item
                    sink = None if match is None else match.sink
                    if sink is not None and packet is not None:
                        sink(seat, packet)
            except Exception as error:        # a caller's fault never stops the room; it is said
                self.log.note(f'a callback failed: {type(error).__name__}')

    @property
    def counters(self) -> dict:
        return dict(self._counters.total)


# =====================================================================================================================
# the guest
# =====================================================================================================================

class _GuestMatch:
    def __init__(self, launch: control.Launch, receiver: datagram.GuestReceiver, sender: datagram.Sender):
        self.launch, self.receiver, self.sender = launch, receiver, sender
        self.sink: Callable | None = None
        self.mirrored = False


class _GuestLink:
    """The driver's `SeatLink` for a guest's seat in one match: it talks to the host (seat 0) only."""

    def __init__(self, room: 'RoomGuest', match: _GuestMatch):
        self._room, self._match = room, match
        self.seat = match.launch.seat

    def open(self, sink) -> None:
        self._match.sink = sink

    def send(self, to_seat: int, data: bytes) -> None:
        if to_seat == 0:
            self._room._send_datagram(self._match, data)

    def close(self) -> None:
        self._match.sink = None
        self._room._link_closed(self._match)


class RoomGuest:
    """A guest in a room. `connect()` does the handshake (it raises `RoomError` with a sentence), then a thread keeps the
    control stream and the datagrams. `on_event(dict)` and `on_launch(control.Launch)` are called from that thread, after
    the lock is released, and must not block."""

    def __init__(self, invited: invitation.Invitation, name: str, *, tests: bool = False, version: tuple = (0, 0, 0),
                 on_event: Callable[[dict], None] | None = None, on_launch: Callable[[control.Launch], None] | None = None,
                 clock: Callable[[], float] = time.monotonic, rng: Callable[[int], bytes] = secrets.token_bytes):
        if not invitation.is_lan_address(invited.address, tests):
            raise RoomError('this invitation is not for a room on a local network')
        self.invited, self.tests, self.version = invited, tests, tuple(version)
        if len(self.version) != 3 or not all(isinstance(part, int) and not isinstance(part, bool) and 0 <= part <= 0xffff
                                             for part in self.version):
            raise ValueError('a version of three numbers')       # the HELLO carries three 16-bit numbers (L7)
        self.name = control.display_name(name, 'Guest')
        self.lobby = lobbies.GuestLobby(self.name)
        self._on_event, self._on_launch, self._clock, self._rng = on_event, on_launch, clock, rng
        self._lock = threading.RLock()
        self._counters = Counters()
        self._outbox: list = []
        self._stream: _Stream | None = None
        self._udp: socket.socket | None = None
        self._selector: selectors.BaseSelector | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._session: handshake.Session | None = None
        self._match: _GuestMatch | None = None
        self._last_match = 0
        self._save: dict | None = None          # the host's save being received (SAVE_HEAD, then SAVE_DATA in order)
        self._saves: dict[int, bytes | None] = {}   # match id -> the host's save of that launch (None: its game has none)
        self.guest_id: int | None = None
        self.capacity = 0
        self.stats: collections.Counter = collections.Counter()
        self._host = (invited.address, invited.port)
        self._gone = False

    def connect(self, timeout: float = handshake.HANDSHAKE_SECONDS) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(timeout)
            try:
                sock.connect(self._host)
            except OSError:
                raise RoomError(NO_ANSWER) from None
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass
            now = self._clock()
            shake = handshake.GuestHandshake(self.invited.secret, now, self._rng)
            try:
                sock.sendall(shake.first())
                step = handshake.Step()
                while not step.done:
                    sock.settimeout(max(0.05, shake.deadline - self._clock()))
                    data = sock.recv(256)
                    if not data:
                        raise RoomError(NO_ANSWER)
                    step = shake.feed(data, self._clock())
                    if step.closed:
                        raise RoomError(NO_ANSWER)
                sock.sendall(step.send)
                to_host, to_guest = handshake.tcp_keys(shake.session.key)
                reader = control.FrameReader(to_guest, control.FROM_HOST)
                messages = reader.feed(step.leftover)
                while not messages:
                    sock.settimeout(max(0.05, shake.deadline + 5.0 - self._clock()))
                    data = sock.recv(1024)
                    if not data:
                        raise RoomError(NO_ANSWER)
                    messages = reader.feed(data)
            except (OSError, control.FrameError):
                raise RoomError(NO_ANSWER) from None
            first = messages[0]
            if isinstance(first, control.Reject):
                raise RoomError(REJECTIONS[first.reason])
            if not isinstance(first, control.Welcome):
                raise RoomError(NO_ANSWER)
            local_ip = sock.getsockname()[0]
            if not invitation.is_lan_address(local_ip, self.tests):
                raise RoomError('this PC reaches that room through an address that is not on a local network')
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                _exclusive(udp, False)
                udp.bind((local_ip, 0))
                udp.setblocking(False)
            except OSError:
                udp.close()
                raise RoomError('this PC could not open a datagram port') from None
        except BaseException:
            sock.close()
            raise
        sock.setblocking(False)
        stream = _Stream(sock, self.invited.address, self.invited.port, self._clock())
        stream.writer, stream.reader = control.FrameWriter(to_host), reader
        self._stream, self._udp, self._session = stream, udp, shake.session
        self.guest_id, self.capacity = first.guest_id, first.capacity
        self.lobby.me = first.guest_id
        stream.send(control.Hello(self.version, self.name))
        self._selector = selectors.DefaultSelector()
        self._selector.register(sock, selectors.EVENT_READ, 'tcp')
        self._selector.register(udp, selectors.EVENT_READ, 'udp')
        self._thread = threading.Thread(target=self._run, name='netplay-room-guest', daemon=True)
        self._thread.start()
        self._emit({'event': 'joined_room', 'guest': self.guest_id, 'capacity': self.capacity})
        with self._lock:
            for message in messages[1:]:
                self._message(message, self._clock())
        self._flush()

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(5)

    # ---- the loop ----

    def _run(self) -> None:
        try:
            while not self._stop.is_set() and not self._gone:
                events = self._selector.select(BUSY_TICK if self._stream.waiting() else IDLE_TICK)
                now = self._clock()
                with self._lock:
                    for key, _mask in events:
                        if key.data == 'tcp':
                            self._readable(now)
                        else:
                            self._receive_datagrams(now)
                    self._timers(now)
                self._flush()
        except Exception as error:
            self._emit({'event': 'room_error', 'detail': f'the connection stopped: {type(error).__name__}'})
            self._host_gone('the connection stopped')
            self._flush()
        finally:
            self._shutdown()

    def _shutdown(self) -> None:
        with self._lock:
            if not self._gone and self._stream is not None and not self._stream.closed:
                self._stream.send(control.Bye(BYE_LEFT))
                self._stream.flush()
            self._gone = True
            for sock in (self._stream.sock, self._udp):
                try:
                    self._selector.unregister(sock)
                except (KeyError, ValueError):
                    pass
                sock.close()
            self._selector.close()
        self._flush()

    def _readable(self, now: float) -> None:
        stream = self._stream
        try:
            data = stream.sock.recv(4096)
        except (BlockingIOError, InterruptedError):
            return
        except OSError:
            self._host_gone('the connection to the host broke')
            return
        if not data:
            self._host_gone('the host closed the connection')
            return
        try:
            messages = stream.reader.feed(data)
        except control.FrameError as error:
            self._host_gone(_frame_error_text(error))
            return
        for message in messages:
            # A chunk of the save the host announced, within its announced size, is not counted against the frame rate (a
            # save of a few hundred KB is hundreds of frames); anything else is.
            announced = (isinstance(message, control.SaveData) and self._save is not None
                         and message.offset == len(self._save['data']) and message.offset + len(message.data) <= self._save['size'])
            if not announced and not stream.bucket.take(now):
                self._host_gone('too many control frames')
                return
            stream.last_heard = now
            self._message(message, now)
            if self._gone:
                return

    def _message(self, message, now: float) -> None:
        stream = self._stream
        if isinstance(message, control.Ping):
            stream.send(control.Pong(message.time_ms))
        elif isinstance(message, control.SaveHead):
            self._save = {'size': message.size, 'sha256': message.sha256, 'data': bytearray()}
        elif isinstance(message, control.SaveData):
            save = self._save
            if save is None or message.offset != len(save['data']) or message.offset + len(message.data) > save['size']:
                self._host_gone('the host\'s save broke the rules')
                return
            save['data'] += message.data
        elif isinstance(message, control.Launch):
            self._launch(message, now)
        elif isinstance(message, (control.Roster, control.Chat, control.Select, control.Notice, control.Back)):
            self._act(self.lobby.on_message(message, now))
        elif isinstance(message, control.End):
            match = self._match
            if match is not None and match.launch.match_id == message.match_id:
                self._outbox.append(('sink', match, 0, wire.encode_bye(0, message.reason, 0, message.who)))
        elif isinstance(message, control.Reject):
            self._host_gone(REJECTIONS[message.reason])
        elif isinstance(message, control.Bye):
            self._host_gone('the host closed the room')

    def _launch(self, launch: control.Launch, now: float) -> None:
        stream = self._stream
        if self._match is not None or launch.match_id <= self._last_match:
            self._counters.count('launch_ignored')
            return
        self._last_match = launch.match_id
        if not (control.MAX_SEATS >= launch.seats >= 2 and 1 <= launch.seat < launch.seats):
            stream.send(control.Launched(launch.match_id, control.LAUNCHED_FAILED))
            return
        if not seat_map.allowed(launch.machine, launch.sharing):      # a handheld is played in input sharing only, on both ends
            stream.send(control.Launched(launch.match_id, control.LAUNCHED_FAILED))
            return
        status = self.lobby.launch_status(launch)       # the game this PC said "same" to, or the host's launch is refused
        if status != control.LAUNCHED_READY:
            stream.send(control.Launched(launch.match_id, status))
            self._counters.count('launch_not_the_pick')
            self._emit({'event': 'launch_refused', 'match_id': launch.match_id,
                        'detail': 'this PC does not hold the game the host picked, in the same version'})
            return
        # The host's save of this launch: complete and the bytes it announced, or the launch fails (never a guess).
        save, self._save = self._save, None
        if save is None or len(save['data']) != save['size'] or hashlib.sha256(bytes(save['data'])).digest() != save['sha256']:
            stream.send(control.Launched(launch.match_id, control.LAUNCHED_FAILED))
            self._counters.count('launch_without_save')
            return
        self._saves = {launch.match_id: bytes(save['data']) if save['size'] else None}
        to_host, to_guest = handshake.udp_keys(self._session.key, launch.match_id, launch.seat)
        receiver = datagram.GuestReceiver(self._counters, self._host, launch.match_id, launch.seat, to_guest, launch.seats, now)
        self._match = _GuestMatch(launch, receiver, datagram.Sender(to_host, launch.match_id, launch.seat))
        if self._on_launch is not None:
            self._outbox.append(('launch', launch))

    def _act(self, actions: list) -> None:
        """What the lobby asked for: control messages for the host and events for the caller."""
        for action in actions:
            if isinstance(action, lobbies.Event):
                self._emit(action.data)
            elif self._stream is not None and not self._stream.closed:
                self._stream.send(action.message)

    def lobby_say(self, text: str, phrase: int = 0) -> None:
        """A line of chat from this guest (cleaned and limited here as the host will, so that the host has nothing to refuse)."""
        with self._lock:
            self._act(self.lobby.say(text, self._clock(), phrase))
        self._flush()

    def lobby_ready(self, ready: bool) -> None:
        with self._lock:
            self._act(self.lobby.ready(ready, self._clock()))
        self._flush()

    def lobby_answer(self, selection: int, status: int, reasons: int = 0, version=(0, 0, 0)) -> None:
        """This PC's answer to the host's pick number `selection` (the caller looked in its own library)."""
        with self._lock:
            self._act(self.lobby.answer(selection, status, reasons, version))
        self._flush()

    def take_save(self, match_id: int) -> bytes | None:
        """The host's save of that launch (None: the host's game has none); given once."""
        with self._lock:
            return self._saves.pop(match_id, None)

    def launched(self, match_id: int, status: int) -> None:
        """The caller's answer to a LAUNCH (ready, or why not). Anything but ready drops that match's datagram state."""
        with self._lock:
            if self._stream is not None and not self._stream.closed:
                self._stream.send(control.Launched(match_id, status))
            match = self._match
            if status != control.LAUNCHED_READY and match is not None and match.launch.match_id == match_id:
                self._match = None

    def link(self) -> _GuestLink:
        with self._lock:
            if self._match is None:
                raise RoomError('no match is running')
            return _GuestLink(self, self._match)

    def _link_closed(self, match: _GuestMatch) -> None:
        with self._lock:
            if self._match is match:
                self._match = None

    # ---- datagrams ----

    def _receive_datagrams(self, now: float) -> None:
        for _ in range(64):
            try:
                data, source = self._udp.recvfrom(datagram.READ_SIZE)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                self._counters.count('receive_error')
                continue
            match = self._match
            if match is None:
                self._counters.count('no_match', source[0])
                continue
            accepted = match.receiver.receive(source, data, now)
            if accepted is not None:
                self.stats['datagrams_in'] += 1
                self._outbox.append(('sink', match, 0, accepted.packet))

    def _send_datagram(self, match: _GuestMatch, data: bytes) -> None:
        with self._lock:
            if match is not self._match or self._udp is None:
                return
            split = datagram.split_inner(data, match.launch.seat)
            if split is None:
                self._counters.count('bad_outgoing')
                return
            kind, body, flags = split
            try:
                self._udp.sendto(match.sender.pack(kind, body, flags), self._host)
                self.stats['datagrams_out'] += 1
            except (OSError, ValueError):
                self._counters.count('send_error')
                return
            if kind == wire.BYE and not match.mirrored and len(body) == 6:
                match.mirrored = True
                reason, _frame, who = struct.unpack('<BIB', body)
                if reason in control.BYE_REASONS_WIRE and (who < control.MAX_SEATS or who == wire.NO_SEAT):
                    self._stream.send(control.End(match.launch.match_id, reason, who))

    # ---- time and the end ----

    def _timers(self, now: float) -> None:
        stream = self._stream
        if stream.closed or (stream.waiting() and not stream.flush()):
            self._host_gone('the host did not read what was sent' if stream.overflow else 'the connection to the host broke')
            return
        if now - stream.last_heard >= SILENCE:
            self._host_gone('the host was silent for ten seconds')
        elif now - stream.last_ping >= PING_EVERY:
            stream.last_ping = now
            stream.send(control.Ping(int(now * 1000) & 0xffffffff))

    def _host_gone(self, reason: str, event: bool = True) -> None:
        """The control connection is over: for the driver, the host is gone at once (no ten-second wait)."""
        if self._gone:
            return
        self._gone = True
        match = self._match
        if match is not None:
            self._outbox.append(('sink', match, 0, wire.encode_bye(0, wire.BYE_HOST_CLOSED, 0)))
        if event:
            self._emit({'event': 'host_gone', 'detail': reason, 'code': room_code(reason)})

    def _emit(self, event: dict) -> None:
        self._outbox.append(('event', event))

    def _flush(self) -> None:
        with self._lock:
            items, self._outbox = self._outbox, []
        for item in items:
            try:
                if item[0] == 'event':
                    if self._on_event is not None:
                        self._on_event(item[1])
                elif item[0] == 'launch':
                    if self._on_launch is not None:
                        self._on_launch(item[1])
                else:
                    _tag, match, seat, packet = item
                    sink = match.sink
                    if sink is not None:
                        sink(seat, packet)
            except Exception:
                pass

    @property
    def counters(self) -> dict:
        return dict(self._counters.total)
