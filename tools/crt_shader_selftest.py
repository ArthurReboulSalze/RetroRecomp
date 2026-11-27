"""The CRT looks on the graphics card (HOST_KIT D35, stage 2), through the host kit's real shell (needs a C compiler, the pinned
SDL2 and a screen session; the windows are hidden test-run windows, never shown).

    python -B tools/crt_shader_selftest.py

Builds `tools/crt_shader_probe/probe.c` around the shell and runs it per renderer (Direct3D 11 on Windows, OpenGL everywhere)
with the look off, CRT flat and CRT curved. For a renderer whose pass draws ("[host] CRT look: drawn by the graphics card"), it
checks the picture is there and stays inside the game's rectangle, the curved corner is black, the tone map keeps the
brightness near the plain picture's, and Direct3D 11 and OpenGL agree. A renderer that falls back (no graphics card, a CPU
rasterizer, no screen) is reported, never failed: the stage-1 look then draws, which tools/crt_look_selftest.py checks.

The stage-1 looks (CRT flat, CRT curved, the LCD's real screen and grid, drawn with SDL_Renderer alone) are run on the same
real renderers too, Direct3D 12 included, with the pass turned off for the test run (RETRORECOMP_HOST_TEST_CRT_PASS=0): their
render targets, triangle grid and custom blend under a graphics driver, the same checks, and the renderers agreeing with each
other.

Every CRT check runs in the three styles (RETRORECOMP_HOST_TEST_CRT_STYLE: soft, sharp, arcade), in both stages: the sharp
style keeps more of a fine black and white pattern than the soft one, the arcade style's mask is stronger (read flat). The LCD's real screen
is read on a black frame after a lit one: its slow response leaves the last picture there, the grid none.
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
STAGE1_DRIVERS = ('direct3d11', 'direct3d12', 'opengl') if os.name == 'nt' else ('opengl',)


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


STYLES = ('soft', 'sharp', 'arcade')


def probe_run(exe: Path, box: Path, driver: str, look: int, stage1: bool = False, crt_style: int = 0, lcd_style: int = 0,
              flicker: bool = False) -> tuple[dict | None, str]:
    shutil.rmtree(box / 'datas', ignore_errors=True)
    env = dict(os.environ, SDL_AUDIODRIVER='dummy', SDL_RENDER_DRIVER=driver, RETRORECOMP_HOST_TEST_FRAMES='1000',
               SDL_RENDER_VSYNC='0', **REAL_PADS_OFF)
    env.pop('SDL_VIDEODRIVER', None)
    for name in ('RETRORECOMP_HOST_TEST_FILTER', 'RETRORECOMP_HOST_TEST_CRT_PASS', 'CRT_PROBE_FLICKER'):
        env.pop(name, None)
    env['RETRORECOMP_HOST_TEST_CRT_STYLE'] = str(crt_style)
    env['RETRORECOMP_HOST_TEST_LCD_STYLE'] = str(lcd_style)
    if look:
        env['RETRORECOMP_HOST_TEST_FILTER'] = str(look)
    if stage1:
        env['RETRORECOMP_HOST_TEST_CRT_PASS'] = '0'
    if flicker:
        env['CRT_PROBE_FLICKER'] = '1'
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
    result = {'passed': 0, 'failed': 0, 'drawn': [], 'fallback': {}, 'failures': [], 'blocks': {}, 'metrics': {}}

    def check(ok: bool, what: str) -> None:
        result['passed' if ok else 'failed'] += 1
        if not ok:
            result['failures'].append(what)

    def look_checks(label: str, run_: dict | None, plain: dict, floor: float, curved: bool) -> bool:
        check(bool(run_ and run_.get('read')), f'{label}: read back')
        if not run_ or not run_.get('read'):
            return False
        area = run_['dst'][2] * run_['dst'][3]
        check(run_['lit'] > area * (0.5 if floor > 0.5 else 0.4), f'{label}: the picture is there ({run_["lit"]} of {area})')
        check(run_['outside'] == 0, f'{label}: nothing outside the game rectangle')
        check(run_['mean'] > plain['mean'] * floor, f'{label}: brightness kept ({run_["mean"]:.1f} vs {plain["mean"]:.1f})')
        check(run_['block'] != plain['block'], f'{label}: not the plain picture')
        if curved:
            check(run_['corner'] == 0, f'{label}: the corner is black')
        result['metrics'][label] = {'mean': run_['mean'], 'detail': run_['detail'], 'mask': run_['mask']}
        return True

    def style_checks(label: str, runs: dict) -> None:
        soft, sharp, arcade = (runs.get(name) for name in STYLES)
        if soft and sharp:
            check(sharp['detail'] > soft['detail'] * 1.1, f'{label}: sharp keeps more detail ({sharp["detail"]:.3f} vs {soft["detail"]:.3f})')
        if soft and arcade and 'curved' not in label:   # curved: the vignette and the curve weigh on the edge it is read at
            check(arcade['mask'] > soft['mask'], f'{label}: arcade has the stronger mask ({arcade["mask"]:.3f} vs {soft["mask"]:.3f})')
        blocks = [run_['block'] for run_ in runs.values()]
        check(len(set(blocks)) == len(blocks), f'{label}: each style its own picture')

    for driver in DRIVERS:
        plain, _ = probe_run(exe, box, driver, 0)
        if not plain or not plain.get('read') or plain.get('renderer') != driver:
            result['fallback'][driver] = 'no window or renderer here'
            continue
        first, first_log = probe_run(exe, box, driver, 4)
        if 'drawn by the graphics card' not in first_log:
            reason = next((text for text in first_log.splitlines() if 'CRT look' in text), 'the pass was not tried')
            result['fallback'][driver] = reason
            continue
        result['drawn'].append(driver)
        for look, name in ((4, 'flat'), (5, 'curved')):
            runs = {}
            for index, style in enumerate(STYLES):
                run_, log = (first, first_log) if (look, index) == (4, 0) else probe_run(exe, box, driver, look, crt_style=index)
                check('drawn by the graphics card' in log, f'{driver} {name} {style}: drawn by the graphics card')
                if look_checks(f'{driver} {name} {style}', run_, plain, 0.6, name == 'curved'):
                    runs[style] = run_
                    result['blocks'][f'{driver}-{name}-{style}'] = run_['block']
            style_checks(f'{driver} {name}', runs)
    # stage 1 on the real renderers
    result['stage1'] = []
    stage1_blocks: dict[str, dict[str, int]] = {}
    for driver in STAGE1_DRIVERS:
        plain, _ = probe_run(exe, box, driver, 0, stage1=True)
        if not plain or not plain.get('read') or plain.get('renderer') != driver:
            result['fallback'][f'{driver} (stage 1)'] = 'no window or renderer here'
            continue
        result['stage1'].append(driver)
        for look, name, floor in ((4, 'flat', 0.4), (5, 'curved', 0.3)):
            runs = {}
            for index, style in enumerate(STYLES):
                run_, log = probe_run(exe, box, driver, look, stage1=True, crt_style=index)
                check('drawn by the graphics card' not in log, f'{driver} stage 1 {name} {style}: drawn without the pass')
                if look_checks(f'{driver} stage 1 {name} {style}', run_, plain, floor, name == 'curved'):
                    runs[style] = run_
                    stage1_blocks.setdefault(f'{name} {style}', {})[driver] = run_['block']
            style_checks(f'{driver} stage 1 {name}', runs)
        lcd = {}
        for lcd_style, name in ((0, 'lcd real'), (1, 'lcd grid')):
            run_, log = probe_run(exe, box, driver, 6, stage1=True, lcd_style=lcd_style)
            if look_checks(f'{driver} stage 1 {name}', run_, plain, 0.6, False):
                lcd[name] = run_
                stage1_blocks.setdefault(name, {})[driver] = run_['block']
        if len(lcd) == 2:
            check(lcd['lcd real']['block'] != lcd['lcd grid']['block'], f'{driver} stage 1: the real screen is not the grid')
        # the slow response: a black frame after a lit one keeps some of it on the real screen, none on the grid
        real, _ = probe_run(exe, box, driver, 6, stage1=True, lcd_style=0, flicker=True)
        grid, _ = probe_run(exe, box, driver, 6, stage1=True, lcd_style=1, flicker=True)
        if real and grid and real.get('read') and grid.get('read'):
            check(grid['mean'] < 1.0 and real['mean'] > 2.0,
                  f'{driver} stage 1: the real screen responds slowly (black frame: {real["mean"]:.2f} vs grid {grid["mean"]:.2f})')
            result['metrics'][f'{driver} stage 1 lcd response'] = {'real': real['mean'], 'grid': grid['mean']}
        else:
            check(False, f'{driver} stage 1: the flicker runs read back')
    for name, blocks in stage1_blocks.items():
        if len(blocks) > 1:
            low, high = min(blocks.values()), max(blocks.values())
            check(high - low <= 0.05 * high, f'stage 1 {name}: the renderers agree ({blocks})')
    if {'direct3d11', 'opengl'} <= set(result['drawn']):
        for name in ('flat', 'curved'):
            for style in STYLES:
                a, b = result['blocks'].get(f'direct3d11-{name}-{style}'), result['blocks'].get(f'opengl-{name}-{style}')
                if a and b:
                    check(abs(a - b) <= 0.02 * max(a, b), f'{name} {style}: Direct3D 11 and OpenGL agree ({a} vs {b})')
    return result


def main() -> int:
    result = run_checks()
    print(f"{result['passed']} checks passed, {result['failed']} failed; drawn by the card on {result['drawn'] or 'none'}; "
          f"stage 1 run on {result.get('stage1') or 'none'}; fallback: {result['fallback'] or 'none'}")
    for failure in result['failures']:
        print('FAIL', failure)
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
