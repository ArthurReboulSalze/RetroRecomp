/* Included in the generated glue: uses the same SMS bus, VDP and audio as
 * the original runner. Control flow uses only the real guest PC and stack. */
#ifdef SMSRECOMP_BANKED_AOT
#include "game_banked.h"
static uint64_t banked_native_steps, banked_halt_steps, banked_fallback_steps;
static uint64_t banked_guarded_steps;
static uint64_t banked_prefix_fragments;
static uint8_t banked_seen[3][256];

static void smsrecomp_banked_fallback(uint16_t addr) {
    uint8_t bytes[4];
    for (unsigned i = 0; i < 4; ++i) bytes[i] = sms_read8((uint16_t)(addr + i));
    smsrecomp_observe_code(bytes);
    if (!g_hz_init) {
        z80_init(&g_hz);
        g_hz.read_byte = hyb_read; g_hz.write_byte = hyb_write;
        g_hz.port_in = hyb_in; g_hz.port_out = hyb_out; g_hz_init = true;
    }
    state_to_hz(); g_hz.pc = addr; g_hz.cyc = 0;
    banked_last_interpreted = 1;
    uint64_t base = g_z80.cyc;
    smsrecomp_interp_depth++; g_hybrid_calls++; banked_fallback_steps++;
    z80_step(&g_hz);
    state_from_hz(); g_z80.pc = g_hz.pc; g_z80.cyc = base + g_hz.cyc;
    g_hybrid_cyc += g_hz.cyc;
    smsrecomp_interp_depth--;
}

static void smsrecomp_banked_run(void) {
    /* Same documented reset AF/SP as the reference CPU. Other registers stay
     * at the runtime's deterministic reset values. */
    g_z80.a = g_z80.f = 0xFF; g_z80.sp = 0xFFFF;
    banked_native_steps = banked_halt_steps = banked_fallback_steps = 0;
    banked_guarded_steps = banked_prefix_fragments = 0;
    memset(banked_seen, 0, sizeof(banked_seen));
    fprintf(stderr, "[backend] banked-aot-v3: static ROM, native prefixes and byte-guarded RAM\n");
    int prefix_pending = 0, pending_irq = 0;
    for (;;) {
        /* Match the shared reference runner's sampling contract: /INT is
         * latched at the start of the step and accepted at its completion.
         * EI suppresses acceptance through its own completion. HALT keeps PC
         * at the following instruction and performs refresh cycles. */
        if (!prefix_pending) pending_irq = vdp_irq_asserted();
        banked_last_interpreted = 0;
        SMS_PC(g_z80.pc);
        for (int slot = 0; slot < 3; ++slot) banked_seen[slot][(uint8_t)g_bank[slot]] = 1;
        if (g_z80.halted) {
            g_z80.r = (uint8_t)((g_z80.r & 0x80) | ((g_z80.r + 1) & 0x7F));
            g_z80.cyc += 4; banked_halt_steps++;
        } else {
            int step = game_banked_step((uint8_t)g_bank[0], (uint8_t)g_bank[1], (uint8_t)g_bank[2]);
            if (step >= 3) {
                banked_prefix_fragments++; if (step == 4) banked_guarded_steps++;
                /* A redundant prefix never completes EI's delay and never
                 * accepts an interrupt. Keep hardware time moving even in an
                 * endless prefix stream; no host recursion is involved. */
                prefix_pending = 1;
                advance_vdp(g_z80.cyc); g_sync_deadline = g_next_line_cyc;
                continue;
            }
            if (step) { banked_native_steps++; if (step == 2) banked_guarded_steps++; }
            else { sms_enter(g_z80.pc); sms_dispatch_miss(g_z80.pc); }
        }
        prefix_pending = 0; g_frame_ic++;
        if (g_z80.ei_block) g_z80.ei_block = 0;
        else if (pending_irq && g_z80.iff1) {
            g_irq_taken++;
            if (g_z80.p) g_z80.f &= (uint8_t)~Z80_FLAG_P;
            g_z80.p = g_z80.q = 0;
            g_z80.iff1 = g_z80.iff2 = false; g_z80.halted = false;
            g_z80.r = (uint8_t)((g_z80.r & 0x80) | ((g_z80.r + 1) & 0x7F));
            g_z80.cyc += g_z80.im == 2 ? 19 : 13;
            g_z80.sp = (uint16_t)(g_z80.sp - 2); sms_write16(g_z80.sp, g_z80.pc);
            g_z80.pc = g_z80.im == 2 ? sms_read16((uint16_t)((g_z80.i << 8) | 0xFF)) : 0x0038;
            g_z80.wz = g_z80.pc;
        }
        advance_vdp(g_z80.cyc);
        g_sync_deadline = g_next_line_cyc;
    }
}

static void smsrecomp_banked_stats(void) {
    unsigned counts[3] = {0};
    for (int s = 0; s < 3; ++s) for (int b = 0; b < 256; ++b) counts[s] += banked_seen[s][b];
    fprintf(stderr, "[banked] native_steps=%llu halt_steps=%llu fallback_steps=%llu banks_seen=%u/%u/%u\n",
        (unsigned long long)banked_native_steps, (unsigned long long)banked_halt_steps,
        (unsigned long long)banked_fallback_steps, counts[0], counts[1], counts[2]);
    fprintf(stderr, "[banked-guards] native_steps=%llu\n", (unsigned long long)banked_guarded_steps);
    fprintf(stderr, "[banked-prefixes] native_fragments=%llu\n", (unsigned long long)banked_prefix_fragments);
}
#endif

/* A final CPU record complements the existing frame/VRAM/RAM dumps. It is an
 * execution observation, never a user save state or a mechanism to restore PC. */
static void smsrecomp_cpu_record(void) {
    fprintf(stderr, "[cpu] {\"pc\":%u,\"sp\":%u,\"af\":%u,\"bc\":%u,\"de\":%u,\"hl\":%u,"
        "\"af2\":%u,\"bc2\":%u,\"de2\":%u,\"hl2\":%u,\"ix\":%u,\"iy\":%u,\"wz\":%u,"
        "\"i\":%u,\"r\":%u,\"iff1\":%u,\"iff2\":%u,\"im\":%u,\"halted\":%u,\"q\":%u,\"p\":%u,\"cycles\":%llu}\n",
        g_z80.pc, g_z80.sp, z80_af(&g_z80), z80_bc(&g_z80), z80_de(&g_z80), z80_hl(&g_z80),
        (g_z80.a_<<8)|g_z80.f_, (g_z80.b_<<8)|g_z80.c_, (g_z80.d_<<8)|g_z80.e_, (g_z80.h_<<8)|g_z80.l_,
        g_z80.ix, g_z80.iy, g_z80.wz, g_z80.i, g_z80.r, g_z80.iff1, g_z80.iff2, g_z80.im,
        g_z80.halted, g_z80.q, g_z80.p, (unsigned long long)g_z80.cyc);
}
