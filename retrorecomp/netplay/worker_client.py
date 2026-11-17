"""The converter's side of a netplay worker: start the process, talk to it over its two pipes, read what it reports.

    worker = WorkerProcess(config, carry=lambda to_seat, data: ...)   # `carry` takes the packets the worker sends
    worker.start()
    worker.deliver(from_seat, data)       # a packet for the worker (from the network, or in tests the link simulator)
    worker.wait_for(lambda w: w.next_run >= 100, timeout)
    worker.stop(); worker.join(timeout)   # then worker.outcome, worker.history, worker.digests, ...

`config` is what `worker.py` reads: {"game": {"exe", "cwd", "env", "stdout", "stderr"}, "settings": {...}}, or, for a
room (stage 2, `room_worker.py`), {"room": {...}, "tests": ...} with the game given later by `launch`. The process
is the converter's own entry (`worker_command`): the packaged converter with `_netplay-worker`, or Python on
RetroRecomp.py. Its window is hidden. The channel is its stdin and stdout; no socket is opened here either (a room's
sockets belong to the worker). A room's worker reports `events` (what happened in the room) and asks `resolve(event)`
which game a host's launch names on this PC (a guest's `launch_request`): it answers with the `launch` call, or None.

The attributes of a finished (or running) worker read like a `LockstepDriver`'s: `outcome`, `detail`, `delay`,
`next_run`, `game_frame`, `paused`, `stats`, `pauses`, `desync`, `measured`, `boot_digest`, `exit_code`,
`exit_reason`, `pace`, `hello`, `sharing`, `token`, `tier`, `rollback_depths` from its latest STATUS, and `history`, `digests`, `pace_trace` from its RESULT.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path
import subprocess
import sys
import threading
from typing import Callable

from . import worker_channel as channel

from ..paths import ROOT     # the roots come from paths.py, never from a module's own file (the packaged exe)
COMMAND = '_netplay-worker'
EVENT_LIMIT = 1000                              # a room's events kept in `events`: the last ones (a hostile guest cannot grow it)
# What a worker that has not said a thing yet shows (a status says all of it once the driver has started).
DEFAULTS = {
    'phase': lambda: 'hello', 'outcome': lambda: None, 'detail': lambda: '', 'delay': lambda: None,
    'next_run': lambda: 0, 'game_frame': lambda: -1, 'paused': lambda: None, 'stats': dict, 'pauses': list,
    'desync': lambda: None, 'measured': lambda: None, 'boot_digest': lambda: None, 'exit_code': lambda: None,
    'exit_reason': lambda: None, 'pace': dict, 'hello': lambda: None, 'history': list, 'digests': dict,
    'pace_trace': list, 'sharing': lambda: 'per_player', 'token': lambda: 0, 'tier': lambda: 'delay',
    'rollback_depths': list, 'history_frames': lambda: 0, 'history_digest': lambda: '', 'restarts': list,
}


def worker_command() -> list[str]:
    """The command that starts a worker: the converter itself, with the internal command."""
    if getattr(sys, 'frozen', False):
        return [sys.executable, COMMAND]
    return [sys.executable, '-B', str(ROOT / 'RetroRecomp.py'), COMMAND]


class WorkerProcess:
    def __init__(self, config: dict, carry: Callable[[int, bytes], None] | None = None, command: list[str] | None = None,
                 log: Path | None = None, resolve: Callable[[dict], dict | None] | None = None,
                 on_event: Callable[[dict], None] | None = None):
        self.config, self.carry = config, carry
        self.command = command or worker_command()
        self.log = log                          # the worker's stderr (its own text; nothing is read from it)
        self.seat = config.get('settings', {}).get('seat', 0 if config.get('room', {}).get('role') == 'host' else None)
        self.resolve, self.on_event = resolve, on_event
        self.events: list[dict] = []            # a room's events, in order: the last `EVENT_LIMIT` only
        self.event_count = 0                    # every event ever reported (the number `wait_event(after=...)` counts in)
        self.event_totals: collections.Counter = collections.Counter()      # ... and how many of each name
        self.process: subprocess.Popen | None = None
        self.status: dict = {}
        self.result: dict | None = None
        self.results: list[dict] = []           # a room's results, one per match
        self.exit_code_of_process: int | None = None
        self._changed = threading.Condition()
        self._write_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    # ---- starting and talking ----

    def start(self) -> 'WorkerProcess':
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        errors = open(self.log, 'wb') if self.log else subprocess.DEVNULL
        try:
            self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                            cwd=str(ROOT), creationflags=flags)
        finally:
            if self.log:
                errors.close()
        self._thread = threading.Thread(target=self._reader, name=f'netplay-worker-{self.seat}', daemon=True)
        self._thread.start()
        self._send(channel.CONFIG, json.dumps(self.config).encode('utf-8'))
        return self

    def _send(self, kind: int, payload: bytes = b'') -> bool:
        data = channel.frame(kind, payload)
        with self._write_lock:
            try:
                self.process.stdin.write(data)
                self.process.stdin.flush()
                return True
            except (OSError, ValueError):       # the worker is gone
                return False

    def deliver(self, from_seat: int, data: bytes) -> None:
        self._send(channel.NET_IN, bytes([from_seat]) + data)

    def call(self, name: str, **fields) -> None:
        self._send(channel.CALL, json.dumps({'call': name, **fields}).encode('utf-8'))

    def stop(self) -> None:
        self.call('stop')

    def resume(self) -> None:
        self.call('resume')

    def pass_token(self, to: int | None = None) -> None:
        """Input sharing, "turns": pass the token to the next seat (the holder), or to seat `to` (the host)."""
        self.call('pass_token') if to is None else self.call('pass_token', to=to)

    def share_mode(self, mode: int) -> None:
        """Input sharing, the host: the shared match goes to "everyone" or "turns" (`seat_map.SHARED_ALL`, `SHARED_TURNS`)."""
        self.call('share_mode', mode=mode)

    def close_game_pipe(self) -> None:
        self.call('close_game_pipe')

    def _reader(self):
        reader = channel.Reader()
        try:
            while True:
                chunk = self.process.stdout.read1(65536)
                if not chunk:
                    break
                for kind, payload in reader.feed(chunk):
                    if kind == channel.NET_OUT and len(payload) > 1:
                        if self.carry is not None:
                            self.carry(payload[0], payload[1:])
                    elif kind == channel.EVENT:
                        self._event(json.loads(payload.decode('utf-8')))
                    elif kind == channel.STATUS:
                        self._take(json.loads(payload.decode('utf-8')), final=False)
                    elif kind == channel.RESULT:
                        self._take(json.loads(payload.decode('utf-8')), final=True)
        except (OSError, ValueError, channel.Broken):
            pass
        finally:
            with self._changed:
                self.exit_code_of_process = self.process.wait()
                self._changed.notify_all()

    def _event(self, event: dict) -> None:
        with self._changed:
            self.events.append(event)
            self.event_count += 1
            self.event_totals[event.get('event')] += 1
            del self.events[:-EVENT_LIMIT]
            self._changed.notify_all()
        if self.on_event is not None:
            self.on_event(event)
        if event.get('event') == 'launch_request' and self.resolve is not None:
            reply = self.resolve(event)
            if reply and 'call' in reply:
                fields = dict(reply)
                self.call(fields.pop('call'), **fields)

    def wait_event(self, name: str, timeout: float, after: int = 0) -> dict | None:
        """Sleeps until an event of that name has been reported (from the `after`-th event ever, as `event_count` counted
        it); the event, or None."""
        found = []

        def seen(worker):
            first = max(0, after - (worker.event_count - len(worker.events)))
            found[:] = [event for event in worker.events[first:] if event.get('event') == name][:1]
            return bool(found)
        with self._changed:
            self._changed.wait_for(lambda: seen(self) or self.exit_code_of_process is not None, timeout)
        return found[0] if found else None

    def _take(self, values: dict, final: bool) -> None:
        with self._changed:
            if final:
                values['history'] = [tuple(words) for words in values.get('history', [])]
                values['digests'] = {int(frame): digest for frame, digest in values.get('digests', {}).items()}
                self.result = values
                self.results.append(values)
            self.status = {**self.status, **values}
            self._changed.notify_all()

    # ---- reading ----

    def wait_for(self, predicate: Callable[['WorkerProcess'], bool], timeout: float) -> bool:
        """Sleeps until `predicate(worker)` holds or the worker is gone; False when `timeout` passed first."""
        with self._changed:
            return self._changed.wait_for(lambda: predicate(self) or self.exit_code_of_process is not None,
                                          timeout) and predicate(self)

    def reached(self, frame: int, timeout: float) -> bool:
        return self.wait_for(lambda worker: worker.next_run >= frame, timeout)

    def join(self, timeout: float | None = None) -> bool:
        """True when the worker process ended and said its last word."""
        with self._changed:
            return self._changed.wait_for(lambda: self.exit_code_of_process is not None, timeout)

    @property
    def done(self) -> bool:
        return self.exit_code_of_process is not None

    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def kill(self) -> None:
        """Ends the worker, and with it (the game sees its pipe close) its game."""
        if self.process is not None and self.process.poll() is None:
            self.process.kill()

    def close(self) -> None:
        """Closes the worker's stdin: the converter going away, as the worker sees it (it ends the match as a seat
        leaving, and its game stops by itself)."""
        try:
            self.process.stdin.close()
        except OSError:
            pass

    def cleanup(self) -> None:
        """After the match: whatever is still running is ended, the pipes are closed."""
        self.kill()
        self.close()
        if self._thread is not None:
            self._thread.join(5)
        try:
            self.process.stdout.close()
        except OSError:
            pass

    def __getattr__(self, name):
        if name.startswith('_') or name in ('status', 'result'):
            raise AttributeError(name)
        if name not in DEFAULTS:
            raise AttributeError(name)
        value = self.status.get(name, DEFAULTS[name]())
        if name in ('desync', 'paused', 'measured') and value is not None:
            return tuple(value)
        if name == 'pauses':
            return [tuple(item) for item in value]
        if name == 'stats':
            return collections.defaultdict(int, value)
        return value

    def summary(self) -> str:
        """One line for a failure message: where the worker stood."""
        status = self.status
        seat = status.get('seat', self.seat)
        return (f'seat {"?" if seat is None else seat + 1}: {status.get("phase")}, delay {status.get("delay")}, next frame {status.get("next_run")}, '
                f'game at {status.get("game_frame")}, paused {status.get("paused")}, {status.get("outcome")} '
                f'{status.get("detail", "")}, process exit {self.exit_code_of_process}')
