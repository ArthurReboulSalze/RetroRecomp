/* Portable frame-boundary state: canonical machine + missing CPU latches and
 * the already presented frame. Disk integrity/identity/atomic IO is shared. */
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "geo.h"
#include "console16_state.h"
#include "neogeo_host.h"
#include "neogeo_reference.h"
#include "retro_console16.h"
enum { HEADER=32, PIXEL_BYTES=320*224*4, LSPC_EXTRA_BYTES=2592, EXTRA_BYTES=64+LSPC_EXTRA_BYTES };
static void put(uint8_t *p,uint32_t v) {for(unsigned n=0;n<4;++n)p[n]=(uint8_t)(v>>(n*8));}
static uint32_t get(const uint8_t *p) {uint32_t v=0;for(unsigned n=0;n<4;++n)v|=(uint32_t)p[n]<<(n*8);return v;}
bool rr16_state_ready(void) {return true; /* geo_exec retired both CPU instructions. */}
uint8_t *rr16_state_capture(size_t *size) {
    size_t core=geo_state_size();if(!size || !core || core>(2u<<20))return NULL;
    *size=HEADER+core+EXTRA_BYTES+PIXEL_BYTES;
    uint8_t *data=calloc(*size,1);if(!data)return NULL;
    memcpy(data,"RNGSTATE",8);put(data+8,3);put(data+12,(uint32_t)core);put(data+16,rr_ng_frame_index());
    put(data+20,EXTRA_BYTES);put(data+24,PIXEL_BYTES);
    put(data+28,rr_ng_enhanced()?1u:0u);
    memcpy(data+HEADER,geo_state_save_raw(),core);
    if(rr_ng_cpu_extra_save(data+HEADER+core,32)!=32 ||
       rr_ng_ym_extra_save(data+HEADER+core+32,16)!=16 ||
       rr_ng_board_extra_save(data+HEADER+core+48,16)!=16 ||
       rr_ng_lspc_extra_save(data+HEADER+core+64,LSPC_EXTRA_BYTES)!=LSPC_EXTRA_BYTES) {free(data);return NULL;}
    memcpy(data+HEADER+core+EXTRA_BYTES,rr_ng_visible_pixels(),PIXEL_BYTES);return data;
}
bool rr16_state_restore(const uint8_t *data,size_t size) {
    size_t core=geo_state_size();
    if(!data || size!=HEADER+core+EXTRA_BYTES+PIXEL_BYTES || memcmp(data,"RNGSTATE",8) ||
       (get(data+8)!=2 && get(data+8)!=3) || get(data+12)!=core || get(data+20)!=EXTRA_BYTES || get(data+24)!=PIXEL_BYTES ||
       (get(data+8)==2?get(data+28)!=0:get(data+28)>1))return false;
    if(!rr_ng_core_state_valid(data+HEADER,core) || !rr_ng_board_extra_valid(data+HEADER+core+48,16) ||
       !rr_ng_lspc_extra_valid(data+HEADER+core+64,LSPC_EXTRA_BYTES))return false;
    /* The shared file layer has already captured rollback state. Restore
     * additional latches only after validating the complete outer layout. */
    /* Select the clock domain before loading its fractional timer state. Old
     * v2 snapshots were standard-clock only. Shared IO retains rollback state. */
    rr_ng_set_enhanced(get(data+8)==3 && get(data+28)!=0);
    if(!geo_state_load_raw(data+HEADER) || !rr_ng_cpu_extra_restore(data+HEADER+core,32) ||
       !rr_ng_ym_extra_restore(data+HEADER+core+32,16) ||
       !rr_ng_board_extra_restore(data+HEADER+core+48,16) ||
       !rr_ng_lspc_extra_restore(data+HEADER+core+64,LSPC_EXTRA_BYTES))return false;
    rr_ng_restore_frame(get(data+16));
    memcpy(rr_ng_visible_pixels(),data+HEADER+core+EXTRA_BYTES,PIXEL_BYTES);
    extern void rr_ng_audio_discontinuity(void);rr_ng_audio_discontinuity();rr16_host_discontinuity();return true;
}
