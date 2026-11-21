"""The uPD765 floppy controller and the DSK / EXTENDED DSK reader (native/upd765), driven through their registers (needs a C compiler).

    python -B tools/upd765_selftest.py

Builds `native/upd765/upd765_checks.c` with the controller and the reader and runs it, on images the check builds itself: a
standard AMSDOS data disk and an extended one with an unformatted track, a weak sector in three copies, an 8 KiB sector stored
as 6 KiB, a deleted sector, a CRC error, an ID with no data field and odd IDs. It checks the reader's tables and refusals, reads
as AMSDOS makes them on a CPC (no terminal count: "end of cylinder" is the normal end), the IDs in the order they pass the
head, the recorded errors and marks, the weak sector's copies in turn, writes that change exactly their sector, a format in
place, and the terminal count of a machine that wires it. It says nothing about a game: that is the conversions' work.
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
    project = project or ROOT / '.build' / 'upd765-selftest'
    project.mkdir(parents=True, exist_ok=True)
    native = (ROOT / 'native' / 'upd765').as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroUpd765 C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/upd765_checks.c" "{native}/upd765.c" "{native}/dsk_image.c")
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
