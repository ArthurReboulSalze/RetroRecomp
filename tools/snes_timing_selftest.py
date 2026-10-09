"""Compile PAL/NTSC fractional audio-clock fixtures without commercial ROMs."""
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp.snes_timing import apu_clock


def main():
    project = ROOT / '.build/snes-timing-selftest'
    project.mkdir(parents=True, exist_ok=True)
    (project / 'retro_snes_game.h').write_text('/* Authored fixture. */\n', encoding='ascii')
    shutil.copy2(ROOT / 'native/snes_timing.h', project / 'snes_timing.h')
    (project / 'apu_frame_clock.h').write_text(apu_clock(
        (ROOT / '.deps/snesrecomp/runner/src/apu_frame_clock.h').read_text(encoding='utf-8')),
        encoding='utf-8')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroSnesTimingChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
foreach(PAL RANGE 0 1)
  add_executable(checks${{PAL}} "{ROOT.as_posix()}/native/snes_timing_checks.c")
  target_compile_definitions(checks${{PAL}} PRIVATE RR_SN_PAL=${{PAL}})
  target_include_directories(checks${{PAL}} PRIVATE .)
  target_compile_options(checks${{PAL}} PRIVATE /utf-8)
endforeach()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    results = [json.loads(run([project / f'build/Release/checks{pal}.exe']).strip()) for pal in (0, 1)]
    (project / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
