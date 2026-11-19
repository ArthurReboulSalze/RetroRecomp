/* Game Boy Advance adapter: the machine contract of the host kit over the pinned gbarecomp engine, which native/gba_machine.cpp
 * drives one frame at a time (the engine's own window loop is not used). Original Retro-Recomp code: MIT; the linked engine
 * keeps its own terms (PolyForm Noncommercial) and so does the player's own BIOS, which the exported game carries privately.
 * This file is the machine's own: the ten buttons and their defaults, the picture (240 x 160), the sound (mono, 32768 Hz), the
 * quick state and the entry the engine's driver reaches (rrhk_main). One player. A multiplayer session (hostkit_session.h) plays on the delay tier: the digest
 * comes from native/gba_machine.cpp and there is no in-process snapshot (the engine's state container allocates per call), so no rollback. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <wchar.h>
#include "gba_machine.h"
#include "retro_menu.h"
#include "hostkit/hostkit.h"

/* The pad word is the hardware's KEYINPUT, positive logic: bit 0 A, 1 B, 2 Select, 3 Start, 4 Right, 5 Left, 6 Up, 7 Down,
 * 8 R, 9 L. The machine inverts it for the register. */
enum { A, B, L, R, SELECT, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 0x001, RRHK_FACE, 0, {SDL_SCANCODE_D}, {SDL_CONTROLLER_BUTTON_B}, NULL, SDLK_x},
    {"B", L"B", 0x002, RRHK_FACE, 0, {SDL_SCANCODE_S}, {SDL_CONTROLLER_BUTTON_A}, NULL, SDLK_w},
    {"L", L"L", 0x200, RRHK_SYSTEM, 0, {SDL_SCANCODE_E}, {SDL_CONTROLLER_BUTTON_LEFTSHOULDER}, NULL, SDLK_a},
    {"R", L"R", 0x100, RRHK_SYSTEM, 0, {SDL_SCANCODE_R}, {SDL_CONTROLLER_BUTTON_RIGHTSHOULDER}, NULL, SDLK_s},
    {"Select", L"Select", 0x004, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT}, {SDL_CONTROLLER_BUTTON_BACK}},
    {"Start", L"Start", 0x008, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN}, {SDL_CONTROLLER_BUTTON_START}},
    {"Up", L"Up", 0x040, RRHK_DIR, 0, {SDL_SCANCODE_UP}, {SDL_CONTROLLER_BUTTON_DPAD_UP}},
    {"Down", L"Down", 0x080, RRHK_DIR, 0, {SDL_SCANCODE_DOWN}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
    {"Left", L"Left", 0x020, RRHK_DIR, 0, {SDL_SCANCODE_LEFT}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
    {"Right", L"Right", 0x010, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
};

#define WIDTH 240
#define HEIGHT 160

static int players(void) { return 1; }
static int width(void) { return WIDTH; }
static int height(void) { return HEIGHT; }

static void reset(void) { rrgba_reset(); }
static bool run_frame(uint16_t p1, uint16_t p2) { (void)p2; return rrgba_frame(p1); }
static void pause_machine(bool paused) { (void)paused; }
static size_t audio(int16_t *pcm, size_t capacity) { return rrgba_audio(pcm, capacity); }
static bool audio_enable(unsigned rate) { (void)rate; return true; }
static uint64_t interpreted(void) { return rrgba_interpreted(); }
static uint64_t no_count(void) { return 0; }
static uint64_t input_frame(void) { return rrgba_frames(); }
static bool state_ready(void) { return true; }

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("GBA: arrows + D (A), S (B), E (L), R (R)", "GBA : fleches + D (A), S (B), E (L), R (R)"));
    rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Enter Start, Shift Select", "Entree Start, Maj Select"));
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = L"GameBoyAdvance", .console_name = "Game Boy Advance",
            .table_players = 1, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
            .max_width = WIDTH, .max_height = HEIGHT, .frame_seconds = 280896.0 / 16777216.0,
            .pointer = RRHK_POINTER_NONE,
            .audio_model = RRHK_AUDIO_RING, .audio_rate = 32768u, .audio_enable = audio_enable,
            .save_failed_en = "Unable to save quick state", .save_failed_fr = "Impossible de sauvegarder",
            .reset = reset, .run_frame = run_frame, .pause = pause_machine,
            .pixels = rrgba_pixels, .visible_width = width, .visible_height = height,
            .raster_height = height, .display_width = width,
            .audio = audio, .interpreted = interpreted, .audio_interpreted = no_count,
            .state_path = rrgba_state_path, .state_ready = state_ready, .state_file = rrgba_state_file,
            .input_frame = input_frame,
            .digest = rrgba_digest, .side_effects = rrgba_side_effects,
            .session_save = rrgba_session_save, .session_save_put = rrgba_session_save_put, .session_begin = rrgba_session_begin,
            .help_controls = help_controls,
        };
    }
    return &machine;
}
