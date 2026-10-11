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
#define RR_NES_AUDIO_COUNTER counter
#define RR_NES_AUDIO_FREQUENCY check_frequency
#include "nes_audio_output.inc"

static int16_t sample(uint64_t index) { return (int16_t)(index * 173u + 19u); }
static void reset(unsigned period, SDL_AudioFormat format) {
    nes_audio_clear();
    nes_audio.spec.samples = (Uint16)period;
    nes_audio.spec.format = format;
    nes_audio.produced = nes_audio.played = nes_audio.dropped = nes_audio.missing = 0;
    nes_audio.startup_silence = nes_audio.peak = 0;
    nes_audio.keep = (21u + RR_NES_AUDIO_MARGIN_MS) * 48u + period;
    nes_audio.limit = nes_audio.keep + 1008u;
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
                    nes_audio_submit(block, n); produced = end; frame++;
                    /* Old host submits or drops a complete frame at 20 ms. */
                    if (legacy_fill < 960) legacy_fill += n; else legacy_dropped += n;
                } else {
                    clock_us = pull_time;
                    float output[2048];
                    uint64_t before = nes_audio.played, silence_before = nes_audio.startup_silence;
                    nes_audio_callback(NULL, (Uint8 *)output, (int)(period * 2u * SDL_AUDIO_BITSIZE(format) / 8u));
                    unsigned silence = (unsigned)(nes_audio.startup_silence - silence_before);
                    unsigned took = (unsigned)(nes_audio.played - before);
                    if (took && !consumed) {
                        double start = (clock_us - origin) / 1000.0 + silence / 48.0;
                        double expected = period / 48.0 + RR_NES_AUDIO_MARGIN_MS;
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
                    assert(!nes_audio.missing && !nes_audio.dropped);
                }
            }
            assert(nes_audio.produced == produced && nes_audio.played == consumed);
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
    nes_audio_submit(input, 960);
    assert(nes_audio.deadline == 1040000);
    nes_audio_clear(); assert(!nes_audio.fill && !nes_audio.deadline && !nes_audio.started);
    int16_t output[2048]; nes_audio_callback(NULL, (Uint8 *)output, sizeof output);
    for (unsigned i = 0; i < 2048; ++i) assert(output[i] == 0);
    assert(!nes_audio.missing);
    nes_audio_submit(input, 100); clock_us += 40000;
    nes_audio_callback(NULL, (Uint8 *)output, 480 * 4);
    assert(nes_audio.missing == 380 && !nes_audio.started);
    nes_audio_submit(input, 960); assert(nes_audio.deadline == clock_us + 40000);
    nes_audio_clear();
    nes_audio_submit(input, 4096); nes_audio_submit(input, 4096);
    /* Exceptional catch-up: keep the newest PCM. */
    assert(nes_audio.fill == nes_audio.keep && nes_audio.dropped == 8192 - nes_audio.keep);
    assert(nes_audio.pcm[nes_audio.read] == input[4096 - nes_audio.keep]);
    puts("PASS: pause/reset/load flush, silence while empty, underrun recovery, bounded catch-up keeps newest samples.");
}

int main(void) {
    SDL_SetMainReady(); SDL_setenv("SDL_AUDIODRIVER", "dummy", 1);
    assert(SDL_Init(SDL_INIT_AUDIO | SDL_INIT_TIMER) == 0);
    assert(nes_audio_open()); /* Remains paused during virtual-clock tests. */
    schedules(); resets(); nes_audio_close(); SDL_Quit(); return 0;
}
