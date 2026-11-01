"""The Wisdom Tree mapper of the Game Boy runtime on a cartridge authored for the check (no original cartridge bytes).

The cartridge has eight 32 KiB banks. Its header repeats in every bank, with the switching code (the latch is undefined at
power-on), and each bank has its own routine at 0x1000 (lower window) and 0x5000 (upper window). The program writes to 0x0000
to 0x0007 with a value that would mean another bank on any other mapper, calls both routines of every bank and keeps the eight
results of each in work RAM. The checks: the mapper (native/gb_wisdom_checks.c), the generated program against the pinned
interpreter in lockstep, and the results in work RAM.
"""
from pathlib import Path
import json
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.core import run
from retrorecomp.gameboy import _dependencies, CPU_MATCH
from retrorecomp.gameboy_runtime import adapt_generated_project
from retrorecomp.resources import embed_resources
from retrorecomp.paths import ASSETS

BANKS = 8


def authored_rom() -> bytes:
    """Eight banks of 32 KiB: the first 0x200 bytes (header and program) are the same in every bank, the rest is the bank's own."""
    common = bytearray(0x200)
    common[0x100:0x104] = bytes.fromhex('00 c3 50 01')                     # NOP ; JP 0150
    common[0x134:0x134 + 12] = b'WISDOM TREE\0'                              # the words, with a NUL for the space as on a cartridge
    checksum = 0
    for index in range(0x134, 0x14D):
        checksum = (checksum - common[index] - 1) & 0xFF
    common[0x14D] = checksum                                                # header type, ROM size and RAM size stay 00
    program = bytearray.fromhex('31 fe ff')                                  # LD SP,FFFE
    for n in range(BANKS):
        program += bytes([0x3E, 0x55, 0xEA, n, 0x00])                        # LD A,55 ; LD (000n),A : bank n, whatever the value
        program += bytes([0xCD, 0x00, 0x10, 0xEA, n, 0xC0])                  # CALL 1000 (lower window of the bank) ; LD (C00n),A
        program += bytes([0xCD, 0x00, 0x50, 0xEA, 0x10 + n, 0xC0])           # CALL 5000 (upper window of the bank) ; LD (C01n),A
    program += bytes([0x3E, 0x55, 0xEA, 0x00, 0x00, 0x18, 0xFE])             # back to bank 0 ; JR -2
    common[0x150:0x150 + len(program)] = program
    assert len(program) + 0x150 < 0x200
    rom = bytearray(BANKS * 0x8000)
    for bank in range(BANKS):
        base = bank * 0x8000
        rom[base:base + 0x200] = common
        rom[base + 0x1000:base + 0x1003] = bytes([0x3E, 0x10 + bank, 0xC9])   # LD A,10+bank ; RET
        rom[base + 0x3000] = 0xA0 + bank                                      # markers for the mapper check
        rom[base + 0x5000:base + 0x5003] = bytes([0x3E, 0x20 + bank, 0xC9])   # LD A,20+bank ; RET
        rom[base + 0x7000] = 0xB0 + bank
    return bytes(rom)


def main():
    project = ROOT / '.build/gb-wisdom-selftest'
    project.mkdir(parents=True, exist_ok=True)
    (project / 'fixture.gb').write_bytes(authored_rom())
    engine, compiler, sdl, cmake, generator = _dependencies(print)
    log = project / 'build.log'
    run([compiler, project / 'fixture.gb', '-o', project, '--runtime-dir', engine / 'runtime',
         '--output-prefix', 'game', '--no-comments'], log=log, timeout=600)
    adapt_generated_project(project, 'wisdom-fixture', '0' * 64, 'Authored Wisdom Tree fixture')
    (project / 'game_resources.rc').write_text('1 RCDATA { 0 }\n', encoding='utf-8')
    embed_resources(project, {})
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as out:
        out.write(f'''\nadd_executable(retro_gb_wisdom_checks "{(ASSETS / 'native/gb_wisdom_checks.c').as_posix()}")
target_link_libraries(retro_gb_wisdom_checks PRIVATE gbrt)
''')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args(),
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=log)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'retro_gb_wisdom_checks', 'game',
         '--parallel', '4'], log=log, timeout=600)
    output = run([build_executable(project / 'build', 'retro_gb_wisdom_checks'), project / 'fixture.gb',
                  project / 'mapper-state.bin'], timeout=180)
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    executable = build_executable(project / 'build', 'game')
    cpu = run([executable, '--differential', '--differential-frames', '3'], timeout=180)
    assert CPU_MATCH.search(cpu), cpu
    run([executable, '--headless', '--limit-frames', '3', '--dump-state', project / 'state.json'], timeout=180)
    state = json.loads((project / 'state.json').read_text(encoding='utf-8'))
    wram = state['wram_bank_0_c000_cfff']
    lower = [wram[n] for n in range(BANKS)]
    upper = [wram[0x10 + n] for n in range(BANKS)]
    assert lower == [0x10 + n for n in range(BANKS)], lower
    assert upper == [0x20 + n for n in range(BANKS)], upper
    result['program_results'] = {'lower_window': lower, 'upper_window': upper, 'cpu_comparison': CPU_MATCH.search(cpu).group(0)}
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
