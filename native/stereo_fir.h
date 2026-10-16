/* Ordered stereo FIR: same float products, double sums and tap order. MIT.
 * SSE2 runs the left/right channels together; it never reassociates taps. */
#ifndef RR_STEREO_FIR_H
#define RR_STEREO_FIR_H
#include <stdint.h>
#include <string.h>
#if !defined(RR_STEREO_FIR_SCALAR) && (defined(__SSE2__) || defined(_M_X64))
#include <emmintrin.h>
#define RR_STEREO_FIR_SIMD 1
#else
#define RR_STEREO_FIR_SIMD 0
#endif
static void rr_stereo_fir(const int16_t *history,unsigned position,
        const float *coefficients,unsigned taps,double *left,double *right) {
    unsigned first=position+1;
#if RR_STEREO_FIR_SIMD
    __m128d sum=_mm_setzero_pd();
#else
    double l=0,r=0;
#endif
    for(unsigned part=0,tap=0;part<2;++part) {
        unsigned count=part?taps-first:first;
        const int16_t *p=history+(part?taps-1:position)*2;
        for(unsigned n=0;n<count;++n,++tap) {
#if RR_STEREO_FIR_SIMD
            int32_t packed;memcpy(&packed,p,sizeof packed);
            __m128i samples=_mm_cvtsi32_si128(packed);
            samples=_mm_unpacklo_epi16(samples,_mm_srai_epi16(samples,15));
            __m128 product=_mm_mul_ps(_mm_cvtepi32_ps(samples),_mm_set1_ps(coefficients[tap]));
            sum=_mm_add_pd(sum,_mm_cvtps_pd(product));
#else
            l+=p[0]*coefficients[tap];r+=p[1]*coefficients[tap];
#endif
            if(n+1<count)p-=2;
        }
    }
#if RR_STEREO_FIR_SIMD
    double pair[2];_mm_storeu_pd(pair,sum);*left=pair[0];*right=pair[1];
#else
    *left=l;*right=r;
#endif
}
#endif
