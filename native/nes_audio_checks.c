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
/* The callback-ring output of the host kit (the sound output of the NES, Game Boy, PC Engine, Game Boy Advance, Nintendo 64 and
 * PlayStation), against authored timelines. Since 1.8.1 the ring is always regulated (rrhk_ring.c): the sound is resampled by at
 * most 0.5 % from its fill, so these checks pin what that keeps (the order of the samples, no jump, the channels apart, no gap
 * and no trim on clocks that drift by 1,000 ppm) instead of the machine's PCM byte for byte. */
#include "hostkit/shell/rrhk_ring.c"
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate) {
    (void)pcm; (void)frames; (void)channels; (void)floating; (void)rate;
}
void rrhk_options_audio_reset(void) {}
const char *rrhk_audio_device(void) { return NULL; }

/* A slow ramp: interpolation keeps it non-decreasing, and a sample lost or inserted in a run shows as a step back or a jump. */
static int16_t sample(uint64_t index) { return (int16_t)((int64_t)(index / 64u) - 16000); }
static void reset(unsigned period, SDL_AudioFormat format) {
    rrhk_ring_clear();
    rrhk_ring.spec.samples = (Uint16)period;
    rrhk_ring.spec.format = format;
    rrhk_ring.produced = rrhk_ring.played = rrhk_ring.dropped = rrhk_ring.missing = 0;
    rrhk_ring.gaps = rrhk_ring.trims = rrhk_ring.clears = rrhk_ring.cleared = 0;
    rrhk_ring.startup_silence = rrhk_ring.peak = 0;
    memset(&rrhk_ring.cushion, 0, sizeof(rrhk_ring.cushion));
    rrhk_ring.keep = (21u + RRHK_RING_MARGIN_MS) * 48u + period;
    rrhk_ring.limit = rrhk_ring.keep + 1008u;
}

static void schedules(void) {
    unsigned periods[] = {256, 441, 480, 512, 1024};
    const double drifts[] = {0.0, 1000.0, -1000.0};   /* the sound card's clock against the PC's, ppm */
    unsigned cases = 0; uint64_t legacy_missing = 0, legacy_dropped = 0;
    double fill_low = 1e9, fill_high = 0, ratio_low = 1e9, ratio_high = 0;
    for (unsigned region = 0; region < 2; ++region) {
        /* Independent rates from the two television master clocks. */
        const double seconds = region ? 531960.0 / 26601712.0 : 357366.0 / 21477272.0;
        for (unsigned p = 0; p < 5; ++p) for (unsigned phase = 0; phase < 16; ++phase) {
            unsigned period = periods[p];
            const double drift = drifts[phase % 3];
            SDL_AudioFormat format = phase & 1 ? AUDIO_F32SYS : AUDIO_S16SYS;
            reset(period, format); clock_us = 1000000;
            uint64_t origin = clock_us, produced = 0, consumed = 0;
            unsigned frame = 0, callback = 0; uint32_t legacy_fill = 0;
            int previous = sample(0);
            Uint64 first = origin + (uint64_t)phase * period * 1000000 / (16u * 48000u);
            while (frame < 2000) {
                Uint64 push_time = origin + (Uint64)(frame * seconds * 1000000) + (frame % 7) * 2000u;
                Uint64 pull_time = first + (Uint64)((double)callback * period * 1000000.0 / 48000.0 * (1.0 + drift / 1e6));
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
                        /* the silence is counted in the card's samples: a drifting card stretches it by its ppm */
                        double start = (clock_us - origin) / 1000.0 + silence / 48.0 * (1.0 + drift / 1e6);
                        double expected = period / 48.0 + RRHK_RING_MARGIN_MS;
                        const double slack = (clock_us - origin) / 1000.0 * SDL_fabs(drift) / 1e6;
                        assert(start >= expected - .002 - slack && start <= expected + .022 + slack);
                    }
                    for (unsigned i = 0; i < took; ++i) {
                        unsigned at = (silence + i) * 2;
                        const int left = format == AUDIO_F32SYS ? (int)(output[at] * 32768.0f) : ((int16_t *)output)[at];
                        const int right = format == AUDIO_F32SYS ? (int)(output[at + 1] * 32768.0f) : ((int16_t *)output)[at + 1];
                        assert(left == right);                              /* a mono source on both channels */
                        assert(left >= previous && left <= previous + 1);   /* in order, nothing lost, nothing inserted */
                        previous = left;
                    }
                    consumed += took; callback++;
                    unsigned take = SDL_min(legacy_fill, period);
                    if (frame > 2) legacy_missing += period - take;
                    legacy_fill -= take;
                    assert(!rrhk_ring.missing && !rrhk_ring.dropped && !rrhk_ring.gaps && !rrhk_ring.trims);
                    if (frame > 1000) {   /* settled: the fill held near the target whatever the drift */
                        fill_low = SDL_min(fill_low, (double)rrhk_ring.fill);
                        fill_high = SDL_max(fill_high, (double)rrhk_ring.fill);
                    }
                }
            }
            assert(rrhk_ring.played == consumed && rrhk_ring.produced == consumed + rrhk_ring.fill);
            const double ratio = (double)rrhk_ring.produced / (double)produced;
            ratio_low = SDL_min(ratio_low, ratio); ratio_high = SDL_max(ratio_high, ratio);
            assert(ratio > 1.0 - RR_DRC_CORRECTION && ratio < 1.0 + RR_DRC_CORRECTION);
            ++cases;
        }
    }
    printf("PASS: %u NTSC/PAL timelines, 2000 frames, 16 phases, five periods, 12 ms jitter, sound card clock 0 / +1000 / -1000 ppm: "
           "regulated, in order, no gap, no trim; settled fill %.0f to %.0f frames, length %.4f to %.4f of the machine's.\n",
           cases, fill_low, fill_high, ratio_low, ratio_high);
    printf("Legacy queue on the same schedules: missing=%llu discarded=%llu samples (software model, not physical audio).\n",
        (unsigned long long)legacy_missing, (unsigned long long)legacy_dropped);
    assert(legacy_missing > 0);
}

/* A ramp of one step a frame, resampled by up to 0.5 %: two neighbours may differ by 2 (a step of 1.005 rounded). */
static void resets(void) {
    reset(480, AUDIO_S16SYS); clock_us = 1000000;
    int16_t input[4096]; for (unsigned i = 0; i < 4096; ++i) input[i] = (int16_t)i;
    rrhk_ring_submit(input, 960);
    assert(rrhk_ring.deadline == 1040000);
    rrhk_ring_clear(); assert(!rrhk_ring.fill && !rrhk_ring.deadline && !rrhk_ring.started && rrhk_ring.clears == 1);
    int16_t output[2048]; rrhk_ring_callback(NULL, (Uint8 *)output, sizeof output);
    for (unsigned i = 0; i < 2048; ++i) assert(output[i] == 0);
    assert(!rrhk_ring.missing && !rrhk_ring.played);
    rrhk_ring_submit(input, 100); clock_us += 40000;
    const uint64_t short_block = rrhk_ring.fill;     /* 100 frames, lengthened by at most 0.5 % below the target */
    assert(short_block >= 100 && short_block <= 101);
    rrhk_ring_callback(NULL, (Uint8 *)output, 480 * 4);
    assert(rrhk_ring.missing == 480 - short_block && rrhk_ring.gaps == 1 && !rrhk_ring.started);
    /* The guest was still producing: that gap adds one restart step. */
    assert(rr_cushion_ms(&rrhk_ring.cushion) == RR_CUSHION_STEP_MS);
    rrhk_ring_submit(input, 960); assert(rrhk_ring.deadline == clock_us + 40000 + RR_CUSHION_STEP_MS * 1000u);
    rrhk_ring_clear();
    /* Exceptional catch-up beyond the bound (its limit, the reserve and 80 ms of room): keep the newest PCM, including the
     * reserve; a trim does not raise the reserve. */
    const uint64_t produced = rrhk_ring.produced;
    rrhk_ring_submit(input, 4096); rrhk_ring_submit(input, 4096);
    uint32_t keep = rrhk_ring.keep + RR_CUSHION_STEP_MS * 48u;
    assert(rrhk_ring.fill == keep && rrhk_ring.dropped == rrhk_ring.produced - produced - keep && rrhk_ring.trims == 1);
    assert(rr_cushion_ms(&rrhk_ring.cushion) == RR_CUSHION_STEP_MS);
    /* The kept frames are the newest, in order: the end of the second block. */
    int16_t previous = rrhk_ring.pcm[rrhk_ring.read];
    assert(previous >= 4096 - (int)keep - 30);
    for (uint32_t i = 1; i < rrhk_ring.fill; ++i) {
        const int16_t value = rrhk_ring.pcm[(rrhk_ring.read + i) % RRHK_RING_FRAMES];
        assert(value >= previous && value <= previous + 2);
        previous = value;
    }
    assert(previous >= 4094);
    puts("PASS: pause/reset/load flush (counted), silence while empty, underrun recovery, bounded catch-up keeps newest samples in order.");
}

/* The Game Boy's source: interleaved 44.1 kHz stereo and a 10 ms start margin. Left and right keep their order and stay apart
 * (S16 and F32), the period starts at the margin, and a backlog trims the same way as for a mono source. */
static void stereo(void) {
    assert(rrhk_ring_open(44100u, 2, 10)); /* Remains paused during virtual-clock tests. */
    assert(rrhk_ring.source == 2 && rrhk_ring.margin == 10);
    for (unsigned format = 0; format < 2; ++format) {
        reset(256, format ? AUDIO_F32SYS : AUDIO_S16SYS);
        rrhk_ring.rate = 44100u; rrhk_ring.keep = (21u + 10u) * 44u + 256u; rrhk_ring.limit = rrhk_ring.keep + 926u;
        clock_us = 1000000;
        int16_t input[2 * 1500];
        for (unsigned i = 0; i < 1500; ++i) { input[2 * i] = (int16_t)i; input[2 * i + 1] = (int16_t)-(int)i; }
        rrhk_ring_submit(input, 1000);
        /* 256 frames at 44.1 kHz and the margin: 5805 us and 10 ms, rounded up. */
        assert(rrhk_ring.deadline == 1000000 + 5805 + 10000);
        float out[2 * 256]; int16_t *wide = (int16_t *)out;
        clock_us = rrhk_ring.deadline;
        rrhk_ring_callback(NULL, (Uint8 *)out, (int)sizeof(out) / (format ? 1 : 2));
        int previous = -1;
        for (unsigned i = 0; i < 256; ++i) {
            const int left = format ? (int)(out[2 * i] * 32768.0f) : wide[2 * i];
            const int right = format ? (int)(out[2 * i + 1] * 32768.0f) : wide[2 * i + 1];
            assert(right == -left && left >= previous && left <= previous + 2);
            previous = left;
        }
        assert(rrhk_ring.played == 256 && rrhk_ring.fill == rrhk_ring.produced - 256 && !rrhk_ring.missing);
        /* A backlog beyond the bound keeps the newest frames, whole pairs. */
        rrhk_ring_clear();
        const uint64_t produced = rrhk_ring.produced;
        for (unsigned block = 0; block < 5; ++block) rrhk_ring_submit(input, 1500);
        assert(rrhk_ring.trims == 1 && rrhk_ring.fill == SDL_min(rrhk_ring.keep, RRHK_RING_FRAMES / 2u));
        assert(rrhk_ring.dropped == rrhk_ring.produced - produced - rrhk_ring.fill);
        for (uint32_t i = 0; i < rrhk_ring.fill; ++i) {
            const uint32_t at = (rrhk_ring.read + i) % RRHK_RING_FRAMES;
            assert(rrhk_ring.pcm[at * 2 + 1] == -rrhk_ring.pcm[at * 2]);
        }
        assert(rrhk_ring.pcm[((rrhk_ring.read + rrhk_ring.fill - 1) % RRHK_RING_FRAMES) * 2] >= 1498);
    }
    rrhk_ring_close();
    puts("PASS: stereo source (Game Boy): in order, channels apart in S16 and F32, 10 ms start margin, backlog keeps the newest pairs.");
}

int main(void) {
    SDL_SetMainReady(); SDL_setenv("SDL_AUDIODRIVER", "dummy", 1);
    assert(SDL_Init(SDL_INIT_AUDIO | SDL_INIT_TIMER) == 0);
    assert(rrhk_ring_open(48000u, 1, 0)); /* Remains paused during virtual-clock tests. */
    schedules(); resets(); rrhk_ring_close();
    stereo();
    SDL_Quit(); return 0;
}
