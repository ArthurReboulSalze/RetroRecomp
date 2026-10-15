/* Frame-boundary sprite pipeline omitted by the pinned LSPC serializer.
 * Original RetroRecomp contributions: MIT. Palette indices, no host pointers. */
#include <stdbool.h>
#include <string.h>
enum { RR_NG_LSPC_EXTRA_BYTES=32+2*LSPC_WIDTH*4 };
static uint32_t rr_lspc_get32(const uint8_t *data) {
    return (uint32_t)data[0]|((uint32_t)data[1]<<8)|((uint32_t)data[2]<<16)|((uint32_t)data[3]<<24);
}
static void rr_lspc_put32(uint8_t *data,uint32_t value) {
    for(unsigned n=0;n<4;++n)data[n]=(uint8_t)(value>>(8*n));
}
size_t rr_ng_lspc_extra_save(uint8_t *data,size_t size) {
    if(!data || size<RR_NG_LSPC_EXTRA_BYTES)return 0;
    memset(data,0,RR_NG_LSPC_EXTRA_BYTES);memcpy(data,"NGL1",4);
    rr_lspc_put32(data+4,lbactive);rr_lspc_put32(data+8,reg_disblspr);
    rr_lspc_put32(data+12,reg_disblfix);rr_lspc_put32(data+16,reg_envideo);
    for(unsigned row=0;row<2;++row)for(unsigned x=0;x<LSPC_WIDTH;++x)
        rr_lspc_put32(data+32+(row*LSPC_WIDTH+x)*4,linebuf[row][x]);
    return RR_NG_LSPC_EXTRA_BYTES;
}
bool rr_ng_lspc_extra_valid(const uint8_t *data,size_t size) {
    if(!data || size!=RR_NG_LSPC_EXTRA_BYTES || memcmp(data,"NGL1",4) || rr_lspc_get32(data+4)>1)return false;
    for(unsigned n=20;n<32;++n)if(data[n])return false;
    for(unsigned n=32;n<RR_NG_LSPC_EXTRA_BYTES;n+=4)
        if(rr_lspc_get32(data+n)>=SIZE_8K)return false;
    return true;
}
bool rr_ng_lspc_extra_restore(const uint8_t *data,size_t size) {
    if(!rr_ng_lspc_extra_valid(data,size))return false;
    lbactive=rr_lspc_get32(data+4);reg_disblspr=rr_lspc_get32(data+8);
    reg_disblfix=rr_lspc_get32(data+12);reg_envideo=rr_lspc_get32(data+16);
    for(unsigned row=0;row<2;++row)for(unsigned x=0;x<LSPC_WIDTH;++x)
        linebuf[row][x]=rr_lspc_get32(data+32+(row*LSPC_WIDTH+x)*4);
    return true;
}
