/* Shared exact Scale2x. SSE2 processes four independent input pixels;
 * the scalar border/tail path retains the same clamped neighbourhood. MIT. */
#ifndef RR_SCALE2X_H
#define RR_SCALE2X_H
#include <stdint.h>
#if !defined(RR_SCALE2X_SCALAR) && (defined(__SSE2__) || defined(_M_X64))
#include <emmintrin.h>
#define RR_SCALE2X_SIMD 1
static inline __m128i rr_scale2x_choose(__m128i mask,__m128i a,__m128i b) {
    return _mm_or_si128(_mm_and_si128(mask,a),_mm_andnot_si128(mask,b));
}
#else
#define RR_SCALE2X_SIMD 0
#endif
static inline void rr_scale2x_pixel(const uint32_t *row,const uint32_t *up,
        const uint32_t *down,int x,int width,uint32_t *a,uint32_t *b) {
    uint32_t e=row[x],n=up[x],s=down[x],w=row[x?x-1:x],r=row[x+1<width?x+1:x];
    if(n!=s && w!=r) {
        a[0]=w==n?w:e;a[1]=n==r?r:e;
        b[0]=w==s?w:e;b[1]=s==r?r:e;
    } else a[0]=a[1]=b[0]=b[1]=e;
}
static void rr_scale2x(const uint32_t *source,int width,int height,int source_stride,
        uint32_t *target,int target_stride) {
    if(width<=0 || height<=0)return;
    for(int y=0;y<height;++y) {
        const uint32_t *row=source+y*source_stride;
        const uint32_t *up=source+(y?y-1:y)*source_stride;
        const uint32_t *down=source+(y+1<height?y+1:y)*source_stride;
        uint32_t *a=target+y*2*target_stride,*b=a+target_stride;
        int x=0;
#if RR_SCALE2X_SIMD
        rr_scale2x_pixel(row,up,down,0,width,a,b);x=1;
        for(;x+4<width;x+=4) {
            __m128i e=_mm_loadu_si128((const __m128i *)(row+x));
            __m128i n=_mm_loadu_si128((const __m128i *)(up+x));
            __m128i s=_mm_loadu_si128((const __m128i *)(down+x));
            __m128i w=_mm_loadu_si128((const __m128i *)(row+x-1));
            __m128i r=_mm_loadu_si128((const __m128i *)(row+x+1));
            __m128i same=_mm_or_si128(_mm_cmpeq_epi32(n,s),_mm_cmpeq_epi32(w,r));
            __m128i nw=rr_scale2x_choose(_mm_andnot_si128(same,_mm_cmpeq_epi32(w,n)),w,e);
            __m128i ne=rr_scale2x_choose(_mm_andnot_si128(same,_mm_cmpeq_epi32(n,r)),r,e);
            __m128i sw=rr_scale2x_choose(_mm_andnot_si128(same,_mm_cmpeq_epi32(w,s)),w,e);
            __m128i se=rr_scale2x_choose(_mm_andnot_si128(same,_mm_cmpeq_epi32(s,r)),r,e);
            _mm_storeu_si128((__m128i *)(a+x*2),_mm_unpacklo_epi32(nw,ne));
            _mm_storeu_si128((__m128i *)(a+x*2+4),_mm_unpackhi_epi32(nw,ne));
            _mm_storeu_si128((__m128i *)(b+x*2),_mm_unpacklo_epi32(sw,se));
            _mm_storeu_si128((__m128i *)(b+x*2+4),_mm_unpackhi_epi32(sw,se));
        }
#endif
        for(;x<width;++x)rr_scale2x_pixel(row,up,down,x,width,a+x*2,b+x*2);
    }
}
#endif
