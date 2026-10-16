/* Exact packed tile rows and SSE2 layer composition. Guest sprite evaluation,
 * VRAM fetch timing and palette state stay in the production VDP. */
#ifndef RR_MD_REFERENCE_PIXELS
#define RR_MD_REFERENCE_PIXELS 0
#endif
static inline uint64_t rr_md_reverse_bytes(uint64_t v) {
    v=((v>>8)&UINT64_C(0x00ff00ff00ff00ff))|((v&UINT64_C(0x00ff00ff00ff00ff))<<8);
    v=((v>>16)&UINT64_C(0x0000ffff0000ffff))|((v&UINT64_C(0x0000ffff0000ffff))<<16);
    return (v>>32)|(v<<32);
}
static inline uint64_t rr_md_expand_tile(uint32_t bits,unsigned flip,uint8_t attr) {
    uint64_t v=bits;
    v=(v|(v<<16))&UINT64_C(0x0000ffff0000ffff);
    v=(v|(v<<8))&UINT64_C(0x00ff00ff00ff00ff);
    v=(v|(v<<4))&UINT64_C(0x0f0f0f0f0f0f0f0f);
    /* Each byte holds 0..15, so adding 15 cannot carry into its neighbour. */
    v|=((v+UINT64_C(0x0f0f0f0f0f0f0f0f))&UINT64_C(0x1010101010101010))<<2;
    if(!flip)v=rr_md_reverse_bytes(v);
    v|=UINT64_C(0x0101010101010101)*attr;
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_BIG_ENDIAN__
    v=rr_md_reverse_bytes(v);
#endif
    return v;
}

#if !RR_MD_REFERENCE_PIXELS && (defined(__SSE2__) || defined(_M_X64))
#include <emmintrin.h>
static inline __m128i rr_md_choose(__m128i mask,__m128i yes,__m128i no) {
    return _mm_or_si128(_mm_and_si128(mask,yes),_mm_andnot_si128(mask,no));
}
static inline __m128i rr_md_nonzero(__m128i v) {
    return _mm_cmpeq_epi8(_mm_cmpeq_epi8(v,_mm_setzero_si128()),_mm_setzero_si128());
}
static int rr_md_compose_pixels(uint8_t *out,int begin,int end,
    const uint8_t *a,const uint8_t *b,const uint8_t *si,const uint8_t *so,const uint8_t *sh,
    const uint8_t *shadow,const uint8_t *highlight,uint8_t backdrop,int shade) {
    const __m128i mask63=_mm_set1_epi8(63),opaque=_mm_set1_epi8(0x40);
    const __m128i high_opaque=_mm_set1_epi8((char)0xc0);
    const __m128i bg=_mm_set1_epi8((char)backdrop),ones=_mm_cmpeq_epi8(mask63,mask63);
    int x=begin;
    for(;x+16<=end;x+=16) {
        __m128i av=_mm_loadu_si128((const __m128i *)(a+x));
        __m128i bv=_mm_loadu_si128((const __m128i *)(b+x));
        __m128i sv=_mm_loadu_si128((const __m128i *)(si+x));
        __m128i a_on=rr_md_nonzero(_mm_and_si128(av,opaque));
        __m128i b_on=rr_md_nonzero(_mm_and_si128(bv,opaque));
        __m128i s_on=rr_md_nonzero(_mm_loadu_si128((const __m128i *)(so+x)));
        __m128i a_hi=_mm_cmpeq_epi8(_mm_and_si128(av,high_opaque),high_opaque);
        __m128i b_hi=_mm_cmpeq_epi8(_mm_and_si128(bv,high_opaque),high_opaque);
        __m128i s_hi=_mm_and_si128(s_on,rr_md_nonzero(_mm_loadu_si128((const __m128i *)(sh+x))));
        av=_mm_and_si128(av,mask63);bv=_mm_and_si128(bv,mask63);
        /* Same first-wins ordering as the scalar renderer, from low to high. */
        __m128i px=rr_md_choose(b_on,bv,bg);
        px=rr_md_choose(a_on,av,px);px=rr_md_choose(s_on,sv,px);
        px=rr_md_choose(b_hi,bv,px);px=rr_md_choose(a_hi,av,px);
        px=rr_md_choose(s_hi,sv,px);
        if(shade) {
            __m128i any_hi=_mm_or_si128(_mm_or_si128(a_hi,b_hi),s_hi);
            __m128i dark=_mm_or_si128(_mm_andnot_si128(any_hi,ones),
                rr_md_nonzero(_mm_loadu_si128((const __m128i *)(shadow+x))));
            __m128i op=rr_md_nonzero(_mm_loadu_si128((const __m128i *)(highlight+x)));
            __m128i bright=_mm_andnot_si128(dark,op);
            dark=_mm_andnot_si128(op,dark);
            __m128i normal=_mm_cmpeq_epi8(_mm_and_si128(px,high_opaque),_mm_setzero_si128());
            __m128i add=_mm_or_si128(_mm_and_si128(dark,_mm_set1_epi8(GVDP_PALETTE_SHADOW)),
                _mm_and_si128(bright,_mm_set1_epi8((char)GVDP_PALETTE_HIGHLIGHT)));
            px=_mm_add_epi8(px,_mm_and_si128(normal,add));
        }
        _mm_storeu_si128((__m128i *)(out+x),px);
    }
    return x;
}
#else
static int rr_md_compose_pixels(uint8_t *out,int begin,int end,
    const uint8_t *a,const uint8_t *b,const uint8_t *si,const uint8_t *so,const uint8_t *sh,
    const uint8_t *shadow,const uint8_t *highlight,uint8_t backdrop,int shade) {
    (void)out;(void)end;(void)a;(void)b;(void)si;(void)so;(void)sh;
    (void)shadow;(void)highlight;(void)backdrop;(void)shade;return begin;
}
#endif
