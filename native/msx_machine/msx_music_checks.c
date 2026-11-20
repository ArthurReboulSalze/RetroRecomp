/* MSX-MUSIC fixtures: the quiet step of msx_music.c against emu2413's own OPLL_calc. MIT, Retro-Recomp. A development check,
 * never built into a game (tools/msx_reference.py runs it with the other fixtures). Chip A runs OPLL_calc for every sample, as
 * music_sample did before the quiet step; chip B runs msx_music.c's music_sample and music_write. After every sample the two
 * chips' whole images (the quick-state serialisation: every field, each slot's patch and wave table) and outputs must be equal:
 * an untouched chip, then random register programs (notes, instruments, volumes, rhythm and test bits) with machine resets,
 * quick states loaded on a quiet chip and silences whose releases end. It also checks that the quiet step was taken, left on a
 * write and taken again, so a predicate that never holds fails too. It holds on emu2413's internals: run it after a bump.
 * Prints one line per check and exits 1 if any fails. */
#include "msx_music.c"

#include <stdio.h>

static int failures;
static uint8_t img_a[4096], img_b[4096];
static MsxMusic A, B;
static uint64_t cycle, quiet_samples, samples, quiet_exits;
static uint32_t rng = 2463534242u;
static int differ;

static void check(const char *name, int ok, long long got, long long want)
{
    printf("%s %s: %lld (expected %lld)\n", ok ? "ok  " : "FAIL", name, got, want);
    failures += !ok;
}

static uint32_t next_rand(void) { rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5; return rng; }

static size_t image(const OPLL *o, uint8_t *buf)
{
    uint8_t *cursor = rr_ser_OPLL(buf, o);
    for (int i = 0; i < 18; ++i) *cursor++ = (uint8_t)(o->slot[i].patch - o->patch);
    for (int i = 0; i < 18; ++i) *cursor++ = (uint8_t)(o->slot[i].wave_table == wave_table_map[1]);
    return (size_t)(cursor - buf);
}

static int step(void)
{
    cycle += MSX_MUSIC_CYCLES;
    while (A.next <= cycle) { A.out = OPLL_calc(A.opll); A.next += MSX_MUSIC_CYCLES; }
    int was_quiet = B.quiet;
    int out_b = music_sample(&B, cycle);
    quiet_samples += was_quiet;
    samples++;
    size_t na = image(A.opll, img_a), nb = image(B.opll, img_b);
    if (na != nb || memcmp(img_a, img_b, na) || A.out != out_b) {
        if (!differ) printf("     first difference at sample %llu (quiet step before it: %d)\n", (unsigned long long)samples, was_quiet);
        differ = 1;
        return 0;
    }
    return 1;
}

static void write_both(uint8_t reg, uint8_t value)
{
    OPLL_writeReg(A.opll, reg, value);
    quiet_exits += B.quiet;
    music_write(&B, 0x7C, reg);
    music_write(&B, 0x7D, value);
}

static void make(MsxMusic *c)
{
    c->opll = OPLL_new(MSX_MUSIC_CLOCK, MSX_MUSIC_RATE);
    OPLL_setChipType(c->opll, OPLL_2413_TONE);
    OPLL_reset(c->opll);
    c->latch = 0; c->next = MSX_MUSIC_CYCLES; c->out = 0; c->quiet = false; c->check = true; c->full = 0;
}

/* B takes A's state as music_state's apply does: the fields, the slot pointers, then the flags. */
static void load_b_from_a(void)
{
    image(A.opll, img_a);
    const uint8_t *cursor = rr_de_OPLL(img_a, B.opll);
    for (int i = 0; i < 18; ++i) {
        B.opll->slot[i].patch = &B.opll->patch[cursor[i]];
        B.opll->slot[i].wave_table = wave_table_map[cursor[18 + i] & 1];
    }
    B.next = A.next; B.out = A.out; B.quiet = false; B.check = true;
}

static int run(long long count)
{
    for (long long i = 0; i < count; ++i)
        if (!step()) return 0;
    return 1;
}

int main(void)
{
    make(&A); make(&B);
    if (!A.opll || !B.opll) { puts("FAIL emu2413 could not make a chip"); return 1; }
    /* An untouched chip, past a whole period of the LFO amplitude table (210 x 64 samples), many times over. */
    int ok = run(600000);
    check("untouched chip: samples equal to OPLL_calc", ok, (long long)samples, 600000);
    check("untouched chip: samples on the quiet step", ok && quiet_samples == 599999, (long long)quiet_samples, 599999);
    uint64_t quiet_before = quiet_samples, samples_before = samples;
    int quiet_again = 0, resets = 0;
    static const uint8_t regs[] = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x0E, 0x0F, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15,
                                   0x16, 0x17, 0x18, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x30, 0x31, 0x32, 0x33,
                                   0x34, 0x35, 0x36, 0x37, 0x38};
    for (int round = 0; ok && round < 40; ++round) {
        int ending = round & 1;
        if (round % 5 == 0) {                                  /* a machine reset, then a quiet while; a state loaded on it */
            OPLL_reset(A.opll); A.latch = 0; A.next = cycle + MSX_MUSIC_CYCLES; A.out = 0;
            music_reset(&B, cycle);
            resets++;
            ok = run((long long)(next_rand() % 20000));
            if (round % 10 == 0) load_b_from_a();
        }
        int writes = 1 + (int)(next_rand() % 30);
        for (int w = 0; ok && w < writes; ++w) {
            uint8_t reg = regs[next_rand() % sizeof regs];
            uint8_t value = (uint8_t)next_rand();
            if (reg == 0x0F && (next_rand() & 3)) value = 0;          /* the test register: mostly off */
            if (ending && (reg == 0x06 || reg == 0x07)) value |= 0x08;  /* the user patch's release ends */
            write_both(reg, value);
            ok = run((long long)(next_rand() % 2000));
        }
        if (round % 7 == 3) load_b_from_a();
        if (ok && ending) {                                    /* silence: built-in instrument 1, key off, F-number 0 */
            write_both(0x0E, 0); write_both(0x0F, 0);
            for (uint8_t ch = 0; ch < 9; ++ch) {
                write_both((uint8_t)(0x30 + ch), 0x10);
                write_both((uint8_t)(0x20 + ch), 0);
                write_both((uint8_t)(0x10 + ch), 0);
            }
            uint64_t q0 = quiet_samples;
            ok = run(100000);
            quiet_again += quiet_samples > q0;
        }
    }
    check("register programs: every sample equal to OPLL_calc", ok, ok, 1);
    printf("     %llu samples, %llu on the quiet step, %d resets\n", (unsigned long long)(samples - samples_before),
           (unsigned long long)(quiet_samples - quiet_before), resets);
    check("register programs: writes made on the quiet step (it is left)", quiet_exits > 0, (long long)quiet_exits, 1);
    (void)quiet_again;
    /* A note that ends: a reset, built-in instrument 1 (violin) at full volume on channel 1, F-number 172 in block 4, keyed on
     * for 20,000 samples, then keyed off and F-number 0; its release ends and the chip is quiet again. */
    if (ok) {
        OPLL_reset(A.opll); A.latch = 0; A.next = cycle + MSX_MUSIC_CYCLES; A.out = 0;
        music_reset(&B, cycle);
        ok = run(100);
        write_both(0x30, 0x10); write_both(0x10, 172); write_both(0x20, 0x18);
        ok = ok && run(20000);
        uint64_t exits = quiet_exits;
        write_both(0x20, 0x00); write_both(0x10, 0x00);
        uint64_t q0 = quiet_samples;
        ok = ok && run(200000);
        check("a note that ends: every sample equal to OPLL_calc", ok, ok, 1);
        check("a note that ends: samples on the quiet step after its release", quiet_samples > q0, (long long)(quiet_samples - q0), 1);
        (void)exits;
    }
    return failures ? 1 : 0;
}
