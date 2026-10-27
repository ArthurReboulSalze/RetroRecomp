"""Build/render the shared menus with authored text only, without any ROM."""
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from retrorecomp.core import ROOT
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>
from selftest_build import compile_and_run

def main():
    stage=ROOT/'.build/language-checks';stage.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env.update(SDL_VIDEODRIVER='dummy',SDL_RENDER_VSYNC='0')
    # Assertions are test gates even in a release build.
    result=compile_and_run(stage,(ROOT/'native/language_checks.c',ROOT/'native/retro_menu.c'),
        requires_sdl=True,link_libraries=('SDL2::SDL2-static',),
        cmake_extras='''if(WIN32)\n  target_link_libraries(checks PRIVATE gdi32)\nendif()\n''',
        arguments=(stage/'menus.bmp',),env=env,timeout=30,combined_output=False)
    print(result.stdout,end='');print(result.stderr,end='')
    if result.returncode:raise RuntimeError(f'Menu checks failed: {result.returncode}')
    from PIL import Image
    with Image.open(stage/'menus.bmp') as image:image.resize((2048,768)).save(stage/'menus.png')

if __name__=='__main__':main()
