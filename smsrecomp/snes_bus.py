"""Timed CPU byte phases, DMA divider ownership and beam-positioned refresh.

The instruction core retains its unused internal-cycle padding. Its placement
for every rare instruction is a separate qualification, not an exactness claim.
"""
from .snes_timing import replace


def bridge(source):
    source='#include "snes_bus.h"\n'+source
    # MMIO words must not hide the individual physical byte phases.
    source=replace(source,'    if (!bridge_hw_word(adrl, adrh)) return false;',
        '    return false; /* guest reads use their two timed byte cycles */')
    source=replace(source,'    if (bridge_is_apu_port(adrl) || reversed || !bridge_hw_word(adrl, adrh)) return false;',
        '    return false; /* including ordered/reversed MMIO stores */')
    source=replace(source,'    if (bridge_is_apu_port(adr)) bridge_apu_flush(cpu);',
        '    if(s_interp_bus_timing_active)rr_snes_cpu_read_begin(adr);\n'
        '    if (bridge_is_apu_port(adr)) bridge_apu_flush(cpu);')
    source=replace(source,'    uint8_t value=cpu_read8(cpu,(uint8)((adr>>16)&0xff),(uint16)adr);',
        '    uint8_t mdr=cpu->open_bus;\n'
        '    uint8_t value=cpu_read8(cpu,(uint8)((adr>>16)&0xff),(uint16)adr);\n'
        '    if((adr&0x40fc00u)==0x4000u)cpu->open_bus=mdr;\n'
        '    if(s_interp_bus_timing_active)rr_snes_cpu_read_end();')
    source=replace(source,'    if (is_apu_port) bridge_apu_flush(cpu);\n'
        '    cpu_write8(cpu, (uint8)((adr >> 16) & 0xFF), (uint16)(adr & 0xFFFF), val);',
        '    if(s_interp_bus_timing_active)rr_snes_cpu_write_begin(adr);\n'
        '    if (is_apu_port) bridge_apu_flush(cpu);\n'
        '    cpu_write8(cpu, (uint8)((adr >> 16) & 0xFF), (uint16)(adr & 0xFFFF), val);')
    # No timing or bus-ownership side effects from the bridge's host lookahead.
    source=replace(source,'    const uint64_t volatile_epoch = s_interp_volatile_read_epoch;',
        '    int timing=s_interp_bus_timing_active;s_interp_bus_timing_active=0;\n'
        '    const uint64_t volatile_epoch = s_interp_volatile_read_epoch;')
    source=replace(source,'    s_interp_volatile_read_epoch = volatile_epoch;',
        '    s_interp_volatile_read_epoch = volatile_epoch;s_interp_bus_timing_active=timing;')
    source=replace(source,'        s_interp_bus_timing_active=1;',
        '        s_interp_bus_timing_active=1;rr_snes_cpu_context(true);')
    source=replace(source,'            cpu->master_cycles += _master;',
        '            rr_snes_cpu_idle(_internal);rr_snes_cpu_context(false);')
    return source


def frame_driver(source):
    source=replace(source,'  cpu_push_interrupt_frame_at(&g_cpu, s_resume_pc);',
        '  vector=rr_snes_cpu_interrupt(s_resume_pc,(uint16_t)vector);')
    source=replace(source,'run_interrupt(nmi_vector(), frame_end);',
        'run_interrupt(g_cpu.emulation ? 0xfffau : 0xffeau, frame_end);')
    source=replace(source,'run_interrupt(irq_vector(), frame_end);',
        'run_interrupt(g_cpu.emulation ? 0xfffeu : 0xffeeu, frame_end);')
    return '#include "snes_bus.h"\n'+source


def infrastructure(source):
    start=source.index('void snes_refresh_charge(void) {')
    end=source.index('\n}\n',start)+3
    return source[:start]+'''void snes_refresh_charge(void) {
  /* The live bus pays refresh at its beam edge. Do not also apply the old
   * per-instruction/per-scanline aggregate tax. Keep rollback ABI fields. */
  s_refresh_phase=0;g_refresh_charged_upto=g_cpu.master_cycles;
}
'''+source[end:]


def dma_header(source):
    return replace(source,'  uint8_t rrHdmaRequest;', '''  bool rrCpuContext,rrBusOwned,rrRefreshDone,rrRefreshRequest,rrBusArmed;
  uint8_t rrCpuClock,rrDmaRequest;
  uint64_t rrBusClocks;
  uint32_t rrRefreshEpoch;
  uint8_t rrHdmaRequest;''')


def dma(source):
    source='#include "snes_bus.h"\n'+source
    source=replace(source,'  dma->hdmaPendingInit=0;dma->rrHdmaRequest=0;dma->rrHdmaEpoch=0;',
        '''  dma->hdmaPendingInit=0;dma->rrHdmaRequest=0;dma->rrHdmaEpoch=0;
  dma->rrCpuContext=dma->rrBusOwned=dma->rrRefreshDone=dma->rrRefreshRequest=dma->rrBusArmed=false;
  dma->rrCpuClock=6;dma->rrDmaRequest=0;dma->rrBusClocks=0;dma->rrRefreshEpoch=0;''')
    source=replace(source,'  wire[208]=dma->hdmaPendingInit;wire[209]=dma->rrHdmaRequest;',
        '''  wire[208]=dma->hdmaPendingInit;wire[209]=dma->rrHdmaRequest;
  wire[215]=dma->rrDmaRequest;wire[216]=dma->rrBusArmed;wire[217]=dma->rrCpuClock;
  wire[218]=dma->rrRefreshRequest;wire[219]=dma->rrRefreshDone;''')
    source=replace(source,'  dma->rrHdmaRequest=legacy ? 0 : wire[209];',
        '''  dma->rrHdmaRequest=legacy ? 0 : wire[209];
  dma->rrDmaRequest=legacy ? 0 : wire[215];dma->rrBusArmed=!legacy && wire[216];
  dma->rrCpuClock=legacy ? 6 : wire[217];dma->rrRefreshRequest=!legacy && wire[218];
  dma->rrRefreshDone=!legacy && wire[219];''')
    source=replace(source,'  rr_snes_dma_charge(dma->snes,12);',
        '  rr_snes_dma_charge(dma->snes,dma->rrBusOwned ? 8 : 12);')
    return source+'\n#include "snes_bus.inc"\n'


def bus(source):
    source='#include "snes_bus.h"\n'+source
    source=replace(source,'      uint8_t val = 0x2; // CPU version (4 bit)',
        '      uint8_t val = 0x2 | (g_cpu.open_bus&0x70u); // CPU-v2 and undriven data bits')
    source=replace(source,'      uint8_t val = snes->inIrq << 7;',
        '      uint8_t val = (snes->inIrq << 7) | (g_cpu.open_bus&0x7fu);')
    source=replace(source,'      uint8_t val = (snes->autoJoyTimer > 0);',
        '      uint8_t val = (snes->autoJoyTimer > 0) | (g_cpu.open_bus&0x3eu);')
    source=replace(source,'      rr_snes_dma_run(snes->dma,val);',
        '      rr_snes_dma_request(snes->dma,val);')
    source=replace(source,'      uint32_t edge=(v==0 && h<12u) ? 12u : 1104u;',
        '''      uint32_t setup=12u+(unsigned)((snes->beamMasterLast+consumed-h)&7u);
      uint32_t edge=(v==0 && h<setup) ? setup : 1104u;''')
    source=replace(source,'    if (span > clocks) span = clocks;',
        '''    uint32_t refresh=538u-(unsigned)((snes->beamMasterLast+consumed-h)&7u);
    if(!snes->dma->rrRefreshDone && h<refresh && span>refresh-h)span=refresh-h;
    if (span > clocks) span = clocks;''')
    source=replace(source,'    h += span;\n    clocks -= span;\n    consumed += span;',
        '''    h += span;
    clocks -= span;
    consumed += span;
    if(!snes->dma->rrRefreshDone && h==refresh) {
      snes->dma->rrRefreshDone=true;snes->dma->rrRefreshRequest=true;
      snes->hPos=(uint16_t)h;snes->vPos=(uint16_t)v;snes->inVblank=v>=RR_SN_VBLANK_LINE;
      return consumed;
    }''')
    source=replace(source,'        ((v==0 && h==12u) || h==1104u)) {',
        '        ((v==0 && h==12u+(unsigned)((snes->beamMasterLast+consumed-h)&7u)) || h==1104u)) {')
    source=replace(source,'      snes->dma->rrHdmaRequest=(h==12u ? 2u : 1u);',
        '      snes->dma->rrHdmaRequest=(h<32u ? 2u : 1u);')
    source=replace(source,'      h = 0;\n      v++;',
        '      h = 0;snes->dma->rrRefreshDone=false;\n      v++;')
    source=replace(source,'  rr_snes_hdma_service(snes->dma,false);',
        '  rr_snes_refresh_service(snes->dma);\n  rr_snes_hdma_service(snes->dma,false);')
    source=replace(source,'    uint32_t epoch=snes->dma->rrHdmaEpoch;',
        '    uint32_t epoch=snes->dma->rrHdmaEpoch+snes->dma->rrRefreshEpoch;')
    source=replace(source,'epoch==snes->dma->rrHdmaEpoch &&',
        'epoch==snes->dma->rrHdmaEpoch+snes->dma->rrRefreshEpoch &&')
    source=replace(source,'void rr_snes_dma_charge(Snes *snes,uint32_t clocks) {',
        'void rr_snes_dma_charge(Snes *snes,uint32_t clocks) {\n  snes->dma->rrBusClocks+=clocks;')
    return source


def adapt_engine(staged):
    for name,adapt in (('snes/interp_bridge.c',bridge),('common_cpu_infra.c',infrastructure),
                       ('snes/dma.h',dma_header),('snes/dma.c',dma),('snes/snes.c',bus),('beam_frame_driver.c',frame_driver)):
        path=staged/'runner/src'/name
        path.write_text(adapt(path.read_text(encoding='utf-8')),encoding='utf-8')
