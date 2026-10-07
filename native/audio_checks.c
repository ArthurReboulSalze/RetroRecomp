/* Authored numeric sound tests. No ROM, video, screenshots or audible sound. */
#undef NDEBUG
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
static SDL_AudioDeviceID audio_device;
#include "audio_output.inc"

static void reset_test(uint32_t source_rate, int output_rate) {
    audio_output_clear();
    rr_audio.produced = rr_audio.played = rr_audio.dropped = rr_audio.underrun = 0;
    rr_audio.startup_silence = rr_audio.peak = 0;
    rr_audio.device.freq = output_rate;
    rr_audio.keep = audio_ms_frames(RR_AUDIO_TARGET_MS) + rr_audio.device.samples;
    rr_audio.start_threshold = rr_audio.keep;
    rr_audio.high_water = rr_audio.keep + audio_ms_frames(RR_AUDIO_BURST_MS) + rr_audio.device.samples;
    audio_resampler_init(source_rate);
}

/* Drain the conversion's FIFO without startup priming, to inspect its PCM. */
static size_t capture(int16_t *output) {
    SDL_LockAudioDevice(audio_device);
    size_t count = rr_audio.fill;
    for (size_t i = 0; i < count; ++i) {
        uint32_t pos = (rr_audio.read + (uint32_t)i) % RR_AUDIO_RING_FRAMES;
        output[i * 2] = rr_audio.pcm[pos * 2];
        output[i * 2 + 1] = rr_audio.pcm[pos * 2 + 1];
    }
    rr_audio.read = (rr_audio.read + (uint32_t)count) % RR_AUDIO_RING_FRAMES;
    rr_audio.fill = 0;
    SDL_UnlockAudioDevice(audio_device);
    return count;
}

static size_t convert(const int16_t *input, size_t count, uint32_t rate,
                      int output_rate, size_t chunk, int16_t *output) {
    reset_test(rate, output_rate);
    size_t produced = 0;
    for (size_t offset = 0; offset < count; offset += chunk) {
        host_audio_submit(input + offset * 2, SDL_min(chunk, count - offset));
        produced += capture(output + produced * 2);
    }
    assert(!rr_audio.dropped);
    assert(produced == (uint64_t)count * output_rate / rate);
    return produced;
}

static void conversion_checks(void) {
    const size_t count = 223721;
    int16_t *input = calloc(count * 2, sizeof(int16_t));
    int16_t *a = calloc(count * 2, sizeof(int16_t));
    int16_t *b = calloc(count * 2, sizeof(int16_t));
    assert(input && a && b);
    for (size_t i = 0; i < count; ++i) {
        input[i * 2] = (int16_t)(12000 * sin(i * .031));
        input[i * 2 + 1] = (int16_t)(9000 * cos(i * .017));
    }
    Uint64 start = SDL_GetPerformanceCounter();
    size_t length = convert(input, count, 223721, 48000, 2048, a);
    double ms = (SDL_GetPerformanceCounter() - start) * 1000.0 / SDL_GetPerformanceFrequency();
    assert(length == 48000);
    assert(convert(input, count, 223721, 48000, 127, b) == length);
    assert(!memcmp(a, b, length * 2 * sizeof(int16_t)));
    assert(convert(input, 221680, 221680, 48000, 37, b) == 48000);
    assert(convert(input, count, 223721, 44100, 2048, b) == 44100);
    printf("conversion: exact NTSC/PAL duration, 44.1/48 kHz, chunk independence; %.3f ms per second of PCM\n", ms);
    // Short causal delay: an impulse starts producing output in the first block.
    memset(input, 0, count * 2 * sizeof(int16_t)); input[0] = 30000;
    length = convert(input, 512, 223721, 48000, 128, a);
    int peak = 0; size_t peak_index = 0;
    for (size_t i = 0; i < length; ++i) {
        assert(a[i * 2 + 1] == 0); // GG stereo must not leak into the other channel.
        if (abs(a[i * 2]) > peak) { peak = abs(a[i * 2]); peak_index = i; }
    }
    assert(peak > 1000 && peak_index <= 32);
    printf("impulse: peak at output sample %zu (%.3f ms), right channel silent\n", peak_index, peak_index * 1000.0 / 48000);
    // A DC input must retain amplitude and polarity after the FIR settles.
    for (size_t i = 0; i < 1024; ++i) { input[i * 2] = 20000; input[i * 2 + 1] = -18000; }
    length = convert(input, 1024, 223721, 48000, 17, a);
    for (size_t i = 64; i < length; ++i) {
        assert(abs(a[i * 2] - 20000) <= 1 && abs(a[i * 2 + 1] + 18000) <= 1);
    }
    // Audible tones pass; ultrasonic PSG content must not alias into the output.
    const double frequencies[] = {1000, 10000, 18000, 26000, 70000};
    double gains[5];
    for (int tone = 0; tone < 5; ++tone) {
        for (size_t i = 0; i < 40000; ++i) {
            input[i * 2] = (int16_t)lrint(12000 * sin(2 * 3.141592653589793 * frequencies[tone] * i / 223721));
            input[i * 2 + 1] = 0;
        }
        length = convert(input, 40000, 223721, 48000, 2048, a);
        double energy = 0, error = 0;
        for (size_t i = 64; i < length; ++i) {
            energy += (double)a[i * 2] * a[i * 2]; assert(a[i * 2 + 1] == 0);
            double time = (i + 1) * 223721.0 / 48000 - 1 - (RR_AUDIO_TAPS - 1) * .5;
            double ideal = 12000 * sin(2 * 3.141592653589793 * frequencies[tone] * time / 223721);
            error += (a[i * 2] - ideal) * (a[i * 2] - ideal);
        }
        gains[tone] = sqrt(energy / (length - 64)) / (12000 / sqrt(2.0));
        if (tone < 3) assert(sqrt(error / energy) < .01); // Phase and waveform, not only RMS amplitude.
    }
    assert(gains[0] > .99 && gains[0] < 1.01 && gains[1] > .98 && gains[1] < 1.02 && gains[2] > .98 && gains[2] < 1.02 && gains[3] < .001 && gains[4] < .001);
    printf("tone gain: 1 kHz %.5f, 10 kHz %.5f, 18 kHz %.5f, 26 kHz %.6f, 70 kHz %.6f\n", gains[0], gains[1], gains[2], gains[3], gains[4]);
    free(input); free(a); free(b);
}

static void ring_checks(void) {
    reset_test(48000, 48000);
    int16_t source[4096 * 2], output[4096 * 2];
    for (int i = 0; i < 4096; ++i) { source[i * 2] = (int16_t)i; source[i * 2 + 1] = (int16_t)-i; }
    // More than a ring's worth of traffic, including both wrap boundaries.
    rr_audio.started = true;
    for (int pass = 0; pass < 40; ++pass) {
        host_audio_submit(source, 731);
        audio_callback(NULL, (Uint8 *)output, 731 * 4);
        assert(!memcmp(source, output, 731 * 4) && rr_audio.fill == 0);
    }
    assert(!rr_audio.dropped && !rr_audio.underrun);
    host_audio_submit(source, 4096);
    assert(rr_audio.fill <= rr_audio.high_water && rr_audio.dropped > 0);
    size_t saved = rr_audio.fill;
    assert(capture(output) == saved);
    assert(!memcmp(output, source + (4096 - saved) * 2, saved * 4));
    // Underrun is silent, then re-primes instead of replaying old PCM.
    audio_output_clear(); rr_audio.started = true;
    audio_callback(NULL, (Uint8 *)output, 256 * 4);
    assert(rr_audio.underrun == 256 && !rr_audio.started);
    for (int i = 0; i < 512; ++i) assert(!output[i]);
    host_audio_submit(source, 100);
    audio_callback(NULL, (Uint8 *)output, 256 * 4);
    assert(rr_audio.fill == 100 && !rr_audio.started);
    audio_output_clear(); assert(!rr_audio.fill && !rr_audio.phase && !rr_audio.started);
    printf("ring: FIFO/stereo/wrap, bounded overflow retains newest sound, silent underrun, clear/re-prime OK\n");
}

static void burst_check(void) {
    reset_test(223721, rr_audio.device.freq);
    int16_t source[2048 * 2] = {0};
    for (int frame = 0; frame < 8; ++frame) {
        host_audio_submit(source, 2048); host_audio_submit(source, 1685);
    }
    assert(rr_audio.produced == (uint64_t)29864 * rr_audio.device.freq / 223721);
    assert(rr_audio.fill <= rr_audio.high_water && rr_audio.peak <= rr_audio.high_water);
    printf("{\"driver\":\"%s\",\"rate\":%d,\"device_samples\":%u,\"produced_frames\":%llu,\"queued_frames\":%u,\"queued_ms\":%.3f,\"peak_ms\":%.3f,\"limit_ms\":%.3f,\"trimmed_frames\":%llu}\n",
        SDL_GetCurrentAudioDriver(), rr_audio.device.freq, rr_audio.device.samples,
        (unsigned long long)rr_audio.produced, rr_audio.fill, rr_audio.fill * 1000.0 / rr_audio.device.freq,
        rr_audio.peak * 1000.0 / rr_audio.device.freq, rr_audio.high_water * 1000.0 / rr_audio.device.freq,
        (unsigned long long)rr_audio.dropped);
}

static void cadence_checks(void) {
    int16_t source[2048 * 2] = {0}, output[2048 * 2];
    Uint16 saved_period = rr_audio.device.samples;
    const Uint16 periods[] = {256, 480, 1024};
    for (int pal = 0; pal < 2; ++pal) for (int p = 0; p < 3; ++p) {
        for (int offset = 0; offset < 16; ++offset) {
            rr_audio.device.samples = periods[p];
            uint32_t rate = pal ? 221680 : 223721;
            double source_per_frame = pal ? 4460.25 : 3733.5;
            double frame_us = source_per_frame * 1e6 / rate;
            double callback_us = periods[p] * 1e6 / 48000;
            reset_test(rate, 48000);
            unsigned callback = 0;
            for (int frame = 0; frame < 1000; ++frame) {
                // Vary producer/callback phase and add up to 1 ms of scheduling jitter.
                double submit_us = frame * frame_us + (frame % 7) * 1000.0 / 6;
                while (callback * callback_us + offset * callback_us / 16 < submit_us) {
                    audio_callback(NULL, (Uint8 *)output, periods[p] * 4);
                    ++callback;
                }
                size_t count = (size_t)((frame + 1) * source_per_frame) - (size_t)(frame * source_per_frame);
                while (count) {
                    size_t chunk = SDL_min(count, 2048u);
                    host_audio_submit(source, chunk); count -= chunk;
                }
            }
            if (rr_audio.underrun || rr_audio.dropped || !rr_audio.started)
                fprintf(stderr, "cadence failure: PAL=%d period=%u offset=%d underrun=%llu trim=%llu peak=%u limit=%u\n",
                    pal, periods[p], offset, (unsigned long long)rr_audio.underrun,
                    (unsigned long long)rr_audio.dropped, rr_audio.peak, rr_audio.high_water);
            assert(!rr_audio.underrun && !rr_audio.dropped && rr_audio.started);
        }
    }
    rr_audio.device.samples = saved_period;
    puts("cadence: PAL/NTSC, 256/480/1024-frame callbacks, 16 starting phases, 1 ms jitter: no underrun or trim");
}

static void steady_check(void) {
    reset_test(223721, rr_audio.device.freq);
    int16_t source[2048 * 2] = {0};
    Uint64 start = SDL_GetPerformanceCounter(), frequency = SDL_GetPerformanceFrequency(), worst_late = 0;
    SDL_PauseAudioDevice(audio_device, 0);
    // Exact source-frame cadence, same end-of-video-frame producer pattern.
    for (int frame = 0; frame < 180; ++frame) {
        Uint64 deadline = start + (Uint64)(frame * 3733.5 * frequency / 223721);
        while (SDL_GetPerformanceCounter() < deadline) SDL_Delay(1);
        Uint64 late = SDL_GetPerformanceCounter() - deadline;
        worst_late = SDL_max(worst_late, late);
        host_audio_submit(source, 2048); host_audio_submit(source, 1685 + (frame & 1));
    }
    SDL_PauseAudioDevice(audio_device, 1);
    printf("steady silent output: produced=%llu played=%llu trimmed=%llu underrun=%llu peak=%.3f ms worst_producer_late=%.3f ms\n",
        (unsigned long long)rr_audio.produced, (unsigned long long)rr_audio.played,
        (unsigned long long)rr_audio.dropped, (unsigned long long)rr_audio.underrun,
        rr_audio.peak * 1000.0 / rr_audio.device.freq, worst_late * 1000.0 / frequency);
    assert(!rr_audio.dropped && !rr_audio.underrun);
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IONBF, 0);
    SDL_SetMainReady();
    bool device = argc > 1 && !strcmp(argv[1], "--device");
    if (!device) SDL_SetHint(SDL_HINT_AUDIODRIVER, "dummy");
    if (!host_audio_init(223721)) { fprintf(stderr, "%s\n", SDL_GetError()); return 1; }
    SDL_PauseAudioDevice(audio_device, 1);
    if (device) { burst_check(); steady_check(); }
    else { conversion_checks(); ring_checks(); cadence_checks(); reset_test(223721, 48000); burst_check(); }
    host_audio_shutdown(); SDL_Quit(); puts("PASS: host audio checks"); return 0;
}
