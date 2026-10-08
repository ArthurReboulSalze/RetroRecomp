/* Differential instruction checks plus independent opcode/IRQ/guard fixtures. */
#include "md_z80_native.h"
#include "fixture_data.h"
#include <stdlib.h>
#include <string.h>

static unsigned char memory[65536], saved[65536], expected[65536];
static int force_reference, deny_peek;
static uint64_t bus_hash;
static unsigned bus_reads, bus_writes;
static void demand(int ok, const char *message) {
    if (!ok) { fprintf(stderr, "Z80 fixture: %s\n", message); exit(2); }
}
static uint8_t read_byte(void *context, uint16_t pc) { (void)context; return memory[pc]; }
static void write_byte(void *context, uint16_t pc, uint8_t value) {
    (void)context; memory[pc] = value;
    bus_hash = (bus_hash ^ ((uint32_t)pc << 8) ^ value) * 1099511628211ull; ++bus_writes;
}
static uint8_t port_in(z80 *z, uint8_t port) {
    ++bus_reads; return (uint8_t)(z->b ^ port ^ 0xa5);
}
static void port_out(z80 *z, uint8_t port, uint8_t value) {
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
static void clear_bus(void) { bus_hash = 14695981039346656037ull; bus_reads = bus_writes = 0; }
int main(void) {
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
            demand(rr_md_z80_native_opcodes() == 1 && rr_md_z80_fallback_opcodes() == 0, "authored operation escaped to reference");
            memcpy(saved, memory, sizeof memory); memcpy(memory, expected, sizeof memory);
            clear_bus(); z80_step(&reference);
            if (memcmp(&native, &reference, sizeof native) || memcmp(saved, memory, sizeof memory) ||
                hash != bus_hash || reads != bus_reads || writes != bus_writes) {
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
    printf("{\"instruction_comparisons\":%u,\"guard_and_irq_checks\":12}\n", comparisons);
    return 0;
}
