"""Beam-owned DMA/HDMA, with presentation replay isolated from the guest bus.

Byte boundaries arbitrate the bus; CPU divider launch/release remains unqualified.
"""
from .snes_timing import replace


def bus(source):
    start=source.index('      {\n        uint64_t dma_master = 12;')
    end=source.index('      break;\n    }\n    case 0x420c:',start)
    source=source[:start]+'''      rr_snes_dma_run(snes->dma,val);
'''+source[end:]
    source=replace(source,'''    if (check_irq && v < RR_SN_VBLANK_LINE && h < 1024u && span > 1024u - h)
      span = 1024u - h;''','''    if(check_irq && !snes->hdmaBeamOff) {
      uint32_t edge=(v==0 && h<12u) ? 12u : 1104u;
      if(v<RR_SN_VBLANK_LINE && h<edge && span>edge-h)span=edge-h;
    }''')
    source=replace(source,'''    if (check_irq && !snes->hdmaBeamOff && v < RR_SN_VBLANK_LINE && h == 1024u)
      dma_doHdma(snes->dma);''','''    if(check_irq && !snes->hdmaBeamOff && v<RR_SN_VBLANK_LINE &&
        ((v==0 && h==12u) || h==1104u)) {
      snes->dma->rrHdmaRequest=(h==12u ? 2u : 1u);
      snes->hPos=(uint16_t)h;snes->vPos=(uint16_t)v;
      snes->inVblank=false;
      return consumed;
    }''')
    source=replace(source,'''        if (check_irq && !snes->hdmaBeamOff)
          dma_initHdma(snes->dma);''','')
    source=replace(source,'  snes->beamMasterLast += consumed;',
        '  snes->beamMasterLast += consumed;\n  rr_snes_hdma_service(snes->dma,false);')
    start=source.index('void snes_sync_master_clock(Snes *snes, uint64_t master_clock) {')
    end=source.index('\nuint8_t snes_readReg',start)
    source=source[:start]+'''void snes_sync_master_clock(Snes *snes,uint64_t master_clock) {
  if(s_beam_hold)return;
  if(master_clock<snes->beamMasterLast) {snes->beamMasterLast=master_clock;return;}
  while(snes->beamMasterLast<master_clock) {
    uint64_t delta=master_clock-snes->beamMasterLast;
    uint32_t chunk=delta>UINT32_MAX ? UINT32_MAX : (uint32_t)delta;
    uint64_t before=snes->beamMasterLast,cpu_before=g_cpu.master_cycles;
    uint32_t epoch=snes->dma->rrHdmaEpoch;
    snes_advance_master_cycles(snes,chunk);
    /* HDMA adds guest stall time to the same clock. Recompute the debt;
     * subtracting a larger walk from the old delta underflows uint64_t. */
    if(g_cpu.master_cycles>cpu_before)master_clock+=g_cpu.master_cycles-cpu_before;
    if(snes->beamMasterLast==before)break;
    if(snes->beamMasterLast-before<chunk && epoch==snes->dma->rrHdmaEpoch &&
        !snes->dma->rrHdmaRequest)break; // IRQ yields at the next CPU boundary
  }
}
''' +source[end:]
    return '#include "snes_dma.h"\n'+source+'''
void rr_snes_dma_charge(Snes *snes,uint32_t clocks) {
  if(s_master_clock_charge_hook) {
    s_master_clock_charge_hook(snes,clocks);
    /* IRQ latches are retained, but DMA cannot be interrupted by a CPU
     * handler. Walk the remaining bus debt before the next device access. */
    uint64_t target=snes->beamMasterLast;
    if(snes->cart && snes->cart->masterClock) target=*snes->cart->masterClock;
    for(unsigned n=0;n<2048 && snes->beamMasterLast<target;n++) {
      uint64_t before=snes->beamMasterLast;
      snes_sync_master_clock(snes,target);
      if(snes->beamMasterLast==before)break;
    }
  } else snes_advance_master_cycles(snes,clocks);
  if(snes->cart && snes->cart->masterClock)
    cart_sync_coprocessors(snes->cart,*snes->cart->masterClock);
}
'''


def dma(source):
    source='#include "snes_dma.h"\nstatic bool rr_dma_clocked;\n'+source
    marker='  if (fromB) {\n    snes_write(dma->snes, (aBank << 16) | aAdr, snes_readBBus(dma->snes, bAdr));'
    source=replace(source,marker,'''  uint32_t address=((uint32_t)aBank<<16)|aAdr;
  bool valid_a=rr_snes_dma_valid_a(address);
  bool valid_b=rr_snes_dma_valid_b(address,bAdr);
  if(rr_dma_clocked)rr_snes_dma_charge(dma->snes,4);
  if (fromB) {
    uint8_t value=valid_b ? snes_readBBus(dma->snes,bAdr) : 0;
    g_cpu.open_bus=value;
    if(rr_dma_clocked)rr_snes_dma_charge(dma->snes,4);
    if(valid_a)snes_write(dma->snes,address,value);''')
    source=replace(source,'    val = snes_read(dma->snes, (aBank << 16) | aAdr);',
        '    val = valid_a ? snes_read(dma->snes,address) : 0;\n'
        '    g_cpu.open_bus=val;\n'
        '    if(rr_dma_clocked)rr_snes_dma_charge(dma->snes,4);')
    source=replace(source,'    snes_writeBBus(dma->snes, bAdr, val);',
        '    if(valid_b)snes_writeBBus(dma->snes,bAdr,val);',count=2)
    source=replace(source,'        debug_server_on_reg_write((uint16_t)(0x2100u + bAdr), val);',
        '        g_cpu.open_bus=val;\n        if(rr_dma_clocked)rr_snes_dma_charge(dma->snes,4);\n'
        '        debug_server_on_reg_write((uint16_t)(0x2100u + bAdr), val);')
    # HDMA has the same direction bit and A/B-bus exclusions as DMA.
    source=replace(source,'bAdr, false, i);','bAdr, ch->fromB, i);',count=4)
    start=source.index('static void dma_hdmaLoadDescriptor(')
    end=source.index('/* ── HDMA',start)
    source=source[:start]+'''#include "snes_hdma.inc"
void dma_initHdma(Dma *dma) { rr_hdma_setup(dma); }
void dma_doHdma(Dma *dma) { rr_hdma_line(dma); }
void dma_primeHdmaFirstLine(Dma *dma) { rr_hdma_line(dma); }
''' +source[end:]
    source=replace(source,'  dma->hdmaPendingInit = 0;',
        '  dma->hdmaPendingInit=0;dma->rrHdmaRequest=0;dma->rrHdmaEpoch=0;')
    source=replace(source,'  sli->func(sli, wire, legacy ? 216 : sizeof(wire));',
        '''  wire[208]=dma->hdmaPendingInit;wire[209]=dma->rrHdmaRequest;
  sli->func(sli, wire, legacy ? 216 : sizeof(wire));
  dma->hdmaPendingInit=legacy ? 0 : wire[208];
  dma->rrHdmaRequest=legacy ? 0 : wire[209];''')
    return source+'''
void rr_snes_dma_run(Dma *dma,uint8_t mask) {
  if(!mask)return;
  dma_startDma(dma,mask,false);
  rr_dma_clocked=true;rr_dma_running=true;
  /* Preserve the qualified startup until CPU-divider phases are measured. */
  rr_snes_dma_charge(dma->snes,12);
  rr_snes_hdma_service(dma,true);
  for(unsigned i=0;i<8;i++) {
    DmaChannel *ch=&dma->channel[i];
    if(!ch->dmaActive)continue;
    rr_snes_dma_charge(dma->snes,8);
    rr_snes_hdma_service(dma,true);
    ch->offIndex=0;
    while(ch->dmaActive) {
      g_ppu_wlog_src=kPpuWlogDma;
      dma_transferByte(dma,ch->aAdr,ch->aBank,
          (uint8_t)(ch->bAdr+bAdrOffsets[ch->mode&7][ch->offIndex++&3]),ch->fromB,i);
      g_ppu_wlog_src=kPpuWlogCpu;
      if(!ch->fixed)ch->aAdr+=ch->decrement ? -1 : 1;
      if(--ch->size==0)ch->dmaActive=false;
      /* HDMA either pauses another channel or cancels this channel.
       * Its indirect pointer shares DAS: do not decrement it afterwards. */
      rr_snes_hdma_service(dma,true);
    }
    ch->offIndex=0;
  }
  dma->dmaTimer=0;dma->dmaBusy=false;rr_dma_running=false;rr_dma_clocked=false;
}
'''


def dma_header(source):
    return replace(source,'  bool dmaBusy;','''  bool dmaBusy;
  uint8_t rrHdmaRequest; // 1=HBlank, 2=field initialization
  uint32_t rrHdmaEpoch; // host synchronization marker, not guest state
''')


def frame_driver(source):
    source=replace(source,'  snes_set_hdma_beam_enabled(g_snes, false);',
        '  snes_set_hdma_beam_enabled(g_snes, true);',count=2)
    source=replace(source,'  dma_initHdma(g_snes->dma);','')
    source=replace(source,'  dma_primeHdmaFirstLine(g_snes->dma);','')
    source=replace(source,'    if (ppu_rasterTakeHdmaen(&hdmaen))\n      dma_startDma(g_snes->dma, hdmaen, true);','')
    source=replace(source,'    dma_doHdma(g_snes->dma);','')
    return source


def ppu(source):
    marker='uint8_t ppu_read(Ppu* ppu, uint8_t adr) {'
    source=replace(source,marker,'''static unsigned rr_sn_replay_line;
static bool rr_sn_vram_access(Ppu *ppu) {
  return PPU_forcedBlank(ppu) || !g_snes ||
      (g_ppu_wlog_src==kPpuWlogReplay ? rr_sn_replay_line : g_snes->vPos) >=
          (ppu->frameOverscan ? 240u : 225u);
}
static uint16_t rr_sn_vram_read(Ppu *ppu) {
  return rr_sn_vram_access(ppu) ? ppu->vram[ppu_getVramRemap(ppu)&0x7fff] : 0;
}
'''+marker)
    source=replace(source,'ppu->vramReadBuffer = ppu->vram[ppu_getVramRemap(ppu) & 0x7fff];',
        'ppu->vramReadBuffer = rr_sn_vram_read(ppu);',count=4)
    source=replace(source,'      // TODO: vram access during rendering (also cgram and oam)',
        '      if(!rr_sn_vram_access(ppu)) {\n'
        '        if(!ppu->vramIncrementOnHigh)ppu->vramPointer+=ppu->vramIncrement;\n'
        '        break;\n      }')
    source=replace(source,'    case 0x19: {\n      uint16_t vramAdr',
        '    case 0x19: {\n      if(!rr_sn_vram_access(ppu)) {\n'
        '        if(ppu->vramIncrementOnHigh)ppu->vramPointer+=ppu->vramIncrement;\n'
        '        break;\n      }\n      uint16_t vramAdr')
    # Replay the values already put on the B bus, never the live HDMA tables.
    # Palette and memory-port writes need their initial memories and latches.
    source=replace(source,'#define PPU_RASTER_MAX 4096',
        '''#define PPU_RASTER_MAX 131072
#define RR_SN_PORT_BYTES (offsetof(Ppu,timeOver)-offsetof(Ppu,vramPointer))
static uint8_t rr_sn_live_regs[PPU_SAVESTATE_REGS_SIZE];
static uint8_t rr_sn_live_mem[PPU_SAVESTATE_MEM_SIZE];
static uint8_t rr_sn_live_ports[RR_SN_PORT_BYTES];
static uint8_t rr_sn_live_scroll[3];''')
    source=replace(source,'  uint8_t regs[PPU_SAVESTATE_REGS_SIZE];',
        '''  uint8_t mem[PPU_SAVESTATE_MEM_SIZE],ports[RR_SN_PORT_BYTES];
  uint8_t regs[PPU_SAVESTATE_REGS_SIZE];''')
    start=source.index('  switch (reg) {',source.index('static int raster_reg_journaled('))
    end=source.index('\n}\n',start)
    source=source[:start]+'  return 1;'+source[end:]
    source=replace(source,'  memcpy(f->regs, &ppu->inidisp, PPU_SAVESTATE_REGS_SIZE);',
        '''  memcpy(f->regs, &ppu->inidisp, PPU_SAVESTATE_REGS_SIZE);
  memcpy(f->mem,&ppu->cgram,PPU_SAVESTATE_MEM_SIZE);
  memcpy(f->ports,&ppu->vramPointer,RR_SN_PORT_BYTES);''')
    source=replace(source,'  s_raster_port.oamAdr = ppu->oamAdr;',
        '''  memcpy(rr_sn_live_regs,&ppu->inidisp,sizeof rr_sn_live_regs);
  memcpy(rr_sn_live_mem,&ppu->cgram,sizeof rr_sn_live_mem);
  memcpy(rr_sn_live_ports,&ppu->vramPointer,sizeof rr_sn_live_ports);
  rr_sn_live_scroll[0]=ppu->scrollPrev;rr_sn_live_scroll[1]=ppu->scrollPrev2;
  rr_sn_live_scroll[2]=ppu->m7prev;
  memcpy(&ppu->cgram,f->mem,sizeof f->mem);
  memcpy(&ppu->vramPointer,f->ports,sizeof f->ports);
  s_raster_port.oamAdr = ppu->oamAdr;''')
    source=replace(source,'      raster_replay(ppu, reg, val);',
        '      rr_sn_replay_line=f->e[s_raster_next].key % (RR_SN_LINES+1u);\n'
        '      raster_replay(ppu, reg, val);')
    start=source.index('  if (s_raster_have_completed) {',source.index('void ppu_rasterRenderEnd('))
    end=source.index('\n}\n',start)
    source=source[:start]+'''  memcpy(&ppu->inidisp,rr_sn_live_regs,sizeof rr_sn_live_regs);
  memcpy(&ppu->cgram,rr_sn_live_mem,sizeof rr_sn_live_mem);
  memcpy(&ppu->vramPointer,rr_sn_live_ports,sizeof rr_sn_live_ports);
  ppu->scrollPrev=rr_sn_live_scroll[0];ppu->scrollPrev2=rr_sn_live_scroll[1];
  ppu->m7prev=rr_sn_live_scroll[2];
'''+source[end:]
    return source


def adapt_engine(staged):
    for name,adapt in (('snes',bus),('dma',dma),('ppu',ppu)):
        path=staged/f'runner/src/snes/{name}.c'
        path.write_text(adapt(path.read_text(encoding='utf-8')),encoding='utf-8')
    for name,adapt in (('snes/dma.h',dma_header),('beam_frame_driver.c',frame_driver)):
        path=staged/'runner/src'/name
        path.write_text(adapt(path.read_text(encoding='utf-8')),encoding='utf-8')
