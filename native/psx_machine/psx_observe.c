/* The conversion's observation of the R3000A code a PlayStation game runs (Retro-Recomp's own code, MIT; linked only into the
 * observing build of the conversion, RR_PSX_OBSERVE, never into a published game).
 *
 * Beetle's step hook (our anchored change of cpu.c) calls rr_psx_observe after each instruction fetch of the interpreter with
 * the address and the word it fetched. Each (physical address, word) pair of main RAM or the BIOS is kept with its count and
 * whether it was ever reached other than from the instruction before it (a branch target, an exception vector, a return):
 * retrorecomp/psx_native.py starts the native steps there. The table is written as text at the end of the run. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

#define SLOTS (1u << 21)

typedef struct {
    uint32_t pc, word, count, entered;
} Entry;

static Entry *table;
static uint32_t used, previous = 0xFFFFFFFFu;
static int overflow;

void rr_psx_observe(uint32_t pc, uint32_t word) {
    const uint32_t physical = pc & 0x1FFFFFFFu;
    const uint32_t entered = physical != previous + 4;
    previous = physical;
    if (!(physical < 0x200000u || physical - 0x1FC00000u < 0x80000u)) return;
    if (!table && !(table = calloc(SLOTS, sizeof *table))) { overflow = 1; return; }
    uint32_t h = ((physical >> 2) * 2654435761u ^ word * 0x9E3779B9u) & (SLOTS - 1);
    for (;;) {
        Entry *e = &table[h];
        if (!e->count) {
            if (used >= SLOTS / 2) { overflow = 1; return; }
            e->pc = physical; e->word = word; e->count = 1; e->entered = entered;
            used++;
            return;
        }
        if (e->pc == physical && e->word == word) {
            if (e->count != UINT32_MAX) e->count++;
            e->entered |= entered;
            return;
        }
        h = (h + 1) & (SLOTS - 1);
    }
}

/* "RRPSX-OBSERVE 1", then one "address word count entered" line (hexadecimal, count decimal) per pair. 0 on a write error. */
int rr_psx_observe_write(FILE *f) {
    fprintf(f, "RRPSX-OBSERVE 1\n%s", overflow ? "overflow\n" : "");
    for (uint32_t n = 0; table && n < SLOTS; n++)
        if (table[n].count)
            fprintf(f, "%08x %08x %u %u\n", table[n].pc, table[n].word, table[n].count, table[n].entered);
    return !ferror(f);
}
