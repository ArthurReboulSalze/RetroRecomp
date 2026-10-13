/* Original beam-owned HDMA engine. Contracts consulted: ares SFC CPU DMA
 * and Snes9x DMA. No external emulator source or firmware is embedded.
 * Byte edges are timed; exact CPU divider launch/release remains separate. */
static bool rr_dma_running,rr_hdma_running;

static uint8_t rr_hdma_read(Dma *dma,DmaChannel *ch) {
  uint32_t address=((uint32_t)ch->aBank<<16)|ch->tableAdr;
  if(rr_dma_clocked)rr_snes_dma_charge(dma->snes,4);
  uint8_t value=rr_snes_dma_valid_a(address) ? snes_read(dma->snes,address) : 0;
  g_cpu.open_bus=value;
  if(rr_dma_clocked)rr_snes_dma_charge(dma->snes,4);
  return value;
}
static void rr_hdma_reload(Dma *dma,unsigned index) {
  DmaChannel *ch=&dma->channel[index];
  /* The table bus read also occurs on rows which do not reload the counter.
   * It costs eight clocks and updates MDR without moving the table cursor. */
  uint8_t count=rr_hdma_read(dma,ch);
  if(ch->repCount&127)return;
  ch->tableAdr++;ch->repCount=count;ch->terminated=count==0;
  ch->doTransfer=!ch->terminated;
  if(!ch->indirect)return;
  uint8_t low=rr_hdma_read(dma,ch);ch->tableAdr++;
  ch->size=(uint16_t)low<<8;
  bool later=false;
  for(unsigned n=index+1;n<8;n++)
    if(dma->channel[n].hdmaActive && !dma->channel[n].terminated)later=true;
  /* A terminating last indirect channel reads only the first pointer byte.
   * Earlier terminating channels read both bytes before the next channel. */
  if(ch->terminated && !later)return;
  uint8_t high=rr_hdma_read(dma,ch);ch->tableAdr++;
  ch->size=((uint16_t)high<<8)|low;
}
static void rr_hdma_setup(Dma *dma) {
  for(unsigned n=0;n<8;n++) {
    DmaChannel *ch=&dma->channel[n];
    ch->terminated=false;ch->doTransfer=false;
  }
  for(unsigned n=0;n<8;n++) {
    DmaChannel *ch=&dma->channel[n];if(!ch->hdmaActive)continue;
    dma->hdmaPendingInit&=(uint8_t)~(1u<<n);
    ch->dmaActive=false;ch->tableAdr=ch->aAdr;ch->repCount=0;
    rr_hdma_reload(dma,n);ch->offIndex=0;
  }
}
static void rr_hdma_line(Dma *dma) {
  uint8_t reload=0;
  /* All payloads precede the channels' counter/table-read phase. */
  for(unsigned n=0;n<8;n++) {
    DmaChannel *ch=&dma->channel[n];if(!ch->hdmaActive)continue;
    if(dma->hdmaPendingInit&(1u<<n)) {
      dma->hdmaPendingInit&=(uint8_t)~(1u<<n);
      ch->dmaActive=false;ch->tableAdr=ch->aAdr;ch->repCount=0;
      rr_hdma_reload(dma,n);ch->offIndex=0;continue;
    }
    if(ch->terminated)continue;
    ch->dmaActive=false;reload|=(uint8_t)(1u<<n);
    if(!ch->doTransfer)continue;
    for(unsigned b=0;b<(unsigned)transferLength[ch->mode&7];b++) {
      uint8_t saved=g_ppu_wlog_src;g_ppu_wlog_src=kPpuWlogHdma;
      uint16_t address=ch->indirect ? ch->size++ : ch->tableAdr++;
      dma_transferByte(dma,address,ch->indirect ? ch->indBank : ch->aBank,
          (uint8_t)(ch->bAdr+bAdrOffsets[ch->mode&7][b]),ch->fromB,(int)n);
      g_ppu_wlog_src=saved;
    }
  }
  for(unsigned n=0;n<8;n++)if(reload&(1u<<n)) {
    DmaChannel *ch=&dma->channel[n];ch->repCount--;
    ch->doTransfer=(ch->repCount&128)!=0;rr_hdma_reload(dma,n);
  }
}
bool rr_snes_hdma_service(Dma *dma,bool dma_boundary) {
  if(!dma->rrHdmaRequest || rr_hdma_running ||
      ((rr_dma_running || dma->rrCpuContext || dma->rrBusOwned) && !dma_boundary))return false;
  uint8_t request=dma->rrHdmaRequest;dma->rrHdmaRequest=0;
  /* Mark even an empty edge as serviced: synchronization must continue the
   * original clock debt, rather than treating it as an IRQ preemption. */
  dma->rrHdmaEpoch++;
  bool any=false;
  for(unsigned n=0;n<8;n++)if(dma->channel[n].hdmaActive &&
      (request==2 || !dma->channel[n].terminated ||
       (dma->hdmaPendingInit&(1u<<n))))any=true;
  if(!any) {
    if(request==2)rr_hdma_setup(dma);
    return false;
  }
  bool clocked=rr_dma_clocked;rr_dma_clocked=true;rr_hdma_running=true;
  /* A parked CPU may already carry a whole scanline of beam debt. Anchor
   * HDMA to the edge just reached, rather than stamping its first write at
   * the parked target (which delayed every split by one visible row). */
  uint64_t debt=g_cpu.master_cycles>dma->snes->beamMasterLast ?
      g_cpu.master_cycles-dma->snes->beamMasterLast : 0;
  g_cpu.master_cycles-=debt;
  rr_snes_dma_charge(dma->snes,8);
  if(request==2)rr_hdma_setup(dma);else rr_hdma_line(dma);
  g_cpu.master_cycles+=debt;
  rr_hdma_running=false;rr_dma_clocked=clocked;
  return true;
}
