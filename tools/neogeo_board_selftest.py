"""ROM-free code-view/protection checks using the pinned board handlers."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.neogeo_build import prepare_project
from retrorecomp.core import run,toolchain
from retrorecomp.platforms import build_executable,cmake_target_args,build_jobs


def main():
    project=ROOT/'.build/neogeo-board-selftest';prepare_project(project)
    # An untouched pinned sprite calculator is an independent oracle for the
    # optimized inner loop, including chaining, shrink, wrap and sprite limits.
    original=(ROOT/'.deps/geolith-libretro/src/geo_lspc.c').read_text(encoding='utf-8')
    scalar=original[original.index('static inline void geo_lspc_sprcalc(void) {'):
                    original.index('static inline void geo_lspc_aa(void) {')]
    (project/'sprite_scalar_reference.inc').write_text(
        scalar.replace('geo_lspc_sprcalc','rr_ng_scalar_sprcalc'),encoding='utf-8')
    cmakefile=project/'CMakeLists.txt'
    with cmakefile.open('a',encoding='utf-8') as source:
        source.write(f'''
add_executable(board_checks "{ROOT.as_posix()}/native/neogeo_board_checks.c" neogeo_state_validate.c)
target_link_libraries(board_checks PRIVATE ng_hardware)
add_executable(lspc_checks "{ROOT.as_posix()}/native/neogeo_lspc_checks.c")
target_link_libraries(lspc_checks PRIVATE ng_hardware)
''')
        for name in ('timer','sound','ym'):
            source.write(f'\nadd_executable({name}_checks "{ROOT.as_posix()}/native/neogeo_{name}_checks.c")\n'
                         f'target_link_libraries({name}_checks PRIVATE ng_hardware)\n'
                         f'if(MSVC)\n'
                         f'  target_compile_definitions({name}_checks PRIVATE __BYTE_ORDER__=1234 __ORDER_LITTLE_ENDIAN__=1234)\n'
                         f'endif()\n')
        source.write('''
foreach(check board_checks lspc_checks timer_checks sound_checks ym_checks)
  if(MSVC)
    target_compile_options(${check} PRIVATE /utf-8 /wd4996)
  else()
    target_link_libraries(${check} PRIVATE m)
  endif()
endforeach()
''')
    cmake,generator=toolchain()
    run([cmake,'-S',project,'-B',project/'build','-G',generator,*cmake_target_args()],log=project/'build.log')
    run([cmake,'--build',project/'build','--config','Release','--target','board_checks','lspc_checks',
         'timer_checks','sound_checks','ym_checks','--parallel',build_jobs()],log=project/'build.log')
    result=json.loads(run([build_executable(project/'build','board_checks')]).strip())
    result.update(json.loads(run([build_executable(project/'build','lspc_checks')]).strip()))
    for name in ('timer','sound','ym'):
        result.update(json.loads(run([build_executable(project/'build',name+'_checks')]).strip()))
    (project/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
