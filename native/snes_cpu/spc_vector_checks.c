/* SPC700: single-instruction vectors of an independent corpus (SingleStepTests/spc700) against the converter's SPC700 core.
 *
 * The cases are read from the file named on the command line (written by tools/snes_cpu_vector_selftest.py from the cached
 * corpus; nothing of it is in the repository). Each case gives the registers and the touched RAM before the instruction, and
 * the registers, the RAM and the bus cycles after it. The core runs it twice, as the game does (compiled operation) and as
 * the reference does (interpreted), on a flat 64 KiB RAM, and each result is compared with the corpus:
 *   - the registers and the touched RAM after the instruction (a difference is a semantic one);
 *   - the number of cycles (a difference is a timing one);
 *   - the order, address and value of the reads and writes (a difference is an ordering one; a dummy read the corpus lists
 *     without a value is checked by its address only).
 * A case that touches the I/O registers ($F0-$FF) or the boot ROM window ($FFC0-) is skipped: the corpus has no I/O there.
 * This is independent evidence for the instruction semantics and the order of the bus accesses; it is not hardware proof.
 *
 * Output: one JSON line of counts; a line "FAIL <index> <compiled?> <class 1-3>" per case that differs; and a line
 * "MISMATCH <index> <class> <detail> <got> <want>" with the first differences (the first 60 of each class).
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "snes/spc.h"
#include "snes_spc_native.h"
#include "fixture_data.h"

static Apu machine;
static struct { uint16_t address; int value; int kind; } log_entries[64];   /* kind 0 read, 1 write */
static unsigned log_count;
uint8_t apu_cpuRead(Apu *apu, uint16_t adr) {
    uint8_t value = apu->ram[adr];
    if (log_count < 64) { log_entries[log_count].address = adr; log_entries[log_count].value = value; log_entries[log_count].kind = 0; }
    ++log_count; return value;
}
void apu_cpuWrite(Apu *apu, uint16_t adr, uint8_t value) {
    if (log_count < 64) { log_entries[log_count].address = adr; log_entries[log_count].value = value; log_entries[log_count].kind = 1; }
    ++log_count; apu->ram[adr] = value;
}

typedef struct { int address, value, kind; } Cycle;   /* kind 0 read, 1 write, 2 wait (no bus) */
typedef struct {
    unsigned index, pc, a, x, y, sp, psw;
    unsigned fpc, fa, fx, fy, fsp, fpsw;
    int nram, nfram, ncycles;
    int ram[64][2], fram[64][2];
    Cycle cycles[64];
} Case;

static unsigned by_class[4];
static unsigned counts[3][5];   /* [native?][semantic, timing, ordering, skipped, passed] */
static unsigned family_failures;
static void report(unsigned index, const char *klass, const char *detail, unsigned a, unsigned b) {
    unsigned which = klass[0] == 's' ? 0 : klass[0] == 't' ? 1 : klass[0] == 'o' ? 2 : 3;
    if (by_class[which]++ < 60) printf("MISMATCH %u %s %s %u %u\n", index, klass, detail, a, b);
}
static uint8_t flags_of(const Spc *spc) {
    return (uint8_t)((spc->c ? 1 : 0) | (spc->z ? 2 : 0) | (spc->i ? 4 : 0) | (spc->h ? 8 : 0) | (spc->b ? 16 : 0) |
                     (spc->p ? 32 : 0) | (spc->v ? 64 : 0) | (spc->n ? 128 : 0));
}
static bool touches_io(const Case *c) {
    if (c->pc >= 0xf0 && c->pc <= 0xff) return true;
    for (int n = 0; n < c->nram; ++n) if ((c->ram[n][0] >= 0xf0 && c->ram[n][0] <= 0xff) || c->ram[n][0] >= 0xffc0) return true;
    for (int n = 0; n < c->ncycles; ++n)
        if (c->cycles[n].address >= 0 && ((c->cycles[n].address >= 0xf0 && c->cycles[n].address <= 0xff) || c->cycles[n].address >= 0xffc0)) return true;
    return false;
}
/* Returns 0 passed, 1 semantic, 2 timing, 3 ordering. */
static int run_case(const Case *c, bool native) {
    memset(machine.ram, 0, sizeof machine.ram);
    for (int n = 0; n < c->nram; ++n) machine.ram[c->ram[n][0]] = (uint8_t)c->ram[n][1];
    Spc spc = {0};
    spc.apu = &machine; spc.a = (uint8_t)c->a; spc.x = (uint8_t)c->x; spc.y = (uint8_t)c->y; spc.sp = (uint8_t)c->sp; spc.pc = (uint16_t)c->pc;
    spc.c = c->psw & 1; spc.z = c->psw & 2; spc.i = c->psw & 4; spc.h = c->psw & 8; spc.b = c->psw & 16; spc.p = c->psw & 32;
    spc.v = c->psw & 64; spc.n = c->psw & 128;
    rr_spc_set_mode(native, false); rr_spc_reset_evidence();
    log_count = 0;
    int used = spc_runOpcode(&spc);
    /* The core must have gone through the path asked for. */
    if (native && rr_spc_native_opcodes() != 1) { report(c->index, "path", "not-native", 0, 0); return 1; }
    if (!native && rr_spc_interpreted_opcodes() != 1) { report(c->index, "path", "not-interpreted", 0, 0); return 1; }
    int klass = 0;
    if (spc.a != c->fa || spc.x != c->fx || spc.y != c->fy || spc.sp != c->fsp || spc.pc != c->fpc || flags_of(&spc) != c->fpsw) {
        report(c->index, "semantic", "registers", spc.a | (spc.x << 8) | (spc.y << 16), c->fa | (c->fx << 8) | (c->fy << 16));
        if (spc.pc != c->fpc || flags_of(&spc) != c->fpsw) report(c->index, "semantic", "pc-or-flags", spc.pc | (flags_of(&spc) << 16), c->fpc | (c->fpsw << 16));
        klass = 1;
    }
    for (int n = 0; n < c->nfram && !klass; ++n)
        if (machine.ram[c->fram[n][0]] != c->fram[n][1]) {
            report(c->index, "semantic", "ram", c->fram[n][0], (machine.ram[c->fram[n][0]] << 8) | c->fram[n][1]); klass = 1;
        }
    if (!klass) {   /* nothing was written outside the addresses the corpus lists */
        for (unsigned n = 0; n < log_count && n < 64; ++n) {
            if (log_entries[n].kind != 1) continue;
            bool listed = false;
            for (int m = 0; m < c->nfram; ++m) listed |= c->fram[m][0] == log_entries[n].address;
            if (!listed) { report(c->index, "semantic", "unlisted-write", log_entries[n].address, 0); klass = 1; break; }
        }
    }
    if (klass) return klass;
    if (used != c->ncycles) { report(c->index, "timing", "cycles", used, c->ncycles); return 2; }
    unsigned expected = 0;
    for (int n = 0; n < c->ncycles; ++n) if (c->cycles[n].kind != 2) ++expected;
    if (expected != log_count) { report(c->index, "ordering", "bus-count", log_count, expected); return 3; }
    unsigned at = 0;
    for (int n = 0; n < c->ncycles; ++n) {
        if (c->cycles[n].kind == 2) continue;
        if (log_entries[at].address != c->cycles[n].address || log_entries[at].kind != c->cycles[n].kind ||
            (c->cycles[n].value >= 0 && log_entries[at].value != c->cycles[n].value)) {
            report(c->index, "ordering", "bus-access", (log_entries[at].address << 1) | log_entries[at].kind,
                   (c->cycles[n].address << 1) | c->cycles[n].kind);
            return 3;
        }
        ++at;
    }
    return 0;
}
int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: spc_vector_checks CASES\n"); return 2; }
    FILE *file = fopen(argv[1], "r");
    if (!file) { fprintf(stderr, "cannot read %s\n", argv[1]); return 2; }
    static Case c;
    unsigned total = 0;
    while (1) {
        int n;
        if (fscanf(file, " %u %u %u %u %u %u %u %d", &c.index, &c.pc, &c.a, &c.x, &c.y, &c.sp, &c.psw, &c.nram) != 8) break;
        for (n = 0; n < c.nram; ++n) fscanf(file, " %d %d", &c.ram[n][0], &c.ram[n][1]);
        fscanf(file, " %u %u %u %u %u %u %d", &c.fpc, &c.fa, &c.fx, &c.fy, &c.fsp, &c.fpsw, &c.nfram);
        for (n = 0; n < c.nfram; ++n) fscanf(file, " %d %d", &c.fram[n][0], &c.fram[n][1]);
        fscanf(file, " %d", &c.ncycles);
        for (n = 0; n < c.ncycles; ++n) fscanf(file, " %d %d %d", &c.cycles[n].address, &c.cycles[n].value, &c.cycles[n].kind);
        ++total;
        if (touches_io(&c)) { ++counts[0][3]; ++counts[1][3]; continue; }
        for (int native = 0; native < 2; ++native) {
            int klass = run_case(&c, native);
            ++counts[native][klass == 0 ? 4 : klass - 1];
            if (klass) printf("FAIL %u %d %d\n", c.index, native, klass);
        }
    }
    fclose(file);
    printf("{\"cases\":%u,", total);
    for (int native = 0; native < 2; ++native)
        printf("\"%s\":{\"semantic\":%u,\"timing\":%u,\"ordering\":%u,\"skipped\":%u,\"passed\":%u}%s", native ? "compiled" : "interpreted",
               counts[native][0], counts[native][1], counts[native][2], counts[native][3], counts[native][4], native ? "" : ",");
    printf("}\n");
    (void)family_failures;
    return 0;
}
