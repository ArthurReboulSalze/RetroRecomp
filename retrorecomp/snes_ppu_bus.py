"""Live PPU memory-port collisions and recorded effective replay addresses."""
from .snes_timing import replace


def header(source):
    return replace(source,'  uint16_t extraLeftCur, extraRightCur, extraLeftRight;', '''  uint8_t rrMdr1,rrMdr2,rrBusCgram,rrBusOam,rrOamFirst,rrOamCount,rrOamItems[32];
  uint16_t rrOamLine,rrOamEvaluated;
  uint16_t rrOamFetchClock,rrOamFetchX;
  int8_t rrOamFetchItem;
  uint8_t rrOamFetchColumn,rrOamFetchWidth,rrOamTiles,rrOamFetchLoaded,rrOamFetchDone,rrOamActive;
  uint16_t extraLeftCur, extraRightCur, extraLeftRight;''')


def bus(source):
    source=replace(source,'        h += upto;\n        consumed += upto;',
        '        rr_sn_ppu_bus_advance(snes->ppu,v,h,h+upto);\n        h += upto;\n        consumed += upto;')
    source=replace(source,'    h += span;\n    clocks -= span;\n    consumed += span;',
        '    rr_sn_ppu_bus_advance(snes->ppu,v,h,h+span);\n    h += span;\n    clocks -= span;\n    consumed += span;')
    return '#include "snes/ppu.h"\nextern void rr_sn_ppu_bus_advance(Ppu *,unsigned,unsigned,unsigned);\n'+source


def legacy(source):
    # The shared pixel resolver supplies the palette bus winner. Direct-color
    # main pixels leave the subscreen's last palette address on the bus.
    source=replace(source,'static void ppu_render_pixel(Ppu *ppu, int x, int y);',
        'static int rr_sn_resolved_palette;\nstatic void ppu_render_pixel(Ppu *ppu, int x, int y);')
    source=replace(source,'    uint16_t color = layer==4',
        '    rr_sn_resolved_palette=pixel&255;\n    uint16_t color = layer==4')
    return source+'''
uint8_t rr_sn_palette_at(Ppu *p,int x,int y) {
  /* This is a fresh live-bus snapshot, not the last displayed scanline. */
  rr_sn_bg_cache_reset();rr_sn_prepare_layers(p);
  int r,g,b;rr_sn_resolved_palette=p->rrBusCgram;
  if(PPU_mode(p)==7)ppu_prepare_mode7(p,y);
  ppu_resolve_pixel(p,x,y,true,&r,&g,&b);
  ppu_resolve_pixel(p,x,y,false,&r,&g,&b);
  return (uint8_t)rr_sn_resolved_palette;
}
'''


def ppu(source):
    # Modes 6/7 have rectangular objects. Vertical flip reverses each square
    # half independently, rather than dropping the lower half of a 16x32 OBJ.
    source=replace(source,'  // TODO: rectangular sprites, wierdness with sprites at -256', '''  static const uint8 spriteHeights[8][2] = {
    {8,16},{8,32},{8,64},{16,32},{16,64},{32,64},{32,64},{32,32}
  };''')
    source=replace(source,'    int spriteHeight = PPU_objInterlace(ppu) ? spriteSize / 2 : spriteSize;', '''    int large=(ppu->highOam[index>>3]>>((index&7)+1))&1;
    int spriteHeight=spriteHeights[PPU_objSize(ppu)][large];
    if(PPU_objInterlace(ppu) && PPU_objSize(ppu)>=6 && !large)spriteHeight=16;
    if(PPU_objInterlace(ppu))spriteHeight/=2;''')
    source=replace(source,'        if(oam1 & 0x8000) row = spriteSize - 1 - row;', '''        if(oam1 & 0x8000) {
          int half=row/spriteSize;
          row=half*spriteSize+spriteSize-1-(row%spriteSize);
        }''')
    source=replace(source,'static uint8_t rr_sn_live_ports[RR_SN_PORT_BYTES];',
        'static uint8_t rr_sn_live_ports[offsetof(Ppu,extraLeftCur)-offsetof(Ppu,vramPointer)];')
    marker='static unsigned rr_sn_replay_line;'
    source=replace(source,marker,'''static unsigned rr_sn_replay_line;
static uint16_t rr_sn_replay_effective=0xffffu;
#include "snes_ppu_bus.inc"
''')
    source=replace(source,'uint8_t ppu_read(Ppu* ppu, uint8_t adr) {',
        'static uint8_t rr_sn_port_read(Ppu* ppu, uint8_t adr) {')
    source=replace(source,'ret = ppu->highOam[((ppu->oamAdr & 0xf) << 1) | ppu->oamSecondWrite];',
        'ret=rr_sn_oam_read(ppu,512u|((ppu->oamAdr&15u)<<1)|ppu->oamSecondWrite);')
    source=replace(source,'ret = ppu->oam[ppu->oamAdr] & 0xff;',
        'ret=rr_sn_oam_read(ppu,ppu->oamAdr*2u);')
    source=replace(source,'ret = ppu->oam[ppu->oamAdr++] >> 8;',
        'ret=rr_sn_oam_read(ppu,ppu->oamAdr*2u+1u);ppu->oamAdr++;')
    source=replace(source,'ret = ppu->cgram[ppu->cgramPointer] & 0xff;',
        'ret=ppu->cgram[rr_sn_cgram_address(ppu)]&255;')
    source=replace(source,'ret = ((ppu->cgram[ppu->cgramPointer++] >> 8) & 0x7f);',
        'ret=((ppu->cgram[rr_sn_cgram_address(ppu)]>>8)&127)|(ppu->rrMdr2&128);ppu->cgramPointer++;')
    source=replace(source,'ppu->highOam[hidx] = val;',
        'rr_sn_oam_write(ppu,512u|(unsigned)hidx,val);')
    source=replace(source,'          ppu->oam[ppu->oamAdr++] = word;',
        '''          rr_sn_oam_write(ppu,ppu->oamAdr*2u,ppu->oamBuffer);
          rr_sn_oam_write(ppu,ppu->oamAdr*2u+1u,val);ppu->oamAdr++;''')
    source=replace(source,'ppu->cgram[ppu->cgramPointer++] = (val << 8) | ppu->cgramBuffer;',
        'ppu->cgram[rr_sn_cgram_address(ppu)]=((val&127u)<<8)|ppu->cgramBuffer;ppu->cgramPointer++;')
    # The replay carries the address resolved when the CPU/DMA performed the
    # transfer. Re-evaluating against the final beam/PPU state is wrong.
    source=replace(source,'typedef struct { uint16_t key; uint16_t reg; uint8_t val; } PpuRasterEntry;',
        'typedef struct { uint16_t key,reg,effective; uint8_t val; } PpuRasterEntry;')
    source=replace(source,'  f->e[f->count].reg = reg;',
        '''  f->e[f->count].effective=0xffffu;
  if(reg==0x2122 && raster_machine_ppu()->cgramSecondWrite)
    f->e[f->count].effective=(uint16_t)rr_sn_cgram_address(raster_machine_ppu());
  if(reg==0x2104) {
    Ppu *p=raster_machine_ppu();unsigned a=(p->oamInHigh?512u:0u)|p->oamAdr*2u|p->oamSecondWrite;
    f->e[f->count].effective=(uint16_t)rr_sn_oam_address(p,a);
  }
  f->e[f->count].reg = reg;''')
    source=replace(source,'      rr_sn_replay_line=f->e[s_raster_next].key % (RR_SN_LINES+1u);',
        '''      rr_sn_replay_effective=f->e[s_raster_next].effective;
      rr_sn_replay_line=f->e[s_raster_next].key % (RR_SN_LINES+1u);''')
    source=replace(source,'      raster_replay(ppu, reg, val);',
        '      raster_replay(ppu, reg, val);rr_sn_replay_effective=0xffffu;')
    return '#include "cpu_state.h"\n'+source+'''
uint8_t ppu_read(Ppu *p,uint8_t address) {
  if(address<0x34) {
    switch(address) {
      case 4:case 5:case 6:case 8:case 9:case 10:case 20:case 21:case 22:
      case 24:case 25:case 26:case 36:case 37:case 38:case 40:case 41:case 42:return p->rrMdr1;
      default:return g_cpu.open_bus;
    }
  }
  uint8_t value=rr_sn_port_read(p,address);
  if(address==0x37)return g_cpu.open_bus;
  if(address<=0x3a || address==0x3e) {
    if(address==0x3e)value=(value&239u)|(p->rrMdr1&16u);
    p->rrMdr1=value;
  } else {
    if((address==0x3c && !p->hCountSecond) || (address==0x3d && !p->vCountSecond))
      value=(value&1u)|(p->rrMdr2&254u);
    if(address==0x3f)value=(value&223u)|(p->rrMdr2&32u);
    p->rrMdr2=value;
  }
  return value;
}
'''


def adapt_engine(staged):
    for name,adapt in (('snes/ppu.h',header),('snes/snes.c',bus),
                       ('snes/ppu.c',ppu),('snes/ppu_legacy.c',legacy)):
        path=staged/'runner/src'/name
        path.write_text(adapt(path.read_text(encoding='utf-8')),encoding='utf-8')
