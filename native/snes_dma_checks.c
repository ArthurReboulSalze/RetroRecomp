/* Authored bus/VRAM expectations, independent of opcode selection. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "cpu_state.h"
#include "snes/ppu.h"
#include "snes/apu.h"
#include "snes/spc.h"
#include "snes_dma.h"
#include "beam_frame_driver.h"
extern Snes *g_snes;
extern Ppu *g_ppu;
extern uint8_t g_ram[0x20000];
static unsigned checks,logged;
static uint64_t clock_log[65536];
#define CHECK(x) do { ++checks;if(!(x)){fprintf(stderr,"line %u: %s\n",__LINE__,#x);exit(1);} }while(0)
static void log_write(uint32_t adr,uint8_t value){if(logged<65536)clock_log[logged]=g_cpu.master_cycles;logged++;}
static void setup(unsigned line,unsigned column){
    rr16_reset();g_cpu.master_cycles=100000;g_snes->beamMasterLast=100000;
    g_snes->vPos=line;g_snes->hPos=column;g_snes->hIrqEnabled=false;g_snes->vIrqEnabled=false;
    snes_set_hdma_beam_enabled(g_snes,false);ppu_write(g_ppu,0,0x80);
    g_snes->apu->spc->stopped=true;logged=0;
}
static DmaChannel *channel(unsigned mode,unsigned length,unsigned bank,unsigned adr,unsigned b,bool reverse){
    DmaChannel *ch=&g_snes->dma->channel[0];memset(ch,0,sizeof *ch);
    ch->mode=mode;ch->size=length;ch->aBank=bank;ch->aAdr=adr;ch->bAdr=b;ch->fromB=reverse;return ch;
}
static void bus_exclusions(void){
    const unsigned adr[]={0x1fff,0x2100,0x21ff,0x2200,0x4000,0x41ff,0x4200,0x421f,0x4220,0x4300,0x437f,0x4380,0x6000,0xffff};
    for(unsigned bank=0;bank<256;bank++)for(unsigned n=0;n<14;n++){
        bool io=(bank&127)<64;
        bool bad=io && ((adr[n]>=0x2100 && adr[n]<=0x21ff) ||
            (adr[n]>=0x4000 && adr[n]<=0x421f) || (adr[n]>=0x4300 && adr[n]<=0x437f));
        CHECK(rr_snes_dma_valid_a((bank<<16)|adr[n])==!bad);
        bool wram=bank==126 || bank==127 || (io && adr[n]<0x2000);
        CHECK(rr_snes_dma_valid_b((bank<<16)|adr[n],0x80)==!wram);
        CHECK(rr_snes_dma_valid_b((bank<<16)|adr[n],0x18));
    }
    setup(225,0);g_snes->rdnmiPending=true;g_ram[0x4000]=0xcc;
    channel(0,1,0x00,0x4210,0x80,false);g_snes->ramAdr=0x4000;
    snes_write(g_snes,0x420b,1);CHECK(g_snes->rdnmiPending);CHECK(g_ram[0x4000]==0);
    CHECK(g_cpu.open_bus==0);
    setup(225,0);g_snes->ramAdr=0x5000;g_ram[0x5000]=0xbb;g_ram[0x4000]=0xaa;
    channel(0,1,0x7e,0x4000,0x80,false);snes_write(g_snes,0x420b,1);
    CHECK(g_snes->ramAdr==0x5000);CHECK(g_ram[0x5000]==0xbb);
    setup(225,0);g_snes->ramAdr=0x5000;g_ram[0x5000]=0xbb;
    channel(0,1,0x7e,0x4000,0x80,true);snes_write(g_snes,0x420b,1);
    CHECK(g_snes->ramAdr==0x5000);CHECK(g_ram[0x4000]==0);
    setup(225,0);g_snes->ramAdr=0x5000;g_ram[0x5000]=0xbb;
    channel(0,1,0,0x420b,0x80,true);snes_write(g_snes,0x420b,1);
    CHECK(!g_snes->dma->dmaBusy);CHECK(g_snes->ramAdr==0x5001); // no recursive DMA write
}
static void modes(void){
    const unsigned off[8][4]={{0,0,0,0},{0,1,0,1},{0,0,0,0},{0,0,1,1},
        {0,1,2,3},{0,1,0,1},{0,0,0,0},{0,0,1,1}};
    for(unsigned mode=0;mode<8;mode++)for(unsigned pattern=0;pattern<3;pattern++){
        setup(225,0);for(unsigned p=0;p<4;p++)g_snes->apu->outPorts[p]=0x90+p;
        DmaChannel *ch=channel(mode,8,0x7e,0x4000,0x40,true);
        ch->fixed=pattern==1;ch->decrement=pattern==2;
        snes_write(g_snes,0x420b,1);CHECK(g_cpu.master_cycles==100000+12+8+64);
        for(unsigned p=0;p<8;p++){
            unsigned a=pattern==1?0x4000:pattern==2?0x4000-p:0x4000+p;
            if(pattern!=1 || p==7)CHECK(g_ram[a]==0x90+off[mode][p%4]);
        }
        CHECK(ch->size==0);CHECK(ch->aAdr==(pattern==1?0x4000:pattern==2?0x3ff8:0x4008));
    }
}
static void phases(void){
    setup(225,0);ppu_set_vram_write_log_hook(log_write);
    for(unsigned p=0;p<12;p++)g_ram[0x4000+p]=p+1;
    channel(1,12,0x7e,0x4000,0x18,false);snes_write(g_snes,0x420b,1);
    CHECK(logged==12);for(unsigned p=0;p<12;p++)CHECK(clock_log[p]==100000+28+8*p);
    CHECK(g_snes->beamMasterLast==g_cpu.master_cycles);
    CHECK(g_cpu.open_bus==12);
    // Cross the real vblank edge inside a DMA: only accesses after it succeed.
    setup(224,1330);g_ppu->inidisp=15;g_ppu->vramPointer=0;g_ppu->vramIncrement=1;
    g_ppu->vramIncrementOnHigh=true;memset(g_ppu->vram,0,sizeof g_ppu->vram);
    for(unsigned p=0;p<8;p++)g_ram[0x4000+p]=p+1;
    channel(1,8,0x7e,0x4000,0x18,false);snes_write(g_snes,0x420b,1);
    CHECK(logged==7);CHECK(g_ppu->vram[0]==0x0200);CHECK(g_ppu->vram[1]==0x0403);
    // An IRQ may latch during DMA but cannot freeze its following bus phases.
    setup(225,0);g_snes->hIrqEnabled=true;g_snes->hTimer=10;
    channel(1,8,0x7e,0x4000,0x18,false);snes_write(g_snes,0x420b,1);
    CHECK(g_snes->inIrq);CHECK(logged==8);CHECK(g_snes->hPos==84);
    CHECK(g_snes->beamMasterLast==g_cpu.master_cycles);
    // Bank wraps, and a zero byte count means 65536 bytes.
    setup(225,0);channel(0,0,0x7e,0xfffe,0x18,false);
    snes_write(g_snes,0x420b,1);CHECK(logged==65536);
    // CPU v2 refresh: phase-0 line at H538, next line (phase 4) at H534.
    // Physical periods remain 1364 clocks; each encountered hold costs 40.
    uint64_t expected=20+65536*8;
    for(unsigned n=0;n<8;n++) {
        uint64_t holds=(expected>=538 ? 1+(expected-538)/2728 : 0)+
                       (expected>=1898 ? 1+(expected-1898)/2728 : 0);
        uint64_t next=20+65536*8+40*holds;
        if(next==expected)break;expected=next;
    }
    CHECK(g_cpu.master_cycles==100000+expected);CHECK(g_snes->dma->channel[0].aAdr==0xfffe);
    ppu_set_vram_write_log_hook(NULL);
}
static void vram_ports(void){
    for(unsigned overscan=0;overscan<2;overscan++)for(unsigned blank=0;blank<2;blank++)
    for(unsigned high=0;high<2;high++)for(unsigned line=0;line<242;line++){
        setup(line,100);g_ppu->inidisp=blank?0x80:15;g_ppu->frameOverscan=overscan;
        g_ppu->vram[0]=0x1234;g_ppu->vram[1]=0x5678;g_ppu->vramIncrementOnHigh=high;
        ppu_write(g_ppu,0x16,0);ppu_write(g_ppu,0x17,0);
        bool allowed=blank || line>=(overscan?240:225);
        CHECK(g_ppu->vramReadBuffer==(allowed?0x1234:0));
        ppu_write(g_ppu,0x18,0xaa);ppu_write(g_ppu,0x19,0xbb);
        CHECK(g_ppu->vram[0]==(allowed?(high?0xbbaa:0x12aa):0x1234));
        CHECK(g_ppu->vramPointer==1);
        ppu_write(g_ppu,0x16,0);ppu_write(g_ppu,0x17,0);
        CHECK(ppu_read(g_ppu,0x39)==(allowed?0xaa:0));
    }
}
static void hdma_direction(void){
    const unsigned len[8]={1,2,2,4,4,4,2,4};
    const unsigned off[8][4]={{0,0,0,0},{0,1,0,1},{0,0,0,0},{0,0,1,1},
        {0,1,2,3},{0,1,0,1},{0,0,0,0},{0,0,1,1}};
    for(unsigned mode=0;mode<8;mode++)for(unsigned indirect=0;indirect<2;indirect++){
        setup(225,0);for(unsigned p=0;p<4;p++)g_snes->apu->outPorts[p]=0x90+p;
        DmaChannel *ch=channel(mode,0,0x7e,0x4000,0x40,true);ch->indirect=indirect;ch->indBank=0x7e;
        g_ram[0x4000]=0x81;
        if(indirect){g_ram[0x4001]=0;g_ram[0x4002]=0x50;g_ram[0x4003]=0;}
        else g_ram[0x4001+len[mode]]=0;
        dma_startDma(g_snes->dma,1,true);dma_initHdma(g_snes->dma);dma_doHdma(g_snes->dma);
        for(unsigned p=0;p<len[mode];p++)CHECK(g_ram[(indirect?0x5000:0x4001)+p]==0x90+off[mode][p]);
        CHECK(ch->terminated);CHECK(g_cpu.master_cycles==100000); // replay owns no guest clocks
    }
}
static void hdma_first_line(void){
    /* Independent authored brightness cartridge under Snes9x: visible rows
     * are black/white/black/white/black/white, then remain white. */
    for(unsigned indirect=0;indirect<2;indirect++) {
        setup(225,0);DmaChannel *ch=channel(0,0,0x7e,0x4000,0,false);
        ch->indirect=indirect;ch->indBank=0x7e;
        for(unsigned row=0;row<6;row++) {
            unsigned table=0x4000+row*(indirect?3:2);
            g_ram[table]=0x81;
            if(indirect) {
                g_ram[table+1]=(uint8_t)row;g_ram[table+2]=0x50;
                g_ram[0x5000+row]=row&1 ? 15:0;
            } else g_ram[table+1]=row&1 ? 15:0;
        }
        g_ram[0x4000+6*(indirect?3:2)]=0;
        dma_startDma(g_snes->dma,1,true);dma_initHdma(g_snes->dma);
        dma_primeHdmaFirstLine(g_snes->dma);
        CHECK(g_ppu->inidisp==0);
        for(unsigned row=1;row<12;row++) {
            dma_doHdma(g_snes->dma);
            CHECK(g_ppu->inidisp==(row<6 ? (row&1 ? 15:0) : 15));
        }
        CHECK(ch->terminated);CHECK(ch->tableAdr==0x4000+6*(indirect?3:2)+(indirect?2:1));
        CHECK(g_cpu.master_cycles==100000); // replay must not charge CPU a second time
    }
}
static void arbitration(void){
    for(unsigned dma_index=0;dma_index<8;dma_index++)for(unsigned same=0;same<2;same++) {
        setup(10,1080);ppu_set_vram_write_log_hook(log_write);
        snes_set_hdma_beam_enabled(g_snes,true);
        unsigned h=same ? dma_index : (dma_index+1)&7;
        DmaChannel *active=&g_snes->dma->channel[dma_index];memset(active,0,sizeof *active);
        active->aBank=0x7e;active->aAdr=0x6000;active->bAdr=0x18;active->size=8;
        for(unsigned n=0;n<8;n++)g_ram[0x6000+n]=n+1;
        DmaChannel *hdma=&g_snes->dma->channel[h];
        if(!same)memset(hdma,0,sizeof *hdma);
        // A same-channel HDMA shares the source/bank/target but uses A2A.
        hdma->hdmaActive=true;hdma->tableAdr=0x4001;
        hdma->repCount=0x81;hdma->doTransfer=true;hdma->terminated=false;
        if(!same){hdma->aBank=0x7e;hdma->bAdr=0;}
        g_ram[0x4001]=same ? 0xee : 0x80;g_ram[0x4002]=0;
        snes_write(g_snes,0x420b,(uint8_t)(1u<<dma_index));
        CHECK(g_snes->dma->rrHdmaEpoch==1);CHECK(hdma->terminated);
        CHECK(g_snes->beamMasterLast==g_cpu.master_cycles);
        CHECK(!g_snes->dma->dmaBusy && !active->dmaActive);
        CHECK(active->aAdr==(same ? 0x6001 : 0x6008));
        CHECK(active->size==(same ? 7 : 0));
        CHECK(g_cpu.master_cycles==100000+(same ? 52 : 108));
        CHECK(logged==(same ? 2 : 8));
        CHECK(clock_log[0]==100028);
        if(same)CHECK(clock_log[1]==100044);
        else CHECK(clock_log[1]==100060); // DMA resumes after HDMA stall
        CHECK(g_snes->dma->rrHdmaRequest==0);
    }
    // Field setup is a real CPU stall even when the CPU is parked in WAI.
    for(unsigned indirect=0;indirect<2;indirect++) {
        setup(0,0);snes_set_hdma_beam_enabled(g_snes,true);
        DmaChannel *ch=channel(0,0,0x7e,0x4000,0,false);
        ch->indirect=indirect;g_ram[0x4000]=0x82;
        g_ram[0x4001]=0;g_ram[0x4002]=0x50;
        dma_startDma(g_snes->dma,1,true);
        g_cpu.master_cycles+=20;snes_sync_master_clock(g_snes,g_cpu.master_cycles);
        CHECK(g_cpu.master_cycles==100000+36+indirect*16);
        CHECK(g_snes->beamMasterLast==g_cpu.master_cycles);
        CHECK(ch->tableAdr==0x4001+indirect*2);CHECK(ch->repCount==0x82);
        CHECK(!g_snes->dma->hdmaPendingInit);CHECK(g_snes->dma->rrHdmaEpoch==1);
    }
    // A non-reloading row still reads the table bus but does not move A2A.
    setup(20,1100);snes_set_hdma_beam_enabled(g_snes,true);
    DmaChannel *ch=channel(0,0,0x7e,0x4000,0,false);
    ch->hdmaActive=true;ch->tableAdr=0x4100;ch->repCount=3;
    g_ram[0x4100]=0xa6;g_cpu.master_cycles+=12;
    snes_sync_master_clock(g_snes,g_cpu.master_cycles);
    CHECK(g_cpu.master_cycles==100028);CHECK(ch->tableAdr==0x4100);
    CHECK(ch->repCount==2);CHECK(g_cpu.open_bus==0xa6);
    CHECK(g_snes->beamMasterLast==100028);
    // No HDMA transfer or stall in vblank, even with an enabled channel.
    setup(250,1100);snes_set_hdma_beam_enabled(g_snes,true);
    ch=channel(0,0,0x7e,0x4000,0,false);ch->hdmaActive=true;
    g_cpu.master_cycles+=100;snes_sync_master_clock(g_snes,g_cpu.master_cycles);
    CHECK(g_cpu.master_cycles==100100);CHECK(!g_snes->dma->rrHdmaEpoch);
    // Disabled channels do not steal time or masquerade as an IRQ yield.
    setup(0,0);snes_set_hdma_beam_enabled(g_snes,true);
    g_cpu.master_cycles+=5000;snes_sync_master_clock(g_snes,g_cpu.master_cycles);
    CHECK(g_cpu.master_cycles==105000);CHECK(g_snes->beamMasterLast==105000);
    CHECK(g_snes->vPos==3 && g_snes->hPos==908);
    CHECK(g_snes->dma->rrHdmaEpoch==4);
}
static void render_is_read_only(void){
    rr16_reset();for(unsigned n=0;n<3;n++)CHECK(rr16_frame(0,0));
    uint8_t regs[PPU_SAVESTATE_REGS_SIZE],mem[PPU_SAVESTATE_MEM_SIZE];
    uint8_t ports[offsetof(Ppu,timeOver)-offsetof(Ppu,vramPointer)],ram[0x20000];
    DmaChannel channels[8];
    memcpy(regs,&g_ppu->inidisp,sizeof regs);memcpy(mem,&g_ppu->cgram,sizeof mem);
    memcpy(ports,&g_ppu->vramPointer,sizeof ports);memcpy(ram,g_ram,sizeof ram);
    memcpy(channels,g_snes->dma->channel,sizeof channels);
    uint64_t cycles=g_cpu.master_cycles;uint32_t epoch=g_snes->dma->rrHdmaEpoch;
    for(unsigned n=0;n<2;n++) {
        snes_beam_frame_driver_draw_ppu_frame();
        CHECK(!memcmp(regs,&g_ppu->inidisp,sizeof regs));
        CHECK(!memcmp(mem,&g_ppu->cgram,sizeof mem));
        CHECK(!memcmp(ports,&g_ppu->vramPointer,sizeof ports));
        CHECK(!memcmp(ram,g_ram,sizeof ram));
        CHECK(!memcmp(channels,g_snes->dma->channel,sizeof channels));
        CHECK(g_cpu.master_cycles==cycles);CHECK(g_snes->dma->rrHdmaEpoch==epoch);
    }
}
int main(void){CHECK(rr16_init(true));bus_exclusions();modes();phases();vram_ports();hdma_direction();hdma_first_line();arbitration();render_is_read_only();
    printf("{\"checks\":%u,\"passed\":true}\n",checks);rr16_shutdown();return 0;}
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){return main();}
