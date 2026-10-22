#include "planar_rows.h"
/* Original scanline-local tile-row cache. All VRAM accesses here are reads
 * of the presentation snapshot, not guest bus transactions. Reset before
 * each line, after its raster writes have been applied. Keep window, mosaic,
 * offset-per-tile, main/sub selection and color math in the original caller. */
static struct {
  int valid, x, y, priority;
  int pixels[8];
} rr_sn_bg_rows[4];
static struct {
  unsigned count[2];
  uint8_t layer[2][12], priority[2][12];
} rr_sn_layers;
static void rr_sn_prepare_layers(Ppu *ppu) {
  unsigned mode=PPU_mode(ppu);
  if(mode==1 && PPU_bg3priority(ppu))mode=8;
  else if(mode==7 && PPU_m7extBg(ppu))mode=9;
  for(unsigned sub=0;sub<2;sub++) {
    unsigned count=0;
    for(int i=0;i<layer_count_per_mode[mode];i++) {
      int layer=layers_per_mode[mode][i];
      if(!IS_SCREEN_ENABLED(ppu,sub,layer))continue;
      rr_sn_layers.layer[sub][count]=(uint8_t)layer;
      rr_sn_layers.priority[sub][count++]=(uint8_t)priorities_per_mode[mode][i];
    }
    rr_sn_layers.count[sub]=count;
  }
}
static void rr_sn_bg_cache_reset(void) {
  for (unsigned layer=0;layer<4;layer++) rr_sn_bg_rows[layer].valid=0;
}
static void rr_sn_bg_refill(Ppu *ppu,int x,int y,int layer) {
  int group=x>>3;
  {
    const uint16_t *vram=PpuRenderVram(ppu);
    int mode=PPU_mode(ppu);
    bool wide=PPU_bigTiles(ppu,layer) || mode==5 || mode==6;
    int xb=wide?4:3,yb=PPU_bigTiles(ppu,layer)?4:3;
    uint16_t map=PPU_bgTilemapAdr(ppu,layer)+(((y>>yb)&31)<<5|((x>>xb)&31));
    if((x&(wide?512:256)) && PPU_bgTilemapWider(ppu,layer))map+=0x400;
    if((y&(PPU_bigTiles(ppu,layer)?512:256)) && PPU_bgTilemapHigher(ppu,layer))
      map+=PPU_bgTilemapWider(ppu,layer)?0x800:0x400;
    uint16_t tile=vram[map&0x7fff];
    int row=(tile&0x8000)?7-(y&7):y&7;
    int number=tile&0x3ff;
    if(wide && (!!(x&8)^!!(tile&0x4000)))number++;
    if(PPU_bigTiles(ppu,layer) && (!!(y&8)^!!(tile&0x8000)))number+=16;
    int depth=bit_depths_per_mode[mode][layer];
    int palette=(tile&0x1c00)>>10;
    if(mode==0)palette+=8*layer;
    unsigned address=PPU_bgTileAdr(ppu,layer)+(number&1023)*4*depth+row;
    uint16_t planes[4]={vram[address&0x7fff],0,0,0};
    if(depth>2)planes[1]=vram[(address+8)&0x7fff];
    if(depth>4){planes[2]=vram[(address+16)&0x7fff];planes[3]=vram[(address+24)&0x7fff];}
    int palette_size=depth>4?256:depth>2?16:4;
    uint64_t colors=rr_planar_pair(planes[0]);
    if(depth>2)colors|=rr_planar_pair(planes[1])<<2;
    if(depth>4)colors|=(rr_planar_pair(planes[2])<<4)|(rr_planar_pair(planes[3])<<6);
    for(unsigned n=0;n<8;n++) {
      int pixel=(int)rr_planar_pixel(colors,(tile&0x4000)?n:7-n);
      rr_sn_bg_rows[layer].pixels[n]=pixel?palette_size*palette+pixel:0;
    }
    rr_sn_bg_rows[layer].priority=!!(tile&0x2000);
    rr_sn_bg_rows[layer].x=group;rr_sn_bg_rows[layer].y=y;rr_sn_bg_rows[layer].valid=1;
  }
}
/* Hit path small enough to inline into the per-dot walk. */
static inline int rr_sn_sample_bg_cached(Ppu *ppu,int x,int y,int layer,bool priority) {
  if(!rr_sn_bg_rows[layer].valid || rr_sn_bg_rows[layer].x!=(x>>3) || rr_sn_bg_rows[layer].y!=y)
    rr_sn_bg_refill(ppu,x,y,layer);
  return rr_sn_bg_rows[layer].priority==(int)priority ? rr_sn_bg_rows[layer].pixels[x&7] : 0;
}


/* Original line-constant walk. The pinned resolver evaluates per dot what is
 * constant in one presentation line: priority order, window enables, scroll,
 * mode and mosaic flags. Hoist them once per line; keep the same lazy walk,
 * order and samplers. A background without mosaic, offset-per-tile, hires,
 * mode 7 or widescreen anchoring samples x+scroll directly; any other layer
 * runs the pinned per-dot transforms. Valid inside ppu_draw_whole_line_legacy. */
static struct {
  int active, y;
  unsigned count[2];
  struct { uint8_t layer, priority, windowed, simple; int hscroll, ly; } entry[2][12];
} rr_sn_line;
static void rr_sn_line_begin(Ppu *ppu,int y) {
  int mode=PPU_mode(ppu);
  int plain=mode!=2 && mode!=4 && mode!=5 && mode!=6 && mode!=7 &&
            !(ppu->extraLeftCur | ppu->extraRightCur);
  rr_sn_line.active=1;rr_sn_line.y=y;
  for(unsigned sub=0;sub<2;sub++) {
    rr_sn_line.count[sub]=rr_sn_layers.count[sub];
    for(unsigned n=0;n<rr_sn_layers.count[sub];n++) {
      int layer=rr_sn_layers.layer[sub][n];
      rr_sn_line.entry[sub][n].layer=(uint8_t)layer;
      rr_sn_line.entry[sub][n].priority=rr_sn_layers.priority[sub][n];
      rr_sn_line.entry[sub][n].windowed=IS_SCREEN_WINDOWED(ppu,sub,layer)!=0;
      rr_sn_line.entry[sub][n].simple=layer<4 && plain &&
        !(PPU_mosaicEnabled(ppu,layer) && PPU_mosaicSize(ppu)>1);
      rr_sn_line.entry[sub][n].hscroll=layer<4?ppu->hScroll[layer]:0;
      rr_sn_line.entry[sub][n].ly=layer<4?y+ppu->vScroll[layer]:0;
    }
  }
}
static void rr_sn_line_pick(Ppu *ppu,int x,bool sub,int *layer_out,int *pixel_out) {
  for(unsigned n=0;n<rr_sn_line.count[sub];n++) {
    int layer=rr_sn_line.entry[sub][n].layer,priority=rr_sn_line.entry[sub][n].priority;
    if(rr_sn_line.entry[sub][n].windowed && ppu_window_contains(ppu,layer,x))continue;
    int pixel;
    if(layer==4) {
      uint16_t object=ppu->objBuffer.data[x+kPpuExtraLeftRight];
      pixel=(object>>12)==SPRITE_PRIO_TO_PRIO_HI(priority)?object&0xff:0;
    } else if(rr_sn_line.entry[sub][n].simple) {
      pixel=ppu_sample_bg(ppu,(x+rr_sn_line.entry[sub][n].hscroll)&0x3ff,
                          rr_sn_line.entry[sub][n].ly&0x3ff,layer,priority);
    } else {
      /* The pinned per-dot transforms. */
      int lx=x,ly=rr_sn_line.y;
      if(!ppu_apply_layer_anchor(ppu,layer,ly,sub,&lx))continue;
      if(PPU_mosaicEnabled(ppu,layer) && PPU_mosaicSize(ppu)>1) {
        lx-=lx%PPU_mosaicSize(ppu);
        ly-=(ly-ppu->mosaicStartLine)%PPU_mosaicSize(ppu);
      }
      if(PPU_mode(ppu)==7) pixel=ppu_sample_mode7(ppu,lx,layer,priority);
      else {
        lx+=ppu->hScroll[layer];
        if(PPU_mode(ppu)==5 || PPU_mode(ppu)==6) {
          lx*=2;
          lx+=(sub || PPU_mosaicEnabled(ppu,layer))?0:1;
          if(PPU_interlace(ppu)) {
            ly*=2;
            ly+=(ppu->evenFrame || PPU_mosaicEnabled(ppu,layer))?0:1;
          }
        }
        ly+=ppu->vScroll[layer];
        if(PPU_mode(ppu)==2 || PPU_mode(ppu)==4 || PPU_mode(ppu)==6)
          ppu_apply_offset_per_tile(ppu,layer,&lx,&ly);
        pixel=ppu_sample_bg(ppu,lx&0x3ff,ly&0x3ff,layer,priority);
      }
    }
    if(pixel>0) { *layer_out=layer;*pixel_out=pixel;return; }
  }
}
