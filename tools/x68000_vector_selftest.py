"""Independent MC68000 vectors replayed through the X68000 generator path (gate G10, independent CPU evidence).

    python -B tools/x68000_vector_selftest.py [fixture ...]        (default: every fixture)

The vectors are the pinned SingleStepTests/m68000 fixtures of the repository (`tests/fixtures`, MIT, generated with MAME, not
recorded from hardware; synthetic instruction data, no disk, no firmware): the same fixtures and the same reading of them as
`tools/cps1_vector_selftest.py`, whose `cases_header`, `summary` and `problems` this tool uses. For each fixture the converter's
own X68000 generator (`tools/x68000_native.generate`: the Musashi of the pinned Geolith with the X68000 binding, the instruction
decoder, the translated steps and their live-word guards) is run on observations that put each vector's instruction at its own
address of the machine's RAM window, as a conversion does for code a game loads. The harness `native/x68000_vector_checks.c`
then runs every vector twice on a flat 24-bit bus (no machine): through the X68000 native steps (`rr_x68k_native_run`, inside the
patched Musashi loop) and through the same Musashi with every instruction interpreted, and compares each path with the vector's
final registers, SR, PC, written bytes and clocks, and the two paths with each other.

What it shows and what it does not: CPU behaviour of the translated steps and of the Musashi reference against an oracle that
neither of them was written from. It does not show the X68000 machine, its bus, hardware fidelity (the oracle is MAME) or
gameplay. The clocks of an X68000 game are Musashi's table with prefetch disabled, so the clock counts are reported apart from
the state counts and are not required to equal the vectors' bus-accurate timings.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
from tools import x68000_native

_spec = importlib.util.spec_from_file_location('cps1_vector_selftest', ROOT / 'tools' / 'cps1_vector_selftest.py')
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)

FIXTURES = shared.FIXTURES
PROGRAM_BYTES = shared.PROGRAM_BYTES
OBSERVED_BYTES = 16     # the bytes read at a vector's address: enough for the longest instruction (eight words)


def observations(fixture_name: str, program: bytes) -> list[tuple[int, str]]:
    """(address, words) of every vector's instruction, as the observation layer of a conversion records executed code."""
    fixture = json.loads((ROOT / 'tests/fixtures' / fixture_name / 'cases.json').read_text(encoding='utf-8'))
    tests = list(fixture['tests'])
    if fixture_name == 'md-prefetch':
        tests += json.loads((ROOT / 'tests/fixtures/md-prefetch/authored.json').read_text(encoding='utf-8'))['tests']
    addresses = sorted({test['initial']['pc'] - 4 for test in tests if 0 <= test['initial']['pc'] - 4 < PROGRAM_BYTES - OBSERVED_BYTES})
    return [(address, program[address:address + OBSERVED_BYTES].hex()) for address in addresses]


def replay(fixture_name: str, project: Path | None = None) -> dict:
    project = project or ROOT / '.build' / 'x68000-vector-selftest' / fixture_name
    project.mkdir(parents=True, exist_ok=True)
    header, program, fixture = shared.cases_header(fixture_name)
    samples = observations(fixture_name, program)
    analysis = x68000_native.generate(project, samples, ROOT / '.deps' / 'px68k-reference', machine_base='hissorii')
    (project / 'vector_fixture.h').write_text(header, encoding='utf-8')
    # The live-word guards of the steps read the machine's RAM through `memory.h`; the harness provides the same four names.
    (project / 'harness').mkdir(exist_ok=True)
    (project / 'harness' / 'memory.h').write_text('#pragma once\n#include <stdint.h>\n'
                                                  'extern uint8_t *MEM, *TVRAM, *SCSIIPL, *IPL;\n', encoding='utf-8')
    checks = (ROOT / 'native/x68000_vector_checks.c').as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroX68Vectors C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(GLOB STEPS "${{CMAKE_CURRENT_SOURCE_DIR}}/steps/*.c")
add_executable(checks "{checks}" m68kcpu.c musashi/m68kops.c cpu.c arithmetic.c ${{STEPS}})
target_include_directories(checks BEFORE PRIVATE musashi harness)
target_include_directories(checks PRIVATE . "{(ROOT / 'native').as_posix()}" "{(ROOT / 'native/x68000_native').as_posix()}"
                           "{(ROOT / 'native/x68000_reference').as_posix()}")
target_compile_definitions(checks PRIVATE RR_X68000_BASE74=1)
if(MSVC)
  target_compile_options(checks PRIVATE /utf-8 /wd4996 /wd4244 /wd4267)
endif()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log')
    output = run([build_executable(project / 'build', 'checks')])
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result.update(fixture=fixture_name, source=fixture['source'], revision=fixture['revision'], scope=fixture['scope'],
                  excluded=fixture['excluded'], translated_instructions=analysis['instructions'], observed_addresses=len(samples))
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main(names=None) -> int:
    results = [replay(name) for name in (names or FIXTURES)]
    failed = 0
    for result in results:
        print(shared.summary(result))
        for text in shared.problems(result):
            failed += 1
            print('PROBLEM', result['fixture'], text)
    print(json.dumps(results))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or None))
