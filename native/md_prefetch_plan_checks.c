/* Compare native preparation with the previous live preparation, on the
 * authored/pinned CPU fixtures. No cartridge or game is executed. */
#define main rr_prefetch_corpus_main
#include "md_prefetch_checks.c"
#undef main
#include "reference.c"
#include <time.h>
#ifdef _WIN32
#include <windows.h>
static uint64_t host_clock(void) {LARGE_INTEGER v;QueryPerformanceCounter(&v);return (uint64_t)v.QuadPart;}
static double host_frequency(void) {LARGE_INTEGER v;QueryPerformanceFrequency(&v);return (double)v.QuadPart;}
#else
static uint64_t host_clock(void) {struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000u+t.tv_nsec;}
static double host_frequency(void) {return 1000000000.0;}
#endif

static uint64_t plan_digest(void) {
    uint64_t h=UINT64_C(14695981039346656037);
#define HASH_BYTES(ptr,n) do {const unsigned char *p=(const unsigned char *)(ptr); \
    for(size_t k=0;k<(n);++k)h=(h^p[k])*UINT64_C(1099511628211);}while(0)
    HASH_BYTES(&rr_md_prefetch,sizeof rr_md_prefetch);
    HASH_BYTES(rr_pf_image,sizeof rr_pf_image);
    unsigned fields[]={rr_pf_image_pc,rr_pf_image_count,rr_pf_pending,rr_pf_before_write,
        rr_pf_control,rr_pf_control_cycles,rr_pf_condition,rr_pf_image_valid,rr_pf_move,
        rr_pf_dst_advance,rr_pf_dst_idle,paid,g_audio_cycle_counter,tx_count};
    HASH_BYTES(fields,sizeof fields);HASH_BYTES(observed,tx_count*sizeof *observed);
    return h;
#undef HASH_BYTES
}
static void plan_begin(const CorpusCase *t) {
    memcpy(g_cpu.D,t->initial,sizeof g_cpu.D);memcpy(g_cpu.A,t->initial+8,7*sizeof *g_cpu.A);
    g_cpu.SR=t->initial[17];g_cpu.PC=t->initial[18];
    g_cpu.A[7]=g_cpu.SR&SR_S?t->initial[16]:t->initial[15];
    rr_md_prefetch_reset();rr_md_prefetch=(RrMdPrefetch){g_cpu.PC,2,{t->pf_before[0],t->pf_before[1]}};
    memset(rr_pf_image,0,sizeof rr_pf_image);rr_pf_condition=0;
    paid=g_audio_cycle_counter=g_cycle_accumulator=tx_count=change_extension=0;
}
int main(void) {
    unsigned count=sizeof corpus_cases/sizeof *corpus_cases,checked=0;
    double seconds[2]={0};volatile uint64_t digest=0;
    for(unsigned i=0;i<count;++i) {
        const CorpusCase *t=&corpus_cases[i];
        for(unsigned j=0;j<t->before_count;++j)flat_bus[t->before[j].address]=t->before[j].value;
        plan_begin(t);const RrMdNativeStep *op=rr_md_native_lookup(g_cpu.PC);
        if(!op || !op->prefetch.kind)continue;
        rr_pf_prepare(&op->instruction);uint64_t expected=plan_digest();
        plan_begin(t);rr_pf_prepare_native(&op->instruction,&op->prefetch);
        if(expected!=plan_digest()) {fprintf(stderr,"plan mismatch: %s\n",t->name);return 1;}
        ++checked;
        /* Alternate order to avoid consistently favoring a warmer cache.
         * This measures preparation and identical setup only, never FPS. */
        for(unsigned pass=0;pass<2;++pass) {
            unsigned mode=(i+pass)&1;uint64_t start=host_clock();
            for(unsigned repeat=0;repeat<4096;++repeat) {
                plan_begin(t);
                if(mode)rr_pf_prepare_native(&op->instruction,&op->prefetch);
                else rr_pf_prepare(&op->instruction);
                digest+=rr_pf_image_valid+rr_pf_pending+rr_pf_control_cycles+paid;
            }
            seconds[mode]+=(double)(host_clock()-start)/host_frequency();
        }
    }
    if(checked!=count)return 2;
    printf("{\"passed\":true,\"instruction_plans\":%u,\"runs_per_mode\":%u,"
        "\"dynamic_seconds\":%.9f,\"static_seconds\":%.9f,\"digest\":\"%016llx\"}\n",
        checked,checked*4096,seconds[0],seconds[1],(unsigned long long)digest);
    return 0;
}
