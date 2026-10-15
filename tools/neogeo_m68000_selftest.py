"""ROM-free Neo Geo native MC68000 ABI, dynamic-cycle, IRQ and guard checks."""
from pathlib import Path
import json,struct,sys
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from smsrecomp.neogeo_build import prepare_project
from smsrecomp.neogeo_codegen import generate
from smsrecomp.core import run,toolchain

def main():
    project=ROOT/'.build/neogeo-m68000-selftest';project.mkdir(exist_ok=True)
    cases=['d5c0','08c7000e','08c7001f','0141','08800001','51c8fffe','67000004',
        'c0c1','c1c1','80c1','81c1','e5ab','48e7c080','4c98000f','b109','121f',
        '2300','40c2','027cffff','4e73','4e40','4e60','4e722700','aabc','fabc','4afc',
        '7001','d280','d0b0f000','4eb900001000','4ef900001000','4e75','4e71']
    program=bytearray(b'\x4a\xfc'*(0x200000//2));bios=bytearray(b'\x4a\xfc'*(131072//2))
    for n,raw in enumerate(cases):
        data=bytes.fromhex(raw)+b'\x4e\x75';address=0x200+n*32
        program[address:address+len(data)]=data;bios[address:address+len(data)]=data
        for bank in (0x100000,0x110000):program[bank+address:bank+address+len(data)]=data
        if raw=='7001':program[0x110000+address:0x110002+address]=b'\x70\x07'
    program[0x1000:0x1002]=bios[0x1000:0x1002]=b'\x4e\x71'
    for bank in (0x100000,0x110000):program[bank+0x1000:bank+0x1002]=b'\x4e\x71'
    header=bytearray(4096);header[:4]=b'NEO\x01';struct.pack_into('<6I',header,4,len(program),131072,65536,0,0,128)
    def swapped(data):
        result=bytearray(data);result[0::2],result[1::2]=data[1::2],data[0::2];return result
    (project/'cartridge.neo').write_bytes(header+swapped(program)+bytes(131072+65536+128))
    with ZipFile(project/'bios.zip','w') as archive:archive.writestr('sp-s2.sp1',swapped(bios))
    prepare_project(project,native=True)
    ram=[{'offset':0xf200+n*32,'words':raw} for n,raw in enumerate(cases)]
    ram += [{'offset':0xfc00,'words':raw} for raw in ('203c11223344','203c55667788')]
    # MOVEQ has no observed fixed/BIOS root: the offline aperture sweep must
    # still translate it. The banked and mutable cases retain explicit roots.
    stats=generate(project,{*(0x200+n*32 for n in range(len(cases)) if cases[n]!='7001'),
        *(0xc00200+n*32 for n in range(len(cases)) if cases[n]!='7001'),0x1000,0xc01000},
        {'p':[bank+0x200+n*32 for bank in (0x100000,0x110000) for n in range(len(cases))]},ram)
    (project/'fixture_data.h').write_text('static const uint16_t instructions[][8]={\n'+
        ',\n'.join('{'+','.join(str(int.from_bytes((bytes.fromhex(raw)+bytes(16))[w:w+2],'big')) for w in range(0,16,2))+'}' for raw in cases)+'\n};\n',encoding='ascii')
    (project/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroNgM68kChecks LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
file(GLOB STEPS "${{CMAKE_CURRENT_SOURCE_DIR}}/steps/ng_step_*.c")
add_executable(checks "{ROOT.as_posix()}/native/neogeo_m68000_checks.c" neogeo_native.c ng_arithmetic.c
 engine/m68k/m68kcpu.c engine/m68k/m68kops.c ${{STEPS}})
target_include_directories(checks PRIVATE . engine)
target_compile_definitions(checks PRIVATE RR_NG_NATIVE=1)
target_compile_options(checks PRIVATE /utf-8 /wd4996)
''',encoding='utf-8')
    cmake,generator=toolchain();run([cmake,'-S',project,'-B',project/'build','-G',generator,'-A','x64'],log=project/'build.log')
    run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=project/'build.log')
    result=json.loads(run([project/'build/Release/checks.exe']).strip());result['analysis']=stats
    (project/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
