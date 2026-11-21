/* Checks of the box filter (native/audio_box.h) on levels this file makes: a constant level, a square wave of a known period,
 * mono and stereo, a full buffer, a restart, the clamp, and the same samples whatever the calls are cut in. Built by
 * tools/audio_box_selftest.py; no ROM, no machine. MIT, Retro-Recomp. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "audio_box.h"

static unsigned passed, failed;

static void expect(const char *what, int ok)
{
    if (ok) ++passed; else { ++failed; fprintf(stderr, "FAIL: %s\n", what); }
}

enum { CAPACITY = 60000 };
static int16_t buffer_a[CAPACITY * 2], buffer_b[CAPACITY * 2], taken[CAPACITY * 2];

static void check_constant(void)
{
    AudioBox box;
    audio_box_init(&box, 1, 1000000, 44100, buffer_a, CAPACITY, 0);
    audio_box_feed_mono(&box, 1000, 1000000);                       /* one second of a 1 MHz guest */
    int same = 1;
    for (uint32_t i = 0; i < box.count; ++i) same &= buffer_a[i] == 1000;
    expect("a constant level for one second: 44,100 samples of it (the last may wait for its end)",
        (box.count == 44100 || box.count == 44099) && same && box.dropped == 0);
    expect("the step keeps its fraction: cycles x 65536 per sample", box.step == 1000000ull * 65536u / 44100);
}

static void check_square(void)
{
    /* 1 MHz, 50 kHz: 20 cycles a sample; a square of 40 cycles (20 at 26212, the SN76489's top, 20 at 0) gives the two
     * levels in turn, each sample one half period. */
    AudioBox box;
    audio_box_init(&box, 1, 1000000, 50000, buffer_a, CAPACITY, 0);
    for (int period = 0; period < 1000; ++period) {
        audio_box_feed_mono(&box, 26212, 20);
        audio_box_feed_mono(&box, 0, 20);
    }
    int alternate = box.count == 2000;
    for (uint32_t i = 0; alternate && i < box.count; ++i) alternate = buffer_a[i] == (i & 1 ? 0 : 26212);
    expect("a square of a known period: one half period a sample, 26212 then 0", alternate);
    /* The same square on the SG-1000's clock and rate, fed one 16-cycle chip tick at a time: its mean is half the level. */
    audio_box_init(&box, 1, 3579545, 44100, buffer_a, CAPACITY, 0);
    for (int tick = 0; tick < 3579545 / 16; ++tick)
        audio_box_feed_mono(&box, (tick & 1) ? 0 : 26212, 16);
    int64_t sum = 0;
    for (uint32_t i = 0; i < box.count; ++i) sum += buffer_a[i];
    expect("16-cycle ticks at 3,579,545 Hz to 44,100 Hz: about 44,100 samples whose mean is half the level",
        box.count >= 44095 && box.count <= 44100 && llabs(sum / (int64_t)box.count - 13106) <= 2);
}

static void check_stereo(void)
{
    AudioBox box;
    audio_box_init(&box, 2, 4000000, 50000, buffer_a, CAPACITY, 0);          /* the CPC: 80 cycles a sample */
    audio_box_feed(&box, 1200, -800, 80 * 10);
    int pairs = box.count == 10;
    for (uint32_t i = 0; pairs && i < box.count; ++i) pairs = buffer_a[2 * i] == 1200 && buffer_a[2 * i + 1] == -800;
    expect("stereo: left and right interleaved, each its own mean", pairs);
    audio_box_feed(&box, 1000, 0, 40);
    audio_box_feed(&box, 0, 1000, 40);
    expect("stereo: a sample cut in two halves gives each side its half", box.count == 11 && buffer_a[20] == 500
        && buffer_a[21] == 500);
    audio_box_feed_mono(&box, 300, 80);
    expect("a mono feed on a stereo box writes both sides", buffer_a[22] == 300 && buffer_a[23] == 300);
}

static void check_drops_and_take(void)
{
    static int16_t small[10];
    AudioBox box;
    audio_box_init(&box, 1, 1000000, 50000, small, 10, 0);
    for (int i = 0; i < 25; ++i) audio_box_feed_mono(&box, i, 20);
    expect("a full buffer: 10 kept, 15 counted as dropped", box.count == 10 && box.dropped == 15 && small[9] == 9);
    uint32_t n = audio_box_take(&box, taken, 4);
    expect("take moves the oldest out", n == 4 && taken[0] == 0 && taken[3] == 3 && box.count == 6 && small[0] == 4);
    audio_box_feed_mono(&box, 77, 20);
    expect("and frees room for the next", box.count == 7 && small[6] == 77 && box.dropped == 15);
    n = audio_box_take(&box, taken, 100);
    expect("take gives at most what waits", n == 7 && box.count == 0 && taken[6] == 77);
}

static void check_reset_and_clamp(void)
{
    AudioBox one, two;
    audio_box_init(&one, 1, 1000000, 44100, buffer_a, CAPACITY, 0);
    audio_box_feed_mono(&one, 5000, 12345);
    audio_box_reset(&one, 777777);
    audio_box_init(&two, 1, 1000000, 44100, buffer_b, CAPACITY, 777777);
    audio_box_feed_mono(&one, 321, 50000);
    audio_box_feed_mono(&two, 321, 50000);
    expect("a reset at a cycle is a fresh start at that cycle", one.count == two.count && one.count > 0
        && !memcmp(buffer_a, buffer_b, one.count * sizeof *buffer_a) && one.time == two.time);
    audio_box_init(&one, 2, 1000000, 50000, buffer_a, CAPACITY, 0);
    audio_box_feed(&one, 40000, -40000, 20);
    expect("levels beyond int16 are clamped", buffer_a[0] == 32767 && buffer_a[1] == -32768);
}

/* The same levels fed as one span each, as many short feeds, and as holds to absolute cycles: the same samples. */
static uint32_t rng = 12345;
static unsigned next_random(unsigned below) { rng = rng * 1103515245u + 12345u; return (rng >> 8) % below; }

static void check_granularity(void)
{
    for (unsigned channels = 1; channels <= 2; ++channels) {
        AudioBox whole, cut, held;
        static int16_t buffer_c[CAPACITY * 2];
        audio_box_init(&whole, channels, 3579545, 44100, buffer_a, CAPACITY, 1000);
        audio_box_init(&cut, channels, 3579545, 44100, buffer_b, CAPACITY, 1000);
        audio_box_init(&held, channels, 3579545, 44100, buffer_c, CAPACITY, 1000);
        rng = 12345 + channels;
        uint64_t at = 1000;
        for (int span = 0; span < 20000; ++span) {
            int left = (int)next_random(26213), right = (int)next_random(26213);
            uint64_t cycles = 1 + next_random(400);
            audio_box_feed(&whole, left, right, cycles);
            for (uint64_t done = 0; done < cycles;) {
                uint64_t piece = 1 + next_random(37);
                if (piece > cycles - done) piece = cycles - done;
                audio_box_feed(&cut, left, right, piece);
                done += piece;
            }
            at += cycles;
            audio_box_hold(&held, left, right, at);
        }
        size_t values = (size_t)whole.count * channels;
        expect(channels == 1 ? "mono: one long feed per level and many short ones give the same samples"
                             : "stereo: one long feed per level and many short ones give the same samples",
            whole.count > 1000 && whole.count == cut.count && !memcmp(buffer_a, buffer_b, values * sizeof *buffer_a)
            && whole.time == cut.time && whole.next_sample == cut.next_sample);
        expect("holds to absolute cycles give them too", held.count == whole.count
            && !memcmp(buffer_a, buffer_c, values * sizeof *buffer_a));
    }
}

int main(void)
{
    check_constant();
    check_square();
    check_stereo();
    check_drops_and_take();
    check_reset_and_clamp();
    check_granularity();
    printf("{\"passed\": %u, \"failed\": %u}\n", passed, failed);
    return failed ? 1 : 0;
}
