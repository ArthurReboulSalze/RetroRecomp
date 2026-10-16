/* Authored signals only. Compare complete PCM and loop choices against the
 * unmodified pinned bridge, including starvation, ring wrap and resets. */
#define RR_MD_AUDIO_LOOP_CHECKS 1
static int rr_md_audio_check_enabled;
static unsigned long long rr_md_audio_transform_checks;
#define RECOMP_AUDIO_DRC_IMPL
#include "bridge.h"
#include <stdio.h>
#include <time.h>

static uint32_t rng = 0x754311abu;
static uint64_t hash = 1469598103934665603ull;
#ifdef RR_MD_AUDIO_SSE_DOT
static unsigned dot_edges(void) {
    int16_t a[144],b[144];unsigned checks=0;uint32_t saved_rng=rng;
    for(unsigned pattern=0;pattern<5;++pattern) {
        for(unsigned k=0;k<144;++k) {
            rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;
            a[k]=pattern<2?-32768:pattern==2?32767:(int16_t)rng;
            b[k]=pattern==0?-32768:pattern==1?32767:pattern==2?-32768:(int16_t)(rng>>16);
        }
        for(int offset=0;offset<8;++offset)for(int n=1;n<=129;++n) {
            int64_t expected=0;for(int k=0;k<n;++k)expected+=(int64_t)a[k]*b[offset+k];
            if(rr_md_loop_dot(a,b+offset,n)!=expected)abort();++checks;
        }
    }
    rng=saved_rng;return checks;
}
#else
static unsigned dot_edges(void) {return 0;}
#endif
static void hash_bytes(const void *data, size_t n) {
    const unsigned char *p = (const unsigned char *)data;
    while (n--) { hash ^= *p++; hash *= 1099511628211ull; }
}
static void signal(int16_t *pcm, int frames, int ch, int pattern, int64_t pos) {
    for (int i=0;i<frames;++i) for(int c=0;c<ch;++c) {
        rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
        int v = 0;
        if (pattern==1) v=(int)(12000*sin((pos+i)*0.017)+5000*sin((pos+i)*0.039+c));
        if (pattern==2) v=(int)(rng & 65535)-32768;
        if (pattern==3) v=((pos+i)%127 < 3) ? (c ? -23000 : 31000) : 0;
        if (pattern==4) v=32767;
        if (pattern==5) v=-32768;
        if (pattern==6) v=((pos+i)&1) ? -32768 : 32767;
        if (pattern==7) v=((pos+i)%37 < 18) ? (c ? -1 : 1) : (c ? 1 : -1);
        pcm[i*ch+c]=(int16_t)v;
    }
}
static int steady(void) {
    rab_config cfg;rab_config_defaults(&cfg);
    cfg.source_rate=223721;cfg.host_rate=48000;cfg.channels=2;cfg.target_ms=25;cfg.preroll_ms=25;
    rab_bridge b;if(rab_init(&b,&cfg))return 1;
    int16_t *input=(int16_t *)malloc((size_t)b.cap*2*sizeof(int16_t));
    if(!input)return 2;
    signal(input,(int)b.cap,2,2,0);
    rab_push(&b,input,(int)(cfg.source_rate*.06));
    int16_t pcm[512*2];uint64_t credit=0;double seconds=0;
    for(unsigned block=0;block<512;++block) {
        credit+=223721ull*512;unsigned frames=(unsigned)(credit/48000);credit%=48000;
        clock_t start=clock();rab_push(&b,input,(int)frames);rab_pull(&b,pcm,512);
        seconds+=(double)(clock()-start)/CLOCKS_PER_SEC;
        hash_bytes(pcm,sizeof pcm);
    }
    hash_bytes(&b.out_pos,sizeof b.out_pos);
    printf("{\"hash\":\"%016llx\",\"output_samples\":524288,\"work_cpu_seconds\":%.6f,\"stretch_events\":%llu}\n",
        (unsigned long long)hash,seconds,(unsigned long long)b.stats.stretch_events);
    int failed=b.stats.stretch_events!=0;free(input);rab_free(&b);return failed;
}
int main(int argc,char **argv) {
    if(argc>1 && !strcmp(argv[1],"--steady"))return steady();
    unsigned edge_checks=dot_edges();
    rr_md_audio_check_enabled=argc>1 && !strcmp(argv[1],"--verify-transform");
    double search_seconds=0,search_max_ms=0;
    unsigned searches=0, pulls=0;
    uint64_t stretches=0;
    for(int rate=0;rate<2;++rate) for(int ch=1;ch<=2;++ch) for(int pat=0;pat<8;++pat) {
        rab_config cfg;rab_config_defaults(&cfg);
        cfg.source_rate=rate ? 223721.5909 : 44100; cfg.host_rate=48000;cfg.channels=ch;
        cfg.target_ms=25;cfg.preroll_ms=25;cfg.em_low_ms=5;cfg.em_high_ms=80;
        rab_bridge b;if(rab_init(&b,&cfg))return 1;
        int n=(int)b.cap;
        int16_t *pcm=(int16_t *)malloc((size_t)n*ch*sizeof(int16_t));
        if(!pcm)return 2;
        for(int wrap=0;wrap<3;++wrap) {
            signal(pcm,n,ch,pat,(int64_t)wrap*n);rab_push(&b,pcm,n);
            /* Both a contiguous history and a window crossing ring index 0. */
            int64_t end=(int64_t)b.in_count-b.half-1-(wrap==1 ? n/4 : 0);
            clock_t start=clock();double len=rab__find_loop_len(&b,end);
            double seconds=(double)(clock()-start)/CLOCKS_PER_SEC;
            search_seconds+=seconds;if(seconds*1000>search_max_ms)search_max_ms=seconds*1000;
            hash_bytes(&len,sizeof len);++searches;
        }
        rab_reset(&b);int64_t pos=0;
        for(int block=0;block<60;++block) {
            /* Prime, normal bursts, repeated complete stalls, recovery. */
            int frames=block==0 ? (int)(cfg.source_rate*.04) : (int)(cfg.source_rate/100.0);
            if(block%10>=3 && block%10<=6)frames=0;
            signal(pcm,frames,ch,pat,pos);pos+=frames;rab_push(&b,pcm,frames);
            int16_t out[512*2];rab_pull(&b,out,512);++pulls;
            hash_bytes(out,(size_t)512*ch*sizeof(int16_t));
            hash_bytes(&b.loop_len,sizeof b.loop_len);
            hash_bytes(&b.out_pos,sizeof b.out_pos);
        }
        stretches+=b.stats.stretch_events;
        rab_reset(&b);int16_t empty[32*2];rab_pull(&b,empty,32);
        hash_bytes(empty,(size_t)32*ch*sizeof(int16_t));
        free(pcm);rab_free(&b);rab_free(&b);
    }
    printf("{\"hash\":\"%016llx\",\"searches\":%u,\"pulls\":%u,\"stretches\":%llu,\"search_seconds\":%.6f,\"search_max_ms\":%.6f,\"transform_checks\":%llu,\"packed_dot_edges\":%u}\n",
        (unsigned long long)hash,searches,pulls,(unsigned long long)stretches,search_seconds,search_max_ms,rr_md_audio_transform_checks,edge_checks);
    return 0;
}
