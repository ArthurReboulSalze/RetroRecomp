/* Authored CPU/bus/guard differential fixtures; no retail ROM/BIOS. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "neogeo_z80_native.h"
#include "fixture_data.h"
int rr_ng_force_reference,rr_ng_force_z80_reference;
uint64_t rr_ng_native_z80,rr_ng_z80_instructions,rr_ng_m1_instructions,rr_ng_sm1_instructions;
uint8_t rr_ng_z80_fallback_pc[65536];
static uint8_t memory[65536],before[65536],expected[65536];
static uint32_t physical;
static uint64_t bus_hash;
static unsigned bus_events;
static void bus(unsigned type,unsigned address,unsigned value) {
    bus_hash=(bus_hash^((uint64_t)type<<32)^((uint64_t)address<<8)^value)*1099511628211ull;++bus_events;
}
static uint8_t read_byte(void *ctx,uint16_t a) {(void)ctx;bus(0,a,memory[a]);return memory[a];}
static void write_byte(void *ctx,uint16_t a,uint8_t v) {(void)ctx;bus(1,a,v);memory[a]=v;}
static uint8_t port_in(z80 *z,uint16_t p) {uint8_t v=(uint8_t)(p^(p>>8)^z->a^0x65);bus(2,p,v);return v;}
static void port_out(z80 *z,uint16_t p,uint8_t v) {(void)z;bus(3,p,v);}
int rr_ng_z80_code_location(uint16_t pc,unsigned *region,uint32_t *offset) {
    if(pc>=0xf800)return 0;*region=1;*offset=physical;return 1;
}
int rr_ng_z80_code_byte(uint16_t pc,uint8_t *v) {*v=memory[pc];return 1;}
void rr_ng_z80_observe(uint16_t pc) {(void)pc;}
void rr_ng_z80_note_fallback(uint16_t pc) {rr_ng_z80_fallback_pc[pc]=1;}
static z80 initial(unsigned seed) {
    z80 z={0};z80_init(&z);z.read_byte=read_byte;z.write_byte=write_byte;z.port_in=port_in;z.port_out=port_out;
    z.pc=0x400;z.sp=seed&1?0:0xf100;z.ix=0xc234;z.iy=0xe431;z.mem_ptr=0xbe91;
    z.af=(uint16_t)(seed*13067);z.bc=(uint16_t)(seed*17+0x111);z.de=0xc321;z.hl=0xe543;
    z.a_f_=0xabcd;z.b_c_=0x5432;z.d_e_=0x6789;z.h_l_=0x1234;z.i=0xf2;z.r=0xff;
    z.iff1=z.iff2=seed&1;z.iff_delay=seed%3;z.interrupt_mode=seed%3;
    z.irq_pending=seed&2?Z80_PULSE:0;z.nmi_pending=seed&4?Z80_PULSE:0;z.irq_data=0xff;
    return z;
}
static void clear_bus(void) {bus_hash=14695981039346656037ull;bus_events=0;rr_ng_native_z80=rr_ng_z80_instructions=0;}
int main(void) {
    unsigned checked=0,guards=0;
    for(unsigned i=0;i<sizeof instructions/sizeof *instructions;++i)for(unsigned seed=0;seed<8;++seed) {
        physical=0x1000+i*8;
        for(unsigned n=0;n<65536;++n)memory[n]=(uint8_t)(n*73+seed*17);
        memcpy(memory+0x400,instructions[i],4);memcpy(before,memory,sizeof memory);
        z80 z=initial(seed);rr_ng_force_reference=1;clear_bus();unsigned cycles=z80_step(&z);
        uint64_t expected_bus=bus_hash;unsigned events=bus_events;memcpy(expected,memory,sizeof memory);
        memcpy(memory,before,sizeof memory);z80 native=initial(seed);rr_ng_force_reference=0;clear_bus();unsigned actual=z80_step(&native);
        if(cycles!=actual || memcmp(&z,&native,sizeof z) || memcmp(memory,expected,sizeof memory) || expected_bus!=bus_hash || events!=bus_events || rr_ng_native_z80!=1) {
            fprintf(stderr,"Z80 case %u (%02x%02x%02x%02x) seed %u cycles %u/%u bus %u/%u native %llu CPUdiff=%d MEMdiff=%d BUSdiff=%d\n",i,instructions[i][0],instructions[i][1],instructions[i][2],instructions[i][3],seed,cycles,actual,events,bus_events,rr_ng_native_z80,memcmp(&z,&native,sizeof z),memcmp(memory,expected,sizeof memory),expected_bus!=bus_hash);return 2;
        }
        ++checked;
    }
    /* Immediate operand changes retain native execution. A structural opcode
     * change escapes before any real fetch, with no duplicate bus access. */
    const uint8_t code[4]={0x3e,0x23,0,0};
    for(unsigned i=0;i<sizeof instructions/sizeof *instructions;++i)if(instructions[i][0]==0x3e) {
        physical=0x1000+i*8;
        for(unsigned change=0;change<2;++change) {
            memset(memory,0,sizeof memory);memcpy(memory+0x400,code,4);
            memory[0x400+!change]=(uint8_t)(change?0x00:0x91);memcpy(before,memory,sizeof memory);
            z80 z=initial(0);rr_ng_force_reference=1;clear_bus();unsigned expected_cycles=z80_step(&z);uint64_t hash=bus_hash;
            memcpy(memory,before,sizeof memory);z80 n=initial(0);rr_ng_force_reference=0;clear_bus();unsigned cycles=z80_step(&n);
            if(cycles!=expected_cycles || memcmp(&n,&z,sizeof z) || hash!=bus_hash || rr_ng_native_z80!=(change?0u:1u))return 3;
            ++guards;
        }
    }
    /* Mutable RAM branch, including a live target and a changed opcode. */
    for(unsigned mutate=0;mutate<2;++mutate) {
        memset(memory,0,sizeof memory);memory[0xfffd]=mutate?0x00:0xc3;memory[0xfffe]=0x23;memory[0xffff]=0x81;
        z80 z=initial(0);z.pc=0xfffd;rr_ng_force_reference=1;clear_bus();unsigned expected_cycles=z80_step(&z);uint64_t hash=bus_hash;
        z80 n=initial(0);n.pc=0xfffd;rr_ng_force_reference=0;clear_bus();unsigned cycles=z80_step(&n);
        if(cycles!=expected_cycles || memcmp(&n,&z,sizeof z) || hash!=bus_hash || rr_ng_native_z80!=(mutate?0u:1u))return 4;
        ++guards;
    }
    printf("{\"passed\":true,\"instruction_comparisons\":%u,\"guard_checks\":%u,\"full_16bit_port_bus_compared\":true}\n",checked,guards);return 0;
}
