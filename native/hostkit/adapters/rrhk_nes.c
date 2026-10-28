/* NES adapter: the machine contract of the host kit over the cyc_* functions of the NES runner.
 * Original RetroRecomp code: MIT; the linked NESRecomp machine retains its separate PolyForm
 * Noncommercial terms. This file is the NES host's former nes_host_ui.c reduced to what is the
 * NES's own: the action table, the sprite-flicker option, the Zapper hook and the entry. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <wchar.h>
#include "platform_io.h"
#include "cyc_core.h"
#include "cyc_run.h"
#include "retro_menu.h"
#include "runtime_feedback.h"
#include "display_settings.h"
#include "retro_nes.h"
#include "hostkit/hostkit.h"

void rr_nes_extra_sprites(bool enabled);

enum { A, B, SELECT, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 128, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}},
    {"B", L"B", 64, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}},
    {"Select", L"Select", 32, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_4}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
    {"Start", L"Start", 16, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_7}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
    {"Up", L"Up", 8, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
    {"Down", L"Down", 4, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
    {"Left", L"Left", 2, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
    {"Right", L"Right", 1, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}}};

/* Host-only extra sprites per scanline (F5); the Zapper options have their own F2 page. */
static int extra_sprites;

static int players(void) { return 2; }
static int width(void) { return 256; }
static int height(void) { return 240; }

static void reset(void) { cyc_power_on(0); cyc_run_power_on(); }
static bool run_frame(uint16_t p1, uint16_t p2) {
    cyc_set_controller(0, (uint8_t)p1);
    cyc_set_controller(1, (uint8_t)p2);
    cyc_run_frame();
    return true;
}
static void pause_machine(bool paused) { (void)paused; }
static size_t audio(int16_t *pcm, size_t capacity) { return cyc_audio_read(pcm, capacity); }
static bool audio_enable(unsigned rate) { return cyc_audio_enable((int)rate); }
static uint64_t interpreted(void) { return cyc_run_interp_rom_cycles + cyc_run_interp_ram_cycles + cyc_run_interp_other_cycles; }
static uint64_t audio_interpreted(void) { return 0; }
static bool state_path(wchar_t *path, size_t capacity) { rr_nes_state_path(path, capacity); return path[0] != 0; }
static bool state_ready(void) { return true; }

/* The Zapper: the picture position and the trigger. The right button also pulls the trigger,
 * pointed off the picture. Nothing is aimed while a menu is open. */
static void pointer_input(RrhkPointer p) {
    if (!RR_NES_ZAPPER || rrhk_ui()->menu) return;
    rr_nes_zapper_aim(p.x, p.y, p.fire || p.aux, p.offscreen || p.aux);
}

static void settings_loaded(RrhkUi *ui) {
    extra_sprites = rr_ini_int(L"NES.Video", L"reduce_sprite_flicker", 0, ui->ini_file) == 1;
    rr_nes_extra_sprites(extra_sprites != 0);
}

/* F5 sprite flicker reduction. F6 autofire is the shell's own key, with its notice (divergence 11). */
static bool key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
    (void)running;
    if (key == SDL_SCANCODE_F5) {
        extra_sprites = !extra_sprites; rr_nes_extra_sprites(extra_sprites != 0);
        rrhk_notice(extra_sprites ? rrhk_tr("Sprite flicker reduction ON", "Reduction du scintillement ON") :
                                    rrhk_tr("Original console sprite limit", "Limite de sprites de la console"), 1800);
        if (!rr_display_save(ui->ini_file, ui->data_dir, L"NES.Video", L"reduce_sprite_flicker", extra_sprites))
            snprintf(ui->status, sizeof ui->status, "%s", rrhk_tr("Config unavailable", "Config inaccessible"));
        return true;
    }
    return false;
}

static void option_rows(int slot, RrhkOptionRows *rows) {
    if (slot == 0) rrhk_option_row(rows, SDL_SCANCODE_F5, "F5 Sprite flicker reduction: %s", rr_tr(extra_sprites ? "ON" : "OFF"));
}

static void help_lines(int slot, const char **lines, int *count) {
    static char sprites[64];
    if (slot != 0) return;
    snprintf(sprites, sizeof sprites, rrhk_tr("F5 Sprite flicker reduction: %s", "F5 Reduction scintillement : %s"),
             extra_sprites ? "ON" : "OFF");
    lines[(*count)++] = sprites;
}

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("NES: arrows + W/X; Enter Start", "NES : fleches + W/X; Entree Start"));
    rrhk_menu_line(ctx, y + RR_MENU_LINE, RR_NES_ZAPPER ? rrhk_tr("Mouse: aim/fire; right: offscreen", "Souris : viser/tirer; droit : hors ecran") :
        rrhk_tr("Shift Select; two controllers", "Maj Select; deux manettes"));
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = L"NES", .console_name = "NES",
            .table_players = 2, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
            .max_width = 256, .max_height = 240, .frame_seconds = RR_FRAME_SECONDS,
            .pointer = RR_NES_ZAPPER ? RRHK_POINTER_ZAPPER : RRHK_POINTER_NONE,
            .audio_model = RRHK_AUDIO_RING, .audio_rate = 48000u, .audio_enable = audio_enable,
            .pointer_keeps_player2 = true,
            .pointer_section = L"NES.Zapper", .pointer_max = 8,
            .save_failed_en = "Unable to save quick state", .save_failed_fr = "Impossible de sauvegarder",
            .reset = reset, .run_frame = run_frame, .pause = pause_machine,
            .pixels = cyc_frame_argb, .visible_width = width, .visible_height = height,
            .raster_height = height, .display_width = width,
            .audio = audio, .interpreted = interpreted, .audio_interpreted = audio_interpreted,
            .state_path = state_path, .state_ready = state_ready, .state_file = rr_nes_state_file,
            .pointer_input = pointer_input,
            .page = RR_NES_ZAPPER ? &rrhk_pointer_page : NULL,
            .settings_loaded = settings_loaded, .option_rows = option_rows, .help_lines = help_lines,
            .help_controls = help_controls, .key_event = key_event,
        };
    }
    return &machine;
}

/* The runner (cyc_host.c, adapted by nes_runtime.py) calls this for a windowed game. */
int cyc_sdl_main(const char *title, int scale) {
    /* The command line's headless setup is reached only after this early return. */
    rr_feedback_start(cyc_run_native);
    int status = rrhk_main(rrhk_adapter(), title, scale);
    SDL_Quit();
    return status;
}
