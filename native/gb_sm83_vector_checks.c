/* Independent SM83 vectors (SingleStepTests/sm83, MIT, generated from a reference model, not recorded from hardware) against the
 * pinned runtime's interpreter, and against our one-instruction executor of code in WRAM and HRAM.
 *
 * The vectors are read from a text file made by tools/gameboy_sm83_vector_selftest.py, one vector per line:
 *   family index  pc sp a b c d e f h l ime ei ie  NI (addr value)*NI  a b c d e f h l pc sp ime ei  NF (addr value)*NF  mcycles
 * Only vectors that touch plain memory are given (ROM read-only, VRAM, cartridge RAM, WRAM, OAM and HRAM; no echo, no I/O, no
 * writes to ROM): the vector model is a flat 64 KiB RAM, the runtime's bus is not. No ROM bytes of any game are involved.
 *
 * Output: lines "MISMATCH ..." (at most MAX_REPORT per family and path) and one JSON line with the totals. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "gb_ram_helpers.h"

#define MAX_RAM 32
#define MAX_REPORT 3
#define FAMILIES 512

typedef struct {
    unsigned family, index;
    uint16_t pc, sp;
    uint8_t a, b, c, d, e, f, h, l, ime, ei, ie;
    unsigned ni;
    uint16_t iaddr[MAX_RAM];
    uint8_t ival[MAX_RAM];
    uint8_t fa, fb, fc, fd, fe, ff, fh, fl;
    uint16_t fpc, fsp;
    uint8_t fime, fei;
    unsigned nf;
    uint16_t faddr[MAX_RAM];
    uint8_t fval[MAX_RAM];
    unsigned mcycles;
} Vector;

typedef struct { unsigned long run, matched, unhandled; unsigned reported[FAMILIES]; unsigned long failed[FAMILIES]; } Tally;

static int read_vector(FILE* in, Vector* v) {
    unsigned x[14];
    if (fscanf(in, "%u %u", &v->family, &v->index) != 2) return 0;
    for (unsigned i = 0; i < 14; ++i) if (fscanf(in, "%u", &x[i]) != 1) return 0;
    v->pc = x[0]; v->sp = x[1]; v->a = x[2]; v->b = x[3]; v->c = x[4]; v->d = x[5]; v->e = x[6]; v->f = x[7];
    v->h = x[8]; v->l = x[9]; v->ime = x[10]; v->ei = x[11]; v->ie = x[12]; v->ni = x[13];
    assert(v->ni <= MAX_RAM);
    for (unsigned i = 0; i < v->ni; ++i) { unsigned p, q; if (fscanf(in, "%u %u", &p, &q) != 2) return 0; v->iaddr[i] = p; v->ival[i] = q; }
    for (unsigned i = 0; i < 13; ++i) if (fscanf(in, "%u", &x[i]) != 1) return 0;
    v->fa = x[0]; v->fb = x[1]; v->fc = x[2]; v->fd = x[3]; v->fe = x[4]; v->ff = x[5]; v->fh = x[6]; v->fl = x[7];
    v->fpc = x[8]; v->fsp = x[9]; v->fime = x[10]; v->fei = x[11]; v->nf = x[12];
    assert(v->nf <= MAX_RAM);
    for (unsigned i = 0; i < v->nf; ++i) { unsigned p, q; if (fscanf(in, "%u %u", &p, &q) != 2) return 0; v->faddr[i] = p; v->fval[i] = q; }
    unsigned cycles;
    if (fscanf(in, "%u", &cycles) != 1) return 0;
    v->mcycles = cycles;
    return 1;
}

static GBContext* make_context(void) {
    static uint8_t rom[0x8000];
    memset(rom, 0, sizeof rom);
    rom[0x147] = 0x08;               /* ROM + RAM, no mapper: nothing in the cartridge changes what the bus does */
    rom[0x149] = 0x02;               /* 8 KiB of cartridge RAM */
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    assert(gb_context_load_rom(ctx, rom, sizeof rom));
    gb_write8(ctx, 0xFF40, 0x00);    /* screen off: VRAM and OAM answer at every moment */
    ctx->ram_enabled = 1;
    return ctx;
}

static void load(GBContext* ctx, const Vector* v) {
    for (unsigned i = 0; i < v->ni; ++i) {
        const uint16_t address = v->iaddr[i];
        if (address < 0x8000) ctx->rom[address] = v->ival[i];     /* ROM space: read-only for the program, set by the harness */
        else gb_write8(ctx, address, v->ival[i]);
    }
    ctx->a = v->a; ctx->b = v->b; ctx->c = v->c; ctx->d = v->d; ctx->e = v->e; ctx->h = v->h; ctx->l = v->l;
    ctx->f_z = (v->f >> 7) & 1; ctx->f_n = (v->f >> 6) & 1; ctx->f_h = (v->f >> 5) & 1; ctx->f_c = (v->f >> 4) & 1;
    ctx->sp = v->sp; ctx->pc = v->pc;
    ctx->ime = v->ime; ctx->ime_pending = v->ei;
    ctx->halted = ctx->stopped = ctx->stop_mode_active = ctx->halt_bug = 0;
    gb_write8(ctx, 0xFF0F, 0x00);
    gb_write8(ctx, 0xFFFF, v->ie);
}

/* Returns 0 when the state is the vector's final state, else a short description in `why`. */
static int compare(GBContext* ctx, const Vector* v, uint32_t cycles, char* why, size_t size) {
    const uint8_t flags = (uint8_t)((ctx->f_z << 7) | (ctx->f_n << 6) | (ctx->f_h << 5) | (ctx->f_c << 4));
    if (ctx->a != v->fa || ctx->b != v->fb || ctx->c != v->fc || ctx->d != v->fd || ctx->e != v->fe || ctx->h != v->fh ||
        ctx->l != v->fl) {
        snprintf(why, size, "registers A%02X/%02X B%02X/%02X C%02X/%02X D%02X/%02X E%02X/%02X H%02X/%02X L%02X/%02X (got/want)",
                 ctx->a, v->fa, ctx->b, v->fb, ctx->c, v->fc, ctx->d, v->fd, ctx->e, v->fe, ctx->h, v->fh, ctx->l, v->fl);
        return 1;
    }
    if (flags != (v->ff & 0xF0)) { snprintf(why, size, "flags %02X/%02X", flags, v->ff & 0xF0); return 1; }
    if (ctx->pc != v->fpc) { snprintf(why, size, "pc %04X/%04X", ctx->pc, v->fpc); return 1; }
    if (ctx->sp != v->fsp) { snprintf(why, size, "sp %04X/%04X", ctx->sp, v->fsp); return 1; }
    if (ctx->ime != v->fime) { snprintf(why, size, "ime %u/%u", ctx->ime, v->fime); return 1; }
    if ((ctx->ime_pending ? 1u : 0u) != (v->fei ? 1u : 0u)) { snprintf(why, size, "ei %u/%u", ctx->ime_pending, v->fei); return 1; }
    for (unsigned i = 0; i < v->nf; ++i) {
        const uint8_t value = v->faddr[i] < 0x8000 ? ctx->rom[v->faddr[i]] : gb_read8(ctx, v->faddr[i]);
        if (value != v->fval[i]) { snprintf(why, size, "memory %04X %02X/%02X", v->faddr[i], value, v->fval[i]); return 1; }
    }
    if (cycles != v->mcycles * 4u) { snprintf(why, size, "cycles %u/%u", cycles, v->mcycles * 4u); return 1; }
    return 0;
}

static void note(Tally* tally, const Vector* v, const char* path, const char* why) {
    tally->failed[v->family]++;
    if (tally->reported[v->family]++ < MAX_REPORT)
        printf("MISMATCH %s family=%u index=%u pc=%04X: %s\n", path, v->family, v->index, v->pc, why);
}

int main(int argc, char** argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s vectors.txt\n", argv[0]); return 2; }
    FILE* in = fopen(argv[1], "r"); assert(in);
    GBContext* interpreter = make_context();
    GBContext* executor = make_context();
    GBContext* dispatcher = make_context();
    static Tally a, b, c;
    static unsigned long unhandled_by_family[FAMILIES], interpreted_by_family[FAMILIES];
    Vector v;
    unsigned long plain_ram = 0;
    while (read_vector(in, &v)) {
        char why[160];
        load(interpreter, &v);
        const uint32_t start = interpreter->cycles;
        interpreter->single_step_mode = 1;
        gb_interpret(interpreter, v.pc);
        interpreter->single_step_mode = 0;
        a.run++;
        if (compare(interpreter, &v, interpreter->cycles - start, why, sizeof why)) note(&a, &v, "interpreter", why);
        else a.matched++;
        const int in_ram = (v.pc >= 0xC000 && v.pc < 0xE000) || (v.pc >= 0xFF80 && v.pc <= 0xFFFE);
        if (!in_ram) continue;
        plain_ram++;
        load(executor, &v);
        const uint32_t before = executor->cycles;
        if (!rr_gb_try_ram_instruction(executor, v.pc)) { b.unhandled++; unhandled_by_family[v.family]++; }
        else {
            b.run++;
            if (compare(executor, &v, executor->cycles - before, why, sizeof why)) note(&b, &v, "ram_executor", why);
            else b.matched++;
        }
        /* The dispatch the generated code calls for code in RAM: the store helper, the upstream stub, then our executor. What none of
         * them takes goes to an interpreter session (counted and reported as such). */
        load(dispatcher, &v);
        const uint32_t start_dispatch = dispatcher->cycles;
        if (!rr_gb_try_ram_dispatch(dispatcher, v.pc)) { c.unhandled++; interpreted_by_family[v.family]++; continue; }
        c.run++;
        if (compare(dispatcher, &v, dispatcher->cycles - start_dispatch, why, sizeof why)) note(&c, &v, "ram_dispatch", why);
        else c.matched++;
    }
    fclose(in);
    unsigned long bad_families_a = 0, bad_families_b = 0, bad_families_c = 0;
    for (unsigned i = 0; i < FAMILIES; ++i) {
        bad_families_a += a.failed[i] != 0; bad_families_b += b.failed[i] != 0; bad_families_c += c.failed[i] != 0;
    }
    printf("{\"interpreter\":{\"run\":%lu,\"matched\":%lu,\"families_with_mismatch\":%lu},"
           "\"ram_executor\":{\"vectors_with_code_in_ram\":%lu,\"run\":%lu,\"matched\":%lu,\"not_handled\":%lu,\"families_with_mismatch\":%lu},"
           "\"ram_dispatch\":{\"run\":%lu,\"matched\":%lu,\"left_to_the_interpreter\":%lu,\"families_with_mismatch\":%lu},"
           "\"mismatching_families\":[", a.run, a.matched, bad_families_a, plain_ram, b.run, b.matched, b.unhandled, bad_families_b,
           c.run, c.matched, c.unhandled, bad_families_c);
    int first = 1;
    for (unsigned i = 0; i < FAMILIES; ++i)
        if (a.failed[i] || b.failed[i] || c.failed[i]) {
            printf("%s{\"family\":%u,\"interpreter\":%lu,\"ram_executor\":%lu,\"ram_dispatch\":%lu}", first ? "" : ",", i,
                   a.failed[i], b.failed[i], c.failed[i]);
            first = 0;
        }
    printf("],\"ram_dispatch_left_to_the_interpreter\":[");
    first = 1;
    for (unsigned i = 0; i < FAMILIES; ++i)
        if (interpreted_by_family[i]) { printf("%s{\"family\":%u,\"vectors\":%lu}", first ? "" : ",", i, interpreted_by_family[i]); first = 0; }
    printf("],\"ram_executor_not_handled\":[");
    first = 1;
    for (unsigned i = 0; i < FAMILIES; ++i)
        if (unhandled_by_family[i]) { printf("%s{\"family\":%u,\"vectors\":%lu}", first ? "" : ",", i, unhandled_by_family[i]); first = 0; }
    printf("]}\n");
    return 0;
}
