"""Actual built EEPROM game's F8/F9, unfinished write and battery restart.

Test writes are isolated. The source cartridge and player files are untouched.
"""
from pathlib import Path
import argparse,json,sys,tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from smsrecomp.core import run
from tools.megadrive_bus_selftest import executable

MAIN=r'''
int wmain(int argc,wchar_t **argv) {
    CHECK(argc==4 && rr16_init(true));CHECK(RR_MD_EEPROM_KIND);
    CHECK(rr_md_battery_open(&g_machine.bus,argv[3]));
    if(!wcscmp(argv[1],L"gamewrite") || !wcscmp(argv[1],L"gameread")) {
        CHECK(RR_MD_EEPROM_KIND==1);uint32_t writes=rr_md_cart_state()->eeprom.completed_writes;
        for(unsigned frame=0;frame<600;++frame)CHECK(rr16_frame(0,0));
        uint32_t delta=rr_md_cart_state()->eeprom.completed_writes-writes;
        CHECK(!wcscmp(argv[1],L"gamewrite")?delta>0:delta==0);
        CHECK(rr16_interpreted()==0 && rr16_audio_interpreted()==0);
        CHECK(rr_md_battery_flush(&g_machine.bus,600,true));
        rr16_shutdown();printf("{\"passed\":true,\"checks\":%u,\"original_game_writes\":%u}\n",checks,delta);return 0;
    }
    if(!wcscmp(argv[1],L"create")) {
        CHECK(read_byte(0x63)==0xff);write_byte(0x63,0x96);
        CHECK(rr_md_cart_state()->eeprom.busy_left && g_machine.bus.sram[0x63]==0xff);
        CHECK(rr16_state_file(argv[2],false));
    } else CHECK(!wcscmp(argv[1],L"restore") && rr16_state_file(argv[2],true));
    CHECK(rr_md_cart_state()->eeprom.busy_left && g_machine.bus.sram[0x63]==0xff);
    size_t size;uint8_t *saved=rr16_state_capture(&size);CHECK(saved);
    RrMdCartState before=*rr_md_cart_state();
    saved[size-sizeof before+offsetof(RrMdCartState,eeprom)+offsetof(RrMdEeprom,phase)]=0xff;
    CHECK(!rr16_state_restore(saved,size));CHECK(!memcmp(&before,rr_md_cart_state(),sizeof before));
    RrMdCartState invalid=before;invalid.eeprom.phase=RR_EE_READ;
    invalid.eeprom.bits=8;invalid.eeprom.scl=0;
    memcpy(saved+size-sizeof invalid,&invalid,sizeof invalid);
    CHECK(!rr16_state_restore(saved,size));CHECK(!memcmp(&before,rr_md_cart_state(),sizeof before));free(saved);
    g_machine.master_cycle=before.eeprom.last_tick+before.eeprom.busy_left-1;
    rr_md_cart_advance(&g_machine.bus,g_machine.master_cycle);CHECK(g_machine.bus.sram[0x63]==0xff);
    rr_md_cart_advance(&g_machine.bus,++g_machine.master_cycle);CHECK(g_machine.bus.sram[0x63]==0x96);
    CHECK(rr_md_cart_state()->eeprom.completed_writes==1 && read_byte(0x63)==0x96);
    CHECK(rr_md_battery_flush(&g_machine.bus,30000,true));
    CHECK(rr16_state_file(argv[2],true));CHECK(g_machine.bus.sram[0x63]==0xff);
    CHECK(rr_md_battery_flush(&g_machine.bus,30001,true));
    CHECK(rr_md_cart_state()->eeprom.busy_left==before.eeprom.busy_left);
    g_machine.master_cycle=before.eeprom.last_tick+before.eeprom.busy_left;
    rr_md_cart_advance(&g_machine.bus,g_machine.master_cycle);CHECK(read_byte(0x63)==0x96);
    rr16_reset();CHECK(read_byte(0x63)==0x96 && !rr_md_cart_state()->eeprom.busy_left);
    CHECK(rr_md_battery_flush(&g_machine.bus,30002,true));
    rr16_shutdown();printf("{\"passed\":true,\"checks\":%u}\n",checks);return 0;
}
'''


def check(project,output):
    master=(ROOT/'native/md_cart_checks.c').read_text(encoding='utf-8').split('int wmain(')[0]
    master=master.replace('static GenesisBus fixture_bus;','#define fixture_bus g_machine.bus')
    master=master.replace('static uint64_t guest_clock;','')
    master=master.replace('uint64_t machine_cart_stamp(void) { return guest_clock; }','')
    master=master.replace('guest_clock+=101;','g_machine.master_cycle+=101;')
    harness='''#include <stdio.h>
#include <stdlib.h>
#include <stddef.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "genesis_machine.c"
static unsigned checks;
#define CHECK(ok) do {++checks;if(!(ok)){fprintf(stderr,"FAIL %d: %s\\n",__LINE__,#ok);exit(1);}}while(0)
'''+master+MAIN
    exe=executable(project,output,harness);results=[]
    with tempfile.TemporaryDirectory(prefix='rr-ee-state-') as temp:
        root=Path(temp);state=root/'busy.rrstate';battery=root/'datas/saves/authored.rrsram'
        for mode in ('create','restore'):
            results.append(json.loads(run([exe,mode,state,battery]).strip().splitlines()[-1]))
        kind_header=(project/'retro_md_game.h').read_text()
        if '#define RR_MD_EEPROM_KIND 1\n' in kind_header:
            game_battery=root/'game/datas/saves/original.rrsram'
            original=[]
            for mode in ('gamewrite','gameread'):
                original.append(json.loads(run([exe,mode,state,game_battery]).strip().splitlines()[-1]))
            assert original[0]['original_game_writes']>0 and original[1]['original_game_writes']==0
            results+=original
    result=dict(passed=True,checks=sum(r['checks'] for r in results),busy_state_fresh_process=True,
        invalid_phase_rejected_before_mutation=True,battery_rewind=True,reset_preserves_committed=True)
    if 'original' in locals():result['original_boot_formats_once_and_reuses_save']=original
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('project',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();print(json.dumps(check(a.project.resolve(),a.output or ROOT/'.build/megadrive-eeprom-state-selftest'/a.project.name)))
