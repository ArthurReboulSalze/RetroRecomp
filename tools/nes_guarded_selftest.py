"""Authored NES RAM guards and PPU-driven mapper fetch comparisons."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from smsrecomp.core import run,toolchain
from smsrecomp.nes_codegen import prepare_compiler
from smsrecomp.nes_machine import prepare_machine
from smsrecomp.nes_ram import write_guards
from smsrecomp.nes import read_nes_rom
from tools.nes_native_selftest import fixture

def authored(mapper):
    base=fixture(0);prg=bytearray(base[16:16+32768])
    count=32 if mapper in (1,153,155) else 2
    prg=(prg*(count//2))
    if count==32:
        for bank in range(64,128):
            for op in range(256):prg[bank*4096+0x100+op*4]^=0x40
    header=bytearray(b'NES\x1a'+bytes(12));header[4]=count;header[5]=1
    header[6]=(mapper&15)<<4;header[7]=(mapper&0xF0)|8
    header[10]=9 if mapper==5 else 8 if mapper==69 else 7
    if count==32:
        header[5]=0;header[11]=7
    if mapper==153:header[10]=0x70
    return bytes(header+prg+bytes(header[5]*8192))

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mappers',nargs='+',type=int,default=[0,5,69,1,153,155])
    ap.add_argument('--standards',nargs='+',choices=['ntsc','pal'],default=['ntsc','pal'])
    args=ap.parse_args();cmake,generator=toolchain();engine=ROOT/'.deps/nesrecomp'
    compiler=prepare_compiler(engine,cmake,generator,print);work=ROOT/'.build/nes-guarded-selftest'
    results=[]
    for standard in args.standards:
        for mapper in args.mappers:
            project=work/f'{standard}-{mapper}';project.mkdir(parents=True,exist_ok=True)
            rom=project/'fixture.nes';rom.write_bytes(authored(mapper))
            (project/'game.toml').write_text('[game]\n')
            run([compiler,rom,'--game',project/'game.toml','--cycle-accurate','--output-prefix','game'],cwd=project,log=project/'codegen.log')
            addresses=[0x0300,0x0B00,0x07FE,0x1FFE,0x6000,0x6FFE,0x7FFE,0x8000,0xBFFE]
            guards={(pc,op) for pc in addresses for op in range(256)}|{(0x0400,0xA9)}
            write_guards(project/'generated/game_cyc.c',guards,read_nes_rom(rom))
            machine=prepare_machine(project,engine)
            (project/'retro_nes_config.h').write_text('#define RR_NES_ROM_SHA "'+'0'*64+'"\n')
            sources='\n'.join(f'"{p.as_posix()}"' for p in sorted((project/'generated').glob('game_cyc_*.c')))
            (project/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(NesGuardedChecks C)
include("{machine.as_posix()}/cyc.cmake")
list(REMOVE_ITEM NESRECOMP_CYC_SOURCES "${{NESRECOMP_CYC_DIR}}/cyc_host.c")
add_executable(checks ${{NESRECOMP_CYC_SOURCES}} "{ROOT.as_posix()}/native/nes_guarded_checks.c" {sources})
target_include_directories(checks PRIVATE ${{NESRECOMP_CYC_INCLUDE_DIRS}} generated "{ROOT.as_posix()}/native" "{project.as_posix()}")
target_compile_definitions(checks PRIVATE _CRT_SECURE_NO_WARNINGS RR_NES_PAL={int(standard=='pal')})
if(MSVC)
target_compile_options(checks PRIVATE /bigobj)
endif()
target_link_libraries(checks PRIVATE ${{NESRECOMP_CYC_LIBRARIES}})
''')
            run([cmake,'-S',project,'-B',project/'build','-G',generator,'-A','x64'],log=project/'build.log',timeout=600)
            run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=project/'build.log',timeout=1800)
            result=json.loads(run([project/'build/Release/checks.exe',rom],timeout=600).strip())
            result['standard']=standard
            (project/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            results.append(result);print(json.dumps(result),flush=True)
    (work/'results.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
