#include "planar_rows.h"
/* Original scanline-local tile-row cache. All VRAM accesses here are reads
 * of the presentation snapshot, not guest bus transactions. Reset before
 * each line, after its raster writes have been applied. Keep window, mosaic,
 * offset-per-tile, main/sub selection and color math in the original caller. */
static struct {
  int valid, x, y, priority, opaque;
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
/* Offset-per-tile (modes 2, 4, 6): the two BG3 words that displace a layer depend only on the
 * 8-dot column, never on the layer or the dot, and BG3's scroll, tilemap and VRAM are constant
 * within a presentation line. Read them once per column and line. A reset starts a new line. */
static struct {
  uint32_t generation;
  struct { uint32_t generation; uint16_t h, v; } column[256];
} rr_sn_offsets;
static void rr_sn_bg_cache_reset(void) {
  for (unsigned layer=0;layer<4;layer++) rr_sn_bg_rows[layer].valid=0;
  rr_sn_offsets.generation++;
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
    rr_sn_bg_rows[layer].opaque=0;
    for(unsigned n=0;n<8;n++)rr_sn_bg_rows[layer].opaque|=rr_sn_bg_rows[layer].pixels[n]!=0;
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
 * mode and mosaic flags. Hoist them once per line; keep the same first-hit walk
 * in the same order. A background without mosaic, hires, mode 7 or widescreen
 * margins is decoded for the whole line first (rr_sn_fill_layer, offset-per-tile
 * included); any other layer runs the pinned per-dot transforms. Windows are
 * tested once per line, and entries with nothing to show are dropped. The result
 * for every dot is the pinned resolver's (tools/snes_ppu_cache_selftest.py).
 * Valid inside ppu_draw_whole_line_legacy. */
static struct {
  int active, y;
  unsigned count[2];
  struct { uint8_t layer, priority, windowed, fill; } entry[2][12];
  uint8_t window_ready[5], pruned[2];
  uint16_t object_priorities;   /* bit n: an opaque sprite dot whose priority nibble is n */
  int left, right;
} rr_sn_line;
/* Per-line products shared by every dot of the line (all pure functions of line state):
 *  - pixel/priority: a background without mosaic, hires, mode 7 or widescreen margins is
 *    decoded once per line, run by run, instead of once per dot and priority;
 *  - window: ppu_window_contains() of each windowed layer for every dot of the line. */
static struct {
  uint16_t pixel[4][256];
  uint8_t priority[4][256];
  uint8_t opaque[4][2];                  /* a tile row with an opaque dot was met at this tile priority */
  uint8_t window[5][kPpuBufWidth];
} rr_sn_fill;
/* Same result as the pinned ppu_apply_offset_per_tile, with the BG3 words memoized per column. */
static void rr_sn_offset_per_tile(Ppu *ppu,int layer,int *lx,int *ly) {
  int x=*lx,y=*ly,column=0;
  if(PPU_mode(ppu)==6)column=((x-(x&0xf))-((ppu->hScroll[layer]*2)&0xfff0))>>4;
  else column=((x-(x&0x7))-(ppu->hScroll[layer]&0xfff8))>>3;
  if(column<=0)return;
  if(column>=256) {ppu_apply_offset_per_tile(ppu,layer,lx,ly);return;}
  if(rr_sn_offsets.column[column].generation!=rr_sn_offsets.generation) {
    uint16_t hOffset=ppu_read_offset(ppu,column-1,0),vOffset=0;
    if(PPU_mode(ppu)==4) {
      if(hOffset&0x8000) {vOffset=hOffset;hOffset=0;}
    } else vOffset=ppu_read_offset(ppu,column-1,1);
    rr_sn_offsets.column[column].generation=rr_sn_offsets.generation;
    rr_sn_offsets.column[column].h=hOffset;rr_sn_offsets.column[column].v=vOffset;
  }
  uint16_t hOffset=rr_sn_offsets.column[column].h,vOffset=rr_sn_offsets.column[column].v;
  int valid=layer==0?0x2000:0x4000;
  if(PPU_mode(ppu)==6) {
    if(hOffset&valid)*lx=(((hOffset&0x3f8)+(column*8))*2)|(x&0xf);
  } else {
    if(hOffset&valid)*lx=((hOffset&0x3f8)+(column*8))|(x&0x7);
  }
  if(vOffset&valid)*ly=(vOffset&0x3ff)+(y-ppu->vScroll[layer]);
}
/* One background for the whole line, 256 dots, same result per dot as the pinned per-dot
 * transforms (scroll, then offset-per-tile in modes 2 and 4, then the tile row sampler).
 * Within one 8-dot run the offset-per-tile column is constant, the tile row is constant
 * and the sampled tile column advances by one per dot (no carry out of the 8-dot group:
 * a run ends where x + scroll reaches the next multiple of 8). */
static void rr_sn_fill_layer(Ppu *ppu,int layer,int y) {
  const int mode=PPU_mode(ppu),hscroll=ppu->hScroll[layer],vscroll=ppu->vScroll[layer];
  const bool offsets=mode==2 || mode==4;
  uint16_t *pixel=rr_sn_fill.pixel[layer];
  uint8_t *priority=rr_sn_fill.priority[layer];
  rr_sn_fill.opaque[layer][0]=rr_sn_fill.opaque[layer][1]=0;
  for(int x=0;x<256;) {
    int lx=x+hscroll,ly=y+vscroll;
    int run=8-(lx&7);
    if(run>256-x)run=256-x;
    if(offsets)rr_sn_offset_per_tile(ppu,layer,&lx,&ly);
    int sx=lx&0x3ff,sy=ly&0x3ff;
    if(!rr_sn_bg_rows[layer].valid || rr_sn_bg_rows[layer].x!=(sx>>3) || rr_sn_bg_rows[layer].y!=sy)
      rr_sn_bg_refill(ppu,sx,sy,layer);
    const int tile_priority=rr_sn_bg_rows[layer].priority;
    if(rr_sn_bg_rows[layer].opaque)rr_sn_fill.opaque[layer][tile_priority&1]=1;
    for(int k=0;k<run;k++) {
      pixel[x+k]=(uint16_t)rr_sn_bg_rows[layer].pixels[(sx+k)&7];
      priority[x+k]=(uint8_t)tile_priority;
    }
    x+=run;
  }
}
/* The pinned per-dot transforms of one background entry (mosaic, hires, mode 7, widescreen
 * margins). False: the layer is skipped at this dot (widescreen anchoring). */
static bool rr_sn_entry_generic(Ppu *ppu,int x,bool sub,int layer,int priority,int *pixel_out) {
  int pixel,lx=x,ly=rr_sn_line.y;
  if(!ppu_apply_layer_anchor(ppu,layer,ly,sub,&lx))return false;
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
      rr_sn_offset_per_tile(ppu,layer,&lx,&ly);
    pixel=ppu_sample_bg(ppu,lx&0x3ff,ly&0x3ff,layer,priority);
  }
  *pixel_out=pixel;
  return true;
}
/* Drop the entries that cannot win a dot of this line: a background or sprite priority with no
 * opaque dot to show (the walk would test them at every dot and always fall through). Windows
 * only remove dots, so a windowed entry is dropped on the same test. The first-hit result of
 * the remaining entries, in the same order, is unchanged. Sprites are tested over the dots the
 * line draws; backgrounds without a decoded line (mosaic, hires, mode 7, margins) always stay. */
static void rr_sn_prune(Ppu *ppu,bool sub) {
  unsigned kept=0;
  (void)ppu;
  for(unsigned n=0;n<rr_sn_line.count[sub];n++) {
    const int layer=rr_sn_line.entry[sub][n].layer,priority=rr_sn_line.entry[sub][n].priority;
    bool any=true;
    if(layer==4)any=(rr_sn_line.object_priorities>>SPRITE_PRIO_TO_PRIO_HI(priority)&1)!=0;
    else if(rr_sn_line.entry[sub][n].fill)any=(unsigned)priority<2 && rr_sn_fill.opaque[layer][priority];
    if(any)rr_sn_line.entry[sub][kept++]=rr_sn_line.entry[sub][n];
  }
  rr_sn_line.count[sub]=kept;
  rr_sn_line.pruned[sub]=1;
}
static void rr_sn_line_begin(Ppu *ppu,int y) {
  int mode=PPU_mode(ppu);
  int eligible=mode!=5 && mode!=6 && mode!=7 && !(ppu->extraLeftCur | ppu->extraRightCur);
  bool filled[4]={false,false,false,false};
  bool windowed[5]={false,false,false,false,false};
  rr_sn_line.active=1;rr_sn_line.y=y;
  for(unsigned sub=0;sub<2;sub++) {
    rr_sn_line.count[sub]=rr_sn_layers.count[sub];
    for(unsigned n=0;n<rr_sn_layers.count[sub];n++) {
      int layer=rr_sn_layers.layer[sub][n];
      rr_sn_line.entry[sub][n].layer=(uint8_t)layer;
      rr_sn_line.entry[sub][n].priority=rr_sn_layers.priority[sub][n];
      rr_sn_line.entry[sub][n].windowed=IS_SCREEN_WINDOWED(ppu,sub,layer)!=0;
      rr_sn_line.entry[sub][n].fill=layer<4 && eligible &&
        !(PPU_mosaicEnabled(ppu,layer) && PPU_mosaicSize(ppu)>1);
      if(rr_sn_line.entry[sub][n].fill)filled[layer]=true;
      if(rr_sn_line.entry[sub][n].windowed)windowed[layer]=true;
    }
  }
  for(int layer=0;layer<4;layer++)if(filled[layer])rr_sn_fill_layer(ppu,layer,y);
  int left=-ppu->extraLeftCur,right=256+ppu->extraRightCur;
  for(int layer=0;layer<5;layer++) {
    rr_sn_line.window_ready[layer]=0;
    if(!windowed[layer] || left<-kPpuExtraLeftRight || right>256+kPpuExtraLeftRight)continue;
    for(int x=left;x<right;x++)rr_sn_fill.window[layer][x+kPpuExtraLeftRight]=ppu_window_contains(ppu,layer,x);
    rr_sn_line.window_ready[layer]=1;
  }
  rr_sn_line.left=left;rr_sn_line.right=right;
  rr_sn_line.object_priorities=0;
  if(rr_sn_layers.count[0] | rr_sn_layers.count[1]) {
    const uint16_t *objects=ppu->objBuffer.data+kPpuExtraLeftRight;
    for(int x=left;x<right;x++)
      if(objects[x]&0xff)rr_sn_line.object_priorities|=(uint16_t)(1u<<(objects[x]>>12));
  }
  rr_sn_line.pruned[0]=rr_sn_line.pruned[1]=0;
  rr_sn_prune(ppu,false);
}
static void rr_sn_line_pick(Ppu *ppu,int x,bool sub,int *layer_out,int *pixel_out) {
  if(!rr_sn_line.pruned[sub])rr_sn_prune(ppu,sub);
  for(unsigned n=0;n<rr_sn_line.count[sub];n++) {
    int layer=rr_sn_line.entry[sub][n].layer,priority=rr_sn_line.entry[sub][n].priority;
    if(rr_sn_line.entry[sub][n].windowed &&
       (rr_sn_line.window_ready[layer] ? rr_sn_fill.window[layer][x+kPpuExtraLeftRight] :
                                         ppu_window_contains(ppu,layer,x)))continue;
    int pixel;
    if(layer==4) {
      uint16_t object=ppu->objBuffer.data[x+kPpuExtraLeftRight];
      pixel=(object>>12)==SPRITE_PRIO_TO_PRIO_HI(priority)?object&0xff:0;
    } else if(rr_sn_line.entry[sub][n].fill) {
      pixel=rr_sn_fill.priority[layer][x]==priority?rr_sn_fill.pixel[layer][x]:0;
    } else if(!rr_sn_entry_generic(ppu,x,sub,layer,priority,&pixel))continue;
    if(pixel>0) { *layer_out=layer;*pixel_out=pixel;return; }
  }
}
