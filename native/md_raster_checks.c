/* Authored row patterns. No cartridge, external image or guest-memory patch. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "video/genesis_vdp.h"
extern int gvdp_render_scanline_latched(GVDP *,int,uint8_t *,uint16_t,uint16_t);
unsigned machine_vdp_phase(void) { return 0; }
static unsigned checks;
#define CHECK(ok) do { ++checks; if(!(ok)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#ok);exit(1);} }while(0)
static uint8_t out[GVDP_MAX_WIDTH];
int main(void) {
 for(unsigned h40=0;h40<2;++h40) for(unsigned im2=0;im2<2;++im2) for(unsigned plane=0;plane<2;++plane) {
  GVDP v;gvdp_init(&v);unsigned density=im2?2:1,rows=8*density,width=h40?320:256;
  v.reg[1]=0x40;v.reg[12]=(h40?0x81:0)|(im2?6:0);
  v.reg[2]=0x38;v.reg[4]=6;v.reg[5]=0x68;v.reg[16]=1;
  unsigned base=plane?0xc000:0xe000;
  for(unsigned i=0;i<64*32;++i)v.vram[base+i*2+1]=1;
  for(unsigned y=0;y<rows;++y)for(unsigned x=0;x<4;++x)v.vram[32*density+y*4+x]=(uint8_t)(((y%15+1)<<4)|(y%15+1));
  for(unsigned y=0;y<224*density;++y) {
   uint16_t latched[2]={0,0};
   /* A late horizontal IRQ changes the live words. This row still consumes
    * the values fetched before that IRQ; the following row can use the new
    * words. Framebuffer filtering cannot satisfy these index expectations. */
   v.vsram[0]=v.vsram[1]=3;
   CHECK(gvdp_render_scanline_latched(&v,y,out,latched[0],latched[1])==(int)width);
   for(unsigned x=0;x<width;++x)CHECK(out[x]==(uint8_t)(y%rows%15+1));
   CHECK(v.vsram[0]==3 && v.vsram[1]==3);
   CHECK(gvdp_render_scanline(&v,y,out)==(int)width);
   CHECK(out[0]==(uint8_t)((y+3)%rows%15+1));
   CHECK(gvdp_render_scanline_latched(&v,y+1,out,3,3)==(int)width);
   CHECK(out[0]==(uint8_t)((y+4)%rows%15+1));
  }
  v.reg[11]=4;v.vsram[0]=v.vsram[1]=5;
  CHECK(gvdp_render_scanline_latched(&v,0,out,0,0)==(int)width);
  CHECK(out[0]==6); /* two-cell mode uses its live column words */
 }
 printf("{\"checks\":%u,\"full_plane_scroll_latched_before_irq\":true,\"live_vsram_preserved\":true,\"two_cell_scroll_preserved\":true,\"passed\":true}\n",checks);
 return 0;
}
