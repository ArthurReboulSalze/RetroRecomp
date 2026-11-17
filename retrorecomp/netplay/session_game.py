"""One game executable started in a session: its two anonymous pipes, a reader thread, its end.

The game inherits exactly two handles (Windows) or file descriptors (POSIX) and learns them from
RETRORECOMP_NETPLAY_PIPE="<in>,<out>" (`native/hostkit/hostkit_session.h`). Nothing has a name another program
could open, and nothing is a socket. The reader thread blocks in a read of the pipe and hands whole messages to
the driver's sink; None is handed once, when the game closed its end or broke the rules.

A game may be started before its driver exists (`hold`): its messages are kept, in order, until `attach` hands them all over, so
a host can read its game's HELLO (`wait_hello`) before it says which tier the match is on. The game itself waits for its SETUP.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
from typing import Callable

from . import session_pipe as pipe

# A hidden-window test run (the conversion's checks) is never a session: the kit ignores the pipes there.
NEVER_IN_A_SESSION = ('RETRORECOMP_HOST_TEST_FRAMES',)


def _allow_foreground() -> None:
    """Windows: lets the game about to start take the foreground (its window then has the keyboard and the pads, as a game
    the player opened does). A process may only pass on a right it has: from a background worker this does nothing, and it
    is never an error."""
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)      # ASFW_ANY
    except (AttributeError, OSError):
        pass


class SessionGame:
    def __init__(self, executable: Path, cwd: Path | None = None, env: dict | None = None,
                 stdout: Path | None = None, stderr: Path | None = None):
        """Starts the game. `env` is added to this process's environment; `stdout` and `stderr` are files the
        game's own lines go to (nowhere when None: the pipes of the session are the only link that matters)."""
        environment = dict(os.environ)
        environment.update(env or {})
        for name in NEVER_IN_A_SESSION:
            environment.pop(name, None)
        self.executable = Path(executable)
        self.broken: str | None = None
        self._lock = threading.Lock()
        self._sink: Callable | None = None
        self._held: list | None = None              # `hold`: the messages that came before a sink was attached
        self._first = threading.Event()             # the HELLO (or the end) is among the held messages
        self._reading = False
        self._deliver_lock = threading.Lock()
        game_in, self._write = os.pipe()
        self._read, game_out = os.pipe()
        files = []
        try:
            outputs = {}
            for key, path in (('stdout', stdout), ('stderr', stderr)):
                if path is None:
                    outputs[key] = subprocess.DEVNULL
                else:
                    files.append(open(path, 'wb'))
                    outputs[key] = files[-1]
            kwargs = dict(cwd=cwd or self.executable.parent, env=environment, stdin=subprocess.DEVNULL, **outputs)
            if os.name == 'nt':
                import msvcrt
                handles = [msvcrt.get_osfhandle(game_in), msvcrt.get_osfhandle(game_out)]
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                environment[pipe.ENV] = f'{handles[0]},{handles[1]}'
                info = subprocess.STARTUPINFO()
                info.lpAttributeList = {'handle_list': handles}      # these two and no other handle of the converter
                kwargs.update(startupinfo=info, close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                environment[pipe.ENV] = f'{game_in},{game_out}'
                kwargs.update(pass_fds=(game_in, game_out))
            _allow_foreground()
            self.process = subprocess.Popen([str(self.executable)], **kwargs)
        except BaseException:
            for descriptor in (self._write, self._read):
                os.close(descriptor)
            self._write = self._read = None
            raise
        finally:
            os.close(game_in)
            os.close(game_out)
            for handle in files:
                handle.close()

    def attach(self, sink: Callable[[tuple[int, bytes] | None], None]) -> None:
        """Messages go to `sink` from now on, in order, from a thread of this game; None once, at the end."""
        with self._deliver_lock:
            held, self._held = self._held, None
            self._sink = sink
            for message in held or ():              # in order, before anything that comes next (the reader waits for this lock)
                sink(message)
            reading, self._reading = self._reading, True
        if not reading:
            threading.Thread(target=self._reader, name='netplay-game-pipe', daemon=True).start()

    def hold(self) -> None:
        """Starts reading the game's messages and keeps them for `attach` (once, before `attach`)."""
        with self._deliver_lock:
            if self._reading or self._sink is not None:
                raise RuntimeError('the game is already being read')
            self._held, self._reading = [], True
        threading.Thread(target=self._reader, name='netplay-game-pipe', daemon=True).start()

    def wait_hello(self, timeout: float) -> pipe.Hello | None:
        """The game's HELLO once it came (the game was started with `hold`), or None: too late, the game ended, or a HELLO that
        is not one. The message stays held for the driver, which judges it again."""
        if not self._first.wait(timeout):
            return None
        with self._deliver_lock:
            for message in self._held or ():
                if message is not None and message[0] == pipe.MSG_HELLO:
                    try:
                        return pipe.parse_hello(message[1])
                    except pipe.Broken:
                        return None
        return None

    def _give(self, message) -> None:
        with self._deliver_lock:
            if self._held is not None:
                self._held.append(message)
                if message is None or message[0] == pipe.MSG_HELLO:
                    self._first.set()
                return
            sink = self._sink
        sink(message)

    def _reader(self):
        reader = pipe.MessageReader()
        while True:
            try:
                chunk = os.read(self._read, 4096)       # blocks: no polling
            except OSError:
                chunk = b''
            if not chunk:
                break
            try:
                messages = reader.feed(chunk)
            except pipe.Broken as error:
                self.broken = str(error)
                break
            for message in messages:
                self._give(message)
        self._give(None)

    def send(self, data: bytes) -> bool:
        """False when the game is gone (its end of the pipe is closed)."""
        with self._lock:
            if self._write is None:
                return False
            try:
                os.write(self._write, data)
                return True
            except OSError:
                return False

    def alive(self) -> bool:
        return self.process.poll() is None

    def close_pipe(self) -> None:
        with self._lock:
            if self._write is not None:
                try:
                    os.close(self._write)
                except OSError:
                    pass
                self._write = None

    def finish(self, timeout: float = 10.0) -> int | None:
        """Closes the worker's end and waits for the game; a game still there after `timeout` is ended. Its exit code."""
        self.close_pipe()
        try:
            code = self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = self.process.wait(timeout=5)
        if self._read is not None:
            try:
                os.close(self._read)
            except OSError:
                pass
            self._read = None
        return code
