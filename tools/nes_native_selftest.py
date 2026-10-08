"""Compile authored NES fixtures and compare AOT bodies to the internal CPU.

Checks all 256 opcodes across CPU slots, mapper modes, PPU alignments, flags,
indexed page crossings, bank-boundary operands, wrapping PC, NMI and IRQ.
This verifies the compiler adapter, not independent hardware fidelity.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from smsrecomp.core import run, toolchain
from smsrecomp.nes_codegen import prepare_compiler
from smsrecomp.nes_machine import prepare_machine


def fixture(mapper: int) -> bytes:
    banks = 2 if mapper in (0, 3) else 4
    header = bytearray(b'NES\x1a' + bytes(12))
    header[4:8] = bytes((banks, 1, mapper << 4, 0))
    prg = bytearray([0xEA] * (banks * 16384))
    for bank in range(banks * 4):
        base = bank * 4096
        prg[base:base + 3] = b'\x4c\x00\x80'
        for op in range(256):
            offset = base + 0x100 + op * 4
            # Absolute operands alternate RAM, ROM, mapper registers and MMIO.
            # In particular STA $8000 tests the write which changes the mapping.
            high = (0x01, 0x80, 0x20, 0x40)[(op + bank) & 3]
            if op == 0x8D:
                high = 0x80
            low = 0 if op == 0x8D else 0xFF if op & 1 else 0x01
            prg[offset:offset + 3] = bytes((op, low, high))
        prg[base + 0xFFE:base + 0x1000] = b'\xad\xa9'
    prg[-6:-2] = b'\x00\x80' * 2  # NMI/reset; leave IRQ bytes for wrap tests.
    return bytes(header + prg + bytes(8192))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mappers', nargs='+', type=int, default=[0, 1, 2, 3, 4])
    ap.add_argument('--standards', nargs='+', choices=['ntsc', 'pal'], default=['ntsc', 'pal'])
    args = ap.parse_args()
    cmake, generator = toolchain()
    engine = ROOT / '.deps/nesrecomp'
    compiler = prepare_compiler(engine, cmake, generator, print)
    root = ROOT / '.build/nes-native-selftest'
    root.mkdir(parents=True, exist_ok=True)
    results = []
    for standard, mapper in ((s, m) for s in args.standards for m in args.mappers):
        project = root / f'{standard}-mapper-{mapper}'
        project.mkdir(exist_ok=True)
        machine = prepare_machine(project, engine)
        (project / 'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "' + '0' * 64 + '"\n')
        rom = project / 'fixture.nes'
        rom.write_bytes(fixture(mapper))
        (project / 'game.toml').write_text('[game]\n', encoding='ascii')
        run([compiler, rom, '--game', project / 'game.toml', '--cycle-accurate',
             '--output-prefix', 'game'], cwd=project, log=project / 'codegen.log')
        # Include the umbrella in the harness to expose its private single-step
        # entry; keep every other generated translation unit as a normal source.
        generated = sorted((project / 'generated').glob('game_cyc_*.c'))
        sources = '\n'.join(f'"{p.as_posix()}"' for p in generated)
        (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NesNativeChecks C)
include("{machine.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
add_executable(checks ${{NESRECOMP_CYC_SOURCES}}
    "{ROOT.as_posix()}/native/nes_dense_checks.c" {sources})
target_include_directories(checks PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} generated "{ROOT.as_posix()}/native" "{project.as_posix()}")
target_compile_definitions(checks PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL={int(standard == 'pal')})
if(MSVC)
    target_compile_options(checks PRIVATE /bigobj)
endif()
target_link_libraries(checks PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
''', encoding='utf-8')
        run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'],
            log=project / 'build.log', timeout=600)
        run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'],
            log=project / 'build.log', timeout=1800)
        output = run([project / 'build/Release/checks.exe', rom], timeout=600)
        result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
        result['standard'] = standard
        results.append(result)
        print(json.dumps(result), flush=True)
    (root / 'results.json').write_text(json.dumps(results, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
