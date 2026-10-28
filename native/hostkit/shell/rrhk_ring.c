/* Callback-ring audio output (HOST_KIT.md decision D5, the model of the NES host): the machine's
 * mono 16-bit PCM at its own rate is kept in order in a ring and the device callback converts it
 * to the device format (S16 or F32, any channel count). No guest execution, allocation or clock
 * correction in the callback. The adaptive reserve (audio_cushion.h) sets when a device period
 * may start. This file is the NES host's former nes_audio_output.inc, unchanged in its logic;
 * a machine selects it with audio_model = RRHK_AUDIO_RING. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdio.h>
#include <string.h>
#include "audio_cushion.h"
#include "hostkit/hostkit_internal.h"

/* Checks drive the ring with a synthetic clock by defining these before including this file. */
#ifndef RRHK_RING_COUNTER
#define RRHK_RING_COUNTER SDL_GetPerformanceCounter
#define RRHK_RING_FREQUENCY SDL_GetPerformanceFrequency
#endif
#define RRHK_RING_FRAMES 8192u
#define RRHK_RING_MARGIN_MS 30u

static struct {
    SDL_AudioDeviceID id;
    SDL_AudioSpec spec;
    int16_t pcm[RRHK_RING_FRAMES];
    uint32_t rate, read, write, fill, keep, limit, peak;
    uint64_t deadline, produced, played, dropped, missing, startup_silence;
    bool started;
    RrAudioCushion cushion;
} rrhk_ring;

static void SDLCALL rrhk_ring_callback(void *unused, Uint8 *stream, int bytes) {
    (void)unused;
    memset(stream, 0, (size_t)bytes);
    uint32_t stride = rrhk_ring.spec.channels * SDL_AUDIO_BITSIZE(rrhk_ring.spec.format) / 8u;
    uint32_t wanted = (uint32_t)bytes / stride;
    if (!rrhk_ring.started) {
        if (!rrhk_ring.fill) { rrhk_ring.startup_silence += wanted; return; }
        uint64_t now = RRHK_RING_COUNTER(), frequency = RRHK_RING_FREQUENCY();
        if (now < rrhk_ring.deadline) {
            uint32_t silence = (uint32_t)SDL_min((uint64_t)wanted,
                ((rrhk_ring.deadline - now) * rrhk_ring.rate + frequency - 1) / frequency);
            rrhk_ring.startup_silence += silence;
            if (silence == wanted) return;
            stream += silence * stride;
            wanted -= silence;
        }
        rrhk_ring.started = true;
    }
    uint32_t take = SDL_min(wanted, rrhk_ring.fill);
    uint32_t first = SDL_min(take, RRHK_RING_FRAMES - rrhk_ring.read);
    for (unsigned part = 0; part < 2; ++part) {
        uint32_t frames = part ? take - first : first;
        const int16_t *source = rrhk_ring.pcm + (part ? 0 : rrhk_ring.read);
        Uint8 *output = stream + (part ? first : 0) * stride;
        if (rrhk_ring.spec.format == AUDIO_F32SYS) {
            float *target = (float *)output;
            for (uint32_t i = 0; i < frames; ++i) {
                float sample = source[i] / 32768.0f;
                for (uint32_t ch = 0; ch < rrhk_ring.spec.channels; ++ch)
                    target[i * rrhk_ring.spec.channels + ch] = sample;
            }
        } else if (rrhk_ring.spec.channels == 1) {
            memcpy(output, source, frames * sizeof(*source));
        } else {
            int16_t *target = (int16_t *)output;
            for (uint32_t i = 0; i < frames; ++i)
                for (uint32_t ch = 0; ch < rrhk_ring.spec.channels; ++ch)
                    target[i * rrhk_ring.spec.channels + ch] = source[i];
        }
    }
    rrhk_options_audio(stream, take, (int)rrhk_ring.spec.channels, rrhk_ring.spec.format == AUDIO_F32SYS, (int)rrhk_ring.rate);
    rrhk_ring.read = (rrhk_ring.read + take) % RRHK_RING_FRAMES;
    rrhk_ring.fill -= take;
    rrhk_ring.played += take;
    if (take < wanted) {
        rrhk_ring.missing += wanted - take;
        rrhk_ring.started = false;
        rrhk_ring.deadline = 0;
        rr_cushion_gap(&rrhk_ring.cushion);
    } else rr_cushion_clean(&rrhk_ring.cushion, take, rrhk_ring.rate);
}

void rrhk_ring_submit(const int16_t *pcm, uint32_t count) {
    if (!rrhk_ring.id || !count) return;
    SDL_LockAudioDevice(rrhk_ring.id);
    rr_cushion_pushed(&rrhk_ring.cushion);
    uint32_t extra = rr_cushion_frames(&rrhk_ring.cushion, rrhk_ring.rate);
    if (!rrhk_ring.started && !rrhk_ring.fill) {
        uint64_t frequency = RRHK_RING_FREQUENCY();
        rrhk_ring.deadline = RRHK_RING_COUNTER() +
            ((uint64_t)rrhk_ring.spec.samples * frequency + rrhk_ring.rate - 1) / rrhk_ring.rate +
            (frequency * (RRHK_RING_MARGIN_MS + (uint32_t)rr_cushion_ms(&rrhk_ring.cushion)) + 999u) / 1000u;
    }
    rrhk_ring.produced += count;
    /* Normal PAL/NTSC bursts must never discard a whole guest frame. Only
     * trim exceptional catch-up backlogs, retaining the newest timeline. */
    uint32_t keep = SDL_min(RRHK_RING_FRAMES / 2u, rrhk_ring.keep + extra);
    if ((uint64_t)rrhk_ring.fill + count > SDL_min(RRHK_RING_FRAMES, rrhk_ring.limit + extra)) {
        uint32_t discard = rrhk_ring.fill + count - keep;
        uint32_t old = SDL_min(discard, rrhk_ring.fill);
        rrhk_ring.read = (rrhk_ring.read + old) % RRHK_RING_FRAMES;
        rrhk_ring.fill -= old;
        discard -= old;
        pcm += discard; count -= discard;
        rrhk_ring.dropped += old + discard;
        /* A device that stalled while playing: same jitter evidence as a gap. */
        if (rrhk_ring.started) rr_cushion_gap(&rrhk_ring.cushion);
    }
    uint32_t first = SDL_min(count, RRHK_RING_FRAMES - rrhk_ring.write);
    memcpy(rrhk_ring.pcm + rrhk_ring.write, pcm, first * sizeof(*pcm));
    if (count > first) memcpy(rrhk_ring.pcm, pcm + first, (count - first) * sizeof(*pcm));
    rrhk_ring.write = (rrhk_ring.write + count) % RRHK_RING_FRAMES;
    rrhk_ring.fill += count;
    rrhk_ring.peak = SDL_max(rrhk_ring.peak, rrhk_ring.fill);
    SDL_UnlockAudioDevice(rrhk_ring.id);
}

void rrhk_ring_clear(void) {
    rrhk_options_audio_reset();
    if (!rrhk_ring.id) return;
    SDL_LockAudioDevice(rrhk_ring.id);
    rrhk_ring.read = rrhk_ring.write = rrhk_ring.fill = 0;
    rrhk_ring.started = false; rrhk_ring.deadline = 0;
    SDL_UnlockAudioDevice(rrhk_ring.id);
}

void rrhk_ring_close(void) {
    if (rrhk_ring.id && rrhk_ring.produced)
        fprintf(stderr, "[host] audio produced=%llu played=%llu missing=%llu trimmed=%llu reserve=+%d ms (raised %d times); physical latency unmeasured\n",
            (unsigned long long)rrhk_ring.produced, (unsigned long long)rrhk_ring.played,
            (unsigned long long)rrhk_ring.missing, (unsigned long long)rrhk_ring.dropped,
            rr_cushion_ms(&rrhk_ring.cushion), SDL_AtomicGet(&rrhk_ring.cushion.raises));
    if (rrhk_ring.id) SDL_CloseAudioDevice(rrhk_ring.id);
    rrhk_ring.id = 0;
}

/* Opens the device paused at the machine's rate. The caller starts it with rrhk_ring_start()
 * once the machine produces sound. */
bool rrhk_ring_open(unsigned rate) {
    SDL_AudioSpec want = {0}, have = {0};
    memset(&rrhk_ring, 0, sizeof(rrhk_ring));
    rrhk_ring.rate = rate;
    want.freq = (int)rate; want.format = AUDIO_S16SYS;
    want.channels = 2; want.samples = 256; want.callback = rrhk_ring_callback;
    rrhk_ring.id = SDL_OpenAudioDevice(NULL, 0, &want, &have,
        SDL_AUDIO_ALLOW_FORMAT_CHANGE | SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    if (rrhk_ring.id && have.format != AUDIO_S16SYS && have.format != AUDIO_F32SYS) {
        rrhk_ring_close();
        rrhk_ring.id = SDL_OpenAudioDevice(NULL, 0, &want, &have, SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    }
    if (!rrhk_ring.id) return false;
    rrhk_ring.spec = have;
    /* One PAL frame + output period + reserve, plus one catch-up frame.
     * The callback deadline, not this exceptional limit, controls startup. */
    rrhk_ring.keep = rate * (21u + RRHK_RING_MARGIN_MS) / 1000u + have.samples;
    rrhk_ring.limit = SDL_min(RRHK_RING_FRAMES, rrhk_ring.keep + rate * 21u / 1000u);
    rrhk_ring.keep = SDL_min(rrhk_ring.keep, rrhk_ring.limit);
    return true;
}

void rrhk_ring_start(void) {
    if (rrhk_ring.id) SDL_PauseAudioDevice(rrhk_ring.id, 0);
}

SDL_AudioDeviceID rrhk_ring_device(void) { return rrhk_ring.id; }
