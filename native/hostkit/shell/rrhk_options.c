/* Options, F2 pages, quit/restart combinations and the audio filter: the only
 * file of the kit that includes game_options.h. That header keeps its settings
 * in file-level statics, so a second includer would get a second, separate
 * copy of them. Everything the rest of the shell needs from it is here. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include "game_options.h"
#include "runtime_feedback.h"
#include "hostkit/hostkit_internal.h"

/* The menu numbers and the combination rows belong to game_options.h; the
 * other files of the kit use these names. A mismatch is a negative array size. */
typedef char rrhk_menu_numbers_follow_game_options[
    (RRHK_MENU_CONTROLS == RR_CONTROLS_MENU && RRHK_MENU_PAGE == RR_GUN_MENU &&
     RRHK_MENU_OPTIONS == RR_OPTIONS_MENU && RRHK_COMBO_ROWS == RR_COMBO_ROWS) ? 1 : -1];

struct RrhkOptionRows { RrOptionRows rows; };

void rrhk_option_row(RrhkOptionRows *rows, int key, const char *format, const char *value) {
    rr_option_row(&rows->rows, key, format, value);
}

void rrhk_options_init(const wchar_t *console) { rr_options_init(console); }
void rrhk_options_keyboard(const char *machine, int count) { rr_options_keyboard(machine, count); }
void rrhk_options_observe(const SDL_Event *event) { rr_options_observe(event); }
bool rrhk_options_host_fkey(int key, SDL_Keymod mod, bool menu) { return rr_options_host_fkey(key, mod, menu); }
bool rrhk_options_event(const SDL_Event *event, int *menu, bool binding_capture) {
    return rr_options_event(event, menu, binding_capture);
}
bool rrhk_options_quit(int menu) { return rr_options_quit(menu); }
bool rrhk_options_restart(int menu) { return rr_options_restart(menu); }
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate) {
    rr_options_audio(pcm, frames, channels, floating, rate);
}
void rrhk_options_audio_reset(void) { rr_options_audio_reset(); }

/* F2 pages: each player's keyboard then gamepad, the machine's own page, then
 * the options. */
static RrPages settings_pages(void) {
    const RrhkMachine *m = rrhk.machine;
    bool page = m->page && (!m->page->available || m->page->available());
    return (RrPages){2 * m->players(), page ? 1 : 0};
}
int rrhk_pages_count(void) { return rr_pages_count(settings_pages()); }
int rrhk_pages_index(void) {
    return rr_pages_index(settings_pages(), rrhk.menu, rrhk.player * 2 + (rrhk.gamepad_page ? 1 : 0));
}
int rrhk_pages_goto(int page, int *control) { return rr_pages_goto(settings_pages(), page, control); }
bool rrhk_pages_open(int menu) { return rr_pages_open(menu); }
int rrhk_pages_step(const SDL_Event *event) { return rr_pages_step(event); }

/* Option rows run their function keys exactly as the shortcuts do. */
static RrhkOptionRows option_rows(void) {
    const RrhkMachine *m = rrhk.machine;
    RrhkOptionRows d; d.rows.count = 0;
    rr_option_row(&d.rows, SDL_SCANCODE_F3, "F3 Filter: %s", rr_option_filter_name(rrhk.filter));
    rr_option_row(&d.rows, SDL_SCANCODE_F4, "F4 Display: %s", rr_option_mode_name(rrhk.fullscreen));
    if (m->option_rows) m->option_rows(0, &d);
    rr_option_row(&d.rows, SDL_SCANCODE_F6, "F6 Autofire: %s", rr_tr(rrhk.autofire ? "ON" : "OFF"));
    rr_option_row(&d.rows, SDL_SCANCODE_F7, "F7 Language: %s", rr_language_name(rrhk.language));
    if (m->option_rows) m->option_rows(1, &d);
    rr_option_row(&d.rows, SDL_SCANCODE_F12, "%s", rr_tr(rr_feedback_label()));
    rr_option_shared_rows(&d.rows);
    return d;
}
int rrhk_option_page_event(const SDL_Event *event) {
    RrhkOptionRows d = option_rows();
    return rr_option_page_event(event, &d.rows);
}
void rrhk_option_page_draw(SDL_Renderer *renderer) {
    RrhkOptionRows d = option_rows();
    rr_option_page_draw(renderer, &d.rows, rrhk_pages_index(), rrhk_pages_count());
}

void rrhk_combo_start(int index, bool gamepad) { rr_combo_start(index, gamepad); }
void rrhk_combo_clear(int index, bool gamepad) { rr_combo_clear(index, gamepad); }
void rrhk_combo_value(char *out, size_t size, int index, bool gamepad) { rr_combo_value(out, size, index, gamepad); }
const char *rrhk_combo_label(int index) { return rr_combo_label(index); }
const char *rrhk_combo_hint(int index) { return rr_combo_hint(index); }
void rrhk_menu_page_header(const RrhkMenuCtx *ctx, const char *title) {
    rr_menu_page_header(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, title, rrhk_pages_index(), rrhk_pages_count());
}
