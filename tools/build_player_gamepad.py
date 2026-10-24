"""Build the converter's small SDL2 controller bridge, never at app runtime."""
from pathlib import Path
import os
import shutil
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrorecomp.core import SDL_REV, toolchain, run
from retrorecomp.paths import ROOT
from retrorecomp.platforms import cmake_target_args


def build():
    cmake, generator = toolchain()
    sdl = ROOT / '.deps/SDL'
    # Game executables use SDL's existing static archive. ELF shared libraries
    # require PIC objects; build a separate controller-only archive so their
    # configuration and performance are not changed by the converter UI.
    sdk = sdl if os.name == 'nt' else ROOT/'.deps/player-sdl'
    prefix = sdk/'install'
    out = ROOT / '.build/player-gamepad'
    out.mkdir(parents=True, exist_ok=True)
    log = out / 'build.log'
    if not any((prefix / p).is_file() for p in ('cmake/SDL2Config.cmake', 'lib/cmake/SDL2/SDL2Config.cmake')):
        if not sdl.exists():
            run(['git','clone','https://github.com/libsdl-org/SDL.git',sdl], log=log)
            run(['git','-C',sdl,'checkout','--detach',SDL_REV], log=log)
        if run(['git','-C',sdl,'rev-parse','HEAD']).strip() != SDL_REV:
            raise RuntimeError('Unexpected SDL2 source revision.')
        options = [] if os.name == 'nt' else ['-DCMAKE_POSITION_INDEPENDENT_CODE=ON',
            '-DSDL_AUDIO=OFF','-DSDL_VIDEO=OFF','-DSDL_RENDER=OFF','-DSDL_HAPTIC=OFF','-DSDL_SENSOR=OFF']
        run([cmake,'-S',sdl,'-B',sdk/'build','-G',generator,*cmake_target_args(),*options,
            '-DSDL_SHARED=OFF','-DSDL_STATIC=ON','-DSDL_TEST=OFF','-DSDL_TESTS=OFF',
            '-DSDL_FORCE_STATIC_VCRT=ON',f'-DCMAKE_INSTALL_PREFIX={prefix.as_posix()}'],log=log)
        run([cmake,'--build',sdk/'build','--config','Release','--parallel','4'],log=log)
        run([cmake,'--install',sdk/'build','--config','Release'],log=log)
    config = next((prefix/p).parent for p in ('cmake/SDL2Config.cmake','lib/cmake/SDL2/SDL2Config.cmake')
        if (prefix/p).is_file())
    run([cmake,'-S',ROOT/'tools/player_gamepad','-B',out/'build','-G',generator,
        *cmake_target_args(),f'-DCMAKE_PREFIX_PATH={prefix.as_posix()}',f'-DSDL2_DIR={config.as_posix()}'],log=log)
    run([cmake,'--build',out/'build','--config','Release','--parallel','4'],log=log)
    name = 'retro_gamepad.dll' if os.name == 'nt' else 'libretro_gamepad.so'
    source = out/'build'/('Release' if os.name == 'nt' else '')/name
    target = out/'runtime'/name
    target.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as f: pending = Path(f.name)
    try:
        shutil.copy2(source,pending)
        os.replace(pending,target)
    finally: pending.unlink(missing_ok=True)
    return target


if __name__ == '__main__': print(build())
