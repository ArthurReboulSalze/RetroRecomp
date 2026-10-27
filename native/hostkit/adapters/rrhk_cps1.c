/* CPS-1 adapter: the machine contract of the host kit over the rr16_*
 * functions of the CPS-1 host, plus the board's DIP switch page. Original
 * RetroRecomp code: MIT; the linked machine keeps its own terms. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include "retro_console16.h"
#include "console16_state.h"
#include "retro_menu.h"
#include "platform_io.h"
#include "hostkit/hostkit.h"

/* Bits follow cps1_host.h; each game maps them to its own ports. Players 3 and
 * 4 have no default keys (the keyboard is full); F2 binds them. */
#define PADS(button) {button, button, button, button}
enum { A, B, C, X, Y, Z, START, COIN, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const RrhkAction actions[ACTIONS] = {
    {"Button 1", L"B1", 1, RRHK_FACE, SDLK_w, {SDL_SCANCODE_W, SDL_SCANCODE_KP_7}, PADS(SDL_CONTROLLER_BUTTON_A)},
    {"Button 2", L"B2", 2, RRHK_FACE, SDLK_x, {SDL_SCANCODE_X, SDL_SCANCODE_KP_8}, PADS(SDL_CONTROLLER_BUTTON_B)},
    {"Button 3", L"B3", 4, RRHK_FACE, SDLK_c, {SDL_SCANCODE_C, SDL_SCANCODE_KP_9}, PADS(SDL_CONTROLLER_BUTTON_X)},
    {"Button 4", L"B4", 8, RRHK_FACE, SDLK_a, {SDL_SCANCODE_A, SDL_SCANCODE_KP_4}, PADS(SDL_CONTROLLER_BUTTON_Y)},
    {"Button 5", L"B5", 16, RRHK_FACE, SDLK_s, {SDL_SCANCODE_S, SDL_SCANCODE_KP_6}, PADS(SDL_CONTROLLER_BUTTON_LEFTSHOULDER)},
    {"Button 6", L"B6", 32, RRHK_FACE, SDLK_d, {SDL_SCANCODE_D, SDL_SCANCODE_KP_PLUS}, PADS(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)},
    {"Start", L"Start", 64, RRHK_SYSTEM, 0, {SDL_SCANCODE_RETURN, SDL_SCANCODE_KP_ENTER}, PADS(SDL_CONTROLLER_BUTTON_START)},
    {"Coin", L"Coin", 128, RRHK_SYSTEM, 0, {SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_0}, PADS(SDL_CONTROLLER_BUTTON_BACK)},
    {"Up", L"Up", 256, RRHK_DIR, 0, {SDL_SCANCODE_UP, SDL_SCANCODE_KP_5}, PADS(SDL_CONTROLLER_BUTTON_DPAD_UP)},
    {"Down", L"Down", 512, RRHK_DIR, 0, {SDL_SCANCODE_DOWN, SDL_SCANCODE_KP_2}, PADS(SDL_CONTROLLER_BUTTON_DPAD_DOWN)},
    {"Left", L"Left", 1024, RRHK_DIR, 0, {SDL_SCANCODE_LEFT, SDL_SCANCODE_KP_1}, PADS(SDL_CONTROLLER_BUTTON_DPAD_LEFT)},
    {"Right", L"Right", 2048, RRHK_DIR, 0, {SDL_SCANCODE_RIGHT, SDL_SCANCODE_KP_3}, PADS(SDL_CONTROLLER_BUTTON_DPAD_RIGHT)}};

/* Autofire counts guest frames; a reset or a load forgets held buttons. */
void rr16_host_discontinuity(void) { rrhk_autofire_reset(); }

/* DIP switches, per set in the export's settings file: applied before the
 * first frame and kept across Shift+F1 and F9. Only bits of known settings are
 * read back; anything else keeps the catalogue default. */
static const wchar_t *const dip_keys[3] = {L"DSWA", L"DSWB", L"DSWC"};
static void dip_section(wchar_t *out, size_t size) {
    const wchar_t *prefix = L"CPS1.Dips.";
    const char *set = RR_CPS1_SET;
    size_t n = 0;
    for (; prefix[n] && n + 1 < size; ++n) out[n] = prefix[n];
    for (size_t i = 0; set[i] && n + 1 < size; ++i) out[n++] = (wchar_t)(unsigned char)set[i];
    out[n] = 0;
}
static void settings_loaded(RrhkUi *ui) {
    if (!ui->ini_file[0] || !rr_cps1_dip_count()) return;
    wchar_t sec[64]; dip_section(sec, 64);
    uint16_t values[3]; rr_cps1_dip_values(values);
    bool stored_any = false;
    for (int port = 0; port < 3; ++port) {
        int stored = rr_ini_int(sec, dip_keys[port], -1, ui->ini_file);
        if (stored < 0 || stored > 0xffff) continue;
        for (int i = 0; i < rr_cps1_dip_count(); ++i) {
            const RrCps1Dip *dip = rr_cps1_dip(i);
            for (int k = 0; dip->port == port && k < dip->count; ++k)
                if ((stored & dip->mask) == dip->values[k]) {
                    values[port] = (uint16_t)((values[port] & ~dip->mask) | dip->values[k]);
                    stored_any = true;
                    break;
                }
        }
    }
    if (stored_any) rr_cps1_set_dip_values(values);
}
static void save_dips(const RrhkUi *ui) {
    if (!ui->ini_file[0]) return;
    rr_mkdir(ui->data_dir);
    wchar_t sec[64], value[16]; dip_section(sec, 64);
    uint16_t values[3]; rr_cps1_dip_values(values);
    for (int port = 0; port < 3; ++port) { swprintf(value, 16, L"%d", values[port]); rr_ini_set(sec, dip_keys[port], value, ui->ini_file); }
}
/* Rows of the DIP page: the switches whose condition holds now. */
static int dip_rows(int *rows) {
    int count = 0;
    for (int i = 0; i < rr_cps1_dip_count(); ++i) if (rr_cps1_dip_visible(i)) rows[count++] = i;
    return count;
}
static void dip_option(RrhkUi *ui, int step) {
    int rows[RR_CPS1_DIP_COUNT + 1], count = dip_rows(rows);
    if (!count) return;
    if (ui->row >= count) ui->row = count - 1;
    rr_cps1_dip_cycle(rows[ui->row], step);
    save_dips(ui);
    /* Most boards read their switches at power-on. */
    rrhk_notice(rr_tr("Shift+F1: restart"), 2500);
}
static bool dip_available(void) { return rr_cps1_dip_count() > 0; }
static void dip_key(RrhkUi *ui, SDL_Scancode key) {
    /* Left/Right turn pages: Enter / + choose the next value, - the previous. */
    int shown[RR_CPS1_DIP_COUNT + 1], rows = dip_rows(shown);
    if (!rows) return;
    if (key == SDL_SCANCODE_UP) ui->row = (ui->row + rows - 1) % rows;
    else if (key == SDL_SCANCODE_DOWN) ui->row = (ui->row + 1) % rows;
    else if (key == SDL_SCANCODE_MINUS || key == SDL_SCANCODE_KP_MINUS) dip_option(ui, -1);
    else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER || key == SDL_SCANCODE_EQUALS ||
             key == SDL_SCANCODE_KP_PLUS) dip_option(ui, 1);
}
static void dip_draw(RrhkUi *ui, const RrhkMenuCtx *ctx) {
    SDL_Renderer *ren = ctx->renderer;
    const int ox = ctx->ox, oy = ctx->oy, unit = ctx->unit;
    /* Twelve switches at a time, the selected one written out in full
     * below them; MAME's English names and settings. */
    int rows[RR_CPS1_DIP_COUNT + 1], count = dip_rows(rows);
    if (ui->row >= count) ui->row = count ? count - 1 : 0;
    const int shown = 12, top = ui->row < shown ? 0 : ui->row - shown + 1;
    for (int n = 0; n < shown && top + n < count; ++n) {
        const RrCps1Dip *dip = rr_cps1_dip(rows[top + n]);
        const int setting = rr_cps1_dip_setting(rows[top + n]), y = RR_MENU_FIRST_LINE + n * RR_MENU_LINE;
        char name[48];
        if (top + n == ui->row) rr_menu_box(ren, ox, oy, unit, 12, y, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
        snprintf(name, sizeof name, "%c %s", top + n == ui->row ? '>' : ' ', dip->name);
        rr_menu_text_fit(ren, ox, oy, unit, 14, y, 126, name, RR_MENU_GOLD);
        rr_menu_text_fit(ren, ox, oy, unit, 144, y, 98, setting < 0 ? "?" : dip->labels[setting], RR_MENU_GOLD);
    }
    if (count) {
        const RrCps1Dip *dip = rr_cps1_dip(rows[ui->row]);
        const int setting = rr_cps1_dip_setting(rows[ui->row]);
        char full[96];
        snprintf(full, sizeof full, "%s: %s", dip->name, setting < 0 ? "?" : dip->labels[setting]);
        rr_menu_text_fit(ren, ox, oy, unit, 14, RR_MENU_FIRST_LINE + shown * RR_MENU_LINE, 228, full, RR_MENU_ACCENT);
    }
    rr_menu_text(ren, ox, oy, unit, 14, RR_MENU_HINT_LINE, rr_tr("Enter / A / +: next | -: previous"), RR_MENU_GOLD);
    if (!ui->status[0]) rr_menu_text(ren, ox, oy, unit, 14, RR_MENU_LAST_LINE, rr_tr("Left/Right: page | Esc: close"), RR_MENU_GOLD);
}
static const RrhkPage dip_page = {"DIP switches", dip_available, dip_draw, dip_key};

static void help_controls(RrhkUi *ui, const RrhkMenuCtx *ctx, int y) {
    (void)ui;
    rrhk_menu_line(ctx, y, rr_tr("Arrows; W/X/C + A/S/D: buttons 1-6"));
    rrhk_menu_line(ctx, y + RR_MENU_LINE, rr_tr("Enter: Start; Shift/Back: coin"));
    rrhk_menu_line(ctx, y + 2 * RR_MENU_LINE, rr16_audio_interpreted() ? rr_tr("Sound CPU: interpreter fallback") :
                                                                          rr_tr("Sound CPU: native code"));
}

/* CPS-1 three- and four-player boards also read the third and fourth controllers. */
static int players(void) { return RR_CPS1_PLAYERS; }
static void before_frame(const RrhkAudioProbe *audio, uint64_t input_frame) {
    (void)audio;
    rr_cps1_set_extra_pads(players() > 2 ? rrhk_pad_word(2, input_frame) : 0,
                           players() > 3 ? rrhk_pad_word(3, input_frame) : 0);
}

const RrhkMachine *rrhk_adapter(void) {
    static RrhkMachine machine;
    if (!machine.actions) {
        machine = (RrhkMachine){
            .ini_section = RR16_SECTION, .console_name = RR16_CONSOLE,
            .table_players = 4, .players = players,
            .actions = actions, .action_count = ACTIONS,
            .up = UP, .down = DOWN, .left = LEFT, .right = RIGHT, .start = START,
            .max_width = RR16_WIDTH, .max_height = RR16_HEIGHT, .frame_seconds = RR16_FRAME_SECONDS,
            .reset = rr16_reset, .run_frame = rr16_frame, .pause = rr16_pause,
            .pixels = rr16_pixels, .visible_width = rr16_visible_width, .visible_height = rr16_visible_height,
            .raster_height = rr16_raster_height, .display_width = rr_cps1_display_width,
            .audio = rr16_audio, .interpreted = rr16_interpreted, .audio_interpreted = rr16_audio_interpreted,
            .state_path = rr16_state_path, .state_ready = rr16_state_ready, .state_file = rr16_state_file,
            .input_frame = rr16_input_frame,
            .page = &dip_page, .settings_loaded = settings_loaded, .help_controls = help_controls,
            .before_frame = before_frame,
        };
    }
    return &machine;
}

int rr16_sdl_main(const char *title, int scale) { return rrhk_main(rrhk_adapter(), title, scale); }
