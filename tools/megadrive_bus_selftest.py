"""Exercise DMA bus suspension using the objects of an actual game build."""
from pathlib import Path
import argparse
import inspect
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tools.megadrive_save_selftest as build
from smsrecomp.core import run


def executable(project, output, harness, z80_source=None):
    # Reuse the checked production-object linker; include the machine copy to
    # exercise Z80 slices without running an artificial future raster frame.
    source = inspect.getsource(build.check)
    if '#include "glue.c"' in harness:
        source=source.replace("Path(p).name.lower()!='console16_main.obj'",
            "Path(p).name.lower() not in ('console16_main.obj','glue.obj')")
        harness=harness.replace('#include "glue.c"','#include "'+(project/'native/glue.c').as_posix()+'"')
    source = source.replace('    assert objects and all(p.is_file() for p in objects)',
        '    objects=[p for p in objects if p.name.lower()!="genesis_machine.obj"]\n'
        '    assert objects and all(p.is_file() for p in objects)')
    source = source[:source.index('    results=[]')] + '    return exe\n'
    if z80_source is not None:
        source = source.replace('    assert objects and all(p.is_file() for p in objects)',
            '    objects=[p for p in objects if p.name.lower()!="md_z80_generated.obj"]\n'
            '    assert objects and all(p.is_file() for p in objects)')
        source = source.replace("    resources=' '.join",
            '    sources += \'\\n  "\' + z80_source.as_posix() + \'"\'\n' + "    resources=' '.join")
    namespace = dict(build.__dict__)
    namespace['z80_source'] = z80_source
    exec(source, namespace)
    namespace['HARNESS'] = harness.replace(
        '#include "genesis_machine.c"', '#include "' + (project / 'native/genesis_machine.c').as_posix() + '"')
    return namespace['check'](project, output)


LOCAL_STATE = r'''
#include <windows.h>
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
int wmain(int argc,wchar_t **argv) {
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
 DeleteFileW(argv[1]);rr16_shutdown();
 printf("{\"checks\":%u,\"passed\":true,\"pending_capture_rejected\":true,\"stable_ack_restored\":true,\"DMA_WAIT_finishes_before_ack\":true}\n",checks);
 return 0;
}
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
