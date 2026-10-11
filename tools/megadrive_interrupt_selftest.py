"""Authored nominal VDP interrupt priority, stack and mask boundary matrix.

Requires a generated game's objects. No claim about VPA/E-clock electrical
timing or level-7/external-vector device wiring.
"""
from pathlib import Path
import argparse
import inspect
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from smsrecomp.core import run
import tools.megadrive_save_selftest as build

HARNESS = r'''
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "SOURCE_GLUE"
static unsigned checks,cases;
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static uint32_t peek32(uint32_t a) {
 return ((uint32_t)gbus_peek16(&g_machine.bus,a)<<16)|gbus_peek16(&g_machine.bus,a+2);
}
int wmain(void) {
 CHECK(rr16_init(true));s_game_running=1;rr_step_running=1;
 for(unsigned mask=0;mask<8;++mask)for(unsigned pending=0;pending<4;++pending)
 for(unsigned enabled=0;enabled<4;++enabled)for(unsigned supervisor=0;supervisor<2;++supervisor)
 for(unsigned stopped=0;stopped<2;++stopped)for(unsigned wrap=0;wrap<2;++wrap)
 for(unsigned held=0;held<3;++held) {
  GVDP *v=&g_machine.vdp;
  v->reg[0]=(enabled&1)?0x10:0;v->reg[1]=(enabled&2)?0x20:0;
  v->rr_irq.hint_pending=pending&1;v->vint_pending=!!(pending&2);s_own_vint_latched=0;
  memset(&v->rr_dma,0,sizeof v->rr_dma);v->dma_active=held==1;
  if(held==1){v->rr_dma.mode=1;v->rr_dma.remaining=1;}
  rr16_md_instruction(held==2);
  uint16_t sr=(supervisor?0xa000:0x8000)|(mask<<8)|0x15;
  g_cpu.SR=sr;g_cpu.PC=0xff1000;g_cpu.A[7]=supervisor?0xffe000:0xffd000;
  g_cpu.USP=supervisor?0xffd000:0xffe000;
  rr_md_cpu_stopped=stopped;rr_md_prefetch_reset();
  uint32_t before=wrap?0xfffffff0u:0;g_audio_cycle_counter=g_cycle_accumulator=before;
  unsigned level=held?0:(pending&enabled&2) && mask<6?6:(pending&enabled&1) && mask<4?4:0;
  rr_md_poll_vdp_irq();++cases;
  if(!level) {
   CHECK(g_cpu.PC==0xff1000 && g_cpu.SR==sr && g_audio_cycle_counter==before);
   CHECK(g_cpu.A[7]==(supervisor?0xffe000:0xffd000) && rr_md_cpu_stopped==stopped);
   CHECK(v->rr_irq.hint_pending==(pending&1) && v->vint_pending==!!(pending&2));
  } else {
   CHECK(g_cpu.PC==(peek32(0x60+4*level)&0xffffffu));
   CHECK(g_cpu.SR==(0x2015|(level<<8)) && !rr_md_cpu_stopped);
   CHECK(g_cpu.A[7]==0xffdffa && g_cpu.USP==0xffd000);
   CHECK(gbus_peek16(&g_machine.bus,0xffdffa)==sr && peek32(0xffdffc)==0xff1000);
   CHECK(g_audio_cycle_counter-before==44 && g_cycle_accumulator-before==44);
   CHECK(v->rr_irq.hint_pending==(level==4?0:(pending&1)) && v->vint_pending==(level==6?0:!!(pending&2)));
   /* A repeated poll at the raised mask must not duplicate the frame or ACK. */
   rr_md_poll_vdp_irq();CHECK(g_cpu.A[7]==0xffdffa && g_audio_cycle_counter-before==44);
  }
  rr16_md_instruction(false);
 }
 rr_step_running=s_game_running=0;rr16_shutdown();
 printf("{\"cases\":%u,\"checks\":%u,\"passed\":true,\"actual_backend\":true,\"nominal_masks_priority_user_supervisor_STOP_DMA_live_instruction_wrap\":true,\"electrical_VPA_level7_external_devices_qualified\":false}\n",cases,checks);
 return 0;
}
'''


def check(project, output):
    source = inspect.getsource(build.check)
    source = source.replace('    assert objects and all(p.is_file() for p in objects)',
        '    objects=[p for p in objects if p.name.lower()!="glue.obj"]\n'
        '    assert objects and all(p.is_file() for p in objects)')
    source = source[:source.index('    results=[]')] + '    return exe\n'
    source = source.replace('    cmake,generator=toolchain()',
        '    with (work/"CMakeLists.txt").open("a",encoding="utf-8") as f:\n'
        '        f.write(\'target_include_directories(checks PRIVATE "\'+(ROOT/".deps/segagenesisrecomp/recompiler/src").as_posix()+\'" "\'+(ROOT/".deps/segagenesisrecomp/external/m68k-recomp-core/src").as_posix()+\'")\\n\')\n'
        '    cmake,generator=toolchain()')
    ns = dict(build.__dict__)
    exec(source, ns)
    ns['HARNESS'] = HARNESS.replace('SOURCE_GLUE', (project / 'native/glue.c').as_posix())
    exe = ns['check'](project, output)
    result = json.loads(run([exe]).strip().splitlines()[-1])
    (output / 'interrupts.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('project', type=Path)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(check(args.project.resolve(), args.output.resolve())))
