/* Checks of the Z80 chain's CPU state (native/z80_chain_state.inc) and of the quick-state file (native/state_file.h), on a toy
 * machine made here: the CPU, 256 bytes of RAM and a frame count, whose consistency check wants the CPU's cycle at least the
 * frame count. MIT, Retro-Recomp. Built by tools/z80_chain_state_selftest.py, never into a game. No ROM.
 *
 *   state_file_checks FOLDER     (an ASCII folder that exists; the checks write their files there)
 *
 * Prints one line per check and a last JSON line {"passed": N, "failed": M}. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#ifdef _WIN32
#include <direct.h>
#define make_folder(path) _mkdir(path)
#define remove_folder(path) _rmdir(path)
#else
#include <unistd.h>
#define make_folder(path) mkdir(path, 0700)
#define remove_folder(path) rmdir(path)
#endif
#include "sms_runtime.h"
#include "z80_chain_state.inc"
#include "state_file.h"

static int passed, failed;
static void expect(const char *name, int condition)
{
    printf("%s %s\n", condition ? "ok  " : "FAIL", name);
    if (condition) ++passed; else ++failed;
}

/* The toy machine, live and the check pass's candidates. */
static Z80State cpu, cpu_candidate;
static struct { uint8_t ram[256]; uint64_t frames; } board, board_candidate;
static int refuse_write;

static void toy_body(RetroStateIO *io)
{
    if (io->mode == RR_STATE_WRITE && refuse_write) { io->ok = false; return; }
    Z80State c = cpu;
    rr_z80_cpu_state(io, &c);
    if (io->mode == RR_STATE_CHECK) {
        board_candidate = board;
        rr_state_bytes(io, board_candidate.ram, sizeof board_candidate.ram);
        board_candidate.frames = rr_state_word(io, board.frames, 8, 1ULL << 40);
        cpu_candidate = c;
        return;
    }
    rr_state_bytes(io, board.ram, sizeof board.ram);
    uint64_t frames = rr_state_word(io, board.frames, 8, 1ULL << 40);
    if (io->mode == RR_STATE_APPLY && io->ok) { board.frames = frames; cpu = c; }
}

static bool toy_consistent(void) { return cpu_candidate.cyc >= board_candidate.frames; }

static const uint8_t binding_a[4] = { 1, 2, 3, 4 }, binding_b[4] = { 1, 2, 3, 5 };
static const char identity[65] = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

static RetroStateFile toy_file(const uint8_t *binding, uint32_t schema)
{
    RetroStateFile f = { { "RRTOYST\0", schema, 1, identity, toy_body }, binding, 4, toy_consistent, 4096 };
    return f;
}

static void set_machine(unsigned seed)
{
    memset(&cpu, 0, sizeof cpu);
    cpu.a = (uint8_t)(0x11 + seed); cpu.f = 0x22; cpu.b = 0x33; cpu.c = 0x44; cpu.d = 0x55; cpu.e = 0x66; cpu.h = 0x77; cpu.l = 0x88;
    cpu.a_ = 0x99; cpu.f_ = 0xAA; cpu.b_ = 0xBB; cpu.c_ = 0xCC; cpu.d_ = 0xDD; cpu.e_ = 0xEE; cpu.h_ = 0xF0; cpu.l_ = 0x0F;
    cpu.pc = 0x1234; cpu.sp = 0xFFF0; cpu.ix = 0x5678; cpu.iy = 0x9ABC; cpu.wz = 0xDEF0; cpu.i = 0x3F; cpu.r = 0x7E;
    cpu.iff1 = 1; cpu.iff2 = 1; cpu.im = 2; cpu.halted = 1; cpu.q = 0x28; cpu.p = 1; cpu.ei_block = 1;
    cpu.cyc = 123456789012ULL + seed;
    for (int i = 0; i < 256; ++i) board.ram[i] = (uint8_t)(i * 7 + seed);
    board.frames = 1000 + seed;
}

static int cpu_equal(const Z80State *x, const Z80State *y)
{
    return x->a == y->a && x->f == y->f && x->b == y->b && x->c == y->c && x->d == y->d && x->e == y->e && x->h == y->h
        && x->l == y->l && x->a_ == y->a_ && x->f_ == y->f_ && x->b_ == y->b_ && x->c_ == y->c_ && x->d_ == y->d_
        && x->e_ == y->e_ && x->h_ == y->h_ && x->l_ == y->l_ && x->pc == y->pc && x->sp == y->sp && x->ix == y->ix
        && x->iy == y->iy && x->wz == y->wz && x->i == y->i && x->r == y->r && x->iff1 == y->iff1 && x->iff2 == y->iff2
        && x->im == y->im && x->halted == y->halted && x->q == y->q && x->p == y->p && x->ei_block == y->ei_block
        && x->cyc == y->cyc;
}

/* The live machine kept aside, to see that a refused load left it as it was. */
static Z80State kept_cpu;
static uint8_t kept_board[sizeof board];
static void keep(void) { kept_cpu = cpu; memcpy(kept_board, &board, sizeof board); }
static int unchanged(void) { return cpu_equal(&cpu, &kept_cpu) && !memcmp(kept_board, &board, sizeof board); }

static char folder[1024];
static wchar_t *wide(const char *name)
{
    static wchar_t out[4][2048];
    static int turn;
    char path[2048];
    snprintf(path, sizeof path, "%s/%s", folder, name);
    wchar_t *w = out[turn++ & 3];
    rr_from_utf8(path, w, 2048);
    return w;
}

static long file_bytes(const char *name, uint8_t *into, size_t room)
{
    char path[2048];
    snprintf(path, sizeof path, "%s/%s", folder, name);
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    long n = (long)fread(into, 1, room, f);
    fclose(f);
    return n;
}

static void put_file(const char *name, const uint8_t *data, size_t size)
{
    char path[2048];
    snprintf(path, sizeof path, "%s/%s", folder, name);
    FILE *f = fopen(path, "wb");
    if (f) { fwrite(data, 1, size, f); fclose(f); }
}

static void set_crc(uint8_t *data, size_t size)
{
    uint32_t crc = rr_state_crc(data + RR_STATE_ENVELOPE_HEADER, size - RR_STATE_ENVELOPE_HEADER);
    for (int i = 0; i < 4; ++i) data[84 + i] = (uint8_t)(crc >> (8 * i));
}

static void check_cpu(void)
{
    uint8_t bytes[64];
    set_machine(0);
    Z80State written = cpu, read;
    RetroStateIO out = { bytes, sizeof bytes, 0, RR_STATE_WRITE, true };
    rr_z80_cpu_state(&out, &written);
    expect("CPU: 43 bytes written", out.ok && out.pos == RR_Z80_CPU_STATE_BYTES);
    expect("CPU: the order of gamestate.inc and msx_state_file.inc (A first, L' at 15, PC little endian at 16, cycle last)",
           bytes[0] == cpu.a && bytes[1] == cpu.f && bytes[15] == cpu.l_ && bytes[16] == 0x34 && bytes[17] == 0x12
           && bytes[24] == 0xF0 && bytes[25] == 0xDE && bytes[26] == cpu.i && bytes[27] == cpu.r && bytes[30] == cpu.im
           && bytes[31] == cpu.halted && bytes[32] == cpu.q && bytes[35] == (uint8_t)cpu.cyc && bytes[42] == (uint8_t)(cpu.cyc >> 56));
    memset(&read, 0, sizeof read);
    RetroStateIO check = { bytes, out.pos, 0, RR_STATE_CHECK, true };
    rr_z80_cpu_state(&check, &read);
    expect("CPU: round trip, every field", check.ok && check.pos == out.pos && cpu_equal(&read, &cpu));
    static const struct { unsigned at; uint8_t value; const char *name; } forged[] = {
        { 28, 2, "IFF1 2" }, { 29, 2, "IFF2 2" }, { 30, 3, "IM 3" }, { 31, 2, "HALT 2" }, { 33, 2, "P 2" }, { 34, 2, "EI block 2" },
        { 42, 0x10, "cycle 2^60 + 1" },
    };
    for (unsigned n = 0; n < sizeof forged / sizeof forged[0]; ++n) {
        uint8_t copy[64];
        memcpy(copy, bytes, sizeof copy);
        copy[forged[n].at] = forged[n].value;
        if (forged[n].at == 42) { memset(copy + 35, 0, 7); copy[35] = 1; }   /* 2^60 + 1 (2^60 itself is allowed) */
        RetroStateIO bad = { copy, out.pos, 0, RR_STATE_CHECK, true };
        Z80State candidate = cpu;
        rr_z80_cpu_state(&bad, &candidate);
        char name[96];
        snprintf(name, sizeof name, "CPU: %s out of its bounds refused", forged[n].name);
        expect(name, !bad.ok);
    }
    RetroStateIO cut = { bytes, out.pos - 1, 0, RR_STATE_CHECK, true };
    Z80State candidate = cpu;
    rr_z80_cpu_state(&cut, &candidate);
    expect("CPU: one byte short refused", !cut.ok);
}

static void check_file(void)
{
    RetroStateFile a = toy_file(binding_a, 1), b = toy_file(binding_b, 1), other_schema = toy_file(binding_a, 2);
    static uint8_t saved[4096], data[4096];

    set_machine(1);
    expect("file: missing", rr_state_file_load(&a, wide("toy.rrstate")) == RR_STATE_MISSING);
    expect("file: save", rr_state_file_save(&a, wide("toy.rrstate")) == RR_STATE_OK);
    long size = file_bytes("toy.rrstate", saved, sizeof saved);
    expect("file: 88-byte header, binding, CPU, RAM, frames", size == 88 + 4 + 43 + 256 + 8);
    expect("file: the binding opens the body", !memcmp(saved + 88, binding_a, 4) && saved[92] == cpu.a);
    Z80State before = cpu;
    set_machine(2);
    expect("file: load", rr_state_file_load(&a, wide("toy.rrstate")) == RR_STATE_OK);
    set_machine(1);
    Z80State expected_cpu = cpu;
    uint8_t expected_board[sizeof board];
    memcpy(expected_board, &board, sizeof board);
    set_machine(2);
    rr_state_file_load(&a, wide("toy.rrstate"));
    expect("file: round trip, the CPU and the machine", cpu_equal(&cpu, &before) && cpu_equal(&cpu, &expected_cpu)
           && !memcmp(&board, expected_board, sizeof board));

    set_machine(3); keep();
    put_file("cut.rrstate", saved, (size_t)size - 1);
    expect("file: truncated refused (invalid)", rr_state_file_load(&a, wide("cut.rrstate")) == RR_STATE_INVALID);
    expect("file: truncated left the machine unchanged", unchanged());
    put_file("long.rrstate", saved, (size_t)size + 1);
    expect("file: a byte too many refused", rr_state_file_load(&a, wide("long.rrstate")) == RR_STATE_INVALID && unchanged());

    memcpy(data, saved, (size_t)size);
    data[88 + 4 + 43 + 10] ^= 0x40;                                     /* a RAM byte, CRC left as it was */
    put_file("damaged.rrstate", data, (size_t)size);
    expect("file: damaged refused (invalid)", rr_state_file_load(&a, wide("damaged.rrstate")) == RR_STATE_INVALID && unchanged());

    memcpy(data, saved, (size_t)size);
    data[88 + 4 + 30] = 3;                                              /* IM 3 */
    set_crc(data, (size_t)size);
    put_file("forged.rrstate", data, (size_t)size);
    expect("file: an out-of-range CPU field with a right CRC refused (invalid)",
           rr_state_file_load(&a, wide("forged.rrstate")) == RR_STATE_INVALID && unchanged());

    expect("file: another build's binding told apart (incompatible)",
           rr_state_file_load(&b, wide("toy.rrstate")) == RR_STATE_INCOMPATIBLE && unchanged());
    expect("file: another schema (incompatible)", rr_state_file_load(&other_schema, wide("toy.rrstate")) == RR_STATE_INCOMPATIBLE
           && unchanged());
    memcpy(data, saved, (size_t)size);
    data[88 + 3] = 9;                                                   /* the binding changed, CRC left: damage, not a build */
    put_file("binding-damaged.rrstate", data, (size_t)size);
    expect("file: a binding byte damaged under the CRC stays invalid",
           rr_state_file_load(&b, wide("binding-damaged.rrstate")) == RR_STATE_INVALID && unchanged());

    /* The machine's consistency check: the cycle below the frame count. */
    set_machine(4);
    cpu.cyc = 10; board.frames = 20;
    expect("file: an inconsistent state saved", rr_state_file_save(&a, wide("inconsistent.rrstate")) == RR_STATE_OK);
    set_machine(5); keep();
    expect("file: the machine's consistency check refuses it (invalid)",
           rr_state_file_load(&a, wide("inconsistent.rrstate")) == RR_STATE_INVALID && unchanged());
    RetroStateFile no_hook = a;
    no_hook.consistent = NULL;
    expect("file: the same state loads without the check (positive control)",
           rr_state_file_load(&no_hook, wide("inconsistent.rrstate")) == RR_STATE_OK && cpu.cyc == 10 && board.frames == 20);

    /* Interrupted saves: the old file stays whole. */
    set_machine(6);
    char temporary[2048];
    snprintf(temporary, sizeof temporary, "%s/toy.rrstate.%lu.tmp", folder, rr_process_id());
    make_folder(temporary);                                             /* the temporary cannot be opened */
    expect("file: a save that cannot write fails", rr_state_file_save(&a, wide("toy.rrstate")) == RR_STATE_IO_ERROR);
    remove_folder(temporary);
    long now = file_bytes("toy.rrstate", data, sizeof data);
    expect("file: ...and leaves the old file whole", now == size && !memcmp(data, saved, (size_t)size));
    refuse_write = 1;
    expect("file: a machine that refuses to write fails", rr_state_file_save(&a, wide("toy.rrstate")) == RR_STATE_INVALID);
    refuse_write = 0;
    now = file_bytes("toy.rrstate", data, sizeof data);
    expect("file: ...and leaves the old file whole", now == size && !memcmp(data, saved, (size_t)size));
    RetroStateFile small = a;
    small.capacity = 100;
    expect("file: a state larger than the capacity is not written", rr_state_file_save(&small, wide("toy.rrstate")) == RR_STATE_INVALID
           && file_bytes("toy.rrstate", data, sizeof data) == size);
    expect("file: ...nor read", rr_state_file_load(&small, wide("toy.rrstate")) == RR_STATE_INVALID);
    expect("file: no temporary left", file_bytes(strrchr(temporary, '/') + 1, data, sizeof data) < 0);
}

int main(int argc, char **argv)
{
    if (argc < 2 || strlen(argv[1]) >= sizeof folder) { fprintf(stderr, "usage: state_file_checks FOLDER\n"); return 2; }
    strcpy(folder, argv[1]);
    check_cpu();
    check_file();
    printf("{\"passed\": %d, \"failed\": %d}\n", passed, failed);
    return 0;                                    /* the JSON line carries the verdict (the runner reads every line) */
}
