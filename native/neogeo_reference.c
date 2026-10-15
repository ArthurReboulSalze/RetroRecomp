/* Reference backend for the first hardware prototype, wholly interpreted.
 * Future AOT uses the same board boundary; counters never imply native work. */
#include "neogeo_reference.h"
#include "runtime_feedback.h"
extern int rr_ng_force_z80_reference;
#include <string.h>
#include "m68k/m68k.h"
#include "geo_m68k.h"
#include "m68k/m68kcpu.h"
extern int m68ki_initial_cycles;
static void rr_ng_put32(uint8_t *p,uint32_t v) {for(unsigned n=0;n<4;++n)p[n]=(uint8_t)(v>>(8*n));}
static uint32_t rr_ng_get32(const uint8_t *p) {uint32_t v=0;for(unsigned n=0;n<4;++n)v|=(uint32_t)p[n]<<(8*n);return v;}
size_t rr_ng_cpu_extra_save(uint8_t *data,size_t size) {
    if(!data || size<32)return 0;
    rr_ng_put32(data,CPU_STOPPED);rr_ng_put32(data+4,RESET_CYCLES);
    rr_ng_put32(data+8,CPU_RUN_MODE);rr_ng_put32(data+12,CPU_INSTR_MODE);
    rr_ng_put32(data+16,(uint32_t)m68ki_remaining_cycles);rr_ng_put32(data+20,(uint32_t)m68ki_initial_cycles);
    rr_ng_put32(data+24,0);rr_ng_put32(data+28,0);return 32;
}
bool rr_ng_cpu_extra_restore(const uint8_t *data,size_t size) {
    if(!data || size!=32 || (rr_ng_get32(data)&~3u) || rr_ng_get32(data+4)>518 ||
       rr_ng_get32(data+8)>1 || (rr_ng_get32(data+12)!=0 && rr_ng_get32(data+12)!=8) ||
       (int32_t)rr_ng_get32(data+16)<-10000 || (int32_t)rr_ng_get32(data+16)>10000 ||
       (int32_t)rr_ng_get32(data+20)<-10000 || (int32_t)rr_ng_get32(data+20)>10000 ||
       rr_ng_get32(data+24) || rr_ng_get32(data+28))return false;
    CPU_STOPPED=rr_ng_get32(data);RESET_CYCLES=rr_ng_get32(data+4);
    CPU_RUN_MODE=rr_ng_get32(data+8);CPU_INSTR_MODE=rr_ng_get32(data+12);
    m68ki_remaining_cycles=(int)rr_ng_get32(data+16);m68ki_initial_cycles=(int)rr_ng_get32(data+20);return true;
}
uint64_t rr_ng_z80_instructions;
int rr_ng_observations=1;
uint64_t rr_ng_native_z80,rr_ng_m1_instructions,rr_ng_sm1_instructions;
uint8_t rr_ng_z80_fallback_pc[65536];
RrNgZ80Variant rr_ng_z80_variants[4096];
unsigned rr_ng_z80_variant_count;
void rr_ng_z80_note_fallback(uint16_t pc) {
    if(rr_ng_force_z80_reference)return;
    extern int rr_ng_z80_code_byte(uint16_t,uint8_t*);
    uint8_t bytes[4];rr_ng_z80_fallback_pc[pc]=1;
    for(unsigned n=0;n<4;++n)if(!rr_ng_z80_code_byte((uint16_t)(pc+n),&bytes[n]))return;
    rr_feedback_note(RR_FB_NG_Z80,pc,0,bytes,4);
    if(!rr_ng_observations)return;
    for(unsigned n=0;n<rr_ng_z80_variant_count;++n)
        if(rr_ng_z80_variants[n].pc==pc && !memcmp(rr_ng_z80_variants[n].bytes,bytes,4))return;
    if(rr_ng_z80_variant_count<4096) {
        RrNgZ80Variant *v=&rr_ng_z80_variants[rr_ng_z80_variant_count++];v->pc=pc;memcpy(v->bytes,bytes,4);
    }
}
int rr_ng_force_z80_reference;
uint64_t rr_ng_bios_instructions, rr_ng_cart_instructions, rr_ng_ram_instructions;
uint8_t rr_ng_reached_pc[0x800000];
uint8_t rr_ng_reached_p[0x800000],rr_ng_reached_bios[0x10000];
RrNgRamVariant rr_ng_ram_variants[4096];
unsigned rr_ng_ram_variant_count,rr_ng_ram_observations_truncated;
static uint16_t ram_variant_slots[8192];
static void observe_ram(uint32_t pc,const RrM68000CodeLocation *loc) {
    extern int rr_ng_code_word(uint32_t,uint16_t*);
    RrNgRamVariant value={0};value.offset=(uint16_t)loc->physical_offset;
    unsigned length=loc->available_bytes/2;if(length>8)length=8;
    uint32_t hash=loc->physical_offset*2654435761u;
    for(unsigned n=0;n<length;++n) {
        if(!rr_ng_code_word(pc+n*2,&value.words[n]))break;
        ++value.count;hash=(hash^value.words[n])*16777619u;
    }
    if(!value.count)return;
    for(unsigned slot=hash&8191u,n=0;n<32;++n,slot=(slot+1)&8191u) {
        unsigned index=ram_variant_slots[slot];
        if(index) {
            const RrNgRamVariant *old=&rr_ng_ram_variants[index-1];
            if(old->offset==value.offset && old->count==value.count &&
               !memcmp(old->words,value.words,value.count*2))return;
        } else {
            if(rr_ng_ram_variant_count>=4096)break;
            rr_ng_ram_variants[rr_ng_ram_variant_count]=value;
            ram_variant_slots[slot]=(uint16_t)++rr_ng_ram_variant_count;return;
        }
    }
    rr_ng_ram_observations_truncated=1;
}
int rr_ng_test_clock_enabled;
int64_t rr_ng_test_clock;
FILE *rr_ng_cpu_trace;
uint64_t rr_ng_trace_from,rr_ng_trace_limit,rr_ng_trace_step;
unsigned rr_ng_trace_stride=1;
/* Bounded numeric diagnostics identify the actual mapped miss, including
 * bank aliases. No file is created unless the caller requests a report. */
typedef struct {uint32_t pc,region,offset;uint16_t opcode;uint64_t count;} RrNgMiss;
static RrNgMiss misses[16384];
static unsigned misses_full;
void rr_ng_note_instruction(uint32_t pc,int native) {
    rr_m68000_count_instruction(native);if(native)return;
#ifdef RR_NG_NATIVE
    extern int rr_ng_force_reference;if(rr_ng_force_reference)return;
#endif
    RrM68000CodeLocation loc={0};uint16_t opcode=0;
    extern int rr_ng_code_word(uint32_t,uint16_t*);
    if(!rr_ng_code_location(pc,&loc))loc.physical_offset=pc&0xffffffu;
    rr_ng_code_word(pc,&opcode);
    if(rr_feedback_enabled() && loc.available_bytes>=2) {
        uint8_t bytes[16];unsigned size=loc.available_bytes<16?loc.available_bytes:16;size&=~1u;
        for(unsigned n=0;n<size/2;++n) {
            uint16_t word;if(!rr_ng_code_word(pc+2*n,&word)) {size=n*2;break;}
            bytes[n*2]=(uint8_t)(word>>8);bytes[n*2+1]=(uint8_t)word;
        }
        if(loc.region==RR_M68000_CODE_RAM)
            rr_feedback_note(RR_FB_NG_RAM,loc.physical_offset,0,bytes,size);
        else if(loc.region==RR_M68000_CODE_CART || loc.region==RR_M68000_CODE_BIOS)
            rr_feedback_note(RR_FB_NG_ROM,loc.physical_offset,loc.region,bytes,2);
    }
    if(!rr_ng_observations)return;
    unsigned slot=(pc^(loc.physical_offset*2654435761u)^(loc.region*131u)^opcode)&16383u;
    for(unsigned n=0;n<32;++n,slot=(slot+1)&16383u) {
        RrNgMiss *m=&misses[slot];
        if(!m->count) {*m=(RrNgMiss){pc,loc.region,loc.physical_offset,opcode,1};return;}
        if(m->pc==pc && m->region==loc.region && m->offset==loc.physical_offset && m->opcode==opcode) {++m->count;return;}
    }
    misses_full=1;
}
void rr_ng_fallback_report(FILE *file) {
    fprintf(file,",\"fallback_68000\":[");unsigned comma=0;
    for(unsigned n=0;n<16384;++n)if(misses[n].count) {
        const RrNgMiss *m=&misses[n];
        fprintf(file,"%s{\"pc\":%u,\"region\":%u,\"offset\":%u,\"opcode\":%u,\"count\":%llu}",
            comma?",":"",m->pc,m->region,m->offset,m->opcode,m->count);comma=1;
    }
    fprintf(file,"],\"fallback_diagnostics_truncated\":%s",misses_full?"true":"false");
}
static void instruction(unsigned pc) {
    pc &= 0xffffff;
#ifndef RR_NG_NATIVE
    rr_m68000_count_instruction(0);
#endif
    if(!rr_ng_observations)return;
    if(rr_ng_cpu_trace && rr_ng_trace_step>=rr_ng_trace_from &&
       rr_ng_trace_step-rr_ng_trace_from<rr_ng_trace_limit &&
       (rr_ng_trace_step-rr_ng_trace_from)%rr_ng_trace_stride==0) {
        fprintf(rr_ng_cpu_trace,"%llu %06x %04x %llu",rr_ng_trace_step,pc,m68k_get_reg(NULL,M68K_REG_SR),rr_m68000_stats()->clocks);
        for(unsigned n=0;n<16;++n)fprintf(rr_ng_cpu_trace," %08x",m68k_get_reg(NULL,(m68k_register_t)(M68K_REG_D0+n)));
        fputc('\n',rr_ng_cpu_trace);
    }
    ++rr_ng_trace_step;
    rr_ng_reached_pc[pc >> 1] = 1;
    RrM68000CodeLocation loc;int mapped=!(pc&1u) && rr_ng_code_location(pc,&loc);
    if(mapped) {
        if(loc.region==RR_M68000_CODE_CART && loc.physical_offset<0x1000000u)
            rr_ng_reached_p[loc.physical_offset>>1]=1;
        else if(loc.region==RR_M68000_CODE_BIOS && loc.physical_offset<0x20000u)
            rr_ng_reached_bios[loc.physical_offset>>1]=1;
        else if(loc.region==RR_M68000_CODE_RAM)observe_ram(pc,&loc);
    }
    if(mapped && loc.region==RR_M68000_CODE_BIOS)++rr_ng_bios_instructions;
    else if(mapped && loc.region==RR_M68000_CODE_RAM)++rr_ng_ram_instructions;
    else if(mapped && loc.region==RR_M68000_CODE_CART)++rr_ng_cart_instructions;
    else if(pc<0x100000 || (pc>=0x200000 && pc<0x300000))++rr_ng_cart_instructions;
}
void rr_ng_reference_observer_enable(void) {
#ifdef RR_NG_NATIVE
    m68k_set_instr_hook_callback(rr_ng_observations?instruction:NULL);
#else
    /* Reference-only builds still count actual retired instructions. */
    m68k_set_instr_hook_callback(instruction);
#endif
}
static void init(void *ctx) {
    (void)ctx; m68k_init(); m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    m68k_set_instr_hook_callback(instruction);
}
static void reset(void *ctx) { (void)ctx; m68k_pulse_reset(); }
static int run(void *ctx, unsigned clocks) { (void)ctx; return m68k_execute(clocks); }
static void wait(void *ctx, int clocks) { (void)ctx; m68k_modify_timeslice(clocks); }
static void set_irq(void *ctx, unsigned level, unsigned value) { (void)ctx; m68k_set_virq(level, value); }
static unsigned get_irq(void *ctx, unsigned level) { (void)ctx; return m68k_get_virq(level); }
static uint8_t read8(void *ctx, uint32_t address) { (void)ctx; return (uint8_t)m68k_read_memory_8(address); }
static uint16_t read16(void *ctx, uint32_t address) { (void)ctx; return (uint16_t)m68k_read_memory_16(address); }
static void write8(void *ctx, uint32_t address, uint8_t value) { (void)ctx; m68k_write_memory_8(address, value); }
static void write16(void *ctx, uint32_t address, uint16_t value) { (void)ctx; m68k_write_memory_16(address, value); }
static int ack(void *ctx, unsigned level) { (void)ctx; return geo_m68k_int_ack((int)level); }
/* NULL means external RESET must be qualified before an AOT backend handles it. */
static int location(void *ctx,uint32_t address,RrM68000CodeLocation *value) {
    (void)ctx;return rr_ng_code_location(address,value);
}
static const RrM68000Bus bus = {NULL, read8, read16, write8, write16, ack, NULL, location};
const RrM68000Bus *rr_ng_cpu_bus(void) { return &bus; }
void rr_ng_reference_bind(void) {
    const RrM68000Backend backend = {NULL, init, reset, run, wait, set_irq, get_irq};
    rr_m68000_bind(&backend);
}
