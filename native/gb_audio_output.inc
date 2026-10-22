/* Host-only GB consumer. Preserve 44.1 kHz guest PCM and volume semantics.
 * Start at a sample-accurate deadline, not after a second guest frame.
 * No allocations, guest execution or input polling on the audio thread. */
#include "audio_cushion.h"
static RrAudioCushion g_rr_cushion;
static void sdl_audio_callback(void* userdata, Uint8* stream, int len) {
    (void)userdata;
    memset(stream, 0, (size_t)len);
    const uint32_t frame_bytes = g_rr_audio_format == AUDIO_F32SYS ? 8u : 4u;
    uint32_t needed = (uint32_t)len / frame_bytes;
    if (!g_rr_audio_ready) {
        const uint64_t deadline = g_rr_audio_start_counter.load(std::memory_order_acquire);
        const uint64_t now = SDL_GetPerformanceCounter();
        if (!deadline) { g_rr_audio_startup_silence += needed; return; }
        if (now < deadline) {
            const uint64_t frequency = SDL_GetPerformanceFrequency();
            const uint32_t silence = (uint32_t)SDL_min((uint64_t)needed,
                ((deadline - now) * AUDIO_SAMPLE_RATE + frequency - 1) / frequency);
            g_rr_audio_startup_silence += silence;
            if (silence == needed) return;
            stream += silence * frame_bytes;
            needed -= silence;
        }
        g_rr_audio_ready = true;
    }
    const uint32_t write = g_audio_write_pos.load(std::memory_order_acquire);
    uint32_t read = g_audio_read_pos.load(std::memory_order_relaxed);
    uint32_t available = (write + AUDIO_RING_SIZE - read) % AUDIO_RING_SIZE;
    const uint32_t burst = (uint32_t)(((uint64_t)AUDIO_SAMPLE_RATE * 70224 + 4194303) / 4194304);
    const uint32_t keep = g_audio_start_threshold + needed + rr_cushion_frames(&g_rr_cushion, AUDIO_SAMPLE_RATE);
    if (available > keep + burst) {
        const uint32_t discard = available - keep;
        read = (read + discard) % AUDIO_RING_SIZE;
        available = keep;
        g_rr_audio_trimmed.fetch_add(discard, std::memory_order_relaxed);
        rr_cushion_gap(&g_rr_cushion); /* A device stall while playing. */
    }
    const uint32_t take = SDL_min(available, needed);
    const bool muted = g_audio_muted.load(std::memory_order_relaxed);
    const uint32_t volume = g_audio_volume_percent.load(std::memory_order_relaxed);
    if (!muted && volume) {
        uint32_t first = SDL_min(take, AUDIO_RING_SIZE - read);
        for (unsigned part = 0; part < 2; ++part) {
            const uint32_t frames = part ? take - first : first;
            const int16_t* source = g_audio_ring + (part ? 0 : read) * 2u;
            Uint8* output = stream + (part ? first : 0) * frame_bytes;
            if (volume == 100 && g_rr_audio_format == AUDIO_S16SYS) {
                memcpy(output, source, frames * 2u * sizeof(*source));
            } else if (g_rr_audio_format == AUDIO_F32SYS) {
                for (uint32_t i = 0; i < frames * 2u; ++i) {
                    int32_t value = volume == 100 ? source[i] :
                        SDL_clamp(source[i] * (int32_t)volume / 100, -32768, 32767);
                    ((float*)output)[i] = value / 32768.0f;
                }
            } else {
                for (uint32_t i = 0; i < frames * 2u; ++i)
                    ((int16_t*)output)[i] = (int16_t)SDL_clamp(source[i] * (int32_t)volume / 100, -32768, 32767);
            }
        }
    }
#ifdef RR_HOST_AUDIO_FILTER
    if (!muted && volume)
        RR_HOST_AUDIO_FILTER(stream, take, 2, g_rr_audio_format == AUDIO_F32SYS, AUDIO_SAMPLE_RATE);
    else rr_options_dsp.ready = 0;
#endif
    if (take < needed) {
        g_audio_underruns.fetch_add(needed - take, std::memory_order_relaxed);
        g_rr_audio_ready = false;
        g_rr_audio_start_counter.store(0, std::memory_order_release);
        rr_cushion_gap(&g_rr_cushion);
    } else rr_cushion_clean(&g_rr_cushion, take, AUDIO_SAMPLE_RATE);
    g_audio_read_pos.store((read + take) % AUDIO_RING_SIZE, std::memory_order_release);
}
