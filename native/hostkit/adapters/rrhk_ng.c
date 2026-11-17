/* Neo Geo adapter: the machine contract of the host kit over the rr16_*
 * functions of the Neo Geo host, plus the machine's own options (enhanced
 * mode, MVS/AES) and the test snapshot of its UI harness. Original RetroRecomp
 * code: MIT; the linked engine keeps its own terms. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "retro_menu.h"
#include "retro_keyboard.h"
#include "display_settings.h"
#include "neogeo_fixmask.h"
#include "hostkit/hostkit.h"

enum { A, B, C, D, START, COIN, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"A", L"A", 16, RRHK_FACE, 0, {SDL_SCANCODE_S, SDL_SCANCODE_KP_8}, {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_A}, NULL, SDLK_w},
    {"B", L"B", 32, RRHK_FACE, 0, {SDL_SCANCODE_D, SDL_SCANCODE_KP_9}, {SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_B}, NULL, SDLK_x},
    {"C", L"C", 64, RRHK_FACE, 0, {SDL_SCANCODE_F, SDL_SCANCODE_KP_6}, {SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_X}, NULL, SDLK_c},
    {"D", L"D", 128, RRHK_FACE, 0, {SDL_SCANCODE_E, SDL_SCANCODE_KP_4}, {SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_Y}, NULL, SDLK_v},
    {"Start", L"Start", 256, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER}, {SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_START}},
    {"Coin", L"Coin", 512, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_0}, {SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_BACK}},
    {"Up", L"Up", 1, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_UP}},
    {"Down", L"Down", 2, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, {SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_DOWN}},
    {"Left", L"Left", 4, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, {SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_LEFT}},
    {"Right", L"Right", 8, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, {SDL_CONTROLLER_BUTTON_DPAD_RIGHT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}}};

/* Autofire counts guest frames; a reset or a load forgets held buttons. */
void rr16_host_discontinuity(void) { rrhk_autofire_reset(); }

/* Multiplayer (native/hostkit/hostkit_session.h): the snapshot of the whole machine (native/neogeo_state.c), its digest, what a frame
 * may do outside the guest, and the clock of the match. */
size_t rr_ng_snap_bound(void);
size_t rr_ng_snap_save(void *buffer, size_t capacity);
bool rr_ng_snap_load(const void *buffer, size_t size);
uint64_t rr_ng_digest(void);
void rr_ng_side_effects(bool allowed);
void rr_ng_session_clock(uint64_t clock);

/* A match runs the export's defaults on every seat: the player's clock-mode preference is not read (neogeo_main.c does the same for
 * MVS / AES) until the host pushes its values (session_option). RRHK_SESSION_ENV is set only for a game the converter started. */
static void settings_loaded(RrhkUi *ui) {
    if (getenv("RETRORECOMP_NETPLAY_PIPE")) return;
    rr_ng_set_enhanced(rr_ini_int(L"NeoGeo.Runtime", L"enhanced", rr_ng_enhanced() ? 1 : 0, ui->ini_file) == 1);
}
/* The host's run-changing values, pushed before frame 0: the clock mode (an enhanced game runs 24 MHz and 381 sprites) and the
 * machine (MVS or AES: a change of machine restarts the game, so only the one running is honoured). */
static bool session_option(const char *key, const char *value) {
    if (!strcmp(key, "enhanced") && (!strcmp(value, "0") || !strcmp(value, "1"))) {
        rr_ng_set_enhanced(value[0] == '1');
        return true;
    }
    if (!strcmp(key, "machine") && (!strcmp(value, "mvs") || !strcmp(value, "aes"))) return (value[0] == 'a') == (rr_ng_aes() != 0);
    return false;
}

static void option_rows(int slot, RrhkOptionRows *rows) {
    if (slot == 0)
        rrhk_option_row_run(rows, SDL_SCANCODE_F5, RR_ICON_ROW_SPRITE, "%s",
                             rr_tr(rr_ng_enhanced() ? "F5 Enhanced Neo Geo: ON" : "F5 Enhanced Neo Geo: OFF"));
    else
        rrhk_option_row_run(rows, SDL_SCANCODE_F11, RR_ICON_ROW_COIN, "%s", rr_ng_arcade_only() ? "F11 Arcade Only" : !rr_ng_aes_available() ?
            rr_tr("F11 AES: BIOS neo-epo.bin required") : rr_ng_aes() ? "F11 Console AES -> Arcade MVS (restart)" :
            "F11 Arcade MVS -> Console AES (restart)");
}

static void help_lines(int slot, const char **lines, int *count) {
    if (slot == 0)
        lines[(*count)++] = rr_ng_enhanced() ? rrhk_tr("F5 Enhanced Neo Geo: ON", "F5 Neo Geo amelioree : OUI") :
                                               rrhk_tr("F5 Enhanced Neo Geo: OFF", "F5 Neo Geo amelioree : NON");
    else
        lines[(*count)++] = rr_ng_arcade_only() ? "F11 Arcade Only" : !rr_ng_aes_available() ? "F11 AES: BIOS neo-epo.bin required" :
                            rr_ng_aes() ? "F11 Console AES -> Arcade MVS (restart)" : "F11 Arcade MVS -> Console AES (restart)";
}

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rrhk_tr("Arrows + S/D/F/E: A/B/C/D", "Fleches + S/D/F/E : A/B/C/D"));
    /* In AES the Coin action drives nothing (rr_ng_host_coin_bits), so only Start is listed. */
    rrhk_menu_line(ctx, y + RR_MENU_LINE, rr_ng_aes() ? rrhk_tr("Enter / pad Start: cartridge Start", "Entree / Start manette : Start jeu") :
                                                       rrhk_tr("Enter: Start; Shift/Back: coin", "Entree : Start; Maj/Back : credit"));
}

static bool key_event(RrhkUi *ui, SDL_Scancode key, bool *running) {
    if (key == SDL_SCANCODE_F11) {
        if (rr_ng_arcade_only()) {
            rrhk_notice("Arcade Only", 2500);
        } else if (rr_ng_aes_available()) {
            if (rr_display_save(ui->ini_file, ui->data_dir, L"NeoGeo.Runtime", L"aes", rr_ng_aes() ? 0 : 1)) {
                rr_ng_request_mode_restart(); *running = false;
            } else rrhk_notice("Config unavailable", 2500);
        } else rrhk_notice("AES requires neo-epo.bin in your BIOS archive. Regenerate this game.", 5000);
        return true;
    }
    if (key == SDL_SCANCODE_F5) {
        rr_ng_set_enhanced(!rr_ng_enhanced());
        rrhk_notice(rr_ng_enhanced() ? rrhk_tr("Enhanced Neo Geo: ON", "Neo Geo amelioree : OUI") :
                                       rrhk_tr("Enhanced Neo Geo: OFF", "Neo Geo amelioree : NON"), 1800);
        if (!rr_display_save(ui->ini_file, ui->data_dir, L"NeoGeo.Runtime", L"enhanced", rr_ng_enhanced() ? 1 : 0))
            snprintf(ui->status, sizeof(ui->status), "%s", rrhk_tr("Config unavailable", "Config inaccessible"));
        return true;
    }
    return false;
}

static void before_frame(const RrhkAudioProbe *audio, uint64_t input_frame) {
    (void)input_frame;
    rr_ng_audio_queue_probe(audio->audio_playing, audio->audio_queued, audio->audio_rate, audio->audio_period);
}
static void before_present(SDL_Renderer *renderer) { rr_ng_ui_test_present(renderer); }
static int players(void) { return 2; }

/* The picture shown: the frame itself, but for the 8-pixel band of a fix-layer edge mask the detector has latched as a
 * coloured overscan band (neogeo_fixmask.h), painted black in a copy. rr16_pixels() - what the validation hashes, the
 * reference runs and the checks read - is never touched. */
static const uint32_t *view_pixels(void) {
    static uint32_t view[RR16_WIDTH * RR16_HEIGHT];
    return rr_ng_fixmask_view(&rr_ng_fix_mask, rr16_pixels(), view);
}

/* Only the explicit test event harness calls this read-only observation. */
void rr_ng_ui_snapshot(FILE *file, const char *label, void *window) {
    const RrhkUi *ui = rrhk_ui();
    SDL_Window *win = window; int width, height; SDL_GetWindowSize(win, &width, &height);
    fprintf(file, "{\"label\":"); rr_ng_test_json(file, label);
    fprintf(file, ",\"frame\":%u,\"menu\":%d,\"player\":%d,\"row\":%d,\"gamepad_page\":%d,\"capturing\":%d,"
        "\"filter\":%d,\"display_mode\":%d,\"fullscreen\":%s,\"french\":%d,\"autofire\":%d,\"width\":%d,\"height\":%d,\"title\":",
        rr_ng_frame_index(), ui->menu, ui->player, ui->row, ui->gamepad_page, ui->capturing,
        ui->filter, ui->fullscreen, (SDL_GetWindowFlags(win) & SDL_WINDOW_FULLSCREEN) ? "true" : "false", ui->language, ui->autofire, width, height);
    rr_ng_test_json(file, SDL_GetWindowTitle(win)); fprintf(file, ",\"version\":"); rr_ng_test_json(file, rr_menu_build_label());
    fprintf(file, ",\"enhanced_mode\":%s,\"machine_mode\":\"%s\",\"aes_available\":%s", rr_ng_enhanced() ? "true" : "false", rr_ng_aes() ? "aes" : "mvs", rr_ng_aes_available() ? "true" : "false");
    fprintf(file, ",\"status\":"); rr_ng_test_json(file, ui->status);
    fprintf(file, ",\"pads\":[%u,%u],\"controllers\":[%s,%s],\"keyboard\":[",
        rrhk_pad_word(0, rr16_input_frame()), rrhk_pad_word(1, rr16_input_frame()), ui->pads[0] ? "true" : "false", ui->pads[1] ? "true" : "false");
    for (int p = 0; p < 2; ++p) { fprintf(file, "%s[", p ? "," : ""); for (int a = 0; a < ACTIONS; ++a) fprintf(file, "%s%d", a ? "," : "", ui->keys[p][a]); fprintf(file, "]"); }
    fprintf(file, "],\"key_labels\":[");
    for (int a = 0; a < 4; ++a) { if (a) fputc(',', file); rr_ng_test_json(file, rr_keyboard_name(ui->keys[0][a])); }
    fprintf(file, "],\"gamepad\":[");
    for (int p = 0; p < 2; ++p) { fprintf(file, "%s[", p ? "," : ""); for (int a = 0; a < ACTIONS; ++a) fprintf(file, "%s%d", a ? "," : "", ui->buttons[p][a]); fprintf(file, "]"); }
    fprintf(file, "]}\n"); fflush(file);
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = RR16_SECTION, .console_name = RR16_CONSOLE,
            .table_players = 2, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
            .max_width = RR16_WIDTH, .max_height = RR16_HEIGHT, .frame_seconds = RR16_FRAME_SECONDS,
            .reset = rr16_reset, .run_frame = rr16_frame, .pause = rr16_pause,
            .pixels = view_pixels, .visible_width = rr16_visible_width, .visible_height = rr16_visible_height,
            .raster_height = rr16_raster_height, .display_width = rr16_visible_width,
            .audio = rr16_audio, .interpreted = rr16_interpreted, .audio_interpreted = rr16_audio_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .input_frame = rr16_input_frame,
            .settings_loaded = settings_loaded, .option_rows = option_rows, .help_lines = help_lines,
            .help_controls = help_controls, .key_event = key_event,
            .snap_bound = rr_ng_snap_bound, .snap_save = rr_ng_snap_save, .snap_load = rr_ng_snap_load,
            .digest = rr_ng_digest, .side_effects = rr_ng_side_effects, .session_begin = rr_ng_session_clock,
            .session_option = session_option,
            .frame_limit = rr16_host_frame_limit, .frame_start = rr16_host_test_tick,
            .before_frame = before_frame, .cost_enabled = rr_ng_performance_enabled, .cost = rr_ng_host_cost,
            .before_present = before_present, .finished = rr_ng_host_timing,
        };
    }
    return &machine;
}

int rr16_sdl_main(const char *title, int scale) { return rrhk_main(rrhk_adapter(), title, scale); }
