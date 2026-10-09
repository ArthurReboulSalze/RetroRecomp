"""Check the adapted VDP and simulation clocks against authored expectations."""
from pathlib import Path
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run, toolchain
from smsrecomp.megadrive_runtime import timing_source, timing_vdp


def main():
    project = ROOT / '.build/megadrive-timing-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp/runner'
    (project / 'retro_md_game.h').write_text('/* Authored fixture. */\n')
    shutil.copy2(ROOT / 'native/md_timing.h', project / 'md_timing.h')
    (project / 'vdp.c').write_text(timing_vdp((engine / 'video/genesis_vdp.c').read_text()), encoding='utf-8')
    (project / 'sim.c').write_text(timing_source((engine / 'sim_step.c').read_text(), 'sim'), encoding='utf-8')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdTimingChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
foreach(PAL RANGE 0 1)
  add_executable(checks${{PAL}} "{ROOT.as_posix()}/native/md_timing_checks.c" vdp.c sim.c)
  target_compile_definitions(checks${{PAL}} PRIVATE RR_MD_PAL=${{PAL}})
  target_include_directories(checks${{PAL}} PRIVATE . "{engine.as_posix()}" "{engine.as_posix()}/video"
    "{engine.as_posix()}/external/superzazu" "{engine.as_posix()}/external/clowncommon"
    "{engine.as_posix()}/include")
  target_compile_options(checks${{PAL}} PRIVATE /utf-8)
endforeach()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    results = [json.loads(run([project / f'build/Release/checks{pal}.exe']).strip()) for pal in (0, 1)]
    (project / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results))


if __name__ == '__main__':
    main()
