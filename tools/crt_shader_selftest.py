"""The CRT looks on the graphics card (HOST_KIT D35, stage 2), through the host kit's real shell (needs a C compiler, the pinned
SDL2 and a screen session; the windows are hidden test-run windows, never shown).

    python -B tools/crt_shader_selftest.py

Builds `tools/crt_shader_probe/probe.c` around the shell and runs it per renderer (Direct3D 11 on Windows, OpenGL everywhere)
with the look off, CRT flat and CRT curved. For a renderer whose pass draws ("[host] CRT look: drawn by the graphics card"), it
checks the picture is there and stays inside the game's rectangle, the curved corner is black, the tone map keeps the
brightness near the plain picture's, and Direct3D 11 and OpenGL agree. A renderer that falls back (no graphics card, a CPU
rasterizer, no screen) is reported, never failed: the stage-1 look then draws, which tools/crt_look_selftest.py checks.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>
from retrorecomp import hostkit
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args, sdl_install
from hostkit_capabilities_selftest import REAL_PADS_OFF

DRIVERS = ('direct3d11', 'opengl') if os.name == 'nt' else ('opengl',)


def build(project: Path) -> Path:
    native = (ROOT / 'native').as_posix()
    shell = ' '.join(f'"{native}/hostkit/{name}"' for name in hostkit.SHELL)
    probe = (ROOT / 'tools/crt_shader_probe/probe.c').as_posix()
    project.mkdir(parents=True, exist_ok=True)
    (project / 'CMakeLists.txt').write_text('\n'.join([
        'cmake_minimum_required(VERSION 3.21)', 'project(CrtShaderProbe C)', 'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'find_package(SDL2 CONFIG REQUIRED)',
        f'add_executable(probe "{probe}" {shell} "{native}/platform_io.c" "{native}/retro_menu.c")',
        f'target_include_directories(probe PRIVATE "{native}")',
        'target_compile_definitions(probe PRIVATE _CRT_SECURE_NO_WARNINGS RR_RECOMP_VERSION="crt-probe")',
        'target_link_libraries(probe PRIVATE SDL2::SDL2-static)']) + '\n', encoding='utf-8')
    cmake, generator = toolchain()
    log = project / 'build.log'
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl_install().as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=log, timeout=900)
    return build_executable(project / 'build', 'probe')


def probe_run(exe: Path, box: Path, driver: str, look: int) -> tuple[dict | None, str]:
    shutil.rmtree(box / 'datas', ignore_errors=True)
    env = dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_RENDER_DRIVER=driver, RETRORECOMP_HOST_TEST_FRAMES='1000',
               SDL_RENDER_VSYNC='0', **REAL_PADS_OFF)
    env.pop('SDL_VIDEODRIVER', None)
    env.pop('RETRORECOMP_HOST_TEST_FILTER', None)
    if look:
        env['RETRORECOMP_HOST_TEST_FILTER'] = str(look)
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    done = subprocess.run([str(exe)], cwd=box, env=env, capture_output=True, text=True, timeout=120, **flags)
    shutil.rmtree(box / 'datas', ignore_errors=True)
    line = next((text for text in done.stdout.splitlines() if text.startswith('{')), None)
    return (json.loads(line) if line else None), done.stderr


def run_checks(project: Path | None = None) -> dict:
    project = project or ROOT / '.build' / 'crt-shader-selftest'
    exe = build(project)
    box = project / 'box'
    box.mkdir(exist_ok=True)
    result = {'passed': 0, 'failed': 0, 'drawn': [], 'fallback': {}, 'failures': [], 'blocks': {}}

    def check(ok: bool, what: str) -> None:
        result['passed' if ok else 'failed'] += 1
        if not ok:
            result['failures'].append(what)

    for driver in DRIVERS:
        plain, _ = probe_run(exe, box, driver, 0)
        if not plain or not plain.get('read') or plain.get('renderer') != driver:
            result['fallback'][driver] = 'no window or renderer here'
            continue
        flat, flat_log = probe_run(exe, box, driver, 4)
        curved, _ = probe_run(exe, box, driver, 5)
        if 'drawn by the graphics card' not in flat_log:
            reason = next((text for text in flat_log.splitlines() if 'CRT look' in text), 'the pass was not tried')
            result['fallback'][driver] = reason
            continue
        result['drawn'].append(driver)
        for name, run_ in (('flat', flat), ('curved', curved)):
            check(bool(run_ and run_.get('read')), f'{driver} {name}: read back')
            if not run_ or not run_.get('read'):
                continue
            area = run_['dst'][2] * run_['dst'][3]
            check(run_['lit'] > area * 0.5, f'{driver} {name}: the picture is there ({run_["lit"]} of {area})')
            check(run_['outside'] == 0, f'{driver} {name}: nothing outside the game rectangle')
            check(run_['mean'] > plain['mean'] * 0.6, f'{driver} {name}: brightness kept ({run_["mean"]:.1f} vs {plain["mean"]:.1f})')
            check(run_['block'] != plain['block'], f'{driver} {name}: not the plain picture')
            result['blocks'][f'{driver}-{name}'] = run_['block']
        if curved and curved.get('read'):
            check(curved['corner'] == 0, f'{driver} curved: the corner is black')
    if {'direct3d11', 'opengl'} <= set(result['drawn']):
        for name in ('flat', 'curved'):
            a, b = result['blocks'].get(f'direct3d11-{name}'), result['blocks'].get(f'opengl-{name}')
            if a and b:
                check(abs(a - b) <= 0.02 * max(a, b), f'{name}: Direct3D 11 and OpenGL agree ({a} vs {b})')
    return result


def main() -> int:
    result = run_checks()
    print(f"{result['passed']} checks passed, {result['failed']} failed; drawn by the card on {result['drawn'] or 'none'}; "
          f"fallback: {result['fallback'] or 'none'}")
    for failure in result['failures']:
        print('FAIL', failure)
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
