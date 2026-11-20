"""Compile and exercise Sega host audio numerically, without games or visuals."""
from pathlib import Path
import argparse
import os
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrorecomp.platforms import sdl_install
from retrorecomp.core import run, toolchain
from retrorecomp.paths import ROOT, ASSETS
from retrorecomp.platforms import build_executable, cmake_target_args


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', action='store_true', help='Also exercise the real default audio device with silence.')
    parser.add_argument('--allow-skipped-body', action='store_true',
                        help='Pass on a CPU without AVX2: by default a converter body the CPU cannot run fails the check, so the '
                             'release evidence always covers every body (portable C, SSE2, AVX2).')
    args = parser.parse_args()
    project = ROOT / '.build/sms-audio-selftest'
    project.mkdir(parents=True, exist_ok=True)
    sdl = sdl_install()
    if not any((sdl / name).is_file() for name in
               ('cmake/SDL2Config.cmake', 'lib/cmake/SDL2/SDL2Config.cmake')):
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
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=log)
    executable = build_executable(project / 'build', 'audio_checks')
    for name, extra in [('dummy', [])] + ([('device', ['--device'])] if args.device else []):
        result = subprocess.run([str(executable), *extra], cwd=project, capture_output=True,
            text=True, timeout=180, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        (project / f'{name}.log').write_text(result.stdout + result.stderr, encoding='utf-8')
        print(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(result.returncode)
        if 'skipped' in result.stdout and not args.allow_skipped_body:
            raise SystemExit('A converter body was skipped on this CPU (see the FIR A/B lines): run on a CPU with AVX2, '
                             'or pass --allow-skipped-body.')


if __name__ == '__main__':
    main()
