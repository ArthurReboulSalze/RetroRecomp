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
#define CAPACITY 1048576u
#define SLOTS (CAPACITY*2u)
/* Static expansion never fills the table: dynamic observations keep this
 * headroom, and only they can mark a capture truncated. */
#define STATIC_LIMIT (CAPACITY-131072u)
#define WALK_STACK 65536u
typedef struct {uint32_t pc;uint16_t words[8];uint8_t count;uint64_t hits;} Variant;
static Variant variants[CAPACITY];
static uint32_t slots[SLOTS],used,overflow;
static uint32_t walk_stack[WALK_STACK];
static uint64_t static_added;
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
/* Native runs keep the status register outside Musashi between chained
 * instructions; an active instruction trace receives it per instruction. */
int rr_x68k_trace_active(void) {return trace_count<trace_limit;}
void rr_x68k_before(uint32_t pc) {rr_x68k_before_sr(pc,m68ki_get_sr());}
void rr_x68k_before_sr(uint32_t pc,uint32_t sr) {
    if(trace_count>=trace_limit)return;
    CpuTrace *t=&cpu_trace[trace_count++];t->regs[0]=pc;t->regs[1]=sr;
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
    memset(slots,0,sizeof slots);used=overflow=0;unmapped=0;static_added=0;
    memset(unmapped_sites,0,sizeof unmapped_sites);unmapped_site_count=0;return 1;
}
/* Static flow expansion (Retro-Recomp, MIT).
 * When a new instruction is observed, the code around it is in memory right
 * now: follow fallthrough, branches and calls with known targets and record
 * every reachable instruction as a candidate. Candidates are only compiled
 * with live word guards, so a wrong guess (data, replaced overlay) simply
 * keeps using the interpreter. Memory is read exactly as the guards read it,
 * never through I/O. */
static int static_instruction(uint32_t pc,Variant *v) {
    uint16_t opcode;
    if(!rr_x68k_code_word(pc,&opcode))return 0;
    unsigned words=rr_x68k_word_counts[opcode];
    if(words<1 || words>5)return 0;        /* undecodable: stop this path */
    memset(v,0,sizeof *v);v->pc=pc;
    for(unsigned n=0;n<words;++n)if(!rr_x68k_code_word(pc+n*2,&v->words[n]))return 0;
    v->count=(uint8_t)words;
    /* Erased or never-loaded memory decodes as ORI.B #0,D0 or line F. */
    if(words>=2 && v->words[0]==0 && v->words[1]==0)return 0;
    return 1;
}
static int lookup(const Variant *v,uint32_t *index) {
    uint32_t hash=v->pc*2654435761u;
    for(unsigned i=0;i<v->count;++i)hash=(hash^v->words[i])*16777619u;
    for(unsigned slot=hash&(SLOTS-1u),n=0;n<128;++n,slot=(slot+1)&(SLOTS-1u)) {
        uint32_t entry=slots[slot];
        if(!entry){*index=slot;return 0;}
        const Variant *old=&variants[entry-1];
        if(old->pc==v->pc && old->count==v->count && !memcmp(old->words,v->words,v->count*2u)) {*index=entry-1;return 1;}
    }
    *index=UINT32_MAX;return 0;
}
static void push(unsigned *top,uint32_t pc) {
    pc&=0xffffffu;
    if(!(pc&1u) && *top<WALK_STACK)walk_stack[(*top)++]=pc;
}
/* Successors of one decoded instruction (MC68000 encodings). */
static void successors(const Variant *v,unsigned *top) {
    uint32_t pc=v->pc,next=pc+v->count*2u;
    uint16_t op=v->words[0];
    if(op==0x4e75 || op==0x4e73 || op==0x4e77 || op==0x4afc || op==0x4e72)return; /* RTS RTE RTR ILLEGAL STOP */
    if((op&0xf000)==0x6000) {                                /* BRA BSR Bcc */
        int32_t disp=(int8_t)(op&0xff);
        if(!disp)disp=(int16_t)v->words[1];
        push(top,pc+2u+(uint32_t)disp);
        if((op&0x0f00)!=0x0000)push(top,next);              /* not BRA */
        return;
    }
    if((op&0xf0f8)==0x50c8) {                                /* DBcc */
        push(top,pc+2u+(uint32_t)(int32_t)(int16_t)v->words[1]);push(top,next);return;
    }
    if((op&0xffc0)==0x4ec0 || (op&0xffc0)==0x4e80) {         /* JMP JSR */
        int call=(op&0xffc0)==0x4e80;
        switch(op&0x3f) {
        case 0x38: push(top,(uint32_t)(int32_t)(int16_t)v->words[1]);break;             /* abs.W */
        case 0x39: push(top,((uint32_t)v->words[1]<<16)|v->words[2]);break;            /* abs.L */
        case 0x3a: push(top,pc+2u+(uint32_t)(int32_t)(int16_t)v->words[1]);break;      /* d16(PC) */
        default: break;                                      /* computed target */
        }
        if(call)push(top,next);
        return;
    }
    push(top,next);                                          /* TRAP and the rest */
}
static void expand(const Variant *seed) {
    unsigned top=0;
    successors(seed,&top);
    while(top && used<STATIC_LIMIT) {
        uint32_t pc=walk_stack[--top],index;
        uint16_t op;
        /* Human68k DOS calls (line F $FFxx) return to the next word. */
        if(rr_x68k_code_word(pc,&op) && (op&0xff00)==0xff00 && op!=0xffff) {push(&top,pc+2u);continue;}
        Variant v;
        if(!static_instruction(pc,&v))continue;
        if(lookup(&v,&index) || index==UINT32_MAX)continue;  /* known, or table neighbourhood full */
        v.hits=0;variants[used]=v;slots[index]=++used;++static_added;
        successors(&v,&top);
    }
}

/* A chained native run counts its RAM and IPL instructions once. */
void rr_x68k_note_native(unsigned ram,unsigned ipl) {native_count[0]+=ram;native_count[1]+=ipl;}
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
            v.hits=1;variants[used]=v;slots[slot]=++used;
            expand(&variants[used-1]);
            return;
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
      ",\"truncated\":%s,\"unmapped\":%" PRIu64 ",\"static_variants\":%" PRIu64 ",\"variants\":[\n",
      native_count[0],native_count[1],reference_count[0],reference_count[1],overflow?"true":"false",unmapped,static_added);
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
