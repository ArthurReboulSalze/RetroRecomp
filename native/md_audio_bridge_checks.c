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
#ifdef RR_MD_AUDIO_FEED
/* A game locked to the display: the machine makes its frames 1/base times faster than its own clock (59.9228 Hz paced at
 * 60 Hz: base 0.99871), the device still takes 48,000 frames a second. `feed` is the bridge's feed-forward (1/base, or 1.0
 * for none: then only its fill controller works). Simulated minutes of 512-frame pulls after a 10 s settle: the band the
 * fill stays in, and no stretch, underrun or overflow. */
static int locked(double base,int feed,double *low,double *high,double *mean,uint64_t *events) {
    rab_config cfg;rab_config_defaults(&cfg);
    cfg.source_rate=223721;cfg.host_rate=48000;cfg.channels=2;cfg.target_ms=25;cfg.preroll_ms=25;
    rab_bridge b;if(rab_init(&b,&cfg))return 1;
    if(feed)b.rr_feed=1.0/base;
    int16_t *input=(int16_t *)malloc((size_t)b.cap*2*sizeof(int16_t));if(!input)return 2;
    signal(input,(int)b.cap,2,1,0);
    rab_push(&b,input,(int)(cfg.source_rate*.03));
    int16_t pcm[512*2];double credit=0,sum=0;unsigned measured=0;*low=1e9;*high=-1e9;
    const unsigned settle=(unsigned)(10.0*48000/512),total=(unsigned)(300.0*48000/512);
    for(unsigned block=0;block<total;++block) {
        credit+=223721.0*512/48000.0/base;unsigned frames=(unsigned)credit;credit-=frames;
        rab_push(&b,input,(int)frames);rab_pull(&b,pcm,512);
        if(block>=settle) {
            double fill=b.stats.last_fill_ms;sum+=fill;++measured;
            if(fill<*low)*low=fill;if(fill>*high)*high=fill;
        }
    }
    *mean=sum/measured;
    *events=b.stats.stretch_events+b.stats.underrun_events+b.stats.overflow_drops;
    free(input);rab_free(&b);return 0;
}
static int locked_report(void) {
    const double bases[]={0.99871,1.003,1.0};int failed=0;
    printf("{\"locked\":[");
    for(unsigned i=0;i<3;++i)for(int feed=0;feed<2;++feed) {
        double low,high,mean;uint64_t events;
        if(locked(bases[i],feed,&low,&high,&mean,&events))return 1;
        /* With the feed-forward the fill stays within 3 ms of its 25 ms target; nothing is ever concealed or dropped. */
        if(events || (feed && (low<22.0 || high>28.0)))failed=1;
        printf("%s{\"base\":%.5f,\"feed_forward\":%s,\"fill_min_ms\":%.3f,\"fill_max_ms\":%.3f,\"fill_mean_ms\":%.3f,\"stretch_underrun_overflow\":%llu}",
               i||feed?",":"",bases[i],feed?"true":"false",low,high,mean,(unsigned long long)events);
    }
    printf("],\"passed\":%s}\n",failed?"false":"true");
    return failed;
}
#endif
int main(int argc,char **argv) {
    if(argc>1 && !strcmp(argv[1],"--steady"))return steady();
#ifdef RR_MD_AUDIO_FEED
    if(argc>1 && !strcmp(argv[1],"--locked"))return locked_report();
#endif
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
