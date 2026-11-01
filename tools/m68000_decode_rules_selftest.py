"""The decoding rules of the original MC68000 (native/md_exception_decode.h), checked without a ROM.

1. native/m68000_decode_rules_checks.c decodes all 65,536 opcode words with the pinned decoder and the rules, against
   an expectation written from the Motorola manual, and a few hand-written byte sequences.
2. The real decoding tools of the four machines then read the same hand-written bytes: the Mega Drive tool (also the
   CPS-1 one), the Neo Geo one and the X68000 one (and its table of instruction lengths). Words the 68000 does not
   know come out as the illegal instruction; the valid neighbours and the $FF branch (refused by the validator, as
   speculative code) behave as before.

    python -B tools/m68000_decode_rules_selftest.py [--output DIR]
"""
from pathlib import Path
import argparse
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.m68000 import mnemonic_names
from retrorecomp.platforms import build_executable, cmake_target_args, build_jobs

ENGINE = ROOT / '.deps/segagenesisrecomp'

# Hand-written code, one slot of 16 bytes each. The expected mnemonic is "ILLEGAL", a name, or None (not emitted).
SLOTS = [
    ('LEA D0,A0',          '41c0',                 'MN_ILLEGAL'),
    ('MOVEC Rn,Rc',        '4e7b0801',             'MN_ILLEGAL'),
    ('BKPT #0',            '4848',                 'MN_ILLEGAL'),
    ('JMP (A0)',           '4ed0',                 'MN_JMP'),
    ('BRA.B $FF',          '60ff00000000',         None),
    ('RTS',                '4e75',                 'MN_RTS'),
    ('JSR A0',             '4e88',                 'MN_ILLEGAL'),
    ('PEA (A0)+',          '4858',                 'MN_ILLEGAL'),
    ('JMP #imm',           '4efc00000200',         'MN_ILLEGAL'),
    ('LEA d16(PC),A0',     '41fa0008',             'MN_LEA'),
]
BASE = 0x200


def slot_bytes(index: int) -> bytes:
    raw = bytes.fromhex(SLOTS[index][1])
    return raw + b'\xff' * (16 - len(raw))


def decoded(path: Path, names) -> dict[int, str]:
    return {item['addr']: names[item['mnemonic']] for item in json.loads(path.read_text(encoding='utf-8'))}


FAILURES: list[str] = []


def expect(results: dict[int, str], machine: str) -> int:
    count = 0
    for index, (label, _, wanted) in enumerate(SLOTS):
        got = results.get(BASE + index * 16)
        if got != wanted:
            FAILURES.append(f'{machine}: {label}: expected {wanted}, got {got}')
        else:
            count += 1
    return count


def harness(work: Path) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    prefix = ENGINE.as_posix()
    (work / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroM68000DecodeRules LANGUAGES C)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{(ROOT / 'native/m68000_decode_rules_checks.c').as_posix()}"
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/m68k_validator.c"
  "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(checks PRIVATE "{(ROOT / 'native').as_posix()}" "{prefix}/recompiler/src")
if(MSVC)
  target_compile_options(checks PRIVATE /utf-8 /wd4996)
endif()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', work, '-B', work / 'build', '-G', generator, *cmake_target_args()], log=work / 'build.log')
    run([cmake, '--build', work / 'build', '--config', 'Release', '--parallel', build_jobs()], log=work / 'build.log')
    return json.loads(run([build_executable(work / 'build', 'checks')]).strip().splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '.build/m68000-decode-rules')
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    names = mnemonic_names(ENGINE)
    try:
        result = {'opcode_table': harness(output / 'opcode-table')}
    except Exception as error:   # the harness stops at its first failing check; the four tools are still read
        result = {'opcode_table': 'failed'}
        FAILURES.append('opcode table: ' + str(error).strip().splitlines()[-1])

    # Mega Drive and CPS-1 tool: a cartridge image with the SEGA header and the hand-written code.
    from retrorecomp.megadrive_codegen import decoder_tool as md_decoder
    image = bytearray(b'\xff' * 0x1000)
    image[0x100:0x104] = b'SEGA'
    for index in range(len(SLOTS)):
        image[BASE + index * 16:BASE + index * 16 + 16] = slot_bytes(index)
    (output / 'md.bin').write_bytes(image)
    (output / 'md-pcs.txt').write_text(''.join(f'{BASE + i * 16:06x}\n' for i in range(len(SLOTS))), encoding='ascii')
    run([md_decoder(ENGINE), output / 'md.bin', output / 'md-pcs.txt', output / 'md.json'])
    result['mega_drive_and_cps1'] = expect(decoded(output / 'md.json', names), 'Mega Drive')

    # Neo Geo tool: a bounded region of bytes, the entries listed.
    from retrorecomp.neogeo_codegen import decoder_tool as ng_decoder
    region = b'\xff' * BASE + b''.join(slot_bytes(i) for i in range(len(SLOTS)))
    region += b'\xff' * (len(region) % 2)
    (output / 'ng.bin').write_bytes(region)
    run([ng_decoder(ENGINE), output / 'ng.bin', '0', output / 'md-pcs.txt', output / 'ng.json'])
    result['neo_geo'] = expect(decoded(output / 'ng.json', names), 'Neo Geo')

    # X68000 tool: one "address hex-bytes" line per slot, and the table of lengths.
    from tools import x68000_native
    x68 = x68000_native.decoder(output, ENGINE)
    (output / 'x68.txt').write_text(''.join(
        f'{BASE + i * 16:x} {slot_bytes(i).hex()}\n' for i in range(len(SLOTS))), encoding='ascii')
    run([x68, output / 'x68.txt', output / 'x68.json'])
    result['x68000'] = expect(decoded(output / 'x68.json', names), 'X68000')
    run([x68, '--lengths', output / 'x68-lengths.bin'])
    lengths = (output / 'x68-lengths.bin').read_bytes()
    assert len(lengths) == 65536
    one_word = [0x41c0, 0x4e7a, 0x4e7b, 0x4848, 0x4e88, 0x4efc, 0x60ff, 0x61ff, 0x66ff, 0x6fff]
    wrong = [f'{op:04x}={lengths[op]}' for op in one_word if lengths[op] != 1]
    if wrong:
        FAILURES.append('X68000 length table: expected one word for ' + ', '.join(wrong))
    if not (lengths[0x6000] == 2 and lengths[0x4ef9] == 3 and lengths[0x4eb9] == 3 and lengths[0x4ed0] == 1):
        FAILURES.append('X68000 length table: a valid neighbour changed')
    result['x68000_lengths_checked'] = len(one_word) + 4
    result['passed'] = not FAILURES
    result['failures'] = FAILURES
    (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    if FAILURES:
        sys.exit(chr(10).join(FAILURES))


if __name__ == '__main__':
    main()
