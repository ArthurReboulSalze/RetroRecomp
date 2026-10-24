"""Exercise VDP interlace patterns and the shared presentation geometry, headless."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run, toolchain


def main():
    project = ROOT / '.build/megadrive-video-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp/runner'
    (project/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdVideoChecks C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{ROOT.as_posix()}/native/md_video_checks.c" "{engine.as_posix()}/video/genesis_vdp.c")
target_include_directories(checks PRIVATE "{ROOT.as_posix()}/native" "{engine.as_posix()}")
target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8>")
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project/'build', '-G', generator, *cmake_target_args()], log=project/'build.log')
    run([cmake, '--build', project/'build', '--config', 'Release', '--parallel', '2'], log=project/'build.log')
    result = json.loads(run([build_executable(project / 'build', 'checks')]).strip())
    (project/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
