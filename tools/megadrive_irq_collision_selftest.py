"""Sega's late H/V interrupt acknowledgement, in an actual game backend.

The literal 6+4+4 clock entry boundary is a nominal CPU fixture. The source
device priority is from Sega's 1991 Software Development Manual, page 15.
Neither this test nor the runtime claims measured electrical VPA/E timing.
"""
from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.core import run
from tools.megadrive_bus_selftest import executable

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "genesis_machine.c"
#include "glue.c"
static unsigned checks,cases;
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);}}while(0)
static uint32_t peek32(uint32_t a) {
 return ((uint32_t)gbus_peek16(&g_machine.bus,a)<<16)|gbus_peek16(&g_machine.bus,a+2);
}
int main(void) {
 CHECK(rr16_init(true));s_game_running=rr_step_running=1;s_interleave_active=0;
 GVDP *v=&g_machine.vdp;
 for(unsigned h40=0;h40<2;++h40)for(unsigned tall=0;tall<2;++tall)
 for(unsigned enabled=0;enabled<2;++enabled)for(unsigned base=95;base<118;++base) {
  gvdp_reset(v);v->reg[0]=0x10;v->reg[1]=(enabled?0x20:0)|(tall?8:0);
  v->reg[12]=h40?0x81:0;unsigned height=gvdp_screen_height(v);
  gvdp_begin_scanline(v,height);v->rr_irq.hint_pending=1;
  rr_vdp_z80_active=0;
  g_audio_cycle_counter=base;g_cycle_accumulator=0;rr_vdp_cpu_origin=0;
  g_cpu.SR=0x2000;g_cpu.PC=0xff1000;g_cpu.A[7]=0xffe000;
  rr_md_prefetch_reset();rr_md_cpu_stopped=0;
  unsigned fraction=height*3420u%7u,edge=h40?812:800;
  rr_main_fraction=fraction;
  unsigned initial=base*7u-fraction,ack=(base+14u)*7u-fraction;
  gvdp_fifo_advance(v,initial);
  /* The CPU has already selected the H autovector. A later V source can
   * change which VDP latch acknowledges, never that captured CPU vector. */
  uint32_t handler=peek32(0x70)&0xffffffu;
  rr_md_interrupt_entry(4,0x70);++cases;
  gvdp_fifo_advance(v,machine_vdp_phase());
  CHECK(g_cpu.PC==handler && g_cpu.SR==0x2400 && g_cpu.A[7]==0xffdffa);
  CHECK(gbus_peek16(&g_machine.bus,0xffdffa)==0x2000 && peek32(0xffdffc)==0xff1000);
  CHECK(g_audio_cycle_counter==base+44 && g_cycle_accumulator==44);
  if(enabled && ack>=edge) {
   CHECK(!v->vint_pending && v->rr_irq.hint_pending && gvdp_irq_level(v)==4);
   /* The preserved H source is acknowledged at the next entry after RTE. */
   gvdp_irq_ack(v,4);CHECK(!gvdp_irq_level(v) && !v->rr_irq.hint_pending);
  } else {
   if(v->rr_irq.hint_pending)fprintf(stderr,"h40=%u height=%u scanline=%d enabled=%u base=%u initial=%u ack=%u edge=%u fraction=%u pendingV=%u final=%u\n",h40,height,v->scanline,enabled,base,initial,ack,edge,fraction,v->vint_pending,machine_vdp_phase());
   CHECK(!v->rr_irq.hint_pending);
   CHECK(v->vint_pending==(machine_vdp_phase()>=edge));
  }
 }
 /* An unrelated external/gun ACK and masked VDP sources keep their latches.
  * Their physical cross-device acknowledge wiring remains outside this test. */
 gvdp_reset(v);v->reg[0]=0x10;v->reg[1]=0x20;
 v->rr_irq.hint_pending=v->vint_pending=1;gvdp_irq_ack(v,2);
 CHECK(v->rr_irq.hint_pending && v->vint_pending);
 gvdp_irq_ack(v,4);CHECK(!v->vint_pending && v->rr_irq.hint_pending);
 v->reg[0]=0;gvdp_irq_ack(v,4);CHECK(v->rr_irq.hint_pending);
 rr_step_running=s_game_running=0;rr16_shutdown();
 printf("{\"cases\":%u,\"checks\":%u,\"passed\":true,\"actual_backend\":true,\"late_VINT_preserves_HINT_and_selected_CPU_vector\":true,\"electrical_VPA_E_clock_measured\":false}\n",cases,checks);return 0;
}
'''


def check(project, output):
    exe = executable(project, output, HARNESS)
    result = json.loads(run([exe]).strip().splitlines()[-1])
    (output / 'irq-collisions.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('project', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.project.resolve(), args.output.resolve())))
