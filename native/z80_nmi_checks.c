/* The Z80 chain's NMI acceptance (banked_accept_nmi, retrorecomp/z80_chain.py) against the reference CPU, state by state.
 * MIT, Retro-Recomp. Built by tools/z80_nmi_selftest.py for a check, never into a game.
 *
 * Both sides start from the same register file and the same memory. The native side is the chain's function, pasted from
 * z80_chain._NMI_ACCEPT (z80_nmi_accept.inc); the reference side is the corrected interpreter of the game folder
 * (cpu.prepare_reference, with `nmi=True`): a pending NMI, then its interrupt acceptance. What must agree: every register,
 * both interrupt flip-flops, HALT, the cycle count, the return address pushed and the memory around it. EI's pending delay
 * (`ei_block`, `iff_delay`) is not compared after the NMI: IFF1 is clear then, so nothing is left for it to hold back.
 *
 * `--expect-difference` runs the same cases against the interpreter as the pinned engine has it (`nmi=False`), which lets EI's
 * delay hold an NMI back and keeps the Q and P latches: the checks must then FAIL, which shows they can see a difference. */
#include <stdio.h>
#include <string.h>
#include "sms_runtime.h"
#include "runtime_reference.c"

Z80State g_z80;
static z80 g_hz;
static uint8_t memory[65536];

uint8_t sms_read8(uint16_t a) { return memory[a]; }
void sms_write8(uint16_t a, uint8_t v) { memory[a] = v; }
uint8_t sms_io_in(uint8_t port) { (void)port; return 0xFF; }
void sms_io_out(uint8_t port, uint8_t value) { (void)port; (void)value; }
static uint8_t read_byte(void *u, uint16_t a) { (void)u; return memory[a]; }
static void write_byte(void *u, uint16_t a, uint8_t v) { (void)u; memory[a] = v; }
static uint8_t port_in(z80 *z, uint8_t p) { (void)z; (void)p; return 0xFF; }
static void port_out(z80 *z, uint8_t p, uint8_t v) { (void)z; (void)p; (void)v; }

#include "banked_reference_state.inc"
#include "z80_nmi_accept.inc"

static void fill_memory(void) { for (unsigned i = 0; i < sizeof memory; ++i) memory[i] = (uint8_t)(i * 31 + 7); }

static int same_state(const Z80State *a, const Z80State *b) {
    return a->pc == b->pc && a->sp == b->sp && a->a == b->a && a->f == b->f && a->b == b->b && a->c == b->c &&
        a->d == b->d && a->e == b->e && a->h == b->h && a->l == b->l && a->a_ == b->a_ && a->f_ == b->f_ &&
        a->b_ == b->b_ && a->c_ == b->c_ && a->d_ == b->d_ && a->e_ == b->e_ && a->h_ == b->h_ && a->l_ == b->l_ &&
        a->ix == b->ix && a->iy == b->iy && a->i == b->i && a->r == b->r && a->iff1 == b->iff1 && a->iff2 == b->iff2 &&
        a->im == b->im && a->halted == b->halted && a->cyc == b->cyc && a->wz == b->wz && a->q == b->q && a->p == b->p;
}

int main(int argc, char **argv) {
    const int expect_difference = argc > 1 && !strcmp(argv[1], "--expect-difference");
    static uint8_t after_native[65536];
    const uint16_t pcs[] = { 0x0000, 0x0066, 0x1234, 0xC000, 0xFFFF };
    const uint16_t sps[] = { 0x0000, 0x0001, 0x0002, 0x8000, 0xDFF0, 0xFFFF };
    const uint8_t rs[] = { 0x00, 0x55, 0x7F, 0x80, 0xFF };
    const uint8_t fs[] = { 0x00, 0xA5, 0xFF };
    unsigned cases = 0, failed = 0;
    for (unsigned pi = 0; pi < sizeof pcs / sizeof *pcs; ++pi)
    for (unsigned si = 0; si < sizeof sps / sizeof *sps; ++si)
    for (unsigned ri = 0; ri < sizeof rs / sizeof *rs; ++ri)
    for (unsigned fi = 0; fi < sizeof fs / sizeof *fs; ++fi)
    for (unsigned flags = 0; flags < 64; ++flags) {
        Z80State s;
        memset(&s, 0, sizeof s);
        s.pc = pcs[pi]; s.sp = sps[si]; s.r = rs[ri]; s.f = fs[fi];
        s.iff1 = flags & 1; s.iff2 = (flags >> 1) & 1; s.halted = (flags >> 2) & 1; s.ei_block = (flags >> 3) & 1;
        s.p = (flags >> 4) & 1; s.q = (flags >> 5) & 1 ? 0x28 : 0;
        s.a = 0xA5; s.b = 2; s.c = 0x13; s.d = 0xC5; s.e = 0x10; s.h = 0xC2; s.l = 0x10; s.im = (uint8_t)(flags % 3);
        s.a_ = 0x56; s.f_ = 0x12; s.ix = 0xC400; s.iy = 0xC600; s.wz = 0x2834; s.i = 0x17; s.cyc = 1000;
        /* the native side */
        fill_memory();
        g_z80 = s;
        banked_accept_nmi();
        const Z80State native = g_z80;
        memcpy(after_native, memory, sizeof memory);
        /* the reference side */
        fill_memory();
        memset(&g_hz, 0, sizeof g_hz);
        g_hz.read_byte = read_byte; g_hz.write_byte = write_byte; g_hz.port_in = port_in; g_hz.port_out = port_out;
        g_z80 = s;
        state_to_hz();
        g_hz.pc = s.pc; g_hz.cyc = 0;
        g_hz.nmi_pending = 1;
        process_interrupts(&g_hz);
        state_from_hz();
        g_z80.pc = g_hz.pc; g_z80.cyc = s.cyc + g_hz.cyc;
        ++cases;
        if (!same_state(&native, &g_z80) || memcmp(after_native, memory, sizeof memory)) ++failed;
    }
    printf("CASES=%u FAILED=%u\n", cases, failed);
    if (expect_difference) return failed ? 0 : 1;
    return failed ? 1 : 0;
}
