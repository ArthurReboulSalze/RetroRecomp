"""The Z80 chain's CPU state (native/z80_chain_state.inc) and the quick-state file (native/state_file.h), checked on a toy machine
(needs a C compiler and the pinned engine's CPU header; no ROM, no machine).

    python -B tools/z80_chain_state_selftest.py [--engine PATH]

Builds native/state_file_checks.c with the CPU's type as cpu.prepare_cpu_headers writes it for a game, and runs it in
.build/z80-chain-state-selftest: the CPU's 43 bytes in the Master System's and the MSX's order, a round trip, each bounded field
out of range refused; the file's round trip, a truncated, a longer and a damaged file refused, an out-of-range field under a right
CRC refused, another build's binding and another schema told apart as incompatible, the machine's consistency check refusing a
state (and the same state loading without it), saves that fail leaving the old file whole and no temporary behind. Every refused
load leaves the toy machine unchanged.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args


def run_checks(engine: Path | None = None, project: Path | None = None) -> dict:
    from retrorecomp.cpu import prepare_cpu_headers
    engine = engine or ROOT / '.deps' / 'smsggrecomp'
    project = project or ROOT / '.build' / 'z80-chain-state-selftest'
    project.mkdir(parents=True, exist_ok=True)
    headers = project / 'cpu'
    headers.mkdir(exist_ok=True)
    prepare_cpu_headers(headers, engine)
    native = (ROOT / 'native').as_posix()
    posix = '' if sys.platform == 'win32' else f' "{native}/platform_io.c"'
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroStateFile C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/state_file_checks.c"{posix})
target_include_directories(checks PRIVATE "{headers.as_posix()}" "{native}")
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
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--engine', type=Path, help='the pinned engine folder (default .deps/smsggrecomp)')
    args = parser.parse_args()
    result = run_checks(args.engine)
    for line in result['lines']:
        if line.startswith('FAIL'):
            print(line)
    print(f'{result["passed"]} checks passed, {result["failed"]} failed')
    return 0 if not result['failed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
