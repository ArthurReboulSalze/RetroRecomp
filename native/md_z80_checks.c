/* Differential instruction checks plus independent opcode/IRQ/guard fixtures. */
#include "md_z80_native.h"
#include "fixture_data.h"
#include "phase_data.h"
#include <stdlib.h>
#include <string.h>

static unsigned char memory[65536], saved[65536], expected[65536];
static int force_reference, deny_peek;
static uint64_t bus_hash;
static unsigned bus_reads, bus_writes;
static unsigned ticks, phase_count;
static unsigned mutation_address, mutation_value, mutation_read;
typedef struct { unsigned tick, address, value, write; } Phase;
static Phase phases[64];
void machine_z80_cycles(unsigned cycles) { ticks += cycles; }
static void trace(unsigned address,unsigned value,unsigned write) {
    if(phase_count<64)phases[phase_count++]=(Phase){ticks,address,value,write};
}
/* Instruction-only fixture: no DMA owns this authored flat address space. */
void machine_z80_bus_wait(void) {}
void machine_z80_bus_barrier(void) {}
void machine_z80_boundary(void) {}
void machine_z80_instruction_boundary(void) {}
void machine_z80_access(uint16_t address) { (void)address; }
void machine_z80_write(uint16_t address) { (void)address; }
void machine_z80_fallback(void) {}
/* Learning is not part of this fixture. */
void rr_feedback_note(unsigned kind, uint32_t address, uint32_t auxiliary,
                      const uint8_t *bytes, unsigned length) {
    (void)kind; (void)address; (void)auxiliary; (void)bytes; (void)length;
}
static void demand(int ok, const char *message) {
    if (!ok) { fprintf(stderr, "Z80 fixture: %s\n", message); exit(2); }
}
static uint8_t read_byte(void *context, uint16_t pc) {
    (void)context;
    /* Simulate a writer while this exact fetch is suspended, AFTER the
     * dispatcher's side-effect-free peek and BEFORE the bus returns data. */
    if(mutation_read && pc==mutation_address) {
        memory[pc]=(uint8_t)mutation_value;mutation_read=0;
    }
    trace(pc,memory[pc],0); return memory[pc];
}
static void write_byte(void *context, uint16_t pc, uint8_t value) {
    (void)context; memory[pc] = value;
    trace(pc,value,1);
    bus_hash = (bus_hash ^ ((uint32_t)pc << 8) ^ value) * 1099511628211ull; ++bus_writes;
}
static uint8_t port_in(z80 *z, uint8_t port) {
    trace(0x10000u|port,0,2);
    ++bus_reads; return (uint8_t)(z->b ^ port ^ 0xa5);
}
static void port_out(z80 *z, uint8_t port, uint8_t value) {
    trace(0x10000u|port,value,3);
    bus_hash = (bus_hash ^ ((uint32_t)z->b << 16) ^ ((uint32_t)port << 8) ^ value) * 1099511628211ull;
    ++bus_writes;
}
int rr_md_z80_force_reference(void) { return force_reference; }
int rr_md_z80_probe(void) { return 0; }
int rr_md_z80_peek(uint16_t pc, uint8_t *value) {
    if (deny_peek) return 0;
    *value = memory[pc]; return 1;
}
static z80 initial(uint16_t pc, unsigned seed) {
    z80 z = {0}; z80_init(&z);
    z.read_byte = read_byte; z.write_byte = write_byte; z.port_in = port_in; z.port_out = port_out;
    z.pc = pc; z.sp = seed & 1 ? 0 : 0xf010; z.ix = 0xc137; z.iy = 0xe27a; z.mem_ptr = 0xab34;
    z.a = (uint8_t)(seed * 67); z.b = seed & 1 ? 1 : (uint8_t)(seed + 2); z.c = 1;
    z.d = 0xe1; z.e = 0x17; z.h = 0xc2; z.l = 0x27;
    z.a_ = 0x73; z.f_ = 0xe5; z.b_ = 0x62; z.c_ = 0x88;
    z.d_ = 0x42; z.e_ = 0x36; z.h_ = 0x58; z.l_ = 0x79;
    z.sf = seed & 1; z.zf = seed & 2; z.yf = seed & 4; z.hf = seed & 8;
    z.xf = seed & 1; z.pf = seed & 2; z.nf = seed & 4; z.cf = seed & 8;
    z.i = 0xf2; z.r = 0xff; z.iff1 = z.iff2 = seed & 1;
    z.interrupt_mode = seed % 3; z.int_pending = seed & 4; z.nmi_pending = seed & 8; z.int_data = 0xff;
    z.iff_delay = seed % 4 == 0; z.cyc = 100;
    return z;
}
static void clear_bus(void) { bus_hash = 14695981039346656037ull; bus_reads = bus_writes = ticks = phase_count = 0; }
static void phase_baseline(void) {
    /* Zilog UM008011: LD A,(nn) = fetch 4T, low 3T, high 3T, data 3T.
     * The data request must be at T10, not at instruction start. */
    for(unsigned i=0;i<sizeof instructions/sizeof instructions[0];++i)if(instructions[i][0]==0x3a) {
        unsigned pc=4*i;
        memory[pc]=0x3a;memory[pc+1]=0;memory[pc+2]=0x80;memory[0x8000]=0x61;
        z80 z=initial(pc,0);z.int_pending=z.nmi_pending=z.iff_delay=0;
        clear_bus();rr_md_z80_step(&z);
        for(unsigned j=0;j<phase_count;++j)if(phases[j].address==0x8000) {
            if(phases[j].tick!=10)fprintf(stderr,"LD A,(nn) data request: T%u, expected T10\n",phases[j].tick);
            demand(phases[j].tick==10,"operand phase");return;
        }
        demand(0,"missing operand access");
    }
}
static unsigned authored_phases(void) {
    unsigned checked=0;
    for(unsigned i=0;i<sizeof phase_cases/sizeof *phase_cases;++i)for(int ref=0;ref<2;++ref)
    for(unsigned wrap=0;wrap<2;++wrap) {
        const PhaseCase *c=&phase_cases[i];unsigned pc=0x9000+16*i;
        memset(memory,0x55,sizeof memory);memcpy(memory+pc,c->code,sizeof c->code);
        z80 z=initial(pc,0);z.int_pending=z.nmi_pending=z.iff_delay=0;
        z.h=0x81;z.l=0;z.ix=0x8200;z.iy=0x8300;z.sp=0x8402;
        z.b=0x85;z.c=0;z.d=0x86;z.e=0;z.zf=0;z.cyc=wrap?~0ul-7:0;
        unsigned long before=z.cyc;
        clear_bus();rr_md_z80_reset_evidence();force_reference=ref;rr_md_z80_step(&z);force_reference=0;
        int ok=ticks==c->total && z.cyc-before==c->total && phase_count==c->count && !rr_md_z80_timing_misses();
        for(unsigned e=0;e<c->count && ok;++e) {
            unsigned addr=c->events[e][1];if(addr<6)addr+=pc;
            ok=phases[e].tick==c->events[e][0] && phases[e].address==addr && phases[e].write==c->events[e][2];
        }
        if(!ok) {
            fprintf(stderr,"Phase case %u ref=%d total=%u/%u cycles=%lu events=%u/%u\n",i,ref,ticks,c->total,z.cyc-before,phase_count,c->count);
            for(unsigned e=0;e<phase_count;++e)fprintf(stderr," T%u %x type%u\n",phases[e].tick,phases[e].address,phases[e].write);
            demand(0,"independent nominal phase sequence");
        }
        demand(ref || !rr_md_z80_fallback_opcodes(),"authored phase must stay native");++checked;
    }
    return checked;
}
static unsigned interrupt_phases(void) {
    unsigned count=0;
    for(int ref=0;ref<2;++ref)for(int mode=0;mode<4;++mode) {
        memset(memory,0,sizeof memory);
        z80 z=initial(0x9000,0);z.sp=0x8402;z.i=0x80;z.int_data=0xff;
        z.iff_delay=0;z.iff1=z.iff2=1;z.int_pending=mode!=3;z.nmi_pending=mode==3;
        z.interrupt_mode=mode%3;z.cyc=0;z.r=0;memory[0x80ff]=0x34;memory[0x8100]=0x12;
        clear_bus();rr_md_z80_reset_evidence();force_reference=ref;rr_md_z80_step(&z);force_reference=0;
        unsigned ack=mode==3?5:7,total=4+(mode==3?11:mode==2?19:13);
        demand(z.cyc==total && ticks==total && !rr_md_z80_timing_misses(),"NMI/IM0 FF/IM1/IM2 total");
        demand(phase_count==(mode==2?5:3),"interrupt bus access count");
        demand(phases[1].tick==4+ack && phases[1].address==0x8401 && phases[1].write==1 &&
               phases[2].tick==7+ack && phases[2].address==0x8400 && phases[2].write==1,"interrupt stack order/phase");
        if(mode==2)demand(phases[3].tick==17 && phases[3].address==0x80ff &&
                         phases[4].tick==20 && phases[4].address==0x8100,"IM2 vector follows stack");
        demand(z.pc==(mode==3?0x66:mode==2?0x1234:0x38),"interrupt target");
        demand(z.r==2,"one refresh increment for opcode, one for interrupt acknowledge");
        demand(ref || !rr_md_z80_fallback_opcodes(),"interrupt phase native coverage");++count;
    }
    return count;
}
static unsigned suspended_fetches(void) {
    unsigned checked=0;
    for(unsigned i=0;i<sizeof mutation_cases/sizeof *mutation_cases;++i) {
        unsigned pc=0xa000+16*i,count;
        const RrMdZ80Body *body=rr_md_z80_bodies(pc,&count);
        demand(count==1,"mutation fixture starts in a compiled variant");
        for(unsigned byte=0;byte<4;++byte)for(unsigned value=0;value<256;++value)
        for(unsigned irq=0;irq<2;++irq) {
            memset(memory,0x55,sizeof memory);memcpy(memory+pc,mutation_cases[i],4);
            memcpy(expected,memory,sizeof memory);
            z80 native=initial(pc,0);native.int_pending=irq;native.nmi_pending=0;
            native.iff_delay=0;native.iff1=native.iff2=irq;native.interrupt_mode=1;
            z80 reference=native;
            mutation_address=pc+byte;mutation_value=value;mutation_read=1;
            clear_bus();rr_md_z80_reset_evidence();rr_md_z80_step(&native);
            unsigned changed=(body->mask&(1u<<byte)) && value!=mutation_cases[i][byte];
            if(rr_md_z80_fallback_opcodes()!=changed || rr_md_z80_native_opcodes()!=!changed) {
                fprintf(stderr,"Mutation %u byte %u value %02x: native=%llu fallback=%llu expected=%u\n",
                    i,byte,value,rr_md_z80_native_opcodes(),rr_md_z80_fallback_opcodes(),changed);
                demand(0,"suspended fetch must not execute the stale native operation");
            }
            uint64_t hash=bus_hash;unsigned reads=bus_reads,writes=bus_writes;
            unsigned native_ticks=ticks,native_count=phase_count;Phase native_phases[64];
            memcpy(native_phases,phases,sizeof phases);memcpy(saved,memory,sizeof memory);
            unsigned long cost=native.cyc-100;
            demand(rr_md_z80_fallback_cycles()==(changed?cost:0) &&
                   rr_md_z80_native_cycles()==(changed?0:cost),"resume cycles counted once");
            memcpy(memory,expected,sizeof memory);mutation_read=1;
            clear_bus();z80_step(&reference);
            if(memcmp(&native,&reference,sizeof native) || memcmp(saved,memory,sizeof memory) ||
               hash!=bus_hash || reads!=bus_reads || writes!=bus_writes || native_ticks!=ticks ||
               native_count!=phase_count || memcmp(phases,native_phases,phase_count*sizeof *phases) ||
               rr_md_z80_timing_misses()) {
                fprintf(stderr,"Resume %u byte %u value %02x IRQ%u PC=%04x/%04x cyc=%lu/%lu R=%02x/%02x\n",
                    i,byte,value,irq,native.pc,reference.pc,native.cyc,reference.cyc,native.r,reference.r);
                demand(0,"resume must preserve consumed prefixes, cycles, refresh, IRQ and bus effects");
            }
            mutation_read=0;++checked;
        }
    }
    return checked;
}
int main(void) {
    phase_baseline();
    unsigned phase_checks=authored_phases();
    phase_checks+=interrupt_phases();
    unsigned resume_checks=suspended_fetches();
    unsigned comparisons = 0;
    for (unsigned i = 0; i < 65536; ++i) saved[i] = (uint8_t)(i * 71 + (i >> 8));
    for (unsigned op = 0; op < sizeof instructions / sizeof instructions[0]; ++op) {
        for (unsigned seed = 0; seed < 16; ++seed) {
            memcpy(memory, saved, sizeof memory);
            uint16_t pc = (uint16_t)(op * 4);
            memcpy(memory + pc, instructions[op], 4);
            /* Vary operands while preserving guarded operation bytes. */
            unsigned count; const RrMdZ80Body *body = rr_md_z80_bodies(pc, &count);
            demand(count == 1, "missing authored native variant");
            for (unsigned b = 0; b < 4; ++b) if (!(body->mask & (1u << b))) memory[pc + b] ^= (uint8_t)(seed * 29);
            z80 native = initial(pc, seed), reference = native;
            memcpy(expected, memory, sizeof memory);
            clear_bus(); rr_md_z80_reset_evidence(); rr_md_z80_step(&native);
            uint64_t hash = bus_hash; unsigned reads = bus_reads, writes = bus_writes;
            unsigned native_ticks=ticks,native_count=phase_count;Phase native_phases[64];
            memcpy(native_phases,phases,sizeof phases);
            demand(rr_md_z80_native_opcodes() == 1 && rr_md_z80_fallback_opcodes() == 0, "authored operation escaped to reference");
            memcpy(saved, memory, sizeof memory); memcpy(memory, expected, sizeof memory);
            clear_bus(); z80_step(&reference);
            if (memcmp(&native, &reference, sizeof native) || memcmp(saved, memory, sizeof memory) ||
                hash != bus_hash || reads != bus_reads || writes != bus_writes ||
                ticks!=native_ticks || phase_count!=native_count ||
                memcmp(phases,native_phases,phase_count*sizeof *phases) || rr_md_z80_timing_misses()) {
                fprintf(stderr, "Opcode fixture %u seed %u bytes=%02x%02x%02x%02x PC=%04x/%04x cyc=%lu/%lu\n",
                    op, seed, instructions[op][0], instructions[op][1], instructions[op][2], instructions[op][3],
                    native.pc, reference.pc, native.cyc, reference.cyc);
                demand(0, "native/reference state or ordered bus writes differ");
            }
            ++comparisons;
        }
    }
    /* Live immediate replacement must not trigger a fallback. Opcode
     * replacement, missing PC, denied I/O peeks must trigger counted escape. */
    unsigned ld_pc = 0;
    for (unsigned i = 0; i < sizeof instructions / sizeof instructions[0]; ++i)
        if (instructions[i][0] == 0x3e) { ld_pc = i * 4; break; }
    z80 z = initial((uint16_t)ld_pc, 0); z.int_pending = z.nmi_pending = 0;
    memory[ld_pc] = 0x3e; memory[ld_pc + 1] = 0x71;
    rr_md_z80_reset_evidence(); rr_md_z80_step(&z);
    demand(z.a == 0x71 && z.pc == ld_pc + 2 && z.cyc == 107 && !rr_md_z80_fallback_opcodes(), "mutable LD immediate");
    z.pc = ld_pc; memory[ld_pc] = 0x06; memory[ld_pc + 1] = 0x5a;
    rr_md_z80_step(&z); demand(z.b == 0x5a && rr_md_z80_fallback_opcodes() == 1, "changed opcode must escape");
    z.pc = 0x7000; memory[0x7000] = 0; rr_md_z80_step(&z);
    demand(rr_md_z80_fallback_opcodes() == 2, "unmapped PC must escape");
    z.pc = ld_pc; memory[ld_pc] = 0x3e; deny_peek = 1; rr_md_z80_step(&z); deny_peek = 0;
    demand(rr_md_z80_fallback_opcodes() == 3, "I/O code guard must escape");
    z.pc = ld_pc; force_reference = 1; rr_md_z80_step(&z); force_reference = 0;
    demand(rr_md_z80_fallback_opcodes() == 4, "reference override must be counted");
    z = initial(0xffff, 0); z.int_pending = z.nmi_pending = 0;
    memory[0xffff] = 0x3e; memory[0] = 0x6a; rr_md_z80_reset_evidence(); rr_md_z80_step(&z);
    demand(z.a == 0x6a && z.pc == 1 && !rr_md_z80_fallback_opcodes(), "PC wrap");
    z = initial(0x8000, 0); z.int_pending = z.nmi_pending = 0;
    memory[0x8000] = 0x21; memory[0x8001] = 0x42; memory[0x8002] = 0x39;
    rr_md_z80_step(&z); demand(z.h == 0x39 && z.l == 0x42 && !rr_md_z80_fallback_opcodes(), "banked live operands");
    memory[0x8000] = 0x31; z.pc = 0x8000; rr_md_z80_step(&z);
    demand(z.sp == 0x3942 && rr_md_z80_fallback_opcodes() == 1, "bank change must verify opcode");
    /* Independent EI delay / HALT refresh / IM1 stack-frame assertions. */
    unsigned ei_pc = 0;
    for (unsigned i = 0; i < sizeof instructions / sizeof instructions[0]; ++i)
        if (instructions[i][0] == 0xfb) { ei_pc = i * 4; break; }
    z = initial(ei_pc, 0); z.iff_delay = 0; z.iff1 = z.iff2 = 0; z.interrupt_mode = 1;
    z.int_pending = 1; z.nmi_pending = 0; z.sp = 0xf010; memory[ei_pc] = 0xfb;
    rr_md_z80_reset_evidence(); rr_md_z80_step(&z);
    demand(z.pc == ei_pc + 1 && z.iff1 && z.int_pending && z.cyc == 104, "EI must defer IRQ");
    z.halted = 1; rr_md_z80_step(&z);
    demand(z.pc == 0x38 && z.sp == 0xf00e && z.cyc == 121 && !z.halted && !z.int_pending &&
           memory[0xf00e] == (uint8_t)(ei_pc + 1) && memory[0xf00f] == (uint8_t)((ei_pc + 1) >> 8), "HALT/IM1 frame and cycles");
    demand(!rr_md_z80_fallback_opcodes(), "IRQ/HALT must stay native");
    z.int_pending = 0; z.halted = 1; z.r = 0xff; uint16_t previous_pc = z.pc; unsigned long cycles = z.cyc;
    rr_md_z80_step(&z);
    demand(z.r == 0x80 && z.pc == previous_pc && z.cyc == cycles + 4, "HALT M1 refresh without advancing PC");
    printf("{\"instruction_comparisons\":%u,\"guard_and_irq_checks\":12,\"authored_phase_cases\":%u,\"suspended_fetch_comparisons\":%u,\"timing_misses\":%llu}\n", comparisons,phase_checks,resume_checks,rr_md_z80_timing_misses());
    return 0;
}
