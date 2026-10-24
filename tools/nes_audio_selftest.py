"""Build the real NES host output and check authored PCM timelines, silently."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, cmake_target_args

def main():
    project = ROOT / '.build/nes-audio-selftest'
    project.mkdir(parents=True, exist_ok=True)
    cmake, generator = toolchain()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.21)
project(NesAudioChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 CONFIG REQUIRED)
add_executable(checks "{ROOT.as_posix()}/native/nes_audio_checks.c")
target_link_libraries(checks PRIVATE SDL2::SDL2-static)
''')
    log = project / 'build.log'
    run([cmake, '-S', project, '-B', project/'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={(ROOT/".deps/SDL/install").as_posix()}'], log=log)
    run([cmake, '--build', project/'build', '--config', 'Release', '--parallel', '4'], log=log)
    result = run([build_executable(project/'build', 'checks')], timeout=60)
    (project/'checks.log').write_text(result)
    print(result)

if __name__ == '__main__': main()
