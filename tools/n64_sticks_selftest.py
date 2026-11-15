"""The Nintendo 64's gamepad through the host kit's real loop, ROM-free (tools/n64_sticks/checks.c says what is checked).

    python -B tools/n64_sticks_selftest.py [--output DIR]

The kit's shell and the N64 adapter are compiled as an export compiles them, around a stub session that records what the adapter
hands the core, and run with one virtual game controller under SDL's dummy video and audio drivers (a hidden window, no sound
device). Needs the C toolchain and the pinned static SDL2 of `.deps`; nothing is written outside DIR (default
.build/n64-sticks-selftest). A few seconds of run time.
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
        'cmake_minimum_required(VERSION 3.21)', 'project(N64Sticks C)', 'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'find_package(SDL2 CONFIG REQUIRED)',
        f'add_executable(n64sticks "{(ROOT / "tools/n64_sticks/checks.c").as_posix()}" {shell} "{native}/platform_io.c" '
        f'"{native}/retro_menu.c")',
        f'target_include_directories(n64sticks PRIVATE "{native}")',
        'target_link_libraries(n64sticks PRIVATE SDL2::SDL2-static)',
        'if(NOT MSVC)\n  target_link_libraries(n64sticks PRIVATE m)\nendif()']) + '\n'


def run_checks(out: Path, timeout: int = 60) -> tuple[int, str, float]:
    """Build in `out`, run, return (exit code, output, seconds)."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
    out.mkdir(parents=True, exist_ok=True)
    (out / 'CMakeLists.txt').write_text(cmake_text(), encoding='utf-8')
    cmake, generator = toolchain()
    log = out / 'build.log'
    run([cmake, '-S', out, '-B', out / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}'], log=log)
    run([cmake, '--build', out / 'build', '--config', 'Release', '--parallel', '4'], log=log)
    # Only SDL's virtual controller: a real pad plugged into the computer would take player 1's slot.
    from tools.hostkit_capabilities_selftest import REAL_PADS_OFF
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', SDL_RENDER_VSYNC='0',
               SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS='1', **REAL_PADS_OFF)
    for name in ('RETRORECOMP_HOST_TEST_FRAMES', 'RETRORECOMP_TIMING_REPORT', 'RETRORECOMP_HOST_TEST_NO_AUDIO'):
        env.pop(name, None)
    executable = build_executable(out / 'build', 'n64sticks')
    # The preferences live beside the executable: each run starts from the defaults.
    shutil.rmtree(executable.parent / 'datas', ignore_errors=True)
    started = time.perf_counter()
    result = subprocess.run([str(executable)], cwd=out, env=env, capture_output=True, text=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    shutil.rmtree(executable.parent / 'datas', ignore_errors=True)
    return result.returncode, result.stdout + result.stderr, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/n64-sticks-selftest')
    args = parser.parse_args()
    reason = ready()
    if reason:
        print('skipped:', reason)
        return 0
    code, output, seconds = run_checks(args.output.resolve())
    print(f'exit {code}, {seconds:.1f} s\n{output.strip()}')
    return 1 if code != 0 else 0


if __name__ == '__main__':
    sys.exit(main())
