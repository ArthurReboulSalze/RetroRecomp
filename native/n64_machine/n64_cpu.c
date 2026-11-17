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
#include <time.h>

#include "backends/api/clock_backend.h"
#include "device/r4300/r4300_core.h"
#include "device/r4300/cp0.h"
#include "device/device.h"
#include "device/memory/memory.h"
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
static uint32_t last_pc, run_end;
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

/* The live words at a PC with no side effect: KSEG0 and KSEG1 directly, a TLB-mapped address through the core's lookup table of the
 * pages the TLB maps (an unmapped page gives NULL, never a TLB exception: the interpreter then takes it as the console would). */
static const uint32_t *live_words(struct r4300_core *r4300, uint32_t pc)
{
    uint32_t entry;
    if ((pc & 0xC0000000u) == 0x80000000u) return mem_base_u32(r4300->mem->base, pc & 0x1FFFFFFCu);
    entry = r4300->cp0.tlb.LUT_r[pc >> 12];
    if (!entry) return NULL;
    return mem_base_u32(r4300->mem->base, ((entry & 0xFFFFF000u) | (pc & 0xFFCu)) & 0x1FFFFFFCu);
}

/* A run of TLB-mapped code stays within its 4 KiB page: the next virtual page may map another physical one. */
static int mapped(uint32_t pc) { return (pc & 0xC0000000u) != 0x80000000u; }

static void observe_leader(uint32_t pc)
{
    const uint32_t *w = live_words(cpu, pc);
    uint32_t len = 0, slot, i, cap = RUN_MAX;
    uint64_t hash = 1469598103934665603ull;
    if (!w || observe_overflow) return;
    if (mapped(pc) && (0x1000u - (pc & 0xFFFu)) / 4 < cap) cap = (0x1000u - (pc & 0xFFFu)) / 4;
    while (len < cap) {
        uint32_t op = w[len++];
        if (rr_n64_is_flow(op)) {
            if (rr_n64_has_delay(op)) {
                if (len == cap && cap < RUN_MAX) { len--; break; }   /* the delay slot is on the next page: the jump runs interpreted */
                len++;
            }
            break;
        }
    }
    run_end = pc + 4 * len;
    if (!len) return;
    /* A run that ends on an instruction with no delay slot that does not jump (MFC0, CACHE), at RUN_MAX or at a page's end goes on in a
     * straight line: the instruction after it starts a run of its own (else it never becomes a block: SM64's wait on the Count register). */
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
    if (pc != last_pc + 4 || pc == run_end) observe_leader(pc);
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

/* A block of TLB-mapped code: the first variant of its address by a binary search of the table, which the generator sorts by address. */
static uint32_t first_variant(uint32_t pc)
{
    uint32_t lo = 0, hi = rr_n64_block_count;
    while (lo < hi) { uint32_t mid = (lo + hi) / 2; if (rr_n64_blocks[mid].pc < pc) lo = mid + 1; else hi = mid; }
    return lo < rr_n64_block_count && rr_n64_blocks[lo].pc == pc ? lo + 1 : 0;
}

void rr_n64_cpu_start(struct r4300_core *r4300)
{
    cpu = r4300;
    last_pc = 0;
    run_end = 0;
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

/* ---- where the interpreter ran (gate G3), only when asked (--interpreted-sites): one entry per (pc, word, reason) with its
 * count. The reason is the one that started the interpreted stretch the instruction belongs to (a stretch ends when a block runs):
 * the PC outside KSEG0, no block at a KSEG0 address, or a guard miss. */
#define SITE_SLOTS (1u << 21)
typedef struct { uint32_t pc, word, reason, start; uint64_t count; } Site;
static Site *sites;
static uint32_t sites_used;
static uint64_t sites_unlisted;
static uint32_t stretch_reason, stretch_start;   /* 0: a block ran last (the next interpreted instruction starts a stretch) */

int rr_n64_set_sites(int enabled)
{
    if (enabled && !sites) sites = calloc(SITE_SLOTS, sizeof *sites);
    return !enabled || sites != 0;
}

static void note_site(struct r4300_core *r4300, uint32_t pc, uint32_t reason)
{
    const uint32_t *w;
    uint32_t word, slot;
    /* A guard miss always starts a stretch of its own, even inside one: else it took the class of the stretch it fell in. */
    if (!stretch_reason || reason == 3) { stretch_reason = reason; stretch_start = pc; }
    if (!sites) return;
    w = live_words(r4300, pc);
    word = w ? *w : 0;
    slot = (pc * 2654435761u) ^ (word * 40503u) ^ (stretch_start * 97u) ^ stretch_reason;
    for (;;) {
        Site *s;
        slot &= SITE_SLOTS - 1;
        s = &sites[slot];
        if (s->count && s->pc == pc && s->word == word && s->reason == stretch_reason && s->start == stretch_start) { s->count++; return; }
        if (!s->count) {
            if (sites_used >= SITE_SLOTS / 2) { sites_unlisted++; return; }
            s->pc = pc; s->word = word; s->reason = stretch_reason; s->start = stretch_start; s->count = 1; sites_used++;
            return;
        }
        slot++;
    }
}

size_t rr_n64_site_distinct(void) { return sites_used; }
uint64_t rr_n64_site_unlisted(void) { return sites_unlisted; }
static const char *const reason_names[] = {"", "outside_kseg0", "no_block", "guard_miss"};
/* JSON rows [pc, word, reason, stretch start, count], comma-separated, no brackets. */
int rr_n64_write_sites(FILE *out)
{
    uint32_t i;
    int first = 1;
    if (!out) return 0;
    for (i = 0; sites && i < SITE_SLOTS; i++) {
        const Site *s = &sites[i];
        if (!s->count) continue;
        fprintf(out, "%s[%u,%u,\"%s\",%u,%llu]", first ? "" : ",", s->pc, s->word, reason_names[s->reason], s->start,
                (unsigned long long)s->count);
        first = 0;
    }
    return !ferror(out);
}

int rr_n64_run_blocks(struct r4300_core *r4300)
{
    int ran = 0;
    uint32_t pc = *r4300_pc(r4300), first;
    while ((first = (pc & 0xFF800000u) == 0x80000000u ? table[(pc & 0x7FFFFFu) >> 2] : mapped(pc) ? first_variant(pc) : 0) != 0) {
        const uint32_t *live = live_words(r4300, pc);
        const RrN64Block *block = 0;
        uint32_t k;
        if (live)
            for (k = first - 1; k < rr_n64_block_count && rr_n64_blocks[k].pc == pc; k++)
                if (memcmp(live, rr_n64_blocks[k].words, rr_n64_blocks[k].len * 4) == 0) { block = &rr_n64_blocks[k]; break; }
        /* After a chain of blocks the loop calls again at this PC, which misses again: only that call notes the site. */
        if (!block) { rr_n64_guard_misses++; if (!ran) note_site(r4300, pc, 3); return ran; }
        rr_n64_native += (uint64_t)block->run(r4300, live);
        rr_n64_block_entries++;
        stretch_reason = 0;
        ran = 1;
        if (*r4300_stop(r4300)) return ran;
        pc = *r4300_pc(r4300);
    }
    if (!ran) note_site(r4300, pc, (pc & 0xFF800000u) == 0x80000000u || mapped(pc) ? 2 : 1);
    return ran;
}

/* ---- what the core's own state leaves out ----
 * A quick state keeps what the core rebuilds wrongly or clears when it loads one: the addresses of the two audio DMAs queued in the AI
 * (the core sets both to the last one written, so the AI played another buffer: Banjo-Tooie's sound and two audio buffers in RDRAM
 * differed from the first frame after a load), the AI's format flag, whether an RSP task stopped on an interrupt and waits to go on
 * (rsp_task_locked, cleared by the core: the task would be marked done at the next SP event) and the CPU's "unsafe" flags with it. */
size_t rr_n64_core_extra_size(void) { return 5 * sizeof(uint32_t); }

void rr_n64_core_extra(void *out, const void *in)
{
    uint32_t v[5];
    if (out) {
        v[0] = g_dev.sp.rsp_task_locked;
        v[1] = g_dev.r4300.cp0.interrupt_unsafe_state;
        v[2] = g_dev.ai.fifo[0].address;
        v[3] = g_dev.ai.fifo[1].address;
        v[4] = g_dev.ai.samples_format_changed;
        memcpy(out, v, sizeof v);
    }
    if (in) {
        memcpy(v, in, sizeof v);
        g_dev.sp.rsp_task_locked = v[0];
        g_dev.r4300.cp0.interrupt_unsafe_state = v[1];
        g_dev.ai.fifo[0].address = v[2];
        g_dev.ai.fifo[1].address = v[3];
        g_dev.ai.samples_format_changed = v[4];
    }
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

/* ---- multiplayer (hostkit RrhkMachine.digest and session_begin) ----
 * The digest folds named fields as integer values, in this fixed order, never a struct's bytes nor a pointer: the same on Windows
 * and Linux. The quick state cannot serve: about a kilobyte of the core's own block holds heap and code addresses that differ
 * from one run to the next. */
static uint64_t mix(uint64_t h, uint64_t v) { h ^= v; h *= 1099511628211ull; return h ^ (h >> 29); }
/* A memory the core has not set up yet (before the first frame, when a session takes its start digest) counts as absent. */
static uint64_t mix_words(uint64_t h, const uint32_t *w, size_t count)
{
    size_t i;
    if (!w) return mix(h, 0x6E6F6E65ull);
    for (i = 0; i < count; i++) h = mix(h, w[i]);
    return h;
}

uint64_t rr_n64_cpu_digest(const uint8_t *saves, size_t saves_size)
{
    struct r4300_core *r = &g_dev.r4300;
    const int64_t *gpr = r4300_regs(r);
    const uint32_t *cp0 = r4300_cp0_regs(&r->cp0);
    const cp1_reg *fpr = r4300_cp1_regs(&r->cp1);
    uint64_t h = 1469598103934665603ull;
    size_t i;
    for (i = 0; i < 32; i++) h = mix(h, (uint64_t)gpr[i]);                       /* VR4300: GPRs, HI, LO, PC */
    h = mix(h, (uint64_t)*r4300_mult_hi(r));
    h = mix(h, (uint64_t)*r4300_mult_lo(r));
    h = mix(h, rr_n64_cpu_pc());   /* 0 before the machine has started */
    h = mix_words(h, cp0, 32);                                                     /* COP0 (Count, Compare, Status, Cause...) */
    for (i = 0; i < 32; i++) h = mix(h, (uint64_t)fpr[i].dword);                  /* COP1 registers, FCR0, FCR31 */
    h = mix(h, *r4300_cp1_fcr0(&r->cp1));
    h = mix(h, *r4300_cp1_fcr31(&r->cp1));
    h = mix_words(h, g_dev.sp.mem, SP_MEM_SIZE / 4);                               /* RSP: DMEM and IMEM, its registers */
    h = mix_words(h, g_dev.sp.regs, SP_REGS_COUNT);
    h = mix_words(h, g_dev.sp.regs2, SP_REGS2_COUNT);
    h = mix_words(h, g_dev.dp.dpc_regs, DPC_REGS_COUNT);                           /* RDP command and span registers */
    h = mix_words(h, g_dev.dp.dps_regs, DPS_REGS_COUNT);
    h = mix_words(h, g_dev.mi.regs, MI_REGS_COUNT);                                /* MI, VI, AI, PI, RI, SI */
    h = mix_words(h, g_dev.vi.regs, VI_REGS_COUNT);
    h = mix_words(h, g_dev.ai.regs, AI_REGS_COUNT);
    h = mix_words(h, g_dev.pi.regs, PI_REGS_COUNT);
    h = mix_words(h, g_dev.ri.regs, RI_REGS_COUNT);
    h = mix_words(h, g_dev.si.regs, SI_REGS_COUNT);
    if (g_dev.pif.ram) for (i = 0; i < PIF_RAM_SIZE; i++) h = mix(h, g_dev.pif.ram[i]);   /* PIF RAM */
    else h = mix(h, 0x6E6F6E65ull);
    h = mix(h, (uint64_t)g_dev.rdram.dram_size);                                   /* RDRAM, whole */
    h = mix_words(h, g_dev.rdram.dram, g_dev.rdram.dram_size / 4);
    h = mix(h, (uint64_t)saves_size);                                              /* cartridge saves and the four paks */
    for (i = 0; i + 4 <= saves_size; i += 4)
        h = mix(h, (uint32_t)saves[i] | (uint32_t)saves[i + 1] << 8 | (uint32_t)saves[i + 2] << 16 | (uint32_t)saves[i + 3] << 24);
    for (; i < saves_size; i++) h = mix(h, saves[i]);
    return h;
}

/* The real-time clock of the cartridges that have one (Animal Forest's): in a session it reads the session's clock plus the
 * emulated seconds, not this PC's time, so every seat sees the same date. The core turns the time into a date with localtime(),
 * so the base is shifted by this PC's zone: every seat shows the session's UTC date, whatever its zone. */
static int64_t session_base;
static const uint64_t *session_frames;
static double session_fps = 60.0;
static time_t session_time(void *clock)
{
    (void)clock;
    return (time_t)(session_base + (int64_t)((double)*session_frames / session_fps));
}
static const struct clock_backend_interface session_clock = {session_time};
static int session_clock_on;

void rr_n64_cpu_session_clock(uint64_t clock, const uint64_t *frames, double fps)
{
    time_t utc = (time_t)clock;
    struct tm fields = *gmtime(&utc);
    fields.tm_isdst = -1;
    session_base = (int64_t)mktime(&fields);   /* the local time whose date is the session's UTC date */
    session_frames = frames;
    session_fps = fps > 0 ? fps : 60.0;
    session_clock_on = 1;
    g_dev.cart.af_rtc.iclock = NULL;           /* set (again) by rr_n64_cpu_session_clock_keep */
    rr_n64_cpu_session_clock_keep();
}

/* The core sets up its devices during the first frame (its run loop starts there), which points the cartridge clock at this PC's
 * time again: the session's clock is put back after each frame until it holds, as at power on (the next read takes it). */
void rr_n64_cpu_session_clock_keep(void)
{
    if (!session_clock_on || g_dev.cart.af_rtc.iclock == &session_clock) return;
    g_dev.cart.af_rtc.clock = NULL;
    g_dev.cart.af_rtc.iclock = &session_clock;
    g_dev.cart.af_rtc.now = 0;
    g_dev.cart.af_rtc.last_update_rtc = 0;
}

/* The PC; 0 before the machine has started (the core sets its PC pointer when its CPU loop begins). */
uint32_t rr_n64_cpu_pc(void)
{
    struct r4300_core *r4300 = cpu ? cpu : &g_dev.r4300;
    return *r4300_pc_struct(r4300) ? *r4300_pc(r4300) : 0;
}
