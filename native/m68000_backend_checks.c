/* Authored CPU/bus boundary checks, no ROM or copied cartridge data. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "m68000_backend.h"
#include "m68000_state_helpers.h"
#include "neogeo_input.h"
static unsigned checks;
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"FAIL %s\n",#x);return 1;}}while(0)
static uint32_t addresses[3];static uint16_t values[3];static unsigned writes;
static void write16(uint32_t address,uint16_t value) { addresses[writes]=address;values[writes++]=value; }
static unsigned resets,waits,irq[8];
static void init(void *p) { (void)p; }
static void reset(void *p) { (void)p;++resets; }
static int run(void *p,unsigned clocks) { (void)p;rr_m68000_count_instruction(0);return clocks+4; }
static void wait(void *p,int clocks) { (void)p;waits+=clocks; }
static void set_irq(void *p,unsigned level,unsigned value) { (void)p;irq[level]=value; }
static unsigned get_irq(void *p,unsigned level) { (void)p;return irq[level]; }
static void put32(uint8_t *p,uint32_t v) { for(unsigned n=0;n<4;++n)p[n]=(uint8_t)(v>>(n*8)); }
int main(void) {
    uint16_t sr=0x0000;uint32_t a7=0x10f000,inactive=0x10ff00;
    CHECK(rr_m68000_user_sp(sr,a7,inactive)==0x10f000);
    CHECK(rr_m68000_supervisor_sp(sr,a7,inactive)==0x10ff00);
    rr_m68000_select_sr(&sr,&a7,&inactive,0x2700);
    CHECK(sr==0x2700 && a7==0x10ff00 && inactive==0x10f000);
    rr_m68000_push_normal_frame(&a7,0x0015,0xc01234,write16);
    CHECK(a7==0x10fefa && writes==3);
    CHECK(addresses[0]==0x10fefe && values[0]==0x1234);
    CHECK(addresses[1]==0x10fefa && values[1]==0x0015);
    CHECK(addresses[2]==0x10fefc && values[2]==0x00c0);
    rr_m68000_select_sr(&sr,&a7,&inactive,0xffff);
    CHECK(sr==0xa71f && a7==0x10fefa);
    rr_m68000_select_sr(&sr,&a7,&inactive,0x0015);
    CHECK(sr==0x15 && a7==0x10f000 && inactive==0x10fefa);
    const RrM68000Backend backend={NULL,init,reset,run,wait,set_irq,get_irq};
    CHECK(!rr_m68000_bind(NULL));CHECK(rr_m68000_bind(&backend));
    rr_m68000_init();rr_m68000_reset();CHECK(resets==1);
    CHECK(rr_m68000_run(1)==5);rr_m68000_wait(2);CHECK(waits==2);
    rr_m68000_set_irq(2,1);CHECK(rr_m68000_get_irq(2)==1);
    rr_m68000_set_irq(2,0);CHECK(rr_m68000_get_irq(2)==0);
    rr_m68000_set_irq(8,1);CHECK(rr_m68000_get_irq(8)==0);
    CHECK(rr_m68000_stats()->native_instructions==0);
    CHECK(rr_m68000_stats()->interpreted_instructions==1 && rr_m68000_stats()->clocks==5);
    CHECK(rr_m68000_stats()->bus_wait_clocks==2 && rr_m68000_stats()->resets==1);
    size_t size=4096+512+131072+65536+128;
    uint8_t *data=calloc(1,size);CHECK(data!=NULL);
    memcpy(data,"NEO\1",4);put32(data+4,512);put32(data+8,131072);
    put32(data+12,65536);put32(data+24,128);
    CHECK(rr_ng_container_valid(data,size));
    CHECK(!rr_ng_container_valid(data,size-1));CHECK(!rr_ng_container_valid(data,size+1));
    data[3]=2;CHECK(!rr_ng_container_valid(data,size));data[3]=1;
    put32(data+4,0xffffffff);CHECK(!rr_ng_container_valid(data,size));
    free(data);printf("{\"checks\":%u,\"passed\":true,\"authored\":true}\n",checks);return 0;
}
