#ifndef RR_MD_AUDIO_MIX_H
#define RR_MD_AUDIO_MIX_H
#include <stdint.h>
#include <stddef.h>
/* Preserve floor(i * fm_frames / psg_frames), signed division and clipping.
 * Quotient/remainder stepping replaces one 64-bit division for every sample.
 * Callers clamp PSG frames to their output capacity before entering here. */
static void rr_md_audio_mix(int16_t *out,const int16_t *fm,size_t fm_frames,
        const int16_t *psg,size_t psg_frames,int psg_divisor) {
    if(!psg_frames)return;
    size_t index=0,remainder=0;
    size_t advance=fm_frames/psg_frames,extra=fm_frames%psg_frames;
    for(size_t i=0;i<psg_frames;++i) {
        int32_t p=(int32_t)psg[i]/psg_divisor,l=p,r=p;
        if(fm && fm_frames) {l+=fm[index*2];r+=fm[index*2+1];}
        if(l>32767)l=32767;else if(l< -32768)l= -32768;
        if(r>32767)r=32767;else if(r< -32768)r= -32768;
        out[i*2]=(int16_t)l;out[i*2+1]=(int16_t)r;
        index+=advance;remainder+=extra;
        if(remainder>=psg_frames) {remainder-=psg_frames;++index;}
    }
}
#endif
