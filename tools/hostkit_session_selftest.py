"""The host kit's multiplayer session through its real loop, ROM-free (native/hostkit/hostkit_session.h).

    python -B tools/hostkit_session_selftest.py [--output DIR]

The kit's shell is compiled as an export compiles it, around the fake machine of tools/hostkit_session/fake.c (its state folds
the four ports' words of every frame), and driven through two anonymous pipes by a scripted worker written here, which folds the
same words in Python and compares digests. Scenarios: alone (no session: the game plays as before, F8 still saves); delay
(four ports, players 3 and 4 included); rollback (snapshots, loads, silent frames, then the live frame); a guest (no side
effects); pause for everyone; an option the machine cannot honour; the pipe lost; the restart (alone at once as before; in a
session the host's Shift+F1 is a request in its LOCAL and the machine restarts only on the worker's RUN, live or silent; a
guest's is refused); the match's state (the host's F8 / F9: requests in its LOCALs, saved and loaded only on the worker's
RUN, again after a correction; a guest's refused; a load with nothing saved ends the session). Runs under SDL's
dummy video and audio drivers (no window, no sound device). Needs the C toolchain and the pinned static SDL2 of `.deps`;
nothing is written outside DIR (default .build/hostkit-session-selftest). A few seconds.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import queue
import re
import struct
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# hostkit_session.h, read as the specification of the wire
HEADER = (ROOT / 'native/hostkit/hostkit_session.h').read_text(encoding='utf-8')
CONSTANTS = {name: int(value) for name, value in re.findall(r'\b(RRHK_\w+) = (\d+)', HEADER)}
ABI = int(re.search(r'#define RRHK_SESSION_ABI (\d+)', HEADER).group(1))
ENV = re.search(r'#define RRHK_SESSION_ENV "(\w+)"', HEADER).group(1)
M = (1 << 64) - 1


def ready() -> str | None:
    """Why the check cannot run here (no compiler, no SDL build), or None."""
    try:
        from retrorecomp.core import toolchain
        toolchain()
    except Exception as error:      # no compiler in this installation
        return f'no C toolchain: {error}'
    from retrorecomp.platforms import sdl_install_current
    if not sdl_install_current():
        return 'the pinned static SDL2 is not built (.deps/SDL)'
    return None


def cmake_text() -> str:
    from retrorecomp import hostkit
    native = (ROOT / 'native').as_posix()
    shell = ' '.join(f'"{native}/hostkit/{name}"' for name in hostkit.SHELL)
    return '\n'.join([
        'cmake_minimum_required(VERSION 3.21)', 'project(HostkitSession C)', 'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'find_package(SDL2 CONFIG REQUIRED)',
        f'add_executable(session_fake "{(ROOT / "tools/hostkit_session/fake.c").as_posix()}" {shell} '
        f'"{native}/platform_io.c" "{native}/retro_menu.c")',
        f'target_include_directories(session_fake PRIVATE "{native}")',
        'target_compile_definitions(session_fake PRIVATE _CRT_SECURE_NO_WARNINGS)',
        'target_link_libraries(session_fake PRIVATE SDL2::SDL2-static)',
        'if(NOT MSVC)\n  target_link_libraries(session_fake PRIVATE m)\nendif()']) + '\n'


def build(out: Path) -> Path:
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
    out.mkdir(parents=True, exist_ok=True)
    (out / 'CMakeLists.txt').write_text(cmake_text(), encoding='utf-8')
    cmake, generator = toolchain()
    log = out / 'build.log'
    run([cmake, '-S', out, '-B', out / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}'], log=log)
    run([cmake, '--build', out / 'build', '--config', 'Release', '--parallel', '4'], log=log)
    return build_executable(out / 'build', 'session_fake')


# ---- the fake machine's fold, as fake.c computes it ----

def mix(x: int) -> int:
    x = (x + 0x9e3779b97f4a7c15) & M
    x = ((x ^ (x >> 30)) * 0xbf58476d1ce4e5b9) & M
    x = ((x ^ (x >> 27)) * 0x94d049bb133111eb) & M
    return x ^ (x >> 31)


def clean(word: int) -> int:
    """The word as the game's session keeps it (rrhk_session.inc clean_word): the fake's eight action bits only, and
    opposite directions held together cancel (Up 8 / Down 4, Left 2 / Right 1)."""
    word &= 0xFF
    if word & 3 == 3:
        word &= ~3
    if word & 12 == 12:
        word &= ~12
    return word


RESTART = 0x5245534554       # what the fake's restart mixes into its accumulator (fake.c reset)


def battery(seed: int) -> bytes:
    """The fake's 64-byte battery of SESSION_FAKE_SAVE=seed."""
    return bytes((seed * 31 + i * 7) & 0xff for i in range(64))


def battery_start(data: bytes) -> int:
    """The fake's accumulator at power-on with that battery (its 8-byte words folded in)."""
    acc = 0x9e3779b97f4a7c15
    for i in range(0, len(data), 8):
        acc = mix(acc ^ int.from_bytes(data[i:i + 8], 'little'))
    return acc


def digest_of(history: list[tuple[int, int, int, int]], restarts=(), states=None, sticks=None, start=None) -> int:
    """The fake's digest after `history`; `restarts`: the frames the machine restarted before (the frame count goes on);
    `states`: {frame: 'save' | 'load'}, the match's state saved or loaded before that frame (its whole state: the fake's own
    frame count comes back with a load); `sticks`: per frame, every port's four int8 sticks (a machine with sticks: each
    port's values times 258 fold in after the words, as the fake reads them)."""
    acc, frames = (0x9e3779b97f4a7c15 if start is None else start), 0
    restarts, states, slot = set(restarts), states or {}, None
    for index, (p1, p2, p3, p4) in enumerate(history):
        if index in restarts:
            acc = mix(acc ^ RESTART)
        if states.get(index) == 'save':
            slot = (acc, frames)
        elif states.get(index) == 'load':
            acc, frames = slot
        p1, p2, p3, p4 = clean(p1), clean(p2), clean(p3), clean(p4)
        words = p1 | p2 << 16 | p3 << 32 | p4 << 48
        acc = mix(acc ^ words ^ ((frames << 7) & M))
        if sticks is not None:
            for port in sticks[index]:
                values = [(value * 258) & 0xffff for value in port]
                acc = mix(acc ^ (values[0] | values[1] << 16 | values[2] << 32 | values[3] << 48))
        frames += 1
    return acc ^ frames


# ---- the worker side of the pipes ----

class Game:
    """The fake game started in a session (or alone): its pipes, a reader thread, its exit."""

    def __init__(self, executable: Path, out: Path, session: bool = True, frames: int | None = None, menu_at: int = 0,
                 restart_at: int = 0, chat_at: int = 0, load_at: int = 0, driven: bool = False, sticks: bool = False,
                 save: int | None = None):
        # A session is never a hidden-window test run (the kit ignores the pipes there): session runs set no frame count and
        # end by STOP or a closed pipe; SDL's dummy drivers keep every window and sound device away.
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', SDL_RENDER_VSYNC='0')
        for name in (ENV, 'RETRORECOMP_TIMING_REPORT', 'RETRORECOMP_HOST_TEST_NO_AUDIO', 'RETRORECOMP_HOST_TEST_FILTER',
                     'RETRORECOMP_HOST_TEST_FRAMES'):
            env.pop(name, None)
        if frames:
            env['RETRORECOMP_HOST_TEST_FRAMES'] = str(frames)
        env.pop('SESSION_FAKE_MENU_AT', None)
        env.pop('SESSION_FAKE_RESTART_AT', None)
        env.pop('SESSION_FAKE_CHAT_AT', None)
        env.pop('SESSION_FAKE_LOAD_AT', None)
        env.pop('SESSION_FAKE_DRIVEN', None)
        env.pop('SESSION_FAKE_STICKS', None)
        env.pop('SESSION_FAKE_SAVE', None)
        if save is not None:
            env['SESSION_FAKE_SAVE'] = str(save)
        if sticks:
            env['SESSION_FAKE_STICKS'] = '1'
        if driven:
            env['SESSION_FAKE_DRIVEN'] = '1'
        if load_at:
            env['SESSION_FAKE_LOAD_AT'] = str(load_at)
        if chat_at:
            env['SESSION_FAKE_CHAT_AT'] = str(chat_at)
        if menu_at:
            env['SESSION_FAKE_MENU_AT'] = str(menu_at)
        if restart_at:
            env['SESSION_FAKE_RESTART_AT'] = str(restart_at)
        self.messages: queue.Queue = queue.Queue()
        self.pending: list = []
        self.write = None
        kwargs = dict(cwd=out, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if session:
            game_in, self.write = os.pipe()
            self.read, game_out = os.pipe()
            if os.name == 'nt':
                import msvcrt
                handles = [msvcrt.get_osfhandle(game_in), msvcrt.get_osfhandle(game_out)]
                for handle in handles:
                    os.set_handle_inheritable(handle, True)
                env[ENV] = f'{handles[0]},{handles[1]}'
                info = subprocess.STARTUPINFO()
                info.lpAttributeList = {'handle_list': handles}
                kwargs.update(startupinfo=info, close_fds=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                env[ENV] = f'{game_in},{game_out}'
                kwargs.update(pass_fds=(game_in, game_out))
            self.process = subprocess.Popen([str(executable)], **kwargs)
            os.close(game_in)
            os.close(game_out)
            threading.Thread(target=self._reader, daemon=True).start()
        else:
            if os.name == 'nt':
                kwargs.update(creationflags=subprocess.CREATE_NO_WINDOW)
            self.process = subprocess.Popen([str(executable)], **kwargs)

    def _reader(self):
        buffer = b''
        while True:
            try:
                chunk = os.read(self.read, 4096)
            except OSError:
                chunk = b''
            if not chunk:
                self.messages.put(None)
                return
            buffer += chunk
            while len(buffer) >= 4:
                kind, size = struct.unpack_from('<HH', buffer)
                if len(buffer) < 4 + size:
                    break
                self.messages.put((kind, buffer[4:4 + size]))
                buffer = buffer[4 + size:]

    def send(self, kind: str, payload: bytes = b''):
        os.write(self.write, struct.pack('<HH', CONSTANTS[kind], len(payload)) + payload)

    def receive(self, timeout: float = 5.0):
        """The next message as (name, payload), or None when the game closed its pipe."""
        item = self.messages.get(timeout=timeout)
        if item is None:
            return None
        names = {value: name for name, value in CONSTANTS.items() if name.startswith('RRHK_MSG_')}
        return names.get(item[0], str(item[0])), item[1]

    def expect(self, kind: str, timeout: float = 5.0) -> bytes:
        # The game reports the next frame's LOCAL as soon as a frame is done, so a LOCAL may come before the answer to a
        # command sent meanwhile (DIGEST): it is kept for the next expect('RRHK_MSG_LOCAL').
        for index, (name, payload) in enumerate(self.pending):
            if name == kind:
                del self.pending[index]
                return payload
        while True:
            got = self.receive(timeout)
            if got is not None and got[0] == 'RRHK_MSG_LOCAL' and kind != 'RRHK_MSG_LOCAL':
                self.pending.append(got)
                continue
            if got is None or got[0] != kind:
                raise AssertionError(f'expected {kind}, got {got and got[0]}')
            return got[1]

    def quiet(self, seconds: float) -> bool:
        try:
            return self.messages.get(timeout=seconds) is None
        except queue.Empty:
            return True

    def finish(self, timeout: float = 15.0) -> tuple[int, dict, str]:
        if self.write is not None:
            try:
                os.close(self.write)
            except OSError:
                pass
            self.write = None
        stdout, stderr = self.process.communicate(timeout=timeout)
        match = re.search(r'RESULT (.*)', stdout)
        result = dict(item.split('=') for item in match.group(1).split()) if match else {}
        return self.process.returncode, result, stdout + stderr


def setup(game: Game, *, seat: int = 0, ports: int = 4, depth: int = 0, guest: bool = False, options: str = 'speed=1'):
    hello = game.expect('RRHK_MSG_HELLO', timeout=30)     # a game starting on a busy PC (other builds running) may be slow
    abi, players, caps = struct.unpack_from('<HBB', hello)
    assert abi == ABI, abi
    assert players == 4, players
    assert caps & CONSTANTS['RRHK_CAP_SNAPSHOT'] and caps & CONSTANTS['RRHK_CAP_DIGEST'], caps
    text = options.encode('ascii')
    game.send('RRHK_MSG_SETUP', struct.pack('<BBBBH', seat, ports, depth, CONSTANTS['RRHK_SETUP_GUEST'] if guest else 0,
                                            len(text)) + text)


def run_payload(frame: int, words, silent: bool = False, reset: bool = False, flags: int = 0, sticks=None) -> bytes:
    flags |= (CONSTANTS['RRHK_RUN_SILENT'] if silent else 0) | (CONSTANTS['RRHK_RUN_RESET'] if reset else 0)
    if sticks is not None:
        flags |= CONSTANTS['RRHK_RUN_AXES']
    payload = struct.pack('<IBB', frame, flags, len(words)) + struct.pack(f'<{len(words)}H', *words)
    if sticks is not None:
        payload += struct.pack(f'<{4 * len(words)}b', *(value for port in sticks for value in port))
    return payload


def remote(frame: int, salt: int = 0) -> tuple[int, int, int]:
    return ((frame * 7 + salt) & 0xff, (frame * 13 + salt) & 0xff, (frame * 29 + salt) & 0xff)


def live_frame(game: Game, frame: int, words, history: list, *, save: bool = False, reset: bool = False, flags: int = 0) -> int:
    """Runs `frame` live; returns the system bits of its LOCAL."""
    local = game.expect('RRHK_MSG_LOCAL')
    got_frame, word, system = struct.unpack('<IHH', local)
    assert got_frame == frame, (got_frame, frame)
    assert word == 0, word                    # no key, no pad in a test run
    if save:
        game.send('RRHK_MSG_SAVE', struct.pack('<I', frame))
    game.send('RRHK_MSG_RUN', run_payload(frame, words, reset=reset, flags=flags))
    done = game.expect('RRHK_MSG_DONE')
    assert struct.unpack_from('<I', done)[0] == frame
    history.append(tuple(words))
    return system


def check_digest(game: Game, history: list, restarts=(), states=None) -> None:
    game.send('RRHK_MSG_DIGEST')
    frame, low, high = struct.unpack('<III', game.expect('RRHK_MSG_DIGEST_OF'))
    assert frame == len(history) - 1, (frame, len(history))
    assert (low | high << 32) == digest_of(history, restarts, states), 'digest differs from the fold'


def stop(game: Game) -> None:
    game.send('RRHK_MSG_STOP', struct.pack('<H', CONSTANTS['RRHK_STOP_ENDED']))
    exit_payload = game.expect('RRHK_MSG_EXIT', timeout=10)
    assert struct.unpack('<H', exit_payload)[0] == CONSTANTS['RRHK_EXIT_STOPPED']     # not the player closing the window


def scenarios(executable: Path, out: Path) -> list[str]:
    passed = []

    # 1. Alone: no session, the game reads its own (absent) controls, F8 still reaches the quick-state file.
    game = Game(executable, out, session=False, frames=200)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['frames']) == 200 and int(result['quick']) == 1, result
    assert int(result['digest'], 16) == digest_of([(0, 0, 0, 0)] * 200), result
    passed.append('alone: as before (200 frames, F8 saves, digest of all-zero pads)')

    # 2. Delay: four ports, every word from the worker, players 3 and 4 included; digests every 50 frames; F8 refused.
    game = Game(executable, out)
    setup(game)
    history = []
    for frame in range(300):
        live_frame(game, frame, (0, *remote(frame)), history)
        if frame % 50 == 49:
            check_digest(game, history)
    stop(game)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['frames']) == 300 and int(result['live']) == 300 and int(result['silent']) == 0, result
    assert int(result['quick']) == 0, result               # F8 at frame 10: never the player's own quick-state file
    assert int(result['options']) == 1, result
    assert int(result['digest'], 16) == digest_of(history), result
    passed.append('delay: 300 frames, 4 ports, digests equal, F8 never the player\'s own quick state')

    # 3. Rollback: a snapshot before every frame; every 25 frames, back 6 frames, 6 silent frames with other words, live.
    game = Game(executable, out)
    setup(game, depth=16)
    history = []
    corrections = 0
    for frame in range(300):
        if frame >= 12 and frame % 25 == 0:
            local = game.expect('RRHK_MSG_LOCAL')
            assert struct.unpack('<IHH', local)[0] == frame
            back = frame - 6
            game.send('RRHK_MSG_LOAD', struct.pack('<I', back))
            del history[back:]
            for again in range(back, frame):
                words = (0, *remote(again, salt=0x55))
                game.send('RRHK_MSG_SAVE', struct.pack('<I', again))
                game.send('RRHK_MSG_RUN', run_payload(again, words, silent=True))
                history.append(words)
            game.send('RRHK_MSG_SAVE', struct.pack('<I', frame))
            game.send('RRHK_MSG_RUN', run_payload(frame, (0, *remote(frame))))
            assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == frame
            history.append((0, *remote(frame)))
            corrections += 1
            check_digest(game, history)
            continue
        live_frame(game, frame, (0, *remote(frame)), history, save=True)
    stop(game)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['live']) == 300 and int(result['silent']) == 6 * corrections, (result, corrections)
    assert int(result['effects_off']) == 6 * corrections, result      # side effects off for silent frames only
    assert int(result['digest'], 16) == digest_of(history), result
    passed.append(f'rollback: {corrections} corrections of 6 frames, silent frames without side effects, digests equal')

    # 4. A guest: no side effects at all (its cartridge save is never written).
    game = Game(executable, out)
    setup(game, seat=1, guest=True)
    history = []
    for frame in range(40):
        live_frame(game, frame, (*remote(frame)[:1], 0, 0, 0), history)
    stop(game)
    code, result, _text = game.finish()
    assert code == 0 and int(result['effects_off']) == 40, result
    passed.append('guest: 40 frames, side effects off throughout')

    # 5. Pause for everyone: nothing runs and nothing is reported while paused; the frame runs once resumed.
    game = Game(executable, out)
    setup(game)
    history = []
    for frame in range(31):
        live_frame(game, frame, (0, *remote(frame)), history)
    assert struct.unpack('<IHH', game.expect('RRHK_MSG_LOCAL'))[0] == 31
    name = 'Nadia'.encode()
    game.send('RRHK_MSG_PAUSE', bytes([1, len(name)]) + name)
    assert game.quiet(0.3), 'the game reported something while paused'
    game.send('RRHK_MSG_PAUSE', bytes([0, 0]))
    game.send('RRHK_MSG_RUN', run_payload(31, (0, *remote(31))))
    assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == 31
    history.append((0, *remote(31)))
    check_digest(game, history)
    stop(game)
    code, result, _text = game.finish()
    assert code == 0 and int(result['frames']) == 32, result
    passed.append('pause: nothing runs while paused, frame 31 after resume')

    # 6. An option the machine cannot honour: refused with its key, the session ends before frame 0.
    game = Game(executable, out)
    setup(game, options='bogus=1')
    refused = game.expect('RRHK_MSG_REFUSED')
    code_refused, length = struct.unpack_from('<HB', refused)
    assert code_refused == CONSTANTS['RRHK_REFUSED_OPTION'] and refused[3:3 + length] == b'bogus', refused
    code, result, _text = game.finish()
    assert int(result['frames']) == 0, (code, result)
    passed.append('option refused: key named, nothing run')

    # 7. The pipe lost: the game stops by itself, it does not hang.
    game = Game(executable, out)
    setup(game)
    history = []
    for frame in range(20):
        live_frame(game, frame, (0, *remote(frame)), history)
    started = time.perf_counter()
    code, result, text = game.finish(timeout=10)
    assert code == 0 and int(result['frames']) == 20, (code, result, text)
    assert 'pipe is closed' in text, text
    seconds = time.perf_counter() - started
    assert 3.0 < seconds < 8.0, seconds       # the message stays about 3.5 s, then the game closes by itself
    passed.append(f'pipe lost: message shown, closed by itself in {seconds:.1f} s')

    # 8b. A menu opened by the player asks everyone to pause; closing it while paused is reported, and the game resumes.
    game = Game(executable, out, menu_at=31)
    setup(game)
    history = []
    for frame in range(31):
        live_frame(game, frame, (0, *remote(frame)), history)
    frame, word, system = struct.unpack('<IHH', game.expect('RRHK_MSG_LOCAL'))
    assert (frame, word, system) == (31, 0, CONSTANTS['RRHK_SYS_PAUSE']), (frame, word, system)
    name = b'Arthur'
    game.send('RRHK_MSG_PAUSE', bytes([1, len(name)]) + name)
    frame, word, system = struct.unpack('<IHH', game.expect('RRHK_MSG_LOCAL', timeout=10))
    assert (frame, word, system) == (31, 0, 0), (frame, word, system)        # Help closed: the same frame, no pause asked
    game.send('RRHK_MSG_PAUSE', bytes([0, 0]))
    game.send('RRHK_MSG_RUN', run_payload(31, (0, *remote(31))))
    assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == 31
    history.append((0, *remote(31)))
    check_digest(game, history)
    stop(game)
    code, result, _text = game.finish()
    assert code == 0 and int(result['frames']) == 32, result
    passed.append('menu: pause asked by opening Help, resumed by closing it')

    # 8. A hidden-window test run (the conversion's checks) is never a session, even with the pipes handed to it.
    game = Game(executable, out, frames=50)
    assert game.quiet(1.0), 'a test run spoke to the worker'
    code, result, text = game.finish()
    assert code == 0 and int(result['frames']) == 50 and int(result['quick']) == 1, (code, result, text)
    passed.append('test run: no session, plays alone (50 frames)')
    passed.extend(restart_scenarios(executable, out))
    passed.extend(chat_scenarios(executable, out))
    passed.extend(state_scenarios(executable, out))
    passed.extend(driven_scenarios(executable, out))
    passed.extend(stick_scenarios(executable, out))
    passed.extend(save_scenarios(executable, out))
    return passed


def restart_scenarios(executable: Path, out: Path) -> list[str]:
    passed = []
    restart_bit = CONSTANTS['RRHK_SYS_RESTART']

    # 9. Alone, Shift+F1 restarts at once, as before the session existed: the machine restarts before frame 50, nothing
    # else changes (the session's restart is inert without the pipes).
    game = Game(executable, out, session=False, frames=200, restart_at=50)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['frames']) == 200 and int(result['resets']) == 1, result
    assert int(result['digest'], 16) == digest_of([(0, 0, 0, 0)] * 200, {50}), result
    passed.append('restart alone: Shift+F1 restarts at once before frame 50, as before')

    # 10. The host's Shift+F1 in a session: no restart on this PC alone; the request is in the LOCALs of one frame, and the
    # machine restarts when the worker's RUN says so (here 3 frames later, as the input delay would put it), live; then a
    # correction runs the restart again in a silent frame after a LOAD, and the digests follow the fold.
    game = Game(executable, out, restart_at=20)
    setup(game, depth=16)
    history, restarts, asked = [], [], []
    for frame in range(30):
        reset = frame == 23
        if reset:
            restarts.append(frame)
        if live_frame(game, frame, (0, *remote(frame)), history, save=True, reset=reset) & restart_bit:
            asked.append(frame)
    assert asked == [20], asked                 # pressed during frame 19: in the LOCAL of frame 20 only
    check_digest(game, history, restarts)
    local = game.expect('RRHK_MSG_LOCAL')
    assert struct.unpack('<IHH', local)[0] == 30
    game.send('RRHK_MSG_LOAD', struct.pack('<I', 22))       # back before the restart: frames 22..29 again, silent
    del history[22:]
    for again in range(22, 30):
        words = (0, *remote(again, salt=0x33))
        game.send('RRHK_MSG_SAVE', struct.pack('<I', again))
        game.send('RRHK_MSG_RUN', run_payload(again, words, silent=True, reset=again == 23))
        history.append(words)
    game.send('RRHK_MSG_RUN', run_payload(30, (0, *remote(30))))
    assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == 30
    history.append((0, *remote(30)))
    check_digest(game, history, restarts)
    stop(game)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['resets']) == 2 and int(result['silent']) == 8, result      # live once, silent once
    assert int(result['digest'], 16) == digest_of(history, restarts), result
    passed.append('restart, host: Shift+F1 asked in the LOCAL of frame 20 only, restarted on the RUN of frame 23 (live, then '
                  'again silent after a LOAD), digests equal')

    # 11. A guest's Shift+F1 is refused ("Only the host can restart"): nothing in its LOCALs, no restart; the host's RUN
    # still restarts it.
    game = Game(executable, out, restart_at=10)
    setup(game, seat=1, guest=True)
    history, restarts = [], []
    for frame in range(30):
        reset = frame == 25
        if reset:
            restarts.append(frame)
        assert not live_frame(game, frame, (*remote(frame)[:1], 0, 0, 0), history, reset=reset) & restart_bit, frame
    check_digest(game, history, restarts)
    stop(game)
    code, result, text = game.finish()
    assert code == 0 and int(result['resets']) == 1, result
    passed.append('restart, guest: Shift+F1 refused, nothing asked; the host\'s RUN restarts it at frame 25')

    # 12. A RUN with a flag the kit does not know ends the session (never a guess at its meaning).
    game = Game(executable, out)
    setup(game)
    history = []
    for frame in range(5):
        live_frame(game, frame, (0, 0, 0, 0), history)
    game.expect('RRHK_MSG_LOCAL')
    game.send('RRHK_MSG_RUN', run_payload(5, (0, 0, 0, 0), flags=0x80))
    code, result, text = game.finish(timeout=10)
    assert code == 0 and int(result['frames']) == 5 and 'unknown flags' in text, (code, result, text)
    passed.append('a RUN with an unknown flag: the session ends, nothing run')
    return passed


def state_scenarios(executable: Path, out: Path) -> list[str]:
    """The match's state (session ABI 4): the host's F8 / F9 are requests in its LOCALs; every seat saves or loads its own
    in-memory slot only when the worker's RUN says so (live, or silent after a correction); a guest's are refused; a load with
    nothing saved ends the session; the player's own quick-state file is never touched."""
    passed = []
    save_bit, load_bit = CONSTANTS['RRHK_SYS_STATE_SAVE'], CONSTANTS['RRHK_SYS_STATE_LOAD']
    save_flag, load_flag = CONSTANTS['RRHK_RUN_STATE_SAVE'], CONSTANTS['RRHK_RUN_STATE_LOAD']

    # 16. The host: F8 during frame 9 and F9 during frame 19 are asked in the LOCALs of frames 10 and 20 only; the worker's RUN
    # saves before frame 13 and loads before frame 25 (live), then a correction from frame 24 loads again (silent); digests
    # follow the fold (the load brings back the whole state).
    game = Game(executable, out, load_at=20)
    setup(game, depth=16)
    history, states, asked = [], {13: 'save', 25: 'load'}, {}
    for frame in range(40):
        flags = save_flag if frame == 13 else load_flag if frame == 25 else 0
        system = live_frame(game, frame, (0, *remote(frame)), history, save=True, flags=flags)
        if system & (save_bit | load_bit):
            asked[frame] = system & (save_bit | load_bit)
    assert asked == {10: save_bit, 20: load_bit}, asked
    check_digest(game, history, (), states)
    assert struct.unpack('<IHH', game.expect('RRHK_MSG_LOCAL'))[0] == 40
    game.send('RRHK_MSG_LOAD', struct.pack('<I', 24))
    del history[24:]
    for again in range(24, 40):
        words = (0, *remote(again, salt=0x21))
        game.send('RRHK_MSG_SAVE', struct.pack('<I', again))
        game.send('RRHK_MSG_RUN', run_payload(again, words, silent=True, flags=load_flag if again == 25 else 0))
        history.append(words)
    game.send('RRHK_MSG_RUN', run_payload(40, (0, *remote(40))))
    assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == 40
    history.append((0, *remote(40)))
    check_digest(game, history, (), states)
    stop(game)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['quick']) == 0, result                # the player's own quick-state file is never touched
    assert int(result['digest'], 16) == digest_of(history, (), states), result
    passed.append('match state, host: F8 / F9 asked in the LOCALs of frames 10 and 20 only, saved before frame 13 and loaded '
                  'before frame 25 on the RUN (live, then again silent after a correction), digests equal, own quick state '
                  'untouched')

    # 17. A guest: its F8 and F9 are refused (nothing in its LOCALs); the host's RUN saves and loads it all the same.
    game = Game(executable, out, load_at=20)
    setup(game, seat=1, guest=True)
    history, states = [], {12: 'save', 22: 'load'}
    for frame in range(30):
        flags = save_flag if frame == 12 else load_flag if frame == 22 else 0
        system = live_frame(game, frame, (*remote(frame)[:1], 0, 0, 0), history, flags=flags)
        assert not system & (save_bit | load_bit), (frame, system)
    check_digest(game, history, (), states)
    stop(game)
    code, result, text = game.finish()
    assert code == 0 and int(result['quick']) == 0, result
    assert int(result['digest'], 16) == digest_of(history, (), states), result
    passed.append('match state, guest: F8 / F9 refused, nothing asked; the host\'s RUN saves before frame 12 and loads before 22')

    # 18. A load with nothing saved in this match ends the session (never a guess, never the player's own file).
    game = Game(executable, out)
    setup(game)
    history = []
    for frame in range(5):
        live_frame(game, frame, (0, 0, 0, 0), history)
    game.expect('RRHK_MSG_LOCAL')
    game.send('RRHK_MSG_RUN', run_payload(5, (0, 0, 0, 0), flags=load_flag))
    code, result, text = game.finish(timeout=10)
    assert code == 0 and int(result['frames']) == 5 and int(result['quick']) == 0, (code, result, text)
    assert "match's state could not be saved or loaded" in text, text
    passed.append('match state: a load with nothing saved ends the session, nothing run')
    return passed


def save_scenarios(executable: Path, out: Path) -> list[str]:
    """The host's save travels (session ABI 8): a game with a save says its size in HELLO and gives its bytes (SAVE_OUT); a
    guest is handed the host's (SAVE_IN) before SETUP and plays on them in memory; a host keeps its own."""
    passed = []

    def opened(game: Game) -> tuple[bytes, bytes]:
        hello = game.expect('RRHK_MSG_HELLO', timeout=30)
        name_length = hello[12]
        options_length = struct.unpack_from('<H', hello, 13 + name_length)[0]
        size = struct.unpack_from('<I', hello, 15 + name_length + options_length)[0]
        data = b''
        while len(data) < size:
            chunk = game.expect('RRHK_MSG_SAVE_OUT')
            assert struct.unpack_from('<I', chunk)[0] == len(data)
            data += chunk[4:]
        return hello, data

    # 22. A guest whose own battery differs plays on the host's: its HELLO says 64 bytes and gives its own; SAVE_IN hands it the
    # host's before SETUP; the boot digest and every frame follow the host's battery.
    game = Game(executable, out, save=2)
    hello, own = opened(game)
    assert own == battery(2), own
    host = battery(1)
    for offset in range(0, len(host), 40):           # in two parts, as a larger save would come
        game.send('RRHK_MSG_SAVE_IN', struct.pack('<II', len(host), offset) + host[offset:offset + 40])
    game.pending.insert(0, ('RRHK_MSG_HELLO', hello))
    setup(game, seat=1, guest=True)
    game.send('RRHK_MSG_DIGEST')
    _frame, low, high = struct.unpack('<III', game.expect('RRHK_MSG_DIGEST_OF'))
    assert (low | high << 32) == digest_of([], start=battery_start(host)), 'the boot digest is not the host battery\'s'
    history = []
    for frame in range(20):
        live_frame(game, frame, (*remote(frame)[:1], 0, 0, 0), history)
    check_digest_start = digest_of(history, start=battery_start(host))
    game.send('RRHK_MSG_DIGEST')
    _frame, low, high = struct.unpack('<III', game.expect('RRHK_MSG_DIGEST_OF'))
    assert (low | high << 32) == check_digest_start, 'the frames do not follow the host battery'
    stop(game)
    code, result, text = game.finish()
    assert code == 0 and int(result['digest'], 16) == check_digest_start, (code, result, text)
    passed.append('save, guest: its own battery said in HELLO and SAVE_OUT, the host\'s handed in SAVE_IN before SETUP, boot '
                  'digest and 20 frames on the host\'s battery')

    # 23. A SAVE_IN out of order ends the session (never a guess at the host's bytes).
    game = Game(executable, out, save=2)
    hello, _own = opened(game)
    game.send('RRHK_MSG_SAVE_IN', struct.pack('<II', 64, 8) + bytes(8))
    code, result, text = game.finish(timeout=15)
    assert code == 0 and int(result['frames']) == 0 and 'SAVE_IN' in text, (code, result, text)
    passed.append('save: a SAVE_IN out of order ends the session, nothing run')
    return passed


def stick_scenarios(executable: Path, out: Path) -> list[str]:
    """The sticks travel (session ABI 7): a game with sticks says CAP_AXES, its LOCAL carries this PC's four int8 sticks, and a
    RUN with RRHK_RUN_AXES gives every port's sticks to the machine (rrhk_pad_axes), live and again after a correction."""
    passed = []

    def sticks_of(frame: int, salt: int = 0) -> tuple:
        return tuple(tuple(((frame * (port + 3) + axis * 17 + salt) % 255) - 127 for axis in range(4)) for port in range(4))

    # 21. A machine with sticks: LOCALs of 12 bytes (centred: no pad here), RUNs with the sticks, a correction from frame 30.
    game = Game(executable, out, sticks=True)
    hello = game.expect('RRHK_MSG_HELLO', timeout=30)
    assert struct.unpack_from('<HBB', hello)[2] & CONSTANTS['RRHK_CAP_AXES'], 'no CAP_AXES in the HELLO'
    game.pending.insert(0, ('RRHK_MSG_HELLO', hello))
    setup(game, depth=16)
    history, sticks = [], []
    for frame in range(40):
        local = game.expect('RRHK_MSG_LOCAL')
        assert len(local) == 12, len(local)
        got, word, system, *axes = struct.unpack('<IHH4b', local)
        assert got == frame and axes == [0, 0, 0, 0], (got, axes)
        game.send('RRHK_MSG_SAVE', struct.pack('<I', frame))
        words = (0, *remote(frame))
        game.send('RRHK_MSG_RUN', run_payload(frame, words, sticks=sticks_of(frame)))
        assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == frame
        history.append(words)
        sticks.append(sticks_of(frame))
    game.send('RRHK_MSG_DIGEST')
    last, low, high = struct.unpack('<III', game.expect('RRHK_MSG_DIGEST_OF'))
    assert last == 39 and (low | high << 32) == digest_of(history, sticks=sticks), 'digest differs from the fold (sticks)'
    assert struct.unpack('<IHH4b', game.expect('RRHK_MSG_LOCAL'))[0] == 40
    game.send('RRHK_MSG_LOAD', struct.pack('<I', 30))
    del history[30:], sticks[30:]
    for again in range(30, 40):
        words = (0, *remote(again, salt=0x44))
        game.send('RRHK_MSG_SAVE', struct.pack('<I', again))
        game.send('RRHK_MSG_RUN', run_payload(again, words, silent=True, sticks=sticks_of(again, salt=9)))
        history.append(words)
        sticks.append(sticks_of(again, salt=9))
    game.send('RRHK_MSG_RUN', run_payload(40, (0, *remote(40)), sticks=sticks_of(40)))
    assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == 40
    history.append((0, *remote(40)))
    sticks.append(sticks_of(40))
    game.send('RRHK_MSG_DIGEST')
    last, low, high = struct.unpack('<III', game.expect('RRHK_MSG_DIGEST_OF'))
    assert last == 40 and (low | high << 32) == digest_of(history, sticks=sticks), 'digest differs after the correction (sticks)'
    stop(game)
    code, result, text = game.finish()
    assert code == 0 and int(result['digest'], 16) == digest_of(history, sticks=sticks), (code, result, text)
    passed.append('sticks: CAP_AXES, LOCALs of 12 bytes, every port\'s sticks in the RUN read by the machine, again after a '
                  'correction, digests equal')
    return passed


def driven_scenarios(executable: Path, out: Path) -> list[str]:
    """A driven machine (its guest owns the loop: Master System, Game Boy, MSX) rolls back too (session ABI 5): its guest runs
    the silent frames, which the kit neither shows nor paces; the match's state and the restart (an unwinding and a new shell,
    the session kept) are run again after a correction as on a machine the kit drives."""
    passed = []
    load_flag, save_flag = CONSTANTS['RRHK_RUN_STATE_LOAD'], CONSTANTS['RRHK_RUN_STATE_SAVE']

    # 19. Rollback: a snapshot before every frame; every 25 frames back 6, 6 silent frames run by the guest, then live.
    game = Game(executable, out, driven=True)
    setup(game, depth=16)
    history = []
    for frame in range(200):
        if frame >= 12 and frame % 25 == 0:
            assert struct.unpack('<IHH', game.expect('RRHK_MSG_LOCAL'))[0] == frame
            back = frame - 6
            game.send('RRHK_MSG_LOAD', struct.pack('<I', back))
            del history[back:]
            for again in range(back, frame):
                words = (0, *remote(again, salt=0x55))
                game.send('RRHK_MSG_SAVE', struct.pack('<I', again))
                game.send('RRHK_MSG_RUN', run_payload(again, words, silent=True))
                history.append(words)
            game.send('RRHK_MSG_SAVE', struct.pack('<I', frame))
            game.send('RRHK_MSG_RUN', run_payload(frame, (0, *remote(frame))))
            assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == frame
            history.append((0, *remote(frame)))
            check_digest(game, history)
            continue
        live_frame(game, frame, (0, *remote(frame)), history, save=True)
    check_digest(game, history)
    stop(game)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['silent']) == 7 * 6 and int(result['live']) == 200, result
    assert int(result['digest'], 16) == digest_of(history), result
    passed.append('driven: rollback, 7 corrections of 6 frames run silently by the guest, digests equal')

    # 20. The match's state and the restart, run again by the guest after a correction: save before 13, load before 25,
    # restart before 31 (the shell closes and opens again, the session goes on), then back to 24 and all of it again.
    game = Game(executable, out, driven=True, load_at=20, restart_at=28)
    setup(game, depth=16)
    history, states, restarts = [], {13: 'save', 25: 'load'}, [31]
    for frame in range(40):
        flags = save_flag if frame == 13 else load_flag if frame == 25 else 0
        live_frame(game, frame, (0, *remote(frame)), history, save=True, flags=flags, reset=frame == 31)
    check_digest(game, history, restarts, states)
    assert struct.unpack('<IHH', game.expect('RRHK_MSG_LOCAL'))[0] == 40
    game.send('RRHK_MSG_LOAD', struct.pack('<I', 24))
    del history[24:]
    for again in range(24, 40):
        words = (0, *remote(again, salt=0x21))
        game.send('RRHK_MSG_SAVE', struct.pack('<I', again))
        game.send('RRHK_MSG_RUN', run_payload(again, words, silent=True, reset=again == 31,
                                              flags=load_flag if again == 25 else 0))
        history.append(words)
    game.send('RRHK_MSG_RUN', run_payload(40, (0, *remote(40))))
    assert struct.unpack_from('<I', game.expect('RRHK_MSG_DONE'))[0] == 40
    history.append((0, *remote(40)))
    check_digest(game, history, restarts, states)
    stop(game)
    code, result, text = game.finish()
    assert code == 0, text
    assert int(result['resets']) == 2 and int(result['silent']) == 16, result
    assert int(result['digest'], 16) == digest_of(history, restarts, states), result
    passed.append('driven: the match\'s state and a restart (a new shell, the session kept) run again by the guest after a '
                  'correction, digests equal')
    return passed


def chat_scenarios(executable: Path, out: Path) -> list[str]:
    passed = []

    def frames(game: Game, count: int, history: list, chats: list, systems: list, first: int = 0) -> None:
        """Runs frames live as a guest's worker would, keeping the CHAT_OUT lines that come between them."""
        for frame in range(first, first + count):
            while True:
                name, payload = game.receive()
                if name != 'RRHK_MSG_CHAT_OUT':
                    break
                chats.append(payload)
            assert name == 'RRHK_MSG_LOCAL', name
            got, word, system = struct.unpack('<IHH', payload)
            assert (got, word) == (frame, 0), (got, word, frame)
            systems.append(system)
            words = (*remote(frame)[:1], 0, 0, 0)
            game.send('RRHK_MSG_RUN', run_payload(frame, words))
            while True:
                name, payload = game.receive()
                if name != 'RRHK_MSG_CHAT_OUT':
                    break
                chats.append(payload)
            assert name == 'RRHK_MSG_DONE' and struct.unpack_from('<I', payload)[0] == frame, name
            history.append(words)

    # 13. A guest opens the chat with Y during frame 19 and sends a line twenty iterations later: the frames go on meanwhile
    # (no pause asked), Y's own text is not typed, the line is one CHAT_OUT; lines, phrases and the turn notices from the
    # worker are shown and the session goes on, digests equal.
    game = Game(executable, out, chat_at=20)
    setup(game, seat=1, guest=True)
    history, chats, systems = [], [], []
    frames(game, 60, history, chats, systems)
    assert systems == [0] * 60, systems
    assert chats == [bytes([0, 11]) + b'Hello there'], chats
    name = b'Alessandra Rossi'
    game.send('RRHK_MSG_CHAT_SHOW', bytes([0, len(name)]) + name + bytes([11]) + b'Hello there')
    game.send('RRHK_MSG_CHAT_SHOW', bytes([CONSTANTS['RRHK_PHRASE_AGAIN'], len(name)]) + name + bytes([0]))
    game.send('RRHK_MSG_NOTICE', struct.pack('<HB', CONSTANTS['RRHK_NOTICE_TURN'], len(name)) + name)
    game.send('RRHK_MSG_NOTICE', struct.pack('<HB', CONSTANTS['RRHK_NOTICE_YOUR_TURN'], 0))
    game.send('RRHK_MSG_NOTICE', struct.pack('<HB', CONSTANTS['RRHK_NOTICE_CHAT_SLOW'], 0))
    frames(game, 10, history, chats, systems, first=60)
    check_digest(game, history)
    stop(game)
    code, result, text = game.finish()
    assert code == 0 and int(result['frames']) == 70, (code, result, text)
    passed.append('chat: Y opens the entry of a guest, the frames go on with no pause asked, one CHAT_OUT "Hello there"; '
                  'lines, a phrase and the turn notices shown, the session goes on, digests equal')

    # 14. A CHAT_SHOW that breaks its rules (a phrase that also carries text) ends the session, as any message would.
    game = Game(executable, out)
    setup(game)
    history = []
    for frame in range(5):
        live_frame(game, frame, (0, 0, 0, 0), history)
    game.send('RRHK_MSG_CHAT_SHOW', bytes([CONSTANTS['RRHK_PHRASE_GG'], 1]) + b'A' + bytes([1]) + b'x')
    code, result, text = game.finish(timeout=10)
    assert code == 0 and 'CHAT_SHOW broke the rules' in text, (code, result, text)
    passed.append('chat: a CHAT_SHOW that breaks its rules ends the session')
    return passed


def run_checks(out: Path) -> tuple[int, str, float]:
    started = time.perf_counter()
    try:
        executable = build(out)
        lines = scenarios(executable, out)
    except Exception as error:   # report, do not hide
        import traceback
        return 1, f'FAIL: {error}\n{traceback.format_exc()}', time.perf_counter() - started
    return 0, '\n'.join(lines) + f'\nPASS: {len(lines)} scenarios', time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/hostkit-session-selftest')
    args = parser.parse_args()
    reason = ready()
    if reason:
        print('skipped:', reason)
        return 0
    code, output, seconds = run_checks(args.output.resolve())
    print(f'exit {code}, {seconds:.1f} s\n{output.strip()}')
    return code


if __name__ == '__main__':
    sys.exit(main())
