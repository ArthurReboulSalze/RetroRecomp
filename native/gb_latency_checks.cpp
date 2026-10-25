/* Authored SDL/input/audio checks. No game ROM, screenshots or gameplay. */
#undef NDEBUG
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <cassert>
#include <cstdio>
#include <cstring>
static Uint8 test_keys[SDL_NUM_SCANCODES];
static SDL_Window* test_focus;
static bool test_clock_enabled;
static uint64_t test_clock;
static const Uint8* test_keyboard(int* count) {
    if (count) *count = SDL_NUM_SCANCODES;
    return test_keys;
}
static uint64_t input_clock() {
    return test_clock_enabled ? test_clock : SDL_GetPerformanceCounter();
}
static SDL_bool virtual_controller(int index) {
    return SDL_JoystickIsVirtual(index) ? SDL_IsGameController(index) : SDL_FALSE;
}
#define SDL_GetKeyboardState test_keyboard
#define SDL_GetKeyboardFocus() test_focus
#define SDL_GetPerformanceCounter input_clock
#define SDL_IsGameController virtual_controller
#include "platform_sdl.cpp"
#undef SDL_IsGameController
#undef SDL_GetPerformanceCounter
#undef SDL_GetKeyboardFocus
#undef SDL_GetKeyboardState

extern "C" void gb_dispatch(GBContext*, uint16_t) {
    assert(false && "This host test must not execute cartridge code");
}

static void audio_checks() {
    assert(g_audio_latency_ms == 20 && g_audio_device_buffer_samples == 256);
    const fs::path prefs = runtime_preferences_path();
    assert(!fs::exists(prefs));
    fs::create_directories(prefs.parent_path());
    FILE* file = fopen(prefs.string().c_str(), "w"); assert(file);
    fputs("audio.latency_ms=80\n", file); fclose(file);
    load_runtime_preferences();
    assert(g_audio_latency_ms == 20);
    fs::remove(prefs); fs::remove(prefs.parent_path());

    // Empty audio must not accelerate the CPU or bypass the frame deadline.
    g_audio_muted.store(true);
    g_audio_started = true;
    refresh_audio_device_pause_state();
    g_rr_next_frame_time = g_rr_frame_remainder = 0;
    uint64_t start = SDL_GetPerformanceCounter();
    for (int i = 0; i < 6; ++i) gb_platform_vsync(70224);
    double elapsed = (SDL_GetPerformanceCounter() - start) * 1000.0 / SDL_GetPerformanceFrequency();
    assert(elapsed >= 95 && elapsed < 600);
    close_audio_output_device();
    g_audio_device_sample_rate = 44100;
    g_audio_device_buffer_samples = 512;
    recompute_audio_targets();
    assert(g_audio_start_threshold == 882);
    reset_audio_output_buffer(false);
    g_audio_muted.store(false);
    g_audio_started = true;
    g_rr_audio_ready = true;
    g_rr_audio_format = AUDIO_S16SYS;
    for (int i = 0; i < 1024; ++i) assert(enqueue_audio_sample((int16_t)i, (int16_t)-i));
    publish_audio_write_batch();
    int16_t pcm[512 * 2];
    sdl_audio_callback(NULL, (Uint8*)pcm, sizeof(pcm));
    for (int i = 0; i < 512; ++i) assert(pcm[i * 2] == i && pcm[i * 2 + 1] == -i);
    assert(g_rr_audio_trimmed.load() == 0);
    sdl_audio_callback(NULL, (Uint8*)pcm, sizeof(pcm));
    for (int i = 0; i < 512; ++i) assert(pcm[i * 2] == i + 512 && pcm[i * 2 + 1] == -i - 512);
    sdl_audio_callback(NULL, (Uint8*)pcm, sizeof(pcm));
    for (int16_t sample : pcm) assert(sample == 0);
    // The guest had just produced PCM: one adaptive restart step, no more.
    assert(rr_cushion_ms(&g_rr_cushion) == RR_CUSHION_STEP_MS);
    g_rr_cushion = RrAudioCushion{};

    reset_audio_output_buffer(false);
    g_audio_started = true;
    g_rr_audio_ready = true;
    for (int i = 0; i < 5000; ++i) assert(enqueue_audio_sample((int16_t)i, (int16_t)-i));
    publish_audio_write_batch();
    sdl_audio_callback(NULL, (Uint8*)pcm, sizeof(pcm));
    const uint32_t discarded = 5000 - 882 - 512;
    assert(g_rr_audio_trimmed.load() == discarded);
    assert(audio_ring_fill_samples() == 882);
    for (int i = 0; i < 512; ++i)
        assert(pcm[i * 2] == i + discarded && pcm[i * 2 + 1] == -(int)(i + discarded));
    update_audio_stats_from_ring();
    assert(g_audio_stats.total_samples_dropped == discarded);

    reset_audio_output_buffer(false);
    GBAudioStressResult stress = {};
    assert(gb_platform_test_audio_concurrency(200000, &stress));
    assert(stress.frames_enqueued > 0 && stress.write_publications * 4 < stress.frames_enqueued);
    printf("PASS: legacy prefs, %.1f ms for six paced frames, PCM order, bounded backlog and concurrent ring.\n", elapsed);
}

static void audio_deadline_checks() {
    test_clock_enabled = true;
    const uint64_t frequency = SDL_GetPerformanceFrequency();
    for (unsigned period : {256u, 441u, 480u, 512u, 1024u}) {
        for (unsigned phase = 0; phase < 16; ++phase) {
            reset_audio_output_buffer(false);
            g_rr_cushion = RrAudioCushion{}; // Base latency, before any learned reserve.
            g_audio_device_sample_rate = AUDIO_SAMPLE_RATE;
            g_audio_device_buffer_samples = period;
            recompute_audio_targets();
            g_audio_started = true;
            g_audio_muted.store(false); g_audio_volume_percent.store(100);
            g_rr_audio_format = phase & 1 ? AUDIO_F32SYS : AUDIO_S16SYS;
            uint64_t produced = 0, consumed = 0, callbacks = 0;
            unsigned frame = 0;
            const uint64_t origin = frequency;
            const uint64_t first_callback = origin + phase * period * frequency / (16u * AUDIO_SAMPLE_RATE);
            std::vector<Uint8> output(period * (g_rr_audio_format == AUDIO_F32SYS ? 8u : 4u));
            while (frame < 2000) {
                const uint64_t next_frame = origin + (uint64_t)frame * 70224 * frequency / 4194304 +
                    (frame ? (frame % 7) * frequency / 2000 : 0); // Up to 3 ms scheduling jitter.
                const uint64_t next_callback = first_callback + callbacks * period * frequency / AUDIO_SAMPLE_RATE;
                if (next_frame <= next_callback) {
                    test_clock = next_frame;
                    const uint64_t end = (uint64_t)(++frame) * 70224 * AUDIO_SAMPLE_RATE / 4194304;
                    while (produced < end) {
                        assert(enqueue_audio_sample((int16_t)produced, (int16_t)~produced)); ++produced;
                    }
                    publish_audio_write_batch();
                } else {
                    test_clock = next_callback; ++callbacks;
                    const uint64_t old_silence = g_rr_audio_startup_silence;
                    sdl_audio_callback(NULL, output.data(), (int)output.size());
                    const uint32_t silence = (uint32_t)(g_rr_audio_startup_silence - old_silence);
                    if (!consumed && silence < period) {
                        const double start_ms = (test_clock - origin) * 1000.0 / frequency + silence * 1000.0 / AUDIO_SAMPLE_RATE;
                        const double expected_ms = period * 1000.0 / AUDIO_SAMPLE_RATE + 10.0;
                        assert(start_ms >= expected_ms - 0.001 && start_ms <= expected_ms + 0.025);
                    }
                    for (uint32_t i = 0; i < period; ++i) {
                        int16_t left = i < silence ? 0 : (int16_t)consumed;
                        int16_t right = i < silence ? 0 : (int16_t)~consumed;
                        if (g_rr_audio_format == AUDIO_F32SYS) {
                            assert(((float*)output.data())[i * 2] == left / 32768.0f);
                            assert(((float*)output.data())[i * 2 + 1] == right / 32768.0f);
                        } else {
                            assert(((int16_t*)output.data())[i * 2] == left);
                            assert(((int16_t*)output.data())[i * 2 + 1] == right);
                        }
                        if (i >= silence) ++consumed;
                    }
                    assert(g_audio_underruns.load() == 0 && g_rr_audio_trimmed.load() == 0);
                }
            }
            const double lag = (test_clock - origin) * 1000.0 / frequency - consumed * 1000.0 / AUDIO_SAMPLE_RATE;
            assert(consumed > 1000000 && lag < 60); // No accumulating queue/drift.
            assert(g_rr_audio_startup_silence > 0);
        }
    }
    reset_audio_output_buffer(false);
    assert(!g_rr_audio_ready && !g_rr_audio_start_counter.load());
    // Float output preserves integer volume rounding/clipping and mute.
    g_audio_started = g_rr_audio_ready = true;
    g_rr_audio_format = AUDIO_F32SYS;
    g_audio_volume_percent.store(50);
    assert(enqueue_audio_sample(30001, -30001)); publish_audio_write_batch();
    float stereo[2]; sdl_audio_callback(NULL, (Uint8*)stereo, sizeof(stereo));
    assert(stereo[0] == 15000 / 32768.0f && stereo[1] == -15000 / 32768.0f);
    g_audio_muted.store(true);
    assert(enqueue_audio_sample(30000, -30000)); publish_audio_write_batch();
    sdl_audio_callback(NULL, (Uint8*)stereo, sizeof(stereo));
    assert(stereo[0] == 0 && stereo[1] == 0);
    g_audio_muted.store(false); g_audio_volume_percent.store(100);
    // Starvation silences the tail and re-primes; the next frame cannot play
    // against an expired startup deadline after a device/CPU stall.
    sdl_audio_callback(NULL, (Uint8*)stereo, sizeof(stereo));
    assert(!g_rr_audio_ready && !g_rr_audio_start_counter.load());
    assert(enqueue_audio_sample(123, -456)); publish_audio_write_batch();
    const uint64_t restart = g_rr_audio_start_counter.load();
    assert(restart > test_clock);
    sdl_audio_callback(NULL, (Uint8*)stereo, sizeof(stereo));
    assert(stereo[0] == 0 && stereo[1] == 0 && audio_ring_fill_samples() == 1);
    test_clock = restart;
    sdl_audio_callback(NULL, (Uint8*)stereo, sizeof(stereo));
    assert(stereo[0] == 123 / 32768.0f && stereo[1] == -456 / 32768.0f);
    test_clock_enabled = false;
    puts("PASS: 80 jittered 2000-frame timelines, five callback periods, exact S16/F32 PCM, volume/mute, no underrun/drop, reset clears deadline.");
}

static void input_checks(GBContext* ctx) {
    test_focus = g_window;
    set_default_input_bindings();
    clear_all_binding_pressed_state();
    test_clock_enabled = true;
    test_clock = SDL_GetPerformanceCounter();
    const uint64_t interval = SDL_GetPerformanceFrequency() / 1000 + 1;
    ctx->io[0] = 0x10; // Select the cartridge's buttons.
    ctx->io[0x0F] = 0;
    test_keys[rr_letter_key(SDLK_w, SDL_SCANCODE_W)] = 1;
    g_rr_input_sample_time = 0;
    assert(!(gb_read8(ctx, 0xFF00) & 1));
    assert(ctx->io[0x0F] & 0x10);
    test_keys[rr_letter_key(SDLK_w, SDL_SCANCODE_W)] = 0;
    assert(!(gb_read8(ctx, 0xFF00) & 1)); // Throttled inside the 1 ms window.
    test_clock += interval;
    assert(gb_read8(ctx, 0xFF00) & 1);

    // The ordinary pre-slice event loop samples a just-pressed Start after pacing.
    test_keys[SDL_SCANCODE_RETURN] = 1;
    assert(gb_platform_wait_while_menu(ctx));
    assert(!(g_joypad_buttons & 8) && !g_show_menu);
    test_keys[SDL_SCANCODE_RETURN] = 0;
    test_keys[SDL_SCANCODE_LSHIFT] = 1;
    test_clock += interval;
    assert(!(gb_read8(ctx, 0xFF00) & 4));
    // Either Shift is Select: the second slot keeps the upstream Right Shift.
    test_keys[SDL_SCANCODE_LSHIFT] = 0; test_clock += interval;
    assert(gb_read8(ctx, 0xFF00) & 4);
    test_keys[SDL_SCANCODE_RSHIFT] = 1; test_clock += interval;
    assert(!(gb_read8(ctx, 0xFF00) & 4));
    memset(test_keys, 0, sizeof(test_keys));
    assert(gb_platform_set_input_script("0:A:2"));
    test_keys[SDL_SCANCODE_X] = 1;
    assert(gb_platform_poll_events(ctx));
    assert((gb_read8(ctx, 0xFF00) & 3) == 2); // Script stays authoritative.
    assert(gb_platform_set_input_script(NULL));
    memset(test_keys, 0, sizeof(test_keys));

    SDL_VirtualJoystickDesc desc = {};
    desc.version = SDL_VIRTUAL_JOYSTICK_DESC_VERSION;
    desc.type = SDL_JOYSTICK_TYPE_GAMECONTROLLER;
    desc.naxes = SDL_CONTROLLER_AXIS_MAX; desc.nbuttons = SDL_CONTROLLER_BUTTON_MAX;
    desc.axis_mask = (1u << SDL_CONTROLLER_AXIS_MAX) - 1;
    desc.button_mask = (1u << SDL_CONTROLLER_BUTTON_MAX) - 1;
    desc.name = "RetroRecomp input fixture";
    int device = SDL_JoystickAttachVirtualEx(&desc); assert(device >= 0);
    open_first_available_controller(); assert(g_controller);
    SDL_Joystick* stick = SDL_GameControllerGetJoystick(g_controller);
    assert(SDL_JoystickSetVirtualButton(stick, SDL_CONTROLLER_BUTTON_B, 1) == 0);
    assert(SDL_JoystickSetVirtualAxis(stick, SDL_CONTROLLER_AXIS_LEFTX, -20000) == 0);
    SDL_GameControllerUpdate(); test_clock += interval;
    assert(!(gb_read8(ctx, 0xFF00) & 1));
    ctx->io[0] = 0x20;
    assert(!(gb_read8(ctx, 0xFF00) & 2));
    assert(SDL_JoystickSetVirtualAxis(stick, SDL_CONTROLLER_AXIS_LEFTX, 0) == 0);
    SDL_GameControllerUpdate(); test_clock += interval;
    assert(gb_read8(ctx, 0xFF00) & 2);

    g_rr_next_frame_time = test_clock + interval * 50;
    g_rr_frame_remainder = 42;
    rr_gb_toggle_menu(RR_GB_PAUSE);
    assert(!g_rr_next_frame_time && !g_rr_frame_remainder && !audio_output_should_run());
    const uint8_t paused = g_joypad_dpad;
    test_keys[SDL_SCANCODE_LEFT] = 1; test_clock += interval;
    gb_read8(ctx, 0xFF00); assert(g_joypad_dpad == paused);
    rr_gb_toggle_menu(RR_GB_PAUSE);
    test_clock += interval; assert(!(gb_read8(ctx, 0xFF00) & 2));
    test_clock_enabled = false;
    puts("PASS: fresh pre-slice keyboard, Start/Shift, live JOYP sampling and throttling, interrupt, scripted isolation, virtual gamepad and pause deadline reset.");
}

int main() {
    SDL_SetMainReady();
    SDL_setenv("SDL_VIDEODRIVER", "dummy", 1);
    SDL_setenv("SDL_AUDIODRIVER", "dummy", 1);
    SDL_setenv("SDL_RENDER_DRIVER", "software", 1);
    assert(gb_platform_init(1));
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    gb_platform_register_context(ctx);
    audio_checks();
    audio_deadline_checks();
    input_checks(ctx);
    gb_platform_shutdown();
    gb_context_destroy(ctx);
    return 0;
}
