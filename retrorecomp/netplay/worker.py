"""The netplay worker process: one per seat, started by the converter, owning the driver and its game's pipes.

    RetroRecomp.py _netplay-worker       (the packaged converter: Retro-Recomp.exe _netplay-worker)

The converter's window (Tk) is never in the loop: the worker is a process of its own whose driver thread sleeps on
its queue, so a cover being drawn or a file dialog cannot make a frame late. The worker reads its stdin and writes
its stdout: the local channel of `worker_channel` (two anonymous pipes, no socket, no port). It first reads CONFIG
(the game to start, this seat's `Settings`, test sources), starts the game with its own two inherited pipes
(`SessionGame`) and the driver (`LockstepDriver`, or `RollbackDriver` when the settings ask for rollback), and then

* hands the packets the driver sends to the converter side (NET), and the packets the converter side delivers to the
  driver (the `ChannelLink` below is the driver's `SeatLink`);
* acts on CALL (stop, resume);
* reports STATUS while the state changes (at most ten times a second);
* sends RESULT when the match ended, and exits with 0 (2 when it could not start).

When the converter goes away (its end of the channel closes) the worker ends the match as a seat leaving, and the
game, which sees its own pipe close, stops by itself. Nothing is printed on stdout; the worker's text goes to stderr.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading

from . import scripted_inputs
from . import worker_channel as channel
from .lockstep import Settings
from .rollback import driver_for
from .session_game import SessionGame

STATUS_EVERY = 0.1           # seconds between two looks at the driver for a change to report
RESULT_LIMIT = channel.MAX_PAYLOAD - 65536      # a RESULT above this is sent without its history (it would not fit)
TEST_FIELDS = {'local_source': None, 'words_filter': None, 'clock_ppm': 0, 'topology': 'star', 'opposites': ()}   # settings only a test may change
END_WAIT = 20.0              # after the converter went away: seconds the driver has to end the match


class ChannelLink:
    """The driver's link, in stage 1: packets for other seats go out over the channel and the converter side carries
    them; the ones it hands back are delivered to the driver. (The real network of stage 2 replaces this class.)"""

    def __init__(self, seat: int, writer: channel.Writer):
        self.seat, self.writer = seat, writer
        self._sink = None

    def open(self, sink) -> None:
        self._sink = sink

    def send(self, to_seat: int, data: bytes) -> None:
        self.writer.send(channel.NET_OUT, bytes([to_seat]) + data)

    def close(self) -> None:
        self._sink = None

    def deliver(self, from_seat: int, data: bytes) -> None:
        sink = self._sink
        if sink is not None:
            sink(from_seat, data)


def _seat_of(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def settings_from(values: dict, tests: bool = False) -> Settings:
    """The config's settings, with the test sources named in it. The test hooks (a scripted pad, a tampered word, a
    clock offset, the mesh) are taken only when the config says `"tests": true`: a worker that is not under test
    refuses them, and nothing a launch message says can ever set them (`launch.launch_settings`)."""
    fields = dict(values)
    if not tests:
        used = sorted(name for name, default in TEST_FIELDS.items() if fields.get(name, default) != default)
        if used:
            raise ValueError(f'test settings without "tests": true ({", ".join(used)})')
    local = scripted_inputs.local_source(fields.pop('local_source', None))
    words = scripted_inputs.words_filter(fields.pop('words_filter', None))
    fields['names'] = tuple(fields.get('names', ()))
    if 'opposites' in fields:
        fields['opposites'] = tuple(tuple(pair) for pair in fields['opposites'])
    return Settings(**fields, local_source=local, words_filter=words)


def result_message(result: dict, limit: int = RESULT_LIMIT) -> bytes:
    """The RESULT payload. A match so long that its history does not fit in one channel message is reported without
    the history and with the last digests only (`truncated`), never lost."""
    data = json.dumps(result).encode('utf-8')
    if len(data) > limit:
        digests = dict(list(result.get('digests', {}).items())[-64:])
        data = json.dumps({**result, 'history': [], 'digests': digests, 'truncated': True}).encode('utf-8')
    return data


def _read_config(fd: int, reader: channel.Reader) -> dict:
    while True:
        chunk = os.read(fd, 65536)
        if not chunk:
            raise channel.Broken('the converter closed the channel before the config')
        messages = reader.feed(chunk)
        if messages:
            if messages[0][0] != channel.CONFIG:
                raise channel.Broken('the first message is not the config')
            reader.leftover = messages[1:]      # whatever came in the same chunk is acted on by the worker, not lost
            return json.loads(messages[0][1].decode('utf-8'))


def run_worker(fd_in: int, fd_out: int) -> int:
    reader, writer = channel.Reader(), channel.Writer(fd_out)
    try:
        config = _read_config(fd_in, reader)
        if 'room' in config:            # stage 2: the worker's life is a room's, the game comes later in a `launch` call
            from .room_worker import run_room
            return run_room(config, reader, writer, fd_in)
        game = config['game']
        session = SessionGame(Path(game['exe']), cwd=Path(game['cwd']) if game.get('cwd') else None, env=game.get('env'),
                              stdout=Path(game['stdout']) if game.get('stdout') else None,
                              stderr=Path(game['stderr']) if game.get('stderr') else None)
        link = ChannelLink(config['settings']['seat'], writer)
        tests = config.get('tests') is True
        driver = driver_for(session, link, settings_from(config['settings'], tests))
    except Exception as error:      # the converter side is told, and the worker ends: nothing is hidden
        writer.send(channel.RESULT, json.dumps({'done': True, 'outcome': 'error',
                                                 'detail': f'the worker could not start: {type(error).__name__}: {error}',
                                                 'history': [], 'digests': {}, 'pace_trace': []}).encode('utf-8'))
        return 2
    finished = threading.Event()

    def call(message):
        name = message.get('call')
        if name == 'stop':
            driver.stop()
        elif name == 'resume':
            driver.resume()
        elif name == 'pass_token':
            driver.pass_token(_seat_of(message.get('to')))
        elif name == 'share_mode':
            driver.set_sharing(int(message.get('mode', 0)))
        elif name == 'close_game_pipe' and tests:       # tests: the worker loses its game
            driver.close_game_pipe()

    def from_converter():
        def act(kind, payload):
            if kind == channel.NET_IN and len(payload) > 1:
                link.deliver(payload[0], payload[1:])
            elif kind == channel.CALL:
                call(json.loads(payload.decode('utf-8')))
        try:
            for kind, payload in reader.leftover:
                act(kind, payload)
            while True:
                chunk = os.read(fd_in, 65536)
                if not chunk:
                    break
                for kind, payload in reader.feed(chunk):
                    act(kind, payload)
        except Exception:       # a closed channel, a broken one, a message that is not what it should be: the converter is gone
            pass
        if not finished.is_set():       # the converter is gone: this seat leaves, the game stops by itself
            driver.stop()
            if not finished.wait(END_WAIT):
                session.process.kill()

    def report():
        last = None
        while not finished.wait(STATUS_EVERY):
            status = driver.snapshot()
            if status != last:
                last = status
                writer.send(channel.STATUS, json.dumps(status).encode('utf-8'))

    threading.Thread(target=from_converter, name='netplay-worker-channel', daemon=True).start()
    threading.Thread(target=report, name='netplay-worker-status', daemon=True).start()
    driver.start()
    driver.join()
    finished.set()
    writer.send(channel.RESULT, result_message(driver.result()))
    return 0


def main() -> int:
    """The `_netplay-worker` command: the channel is this process's stdin and stdout, taken over so that nothing
    else can write on it (print goes to nowhere)."""
    fd_in, fd_out = os.dup(0), os.dup(1)
    if os.name == 'nt':
        import msvcrt
        msvcrt.setmode(fd_in, os.O_BINARY)
        msvcrt.setmode(fd_out, os.O_BINARY)
    for target, mode in ((0, os.O_RDONLY), (1, os.O_WRONLY)):
        null = os.open(os.devnull, mode)
        os.dup2(null, target)
        os.close(null)
    try:
        return run_worker(fd_in, fd_out)
    except Exception as error:      # never a traceback on the channel; the converter sees the exit code
        print(f'netplay worker: {type(error).__name__}: {error}', file=sys.stderr)
        return 3
