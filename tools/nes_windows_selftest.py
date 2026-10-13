"""Authored NES lower-ROM and protected cartridge-RAM instruction checks."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from smsrecomp.core import run,toolchain
from smsrecomp.nes_codegen import prepare_compiler
from smsrecomp.nes_machine import prepare_machine
from smsrecomp.nes_ram import write_guards
from smsrecomp.nes import read_nes_rom
from tools.nes_native_selftest import fixture

BOARDS=[(40,0,0),(69,0,8),(21,1,7),(21,2,5),(22,0,7),(22,0,0),
        (23,1,7),(23,2,5),(23,3,7),(23,3,0),(25,1,7),(25,2,5),(25,3,7),
        (80,0,1),(207,0,1),(82,0,7),(552,0,7)]
PCS=[0x0300,0x6000,0x67FE,0x6800,0x6FFE,0x7000,0x73FE,0x73FF,
     0x7F00,0x7F7E,0x7F80,0x7FFE]

def authored(mapper,sub,ram):
    data=bytearray(fixture(69));data[6]=(mapper&15)<<4;data[7]=(mapper&0xF0)|8
    data[8]=(sub<<4)|(mapper>>8);data[10]=ram
    return bytes(data)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--jobs',type=int,choices=range(1,9),default=2)
    ap.add_argument('--mappers',nargs='+',type=int,choices=sorted({b[0] for b in BOARDS}))
    args=ap.parse_args()
    boards=[b for b in BOARDS if not args.mappers or b[0] in args.mappers]
    cmake,generator=toolchain();engine=ROOT/'.deps/nesrecomp'
    compiler=prepare_compiler(engine,cmake,generator,print)
    work=ROOT/'.build/nes-windows-selftest';work.mkdir(parents=True,exist_ok=True)
    base=work/'fixture.nes';base.write_bytes(authored(69,0,8));(work/'game.toml').write_text('[game]\n')
    run([compiler,base,'--game',work/'game.toml','--cycle-accurate','--output-prefix','game'],cwd=work,log=work/'codegen.log')
    guards={(pc,op) for pc in PCS for op in range(256)}|{(0x0400,0xA9)}
    write_guards(work/'generated/game_cyc.c',guards,read_nes_rom(base))
    machine=prepare_machine(work,engine)
    (work/'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "'+'0'*64+'"\n')
    sources='\n'.join(f'"{p.as_posix()}"' for p in sorted((work/'generated').glob('game_cyc_*.c')))
    (work/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NesWindowChecks C)
include("{machine.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
foreach(pal 0 1)
add_executable(checks${{pal}} ${{NESRECOMP_CYC_SOURCES}} "{ROOT.as_posix()}/native/nes_windows_checks.c" {sources})
target_include_directories(checks${{pal}} PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} generated "{ROOT.as_posix()}/native" "{work.as_posix()}")
target_compile_definitions(checks${{pal}} PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL=${{pal}})
if(MSVC)
target_compile_options(checks${{pal}} PRIVATE /bigobj)
endif()
target_link_libraries(checks${{pal}} PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
endforeach()
''')
    run([cmake,'-S',work,'-B',work/'build','-G',generator,'-A','x64'],log=work/'build.log')
    run([cmake,'--build',work/'build','--config','Release','--parallel','4'],log=work/'build.log',timeout=1800)
    def check(pal,mapper,sub,ram):
        rom=work/f'board-{mapper}-{sub}-{ram}.nes'
        # Only live bodies and lower-alias dense_step are executed. No hot
        # block compiled for the base mapper is used on another board.
        result=json.loads(run([work/f'build/Release/checks{pal}.exe',rom],cwd=work,timeout=900).strip())
        result['pal']=pal;result['ram_exponent']=ram
        (work/f'result-{pal}-{mapper}-{sub}-{ram}.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result),flush=True)
        return result
    # PAL/NTSC processes may read the same fixture; create them before launch.
    for mapper,sub,ram in boards:
        (work/f'board-{mapper}-{sub}-{ram}.nes').write_bytes(authored(mapper,sub,ram))
    results=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        tasks=[pool.submit(check,pal,*board) for pal in (0,1) for board in boards]
        for task in as_completed(tasks):results.append(task.result())
    results.sort(key=lambda r:(r['pal'],r['mapper'],r['submapper'],r['ram_exponent']))
    (work/('results-selected.json' if args.mappers else 'results.json')).write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
