/* Authored randomized tile rows: no cartridge or game image. */
#include <stdio.h>
#include <stdlib.h>
#include "snes/ppu_legacy.c"
uint8_t g_snes_ppu_dbg_layer_mask=31;
static uint32_t random_state=0x68491723u;
static unsigned value(void) {
  random_state^=random_state<<13;random_state^=random_state>>17;random_state^=random_state<<5;
  return random_state;
}
int main(void) {
  Ppu *p=calloc(1,sizeof(*p));if(!p)return 2;
  unsigned checks=0;
  for(unsigned mode=0;mode<7;mode++)for(unsigned scene=0;scene<128;scene++) {
    for(unsigned i=0;i<0x8000;i++)p->vram[i]=(uint16_t)value();
    p->bgmode=(uint8_t)((value()&0xf0)|mode);
    p->bgTileAdr=(uint16_t)value();
    for(unsigned i=0;i<4;i++)p->bgXsc[i]=(uint8_t)value();
    for(unsigned pass=0;pass<4;pass++) {
      rr_sn_bg_cache_reset(); // raster changes invalidate all cached rows
      unsigned y=value()&1023;
      for(unsigned x=0;x<1024;x++)for(int layer=0;layer<4;layer++) {
        if(bit_depths_per_mode[mode][layer]==5)continue;
        for(int prio=0;prio<2;prio++) {
          int a=rr_sn_sample_bg_reference(p,x,y,layer,prio);
          int b=rr_sn_sample_bg_cached(p,x,y,layer,prio);
          checks++;
          if(a!=b){fprintf(stderr,"mode=%u scene=%u x=%u y=%u layer=%d priority=%d expected=%d actual=%d\n",mode,scene,x,y,layer,prio,a,b);return 1;}
        }
      }
    }
  }
  unsigned resolve_checks=0,line_checks=0;
  for(unsigned mode=0;mode<8;mode++)for(unsigned scene=0;scene<128;scene++) {
    for(unsigned i=0;i<0x8000;i++)p->vram[i]=(uint16_t)value();
    for(unsigned i=0;i<256;i++)p->cgram[i]=(uint16_t)value();
    p->bgmode=(uint8_t)((value()&0xf8)|mode);
    p->bgTileAdr=(uint16_t)value();p->mosaic=(uint8_t)value();
    p->mosaicStartLine=(uint8_t)(value()&31);p->setini=(uint8_t)value();
    p->m7sel=(uint8_t)value();p->cgwsel=(uint8_t)value();
    p->windowsel=value();p->wbgobjlog=(uint16_t)value();
    p->window1left=(uint8_t)value();p->window1right=(uint8_t)value();
    p->window2left=(uint8_t)value();p->window2right=(uint8_t)value();
    p->screenEnabled[0]=(uint8_t)value();p->screenEnabled[1]=(uint8_t)value();
    p->screenWindowed[0]=(uint8_t)value();p->screenWindowed[1]=(uint8_t)value();
    p->evenFrame=!!(scene&1);g_snes_ppu_dbg_layer_mask=(uint8_t)value();
    for(unsigned i=0;i<4;i++) {
      p->bgXsc[i]=(uint8_t)value();p->hScroll[i]=(uint16_t)(value()&1023);
      p->vScroll[i]=(uint16_t)(value()&1023);
    }
    for(unsigned i=0;i<8;i++)p->m7matrix[i]=(int16_t)value();
    for(unsigned x=0;x<kPpuBufWidth;x++)p->objBuffer.data[x]=(uint16_t)value();
    /* Sparse scenes: most sprite dots empty, most tile words zero, so that whole layer
     * priorities have nothing to show and are dropped from the line's walk. */
    if(scene&2)for(unsigned x=0;x<kPpuBufWidth;x++)if(value()&7)p->objBuffer.data[x]=0;
    if(scene&4)for(unsigned i=0;i<0x8000;i++)if(value()&7)p->vram[i]=0;
    if(scene&8)for(unsigned x=0;x<kPpuBufWidth;x++)p->objBuffer.data[x]&=(uint16_t)(0x0fffu|((value()&3)<<12));
    for(unsigned line=1;line<240;line+=17) {
      rr_sn_bg_cache_reset();rr_sn_prepare_layers(p);
      if(mode==7)ppu_prepare_mode7(p,line);
      for(int x=0;x<256;x++)for(unsigned sub=0;sub<2;sub++) {
        int a[3],b[3];
        int la=rr_sn_resolve_reference(p,x,line,sub,&a[0],&a[1],&a[2]);
        int lb=ppu_resolve_pixel(p,x,line,sub,&b[0],&b[1],&b[2]);
        resolve_checks++;
        if(la!=lb || memcmp(a,b,sizeof a)) {
          fprintf(stderr,"resolve mode=%u scene=%u x=%d line=%u sub=%u\n",mode,scene,x,line,sub);return 1;
        }
      }
      /* The scanline compositor must resolve every dot exactly the same. */
      rr_sn_bg_cache_reset();rr_sn_line_begin(p,(int)line);
      for(int x=0;x<256;x++)for(unsigned sub=0;sub<2;sub++) {
        int a[3],b[3];
        int la=rr_sn_resolve_reference(p,x,line,sub,&a[0],&a[1],&a[2]);
        int lb=ppu_resolve_pixel(p,x,line,sub,&b[0],&b[1],&b[2]);
        line_checks++;
        if(la!=lb || memcmp(a,b,sizeof a)) {
          fprintf(stderr,"line mode=%u scene=%u x=%d line=%u sub=%u\n",mode,scene,x,line,sub);return 1;
        }
      }
      rr_sn_line.active=0;
    }
  }
  /* Widescreen margins: every dot of [-left, 256+right) with random layer anchor bands. The
   * line products (decoded backgrounds, window masks) must either match the per-dot walk or
   * stay out of the way (backgrounds fall back to it whenever a margin exists). */
  unsigned margin_checks=0;
  for(unsigned mode=0;mode<8;mode++)for(unsigned scene=0;scene<48;scene++) {
    for(unsigned i=0;i<0x8000;i++)p->vram[i]=(uint16_t)value();
    for(unsigned i=0;i<256;i++)p->cgram[i]=(uint16_t)value();
    p->bgmode=(uint8_t)((value()&0xf8)|mode);
    p->bgTileAdr=(uint16_t)value();p->mosaic=(uint8_t)(scene&1?value():value()&0xf0);
    p->mosaicStartLine=(uint8_t)(value()&31);p->setini=(uint8_t)value();
    p->m7sel=(uint8_t)value();p->cgwsel=(uint8_t)value();
    p->windowsel=value();p->wbgobjlog=(uint16_t)value();
    p->window1left=(uint8_t)value();p->window1right=(uint8_t)value();
    p->window2left=(uint8_t)value();p->window2right=(uint8_t)value();
    p->screenEnabled[0]=(uint8_t)value();p->screenEnabled[1]=(uint8_t)value();
    p->screenWindowed[0]=(uint8_t)value();p->screenWindowed[1]=(uint8_t)value();
    p->evenFrame=!!(scene&1);g_snes_ppu_dbg_layer_mask=(uint8_t)value();
    for(unsigned i=0;i<4;i++) {
      p->bgXsc[i]=(uint8_t)value();p->hScroll[i]=(uint16_t)(value()&1023);
      p->vScroll[i]=(uint16_t)(value()&1023);
    }
    for(unsigned i=0;i<8;i++)p->m7matrix[i]=(int16_t)value();
    for(unsigned x=0;x<kPpuBufWidth;x++)p->objBuffer.data[x]=(uint16_t)value();
    /* Sparse scenes: most sprite dots empty, most tile words zero, so that whole layer
     * priorities have nothing to show and are dropped from the line's walk. */
    if(scene&2)for(unsigned x=0;x<kPpuBufWidth;x++)if(value()&7)p->objBuffer.data[x]=0;
    if(scene&4)for(unsigned i=0;i<0x8000;i++)if(value()&7)p->vram[i]=0;
    if(scene&8)for(unsigned x=0;x<kPpuBufWidth;x++)p->objBuffer.data[x]&=(uint16_t)(0x0fffu|((value()&3)<<12));
    p->extraLeftCur=(uint16_t)(value()%97);p->extraRightCur=(uint16_t)(value()%97);
    for(unsigned slot=0;slot<kPpuWsAnchorBands;slot++)for(unsigned layer=0;layer<4;layer++) {
      p->wsAnchorY0[slot][layer]=(uint8_t)(value()%100);p->wsAnchorY1[slot][layer]=(uint8_t)(100+value()%140);
      p->wsAnchorLeftEnd[slot][layer]=(uint8_t)(value()%120);p->wsAnchorRightStart[slot][layer]=(uint8_t)(120+value()%130);
    }
    for(unsigned line=1;line<240;line+=23) {
      rr_sn_bg_cache_reset();rr_sn_prepare_layers(p);
      if(mode==7)ppu_prepare_mode7(p,line);
      rr_sn_line_begin(p,(int)line);
      for(int x=-(int)p->extraLeftCur;x<256+(int)p->extraRightCur;x++)for(unsigned sub=0;sub<2;sub++) {
        int a[3],b[3];
        int la=rr_sn_resolve_reference(p,x,line,sub,&a[0],&a[1],&a[2]);
        int lb=ppu_resolve_pixel(p,x,line,sub,&b[0],&b[1],&b[2]);
        margin_checks++;
        if(la!=lb || memcmp(a,b,sizeof a)) {
          fprintf(stderr,"margin mode=%u scene=%u x=%d line=%u sub=%u\n",mode,scene,x,line,sub);return 1;
        }
      }
      rr_sn_line.active=0;
    }
  }
  free(p);printf("{\"pixel_comparisons\":%u,\"resolved_comparisons\":%u,\"line_comparisons\":%u,\"margin_comparisons\":%u,\"equal\":true}\n",checks,resolve_checks,line_checks,margin_checks);return 0;
}
