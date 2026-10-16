#include "md_audio_mix.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned long long checks;
static uint32_t random_value=0x823741adu;
static int16_t next_sample(void) {
    random_value^=random_value<<13;random_value^=random_value>>17;random_value^=random_value<<5;
    return (int16_t)random_value;
}
int main(void) {
    static int16_t fm[8192],psg[16384],out[32770];
    const size_t sizes[]={0,1,2,3,7,31,32,255,511,512,740,1024,3728,4475,16384};
    const size_t fm_sizes[]={0,1,2,3,7,511,740,889,1492,4096};
    for(size_t i=0;i<8192;++i)fm[i]=next_sample();
    for(size_t i=0;i<16384;++i)psg[i]=next_sample();
    for(unsigned ns=0;ns<sizeof sizes/sizeof *sizes;++ns)
    for(unsigned nf=0;nf<sizeof fm_sizes/sizeof *fm_sizes;++nf)
    for(int divisor=1;divisor<=64;++divisor)for(int connected=0;connected<=1;++connected) {
        size_t n=sizes[ns],f=fm_sizes[nf];
        memset(out,0x5a,sizeof out);
        rr_md_audio_mix(out,connected?fm:NULL,f,psg,n,divisor);
        /* Original pinned MIX_INTO(psg_frames), retaining its direct index
         * formula as an independent oracle for the remainder cursor. */
        for(size_t i=0;i<n;++i) {
            int32_t l=(int32_t)psg[i]/divisor,r=l;
            if(connected && f) {size_t index=i*f/n;l+=fm[index*2];r+=fm[index*2+1];}
            if(l>32767)l=32767;else if(l< -32768)l= -32768;
            if(r>32767)r=32767;else if(r< -32768)r= -32768;
            if(out[i*2]!=l || out[i*2+1]!=r)return 1;
            checks+=2;
        }
        if(out[n*2]!=0x5a5a || out[n*2+1]!=0x5a5a)return 2;
    }
    printf("{\"sample_comparisons\":%llu,\"divisors\":64,\"psg_sizes\":15,\"fm_sizes\":10,\"pcm_equal\":true}\n",checks);
    return 0;
}
