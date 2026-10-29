/* Master System and Game Gear adapter: the machine contract of the host kit over the recompiled Z80 runtime of the SMS/GG
 * runner. Original RetroRecomp code: MIT; the linked engine keeps its own terms. This file is the former host.c,
 * controls.c and ui.c reduced to what is the machine's own: the action tables and the former preference keys, the
 * guest-driven refresh of the pads (the guest polls its ports), the Light Phaser, the sprite-flicker option, the Pause menu,
 * the picture crop (the Game Gear window, the Master System left border) and the entry points the runner calls
 * (host_init, host_present, host_shutdown, host_audio_*). The loop belongs to the guest: the kit's frame function is called
 * from host_present, and a menu is a loop inside it. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <math.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "host_sdl.h"
#include "host_control.h"
#include "glue.h"
#include "video/sms_vdp.h"
#include "video_frame.h"
#include "embedded_rom.h"
#include "icon.h"
#include "lightphaser.h"
#include "gamestate.h"
#include "platform_io.h"
#include "display_settings.h"
#include "retro_menu.h"
#include "runtime_i18n.h"
#include "audio_cushion.h"
#include "stereo_fir.h"
#include "hostkit/hostkit.h"

#ifndef _WIN32
#include "embedded_icon.h"
/* The shared window-icon routine of the kit asks for resource 101: the game's BMP icon. */
const void *rr_resource(unsigned id, size_t *size) {
    if (id == 101 && rr_icon_size) { *size = rr_icon_size; return rr_icon_data; }
    *size = 0;
    return NULL;
}
#endif

/* ---- the controls ---- */
#ifdef RETRO_GAME_GEAR
enum { UP, DOWN, LEFT, RIGHT, BUTTON1, BUTTON2, PAUSE, START, ACTIONS };
#define PLAYERS 1
#define SECTION L"GameGear"
#else
enum { UP, DOWN, LEFT, RIGHT, BUTTON1, BUTTON2, PAUSE, ACTIONS };
#define PLAYERS 2
#define SECTION L"MasterSystem"
#endif

/* Bits follow the runner's SMS_PAD_* pad byte. The Pause/Menu action is the host's own: it has no bit, the guest never
 * sees it (the Master System pauses its menu with it, the Game Gear has the cartridge Start on its own row). */
static const RrhkAction actions[ACTIONS] = {
    {"Up", L"Up", SMS_PAD_UP, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
    {"Down", L"Down", SMS_PAD_DOWN, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
    {"Left", L"Left", SMS_PAD_LEFT, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
    {"Right", L"Right", SMS_PAD_RIGHT, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}},
    {"Button 1", L"Button1", SMS_PAD_B1, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
    {"Button 2", L"Button2", SMS_PAD_B2, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
#ifdef RETRO_GAME_GEAR
    /* Enter is the cartridge Start, as on every console with a Start button; P opens the Pause menu, as on the Game Boy. */
    {"Pause/Menu", L"Pause", 0, RRHK_SYSTEM, 0, {SDL_SCANCODE_P, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_START}},
    {"Game Start", L"Start", SMS_PAD_START, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_UNKNOWN}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_INVALID}},
#else
    /* Enter is the default Start/Menu key (the Master System has no Start button) and P is free. */
    {"Start/Menu", L"Pause", 0, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
#endif
};

/* ---- the former preferences (French sections and keys, SDL names), read when the kit's keys are absent ---- */
#ifdef RETRO_GAME_GEAR
static const wchar_t *const old_key_sections[2] = {L"ClavierGameGear", L"ClavierGameGearJ2"};
static const wchar_t *const old_pad_sections[2] = {L"ManetteGameGear", L"ManetteGameGearJ2"};
static const wchar_t *const old_entries[ACTIONS] = {L"haut", L"bas", L"gauche", L"droite", L"bouton1", L"bouton2", L"menu", L"start"};
#else
static const wchar_t *const old_key_sections[2] = {L"Clavier", L"ClavierJ2"};
static const wchar_t *const old_pad_sections[2] = {L"Manette", L"ManetteJ2"};
static const wchar_t *const old_entries[ACTIONS] = {L"haut", L"bas", L"gauche", L"droite", L"bouton1", L"bouton2", L"start"};
#endif

/* ---- the machine's state ---- */
static uint8_t pads[2];
static RrhkMachine machine;
static bool phaser_alias;               /* the P2 trigger some Light Phaser games read as well as P1 TL */
static bool phaser_blocked;             /* a trigger held while a menu closed does not shoot */
static bool reset_requested;
static bool paused_machine;
static bool reduce_sprites;
static SDL_Rect full_crop, crop;        /* the picture inside the 256 x 192 frame: the Game Gear window, the Master System border */
static uint32_t view[SMS_SCREEN_W * SMS_SCREEN_H];   /* the visible picture alone, at the origin of the kit's texture */
static uint64_t input_sample_counter, input_poll_period;
static SDL_AudioDeviceID audio_device;

int smsrecomp_take_reset_request(void) {
    bool requested = reset_requested;
    reset_requested = false;
    return requested;
}

/* ---- sound: the stereo callback ring of the Master System host, unchanged (HOST_KIT.md decision D5: the ring it always
 * had; the kit's own mono ring serves the NES) ---- */
static void audio_output_clear(void);
#define RR_HOST_AUDIO_FILTER rrhk_options_audio
#define RR_HOST_AUDIO_RESET rrhk_options_audio_reset
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate);
void rrhk_options_audio_reset(void);
#include "audio_output.inc"

/* ---- the machine ---- */
static int players(void) { return PLAYERS; }
static int view_width(void) { return crop.w; }
static int view_height(void) { return crop.h; }
static const uint32_t *view_pixels(void) { return view; }
static size_t no_audio(int16_t *pcm, size_t capacity) { (void)pcm; (void)capacity; return 0; }
static uint64_t input_frame(void) { return glue_frame_count(); }

/* The guest runs when host_present returns: the kit only hands the pad words over. */
static void deliver(uint16_t p1, uint16_t p2) {
    pads[0] = (uint8_t)p1;
    pads[1] = PLAYERS > 1 ? (uint8_t)(p2 | (phaser_alias ? SMS_PAD_B1 : 0)) : 0;
    input_sample_counter = SDL_GetPerformanceCounter();
}
static bool run_frame(uint16_t p1, uint16_t p2) { deliver(p1, p2); return true; }

/* Reset unwinds the generated call stack through glue_run(); the launcher then starts the runtime again. */
static void reset_machine(void) {
    fprintf(stderr, "[host] reset requested at frame %llu\n", (unsigned long long)glue_frame_count());
    reset_requested = true;
    rrhk_stop();
}

/* A menu or the Pause menu is up: the sound stops and starts clean. */
static void pause_machine(bool paused) {
    if (paused == paused_machine) return;
    paused_machine = paused;
    audio_output_clear();
    if (audio_device) SDL_PauseAudioDevice(audio_device, paused ? 1 : 0);
}

static uint64_t interpreted(void) {
    /* The reference interpreter is the fallback by definition: never reported as native code. */
    return getenv("SMSRECOMP_REFERENCE") ? 1 : smsrecomp_interpreter_cycles();
}
static uint64_t no_count(void) { return 0; }
static bool state_ready(void) { return true; }
/* The guest services the request after a completed banked CPU instruction and reports through state_completed. */
static bool state_file(const wchar_t *path, bool load) {
    (void)path;
    return smsrecomp_request_state(load ? RR_QUICKLOAD : RR_QUICKSAVE);
}
static void state_completed(int operation, int result) {
    if (operation == RR_QUICKLOAD) {
        if (result == RR_STATE_OK) audio_output_clear();
        rrhk_autofire_reset();
    }
    rrhk_state_done(operation == RR_QUICKLOAD, result);
}

/* ---- the Light Phaser: mouse to picture, trigger on either button ---- */
static void pointer_input(RrhkPointer p) {
    if (rrhk_ui()->menu) {
        lightphaser_pointer(-1, -1, false);
        phaser_blocked = true; phaser_alias = false;
        return;
    }
    const bool held = p.fire || p.aux;
    if (!held) phaser_blocked = false;
    const bool pressed = !phaser_blocked && held;
    const bool offscreen = p.offscreen || p.aux;      /* the right button is a shot off the screen */
    lightphaser_pointer(offscreen ? -1 : crop.x + p.x, offscreen ? -1 : crop.y + p.y, pressed);
    /* Laser Ghost selects its original gun mode through a P2 trigger: supply that alias, no cartridge code is patched. */
    phaser_alias = pressed && sms_light_phaser_trigger_p2;
}
static bool phaser_page_available(void) { return lightphaser_enabled(); }

/* ---- the window: the picture keeps whole pixels, centred; Fit fills the output at the picture's own aspect ----
 * The scale is taken from the full picture so that it does not jump when a game blanks the left column. */
static bool game_rect(int out_w, int out_h, int mode, SDL_Rect *rect) {
    if (mode == 2) {
        int width, height;
        if ((int64_t)out_w * crop.h <= (int64_t)out_h * crop.w) {
            width = out_w; height = SDL_max(1, (int)((int64_t)out_w * crop.h / crop.w));
        } else {
            height = out_h; width = SDL_max(1, (int)((int64_t)out_h * crop.w / crop.h));
        }
        *rect = (SDL_Rect){(out_w - width) / 2, (out_h - height) / 2, width, height};
        return true;
    }
    int k = SDL_min(out_w / full_crop.w, out_h / full_crop.h);
    if (k < 1) k = 1;
    if (rrhk_ui()->filter == 2 && k >= 2) k -= k % 2;
    *rect = (SDL_Rect){(out_w - crop.w * k) / 2, (out_h - crop.h * k) / 2, crop.w * k, crop.h * k};
    return true;
}

/* ---- the sprite-flicker option (F5): the Master System only, the Game Gear has none ---- */
static bool key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
    (void)running;
    if (key != SDL_SCANCODE_F5) return false;
#ifdef RETRO_GAME_GEAR
    rrhk_notice(rrhk_tr("Config unavailable", "Config inaccessible"), 1800);
#else
    if (rrhk_write_ready() && rr_display_save(ui->ini_file, ui->data_dir, SECTION L".Video", L"reduce_sprite_flicker", !reduce_sprites)) {
        reduce_sprites = !reduce_sprites;
        smsrecomp_video_set_sprite_flicker_reduction(reduce_sprites);
        rrhk_notice(reduce_sprites ? rrhk_tr("Sprite flicker reduction ON", "Reduction du scintillement ON") :
                                     rrhk_tr("Original console sprite limit", "Limite de sprites de la console"), 1800);
    } else rrhk_notice(rrhk_tr("Config unavailable", "Config inaccessible"), 1800);
#endif
    return true;
}

static void option_rows(int slot, RrhkOptionRows *rows) {
#ifndef RETRO_GAME_GEAR
    if (slot == 0) rrhk_option_row(rows, SDL_SCANCODE_F5, "F5 Sprite flicker reduction: %s", rr_tr(reduce_sprites ? "ON" : "OFF"));
#else
    (void)slot; (void)rows;
#endif
}

static void help_lines(int slot, const char **lines, int *count) {
    if (slot == 0) lines[(*count)++] = rrhk_tr("F5  Reduce sprite flicker", "F5  Reduire le scintillement");
    else lines[(*count)++] =
#ifdef RETRO_GAME_GEAR
        rrhk_tr("P  Pause | Enter  Start", "P  Pause | Entree  Start");
#else
        rrhk_tr("Enter  Pause", "Entree  Pause");
#endif
}

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui; (void)y;
    const char *line = NULL;
    if (sms_light_phaser) line = rrhk_tr("Gun: mouse/left click", "Gun : souris/clic gauche");
#ifdef RETRO_GAME_GEAR
    line = rrhk_tr("Enter / pad Start: cartridge Start", "Entree / Start manette : Start jeu");
#endif
    if (line) rr_menu_text(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, 14, RR_MENU_HINT_LINE, line, RR_MENU_ACCENT);
}

static void window_icon(SDL_Window *window) { smsrecomp_set_window_icon(window); }

static void pause_text(const RrhkMenuCtx *ctx, int y, const char *text, int red, int green, int blue) {
    rr_menu_text(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, 14, y, text, red, green, blue);
}

static void pause_page(RrhkUi *ui, const RrhkMenuCtx *ctx) {
    (void)ui;
    pause_text(ctx, 62, rrhk_tr("Game paused", "Jeu en pause"), RR_MENU_GOLD);
#ifdef RETRO_GAME_GEAR
    pause_text(ctx, 90, rrhk_tr("P: resume", "P : reprendre"), RR_MENU_GOLD);
#else
    pause_text(ctx, 90, rrhk_tr("Enter: resume", "Entree : reprendre"), RR_MENU_GOLD);
#endif
    pause_text(ctx, 118, rrhk_tr("Shift+F1: restart", "Maj+F1 : redemarrer"), RR_MENU_HINT);
    char sprites[64];
    snprintf(sprites, sizeof sprites, rrhk_tr("F5 Sprite flicker reduction: %s", "F5 Reduction scintillement : %s"), reduce_sprites ? "ON" : "OFF");
    pause_text(ctx, 140, sprites, RR_MENU_HINT);
#ifdef RETRO_GAME_GEAR
    pause_text(ctx, 152, rrhk_tr("Gamepad shortcuts: see F2", "Raccourcis manette : voir F2"), RR_MENU_HINT);
#endif
    pause_text(ctx, 164, rrhk_tr("F1: help | F2: controls & options", "F1 : aide | F2 : commandes et options"), RR_MENU_HINT);
}

/* ---- preferences: the former keys, read when the kit's are absent ---- */
static void read_text(const wchar_t *file, const wchar_t *section, const wchar_t *key, char *out, int size) {
    wchar_t value[128];
    rr_ini_get(section, key, L"", value, 128, file);
    rr_to_utf8(value, out, size);
}

static void settings_loaded(RrhkUi *ui) {
    const wchar_t *file = ui->read_file;
    char value[128];
    /* Keyboard and gamepad: the SDL names of the French sections. The kit reads its own numeric keys after this and wins. */
    static const SDL_Scancode old_player2_layout[6] = {SDL_SCANCODE_I, SDL_SCANCODE_K, SDL_SCANCODE_J, SDL_SCANCODE_L, SDL_SCANCODE_N, SDL_SCANCODE_M};
    bool old_layout = true;      /* the unchanged 0.8 default layout of player 2 is not a choice of the player */
    for (int a = 0; a < 6; ++a) {
        read_text(file, old_key_sections[1], old_entries[a], value, sizeof value);
        if (SDL_GetScancodeFromName(value) != old_player2_layout[a]) old_layout = false;
    }
    for (int p = 0; p < PLAYERS; ++p) for (int a = 0; a < ACTIONS; ++a) {
        read_text(file, old_key_sections[p], old_entries[a], value, sizeof value);
        SDL_Scancode key = SDL_GetScancodeFromName(value);
        const bool reserved = key == SDL_SCANCODE_ESCAPE || (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12);
        if (key != SDL_SCANCODE_UNKNOWN && !reserved && !(p == 1 && old_layout)) ui->keys[p][a] = key;
        read_text(file, old_pad_sections[p], old_entries[a], value, sizeof value);
        SDL_GameControllerButton button = SDL_GameControllerGetButtonFromString(value);
        if (button != SDL_CONTROLLER_BUTTON_INVALID) ui->buttons[p][a] = button;
    }
    /* Picture: [Video] filtre and display_mode were the defaults of [<Console>.Video]. */
    int filter = (int)rr_ini_int(L"Video", L"filtre", 0, file), mode = (int)rr_ini_int(L"Video", L"display_mode", 0, file);
    filter = (int)rr_ini_int(ui->video_section, L"filter", filter, file);
    mode = (int)rr_ini_int(ui->video_section, L"display_mode", mode, file);
    ui->filter = filter >= 0 && filter < 4 ? filter : 0;
    ui->fullscreen = mode >= 0 && mode < 3 ? mode : 0;
    /* Light Phaser: [LightPhaser] dot_size 1..5, shape cross|dot, color red|white|green. */
    int dot = (int)rr_ini_int(L"LightPhaser", L"dot_size", 1, file);
    ui->pointer_size = dot >= 1 && dot <= 5 ? dot : 1;
    read_text(file, L"LightPhaser", L"shape", value, sizeof value);
    ui->pointer_shape = !strcmp(value, "dot");
    read_text(file, L"LightPhaser", L"color", value, sizeof value);
    ui->pointer_color = !strcmp(value, "white") ? 1 : !strcmp(value, "green") ? 2 : 0;
#ifndef RETRO_GAME_GEAR
    reduce_sprites = rr_ini_int(ui->video_section, L"reduce_sprite_flicker", 0, file) == 1;
#else
    reduce_sprites = false;
#endif
    smsrecomp_video_set_sprite_flicker_reduction(reduce_sprites);
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkPage page;
    if (!machine.actions) {
        page = rrhk_pointer_page;
        page.available = phaser_page_available;
        machine = (RrhkMachine){
#ifdef RETRO_GAME_GEAR
            .ini_section = SECTION, .console_name = "Game Gear", .start = START,
#else
            .ini_section = SECTION, .console_name = "Master System", .start = PAUSE,
#endif
            .table_players = PLAYERS, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT,
            .max_width = SMS_SCREEN_W, .max_height = SMS_SCREEN_H, .frame_seconds = 1.0 / 60.0,
            .pointer = sms_light_phaser ? RRHK_POINTER_PHASER : RRHK_POINTER_NONE,
            .own_audio = true, .driven = true, .host_pause = PAUSE + 1, .minimum_window = true, .state_deferred = true,
            .legacy_ini = L"SMSRecomp.ini", .window_icon = window_icon,
            .pointer_keeps_player2 = true, .pointer_section = SECTION L".Pointer", .pointer_max = 5,
            .save_failed_en = "Game states need the native banked backend", .save_failed_fr = "Etats : moteur natif par banques requis",
            .reset = reset_machine, .run_frame = run_frame, .pause = pause_machine,
            .pixels = view_pixels, .visible_width = view_width, .visible_height = view_height,
            .raster_height = view_height, .display_width = view_width,
            .audio = no_audio, .interpreted = interpreted, .audio_interpreted = no_count,
            .state_ready = state_ready, .state_file = state_file, .input_frame = input_frame,
            .pointer_input = pointer_input,
            .page = sms_light_phaser ? &page : NULL,
            .settings_loaded = settings_loaded, .option_rows = option_rows, .help_lines = help_lines,
            .help_controls = help_controls, .key_event = key_event, .game_rect = game_rect, .pause_page = pause_page,
        };
    }
    return &machine;
}

/* ---- the entry points of the runner (runner/host_sdl.h and the patches of the converter) ---- */
bool host_init(int width, int height, int x, int y, int crop_w, int crop_h, int scale, const char *unused_title) {
    (void)width; (void)height; (void)unused_title;
    full_crop = crop = (SDL_Rect){x, y, crop_w, crop_h};
    memset(pads, 0, sizeof pads);
    phaser_alias = phaser_blocked = paused_machine = false;
    input_sample_counter = 0;
    input_poll_period = SDL_GetPerformanceFrequency() / 1000;
    if (!input_poll_period) input_poll_period = 1;
    if (!rrhk_open(rrhk_adapter(), sms_game_title, scale)) return false;
    rrhk_autofire_reset();
    smsrecomp_set_state_callback(state_completed);
#ifdef RETRO_GAME_GEAR
    rrhk_notice(rrhk_tr("F1: help | Enter: pause", "F1 : aide | Entree : pause"), 2400);
#else
    rrhk_notice(sms_light_phaser ? rrhk_tr("Light Phaser: mouse | F2: options", "Light Phaser : souris | F2 : options") :
                                   rrhk_tr("F1: help | Enter: pause", "F1 : aide | Entree : pause"), 2400);
#endif
    if (sms_light_phaser) fprintf(stderr, "[host] Light Phaser: mouse, left=trigger, right=off-screen; reticle=%s size=%d color=%d\n",
        rrhk_ui()->pointer_shape ? "dot" : "cross", rrhk_ui()->pointer_size, rrhk_ui()->pointer_color);
    return true;
}

void host_set_frame_cap(double fps) {
    rrhk_adapter();
    machine.frame_seconds = fps > 0.0 ? 1.0 / fps : 0.0;
}

/* The picture of the frame the guest just ran: the visible part, then the kit's end of frame and the next beginning. */
bool host_present(const uint32_t *fb, int width, int height) {
    (void)height;
    if (!rrhk_window()) return false;
    /* Use the mask attached to the rendered frame, not a shared setting or a live register. The window size is unchanged. */
    crop = full_crop;
    if (full_crop.x == 0 && full_crop.w == SMS_SCREEN_W && smsrecomp_frame_left_border() == 8) { crop.x += 8; crop.w -= 8; }
    for (int row = 0; row < crop.h; ++row)
        memcpy(view + row * SMS_SCREEN_W, fb + (crop.y + row) * width + crop.x, (size_t)crop.w * sizeof *view);
    return rrhk_frame_done();
}

uint8_t host_get_pad1(void) { return pads[0]; }
uint8_t host_get_pad2(void) { return PLAYERS > 1 ? pads[1] : 0; }

/* The guest polls its ports many times in a frame: refresh both players and the Light Phaser together, at most once a
 * millisecond, so that a busy guest cannot force an operating-system poll per instruction. Main thread only. System
 * actions stay in the frame's event loop so that reset can unwind safely. */
void host_refresh_input(void) {
    if (!rrhk_window() || rrhk_ui()->menu) return;
    uint64_t now = SDL_GetPerformanceCounter();
    if (input_sample_counter && now - input_sample_counter < input_poll_period) return;
    SDL_PumpEvents();
    const uint64_t frame = glue_frame_count();
    const uint16_t p1 = rrhk_pad_word(0, frame), p2 = PLAYERS > 1 ? rrhk_pad_word(1, frame) : 0;
    rrhk_pointer_poll(p1);
    deliver(p1, p2);
    glue_set_pad1(pads[0]); glue_set_pad2(pads[1]);
}

void host_shutdown(void) {
    if (sms_light_phaser) { lightphaser_pointer(-1, -1, false); SDL_ShowCursor(SDL_ENABLE); }
    smsrecomp_set_input_refresh(NULL);
    smsrecomp_set_state_callback(NULL);
    input_sample_counter = 0;
    rrhk_close();
    SDL_Quit();
}
