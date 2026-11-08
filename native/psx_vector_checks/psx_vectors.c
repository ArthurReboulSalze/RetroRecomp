/* Independent vectors against the PlayStation's R3000A and GTE (gate G10), run by tools/psx_vector_selftest.py. Never linked
 * into a game. Retro-Recomp's own code (MIT); this test program compiles Beetle PSX's cpu.c into itself and is GPL-2.0 as a whole.
 *
 * psx_vectors R3000_FOLDER FILES_LIST GTE_FILE STEPS_FILE
 *
 * One instruction at a time, each vector of SingleStepTests/r3000 goes through the core's interpreter (CPU_RunReal, stopped after
 * one instruction by its own event check) and through the native step written for its opcode (retrorecomp/psx_native.py, the
 * code a game runs), on a simulated bus that serves the bytes the vector read and records the bytes written. Compared: the
 * thirty-one registers, HI, LO, PC, the next PC, the branch delay state, the pending load, EPC, TAR, CAUSE and the data bytes.
 * Not compared: cycles (the suite's are its model's), the shape of a bus access (an LWL may read fewer bytes than the model).
 * Each GTE vector writes the 64 registers, runs its command and compares the 64 registers.
 * One JSON line per file and path, and the first failures of each file for the report. Exit 0: it ran (the tool judges). */
#include <stdbool.h>
#include <stdint.h>
#define PSX_MemRead8 vec_read8
#define PSX_MemRead16 vec_read16
#define PSX_MemRead24 vec_read24
#define PSX_MemRead32 vec_read32
#define PSX_MemWrite8 vec_write8
#define PSX_MemWrite16 vec_write16
#define PSX_MemWrite24 vec_write24
#define PSX_MemWrite32 vec_write32
#define PSX_EventHandler vec_event
#include "mednafen/psx/cpu.c"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { READ_ACTION = 1, WRITE_ACTION = 2, MAX_BYTES = 64, FAILURES_SHOWN = 3 };
enum { F_R, F_HI, F_LO, F_PC, F_NEXT, F_DELAY, F_LOAD, F_EPC, F_TAR, F_CAUSE, F_READ, F_WRITE, FIELDS };
static const char *const FIELD_NAMES[FIELDS] = {"r", "hi", "lo", "pc", "next", "delay", "load", "epc", "tar", "cause", "read", "write"};

typedef struct {
    uint32_t r[32], hi, lo, epc, tar, cause, pc;
    uint32_t branch_target, branch_slot, branch_take;
    int32_t load_target;
    uint32_t load_value;
} State;

typedef struct { uint32_t address; uint8_t value; } Byte;
static Byte known[MAX_BYTES], written[MAX_BYTES], expected_written[MAX_BYTES];
static unsigned known_count, written_count, expected_written_count;
static bool bus_bad_read, bus_overflow;

/* ---- the simulated bus: `address` is already masked by the core (addr_mask) ---- */
static uint8_t read_byte(uint32_t address) {
    for (unsigned n = 0; n < known_count; ++n) if (known[n].address == address) return known[n].value;
    bus_bad_read = true;
    return 0;
}
static uint32_t read_bytes(uint32_t address, unsigned size) {
    uint32_t value = 0;
    for (unsigned n = 0; n < size; ++n) value |= (uint32_t)read_byte(address + n) << (8 * n);
    return value;
}
static void write_bytes(uint32_t address, uint32_t value, unsigned size) {
    for (unsigned n = 0; n < size; ++n) {
        if (written_count == MAX_BYTES) { bus_overflow = true; return; }
        written[written_count].address = address + n;
        written[written_count++].value = (uint8_t)(value >> (8 * n));
    }
}
uint8_t MDFN_FASTCALL vec_read8(int32_t *t, uint32_t a) { (void)t; return (uint8_t)read_bytes(a, 1); }
uint16_t MDFN_FASTCALL vec_read16(int32_t *t, uint32_t a) { (void)t; return (uint16_t)read_bytes(a, 2); }
uint32_t MDFN_FASTCALL vec_read24(int32_t *t, uint32_t a) { (void)t; return read_bytes(a, 3); }
uint32_t MDFN_FASTCALL vec_read32(int32_t *t, uint32_t a) { (void)t; return read_bytes(a, 4); }
void MDFN_FASTCALL vec_write8(int32_t t, uint32_t a, uint32_t v) { (void)t; write_bytes(a, v, 1); }
void MDFN_FASTCALL vec_write16(int32_t t, uint32_t a, uint32_t v) { (void)t; write_bytes(a, v, 2); }
void MDFN_FASTCALL vec_write24(int32_t t, uint32_t a, uint32_t v) { (void)t; write_bytes(a, v, 3); }
void MDFN_FASTCALL vec_write32(int32_t t, uint32_t a, uint32_t v) { (void)t; write_bytes(a, v, 4); }
bool MDFN_FASTCALL vec_event(const int32_t t) { (void)t; return false; }   /* one instruction: the run ends at its first check */
void rr_psx_fallback(uint32_t pc, uint32_t instr) { (void)pc; (void)instr; }

/* ---- the suite's binary format (its transcode_json.py) ---- */
static uint32_t get32(const uint8_t *p) { return p[0] | p[1] << 8 | p[2] << 16 | (uint32_t)p[3] << 24; }
static const uint8_t *load_state(const uint8_t *p, State *s) {
    for (int n = 0; n < 32; ++n, p += 4) s->r[n] = get32(p);
    s->hi = get32(p); s->lo = get32(p + 4); s->epc = get32(p + 8); s->tar = get32(p + 12); s->cause = get32(p + 16); s->pc = get32(p + 20);
    p += 24;
    /* The suite's own names: the first triple is the branch (target, in the delay slot, taken), then the load (register or -1, value). */
    s->branch_target = get32(p); s->branch_slot = get32(p + 4); s->branch_take = get32(p + 8);
    s->load_target = (int32_t)get32(p + 12); s->load_value = get32(p + 16);
    return p + 20;
}

static bool scratchpad(uint32_t masked) { return masked >= 0x1F800000u && masked <= 0x1F8003FFu; }

/* The bytes this vector's reads gave and its writes left. false: it touches the scratchpad, which the core does not take from the
 * bus (one vector in millions): not run. */
static bool load_bus(const uint8_t *cycles, uint32_t count) {
    known_count = written_count = expected_written_count = 0;
    bus_bad_read = bus_overflow = false;
    for (uint32_t c = 0; c < count; ++c, cycles += 24) {
        const uint32_t value = get32(cycles), action = get32(cycles + 8), raw = get32(cycles + 12), size = get32(cycles + 20);
        if (action != READ_ACTION && action != WRITE_ACTION) continue;
        const uint32_t masked = raw & addr_mask[raw >> 29];
        if (scratchpad(masked)) return false;
        for (uint32_t n = 0; n < size && n < 4; ++n) {
            const uint8_t byte = (uint8_t)(value >> (8 * n));
            if (action == READ_ACTION && known_count < MAX_BYTES) { known[known_count].address = masked + n; known[known_count++].value = byte; }
            if (action == WRITE_ACTION && expected_written_count < MAX_BYTES) {
                expected_written[expected_written_count].address = masked + n;
                expected_written[expected_written_count++].value = byte;
            }
        }
    }
    return true;
}

static uint32_t fetch_word;
static void load_machine(const State *i, uint32_t opcode) {
    memcpy(GPR, i->r, sizeof i->r);
    GPR[0] = 0;
    LO = i->lo; HI = i->hi;
    CP0.EPC = i->epc; CP0.TAR = i->tar; CP0.CAUSE = i->cause; CP0.SR = 0;
    BIU = 0; IPCache = 0; Halted = false;
    memset(ReadAbsorb, 0, sizeof ReadAbsorb);
    ReadAbsorbWhich = 0; ReadFudge = 0; LDAbsorb = 0; gte_ts_done = 0; muldiv_ts_done = 0;
    next_event_ts = 1;
    BDBT = i->branch_slot ? (i->branch_take ? 3 : 2) : 0;
    /* Uncached fetch through the core's own map: this page reads the vector's opcode. */
    fetch_word = opcode;
    ICache[(i->pc & 0xFFC) >> 2].TV = 2;
    FastMap[i->pc >> FAST_MAP_SHIFT] = (uintptr_t)&fetch_word - i->pc;
}

static unsigned compare(const State *f, uint32_t pc, uint32_t next, uint32_t ld_which, uint32_t ld_value) {
    unsigned bad = 0;
    for (int n = 1; n < 32; ++n) if (GPR[n] != f->r[n]) bad |= 1u << F_R;
    if (HI != f->hi) bad |= 1u << F_HI;
    if (LO != f->lo) bad |= 1u << F_LO;
    if (pc != f->pc) bad |= 1u << F_PC;
    /* The instruction after this one: the branch's target when it was taken, otherwise the next word. */
    if (next != (f->branch_slot && f->branch_take ? f->branch_target : f->pc + 4)) bad |= 1u << F_NEXT;
    if ((BDBT & 2) != (f->branch_slot ? 2 : 0)) bad |= 1u << F_DELAY;
    /* The core keeps a load of r0 pending, harmlessly; the model drops it. */
    const bool pending = ld_which >= 1 && ld_which <= 31, wanted = f->load_target >= 1 && f->load_target <= 31;
    if (pending != wanted || (wanted && (ld_which != (uint32_t)f->load_target || ld_value != f->load_value))) bad |= 1u << F_LOAD;
    if (CP0.EPC != f->epc) bad |= 1u << F_EPC;
    if (CP0.TAR != f->tar) bad |= 1u << F_TAR;
    if (CP0.CAUSE != f->cause) bad |= 1u << F_CAUSE;
    if (bus_bad_read) bad |= 1u << F_READ;
    if (bus_overflow || written_count != expected_written_count) bad |= 1u << F_WRITE;
    else for (unsigned n = 0; n < written_count; ++n) {
        bool found = false;
        for (unsigned k = 0; k < expected_written_count && !found; ++k)
            found = expected_written[k].address == written[n].address && expected_written[k].value == written[n].value;
        if (!found) bad |= 1u << F_WRITE;
    }
    return bad;
}

static unsigned run_interpreter(const State *i, const State *f, uint32_t opcode) {
    load_machine(i, opcode);
    BACKED_PC = i->pc;
    BACKED_new_PC = i->branch_slot && i->branch_take ? i->branch_target : i->pc + 4;
    BACKED_LDWhich = i->load_target >= 0 && i->load_target <= 31 ? (uint32_t)i->load_target : 0x22;
    BACKED_LDValue = i->load_value;
    CPU_RunReal(&s_cpu, 0);
    return compare(f, BACKED_PC, BACKED_new_PC, BACKED_LDWhich, BACKED_LDValue);
}

static unsigned run_step(RrPsxStep step, const State *i, const State *f, uint32_t opcode) {
    load_machine(i, opcode);
    RrPsxRegs regs;
    regs.timestamp = 0;
    regs.PC = i->pc;
    regs.new_PC = i->branch_slot && i->branch_take ? i->branch_target : i->pc + 4;
    regs.LDWhich = i->load_target >= 0 && i->load_target <= 31 ? (uint32_t)i->load_target : 0x22;
    regs.LDValue = i->load_value;
    regs.instr = opcode;
    if (step(&regs) != 0) return 1u << F_PC;      /* the guard refused its own word */
    return compare(f, regs.PC, regs.new_PC, regs.LDWhich, regs.LDValue);
}

/* ---- the steps: rr_psx_ram_steps[address / 4], (word, address) in STEPS_FILE, sorted by word ---- */
typedef struct { uint32_t word; RrPsxStep step; } StepEntry;
static StepEntry *steps;
static size_t step_count;
static int by_word(const void *a, const void *b) {
    const uint32_t x = ((const StepEntry *)a)->word, y = ((const StepEntry *)b)->word;
    return x < y ? -1 : x > y;
}
static RrPsxStep step_of(uint32_t word) {
    const StepEntry key = {word, NULL};
    const StepEntry *found = (const StepEntry *)bsearch(&key, steps, step_count, sizeof *steps, by_word);
    return found ? found->step : NULL;
}
static bool load_steps(const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return false;
    size_t capacity = 1 << 17;
    steps = (StepEntry *)malloc(capacity * sizeof *steps);
    uint32_t word, address;
    while (steps && step_count < capacity && fscanf(f, "%x %x", &word, &address) == 2) {
        steps[step_count].word = word;
        steps[step_count++].step = rr_psx_ram_steps[address >> 2];
    }
    fclose(f);
    qsort(steps, step_count, sizeof *steps, by_word);
    /* The interpreter's own hook must find nothing: each path runs alone. */
    memset(rr_psx_ram_steps, 0, sizeof rr_psx_ram_steps);
    return steps != NULL;
}

static uint8_t *read_file(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    *size = (size_t)ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *data = (uint8_t *)malloc(*size + 1);
    if (data && fread(data, 1, *size, f) != *size) { free(data); data = NULL; }
    fclose(f);
    return data;
}

static void print_failure(const char *file, const char *path, const char *name, uint32_t opcode, unsigned bad, const State *i, const State *f) {
    printf("{\"failure\":\"%s\",\"path\":\"%s\",\"name\":\"%s\",\"opcode\":\"%08x\",\"pc\":\"%08x\",\"fields\":[", file, path, name, opcode, i->pc);
    for (int n = 0, first = 1; n < FIELDS; ++n) if (bad >> n & 1) { printf("%s\"%s\"", first ? "" : ",", FIELD_NAMES[n]); first = 0; }
    printf("],\"final_pc\":\"%08x\",\"got_pc\":\"%08x\",\"got_new_pc\":\"%08x\",\"want_cause\":\"%08x\",\"got_cause\":\"%08x\"}\n", f->pc, BACKED_PC, BACKED_new_PC, f->cause, CP0.CAUSE);
}

typedef struct { uint64_t total, passed, skipped, field[FIELDS]; unsigned shown; } Tally;
static void print_tally(const char *file, const char *path, const Tally *t) {
    printf("{\"file\":\"%s\",\"path\":\"%s\",\"total\":%llu,\"passed\":%llu,\"skipped\":%llu,\"fields\":{", file, path,
           (unsigned long long)t->total, (unsigned long long)t->passed, (unsigned long long)t->skipped);
    for (int n = 0; n < FIELDS; ++n) printf("%s\"%s\":%llu", n ? "," : "", FIELD_NAMES[n], (unsigned long long)t->field[n]);
    printf("}}\n");
}
static void count(Tally *t, unsigned bad) {
    t->total++;
    if (!bad) t->passed++;
    for (int n = 0; n < FIELDS; ++n) if (bad >> n & 1) t->field[n]++;
}

static bool run_file(const char *folder, const char *file) {
    char path[4096];
    snprintf(path, sizeof path, "%s/%s.json.bin", folder, file);
    size_t size = 0;
    uint8_t *data = read_file(path, &size);
    if (!data) return false;
    const uint8_t *p = data + 4;
    const uint32_t tests = get32(data);
    Tally interp, native;
    memset(&interp, 0, sizeof interp);
    memset(&native, 0, sizeof native);
    for (uint32_t n = 0; n < tests; ++n) {
        char name[52];
        const unsigned length = p[0] < 50 ? p[0] : 50;
        memcpy(name, p + 1, length);
        name[length] = 0;
        p += 51;
        const uint32_t opcode = get32(p);
        p += 8;
        State i, f;
        p = load_state(p, &i);
        p = load_state(p, &f);
        const uint32_t cycles = get32(p);
        p += 4;
        const uint8_t *cycle_data = p;
        p += (size_t)cycles * 24;
        if (!load_bus(cycle_data, cycles)) { interp.skipped++; native.skipped++; continue; }
        unsigned bad = run_interpreter(&i, &f, opcode);
        count(&interp, bad);
        if (bad && interp.shown < FAILURES_SHOWN) { interp.shown++; print_failure(file, "interpreter", name, opcode, bad, &i, &f); }
        const RrPsxStep step = step_of(opcode);
        if (step) {
            load_bus(cycle_data, cycles);
            bad = run_step(step, &i, &f, opcode);
            count(&native, bad);
            if (bad && native.shown < FAILURES_SHOWN) { native.shown++; print_failure(file, "native", name, opcode, bad, &i, &f); }
        }
    }
    print_tally(file, "interpreter", &interp);
    print_tally(file, "native", &native);
    free(data);
    return true;
}

/* 1150 records of 64 inputs, the command (0xFFFFFFFF: none, a test of the registers alone), 64 outputs (little-endian u32). */
static bool run_gte(const char *path) {
    size_t size = 0;
    uint8_t *data = read_file(path, &size);
    if (!data) return false;
    enum { RECORD = (64 + 1 + 64) * 4 };
    unsigned total = 0, passed = 0, shown = 0;
    uint64_t registers[64];
    memset(registers, 0, sizeof registers);
    for (size_t at = 0; at + RECORD <= size; at += RECORD, ++total) {
        const uint8_t *r = data + at;
        for (unsigned n = 0; n < 32; ++n) GTE_WriteDR(n, 0);
        for (unsigned n = 0; n < 32; ++n) GTE_WriteCR(n, 0);
        for (unsigned n = 0; n < 32; ++n) GTE_WriteDR(n, get32(r + n * 4));
        for (unsigned n = 0; n < 32; ++n) GTE_WriteCR(n, get32(r + (32 + n) * 4));
        const uint32_t opcode = get32(r + 64 * 4);
        if (opcode != 0xFFFFFFFFu) GTE_Instruction(opcode);
        bool same = true;
        for (unsigned n = 0; n < 64; ++n) {
            const uint32_t got = n < 32 ? GTE_ReadDR(n) : GTE_ReadCR(n - 32), want = get32(r + (65 + n) * 4);
            if (got != want) {
                same = false;
                registers[n]++;
                if (shown < 12) { shown++; printf("{\"gte_failure\":%u,\"opcode\":\"%08x\",\"register\":%u,\"got\":\"%08x\",\"want\":\"%08x\"}\n", total, opcode, n, got, want); }
            }
        }
        passed += same;
    }
    printf("{\"gte\":{\"total\":%u,\"passed\":%u,\"registers\":{", total, passed);
    for (unsigned n = 0, first = 1; n < 64; ++n) if (registers[n]) { printf("%s\"%u\":%llu", first ? "" : ",", n, (unsigned long long)registers[n]); first = 0; }
    printf("}}}\n");
    free(data);
    return true;
}

int main(int argc, char **argv) {
    if (argc != 5) { fprintf(stderr, "usage: psx_vectors R3000_FOLDER FILES_LIST GTE_FILE STEPS_FILE\n"); return 2; }
    CPU_New();
    GTE_Power();
    if (!load_steps(argv[4])) { fprintf(stderr, "cannot read %s\n", argv[4]); return 3; }
    FILE *list = fopen(argv[2], "r");
    if (!list) { fprintf(stderr, "cannot read %s\n", argv[2]); return 3; }
    char file[128];
    int ok = 1;
    while (fscanf(list, "%127s", file) == 1) {
        if (!run_file(argv[1], file)) { fprintf(stderr, "cannot read vectors of %s\n", file); ok = 0; }
        fflush(stdout);
    }
    fclose(list);
    if (!run_gte(argv[3])) { fprintf(stderr, "cannot read %s\n", argv[3]); ok = 0; }
    return ok ? 0 : 3;
}
