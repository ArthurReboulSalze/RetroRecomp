"""The Amiga Blitter's specialised routines against vAmiga's microprogram, shape by shape (no ROM, no Kickstart, no disk; needs a compiler and a first build of vAmiga's Core).

    python -B tools/amiga_blitter_selftest.py [--blits N]

The routines are the ones the converter generates (`amiga_codegen`, `amiga_vamiga.blitter_shape_header`): vAmiga's own copy microprogram compiled per shape. Each blit runs twice from the same
random state, through the microprogram's table and through the routine, on a machine that is not powered on, with the same random bus from slot to slot; the Blitter's snapshot, the bus record
and the counters must be equal after every slot, Agnus, Paula and chip RAM at the end (`native/amiga_machine/amiga_blit_checks.cpp`). The states are the harness's own: this shows that a routine
equals the microprogram, not the hardware. A routine that writes a wrong word must be seen.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BLITS = 8           # random blits per shape; one in four has BLTCON0 or BLTCON1 changed on the way
PARTS = 8
MINTERMS = (0xf0, 0xcc, 0xaa, 0xca, 0x00, 0xff, 0x0f, 0x5a, 0x66, 0xe2)


def shapes() -> list:
    """Every channel set with every fill, direction and fill carry under a few minterms, then every minterm on the four channels."""
    found = set()
    for use in range(16):
        for fill in (0, 0x08, 0x10, 0x18):
            for desc in (0, 2):
                for carry in (0, 4):
                    for k in range(3):
                        minterm = MINTERMS[(use + fill + desc + carry + k * 3) % len(MINTERMS)]
                        found.add((use << 8 | minterm, fill | desc | carry))
    found |= {(0xf00 | minterm, 0) for minterm in range(256)}
    found |= {(0x9f0, 0), (0xd0c, 0)}
    return sorted(found)


def write_sources(folder: Path, chosen: list, prefix: str) -> None:
    from retrorecomp import amiga_codegen
    steps = folder / 'steps'
    steps.mkdir(parents=True, exist_ok=True)
    for n in range(PARTS):
        (steps / f'blitter{n}.cpp').write_text(amiga_codegen._blitter_source(prefix, chosen[n::PARTS]), encoding='utf-8', newline='\n')
    (steps / 'table.c').write_text('#include <stddef.h>\n#include <stdint.h>\ntypedef void (*RrAmigaCode)(void *);\n' + amiga_codegen._blit_table(prefix, chosen), encoding='utf-8', newline='\n')


def build(work: Path, core: Path, generated: Path) -> Path:
    from retrorecomp.core import run, toolchain
    from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args
    machine = (ROOT / 'native' / 'amiga_machine').as_posix()
    source = work / 'cmake'
    source.mkdir(parents=True, exist_ok=True)
    (source / 'CMakeLists.txt').write_text(f"""cmake_minimum_required(VERSION 3.20)
project(RetroAmigaBlitter LANGUAGES C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_subdirectory("{core.as_posix()}" vacore)
foreach(RR_TARGET VACore rvlib utlib)
    if(TARGET ${{RR_TARGET}})
        set_property(TARGET ${{RR_TARGET}} PROPERTY INTERFACE_COMPILE_OPTIONS "")
    endif()
endforeach()
file(GLOB RR_STEPS "{generated.as_posix()}/steps/*.cpp" "{generated.as_posix()}/steps/*.c")
add_executable(amiga_blit_checks "{machine}/amiga_blit_checks.cpp" ${{RR_STEPS}})
target_link_libraries(amiga_blit_checks PRIVATE VACore)
if(WIN32)
    target_link_libraries(amiga_blit_checks PRIVATE ws2_32)
endif()
""", encoding='utf-8', newline='\n')
    folder = work / 'build'
    cmake, generator = toolchain()
    run([cmake, '-S', source, '-B', folder, '-G', generator, *cmake_target_args(), '-DCMAKE_BUILD_TYPE=Release'], log=work / 'build.log', cwd=work)
    run([cmake, '--build', folder, '--parallel', build_jobs(), '--target', 'amiga_blit_checks'], log=work / 'build.log', timeout=7200, cwd=work)
    return build_executable(folder, 'amiga_blit_checks')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--blits', type=int, default=BLITS)
    parser.add_argument('--workspace', type=Path, default=ROOT, help='where .deps and .build live')
    arguments = parser.parse_args()
    from retrorecomp import amiga_vamiga, paths
    from retrorecomp.systems import get_profile
    paths.ROOT = amiga_vamiga.ROOT = arguments.workspace.resolve()
    work = paths.ROOT / '.build' / 'amiga-blitter'
    core = amiga_vamiga.adapt(amiga_vamiga.source(), work / 'vamiga')
    generated = work / 'generated'
    chosen = shapes()
    write_sources(generated, chosen, get_profile('amiga').observed_code.prefix)
    program = build(work, core, generated)
    result = subprocess.run([str(program), str(arguments.blits)], cwd=work, capture_output=True, text=True)
    print(result.stdout[-4000:], end='')
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    if result.returncode or not rows:
        print(result.stderr[-2000:], file=sys.stderr)
        print('Blitter self-test FAILED.')
        return 1
    print(f"Blitter self-test passed: {rows[0]['shapes']} shapes, {rows[0]['blits']} blits ({rows[0]['changed_on_the_way']} changed on the way), {rows[0]['slots']} slots, 0 differ; "
          f"a wrong routine was seen {rows[0]['wrong_routine_seen']} times out of 16. This shows equality with vAmiga's microprogram, not with the hardware.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
