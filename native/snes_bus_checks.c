#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "snes_bus.h"
#include "snes/ppu.h"
#include "snes/apu.h"
#include "snes/spc.h"
extern Ppu *g_ppu;extern uint8_t g_ram[0x20000];
static unsigned checks;
#define CHECK(x) do { ++checks;if(!(x)){fprintf(stderr,"line %u: %s\n",__LINE__,#x);exit(1);} }while(0)
static void setup(unsigned h) {
    rr16_reset();g_snes->vPos=50;g_snes->hPos=h;
    g_cpu.master_cycles=g_snes->beamMasterLast=50*1364u+h;
    g_snes->apu->spc->stopped=true;snes_set_hdma_beam_enabled(g_snes,false);
    g_ppu->inidisp=128;g_memsel=0;
}
static void phases(void) {
    for(unsigned clocks=6;clocks<=12;clocks+=2) {
        if(clocks==10)continue;
        setup(20);uint32_t addr=clocks==6 ? 0x002100u : clocks==8 ? 0x7e0000u : 0x004016u;
        uint64_t t=g_cpu.master_cycles;rr_snes_cpu_context(true);
        rr_snes_cpu_read_begin(addr);CHECK(g_cpu.master_cycles==t+clocks-4);
        rr_snes_cpu_read_end();CHECK(g_cpu.master_cycles==t+clocks);
        rr_snes_cpu_write_begin(addr);CHECK(g_cpu.master_cycles==t+clocks*2);
        CHECK(g_snes->beamMasterLast==g_cpu.master_cycles);rr_snes_cpu_context(false);
    }
    setup(534);uint64_t t=g_cpu.master_cycles;rr_snes_cpu_context(true);
    rr_snes_cpu_read_begin(0x7e0000);CHECK(g_cpu.master_cycles==t+44);
    rr_snes_cpu_read_end();CHECK(g_cpu.master_cycles==t+48);
    CHECK(g_snes->dma->rrRefreshEpoch==1);CHECK(g_snes->hPos==582);
    // A second access on the same raster line does not refresh twice.
    rr_snes_cpu_read_begin(0x7e0000);rr_snes_cpu_read_end();CHECK(g_cpu.master_cycles==t+56);
    rr_snes_cpu_context(false);
    for(unsigned phase=0;phase<8;phase+=2)for(unsigned next=6;next<=8;next+=2) {
        setup(20);g_cpu.master_cycles=g_snes->beamMasterLast=100000+phase;
        DmaChannel *ch=&g_snes->dma->channel[0];memset(ch,0,sizeof *ch);
        ch->aBank=0x7e;ch->aAdr=0x4000;ch->size=2;ch->bAdr=0x40;
        rr_snes_cpu_context(true);rr_snes_cpu_write_begin(0x420b);
        snes_write(g_snes,0x420b,1);CHECK(ch->size==2);
        rr_snes_cpu_read_begin(0x008000);rr_snes_cpu_read_end();CHECK(ch->size==2);
        uint64_t before=g_cpu.master_cycles;
        unsigned alignment=8-(before&7),dma_clocks=alignment+32;
        unsigned release=next-(dma_clocks%next);
        g_memsel=next==6;rr_snes_cpu_read_begin(next==6?0x808000u:0x008000u);rr_snes_cpu_read_end();
        CHECK(ch->size==0);CHECK(g_cpu.master_cycles==before+dma_clocks+release+next);
        CHECK(g_snes->beamMasterLast==g_cpu.master_cycles);
        CHECK(!g_snes->dma->rrDmaRequest && !g_snes->dma->rrBusArmed);
        rr_snes_cpu_context(false);
    }
}
static void interrupt_entry(void) {
    for(unsigned emu=0;emu<2;emu++) {
        setup(20);g_cpu.S=emu ? 0x100:0x1fff;g_cpu.emulation=emu;
        g_cpu._flag_I=0;g_cpu._flag_D=1;g_cpu.PB=0x81;cpu_mirrors_to_p(&g_cpu);uint8_t p=g_cpu.P;
        uint64_t before=g_cpu.master_cycles;
        CHECK(rr_snes_cpu_interrupt(0x818034,emu?0xfffe:0xffee)==0xf000);
        CHECK(g_cpu.master_cycles==before+(emu?54:62));
        CHECK(g_cpu._flag_I && !g_cpu._flag_D && g_cpu.PB==0);
        if(emu){CHECK(g_cpu.S==0x1fd);CHECK(g_ram[0x100]==0x80);CHECK(g_ram[0x1ff]==0x34);CHECK(g_ram[0x1fe]==(p&~16u));}
        else {CHECK(g_cpu.S==0x1ffb);CHECK(g_ram[0x1fff]==0x81);CHECK(g_ram[0x1ffe]==0x80);
              CHECK(g_ram[0x1ffd]==0x34);CHECK(g_ram[0x1ffc]==p);}
    }
}
static void cpu_register_latches(void) {
    setup(20);
    for(unsigned mdr=0;mdr<256;mdr++) {
        g_cpu.open_bus=(uint8_t)mdr;g_snes->inNmi=true;g_snes->rdnmiPending=true;
        CHECK(snes_readReg(g_snes,0x4210)==(0x82u|(mdr&0x70u)));
        CHECK(snes_readReg(g_snes,0x4210)==(2u|(mdr&0x70u)));
        g_snes->inIrq=true;
        CHECK(snes_readReg(g_snes,0x4211)==(0x80u|(mdr&0x7fu)));
        CHECK(snes_readReg(g_snes,0x4211)==(mdr&0x7fu));
        g_snes->hPos=20;g_snes->vPos=50;
        g_snes->autoJoyTimer=1000;
        CHECK(snes_readReg(g_snes,0x4212)==(1u|(mdr&0x3eu)));
        // Reads of the CPU's internal data bus do not replace CPU MDR.
        CHECK(g_cpu.open_bus==mdr);
    }
}
static void cartridge_bus_holes(void) {
    setup(20);int original=g_snes->cart->type;
    extern bool g_fail;
    for(unsigned type=0;type<2;type++) {
        g_snes->cart->type=type?CART_HIROM:CART_LOROM;
        for(unsigned mdr=0;mdr<256;mdr++)for(unsigned n=0;n<4;n++) {
            uint8_t bank=(uint8_t[]){0,0x30,0x80,0xb0}[n];
            g_cpu.open_bus=(uint8_t)mdr;g_fail=false;
            CHECK(cpu_read8(&g_cpu,bank,0x6002)==mdr);CHECK(!g_fail);
            CHECK(cpu_read16(&g_cpu,bank,0x6002)==(mdr*257u));CHECK(!g_fail);
        }
    }
    g_snes->cart->type=original;
    // A word at the end of $7F wraps inside that bank; a ROM word crosses
    // $FFFF into the WRAM mirror, never into a contiguous host-ROM pointer.
    g_ram[0x1ffff]=0x34;g_ram[0x10000]=0x12;
    CHECK(cpu_read16(&g_cpu,0x7f,0xffff)==0x1234);
    g_ram[0]=0x67;uint8_t lo=cpu_read8(&g_cpu,0,0xffff);
    CHECK(cpu_read16(&g_cpu,0,0xffff)==((unsigned)0x67<<8|lo));
}
int main(void) {
    CHECK(rr16_init(true));phases();interrupt_entry();cpu_register_latches();cartridge_bus_holes();rr16_reset();
    for(unsigned n=0;n<4;n++)CHECK(rr16_frame(0,0));
    printf("{\"checks\":%u,\"passed\":true,\"main_fallback\":%llu,\"guest\":\"",checks,
        (unsigned long long)rr16_interpreted());
    for(unsigned n=0;n<16;n++)printf("%02x",g_ram[0x1000+n]);
    printf("\"}\n");rr16_shutdown();return 0;
}
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){return main();}
