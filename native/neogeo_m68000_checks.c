/* Authored architectural ABI/cycle/exception fixtures; no retail data. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "m68k/m68k.h"
#include "neogeo_native.h"
#include "m68000_backend.h"
#include "fixture_data.h"
static uint8_t memory[0x1000000],expected[65536];
static uint8_t banked[0x20000];
static unsigned active_bank;
static unsigned native_count,fallback_count;
int geo_m68k_int_ack(int level) {m68k_set_virq((unsigned)level,0);return M68K_INT_ACK_AUTOVECTOR;}
unsigned m68k_read_memory_8(unsigned a) {
    a&=0xffffff;if(a>=0x200000 && a<0x210000)return banked[active_bank*0x10000+(a&0xffff)];
    if(a>=0x100000 && a<0x200000)a=0x100000+(a&0xffff);
    return memory[a];
}
unsigned m68k_read_memory_16(unsigned a) {return (m68k_read_memory_8(a)<<8)|m68k_read_memory_8(a+1);}
unsigned m68k_read_memory_32(unsigned a) {return (m68k_read_memory_16(a)<<16)|m68k_read_memory_16(a+2);}
void m68k_write_memory_8(unsigned a,unsigned v) {
    a&=0xffffff;if(a>=0x100000 && a<0x200000)a=0x100000+(a&0xffff);
    memory[a]=(uint8_t)v;
}
void m68k_write_memory_16(unsigned a,unsigned v) {m68k_write_memory_8(a,v>>8);m68k_write_memory_8(a+1,v);}
void m68k_write_memory_32(unsigned a,unsigned v) {m68k_write_memory_16(a,v>>16);m68k_write_memory_16(a+2,v);}
int rr_ng_code_location(uint32_t pc,RrM68000CodeLocation *loc) {
    memset(loc,0,sizeof *loc);pc&=0xffffffu;
    if(pc<0x10000) {loc->region=1;loc->physical_offset=pc;loc->available_bytes=0x10000-pc;return 1;}
    if(pc>=0xc00000 && pc<0xc20000) {loc->region=2;loc->physical_offset=pc-0xc00000;loc->available_bytes=0xc20000-pc;return 1;}
    if(pc>=0x100000 && pc<0x200000) {
        loc->region=3;loc->physical_offset=pc&0xffff;loc->available_bytes=0x10000-(pc&0xffff);loc->mutable_code=1;return 1;
    }
    if(pc>=0x200000 && pc<0x210000) {
        loc->region=1;loc->physical_offset=0x100000+active_bank*0x10000+(pc&0xffff);
        loc->available_bytes=0x210000-pc;return 1;
    }
    return 0;
}
int rr_ng_code_word(uint32_t pc,uint16_t *word) {*word=(uint16_t)m68k_read_memory_16(pc);return 1;}
int rr_ng_code_matches(const RrM68000CodeLocation *loc,const uint16_t *words,unsigned count) {
    if(!count || count>8 || count*2>loc->available_bytes)return 0;
    const uint8_t *src=loc->region==2?memory+0xc00000+loc->physical_offset:
        loc->region==3?memory+0x100000+loc->physical_offset:
        loc->physical_offset>=0x100000?banked+(loc->physical_offset-0x100000):memory+loc->physical_offset;
    for(unsigned n=0;n<count;++n)if(((src[2*n]<<8)|src[2*n+1])!=words[n])return 0;
    return 1;
}
void rr_ng_note_instruction(uint32_t pc,int native) {(void)pc;if(native)++native_count;else ++fallback_count;}
/* Chained native runs count once and charge fixture fetches no wait. */
void rr_m68000_count_native(unsigned count) {native_count+=count;}
void rr_m68000_wait(int clocks) {(void)clocks;}
const uint8_t *rr_ng_code_bytes(uint32_t pc,RrM68000CodeLocation *loc,unsigned *word_waits) {
    if(!rr_ng_code_location(pc,loc))return NULL;
    *word_waits=0;
    return loc->region==2?memory+0xc00000+loc->physical_offset:
        loc->region==3?memory+0x100000+loc->physical_offset:
        loc->physical_offset>=0x100000?banked+(loc->physical_offset-0x100000):memory+loc->physical_offset;
}
int rr_ng_observations;
/* The fixture board is an MVS (Geolith SYSTEM_MVS): BIOS code is region 2. */
int geo_get_system(void) {return 1;}
void rr_ng_reference_bind(void) {}
static uint32_t result[20];
static void state(uint32_t *out) {
    for(unsigned n=0;n<16;++n)out[n]=m68k_get_reg(NULL,(m68k_register_t)(M68K_REG_D0+n));
    out[16]=m68k_get_reg(NULL,M68K_REG_PC);out[17]=m68k_get_reg(NULL,M68K_REG_SR);
    out[18]=m68k_get_reg(NULL,M68K_REG_USP);out[19]=m68k_get_reg(NULL,M68K_REG_ISP);
}
static void initial(unsigned pc,unsigned seed,unsigned irq) {
    memset(memory,0,sizeof memory);memset(banked,0,sizeof banked);
    for(unsigned v=2;v<256;++v)m68k_write_memory_32(v*4,0x1000);
    for(unsigned n=0;n<sizeof instructions/sizeof *instructions;++n) {
        unsigned address=0x200+n*32;
        for(unsigned w=0;w<8;++w) {
            m68k_write_memory_16(address+w*2,instructions[n][w]);
            m68k_write_memory_16(0xc00000+address+w*2,instructions[n][w]);
            for(unsigned bank=0;bank<2;++bank) {
                unsigned word=instructions[n][w];
                if(bank && !w && word==0x7001)word=0x7007;
                unsigned offset=bank*0x10000+address+w*2;
                banked[offset]=(uint8_t)(word>>8);banked[offset+1]=(uint8_t)word;
            }
        }
    }
    m68k_write_memory_16(0x1000,0x4e71);m68k_write_memory_16(0xc01000,0x4e71);
    for(unsigned bank=0;bank<2;++bank) {banked[bank*0x10000+0x1000]=0x4e;banked[bank*0x10000+0x1001]=0x71;}
    m68k_write_memory_32(0,0x100200);m68k_write_memory_32(4,pc);
    m68k_init();m68k_set_cpu_type(M68K_CPU_TYPE_68000);m68k_pulse_reset();m68k_execute(1);
    for(unsigned n=0;n<8;++n)m68k_set_reg((m68k_register_t)(M68K_REG_D0+n),seed*419+n*9+1407);
    m68k_set_reg(M68K_REG_D1,seed+9);m68k_set_reg(M68K_REG_D2,seed&63);
    for(unsigned n=0;n<7;++n)m68k_set_reg((m68k_register_t)(M68K_REG_A0+n),0x100800+n*256);
    m68k_set_reg(M68K_REG_A7,0x100200);m68k_set_reg(M68K_REG_USP,0x100400);
    for(unsigned n=0;n<65536;++n)memory[0x100000+n]=(uint8_t)(n*73+seed*17);
    for(unsigned n=0;n<sizeof instructions/sizeof *instructions;++n)
        for(unsigned w=0;w<8;++w)m68k_write_memory_16(0x10f200+n*32+w*2,instructions[n][w]);
    m68k_write_memory_16(0x100200,0x2000|(seed&31));m68k_write_memory_32(0x100202,0x1000);
    m68k_set_reg(M68K_REG_SR,0x2000|(seed&31));
    m68k_set_virq(2,irq);native_count=fallback_count=0;
}
static void edge_registers(uint32_t d0,uint32_t d1,unsigned x) {
    m68k_set_reg(M68K_REG_D0,d0);m68k_set_reg(M68K_REG_D1,d1);
    m68k_set_reg(M68K_REG_SR,0x2000|(x?0x10:0));
}
int main(void) {
    unsigned comparisons=0,guards=0,shift_edges=0,shift_failures=0,failed_by_op[4]={0,0,0,0};
    /* Region 6 enters cartridge code through a pointer with a flagged high
     * byte: branch targets and pushed return addresses keep the 32-bit PC. */
    for(unsigned region=0;region<7;++region)for(unsigned i=0;i<sizeof instructions/sizeof *instructions;++i)
    for(unsigned seed=0;seed<16;++seed) {
        active_bank=region==3;
        unsigned pc=(region==6?0x80000000u:region>=4?(region==4?0x10f000:0x1af000):region>=2?0x200000:region?0xc00000:0)+0x200+i*32;
        rr_ng_force_reference=1;initial(pc,seed,0);int clocks=m68k_execute(1);state(result);memcpy(expected,memory+0x100000,sizeof expected);
        rr_ng_force_reference=0;initial(pc,seed,0);int actual=m68k_execute(1);uint32_t values[20];state(values);
        if(clocks!=actual || memcmp(result,values,sizeof result) || memcmp(expected,memory+0x100000,sizeof expected) || native_count!=1) {
            fprintf(stderr,"MC68000 case %u / %04x region %u seed %u clocks %d/%d native %u CPUdiff=%d MEMdiff=%d\n",i,instructions[i][0],region,seed,clocks,actual,native_count,memcmp(result,values,sizeof result),memcmp(expected,memory+0x100000,sizeof expected));
            for(unsigned n=0;n<20;++n)if(result[n]!=values[n])fprintf(stderr,"reg %u: %08x/%08x\n",n,result[n],values[n]);return 2;
        }
        ++comparisons;
    }
    /* Register-count shifts at the edges the seeds above never reach (they leave X clear and the
     * count small): X=1, a count of 0, 64 (0 modulo 64), 17 (ROXL.W period) and 31 (ASL.L). */
    for(unsigned i=0;i<sizeof instructions/sizeof *instructions;++i) {
        unsigned op=instructions[i][0];
        if(op!=0xe370 && op!=0xe2b0 && op!=0xe3a0 && op!=0xe270)continue;
        static const uint32_t d0s[]={0xffffffffu,0x80000000u,0x7fffffffu},counts[]={0,64,31,17};
        for(unsigned region=0;region<7;++region)for(unsigned x=0;x<2;++x)
        for(unsigned a=0;a<3;++a)for(unsigned b=0;b<4;++b) {
            active_bank=region==3;
            unsigned pc=(region==6?0x80000000u:region>=4?(region==4?0x10f000:0x1af000):region>=2?0x200000:region?0xc00000:0)+0x200+i*32;
            rr_ng_force_reference=1;initial(pc,0,0);edge_registers(d0s[a],counts[b],x);
            int clocks=m68k_execute(1);state(result);
            rr_ng_force_reference=0;initial(pc,0,0);edge_registers(d0s[a],counts[b],x);
            int actual=m68k_execute(1);uint32_t values[20];state(values);
            if(clocks!=actual || memcmp(result,values,sizeof result) || native_count!=1) {
                ++shift_failures;++failed_by_op[op==0xe370?0:op==0xe2b0?1:op==0xe3a0?2:3];
                if(shift_failures<=4 || (op==0xe3a0 && failed_by_op[2]<=2)) {
                    fprintf(stderr,"MC68000 shift %04x D0=%08x D1=%u X=%u region %u clocks %d/%d native %u\n",op,d0s[a],counts[b],x,region,clocks,actual,native_count);
                    for(unsigned n=0;n<20;++n)if(result[n]!=values[n])fprintf(stderr,"reg %u: musashi %08x / native %08x\n",n,result[n],values[n]);
                }
                continue;
            }
            ++comparisons;++shift_edges;
        }
    }
    if(shift_failures) {
        fprintf(stderr,"%u shift edge cases differ from Musashi (ROXL.W %u, ROXR.L %u, ASL.L %u, ROXR.W %u)\n",shift_failures,failed_by_op[0],failed_by_op[1],failed_by_op[2],failed_by_op[3]);
        return 6;
    }
    /* Stale immutable bytes must escape without running the old body. */
    rr_ng_force_reference=0;initial(0x200,0,0);m68k_write_memory_16(0x200,0x7001);m68k_execute(1);
    if(native_count || fallback_count!=1 || m68k_get_reg(NULL,M68K_REG_D0)!=1)return 3;++guards;
    /* Accepted IRQ uses the canonical vector/stack state, then resumes AOT. */
    rr_ng_force_reference=1;initial(0x200,0,1);int clocks=m68k_execute(1);state(result);memcpy(expected,memory+0x100000,sizeof expected);
    rr_ng_force_reference=0;initial(0x200,0,1);int actual=m68k_execute(1);uint32_t values[20];state(values);
    if(clocks!=actual || memcmp(result,values,sizeof result) || memcmp(expected,memory+0x100000,sizeof expected))return 4;++guards;
    /* Two observed immediates share one RAM PC; an unseen value must fall back. */
    for(unsigned variant=0;variant<3;++variant) {
        static const uint32_t values[]={0x11223344,0x55667788,0xdeadbeef};
        rr_ng_force_reference=0;initial(0x10fc00,0,0);
        m68k_write_memory_16(0x10fc00,0x203c);m68k_write_memory_32(0x10fc02,values[variant]);m68k_execute(1);
        if(m68k_get_reg(NULL,M68K_REG_D0)!=values[variant] || native_count!=(variant<2) || fallback_count!=(variant==2))return 5;
        ++guards;
    }
    printf("{\"passed\":true,\"architectural_comparisons\":%u,\"shift_edge_comparisons\":%u,\"guard_irq_checks\":%u,\"physical_bank_aliases\":2,\"physical_bus_phases_qualified\":false}\n",comparisons,shift_edges,guards);return 0;
}
