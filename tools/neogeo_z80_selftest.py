"""ROM-free Neo Geo Z80 AOT ABI, cycle, memory, full-port and guard checks."""
from pathlib import Path
import json,struct,sys
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args
from retrorecomp.neogeo_build import prepare_project
from retrorecomp.neogeo_z80 import generate
from retrorecomp.core import run,toolchain

def main():
    project=ROOT/'.build/neogeo-z80-selftest';project.mkdir(exist_ok=True)
    payload=[]
    for op in range(256):
        if op not in (0xcb,0xdd,0xed,0xfd):payload.append(bytes((op,0x9a,0x1e,0x5d)))
        for prefix in (0xcb,0xed,0xdd,0xfd):payload.append(bytes((prefix,op,0x9a,0x1e)))
        for prefix in (0xdd,0xfd):payload.append(bytes((prefix,0xcb,0xf9,op)))
    payload += [bytes.fromhex(raw) for raw in ('ddfd2100','fddd7600','dded4300','ddedb000','dddd3e00','ddfded43')]
    image=bytearray(65536)
    for n,raw in enumerate(payload):image[0x1000+n*8:0x1004+n*8]=raw
    header=bytearray(4096);header[:4]=b'NEO\x01';struct.pack_into('<6I',header,4,512,131072,65536,0,0,128)
    (project/'cartridge.neo').write_bytes(header+bytes(512+131072)+image+bytes(128))
    with ZipFile(project/'bios.zip','w') as archive:archive.writestr('sm1.sm1',image)
    prepare_project(project,native=True,native_sound=True)
    stats=generate(project,ROOT/'.deps/geolith-libretro',[{'address':0xfffd,'bytes':'c3fdfff3'}])
    (project/'fixture_data.h').write_text('static const uint8_t instructions[][4]={\n'+
        ',\n'.join('{'+','.join(map(str,raw))+'}' for raw in payload)+'\n};\n',encoding='ascii')
    (project/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroNgZ80Checks LANGUAGES C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
add_executable(checks "{ROOT.as_posix()}/native/neogeo_z80_checks.c" engine/z80/z80.c)
target_include_directories(checks PRIVATE . engine)
target_compile_definitions(checks PRIVATE __BYTE_ORDER__=1234 __ORDER_LITTLE_ENDIAN__=1234)
target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
''',encoding='utf-8')
    cmake,generator=toolchain()
    run([cmake,'-S',project,'-B',project/'build','-G',generator,*cmake_target_args()],log=project/'build.log')
    run([cmake,'--build',project/'build','--config','Release','--parallel','4'],log=project/'build.log')
    result=json.loads(run([build_executable(project / 'build', 'checks')]).strip());result['analysis']=stats
    (project/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
