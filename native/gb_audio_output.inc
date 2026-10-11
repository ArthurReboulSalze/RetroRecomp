/* Host-only GB consumer. Preserve 44.1 kHz guest PCM and volume semantics.
 * Start at a sample-accurate deadline, not after a second guest frame.
 * No allocations, guest execution or input polling on the audio thread. */
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
    const uint32_t keep = g_audio_start_threshold + needed;
    if (available > keep + burst) {
        const uint32_t discard = available - keep;
        read = (read + discard) % AUDIO_RING_SIZE;
        available = keep;
        g_rr_audio_trimmed.fetch_add(discard, std::memory_order_relaxed);
    }
    const uint32_t take = SDL_min(available, needed);
    const bool muted = g_audio_muted.load(std::memory_order_relaxed);
    const uint32_t volume = g_audio_volume_percent.load(std::memory_order_relaxed);
    for (uint32_t i = 0; i < take; ++i) {
        const uint32_t at = (read + i) % AUDIO_RING_SIZE;
        for (uint32_t channel = 0; channel < 2; ++channel) {
            int32_t value = muted ? 0 : g_audio_ring[at * 2u + channel];
            value = SDL_clamp(value * (int32_t)volume / 100, -32768, 32767);
            if (g_rr_audio_format == AUDIO_F32SYS)
                ((float*)stream)[i * 2u + channel] = value / 32768.0f;
            else
                ((int16_t*)stream)[i * 2u + channel] = (int16_t)value;
        }
    }
    if (take < needed) {
        g_audio_underruns.fetch_add(needed - take, std::memory_order_relaxed);
        g_rr_audio_ready = false;
        g_rr_audio_start_counter.store(0, std::memory_order_release);
    }
    g_audio_read_pos.store((read + take) % AUDIO_RING_SIZE, std::memory_order_release);
}
