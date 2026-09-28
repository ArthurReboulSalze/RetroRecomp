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
    assert(g_audio_latency_ms == 20 && g_audio_device_buffer_samples == 512);
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

    reset_audio_output_buffer(false);
    g_audio_started = true;
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
    printf("PASS: 20 ms target, 512-sample callback, legacy prefs, %.1f ms for six paced frames, PCM order, bounded backlog and concurrent ring.\n", elapsed);
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
    input_checks(ctx);
    gb_platform_shutdown();
    gb_context_destroy(ctx);
    return 0;
}
