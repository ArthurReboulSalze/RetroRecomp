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
#ifndef RR_MD_PLAYERS
#define RR_MD_PLAYERS 2
#endif
#ifndef RR_MD_MULTITAP
#define RR_MD_MULTITAP 0
#endif

/* One gamepad button for every player's table (players 3 and 4 play through a multitap game's adapter). */
#define PADS(button) {button, button, button, button}

/* Three-button pad; the six-button pad (a property of the game) adds X, Y, Z
 * and Mode. Bits follow the engine's pad word. */
#define DIRECTIONS \
    {"Up", L"Up", 1, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, PADS(SDL_CONTROLLER_BUTTON_DPAD_UP)}, \
    {"Down", L"Down", 2, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, PADS(SDL_CONTROLLER_BUTTON_DPAD_DOWN)}, \
    {"Left", L"Left", 4, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, PADS(SDL_CONTROLLER_BUTTON_DPAD_LEFT)}, \
    {"Right", L"Right", 8, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, PADS(SDL_CONTROLLER_BUTTON_DPAD_RIGHT)}

#if RR_MD_SIX_BUTTONS
enum { A, B, C, X, Y, Z, MODE, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 64, RRHK_FACE, 0, {SDL_SCANCODE_S, SDL_SCANCODE_KP_8}, PADS(SDL_CONTROLLER_BUTTON_A), NULL, SDLK_w},
    {"B", L"B", 16, RRHK_FACE, 0, {SDL_SCANCODE_D, SDL_SCANCODE_KP_9}, PADS(SDL_CONTROLLER_BUTTON_B), NULL, SDLK_x},
    {"C", L"C", 32, RRHK_FACE, 0, {SDL_SCANCODE_F, SDL_SCANCODE_KP_6}, PADS(SDL_CONTROLLER_BUTTON_X), NULL, SDLK_c},
    {"X", L"X", 256, RRHK_FACE, 0, {SDL_SCANCODE_E, SDL_SCANCODE_KP_0}, PADS(SDL_CONTROLLER_BUTTON_Y), NULL, SDLK_a},
    {"Y", L"Y", 512, RRHK_FACE, 0, {SDL_SCANCODE_R, SDL_SCANCODE_KP_PERIOD}, PADS(SDL_CONTROLLER_BUTTON_LEFTSHOULDER), NULL, SDLK_s},
    {"Z", L"Z", 1024, RRHK_FACE, 0, {SDL_SCANCODE_T, SDL_SCANCODE_KP_ENTER}, PADS(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER), NULL, SDLK_d},
    {"Mode", L"Mode", 2048, RRHK_SYSTEM, 0, {SDL_SCANCODE_RSHIFT, SDL_SCANCODE_KP_4}, PADS(SDL_CONTROLLER_BUTTON_BACK)},
    {"Start", L"Start", 128, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, PADS(SDL_CONTROLLER_BUTTON_START)},
    DIRECTIONS};
#else
enum { A, B, C, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 64, RRHK_FACE, 0, {SDL_SCANCODE_S, SDL_SCANCODE_KP_8}, PADS(SDL_CONTROLLER_BUTTON_A), NULL, SDLK_w},
    {"B", L"B", 16, RRHK_FACE, 0, {SDL_SCANCODE_D, SDL_SCANCODE_KP_9}, PADS(SDL_CONTROLLER_BUTTON_B), NULL, SDLK_x},
    {"C", L"C", 32, RRHK_FACE, 0, {SDL_SCANCODE_F, SDL_SCANCODE_KP_6}, PADS(SDL_CONTROLLER_BUTTON_X), NULL, SDLK_c},
    {"Start", L"Start", 128, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, PADS(SDL_CONTROLLER_BUTTON_START)},
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

/* The engine's sound is its own device (own_audio). The kit's sound stage (volume, mute, audio filter, decision D12) runs on what
 * the engine's callback gives the device, and the output the player chose is the one the engine opens (megadrive_audio.py). */
extern void (*rr_md_audio_stage)(void *pcm, unsigned frames, int channels, int floating, int rate);
extern const char *rr_md_audio_device_name;
extern int rr_md_audio_reopen(void);
extern unsigned rr_md_audio_device_id(void);
/* Sync to display (D30): while the kit paces the game by the screen, base = machine Hz / refresh Hz (1.0 otherwise); the
 * engine's bridge then takes base x the machine's sound as a feed-forward on its step (megadrive_audio.py). */
extern void rr_md_audio_base(double base);
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
static void sound_ready(void) {
    rr_md_audio_device_name = rrhk_audio_device();
    rr_md_audio_stage = rrhk_options_audio;
}
static SDL_AudioDeviceID audio_device_id(void) { return (SDL_AudioDeviceID)rr_md_audio_device_id(); }
static bool audio_reopen(void) {
    rr_md_audio_device_name = rrhk_audio_device();
    return rr_md_audio_reopen() != 0;
}

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    if (RR16_GUN) {
        rrhk_menu_line(ctx, y, rrhk_tr("Mouse: aim | Left: fire", "Souris : viser | Gauche : tirer"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, RR16_GUN == RR_GUN_SCOPE ? rrhk_tr("Right: cursor | Middle/Enter: gun pause", "Droit : curseur | Milieu/Entree : pause gun") :
            rrhk_tr("Right: B | Middle: C | Enter: Start", "Droit : B | Milieu : C | Entree : Start"));
    } else if (RR_MD_SIX_BUTTONS) {
        rrhk_menu_line(ctx, y, rrhk_tr("Arrows; S/D/F: A/B/C; Enter: Start", "Fleches; S/D/F : A/B/C; Entree : Start"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("E/R/T: X/Y/Z; Right Shift: Mode", "E/R/T : X/Y/Z; Maj droite : Mode"));
    } else {
        rrhk_menu_line(ctx, y, rrhk_tr("Arrows + S/D/F; Enter Start", "Fleches + S/D/F; Entree Start"));
        rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Two controllers supported", "Deux manettes disponibles"));
    }
    rrhk_help_sound_line(ctx, y + 2 * RR_MENU_LINE);
}

/* Two pads, or four in a game made for the Team Player, the 4 Way Play or the J-Cart (retrorecomp/megadrive_multitap.py). */
static int players(void) { return RR_MD_PLAYERS; }
void rr16_md_extra_pads(uint16_t p3, uint16_t p4);
/* Players 3 and 4 are set here, in the frame itself, never in before_frame: a frame run again after a correction in a
 * multiplayer session (a "silent" frame) calls run_frame with the session's words but not before_frame. Alone, the pads
 * of the frame about to run are the same either way. */
static uint64_t extra_frame;
static bool run_frame(uint16_t p1, uint16_t p2) {
    if (RR_MD_PLAYERS > 2) {
        rr16_md_extra_pads(rrhk_pad_word(2, extra_frame), rrhk_pad_word(3, extra_frame));
        ++extra_frame;
    }
    return rr16_frame(p1, p2);
}
/* Multiplayer (hostkit_session.h): a Team Player / 4 Way Play game plays as alone with that many players: the adapter on
 * the control ports stays plugged only when the session has three or four ports (two players play on two plain pads,
 * as on a console without the adapter). The J-Cart is the cartridge itself and stays. The host's cartridge save (battery
 * SRAM or EEPROM) is what every seat plays on. */
extern int rr_md_tap_mode;
size_t rr16_md_session_save(void *out, size_t capacity);
bool rr16_md_session_save_put(const void *in, size_t size);
static void session_begin(uint64_t clock) {
    (void)clock;
    if (RR_MD_MULTITAP == 1) rr_md_tap_mode = rrhk_session_ports() >= 3 ? 1 : 0;
}
/* Multiplayer (hostkit_session.h): md_backend.c gives the digest, holds the guest's cartridge save and gives the in-process
 * snapshot of the rollback tier and of the host's F8 / F9 for everyone (none in a build without step code: delay tier). */
uint64_t rr16_md_digest(void);
void rr16_md_side_effects(bool allowed);
size_t rr16_md_snap_bound(void);
size_t rr16_md_snap_save(void *buffer, size_t capacity);
bool rr16_md_snap_load(const void *buffer, size_t size);
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
            .table_players = RR_MD_PLAYERS, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
            .max_width = RR16_WIDTH, .max_height = RR16_HEIGHT, .frame_seconds = RR16_FRAME_SECONDS,
            /* Most games are 320 wide and the engine says 256 until its first frame: the window opens for 320 x 240, the larger of the
             * NTSC (224) and PAL (240) pictures. */
            .open_width = 320, .open_height = 240,
            .pointer = RR16_GUN, .own_audio = true,
            .reset = rr16_reset, .run_frame = run_frame, .pause = rr16_pause,
            .pixels = rr16_pixels, .visible_width = rr16_visible_width, .visible_height = rr16_visible_height,
            .raster_height = rr16_raster_height, .display_width = rr16_visible_width,
            .audio = rr16_audio, .interpreted = rr16_interpreted, .audio_interpreted = rr16_audio_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .pointer_input = pointer_input,
            .digest = rr16_md_digest, .side_effects = rr16_md_side_effects,
            .snap_bound = rr16_md_snap_bound, .snap_save = rr16_md_snap_save,
            .snap_load = rr16_md_snap_load,
            .session_save = rr16_md_session_save, .session_save_put = rr16_md_session_save_put,
            .session_begin = session_begin,
            .page = RR16_GUN ? &rrhk_pointer_page : NULL,
            .help_controls = help_controls, .timing_report = timing_report,
            .sound_ready = sound_ready, .audio_reopen = audio_reopen, .audio_device_id = audio_device_id,
            .audio_ratio = rr_md_audio_base,
        };
    }
    return &machine;
}

int rr16_sdl_main(const char *title, int scale) { return rrhk_main(rrhk_adapter(), title, scale); }
