/* Missing YM2610 SSG output divider/held samples, portable frame state.
 * Included in the private pinned ymfm_opn.c adapter, never in upstream. */
static void rr_ng_ym_put32(uint8_t *p,uint32_t v) {for(unsigned n=0;n<4;++n)p[n]=(uint8_t)(v>>(n*8));}
static uint32_t rr_ng_ym_get32(const uint8_t *p) {uint32_t v=0;for(unsigned n=0;n<4;++n)v|=(uint32_t)p[n]<<(n*8);return v;}
size_t rr_ng_ym_extra_save(uint8_t *data,size_t size) {
    if(!data || size<16)return 0;
    rr_ng_ym_put32(data,m_ssg_resampler_sampindex);
    for(unsigned n=0;n<3;++n)rr_ng_ym_put32(data+4+n*4,(uint32_t)m_ssg_resampler_last[n]);
    return 16;
}
bool rr_ng_ym_extra_restore(const uint8_t *data,size_t size) {
    if(!data || size!=16)return false;
    for(unsigned n=0;n<3;++n)if((int32_t)rr_ng_ym_get32(data+4+n*4)<-1048576 ||
        (int32_t)rr_ng_ym_get32(data+4+n*4)>1048576)return false;
    m_ssg_resampler_sampindex=rr_ng_ym_get32(data);
    for(unsigned n=0;n<3;++n)m_ssg_resampler_last[n]=(int32_t)rr_ng_ym_get32(data+4+n*4);
    return true;
}
