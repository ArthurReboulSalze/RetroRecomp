/* Authored writable-code fixtures. No original cartridge bytes or assets. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "gb_ram_helpers.h"

static unsigned checks;

static void copy_differential_checks(void) {
    static const uint8_t signatures[3][17] = {
        {0x12,0x1C,0x2A},
        {0xF3,0xF0,0x41,0xCB,0x4F,0x20,0xFA,0x2A,0x12,0xFB,0x13,0x0B,0x79,0xB0,0x20,0xF0,0xC9},
        {0x57,0xF3,0xF0,0x41,0xCB,0x4F,0x20,0xFA,0x72,0xFB,0x23,0x0B,0x79,0xB0,0x20,0xF1,0xC9}
    };
    const unsigned entries[3][9] = {{0},{0,3,8,9,10,11,12,13},{0,1,4,8,9,10,11,12,13}};
    const unsigned counts[] = {1,8,9};
    const uint16_t bases[] = {0xCFFF,0xDB81,0xFF80};
    const uint16_t targets[] = {0x8000,0xC000,0xDFFF,0xFE00,0xFF04,0xFF46};
    const unsigned phases[] = {0,3,77,251};
    for (unsigned kind=0;kind<3;++kind)
    for (unsigned e=0;e<counts[kind];++e)
    for (unsigned b=0;b<3;++b)
    for (unsigned t=0;t<6;++t)
    for (unsigned f=0;f<16;++f)
    for (unsigned p=0;p<4;++p) {
        GBContext* ctxs[2];
        for (unsigned c=0;c<2;++c) {
            GBContext* ctx=ctxs[c]=gb_context_create(NULL); assert(ctx);
            for (unsigned i=0;i<(kind ? 17u : 3u);++i) gb_write8(ctx,bases[b]+i,signatures[kind][i]);
            ctx->pc=bases[b]+entries[kind][e];ctx->sp=0xC800;
            ctx->de=ctx->hl=targets[t];ctx->bc=(f & 1) ? 0 : 0x100;ctx->a=0x91;
            ctx->ime=ctx->ime_pending=ctx->halted=ctx->stopped=0;
            ctx->f_z=(f>>3)&1;ctx->f_n=(f>>2)&1;ctx->f_h=(f>>1)&1;ctx->f_c=f&1;
            gb_tick(ctx,phases[p]);
        }
        GBDifferentialOptions options={0};options.max_steps=1;options.compare_memory=true;options.fail_on_fallback=true;
        GBDifferentialResult result;
        assert(gb_run_differential(ctxs[0],ctxs[1],&options,&result));
        assert(result.steps_completed==1 && ctxs[0]->total_interpreter_cycles==0);
        gb_context_destroy(ctxs[0]);gb_context_destroy(ctxs[1]);++checks;
    }
    for (unsigned i=0;i<17;++i) {
        GBContext* ctx=gb_context_create(NULL);assert(ctx);
        for (unsigned j=0;j<17;++j) gb_write8(ctx,0xDE00+j,signatures[1][j] ^ (i==j ? 1 : 0));
        ctx->pc=0xDE00;ctx->halt_bug=0;ctx->dma.active=0;
        assert(!rr_gb_try_copy_helper(ctx,0xDE00));
        gb_context_destroy(ctx);++checks;
    }
}

static void dma_page_checks(void) {
    const uint8_t code[]={0xF0,0x80,0x1F,0x1F,0x3E,0xC1,0x30,0x02,0x3E,0xD2,0xE0,0x46,0x3E,0x28,0x3D,0x20,0xFD,0xC9};
    for (unsigned entry=2;entry<=3;++entry)
    for (unsigned a=0;a<256;++a)
    for (unsigned carry=0;carry<2;++carry) {
        GBContext* ctxs[2];
        for (unsigned c=0;c<2;++c) {
            GBContext* ctx=ctxs[c]=gb_context_create(NULL);assert(ctx);
            for (unsigned i=0;i<sizeof(code);++i) gb_write8(ctx,0xFFE0+i,code[i]);
            ctx->pc=0xFFE0+entry;ctx->a=(uint8_t)a;ctx->f_c=carry;
            ctx->f_z=ctx->f_n=ctx->f_h=1;ctx->ime=ctx->ime_pending=0;
        }
        GBDifferentialOptions options={0};options.max_steps=1;options.compare_memory=true;options.fail_on_fallback=true;
        GBDifferentialResult result;assert(gb_run_differential(ctxs[0],ctxs[1],&options,&result));
        assert(result.steps_completed==1 && ctxs[0]->total_interpreter_cycles==0);
        gb_context_destroy(ctxs[0]);gb_context_destroy(ctxs[1]);++checks;
    }
    for (unsigned i=0;i<sizeof(code);++i) {
        GBContext* ctx=gb_context_create(NULL);assert(ctx);
        for (unsigned j=0;j<sizeof(code);++j) gb_write8(ctx,0xFFE0+j,code[j] ^ (i==j ? 1 : 0));
        assert(rr_gb_dma_page_signature(ctx,0xFFE0)==(i==5 || i==9));
        gb_context_destroy(ctx);++checks;
    }
}
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
    dma_sequence_checks(); copy_differential_checks(); dma_page_checks();
    printf("{\"checks\":%u,\"cpu_memory_timing_match\":true,\"live_guards\":true}\n", checks);
    return 0;
}
