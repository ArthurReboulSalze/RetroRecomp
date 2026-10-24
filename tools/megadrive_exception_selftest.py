"""Independent MC68000 exception states from a pinned MAME-generated corpus.

The MIT fixture contains synthetic instruction data only, no cartridge. Tests
use a flat 24-bit bus to isolate CPU behavior from the Mega Drive memory map.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run, toolchain
from retrorecomp.megadrive_codegen import adapt_interpreter, generate_steps


REGS = [*(f'd{i}' for i in range(8)), *(f'a{i}' for i in range(7)), 'usp', 'ssp', 'sr', 'pc']

def state_literal(state, pc_offset=4):
    values = [state[key] if key != 'pc' else (state[key] - pc_offset) & 0xffffff for key in REGS]
    return '{' + ','.join(f'{v}u' for v in values) + '}'

def main():
    project = ROOT / '.build/megadrive-exception-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp'
    fixture = json.loads((ROOT / 'tests/fixtures/md-exceptions/cases.json').read_text())
    payload = bytearray(0x400000)
    payload[0x100:0x104] = b'SEGA'
    pcs, occupied = set(), {}
    arrays, cases = [], []
    for index, test in enumerate(fixture['tests']):
        pc = test['initial']['pc'] - 4
        pcs.add(pc)
        initial = dict(test['initial']['ram'])
        for address in range(pc, min(pc + 16, len(payload))):
            if address in initial:
                byte = initial[address]
                assert occupied.get(address, byte) == byte, 'Conflicting code fixtures'
                occupied[address] = payload[address] = byte
        for stage in ('initial', 'final'):
            pairs = test[stage]['ram']
            arrays.append(f'static const BytePair {stage}_{index}[] = {{' +
                          ','.join(f'{{{a}u,{b}u}}' for a, b in pairs) + '};')
        # STOP performs no new prefetch. MAME's final PC is already the
        # following instruction, with its original two-word queue retained.
        final_offset = 0 if test['group'] == 'STOP' and test['cycles'] == 4 else 4
        cases.append('{' + json.dumps(test['group'] + ': ' + test['name']) + ',' +
                     state_literal(test['initial']) + ',' + state_literal(test['final'], final_offset) + ',' +
                     f'initial_{index},{len(test["initial"]["ram"])},' +
                     f'final_{index},{len(test["final"]["ram"])},{test["cycles"]}' + '}')
    (project / 'cartridge.bin').write_bytes(payload)
    rom = SimpleNamespace(data=payload, sha256=hashlib.sha256(payload).hexdigest())
    stats = generate_steps(engine, project, rom, pcs, follow_flow=False)
    assert stats['translated_instructions'] == len(pcs), stats
    (project / 'exception_fixture.h').write_text('\n'.join(arrays) +
        '\nstatic const CorpusCase corpus_cases[] = {' + ',\n'.join(cases) + '};\n', encoding='utf-8')
    for name in ('md_native_steps.h', 'md_exception_decode.h', 'md_bus_scheduler.h'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    (project / 'retro_md_game.h').write_text('#define RR_MD_STEP_AOT 1\n', encoding='ascii')
    source = (engine / 'runner/m68k_interp.c').read_text(encoding='utf-8')
    source = source.replace('static void cov_mark(uint32_t pc) {',
        'extern void rr16_note_interpreted(void);\nstatic void cov_mark(uint32_t pc) {\n rr16_note_interpreted();', 1)
    (project / 'reference.c').write_text(adapt_interpreter(source), encoding='utf-8')
    for name in ('md_prefetch.h', 'md_prefetch.inc'):
        shutil.copy2(ROOT / 'native' / name, project / name)
    prefix = engine.as_posix()
    (project / 'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdExceptions C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(GLOB STEPS "steps/*.c")
add_executable(checks "{ROOT.as_posix()}/native/md_exception_checks.c" reference.c ${{STEPS}}
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(checks PRIVATE . "{prefix}/runner" "{prefix}/runner/include" "{prefix}/recompiler/src")
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64'], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'], log=project / 'build.log')
    output = run([project / 'build/Release/checks.exe'])
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result.update(source=fixture['source'], revision=fixture['revision'], scope=fixture['scope'],
                  excluded=fixture['excluded'])
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
