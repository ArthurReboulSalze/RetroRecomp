"""Independent MC68000 vectors replayed through the Neo Geo generator path (gate G10, independent CPU evidence).

    python -B tools/neogeo_vector_selftest.py [fixture ...]        (default: every fixture)

The vectors are the pinned SingleStepTests/m68000 fixtures of the repository (`tests/fixtures`, MIT, generated with MAME, not
recorded from hardware; synthetic instruction data, no cartridge): the same fixtures and the same reading of them as
`tools/cps1_vector_selftest.py`, whose `cases_header`, `summary` and `problems` this tool uses. For each fixture a synthetic
Neo Geo cartridge is built whose program ROM is the flat image holding the vectors' code, and the converter's own generator
(`neogeo_build.prepare_project` and `neogeo_codegen.generate`: the patched Musashi loop, the static sweep of the fixed megabyte,
the vectors' addresses as observed physical entries above it, the translated steps and their guards) produces the native steps.
The harness `native/neogeo_vector_checks.c` then runs every vector twice on a flat 24-bit bus (no board): through the Neo Geo
native steps and through the same Musashi with every instruction interpreted, and compares each path with the vector's final
registers, SR, PC, written bytes and clocks, and the two paths with each other.

What it shows and what it does not: CPU behaviour of the translated steps and of the Musashi reference against an oracle that
neither of them was written from. It does not show the Neo Geo board or bus, hardware fidelity (the oracle is MAME) or gameplay.
The clocks of a Neo Geo game are Musashi's table with prefetch disabled, so the clock counts are reported apart from the state
counts and are not required to equal the vectors' bus-accurate timings.
"""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import struct
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.neogeo_build import prepare_project
from retrorecomp.neogeo_codegen import generate
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args

_spec = importlib.util.spec_from_file_location('cps1_vector_selftest', ROOT / 'tools' / 'cps1_vector_selftest.py')
shared = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(shared)

FIXTURES = shared.FIXTURES
PROGRAM_BYTES = shared.PROGRAM_BYTES


def swapped(data: bytes) -> bytes:
    """The NEO container and the BIOS dump store words byte-swapped; the generator swaps them back."""
    result = bytearray(data)
    result[0::2], result[1::2] = data[1::2], data[0::2]
    return bytes(result)


def entry_offsets(fixture_name: str) -> list[int]:
    """The address of every vector's instruction: the translated steps above the first megabyte are rooted there, as observed
    physical entries (below it the fixed aperture is swept whole)."""
    fixture = json.loads((ROOT / 'tests/fixtures' / fixture_name / 'cases.json').read_text(encoding='utf-8'))
    tests = list(fixture['tests'])
    if fixture_name == 'md-prefetch':
        tests += json.loads((ROOT / 'tests/fixtures/md-prefetch/authored.json').read_text(encoding='utf-8'))['tests']
    return sorted({test['initial']['pc'] - 4 for test in tests if 0 <= test['initial']['pc'] - 4 < PROGRAM_BYTES - 16})


def write_cartridge(project: Path, program: bytes) -> None:
    """A NEO container (program, 128 KiB fixed, 64 KiB sound, 128 bytes of sprites) and a BIOS archive, authored, no game."""
    lengths = (len(program), 131072, 65536, 0, 0, 128)
    header = bytearray(4096)
    header[:4] = b'NEO\x01'
    struct.pack_into('<6I', header, 4, *lengths)
    (project / 'cartridge.neo').write_bytes(bytes(header) + swapped(program) + bytes(sum(lengths[1:])))
    with ZipFile(project / 'bios.zip', 'w') as archive:
        archive.writestr('sp-s2.sp1', swapped(b'\x4a\xfc' * (131072 // 2)))


def replay(fixture_name: str, project: Path | None = None) -> dict:
    project = project or ROOT / '.build' / 'neogeo-vector-selftest' / fixture_name
    project.mkdir(parents=True, exist_ok=True)
    header, program, fixture = shared.cases_header(fixture_name)
    write_cartridge(project, program)
    prepare_project(project, native=True)
    entries = entry_offsets(fixture_name)
    analysis = generate(project, set(), {'p': entries}, [])
    (project / 'vector_fixture.h').write_text(header, encoding='utf-8')
    checks = (ROOT / 'native/neogeo_vector_checks.c').as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroNgVectors LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(GLOB STEPS "${{CMAKE_CURRENT_SOURCE_DIR}}/steps/ng_step_*.c")
add_executable(checks "{checks}" neogeo_native.c ng_arithmetic.c engine/m68k/m68kcpu.c engine/m68k/m68kops.c ${{STEPS}})
target_include_directories(checks PRIVATE . engine)
target_compile_definitions(checks PRIVATE RR_NG_NATIVE=1)
target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996;/wd4244;/wd4267>")
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log')
    output = run([build_executable(project / 'build', 'checks')])
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result.update(fixture=fixture_name, source=fixture['source'], revision=fixture['revision'], scope=fixture['scope'],
                  excluded=fixture['excluded'], translated_instructions=analysis['translated_instructions'],
                  physical_entries=len(entries))
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main(names=None) -> int:
    results = [replay(name) for name in (names or FIXTURES + (shared.GROUPS,))]
    failed = 0
    for result in results:
        print(shared.summary(result))
        for text in shared.machine_problems(result, 'neogeo'):
            failed += 1
            print('PROBLEM', result['fixture'], text)
    print(json.dumps(results))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:] or None))
