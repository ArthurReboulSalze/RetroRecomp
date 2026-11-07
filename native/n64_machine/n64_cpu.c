/* Retro-Recomp Nintendo 64: the VR4300 side of the conversion, hooked into the core's pure interpreter (retrorecomp/n64_core.py
 * splits it and calls the functions below from its run loop). Original Retro-Recomp code, MIT; it is linked with Mupen64Plus
 * (GPL-2.0-or-later), so a program built with it is distributed under the GPL (licenses/mupen64plus-next.md).
 *
 * Mode 1, observation: at every leader (a PC reached by anything but a straight step: a jump target, a branch not taken, an
 * exception vector) the live words of the straight run that starts there, up to and including its first control-flow
 * instruction and that instruction's delay slot, are kept once per (address, code identity) with their count. Several variants
 * of one address are kept (overlays load different code at one place).
 *
 * Mode 2, native blocks: the generated blocks (retrorecomp/n64_native.py) call the core's own instruction functions with
 * constant opcodes. Dispatch is one table read for a KSEG0 address; a block runs only when its words (delay slot included) are
 * the live ones, else the interpreter runs the instruction (a guard miss, counted). Blocks chain without going back to the loop.
 *
 * Mode 0 runs nothing here: a game without blocks runs the core's cached interpreter (Fable review, condition 4), which counts
 * its instructions in rr_n64_interpreted too. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "device/r4300/r4300_core.h"
#include "device/r4300/cp0.h"
#include "device/device.h"
#include "main/main.h"
#include "n64_cpu.h"

int rr_n64_cpu_mode;
uint64_t rr_n64_interpreted, rr_n64_native, rr_n64_block_entries, rr_n64_guard_misses;

static struct r4300_core *cpu;

#ifndef RR_N64_NATIVE
/* A build without native blocks: an empty table (mode 2 is then refused by the session). */
const RrN64Block rr_n64_blocks[1] = {{0, 0, 0, 0}};
const uint32_t rr_n64_block_count = 0;
#endif

/* ---- observation ---- */
#define OBS_SLOTS (1u << 20)
#define RUN_MAX 128
typedef struct { uint32_t pc, len; uint64_t hash, count; uint32_t words; } Observed;
static Observed *observed;
static uint32_t *words, words_used, words_cap, observed_used;
static uint32_t last_pc;
static int observe_overflow;

int rr_n64_is_flow(uint32_t op)
{
    uint32_t major = op >> 26, funct = op & 0x3F, rs = (op >> 21) & 0x1F;
    if (major == 0) return funct == 8 || funct == 9 || funct == 12 || funct == 13 || funct == 15 || (funct >= 48 && funct <= 54);
    if (major == 1 || major == 2 || major == 3 || (major >= 4 && major <= 7) || (major >= 20 && major <= 23)) return 1;
    if (major == 16 || major == 47) return 1;   /* COP0 (ERET, TLB, MTC0 of Status may raise an interrupt), CACHE */
    return major == 17 && rs == 8;               /* BC1x */
}

int rr_n64_has_delay(uint32_t op)
{
    uint32_t major = op >> 26, funct = op & 0x3F, rs = (op >> 21) & 0x1F, rt = (op >> 16) & 0x1F;
    if (major == 0) return funct == 8 || funct == 9;
    if (major == 1) return rt <= 3 || (rt >= 16 && rt <= 19);
    if (major == 2 || major == 3 || (major >= 4 && major <= 7) || (major >= 20 && major <= 23)) return 1;
    return major == 17 && rs == 8;
}

static void observe_leader(uint32_t pc)
{
    const uint32_t *w = fast_mem_access(cpu, pc);
    uint32_t len = 0, slot, i;
    uint64_t hash = 1469598103934665603ull;
    if (!w || observe_overflow) return;
    while (len < RUN_MAX) {
        uint32_t op = w[len++];
        if (rr_n64_is_flow(op)) { if (rr_n64_has_delay(op)) len++; break; }
    }
    for (i = 0; i < len; i++) { hash ^= w[i]; hash *= 1099511628211ull; }
    slot = (uint32_t)((hash ^ (pc * 2654435761u)) >> 7);
    for (;;) {
        Observed *o;
        slot &= OBS_SLOTS - 1;
        o = &observed[slot];
        if (o->count && o->pc == pc && o->hash == hash && o->len == len) { o->count++; return; }
        if (!o->count) {
            if (observed_used >= OBS_SLOTS / 2) { observe_overflow = 1; return; }   /* the table stays fast; reported */
            if (words_used + len > words_cap) {
                uint32_t cap = words_cap ? words_cap * 2 : (1u << 20);
                uint32_t *grown = realloc(words, (size_t)cap * 4);
                if (!grown) { observe_overflow = 1; return; }
                words = grown; words_cap = cap;
            }
            memcpy(words + words_used, w, len * 4);
            o->pc = pc; o->len = len; o->hash = hash; o->count = 1; o->words = words_used;
            words_used += len; observed_used++;
            return;
        }
        slot++;
    }
}

void rr_n64_observe(uint32_t pc)
{
    if (pc != last_pc + 4) observe_leader(pc);
    last_pc = pc;
}

int rr_n64_set_observe(int enabled)
{
    if (enabled && !observed) observed = calloc(OBS_SLOTS, sizeof *observed);
    if (enabled && !observed) return 0;
    return 1;
}

size_t rr_n64_observation_count(void) { return observed_used; }
int rr_n64_observation_overflow(void) { return observe_overflow; }

/* One line per (address, code identity): "pc count len word..." (len counts the delay slot's word). */
int rr_n64_write_observations(FILE *out)
{
    uint32_t i, k;
    if (!observed || !out) return 0;
    for (i = 0; i < OBS_SLOTS; i++) {
        const Observed *o = &observed[i];
        if (!o->count) continue;
        fprintf(out, "%08x %llu %u", o->pc, (unsigned long long)o->count, o->len);
        for (k = 0; k < o->len; k++) fprintf(out, " %08x", words[o->words + k]);
        fputc('\n', out);
    }
    return !ferror(out);
}

/* ---- native blocks ---- */
static uint32_t *table;   /* (pc & 0x7FFFFF) >> 2 -> 1 + the first variant of that address, KSEG0 only */

void rr_n64_cpu_start(struct r4300_core *r4300)
{
    cpu = r4300;
    last_pc = 0;
    if (rr_n64_cpu_mode == 2 && !table && rr_n64_block_count) {
        /* The generator lists the variants of one address together, the most run first. */
        uint32_t i;
        table = calloc(0x800000 / 4, sizeof *table);
        if (!table) { rr_n64_cpu_mode = 0; return; }
        for (i = rr_n64_block_count; i-- > 0;)
            if ((rr_n64_blocks[i].pc & 0xFF800000u) == 0x80000000u) table[(rr_n64_blocks[i].pc & 0x7FFFFFu) >> 2] = i + 1;
    }
    if (rr_n64_cpu_mode == 2 && !table) rr_n64_cpu_mode = 0;
}

int rr_n64_run_blocks(struct r4300_core *r4300)
{
    int ran = 0;
    uint32_t pc = *r4300_pc(r4300), first;
    while ((pc & 0xFF800000u) == 0x80000000u && (first = table[(pc & 0x7FFFFFu) >> 2]) != 0) {
        const uint32_t *live = fast_mem_access(r4300, pc);
        const RrN64Block *block = 0;
        uint32_t k;
        if (live)
            for (k = first - 1; k < rr_n64_block_count && rr_n64_blocks[k].pc == pc; k++)
                if (memcmp(live, rr_n64_blocks[k].words, rr_n64_blocks[k].len * 4) == 0) { block = &rr_n64_blocks[k]; break; }
        if (!block) { rr_n64_guard_misses++; break; }
        rr_n64_native += (uint64_t)block->run(r4300, live);
        rr_n64_block_entries++;
        ran = 1;
        if (*r4300_stop(r4300)) break;
        pc = *r4300_pc(r4300);
    }
    return ran;
}

/* ---- evidence ---- */
uint64_t rr_n64_cpu_state_hash(void)
{
    uint64_t h = 1469598103934665603ull, pair[2];
    const unsigned char *q;
    uint32_t pc;
    unsigned i;
#define FOLD(pointer, bytes) do { q = (const unsigned char *)(pointer); for (i = 0; i < (bytes); i++) { h ^= q[i]; h *= 1099511628211ull; } } while (0)
    if (!cpu) cpu = &g_dev.r4300;   /* the cached interpreter never calls rr_n64_cpu_start */
    FOLD(r4300_regs(cpu), 32 * 8);
    pair[0] = (uint64_t)*r4300_mult_hi(cpu); pair[1] = (uint64_t)*r4300_mult_lo(cpu);
    FOLD(pair, 16);
    pc = rr_n64_cpu_pc();
    FOLD(&pc, 4);
    FOLD(r4300_cp0_regs(&cpu->cp0), 32 * 4);
#undef FOLD
    return h;
}

/* The PC; 0 before the machine has started (the core sets its PC pointer when its CPU loop begins). */
uint32_t rr_n64_cpu_pc(void)
{
    struct r4300_core *r4300 = cpu ? cpu : &g_dev.r4300;
    return *r4300_pc_struct(r4300) ? *r4300_pc(r4300) : 0;
}
