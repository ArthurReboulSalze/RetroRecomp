/* PC Engine adapter: the machine contract of the host kit over the PC Engine game (pce_main.c, pce_machine.cpp).
 * Four players through the kit (the multitap takes five: the fifth port stays released, a named limit), the
 * 2- and 6-button pads, the picture of the HuC6260 at its dot clock, and the PSG as 44.1 kHz stereo through the
 * kit's ring. Original RetroRecomp code: MIT; the engine keeps its own MIT terms (licenses/pcenginerecomp.md). */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <wchar.h>
#include "platform_io.h"
#include "console16_state.h"
#include "retro_menu.h"
#include "pce_game.h"
#include "pce_machine.h"
#include "hostkit/hostkit.h"

int rr_pce_host_frame(const uint16_t pads[4]);
size_t rr_pce_take_audio(int16_t *out, size_t capacity);
unsigned rr_pce_frame_index(void);
int rr_pce_reset(void);

/* Bits are the engine's pad masks: I, II, Select, Run, Up, Right, Down, Left, then III to VI on six-button pads. */
#define PADS(button) {button, button, button, button}
enum { I, II, III, IV, V, VI, SELECT, RUN, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"I", L"I", 0x001, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_9}, PADS(SDL_CONTROLLER_BUTTON_B)},
    {"II", L"II", 0x002, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_8}, PADS(SDL_CONTROLLER_BUTTON_A)},
    {"III", L"III", 0x100, RRHK_FACE, SDLK_c, {SDL_SCANCODE_C, SDL_SCANCODE_KP_7}, PADS(SDL_CONTROLLER_BUTTON_X)},
    {"IV", L"IV", 0x200, RRHK_FACE, SDLK_a, {SDL_SCANCODE_A, SDL_SCANCODE_KP_4}, PADS(SDL_CONTROLLER_BUTTON_Y)},
    {"V", L"V", 0x400, RRHK_FACE, SDLK_s, {SDL_SCANCODE_S, SDL_SCANCODE_KP_6}, PADS(SDL_CONTROLLER_BUTTON_LEFTSHOULDER)},
    {"VI", L"VI", 0x800, RRHK_FACE, SDLK_d, {SDL_SCANCODE_D, SDL_SCANCODE_KP_PLUS}, PADS(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)},
    {"Select", L"Select", 0x004, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_0}, PADS(SDL_CONTROLLER_BUTTON_BACK)},
    {"Run", L"Run", 0x008, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER}, PADS(SDL_CONTROLLER_BUTTON_START)},
    {"Up", L"Up", 0x010, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, PADS(SDL_CONTROLLER_BUTTON_DPAD_UP)},
    {"Down", L"Down", 0x040, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, PADS(SDL_CONTROLLER_BUTTON_DPAD_DOWN)},
    {"Left", L"Left", 0x080, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, PADS(SDL_CONTROLLER_BUTTON_DPAD_LEFT)},
    {"Right", L"Right", 0x020, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, PADS(SDL_CONTROLLER_BUTTON_DPAD_RIGHT)}};

static uint16_t extra_pads[2];
static unsigned width, height;

static int players(void) { return RR_PCE_PLAYERS; }
static void reset(void) { rr_pce_reset(); rrhk_autofire_reset(); }
static bool run_frame(uint16_t p1, uint16_t p2) {
    const uint16_t pads[4] = {p1, p2, extra_pads[0], extra_pads[1]};
    if (!rr_pce_host_frame(pads)) return false;
    pce_machine_pixels(&width, &height);
    return true;
}
static void before_frame(const RrhkAudioProbe *audio, uint64_t input_frame) {
    (void)audio;
    extra_pads[0] = players() > 2 ? rrhk_pad_word(2, input_frame) : 0;
    extra_pads[1] = players() > 3 ? rrhk_pad_word(3, input_frame) : 0;
}
static void pause_machine(bool paused) { (void)paused; }
static const uint32_t *pixels(void) { return pce_machine_pixels(&width, &height); }
static int visible_width(void) { pce_machine_pixels(&width, &height); return width ? (int)width : 256; }
static int visible_height(void) { pce_machine_pixels(&width, &height); return height ? (int)height : 240; }
static int raster_height(void) { return visible_height(); }
/* The HuC6260 dot clocks (5.37, 7.16 and 10.74 MHz) give pixels 8/7, 6/7 and 4/7 as wide as tall on a 4:3 set. */
static int display_width(void) {
    static const int numerator[4] = {8, 6, 4, 4};
    const unsigned clock = pce_machine_dot_clock() & 3u;
    return (visible_width() * numerator[clock] + 3) / 7;
}
/* Ring model, stereo: the frames of the last guest frame (two int16 values each). */
static size_t audio(int16_t *pcm, size_t capacity) { return rr_pce_take_audio(pcm, capacity) / 2; }
static bool audio_enable(unsigned rate) { return rate == PCE_AUDIO_RATE; }
static uint64_t interpreted(void) { PceCounters c; pce_machine_counters(&c); return c.interpreted; }
static uint64_t audio_interpreted(void) { return 0; }   /* the PSG is part of the HuC6280: there is no sound CPU */
static uint64_t input_frame(void) { return rr_pce_frame_index(); }

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("Arrows; X: I, W: II; Enter Run; Shift Select",
                                   "Fleches; X : I, W : II; Entree Run; Maj Select"));
    rrhk_menu_line(ctx, y + RR_MENU_LINE, RR_PCE_PAD_BUTTONS == 6 ? rrhk_tr("C/A/S/D: III-VI (six-button pad)",
                                                                              "C/A/S/D : III-VI (manette six boutons)")
                                                                   : rrhk_tr("Up to four players", "Jusqu'a quatre joueurs"));
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = L"PCEngine", .console_name = "PC Engine",
            .table_players = 4, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = RUN,
            .max_width = PCE_MAX_WIDTH, .max_height = PCE_MAX_HEIGHT, .frame_seconds = 1365.0 * 262.0 / 21477272.7,
            .audio_model = RRHK_AUDIO_RING, .audio_rate = PCE_AUDIO_RATE, .audio_enable = audio_enable,
            .audio_channels = 2,
            .reset = reset, .run_frame = run_frame, .pause = pause_machine,
            .pixels = pixels, .visible_width = visible_width, .visible_height = visible_height,
            .raster_height = raster_height, .display_width = display_width,
            .audio = audio, .interpreted = interpreted, .audio_interpreted = audio_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .input_frame = input_frame, .before_frame = before_frame, .help_controls = help_controls,
        };
    }
    return &machine;
}

int rr_pce_sdl_main(const char *title, int scale) { return rrhk_main(rrhk_adapter(), title, scale); }
