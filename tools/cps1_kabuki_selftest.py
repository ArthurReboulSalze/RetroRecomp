"""The Kabuki fetch of the CPS-1.5 sound CPU on the patched Geolith Z80 core (needs a C compiler, see docs/BUILDING.md).

    python -B tools/cps1_kabuki_selftest.py

Builds `native/cps1_kabuki_checks.c` twice from the converter's own code: against the reference core that
`cps1_build.z80_core(native=False)` gives (instruction fetches read through `rr_cps1_z80_read_op`), and against the native core for
a Kabuki board (`z80_core(native=True, kabuki=True)`) with the Z80 bodies that `cps1_codegen.generate_z80` generates from two
different synthetic images, the opcode image and the data image. Five scenarios (a one-byte operand, a prefix byte, a two-byte
operand after a prefix, the last byte of DD CB d op, an indexed load) each give a result that only the right view produces; on
the native build each one must also run as exactly one native step, with none interpreted.

What it shows: the core and the generator tell instruction fetches from data reads in the way MAME's Z80 does (opcode view for the
opcode and the byte after CB, ED, DD, FD, data view for the rest, the last byte of DD CB d op included). The images are
synthetic; no ROM is read. It says nothing about the QSound board, the DSP or a game.
"""
from __future__ import annotations
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp import cps1_build, cps1_codegen
from retrorecomp.core import run, toolchain
from retrorecomp.neogeo_z80 import adapt_source
from retrorecomp.platforms import build_executable, build_jobs, cmake_target_args

SIZE = 0x8000
# (address, opcode-view bytes, data-view bytes): the views differ on purpose, see native/cps1_kabuki_checks.c
SCENARIOS = ((0x0100, b'\x3e\xff', b'\x00\x42'),
             (0x0110, b'\xed\x44', b'\x00\x00'),
             (0x0120, b'\xdd\x21\xff\xff', b'\x00\x00\x34\x12'),
             (0x0130, b'\xdd\xcb\x77\x77', b'\x00\x00\x02\x46'),
             (0x0140, b'\xdd\x7e\xff', b'\x00\x00\x03'))


def images() -> tuple[bytes, bytes]:
    opcodes, data = bytearray(SIZE), bytearray(SIZE)
    for address, op, plain in SCENARIOS:
        opcodes[address:address + len(op)] = op
        data[address:address + len(plain)] = plain
    return bytes(opcodes), bytes(data)


def build_and_run(project: Path, native: bool) -> dict:
    project.mkdir(parents=True, exist_ok=True)
    opcodes, data = images()
    (project / 'opcodes.bin').write_bytes(opcodes)
    (project / 'data.bin').write_bytes(data)
    cps1_build._engine(project, native=native, kabuki=True)
    geolith, _ = cps1_build.sources()
    if native:
        cps1_codegen.generate_z80(project, adapt_source((geolith / 'src/z80/z80.c').read_text(encoding='utf-8')), data, (), opcodes)
    checks = (ROOT / 'native/cps1_kabuki_checks.c').as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroCps1Kabuki C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{checks}" engine/z80/z80.c)
target_include_directories(checks PRIVATE . engine/z80)
{"target_compile_definitions(checks PRIVATE NATIVE=1)" if native else ""}
if(MSVC)
  target_compile_options(checks PRIVATE /utf-8 /wd4996 /wd4244 /wd4267)
  target_compile_definitions(checks PRIVATE __BYTE_ORDER__=1234 __ORDER_LITTLE_ENDIAN__=1234)
endif()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log', timeout=1800)
    output = run([build_executable(project / 'build', 'checks'), project / 'opcodes.bin', project / 'data.bin'], timeout=120)
    return json.loads(next(line for line in output.splitlines() if line.startswith('{')))


def main() -> int:
    results = {}
    for name, native in (('reference', False), ('native', True)):
        results[name] = build_and_run(ROOT / '.build' / f'cps1-kabuki-selftest-{name}', native)
        print(f'{name}: {results[name]["passed"]} checks passed, {results[name]["failed"]} failed')
    return 0 if all(not result['failed'] for result in results.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
