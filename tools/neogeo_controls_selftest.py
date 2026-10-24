"""Build a ROM-free check for keyboard and two-player MVS switch wiring."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
from retrorecomp.core import toolchain,run
from retrorecomp.feedback import stage


def main():
    p=ROOT/'.build/neogeo-controls-selftest';p.mkdir(parents=True,exist_ok=True)
    (p/'ng_game.h').write_text('#pragma once\n')
    (p/'retro_gun_game.h').write_text('#pragma once\n#define RR16_GUN 0\n')
    # Assertions remain enabled in the Release executable.
    (p/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NeoGeoControls C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 CONFIG REQUIRED)
add_executable(checks "{(ROOT/'native/neogeo_controls_checks.c').as_posix()}" "{(ROOT/'native/retro_menu.c').as_posix()}")
target_include_directories(checks PRIVATE . "{(ROOT/'native').as_posix()}")
target_compile_definitions(checks PRIVATE RR16_NG=1)
target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/UNDEBUG>")
target_link_libraries(checks PRIVATE SDL2::SDL2-static user32 gdi32)
''',encoding='utf-8')
    stage(p,'ng','0'*64,target='checks')
    cmake,generator=toolchain();sdl=sdl_install()
    run([cmake,'-S',p,'-B',p/'build','-G',generator,*cmake_target_args(),f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'],log=p/'build.log')
    run([cmake,'--build',p/'build','--config','Release','--parallel','4'],log=p/'build.log')
    result=run([build_executable(p / 'build', 'checks')]);(p/'result.json').write_text(result,encoding='utf-8');print(result.strip())
if __name__=='__main__':main()
