/* Authored checks of the Game Boy adapter of the host kit (native/hostkit/adapters/rrhk_gb.inc), compiled into the patched
 * platform layer of the generated runtime. No game ROM, screenshots or gameplay. The kit's pad word is replaced by a word the
 * check sets, and the clock by a virtual one, so that what is measured is the adapter: the pad word becomes the cartridge's
 * JOYP registers and interrupt, a live sample is throttled and never overrides a script, a menu freezes the pad, the sound of
 * the APU reaches the kit in order, and a missing data folder is not created by a launch. */
#undef NDEBUG
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <cassert>
#include <cstdio>
#include <cstring>
static bool test_clock_enabled;
static uint64_t test_clock;
static uint64_t input_clock() {
    return test_clock_enabled ? test_clock : SDL_GetPerformanceCounter();
}
static uint16_t test_word;
static unsigned test_words_read;
extern "C" uint16_t check_pad_word(int player, uint64_t frame) {
    (void)player; (void)frame; ++test_words_read;
    return test_word;
}
#define SDL_GetPerformanceCounter input_clock
#define rrhk_pad_word check_pad_word
#include "platform_sdl.cpp"
#undef rrhk_pad_word
#undef SDL_GetPerformanceCounter

extern "C" void gb_dispatch(GBContext*, uint16_t) {
    assert(false && "This host test must not execute cartridge code");
}

enum { RIGHT = 0x01, LEFT = 0x02, UP = 0x04, DOWN = 0x08, A = 0x10, B = 0x20, SELECT = 0x40, START = 0x80 };

static void pad_checks(GBContext* ctx) {
    /* The pad word is the two nibbles of JOYP, positive logic; the registers are active low. A JOYP read inside the 1 ms
     * window of the last sample asks the host for nothing, so the registers read back are the ones just set. */
    test_clock_enabled = true;
    test_clock = 1000000;   /* never 0: that stands for "not sampled yet" */
    g_rr_sample_time = test_clock;
    ctx->io[0] = 0x20;   /* directions selected */
    rr_gb_apply_pad(ctx, RIGHT | DOWN);
    assert(g_joypad_dpad == 0xF6 && g_joypad_buttons == 0xFF);
    assert(!(gb_read8(ctx, 0xFF00) & 1) && !(gb_read8(ctx, 0xFF00) & 8) && (gb_read8(ctx, 0xFF00) & 6) == 6);
    ctx->io[0] = 0x10;   /* buttons selected */
    rr_gb_apply_pad(ctx, A | START);
    assert(g_joypad_dpad == 0xFF && g_joypad_buttons == 0xF6);
    assert(!(gb_read8(ctx, 0xFF00) & 1) && !(gb_read8(ctx, 0xFF00) & 8) && (gb_read8(ctx, 0xFF00) & 6) == 6);
    rr_gb_apply_pad(ctx, B | SELECT);
    assert(g_joypad_buttons == 0xF9);
    /* A new press of a selected line raises the joypad interrupt; a release or a press on the other line does not. */
    ctx->io[0x0F] = 0;
    rr_gb_apply_pad(ctx, 0);
    assert(!(ctx->io[0x0F] & 0x10));
    rr_gb_apply_pad(ctx, RIGHT);
    assert(!(ctx->io[0x0F] & 0x10));
    rr_gb_apply_pad(ctx, RIGHT | START);
    assert(ctx->io[0x0F] & 0x10);
    rr_gb_apply_pad(ctx, 0);
    printf("PASS: pad word to JOYP registers (both nibbles, active low) and the interrupt on a new press.\n");
}

static void sample_checks(GBContext* ctx) {
    assert(rrhk_window());
    test_clock_enabled = true;
    test_clock = 1000000;   /* never 0: that stands for "not sampled yet" */
    const uint64_t interval = SDL_GetPerformanceFrequency() / 1000 + 1;
    ctx->io[0] = 0x10;
    ctx->io[0x0F] = 0;
    rr_gb_apply_pad(ctx, 0);
    g_rr_sample_time = 0;
    test_word = A;
    assert(!(gb_read8(ctx, 0xFF00) & 1));                 /* a JOYP read asks the host for fresh input */
    assert(ctx->io[0x0F] & 0x10);
    test_word = 0;
    assert(!(gb_read8(ctx, 0xFF00) & 1));                 /* throttled inside the 1 ms window */
    test_clock += interval;
    assert(gb_read8(ctx, 0xFF00) & 1);
    /* The slice's own poll samples at once and does not wait for the window. */
    test_word = START;
    assert(gb_platform_poll_events(ctx));
    assert(!(g_joypad_buttons & 8));
    assert(gb_platform_wait_while_menu(ctx));
    test_word = 0; test_clock += interval;
    assert(gb_read8(ctx, 0xFF00) & 8);
    /* A script stays authoritative: live input is not sampled while one is installed. */
    assert(gb_platform_set_input_script("0:A:2"));
    test_word = B;
    const unsigned before = test_words_read;
    assert(gb_platform_poll_events(ctx));
    assert(test_words_read == before && (gb_read8(ctx, 0xFF00) & 3) == 2);
    assert(gb_platform_set_input_script(NULL));
    /* A menu freezes what the cartridge is handed; closing it samples again. */
    test_word = 0; test_clock += interval; gb_read8(ctx, 0xFF00);
    const uint8_t frozen = g_joypad_dpad;
    rrhk_ui()->menu = RRHK_MENU_PAUSE;
    test_word = LEFT; test_clock += interval; gb_read8(ctx, 0xFF00);
    assert(g_joypad_dpad == frozen);
    rrhk_ui()->menu = 0;
    ctx->io[0] = 0x20;
    test_clock += interval; assert(!(gb_read8(ctx, 0xFF00) & 2));
    test_word = 0;
    test_clock_enabled = false;
    printf("PASS: live JOYP sampling and throttling, the slice's poll, scripted isolation and a menu that freezes the pad.\n");
}

static void audio_checks() {
    /* The kit takes the sound of a frame in order, stereo, 44.1 kHz: whole frames, never more than it asks for. */
    g_rr_pcm.clear();
    for (int i = 0; i < 1000; ++i) on_audio_sample(NULL, (int16_t)i, (int16_t)-i);
    assert(g_rr_pcm.size() == 2000);
    int16_t pcm[2 * 512];
    assert(rr_gb_audio(pcm, 2 * 512) == 512);
    for (int i = 0; i < 512; ++i) assert(pcm[2 * i] == i && pcm[2 * i + 1] == -i);
    assert(rr_gb_audio(pcm, 2 * 512) == 488);
    for (int i = 0; i < 488; ++i) assert(pcm[2 * i] == 512 + i && pcm[2 * i + 1] == -512 - i);
    assert(rr_gb_audio(pcm, 2 * 512) == 0);
    /* A kit that never drains is bounded. */
    for (int i = 0; i < 40000; ++i) on_audio_sample(NULL, 1, 1);
    assert(g_rr_pcm.size() == (size_t)RR_GB_PCM_LIMIT_FRAMES * 2);
    g_rr_pcm.clear();
    const RrhkMachine* machine = rr_gb_adapter();
    assert(machine->audio_model == RRHK_AUDIO_RING && machine->audio_rate == 44100 && machine->audio_channels == 2);
    assert(machine->audio_margin_ms == 10 && machine->driven && machine->action_count == RR_GB_ACTIONS);
    printf("PASS: APU samples reach the kit in order as 44.1 kHz stereo frames, bounded.\n");
}

static void files_checks() {
    /* A data folder that does not exist is accepted and not created: a launch that saves nothing leaves no file. */
    const fs::path folder = fs::path("gb-latency-checks-folder");
    fs::remove_all(folder);
    assert(gb_platform_set_persistence_dir(folder.string().c_str()) && !fs::exists(folder));
    assert(gb_platform_set_persistence_dir(NULL));
    printf("PASS: a missing data folder is allowed and not created by reading.\n");
}

int main() {
    SDL_SetMainReady();
    SDL_setenv("SDL_VIDEODRIVER", "dummy", 1);
    SDL_setenv("SDL_AUDIODRIVER", "dummy", 1);
    SDL_setenv("SDL_RENDER_DRIVER", "software", 1);
    assert(gb_platform_init(1));
    GBContext* ctx = gb_context_create(NULL); assert(ctx);
    gb_platform_register_context(ctx);
    pad_checks(ctx);
    sample_checks(ctx);
    audio_checks();
    files_checks();
    gb_platform_shutdown();
    gb_context_destroy(ctx);
    return 0;
}
