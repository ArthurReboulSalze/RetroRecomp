/* 16-bit ports on the banked Z80 chain (retrorecomp/z80_chain.py, Z80Machine.port_bits): the emitter's bodies against the reference
 * CPU, I/O encoding by I/O encoding. MIT, Retro-Recomp. Built by tools/z80_ports_selftest.py for a check, never into a game.
 *
 * The bodies come from native/z80_ports_emit.c (z80_ports_bodies.inc), the reference is the interpreter of the counted fallback as
 * cpu.prepare_reference(port16=True) copies it. Every encoding runs from the same registers and memory on both sides, in five states
 * (A, B, C and HL varied, B at 1, 2, 80h, FFh so that the block forms end or go on), and every port access is recorded: its direction,
 * its 16-bit address and the value. What must agree: the accesses in order, then PC, B, C and the cycles.
 * Built with RR_REFERENCE_PORT8 the reference is the interpreter left at 8 bits (prepare_reference without port16): its addresses
 * have no high byte, so the check must fail (`--expect-difference`, a positive control). */
#include <stdio.h>
#include <string.h>
#include "sms_runtime.h"
#include "z80_ops.h"
#include "runtime_reference.c"

uint8_t sms_io_in16(uint16_t port);
void sms_io_out16(uint16_t port, uint8_t value);

Z80State g_z80;
static z80 g_hz;
static uint8_t memory[65536];

typedef struct { int out; uint16_t port; uint8_t value; } Access;
static Access seen[64];
static int seen_count;
static void record(int out, uint16_t port, uint8_t value)
{
    if (seen_count < 64) { seen[seen_count].out = out; seen[seen_count].port = port; seen[seen_count].value = value; }
    ++seen_count;
}
static uint8_t port_value(uint16_t port) { return (uint8_t)(port * 7 + (port >> 8) * 3 + 1); }

uint8_t sms_read8(uint16_t a) { return memory[a]; }
void sms_write8(uint16_t a, uint8_t v) { memory[a] = v; }
uint8_t sms_io_in(uint8_t port) { (void)port; return 0; }      /* the 8-bit pair: never called by 16-bit bodies */
void sms_io_out(uint8_t port, uint8_t value) { (void)port; (void)value; }
uint8_t sms_io_in16(uint16_t port) { uint8_t v = port_value(port); record(0, port, v); return v; }
void sms_io_out16(uint16_t port, uint8_t value) { record(1, port, value); }
static uint8_t read_byte(void *u, uint16_t a) { (void)u; return memory[a]; }
static void write_byte(void *u, uint16_t a, uint8_t v) { (void)u; memory[a] = v; }
#ifdef RR_REFERENCE_PORT8
static uint8_t port_in(z80 *z, uint8_t p) { (void)z; uint8_t v = port_value(p); record(0, p, v); return v; }
static void port_out(z80 *z, uint8_t p, uint8_t v) { (void)z; record(1, p, v); }
#else
static uint8_t port_in(z80 *z, uint16_t p) { (void)z; uint8_t v = port_value(p); record(0, p, v); return v; }
static void port_out(z80 *z, uint16_t p, uint8_t v) { (void)z; record(1, p, v); }
#endif

#include "banked_reference_state.inc"
#include "z80_ports_bodies.inc"

enum { START = 0x8000 };
static const uint8_t states[5][5] = {          /* A, B, C, H, L */
    {0x5A, 0x80, 0x34, 0x60, 0x10}, {0xFE, 0x01, 0xFE, 0x61, 0x00}, {0x7F, 0xFF, 0xFD, 0x62, 0xFF},
    {0x00, 0x02, 0x1F, 0x63, 0x80}, {0xBF, 0x7F, 0xFE, 0x64, 0x40},
};

static void setup(const uint8_t bytes[4], int state)
{
    for (unsigned i = 0; i < sizeof memory; ++i) memory[i] = (uint8_t)(i * 31 + 7);
    memcpy(memory + START, bytes, 4);
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = states[state][0]; g_z80.b = states[state][1]; g_z80.c = states[state][2];
    g_z80.h = states[state][3]; g_z80.l = states[state][4];
    g_z80.d = 0x40; g_z80.e = 0x10; g_z80.f = 0x55; g_z80.sp = 0xC000; g_z80.im = 1;
    g_z80.pc = START; g_z80.cyc = 1000;
    seen_count = 0;
}

int main(int argc, char **argv)
{
    int expect_difference = argc > 1 && strcmp(argv[1], "--expect-difference") == 0;
    z80_init(&g_hz);
    g_hz.read_byte = read_byte; g_hz.write_byte = write_byte; g_hz.port_in = port_in; g_hz.port_out = port_out;
    unsigned compared = 0, differ = 0, accesses = 0, shown = 0;
    for (unsigned c = 0; c < sizeof cases / sizeof cases[0]; ++c) {
        for (int state = 0; state < 5; ++state) {
            setup(cases[c].bytes, state);
            bodies[cases[c].body]();
            Access native[64]; int native_count = seen_count; memcpy(native, seen, sizeof seen);
            uint16_t native_pc = g_z80.pc; uint8_t native_b = g_z80.b, native_c = g_z80.c; uint64_t native_cyc = g_z80.cyc - 1000;
            setup(cases[c].bytes, state);
            state_to_hz(); g_hz.pc = START; g_hz.cyc = 0; g_hz.halted = 0; g_hz.int_pending = 0; g_hz.nmi_pending = 0;
            z80_step(&g_hz);
            ++compared;
            accesses += (unsigned)native_count;
            /* The address the Z80 itself puts on the bus (Zilog UM0080), independent of both sides: A and n for the immediate
             * forms, BC for the (C) forms and INI/IND/INIR/INDR, B - 1 and C for OUTI/OUTD/OTIR/OTDR. */
            const uint8_t *b = cases[c].bytes;
            uint8_t op = b[0] == 0xED ? b[1] : (b[0] == 0xDD || b[0] == 0xFD) ? b[1] : b[0];
            uint8_t n = b[0] == 0xED ? 0 : (b[0] == 0xDD || b[0] == 0xFD) ? b[2] : b[1];
            uint16_t expected = b[0] != 0xED ? (uint16_t)(states[state][0] << 8 | n)
                : (op & 0xE7) == 0xA3 ? (uint16_t)((uint8_t)(states[state][1] - 1) << 8 | states[state][2])
                : (uint16_t)(states[state][1] << 8 | states[state][2]);
            if (native_count < 1 || native[0].port != expected) {
                ++differ;
                if (!expect_difference && shown++ < 12)
                    printf("not the Z80's address: %02X %02X state %d: native %04X, the Z80 %04X\n", b[0], b[1], state,
                           native_count ? native[0].port : 0, expected);
                continue;
            }
            int same = native_count == seen_count && native_count > 0 && native_pc == g_hz.pc && native_b == g_hz.b &&
                       native_c == g_hz.c && native_cyc == g_hz.cyc;
            for (int i = 0; same && i < native_count && i < 64; ++i)
                same = native[i].out == seen[i].out && native[i].port == seen[i].port && native[i].value == seen[i].value;
            if (!same) {
                ++differ;
                if (!expect_difference && shown++ < 12)
                    printf("differ: %02X %02X state %d: native %s %04X=%02X (%d accesses); reference %s %04X=%02X (%d)\n",
                           cases[c].bytes[0], cases[c].bytes[1], state, native[0].out ? "out" : "in", native[0].port,
                           native[0].value, native_count, seen[0].out ? "out" : "in", seen[0].port, seen[0].value, seen_count);
            }
        }
    }
    printf("compared=%u accesses=%u differ=%u\n", compared, accesses, differ);
    return expect_difference ? (differ ? 0 : 1) : (differ ? 1 : 0);
}
