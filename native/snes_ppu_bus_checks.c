/* Original hardware-contract fixtures on the complete staged engine. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "cpu_state.h"
#include "snes/ppu.h"
#include "snes/snes.h"
extern Snes *g_snes;extern Ppu *g_ppu;
extern void rr_sn_ppu_bus_advance(Ppu *,unsigned,unsigned,unsigned);
extern uint8_t rr_sn_palette_at(Ppu *,int,int);
static unsigned checks;
#define CHECK(x) do { ++checks;if(!(x)){fprintf(stderr,"line %u: %s\n",__LINE__,#x);exit(1);} }while(0)
static void setup(unsigned v,unsigned h,bool blank) {
    rr16_reset();g_cpu.master_cycles=g_snes->beamMasterLast=100000;
    g_snes->vPos=v;g_snes->hPos=h;g_ppu->inidisp=blank?128:15;
    for(unsigned n=0;n<128;n++)g_ppu->oam[n*2]=(uint16_t)200<<8;
    g_ppu->bgmode=0;g_ppu->screenEnabled[0]=g_ppu->screenEnabled[1]=0;
}
static void color_ports(void) {
    const unsigned columns[]={86,88,90,1094,1096};
    for(unsigned over=0;over<2;over++)for(unsigned blank=0;blank<2;blank++)
    for(unsigned v=0;v<242;v++)for(unsigned c=0;c<5;c++) {
        setup(v,columns[c],blank);g_ppu->frameOverscan=over;
        g_ppu->cgram[0]=0x1234;g_ppu->cgram[35]=0x4567;
        bool active=!blank && v>0 && v<(over?240:225) && columns[c]>=88 && columns[c]<1096;
        ppu_write(g_ppu,0x21,35);ppu_write(g_ppu,0x22,0xaa);ppu_write(g_ppu,0x22,0xff);
        CHECK(g_ppu->cgram[active?0:35]==0x7faa);
        CHECK(g_ppu->cgram[active?35:0]==(active?0x4567:0x1234));
        CHECK(g_ppu->cgramPointer==36);
        ppu_write(g_ppu,0x21,35);CHECK(ppu_read(g_ppu,0x3b)==0xaa);
        CHECK(ppu_read(g_ppu,0x3b)==0xff);CHECK(g_ppu->cgramPointer==36);
    }
    setup(50,200,false);g_ppu->screenEnabled[0]=0x10;
    g_ppu->oam[0]=(49u<<8)|30;g_ppu->oam[1]=0x0200;
    for(unsigned row=0;row<8;row++){g_ppu->vram[row]=255;g_ppu->vram[row+8]=255;}
    g_ppu->cgram[35]=0x4567;
    ppu_write(g_ppu,0x21,35);ppu_write(g_ppu,0x22,0x32);ppu_write(g_ppu,0x22,0x54);
    // Palette 1 / texel 5 = 128+16+5, current beam pixel x=35.
    CHECK(g_ppu->rrBusCgram==149);CHECK(g_ppu->cgram[149]==0x5432);
    CHECK(g_ppu->cgram[35]==0x4567);
    // Live CGRAM collisions must not reuse a presentation tile row or screen
    // mask from a previous snapshot, even at the very same beam coordinate.
    setup(50,200,false);g_ppu->screenEnabled[0]=1;g_ppu->bgXsc[0]=0x60;
    g_ppu->vram[2]=0x00ff;
    CHECK(rr_sn_palette_at(g_ppu,35,50)==1);
    g_ppu->vram[2]=0xff00;
    CHECK(rr_sn_palette_at(g_ppu,35,50)==2);
    g_ppu->vram[0x6000+(50/8)*32+35/8]=3u<<10;
    CHECK(rr_sn_palette_at(g_ppu,35,50)==14);
    g_ppu->screenEnabled[0]=0;
    CHECK(rr_sn_palette_at(g_ppu,35,50)==0);
}
static void data_latches(void) {
    setup(250,0,true);g_ppu->vram[0]=0x8171;
    ppu_write(g_ppu,0x16,0);ppu_write(g_ppu,0x17,0);
    CHECK(ppu_read(g_ppu,0x39)==0x71);
    g_cpu.open_bus=0xa7;CHECK(ppu_read(g_ppu,0x04)==0x71);
    CHECK(ppu_read(g_ppu,0x37)==0xa7);CHECK(g_ppu->rrMdr1==0x71);
    ppu_write(g_ppu,0x21,0);ppu_write(g_ppu,0x22,0x80);ppu_write(g_ppu,0x22,0xff);
    CHECK(g_ppu->cgram[0]==0x7f80);
    ppu_write(g_ppu,0x21,0);CHECK(ppu_read(g_ppu,0x3b)==0x80);
    CHECK(ppu_read(g_ppu,0x3b)==0xff);
    g_ppu->hCount=0x101;g_ppu->hCountSecond=false;
    CHECK(ppu_read(g_ppu,0x3c)==1);CHECK(ppu_read(g_ppu,0x3c)==1);
    g_ppu->rrMdr2=0xfe;g_ppu->hCountSecond=true;
    CHECK(ppu_read(g_ppu,0x3c)==0xff); // only bit zero driven on second read
}
static void object_ports(void) {
    setup(50,0,false);g_ppu->oamaddh=0x80;g_ppu->oamAdr=14;
    g_ppu->oam[14]=(50u<<8)|81;g_ppu->oam[24]=(50u<<8)|93;
    rr_sn_ppu_bus_advance(g_ppu,50,0,39);CHECK(g_ppu->rrBusOam==7);
    g_ppu->oamAdr=111;g_ppu->oamSecondWrite=false;
    CHECK(ppu_read(g_ppu,0x38)==81);CHECK(ppu_read(g_ppu,0x38)==50);
    CHECK(g_ppu->oamAdr==112);
    rr_sn_ppu_bus_advance(g_ppu,50,39,40);CHECK(g_ppu->rrBusOam==12);
    g_ppu->oamAdr=111;g_ppu->oamSecondWrite=false;
    ppu_write(g_ppu,4,0x42);ppu_write(g_ppu,4,0x39);
    CHECK(g_ppu->oam[24]==0x3942);CHECK(g_ppu->oam[111]==0);
    g_ppu->oamInHigh=true;g_ppu->oamAdr=14;g_ppu->oamSecondWrite=false;
    ppu_write(g_ppu,4,0xd1);CHECK(g_ppu->highOam[3]==0xd1);
    CHECK(g_ppu->highOam[28]==0);
    // The 33rd slot is detected early, but overflow status waits for fetching.
    setup(50,0,false);for(unsigned n=0;n<40;n++)g_ppu->oam[n*2]=(50u<<8)|30;
    rr_sn_ppu_bus_advance(g_ppu,50,0,1018);
    CHECK(g_ppu->rrOamCount==33);CHECK(g_ppu->rrBusOam==32);CHECK(!g_ppu->rangeOver);
    rr_sn_ppu_bus_advance(g_ppu,50,1018,1335);CHECK(!g_ppu->rangeOver);
    rr_sn_ppu_bus_advance(g_ppu,50,1335,1336);CHECK(g_ppu->rangeOver);CHECK(!g_ppu->timeOver);
    setup(50,0,false);for(unsigned n=0;n<33;n++)g_ppu->oam[n*2]=(50u<<8)|30;
    memset(g_ppu->highOam,0xaa,sizeof g_ppu->highOam); // 16-pixel big sprites
    rr_sn_ppu_bus_advance(g_ppu,50,0,1351);CHECK(!g_ppu->rangeOver && !g_ppu->timeOver);
    rr_sn_ppu_bus_advance(g_ppu,50,1351,1352);CHECK(g_ppu->rangeOver && g_ppu->timeOver);
    // HBlank walks accepted sprites in reverse for tile fetches.
    setup(50,0,false);g_ppu->oam[14]=(50u<<8)|30;g_ppu->oam[24]=(50u<<8)|90;
    rr_sn_ppu_bus_advance(g_ppu,50,0,1080);CHECK(g_ppu->rrBusOam==12);
    rr_sn_ppu_bus_advance(g_ppu,50,1080,1088);CHECK(g_ppu->rrBusOam==7);
    for(unsigned bank=0;bank<2;bank++)for(unsigned blank=0;blank<2;blank++) {
        setup(250,100,blank);g_ppu->oamInHigh=bank;g_ppu->oamAdr=14;
        ppu_write(g_ppu,4,0x44);ppu_write(g_ppu,4,0x55);
        CHECK(bank ? g_ppu->highOam[28]==0x44 && g_ppu->highOam[29]==0x55 : g_ppu->oam[14]==0x5544);
    }
}
static void object_progress(void) {
    // Masking the display consumes evaluation slots; unmasking does not replay
    // the sprites whose eight-clock slots have already passed.
    setup(50,0,true);for(unsigned n=0;n<8;n++)g_ppu->oam[n*2]=(50u<<8)|30;
    rr_sn_ppu_bus_advance(g_ppu,50,0,39);CHECK(g_ppu->rrOamCount==0);
    g_ppu->inidisp=15;rr_sn_ppu_bus_advance(g_ppu,50,39,40);
    CHECK(g_ppu->rrOamCount==1);CHECK(g_ppu->rrOamItems[0]==5);
    // A width change after the first fetch half must not lengthen that object
    // retroactively. The next object sees the new width when its turn starts.
    setup(50,0,false);g_ppu->oam[0]=g_ppu->oam[2]=(50u<<8)|30;
    memset(g_ppu->highOam,0xaa,sizeof g_ppu->highOam);
    rr_sn_ppu_bus_advance(g_ppu,50,0,1084);CHECK(g_ppu->rrBusOam==1);
    g_ppu->obsel=5u<<5;
    rr_sn_ppu_bus_advance(g_ppu,50,1084,1095);CHECK(g_ppu->rrBusOam==1);
    rr_sn_ppu_bus_advance(g_ppu,50,1095,1096);CHECK(g_ppu->rrBusOam==0);
    // A masked outer fetch slot costs eight clocks and stays skipped. Changing
    // the display mask halfway through that slot must not bring it back.
    setup(50,0,false);for(unsigned n=0;n<3;n++)g_ppu->oam[n*2]=(50u<<8)|30;
    rr_sn_ppu_bus_advance(g_ppu,50,0,1079);g_ppu->inidisp=128;
    rr_sn_ppu_bus_advance(g_ppu,50,1079,1084);g_ppu->inidisp=15;
    rr_sn_ppu_bus_advance(g_ppu,50,1084,1087);CHECK(g_ppu->rrBusOam==2);
    rr_sn_ppu_bus_advance(g_ppu,50,1087,1088);CHECK(g_ppu->rrBusOam==1);
    // Every sub-slot unblanking position has the same non-retroactive result.
    for(unsigned end=0;end<1024;end++) {
        setup(50,0,true);for(unsigned n=0;n<128;n++)g_ppu->oam[n*2]=(50u<<8)|30;
        rr_sn_ppu_bus_advance(g_ppu,50,0,end);g_ppu->inidisp=15;
        unsigned next=(end/8+1)*8;
        rr_sn_ppu_bus_advance(g_ppu,50,end,next);
        CHECK(g_ppu->rrOamCount==(next<1024?1:0));
        if(next<1024)CHECK(g_ppu->rrOamItems[0]==next/8);
    }
    // The live cursor survives the same architectural-state copy used by
    // quick states, and batching beam spans does not change the end result.
    static Ppu saved,complete;
    setup(50,0,false);for(unsigned n=0;n<40;n++)g_ppu->oam[n*2]=(50u<<8)|30;
    rr_sn_ppu_bus_advance(g_ppu,50,0,1084);memcpy(&saved,g_ppu,sizeof saved);
    rr_sn_ppu_bus_advance(g_ppu,50,1084,1360);memcpy(&complete,g_ppu,sizeof complete);
    memcpy(g_ppu,&saved,sizeof saved);
    for(unsigned h=1085;h<=1360;h++)rr_sn_ppu_bus_advance(g_ppu,50,h-1,h);
    CHECK(!memcmp(g_ppu,&complete,sizeof complete));
}
int main(void) {CHECK(rr16_init(true));color_ports();data_latches();object_ports();object_progress();
    printf("{\"checks\":%u,\"passed\":true}\n",checks);rr16_shutdown();return 0;}
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){return main();}
