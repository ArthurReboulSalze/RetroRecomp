"""ROM-free shared options, audio and SDL controller checks in C and C++."""
from pathlib import Path
import json
import os
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import toolchain, run
from smsrecomp.paths import ROOT
from smsrecomp.platforms import cmake_target_args, build_executable


def main():
    out=ROOT/'.build/game-options-selftest'
    out.mkdir(parents=True,exist_ok=True)
    native=(ROOT/'native').as_posix()
    (out/'check.cpp').write_text((ROOT/'native/game_options_checks.c').read_text(encoding='utf-8'),encoding='utf-8')
    (out/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(GameOptions C CXX)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 CONFIG REQUIRED)
foreach(lang c cpp)
  if(lang STREQUAL "c")
    set(source "{native}/game_options_checks.c")
  else()
    set(source "${{CMAKE_CURRENT_SOURCE_DIR}}/check.cpp")
  endif()
  add_executable(check_${{lang}} "${{source}}" "{native}/retro_menu.c" "{native}/platform_io.c")
  target_include_directories(check_${{lang}} PRIVATE "{native}")
  target_link_libraries(check_${{lang}} PRIVATE SDL2::SDL2-static)
  if(NOT MSVC)
    target_link_libraries(check_${{lang}} PRIVATE m)
  endif()
endforeach()
''',encoding='utf-8')
    cmake,generator=toolchain()
    log=out/'build.log'
    run([cmake,'-S',out,'-B',out/'build','-G',generator,*cmake_target_args(),
        f'-DCMAKE_PREFIX_PATH={(ROOT/".deps/SDL/install").as_posix()}'],log=log)
    run([cmake,'--build',out/'build','--config','Release','--parallel','4'],log=log)
    env=dict(os.environ,SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
    records={}
    for name in ('check_c','check_cpp'):
        result=subprocess.run([str(build_executable(out/'build',name))],env=env,cwd=out,capture_output=True,text=True,timeout=30)
        print(result.stdout+result.stderr)
        records[name]=dict(code=result.returncode,stdout=result.stdout,stderr=result.stderr)
    (out/'results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    assert all(r['code']==0 for r in records.values()),records


if __name__=='__main__':main()
