"""Low-latency host policy applied to the pinned generated GB runtime.

Host only (frame pacing, sound output, input sampling). The guest-side
JOYP refresh hook it relies on is gameboy_runtime.adapt_input_refresh_hook.
"""
from pathlib import Path
from shutil import copyfile

from .core import replace_once
from .paths import ASSETS


def adapt_timing(project: Path) -> None:
    copyfile(ASSETS / 'native/gb_input_refresh.inc', project / 'runtime/src/gb_input_refresh.inc')
    copyfile(ASSETS / 'native/gb_audio_output.inc', project / 'runtime/src/gb_audio_output.inc')
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
    source = replace_once(source, '    want.samples = 2048;', '    want.samples = 256;')
    source = replace_once(source, 'static uint32_t g_audio_start_threshold = 0;', '''static uint32_t g_audio_start_threshold = 0;
#define RR_GB_AUDIO_DEADLINE 1
static SDL_AudioFormat g_rr_audio_format = AUDIO_S16SYS;
static std::atomic<uint64_t> g_rr_audio_start_counter{0};
static bool g_rr_audio_ready = false; /* Callback-owned; reset under device lock. */
static uint64_t g_rr_audio_startup_silence = 0;''')
    source = replace_once(source,
        '    g_audio_device = SDL_OpenAudioDevice(device_name, 0, &want, &have, 0);', '''    g_audio_device = SDL_OpenAudioDevice(device_name, 0, &want, &have,
        SDL_AUDIO_ALLOW_FORMAT_CHANGE | SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    if (g_audio_device && have.format != AUDIO_S16SYS && have.format != AUDIO_F32SYS) {
        SDL_CloseAudioDevice(g_audio_device);
        g_audio_device = SDL_OpenAudioDevice(device_name, 0, &want, &have,
            SDL_AUDIO_ALLOW_SAMPLES_CHANGE);
    }
    g_rr_audio_format = have.format;''')
    source = replace_once(source, '    SDL_AudioSpec want, have;', '    SDL_AudioSpec want, have = {};')
    source = replace_once(source, 'static void clear_audio_ring_buffer_locked(void) {', '''static void clear_audio_ring_buffer_locked(void) {
    g_rr_audio_start_counter.store(0, std::memory_order_relaxed);
    g_rr_audio_ready = false;
    g_rr_audio_startup_silence = 0;''')
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
    rr_options_audio_reset();
    /* Menus, reset, load and suspension start a fresh host deadline. */
    g_rr_next_frame_time = g_rr_frame_remainder = g_rr_input_sample_time = 0;
    if (g_audio_device) {''')
    source = replace_once(source, '''    if (!preserve_stats) {
        g_audio_underruns.store''', '''    if (!preserve_stats) {
        g_rr_audio_trimmed.store(0, std::memory_order_relaxed);
        g_rr_reported_trimmed = 0;
        g_audio_underruns.store''')
    # Replace only the host consumer. The 44.1 kHz APU, guest state and PCM stay
    # unchanged; uncommon backend sample-rate conversion remains SDL's job.
    start = source.index('/* SDL callback - pulls samples from ring buffer */')
    end = source.index('static void publish_audio_write_batch(void) {', start)
    source = source[:start] + '#include "gb_audio_output.inc"\n\n' + source[end:]
    source = replace_once(source, '''    g_audio_write_pos.store(g_audio_producer_write_pos, std::memory_order_release);
    g_audio_write_publications++;''', '''    uint64_t empty_deadline = 0;
    rr_cushion_pushed(&g_rr_cushion);
    const uint64_t frequency = SDL_GetPerformanceFrequency();
    const uint64_t deadline = SDL_GetPerformanceCounter() +
        ((uint64_t)g_audio_device_buffer_samples * frequency + AUDIO_SAMPLE_RATE - 1) / AUDIO_SAMPLE_RATE +
        (frequency * (10u + (uint32_t)rr_cushion_ms(&g_rr_cushion)) + 999u) / 1000u;
    g_rr_audio_start_counter.compare_exchange_strong(empty_deadline, deadline,
        std::memory_order_release, std::memory_order_relaxed);
    g_audio_write_pos.store(g_audio_producer_write_pos, std::memory_order_release);
    g_audio_write_publications++;''')
    source = replace_once(source,
        'if (!g_audio_started && audio_ring_fill_samples() >= g_audio_start_threshold)',
        'if (!g_audio_started && audio_ring_fill_samples() > 0)')
    source = replace_once(source, 'static void reset_audio_test_ring(void) {', '''static void reset_audio_test_ring(void) {
    g_rr_audio_ready = true; /* This hook checks ring concurrency, not pacing. */
    g_rr_audio_format = AUDIO_S16SYS;''')
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
