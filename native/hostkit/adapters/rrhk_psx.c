/* PlayStation adapter: the machine contract of the host kit over the PlayStation game (psx_main.c, psx_session.c on Beetle
 * PSX). Two players with DualShock pads (seventeen controls: the sixteen bits of the pad, both sticks, L2 and R2 on the
 * triggers, and the Analog button), vibration, the graphics page of F3 (HOST_KIT.md section 2.4, D14), the picture as large as
 * the internal resolution makes it, the Change disc action of multi-disc games, the sound as 44.1 kHz stereo through the
 * kit's ring. Original Retro-Recomp code: MIT; the game it is linked into is GPL-2.0 as a whole (licenses/beetle-psx.md). */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "platform_io.h"
#include "console16_state.h"
#include "retro_menu.h"
#include "psx_game.h"
#include "psx_session.h"
#include "hostkit/hostkit.h"
#include "hostkit/hostkit_internal.h"

int rr_psx_host_frame(const uint16_t pads[2], const int16_t axes[2][4]);
void rr_psx_host_analog(int player);
size_t rr_psx_take_audio(int16_t *out, size_t capacity);
unsigned rr_psx_frame_index(void);
int rr_psx_host_reset(void);
RrPsxSession *rr_psx_host_session(void);

/* The bits are the session's (libretro's order of the pad). The Analog button and Change disc are host-side actions (bit 0):
 * the Analog button is a button of the DualShock that libretro has no bit for, given to the session apart; Change disc is
 * the kit's. `ps_bit` is the bit the console itself reads for the action (Sony's order: Select 0 ... Square 15; the Analog
 * button 16), what the input check of the game compares. */
#define PADS(button) {button, button, button, button}
#define NO_PAD ((SDL_GameControllerButton)SDL_CONTROLLER_BUTTON_INVALID)
enum { CROSS, CIRCLE, SQUARE, TRIANGLE, L1, R1, L2, R2, L3, R3, START, SELECT, UP, DOWN, LEFT, RIGHT, ANALOG, DISC, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"Cross", L"Cross", RR_PSX_PAD_B, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_2}, PADS(SDL_CONTROLLER_BUTTON_A)},
    {"Circle", L"Circle", RR_PSX_PAD_A, RRHK_FACE, SDLK_c, {SDL_SCANCODE_C, SDL_SCANCODE_KP_6}, PADS(SDL_CONTROLLER_BUTTON_B)},
    {"Square", L"Square", RR_PSX_PAD_Y, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_4}, PADS(SDL_CONTROLLER_BUTTON_X)},
    {"Triangle", L"Triangle", RR_PSX_PAD_X, RRHK_FACE, SDLK_a, {SDL_SCANCODE_A, SDL_SCANCODE_KP_8}, PADS(SDL_CONTROLLER_BUTTON_Y)},
    {"L1", L"L1", RR_PSX_PAD_L, RRHK_SYSTEM, SDLK_s, {SDL_SCANCODE_S, SDL_SCANCODE_KP_7}, PADS(SDL_CONTROLLER_BUTTON_LEFTSHOULDER)},
    {"R1", L"R1", RR_PSX_PAD_R, RRHK_SYSTEM, SDLK_d, {SDL_SCANCODE_D, SDL_SCANCODE_KP_9}, PADS(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)},
    {"L2", L"L2", RR_PSX_PAD_L2, RRHK_SYSTEM, SDLK_q, {SDL_SCANCODE_Q, SDL_SCANCODE_KP_MULTIPLY}, PADS(RRHK_PAD_LEFT_TRIGGER)},
    {"R2", L"R2", RR_PSX_PAD_R2, RRHK_SYSTEM, SDLK_e, {SDL_SCANCODE_E, SDL_SCANCODE_KP_MINUS}, PADS(RRHK_PAD_RIGHT_TRIGGER)},
    {"L3", L"L3", RR_PSX_PAD_L3, RRHK_SYSTEM, SDLK_z, {SDL_SCANCODE_Z, SDL_SCANCODE_UNKNOWN}, PADS(SDL_CONTROLLER_BUTTON_LEFTSTICK)},
    {"R3", L"R3", RR_PSX_PAD_R3, RRHK_SYSTEM, SDLK_v, {SDL_SCANCODE_V, SDL_SCANCODE_UNKNOWN}, PADS(SDL_CONTROLLER_BUTTON_RIGHTSTICK)},
    {"Start", L"Start", RR_PSX_PAD_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER}, PADS(SDL_CONTROLLER_BUTTON_START)},
    {"Select", L"Select", RR_PSX_PAD_SELECT, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_0}, PADS(SDL_CONTROLLER_BUTTON_BACK)},
    {"Up", L"Up", RR_PSX_PAD_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, PADS(SDL_CONTROLLER_BUTTON_DPAD_UP)},
    {"Down", L"Down", RR_PSX_PAD_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_1}, PADS(SDL_CONTROLLER_BUTTON_DPAD_DOWN)},
    {"Left", L"Left", RR_PSX_PAD_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_3}, PADS(SDL_CONTROLLER_BUTTON_DPAD_LEFT)},
    {"Right", L"Right", RR_PSX_PAD_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_PERIOD}, PADS(SDL_CONTROLLER_BUTTON_DPAD_RIGHT)},
    /* Not on the Guide button: it opens F2. */
    {"Analog", L"Analog", 0, RRHK_SYSTEM, SDLK_f, {SDL_SCANCODE_F, SDL_SCANCODE_UNKNOWN}, PADS(SDL_CONTROLLER_BUTTON_MISC1)},
    {"Change disc", L"ChangeDisc", 0, RRHK_SYSTEM, SDLK_n, {SDL_SCANCODE_N, SDL_SCANCODE_UNKNOWN}, PADS(NO_PAD)}};
/* The console's bit of each action (-1: none, Change disc). */
static const int ps_bits[ACTIONS] = {14, 13, 15, 12, 10, 11, 8, 9, 1, 2, 3, 0, 4, 6, 7, 5, 16, -1};

/* ---- the graphics page (D14): what the player sees only; the default of each is the reference the gates use ---- */
static const char *const resolutions[] = {"1x (native)", "2x", "4x", "8x"};
static const char *const resolution_values[] = {"1x(native)", "2x", "4x", "8x"};
static const char *const dithering[] = {"Native", "At the internal resolution", "Off"};
static const char *const dithering_values[] = {"1x(native)", "internal resolution", "disabled"};
static const char *const deinterlacing[] = {"Weave", "Bob", "Bob (offset)"};
static const char *const deinterlacing_values[] = {"weave", "bob", "bob_offset"};
static const char *const aspects[] = {"Corrected", "Uncorrected", "4:3", "NTSC"};
static const char *const aspect_values[] = {"corrected", "uncorrected", "4:3", "ntsc"};
static const char *const crops[] = {"Horizontal and vertical", "Horizontal", "Off"};
static const char *const crop_values[] = {"smart", "static", "disabled"};
enum { GFX_RESOLUTION, GFX_DITHER, GFX_DEINTERLACE, GFX_ASPECT, GFX_CROP, GFX_COUNT };
static const RrhkGfxOption gfx_options[GFX_COUNT] = {
    {"Internal resolution", L"resolution", resolutions, 4, 0},
    {"Dithering", L"dithering", dithering, 3, 0},
    {"Deinterlacing", L"deinterlacing", deinterlacing, 3, 0},
    {"Aspect ratio", L"aspect", aspects, 4, 0},
    {"Overscan crop", L"crop", crops, 3, 0}};
static const char *const *const gfx_core_values[GFX_COUNT] = {resolution_values, dithering_values, deinterlacing_values,
                                                              aspect_values, crop_values};
static const char *const gfx_core_keys[GFX_COUNT] = {"internal_resolution", "dither_mode", "deinterlacer", "aspect_ratio",
                                                     "crop_overscan"};
static int scale = 1;   /* the internal resolution in force (1, 2, 4, 8) */

static void gfx_apply(int option, int value) {
    if (option < 0 || option >= GFX_COUNT || value < 0 || value >= gfx_options[option].count) return;
    rr_psx_option(rr_psx_host_session(), gfx_core_keys[option], gfx_core_values[option][value]);
    if (option == GFX_RESOLUTION) scale = 1 << value;
}

/* Headless runs never open the kit: the defaults (or `--gfx key=index`, for a capture) are applied here. */
void rr_psx_gfx_defaults(void) { for (int i = 0; i < GFX_COUNT; ++i) gfx_apply(i, gfx_options[i].def); }
bool rr_psx_gfx_assign(const char *assignment, bool windowed) {
    if (windowed) return rrhk_gfx_override(rrhk_adapter(), assignment);
    const char *equals = strchr(assignment, '=');
    if (!equals) return false;
    for (int i = 0; i < GFX_COUNT; ++i) {
        char key[64];
        snprintf(key, sizeof key, "%ls", gfx_options[i].ini_key);
        if (strlen(key) == (size_t)(equals - assignment) && !strncmp(assignment, key, strlen(key))) {
            const int value = atoi(equals + 1);
            if (value < 0 || value >= gfx_options[i].count) return false;
            gfx_apply(i, value);
            return true;
        }
    }
    return false;
}

/* ---- the machine ---- */
static int players(void) { return 2; }
static void reset(void) { rr_psx_host_reset(); rrhk_autofire_reset(); }
static uint16_t rumbling[2][2];
static void rumble(void) {
    for (int p = 0; p < 2; ++p) {
        uint16_t strong = 0, weak = 0;
        rr_psx_rumble(rr_psx_host_session(), p, &strong, &weak);
        /* A motor the game keeps running is renewed every frame; a stop is sent once. */
        if (strong || weak || rumbling[p][0] || rumbling[p][1]) rrhk_rumble(p, strong, weak, strong || weak ? 100 : 0);
        rumbling[p][0] = strong;
        rumbling[p][1] = weak;
    }
}
static bool run_frame(uint16_t p1, uint16_t p2) {
    const uint16_t pads[2] = {p1, p2};
    int16_t axes[2][4];
    const uint64_t frame = rr_psx_frame_index();
    for (int p = 0; p < 2; ++p) rrhk_pad_axes(p, frame, axes[p]);
    const bool ran = rr_psx_host_frame(pads, axes) != 0;
    rumble();
    return ran;
}
static void pause_machine(bool paused) {
    if (paused) for (int p = 0; p < 2; ++p) if (rumbling[p][0] || rumbling[p][1]) { rrhk_rumble(p, 0, 0, 0); rumbling[p][0] = rumbling[p][1] = 0; }
}

/* The Analog button: a press of its key or button, in play, of either player (the kit matches host-side actions the same way). */
static int event_player(SDL_JoystickID which) {
    for (int p = 0; p < 2; ++p)
        if (rrhk.pads[p] && which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(rrhk.pads[p]))) return p;
    return -1;
}
static bool event(const SDL_Event *e, bool *running) {
    (void)running;
    if (rrhk.menu || rrhk.capturing) return false;
    if (e->type == SDL_KEYDOWN && !e->key.repeat) {
        for (int p = 0; p < 2; ++p)
            if (rrhk.keys[p][ANALOG] != SDL_SCANCODE_UNKNOWN && rrhk.keys[p][ANALOG] == e->key.keysym.scancode) rr_psx_host_analog(p);
    } else if (e->type == SDL_CONTROLLERBUTTONDOWN) {
        const int p = event_player(e->cbutton.which);
        if (p >= 0 && rrhk.buttons[p][ANALOG] == (SDL_GameControllerButton)e->cbutton.button) rr_psx_host_analog(p);
    }
    return false;
}

/* The picture: rows packed at its width, which grows with the internal resolution. */
static const uint32_t *pixels(void) { return rr_psx_picture(rr_psx_host_session(), NULL, NULL, NULL); }
static int pixel_pitch(void) { int w = 0; rr_psx_picture(rr_psx_host_session(), &w, NULL, NULL); return w ? w : 320; }
static int visible_width(void) { int w = 0; rr_psx_picture(rr_psx_host_session(), &w, NULL, NULL); return w ? w : 320; }
static int visible_height(void) { int h = 0; rr_psx_picture(rr_psx_host_session(), NULL, &h, NULL); return h ? h : 240; }
/* The shape the picture is shown at: the console's rows (the picture's divided by the internal resolution) and the width the
 * core's display aspect gives them (4:3 on a television; a 480-line picture is two fields of a 4:3 screen). */
static int raster_height(void) { const int h = visible_height() / scale; return h > 0 ? h : 240; }
static int display_width(void) {
    double aspect = 0;
    rr_psx_picture(rr_psx_host_session(), NULL, NULL, &aspect);
    if (aspect <= 0) aspect = 4.0 / 3.0;
    const int h = raster_height();
    return (int)(aspect * (h > 288 ? h / 2 : h) + 0.5) * (h > 288 ? 2 : 1);
}
static size_t audio(int16_t *pcm, size_t capacity) { return rr_psx_take_audio(pcm, capacity) / 2; }
static bool audio_enable(unsigned rate) { return rate == RR_PSX_AUDIO_RATE; }
static uint64_t interpreted(void) { return rr_psx_interpreted(rr_psx_host_session()); }
static uint64_t audio_interpreted(void) { return 0; }   /* the SPU is a device of the one CPU: there is no sound CPU */
static uint64_t input_frame(void) { return rr_psx_frame_index(); }
static int media_count(void) { return rr_psx_disc_count(rr_psx_host_session()); }
static int media_current(void) { return rr_psx_disc_current(rr_psx_host_session()); }
static bool media_select(int index) { return rr_psx_disc_select(rr_psx_host_session(), index) != 0; }

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("Arrows; X Cross, C Circle, W Square, A Triangle; S/D L1/R1, Q/E L2/R2",
                                   "Fleches; X Croix, C Rond, W Carre, A Triangle; S/D L1/R1, Q/E L2/R2"));
    rrhk_menu_line(ctx, y + RR_MENU_LINE, rrhk_tr("Enter Start; Shift Select; F Analog; N Change disc",
                                                  "Entree Start; Maj Select; F Analog; N Changer de disque"));
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
            .pixels = pixels, .pixel_pitch = pixel_pitch, .visible_width = visible_width, .visible_height = visible_height,
            .raster_height = raster_height, .display_width = display_width,
            .audio = audio, .interpreted = interpreted, .audio_interpreted = audio_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .input_frame = input_frame, .help_controls = help_controls, .event = event,
            .analog_sticks = 2, .trigger_buttons = true, .rumble = true,
            .gfx_options = gfx_options, .gfx_option_count = GFX_COUNT, .gfx_apply = gfx_apply,
            .host_media = 1 + DISC, .media_count = media_count, .media_current = media_current, .media_select = media_select,
        };
    }
    return &machine;
}

/* The input check of the game (psx_main.c --input-check): each action, pressed alone, must reach exactly its own button of the
 * console, through the session's libretro inputs and the core's pad mapping; one JSON line per action. 0: all of them do. */
int rr_psx_input_check(RrPsxSession *s, FILE *out) {
    int failures = 0;
    for (int player = 0; player < 2; ++player)
        for (int a = 0; a < ACTIONS; ++a) {
            const uint32_t got = rr_psx_pad_probe(s, player, actions[a].bit, a == ANALOG);
            const uint32_t expected = ps_bits[a] < 0 ? 0 : 1u << ps_bits[a];
            failures += got != expected;
            fprintf(out, "{\"player\":%d,\"action\":\"%s\",\"pad_bit\":%u,\"console_bits\":%u,\"expected\":%u,\"ok\":%s}\n",
                    player + 1, actions[a].name, (unsigned)actions[a].bit, (unsigned)got, (unsigned)expected,
                    got == expected ? "true" : "false");
        }
    /* Each pad is a DualShock in digital mode at power-on, as the console's pad is: a game that reads the d-pad of a digital pad
     * sees its directions (the Analog button switches the mode). */
    for (int player = 0; player < 2; ++player) {
        const int mode = rr_psx_pad_analog_mode(s, player);
        failures += mode != 0;
        fprintf(out, "{\"player\":%d,\"action\":\"power-on mode\",\"analog\":%d,\"expected\":0,\"ok\":%s}\n", player + 1,
                mode, mode == 0 ? "true" : "false");
    }
    /* Nothing pressed: nothing read. */
    const uint32_t idle = rr_psx_pad_probe(s, 0, 0, 0);
    failures += idle != 0;
    fprintf(out, "{\"player\":1,\"action\":\"none\",\"console_bits\":%u,\"expected\":0,\"ok\":%s}\n", (unsigned)idle,
            idle ? "false" : "true");
    return failures;
}

int rr_psx_sdl_main(const char *title, int scale_hint) { return rrhk_main(rrhk_adapter(), title, scale_hint); }
