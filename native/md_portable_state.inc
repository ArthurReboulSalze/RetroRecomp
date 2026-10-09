/* Included in the engine's private rb_state.c. The exec section is an
 * in-process fiber stack and is deliberately excluded from disk snapshots. */
extern void rr_md_portable_restart(uint32_t pc);
extern void rr_md_portable_arm(uint32_t pc);
size_t rr_md_portable_bound(void) {
    size_t n=8;
    for (size_t i=1; i<RB_NSEC; ++i) n+=4+k_sections[i].save(NULL,0);
    return n;
}
size_t rr_md_portable_save(void *data, size_t capacity) {
    if (!data || capacity<rr_md_portable_bound()) return 0;
    uint8_t *p=data; uint32_t count=RB_NSEC-1;
    memcpy(p,"MPS1",4); memcpy(p+4,&count,4); p+=8;
    for (size_t i=1; i<RB_NSEC; ++i) {
        size_t need=k_sections[i].save(NULL,0);
        uint32_t got=need ? (uint32_t)k_sections[i].save(p+4,need) : 0;
        if (got!=need) return 0;
        memcpy(p,&got,4); p+=4+got;
    }
    return p-(uint8_t *)data;
}
int rr_md_portable_load(const void *data, size_t size) {
    if (!data || size<8 || memcmp(data,"MPS1",4)) return 0;
    const uint8_t *p=(const uint8_t *)data+8, *end=(const uint8_t *)data+size;
    uint32_t count; memcpy(&count,(const uint8_t *)data+4,4);
    if (count!=RB_NSEC-1) return 0;
    const uint8_t *sections[RB_NSEC]; uint32_t sizes[RB_NSEC];
    for (size_t i=1; i<RB_NSEC; ++i) {
        if (end-p<4) return 0;
        memcpy(&sizes[i],p,4); p+=4;
        if (sizes[i]>(size_t)(end-p)) return 0;
        /* Audio queues have variable pending-sample counts. Their own loaders
         * validate those counts before accessing or copying the payload. */
        if (i<5 && sizes[i]!=k_sections[i].save(NULL,0)) return 0;
        sections[i]=p; p+=sizes[i];
    }
    if (p!=end) return 0;
    /* Restart first, then restore all scheduler residues it clears. */
    rr_md_portable_restart(1);
    for (size_t i=1; i<RB_NSEC; ++i)
        if (!k_sections[i].load(sections[i],sizes[i])) return 0;
    rr_md_portable_arm(g_cpu.PC);
    return 1;
}
