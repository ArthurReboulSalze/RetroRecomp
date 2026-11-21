/* A machine's instruction costs on the banked Z80 chain (retrorecomp/z80_chain.py, Z80Costs): the emitter's bodies against the
 * reference CPU, encoding by encoding. MIT, Retro-Recomp. Built by tools/z80_costs_selftest.py for a check, never into a game.
 *
 * The bodies come from native/z80_costs_emit.c (z80_costs_bodies.inc), the reference is the interpreter of the counted fallback
 * as cpu.prepare_reference copies it for the same machine (runtime_reference.c). Every encoding runs from the same register
 * file and memory on both sides, in four states (the flags all clear or all set, B and BC at 1 or at 2), so that each
 * conditional branch is seen taken and not taken and each block instruction ends and goes round again. What must agree: the
 * T-states the instruction took and the PC it left (the PC of a HALT is left out: the two sides keep it differently and the
 * cycles say enough). `--expect-difference` checks the bodies against a reference copied without the machine's costs: some
 * encodings must then disagree, which shows the check sees the costs. */
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
void sms_io_out(uint8_t port, uint8_t value) { (void)port; (void)value; }
static uint8_t read_byte(void *u, uint16_t a) { (void)u; return memory[a]; }
static void write_byte(void *u, uint16_t a, uint8_t v) { (void)u; memory[a] = v; }
static uint8_t port_in(z80 *z, uint8_t p) { (void)z; (void)p; return 0x5A; }
static void port_out(z80 *z, uint8_t p, uint8_t v) { (void)z; (void)p; (void)v; }

#include "banked_reference_state.inc"
#include "z80_costs_bodies.inc"

enum { START = 0x8000, BASE = 1000 };

static void setup(const uint8_t bytes[4], int state) {
    for (unsigned i = 0; i < sizeof memory; ++i) memory[i] = (uint8_t)(i * 31 + 7);
    memcpy(memory + START, bytes, 4);
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = 0x5A; g_z80.f = (state & 1) ? 0xFF : 0x00;
    g_z80.b = (state & 2) ? 1 : 2; g_z80.c = (state & 2) ? 0 : 1;      /* BC 0100h or 0201h: an LDI then ends or goes on */
    g_z80.d = 0x40; g_z80.e = 0x10; g_z80.h = 0x60; g_z80.l = 0x20;
    g_z80.ix = 0x7000; g_z80.iy = 0x7100; g_z80.sp = 0xC000; g_z80.i = 0x3F; g_z80.im = 1;
    g_z80.pc = START; g_z80.cyc = BASE;
}

int main(int argc, char **argv) {
    int expect_difference = argc > 1 && strcmp(argv[1], "--expect-difference") == 0;
    z80_init(&g_hz);
    g_hz.read_byte = read_byte; g_hz.write_byte = write_byte; g_hz.port_in = port_in; g_hz.port_out = port_out;
    unsigned compared = 0, differ = 0, shown = 0;
    for (unsigned c = 0; c < sizeof cases / sizeof cases[0]; ++c) {
        for (int state = 0; state < 4; ++state) {
            setup(cases[c].bytes, state);
            bodies[cases[c].body]();
            if (cases[c].then) bodies[cases[c].then]();
            uint64_t native_cycles = g_z80.cyc - BASE;
            uint16_t native_pc = g_z80.pc;
            setup(cases[c].bytes, state);
            state_to_hz(); g_hz.pc = START; g_hz.cyc = 0; g_hz.halted = 0; g_hz.int_pending = 0; g_hz.nmi_pending = 0;
            z80_step(&g_hz);
            uint64_t reference_cycles = g_hz.cyc;
            uint16_t reference_pc = g_hz.pc;
            const uint8_t *b = cases[c].bytes;
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
    printf("compared=%u differ=%u\n", compared, differ);
    return expect_difference ? (differ ? 0 : 1) : (differ ? 1 : 0);
}
