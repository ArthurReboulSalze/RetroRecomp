/* Host delivery only: keep every 48 kHz mono APU sample in order.
 * No guest execution, allocation or clock correction in the callback. */
#ifndef RR_NES_AUDIO_COUNTER
#define RR_NES_AUDIO_COUNTER SDL_GetPerformanceCounter
#define RR_NES_AUDIO_FREQUENCY SDL_GetPerformanceFrequency
#endif
#define RR_NES_AUDIO_RATE 48000u
#define RR_NES_AUDIO_RING 8192u
#define RR_NES_AUDIO_MARGIN_MS 30u
#include "audio_cushion.h"
static struct {
    SDL_AudioDeviceID id;
    SDL_AudioSpec spec;
    int16_t pcm[RR_NES_AUDIO_RING];
    uint32_t read, write, fill, keep, limit, peak;
    uint64_t deadline, produced, played, dropped, missing, startup_silence;
    bool started;
    RrAudioCushion cushion;
} nes_audio;

static void SDLCALL nes_audio_callback(void *unused, Uint8 *stream, int bytes) {
    (void)unused;
    memset(stream, 0, (size_t)bytes);
    uint32_t stride = nes_audio.spec.channels * SDL_AUDIO_BITSIZE(nes_audio.spec.format) / 8u;
    uint32_t wanted = (uint32_t)bytes / stride;
    if (!nes_audio.started) {
        if (!nes_audio.fill) { nes_audio.startup_silence += wanted; return; }
        uint64_t now = RR_NES_AUDIO_COUNTER(), frequency = RR_NES_AUDIO_FREQUENCY();
        if (now < nes_audio.deadline) {
            uint32_t silence = (uint32_t)SDL_min((uint64_t)wanted,
                ((nes_audio.deadline - now) * RR_NES_AUDIO_RATE + frequency - 1) / frequency);
            nes_audio.startup_silence += silence;
            if (silence == wanted) return;
            stream += silence * stride;
            wanted -= silence;
        }
        nes_audio.started = true;
    }
    uint32_t take = SDL_min(wanted, nes_audio.fill);
    uint32_t first = SDL_min(take, RR_NES_AUDIO_RING - nes_audio.read);
    for (unsigned part = 0; part < 2; ++part) {
        uint32_t frames = part ? take - first : first;
        const int16_t *source = nes_audio.pcm + (part ? 0 : nes_audio.read);
        Uint8 *output = stream + (part ? first : 0) * stride;
        if (nes_audio.spec.format == AUDIO_F32SYS) {
            float *target = (float *)output;
            for (uint32_t i = 0; i < frames; ++i) {
                float sample = source[i] / 32768.0f;
                for (uint32_t ch = 0; ch < nes_audio.spec.channels; ++ch)
                    target[i * nes_audio.spec.channels + ch] = sample;
            }
        } else if (nes_audio.spec.channels == 1) {
            memcpy(output, source, frames * sizeof(*source));
        } else {
            int16_t *target = (int16_t *)output;
            for (uint32_t i = 0; i < frames; ++i)
                for (uint32_t ch = 0; ch < nes_audio.spec.channels; ++ch)
                    target[i * nes_audio.spec.channels + ch] = source[i];
        }
    }
#ifdef RR_HOST_AUDIO_FILTER
    RR_HOST_AUDIO_FILTER(stream, take, nes_audio.spec.channels, nes_audio.spec.format == AUDIO_F32SYS, RR_NES_AUDIO_RATE);
#endif
    nes_audio.read = (nes_audio.read + take) % RR_NES_AUDIO_RING;
    nes_audio.fill -= take;
    nes_audio.played += take;
    if (take < wanted) {
        nes_audio.missing += wanted - take;
        nes_audio.started = false;
        nes_audio.deadline = 0;
        rr_cushion_gap(&nes_audio.cushion);
    } else rr_cushion_clean(&nes_audio.cushion, take, RR_NES_AUDIO_RATE);
}

static void nes_audio_submit(const int16_t *pcm, uint32_t count) {
    if (!nes_audio.id || !count) return;
    SDL_LockAudioDevice(nes_audio.id);
    rr_cushion_pushed(&nes_audio.cushion);
    uint32_t extra = rr_cushion_frames(&nes_audio.cushion, RR_NES_AUDIO_RATE);
    if (!nes_audio.started && !nes_audio.fill) {
        uint64_t frequency = RR_NES_AUDIO_FREQUENCY();
        nes_audio.deadline = RR_NES_AUDIO_COUNTER() +
            ((uint64_t)nes_audio.spec.samples * frequency + RR_NES_AUDIO_RATE - 1) / RR_NES_AUDIO_RATE +
            (frequency * (RR_NES_AUDIO_MARGIN_MS + (uint32_t)rr_cushion_ms(&nes_audio.cushion)) + 999u) / 1000u;
    }
    nes_audio.produced += count;
    /* Normal PAL/NTSC bursts must never discard a whole guest frame. Only
     * trim exceptional catch-up backlogs, retaining the newest timeline. */
    uint32_t keep = SDL_min(RR_NES_AUDIO_RING / 2u, nes_audio.keep + extra);
    if ((uint64_t)nes_audio.fill + count > SDL_min(RR_NES_AUDIO_RING, nes_audio.limit + extra)) {
        uint32_t discard = nes_audio.fill + count - keep;
        uint32_t old = SDL_min(discard, nes_audio.fill);
        nes_audio.read = (nes_audio.read + old) % RR_NES_AUDIO_RING;
        nes_audio.fill -= old;
        discard -= old;
        pcm += discard; count -= discard;
        nes_audio.dropped += old + discard;
        /* A device that stalled while playing: same jitter evidence as a gap. */
        if (nes_audio.started) rr_cushion_gap(&nes_audio.cushion);
    }
    uint32_t first = SDL_min(count, RR_NES_AUDIO_RING - nes_audio.write);
    memcpy(nes_audio.pcm + nes_audio.write, pcm, first * sizeof(*pcm));
    if (count > first) memcpy(nes_audio.pcm, pcm + first, (count - first) * sizeof(*pcm));
    nes_audio.write = (nes_audio.write + count) % RR_NES_AUDIO_RING;
    nes_audio.fill += count;
    nes_audio.peak = SDL_max(nes_audio.peak, nes_audio.fill);
    SDL_UnlockAudioDevice(nes_audio.id);
}

static void nes_audio_clear(void) {
#ifdef RR_HOST_AUDIO_RESET
    RR_HOST_AUDIO_RESET();
#endif
    if (!nes_audio.id) return;
    SDL_LockAudioDevice(nes_audio.id);
    nes_audio.read = nes_audio.write = nes_audio.fill = 0;
    nes_audio.started = false; nes_audio.deadline = 0;
    SDL_UnlockAudioDevice(nes_audio.id);
}

static void nes_audio_close(void) {
    if (nes_audio.id && nes_audio.produced)
        fprintf(stderr, "[host] audio produced=%llu played=%llu missing=%llu trimmed=%llu reserve=+%d ms (raised %d times)\n",
            (unsigned long long)nes_audio.produced, (unsigned long long)nes_audio.played,
            (unsigned long long)nes_audio.missing, (unsigned long long)nes_audio.dropped,
            rr_cushion_ms(&nes_audio.cushion), SDL_AtomicGet(&nes_audio.cushion.raises));
    if (nes_audio.id) SDL_CloseAudioDevice(nes_audio.id);
    nes_audio.id = 0;
}

static bool nes_audio_open(void) {
    SDL_AudioSpec want = {0}, have = {0};
    memset(&nes_audio, 0, sizeof(nes_audio));
    want.freq = RR_NES_AUDIO_RATE; want.format = AUDIO_S16SYS;
    want.channels = 2; want.samples = 256; want.callback = nes_audio_callback;
    nes_audio.id = SDL_OpenAudioDevice(NULL, 0, &want, &have,
        SDL_AUDIO_ALLOW_FORMAT_CHANGE | SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    if (nes_audio.id && have.format != AUDIO_S16SYS && have.format != AUDIO_F32SYS) {
        nes_audio_close();
        nes_audio.id = SDL_OpenAudioDevice(NULL, 0, &want, &have, SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    }
    if (!nes_audio.id) return false;
    nes_audio.spec = have;
    /* One PAL frame + output period + reserve, plus one catch-up frame.
     * The callback deadline, not this exceptional limit, controls startup. */
    nes_audio.keep = RR_NES_AUDIO_RATE * (21u + RR_NES_AUDIO_MARGIN_MS) / 1000u + have.samples;
    nes_audio.limit = SDL_min(RR_NES_AUDIO_RING, nes_audio.keep + RR_NES_AUDIO_RATE * 21u / 1000u);
    nes_audio.keep = SDL_min(nes_audio.keep, nes_audio.limit);
    return true; /* Paused until the caller enables the APU. */
}
