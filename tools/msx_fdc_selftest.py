"""The MSX2+ disk controller (native/msx_machine/msx_fdc.c), driven through its registers as a disk ROM does (needs a C compiler).

    python -B tools/msx_fdc_selftest.py

Builds `native/msx_machine/msx_fdc_checks.c` with the controller and runs it: a write of one sector ended by the terminal count
changes that sector and no other byte of the image, two sectors up to EOT change two, a byte past EOT without terminal count ends
the write "end of cylinder" and is not written, a write-protected disk and a sector off the track are refused with nothing changed,
a stray byte in the result phase is not data, and a read changes nothing. It says nothing about a disk ROM or a game: those are
the conversions' disk checks (msx_conversion.check_disks) and the authored write disk (tools/msx_write_disk.py).
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
    project = project or ROOT / '.build' / 'msx-fdc-selftest'
    project.mkdir(parents=True, exist_ok=True)
    native = (ROOT / 'native' / 'msx_machine').as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMsxFdc C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/msx_fdc_checks.c" "{native}/msx_fdc.c")
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
