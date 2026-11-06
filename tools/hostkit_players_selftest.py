"""Four players through the host kit's real loop, ROM-free (tools/hostkit_players/checks.c says what is checked).

    python -B tools/hostkit_players_selftest.py [--output DIR]

The kit's shell and its CPS-1 adapter are compiled as an export compiles them, around a stub CPS-1 machine, once as a
four-player board and once as a two-player one, and run with four virtual game controllers under SDL's dummy video and
audio drivers (a hidden window, no sound device). Needs the C toolchain and the pinned static SDL2 of `.deps`; nothing is
written outside DIR (default .build/hostkit-players-selftest). About four seconds of run time per board
(two holds of a little over one second, measured on SDL's clock).
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

BOARDS = {'players4': 4, 'players2': 2}


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


def cmake_text(out: Path) -> str:
    from retrorecomp import hostkit
    native = (ROOT / 'native').as_posix()
    shell = ' '.join(f'"{native}/hostkit/{name}"' for name in hostkit.SHELL)
    lines = ['cmake_minimum_required(VERSION 3.21)', 'project(HostkitPlayers C)', 'set(CMAKE_C_STANDARD 11)',
             'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
             'find_package(SDL2 CONFIG REQUIRED)',
             # The shell knows no machine: one library for both boards.
             f'add_library(kit STATIC {shell} "{native}/platform_io.c" "{native}/retro_menu.c")',
             f'target_include_directories(kit PUBLIC "{out.as_posix()}/include" "{native}")',
             'target_link_libraries(kit PUBLIC SDL2::SDL2-static)',
             'if(NOT MSVC)\n  target_link_libraries(kit PUBLIC m)\nendif()']
    for name, players in BOARDS.items():
        lines += [f'add_executable({name} "{(ROOT / "tools/hostkit_players/checks.c").as_posix()}" '
                  f'"{native}/hostkit/adapters/rrhk_cps1.c")',
                  f'target_compile_definitions({name} PRIVATE RR16_CPS1=1 RR_CPS1_PLAYERS={players})',
                  f'target_link_libraries({name} PRIVATE kit)']
    return '\n'.join(lines) + '\n'


def run_checks(out: Path, timeout: int = 60) -> dict:
    """Build both boards in `out`, run them, return {board: (exit code, output, seconds)}."""
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
    out.mkdir(parents=True, exist_ok=True)
    include = out / 'include'
    include.mkdir(exist_ok=True)
    # What a CPS-1 conversion writes beside its sources; the player count comes from the target.
    (include / 'cps1_game.h').write_text('#pragma once\n#define RR_CPS1_TITLE "Four players"\n#define RR_CPS1_SET "rrtest"\n'
                                         '#define RR_CPS1_ROTATION 0\n#define RR_CPS1_DIP_COUNT 0\n', encoding='utf-8')
    (include / 'retro_gun_game.h').write_text('#pragma once\n#define RR16_GUN 0\n', encoding='utf-8')
    (out / 'CMakeLists.txt').write_text(cmake_text(out), encoding='utf-8')
    cmake, generator = toolchain()
    log = out / 'build.log'
    run([cmake, '-S', out, '-B', out / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}'], log=log)
    run([cmake, '--build', out / 'build', '--config', 'Release', '--parallel', '4'], log=log)
    # Only SDL's virtual controllers: a real pad plugged into the computer would take player 1's slot.
    from tools.hostkit_capabilities_selftest import REAL_PADS_OFF
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', SDL_RENDER_VSYNC='0',
               SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS='1', **REAL_PADS_OFF)
    for name in ('RETRORECOMP_HOST_TEST_FRAMES', 'RETRORECOMP_TIMING_REPORT', 'RETRORECOMP_HOST_TEST_NO_AUDIO'):
        env.pop(name, None)
    results = {}
    for name in BOARDS:
        executable = build_executable(out / 'build', name)
        # The preferences live beside the executable: each run starts from the defaults.
        shutil.rmtree(executable.parent / 'datas', ignore_errors=True)
        started = time.perf_counter()
        result = subprocess.run([str(executable)], cwd=out, env=env, capture_output=True, text=True, timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        results[name] = (result.returncode, result.stdout + result.stderr, time.perf_counter() - started)
        shutil.rmtree(executable.parent / 'datas', ignore_errors=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/hostkit-players-selftest')
    args = parser.parse_args()
    reason = ready()
    if reason:
        print('skipped:', reason)
        return 0
    failed = False
    for name, (code, output, seconds) in run_checks(args.output.resolve()).items():
        print(f'{name}: exit {code}, {seconds:.1f} s\n{output.strip()}')
        failed = failed or code != 0
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
