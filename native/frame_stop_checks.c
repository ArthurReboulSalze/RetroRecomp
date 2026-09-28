/* Authored opcodes straddle a frame boundary. No game, window or screenshot. */
#include "runtime_glue.c"
#include <stdio.h>

static unsigned callbacks;
static int stop_frame(const uint32_t *pixels, int w, int h) {
    (void)pixels; (void)w; (void)h; callbacks++; return 1;
}
static void setup(unsigned pc, int stop_kind) {
    glue_init(false, stop_kind == 1 ? 1 : 0);
    g_z80.pc = (uint16_t)pc; g_z80.sp = 0xDFF0;
    g_z80.a = 0x21; g_z80.b = 2; g_z80.c = 0xBE;
    g_z80.h = 0xC0; g_z80.l = 0x10; g_z80.r = 0xFD; g_z80.wz = 0x1234;
    g_z80.cyc = SMS_CYC_PER_FRAME - 1;
    g_next_line_cyc = SMS_CYC_PER_FRAME; g_sync_deadline = g_next_line_cyc;
    g_vdp.line = SMS_LINES_PER_FRAME - 1;
    for (unsigned i = 0; i < sizeof(g_ram); ++i) g_ram[i] = (uint8_t)(i * 13 + 7);
    callbacks = 0;
    if (stop_kind == 2) glue_set_frame_callback(stop_frame);
    g_running = true;
}
static void step(unsigned mode) {
    if (mode == 0) {
        if (game_banked_step(0, 1, 2) != 1) { fputs("Missing authored native opcode\n", stderr); exit(2); }
    } else if (mode == 1) {
        uint64_t base = g_z80.cyc;
        z80_init(&g_hz); g_hz.read_byte = hyb_read; g_hz.write_byte = hyb_write;
        g_hz.port_in = hyb_in; g_hz.port_out = hyb_out;
        state_to_hz(); g_hz.pc = g_z80.pc; g_hz.cyc = 0;
        z80_step(&g_hz); state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = base + g_hz.cyc;
    } else {
        smsrecomp_banked_fallback(g_z80.pc);
    }
}
static void cpu_words(const Z80State *s, uint64_t *v) {
    const uint64_t words[] = {s->pc, s->sp, s->a, s->f, s->b, s->c, s->d, s->e, s->h, s->l,
        s->a_, s->f_, s->b_, s->c_, s->d_, s->e_, s->h_, s->l_, s->ix, s->iy, s->wz,
        s->i, s->r, s->iff1, s->iff2, s->im, s->halted, s->q, s->p, s->ei_block, s->cyc};
    memcpy(v, words, sizeof words);
}
int main(void) {
    if (!glue_load_rom("authored")) return 2;
    unsigned failed = 0, checks = 0;
    for (unsigned cell = 0; cell < 12; ++cell) {
        unsigned pc = cell * 8;
        uint64_t expected[31]; uint8_t expected_ram[8192];
        setup(pc, 0); step(1); advance_vdp(g_z80.cyc); g_running = false;
        cpu_words(&g_z80, expected); memcpy(expected_ram, g_ram, sizeof expected_ram);
        /* Explicit block-I/O effects as well as the separate CPU oracle. */
        if (cell >= 4 && (g_z80.b != 1 || z80_hl(&g_z80) != (cell & 1 ? 0xC00F : 0xC011))) return 2;
        for (unsigned mode = 0; mode < 3; ++mode) for (int stop_kind = 1; stop_kind <= 2; ++stop_kind) {
            setup(pc, stop_kind);
            volatile int completed = 0;
            if (setjmp(g_quit_env) == 0) {
                step(mode); completed = 1;
                advance_vdp(g_z80.cyc);
                fputs("Expected frame stop was lost\n", stderr); return 2;
            }
            g_running = false;
            uint64_t actual[31]; cpu_words(&g_z80, actual); checks++;
            if (!completed || memcmp(actual, expected, sizeof actual) ||
                memcmp(g_ram, expected_ram, sizeof expected_ram) || g_frame != 1 ||
                callbacks != (unsigned)(stop_kind == 2) ||
                (mode == 2 && (smsrecomp_interp_depth || g_hybrid_calls != 1 ||
                    g_hybrid_cyc != g_z80.cyc - (SMS_CYC_PER_FRAME - 1)))) {
                printf("FAIL cell=%u mode=%u stop=%d completed=%d frame=%llu bc=%04X wz=%04X\n",
                    cell, mode, stop_kind, completed, (unsigned long long)g_frame, z80_bc(&g_z80), g_z80.wz);
                failed++;
            }
        }
    }
    /* Run/reset/run must clear a previously requested stop. */
    setup(0, 0); step(0); advance_vdp(g_z80.cyc); g_running = false;
    if (g_frame != 1) return 2;
    printf("CHECKS=%u FAILED=%u: frame limits and host stops complete I/O on native, reference and fallback CPUs; reset clears pending stops.\n", checks, failed);
    return failed ? 1 : 0;
}
