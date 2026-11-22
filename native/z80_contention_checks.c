/* Contention on the banked Z80 chain (retrorecomp/z80_chain.py, Z80Machine.contention): the emitter's bodies against the reference
 * CPU, encoding by encoding, under an authored rule. MIT, Retro-Recomp. Built by tools/z80_contention_selftest.py for a check,
 * never into a game.
 *
 * The bodies come from native/z80_costs_emit.c (z80_costs_bodies.inc) built with the generator patched for a machine with (or
 * without) contention; the reference is the interpreter of the counted fallback as cpu.prepare_reference copies it for the same
 * machine; the evaluator is banked_timed.c (retrorecomp/z80_timed.py). The rule is authored for the check, not any real machine's:
 * memory at 4000h-7FFFh waits 6, 5, 4, 3, 2, 1, 0, 0 by the T-state within the first 128 of every 224, and an I/O cycle waits by
 * its port. Every encoding runs from the same register file and memory on both sides, in eight states (the code at 8000h or at
 * 6000h, inside the slow memory; the flags all clear or all set; BC at 0100h or 0201h) and at a T-state that differs by state.
 * What must agree: the T-states and the PC (the PC of a HALT is left out, as in the costs check). `--expect-difference` expects
 * some encodings to disagree (a positive control: bodies and reference built differently). `--dump` prints, per case, the bytes,
 * the state and the bodies' T-states, for the Python model's check in the tool. */
#include <stdio.h>
#include <string.h>
#include "sms_runtime.h"
#include "z80_ops.h"
#include "runtime_reference.c"

Z80State g_z80;
static z80 g_hz;
static uint8_t memory[65536];

uint8_t sms_read8(uint16_t a) { return memory[a]; }
void sms_write8(uint16_t a, uint8_t v) { memory[a] = v; }
uint8_t sms_io_in(uint8_t port) { (void)port; return 0x5A; }
static int odd_bank;     /* the authored rule's paging: an OUT to port 05h toggles whether C000h-FFFFh is slow too */
void sms_io_out(uint8_t port, uint8_t value) { (void)value; if (port == 0x05) odd_bank ^= 1; }
static uint8_t read_byte(void *u, uint16_t a) { (void)u; return memory[a]; }
static void write_byte(void *u, uint16_t a, uint8_t v) { (void)u; memory[a] = v; }
static uint8_t port_in(z80 *z, uint8_t p) { (void)z; (void)p; return 0x5A; }
static void port_out(z80 *z, uint8_t p, uint8_t v) { (void)z; (void)v; if (p == 0x05) odd_bank ^= 1; }

/* The authored rule (the machine's three functions). */
unsigned rr_contend_memory(uint64_t t, uint16_t a)
{
    static const unsigned pattern[8] = {6, 5, 4, 3, 2, 1, 0, 0};
    if ((a & 0xC000) != 0x4000 && !((a & 0xC000) == 0xC000 && odd_bank)) return 0;
    unsigned line = (unsigned)(t % 224);
    return line < 128 ? pattern[line & 7] : 0;
}
unsigned rr_contend_io(uint64_t t, uint16_t port)
{
    if (!(port & 1)) return 1 + (unsigned)(t & 3);
    return (port & 0xC000) == 0x4000 ? 2 : 0;
}
uint8_t rr_contend_peek(uint16_t a) { return memory[a]; }

#ifdef RR_CHECK_TIMED
#define RR_TIMED_API
#include "banked_timed.h"
#define RR_TIMED_START(s) ((RrTimedStart){ (s)->pc, (s)->sp, (uint16_t)((s)->b << 8 | (s)->c), (uint16_t)((s)->d << 8 | (s)->e), \
    (uint16_t)((s)->h << 8 | (s)->l), (s)->ix, (s)->iy, (uint16_t)((s)->i << 8 | 0xFF), (s)->a, (s)->i, (s)->r })
#endif
#include "banked_reference_state.inc"
#include "z80_costs_bodies.inc"

#ifndef RR_REFERENCE_TIMED
uint64_t rr_timed_epoch;    /* a reference copied without contention does not define it */
#endif

static void setup(const uint8_t bytes[4], int state, uint16_t *start, uint64_t *base) {
    for (unsigned i = 0; i < sizeof memory; ++i) memory[i] = (uint8_t)(i * 31 + 7);
    odd_bank = 0;
    *start = state == 8 ? 0xC100 : state == 9 ? 0x3403 : (state & 4) ? 0x6000 : 0x8000;
    *base = state >= 8 ? 2240 : 1000 + 37u * (unsigned)state;   /* the authored cases start at the first T-state of a line */
    memcpy(memory + *start, bytes, 4);
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = 0x5A; g_z80.f = (state & 1) ? 0xFF : 0x00;
    g_z80.b = (state & 2) ? 1 : 2; g_z80.c = (state & 2) ? 0 : 1;
    g_z80.d = 0x40; g_z80.e = 0x10; g_z80.h = 0x60; g_z80.l = 0x20;
    g_z80.ix = 0x7000; g_z80.iy = 0x7100; g_z80.sp = 0xC000; g_z80.i = 0x3F; g_z80.im = 1;
    g_z80.pc = *start; g_z80.cyc = *base;
}

int main(int argc, char **argv) {
    int expect_difference = argc > 1 && strcmp(argv[1], "--expect-difference") == 0;
    int dump = argc > 1 && strcmp(argv[1], "--dump") == 0;
    z80_init(&g_hz);
    g_hz.read_byte = read_byte; g_hz.write_byte = write_byte; g_hz.port_in = port_in; g_hz.port_out = port_out;
    unsigned compared = 0, differ = 0, shown = 0;
    for (unsigned c = 0; c < sizeof cases / sizeof cases[0]; ++c) {
        for (int state = 0; state < 8; ++state) {
            uint16_t start; uint64_t base;
            setup(cases[c].bytes, state, &start, &base);
            bodies[cases[c].body]();
            if (cases[c].then) bodies[cases[c].then]();
            uint64_t native_cycles = g_z80.cyc - base;
            uint16_t native_pc = g_z80.pc;
            const uint8_t *b = cases[c].bytes;
            if (dump) {
                printf("%02X%02X%02X%02X %d %llu\n", b[0], b[1], b[2], b[3], state, (unsigned long long)native_cycles);
                continue;
            }
            setup(cases[c].bytes, state, &start, &base);
            state_to_hz(); g_hz.pc = start; g_hz.cyc = 0; g_hz.halted = 0; g_hz.int_pending = 0; g_hz.nmi_pending = 0;
            g_hz.int_data = 0xFF;
            rr_timed_epoch = base;
            z80_step(&g_hz);
            uint64_t reference_cycles = g_hz.cyc;
            uint16_t reference_pc = g_hz.pc;
            int halt = (b[0] == 0x76) || ((b[0] == 0xDD || b[0] == 0xFD) && b[1] == 0x76);
            ++compared;
            if (native_cycles != reference_cycles || (!halt && native_pc != reference_pc)) {
                ++differ;
                if (!expect_difference && shown++ < 12)
                    printf("differ: %02X %02X %02X %02X state %d: native %llu T, PC %04X; reference %llu T, PC %04X\n",
                           b[0], b[1], b[2], b[3], state, (unsigned long long)native_cycles, native_pc,
                           (unsigned long long)reference_cycles, reference_pc);
            }
        }
    }
    if (dump) return 0;
    /* Two authored cases where the walk must read the state BEFORE the instruction (the bodies do; the reference must too):
     * state 8, OUT (05h),A at C100h, which pages the slow memory in at C000h: its own M1s at C100h/C101h are not slowed;
     * state 9, LD (3405h),A at 3403h, whose write changes its own operand's high byte to 5Ah: the write is at 3405h, not 5A05h. */
    static const uint8_t out_bytes[4] = {0xD3, 0x05, 0x34, 0x12}, store_bytes[4] = {0x32, 0x05, 0x34, 0x12};
    const struct { const uint8_t *bytes; int state; const char *what; } authored[2] = {
        {out_bytes, 8, "OUT paging the slow memory in under its own M1"}, {store_bytes, 9, "a store rewriting its own operand"}};
    for (int k = 0; k < 2; ++k) {
        unsigned c = 0;
        while (c < sizeof cases / sizeof cases[0] && memcmp(cases[c].bytes, authored[k].bytes, 4)) ++c;
        if (c == sizeof cases / sizeof cases[0]) { printf("authored case not interned: %s\n", authored[k].what); return 1; }
        uint16_t start; uint64_t base;
        setup(cases[c].bytes, authored[k].state, &start, &base);
        bodies[cases[c].body]();
        uint64_t native_cycles = g_z80.cyc - base;
        setup(cases[c].bytes, authored[k].state, &start, &base);
        state_to_hz(); g_hz.pc = start; g_hz.cyc = 0; g_hz.halted = 0; g_hz.int_pending = 0; g_hz.nmi_pending = 0;
        g_hz.int_data = 0xFF;
        rr_timed_epoch = base;
        z80_step(&g_hz);
        ++compared;
        if (native_cycles != (uint64_t)g_hz.cyc) {
            ++differ;
            if (!expect_difference)
                printf("differ: %s: native %llu T, reference %llu T\n", authored[k].what, (unsigned long long)native_cycles,
                       (unsigned long long)g_hz.cyc);
        } else
            printf("authored: %s: %llu T on both sides\n", authored[k].what, (unsigned long long)native_cycles);
    }
    printf("compared=%u differ=%u\n", compared, differ);
    return expect_difference ? (differ ? 0 : 1) : (differ ? 1 : 0);
}
