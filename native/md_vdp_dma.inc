/* Authored from documented DMA/IRQ behavior. Included after the FIFO helpers.
 * Access-slot timing is shared with queued writes, never a bulk memory copy.
 * Source fetches and destination writes are separate events on a shared clock.
 * Blanking/source bandwidth is still nominal; pin-level bus acquisition and
 * mid-transfer control-port collisions require further hardware qualification. */
extern void machine_vdp_z80_irq(int asserted);
static uint32_t dma_length(const GVDP *v) {
    uint32_t n=v->reg[19] | ((uint32_t)v->reg[20]<<8);
    return n?n:65536u;
}
static uint32_t dma_source_68k(const GVDP *v) {
    return (v->reg[21] | ((uint32_t)v->reg[22]<<8) |
           ((uint32_t)(v->reg[23]&127)<<16))<<1;
}
static void rr_dma_length_writeback(GVDP *v) {
    uint32_t n=v->rr_dma.remaining;
    v->reg[19]=(uint8_t)n; v->reg[20]=(uint8_t)(n>>8);
}
static void rr_dma_unit_done(GVDP *v) {
    RrMdVdpDma *d=&v->rr_dma;
    d->address=(d->address+d->increment)&65535u; v->address=(uint16_t)d->address;
    --d->remaining; d->half=0; rr_dma_length_writeback(v);
    if(d->mode!=2) {
        unsigned source=d->mode==1?d->source>>1:d->source;
        v->reg[21]=(uint8_t)source; v->reg[22]=(uint8_t)(source>>8);
    }
    if(!d->remaining) { memset(d,0,sizeof *d);v->dma_active=0; }
}
static void rr_dma_retire_slot(GVDP *v) {
    RrMdVdpDma *d=&v->rr_dma;
    if(d->mode==2) {
        v->vram[(d->address^1u)&65535u]=(uint8_t)d->value;
    } else {
        if(!d->half) { d->value=v->vram[d->source&65535u];d->half=1;return; }
        v->vram[d->address&65535u]=(uint8_t)d->value;
        d->source=(d->source+1)&65535u;
    }
    rr_dma_unit_done(v);
}
static void rr_dma_fetch_word(GVDP *v) {
    RrMdVdpDma *d=&v->rr_dma;RrMdVdpFifo *f=&v->rr_fifo;
    RrMdVdpWrite *e=&f->entries[(f->head+f->count)&3];
    memset(e,0,sizeof *e);e->address=(uint16_t)d->address;e->code=(uint8_t)d->code;
    e->value=v->bus_read(v->bus_read_user,d->source);++f->count;
    d->source=(d->source&0xfe0000u)|((d->source+2)&0x1ffffu);
    rr_dma_unit_done(v); /* release the main bus, even with a FIFO tail */
}
/* ABI-4 stored a fetched word directly in the DMA, possibly after its low
 * byte had already reached VRAM. Move that outstanding high byte into the
 * FIFO without another source read. Work only on a validated private copy. */
int gvdp_dma_migrate(GVDP *v) {
    if(!gvdp_timing_valid(v))return 0;
    RrMdVdpDma *d=&v->rr_dma;
    if(d->mode==1 && d->half) {
        if(v->rr_fifo.count)return 0; /* impossible in the previous model */
        RrMdVdpWrite *e=&v->rr_fifo.entries[0];memset(e,0,sizeof *e);
        e->address=(uint16_t)d->address;e->code=(uint8_t)d->code;e->value=(uint16_t)d->value;
        v->rr_fifo.count=1;v->rr_fifo.half=1;
        d->source=(d->source&0xfe0000u)|((d->source+2)&0x1ffffu);
        rr_dma_unit_done(v);
    }
    if(d->mode==1)d->value=0;
    return gvdp_timing_valid(v);
}
/* CPU-visible pending transition at external H=02 in hardware measurements.
 * Pin/latch latency within a pixel is not independently qualified here. */
static unsigned rr_vint_phase(const GVDP *v) { return MODE4_H40(v)?812u:800u; }
static void rr_irq_advance(GVDP *v,unsigned phase) {
    if(!v->rr_irq.vint_stage)return;
    unsigned line=v->scanline, height=(unsigned)gvdp_screen_height(v);
    if(phase<rr_vint_phase(v)) return;
    if(v->rr_irq.vint_stage==1 && line==height) {
        v->vint_pending=1;v->rr_irq.vint_stage=2;machine_vdp_z80_irq(1);
    } else if(v->rr_irq.vint_stage==2 && line==height+1) {
        v->rr_irq.vint_stage=0;machine_vdp_z80_irq(0);
    }
}
static void rr_dma_advance(GVDP *v,unsigned phase,int stop_on_release) {
    RrMdVdpFifo *f=&v->rr_fifo;
    while((f->count || v->rr_dma.remaining
#ifdef RR_MD_TIMED_READ
           || (v->rr_read.state&1u)
#endif
          ) && f->clock<phase) {
        unsigned write=UINT32_MAX,fetch=UINT32_MAX;
        if(f->count || (v->rr_dma.mode>1 && v->rr_dma.remaining))write=rr_fifo_slot(v);
#ifdef RR_MD_TIMED_READ
        unsigned read=(v->rr_read.state&1u) && !f->count?rr_fifo_slot(v):UINT32_MAX;
#endif
        /* The main bus feeds free FIFO entries independently of active-display
         * VRAM availability. Nominal source slots retain the known bandwidth;
         * exact refresh/HSYNC and BR/BG/BGACK edges remain a separate gate. */
        if(v->rr_dma.mode==1 && f->count<4)
            fetch=rr_md_fifo_next_slot(f->clock,MODE4_H40(v),1);
        unsigned next=write<fetch?write:fetch;
#ifdef RR_MD_TIMED_READ
        if(read<next)next=read;
#endif
        if(next>phase)break;
        f->clock=next;rr_irq_advance(v,next);
        /* Older entries win a simultaneous event; a freshly fetched word can
         * never reach VRAM in the very event that accepted it. */
#ifdef RR_MD_TIMED_READ
        if(read==next)rr_read_retire(v);
        else
#endif
        if(write==next) { if(f->count)rr_fifo_retire_slot(v);else rr_dma_retire_slot(v); }
        if(fetch==next && v->rr_dma.mode==1) {
            rr_dma_fetch_word(v);
            if(stop_on_release && !gvdp_dma_blocks_cpu(v))return;
        }
    }
    if(phase>f->clock)f->clock=phase;
    rr_irq_advance(v,f->clock);
}
void gvdp_fifo_advance(GVDP *v,unsigned phase) {
    /* With no queued transaction or pending IRQ edge, only the clock moves.
     * Do not search slots or recompute line geometry for an idle device. */
    if(!v->rr_fifo.count && !v->rr_dma.remaining && !v->rr_irq.vint_stage
#ifdef RR_MD_TIMED_READ
       && !(v->rr_read.state&1u)
#endif
      ) {
        if(phase>v->rr_fifo.clock)v->rr_fifo.clock=phase;
        return;
    }
    rr_dma_advance(v,phase,0);
}
unsigned gvdp_dma_wait_until(GVDP *v,unsigned phase) {
    if(gvdp_dma_blocks_cpu(v))rr_dma_advance(v,phase,1);
    return v->rr_fifo.clock;
}
static void rr_dma_start(GVDP *v,unsigned mode) {
    RrMdVdpDma *d=&v->rr_dma;memset(d,0,sizeof *d);
    d->mode=mode;d->remaining=dma_length(v);d->address=v->address;
    d->increment=REG_AUTOINC(v);d->code=v->code;
    d->source=mode==1?dma_source_68k(v):(v->reg[21]|((uint32_t)v->reg[22]<<8));
    v->dma_active=1;
}
static void dma_run_vram_fill_data(GVDP *v,uint16_t value) {
    /* Normal triggering FIFO word is separate from the byte-fill length. */
    rr_fifo_write(v,value);rr_dma_start(v,2);v->rr_dma.value=value>>8;
    v->dma_fill_pending=0;
}
static void maybe_start_dma(GVDP *v) {
    if(!(v->code&CODE_DMA_BIT))return;
    if(!MODE2_DMA_ON(v))return;
    unsigned mode=v->reg[23]&0xc0;
    if(!(mode&0x80)) {
        if(v->bus_read)rr_dma_start(v,1);
    } else if(!(mode&0x40))v->dma_fill_pending=1;
    else rr_dma_start(v,3);
}
int gvdp_dma_blocks_cpu(const GVDP *v) { return v->rr_dma.mode==1 && v->rr_dma.remaining; }
int gvdp_timing_valid(const GVDP *v) {
    const RrMdVdpDma *d=&v->rr_dma;
    if(d->mode>3 || d->remaining>65536u || d->source>0xffffffu ||
       d->address>65535u || d->increment>255u || d->code>63u || d->half>1 ||
       v->rr_irq.hint_pending>1 || v->rr_irq.vint_stage>2) return 0;
    if((d->mode==0)!=(d->remaining==0) || (!!v->dma_active)!=(d->remaining!=0))return 0;
    if(d->value>(d->mode==1?65535u:255u) || (d->mode==1 && (d->source&1u)) ||
       (d->mode!=1 && d->source>65535u) || (!d->mode && d->half))return 0;
    if(d->half && (d->mode==2 || (d->mode==1 && ((d->code&15u)==3 || (d->code&15u)==5))))return 0;
    return gvdp_fifo_valid(v)
#ifdef RR_MD_TIMED_READ
        && rr_read_valid(v)
#endif
        ;
}
unsigned gvdp_irq_level(const GVDP *v) {
    if(v->vint_pending && MODE2_VINT_ON(v))return 6;
    if(v->rr_irq.hint_pending && MODE1_HINT_ON(v))return 4;
    return 0;
}
void gvdp_irq_ack(GVDP *v,unsigned level) {
    if(level!=4 && level!=6)return;
    /* Sega Software Development Manual, 1991-07-09, p.15: a late V source
     * can acknowledge an entry whose CPU already selected the H vector.
     * The shared VDP acknowledge clears its currently asserted priority,
     * leaving H pending for the next entry. It does not replace the CPU's
     * captured autovector. External/gun acknowledge wiring is separate. */
    unsigned asserted=gvdp_irq_level(v);
    if(asserted==6)v->vint_pending=0;
    else if(asserted==4)v->rr_irq.hint_pending=0;
}
