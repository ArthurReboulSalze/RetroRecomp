/* 65816: single-instruction vectors of an independent corpus (SingleStepTests/65816) against the converter's 65816 core.
 *
 * The cases are read from the file named on the command line (written by tools/snes_cpu_vector_selftest.py from the cached
 * corpus; nothing of it is in the repository). Each case gives the registers and the touched RAM before one instruction, and
 * the registers, the RAM and the bus cycles after it, on a flat 16 MiB address space (no ROM, no I/O, no mirrors). The core
 * runs it as the reference does (interpreted). When the instruction sits where the game keeps RAM code (WRAM), it runs it
 * as the game does too (the compiled operation of its live opcode, counted as compiled and not observed). Each result is
 * compared with the corpus:
 *   - the registers and the touched RAM after the instruction (a difference is a semantic one);
 *   - the number of cycles (a difference is a timing one);
 *   - the order, address and value of the bus reads and writes (a difference is an ordering one). The corpus lists internal
 *     cycles; the core makes no bus access for them, so only cycles with a value are compared, and in order.
 * MVN and MVP move one byte per execution in the core and the whole block in the corpus: the core runs until the
 * instruction is left, the cycles of all the executions are added up.
 * This is independent evidence for the instruction semantics and the order of the bus accesses; it is not hardware proof.
 *
 * Output: one JSON line of counts; a line "FAIL <index> <compiled?> <class 1-3>" per case that differs; and a line
 * "MISMATCH <index> <class> <detail> <got> <want>" with the first differences (the first 60 of each class).
 */
#define main rr_snes_native_base_checks
#include "../snes_native_checks.c"
#undef main

#define MAX_RAM 4096
#define MAX_CYCLES 16384
typedef struct { int address, value, kind; } Cycle;   /* kind: 0 read, 1 write, 2 internal (no value) */
typedef struct {
    unsigned index, e, pc, s, p, a, x, y, dbr, d, pbr;
    unsigned fe, fpc, fs, fp, fa, fx, fy, fdbr, fd, fpbr;
    unsigned opcode;
    int nram, nfram, ncycles;
    int (*ram)[2];
    int (*fram)[2];
    Cycle *cycles;
} Case;

static uint8_t flat[1u << 24];
typedef struct { uint32_t address; int value; int kind; } Access;
static Access *accesses;
static unsigned access_count;
static uint32_t written[MAX_RAM * 2];
static unsigned written_count;
static uint32_t loaded[MAX_RAM];
static unsigned loaded_count;
static unsigned by_class[4], diverged;
static unsigned counts[2][5];   /* [compiled?][semantic, timing, ordering, skipped, passed] */
static void report(unsigned index, const char *klass, const char *detail, unsigned a, unsigned b) {
    unsigned which = klass[0] == 's' ? 0 : klass[0] == 't' ? 1 : klass[0] == 'o' ? 2 : 3;
    if (by_class[which]++ < 60) printf("MISMATCH %u %s %s %u %u\n", index, klass, detail, a, b);
}
static uint8_t vec_read(void *mem, uint32_t address) {
    (void)mem; address &= 0xffffffu;
    uint8_t value = flat[address];
    if (access_count < MAX_CYCLES) { accesses[access_count].address = address; accesses[access_count].value = value; accesses[access_count].kind = 0; }
    ++access_count; return value;
}
static void vec_write(void *mem, uint32_t address, uint8_t value) {
    (void)mem; address &= 0xffffffu;
    if (access_count < MAX_CYCLES) { accesses[access_count].address = address; accesses[access_count].value = value; accesses[access_count].kind = 1; }
    ++access_count;
    if (written_count < MAX_RAM * 2) written[written_count++] = address;
    flat[address] = value;
}
static uint8_t flags_of(const Interp816 *cpu) {
    return (uint8_t)((cpu->c ? 1 : 0) | (cpu->z ? 2 : 0) | (cpu->i ? 4 : 0) | (cpu->d ? 8 : 0) | (cpu->xf ? 16 : 0) |
                     (cpu->mf ? 32 : 0) | (cpu->v ? 64 : 0) | (cpu->n ? 128 : 0));
}
/* Returns 0 passed, 1 semantic, 2 timing, 3 ordering; -1 when the path asked for was not the one taken. */
static int run_case(const Case *c, bool compiled) {
    for (unsigned n = 0; n < written_count; ++n) flat[written[n]] = 0;
    for (unsigned n = 0; n < loaded_count; ++n) flat[loaded[n]] = 0;
    written_count = 0; loaded_count = 0;
    for (int n = 0; n < c->nram; ++n) { flat[c->ram[n][0]] = (uint8_t)c->ram[n][1]; loaded[loaded_count++] = (uint32_t)c->ram[n][0]; }
    Interp816 cpu = {0};
    cpu.read = vec_read; cpu.write = vec_write;
    cpu.a = (uint16_t)c->a; cpu.x = (uint16_t)c->x; cpu.y = (uint16_t)c->y; cpu.sp = (uint16_t)c->s; cpu.pc = (uint16_t)c->pc;
    cpu.dp = (uint16_t)c->d; cpu.k = (uint8_t)c->pbr; cpu.db = (uint8_t)c->dbr; cpu.e = c->e != 0;
    cpu.c = c->p & 1; cpu.z = c->p & 2; cpu.i = c->p & 4; cpu.d = c->p & 8; cpu.xf = c->p & 16; cpu.mf = c->p & 32;
    cpu.v = c->p & 64; cpu.n = c->p & 128;
    /* Emulation mode keeps the stack in page 1 and the index registers 8 bits wide: the corpus gives some cases an initial state
     * the chip cannot be in, and its result follows from that normal form. */
    if (cpu.e) { cpu.xf = cpu.mf = true; cpu.sp = (uint16_t)(0x100 | (c->s & 0xff)); cpu.x &= 0xff; cpu.y &= 0xff; }
    cpu.brkHookEnabled = false;   /* the architectural vectors, not the fallback tier's marker */
    if (compiled) {
        int32_t off = cpu_wram_offset((uint8_t)c->pbr, (uint16_t)c->pc);
        if (off >= 0) g_ram[off] = flat[((uint32_t)c->pbr << 16) | c->pc];
    }
    native_count = fallback_count = unobserved_count = 0;
    rr_snes_native_set_enabled(compiled);
    access_count = 0;
    int used = 0, steps = 0;
    const uint16_t start = (uint16_t)c->pc;
    do { used += interp816_runOpcode(&cpu); ++steps; }
    while ((c->opcode == 0x44 || c->opcode == 0x54) && cpu.pc == start && cpu.k == c->pbr && steps < 4000);
    if (compiled && (unobserved_count != (uint64_t)steps || fallback_count)) return -1;
    if (!compiled && native_count) return -1;
    int klass = 0;
    if (cpu.a != c->fa || cpu.x != c->fx || cpu.y != c->fy || cpu.sp != c->fs || cpu.pc != c->fpc || cpu.dp != c->fd ||
        cpu.k != c->fpbr || cpu.db != c->fdbr || cpu.e != (c->fe != 0)) {
        report(c->index, "semantic", "registers", cpu.a | ((unsigned)cpu.x << 16), c->fa | (c->fx << 16));
        if (cpu.sp != c->fs || cpu.pc != c->fpc) report(c->index, "semantic", "sp-pc", cpu.sp | ((unsigned)cpu.pc << 16), c->fs | (c->fpc << 16));
        if (cpu.k != c->fpbr || cpu.db != c->fdbr || cpu.dp != c->fd)
            report(c->index, "semantic", "banks-dp", cpu.k | (cpu.db << 8) | ((unsigned)cpu.dp << 16), c->fpbr | (c->fdbr << 8) | (c->fd << 16));
        klass = 1;
    }
    unsigned want_p = c->fp, got_p = flags_of(&cpu);
    if (c->fe) { want_p |= 0x30; got_p |= 0x30; }   /* emulation mode: M and X read as 1 */
    if (got_p != want_p) { report(c->index, "semantic", "flags", got_p, want_p); klass = 1; }
    for (int n = 0; n < c->nfram && !klass; ++n)
        if (flat[c->fram[n][0]] != c->fram[n][1]) {
            report(c->index, "semantic", "ram", c->fram[n][0], (flat[c->fram[n][0]] << 8) | c->fram[n][1]); klass = 1;
        }
    for (unsigned n = 0; n < written_count && !klass; ++n) {
        bool listed = false;
        for (int m = 0; m < c->nfram && !listed; ++m) listed = (uint32_t)c->fram[m][0] == written[n];
        if (!listed) { report(c->index, "semantic", "unlisted-write", written[n], 0); klass = 1; }
    }
    if (klass) return klass;
    if (used != c->ncycles) { report(c->index, "timing", "cycles", used, c->ncycles); return 2; }
    unsigned expected = 0;
    for (int n = 0; n < c->ncycles; ++n) if (c->cycles[n].value >= 0) ++expected;
    if (expected != access_count) { report(c->index, "ordering", "bus-count", access_count, expected); return 3; }
    unsigned at = 0;
    for (int n = 0; n < c->ncycles; ++n) {
        if (c->cycles[n].value < 0) continue;
        if ((int)accesses[at].address != c->cycles[n].address || accesses[at].kind != c->cycles[n].kind ||
            accesses[at].value != c->cycles[n].value) {
            report(c->index, "ordering", "bus-access", ((unsigned)accesses[at].address << 1) | accesses[at].kind,
                   ((unsigned)c->cycles[n].address << 1) | c->cycles[n].kind);
            return 3;
        }
        ++at;
    }
    return 0;
}
int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: cpu_vector_checks CASES\n"); return 2; }
    memcpy(cartridge, fixture_rom, sizeof cartridge);
    cart.type = FIXTURE_CART_TYPE; cart.rom = cartridge; cart.romSize = sizeof cartridge;
    cart.romImageSize = FIXTURE_IMAGE_BYTES;
    machine.cart = &cart;
    rr_snes_native_bind();
    FILE *file = fopen(argv[1], "r");
    if (!file) { fprintf(stderr, "cannot read %s\n", argv[1]); return 2; }
    accesses = malloc(sizeof *accesses * MAX_CYCLES);
    static Case c;
    c.ram = malloc(sizeof *c.ram * MAX_RAM); c.fram = malloc(sizeof *c.fram * MAX_RAM); c.cycles = malloc(sizeof *c.cycles * MAX_CYCLES);
    unsigned total = 0, compiled_cases = 0;
    while (1) {
        int n;
        if (fscanf(file, " %u %u %u %u %u %u %u %u %u %u %u %d", &c.index, &c.e, &c.pc, &c.s, &c.p, &c.a, &c.x, &c.y,
                   &c.dbr, &c.d, &c.pbr, &c.nram) != 12) break;
        if (c.nram > MAX_RAM) { fprintf(stderr, "case %u: too many RAM entries\n", c.index); return 2; }
        for (n = 0; n < c.nram; ++n) fscanf(file, " %d %d", &c.ram[n][0], &c.ram[n][1]);
        fscanf(file, " %u %u %u %u %u %u %u %u %u %u %d", &c.fe, &c.fpc, &c.fs, &c.fp, &c.fa, &c.fx, &c.fy, &c.fdbr, &c.fd, &c.fpbr, &c.nfram);
        if (c.nfram > MAX_RAM) { fprintf(stderr, "case %u: too many final RAM entries\n", c.index); return 2; }
        for (n = 0; n < c.nfram; ++n) fscanf(file, " %d %d", &c.fram[n][0], &c.fram[n][1]);
        fscanf(file, " %d", &c.ncycles);
        if (c.ncycles > MAX_CYCLES) { fprintf(stderr, "case %u: too many cycles\n", c.index); return 2; }
        for (n = 0; n < c.ncycles; ++n) fscanf(file, " %d %d %d", &c.cycles[n].address, &c.cycles[n].value, &c.cycles[n].kind);
        c.opcode = 0;
        for (n = 0; n < c.nram; ++n) if ((unsigned)c.ram[n][0] == (((c.pbr << 16) | c.pc) & 0xffffffu)) c.opcode = (unsigned)c.ram[n][1];
        ++total;
        int reference_class = 0;
        for (int compiled = 0; compiled < 2; ++compiled) {
            if (compiled && cpu_wram_offset((uint8_t)c.pbr, (uint16_t)c.pc) < 0) continue;
            if (compiled) ++compiled_cases;
            int klass = run_case(&c, compiled != 0);
            if (klass < 0) { report(c.index, "path", compiled ? "not-compiled" : "not-interpreted", 0, 0); klass = 1; }
            if (!compiled) reference_class = klass;
            else if (klass != reference_class) { ++diverged; printf("DIVERGE %u\n", c.index); }
            ++counts[compiled][klass == 0 ? 4 : klass - 1];
            if (klass) printf("FAIL %u %d %d\n", c.index, compiled, klass);
        }
    }
    fclose(file);
    printf("{\"cases\":%u,\"compiled_cases\":%u,\"compiled_differs_from_interpreted\":%u,", total, compiled_cases, diverged);
    for (int compiled = 0; compiled < 2; ++compiled)
        printf("\"%s\":{\"semantic\":%u,\"timing\":%u,\"ordering\":%u,\"passed\":%u}%s", compiled ? "compiled" : "interpreted",
               counts[compiled][0], counts[compiled][1], counts[compiled][2], counts[compiled][4], compiled ? "" : ",");
    printf("}\n");
    return 0;
}
