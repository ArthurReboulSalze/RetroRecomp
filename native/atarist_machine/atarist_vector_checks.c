/* Independent MC68000 vectors replayed through the Atari ST's 68000 (gate G10, independent CPU evidence). Original Retro-Recomp
 * code, MIT; it is linked with Hatari (GPL-2.0, licenses/hatari.md), so a program built with it is distributed under the GPL.
 *
 * The vectors are SingleStepTests/m68000 data (MIT, generated with MAME, not recorded from hardware). The code under test is the
 * ST's own CPU: the cycle-exact 68000 of Hatari (WinUAE's), in the plain-ST configuration the session builds (8 MHz, 4096 KiB of
 * ST RAM, the cycle-exact table op_smalltbl_14). The machine is brought up by the session with a tiny authored TOS image and a
 * blank floppy image, both built here in memory (no firmware, no disk, no game), and run for one frame so that Hatari builds its
 * CPU tables and enters its cycle-exact loop. Each vector is then loaded straight into Hatari's CPU and RAM and ONE instruction
 * is executed the way the loop executes it: the registers, the stacks, SR and the two prefetched words are set (regs.ir, regs.irc),
 * PC is the instruction's own address, the cycle counter of the loop is zeroed on a 4-cycle boundary, and the handler of the
 * opcode is called (m68k_run_1_ce does `(*cpufunctbl_noret[opcode])(opcode)`; so does the native step of an ST game, with the
 * handler's name as a literal).
 *
 * Two paths run every vector: "interpreter" (the table Hatari's loop calls, cpufunctbl_noret) and "native step" (the handler
 * found in op_smalltbl_14 by its opcode, which is what a generated step calls). They must be the same function; the harness
 * checks the pointers and the results. Both are compared with the vector's final registers, SR, PC and every byte of RAM, and
 * the cycles Hatari charged are compared with the vector's, apart from the state: the ST rounds every bus access up to a
 * multiple of 4 cycles, so a difference that is exactly that rounding is its own category, not a CPU disagreement.
 *
 * The vectors are read from a text file written by tools/atarist_vector_selftest.py (the window filter and the PC convention are
 * there, tested without a compiler). "--flat" replaces every memory bank of the CPU by a flat 24-bit RAM (no ST memory map), which
 * isolates the CPU from the machine's map and allows every vector; the default keeps the ST's map (RAM below 4 MiB, the system
 * area below $800 reserved to the supervisor, the first 8 bytes a ROM mirror, bus errors elsewhere). Nothing is hidden: a
 * difference with the vectors is reported, not excused. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "main.h"
#include "configuration.h"
#include "m68000.h"
#include "stMemory.h"
#include "cycles.h"
#include "sysconfig.h"
#include "sysdeps.h"
#include "options_cpu.h"
#include "memory.h"
#include "newcpu.h"
#include "events.h"

#include "atarist_session.h"

/* The ST RAM the harness uses: 4 MiB (the largest an ST has), so more vectors fit its map. */
#define MEMORY_KB 4096u
#define FLAT_BYTES 0x1000000u

/* ------------------------------------------------------------------------------------------------ the authored machine */
#define TOS_BYTES 196608u        /* 192 KiB: the size of the TOS 1.04 ROM, the largest Hatari accepts at $FC0000 */
#define DISK_BYTES 737280u       /* 720 KiB: a double-sided, 80-track, 9-sector floppy */

static void put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }

/* A TOS image Hatari accepts and whose reset configures the memory and runs a loop: byte 0 is a branch (as the ROM's first word), the
 * version word 0x0104 is at offset 2, the reset program counter (offset 4) and the ROM base (offset 8) are $FC0020 and $FC0000. The
 * code at $20 does what TOS does first: it writes the memory configuration register of the MMU ($FF8001: $0A, two banks of 2 MiB),
 * without which an ST maps only its smallest banks; then `BRA.S *`. */
static uint8_t *authored_tos(void) {
    static const uint8_t code[] = {0x13, 0xfc, 0x00, 0x0a, 0x00, 0xff, 0x80, 0x01,   /* MOVE.B #$0A,$FF8001.L */
                                   0x60, 0xfe};                                      /* BRA.S * */
    uint8_t *tos = (uint8_t *)calloc(1, TOS_BYTES);
    if (!tos) return NULL;
    tos[0] = 0x60; tos[1] = 0x1e;           /* BRA.S, and the high word of the reset stack pointer */
    tos[2] = 0x01; tos[3] = 0x04;           /* TOS version 1.04; the reset stack pointer is $601E0104 (24 bits: RAM) */
    put32(tos + 4, 0x00fc0020u);            /* reset program counter */
    put32(tos + 8, 0x00fc0000u);            /* base address of the ROM */
    memcpy(tos + 0x20, code, sizeof code);
    return tos;
}

static const char *log_text;
static void log_line(const char *line) { if (log_text) fprintf(stderr, "[hatari] %s", line); }

/* ------------------------------------------------------------------------------------------------------------ vectors */
typedef struct { uint32_t address; uint8_t value; } BytePair;
typedef struct {
    char name[112], group[48];
    int cycles, aligned;                 /* the vector's clocks; the same with every bus access on a 4-cycle boundary (-1: unknown) */
    uint32_t sr_mask, stopped, ir, irc;  /* stopped: 1 when the instruction leaves the CPU stopped (STOP) */
    uint32_t initial[19], final[19];     /* d0-d7, a0-a6, usp, ssp, sr, pc (the instruction's own address) */
    BytePair *before, *after;
    unsigned before_count, after_count;
} Vector;

static Vector *vectors;
static unsigned vector_count;

static char *next_token(char **cursor) {
    char *start = *cursor, *end;
    while (*start == ' ') ++start;
    if (!*start) return NULL;
    end = start;
    while (*end && *end != ' ') ++end;
    if (*end) *end++ = 0;
    *cursor = end;
    return start;
}
static uint64_t next_number(char **cursor) { char *t = next_token(cursor); return t ? strtoull(t, NULL, 10) : 0; }
static int64_t next_signed(char **cursor) { char *t = next_token(cursor); return t ? strtoll(t, NULL, 10) : 0; }

static int read_vectors(const char *path) {
    FILE *f = fopen(path, "rb");
    long size;
    char *text, *line, *cursor;
    unsigned capacity = 0;
    if (!f) return 0;
    fseek(f, 0, SEEK_END); size = ftell(f); fseek(f, 0, SEEK_SET);
    text = (char *)malloc((size_t)size + 1);
    if (!text || fread(text, 1, (size_t)size, f) != (size_t)size) { fclose(f); return 0; }
    fclose(f);
    text[size] = 0;
    for (line = strtok(text, "\n"); line; line = strtok(NULL, "\n")) {
        Vector *v;
        char *name, *group;
        unsigned i;
        if (vector_count == capacity) {
            capacity = capacity ? capacity * 2 : 1024;
            vectors = (Vector *)realloc(vectors, capacity * sizeof *vectors);
            if (!vectors) return 0;
        }
        v = &vectors[vector_count++];
        memset(v, 0, sizeof *v);
        cursor = line;
        name = next_token(&cursor); group = next_token(&cursor);
        if (!name || !group) return 0;
        snprintf(v->name, sizeof v->name, "%s", name);
        snprintf(v->group, sizeof v->group, "%s", group);
        v->cycles = (int)next_signed(&cursor);
        v->aligned = (int)next_signed(&cursor);
        v->sr_mask = (uint32_t)next_number(&cursor);
        v->stopped = (uint32_t)next_number(&cursor);
        v->ir = (uint32_t)next_number(&cursor);
        v->irc = (uint32_t)next_number(&cursor);
        for (i = 0; i < 19; ++i) v->initial[i] = (uint32_t)next_number(&cursor);
        for (i = 0; i < 19; ++i) v->final[i] = (uint32_t)next_number(&cursor);
        v->before_count = (unsigned)next_number(&cursor);
        v->before = (BytePair *)malloc((v->before_count + 1) * sizeof *v->before);
        for (i = 0; i < v->before_count; ++i) { v->before[i].address = (uint32_t)next_number(&cursor); v->before[i].value = (uint8_t)next_number(&cursor); }
        v->after_count = (unsigned)next_number(&cursor);
        v->after = (BytePair *)malloc((v->after_count + 1) * sizeof *v->after);
        for (i = 0; i < v->after_count; ++i) { v->after[i].address = (uint32_t)next_number(&cursor); v->after[i].value = (uint8_t)next_number(&cursor); }
    }
    return 1;
}

/* ------------------------------------------------------------------------------------------------------ the memory */
static uint8_t *memory;              /* the RAM the vectors live in: Hatari's ST RAM, or the flat 24-bit RAM */
static uint32_t memory_low, memory_end;   /* the first byte vectors may use (the ST keeps 8 bytes of ROM mirror) and the size */
static int flat, verbose;

/* The flat bus (--flat): one bank over all 256 64-KiB blocks of the 24-bit space, plain big-endian RAM. */
static uae_u8 flat_ram[FLAT_BYTES];
static addrbank flat_bank;
/* Every address aliases into this much of the flat RAM: --all-forms confines an instruction with random registers to a window it can compare. */
static uae_u32 flat_mask = 0xffffffu;
/* --all-forms: each access of the flat bank in order, with its clock, and an interrupt line that changes at one of them. */
typedef struct { uint32_t kind, addr, value; int64_t clock; } BusAccess;
static BusAccess bus_log[256];
static unsigned bus_count;
static int bus_logging, bus_flip_at = -1, bus_flip_level;
static void bus_note(uint32_t kind, uae_u32 addr, uint32_t value) {
    if (!bus_logging) return;
    if (bus_count < sizeof bus_log / sizeof *bus_log) {
        BusAccess *b = &bus_log[bus_count];
        b->kind = kind; b->addr = addr; b->value = value;
        b->clock = (int64_t)CyclesGlobalClockCounter * 2 * CYCLE_UNIT + (int64_t)currcycle * 2;
    }
    if ((int)bus_count == bus_flip_at) {
        regs.ipl_pin_p = regs.ipl_pin; regs.ipl_pin_change_evt_p = regs.ipl_pin_change_evt;
        regs.ipl_pin = bus_flip_level; regs.ipl_pin_change_evt = currcycle;
    }
    ++bus_count;
}
static uae_u32 REGPARAM2 flat_lget(uaecptr a) { a &= flat_mask; bus_note(4, a, 0); return (uae_u32)flat_ram[a] << 24 | (uae_u32)flat_ram[(a + 1) & flat_mask] << 16 |
                                                   (uae_u32)flat_ram[(a + 2) & flat_mask] << 8 | flat_ram[(a + 3) & flat_mask]; }
static uae_u32 REGPARAM2 flat_wget(uaecptr a) { a &= flat_mask; bus_note(2, a, 0); return (uae_u32)flat_ram[a] << 8 | flat_ram[(a + 1) & flat_mask]; }
static uae_u32 REGPARAM2 flat_wgeti(uaecptr a) { a &= flat_mask; bus_note(3, a, 0); return (uae_u32)flat_ram[a] << 8 | flat_ram[(a + 1) & flat_mask]; }
static uae_u32 REGPARAM2 flat_bget(uaecptr a) { a &= flat_mask; bus_note(1, a, 0); return flat_ram[a]; }
static void REGPARAM2 flat_lput(uaecptr a, uae_u32 v) {
    a &= flat_mask;
    bus_note(8, a, v);
    flat_ram[a] = (uae_u8)(v >> 24); flat_ram[(a + 1) & flat_mask] = (uae_u8)(v >> 16);
    flat_ram[(a + 2) & flat_mask] = (uae_u8)(v >> 8); flat_ram[(a + 3) & flat_mask] = (uae_u8)v;
}
static void REGPARAM2 flat_wput(uaecptr a, uae_u32 v) { a &= flat_mask; bus_note(6, a, v & 0xffff); flat_ram[a] = (uae_u8)(v >> 8); flat_ram[(a + 1) & flat_mask] = (uae_u8)v; }
static void REGPARAM2 flat_bput(uaecptr a, uae_u32 v) { a &= flat_mask; bus_note(5, a, v & 0xff); flat_ram[a] = (uae_u8)v; }
static int REGPARAM2 flat_check(uaecptr a, uae_u32 size) { return (a & 0xffffffu) + size <= FLAT_BYTES; }
static uae_u8 *REGPARAM2 flat_xlate(uaecptr a) { return flat_ram + (a & 0xffffffu); }

static void install_flat_bank(void) {
    unsigned block;
    memset(&flat_bank, 0, sizeof flat_bank);
    flat_bank.lget = flat_lget; flat_bank.wget = flat_wget; flat_bank.bget = flat_bget;
    flat_bank.lput = flat_lput; flat_bank.wput = flat_wput; flat_bank.bput = flat_bput;
    flat_bank.lgeti = flat_lget; flat_bank.wgeti = flat_wgeti;
    flat_bank.check = flat_check; flat_bank.xlateaddr = flat_xlate;
    flat_bank.baseaddr = flat_ram;
    flat_bank.label = "flat"; flat_bank.name = "Flat 24-bit RAM";
    flat_bank.flags = ABFLAG_RAM;
    flat_bank.mask = 0xffffffu; flat_bank.startmask = 0; flat_bank.start = 0;
    flat_bank.allocated_size = FLAT_BYTES;
    for (block = 0; block < 256; ++block) {
        map_banks_ce(&flat_bank, (int)block, 1, 0, CE_MEMBANK_CHIP16, CE_MEMBANK_NOT_CACHABLE);
    }
}

/* -------------------------------------------------------------------------------------------- one instruction */
typedef struct { uint32_t reg[19]; int cycles; int bus_error; int stopped; } Outcome;

/* The forms the converter's own generator writes for the opcodes of the vectors (retrorecomp/atarist_codegen.py: Hatari's handler of the opcode compiled for that opcode, on the
 * shared bus functions, as a game's instructions run them). A harness built without them (the first pass of tools/atarist_vector_selftest.py, which only writes Hatari's opcode
 * table) has no native step. */
typedef struct { uint16_t opcode; void (*run)(void); } VectorStep;
#ifdef RR_VECTOR_STEPS
extern const VectorStep rr_vector_steps[];
extern const unsigned rr_vector_step_count;
#endif
static void (*native_step[65536])(void);   /* by opcode; NULL: Hatari's table sends the opcode to an illegal handler, or no step was generated */

static void build_native_table(void) {
#ifdef RR_VECTOR_STEPS
    unsigned n;
    for (n = 0; n < rr_vector_step_count; ++n) native_step[rr_vector_steps[n].opcode] = rr_vector_steps[n].run;
#endif
}

/* The ST's RAM is a "chip" bus: every CPU access waits for a 4-cycle slot. Marking every bank as plain 16-bit memory (what Hatari uses
 * for its ROM and I/O area) removes the wait and leaves the CPU's own timing. The table is indexed by the 16 high bits of the 32-bit
 * address the instruction computed, not only by the 256 banks of the 24-bit bus, so all 65,536 entries change. */
static uae_u8 saved_bank_type[65536];
static void use_plain_bus(int plain) {
    if (plain) {
        memcpy(saved_bank_type, ce_banktype, sizeof saved_bank_type);
        memset(ce_banktype, CE_MEMBANK_FAST16, sizeof saved_bank_type);
    } else {
        memcpy(ce_banktype, saved_bank_type, sizeof saved_bank_type);
    }
}

static void load_vector(const Vector *v) {
    unsigned i;
    uint32_t sr = v->initial[17];
    /* Clean RAM: the vectors list every byte they touch, the rest is zero (the first 8 bytes of an ST are a ROM mirror: left alone). */
    memset(memory + memory_low, 0, memory_end - memory_low);
    for (i = 0; i < v->before_count; ++i) memory[v->before[i].address & 0xffffffu] = v->before[i].value;
    for (i = 0; i < 8; ++i) regs.regs[i] = v->initial[i];
    for (i = 0; i < 7; ++i) regs.regs[8 + i] = v->initial[8 + i];
    regs.t1 = (sr >> 15) & 1; regs.t0 = 0; regs.s = (sr >> 13) & 1; regs.m = 0; regs.intmask = (int)((sr >> 8) & 7);
    regs.usp = v->initial[15]; regs.isp = v->initial[16];
    regs.regs[15] = regs.s ? regs.isp : regs.usp;
    SET_XFLG((sr >> 4) & 1); SET_NFLG((sr >> 3) & 1); SET_ZFLG((sr >> 2) & 1); SET_VFLG((sr >> 1) & 1); SET_CFLG(sr & 1);
    regs.sr = (uae_u16)sr;
    regs.stopped = 0; regs.halted = 0; regs.exception = 0; regs.loop_mode = 0; regs.spcflags = 0;
    regs.ipl[0] = regs.ipl[1] = 0; regs.ipl_pin = regs.ipl_pin_p = 0; regs.lastipl = 0;
    regs.read_buffer = regs.write_buffer = 0; regs.memory_waitstate_cycles = 0; regs.ce020extracycles = 0;
    m68k_setpc(v->initial[18] & 0xffffffu);                  /* also instruction_pc */
    regs.ir = (uae_u16)v->ir; regs.irc = (uae_u16)v->irc; regs.ird = regs.ir; regs.opcode = regs.ir;
    hardware_bus_error = 0;
    /* The loop's own preparation: its cycle counter is zero, and the global clock is on a 4-cycle boundary (the ST's bus slots). */
    CyclesGlobalClockCounter = (CyclesGlobalClockCounter + 3u) & ~(uint64_t)3u;
    currcycle = 0;
}

static void run_handler(cpuop_func_noret *handler, void (*form)(void), Outcome *out) {
    uint64_t clock = CyclesGlobalClockCounter;
    uint32_t opcode = regs.ir;
    regs.opcode = (uae_u16)opcode;
    regs.instruction_pc = m68k_getpc();
    if (form) form();
    else handler(opcode);
    if (regs.memory_waitstate_cycles) { x_do_cycles(regs.memory_waitstate_cycles); regs.memory_waitstate_cycles = 0; }
    out->cycles = (int)(CyclesGlobalClockCounter - clock) + (int)(currcycle * 2 / CYCLE_UNIT);
    out->bus_error = hardware_bus_error;
    out->stopped = regs.stopped != 0;
    {
        unsigned i;
        MakeSR();
        for (i = 0; i < 8; ++i) out->reg[i] = regs.regs[i];
        for (i = 0; i < 7; ++i) out->reg[8 + i] = regs.regs[8 + i];
        out->reg[15] = regs.s ? regs.usp : regs.regs[15];
        out->reg[16] = regs.s ? regs.regs[15] : regs.isp;
        out->reg[17] = regs.sr;
        out->reg[18] = m68k_getpc() & 0xffffffu;
    }
    currcycle = 0;
}

static const char *const field_name[20] = {"d0", "d1", "d2", "d3", "d4", "d5", "d6", "d7", "a0", "a1", "a2", "a3", "a4", "a5", "a6",
                                           "usp", "ssp", "sr", "pc", "stopped"};

/* 0: the registers, SR and PC agree (masked SR); else the index of the first that differs. */
static int registers_differ(const Vector *v, const Outcome *o) {
    unsigned i;
    for (i = 0; i < 19; ++i) {
        const uint32_t mask = i == 17 ? v->sr_mask : 0xffffffffu;
        if ((o->reg[i] & mask) != (v->final[i] & mask)) return (int)i + 1;
    }
    if ((uint32_t)o->stopped != v->stopped) return 20;
    return 0;
}

static uint8_t *expected_ram;
static uint8_t *snapshot_ram;

/* 0: RAM is as the vector's final listing says (every listed byte; every other byte still zero); else the first differing address + 1. */
static int64_t ram_differs(const Vector *v) {
    unsigned i;
    int64_t bad = 0;
    for (i = 0; i < v->before_count; ++i) expected_ram[v->before[i].address & 0xffffffu] = v->before[i].value;
    for (i = 0; i < v->after_count; ++i) expected_ram[v->after[i].address & 0xffffffu] = v->after[i].value;
    if (memcmp(expected_ram + memory_low, memory + memory_low, memory_end - memory_low)) {
        uint32_t a;
        for (a = memory_low; a < memory_end; ++a) if (expected_ram[a] != memory[a]) { bad = (int64_t)a + 1; break; }
    }
    for (i = 0; i < v->before_count; ++i) expected_ram[v->before[i].address & 0xffffffu] = 0;
    for (i = 0; i < v->after_count; ++i) expected_ram[v->after[i].address & 0xffffffu] = 0;
    return bad;
}

/* ------------------------------------------------------------------------------------------------------ the summary */
typedef struct {
    char name[48];
    unsigned run, state_ok, cycle_ok, cycle_bus, cycle_other, cycle_unmodelled, plain_ok, model_checked, model_ok, native_available, native_state_ok, paths_equal;
} Group;
static Group groups[256];
static unsigned group_count;

static Group *group_of(const char *name) {
    unsigned i;
    for (i = 0; i < group_count; ++i) if (!strcmp(groups[i].name, name)) return &groups[i];
    if (group_count >= sizeof groups / sizeof *groups) { fprintf(stderr, "too many groups\n"); exit(2); }
    snprintf(groups[group_count].name, sizeof groups[group_count].name, "%s", name);
    return &groups[group_count++];
}

typedef struct { char name[140]; } Example;
static Example state_examples[20], cycle_examples[20];
static unsigned state_example_count, cycle_example_count;
static unsigned bus_errors;

static void add_example(Example *list, unsigned *count, const char *name, const char *what, long long expected, long long got) {
    if (*count >= 20) return;
    snprintf(list[*count].name, sizeof list[*count].name, "%s | %s | expected %lld | got %lld", name, what, expected, got);
    { char *c; for (c = list[*count].name; *c; ++c) if (*c == '"' || *c == '\\') *c = '\''; }
    ++*count;
}

/* --all-forms: every form of the build against the table's handler of its opcode, on random states: registers, condition codes, interrupt mask and pin, the position in the bus slot,
 * and the RAM in a window every address aliases into. The forms are Hatari's own text compiled again for one opcode: what could differ is what the compiler does with a literal. */
#define WINDOW_BYTES 0x40000u
typedef struct { Outcome o; uint32_t ipl0, ipl1, ipl_evt, irc, ir, opcode, spcflags, db, read_buffer, write_buffer; } FormOutcome;
static uint32_t form_seed;
static uint32_t form_random(void) { form_seed = form_seed * 1664525u + 1013904223u; return form_seed ^ (form_seed >> 15); }

static void form_run(unsigned op, uint32_t seed, uint64_t clock, const uint8_t *pattern, cpuop_func_noret *handler, void (*form)(void), FormOutcome *out, BusAccess *log, unsigned *log_count) {
    unsigned i;
    uint32_t sr;
    memcpy(flat_ram, pattern, WINDOW_BYTES);
    form_seed = seed;
    for (i = 0; i < 8; ++i) regs.regs[i] = form_random();
    for (i = 0; i < 7; ++i) regs.regs[8 + i] = (form_random() & (WINDOW_BYTES - 1)) & ~(form_random() & 1u);
    sr = form_random() & 0xa71fu;
    if (!(seed & 7)) sr &= 0x7fffu; else sr &= 0x271fu;
    regs.t1 = (sr >> 15) & 1; regs.t0 = 0; regs.s = (sr >> 13) & 1; regs.m = 0; regs.intmask = (int)((sr >> 8) & 7);
    regs.usp = form_random() & (WINDOW_BYTES - 2); regs.isp = form_random() & (WINDOW_BYTES - 2);
    regs.regs[15] = regs.s ? regs.isp : regs.usp;
    SET_XFLG((sr >> 4) & 1); SET_NFLG((sr >> 3) & 1); SET_ZFLG((sr >> 2) & 1); SET_VFLG((sr >> 1) & 1); SET_CFLG(sr & 1);
    regs.sr = (uae_u16)sr;
    regs.stopped = 0; regs.halted = 0; regs.exception = 0; regs.loop_mode = 0; regs.spcflags = 0;
    regs.ipl[0] = (int)(form_random() & 7); regs.ipl[1] = 0; regs.ipl_pin = regs.ipl_pin_p = (int)(form_random() & 7); regs.lastipl = 0;
    regs.ipl_evt = 0; regs.ipl_pin_change_evt = regs.ipl_pin_change_evt_p = 0;
    regs.read_buffer = regs.write_buffer = 0; regs.memory_waitstate_cycles = 0; regs.ce020extracycles = 0;
    m68k_setpc(0x1000u + (form_random() & 0xfffeu));
    regs.ir = (uae_u16)op; regs.irc = (uae_u16)form_random(); regs.ird = regs.ir; regs.opcode = regs.ir;
    hardware_bus_error = 0;
    CyclesGlobalClockCounter = clock;
    currcycle = 0;
    bus_count = 0;
    memset(bus_log, 0, sizeof bus_log);
    bus_flip_at = (int)(form_random() % 6);
    bus_flip_level = (int)(form_random() & 7);
    bus_logging = 1;
    run_handler(handler, form, &out->o);
    bus_logging = 0;
    memcpy(log, bus_log, sizeof bus_log);
    *log_count = bus_count;
    out->ipl0 = (uint32_t)regs.ipl[0]; out->ipl1 = (uint32_t)regs.ipl[1]; out->ipl_evt = (uint32_t)regs.ipl_evt; out->irc = regs.irc; out->ir = regs.ir; out->opcode = regs.opcode;
    out->spcflags = (uint32_t)regs.spcflags; out->db = regs.db; out->read_buffer = regs.read_buffer; out->write_buffer = regs.write_buffer;
}

static int all_forms_check(void) {
    static const unsigned reset = 0x4e70;   /* resets the machine's devices: not a state these runs can compare */
    uint8_t *pattern = (uint8_t *)malloc(WINDOW_BYTES), *first = (uint8_t *)malloc(WINDOW_BYTES);
    unsigned long runs = 0, differ = 0, forms = 0, accesses = 0;
    unsigned op, s, i, pass;
    static BusAccess table_log[256], native_log[256];
    unsigned table_count, native_count;
    uint64_t clock = CyclesGlobalClockCounter & ~(uint64_t)3u;
    if (!pattern || !first) return 2;
    form_seed = 0x5eed;
    for (i = 0; i < WINDOW_BYTES; i += 2) {
        uint32_t word = form_random();
        pattern[i] = (uint8_t)(word >> 8);
        pattern[i + 1] = (uint8_t)word;
    }
    /* Pass 0: through the bank's functions, each access logged. Pass 1: the bank offers its RAM directly, the path ST memory takes in steps/bus.c. */
    for (pass = 0; pass < 2; ++pass) {
    flat_bank.baseaddr_direct_r = flat_bank.baseaddr_direct_w = pass ? flat_ram : NULL;
    flat_bank.startaccessmask = 0;
    flat_bank.mask = flat_mask;
    for (op = 0; op < 65536; ++op) {
        if (!native_step[op] || op == reset) continue;
        forms += !pass;
        for (s = 0; s < 4; ++s) {
            FormOutcome table, native;
            uint32_t seed = op * 2654435761u + s + pass * 97u;
            uint64_t start = clock + s;   /* each position in the bus slot */
            form_run(op, seed, start, pattern, cpufunctbl_noret[op], NULL, &table, table_log, &table_count);
            memcpy(first, flat_ram, WINDOW_BYTES);
            form_run(op, seed, start, pattern, NULL, native_step[op], &native, native_log, &native_count);
            ++runs;
            accesses += table_count;
            /* uninitialised padding of the two structures is cleared by comparing field by field */
            if (memcmp(table.o.reg, native.o.reg, sizeof table.o.reg) || table.o.cycles != native.o.cycles || table.o.stopped != native.o.stopped || table.o.bus_error != native.o.bus_error ||
                table.ipl0 != native.ipl0 || table.ipl1 != native.ipl1 || table.ipl_evt != native.ipl_evt || table.irc != native.irc || table.ir != native.ir ||
                table.opcode != native.opcode || table.spcflags != native.spcflags || table.db != native.db || table.read_buffer != native.read_buffer ||
                table.write_buffer != native.write_buffer || memcmp(first, flat_ram, WINDOW_BYTES) ||
                table_count != native_count || memcmp(table_log, native_log, sizeof table_log)) {
                if (++differ <= 40) {
                    fprintf(stderr, "form differs | pass %u | op %04x | seed %u | clocks %d against %d | db %x against %x | ipl %u %u against %u %u | ram %d | accesses %u against %u, log %d\n", pass, op, s, native.o.cycles, table.o.cycles, native.db, table.db,
                            native.ipl0, native.ipl1, table.ipl0, table.ipl1, memcmp(first, flat_ram, WINDOW_BYTES) != 0, native_count, table_count, memcmp(table_log, native_log, sizeof table_log) != 0);
                    for (i = 0; i < 19; ++i) if (native.o.reg[i] != table.o.reg[i]) fprintf(stderr, "  field %s: %08x against %08x\n", field_name[i], native.o.reg[i], table.o.reg[i]);
                }
            }
        }
    }
    }
    printf("{\"forms\":%lu,\"runs\":%lu,\"bus_accesses_compared\":%lu,\"differ\":%lu}\n", forms, runs, accesses, differ);
    return differ ? 1 : 0;
}

int main(int argc, char **argv) {
    uint8_t *tos = authored_tos();
    static RrStDisk disk;
    RrStGame game;
    RrStSession *session;
    char error[256] = "";
    unsigned n, ran = 0, outside_window = 0;
    unsigned total_state = 0, total_cycle_ok = 0, total_bus = 0, total_other = 0, total_unmodelled = 0, total_plain = 0, total_checked = 0, total_model = 0, total_native = 0, total_equal = 0;
    unsigned differ = 0, total_native_state = 0;
    const char *path = NULL, *map_path = NULL;
    int i, all_forms = 0;
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--flat")) flat = 1;
        else if (!strcmp(argv[i], "--log")) log_text = "1";
        else if (!strcmp(argv[i], "--verbose")) verbose = 1;
        else if (!strcmp(argv[i], "--all-forms")) all_forms = 1;
        else if (!strcmp(argv[i], "--opcode-map") && i + 1 < argc) map_path = argv[++i];
        else path = argv[i];
    }
    if ((!path && !map_path && !all_forms) || !tos) {
        fprintf(stderr, "usage: atarist_vector_checks [--flat] [--log] [--verbose] [--opcode-map map.txt] vectors.txt\n");
        return 2;
    }
    if (path && !read_vectors(path)) { fprintf(stderr, "cannot read the vectors\n"); return 2; }

    disk.name = "blank.st"; disk.size = DISK_BYTES;
    disk.data = (const uint8_t *)calloc(1, DISK_BYTES);
    memset(&game, 0, sizeof game);
    game.disks = &disk; game.disk_count = 1; game.tos = tos; game.tos_size = TOS_BYTES;
    game.machine = "st"; game.memory_kb = MEMORY_KB; game.log = log_line;
    session = rr_st_open(&game, error, sizeof error);
    if (!session) { fprintf(stderr, "the session did not open: %s\n", error); return 2; }
    if (rr_st_frame(session) != 0) { fprintf(stderr, "the first frame failed: %s\n", rr_st_error(session)); return 2; }
    if (!CpuRunCycleExact || currprefs.cpu_model != 68000 || !currprefs.cpu_cycle_exact) {
        fprintf(stderr, "Hatari is not running the cycle-exact 68000 (cycle exact %d, model %d)\n", (int)CpuRunCycleExact, (int)currprefs.cpu_model);
        return 2;
    }
    /* The authored TOS ran: the CPU is in its loop in the ROM and the MMU maps the two 2-MiB banks, so ST RAM is the 4 MiB the session asked for. */
    if (M68000_GetPC() < 0xfc0020u || M68000_GetPC() > 0xfc0030u || STRamEnd != MEMORY_KB * 1024u || MMU_Bank0_Size + MMU_Bank1_Size != STRamEnd) {
        fprintf(stderr, "the authored TOS did not set the machine up (pc %06x, RAM %u, MMU banks %u + %u)\n", (unsigned)M68000_GetPC(),
                (unsigned)STRamEnd, (unsigned)MMU_Bank0_Size, (unsigned)MMU_Bank1_Size);
        return 2;
    }
    if (map_path) {   /* the opcode -> handler table of Hatari's cycle-exact 68000, for the converter's step generator */
        FILE *map = fopen(map_path, "wb");
        if (!map || !rr_st_write_opcode_map(session, map) || fclose(map)) { fprintf(stderr, "cannot write the opcode map\n"); return 2; }
        if (!path) return 0;
    }
    build_native_table();
    if (all_forms) {
        flat_mask = WINDOW_BYTES - 1;
        install_flat_bank();
        return all_forms_check();
    }
    if (flat) { install_flat_bank(); memory = flat_ram; memory_low = 0; memory_end = FLAT_BYTES; }
    else { memory = STRam; memory_low = 8; memory_end = STRamEnd; }
    expected_ram = (uint8_t *)calloc(1, FLAT_BYTES);
    snapshot_ram = (uint8_t *)malloc(FLAT_BYTES);
    if (!expected_ram || !snapshot_ram) return 2;

    for (n = 0; n < vector_count; ++n) {
        const Vector *v = &vectors[n];
        Outcome interpreter, native, plain;
        cpuop_func_noret *table_handler = cpufunctbl_noret[v->ir & 0xffff];
        void (*step)(void) = native_step[v->ir & 0xffff];
        Group *g;
        int bad_regs, bad_native_regs = 0, state_ok, paths_equal = 1, cycle_kind, plain_cycles;
        int64_t bad_ram, bad_native_ram = 0;
        unsigned k, outside = 0;
        /* The vector must live in the window the memory offers: RAM above the 8-byte ROM mirror, and the system area below $800 only
         * when the vector starts in supervisor mode (a user-mode access there is a bus error on an ST). */
        for (k = 0; k < v->before_count + v->after_count; ++k) {
            const uint32_t a = (k < v->before_count ? v->before[k].address : v->after[k - v->before_count].address) & 0xffffffu;
            if (a < memory_low || a >= memory_end || (!flat && a < 0x800 && !(v->initial[17] & 0x2000))) outside = 1;
        }
        if (outside) { ++outside_window; continue; }
        g = group_of(v->group);
        ++g->run; ++ran;

        load_vector(v);
        run_handler(table_handler, NULL, &interpreter);
        bad_regs = registers_differ(v, &interpreter);
        bad_ram = ram_differs(v);
        state_ok = !bad_regs && !bad_ram;
        memcpy(snapshot_ram, memory, memory_end);

        if (step) {
            /* The native path: the very same call, through the step the converter generated for the opcode. */
            ++g->native_available;
            load_vector(v);
            run_handler(NULL, step, &native);
            bad_native_regs = registers_differ(v, &native);
            bad_native_ram = ram_differs(v);
            paths_equal = !memcmp(native.reg, interpreter.reg, sizeof native.reg) && native.cycles == interpreter.cycles &&
                          native.stopped == interpreter.stopped && !memcmp(snapshot_ram, memory, memory_end);
            g->paths_equal += paths_equal;
            if (!paths_equal) {
                unsigned r;
                fprintf(stderr, "native differs | %s | op %04x | clocks %d against %d | stopped %d against %d\n", v->name, v->ir, native.cycles, interpreter.cycles, native.stopped, interpreter.stopped);
                for (r = 0; r < sizeof native.reg / sizeof native.reg[0]; ++r)
                    if (native.reg[r] != interpreter.reg[r]) fprintf(stderr, "  field %s: %08x against %08x\n", field_name[r], native.reg[r], interpreter.reg[r]);
            }
            g->native_state_ok += !bad_native_regs && !bad_native_ram;
        }

        /* The same instruction once more with every bank a plain 16-bit bus (no ST slot): the CPU's own timing, as the vector's 68000 has it. */
        use_plain_bus(1);
        load_vector(v);
        run_handler(table_handler, NULL, &plain);
        use_plain_bus(0);
        plain_cycles = plain.cycles;
        /* The clocks are the vector's (0); or the difference is the ST's 4-cycle bus slots (1): the vector's own bus transactions placed on
         * 4-cycle slots give Hatari's clocks, or Hatari's clocks on a plain bus equal the vector's; or they differ and the vector has a
         * transaction list that does not explain it (2: the core's own timing); or they differ and the fixture has no transaction list
         * and the plain bus does not equal the vector either (3: not decided). */
        if (interpreter.cycles == v->cycles) cycle_kind = 0;
        else if ((v->aligned >= 0 && interpreter.cycles == v->aligned) || plain_cycles == v->cycles) cycle_kind = 1;
        else cycle_kind = v->aligned >= 0 ? 2 : 3;
        if (v->aligned >= 0) { ++g->model_checked; g->model_ok += interpreter.cycles == v->aligned; }   /* the vector's own transactions on 4-cycle slots */
        g->plain_ok += plain_cycles == v->cycles;
        if (verbose) fprintf(stderr, "%s | op %04x | vector %d aligned %d hatari %d plain %d | state %d\n", v->name, v->ir, v->cycles, v->aligned, interpreter.cycles, plain_cycles, state_ok);
        g->state_ok += state_ok;
        g->cycle_ok += cycle_kind == 0; g->cycle_bus += cycle_kind == 1; g->cycle_other += cycle_kind == 2; g->cycle_unmodelled += cycle_kind == 3;
        bus_errors += interpreter.bus_error != 0;
        if (!state_ok) {
            ++differ;
            if (bad_regs == 20) add_example(state_examples, &state_example_count, v->name, "stopped", (long long)v->stopped, (long long)interpreter.stopped);
            else if (bad_regs) add_example(state_examples, &state_example_count, v->name, field_name[bad_regs - 1], (long long)v->final[bad_regs - 1], (long long)interpreter.reg[bad_regs - 1]);
            else add_example(state_examples, &state_example_count, v->name, "ram", (long long)bad_ram - 1, 0);
        }
        if (cycle_kind >= 2) add_example(cycle_examples, &cycle_example_count, v->name, "cycles (ST bus / plain bus)", v->cycles, (long long)interpreter.cycles * 1000 + plain_cycles);
    }

    printf("{\"mode\":\"%s\",\"ram_bytes\":%u,\"vectors\":%u,\"outside_window\":%u,\"run\":%u,\"groups\":[", flat ? "flat" : "st", memory_end, vector_count, outside_window, ran);
    for (n = 0; n < group_count; ++n) {
        const Group *g = &groups[n];
        total_state += g->state_ok; total_cycle_ok += g->cycle_ok; total_bus += g->cycle_bus; total_plain += g->plain_ok;
        total_checked += g->model_checked; total_model += g->model_ok;
        total_other += g->cycle_other; total_unmodelled += g->cycle_unmodelled; total_native += g->native_available; total_equal += g->paths_equal; total_native_state += g->native_state_ok;
        printf("%s{\"group\":\"%s\",\"run\":%u,\"state_ok\":%u,\"cycle_ok\":%u,\"cycle_bus\":%u,\"cycle_other\":%u,\"cycle_unmodelled\":%u,\"plain_ok\":%u,"
               "\"model_checked\":%u,\"model_ok\":%u,\"native_step\":%u,\"native_state_ok\":%u,\"paths_equal\":%u}", n ? "," : "", g->name, g->run,
               g->state_ok, g->cycle_ok, g->cycle_bus, g->cycle_other, g->cycle_unmodelled, g->plain_ok, g->model_checked, g->model_ok, g->native_available,
               g->native_state_ok, g->paths_equal);
    }
    printf("],\"totals\":{\"run\":%u,\"state_ok\":%u,\"state_differ\":%u,\"cycle_ok\":%u,\"cycle_bus\":%u,\"cycle_other\":%u,\"cycle_unmodelled\":%u,\"plain_ok\":%u,"
           "\"model_checked\":%u,\"model_ok\":%u,\"native_step\":%u,\"native_state_ok\":%u,\"paths_equal\":%u,\"bus_errors\":%u},\"state_examples\":[",
           ran, total_state, differ, total_cycle_ok, total_bus, total_other, total_unmodelled, total_plain, total_checked, total_model, total_native, total_native_state,
           total_equal, bus_errors);
    for (n = 0; n < state_example_count; ++n) printf("%s\"%s\"", n ? "," : "", state_examples[n].name);
    printf("],\"cycle_examples\":[");
    for (n = 0; n < cycle_example_count; ++n) printf("%s\"%s\"", n ? "," : "", cycle_examples[n].name);
    printf("]}\n");
    return 0;
}
