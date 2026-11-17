"""The host kit's multiplayer session through its real loop, ROM-free (native/hostkit/hostkit_session.h).

    python -B tools/hostkit_session_selftest.py [--output DIR]

The kit's shell is compiled as an export compiles it, around the fake machine of tools/hostkit_session/fake.c (its state folds
the four ports' words of every frame), and driven through two anonymous pipes by a scripted worker written here, which folds the
same words in Python and compares digests. Scenarios: alone (no session: the game plays as before, F8 still saves); delay
(four ports, players 3 and 4 included); rollback (snapshots, loads, silent frames, then the live frame); a guest (no side
effects); pause for everyone; an option the machine cannot honour; the pipe lost; F8 refused in a session. Runs under SDL's
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


def digest_of(history: list[tuple[int, int, int, int]]) -> int:
    acc, frames = 0x9e3779b97f4a7c15, 0
    for p1, p2, p3, p4 in history:
        p1, p2, p3, p4 = clean(p1), clean(p2), clean(p3), clean(p4)
        words = p1 | p2 << 16 | p3 << 32 | p4 << 48
        acc = mix(acc ^ words ^ ((frames << 7) & M))
        frames += 1
    return acc ^ frames


# ---- the worker side of the pipes ----

class Game:
    """The fake game started in a session (or alone): its pipes, a reader thread, its exit."""

    def __init__(self, executable: Path, out: Path, session: bool = True, frames: int | None = None, menu_at: int = 0):
        # A session is never a hidden-window test run (the kit ignores the pipes there): session runs set no frame count and
        # end by STOP or a closed pipe; SDL's dummy drivers keep every window and sound device away.
        env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', SDL_RENDER_VSYNC='0')
        for name in (ENV, 'RETRORECOMP_TIMING_REPORT', 'RETRORECOMP_HOST_TEST_NO_AUDIO', 'RETRORECOMP_HOST_TEST_FILTER',
                     'RETRORECOMP_HOST_TEST_FRAMES'):
            env.pop(name, None)
        if frames:
            env['RETRORECOMP_HOST_TEST_FRAMES'] = str(frames)
        env.pop('SESSION_FAKE_MENU_AT', None)
        if menu_at:
            env['SESSION_FAKE_MENU_AT'] = str(menu_at)
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
    hello = game.expect('RRHK_MSG_HELLO')
    abi, players, caps = struct.unpack_from('<HBB', hello)
    assert abi == ABI, abi
    assert players == 4, players
    assert caps & CONSTANTS['RRHK_CAP_SNAPSHOT'] and caps & CONSTANTS['RRHK_CAP_DIGEST'], caps
    text = options.encode('ascii')
    game.send('RRHK_MSG_SETUP', struct.pack('<BBBBH', seat, ports, depth, CONSTANTS['RRHK_SETUP_GUEST'] if guest else 0,
                                            len(text)) + text)


def run_payload(frame: int, words, silent: bool = False) -> bytes:
    return struct.pack('<IBB', frame, CONSTANTS['RRHK_RUN_SILENT'] if silent else 0, len(words)) + \
        struct.pack(f'<{len(words)}H', *words)


def remote(frame: int, salt: int = 0) -> tuple[int, int, int]:
    return ((frame * 7 + salt) & 0xff, (frame * 13 + salt) & 0xff, (frame * 29 + salt) & 0xff)


def live_frame(game: Game, frame: int, words, history: list, *, save: bool = False):
    local = game.expect('RRHK_MSG_LOCAL')
    got_frame, word, _system = struct.unpack('<IHH', local)
    assert got_frame == frame, (got_frame, frame)
    assert word == 0, word                    # no key, no pad in a test run
    if save:
        game.send('RRHK_MSG_SAVE', struct.pack('<I', frame))
    game.send('RRHK_MSG_RUN', run_payload(frame, words))
    done = game.expect('RRHK_MSG_DONE')
    assert struct.unpack_from('<I', done)[0] == frame
    history.append(tuple(words))


def check_digest(game: Game, history: list) -> None:
    game.send('RRHK_MSG_DIGEST')
    frame, low, high = struct.unpack('<III', game.expect('RRHK_MSG_DIGEST_OF'))
    assert frame == len(history) - 1, (frame, len(history))
    assert (low | high << 32) == digest_of(history), 'digest differs from the fold'


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
    assert int(result['quick']) == 0, result               # F8 at frame 10 refused
    assert int(result['options']) == 1, result
    assert int(result['digest'], 16) == digest_of(history), result
    passed.append('delay: 300 frames, 4 ports, digests equal, F8 refused')

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
