"""Compile and exercise Sega host audio numerically, without games or visuals."""
from pathlib import Path
import argparse
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from smsrecomp.core import run, toolchain
from smsrecomp.paths import ROOT, ASSETS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', action='store_true', help='Also exercise the real default audio device with silence.')
    args = parser.parse_args()
    project = ROOT / '.build/sms-audio-selftest'
    project.mkdir(parents=True, exist_ok=True)
    sdl = ROOT / '.deps/SDL/install'
    if not (sdl / 'cmake/SDL2Config.cmake').exists():
        raise SystemExit('Build the SDL2 dependency first (see docs/BUILDING.md).')
    cmake, generator = toolchain()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(RetroAudioChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 CONFIG REQUIRED)
add_executable(audio_checks "{(ASSETS / 'native/audio_checks.c').as_posix()}")
target_link_libraries(audio_checks PRIVATE SDL2::SDL2-static)
''', encoding='utf-8')
    log = project / 'build.log'
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64',
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=log)
    executable = project / 'build/Release/audio_checks.exe'
    for name, extra in [('dummy', [])] + ([('device', ['--device'])] if args.device else []):
        result = subprocess.run([str(executable), *extra], cwd=project, capture_output=True,
            text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (project / f'{name}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        print(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
