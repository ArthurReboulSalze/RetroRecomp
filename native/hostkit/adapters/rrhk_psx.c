/* PlayStation adapter: the machine contract of the host kit over the PlayStation game (psx_main.c, psx_session.c on Beetle
 * PSX). Two players with DualShock pads (the sticks join when the kit passes them: HOST_KIT D14 work), the core's picture
 * at the console's resolution, its sound as 44.1 kHz stereo through the kit's ring. Original Retro-Recomp code: MIT; the
 * game it is linked into is GPL-2.0 as a whole (licenses/beetle-psx.md). */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <wchar.h>
#include "platform_io.h"
#include "console16_state.h"
#include "retro_menu.h"
#include "psx_game.h"
#include "psx_session.h"
#include "hostkit/hostkit.h"

int rr_psx_host_frame(const uint16_t pads[2]);
size_t rr_psx_take_audio(int16_t *out, size_t capacity);
unsigned rr_psx_frame_index(void);
int rr_psx_host_reset(void);
RrPsxSession *rr_psx_host_session(void);

/* The bits are the session's (libretro's order of the PlayStation pad). Twelve actions: the kit's table holds twelve until
 * it grows (L2, R2, L3, R3 and the Analog button follow then). */
#define PADS(button) {button, button, button, button}
enum { CROSS, CIRCLE, SQUARE, TRIANGLE, L1, R1, START, SELECT, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"Cross", L"Cross", RR_PSX_PAD_B, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_2}, PADS(SDL_CONTROLLER_BUTTON_A)},
    {"Circle", L"Circle", RR_PSX_PAD_A, RRHK_FACE, SDLK_c, {SDL_SCANCODE_C, SDL_SCANCODE_KP_6}, PADS(SDL_CONTROLLER_BUTTON_B)},
    {"Square", L"Square", RR_PSX_PAD_Y, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_4}, PADS(SDL_CONTROLLER_BUTTON_X)},
    {"Triangle", L"Triangle", RR_PSX_PAD_X, RRHK_FACE, SDLK_a, {SDL_SCANCODE_A, SDL_SCANCODE_KP_8}, PADS(SDL_CONTROLLER_BUTTON_Y)},
    {"L1", L"L1", RR_PSX_PAD_L, RRHK_SYSTEM, SDLK_s, {SDL_SCANCODE_S, SDL_SCANCODE_KP_7}, PADS(SDL_CONTROLLER_BUTTON_LEFTSHOULDER)},
    {"R1", L"R1", RR_PSX_PAD_R, RRHK_SYSTEM, SDLK_d, {SDL_SCANCODE_D, SDL_SCANCODE_KP_9}, PADS(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)},
    {"Start", L"Start", RR_PSX_PAD_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER}, PADS(SDL_CONTROLLER_BUTTON_START)},
    {"Select", L"Select", RR_PSX_PAD_SELECT, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_0}, PADS(SDL_CONTROLLER_BUTTON_BACK)},
    {"Up", L"Up", RR_PSX_PAD_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, PADS(SDL_CONTROLLER_BUTTON_DPAD_UP)},
    {"Down", L"Down", RR_PSX_PAD_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_1}, PADS(SDL_CONTROLLER_BUTTON_DPAD_DOWN)},
    {"Left", L"Left", RR_PSX_PAD_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_3}, PADS(SDL_CONTROLLER_BUTTON_DPAD_LEFT)},
    {"Right", L"Right", RR_PSX_PAD_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_PERIOD}, PADS(SDL_CONTROLLER_BUTTON_DPAD_RIGHT)}};

static int players(void) { return 2; }
static void reset(void) { rr_psx_host_reset(); rrhk_autofire_reset(); }
static bool run_frame(uint16_t p1, uint16_t p2) { const uint16_t pads[2] = {p1, p2}; return rr_psx_host_frame(pads) != 0; }
static void pause_machine(bool paused) { (void)paused; }
/* The kit reads the picture with a stride of max_width; the session keeps its rows packed at the picture's width. */
static uint32_t frame_store[RR_PSX_MAX_WIDTH * RR_PSX_MAX_HEIGHT];
static const uint32_t *pixels(void) {
    int w = 0, h = 0;
    const uint32_t *packed = rr_psx_picture(rr_psx_host_session(), &w, &h, NULL);
    if (w > RR_PSX_MAX_WIDTH) w = RR_PSX_MAX_WIDTH;
    if (h > RR_PSX_MAX_HEIGHT) h = RR_PSX_MAX_HEIGHT;
    for (int y = 0; y < h; ++y)
        memcpy(frame_store + (size_t)y * RR_PSX_MAX_WIDTH, packed + (size_t)y * w, (size_t)w * sizeof(uint32_t));
    return frame_store;
}
static int visible_width(void) { int w = 0; rr_psx_picture(rr_psx_host_session(), &w, NULL, NULL); return w ? w : 320; }
static int visible_height(void) { int h = 0; rr_psx_picture(rr_psx_host_session(), NULL, &h, NULL); return h ? h : 240; }
static int raster_height(void) { return visible_height(); }
/* The core states the display aspect of its picture (4:3 on a television); the kit wants the width that gives it. */
static int display_width(void) {
    double aspect = 0;
    int h = 0;
    rr_psx_picture(rr_psx_host_session(), NULL, &h, &aspect);
    if (!h) h = 240;
    if (aspect <= 0) aspect = 4.0 / 3.0;
    /* 480-line pictures are interlaced fields of a 4:3 screen too: the width follows the 240-line frame. */
    return (int)(aspect * (h > 288 ? h / 2 : h) + 0.5) * (h > 288 ? 2 : 1);
}
static size_t audio(int16_t *pcm, size_t capacity) { return rr_psx_take_audio(pcm, capacity) / 2; }
static bool audio_enable(unsigned rate) { return rate == RR_PSX_AUDIO_RATE; }
static uint64_t interpreted(void) { return rr_psx_interpreted(rr_psx_host_session()); }
static uint64_t audio_interpreted(void) { return 0; }   /* the SPU is a device of the one CPU: there is no sound CPU */
static uint64_t input_frame(void) { return rr_psx_frame_index(); }

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("Arrows; X Cross, C Circle, W Square, A Triangle", "Fleches; X Croix, C Rond, W Carre, A Triangle"));
    rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("S/D: L1/R1; Enter Start; Shift Select", "S/D : L1/R1; Entree Start; Maj Select"));
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = L"PlayStation", .console_name = "PlayStation",
            .table_players = 2, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
            .max_width = RR_PSX_MAX_WIDTH, .max_height = RR_PSX_MAX_HEIGHT,
            .frame_seconds = 1.0 / RR_PSX_FPS,
            .audio_model = RRHK_AUDIO_RING, .audio_rate = RR_PSX_AUDIO_RATE, .audio_enable = audio_enable,
            .audio_channels = 2,
            .reset = reset, .run_frame = run_frame, .pause = pause_machine,
            .pixels = pixels, .visible_width = visible_width, .visible_height = visible_height,
            .raster_height = raster_height, .display_width = display_width,
            .audio = audio, .interpreted = interpreted, .audio_interpreted = audio_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .input_frame = input_frame, .help_controls = help_controls,
        };
    }
    return &machine;
}

int rr_psx_sdl_main(const char *title, int scale) { return rrhk_main(rrhk_adapter(), title, scale); }
