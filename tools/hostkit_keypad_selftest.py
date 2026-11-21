"""The on-screen keypad of the host kit through its real loop, ROM-free (tools/hostkit_keypad/checks.c says what is checked).

    python -B tools/hostkit_keypad_selftest.py [--output DIR]

The kit's shell is compiled as an export compiles it, around a fake machine of checks.c that includes
native/hostkit/adapters/rrhk_keypad.inc as an adapter does (a ColecoVision-like controller: a stick, two fire buttons, a
twelve-key keypad), and run with two virtual game controllers under SDL's dummy video and audio drivers (a hidden window, no
sound device). Needs the C toolchain and the pinned static SDL2 of `.deps`; nothing is written outside DIR (default
.build/hostkit-keypad-selftest), where the run leaves two captures of the window (keypad-one.bmp, keypad-two.bmp). Under a
second of run time.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# A hang, not a speed: the same bound as the other host kit self-tests, so a full suite under load does not fail on time alone.
HANG_SECONDS = 240


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
        'cmake_minimum_required(VERSION 3.21)', 'project(HostkitKeypad C)', 'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'find_package(SDL2 CONFIG REQUIRED)',
        f'add_executable(keypad "{(ROOT / "tools/hostkit_keypad/checks.c").as_posix()}" {shell} '
        f'"{native}/platform_io.c" "{native}/retro_menu.c")',
        f'target_include_directories(keypad PRIVATE "{native}")',
        'target_compile_definitions(keypad PRIVATE _CRT_SECURE_NO_WARNINGS)',
        'target_link_libraries(keypad PRIVATE SDL2::SDL2-static)',
        'if(NOT MSVC)\n  target_link_libraries(keypad PRIVATE m)\nendif()']) + '\n'


def run_checks(out: Path, timeout: int = HANG_SECONDS) -> tuple[int, str, float]:
    """Build in `out`, run once, return (exit code, output, seconds)."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
    from tools.hostkit_capabilities_selftest import REAL_PADS_OFF
    out.mkdir(parents=True, exist_ok=True)
    (out / 'CMakeLists.txt').write_text(cmake_text(), encoding='utf-8')
    cmake, generator = toolchain()
    log = out / 'build.log'
    run([cmake, '-S', out, '-B', out / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}'], log=log)
    run([cmake, '--build', out / 'build', '--config', 'Release', '--parallel', '4'], log=log)
    # Only SDL's virtual controllers: a real pad plugged into the computer would take player 1's slot.
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', SDL_RENDER_VSYNC='0',
               SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS='1', **REAL_PADS_OFF)
    for name in ('RETRORECOMP_HOST_TEST_FRAMES', 'RETRORECOMP_TIMING_REPORT', 'RETRORECOMP_HOST_TEST_NO_AUDIO',
                 'RETRORECOMP_HOST_TEST_FILTER'):
        env.pop(name, None)
    executable = build_executable(out / 'build', 'keypad')
    # The preferences live beside the executable: each run starts from the defaults.
    shutil.rmtree(executable.parent / 'datas', ignore_errors=True)
    started = time.perf_counter()
    result = subprocess.run([str(executable)], cwd=out, env=env, capture_output=True, text=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    seconds = time.perf_counter() - started
    shutil.rmtree(executable.parent / 'datas', ignore_errors=True)
    return result.returncode, result.stdout + result.stderr, seconds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/hostkit-keypad-selftest')
    args = parser.parse_args()
    reason = ready()
    if reason:
        print('skipped:', reason)
        return 0
    code, output, seconds = run_checks(args.output.resolve())
    print(f'exit {code}, {seconds:.1f} s\n{output.strip()}')
    return 1 if code else 0


if __name__ == '__main__':
    sys.exit(main())
