/* Super Nintendo adapter: the machine contract of the host kit over the rr16_*
 * functions of the Super Nintendo backend. Original RetroRecomp code: MIT; the
 * linked engine keeps its own terms. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "retro_menu.h"
#include "hostkit/hostkit.h"

enum { A, B, X, Y, L, R, SELECT, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 256, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
    {"B", L"B", 1, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
    {"X", L"X", 512, RRHK_FACE, SDLK_a, {SDL_SCANCODE_A, SDL_SCANCODE_KP_0}, {SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_X}},
    {"Y", L"Y", 2, RRHK_FACE, SDLK_s, {SDL_SCANCODE_S, SDL_SCANCODE_KP_PERIOD}, {SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_Y}},
    {"L", L"L", 1024, RRHK_SYSTEM, SDLK_q, {SDL_SCANCODE_Q, SDL_SCANCODE_KP_DIVIDE}, {SDL_CONTROLLER_BUTTON_LEFTSHOULDER, SDL_CONTROLLER_BUTTON_LEFTSHOULDER}},
    {"R", L"R", 2048, RRHK_SYSTEM, SDLK_e, {SDL_SCANCODE_E, SDL_SCANCODE_KP_MULTIPLY}, {SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER}},
    {"Select", L"Select", 4, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_4}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
    {"Start", L"Start", 8, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
    {"Up", L"Up", 16, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
    {"Down", L"Down", 32, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
    {"Left", L"Left", 64, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
    {"Right", L"Right", 128, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}}};

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    if (RR16_GUN) {
        rrhk_menu_line(ctx, y, rrhk_tr("Mouse: aim | Left: fire", "Souris : viser | Gauche : tirer"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, RR16_GUN == RR_GUN_SCOPE ? rrhk_tr("Right: cursor | Middle/Enter: gun pause", "Droit : curseur | Milieu/Entree : pause gun") :
            rrhk_tr("Right: B | Middle: C | Enter: Start", "Droit : B | Milieu : C | Entree : Start"));
    } else {
        rrhk_menu_line(ctx, y, rrhk_tr("Arrows + W/X/A/S; Q/E shoulders", "Fleches + W/X/A/S; Q/E gachettes"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Enter Start; Shift Select", "Entree Start; Maj Select"));
    }
    rrhk_help_sound_line(ctx, y + 2 * RR_MENU_LINE);
}

static int players(void) { return 2; }
static int display_width(void) { return 256; }
static void pointer_input(RrhkPointer p) {
    rr16_gun_input((Rr16GunInput){.x = p.x, .y = p.y, .fire = p.fire, .aux = p.aux, .secondary = p.secondary,
                                  .start = p.start, .turbo = p.turbo, .pause = p.pause, .offscreen = p.offscreen});
}

typedef char pointer_kinds_agree[(RRHK_POINTER_MENACER == RR_GUN_MENACER && RRHK_POINTER_JUSTIFIER == RR_GUN_JUSTIFIER &&
                                  RRHK_POINTER_SCOPE == RR_GUN_SCOPE) ? 1 : -1];

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = RR16_SECTION, .console_name = RR16_CONSOLE,
            .table_players = 2, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
            .max_width = RR16_WIDTH, .max_height = RR16_HEIGHT, .frame_seconds = RR16_FRAME_SECONDS,
            .pointer = RR16_GUN,
            .reset = rr16_reset, .run_frame = rr16_frame, .pause = rr16_pause,
            .pixels = rr16_pixels, .visible_width = rr16_visible_width, .visible_height = rr16_visible_height,
            .raster_height = rr16_raster_height, .display_width = display_width,
            .audio = rr16_audio, .interpreted = rr16_interpreted, .audio_interpreted = rr16_audio_interpreted,
            .device_interpreted = rr16_device_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .pointer_input = pointer_input,
            .page = RR16_GUN ? &rrhk_pointer_page : NULL,
            .help_controls = help_controls,
        };
    }
    return &machine;
}

int rr16_sdl_main(const char *title, int scale) { return rrhk_main(rrhk_adapter(), title, scale); }
