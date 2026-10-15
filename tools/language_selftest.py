"""Build/render the shared menus with authored text only, without any ROM."""
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import ROOT, dependencies, run
from smsrecomp.platforms import build_executable, cmake_target_args, build_jobs

def main():
    _,sdl,cmake,generator=dependencies()
    stage=ROOT/'.build/language-checks';stage.mkdir(parents=True,exist_ok=True)
    native=(ROOT/'native').as_posix()
    (stage/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(LanguageChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 CONFIG REQUIRED)
add_executable(checks "{native}/language_checks.c" "{native}/retro_menu.c")
target_link_libraries(checks PRIVATE SDL2::SDL2-static)
if(WIN32)
  target_link_libraries(checks PRIVATE gdi32)
endif()
''',encoding='utf-8')
    run([cmake,'-S',stage,'-B',stage/'build','-G',generator,*cmake_target_args(),f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'])
    run([cmake,'--build',stage/'build','--config','Release','--parallel',build_jobs()])
    env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_RENDER_VSYNC='0')
    # Assertions are test gates even in a release build.
    executable=build_executable(stage/'build','checks')
    import subprocess
    result=subprocess.run([str(executable),str(stage/'menus.bmp')],env=env,capture_output=True,text=True,timeout=30)
    print(result.stdout,end='');print(result.stderr,end='')
    if result.returncode:raise RuntimeError(f'Menu checks failed: {result.returncode}')
    from PIL import Image
    with Image.open(stage/'menus.bmp') as image:image.resize((2048,768)).save(stage/'menus.png')

if __name__=='__main__':main()
