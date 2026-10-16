/* Exact normalized correlation for the host audio underrun bridge.
 * The pinned search performs two 64-bit ring divisions per candidate/sample
 * under SDL's audio mutex (millions at the Mega Drive's 223 kHz source rate).
 * Copy channel zero once, in the original summation order, then search the
 * same periods with the same double arithmetic and first-best tie breaking.
 * Large searches use integer number-theoretic convolution, with two primes
 * and signed CRT reconstruction. rab_push produces exact int16 / 32768
 * samples: every dot product and energy is a dyadic rational. Reconstructing
 * its integer numerator preserves the complete search and its results;
 * floating FFT approximation and a shorter pitch search are unnecessary.
 * Scratch belongs to rab_init/free; no callback allocation or guest changes.
 */
#define RR_MD_LOOP_P1 998244353u
#define RR_MD_LOOP_P2 1004535809u
#if (defined(__SSE2__) || defined(_M_X64)) && !defined(RR_MD_AUDIO_NTT_ONLY)
#include <emmintrin.h>
#define RR_MD_AUDIO_SSE_DOT 1
#endif
static uint32_t rr_md_loop_power(uint32_t value, uint32_t exponent, uint32_t prime) {
    uint64_t result=1;
    while(exponent) {
        if(exponent&1u)result=result*value%prime;
        value=(uint32_t)((uint64_t)value*value%prime);
        exponent>>=1;
    }
    return (uint32_t)result;
}
static void rr_md_loop_prepare(rab_bridge *b) {
    int w=(int)(b->cfg.stretch_min_ms*b->cfg.source_rate/1000.0);if(w<1)w=1;
    int max=(int)(b->cfg.stretch_max_ms*b->cfg.source_rate/1000.0);if(max<w)max=w;
    /* Small searches keep the scalar path; a failed optional allocation also
     * falls back to that exact path. The callback never tries to allocate. */
    if((uint64_t)w*(unsigned)(max-w+1)<1000000ull)return;
    uint64_t needed=2ull*(unsigned)w+(unsigned)max-1;
    unsigned n=1;while(n<needed && n<32768u)n*=2;
    if(n<needed)return;
    b->loop_transform=(uint32_t *)malloc(3u*n*sizeof(uint32_t));
    b->loop_roots=(uint32_t *)malloc(2u*n*sizeof(uint32_t));
    if(!b->loop_transform || !b->loop_roots) {
        free(b->loop_transform);b->loop_transform=NULL;
        free(b->loop_roots);b->loop_roots=NULL;return;
    }
    b->loop_transform_size=n;
    for(unsigned which=0;which<2;++which) {
        uint32_t prime=which?RR_MD_LOOP_P2:RR_MD_LOOP_P1;
        uint32_t step=rr_md_loop_power(3u,(prime-1u)/n,prime);
        uint32_t *roots=b->loop_roots+which*n;
        roots[0]=1;
        for(unsigned j=1;j<n;++j)roots[j]=(uint32_t)((uint64_t)roots[j-1]*step%prime);
    }
}
/* Constants are separate instantiations so GCC/MSVC can strength-reduce
 * modular division even without link-time optimization. */
#define RR_MD_LOOP_TRANSFORM(NAME, PRIME) \
static void NAME(uint32_t *a,unsigned n,const uint32_t *roots,int inverse) { \
    for(unsigned i=1,j=0;i<n;++i) { \
        unsigned bit=n>>1;for(;j&bit;bit>>=1)j^=bit;j^=bit; \
        if(i<j) {uint32_t t=a[i];a[i]=a[j];a[j]=t;} \
    } \
    for(unsigned len=2;len<=n;len*=2) { \
        unsigned half=len/2,stride=n/len; \
        for(unsigned i=0;i<n;i+=len)for(unsigned j=0;j<half;++j) { \
            unsigned root=j*stride;if(inverse)root=(n-root)&(n-1u); \
            uint32_t u=a[i+j],v=(uint32_t)((uint64_t)a[i+j+half]*roots[root]%(PRIME)); \
            uint32_t sum=u+v;a[i+j]=sum>=(PRIME)?sum-(PRIME):sum; \
            a[i+j+half]=u>=v?u-v:u+(PRIME)-v; \
        } \
    } \
    if(inverse) { \
        uint32_t scale=rr_md_loop_power(n,(PRIME)-2u,(PRIME)); \
        for(unsigned i=0;i<n;++i)a[i]=(uint32_t)((uint64_t)a[i]*scale%(PRIME)); \
    } \
}
RR_MD_LOOP_TRANSFORM(rr_md_loop_ntt1,RR_MD_LOOP_P1)
RR_MD_LOOP_TRANSFORM(rr_md_loop_ntt2,RR_MD_LOOP_P2)
#undef RR_MD_LOOP_TRANSFORM
static int32_t rr_md_loop_sample(float value) {return (int32_t)(value*32768.0f);}
#ifdef RR_MD_AUDIO_SSE_DOT
/* Eight exact signed PCM products per iteration. PMADDWD can overflow only
 * for two pairs of -32768 * -32768: its 0x80000000 then means +2^31.
 * No negative pair sum can reach -2^31, so that one value is unambiguous.
 * Extend every pair to 64 bits before accumulating; silence, full-scale and
 * anti-phase input retain the scalar correlation and its first-best ties. */
static int64_t rr_md_loop_dot(const int16_t *a,const int16_t *c,int count) {
    __m128i sum0=_mm_setzero_si128(),sum1=_mm_setzero_si128();
    const __m128i overflow=_mm_set1_epi32(INT32_MIN);
    int k=0;
    for(;k+8<=count;k+=8) {
        __m128i pairs=_mm_madd_epi16(_mm_loadu_si128((const __m128i *)(a+k)),
                                   _mm_loadu_si128((const __m128i *)(c+k)));
        __m128i sign=_mm_andnot_si128(_mm_cmpeq_epi32(pairs,overflow),_mm_srai_epi32(pairs,31));
        sum0=_mm_add_epi64(sum0,_mm_unpacklo_epi32(pairs,sign));
        sum1=_mm_add_epi64(sum1,_mm_unpackhi_epi32(pairs,sign));
    }
    int64_t lanes[2];_mm_storeu_si128((__m128i *)lanes,_mm_add_epi64(sum0,sum1));
    int64_t result=lanes[0]+lanes[1];
    for(;k<count;++k)result+=(int64_t)a[k]*c[k];
    return result;
}
static double rr_md_loop_direct(const rab_bridge *b,int W,int Lmin,int Lmax) {
    const int16_t *history=b->loop_pcm;
    int64_t energy1=0,energy2=0;
    for(int k=0;k<W;++k) {
        int64_t x=history[k],y=history[Lmin+k];energy1+=x*x;energy2+=y*y;
    }
    double d1=(double)energy1/1073741824.0,best=-1e30;int bestL=Lmin;
    for(int L=Lmin;L<=Lmax;++L) {
        int64_t dot=rr_md_loop_dot(history,history+L,W);
#ifdef RR_MD_AUDIO_LOOP_CHECKS
        if(rr_md_audio_check_enabled) {
            int64_t expected=0;for(int k=0;k<W;++k)expected+=(int64_t)history[k]*history[L+k];
            if(dot!=expected)abort();++rr_md_audio_transform_checks;
        }
#endif
        double num=(double)dot/1073741824.0,d2=(double)energy2/1073741824.0;
        double r=num/(sqrt(d1*d2)+1e-9);
        if(r>best) {best=r;bestL=L;}
        if(L<Lmax) {
            int64_t old=history[L],next=history[L+W];energy2+=next*next-old*old;
        }
    }
    return (double)bestL;
}
#endif
static double rr_md_loop_correlate(const rab_bridge *b,int W,int Lmin,int Lmax) {
    unsigned n=b->loop_transform_size;
    uint32_t *a=b->loop_transform,*c=a+n,*first=c+n;
    const float *history=b->loop_history;
    for(unsigned which=0;which<2;++which) {
        uint32_t prime=which?RR_MD_LOOP_P2:RR_MD_LOOP_P1;
        memset(a,0,2u*n*sizeof(uint32_t));
        for(int k=0;k<W;++k) {
            int32_t q=rr_md_loop_sample(history[k]);
            a[W-1-k]=q<0?(uint32_t)((int64_t)prime+q):(uint32_t)q;
        }
        for(int k=0;k<W+Lmax;++k) {
            int32_t q=rr_md_loop_sample(history[k]);
            c[k]=q<0?(uint32_t)((int64_t)prime+q):(uint32_t)q;
        }
        if(which) {
            rr_md_loop_ntt2(a,n,b->loop_roots+n,0);rr_md_loop_ntt2(c,n,b->loop_roots+n,0);
            for(unsigned j=0;j<n;++j)a[j]=(uint32_t)((uint64_t)a[j]*c[j]%RR_MD_LOOP_P2);
            rr_md_loop_ntt2(a,n,b->loop_roots+n,1);
        } else {
            rr_md_loop_ntt1(a,n,b->loop_roots,0);rr_md_loop_ntt1(c,n,b->loop_roots,0);
            for(unsigned j=0;j<n;++j)a[j]=(uint32_t)((uint64_t)a[j]*c[j]%RR_MD_LOOP_P1);
            rr_md_loop_ntt1(a,n,b->loop_roots,1);
            memcpy(first,a,n*sizeof(uint32_t));
        }
    }
    int64_t energy1=0,energy2=0;
    for(int k=0;k<W;++k) {
        int64_t x=rr_md_loop_sample(history[k]),y=rr_md_loop_sample(history[Lmin+k]);
        energy1+=x*x;energy2+=y*y;
    }
    const uint64_t modulus=(uint64_t)RR_MD_LOOP_P1*RR_MD_LOOP_P2;
    uint32_t inverse=rr_md_loop_power(RR_MD_LOOP_P1,RR_MD_LOOP_P2-2u,RR_MD_LOOP_P2);
    double d1=(double)energy1/1073741824.0,best=-1e30;
    int bestL=Lmin;
    for(int L=Lmin;L<=Lmax;++L) {
        unsigned index=(unsigned)(W-1+L);
        int64_t difference=(int64_t)a[index]-first[index];
        if(difference<0)difference+=RR_MD_LOOP_P2;
        uint64_t t=(uint64_t)difference*inverse%RR_MD_LOOP_P2;
        uint64_t residue=first[index]+(uint64_t)RR_MD_LOOP_P1*t;
        int64_t dot=residue>modulus/2?(int64_t)residue-(int64_t)modulus:(int64_t)residue;
#ifdef RR_MD_AUDIO_LOOP_CHECKS
        if(rr_md_audio_check_enabled) {
            int64_t expected=0;
            for(int k=0;k<W;++k)expected+=(int64_t)rr_md_loop_sample(history[k])*rr_md_loop_sample(history[L+k]);
            if(dot!=expected)abort();
            ++rr_md_audio_transform_checks;
        }
#endif
        double num=(double)dot/1073741824.0,d2=(double)energy2/1073741824.0;
        double r=num/(sqrt(d1*d2)+1e-9);
        if(r>best) {best=r;bestL=L;}
        if(L<Lmax) {
            int64_t old=rr_md_loop_sample(history[L]),next=rr_md_loop_sample(history[L+W]);
            energy2+=next*next-old*old;
        }
    }
    return (double)bestL;
}
static double rab__find_loop_len(const rab_bridge *b, int64_t end_i) {
    double sr = b->cfg.source_rate;
    int Lmin = (int)(b->cfg.stretch_min_ms * sr / 1000.0); if (Lmin < 1) Lmin = 1;
    int Lmax = (int)(b->cfg.stretch_max_ms * sr / 1000.0); if (Lmax < Lmin) Lmax = Lmin;
    int W = Lmin;
    int64_t oldest = (int64_t)b->in_count - b->cap + b->half + 2;
    if (oldest < (int64_t)b->half) oldest = (int64_t)b->half;
    while (Lmax > Lmin && (end_i - Lmax - W) < oldest) Lmax--;
    if ((end_i - Lmax - W) < oldest) return (double)Lmin;

    /* The live-history bound above guarantees W + Lmax <= cap. */
    float *history = b->loop_history;
    int64_t index = end_i % b->cap;
    for (int k = 0; k < W + Lmax; ++k) {
        history[k] = b->ring[index * b->cfg.channels];
#ifdef RR_MD_AUDIO_SSE_DOT
        if(b->loop_pcm)b->loop_pcm[k]=(int16_t)rr_md_loop_sample(history[k]);
#endif
        if (--index < 0) index = b->cap - 1;
    }
    double d1 = 0.0;
    for (int k = 0; k < W; ++k) d1 += (double)history[k] * history[k];
    /* For exact silence every correlation is zero; the original picks Lmin. */
    if (d1 == 0.0) return (double)Lmin;
#ifdef RR_MD_AUDIO_SSE_DOT
    /* For the 5--25 ms MD window, direct packed dot products cost less than
     * six modular transforms on low-power x86. Larger custom windows retain
     * the bounded-work NTT path; other architectures retain scalar/NTT. */
    if(b->loop_pcm && (uint64_t)W*(unsigned)(Lmax-Lmin+1)<=8000000ull)
        return rr_md_loop_direct(b,W,Lmin,Lmax);
#endif
    if(b->loop_transform_size && 2ull*(unsigned)W+(unsigned)Lmax-1<=b->loop_transform_size)
        return rr_md_loop_correlate(b,W,Lmin,Lmax);
    double best = -1e30; int bestL = Lmin;
    for (int L = Lmin; L <= Lmax; ++L) {
        double num = 0.0, d2 = 0.0;
        for (int k = 0; k < W; ++k) {
            float a = history[k], c = history[L + k];
            num += (double)a * c;
            d2 += (double)c * c;
        }
        double r = num / (sqrt(d1 * d2) + 1e-9);
        if (r > best) { best = r; bestL = L; }
    }
    return (double)bestL;
}
