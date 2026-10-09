/* Authored writable-code fixtures. No original cartridge bytes or assets. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "gb_ram_helpers.h"

static unsigned checks;
void gb_dispatch(GBContext* ctx, uint16_t addr) {
    ctx->pc = addr;
    assert(rr_gb_try_store_helper(ctx, addr) || gbrt_try_execute_ram_stub(ctx, addr));
}

static GBContext* setup(uint16_t base, unsigned entry, uint16_t target,
                        unsigned flags, unsigned phase) {
    static const uint8_t code[] = {0x12, 0x00, 0x00, 0x13, 0xC9};
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    for (unsigned i = 0; i < sizeof(code); ++i) gb_write8(ctx, base + i, code[i]);
    ctx->pc = base + entry; ctx->de = target; ctx->a = 0xA7;
    ctx->sp = 0xC800;
    ctx->f_z = (flags >> 3) & 1; ctx->f_n = (flags >> 2) & 1;
    ctx->f_h = (flags >> 1) & 1; ctx->f_c = flags & 1;
    ctx->ime = 0; ctx->ime_pending = 0; ctx->halted = ctx->stopped = 0;
    gb_tick(ctx, phase);
    return ctx;
}

static void differential_checks(void) {
    const uint16_t bases[] = {0xC030, 0xCFFD, 0xD09B, 0xFF80, 0xFFFA};
    const uint16_t targets[] = {0x8000, 0xC000, 0xC0FF, 0xDFFF, 0xFE00,
                                0xFF04, 0xFF46, 0xFF80, 0xFFFF};
    const unsigned phases[] = {0, 3, 77, 251};
    for (unsigned b = 0; b < sizeof(bases)/sizeof(*bases); ++b)
    for (unsigned t = 0; t < sizeof(targets)/sizeof(*targets); ++t)
    for (unsigned e = 0; e < 2; ++e)
    for (unsigned f = 0; f < 16; ++f)
    for (unsigned p = 0; p < sizeof(phases)/sizeof(*phases); ++p) {
        const unsigned entry = e ? 3 : 0;
        GBContext* native = setup(bases[b], entry, targets[t], f, phases[p]);
        GBContext* reference = setup(bases[b], entry, targets[t], f, phases[p]);
        GBDifferentialOptions options = {0};
        options.max_steps = 1; options.compare_memory = true; options.fail_on_fallback = true;
        GBDifferentialResult result;
        assert(gb_run_differential(native, reference, &options, &result));
        assert(result.steps_completed == 1 && native->total_interpreter_cycles == 0);
        const unsigned cycles = native->cycles;
        assert(cycles == phases[p] + 8);
        gb_context_destroy(native); gb_context_destroy(reference); ++checks;
    }
}

static void guard_checks(void) {
    for (unsigned i = 0; i < 5; ++i) {
        GBContext* ctx = setup(0xD09B, 0, 0xC100, 0, 0);
        gb_write8(ctx, 0xD09B + i, gb_read8(ctx, 0xD09B + i) ^ 1);
        assert(!rr_gb_try_store_helper(ctx, 0xD09B));
        assert(!rr_gb_try_store_helper(ctx, 0xD09E));
        assert(ctx->cycles == 0 && ctx->pc == 0xD09B && ctx->de == 0xC100);
        gb_context_destroy(ctx); checks += 2;
    }
    GBContext* ctx = setup(0xD09B, 0, 0xD09B, 0, 0);
    assert(rr_gb_try_store_helper(ctx, 0xD09B));
    assert(gb_read8(ctx, 0xD09B) == 0xA7);
    assert(!rr_gb_try_store_helper(ctx, 0xD09E)); /* Self-modification invalidates it. */
    gb_context_destroy(ctx); checks += 2;
    ctx = setup(0xD09B, 0, 0xC100, 0, 0); ctx->halt_bug = 1;
    assert(!rr_gb_try_store_helper(ctx, 0xD09B));
    ctx->halt_bug = 0; ctx->dma.active = 1;
    assert(!rr_gb_try_store_helper(ctx, 0xD09B));
    gb_context_destroy(ctx); checks += 2;
    ctx = setup(0xDFFE, 0, 0xC100, 0, 0);
    assert(!rr_gb_try_store_helper(ctx, 0xDFFE));
    gb_context_destroy(ctx); ++checks;
    ctx = setup(0xFFFB, 0, 0xC100, 0, 0);
    assert(!rr_gb_try_store_helper(ctx, 0xFFFB));
    gb_context_destroy(ctx); ++checks;
    assert(!rr_gb_try_store_helper(NULL, 0xC000)); ++checks;
}

static GBContext* setup_dma(uint16_t base, unsigned entry, unsigned page,
                            unsigned ime, unsigned pending, unsigned phase) {
    const uint8_t code[] = {0xF3, 0x3E, (uint8_t)page, 0xE0, 0x46, 0x3E,
                            0x28, 0x3D, 0x20, 0xFD, 0xFB, 0xC9};
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    for (unsigned i = 0; i < sizeof(code); ++i) gb_write8(ctx, base + i, code[i]);
    ctx->pc = base + entry; ctx->sp = 0xC800;
    gb_tick(ctx, phase);
    ctx->ime = ime; ctx->ime_pending = pending;
    return ctx;
}

static void dma_differential_checks(void) {
    const uint16_t bases[] = {0xFF80, 0xFFA3, 0xFFF3};
    const unsigned pages[] = {0, 0x80, 0xC0, 0xC1, 0xC2, 0xDF, 0xFF};
    const unsigned phases[] = {0, 3, 77, 251};
    for (unsigned b = 0; b < sizeof(bases)/sizeof(*bases); ++b)
    for (unsigned p = 0; p < sizeof(pages)/sizeof(*pages); ++p)
    for (unsigned e = 0; e < 2; ++e)
    for (unsigned ime = 0; ime < 2; ++ime)
    for (unsigned pending = 0; pending < 2; ++pending)
    for (unsigned phase = 0; phase < sizeof(phases)/sizeof(*phases); ++phase) {
        const unsigned entry = e ? 10 : 0;
        GBContext* native = setup_dma(bases[b], entry, pages[p], ime, pending, phases[phase]);
        GBContext* reference = setup_dma(bases[b], entry, pages[p], ime, pending, phases[phase]);
        GBDifferentialOptions options = {0};
        options.max_steps = 1; options.compare_memory = true; options.fail_on_fallback = true;
        GBDifferentialResult result;
        assert(gb_run_differential(native, reference, &options, &result));
        assert(result.steps_completed == 1 && native->total_interpreter_cycles == 0);
        assert(native->cycles == phases[phase] + 4);
        gb_context_destroy(native); gb_context_destroy(reference); ++checks;
    }
}

static void dma_guard_checks(void) {
    for (unsigned i = 0; i < 12; ++i) {
        if (i == 2) continue; /* A changed source page is legitimate live data. */
        GBContext* ctx = setup_dma(0xFF80, 0, 0xC1, 1, 1, 0);
        gb_write8(ctx, 0xFF80 + i, gb_read8(ctx, 0xFF80 + i) ^ 1);
        assert(!rr_gb_try_interrupt_dma_helper(ctx, 0xFF80));
        assert(!rr_gb_try_interrupt_dma_helper(ctx, 0xFF8A));
        assert(ctx->cycles == 0 && ctx->ime == 1 && ctx->ime_pending == 1);
        gb_context_destroy(ctx); checks += 2;
    }
    GBContext* ctx = setup_dma(0xFF80, 0, 0xC1, 1, 1, 0);
    ctx->halt_bug = 1;
    assert(!rr_gb_try_interrupt_dma_helper(ctx, 0xFF80));
    ctx->halt_bug = 0; ctx->dma.active = 1;
    assert(rr_gb_try_interrupt_dma_helper(ctx, 0xFF80)); /* HRAM stays on the CPU bus. */
    gb_write8(ctx, 0xFF84, 0x47);
    assert(!rr_gb_try_interrupt_dma_helper(ctx, 0xFF8A));
    gb_context_destroy(ctx); checks += 3;
    ctx = setup_dma(0xC000, 0, 0xC1, 1, 1, 0);
    assert(!rr_gb_try_interrupt_dma_helper(ctx, 0xC000));
    gb_context_destroy(ctx); ++checks;
    ctx = setup_dma(0xFFF4, 0, 0xC1, 1, 1, 0);
    assert(!rr_gb_try_interrupt_dma_helper(ctx, 0xFFF4));
    gb_context_destroy(ctx); ++checks;
    assert(!rr_gb_try_interrupt_dma_helper(NULL, 0xFF80)); ++checks;
}

static void dma_sequence_checks(void) {
    const unsigned pages[] = {0x80, 0xC0, 0xC1, 0xC2, 0xDF};
    for (unsigned p = 0; p < sizeof(pages)/sizeof(*pages); ++p) {
        GBContext* native = setup_dma(0xFF80, 0, pages[p], 1, 1, 0);
        GBContext* reference = setup_dma(0xFF80, 0, pages[p], 1, 1, 0);
        gb_write16(native, 0xC800, 0xC100);
        gb_write16(reference, 0xC800, 0xC100);
        GBDifferentialOptions options = {0};
        options.max_steps = 86; options.compare_memory = true; options.fail_on_fallback = true;
        GBDifferentialResult result;
        assert(gb_run_differential(native, reference, &options, &result));
        assert(result.steps_completed == 86 && native->total_interpreter_cycles == 0);
        assert(native->pc == 0xC100 && native->sp == 0xC802);
        assert(native->cycles == 688 && native->ime == 1 && !native->dma.active);
        gb_context_destroy(native); gb_context_destroy(reference); ++checks;
    }
}

int main(void) {
    guard_checks(); differential_checks(); dma_guard_checks(); dma_differential_checks();
    dma_sequence_checks();
    printf("{\"checks\":%u,\"cpu_memory_timing_match\":true,\"live_guards\":true}\n", checks);
    return 0;
}
