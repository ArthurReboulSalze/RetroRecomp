/* Eight byte-local sprite counters/shifters in parallel, on the same PPU dot.
 * No guest edge or mapper event is skipped. PolyForm Noncommercial:
 * adapted from NESRecomp's shift_sprites; see licenses/nesrecomp.md. */
#ifndef RR_NES_SPRITE_SHIFT_H
#define RR_NES_SPRITE_SHIFT_H
#include <stdint.h>
#include <string.h>
#include <stdbool.h>
#if defined(_MSC_VER) && defined(_M_X64)
#include <intrin.h>
#endif

/* Select the first ready opaque unit using the same priority as the scalar
 * PPU. This is a read-only query: counters, shifters and sprite-zero latches
 * are still updated by their original dot/half-dot paths. */
static inline unsigned rr_nes_sprite_first(const uint8_t *counters,const uint8_t *low,
        const uint8_t *high,bool skipped) {
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
    for(unsigned i=0;i<8;++i)
        if((skipped || !counters[i]) && ((low[i]|high[i])&128))return i;
    return 8;
#else
    uint64_t lo,hi,x;memcpy(&lo,low,8);memcpy(&hi,high,8);
    uint64_t active=(lo|hi)&UINT64_C(0x8080808080808080);
    if(!skipped) {
        memcpy(&x,counters,8);
        const uint64_t lower=UINT64_C(0x7f7f7f7f7f7f7f7f);
        active&=~(((x&lower)+lower)|x);
    }
    if(!active)return 8;
#if defined(_MSC_VER) && defined(_M_X64)
    unsigned long bit;_BitScanForward64(&bit,active);return (unsigned)bit>>3;
#elif defined(__GNUC__) || defined(__clang__)
    return (unsigned)__builtin_ctzll(active)>>3;
#else
    unsigned unit=0;while(!(active&128u)){active>>=8;++unit;}return unit;
#endif
#endif
}

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
