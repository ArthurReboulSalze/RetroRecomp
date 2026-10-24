"""Exercise DMA bus suspension using the objects of an actual game build."""
from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.platforms import sdl_install
from retrorecomp.core import run
from retrorecomp.platforms import build_executable, cmake_target_args, build_jobs


def native_executable(project, output, harness, z80_source=None):
    """Link authored fixtures against current production objects, never run its ROM."""
    from retrorecomp.core import toolchain
    output.mkdir(parents=True, exist_ok=True)
    work = output / 'harness'
    work.mkdir(exist_ok=True)
    excluded = {'console16_main', 'genesis_machine'}
    if '#include "glue.c"' in harness:
        excluded.add('glue')
        harness = harness.replace('#include "glue.c"', '#include "' + (project/'native/glue.c').as_posix() + '"')
    harness = harness.replace('#include "genesis_machine.c"', '#include "' + (project/'native/genesis_machine.c').as_posix() + '"')
    if z80_source is not None:
        excluded.add('md_z80_generated')
    resources=[]
    if os.name=='nt':
        from retrorecomp import toolchain
        if toolchain.active() != toolchain.MSVC:
            raise SystemExit('This check reads Visual Studio build files; run it with RETRO_RECOMP_TOOLCHAIN=msvc.')
        # Incremental MSBuild tlogs retain old input sets. The current project
        # is the authority; using its first historical tlog record omitted
        # later state, battery and feedback objects from the fixture link.
        import xml.etree.ElementTree as ET
        from collections import Counter
        tree=ET.parse(project/'build/game.vcxproj')
        ns={'m':'http://schemas.microsoft.com/developer/msbuild/2003'}
        names=[Path(n.attrib['Include']).stem.lower() for n in tree.findall('.//m:ClCompile',ns)
               if 'Include' in n.attrib]
        assert all(n==1 for n in Counter(names).values()), 'Ambiguous source/object names'
        folder=project/'build/game.dir/Release'
        objects=[]
        for name in names:
            if name in excluded:continue
            found=list(folder.rglob(name+'.obj'))
            assert len(found)==1,(name,found)
            objects.append(found[0])
        for node in tree.findall('.//m:ResourceCompile',ns):
            if 'Include' not in node.attrib:continue
            found=list(folder.rglob(Path(node.attrib['Include']).stem+'.res'))
            assert len(found)==1,found
            resources+=found
    else:
        objects=sorted(p for p in (project/'build/CMakeFiles/game.dir').rglob('*.o')
                       if p.name.removesuffix('.o').removesuffix('.c').removesuffix('.cpp') not in excluded)
    assert objects and any(p.name in ('md_backend.obj','md_backend.c.o') for p in objects)
    sources = '\n'.join('  "' + p.as_posix() + '"' for p in objects)
    if z80_source is not None:
        sources += '\n  "' + z80_source.as_posix() + '"'
    (work/'checks.c').write_text(harness, encoding='utf-8')
    runner = (project/'engine/runner').as_posix()
    libraries='SDL2::SDL2-static '+('ws2_32 comdlg32' if os.name=='nt' else 'dl m pthread')
    libraries+=' '+ ' '.join('"'+p.as_posix()+'"' for p in resources)
    (work/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdBusChecks C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 REQUIRED)
add_executable(checks checks.c
{sources})
set_target_properties(checks PROPERTIES LINKER_LANGUAGE CXX)
target_compile_definitions(checks PRIVATE RR16_MD=1 OWN_BACKEND=1)
target_include_directories(checks PRIVATE "{project.as_posix()}" "{project.as_posix()}/native"
 "{runner}" "{runner}/include" "{runner}/video" "{runner}/audio"
 "{runner}/external/superzazu" "{runner}/external/clowncommon"
 "{(ROOT/'.deps/segagenesisrecomp/recompiler/src').as_posix()}")
target_link_libraries(checks PRIVATE {libraries})
if(MSVC)
 target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
 target_link_options(checks PRIVATE /CETCOMPAT:NO)
endif()
''', encoding='utf-8')
    cmake, generator = toolchain()
    run([cmake, '-S', work, '-B', work/'build', '-G', generator, *cmake_target_args(),
         '-DCMAKE_PREFIX_PATH='+sdl_install().as_posix()], log=work/'build.log')
    run([cmake, '--build', work/'build', '--config', 'Release', '--parallel', build_jobs()], log=work/'build.log')
    return build_executable(work/'build', 'checks')


def executable(project, output, harness, z80_source=None):
    return native_executable(project, output, harness, z80_source)


LOCAL_STATE = r'''
#include "platform_io.h"
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "genesis_runtime.h"
#include "genesis_machine.c"
extern void rr_md_portable_restart(uint32_t pc);
extern void rr_md_portable_arm(uint32_t pc);
extern uint32_t rr_md_cpu_stopped;
static unsigned checks;
#define CHECK(ok) do { ++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static unsigned waiting_reads;
static uint8_t waiting_read(void *user,uint16_t address) {
 uint8_t value=gbus_z80_read((GenesisBus *)user,address);
 if(address==0x8000) { CHECK(!machine_z80_bus_acknowledged());++waiting_reads; }
 return value;
}
static int checks_main(int argc,wchar_t **argv) {
 CHECK(argc==2 && rr16_init(true));GenesisMachine *m=&g_machine;
 g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
 rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
 m->bus.z80_reset_off=1;m->bus.z80_reset_pending=0;
 m->bus.z80_ram[0]=0x04;m->bus.z80_ram[1]=0xc3;m->bus.z80_ram[2]=m->bus.z80_ram[3]=0;
 g_audio_cycle_counter=rr_vdp_cpu_origin=0;
 gbus_write8(&m->bus,0xa11100,1);
 CHECK(!machine_z80_bus_acknowledged() && !rr16_state_ready());
 size_t size=99;CHECK(!rr16_state_capture(&size) && !size);
 machine_run_frame(NULL,NULL);
 CHECK(machine_z80_bus_acknowledged() && !rr_z80_busy && rr16_state_ready());
 uint8_t b=m->z80.b;CHECK(rr16_state_file(argv[1],false));
 gbus_write8(&m->bus,0xa11100,0);machine_run_frame(NULL,NULL);
 CHECK(!m->bus.z80_busreq && m->z80.b!=b);
 CHECK(rr16_state_file(argv[1],true));
 CHECK(machine_z80_bus_acknowledged() && m->bus.z80_busreq && m->z80.b==b);
 machine_run_frame(NULL,NULL);CHECK(machine_z80_bus_acknowledged() && m->z80.b==b);
 gbus_write8(&m->bus,0xa11100,0);machine_run_frame(NULL,NULL);
 CHECK(!machine_z80_bus_acknowledged() && m->z80.b!=b && rr16_state_ready());
 /* An external read already in WAIT must finish before local BUSACK, even
  * when source DMA holds it across scanlines. Observe ACK in the real read
  * callback, rather than inferring its ordering from final CPU equality. */
 rr16_reset();g_cpu.SR=0x2700;g_cpu.A[7]=0xffff00;
 rr_md_portable_restart(1);rr_md_portable_arm(0xff0100);rr_md_cpu_stopped=1;
 m->bus.z80_reset_off=1;m->bus.z80_busreq=m->bus.z80_reset_pending=0;
 z80_own_reset(&m->z80);m->bus.z80_bank=0x1c0;m->z80.read_byte=waiting_read;
 m->bus.z80_ram[0]=0x3a;m->bus.z80_ram[1]=0;m->bus.z80_ram[2]=0x80;m->bus.z80_ram[3]=0x76;
 g_ram[0]=0x71;g_audio_cycle_counter=rr_vdp_cpu_origin=0;
 rr_z80_start();rr_z80_time=-150;rr_z80_limit=1;rr_bus_scheduling=1;
 do { rr_z80_resume(); } while(rr_z80_checkpoint);rr_bus_scheduling=0;
 CHECK(rr_z80_blocked && rr_z80_request && !waiting_reads);
 GVDP *v=&m->vdp;gvdp_reset(v);v->reg[1]=0x50;v->reg[12]=0x81;v->reg[15]=2;
 v->reg[19]=0;v->reg[20]=4;v->reg[21]=v->reg[22]=0;v->reg[23]=0x70;
 gvdp_write_control(v,0x4000);gvdp_write_control(v,0x0080);
 g_audio_cycle_counter=2;gbus_write8(&m->bus,0xa11100,1);
 rr_bus_slice(m,0,213,0,0);
 CHECK(gvdp_dma_blocks_cpu(v) && !machine_z80_bus_acknowledged() && !waiting_reads);
 machine_run_frame(NULL,NULL);
 CHECK(waiting_reads==1 && machine_z80_bus_acknowledged() && m->z80.a==0x71);
 CHECK(rr_z80_busy && !rr16_state_ready());
 gbus_write8(&m->bus,0xa11100,0);machine_run_frame(NULL,NULL);
 CHECK(waiting_reads==1 && !rr_md_bus_busy() && rr16_state_ready());
 rr_remove(argv[1]);rr16_shutdown();
 printf("{\"checks\":%u,\"passed\":true,\"pending_capture_rejected\":true,\"stable_ack_restored\":true,\"DMA_WAIT_finishes_before_ack\":true}\n",checks);
 return 0;
}
#ifdef _WIN32
int wmain(int argc,wchar_t **argv) { return checks_main(argc,argv); }
#else
int main(int argc,char **argv) {
 wchar_t path[4096];CHECK(argc==2 && rr_from_utf8(argv[1],path,4096));
 wchar_t *args[]={L"checks",path};return checks_main(argc,args);
}
#endif

'''


def check(project, output):
    exe = executable(project, output, (ROOT / 'native/md_bus_checks.c').read_text(encoding='utf-8'))
    result = json.loads(run([exe, output / 'guarded.rrstate']).strip().splitlines()[-1])
    state_output = output / 'local-state'
    state_exe = executable(project, state_output, LOCAL_STATE)
    result['local_state'] = json.loads(run([state_exe, state_output / 'stable.rrstate']).strip().splitlines()[-1])
    (output / 'bus.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.project.resolve(), args.output.resolve())))
