"""Run authored FIFO expectations against private adapted VDP sources, ROM-free."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import cmake_target_args, build_executable, build_jobs
from retrorecomp import megadrive_fifo
from retrorecomp.megadrive_runtime import timing_vdp


def main():
    work=ROOT/'.build/megadrive-fifo-selftest';work.mkdir(parents=True,exist_ok=True)
    engine=ROOT/'.deps/segagenesisrecomp/runner'
    for variant in ('current','baseline'):
        folder=work/variant; (folder/'video').mkdir(parents=True,exist_ok=True)
        header=(engine/'video/genesis_vdp.h').read_text(encoding='utf-8')
        source=(engine/'video/genesis_vdp.c').read_text(encoding='utf-8')
        if variant=='current':
            header=megadrive_fifo.header(header);source=megadrive_fifo.vdp(timing_vdp(source))
        (folder/'video/genesis_vdp.h').write_text(header,encoding='utf-8')
        (folder/'vdp.c').write_text(source,encoding='utf-8')
    for name in ('md_vdp_fifo.h','md_vdp_fifo.inc','md_timing.h'):
        shutil.copy2(ROOT/'native'/name,work/name)
    (work/'retro_md_game.h').write_text('/* Authored fixture. */\n')
    (work/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdFifoChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
foreach(PAL RANGE 0 1)
 add_executable(checks${{PAL}} "{ROOT.as_posix()}/native/md_fifo_checks.c" current/vdp.c)
 target_compile_definitions(checks${{PAL}} PRIVATE RR_MD_PAL=${{PAL}})
 target_include_directories(checks${{PAL}} PRIVATE current current/video . "{ROOT.as_posix()}/native")
 if(MSVC)
  target_compile_options(checks${{PAL}} PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8>")
 endif()
endforeach()
add_executable(baseline "{ROOT.as_posix()}/native/md_fifo_checks.c" baseline/vdp.c)
target_compile_definitions(baseline PRIVATE RR_FIFO_BASELINE=1)
target_include_directories(baseline PRIVATE baseline baseline/video "{ROOT.as_posix()}/native")
''')
    cmake,generator=toolchain()
    run([cmake,'-S',work,'-B',work/'build','-G',generator,*cmake_target_args()],log=work/'build.log')
    run([cmake,'--build',work/'build','--config','Release','--parallel',build_jobs()],log=work/'build.log')
    baseline=json.loads(run([build_executable(work/'build','baseline')]).strip())
    assert baseline==dict(immediate_write=True,always_empty=True)
    results=[json.loads(run([build_executable(work/'build',f'checks{pal}')]).strip()) for pal in (0,1)]
    result=dict(baseline=baseline,results=results,passed=True)
    (work/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
