/* Eight byte-local sprite counters/shifters in parallel, on the same PPU dot.
 * No guest edge or mapper event is skipped. PolyForm Noncommercial:
 * adapted from NESRecomp's shift_sprites; see licenses/nesrecomp.md. */
#ifndef RR_NES_SPRITE_SHIFT_H
#define RR_NES_SPRITE_SHIFT_H
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
static inline void rr_nes_sprite_shift(uint8_t *counters,uint8_t *low,uint8_t *high,
        bool skipped,bool rendering) {
    uint64_t x,lo,hi;memcpy(&x,counters,8);memcpy(&lo,low,8);memcpy(&hi,high,8);
    if(!(x|lo|hi))return;
    uint64_t ready=UINT64_MAX;
    if(!skipped) {
        const uint64_t lower=UINT64_C(0x7f7f7f7f7f7f7f7f);
        uint64_t nonzero=(((x&lower)+lower)|x)&UINT64_C(0x8080808080808080);
        /* No byte borrows: a decrement is present only for a nonzero byte. */
        x-=nonzero>>7;memcpy(counters,&x,8);
        ready=~((nonzero>>7)*255u);
    }
    if(rendering) {
        lo=(lo&~ready)|(((lo<<1)&UINT64_C(0xfefefefefefefefe))&ready);
        hi=(hi&~ready)|(((hi<<1)&UINT64_C(0xfefefefefefefefe))&ready);
        memcpy(low,&lo,8);memcpy(high,&hi,8);
    }
}
#endif
