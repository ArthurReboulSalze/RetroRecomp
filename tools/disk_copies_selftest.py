"""The copies of written disks (native/disk_copies.inc), checked on disks the checks make (needs a C compiler; no ROM, no game).

    python -B tools/disk_copies_selftest.py

Builds native/disk_copies_checks.c with platform_io and runs it in .build/disk-copies-selftest: a copy read back only when its
size is the disk's; the timed write after the disks are quiet, the marked disk only, held by a frame that may not write; a failed
write leaving the old copy whole and the disk marked, then written when tried again; the clean end of a match keeping the
previous copy as .bak (none when there was no copy) and refusing to rewrite a copy whose .bak cannot be made; a run without a
copies folder reading and writing nothing.
"""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args


def run_checks(project: Path | None = None) -> dict:
    project = project or ROOT / '.build' / 'disk-copies-selftest'
    project.mkdir(parents=True, exist_ok=True)
    native = (ROOT / 'native').as_posix()
    posix = '' if sys.platform == 'win32' else f' "{native}/platform_io.c"'
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroDiskCopies C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/disk_copies_checks.c"{posix})
target_include_directories(checks PRIVATE "{native}")
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log', timeout=600)
    files = project / 'files'
    shutil.rmtree(files, ignore_errors=True)
    files.mkdir()
    output = run([build_executable(project / 'build', 'checks'), files.as_posix()], timeout=60)
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result['lines'] = [line for line in output.splitlines() if line[:4] in ('ok  ', 'FAIL')]
    return result


def main() -> int:
    result = run_checks()
    for line in result['lines']:
        if line.startswith('FAIL'):
            print(line)
    print(f'{result["passed"]} checks passed, {result["failed"]} failed')
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
