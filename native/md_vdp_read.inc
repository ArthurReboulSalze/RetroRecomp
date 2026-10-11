/* Authored read-buffer model from Kabuto's hardware notes and Nemesis's
 * VRAM bus measurements. CPU VRAM reads use two byte slots; internal serial
 * tile reads are a different operation. CRAM/VSRAM read a word per slot.
 * Older FIFO writes take priority. Exact read/write pipeline overlap and
 * control-port address collisions during prefetch remain unqualified. */
static int rr_read_code(unsigned code) {
    return code==CODE_VRAM_READ || code==CODE_CRAM_READ || code==CODE_VSRAM_READ;
}
static void rr_read_cancel(GVDP *v) { memset(&v->rr_read,0,sizeof v->rr_read); }
static void rr_read_start(GVDP *v) {
    rr_read_cancel(v);
    if(!rr_read_code(v->code))return;
    v->rr_read.address=v->address;v->rr_read.code=v->code;v->rr_read.state=1;
}
static uint16_t rr_read_memory(const GVDP *v,unsigned code,unsigned address) {
    if(code==CODE_CRAM_READ)return v->cram[(address>>1)&(GVDP_CRAM_ENTRIES-1)];
    if(code==CODE_VSRAM_READ) {
        unsigned i=address>>1;return i<GVDP_VSRAM_ENTRIES?v->vsram[i]:0;
    }
    return vram_read_word(v,(uint16_t)address);
}
static void rr_read_retire(GVDP *v) {
    RrMdVdpRead *r=&v->rr_read;
    if(r->code==CODE_VRAM_READ) {
        unsigned address=r->address&65534u;
        if(r->state==1) { r->value=(unsigned)v->vram[address]<<8;r->state=3;return; }
        r->value|=v->vram[address+1];
    } else r->value=rr_read_memory(v,r->code,r->address);
    r->state=2;
    v->address=(uint16_t)(r->address+REG_AUTOINC(v));
}
static int rr_read_valid(const GVDP *v) {
    const RrMdVdpRead *r=&v->rr_read;
    if(r->state>3 || r->address>65535u || r->value>65535u)return 0;
    if(!r->state)return !r->address && !r->value && !r->code;
    return rr_read_code(r->code) && (r->state!=1 || !r->value) &&
        (r->state!=3 || (r->code==CODE_VRAM_READ && !(r->value&255u)));
}
static uint16_t rr_read_data(GVDP *v) {
    unsigned now=machine_vdp_phase();rr_fifo_sync(v);v->control_pending=0;
    if(!v->rr_read.state)rr_read_start(v); /* also qualified old-state loads */
    while(v->rr_read.state&1u)gvdp_fifo_advance(v,rr_fifo_slot(v));
    if(v->rr_fifo.clock>now)s_pending_68k_stall+=(v->rr_fifo.clock-now+6u)/7u;
    uint16_t out=(uint16_t)v->rr_read.value;
    rr_read_start(v); /* next fetch is asynchronous, never consumed here */
    return out;
}
