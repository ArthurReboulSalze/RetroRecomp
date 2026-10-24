"""ROM-free row-fetch regression for the adapted production VDP."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run,toolchain
from retrorecomp.megadrive_runtime import timing_vdp

def main():
    work=ROOT/'.build/megadrive-raster-selftest';work.mkdir(parents=True,exist_ok=True)
    engine=ROOT/'.deps/segagenesisrecomp/runner'
    (work/'vdp.c').write_text(timing_vdp((engine/'video/genesis_vdp.c').read_text()),encoding='utf-8')
    (work/'retro_md_game.h').write_text('/* Authored raster fixture. */\n')
    (work/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdRasterChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
foreach(PAL RANGE 0 1)
 add_executable(checks${{PAL}} "{ROOT.as_posix()}/native/md_raster_checks.c" vdp.c)
 target_compile_definitions(checks${{PAL}} PRIVATE RR_MD_PAL=${{PAL}})
 target_include_directories(checks${{PAL}} PRIVATE . "{ROOT.as_posix()}/native" "{engine.as_posix()}" "{engine.as_posix()}/video")
 target_compile_options(checks${{PAL}} PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8>")
endforeach()
''',encoding='utf-8')
    cmake,generator=toolchain()
    run([cmake,'-S',work,'-B',work/'build','-G',generator,*cmake_target_args()],log=work/'build.log')
    run([cmake,'--build',work/'build','--config','Release','--parallel','2'],log=work/'build.log')
    results=[dict(standard=standard,**json.loads(run([build_executable(work / 'build', f'checks{pal}')]).strip())) for pal,standard in enumerate(('ntsc','pal'))]
    result=dict(passed=all(r['passed'] for r in results),results=results)
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
