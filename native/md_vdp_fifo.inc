/* Included after the private VDP's memory helpers. Authored queue semantics;
 * this slice deliberately leaves bulk DMA and read prefetch timing separate. */
static int rr_fifo_blanked(const GVDP *v, unsigned clock) {
    unsigned line=(v->scanline+clock/RR_MD_MASTER_PER_LINE)%RR_MD_LINES;
    return !MODE2_DISPLAY_ON(v) || line>=(unsigned)gvdp_screen_height(v);
}
static unsigned rr_fifo_slot(const GVDP *v) {
    unsigned after=v->rr_fifo.clock;
    unsigned next=rr_md_fifo_next_slot(after,MODE4_H40(v),rr_fifo_blanked(v,after));
    /* Recompute at a raster boundary if its display availability changes. */
    unsigned edge=(after/RR_MD_MASTER_PER_LINE+1)*RR_MD_MASTER_PER_LINE;
    if (next>=edge && rr_fifo_blanked(v,after)!=rr_fifo_blanked(v,edge))
        next=rr_md_fifo_next_slot(edge,MODE4_H40(v),rr_fifo_blanked(v,edge));
    return next;
}
static void rr_fifo_retire_slot(GVDP *v) {
    RrMdVdpFifo *f=&v->rr_fifo;
    RrMdVdpWrite *e=&f->entries[f->head];
    switch(e->code & 15u) {
    case CODE_CRAM_WRITE: cram_write(v,e->address,e->value); break;
    case CODE_VSRAM_WRITE: vsram_write(v,e->address,e->value); break;
    default: {
        /* Low byte goes to the odd lane for even addresses (odd swaps). */
        unsigned lane=(e->address & 0xfffeu) | ((e->address & 1u) ^ (f->half?0u:1u));
        v->vram[lane]=(uint8_t)(e->value >> (f->half?8:0));
        if(!f->half) { f->half=1; return; }
        break;
    }}
    memset(e,0,sizeof *e); f->head=(f->head+1)&3; --f->count; f->half=0;
    if(!f->count) f->head=0; /* canonical empty snapshot */
}
#ifndef RR_MD_TIMED_DMA
void gvdp_fifo_advance(GVDP *v, unsigned phase) {
    RrMdVdpFifo *f=&v->rr_fifo;
    while(f->count && f->clock<phase) {
        unsigned next=rr_fifo_slot(v);
        if(next>phase) break;
        f->clock=next; rr_fifo_retire_slot(v);
    }
    if(phase>f->clock) f->clock=phase;
}
#endif
static void rr_fifo_sync(GVDP *v) { gvdp_fifo_advance(v,machine_vdp_phase()); }
static void rr_fifo_wait(GVDP *v, unsigned keep) {
    unsigned now=machine_vdp_phase(); rr_fifo_sync(v);
    if(v->rr_fifo.count<=keep) return;
    while(v->rr_fifo.count>keep) {
#ifdef RR_MD_TIMED_DMA
        gvdp_fifo_advance(v,rr_fifo_slot(v)); /* retain IRQ/DMA/read ordering */
#else
        v->rr_fifo.clock=rr_fifo_slot(v); rr_fifo_retire_slot(v);
#endif
    }
    if(v->rr_fifo.clock>now) s_pending_68k_stall+=(v->rr_fifo.clock-now+6u)/7u;
}
static void rr_fifo_write(GVDP *v, uint16_t value) {
    rr_fifo_sync(v);
    if(v->rr_fifo.count==4) rr_fifo_wait(v,3);
    RrMdVdpWrite *e=&v->rr_fifo.entries[(v->rr_fifo.head+v->rr_fifo.count)&3];
    memset(e,0,sizeof *e); e->address=v->address; e->code=v->code; e->value=value;
    ++v->rr_fifo.count;
    v->address=(uint16_t)(v->address+REG_AUTOINC(v));
}
int gvdp_fifo_valid(const GVDP *v) {
    const RrMdVdpFifo *f=&v->rr_fifo;
    if(f->count>4 || f->head>3 || f->half>1 || f->clock>UINT32_MAX-8u*RR_MD_MASTER_PER_LINE) return 0;
    if(!f->count && (f->half || f->head)) return 0;
    if(f->half && ((f->entries[f->head].code&15u)==3 || (f->entries[f->head].code&15u)==5)) return 0;
    return 1;
}
static unsigned rr_fifo_status(const GVDP *v) {
    return (v->rr_fifo.count==0?0x200u:0u) | (v->rr_fifo.count==4?0x100u:0u);
}
