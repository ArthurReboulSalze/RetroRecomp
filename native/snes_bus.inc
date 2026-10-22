/* Original cycle-phase bus controller. Both instruction selection paths
 * enter here; disassembly/guard peeks are explicitly outside guest time. */
void rr_snes_cpu_context(bool active) { g_snes->dma->rrCpuContext=active; }
static void rr_sn_cpu_edge(unsigned clocks) {
  Dma *dma=g_snes->dma;dma->rrCpuClock=(uint8_t)clocks;
  bool request=dma->rrDmaRequest || dma->rrHdmaRequest;
  if(dma->rrBusArmed && request) {
    dma->rrBusOwned=true;
    uint64_t debit=dma->rrBusClocks;
    rr_snes_dma_charge(g_snes,8u-(unsigned)(g_cpu.master_cycles&7u));
    rr_snes_hdma_service(dma,true);
    uint8_t mask=dma->rrDmaRequest;dma->rrDmaRequest=0;
    if(mask)rr_snes_dma_run(dma,mask);
    unsigned used=(unsigned)((dma->rrBusClocks-debit)%clocks);
    rr_snes_dma_charge(g_snes,clocks-used);
    dma->rrBusOwned=false;dma->rrBusArmed=false;
  }
  /* The first request edge lets one full CPU cycle finish before ownership
   * changes. A new HDMA request during release gets the same handshake. */
  if(dma->rrDmaRequest || dma->rrHdmaRequest)dma->rrBusArmed=true;
}
void rr_snes_cpu_read_begin(uint32_t address) {
  unsigned clocks=cpu_region_speed(address);rr_sn_cpu_edge(clocks);
  rr_snes_dma_charge(g_snes,clocks-4u);
}
void rr_snes_cpu_read_end(void) { rr_snes_dma_charge(g_snes,4); }
void rr_snes_cpu_write_begin(uint32_t address) {
  unsigned clocks=cpu_region_speed(address);rr_sn_cpu_edge(clocks);
  rr_snes_dma_charge(g_snes,clocks);
}
void rr_snes_cpu_idle(unsigned cycles) {
  while(cycles--) { rr_sn_cpu_edge(6);rr_snes_dma_charge(g_snes,6); }
}
void rr_snes_dma_request(Dma *dma,uint8_t mask) {
  if(dma->rrCpuContext)dma->rrDmaRequest=mask;
  else rr_snes_dma_run(dma,mask); // direct hardware fixtures/non-CPU clients
}
/* HDMA raised in the CPU's last bus cycle waits for its next edge. A CPU
 * parked on WAI or a poll has none: HDMA takes the bus where the beam stands,
 * rather than after parked time has walked on to the next line's refresh
 * (Donkey Kong Country's colour 0/1 split then reached CGRAM mid-line). */
void rr_snes_parked_hdma(void) {
  Dma *dma=g_snes->dma;
  if(!dma->rrHdmaRequest || !rr_snes_hdma_service(dma,true))return;
  if(!dma->rrDmaRequest)dma->rrBusArmed=false;
}
void rr_snes_refresh_service(Dma *dma) {
  if(!dma->rrRefreshRequest)return;
  dma->rrRefreshRequest=false;
  dma->rrRefreshEpoch++;
  if(!dma->rrCpuContext && !rr_dma_running && !rr_hdma_running)return;
  /* Refresh holds physical time, but is not another DMA transfer cycle.
   * Do not include these 40 clocks in the CPU-release divider debit. */
  uint64_t debt=g_cpu.master_cycles>dma->snes->beamMasterLast ?
      g_cpu.master_cycles-dma->snes->beamMasterLast : 0;
  uint64_t before=dma->rrBusClocks;
  g_cpu.master_cycles-=debt;
  rr_snes_dma_charge(dma->snes,40);
  dma->rrBusClocks=before;
  g_cpu.master_cycles+=debt;
}
uint32_t rr_snes_cpu_interrupt(uint32_t pc,uint16_t vector) {
  rr_snes_cpu_context(true);
  rr_snes_cpu_read_begin(pc);(void)cpu_read8(&g_cpu,(uint8_t)(pc>>16),(uint16_t)pc);rr_snes_cpu_read_end();
  rr_snes_cpu_idle(1);cpu_mirrors_to_p(&g_cpu);
  uint8_t frame[4]={(uint8_t)(pc>>16),(uint8_t)(pc>>8),(uint8_t)pc,g_cpu.P};
  if(g_cpu.emulation)frame[3]&=(uint8_t)~16u; // emulation IRQ/NMI pushes B clear
  for(unsigned n=g_cpu.emulation?1:0;n<4;n++) {
    rr_snes_cpu_write_begin(g_cpu.S);cpu_write8(&g_cpu,0,g_cpu.S,frame[n]);
    g_cpu.S=(uint16_t)(g_cpu.S-1);
    if(g_cpu.emulation)g_cpu.S=0x100u|(g_cpu.S&255u);
  }
  g_cpu._flag_I=1;g_cpu._flag_D=0;g_cpu.PB=0;cpu_mirrors_to_p(&g_cpu);
  rr_snes_cpu_read_begin(vector);uint8_t low=cpu_read8(&g_cpu,0,vector);rr_snes_cpu_read_end();
  rr_snes_cpu_read_begin(vector+1u);uint8_t high=cpu_read8(&g_cpu,0,(uint16_t)(vector+1u));rr_snes_cpu_read_end();
  g_cpu.cycles+=g_cpu.emulation?7:8;g_cpu.coprocessor_master_cycles=g_cpu.master_cycles;
  rr_snes_cpu_context(false);return low|((uint32_t)high<<8);
}
