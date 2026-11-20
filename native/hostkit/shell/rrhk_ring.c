/* Callback-ring audio output (HOST_KIT.md decision D5, the model of the NES host): the machine's
 * 16-bit PCM at its own rate, mono (the NES) or interleaved stereo (the Game Boy), is kept in order
 * in a ring and the device callback converts it to the device format (S16 or F32, two channels).
 * No guest execution, allocation or clock correction in the callback. The adaptive reserve
 * (audio_cushion.h) sets when a device period may start. This file is the NES host's former
 * nes_audio_output.inc, unchanged in its logic for a mono source; a machine selects it with
 * audio_model = RRHK_AUDIO_RING. */
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
#define RRHK_RING_MARGIN_MS 30u        /* the start margin of a machine that states none (RrhkMachine.audio_margin_ms) */

static struct {
    SDL_AudioDeviceID id;
    SDL_AudioSpec spec;
    int16_t pcm[RRHK_RING_FRAMES * 2];     /* frames of `source` interleaved channels */
    uint32_t rate, source, margin, read, write, fill, keep, limit, peak;
    uint64_t deadline, produced, played, dropped, missing, startup_silence;
    /* What a player hears as a crackle, counted (never by ear): the gaps (a device period that found the ring short), the trims
     * (sound thrown away because the ring was too full) and the clears (the sound waiting thrown away by rrhk_ring_clear: a
     * pause, a menu, a load, and before 1.8.1 every multiplayer iteration whose frame had not come yet). */
    uint64_t gaps, trims, clears, cleared;
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
        const int16_t *source = rrhk_ring.pcm + (part ? 0 : rrhk_ring.read) * rrhk_ring.source;
        Uint8 *output = stream + (part ? first : 0) * stride;
        if (rrhk_ring.source == 2) {
            /* Interleaved stereo from the machine to the two device channels. */
            if (rrhk_ring.spec.format == AUDIO_F32SYS) {
                float *target = (float *)output;
                for (uint32_t i = 0; i < frames * 2u; ++i) target[i] = source[i] / 32768.0f;
            } else memcpy(output, source, frames * 2u * sizeof(*source));
        } else if (rrhk_ring.spec.format == AUDIO_F32SYS) {
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
        ++rrhk_ring.gaps;
        rrhk_ring.started = false;
        rrhk_ring.deadline = 0;
        rr_cushion_gap(&rrhk_ring.cushion);
    } else rr_cushion_clean(&rrhk_ring.cushion, take, rrhk_ring.rate);
}

/* The ring is always regulated (1.8.1, Arthur's yes of 19 November 2026): every block goes through the resampler of D30 at
 * `ring_base` (machine_hz / refresh_hz while the game is locked to the display, 1 + ppm in a multiplayer session, else 1.0) and a
 * correction of at most 0.5 % from its fill against the target (its start reserve plus half a frame, 8 ms), so the fill comes
 * back to the target instead of drifting, with the clocks of the PC and of the sound card, to a trim or a gap. Before 1.8.1 a
 * ring at 1.0 was not resampled (byte for byte the machine's PCM), and the drift and the bursts after a late frame were heard as
 * crackles (Tekken 3 on a laptop). The resampler is never restarted by a change of base (a restart repeats a sample), only by a
 * clear. The trim bound has RRHK_RING_ROOM_MS more room (a burst of two or three frames no longer throws sound away) and a trim
 * no longer raises the reserve (it says the ring was too full, not too short). */
#define RRHK_RING_ROOM_MS 80u
static double ring_base = 1.0;
static RrDrcResampler ring_drc;
void rrhk_ring_set_base(double base) { ring_base = base; }

/* `count` frames of the machine's PCM: that many samples when it is mono, twice as many int16 values when it is stereo. */
void rrhk_ring_submit(const int16_t *pcm, uint32_t count) {
    static int16_t stretched[(4096 + 4096 / 20 + 8) * 2];
    if (!rrhk_ring.id || !count) return;
    SDL_LockAudioDevice(rrhk_ring.id);
    const double target = (double)rrhk_ring.spec.samples +
        (double)rrhk_ring.rate * (rrhk_ring.margin + (uint32_t)rr_cushion_ms(&rrhk_ring.cushion) + 8u) / 1000.0;
    count = (uint32_t)rr_drc_resample(&ring_drc, pcm, SDL_min(count, 4096u), (int)rrhk_ring.source,
                                      rr_drc_ratio(ring_base, (double)rrhk_ring.fill, target), stretched,
                                      sizeof stretched / sizeof stretched[0] / rrhk_ring.source);
    pcm = stretched;
    if (!count) { SDL_UnlockAudioDevice(rrhk_ring.id); return; }
    rr_cushion_pushed(&rrhk_ring.cushion);
    uint32_t extra = rr_cushion_frames(&rrhk_ring.cushion, rrhk_ring.rate);
    if (!rrhk_ring.started && !rrhk_ring.fill) {
        uint64_t frequency = RRHK_RING_FREQUENCY();
        rrhk_ring.deadline = RRHK_RING_COUNTER() +
            ((uint64_t)rrhk_ring.spec.samples * frequency + rrhk_ring.rate - 1) / rrhk_ring.rate +
            (frequency * (rrhk_ring.margin + (uint32_t)rr_cushion_ms(&rrhk_ring.cushion)) + 999u) / 1000u;
    }
    rrhk_ring.produced += count;
    /* Normal PAL/NTSC bursts must never discard a whole guest frame. Only
     * trim exceptional catch-up backlogs, retaining the newest timeline. */
    uint32_t keep = SDL_min(RRHK_RING_FRAMES / 2u, rrhk_ring.keep + extra);
    const uint32_t room = rrhk_ring.rate * RRHK_RING_ROOM_MS / 1000u;
    if ((uint64_t)rrhk_ring.fill + count > SDL_min(RRHK_RING_FRAMES, rrhk_ring.limit + extra + room)) {
        uint32_t discard = rrhk_ring.fill + count - keep;
        uint32_t old = SDL_min(discard, rrhk_ring.fill);
        rrhk_ring.read = (rrhk_ring.read + old) % RRHK_RING_FRAMES;
        rrhk_ring.fill -= old;
        discard -= old;
        pcm += discard * rrhk_ring.source; count -= discard;
        rrhk_ring.dropped += old + discard;
        ++rrhk_ring.trims;
    }
    uint32_t first = SDL_min(count, RRHK_RING_FRAMES - rrhk_ring.write);
    memcpy(rrhk_ring.pcm + rrhk_ring.write * rrhk_ring.source, pcm, first * rrhk_ring.source * sizeof(*pcm));
    if (count > first) memcpy(rrhk_ring.pcm, pcm + first * rrhk_ring.source, (count - first) * rrhk_ring.source * sizeof(*pcm));
    rrhk_ring.write = (rrhk_ring.write + count) % RRHK_RING_FRAMES;
    rrhk_ring.fill += count;
    rrhk_ring.peak = SDL_max(rrhk_ring.peak, rrhk_ring.fill);
    SDL_UnlockAudioDevice(rrhk_ring.id);
}

void rrhk_ring_clear(void) {
    rrhk_options_audio_reset();
    if (!rrhk_ring.id) return;
    SDL_LockAudioDevice(rrhk_ring.id);
    if (rrhk_ring.fill) { ++rrhk_ring.clears; rrhk_ring.cleared += rrhk_ring.fill; }
    rrhk_ring.read = rrhk_ring.write = rrhk_ring.fill = 0;
    rrhk_ring.started = false; rrhk_ring.deadline = 0;
    memset(&ring_drc, 0, sizeof ring_drc);
    SDL_UnlockAudioDevice(rrhk_ring.id);
}

void rrhk_ring_close(void) {
    if (rrhk_ring.id && rrhk_ring.produced)
        fprintf(stderr, "[host] audio produced=%llu played=%llu missing=%llu trimmed=%llu cleared=%llu (gaps %llu, trims %llu, clears %llu) "
            "device period %u, reserve=+%d ms (raised %d times); physical latency unmeasured\n",
            (unsigned long long)rrhk_ring.produced, (unsigned long long)rrhk_ring.played,
            (unsigned long long)rrhk_ring.missing, (unsigned long long)rrhk_ring.dropped, (unsigned long long)rrhk_ring.cleared,
            (unsigned long long)rrhk_ring.gaps, (unsigned long long)rrhk_ring.trims, (unsigned long long)rrhk_ring.clears,
            (unsigned)rrhk_ring.spec.samples, rr_cushion_ms(&rrhk_ring.cushion), SDL_AtomicGet(&rrhk_ring.cushion.raises));
    if (rrhk_ring.id) SDL_CloseAudioDevice(rrhk_ring.id);
    rrhk_ring.id = 0;
}

/* Opens the output device the player asked for (rrhk_audio_device(); the system default when it is none or cannot be opened),
 * paused, in the machine's rate. */
static SDL_AudioDeviceID open_device(const SDL_AudioSpec *want, SDL_AudioSpec *have, int flags) {
    const char *name = rrhk_audio_device();
    SDL_AudioDeviceID id = name ? SDL_OpenAudioDevice(name, 0, want, have, flags) : 0;
    if (name && !id) fprintf(stderr, "[host] audio device '%s' cannot be opened: %s; using the system default\n", name, SDL_GetError());
    return id ? id : SDL_OpenAudioDevice(NULL, 0, want, have, flags);
}

static bool open_ring_device(void) {
    SDL_AudioSpec want = {0}, have = {0};
    want.freq = (int)rrhk_ring.rate; want.format = AUDIO_S16SYS;
    want.channels = 2; want.samples = 256; want.callback = rrhk_ring_callback;
    rrhk_ring.id = open_device(&want, &have, SDL_AUDIO_ALLOW_FORMAT_CHANGE | SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    if (rrhk_ring.id && have.format != AUDIO_S16SYS && have.format != AUDIO_F32SYS) {
        SDL_CloseAudioDevice(rrhk_ring.id);
        rrhk_ring.id = open_device(&want, &have, SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    }
    if (!rrhk_ring.id) return false;
    rrhk_ring.spec = have;
    /* One PAL frame + output period + reserve, plus one catch-up frame.
     * The callback deadline, not this exceptional limit, controls startup. */
    rrhk_ring.keep = rrhk_ring.rate * (21u + rrhk_ring.margin) / 1000u + have.samples;
    rrhk_ring.limit = SDL_min(RRHK_RING_FRAMES, rrhk_ring.keep + rrhk_ring.rate * 21u / 1000u);
    rrhk_ring.keep = SDL_min(rrhk_ring.keep, rrhk_ring.limit);
    return true;
}

/* Opens the device paused at the machine's rate. `channels` is 1 or 2 (0: mono), `margin_ms` the start margin
 * (0: 30 ms). The caller starts it with rrhk_ring_start() once the machine produces sound. */
bool rrhk_ring_open(unsigned rate, unsigned channels, unsigned margin_ms) {
    memset(&rrhk_ring, 0, sizeof(rrhk_ring));
    rrhk_ring.rate = rate;
    rrhk_ring.source = channels == 2 ? 2 : 1;
    rrhk_ring.margin = margin_ms ? margin_ms : RRHK_RING_MARGIN_MS;
    return open_ring_device();
}

/* The player chose another output (decision D12): the same ring, the same reserve, on the new device. The sound that was
 * waiting is dropped. false: no device could be opened (the ring is closed). */
bool rrhk_ring_reopen(void) {
    if (!rrhk_ring.id) return false;
    SDL_CloseAudioDevice(rrhk_ring.id);
    rrhk_ring.id = 0;
    rrhk_ring.read = rrhk_ring.write = rrhk_ring.fill = 0;
    rrhk_ring.started = false; rrhk_ring.deadline = 0;
    memset(&ring_drc, 0, sizeof ring_drc);
    if (!open_ring_device()) return false;
    SDL_PauseAudioDevice(rrhk_ring.id, 0);
    return true;
}

void rrhk_ring_start(void) {
    if (rrhk_ring.id) SDL_PauseAudioDevice(rrhk_ring.id, 0);
}

SDL_AudioDeviceID rrhk_ring_device(void) { return rrhk_ring.id; }
