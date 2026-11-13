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

/* The options page holds more rows than the fourteen game_options.h draws at once (1.7.0: the kit's own rows, the shared ones
 * and a machine's): the kit keeps them all here and hands game_options.h a window of fourteen around the selected row, which
 * scrolls. A page of fourteen rows or fewer (every machine of 1.6.9) is handed over whole, as before. Past RRHK_OPTION_ROWS a
 * row is not shown, and stderr says so once. */
#define RRHK_OPTION_ROWS 32
#define RRHK_OPTION_WINDOW ((int)(sizeof ((RrOptionRows *)0)->keys / sizeof ((RrOptionRows *)0)->keys[0]))
struct RrhkOptionRows { char text[RRHK_OPTION_ROWS][80]; int keys[RRHK_OPTION_ROWS], count; };

static void add_row(RrhkOptionRows *rows, int key, const char *text) {
    static bool told;
    if (rows->count >= RRHK_OPTION_ROWS) {
        if (!told) fprintf(stderr, "[host] the options page has more than %d rows: \"%s\" is not shown\n", RRHK_OPTION_ROWS, text);
        told = true;
        return;
    }
    snprintf(rows->text[rows->count], sizeof rows->text[0], "%s", text);
    rows->keys[rows->count++] = key;
}
void rrhk_option_row(RrhkOptionRows *rows, int key, const char *format, const char *value) {
    char text[80];
    snprintf(text, sizeof text, rr_tr(format), value);       /* as rr_option_row formats it */
    add_row(rows, key, text);
}

void rrhk_options_init(const wchar_t *console) {
    rr_options_init(console);
    rr_sound_load(rrhk.audio_volume, rrhk.audio_muted, rrhk.audio_device);
}
void rrhk_options_keyboard(const char *machine, int count) { rr_options_keyboard(machine, count); }
void rrhk_options_observe(const SDL_Event *event) { rr_options_observe(event); }
bool rrhk_options_host_fkey(int key, SDL_Keymod mod, bool menu) { return rr_options_host_fkey(key, mod, menu); }
bool rrhk_options_event(const SDL_Event *event, int *menu, bool binding_capture) {
    return rr_options_event(event, menu, binding_capture);
}
bool rrhk_options_component(int key, int button) { return rr_options_component(key, button); }
/* The gamepad Quit and Restart combinations are held on player 1's pad only, as the F2 capture takes the selected player's:
 * on an arcade board Start+Coin is any player's normal play, and another player's hold must not restart or quit the game for
 * everyone (docs/HOST_KIT.md, D13). Player 1 without a pad: no gamepad combination (the keyboard ones, Shift+F1 and Esc remain).
 * game_options.h tracks every pad it has seen; for the two checks the kit hides the buttons of the pads that are not player 1's
 * (looked up at each poll, so hot-plug and the Gamepad row of F2 are followed) and gives them back at once. It is done here and
 * not in game_options.h, whose bytes the Mega Drive and Super Nintendo quick-state keys hash. */
static bool player1_only(bool (*check)(int), int menu) {
    const SDL_JoystickID owner = rrhk.pads[0] ? SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(rrhk.pads[0])) : -1;
    const int count = (int)(sizeof rr_options.pads / sizeof rr_options.pads[0]);
    Uint32 held[sizeof rr_options.pads / sizeof rr_options.pads[0]];
    for (int i = 0; i < count; ++i) {
        held[i] = rr_options.pads[i].mask;
        if (owner < 0 || rr_options.pads[i].id != owner) rr_options.pads[i].mask = 0;
    }
    const bool fired = check(menu);
    for (int i = 0; i < count; ++i) rr_options.pads[i].mask = held[i];
    return fired;
}
bool rrhk_options_quit(int menu) { return player1_only(rr_options_quit, menu); }
bool rrhk_options_restart(int menu) { return player1_only(rr_options_restart, menu); }
void rrhk_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate) {
    rr_options_audio(pcm, frames, channels, floating, rate);
}
void rrhk_options_audio_reset(void) { rr_options_audio_reset(); }

/* The sound controls of every console (decision D12): volume and mute are applied by rrhk_options_audio to whatever the
 * machine plays, the hold silences the output while the speed is not 100%, the device is the one asked for. */
bool rrhk_sound_toggle_mute(void) { return rr_sound_toggle_mute(); }
bool rrhk_sound_muted(void) { return rr_sound_muted(); }
void rrhk_sound_hold(bool held) { SDL_AtomicSet(&rr_options.speed_held, held ? 1 : 0); }
bool rrhk_audio_held(void) { return SDL_AtomicGet(&rr_options.speed_held) != 0; }
const char *rrhk_audio_device(void) { return rr_sound_device()[0] ? rr_sound_device() : NULL; }
unsigned rrhk_audio_device_serial(void) { return rr_sound_device_serial(); }

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
    RrhkOptionRows d; d.count = 0;
    rrhk_option_row(&d, SDL_SCANCODE_F3, "F3 Filter: %s", rr_option_filter_name(rrhk.filter));
    rrhk_option_row(&d, SDL_SCANCODE_F4, "F4 Display: %s", rr_option_mode_name(rrhk.fullscreen));
    if (m->option_rows) m->option_rows(0, &d);
    rrhk_option_row(&d, SDL_SCANCODE_F6, "F6 Autofire: %s", rr_tr(rrhk.autofire ? "ON" : "OFF"));
    rrhk_option_row(&d, SDL_SCANCODE_F7, "F7 Language: %s", rr_language_name(rrhk.language));
    if (m->option_rows) m->option_rows(1, &d);
    /* The shared Vibration row, on a machine that vibrates (1.7.0): [Manettes] rumble. */
    if (m->rumble) rrhk_option_row(&d, RRHK_KEY_RUMBLE, "Vibration: %s", rr_tr(rrhk.rumble ? "ON" : "OFF"));
    rrhk_option_row(&d, SDL_SCANCODE_F12, "%s", rr_tr(rr_feedback_label()));
    RrOptionRows shared; shared.count = 0;
    rr_option_shared_rows(&shared);
    for (int i = 0; i < shared.count; ++i) add_row(&d, shared.keys[i], shared.text[i]);
    /* 1.7.4: the plates of the first seconds (F1, F2, Esc, the gamepad's combinations, a computer's keyboard) may be turned off. */
    rrhk_option_row(&d, RRHK_KEY_START_HELP, "Start-up reminders: %s", rr_tr(rrhk_start_help() ? "ON" : "OFF"));
    rrhk_option_row(&d, SDL_SCANCODE_GRAVE, "` Max speed: %s", rr_tr(rrhk.max_speed ? "ON" : "OFF"));
    return d;
}

/* The rows game_options.h is handed: all of them up to its fourteen, else the window that starts at `first`. */
static RrOptionRows option_window(const RrhkOptionRows *all, int first) {
    RrOptionRows d;
    d.count = SDL_min(all->count - first, RRHK_OPTION_WINDOW);
    for (int i = 0; i < d.count; ++i) {
        memcpy(d.text[i], all->text[first + i], sizeof d.text[i]);
        d.keys[i] = all->keys[first + i];
    }
    return d;
}
/* Past fourteen rows rr_options.row is the row of the whole list; the window follows it, moving only when it would leave. */
static int option_first;
int rrhk_option_scroll(void) {
    RrhkOptionRows all = option_rows();
    if (all.count <= RRHK_OPTION_WINDOW) return option_first = 0;
    if (rr_options.row < 0 || rr_options.row >= all.count) rr_options.row = 0;
    if (rr_options.row < option_first) option_first = rr_options.row;
    if (rr_options.row >= option_first + RRHK_OPTION_WINDOW) option_first = rr_options.row - RRHK_OPTION_WINDOW + 1;
    if (option_first > all.count - RRHK_OPTION_WINDOW) option_first = all.count - RRHK_OPTION_WINDOW;
    return option_first;
}
int rrhk_option_selected(void) { return rr_options.row; }
int rrhk_option_page_event(const SDL_Event *event) {
    RrhkOptionRows all = option_rows();
    if (all.count <= RRHK_OPTION_WINDOW) {
        RrOptionRows d = option_window(&all, 0);
        return rr_option_page_event(event, &d);
    }
    /* Up and Down move over the whole list (as rr_option_page_event does over its rows); the rest acts in the window. */
    const int key = event->type == SDL_KEYDOWN && !event->key.repeat ? event->key.keysym.scancode : 0;
    const int button = event->type == SDL_CONTROLLERBUTTONDOWN ? event->cbutton.button : -1;
    if (rr_options.row < 0 || rr_options.row >= all.count) rr_options.row = 0;
    if (key == SDL_SCANCODE_UP || button == SDL_CONTROLLER_BUTTON_DPAD_UP) { rr_options.row = (rr_options.row + all.count - 1) % all.count; return -1; }
    if (key == SDL_SCANCODE_DOWN || button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) { rr_options.row = (rr_options.row + 1) % all.count; return -1; }
    const int first = rrhk_option_scroll();
    RrOptionRows d = option_window(&all, first);
    rr_options.row -= first;
    const int chosen = rr_option_page_event(event, &d);
    rr_options.row += first;
    return chosen;
}
void rrhk_option_page_draw(SDL_Renderer *renderer) {
    RrhkOptionRows all = option_rows();
    if (all.count <= RRHK_OPTION_WINDOW) {
        RrOptionRows d = option_window(&all, 0);
        rr_option_page_draw(renderer, &d, rrhk_pages_index(), rrhk_pages_count());
        return;
    }
    const int first = rrhk_option_scroll();
    RrOptionRows d = option_window(&all, first);
    rr_options.row -= first;
    rr_option_page_draw(renderer, &d, rrhk_pages_index(), rrhk_pages_count());
    rr_options.row += first;
    /* ^ and v at the right edge: more rows above or below, as on the control pages */
    int x, y, unit; rr_menu_layout(renderer, &x, &y, &unit);
    SDL_SetRenderDrawBlendMode(renderer, SDL_BLENDMODE_BLEND);
    if (first > 0) rr_menu_text(renderer, x, y, unit, 246, RR_MENU_FIRST_LINE, "^", RR_MENU_HINT);
    if (first + d.count < all.count)
        rr_menu_text(renderer, x, y, unit, 246, RR_MENU_FIRST_LINE + (d.count - 1) * RR_MENU_LINE, "v", RR_MENU_HINT);
    rr_menu_end(renderer);
}

/* A gamepad combination is captured from the selected player's own pad, like a button binding (divergence 3): a
 * player without a pad waits, and the page says so (rrhk_menu_draw). */
void rrhk_combo_start(int index, bool gamepad) {
    rr_combo_start(index, gamepad);
    if (!gamepad) return;
    SDL_GameController *pad = rrhk.pads[rrhk.player];
    rr_options.capture_guard = 1;
    rr_options.capture_from = pad ? SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pad)) : -1;
}
bool rrhk_combo_capturing_pad(void) { return rr_options.capture == 2 || rr_options.capture == 4; }
bool rrhk_combo_capturing(int index, bool gamepad) { return rr_options.capture == rr_combo_id(index, gamepad); }
bool rrhk_combo_set(int index, bool gamepad) {
    if (gamepad) return (index ? rr_options.rpad : rr_options.pad) != 0;
    return (index ? rr_options.rkey : rr_options.key)[0] != 0;
}
void rrhk_combo_clear(int index, bool gamepad) { rr_combo_clear(index, gamepad); }
void rrhk_combo_value(char *out, size_t size, int index, bool gamepad) { rr_combo_value(out, size, index, gamepad); }
const char *rrhk_combo_label(int index) { return rr_combo_label(index); }
const char *rrhk_combo_hint(int index) { return rr_combo_hint(index); }
const char *rrhk_filter_name(int filter) { return rr_option_filter_name(filter); }
const char *rrhk_display_name(int mode) { return rr_option_mode_name(mode); }
void rrhk_menu_page_header(const RrhkMenuCtx *ctx, const char *title) {
    rr_menu_page_header(ctx->renderer, ctx->ox, ctx->oy, ctx->unit, title, rrhk_pages_index(), rrhk_pages_count());
}
