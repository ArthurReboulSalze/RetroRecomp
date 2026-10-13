/* Original deterministic PPU and APU-port expectations. No commercial ROM. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include "retro_console16.h"
#include "console16_video.h"
#include "common_rtl.h"
#include "snes/ppu.h"
#include "snes/snes.h"
#include "audio_trace.h"
static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)){fprintf(stderr,"line %u: %s\n",__LINE__,#x);exit(1);} } while(0)
static struct { uint32_t before,image[512*480],after; } buffer;
static void setup(int mode,int pseudo,int interlace,int parity) {
    ppu_reset(g_ppu);memset(buffer.image,0,sizeof buffer.image);
    buffer.before=0x12345678;buffer.after=0x87654321;
    g_ppu->inidisp=15;g_ppu->bgmode=mode;g_ppu->setini=(pseudo?8:0)|(interlace?1:0);
    g_ppu->frameInterlace=interlace;g_ppu->evenFrame=parity;
    g_ppu->bgTileAdr=0x21;g_ppu->bgXsc[0]=0x60;g_ppu->bgXsc[1]=0x68;
    g_ppu->screenEnabled[0]=1;g_ppu->screenEnabled[1]=(mode==5||mode==6)?1:2;
    g_ppu->cgram[1]=31;g_ppu->cgram[2]=31<<5;g_ppu->cgram[33]=31<<5;
    for(unsigned i=0;i<1024;i++){g_ppu->vram[0x6000+i]=1;g_ppu->vram[0x6800+i]=1;}
    for(unsigned row=0;row<8;row++){
        unsigned depth=mode==0?8:(mode==3||mode==4)?32:16;
        g_ppu->vram[0x1000+depth+row]=(mode==5||mode==6)?0x55aa:0x00ff;
        g_ppu->vram[0x1000+depth*2+row]=0x55aa;
        g_ppu->vram[0x2000+8+row]=0xff;
    }
    PpuBeginDrawing(g_ppu,(uint8_t*)buffer.image,512*4,0x80000000u);
}
static void rectangular_objects(void) {
    for(unsigned mode=6;mode<8;mode++)for(unsigned big=0;big<2;big++)
    for(unsigned flip=0;flip<2;flip++) {
        setup(1,0,0,1);g_ppu->obsel=mode<<5;
        g_ppu->screenEnabled[0]=16;g_ppu->screenEnabled[1]=0;
        for(unsigned n=0;n<128;n++)g_ppu->oam[n*2]=240u<<8;
        g_ppu->oam[0]=(32u<<8)|32;g_ppu->oam[1]=flip?0x8000:0;
        g_ppu->highOam[0]=big?2:0;
        g_ppu->cgram[129]=31;g_ppu->cgram[130]=31<<5;
        // Alternate solid red/green tile rows. Fill all horizontal columns.
        for(unsigned ty=0;ty<8;ty++)for(unsigned tx=0;tx<4;tx++)
        for(unsigned y=0;y<8;y++)g_ppu->vram[((ty*16+tx)*16)+y]=(ty&1)?0xff00:0x00ff;
        unsigned width=big?32:16,height=(mode==6 && big)?64:32;
        for(unsigned y=0;y<=height;y++) {
            ppu_runLine(g_ppu,33+y);
            unsigned row=(32+y)*512;
            unsigned src=flip ? (y/width)*width+width-1-(y%width) : y;
            uint32_t color=y==height?0:((src/8)&1)?0x00ff00:0xff0000;
            CHECK(buffer.image[row+32*2]==color);
            CHECK(buffer.image[row+(32+width-1)*2]==color);
            CHECK(buffer.image[row+(32+width)*2]==0);
        }
    }
}
int main(void){
    SDL_SetMainReady();CHECK(rr16_init(true));CHECK(rr16_frame(0,0));
    AudioTracePortEvent events[128];uint64_t oldest,total;
    unsigned n=audio_trace_copy_port_events(0,128,events,&oldest,&total),k=0;
    const uint8_t values[]={0x34,0x12,0x78,0x56};
    for(unsigned i=0;i<n;i++)if(events[i].type==AUDIO_TRACE_EV_CPU_PORT_WRITE){
        CHECK(k<12);CHECK(events[i].port==k%4);CHECK(events[i].val==values[k%4]);++k;
    }
    CHECK(k==12);CHECK(rr16_interpreted()==0);
    k=0;
    for(unsigned i=0;i<n;i++)if(events[i].type==AUDIO_TRACE_EV_CPU_PORT_APPLY){
        CHECK(k<12);CHECK(events[i].port==k%4);CHECK(events[i].val==values[k%4]);++k;
    }
    CHECK(k==12);
    for(int mode=0;mode<=6;mode++)for(int parity=0;parity<2;parity++){
        int pseudo=mode==0;setup(mode,pseudo,1,parity);
        for(int y=1;y<=239;y++)ppu_runLine(g_ppu,y);
        CHECK(buffer.before==0x12345678 && buffer.after==0x87654321);
        int row=2*238+!parity;
        CHECK(buffer.image[row*512+511]!=0);
        CHECK(buffer.image[(2*238+parity)*512+511]==0);
        if(mode==0 || mode==5 || mode==6){
            CHECK(buffer.image[row*512]==0); // first subscreen dot is clipped
            CHECK(buffer.image[row*512+511]==(mode==0?0xff0000:0x00ff00));
            CHECK(buffer.image[row*512+510]==(mode==0?0x00ff00:0xff0000));
        }
    }
    setup(5,0,0,1);ppu_runLine(g_ppu,1);
    uint64_t hash=rr16_video_hash(buffer.image,512,512,224,224);
    buffer.image[510]^=1;CHECK(hash!=rr16_video_hash(buffer.image,512,512,224,224));
    setup(1,0,0,1);ppu_runLine(g_ppu,1);
    for(unsigned x=0;x<256;x++)CHECK(buffer.image[x*2]==buffer.image[x*2+1]);
    setup(0,1,0,1);g_ppu->cgwsel=2;g_ppu->cgadsub=1;ppu_runLine(g_ppu,1);
    CHECK(buffer.image[3]==0xffff00 && buffer.image[4]==0xffff00);
    setup(0,1,0,1);g_ppu->cgwsel=2;g_ppu->cgadsub=0x81;ppu_runLine(g_ppu,1);
    CHECK(buffer.image[3]==0xff0000 && buffer.image[4]==0x00ff00);
    setup(0,1,0,1);g_ppu->cgwsel=2;g_ppu->cgadsub=0x41;ppu_runLine(g_ppu,1);
    CHECK(buffer.image[3]==0x7b7b00 && buffer.image[4]==0x7b7b00);
    setup(0,1,0,1);g_ppu->fixedColor=31<<10;g_ppu->cgadsub=1;ppu_runLine(g_ppu,1);
    CHECK(buffer.image[3]==0xff00ff && buffer.image[4]==0x00ffff);
    setup(0,1,0,1);g_ppu->windowsel=2u<<20;g_ppu->window1left=0;g_ppu->window1right=127;
    g_ppu->cgwsel=0x80;ppu_runLine(g_ppu,1);
    CHECK(buffer.image[255]==0 && buffer.image[256]==0 && buffer.image[257]==0xff0000);
    Rr16Rect rect=rr16_video_rect(1920,1080,256,224,2,1);
    CHECK(rect.w==1024 && rect.h==896);
    rect=rr16_video_rect(256,224,256,224,2,1);CHECK(rect.w==256&&rect.h==224);
    rectangular_objects();
    rr16_shutdown();printf("{\"standard\":\"%s\",\"checks\":%u,\"apu_word_low_first\":true,\"passed\":true}\n",RR_SN_PAL?"pal":"ntsc",checks);
    return 0;
}
int WINAPI WinMain(HINSTANCE a,HINSTANCE b,LPSTR c,int d){return main();}
