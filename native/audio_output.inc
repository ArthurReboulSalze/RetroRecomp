/* Host-only audio: causal band-limited SRC and a bounded stereo callback ring.
 * The PSG, guest cycles, frame pacing, WAV sink and cartridge stay unchanged.
 * The callback consumes PCM only; it never runs the CPU or polls inputs.
 */
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "stereo_fir.h"
#include "audio_cushion.h"

#define RR_AUDIO_RING_FRAMES 8192u
#define RR_AUDIO_TARGET_MS 21u /* Cover one PAL frame plus the device period. */
#define RR_AUDIO_BURST_MS 21u /* One PAL frame, rounded up. */
#define RR_AUDIO_JITTER_MS 3u
#define RR_AUDIO_TAPS 256u
#define RR_AUDIO_PHASES 128u
/* The host may ask for an output device by name (RR_HOST_AUDIO_DEVICE) and tell that the speed is not 100%
 * (RR_HOST_AUDIO_HELD: the sound is dropped, not converted nor played). */
#ifndef RR_HOST_AUDIO_DEVICE
#define RR_HOST_AUDIO_DEVICE() ((const char *)NULL)
#endif
#ifndef RR_AUDIO_COUNTER
#define RR_AUDIO_COUNTER SDL_GetPerformanceCounter
#define RR_AUDIO_FREQUENCY SDL_GetPerformanceFrequency
#endif

static struct {
    SDL_AudioSpec device;
    uint32_t read, write, fill, keep, high_water;
    uint64_t start_counter;
    bool started;
    int16_t pcm[RR_AUDIO_RING_FRAMES * 2];
    uint64_t produced, played, dropped, underrun, startup_silence;
    uint32_t peak;
    uint32_t source_rate, phase, history_pos;
    int16_t history[RR_AUDIO_TAPS * 2];
    float coefficients[RR_AUDIO_PHASES][RR_AUDIO_TAPS];
    RrAudioCushion cushion;
} rr_audio;

/* The device the player asked for, or the system default when there is none or it cannot be opened. */
static SDL_AudioDeviceID audio_open_device(const SDL_AudioSpec *want, SDL_AudioSpec *have, int flags) {
    const char *name = RR_HOST_AUDIO_DEVICE();
    SDL_AudioDeviceID id = name ? SDL_OpenAudioDevice(name, 0, want, have, flags) : 0;
    if (name && !id) fprintf(stderr, "[host] audio device '%s' cannot be opened: %s; using the system default\n", name, SDL_GetError());
    return id ? id : SDL_OpenAudioDevice(NULL, 0, want, have, flags);
}

static uint32_t audio_ms_frames(uint32_t ms) {
    return (uint32_t)(((uint64_t)rr_audio.device.freq * ms + 999u) / 1000u);
}

static void audio_discard(uint32_t frames) {
    rr_audio.read = (rr_audio.read + frames) % RR_AUDIO_RING_FRAMES;
    rr_audio.fill -= frames;
    rr_audio.dropped += frames;
}

/* Called under SDL's callback/device lock. No allocation or blocking work. */
static void SDLCALL audio_callback(void *unused, Uint8 *output, int bytes) {
    (void)unused;
    memset(output, 0, (size_t)bytes);
    uint32_t frame_bytes = 2u * (SDL_AUDIO_BITSIZE(rr_audio.device.format) / 8u);
    uint32_t wanted = (uint32_t)bytes / frame_bytes;
    if (!rr_audio.started) {
        if (!rr_audio.fill) {
            rr_audio.startup_silence += wanted;
            return;
        }
        /* Start at a fixed time after the first PCM arrives, including within
         * a callback. Waiting for a whole second video frame adds an arbitrary
         * PAL/NTSC frame of lag. One device period plus scheduling headroom
         * covers the burst producer without that extra frame-sized wait. */
        uint64_t now = RR_AUDIO_COUNTER(), frequency = RR_AUDIO_FREQUENCY();
        if (now < rr_audio.start_counter) {
            uint32_t silence = (uint32_t)SDL_min((uint64_t)wanted,
                ((rr_audio.start_counter - now) * rr_audio.device.freq + frequency - 1) / frequency);
            rr_audio.startup_silence += silence;
            if (silence == wanted) return;
            output += silence * frame_bytes;
            wanted -= silence;
        }
        rr_audio.started = true;
    }
    uint32_t taken = SDL_min(wanted, rr_audio.fill);
    if (rr_audio.device.format == AUDIO_F32SYS) {
        float *destination = (float *)output;
        for (uint32_t i = 0; i < taken; ++i) {
            uint32_t position = (rr_audio.read + i) % RR_AUDIO_RING_FRAMES;
            destination[i * 2u] = rr_audio.pcm[position * 2u] / 32768.0f;
            destination[i * 2u + 1u] = rr_audio.pcm[position * 2u + 1u] / 32768.0f;
        }
    } else {
        uint32_t first = SDL_min(taken, RR_AUDIO_RING_FRAMES - rr_audio.read);
        memcpy(output, rr_audio.pcm + rr_audio.read * 2u, first * frame_bytes);
        if (taken > first)
            memcpy(output + first * frame_bytes, rr_audio.pcm, (taken - first) * frame_bytes);
    }
#ifdef RR_HOST_AUDIO_FILTER
    RR_HOST_AUDIO_FILTER(output, taken, 2, rr_audio.device.format == AUDIO_F32SYS, rr_audio.device.freq);
#endif
    rr_audio.read = (rr_audio.read + taken) % RR_AUDIO_RING_FRAMES;
    rr_audio.fill -= taken;
    rr_audio.played += taken;
    if (taken < wanted) {
        rr_audio.underrun += wanted - taken;
        rr_audio.started = false; /* Re-prime after a real CPU/device stall. */
        rr_cushion_gap(&rr_audio.cushion);
    } else rr_cushion_clean(&rr_audio.cushion, taken, (Uint32)rr_audio.device.freq);
}

/* Main thread only. Serialization also makes trimming the oldest PCM safe. */
static void audio_push(const int16_t *samples, uint32_t count) {
    if (!count) return;
    SDL_LockAudioDevice(audio_device);
    rr_cushion_pushed(&rr_audio.cushion);
    uint32_t extra = rr_cushion_frames(&rr_audio.cushion, (Uint32)rr_audio.device.freq);
    if (!rr_audio.started && !rr_audio.fill) {
        uint64_t frequency = RR_AUDIO_FREQUENCY();
        rr_audio.start_counter = RR_AUDIO_COUNTER() +
            ((uint64_t)rr_audio.device.samples * frequency + rr_audio.device.freq - 1) / rr_audio.device.freq +
            (frequency * (RR_AUDIO_JITTER_MS + (uint32_t)rr_cushion_ms(&rr_audio.cushion)) + 999u) / 1000u;
    }
    rr_audio.produced += count;
    uint32_t keep = SDL_min(RR_AUDIO_RING_FRAMES / 2u, rr_audio.keep + extra);
    if (rr_audio.fill + count > SDL_min(RR_AUDIO_RING_FRAMES, rr_audio.high_water + extra)) {
        uint32_t discard = rr_audio.fill + count - keep;
        uint32_t old = SDL_min(discard, rr_audio.fill);
        audio_discard(old);
        discard -= old;
        samples += discard * 2u;
        count -= discard;
        rr_audio.dropped += discard;
        /* A device that stalled while playing: same jitter evidence as a gap. */
        if (rr_audio.started) rr_cushion_gap(&rr_audio.cushion);
    }
    uint32_t first = SDL_min(count, RR_AUDIO_RING_FRAMES - rr_audio.write);
    memcpy(rr_audio.pcm + rr_audio.write * 2u, samples, first * 2u * sizeof(int16_t));
    if (count > first)
        memcpy(rr_audio.pcm, samples + first * 2u, (count - first) * 2u * sizeof(int16_t));
    rr_audio.write = (rr_audio.write + count) % RR_AUDIO_RING_FRAMES;
    rr_audio.fill += count;
    rr_audio.peak = SDL_max(rr_audio.peak, rr_audio.fill);
    SDL_UnlockAudioDevice(audio_device);
}

static void audio_resampler_init(uint32_t source_rate) {
    const double pi = 3.14159265358979323846;
    const double cutoff = .45 * SDL_min(1.0, (double)rr_audio.device.freq / source_rate);
    rr_audio.source_rate = source_rate;
    for (uint32_t phase = 0; phase < RR_AUDIO_PHASES; ++phase) {
        double sum = 0.0;
        for (uint32_t tap = 0; tap < RR_AUDIO_TAPS; ++tap) {
            double x = (double)tap - (RR_AUDIO_TAPS - 1) * .5 - (double)phase / RR_AUDIO_PHASES;
            double sinc = fabs(x) < 1e-12 ? 2.0 * cutoff : sin(2.0 * pi * cutoff * x) / (pi * x);
            double angle = 2.0 * pi * tap / (RR_AUDIO_TAPS - 1);
            double weight = .42 - .5 * cos(angle) + .08 * cos(2.0 * angle);
            rr_audio.coefficients[phase][tap] = (float)(sinc * weight);
            sum += sinc * weight;
        }
        for (uint32_t tap = 0; tap < RR_AUDIO_TAPS; ++tap)
            rr_audio.coefficients[phase][tap] = (float)(rr_audio.coefficients[phase][tap] / sum);
    }
}

static void audio_output_clear(void) {
#ifdef RR_HOST_AUDIO_RESET
    RR_HOST_AUDIO_RESET();
#endif
    if (!audio_device) return;
    SDL_LockAudioDevice(audio_device);
    rr_audio.read = rr_audio.write = rr_audio.fill = 0;
    rr_audio.started = false;
    rr_audio.start_counter = 0;
    rr_audio.phase = rr_audio.history_pos = 0;
    memset(rr_audio.history, 0, sizeof(rr_audio.history));
    SDL_UnlockAudioDevice(audio_device);
}

bool host_audio_init(uint32_t rate) {
    if (!rate || SDL_InitSubSystem(SDL_INIT_AUDIO) != 0) return false;
    SDL_AudioSpec want; SDL_zero(want);
    want.freq = 48000; want.format = AUDIO_S16SYS; want.channels = 2; want.samples = 256;
    want.callback = audio_callback;
    memset(&rr_audio, 0, sizeof(rr_audio));
    /* Consume in the backend's native format/period. WASAPI usually requests
     * float PCM: forcing S16 makes SDL stage another converted output block. */
    audio_device = audio_open_device(&want, &rr_audio.device,
        SDL_AUDIO_ALLOW_FREQUENCY_CHANGE | SDL_AUDIO_ALLOW_SAMPLES_CHANGE | SDL_AUDIO_ALLOW_FORMAT_CHANGE);
    if (!audio_device) return false;
    if (rr_audio.device.format != AUDIO_S16SYS && rr_audio.device.format != AUDIO_F32SYS) {
        SDL_CloseAudioDevice(audio_device);
        /* Less common formats retain SDL's established conversion fallback. */
        audio_device = audio_open_device(&want, &rr_audio.device,
            SDL_AUDIO_ALLOW_FREQUENCY_CHANGE | SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
        if (!audio_device) return false;
    }
    if (rr_audio.device.channels != 2 || rr_audio.device.freq <= 0) {
        SDL_CloseAudioDevice(audio_device); audio_device = 0;
        return false;
    }
    /* Bound abnormal backlogs separately from startup scheduling. */
    rr_audio.keep = SDL_min(RR_AUDIO_RING_FRAMES / 2u,
        audio_ms_frames(RR_AUDIO_TARGET_MS) + rr_audio.device.samples);
    rr_audio.high_water = SDL_min(RR_AUDIO_RING_FRAMES,
        rr_audio.keep + audio_ms_frames(RR_AUDIO_BURST_MS) + rr_audio.device.samples);
    audio_resampler_init(rate);
    SDL_PauseAudioDevice(audio_device, 0);
    fprintf(stderr, "[host] audio driver=%s, %d Hz, %u samples, format=%s, startup=%.1f ms limit=%.1f ms; physical latency unmeasured\n",
        SDL_GetCurrentAudioDriver(), rr_audio.device.freq, rr_audio.device.samples,
        rr_audio.device.format == AUDIO_F32SYS ? "F32" : "S16",
        rr_audio.device.samples * 1000.0 / rr_audio.device.freq + RR_AUDIO_JITTER_MS,
        rr_audio.high_water * 1000.0 / rr_audio.device.freq);
    return true;
}

void host_audio_submit(const int16_t *samples, size_t count) {
    if (!audio_device || !samples || !count) return;
#ifdef RR_HOST_AUDIO_HELD
    if (RR_HOST_AUDIO_HELD()) return;
#endif
    /* Conversion stays on the producer thread. A short causal FIR avoids
     * SDL_AudioStream's future-sample padding at the PSG's ~223 kHz rate. */
    if (rr_audio.source_rate == (uint32_t)rr_audio.device.freq) {
        while (count) {
            uint32_t chunk = (uint32_t)SDL_min(count, 1024u);
            audio_push(samples, chunk); samples += chunk * 2u; count -= chunk;
        }
        return;
    }
    int16_t output[1024 * 2]; uint32_t pending = 0;
    while (count--) {
        rr_audio.history_pos = (rr_audio.history_pos + 1u) % RR_AUDIO_TAPS;
        rr_audio.history[rr_audio.history_pos * 2u] = *samples++;
        rr_audio.history[rr_audio.history_pos * 2u + 1u] = *samples++;
        rr_audio.phase += (uint32_t)rr_audio.device.freq;
        while (rr_audio.phase >= rr_audio.source_rate) {
            rr_audio.phase -= rr_audio.source_rate;
            uint32_t phase = (uint32_t)((uint64_t)rr_audio.phase * RR_AUDIO_PHASES / rr_audio.device.freq);
            phase = SDL_min(phase, RR_AUDIO_PHASES - 1u);
            double left, right;
            rr_stereo_fir(rr_audio.history,rr_audio.history_pos,
                rr_audio.coefficients[phase],RR_AUDIO_TAPS,&left,&right);
            output[pending * 2u] = (int16_t)SDL_clamp((int)lrint(left), -32768, 32767);
            output[pending * 2u + 1u] = (int16_t)SDL_clamp((int)lrint(right), -32768, 32767);
            if (++pending == 1024u) { audio_push(output, pending); pending = 0; }
        }
    }
    audio_push(output, pending);
}

/* The id SDL gave the device (0 without one): the host tells which device an SDL_AUDIODEVICEREMOVED is about. */
SDL_AudioDeviceID host_audio_device_id(void) { return audio_device; }

/* The player chose another output device: the same stream on the new one, from an empty ring. false: none could be opened. */
bool host_audio_reopen(void) {
    if (!audio_device) return false;
    const uint32_t rate = rr_audio.source_rate;
    SDL_CloseAudioDevice(audio_device); audio_device = 0;
    const bool opened = host_audio_init(rate);
    SDL_QuitSubSystem(SDL_INIT_AUDIO);      /* host_audio_init started the subsystem once more: the count stays what it was */
    return opened;
}

void host_audio_shutdown(void) {
    if (!audio_device) return;
    SDL_CloseAudioDevice(audio_device); audio_device = 0;
    fprintf(stderr, "[host] audio produced=%llu played=%llu trimmed=%llu underrun=%llu peak=%u frames"
        " reserve=+%d ms (raised %d times)\n",
        (unsigned long long)rr_audio.produced, (unsigned long long)rr_audio.played,
        (unsigned long long)rr_audio.dropped, (unsigned long long)rr_audio.underrun, rr_audio.peak,
        rr_cushion_ms(&rr_audio.cushion), SDL_AtomicGet(&rr_audio.cushion.raises));
}
