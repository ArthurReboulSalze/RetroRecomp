/* Same taps, coefficients and left/right summation order as the pinned bridge.
 * Walk the ring by spans: a signed 64-bit division per tap is unnecessary. */
static void rab__sample_at(const rab_bridge *b, double pos, float *s) {
    int ch=b->cfg.channels;
    int64_t i=(int64_t)floor(pos),start=i-b->half+1;
    double fr=pos-(double)i;
    int phase=(int)(fr*b->cfg.phases);
    if(phase>=b->cfg.phases)phase=b->cfg.phases-1;
    if(phase<0)phase=0;
    const float *cz=b->coeffs+(size_t)phase*b->cfg.taps;
    float s0=0.0f,s1=0.0f;
    int k=0;
    /* Concealment near startup can repeat the first history frame. */
    while(start<0 && k<b->cfg.taps) {
        s0+=cz[k]*b->ring[0];
        if(ch==2)s1+=cz[k]*b->ring[1];
        ++start;++k;
    }
    int64_t index=start%b->cap;
    while(k<b->cfg.taps) {
        int remaining=b->cfg.taps-k;
        int span=(b->cap-index)<remaining?(int)(b->cap-index):remaining;
        const float *samples=b->ring+index*ch;
        if(ch==2) {
            for(int n=0;n<span;++n,++k,samples+=2) {
                s0+=cz[k]*samples[0];s1+=cz[k]*samples[1];
            }
        } else {
            for(int n=0;n<span;++n,++k,++samples)s0+=cz[k]*samples[0];
        }
        index=0;
    }
    s[0]=s0;s[1]=ch==2?s1:0.0f;
}
