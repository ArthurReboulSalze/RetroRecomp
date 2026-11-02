"""The EEPROM saves of the CPS-1.5 boards (native/cps1_persistence.c) against a stand-in for the board (needs a C compiler).

    python -B tools/cps1_persistence_selftest.py

Builds `native/cps1_persistence_checks.c` with the saves module and runs it beside its own folder: no file, a save written when the
contents change, a second run that loads it, and a damaged file or one written for another set, which is left alone and never written
over. It says nothing about a game; the interactive play that writes the save is not run here.
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
    project = project or ROOT / '.build' / 'cps1-persistence-selftest'
    project.mkdir(parents=True, exist_ok=True)
    native = (ROOT / 'native').as_posix()
    identity = '0123456789abcdef' * 4      # a set identity of the size the saves module checks (64 characters)
    (project / 'retro16_state_config.h').write_text('\n'.join(('#pragma once', f'#define RR16_STATE_ROM "{identity}"', '')), encoding='ascii')
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroCps1Persistence C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/cps1_persistence_checks.c" "{native}/cps1_persistence.c" "{native}/cps1_eeprom.c" "{native}/platform_io.c")
target_include_directories(checks PRIVATE "{native}" "${{CMAKE_CURRENT_SOURCE_DIR}}")
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
