/* Ordered stereo FIR: same float products, double sums and tap order. MIT.
 * SSE2 runs the left/right channels together; it never reassociates taps.
 *
 * rr_stereo_fir_block (1.9.0) computes several outputs at once from a linear history: each output keeps exactly the
 * sequence of rr_stereo_fir (tap 0 the newest sample, the float product of the sample and the coefficient, added to a double
 * sum in tap order), so every output is bit-identical to it. Only independent outputs run side by side: their additions
 * overlap instead of waiting on one chain of 256 dependent sums. Three bodies: portable C (any CPU), SSE2 (x86 baseline) and
 * AVX2 (chosen at start by audio_output.inc when SDL_HasAVX2()), all with the same per-output sequence. */
#ifndef RR_STEREO_FIR_H
#define RR_STEREO_FIR_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#if !defined(RR_STEREO_FIR_SCALAR) && (defined(__SSE2__) || defined(_M_X64))
#include <emmintrin.h>
#define RR_STEREO_FIR_SIMD 1
#else
#define RR_STEREO_FIR_SIMD 0
#endif
#if RR_STEREO_FIR_SIMD && (defined(__x86_64__) || defined(_M_X64) || defined(__i386__)) && \
    (defined(__clang__) || defined(__GNUC__) || defined(_MSC_VER))
#include <immintrin.h>
#define RR_STEREO_FIR_AVX2 1
#if defined(__clang__) || defined(__GNUC__)
#define RR_STEREO_FIR_AVX2_TARGET __attribute__((target("avx2,sse4.1")))
#else
#define RR_STEREO_FIR_AVX2_TARGET
#endif
#else
#define RR_STEREO_FIR_AVX2 0
#endif

static inline void rr_stereo_fir(const int16_t *history,unsigned position,
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

/* One output of the block in plain C: the window ends at newest (a stereo pair), tap t reads newest - 2t. */
static inline void rr_stereo_fir_linear(const int16_t *newest,const float *coefficients,unsigned taps,double *out) {
    double l=0,r=0;
    for(unsigned t=0;t<taps;++t) {
        const int16_t *p=newest-2*(ptrdiff_t)t;
        l+=p[0]*coefficients[t];r+=p[1]*coefficients[t];
    }
    out[0]=l;out[1]=r;
}

/* Portable body: four outputs per pass, eight independent double sums. */
static inline void rr_stereo_fir_block_c(const int16_t *lin,const uint32_t *ends,const float *const *coefficients,
        unsigned taps,unsigned count,double *out) {
    unsigned k=0;
    for(;k+4<=count;k+=4) {
        const int16_t *p0=lin+ends[k]*2,*p1=lin+ends[k+1]*2,*p2=lin+ends[k+2]*2,*p3=lin+ends[k+3]*2;
        const float *c0=coefficients[k],*c1=coefficients[k+1],*c2=coefficients[k+2],*c3=coefficients[k+3];
        double l0=0,r0=0,l1=0,r1=0,l2=0,r2=0,l3=0,r3=0;
        for(unsigned t=0;t<taps;++t) {
            const ptrdiff_t back=-2*(ptrdiff_t)t;
            l0+=p0[back]*c0[t];r0+=p0[back+1]*c0[t];
            l1+=p1[back]*c1[t];r1+=p1[back+1]*c1[t];
            l2+=p2[back]*c2[t];r2+=p2[back+1]*c2[t];
            l3+=p3[back]*c3[t];r3+=p3[back+1]*c3[t];
        }
        out[k*2]=l0;out[k*2+1]=r0;out[k*2+2]=l1;out[k*2+3]=r1;
        out[k*2+4]=l2;out[k*2+5]=r2;out[k*2+6]=l3;out[k*2+7]=r3;
    }
    for(;k<count;++k) rr_stereo_fir_linear(lin+ends[k]*2,coefficients[k],taps,out+k*2);
}

#if RR_STEREO_FIR_SIMD
/* SSE2 body: four outputs per pass, each a [left, right] pair of double sums, the same instructions as rr_stereo_fir. */
static inline __m128d rr_stereo_fir_sse2_tap(__m128d sum,const int16_t *p,float coefficient) {
    int32_t packed;memcpy(&packed,p,sizeof packed);
    __m128i samples=_mm_cvtsi32_si128(packed);
    samples=_mm_unpacklo_epi16(samples,_mm_srai_epi16(samples,15));
    __m128 product=_mm_mul_ps(_mm_cvtepi32_ps(samples),_mm_set1_ps(coefficient));
    return _mm_add_pd(sum,_mm_cvtps_pd(product));
}
static inline void rr_stereo_fir_block_sse2(const int16_t *lin,const uint32_t *ends,const float *const *coefficients,
        unsigned taps,unsigned count,double *out) {
    unsigned k=0;
    for(;k+4<=count;k+=4) {
        const int16_t *p0=lin+ends[k]*2,*p1=lin+ends[k+1]*2,*p2=lin+ends[k+2]*2,*p3=lin+ends[k+3]*2;
        const float *c0=coefficients[k],*c1=coefficients[k+1],*c2=coefficients[k+2],*c3=coefficients[k+3];
        __m128d s0=_mm_setzero_pd(),s1=_mm_setzero_pd(),s2=_mm_setzero_pd(),s3=_mm_setzero_pd();
        for(unsigned t=0;t<taps;++t) {
            const ptrdiff_t back=-2*(ptrdiff_t)t;
            s0=rr_stereo_fir_sse2_tap(s0,p0+back,c0[t]);s1=rr_stereo_fir_sse2_tap(s1,p1+back,c1[t]);
            s2=rr_stereo_fir_sse2_tap(s2,p2+back,c2[t]);s3=rr_stereo_fir_sse2_tap(s3,p3+back,c3[t]);
        }
        _mm_storeu_pd(out+k*2,s0);_mm_storeu_pd(out+k*2+2,s1);_mm_storeu_pd(out+k*2+4,s2);_mm_storeu_pd(out+k*2+6,s3);
    }
    for(;k<count;++k) {
        __m128d s=_mm_setzero_pd();
        const int16_t *p=lin+ends[k]*2;
        for(unsigned t=0;t<taps;++t) s=rr_stereo_fir_sse2_tap(s,p-2*(ptrdiff_t)t,coefficients[k][t]);
        _mm_storeu_pd(out+k*2,s);
    }
}
#endif

#if RR_STEREO_FIR_AVX2
/* AVX2 body: eight outputs per pass in four registers, each [left a, right a, left b, right b]: the samples widened to int32
 * then float, the float product, widened to double and added: per lane the very sequence of rr_stereo_fir. */
static inline RR_STEREO_FIR_AVX2_TARGET __m256d rr_stereo_fir_avx2_tap(__m256d sum,const int16_t *a,const int16_t *b,
        float ca,float cb) {
    int32_t pa,pb;memcpy(&pa,a,sizeof pa);memcpy(&pb,b,sizeof pb);
    __m128i samples=_mm_cvtepi16_epi32(_mm_unpacklo_epi32(_mm_cvtsi32_si128(pa),_mm_cvtsi32_si128(pb)));
    __m128 product=_mm_mul_ps(_mm_cvtepi32_ps(samples),_mm_setr_ps(ca,ca,cb,cb));
    return _mm256_add_pd(sum,_mm256_cvtps_pd(product));
}
static inline RR_STEREO_FIR_AVX2_TARGET void rr_stereo_fir_block_avx2(const int16_t *lin,const uint32_t *ends,
        const float *const *coefficients,unsigned taps,unsigned count,double *out) {
    unsigned k=0;
    for(;k+8<=count;k+=8) {
        const int16_t *p[8];const float *c[8];
        for(unsigned i=0;i<8;++i) { p[i]=lin+ends[k+i]*2; c[i]=coefficients[k+i]; }
        __m256d s0=_mm256_setzero_pd(),s1=_mm256_setzero_pd(),s2=_mm256_setzero_pd(),s3=_mm256_setzero_pd();
        for(unsigned t=0;t<taps;++t) {
            const ptrdiff_t back=-2*(ptrdiff_t)t;
            s0=rr_stereo_fir_avx2_tap(s0,p[0]+back,p[1]+back,c[0][t],c[1][t]);
            s1=rr_stereo_fir_avx2_tap(s1,p[2]+back,p[3]+back,c[2][t],c[3][t]);
            s2=rr_stereo_fir_avx2_tap(s2,p[4]+back,p[5]+back,c[4][t],c[5][t]);
            s3=rr_stereo_fir_avx2_tap(s3,p[6]+back,p[7]+back,c[6][t],c[7][t]);
        }
        _mm256_storeu_pd(out+k*2,s0);_mm256_storeu_pd(out+k*2+4,s1);
        _mm256_storeu_pd(out+k*2+8,s2);_mm256_storeu_pd(out+k*2+12,s3);
    }
    if(k<count) rr_stereo_fir_block_sse2(lin,ends+k,coefficients+k,taps,count-k,out+k*2);
}
#endif

/* The body for this CPU: 2 AVX2, 1 SSE2, 0 portable C (all three give the same bits). */
static inline void rr_stereo_fir_block(int body,const int16_t *lin,const uint32_t *ends,const float *const *coefficients,
        unsigned taps,unsigned count,double *out) {
#if RR_STEREO_FIR_AVX2
    if(body==2) { rr_stereo_fir_block_avx2(lin,ends,coefficients,taps,count,out); return; }
#endif
#if RR_STEREO_FIR_SIMD
    if(body>=1) { rr_stereo_fir_block_sse2(lin,ends,coefficients,taps,count,out); return; }
#endif
    (void)body;
    rr_stereo_fir_block_c(lin,ends,coefficients,taps,count,out);
}
#endif
