"""The QSound model of the CPS-1.5 boards (native/cps1_qsound.c) on synthetic ROMs (needs a C compiler).

    python -B tools/cps1_qsound_selftest.py

Builds `native/cps1_qsound_checks.c` with the model and runs it: the busy flag after a reset and after a register write, a voice that
makes sound, the quick-state round trip (a loaded copy makes the very same 2,000 samples) and the refusal of a state whose indices are out
of range. The ROMs are synthetic: nothing of the player's is read. It says nothing about the sound of a game: the model is MAME's
qsoundhle.cpp (BSD-3-Clause), and whole games are compared with MAME by tools/cps1_mame_compare.py.
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
    project = project or ROOT / '.build' / 'cps1-qsound-selftest'
    project.mkdir(parents=True, exist_ok=True)
    native = (ROOT / 'native').as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroCps1Qsound C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{native}/cps1_qsound_checks.c" "{native}/cps1_qsound.c")
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
