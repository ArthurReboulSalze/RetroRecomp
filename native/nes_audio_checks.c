/* Authored output timelines, independent of commercial cartridges. */
#undef NDEBUG
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static bool synthetic = true;
static Uint64 clock_us;
static Uint64 counter(void) { return synthetic ? clock_us : SDL_GetPerformanceCounter(); }
static Uint64 check_frequency(void) { return synthetic ? 1000000 : SDL_GetPerformanceFrequency(); }
#define RRHK_RING_COUNTER counter
#define RRHK_RING_FREQUENCY check_frequency
/* The callback-ring output of the host kit (the NES host's sound output), against authored timelines. */
#include "hostkit/shell/rrhk_ring.c"
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate) {
    (void)pcm; (void)frames; (void)channels; (void)floating; (void)rate;
}
void rrhk_options_audio_reset(void) {}

static int16_t sample(uint64_t index) { return (int16_t)(index * 173u + 19u); }
static void reset(unsigned period, SDL_AudioFormat format) {
    rrhk_ring_clear();
    rrhk_ring.spec.samples = (Uint16)period;
    rrhk_ring.spec.format = format;
    rrhk_ring.produced = rrhk_ring.played = rrhk_ring.dropped = rrhk_ring.missing = 0;
    rrhk_ring.startup_silence = rrhk_ring.peak = 0;
    memset(&rrhk_ring.cushion, 0, sizeof(rrhk_ring.cushion));
    rrhk_ring.keep = (21u + RRHK_RING_MARGIN_MS) * 48u + period;
    rrhk_ring.limit = rrhk_ring.keep + 1008u;
}

static void schedules(void) {
    unsigned periods[] = {256, 441, 480, 512, 1024};
    unsigned cases = 0; uint64_t legacy_missing = 0, legacy_dropped = 0;
    for (unsigned region = 0; region < 2; ++region) {
        /* Independent rates from the two television master clocks. */
        const double seconds = region ? 531960.0 / 26601712.0 : 357366.0 / 21477272.0;
        for (unsigned p = 0; p < 5; ++p) for (unsigned phase = 0; phase < 16; ++phase) {
            unsigned period = periods[p];
            SDL_AudioFormat format = phase & 1 ? AUDIO_F32SYS : AUDIO_S16SYS;
            reset(period, format); clock_us = 1000000;
            uint64_t origin = clock_us, produced = 0, consumed = 0;
            unsigned frame = 0, callback = 0; uint32_t legacy_fill = 0;
            Uint64 first = origin + (uint64_t)phase * period * 1000000 / (16u * 48000u);
            while (frame < 2000) {
                Uint64 push_time = origin + (Uint64)(frame * seconds * 1000000) + (frame % 7) * 2000u;
                Uint64 pull_time = first + (uint64_t)callback * period * 1000000 / 48000u;
                if (push_time <= pull_time) {
                    clock_us = push_time;
                    uint64_t end = (uint64_t)((frame + 1) * seconds * 48000);
                    unsigned n = (unsigned)(end - produced); int16_t block[1024];
                    assert(n <= 1024);
                    for (unsigned i = 0; i < n; ++i) block[i] = sample(produced + i);
                    rrhk_ring_submit(block, n); produced = end; frame++;
                    /* Old host submits or drops a complete frame at 20 ms. */
                    if (legacy_fill < 960) legacy_fill += n; else legacy_dropped += n;
                } else {
                    clock_us = pull_time;
                    float output[2048];
                    uint64_t before = rrhk_ring.played, silence_before = rrhk_ring.startup_silence;
                    rrhk_ring_callback(NULL, (Uint8 *)output, (int)(period * 2u * SDL_AUDIO_BITSIZE(format) / 8u));
                    unsigned silence = (unsigned)(rrhk_ring.startup_silence - silence_before);
                    unsigned took = (unsigned)(rrhk_ring.played - before);
                    if (took && !consumed) {
                        double start = (clock_us - origin) / 1000.0 + silence / 48.0;
                        double expected = period / 48.0 + RRHK_RING_MARGIN_MS;
                        assert(start >= expected - .002 && start <= expected + .022);
                    }
                    for (unsigned i = 0; i < took; ++i) for (unsigned ch = 0; ch < 2; ++ch) {
                        unsigned at = (silence + i) * 2 + ch;
                        if (format == AUDIO_F32SYS) assert(output[at] == sample(consumed + i) / 32768.0f);
                        else assert(((int16_t *)output)[at] == sample(consumed + i));
                    }
                    consumed += took; callback++;
                    unsigned take = SDL_min(legacy_fill, period);
                    if (frame > 2) legacy_missing += period - take;
                    legacy_fill -= take;
                    assert(!rrhk_ring.missing && !rrhk_ring.dropped);
                }
            }
            assert(rrhk_ring.produced == produced && rrhk_ring.played == consumed);
            ++cases;
        }
    }
    printf("PASS: %u NTSC/PAL timelines, 2000 frames, 16 phases, five periods, 12 ms jitter; exact mono/stereo S16/F32, no missing/discarded PCM.\n", cases);
    printf("Legacy queue on the same schedules: missing=%llu discarded=%llu samples (software model, not physical audio).\n",
        (unsigned long long)legacy_missing, (unsigned long long)legacy_dropped);
    assert(legacy_missing > 0);
}

static void resets(void) {
    reset(480, AUDIO_S16SYS); clock_us = 1000000;
    int16_t input[4096]; for (unsigned i = 0; i < 4096; ++i) input[i] = sample(i);
    rrhk_ring_submit(input, 960);
    assert(rrhk_ring.deadline == 1040000);
    rrhk_ring_clear(); assert(!rrhk_ring.fill && !rrhk_ring.deadline && !rrhk_ring.started);
    int16_t output[2048]; rrhk_ring_callback(NULL, (Uint8 *)output, sizeof output);
    for (unsigned i = 0; i < 2048; ++i) assert(output[i] == 0);
    assert(!rrhk_ring.missing);
    rrhk_ring_submit(input, 100); clock_us += 40000;
    rrhk_ring_callback(NULL, (Uint8 *)output, 480 * 4);
    assert(rrhk_ring.missing == 380 && !rrhk_ring.started);
    /* The guest was still producing: that gap adds one restart step. */
    assert(rr_cushion_ms(&rrhk_ring.cushion) == RR_CUSHION_STEP_MS);
    rrhk_ring_submit(input, 960); assert(rrhk_ring.deadline == clock_us + 40000 + RR_CUSHION_STEP_MS * 1000u);
    rrhk_ring_clear();
    rrhk_ring_submit(input, 4096); rrhk_ring_submit(input, 4096);
    /* Exceptional catch-up: keep the newest PCM, including the reserve. */
    uint32_t keep = rrhk_ring.keep + RR_CUSHION_STEP_MS * 48u;
    assert(rrhk_ring.fill == keep && rrhk_ring.dropped == 8192 - keep);
    assert(rrhk_ring.pcm[rrhk_ring.read] == input[4096 - keep]);
    puts("PASS: pause/reset/load flush, silence while empty, underrun recovery, bounded catch-up keeps newest samples.");
}

/* The Game Boy's source: interleaved 44.1 kHz stereo and a 10 ms start margin. Left and right keep their order and their own
 * samples (S16 and F32), the period starts at the margin, and a backlog trims the same way as for a mono source. */
static void stereo(void) {
    assert(rrhk_ring_open(44100u, 2, 10)); /* Remains paused during virtual-clock tests. */
    assert(rrhk_ring.source == 2 && rrhk_ring.margin == 10);
    for (unsigned format = 0; format < 2; ++format) {
        reset(256, format ? AUDIO_F32SYS : AUDIO_S16SYS);
        rrhk_ring.rate = 44100u; rrhk_ring.keep = (21u + 10u) * 44u + 256u; rrhk_ring.limit = rrhk_ring.keep + 926u;
        clock_us = 1000000;
        int16_t input[2 * 1500];
        for (unsigned i = 0; i < 1500; ++i) { input[2 * i] = sample(i); input[2 * i + 1] = (int16_t)~sample(i); }
        rrhk_ring_submit(input, 1000);
        /* 256 frames at 44.1 kHz and the margin: 5805 us and 10 ms, rounded up. */
        assert(rrhk_ring.deadline == 1000000 + 5805 + 10000);
        float out[2 * 256]; int16_t *wide = (int16_t *)out;
        clock_us = rrhk_ring.deadline;
        rrhk_ring_callback(NULL, (Uint8 *)out, (int)sizeof(out) / (format ? 1 : 2));
        for (unsigned i = 0; i < 256; ++i) {
            if (format) { assert(out[2 * i] == sample(i) / 32768.0f && out[2 * i + 1] == (int16_t)~sample(i) / 32768.0f); }
            else assert(wide[2 * i] == sample(i) && wide[2 * i + 1] == (int16_t)~sample(i));
        }
        assert(rrhk_ring.played == 256 && rrhk_ring.fill == 744 && !rrhk_ring.missing);
        /* A backlog beyond the limit keeps the newest frames, whole pairs. */
        rrhk_ring_clear();
        rrhk_ring_submit(input, 1500); rrhk_ring_submit(input, 1500); rrhk_ring_submit(input, 1500);
        assert(rrhk_ring.fill == SDL_min(rrhk_ring.keep, 4500u) && rrhk_ring.dropped == 4500u - rrhk_ring.fill);
        /* The newest pairs: the tail of the second block, then the whole third one (every block is the same 1500 frames). */
        const unsigned first = 1500 - (rrhk_ring.fill - 1500);
        assert(rrhk_ring.pcm[rrhk_ring.read * 2] == input[2 * first] && rrhk_ring.pcm[rrhk_ring.read * 2 + 1] == input[2 * first + 1]);
    }
    rrhk_ring_close();
    puts("PASS: stereo source (Game Boy): order and channels exact in S16 and F32, 10 ms start margin, backlog keeps the newest pairs.");
}

int main(void) {
    SDL_SetMainReady(); SDL_setenv("SDL_AUDIODRIVER", "dummy", 1);
    assert(SDL_Init(SDL_INIT_AUDIO | SDL_INIT_TIMER) == 0);
    assert(rrhk_ring_open(48000u, 1, 0)); /* Remains paused during virtual-clock tests. */
    schedules(); resets(); rrhk_ring_close();
    stereo();
    SDL_Quit(); return 0;
}
