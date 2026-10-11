/* Host delivery only: keep every 48 kHz mono APU sample in order.
 * No guest execution, allocation or clock correction in the callback. */
#ifndef RR_NES_AUDIO_COUNTER
#define RR_NES_AUDIO_COUNTER SDL_GetPerformanceCounter
#define RR_NES_AUDIO_FREQUENCY SDL_GetPerformanceFrequency
#endif
#define RR_NES_AUDIO_RATE 48000u
#define RR_NES_AUDIO_RING 8192u
#define RR_NES_AUDIO_MARGIN_MS 30u
static struct {
    SDL_AudioDeviceID id;
    SDL_AudioSpec spec;
    int16_t pcm[RR_NES_AUDIO_RING];
    uint32_t read, write, fill, keep, limit, peak;
    uint64_t deadline, produced, played, dropped, missing, startup_silence;
    bool started;
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
    for (uint32_t i = 0; i < take; ++i) {
        int16_t sample = nes_audio.pcm[(nes_audio.read + i) % RR_NES_AUDIO_RING];
        for (uint32_t ch = 0; ch < nes_audio.spec.channels; ++ch) {
            uint32_t at = i * nes_audio.spec.channels + ch;
            if (nes_audio.spec.format == AUDIO_F32SYS) ((float *)stream)[at] = sample / 32768.0f;
            else ((int16_t *)stream)[at] = sample;
        }
    }
    nes_audio.read = (nes_audio.read + take) % RR_NES_AUDIO_RING;
    nes_audio.fill -= take;
    nes_audio.played += take;
    if (take < wanted) {
        nes_audio.missing += wanted - take;
        nes_audio.started = false;
        nes_audio.deadline = 0;
    }
}

static void nes_audio_submit(const int16_t *pcm, uint32_t count) {
    if (!nes_audio.id || !count) return;
    SDL_LockAudioDevice(nes_audio.id);
    if (!nes_audio.started && !nes_audio.fill) {
        uint64_t frequency = RR_NES_AUDIO_FREQUENCY();
        nes_audio.deadline = RR_NES_AUDIO_COUNTER() +
            ((uint64_t)nes_audio.spec.samples * frequency + RR_NES_AUDIO_RATE - 1) / RR_NES_AUDIO_RATE +
            (frequency * RR_NES_AUDIO_MARGIN_MS + 999u) / 1000u;
    }
    nes_audio.produced += count;
    /* Normal PAL/NTSC bursts must never discard a whole guest frame. Only
     * trim exceptional catch-up backlogs, retaining the newest timeline. */
    if ((uint64_t)nes_audio.fill + count > nes_audio.limit) {
        uint32_t discard = nes_audio.fill + count - nes_audio.keep;
        uint32_t old = SDL_min(discard, nes_audio.fill);
        nes_audio.read = (nes_audio.read + old) % RR_NES_AUDIO_RING;
        nes_audio.fill -= old;
        discard -= old;
        pcm += discard; count -= discard;
        nes_audio.dropped += old + discard;
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
    if (!nes_audio.id) return;
    SDL_LockAudioDevice(nes_audio.id);
    nes_audio.read = nes_audio.write = nes_audio.fill = 0;
    nes_audio.started = false; nes_audio.deadline = 0;
    SDL_UnlockAudioDevice(nes_audio.id);
}

static void nes_audio_close(void) {
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
