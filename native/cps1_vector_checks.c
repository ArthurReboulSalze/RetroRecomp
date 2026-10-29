/* Independent MC68000 vectors replayed through the CPS-1 generator path.
 *
 * The vectors are SingleStepTests/m68000 data (MIT, generated with MAME, not recorded from hardware); the
 * code under test is the project's own: the CPS-1 translated steps (retrorecomp/cps1_codegen.py), run by
 * rr_cps1_native_run inside the patched Musashi loop exactly as in a CPS-1 game, and the same Musashi with
 * every instruction interpreted. The bus is flat (24 bits, no board), so CPU behaviour is isolated from the
 * CPS-1 memory map. Each vector is run on both paths and compared with the vector's final state; a path is
 * "state ok" when registers, SR, PC and every byte written agree, and "clock ok" when the clocks returned by
 * m68k_execute equal the vector's. The two paths are also compared with each other. Nothing is hidden: the
 * counts are printed per instruction group, and a difference with the vectors is reported, not excused. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "m68k.h"
#include "cps1_native.h"

typedef struct { uint32_t address; uint8_t value; } BytePair;
typedef struct {
    const char *name;
    uint32_t initial[19], final[19];
    const BytePair *before; unsigned before_count;
    const BytePair *after; unsigned after_count;
    unsigned cycles, sr_mask, authored;
} CorpusCase;
#include "vector_fixture.h"

/* ---------------------------------------------------------------- flat bus */
#define BUS_BYTES 0x1000000u
#define DIRTY_MAX 4096u
static uint8_t bus[BUS_BYTES];
static uint32_t dirty[DIRTY_MAX];
static unsigned dirty_count;
extern uint64_t rr_cps1_native_instructions;
static uint64_t interpreted;

static void touch(uint32_t a) { if (dirty_count >= DIRTY_MAX) { fprintf(stderr, "dirty list full\n"); exit(2); } dirty[dirty_count++] = a; }
static void clear_bus(void) { for (unsigned i = 0; i < dirty_count; ++i) bus[dirty[i]] = 0; dirty_count = 0; }
static void poke(uint32_t a, uint8_t v) { a &= 0xffffffu; touch(a); bus[a] = v; }

unsigned m68k_read_memory_8(unsigned a) { return bus[a & 0xffffffu]; }
unsigned m68k_read_memory_16(unsigned a) { a &= 0xffffffu; return (unsigned)bus[a] << 8 | bus[(a + 1) & 0xffffffu]; }
unsigned m68k_read_memory_32(unsigned a) { return m68k_read_memory_16(a) << 16 | m68k_read_memory_16(a + 2); }
void m68k_write_memory_8(unsigned a, unsigned v) { poke(a, (uint8_t)v); }
void m68k_write_memory_16(unsigned a, unsigned v) { poke(a, (uint8_t)(v >> 8)); poke(a + 1, (uint8_t)v); }
void m68k_write_memory_32(unsigned a, unsigned v) { m68k_write_memory_16(a, v >> 16); m68k_write_memory_16(a + 2, v & 0xffffu); }
unsigned m68k_read_disassembler_8(unsigned a) { return m68k_read_memory_8(a); }
unsigned m68k_read_disassembler_16(unsigned a) { return m68k_read_memory_16(a); }
unsigned m68k_read_disassembler_32(unsigned a) { return m68k_read_memory_32(a); }
int cps1_m68k_entry;
int cps1_m68k_int_ack(int level) { (void)level; return M68K_INT_ACK_AUTOVECTOR; }
void rr_cps1_note_instruction(uint32_t pc, int native) { (void)pc; (void)native; ++interpreted; }

/* The code view: the program ROM is the generated image, read live from the flat bus (as the board reads its
 * ROM), so the steps' complete word guard sees exactly the vector's code. */
const uint8_t *rr_cps1_code_bytes(uint32_t address, uint32_t *region, uint32_t *offset, unsigned *available) {
    address &= 0xffffffu;
    if ((address & 1u) || address + 2u > VECTOR_PROGRAM_BYTES) return NULL;
    *region = RR_CPS1_CODE_ROM; *offset = address; *available = VECTOR_PROGRAM_BYTES - address;
    return bus + address;
}
int rr_cps1_code_word(uint32_t pc, uint16_t *word) {
    pc &= 0xffffffu;
    if ((pc & 1u) || pc + 2u > VECTOR_PROGRAM_BYTES) return 0;
    *word = (uint16_t)(bus[pc] << 8 | bus[pc + 1]);
    return 1;
}

/* ---------------------------------------------------------------- one vector */
typedef struct { uint32_t reg[19]; int clocks; unsigned native; int ram_ok; } Outcome;

static void run_vector(const CorpusCase *t, int reference, Outcome *out) {
    clear_bus();
    m68k_pulse_reset();
    m68k_execute(1);   /* a reset charges its own clocks first: spend them, no instruction runs */
    for (unsigned i = 0; i < t->before_count; ++i) poke(t->before[i].address, t->before[i].value);
    m68k_set_reg(M68K_REG_SR, t->initial[17]);
    for (unsigned i = 0; i < 8; ++i) m68k_set_reg((m68k_register_t)(M68K_REG_D0 + i), t->initial[i]);
    for (unsigned i = 0; i < 7; ++i) m68k_set_reg((m68k_register_t)(M68K_REG_A0 + i), t->initial[8 + i]);
    m68k_set_reg(M68K_REG_USP, t->initial[15]);
    m68k_set_reg(M68K_REG_ISP, t->initial[16]);
    m68k_set_reg(M68K_REG_PC, t->initial[18]);
    rr_cps1_force_reference = reference;
    const uint64_t native_before = rr_cps1_native_instructions;
    out->clocks = m68k_execute(1);
    out->native = (unsigned)(rr_cps1_native_instructions - native_before);
    for (unsigned i = 0; i < 8; ++i) out->reg[i] = m68k_get_reg(NULL, (m68k_register_t)(M68K_REG_D0 + i));
    for (unsigned i = 0; i < 7; ++i) out->reg[8 + i] = m68k_get_reg(NULL, (m68k_register_t)(M68K_REG_A0 + i));
    out->reg[15] = m68k_get_reg(NULL, M68K_REG_USP);
    out->reg[16] = m68k_get_reg(NULL, M68K_REG_ISP);
    out->reg[17] = m68k_get_reg(NULL, M68K_REG_SR);
    out->reg[18] = m68k_get_reg(NULL, M68K_REG_PC) & 0xffffffu;
}

/* Every byte the instruction left different from its start must be listed in the vector's final RAM (a byte
 * listed there is compared, a byte not listed must equal its initial value, zero when absent). */
static int ram_matches(const CorpusCase *t) {
    for (unsigned i = 0; i < t->after_count; ++i)
        if (bus[t->after[i].address & 0xffffffu] != t->after[i].value) return 0;
    for (unsigned i = 0; i < dirty_count; ++i) {
        const uint32_t a = dirty[i];
        int known = 0;
        for (unsigned k = 0; k < t->after_count && !known; ++k) known = (t->after[k].address & 0xffffffu) == a;
        if (known) continue;
        uint8_t initial = 0;
        for (unsigned k = 0; k < t->before_count; ++k) if ((t->before[k].address & 0xffffffu) == a) initial = t->before[k].value;
        if (bus[a] != initial) return 0;
    }
    return 1;
}

static int state_matches(const CorpusCase *t, const Outcome *o, int *first_bad) {
    for (unsigned i = 0; i < 19; ++i) {
        const uint32_t mask = i == 17 ? t->sr_mask : 0xffffffffu;
        if ((o->reg[i] & mask) != (t->final[i] & mask)) { *first_bad = (int)i; return 0; }
    }
    *first_bad = -1;
    return 1;
}

/* ---------------------------------------------------------------- groups */
typedef struct {
    char name[64];
    unsigned cases, native_executed, native_state, reference_state, native_clock, reference_clock, paths_equal, paths_clock_equal;
    unsigned shown[3];
} Group;
static Group groups[512];
static unsigned group_count;
static unsigned example_count;
static char examples[160][240];

static Group *group_of(const CorpusCase *t) {
    char name[64];
    const char *colon = strchr(t->name, ':');
    size_t length = colon ? (size_t)(colon - t->name) : strlen(t->name);
    if (length > 48) length = 48;
    snprintf(name, sizeof name, "%s%.*s", t->authored ? "authored " : "", (int)length, t->name);
    for (unsigned i = 0; i < group_count; ++i) if (!strcmp(groups[i].name, name)) return &groups[i];
    if (group_count >= sizeof groups / sizeof *groups) { fprintf(stderr, "too many groups\n"); exit(2); }
    snprintf(groups[group_count].name, sizeof groups[group_count].name, "%s", name);
    return &groups[group_count++];
}

/* At most two examples per group and kind (0 native, 1 reference, 2 paths differ). */
static void example(Group *g, unsigned kind, const CorpusCase *t, const char *path, const char *what, int field, uint32_t expected,
                    uint32_t got) {
    if (example_count >= sizeof examples / sizeof *examples || g->shown[kind] >= 2) return;
    ++g->shown[kind];
    snprintf(examples[example_count++], sizeof examples[0], "%s | %s | %s | field %d | expected %08x | got %08x",
             t->name, path, what, field, expected, got);
    for (char *c = examples[example_count - 1]; *c; ++c) if (*c == '"' || *c == '\\') *c = '\'';
}

int main(void) {
    m68k_init();
    m68k_set_cpu_type(M68K_CPU_TYPE_68000);
    const unsigned count = sizeof corpus_cases / sizeof *corpus_cases;
    for (unsigned n = 0; n < count; ++n) {
        const CorpusCase *t = &corpus_cases[n];
        Outcome native, reference;
        int bad_native, bad_reference;
        run_vector(t, 0, &native);
        const int native_ram = ram_matches(t);
        uint8_t native_bytes[DIRTY_MAX]; uint32_t native_addresses[DIRTY_MAX]; const unsigned native_dirty = dirty_count;
        for (unsigned i = 0; i < native_dirty; ++i) { native_addresses[i] = dirty[i]; native_bytes[i] = bus[dirty[i]]; }
        run_vector(t, 1, &reference);
        const int reference_ram = ram_matches(t);
        int same_bus = native_dirty == dirty_count;
        for (unsigned i = 0; i < native_dirty && same_bus; ++i) same_bus = bus[native_addresses[i]] == native_bytes[i];
        Group *g = group_of(t);
        ++g->cases;
        g->native_executed += native.native == 1;
        const int native_state = state_matches(t, &native, &bad_native) && native_ram;
        const int reference_state = state_matches(t, &reference, &bad_reference) && reference_ram;
        g->native_state += native_state;
        g->reference_state += reference_state;
        g->native_clock += (unsigned)native.clocks == t->cycles;
        g->reference_clock += (unsigned)reference.clocks == t->cycles;
        const int equal = !memcmp(native.reg, reference.reg, sizeof native.reg) && same_bus;
        g->paths_equal += equal;
        g->paths_clock_equal += native.clocks == reference.clocks;
        if (!native_state) example(g, 0, t, "native", bad_native >= 0 ? "register" : "memory", bad_native,
                                   bad_native >= 0 ? t->final[bad_native] : 0, bad_native >= 0 ? native.reg[bad_native] : 0);
        if (!reference_state) example(g, 1, t, "reference", bad_reference >= 0 ? "register" : "memory", bad_reference,
                                      bad_reference >= 0 ? t->final[bad_reference] : 0,
                                      bad_reference >= 0 ? reference.reg[bad_reference] : 0);
        if (!equal) example(g, 2, t, "native-vs-reference", "paths differ", -1, 0, 0);
    }
    unsigned total_native_state = 0, total_reference_state = 0, total_executed = 0, total_equal = 0, total_native_clock = 0,
             total_reference_clock = 0, total_clock_equal = 0;
    printf("{\"cases\":%u,\"program_bytes\":%u,\"groups\":[", count, (unsigned)VECTOR_PROGRAM_BYTES);
    for (unsigned i = 0; i < group_count; ++i) {
        const Group *g = &groups[i];
        total_native_state += g->native_state; total_reference_state += g->reference_state; total_executed += g->native_executed;
        total_equal += g->paths_equal; total_native_clock += g->native_clock; total_reference_clock += g->reference_clock;
        total_clock_equal += g->paths_clock_equal;
        printf("%s{\"group\":\"%s\",\"cases\":%u,\"native_executed\":%u,\"native_state\":%u,\"reference_state\":%u,"
               "\"native_clock\":%u,\"reference_clock\":%u,\"paths_equal\":%u,\"paths_clock_equal\":%u}",
               i ? "," : "", g->name, g->cases, g->native_executed, g->native_state, g->reference_state, g->native_clock,
               g->reference_clock, g->paths_equal, g->paths_clock_equal);
    }
    printf("],\"totals\":{\"native_executed\":%u,\"native_state\":%u,\"reference_state\":%u,\"native_clock\":%u,"
           "\"reference_clock\":%u,\"paths_equal\":%u,\"paths_clock_equal\":%u},\"examples\":[",
           total_executed, total_native_state, total_reference_state, total_native_clock, total_reference_clock, total_equal,
           total_clock_equal);
    for (unsigned i = 0; i < example_count; ++i) printf("%s\"%s\"", i ? "," : "", examples[i]);
    printf("]}\n");
    return 0;
}
