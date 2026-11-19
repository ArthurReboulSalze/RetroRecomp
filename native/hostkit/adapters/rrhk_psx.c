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
#include "runtime_i18n.h"

int rr_psx_host_frame(const uint16_t pads[2], const int16_t axes[2][4]);
void rr_psx_host_analog(int player);
size_t rr_psx_take_audio(int16_t *out, size_t capacity);
unsigned rr_psx_frame_index(void);
int rr_psx_host_reset(void);
int rr_psx_host_set_renderer(int vulkan);
int rr_psx_host_reopen(void);
unsigned rr_psx_card_notice(void);   /* psx_main.c: 1 a memory card file set aside, 2 saving off */
void rr_psx_host_match(void);
size_t rr_psx_host_card_image(void *out, size_t capacity);
int rr_psx_host_card_put(const void *in, size_t size);
int rr_psx_host_card_commit(void);
void rr_psx_host_effects(int allowed);
uint64_t rr_psx_host_digest(void);
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

/* ---- the graphics page (D14): what the player sees ---- */
/* The renderer (1.7.7, the owner's decisions of 15 November 2026: « je veux que par défaut, on ait une accélération graphique
 * Vulkan », the CPU when no card can be used): the graphics card (Beetle's Vulkan renderer) or the CPU (its software renderer, the
 * reference of the conversion's checks, which never open the card). The card keeps the machine the checked one: its RAM, CPU state,
 * sound and VRAM equal the CPU renderer's at 1x on every frame (the trace's columns), only the picture is its own. Changing the row
 * opens the session again on the other renderer and gives the machine back as a quick state. */
static const char *const renderers[] = {"Graphics card (Vulkan)", "CPU"};
/* The internal resolution. On the CPU it is drawn on one thread: 4x is more than a fast desktop draws in time in a busy scene
 * (Tobal No. 1 in combat on a Ryzen 9 3900X: 18 % too slow; 2x holds), and a raised resolution there also changes the emulated
 * drawing time. 8x only on the card (« le 8x, c'est injouable » on the CPU): chosen with the CPU drawing, it draws 4x and says so. */
static const char *const resolutions[] = {"1x (native)", "2x", "4x", "8x (graphics card)"};
static const char *const resolution_values[] = {"1x(native)", "2x", "4x", "8x"};
/* PGXP (1.7.7, the owner's question of 15 November 2026: « Est-ce qu'on peut, nous aussi, utiliser comme Beetle PGXP ? »): the
 * GTE's results kept with sub-pixel precision and carried through memory to the GPU, so 3D models stop wobbling; and textures
 * drawn with perspective. Both On by default for the player (the owner, after trying them: « C'est impeccable. Il faut l'activer
 * par défaut »); a saved choice is kept, a player who never touched the rows gets On. With PGXP on the emulated run changes slightly
 * (the drawing time follows the vertices: on Ape Escape the RAM and the CPU state differ on some frames and come back), so the
 * conversion's checks run with both Off (`check_default`, headless) and nothing is claimed of the run with them on. "On" is
 * Beetle's "memory only"; its "memory + CPU" mode (« Buggy »), its own primitive culling (known to lock some games) and its vertex
 * cache are not offered. The core's game database still turns PGXP off for the games it knows break with it. Perspective-correct
 * textures need PGXP (Beetle corrects only the primitives PGXP carried): with PGXP Off the row is held off and says why. Both rows
 * change on the fly: no reopening. */
static const char *const pgxp_modes[] = {"Off", "On"};
static const char *const pgxp_mode_values[] = {"disabled", "memory only"};
static const char *const pgxp_textures[] = {"Off", "On"};
static const char *const pgxp_texture_values[] = {"disabled", "enabled"};
/* Anti-aliasing and texture filtering (1.7.7, the owner's questions of 15 November 2026: « il me semble pas avoir vu d'options
 * d'anti-aliasing pour la PlayStation », « juste au moins pouvoir activer ou pas le filtrage des textures »): the card only, both
 * Off by default (Beetle's defaults: one sample, the console's nearest texel). They act on the card's drawing alone: the machine
 * (RAM, CPU state, sound, VRAM) is the CPU renderer's whatever they are, and the CPU renderer ignores them (it says so once).
 * One anti-aliasing row: MSAA (2, 4 or 8 samples per pixel on the polygons' edges, at the internal resolution) or Supersampling
 * as on the Nintendo 64 (the owner, 16 November 2026: « quand on se met en mode 2x, il calcule en 4x et il donne scale en 2x, mais
 * il descend pas à 1x »): the card draws at twice the internal resolution chosen and the session reduces each frame by two as it
 * reads it back (an exact 2x2 mean), so the picture keeps the size the resolution row gives. Beetle's own supersampling, which
 * reduces to the console's size, is not used. At 8x there is nothing larger to draw: it does nothing and says so. Both together
 * only add cost, so they are values of one row; 16x MSAA is left out (beyond what most cards give a colour target, Beetle settles
 * for less). Texture filtering: nearest (the console), bilinear or 3-point (the
 * Nintendo 64's own filter); Beetle's xBR, SABR and JINC2 texture upscalers are not offered, and no mipmapping exists (the
 * console has none and Beetle adds none). Both change on the fly; the anti-aliasing row rebuilds the card's targets as the
 * resolution row does. */
static const char *const antialiasing[] = {"Off", "MSAA 2x", "MSAA 4x", "MSAA 8x", "Supersampling"};
static const char *const msaa_values[] = {"1x", "2x", "4x", "8x", "1x"};
static const char *const texture_filters[] = {"Off", "Bilinear", "3-point"};
static const char *const texture_filter_values[] = {"nearest", "bilinear", "3-point"};
static const char *const dithering[] = {"Native", "At the internal resolution", "Off"};
static const char *const dithering_values[] = {"1x(native)", "internal resolution", "disabled"};
/* No deinterlacing row (the owner's « ok » of 15 November 2026): the picture is always progressive, the session's core setting
 * (psx_session.c): the GPU draws both fields of the displayed frame, so a 480-line picture is shown whole, without combing and
 * without the shaking of Bob. A game that would need the console's fields becomes a per-disc data row, not a menu choice. A
 * saved `deinterlace=` of 1.7.5 is a key no row reads: ignored, the file stays as it is. */
static const char *const aspects[] = {"Corrected", "Uncorrected", "4:3", "NTSC"};
static const char *const aspect_values[] = {"corrected", "uncorrected", "4:3", "ntsc"};
static const char *const crops[] = {"Horizontal and vertical", "Horizontal", "Off"};
static const char *const crop_values[] = {"smart", "static", "disabled"};
enum { GFX_RENDERER, GFX_RESOLUTION, GFX_ANTIALIASING, GFX_TEXTURE_FILTER, GFX_PGXP, GFX_PGXP_TEXTURE, GFX_DITHER, GFX_ASPECT,
       GFX_CROP, GFX_COUNT };
static const RrhkGfxOption gfx_options[GFX_COUNT] = {
    {"Renderer", L"renderer", renderers, 2, 0},
    {"Internal resolution", L"resolution", resolutions, 4, 0},
    {"Anti-aliasing (GPU)", L"antialiasing", antialiasing, 5, 0},
    {"Texture filtering (GPU)", L"texture_filter", texture_filters, 3, 0},
    {"Geometry precision (PGXP)", L"pgxp", pgxp_modes, 2, 1},
    {"Perspective-correct textures", L"pgxp_texture", pgxp_textures, 2, 1},
    {"Dithering", L"dithering", dithering, 3, 0},
    {"Aspect ratio", L"aspect", aspects, 4, 0},
    {"Overscan crop", L"crop", crops, 3, 0}};
static const char *const *const gfx_core_values[GFX_COUNT] = {NULL, resolution_values, msaa_values, texture_filter_values,
                                                              pgxp_mode_values, pgxp_texture_values, dithering_values,
                                                              aspect_values, crop_values};
static const char *const gfx_core_keys[GFX_COUNT] = {NULL, "internal_resolution", "msaa", "filter", "pgxp_mode", "pgxp_texture",
                                                     "dither_mode", "aspect_ratio", "crop_overscan"};
static int scale = 1;   /* the internal resolution in force (1, 2, 4, 8) */
static int chosen[GFX_COUNT];   /* each row's value, given again to a session opened again */
/* A multiplayer game (session_begin; the owner, 17 November 2026: « il faut que ça soit l'hôte qui les synchronise », « le moins
 * de choses possible »). What changes the emulated run is the host's on every seat, pushed before frame 0 (session_option) and
 * refused in F3 during the match:
 *   "pgxp", "pgxp_texture" (0 or 1): PGXP and its textures change the run (Ape Escape's RAM on about 450 of 3,300 frames);
 *   "cpu_resolution" (1, 2 or 4): the internal resolution the CPU's renderer draws at changes the emulated drawing time, so the
 *   run (Ape Escape at 2x: RAM and CPU from frame 96 on); the graphics card's does not (the machine is the CPU renderer's at 1x
 *   under it). The host sends its CPU's resolution, 1 when its card draws; a seat whose card draws takes 1 as it is, and draws
 *   with the CPU at the host's resolution when it is more.
 *   "renderer" (card or cpu), sent only when the host's PGXP is On: with PGXP the renderer changes the run (Ape Escape, 3,300
 *   frames: the card's run differs from the CPU's from frame 2,429 on, the card's own resolution and multisampling do not); with
 *   PGXP Off it does not (the eight discs' gate of 16 November 2026). A seat takes the host's renderer before frame 0; a seat
 *   that cannot draw with a card refuses "renderer=card", so the match is refused with that reason.
 * Not pushed (a host that sends nothing): the export's defaults on every seat (PGXP and its textures On, the CPU at 1x). The
 * renderer and multisampling are not changed in play (both open the core again through a quick state). The player's choices
 * stay saved, unused until the game is played alone. The card's own rows (its resolution, anti-aliasing, filtering), dithering,
 * aspect and crop stay each seat's: they change only the picture. */
static bool in_match;
static int host_value[GFX_COUNT] = {-1, -1, -1, -1, -1, -1, -1, -1, -1};   /* -1: not pushed */
static int host_cpu_resolution = 0;   /* the row index (0 1x, 1 2x, 2 4x) the host's CPU draws at */
static int host_renderer = -1;        /* -1 not pushed, 0 the CPU, 1 the card */
/* Session ABI 9: the host changes a run-changing row in a match. Its choice is kept (chosen[], saved as alone) and reported by
 * rr_psx_session_values, never applied in this match: the kit sees the report differ before the next frame, stops the host's frames
 * and asks the worker to start the match again, every seat with the new values in SETUP. A guest's rows stay the host's. */
static int wanted_card = -1;          /* the host's renderer row changed in a match: 1 the card, 0 the CPU; -1 the renderer in force */
static bool card_failed;              /* the card was asked and refused on this PC (no usable Vulkan device): the CPU draws */
static bool match_host(void) { return in_match && !rrhk_session_guest(); }
static bool run_row(int option) { return option == GFX_PGXP || option == GFX_PGXP_TEXTURE; }
/* The value a row has in force: the host's for a row that changes the run during a match, the player's otherwise. */
static int row_value(int option) {
    if (in_match && run_row(option)) return host_value[option] >= 0 ? host_value[option] : gfx_options[option].def;
    return chosen[option];
}

/* The value a check runs with (headless, no `--gfx`): each row's default, except PGXP and its textures, which a check keeps off. */
static int check_default(int option) {
    return option == GFX_PGXP || option == GFX_PGXP_TEXTURE ? 0 : gfx_options[option].def;
}

/* What the card or the CPU draws, from the resolution and anti-aliasing rows: the internal resolution (8x on the card only), drawn
 * at twice that with Supersampling on the card below 8x, the frames then reduced by two. */
static void apply_drawing(RrPsxSession *s, bool tell) {
    const int card = rr_psx_renderer(s);
    int resolution = chosen[GFX_RESOLUTION];
    if (in_match && !card) resolution = host_cpu_resolution;
    if (resolution == 3 && !card) {
        resolution = 2;
        if (tell) rrhk_notice(rrhk_tr("8x needs the graphics card: 4x on the CPU", "8x demande la carte graphique : 4x sur le CPU"), 4000);
    }
    const int supersampled = chosen[GFX_ANTIALIASING] == 4 && card && resolution < 3;
    rr_psx_option(s, "internal_resolution", resolution_values[resolution + supersampled]);
    rr_psx_option(s, "super_sampling", "disabled");
    rr_psx_set_halve(s, supersampled);
    scale = 1 << resolution;
}

static void core_option(int option, int value) {
    RrPsxSession *s = rr_psx_host_session();
    if (in_match && run_row(option)) value = row_value(option);
    if (option == GFX_PGXP_TEXTURE && !row_value(GFX_PGXP)) value = 0;   /* held off without PGXP */
    if (option == GFX_RESOLUTION) { apply_drawing(s, true); return; }
    rr_psx_option(s, gfx_core_keys[option], gfx_core_values[option][value]);
    if (option == GFX_ANTIALIASING) apply_drawing(s, false);
    if (option == GFX_PGXP) core_option(GFX_PGXP_TEXTURE, chosen[GFX_PGXP_TEXTURE]);
}

static void gfx_apply(int option, int value) {
    if (option < 0 || option >= GFX_COUNT || value < 0 || value >= gfx_options[option].count) return;
    const int before = chosen[option];
    if (in_match && rr_psx_frame_index() > 0 &&
        (option == GFX_RENDERER || (option == GFX_ANTIALIASING && strcmp(msaa_values[before], msaa_values[value]) &&
                                    rr_psx_renderer(rr_psx_host_session())))) {
        chosen[option] = value;   /* kept for the next game alone */
        if (option == GFX_RENDERER && match_host()) {   /* the host: the match starts again with it (session ABI 9) */
            wanted_card = value == 0;
            return;
        }
        rrhk_notice(rr_tr("Not during a multiplayer game"), 4000);
        return;
    }
    if (in_match && (run_row(option) || (option == GFX_RESOLUTION && !rr_psx_renderer(rr_psx_host_session())))) {
        chosen[option] = value;   /* kept for the next game alone; the host's: reported, the match starts again with it */
        if (!match_host()) rrhk_notice(rr_tr("Set by the host in multiplayer"), 4000);
        return;
    }
    chosen[option] = value;
    /* Multisampling changed while the card draws: Beetle's in-place rebuild keeps the programs of the old sample count (the picture
     * then broke at the game's next display mode change: half of it black or stale, the owner's report of 15 November 2026), so
     * the session opens again with the machine carried as a quick state, as for a renderer switch, its renderer built with the new
     * multisampling from the start (the options carried into the open), and gets every row again. */
    if (option == GFX_ANTIALIASING && strcmp(msaa_values[before], msaa_values[value]) && rr_psx_renderer(rr_psx_host_session()) &&
        rr_psx_frame_index() > 0) {
        core_option(option, value);   /* into the session's options, which the session opened again starts with */
        if (!rr_psx_host_reopen()) return;
        for (int i = 0; i < GFX_COUNT; ++i) if (i != GFX_RENDERER) core_option(i, chosen[i]);
        return;
    }
    if (option != GFX_RENDERER) {
        core_option(option, value);
        if ((option == GFX_ANTIALIASING || option == GFX_TEXTURE_FILTER) && value && !rr_psx_renderer(rr_psx_host_session()))
            rrhk_notice(rrhk_tr("Graphics card only: no effect while the CPU draws",
                                "Carte graphique seulement : sans effet quand le CPU dessine"), 4000);
        if ((option == GFX_ANTIALIASING || option == GFX_RESOLUTION) && chosen[GFX_ANTIALIASING] == 4 && chosen[GFX_RESOLUTION] == 3 &&
            rr_psx_renderer(rr_psx_host_session()))
            rrhk_notice(rrhk_tr("Supersampling: nothing larger than 8x to draw", "Surechantillonnage : rien de plus grand que 8x a dessiner"),
                        4000);
        if (option == GFX_PGXP_TEXTURE && value && !chosen[GFX_PGXP])
            rrhk_notice(rrhk_tr("Needs geometry precision (PGXP) On",
                                "Demande la precision geometrique (PGXP) activee"), 4000);
        return;
    }
    if (!rr_psx_host_set_renderer(value == 0)) return;
    RrPsxSession *s = rr_psx_host_session();
    for (int i = 0; i < GFX_COUNT; ++i) if (i != GFX_RENDERER) core_option(i, chosen[i]);
    card_failed = value == 0 && !rr_psx_renderer(s);
    if (card_failed) {
        fprintf(stderr, "[host] graphics card not used: %s\n", rr_psx_renderer_note(s) ? rr_psx_renderer_note(s) : "unknown");
        rrhk_notice(rrhk_tr("No usable graphics card: the CPU draws the picture",
                            "Pas de carte graphique utilisable : le CPU dessine l'image"), 6000);
    }
}

/* Headless runs never open the kit: the checks' values (or `--gfx key=index`, for a capture) are applied here. The renderer is not: a
 * headless run is a check and draws with the CPU, unless `--gfx renderer=0` asks for the card. */
void rr_psx_gfx_defaults(void) { for (int i = 0; i < GFX_COUNT; ++i) if (i != GFX_RENDERER) gfx_apply(i, check_default(i)); }
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
static void reset(void) {
    rr_psx_host_reset();
    for (int i = 0; i < GFX_COUNT; ++i) if (i != GFX_RENDERER) core_option(i, chosen[i]);   /* the session opened again: its options */
    rrhk_autofire_reset();
}
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
/* A DualShock in digital mode does not read its sticks, as on the console, and a game the core knows as digital-only has a
 * standard pad (mode -1: Crash Bandicoot's first port); a gamepad's left stick then drives the d-pad
 * (the kit's threshold, D1), so that a game played with the stick moves either way. In analog mode the sticks go as they are. */
enum { STICK_THRESHOLD = 16000 };
static uint16_t stick_directions(int player, uint16_t pad, const int16_t axes[4]) {
    if (rr_psx_pad_analog_mode(rr_psx_host_session(), player) == 1) return pad;
    if (axes[0] < -STICK_THRESHOLD) pad |= RR_PSX_PAD_LEFT; else if (axes[0] > STICK_THRESHOLD) pad |= RR_PSX_PAD_RIGHT;
    if (axes[1] < -STICK_THRESHOLD) pad |= RR_PSX_PAD_UP; else if (axes[1] > STICK_THRESHOLD) pad |= RR_PSX_PAD_DOWN;
    if ((pad & (RR_PSX_PAD_LEFT | RR_PSX_PAD_RIGHT)) == (RR_PSX_PAD_LEFT | RR_PSX_PAD_RIGHT)) pad &= ~(RR_PSX_PAD_LEFT | RR_PSX_PAD_RIGHT);
    if ((pad & (RR_PSX_PAD_UP | RR_PSX_PAD_DOWN)) == (RR_PSX_PAD_UP | RR_PSX_PAD_DOWN)) pad &= ~(RR_PSX_PAD_UP | RR_PSX_PAD_DOWN);
    return pad;
}

/* The console runs at 59.826 frames a second with a progressive picture and 59.94 with an interlaced one (PAL: 49.761 and
 * 50.0); its sound is 44,100 Hz either way, so a frame carries 737 or 736 samples. The kit paces the frames at the rate the
 * core states (it reads frame_seconds every frame): paced at the progressive rate, an interlaced game gave the sound device
 * about 44,016 samples a second and the ring ran dry (twelve gaps a minute in Tobal No. 1). */
static RrhkMachine machine;
static void follow_frame_rate(void) {
    const double fps = rr_psx_fps(rr_psx_host_session());
    if (fps > 45.0 && fps < 65.0) machine.frame_seconds = 1.0 / fps;
}

/* A raised internal resolution this PC does not draw in time makes the game slow and its sound break up, and nothing tells the
 * player why. Over five seconds of play, 8 % behind the console's rate: one notice per resolution. Only a menu, a pause or a
 * speed change (a long frame, or the kit holding the sound) restarts the count. It reads the clock, never the machine. */
enum { LOAD_FRAMES = 300 };
static void watch_load(void) {
    static Uint64 window_start, last;
    static int frames, warned_scale;
    const Uint64 now = SDL_GetPerformanceCounter(), hz = SDL_GetPerformanceFrequency();
    const bool interrupted = !last || now - last > hz / 4 || rrhk_audio_held();
    last = now;
    if (scale == 1 || warned_scale == scale || interrupted) { window_start = now; frames = 0; return; }
    if (++frames < LOAD_FRAMES) return;
    const double behind = (double)(now - window_start) / (double)hz / (frames * machine.frame_seconds);
    if (behind > 1.08) {
        warned_scale = scale;
        fprintf(stderr, "[host] internal resolution %dx: %.0f%% of the console's speed on this PC\n", scale, 100.0 / behind);
        rrhk_notice(rrhk_tr("Resolution too heavy for this PC: lower it with F3", "Resolution trop lourde pour ce PC : baisse-la avec F3"), 6000);
    }
    window_start = now;
    frames = 0;
}

static bool run_frame(uint16_t p1, uint16_t p2) {
    uint16_t pads[2] = {p1, p2};
    int16_t axes[2][4];
    const uint64_t frame = rr_psx_frame_index();
    for (int p = 0; p < 2; ++p) {
        rrhk_pad_axes(p, frame, axes[p]);   /* in a multiplayer game, the session's sticks (the same on every seat) */
        pads[p] = stick_directions(p, pads[p], axes[p]);
    }
    const bool ran = rr_psx_host_frame(pads, axes) != 0;
    /* A memory card file the game could not use never stops it: it is set aside, the player is told once. */
    static bool card_told;
    if (!card_told) {
        card_told = true;
        const unsigned notice = rr_psx_card_notice();
        if (notice == 1) rrhk_notice(rr_tr("Save unreadable: set aside"), 6000);
        else if (notice == 2) rrhk_notice(rr_tr("Save unreadable: saving is off"), 6000);
    }
    follow_frame_rate();
    watch_load();
    rumble();
    return ran;
}
static void pause_machine(bool paused) {
    if (paused) for (int p = 0; p < 2; ++p) if (rumbling[p][0] || rumbling[p][1]) { rrhk_rumble(p, 0, 0, 0); rumbling[p][0] = rumbling[p][1] = 0; }
}

/* The Analog button: a press of its key or button, in play, of either player. */
static bool event(const SDL_Event *e, bool *running) {
    (void)running;
    const unsigned players = rrhk_action_pressed(e, ANALOG);
    /* The Analog button is not in the pad words a multiplayer game carries: on one seat it would change that seat's console only. */
    if (players && in_match) { rrhk_notice(rr_tr("Not during a multiplayer game"), 4000); return false; }
    for (int p = 0; p < 2; ++p) if (players & (1u << p)) rr_psx_host_analog(p);
    return false;
}

/* Multiplayer (hostkit_session.h): the delay tier (no in-process snapshot). The host's values arrive before session_begin. */
static bool session_option(const char *key, const char *value) {
    const bool bit = !strcmp(value, "0") || !strcmp(value, "1");
    if (!strcmp(key, "pgxp") && bit) { host_value[GFX_PGXP] = value[0] - '0'; return true; }
    if (!strcmp(key, "pgxp_texture") && bit) { host_value[GFX_PGXP_TEXTURE] = value[0] - '0'; return true; }
    if (!strcmp(key, "renderer") && (!strcmp(value, "card") || !strcmp(value, "cpu"))) {
        host_renderer = value[1] == 'a';
        /* Before frame 0: the session opens again on the host's renderer (nothing to carry yet). */
        if (rr_psx_renderer(rr_psx_host_session()) != host_renderer) rr_psx_host_set_renderer(host_renderer);
        return rr_psx_renderer(rr_psx_host_session()) == host_renderer;   /* no usable card here: refused */
    }
    if (!strcmp(key, "cpu_resolution")) {
        if (!strcmp(value, "1")) host_cpu_resolution = 0;
        else if (!strcmp(value, "2")) host_cpu_resolution = 1;
        else if (!strcmp(value, "4")) host_cpu_resolution = 2;
        else return false;
        return true;
    }
    return false;
}
/* What this game, as the host, sends every seat (RrhkMachine.session_options, in its HELLO): its own values of the keys above,
 * one "key=value" a line. */
size_t rr_psx_session_values(char *out, size_t capacity) {
    /* the renderer in force, or the one the host chose in the match (the card only where it was not refused here) */
    const int card = wanted_card >= 0 ? wanted_card && !card_failed : rr_psx_renderer(rr_psx_host_session());
    const int cpu = card ? 1 : 1 << (chosen[GFX_RESOLUTION] > 2 ? 2 : chosen[GFX_RESOLUTION]);
    const int written = snprintf(out, capacity, "pgxp=%d\npgxp_texture=%d\ncpu_resolution=%d\n%s", chosen[GFX_PGXP] ? 1 : 0,
                                 chosen[GFX_PGXP] && chosen[GFX_PGXP_TEXTURE] ? 1 : 0, cpu,
                                 !chosen[GFX_PGXP] ? "" : card ? "renderer=card\n" : "renderer=cpu\n");
    return written > 0 && (size_t)written < capacity ? (size_t)written : 0;
}
/* Called at SETUP, before the boot digest and frame 0. */
static void session_begin(uint64_t clock) {
    (void)clock;   /* the console has no real-time clock */
    in_match = true;
    /* The host's CPU draws above 1x: so does this seat, whose card would draw the run of 1x. */
    if (host_cpu_resolution && rr_psx_renderer(rr_psx_host_session())) {
        if (rr_psx_host_set_renderer(0)) rrhk_notice(rr_tr("Set by the host in multiplayer"), 4000);
    }
    rr_psx_host_match();
    for (int i = 0; i < GFX_COUNT; ++i) if (i != GFX_RENDERER) core_option(i, chosen[i]);
}
void rr_psx_match_begin(void) { session_begin(0); }   /* psx_main.c --match: the evidence of a headless run */
bool rr_psx_match_option(const char *key, const char *value) { return session_option(key, value); }
static void side_effects(bool allowed) { rr_psx_host_effects(allowed); }
/* The host's memory card for the match (session ABI 8): sent by the host, put on every seat before the boot digest. */
static size_t session_save(void *out, size_t capacity) { return rr_psx_host_card_image(out, capacity); }
static bool session_save_put(const void *in, size_t size) { return rr_psx_host_card_put(in, size) != 0; }
/* The host only, when the match ends cleanly: the card with the match's progress into the host's card file (kept: <card>.bak). */
static bool session_save_commit(void) { return rr_psx_host_card_commit() != 0; }
static uint64_t digest(void) { return rr_psx_host_digest(); }

/* The picture: the core's own frame surface, rows pixel_pitch apart, uploaded without a copy of ours. */
static const uint32_t *pixels(void) { return rr_psx_picture(rr_psx_host_session(), NULL, NULL, NULL); }
static int pixel_pitch(void) { const int pitch = rr_psx_picture_pitch(rr_psx_host_session()); return pitch ? pitch : 320; }
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
            .analog_sticks = 2, .trigger_buttons = true, .rumble = true, .native_caption = RRHK_CORE_CAPTION,
            .gfx_options = gfx_options, .gfx_option_count = GFX_COUNT, .gfx_apply = gfx_apply,
            /* Some games have their own 16:9 option and draw a squeezed (anamorphic) picture: the options page offers "Screen
             * format: 4:3 / 16:9", kept per game (D27). At 16:9 the kit shows the picture 16 wide for 9 high, whatever the
             * Aspect ratio row says; the machine and its picture are untouched. */
            .widescreen = true,
            .host_media = 1 + DISC, .media_count = media_count, .media_current = media_current, .media_select = media_select,
            .digest = digest, .side_effects = side_effects, .session_begin = session_begin, .session_option = session_option,
            .session_options = rr_psx_session_values, .session_save = session_save, .session_save_put = session_save_put,
            .session_save_commit = session_save_commit,
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
    /* No pad is in analog mode at power-on, as on the console: a game that reads the d-pad of a digital pad sees its directions
     * (the Analog button switches a DualShock's mode; a game the core knows as digital-only has a standard pad, mode -1). */
    for (int player = 0; player < 2; ++player) {
        const int mode = rr_psx_pad_analog_mode(s, player);
        failures += mode == 1;
        fprintf(out, "{\"player\":%d,\"action\":\"power-on mode\",\"analog\":%d,\"expected\":\"not analog\",\"ok\":%s}\n", player + 1,
                mode, mode != 1 ? "true" : "false");
    }
    /* The mode stays where it is over presses and releases (two seconds of the boot, Cross tapped): only the Analog button,
     * its combination held a second, or the game itself changes it. Each release once switched it (6 November 2026). */
    for (int n = 0; n < 120; ++n) {
        rr_psx_pad(s, 0, n % 20 < 5 ? RR_PSX_PAD_B : 0, NULL);
        rr_psx_pad(s, 1, n % 20 < 5 ? RR_PSX_PAD_B : 0, NULL);
        if (rr_psx_frame(s) != 0) { failures++; break; }
    }
    rr_psx_pad(s, 0, 0, NULL);
    rr_psx_pad(s, 1, 0, NULL);
    for (int player = 0; player < 2; ++player) {
        const int mode = rr_psx_pad_analog_mode(s, player);
        failures += mode == 1;
        fprintf(out, "{\"player\":%d,\"action\":\"mode after presses\",\"analog\":%d,\"expected\":\"not analog\",\"ok\":%s}\n", player + 1,
                mode, mode != 1 ? "true" : "false");
    }
    /* Nothing pressed: nothing read. */
    const uint32_t idle = rr_psx_pad_probe(s, 0, 0, 0);
    failures += idle != 0;
    fprintf(out, "{\"player\":1,\"action\":\"none\",\"console_bits\":%u,\"expected\":0,\"ok\":%s}\n", (unsigned)idle,
            idle ? "false" : "true");
    return failures;
}

int rr_psx_sdl_main(const char *title, int scale_hint) { return rrhk_main(rrhk_adapter(), title, scale_hint); }
