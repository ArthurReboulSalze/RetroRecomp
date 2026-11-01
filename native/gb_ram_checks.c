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
    assert(rr_gb_try_ram_dispatch(ctx, addr));
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

/* Every opcode of rr_gb_try_ram_instruction against the pinned interpreter. */
static uint32_t instruction_seed = 0x2545F491u;
static uint32_t instruction_random(void) {
    instruction_seed ^= instruction_seed << 13; instruction_seed ^= instruction_seed >> 17;
    instruction_seed ^= instruction_seed << 5;
    return instruction_seed;
}

static void instruction_prepare(GBContext* ctx, uint16_t base, unsigned length, const uint8_t* bytes,
                                const uint16_t* registers, unsigned flags, unsigned phase,
                                unsigned ime) {
    for (unsigned i = 0; i < length; ++i) gb_write8(ctx, (uint16_t)(base + i), bytes[i]);
    ctx->pc = base;
    ctx->af = (uint16_t)(registers[0] & 0xFF00u); ctx->bc = registers[1]; ctx->de = registers[2];
    ctx->hl = registers[3]; ctx->sp = registers[4];
    ctx->f_z = (flags >> 3) & 1; ctx->f_n = (flags >> 2) & 1;
    ctx->f_h = (flags >> 1) & 1; ctx->f_c = flags & 1;
    ctx->ime = ime & 1; ctx->ime_pending = (ime >> 1) & 1;
    ctx->halted = ctx->stopped = 0;
    gb_tick(ctx, phase);
}

static void instruction_differential_checks(void) {
    static const uint16_t pointers[] = {0x8000, 0x9FFF, 0xC000, 0xC123, 0xDFFF, 0xFE00, 0xFF04,
                                        0xFF46, 0xFF80, 0xFFFE, 0xFFFF};
    static const uint16_t stacks[] = {0xC800, 0xDFFE, 0xC002, 0xFF90, 0xFFFE, 0x8002};
    static const unsigned phases[] = {0, 3, 77, 251};
    static const uint16_t bases[] = {0xC030, 0xFDFD, 0xFF80, 0xFFFC};
    unsigned opcodes = 0, cb_opcodes = 0;
    /* The CB prefix is one opcode of the executor and 256 instructions: each second byte is checked on its own. */
    for (unsigned entry = 0; entry < 256 + 256; ++entry) {
        const unsigned op = entry < 256 ? entry : 0xCB;
        const unsigned length = rr_gb_ram_length((uint8_t)op);
        if (!length) continue;
        if (entry < 256) ++opcodes;
        else ++cb_opcodes;
        if (entry < 256 && op == 0xCB) continue;   /* covered by the second pass */
        const unsigned rounds = entry < 256 ? 24 : 8;
        for (unsigned b = 0; b < sizeof(bases) / sizeof(*bases); ++b)
        for (unsigned round = 0; round < rounds; ++round) {
            uint8_t bytes[3] = {(uint8_t)op, (uint8_t)instruction_random(), (uint8_t)instruction_random()};
            if (entry >= 256) bytes[1] = (uint8_t)(entry - 256);
            if (length == 3 && (round & 1)) {
                const uint16_t value = pointers[instruction_random() % (sizeof(pointers) / sizeof(*pointers))];
                bytes[1] = (uint8_t)value; bytes[2] = (uint8_t)(value >> 8);
            }
            uint16_t registers[5];
            registers[0] = (uint16_t)instruction_random();
            for (unsigned r = 1; r < 4; ++r)
                registers[r] = (round + r) % 3 ? (uint16_t)instruction_random()
                    : pointers[instruction_random() % (sizeof(pointers) / sizeof(*pointers))];
            registers[4] = stacks[instruction_random() % (sizeof(stacks) / sizeof(*stacks))];
            const unsigned flags = instruction_random() & 15u, ime = instruction_random() & 3u;
            const unsigned phase = phases[instruction_random() % (sizeof(phases) / sizeof(*phases))];
            GBContext* native = gb_context_create(NULL);
            GBContext* reference = gb_context_create(NULL);
            assert(native && reference);
            instruction_prepare(native, bases[b], length, bytes, registers, flags, phase, ime);
            instruction_prepare(reference, bases[b], length, bytes, registers, flags, phase, ime);
            GBDifferentialOptions options = {0};
            options.max_steps = 1; options.compare_memory = true; options.fail_on_fallback = true;
            GBDifferentialResult result;
            if (!gb_run_differential(native, reference, &options, &result)) {
                fprintf(stderr, "opcode %02X base %04X round %u: %s\n", op, bases[b], round, result.message);
                assert(0);
            }
            assert(result.steps_completed == 1 && native->total_interpreter_cycles == 0);
            gb_context_destroy(native); gb_context_destroy(reference); ++checks;
        }
    }
    assert(opcodes == 178 && cb_opcodes == 256);   /* 177 plain opcodes and the CB prefix with its 256 second bytes */
}

/* Every (HL) form of the CB prefix (rotates, shifts, SWAP, BIT, RES, SET: 32 opcodes) at every pointer of a fixed list,
 * which includes the whole map around the echo of WRAM (0xE000-0xFDFF), OAM, the unusable area and the registers:
 * deterministic, so no pointer or form depends on the random draw of the differential check above. */
static void cb_memory_sweep_checks(void) {
    static const uint16_t pointers[] = {0x8000, 0x9FFF, 0xA000, 0xC000, 0xC123, 0xDFFF, 0xE000, 0xE123, 0xFDFF, 0xFE00,
                                        0xFE9F, 0xFEA0, 0xFF00, 0xFF04, 0xFF0F, 0xFF40, 0xFF46, 0xFF80, 0xFFFE, 0xFFFF};
    static const uint16_t bases[] = {0xC030, 0xFF80};
    unsigned forms = 0;
    for (unsigned cb = 0; cb < 256; ++cb) {
        if ((cb & 7u) != 6u) continue;
        ++forms;
        for (unsigned p = 0; p < sizeof(pointers) / sizeof(*pointers); ++p)
        for (unsigned b = 0; b < sizeof(bases) / sizeof(*bases); ++b)
        for (unsigned flags = 0; flags < 16; flags += 15) {
            const uint8_t bytes[2] = {0xCB, (uint8_t)cb};
            const uint16_t registers[5] = {(uint16_t)(instruction_random() << 8), 0x1234, 0x5678, pointers[p], 0xC800};
            GBContext* native = gb_context_create(NULL);
            GBContext* reference = gb_context_create(NULL);
            assert(native && reference);
            instruction_prepare(native, bases[b], 2, bytes, registers, flags, p & 3u, 0);
            instruction_prepare(reference, bases[b], 2, bytes, registers, flags, p & 3u, 0);
            GBDifferentialOptions options = {0};
            options.max_steps = 1; options.compare_memory = true; options.fail_on_fallback = true;
            GBDifferentialResult result;
            if (!gb_run_differential(native, reference, &options, &result)) {
                fprintf(stderr, "CB %02X (HL)=%04X base %04X: %s\n", cb, pointers[p], bases[b], result.message);
                assert(0);
            }
            assert(result.steps_completed == 1 && native->total_interpreter_cycles == 0);
            gb_context_destroy(native); gb_context_destroy(reference); ++checks;
        }
    }
    assert(forms == 32);
}

static GBContext* instruction_declined_setup(uint16_t address, uint8_t opcode) {
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    gb_write8(ctx, address, opcode);
    ctx->pc = address; ctx->hl = 0xC400; ctx->sp = 0xC800;
    return ctx;
}

static void instruction_guard_checks(void) {
    /* Opcodes that stay with the upstream stub or the reference are declined untouched. */
    static const uint8_t declined[] = {0x00, 0x10, 0x18, 0x20, 0x40, 0x76, 0xC0, 0xC2, 0xC3, 0xC7,
                                       0xC9, 0xCD, 0xD3, 0xD9, 0xE9, 0xEF, 0xFF};
    for (unsigned i = 0; i < sizeof(declined); ++i) {
        GBContext* ctx = instruction_declined_setup(0xC200, declined[i]);
        assert(!rr_gb_try_ram_instruction(ctx, 0xC200));
        assert(ctx->pc == 0xC200 && ctx->cycles == 0 && ctx->sp == 0xC800);
        gb_context_destroy(ctx); checks += 3;
    }
    /* An instruction must lie wholly in WRAM or HRAM. */
    static const struct { uint16_t address; uint8_t opcode; } straddling[] = {
        {0xFDFE, 0x21}, {0xFDFF, 0x36}, {0xFDFF, 0xC6}, {0xFFFE, 0x36}, {0xFFFD, 0x01},
        {0x7FFF, 0x3C}, {0x9000, 0x41}, {0xFE00, 0x41}, {0xFF00, 0xC1}, {0xFFFF, 0x41},
        {0xFDFF, 0xCB}, {0xFFFE, 0xCB}, {0xFFFF, 0xCB}};
    for (unsigned i = 0; i < sizeof(straddling) / sizeof(*straddling); ++i) {
        GBContext* ctx = instruction_declined_setup(straddling[i].address, straddling[i].opcode);
        assert(!rr_gb_try_ram_instruction(ctx, straddling[i].address));
        assert(ctx->pc == straddling[i].address && ctx->cycles == 0);
        gb_context_destroy(ctx); checks += 2;
    }
    GBContext* ctx = instruction_declined_setup(0xC200, 0x41);
    ctx->halt_bug = 1;
    assert(!rr_gb_try_ram_instruction(ctx, 0xC200));
    ctx->halt_bug = 0; ctx->dma.active = 1;
    assert(!rr_gb_try_ram_instruction(ctx, 0xC200));   /* WRAM is owned by OAM DMA. */
    gb_write8(ctx, 0xFF90, 0x41);
    assert(rr_gb_try_ram_instruction(ctx, 0xFF90));    /* HRAM stays on the CPU bus. */
    assert(!rr_gb_try_ram_instruction(NULL, 0xC200));
    gb_context_destroy(ctx); checks += 4;
    /* Self-modification: the operand is read live at every execution. */
    ctx = instruction_declined_setup(0xC200, 0x21);
    gb_write16(ctx, 0xC201, 0x1234);
    assert(rr_gb_try_ram_instruction(ctx, 0xC200) && ctx->hl == 0x1234 && ctx->pc == 0xC203);
    gb_write16(ctx, 0xC201, 0xBEEF); ctx->pc = 0xC200;
    assert(rr_gb_try_ram_instruction(ctx, 0xC200) && ctx->hl == 0xBEEF && ctx->cycles == 24);
    gb_context_destroy(ctx); checks += 2;
}

/* The instructions the stub and the single-instruction executor run are counted, each in its own pair. */
static void counter_checks(void) {
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    /* LD HL,nn (executor, 12) ; LD A,n (upstream stub, 8) ; ADD A,B (executor, 4) ; JP nn (stub, 16 plus its jump). */
    static const uint8_t code[] = {0x21, 0x34, 0x12, 0x3E, 0x05, 0x80, 0xC3, 0x00, 0x20};
    for (unsigned i = 0; i < sizeof(code); ++i) gb_write8(ctx, 0xC300 + i, code[i]);
    assert(ctx->rr_ram_stub_instructions == 0 && ctx->rr_ram_single_step_instructions == 0);
    const uint16_t starts[] = {0xC300, 0xC303, 0xC305};
    const uint64_t cycles[] = {12, 8, 4};
    const unsigned stub[] = {0, 1, 0};
    uint64_t single_cycles = 0, stub_cycles = 0, single = 0, stubs = 0;
    for (unsigned i = 0; i < 3; ++i) {
        const uint64_t before = ctx->total_cycles;
        ctx->pc = starts[i];
        assert(rr_gb_try_ram_dispatch(ctx, starts[i]));
        assert(ctx->total_cycles - before == cycles[i]);
        if (stub[i]) { ++stubs; stub_cycles += cycles[i]; } else { ++single; single_cycles += cycles[i]; }
        assert(ctx->rr_ram_single_step_instructions == single && ctx->rr_ram_single_step_cycles == single_cycles);
        assert(ctx->rr_ram_stub_instructions == stubs && ctx->rr_ram_stub_cycles == stub_cycles);
    }
    assert(ctx->hl == 0x1234 && ctx->a == 5);
    /* The CB prefix is counted by the executor with the interpreter's cycle split: 8 on a register, 12 for BIT n,(HL),
     * 16 for the other (HL) forms. */
    static const struct { uint8_t second; uint64_t cycles; } cb_cases[] = {{0x7F, 8}, {0x46, 12}, {0xC6, 16}, {0x06, 16}};
    ctx->hl = 0xC500;
    for (unsigned i = 0; i < sizeof(cb_cases) / sizeof(*cb_cases); ++i) {
        const uint16_t at = (uint16_t)(0xC310 + 2 * i);
        gb_write8(ctx, at, 0xCB); gb_write8(ctx, (uint16_t)(at + 1), cb_cases[i].second);
        const uint64_t before = ctx->total_cycles;
        ctx->pc = at;
        assert(rr_gb_try_ram_dispatch(ctx, at));
        assert(ctx->pc == at + 2 && ctx->total_cycles - before == cb_cases[i].cycles);
        ++single; single_cycles += cb_cases[i].cycles;
        assert(ctx->rr_ram_single_step_instructions == single && ctx->rr_ram_single_step_cycles == single_cycles);
        assert(ctx->rr_ram_stub_instructions == stubs && ctx->rr_ram_stub_cycles == stub_cycles);
    }
    /* A guarded multi-instruction helper counts in neither pair; a declined opcode changes nothing. */
    GBContext* helper = setup(0xD09B, 0, 0xC100, 0, 0);
    assert(rr_gb_try_ram_dispatch(helper, 0xD09B));
    assert(helper->rr_ram_stub_instructions == 0 && helper->rr_ram_single_step_instructions == 0);
    gb_write8(ctx, 0xC400, 0xC7);
    ctx->pc = 0xC400;
    assert(!rr_gb_try_ram_dispatch(ctx, 0xC400));
    assert(ctx->rr_ram_single_step_instructions == single && ctx->rr_ram_stub_instructions == stubs);
    gb_context_destroy(helper); gb_context_destroy(ctx); checks += 12 + 4 * 4;
}

/* The upstream stub for code run from 0xFF00-0xFF7F is counted in its own pair, apart from the other two. The
 * serial data register (0xFF01) reads back what was written, which gives an authored opcode in that range. */
static void highmem_counter_checks(void) {
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    assert(ctx->rr_highmem_stub_instructions == 0 && ctx->rr_highmem_stub_cycles == 0);
    uint64_t instructions = 0, cycles = 0;
    static const uint8_t opcodes[] = {0x00, 0xF3, 0xFB, 0x00};   /* NOP, DI, EI, NOP: 4 guest cycles each */
    for (unsigned i = 0; i < sizeof(opcodes); ++i) {
        gb_write8(ctx, 0xFF01, opcodes[i]);
        assert(gb_read8(ctx, 0xFF01) == opcodes[i]);
        ctx->pc = 0xFF01;
        const uint64_t before = ctx->total_cycles;
        assert(rr_gb_try_highmem_dispatch(ctx, 0xFF01));
        assert(ctx->pc == 0xFF02 && ctx->total_cycles - before == 4);
        ++instructions; cycles += 4;
        assert(ctx->rr_highmem_stub_instructions == instructions && ctx->rr_highmem_stub_cycles == cycles);
    }
    /* Declined: an opcode the stub does not run, an address outside 0xFF00-0xFF7F, a missing context. */
    gb_write8(ctx, 0xFF01, 0x41);
    ctx->pc = 0xFF01;
    assert(!rr_gb_try_highmem_dispatch(ctx, 0xFF01));
    gb_write8(ctx, 0xC300, 0x00);
    ctx->pc = 0xC300;
    assert(!rr_gb_try_highmem_dispatch(ctx, 0xC300));
    assert(!rr_gb_try_highmem_dispatch(ctx, 0xFF80));
    assert(!rr_gb_try_highmem_dispatch(NULL, 0xFF01));
    assert(ctx->rr_highmem_stub_instructions == instructions && ctx->rr_highmem_stub_cycles == cycles);
    /* The other pairs are not touched by it, and it is not touched by theirs. */
    assert(ctx->rr_ram_stub_instructions == 0 && ctx->rr_ram_single_step_instructions == 0);
    ctx->pc = 0xC300;
    assert(rr_gb_try_ram_dispatch(ctx, 0xC300));
    assert(ctx->rr_ram_stub_instructions == 1 && ctx->rr_highmem_stub_instructions == instructions);
    gb_context_destroy(ctx); checks += 22;
}

/* The same stubs called by the pinned interpreter inside a session are part of the session: its instruction and
 * cycle counts hold them, and the counters of the generated dispatch (which would count them twice) stay at zero. */
static void interpreter_session_checks(void) {
    static const struct { uint16_t address; uint8_t opcode; uint8_t operand; uint32_t cycles; const char* name; } cases[] = {
        {0xC300, 0x3E, 0x05, 8, "RAM stub: LD A,n"},
        {0xC300, 0x00, 0x00, 4, "RAM stub: NOP"},
        {0xFF01, 0x00, 0x00, 4, "high-memory stub: NOP"},
        {0xFF01, 0xF3, 0x00, 4, "high-memory stub: DI"},
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(*cases); ++i) {
        GBContext* ctx = gb_context_create(NULL); assert(ctx);
        gb_write8(ctx, cases[i].address, cases[i].opcode);
        if (cases[i].address < 0xFF00) gb_write8(ctx, (uint16_t)(cases[i].address + 1), cases[i].operand);
        ctx->single_step_mode = 1;   /* one instruction, then the session ends */
        const uint64_t before = ctx->total_cycles;
        gb_interpret(ctx, cases[i].address);
        if (ctx->total_interpreter_entries != 1 || ctx->total_interpreter_instructions != 1 ||
            ctx->total_interpreter_cycles != cases[i].cycles || ctx->total_cycles - before != cases[i].cycles) {
            fprintf(stderr, "interpreter session %s: entries=%llu instructions=%llu cycles=%llu\n", cases[i].name,
                    (unsigned long long)ctx->total_interpreter_entries,
                    (unsigned long long)ctx->total_interpreter_instructions,
                    (unsigned long long)ctx->total_interpreter_cycles);
            assert(0);
        }
        assert(ctx->rr_ram_stub_instructions == 0 && ctx->rr_ram_single_step_instructions == 0 &&
               ctx->rr_highmem_stub_instructions == 0);
        gb_context_destroy(ctx); checks += 4;
    }
}

int main(void) {
    counter_checks(); highmem_counter_checks(); interpreter_session_checks();
    guard_checks(); differential_checks(); dma_guard_checks(); dma_differential_checks();
    dma_sequence_checks(); copy_differential_checks(); dma_page_checks();
    instruction_guard_checks(); instruction_differential_checks(); cb_memory_sweep_checks();
    printf("{\"checks\":%u,\"cpu_memory_timing_match\":true,\"live_guards\":true}\n", checks);
    return 0;
}
