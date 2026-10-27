/* Mega Drive adapter: the machine contract of the host kit over the rr16_*
 * functions of the Mega Drive backend. Original RetroRecomp code: MIT; the
 * linked engine keeps its own terms. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "retro_menu.h"
#include "hostkit/hostkit.h"

/* Three-button pad; the six-button pad (a property of the game) adds X, Y, Z
 * and Mode. Bits follow the engine's pad word. */
#define DIRECTIONS \
    {"Up", L"Up", 1, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}}, \
    {"Down", L"Down", 2, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}}, \
    {"Left", L"Left", 4, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}}, \
    {"Right", L"Right", 8, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}}

#if RR_MD_SIX_BUTTONS
enum { A, B, C, X, Y, Z, MODE, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 64, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
    {"B", L"B", 16, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
    {"C", L"C", 32, RRHK_FACE, SDLK_c, {SDL_SCANCODE_C, SDL_SCANCODE_KP_6}, {SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_X}},
    {"X", L"X", 256, RRHK_FACE, SDLK_a, {SDL_SCANCODE_A, SDL_SCANCODE_KP_0}, {SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_Y}},
    {"Y", L"Y", 512, RRHK_FACE, SDLK_s, {SDL_SCANCODE_S, SDL_SCANCODE_KP_PERIOD}, {SDL_CONTROLLER_BUTTON_LEFTSHOULDER, SDL_CONTROLLER_BUTTON_LEFTSHOULDER}},
    {"Z", L"Z", 1024, RRHK_FACE, SDLK_d, {SDL_SCANCODE_D, SDL_SCANCODE_KP_ENTER}, {SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, SDL_CONTROLLER_BUTTON_RIGHTSHOULDER}},
    {"Mode", L"Mode", 2048, RRHK_SYSTEM, 0, {SDL_SCANCODE_RSHIFT, SDL_SCANCODE_KP_4}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
    {"Start", L"Start", 128, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
    DIRECTIONS};
#else
enum { A, B, C, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 64, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
    {"B", L"B", 16, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
    {"C", L"C", 32, RRHK_FACE, SDLK_c, {SDL_SCANCODE_C, SDL_SCANCODE_KP_6}, {SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_X}},
    {"Start", L"Start", 128, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
    DIRECTIONS};
#endif

extern void rr_md_host_timing(uint64_t *simulation, uint64_t *delivery);
extern void rr_md_engine_timing(uint64_t *cpu_bus, uint64_t *vdp);
extern void rr_md_audio_delivery_timing(uint64_t *wait, uint64_t *pull, uint64_t *calls, uint64_t *stretches);

static void timing_report(FILE *file, Uint64 frequency) {
    uint64_t simulation = 0, delivery = 0; rr_md_host_timing(&simulation, &delivery);
    fprintf(file, ",\"md_simulation_seconds\":%.9f,\"md_host_audio_seconds\":%.9f",
        (double)simulation / frequency, (double)delivery / frequency);
    uint64_t cpu_bus = 0, vdp = 0; rr_md_engine_timing(&cpu_bus, &vdp);
    uint64_t rest = simulation > cpu_bus + vdp ? simulation - cpu_bus - vdp : 0;
    fprintf(file, ",\"md_cpu_bus_seconds\":%.9f,\"md_vdp_raster_seconds\":%.9f,\"md_simulation_other_seconds\":%.9f",
        (double)cpu_bus / frequency, (double)vdp / frequency, (double)rest / frequency);
    uint64_t wait = 0, pull = 0, calls = 0, stretches = 0;
    rr_md_audio_delivery_timing(&wait, &pull, &calls, &stretches);
    fprintf(file, ",\"md_audio_lock_wait_seconds\":%.9f,\"md_audio_callback_seconds\":%.9f,\"md_audio_callbacks\":%llu,\"md_audio_stretch_events\":%llu",
        (double)wait / frequency, (double)pull / frequency, (unsigned long long)calls, (unsigned long long)stretches);
}

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    if (RR16_GUN) {
        rrhk_menu_line(ctx, y, rrhk_tr("Mouse: aim | Left: fire", "Souris : viser | Gauche : tirer"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, RR16_GUN == RR_GUN_SCOPE ? rrhk_tr("Right: cursor | Middle/Enter: gun pause", "Droit : curseur | Milieu/Entree : pause gun") :
            rrhk_tr("Right: B | Middle: C | Enter: Start", "Droit : B | Milieu : C | Entree : Start"));
    } else if (RR_MD_SIX_BUTTONS) {
        rrhk_menu_line(ctx, y, rrhk_tr("Arrows; W/X/C: A/B/C; Enter: Start", "Fleches; W/X/C : A/B/C; Entree : Start"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("A/S/D: X/Y/Z; Right Shift: Mode", "A/S/D : X/Y/Z; Maj droite : Mode"));
    } else {
        rrhk_menu_line(ctx, y, rrhk_tr("Arrows + W/X/C; Enter Start", "Fleches + W/X/C; Entree Start"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Two controllers supported", "Deux manettes disponibles"));
    }
    rrhk_help_sound_line(ctx, y + 2 * RR_MENU_LINE);
}

static int players(void) { return 2; }
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
            .pointer = RR16_GUN, .own_audio = true,
            .reset = rr16_reset, .run_frame = rr16_frame, .pause = rr16_pause,
            .pixels = rr16_pixels, .visible_width = rr16_visible_width, .visible_height = rr16_visible_height,
            .raster_height = rr16_raster_height, .display_width = rr16_visible_width,
            .audio = rr16_audio, .interpreted = rr16_interpreted, .audio_interpreted = rr16_audio_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .pointer_input = pointer_input,
            .page = RR16_GUN ? &rrhk_pointer_page : NULL,
            .help_controls = help_controls, .timing_report = timing_report,
        };
    }
    return &machine;
}

int rr16_sdl_main(const char *title, int scale) { return rrhk_main(rrhk_adapter(), title, scale); }
