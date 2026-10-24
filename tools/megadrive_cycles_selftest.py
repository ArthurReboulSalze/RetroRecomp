"""Authored MC68000 memory timing expectations from Motorola tables 8-5/6/8.

Flat-bus tests isolate native/reference instruction totals and discarded reads.
Console bus handoff is checked separately by megadrive_bus_selftest.py.
"""
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.megadrive_codegen import generate_steps, adapt_interpreter

# Totals are literal manual expectations, not obtained from our cycle table.
CASES = [
    ('TST.W D0', '4a40', 4), ('TST.L D0', '4a80', 4),
    ('TST.W (A0)', '4a50', 8), ('TST.L (A0)', '4a90', 12),
    ('TST.L abs.l', '4ab900e02000', 20),
    ('CLR.W D0', '4240', 4), ('CLR.L D0', '4280', 6),
    ('CLR.W (A0)', '4250', 12), ('CLR.L (A0)', '4290', 20),
    ('CLR.L (A0)+', '4298', 20), ('CLR.L -(A0)', '42a0', 22),
    ('CLR.L abs.l', '42b900e02000', 28),
    ('NEG.W (A0)', '4450', 12), ('NEG.L (A0)', '4490', 20),
    ('NOT.W (A0)', '4650', 12), ('NOT.L (A0)', '4690', 20),
    ('ADDQ.W A0', '5248', 8), ('ADDQ.W (A0)', '5250', 12),
    ('ADDQ.L (A0)', '5290', 20), ('SUBQ.W (A0)', '5350', 12),
    ('ADDI.W (A0)', '06500001', 16), ('ADDI.L (A0)', '069000000001', 28),
    ('CMPI.W (A0)', '0c500001', 12), ('CMPI.L (A0)', '0c9000000001', 20),
    ('ADD.W D0,(A0)', 'd150', 12), ('ADD.L D0,(A0)', 'd190', 20),
    ('SUB.W D0,(A0)', '9150', 12), ('AND.W D0,(A0)', 'c150', 12),
    ('OR.W D0,(A0)', '8150', 12), ('EOR.W D0,(A0)', 'b150', 12),
    ('BTST D0,D0', '0100', 6), ('BTST #1,D0', '08000001', 10),
    ('BTST D0,(A0)', '0110', 8), ('BTST #1,(A0)', '08100001', 12),
    ('BSET D0,(A0)', '01d0', 12), ('BSET #1,(A0)', '08d00001', 16),
    ('BCLR D0,D0', '0180', 10), ('BCLR #1,D0', '08800001', 14),
    ('ASR.W (A0)', 'e0d0', 12), ('LSL.W (A0)', 'e3d0', 12),
    ('SNE (A0)+', '56d8', 12), ('NBCD (A0)', '4810', 12),
    ('CMPM.B (A0)+,(A1)+', 'b308', 12), ('CMPM.W (A0)+,(A1)+', 'b348', 12),
    ('CMPM.L (A0)+,(A1)+', 'b388', 20),
    ('CMPM.B (A7)+,(A1)+', 'b30f', 12), ('CMPM.B (A0)+,(A7)+', 'bf08', 12),
    ('ADDX.B -(A0),-(A1)', 'd308', 18), ('ADDX.W -(A0),-(A1)', 'd348', 18),
    ('ADDX.L -(A0),-(A1)', 'd388', 30), ('SUBX.B -(A0),-(A1)', '9308', 18),
    ('SUBX.W -(A0),-(A1)', '9348', 18), ('SUBX.L -(A0),-(A1)', '9388', 30),
    ('ABCD -(A0),-(A1)', 'c308', 18), ('SBCD -(A0),-(A1)', '8308', 18),
]


def main():
    project = ROOT / '.build/megadrive-cycle-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp'
    payload = bytearray(4096)
    payload[0x100:0x104] = b'SEGA'
    pcs = set()
    rows = []
    for i, (name, raw, clocks) in enumerate(CASES):
        pc = 0x200 + i * 16
        code = bytes.fromhex(raw)
        payload[pc:pc+len(code)] = code
        pcs.add(pc)
        rows.append('{' + json.dumps(name) + f',0x{pc:x},{clocks},' +
                    '{' + ','.join(str(x) for x in code) + f'}},{len(code)}' + '}')
    rom = SimpleNamespace(data=payload, sha256=hashlib.sha256(payload).hexdigest())
    (project / 'cartridge.bin').write_bytes(payload)
    stats = generate_steps(engine, project, rom, pcs, follow_flow=False)
    assert stats['translated_instructions'] == len(CASES)
    (project / 'cycle_fixture.h').write_text(
        'static const Case cases[]={' + ',\n'.join(rows) + '};\n', encoding='utf-8')
    for name in ('md_native_steps.h', 'md_exception_decode.h', 'md_bus_scheduler.h'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    (project / 'retro_md_game.h').write_text('#define RR_MD_STEP_AOT 1\n')
    (project / 'reference.c').write_text(adapt_interpreter(
        (engine / 'runner/m68k_interp.c').read_text(encoding='utf-8')), encoding='utf-8')
    for name in ('md_prefetch.h', 'md_prefetch.inc'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    prefix = engine.as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdCycles C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(GLOB STEPS "steps/*.c")
add_executable(checks "{ROOT.as_posix()}/native/md_cycle_checks.c" reference.c ${{STEPS}}
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(checks PRIVATE . "{prefix}/runner" "{prefix}/runner/include" "{prefix}/recompiler/src")
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project/'build.log')
    run([cmake, '--build', project/'build', '--config', 'Release', '--parallel', '4'], log=project/'build.log')
    result = json.loads(run([project/'build/Release/checks.exe']).strip())
    result.update(source='https://www.nxp.com/docs/en/reference-manual/MC68000UM.pdf',
                  tables=['8-5', '8-6', '8-7', '8-8'], original_board_claimed=False)
    (project/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
