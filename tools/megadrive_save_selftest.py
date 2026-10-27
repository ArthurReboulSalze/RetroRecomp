"""Check F1, boot/warm F8/F9 and battery rewinds using a built game's objects.

Only a small diagnostic main is compiled; the game's actual backend, snapshot
codec, generated code and resource are reused. All test writes are isolated.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from retrorecomp.platforms import build_executable, cmake_target_args, sdl_install
from retrorecomp.core import run,toolchain
sys.path.insert(0, str(Path(__file__).resolve().parent))  # tools/, also when imported as tools.<name>
from state_checks import final_json

HARNESS=r'''
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "md_battery.h"
#include "video/genesis_machine.h"
static unsigned checks;
#define CHECK(ok) do { ++checks; if (!(ok)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#ok); exit(1); } } while(0)
static uint8_t before[65536];
static void pattern(uint8_t seed) {
    gbus_write8(&g_machine.bus,0xa130f1,1);
    for(uint32_t i=0;i<g_machine.bus.sram_size;++i)
        gbus_write8(&g_machine.bus,g_machine.bus.sram_base+i*g_machine.bus.sram_stride,(uint8_t)(seed+17*i));
}
static int has_pattern(uint8_t seed) {
    for(uint32_t i=0;i<g_machine.bus.sram_size;++i)
        if(g_machine.bus.sram[i]!=(uint8_t)(seed+17*i))return 0;
    return 1;
}
int wmain(int argc,wchar_t **argv) {
    CHECK(argc==5); CHECK(rr16_init(true));
    GenesisBus *b=&g_machine.bus; CHECK(b->sram_present && b->sram_battery && b->sram_size<=sizeof before);
    uint8_t boot=b->sram_enabled;
    CHECK(rr_md_battery_open(b,argv[4]));
    if(!wcscmp(argv[1],L"create")) {
        for(uint32_t base=0xe00000;base<=0xff0000;base+=0x10000)
            gbus_write16(b,base+0x1234,(uint16_t)(base>>16));
        CHECK(gbus_peek16(b,0xe01234)==0xff); /* one physical array */
        GVDP *v=&g_machine.vdp;
        for(uint32_t base=0xe00000;base<=0xff0000;base+=0x10000) {
            uint32_t src=(base+0x1234)>>1;
            gbus_write16(b,base+0x1234,0x1234);gbus_write16(b,base+0x1236,0x5678);
            v->reg[1]=0x10;v->reg[15]=2;v->reg[0x13]=2;v->reg[0x14]=0;
            v->reg[0x15]=(uint8_t)src;v->reg[0x16]=(uint8_t)(src>>8);v->reg[0x17]=(uint8_t)(src>>16);
            v->control_pending=0;gvdp_write_control(v,0x4000);gvdp_write_control(v,0x0080);
            CHECK(v->dma_active && v->rr_dma.remaining==2);
            gvdp_fifo_advance(v,v->rr_fifo.clock+3420);
            CHECK(v->vram[0]==0x12 && v->vram[1]==0x34 && v->vram[2]==0x56 && v->vram[3]==0x78);
        }
        pattern(0x31);gbus_write8(b,0xa130f1,3);
        gvdp_reset(v);v->reg[1]=0x40;v->reg[12]=0x81;v->reg[15]=2;
        v->vram[0]=v->vram[1]=0;v->code=1;v->address=0;
        gvdp_write_data(v,0x1234);gvdp_fifo_advance(v,352);
        CHECK(v->rr_fifo.count==1 && v->rr_fifo.half==1 && v->vram[0]==0 && v->vram[1]==0x34);
        v->reg[1]|=0x10;v->reg[19]=2;v->reg[20]=0;
        uint32_t source=0xe01234u>>1;
        v->reg[21]=(uint8_t)source;v->reg[22]=(uint8_t)(source>>8);v->reg[23]=(uint8_t)(source>>16);
        v->control_pending=0;gvdp_write_control(v,0x4010);gvdp_write_control(v,0x0080);
        v->vint_pending=1;v->rr_irq.hint_pending=1;
        CHECK(v->rr_dma.remaining==2 && v->dma_active);
        CHECK(rr16_state_file(argv[2],false)); /* F8 before the first frame */
        pattern(0x82);rr16_reset(); CHECK(has_pattern(0x82) && b->sram_enabled==boot);
        gbus_write16(b,0xe01234,0xabcd);
        CHECK(rr16_state_file(argv[2],true)); CHECK(has_pattern(0x31) && b->sram_enabled==3);
        CHECK(v->rr_fifo.count==1 && v->rr_fifo.half==1 && v->rr_fifo.clock==352);
        CHECK(v->rr_dma.remaining==2 && v->dma_active && v->vint_pending && v->rr_irq.hint_pending);
        gvdp_fifo_advance(v,820);CHECK(v->vram[0]==0x12 && v->vram[1]==0x34 && v->rr_fifo.count==2 && !v->dma_active);
        gvdp_fifo_advance(v,2000);CHECK(!v->dma_active && v->vram[16]==0x12 && v->vram[17]==0x34);
        for(uint32_t base=0xe00000;base<=0xff0000;base+=0x10000)
            CHECK(gbus_peek16(b,base+0x1234)==0x1234);
        rr16_reset(); /* discard authored RAM/VDP setup before game progression */
        size_t n=machine_rb_save(NULL,0);void *machine=malloc(n);CHECK(machine && machine_rb_save(machine,n)==n);
        ((GenesisMachine *)machine)->bus.sram_size++;
        CHECK(!machine_rb_load(machine,n) && has_pattern(0x31)); free(machine);
        machine=malloc(n);CHECK(machine && machine_rb_save(machine,n)==n);
        ((GenesisMachine *)machine)->vdp.rr_fifo.count=5;
        CHECK(!machine_rb_load(machine,n) && !g_machine.vdp.rr_fifo.count);free(machine);
        machine=malloc(n);CHECK(machine && machine_rb_save(machine,n)==n);
        ((GenesisMachine *)machine)->vdp.rr_dma.remaining=65537;
        CHECK(!machine_rb_load(machine,n) && !g_machine.vdp.rr_dma.remaining);free(machine);
        for(unsigned i=0;i<90;++i) CHECK(rr16_frame(0,0));
        memcpy(before,b->sram,b->sram_size);uint8_t control=b->sram_enabled;
        CHECK(rr16_state_file(argv[3],false));
        pattern(0x8d);rr16_reset(); CHECK(has_pattern(0x8d) && b->sram_enabled==boot);
        CHECK(rr_md_battery_flush(b,10000,true));
        CHECK(rr16_state_file(argv[3],true));
        CHECK(!memcmp(before,b->sram,b->sram_size) && b->sram_enabled==control);
        CHECK(rr_md_battery_flush(b,10001,true)); /* F9 persists its restored SRAM */
    } else if(!wcscmp(argv[1],L"restore")) {
        memcpy(before,b->sram,b->sram_size);
        CHECK(rr16_state_file(argv[3],true));CHECK(!memcmp(before,b->sram,b->sram_size));
        CHECK(rr16_state_file(argv[2],true));CHECK(has_pattern(0x31) && b->sram_enabled==3);
        GVDP *v=&g_machine.vdp;
        CHECK(v->rr_fifo.count==1 && v->rr_fifo.half==1 && v->rr_fifo.clock==352);
        CHECK(v->rr_dma.remaining==2 && v->dma_active && v->vint_pending && v->rr_irq.hint_pending);
        gvdp_fifo_advance(v,820);CHECK(v->vram[0]==0x12 && v->vram[1]==0x34 && v->rr_fifo.count==2 && !v->dma_active);
        gvdp_fifo_advance(v,2000);CHECK(!v->dma_active && v->vram[16]==0x12 && v->vram[17]==0x34);
        CHECK(gbus_peek16(b,0xe01234)==0x1234 && gbus_peek16(b,0xff1234)==0x1234);
        CHECK(rr_md_battery_flush(b,10000,true));
    } else {
        CHECK(!wcscmp(argv[1],L"verify"));CHECK(has_pattern(0x31));
        rr16_reset();CHECK(has_pattern(0x31) && b->sram_enabled==boot);
    }
    rr16_shutdown();printf("{\"checks\":%u,\"passed\":true}\n",checks);return 0;
}
'''


def check(project,output):
    from retrorecomp import toolchain
    if toolchain.active() != toolchain.MSVC:
        raise SystemExit('This check reads Visual Studio build files; run it with RETRO_RECOMP_TOOLCHAIN=msvc.')
    project=project.resolve();output.mkdir(parents=True,exist_ok=True)
    log=project/'build/game.dir/Release/game.tlog/link.command.1.tlog'
    lines=log.read_text(encoding='utf-16').splitlines()
    objects=[Path(p) for p in next(line for line in lines if line.startswith('^'))[1:].split('|')
             if Path(p).suffix.lower() in ('.obj','.res') and Path(p).name.lower()!='console16_main.obj']
    assert objects and all(p.is_file() for p in objects)
    work=output/'harness';work.mkdir(exist_ok=True)
    (work/'checks.c').write_text(HARNESS,encoding='utf-8')
    runner=(project/'engine/runner').as_posix()
    sources='\n'.join('  "'+p.as_posix()+'"' for p in objects if p.suffix.lower()=='.obj')
    resources=' '.join('"'+p.as_posix()+'"' for p in objects if p.suffix.lower()=='.res')
    (work/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(RetroMdSaveChecks C CXX)
set(CMAKE_C_STANDARD 11)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 REQUIRED)
add_executable(checks checks.c
{sources})
set_target_properties(checks PROPERTIES LINKER_LANGUAGE CXX)
target_compile_definitions(checks PRIVATE RR16_MD=1 OWN_BACKEND=1)
target_include_directories(checks PRIVATE "{project.as_posix()}" "{runner}" "{runner}/include"
 "{(ROOT/'.deps/segagenesisrecomp/recompiler/src').as_posix()}"
 "{runner}/video" "{runner}/audio" "{runner}/external/superzazu" "{runner}/external/clowncommon")
target_link_libraries(checks PRIVATE SDL2::SDL2-static ws2_32 comdlg32 {resources})
target_link_options(checks PRIVATE /CETCOMPAT:NO)
target_compile_options(checks PRIVATE "$<$<C_COMPILER_ID:MSVC>:/utf-8;/wd4996>")
''',encoding='utf-8')
    cmake,generator=toolchain()
    run([cmake,'-S',work,'-B',work/'build','-G',generator,*cmake_target_args(),
         '-DCMAKE_PREFIX_PATH='+sdl_install().as_posix()],log=work/'build.log')
    run([cmake,'--build',work/'build','--config','Release','--parallel','2'],log=work/'build.log')
    exe=build_executable(work / 'build', 'checks')
    results=[]
    with tempfile.TemporaryDirectory(prefix='rr-md-saves-') as temp:
        storage=Path(temp); cold=storage/'cold.rrstate';warm=storage/'warm.rrstate';battery=storage/'datas/saves/authored.rrsram'
        for mode in ('create','restore','verify'):
            results.append(final_json(run([exe,mode,cold,warm,battery])))
        assert sorted(p.relative_to(storage).as_posix() for p in storage.rglob('*') if p.is_file())==[
            'cold.rrstate','datas/saves/authored.rrsram','warm.rrstate']
    result={'project':str(project),'checks':sum(x['checks'] for x in results),'passed':True,
        'reset_retains_cartridge_ram':True,'cold_and_warm_states_restore_sram_and_gate':True,
        'snapshot_rejects_changed_geometry':True,'fresh_process_battery_and_state_reload':True,
        'work_ram_aliases_survive_state_reload':True,'vdp_dma_from_all_work_ram_aliases':True,
        'cold_state_restores_partial_vdp_fifo_word':True,'invalid_vdp_fifo_rejected_before_machine_mutation':True,
        'cold_state_restores_active_dma_and_pending_irqs':True,'invalid_dma_rejected_before_machine_mutation':True,
        'state_rewind_persisted':True,'gameplay_save_menu_validated':False}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args()
    output=a.output or ROOT/'.build/megadrive-save-selftest'/a.project.name
    print(json.dumps(check(a.project,output.resolve())))


if __name__=='__main__':main()
