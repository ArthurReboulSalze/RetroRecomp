"""Low-latency host policy applied to the pinned generated GB runtime."""
from pathlib import Path
from shutil import copyfile

from .core import replace_once
from .paths import ASSETS


def adapt_timing(project: Path) -> None:
    copyfile(ASSETS / 'native/gb_input_refresh.inc', project / 'runtime/src/gb_input_refresh.inc')
    path = project / 'runtime/src/platform_sdl.cpp'
    source = path.read_text(encoding='utf-8')
    source = replace_once(source, 'static uint32_t g_last_frame_time = 0;', '''static uint32_t g_last_frame_time = 0;
static uint64_t g_rr_next_frame_time = 0;
static uint64_t g_rr_frame_remainder = 0;
static uint64_t g_rr_input_sample_time = 0;''')
    source = replace_once(source, 'static uint32_t g_audio_latency_ms = 80;',
                          'static uint32_t g_audio_latency_ms = 20;')
    source = replace_once(source, '    g_audio_latency_ms = 80;', '    g_audio_latency_ms = 20;')
    source = replace_once(source, 'g_audio_latency_ms = (uint32_t)parsed;',
                          'g_audio_latency_ms = parsed == 80 ? 20u : (uint32_t)parsed;')
    source = replace_once(source, '    want.samples = 2048;', '    want.samples = 512;')
    source = replace_once(source, '''    g_app_suspended = suspended;
    refresh_audio_device_pause_state();''', '''    g_app_suspended = suspended;
    reset_audio_output_buffer(true);''')
    source = replace_once(source, '''           !g_app_suspended &&
           effective_speed_percent() == 100;''', '''           !g_app_suspended && !g_show_menu &&
           effective_speed_percent() == 100;''')
    source = replace_once(source, 'static uint64_t g_audio_reported_underruns = 0;', '''static uint64_t g_audio_reported_underruns = 0;
static std::atomic<uint64_t> g_rr_audio_trimmed{0};
static uint64_t g_rr_reported_trimmed = 0;''')
    source = replace_once(source, '''static void update_audio_stats_from_ring(void) {
    const uint64_t total_underruns''', '''static void update_audio_stats_from_ring(void) {
    const uint64_t trimmed = g_rr_audio_trimmed.load(std::memory_order_relaxed);
    const uint64_t newly_trimmed = trimmed - g_rr_reported_trimmed;
    if (newly_trimmed) {
        audio_stats_samples_dropped(newly_trimmed > UINT32_MAX ? UINT32_MAX : (uint32_t)newly_trimmed);
        g_rr_reported_trimmed = trimmed;
    }
    const uint64_t total_underruns''')
    source = replace_once(source, '''static void reset_audio_output_buffer(bool preserve_stats) {
    if (g_audio_device) {''', '''static void reset_audio_output_buffer(bool preserve_stats) {
    /* Menus, reset, load and suspension start a fresh host deadline. */
    g_rr_next_frame_time = g_rr_frame_remainder = g_rr_input_sample_time = 0;
    if (g_audio_device) {''')
    source = replace_once(source, '''    if (!preserve_stats) {
        g_audio_underruns.store''', '''    if (!preserve_stats) {
        g_rr_audio_trimmed.store(0, std::memory_order_relaxed);
        g_rr_reported_trimmed = 0;
        g_audio_underruns.store''')
    source = replace_once(source, '''    const uint32_t available = (write_pos >= read_pos)
        ? (write_pos - read_pos)
        : (AUDIO_RING_SIZE - read_pos + write_pos);
    const uint32_t samples_to_copy''', '''    uint32_t available = (write_pos >= read_pos)
        ? (write_pos - read_pos)
        : (AUDIO_RING_SIZE - read_pos + write_pos);
    /* The consumer owns read_pos. Discard stale audio only if the backlog
     * exceeds the target plus a callback and a guest-frame burst. Never let
     * the ring's large safety capacity become hundreds of ms of sound lag. */
    const uint32_t guest_frame_samples = (uint32_t)(
        ((uint64_t)g_audio_device_sample_rate * 70224u + 4194303u) / 4194304u);
    const uint32_t keep = g_audio_start_threshold + samples_needed;
    if (available > keep + guest_frame_samples) {
        const uint32_t discard = available - keep;
        read_pos = (read_pos + discard) % AUDIO_RING_SIZE;
        available = keep;
        g_rr_audio_trimmed.fetch_add(discard, std::memory_order_relaxed);
    }
    const uint32_t samples_to_copy''')
    source = replace_once(source, '''bool gb_platform_poll_events(GBContext* ctx) {
    SDL_Event event;''', '''#include "gb_input_refresh.inc"

bool gb_platform_poll_events(GBContext* ctx) {
    SDL_Event event;''')
    source = replace_once(source, '''bool gb_platform_wait_while_menu(GBContext* ctx) {
    while (g_show_menu''', '''bool gb_platform_wait_while_menu(GBContext* ctx) {
    /* This runs after pacing, immediately before the next CPU slice.
     * Scripted/headless probes retain their original input boundaries. */
    if (!g_benchmark_mode && !g_script_count && !gb_platform_poll_events(ctx)) return false;
    while (g_show_menu''')
    source = replace_once(source, '''    record_manual_input_state(current_cycles);

    return true;
}

bool gb_platform_wait_while_menu''', '''    rr_gb_sample_input(ctx, true);
    record_manual_input_state(current_cycles);

    return true;
}

bool gb_platform_wait_while_menu''')
    source = replace_once(source, '''    static uint64_t next_frame_time = 0;
    static uint64_t frame_remainder = 0;''', '''    uint64_t& next_frame_time = g_rr_next_frame_time;
    uint64_t& frame_remainder = g_rr_frame_remainder;
    publish_audio_write_batch();''')
    source = replace_once(source,
        '     * at 4194304 Hz, and ease off sleeping when audio fill is too low.',
        '     * at 4194304 Hz, independently of temporary audio underruns.')
    source = replace_once(source, '''    uint32_t audio_fill = audio_ring_fill_samples();
    bool audio_starved = audio_output_should_run() && g_audio_started && audio_fill < g_audio_low_watermark;

    if (!audio_starved && now < target_frame_time) {''', '''    /* Audio underruns must not make the guest run ahead of wall time.
     * Maintain console speed and let the callback silence a missing sample. */
    if (now < target_frame_time) {''')
    source = replace_once(source, '''    if (g_benchmark_mode || g_app_suspended) {
        g_last_timing.pacing_cycles''', '''    if (g_benchmark_mode || g_app_suspended) {
        g_rr_next_frame_time = g_rr_frame_remainder = 0;
        g_last_timing.pacing_cycles''')
    source = replace_once(source, '''    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMECONTROLLER) < 0) {''', '''#ifdef _WIN32
    SDL_SetHintWithPriority(SDL_HINT_RENDER_DRIVER, "direct3d11", SDL_HINT_DEFAULT);
    SDL_SetHintWithPriority(SDL_HINT_JOYSTICK_THREAD, "1", SDL_HINT_DEFAULT);
#endif
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMECONTROLLER | SDL_INIT_TIMER) < 0) {''')
    source = replace_once(source, '''        .save_rtc_data = sdl_save_rtc_data
    };''', '''        .save_rtc_data = sdl_save_rtc_data,
        .refresh_input = rr_gb_refresh_joyp
    };''')
    path.write_text(source, encoding='utf-8')

    path = project / 'runtime/include/gbrt.h'
    source = path.read_text(encoding='utf-8')
    source = replace_once(source, '''} GBPlatformCallbacks;''', '''    /* Host-only input refresh; absent from serialized guest state. */
    void (*refresh_input)(GBContext* ctx);
} GBPlatformCallbacks;''')
    path.write_text(source, encoding='utf-8')
    path = project / 'runtime/src/gbrt.c'
    source = path.read_text(encoding='utf-8')
    source = replace_once(source, '''        if (addr == 0xFF00) {
            const GBJoypadState* joypad''', '''        if (addr == 0xFF00) {
            if (!ctx->joypad && ctx->callbacks.refresh_input) ctx->callbacks.refresh_input(ctx);
            const GBJoypadState* joypad''')
    path.write_text(source, encoding='utf-8')
