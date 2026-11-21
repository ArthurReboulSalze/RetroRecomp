"""The box filter of the sound chips (native/audio_box.h): levels over guest cycles to samples at a stream rate (needs a C compiler).

    python -B tools/audio_box_selftest.py

Builds `native/audio_box_checks.c` and runs it, on levels it makes itself (no ROM, no machine): a constant level for one second,
a square wave of a known period (one half period a sample at 1 MHz and 50 kHz; 16-cycle ticks at 3,579,545 Hz to 44,100 Hz),
mono and stereo, a full buffer with its drop count and take, a restart at any cycle, the int16 clamp, and the same samples
whatever the calls are cut in (one long feed per level, many short random ones, holds to absolute cycles: byte for byte).
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args


def run_checks(project: Path | None = None) -> dict:
    project = project or ROOT / '.build' / 'audio-box-selftest'
    project.mkdir(parents=True, exist_ok=True)
    native = (ROOT / 'native').as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroAudioBox C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/audio_box_checks.c")
target_include_directories(checks PRIVATE "{native}")
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log', timeout=600)
    output = run([build_executable(project / 'build', 'checks')], timeout=60)
    return json.loads(next(line for line in output.splitlines() if line.startswith('{')))


def main() -> int:
    result = run_checks()
    print(f'{result["passed"]} checks passed, {result["failed"]} failed')
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
