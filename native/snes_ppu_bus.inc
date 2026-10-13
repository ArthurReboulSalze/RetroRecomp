/* Original live OAM evaluation/fetch-address model. Pixels are still drawn
 * by the existing renderer. Port collisions use the current bus latch. */
static unsigned rr_sn_obj_width(Ppu *p,unsigned sprite) {
  static const uint8_t width[8][2]={{8,16},{8,32},{8,64},{16,32},{16,64},{32,64},{16,32},{16,32}};
  return width[PPU_objSize(p)][(p->highOam[sprite>>2]>>((sprite&3)*2+1))&1];
}
static unsigned rr_sn_obj_height(Ppu *p,unsigned sprite) {
  static const uint8_t height[8][2]={{8,16},{8,32},{8,64},{16,32},{16,64},{32,64},{32,64},{32,32}};
  unsigned big=(p->highOam[sprite>>2]>>((sprite&3)*2+1))&1;
  unsigned size=height[PPU_objSize(p)][big];
  if(PPU_objInterlace(p) && PPU_objSize(p)>=6 && !big)size=16;
  return PPU_objInterlace(p) ? size/2 : size;
}
void rr_sn_ppu_bus_advance(Ppu *p,unsigned line,unsigned from,unsigned until) {
  (void)from;
  if(!p->rrOamActive || p->rrOamLine!=line) {
    p->rrOamActive=1;
    p->rrOamLine=(uint16_t)line;p->rrOamEvaluated=0;p->rrOamCount=0;
    p->rrOamFirst=PPU_objPriority(p) ? p->oamAdr>>1 : 0;
    p->rrOamFetchClock=1080;p->rrOamFetchItem=-2;p->rrOamFetchLoaded=0;
    p->rrOamFetchDone=0;p->rrOamTiles=0;
    if(line==0) {p->rangeOver=false;p->timeOver=false;}
    if(line==(p->frameOverscan ? 240u : 225u) && !PPU_forcedBlank(p)) {
      p->oamAdr=p->oamaddl;p->oamInHigh=p->oamaddh&1;p->oamSecondWrite=false;
    }
  }
  unsigned upto=until/8+1;if(upto>128)upto=128;
  while(p->rrOamEvaluated<upto) {
    unsigned sprite=(p->rrOamFirst+p->rrOamEvaluated++)&127;
    // A masked slot still elapses. Never evaluate it later on unblanking.
    if(PPU_forcedBlank(p) || line>=(p->frameOverscan ? 239u : 224u))continue;
    if(p->rrOamCount>32)continue;
    unsigned x=(p->oam[sprite*2]&255)|(((p->highOam[sprite>>2]>>((sprite&3)*2))&1)<<8);
    unsigned row=(line-(p->oam[sprite*2]>>8))&255;
    if(row>=rr_sn_obj_height(p,sprite) || (x>256 && x+rr_sn_obj_width(p,sprite)-1<512))continue;
    p->rrBusOam=(uint8_t)sprite;
    if(p->rrOamCount++<32)p->rrOamItems[p->rrOamCount-1]=(uint8_t)sprite;
  }
  if(until<1080 || p->rrOamFetchDone)return;
  if(p->rrOamFetchItem==-2)p->rrOamFetchItem=(int8_t)((p->rrOamCount>32?32:p->rrOamCount)-1);
  // This cursor is architectural state (including in F8/F9). Recomputing the
  // whole sequence from live OAM on every CPU access rewinds elapsed phases.
  while(p->rrOamFetchClock<=until) {
    if(p->rrOamFetchLoaded) {
      if(p->rrOamFetchColumn<p->rrOamFetchWidth) {
        unsigned sx=(p->rrOamFetchX+p->rrOamFetchColumn)&511;
        p->rrOamFetchColumn+=8;
        if(p->rrOamFetchX!=256 && sx>=256 && sx+7<512)continue;
        if(++p->rrOamTiles<=34) {p->rrOamFetchClock+=8;continue;}
      }
      p->rrOamFetchLoaded=0;p->rrOamFetchItem--;
    }
    if(p->rrOamFetchItem<0) {
      p->rangeOver|=p->rrOamCount>32;p->timeOver|=p->rrOamTiles>34;
      p->rrOamFetchDone=1;break;
    }
    if(PPU_forcedBlank(p) || line>=(p->frameOverscan ? 239u : 224u)) {
      p->rrOamFetchItem--;p->rrOamFetchClock+=8;continue;
    }
    unsigned sprite=p->rrOamItems[(unsigned)p->rrOamFetchItem];
    p->rrBusOam=(uint8_t)sprite;
    p->rrOamFetchX=(p->oam[sprite*2]&255)|(((p->highOam[sprite>>2]>>((sprite&3)*2))&1)<<8);
    p->rrOamFetchWidth=(uint8_t)rr_sn_obj_width(p,sprite);
    p->rrOamFetchColumn=0;p->rrOamFetchLoaded=1;
  }
}
static unsigned rr_sn_port_line(void) {
  return g_ppu_wlog_src==kPpuWlogReplay ? rr_sn_replay_line : g_snes->vPos;
}
static unsigned rr_sn_oam_address(Ppu *p,unsigned address) {
  if(g_ppu_wlog_src==kPpuWlogReplay && rr_sn_replay_effective!=0xffffu)
    return address&512 ? rr_sn_replay_effective : (rr_sn_replay_effective&~1u)|(address&1);
  if(!PPU_forcedBlank(p) && rr_sn_port_line()<(p->frameOverscan ? 240u : 225u))
    return address&512 ? 512u+(p->rrBusOam>>2) : (p->rrBusOam*4u)|(address&1);
  return address&512 ? 512u+(address&31) : address&511;
}
static uint8_t rr_sn_oam_read(Ppu *p,unsigned address) {
  unsigned a=rr_sn_oam_address(p,address);
  return a&512 ? p->highOam[a&31] : (uint8_t)(p->oam[a>>1]>>((a&1)*8));
}
static void rr_sn_oam_write(Ppu *p,unsigned address,uint8_t value) {
  unsigned a=rr_sn_oam_address(p,address);
  if(a&512)p->highOam[a&31]=value;
  else {unsigned shift=(a&1)*8;p->oam[a>>1]=(p->oam[a>>1]&~(255u<<shift))|((unsigned)value<<shift);}
}
extern uint8_t rr_sn_palette_at(Ppu *p,int x,int y);
static unsigned rr_sn_cgram_address(Ppu *p) {
  if(g_ppu_wlog_src==kPpuWlogReplay && rr_sn_replay_effective!=0xffffu)return rr_sn_replay_effective;
  unsigned v=rr_sn_port_line(),h=g_snes->hPos;
  if(!PPU_forcedBlank(p) && v>0 && v<(p->frameOverscan ? 240u : 225u) && h>=88 && h<1096) {
    static Ppu sample;memcpy(&sample,p,sizeof sample);
    ClearBackdrop(&sample,&sample.objBuffer);
    sample.lineHasSprites=ppu_evaluateSprites(&sample,(int)v-1);
    int x=(int)(h-58)/4;if(x>255)x=255;
    p->rrBusCgram=rr_sn_palette_at(&sample,x,(int)v);
    return p->rrBusCgram;
  }
  return p->cgramPointer;
}
