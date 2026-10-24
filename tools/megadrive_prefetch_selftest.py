"""Independent MC68000 prefetch states and ordered bus transactions.

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
from retrorecomp.platforms import build_executable, cmake_target_args, build_jobs
from retrorecomp.megadrive_codegen import adapt_interpreter, generate_steps


REGS = [*(f'd{i}' for i in range(8)), *(f'a{i}' for i in range(7)), 'usp', 'ssp', 'sr', 'pc']

def state_literal(state, pc_offset=4):
    values = [state[key] if key != 'pc' else (state[key] - pc_offset) & 0xffffff for key in REGS]
    return '{' + ','.join(f'{v}u' for v in values) + '}'

def main():
    project = ROOT / '.build/megadrive-prefetch-selftest'
    project.mkdir(parents=True, exist_ok=True)
    engine = ROOT / '.deps/segagenesisrecomp'
    fixture = json.loads((ROOT / 'tests/fixtures/md-prefetch/cases.json').read_text())
    external_count = len(fixture['tests'])
    authored = json.loads((ROOT / 'tests/fixtures/md-prefetch/authored.json').read_text())
    fixture['tests'] += authored['tests']
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
        for stage in ('initial','final'):
            arrays.append(f'static const uint16_t pf_{stage}_{index}[2] = {{'+','.join(str(x) for x in test[stage]['prefetch'])+'};')
        clocks=0;trace=[]
        for tx in test['transactions']:
            clocks+=tx[1]
            if tx[0]=='n':continue
            trace.append('{'+','.join([str(ord(tx[0])),str(clocks),*[str(x) for x in (tx[2],tx[3],tx[5],tx[6],tx[7])]])+'}')
        arrays.append(f'static const Transaction tx_{index}[]={{'+','.join(trace)+'};')
        cases.append('{'+json.dumps(test['group']+': '+test['name'])+','+
            state_literal(test['initial'])+','+state_literal(test['final'])+','+
            f'initial_{index},{len(test["initial"]["ram"])},final_{index},{len(test["final"]["ram"])},{test["length"]},'+
            f'pf_initial_{index},pf_final_{index},tx_{index},{len(trace)},{test.get("sr_mask",65535)}'+'}')
    (project / 'cartridge.bin').write_bytes(payload)
    rom = SimpleNamespace(data=payload, sha256=hashlib.sha256(payload).hexdigest())
    variants=[{'address':pc,'bytes':raw} for pc,raw in (
        (0xff1000,'7001'),(0xff1000,'7002'),(0xff1000,'33fc700200ff1008'),
        (0xff1008,'7001'),(0xff1008,'7002'))]
    variants.append({'address':0xff1000,'bytes':'4e71'})
    variants.append({'address':0xff1000,'bytes':'33d000ff2000'})
    stats = generate_steps(engine, project, rom, pcs,variants,follow_flow=False)
    assert stats['translated_instructions'] == len(pcs)+7, stats
    (project / 'prefetch_fixture.h').write_text('\n'.join(arrays) +
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
add_executable(checks "{ROOT.as_posix()}/native/md_prefetch_checks.c" reference.c ${{STEPS}}
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(checks PRIVATE . "{prefix}/runner" "{prefix}/runner/include" "{prefix}/recompiler/src")
if(MSVC)
  target_compile_options(checks PRIVATE /utf-8 /wd4996)
endif()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *cmake_target_args()], log=project / 'build.log')
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', build_jobs()], log=project / 'build.log')
    output = run([build_executable(project / 'build','checks')])
    result = json.loads(next(line for line in output.splitlines() if line.startswith('{')))
    result.update(corpus_cases=external_count,authored_cases=len(authored['tests']))
    result.update(source=fixture['source'], revision=fixture['revision'], scope=fixture['scope'],
                  excluded=fixture['excluded'])
    (project / 'results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
