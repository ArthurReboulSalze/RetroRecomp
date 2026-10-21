/* Original RetroRecomp instrumentation, MIT. No source media is written.
 * Capture is bounded in RAM and written only after execution, when requested.
 * No guard/observation performs a hardware read, including on a miss. */
#include "observe.h"
#ifdef RR_X68000_BASE74
#include "memory.h"
#else
#include "x68k/x68kmemory.h"
#endif
#include <string.h>
#include <inttypes.h>
#include <stdlib.h>
#include "m68kcpu.h"
#include "opcode_lengths.h"
#ifdef RR_X68000_LINKED
#include "runtime_feedback.h"
#endif
#define CAPACITY 262144u
#define SLOTS (CAPACITY*2u)
typedef struct {uint32_t pc;uint16_t words[8];uint8_t count;uint64_t hits;} Variant;
static Variant variants[CAPACITY];
static uint32_t slots[SLOTS],used,overflow;
static uint64_t native_count[2],reference_count[2],unmapped;
/* Bounded diagnostics for code apertures not yet readable without bus effects.
 * Collect addresses only, in memory; never probe I/O to obtain opcode bytes. */
static struct {uint32_t pc;uint64_t hits;} unmapped_sites[16];
static unsigned unmapped_site_count;
static int observe_enabled=1;
int rr_x68k_force_reference;
typedef struct {uint32_t regs[20];int cycles;} CpuTrace;
static CpuTrace *cpu_trace;
static unsigned trace_limit,trace_count;
int rr_x68k_trace_configure(unsigned limit) {
    if(limit>2000000)return 0;
    free(cpu_trace);cpu_trace=limit?calloc(limit,sizeof *cpu_trace):NULL;
    trace_limit=limit;trace_count=0;return !limit || cpu_trace!=NULL;
}
void rr_x68k_before(uint32_t pc) {
    if(trace_count>=trace_limit)return;
    CpuTrace *t=&cpu_trace[trace_count++];t->regs[0]=pc;t->regs[1]=m68ki_get_sr();
    for(unsigned n=0;n<16;++n)t->regs[n+2]=REG_DA[n];
    t->regs[18]=REG_USP;t->regs[19]=REG_ISP;t->cycles=m68ki_remaining_cycles;
}
int rr_x68k_trace_report(const char *path) {
    FILE *f=fopen(path,"wb");if(!f)return 0;
    for(unsigned n=0;n<trace_count;++n) {
        const CpuTrace *t=&cpu_trace[n];fprintf(f,"%u",n);
        for(unsigned k=0;k<20;++k)fprintf(f," %08x",t->regs[k]);
        fprintf(f," %d\n",t->cycles);
    }
    return fclose(f)==0;
}
int rr_x68k_code_word(uint32_t pc,uint16_t *value) {
    uint8_t *bytes;uint32_t offset;
    pc&=0xffffffu;
    if(!value || (pc&1u))return 0;
    /* The pinned core allocates its full 12 MiB RAM aperture. Do not infer
     * code validity from a PC alone; every complete instruction is guarded. */
    if(pc<0xc00000u) {bytes=MEM;offset=pc;}
    else if(pc>=0xe00000u&&pc<0xe80000u){bytes=TVRAM;offset=pc-0xe00000u;}
    /* The external SCSI IOCS ROM is a separate 8 KiB fetch mapping. Read
     * its backing bytes directly, without invoking peripheral read callbacks. */
    else if(pc>=0xea0000u&&pc<0xea2000u){bytes=SCSIIPL;offset=pc-0xea0000u;}
    else if(pc>=0xfc0000u && pc<0xfffffeu) {bytes=IPL;offset=pc-0xfc0000u;}
    else return 0;
    if(!bytes)return 0;
#ifdef MSB_FIRST
    *value=(uint16_t)((bytes[offset]<<8)|bytes[offset+1]);
#else
    *value=(uint16_t)((bytes[offset+1]<<8)|bytes[offset]);
#endif
    return 1;
}
int rr_x68k_cpu_configure(int reference,int observations) {
    rr_x68k_force_reference=reference!=0;observe_enabled=observations!=0;
    memset(native_count,0,sizeof native_count);memset(reference_count,0,sizeof reference_count);
    memset(slots,0,sizeof slots);used=overflow=0;unmapped=0;
    memset(unmapped_sites,0,sizeof unmapped_sites);unmapped_site_count=0;return 1;
}
void rr_x68k_note(uint32_t pc,int native) {
    pc&=0xffffffu;unsigned region=pc>=0xfc0000u?1:0;
    if(native)++native_count[region];else ++reference_count[region];
    uint16_t opcode;
    unsigned words=!native&&rr_x68k_code_word(pc,&opcode)?rr_x68k_word_counts[opcode]:8;
#ifdef RR_X68000_LINKED
    if(!native&&!rr_x68k_force_reference&&rr_feedback_enabled()){
        uint8_t bytes[16];unsigned count=0;uint16_t word;
        for(unsigned n=0;n<words;n++){if(!rr_x68k_code_word(pc+n*2,&word))break;bytes[count++]=(uint8_t)(word>>8);bytes[count++]=(uint8_t)word;}
        if(count)rr_feedback_note(RR_FB_X68000,pc,0,bytes,count);
    }
#endif
    if(!observe_enabled || native)return;
    Variant v={0};v.pc=pc;uint32_t hash=pc*2654435761u;
    for(unsigned i=0;i<words;++i) {
        if(!rr_x68k_code_word(pc+i*2,&v.words[i]))break;
        ++v.count;hash=(hash^v.words[i])*16777619u;
    }
    if(!v.count) {
        ++unmapped;
        unsigned site;
        for(site=0;site<unmapped_site_count;++site)if(unmapped_sites[site].pc==pc)break;
        if(site<unmapped_site_count)++unmapped_sites[site].hits;
        else if(unmapped_site_count<16) {
            unmapped_sites[site].pc=pc;unmapped_sites[site].hits=1;++unmapped_site_count;
        }
        return;
    }
    for(unsigned slot=hash&(SLOTS-1u),n=0;n<128;++n,slot=(slot+1)&(SLOTS-1u)) {
        uint32_t index=slots[slot];
        if(index) {
            Variant *old=&variants[index-1];
            if(old->pc==pc && old->count==v.count && !memcmp(old->words,v.words,v.count*2)) {++old->hits;return;}
        } else {
            if(used>=CAPACITY)break;
            v.hits=1;variants[used]=v;slots[slot]=++used;return;
        }
    }
    overflow=1;
}
void rr_x68k_cpu_stats(uint64_t v[8]) {
    v[0]=native_count[0];v[1]=native_count[1];v[2]=reference_count[0];v[3]=reference_count[1];
    v[4]=used;v[5]=overflow;v[6]=unmapped;v[7]=rr_x68k_force_reference;
}
int rr_x68k_cpu_report(const char *path) {
    FILE *f=fopen(path,"wb");if(!f)return 0;
    fprintf(f,"{\"schema\":1,\"native_ram\":%" PRIu64 ",\"native_ipl\":%" PRIu64
      ",\"reference_ram\":%" PRIu64 ",\"reference_ipl\":%" PRIu64
      ",\"truncated\":%s,\"unmapped\":%" PRIu64 ",\"variants\":[\n",
      native_count[0],native_count[1],reference_count[0],reference_count[1],overflow?"true":"false",unmapped);
    for(unsigned i=0;i<used;++i) {
        const Variant *v=&variants[i];fprintf(f,"%s{\"pc\":%u,\"hits\":%" PRIu64 ",\"words\":\"",i?",\n":"",v->pc,v->hits);
        for(unsigned n=0;n<v->count;++n)fprintf(f,"%04x",v->words[n]);
        fputs("\"}",f);
    }
    fputs("\n],\"unmapped_sites\":[",f);
    for(unsigned i=0;i<unmapped_site_count;++i)
        fprintf(f,"%s{\"pc\":%u,\"hits\":%" PRIu64 "}",i?",":"",unmapped_sites[i].pc,unmapped_sites[i].hits);
    fputs("]}\n",f);return fclose(f)==0;
}
