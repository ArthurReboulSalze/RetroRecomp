/* Shared host-only options for all seven consoles. Settings stay in datas;
 * chord observation never writes during gameplay or bypasses normal shutdown. */
#ifndef RR_GAME_OPTIONS_H
#define RR_GAME_OPTIONS_H
#include <SDL.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "platform_io.h"
#include "retro_menu.h"
#include "retro_keyboard.h"
#include "audio_filter.h"
#define RR_OPTIONS_MENU 5
/* F2 gathers every setting on pages: the console's control pages (with the
 * quit and restart combinations), the gun page of gun games, then the
 * options. Left/Right, Tab, LB/RB or the D-pad turn pages. */
#define RR_CONTROLS_MENU 2
#define RR_GUN_MENU 4
typedef struct { int controls, gun; } RrPages;
/* Controller defaults: hold Start+Select (Back) one second to restart the
 * console, L3+R3 one second to quit. Both can be changed or cleared. */
#define RR_OPTIONS_RESTART_PAD ((1u << SDL_CONTROLLER_BUTTON_START) | (1u << SDL_CONTROLLER_BUTTON_BACK))
#define RR_OPTIONS_QUIT_PAD ((1u << SDL_CONTROLLER_BUTTON_LEFTSTICK) | (1u << SDL_CONTROLLER_BUTTON_RIGHTSTICK))
static struct {
    wchar_t file[32768], dir[32768], section[64];
    SDL_atomic_t audio_mode;
    SDL_atomic_t audio_epoch;
    int key[3], pad, row, capture, armed, pending_key[3], count;
    Uint32 pending_pad;
    SDL_JoystickID capture_pad;
    Uint8 down[SDL_NUM_SCANCODES];
    struct { SDL_JoystickID id; Uint32 mask; } pads[4];
    Uint64 hold;
    int held, suppressed, focused;
    int rkey[3], rpad, rheld, rfired;
    Uint64 rhold;
    int fkeys, fkeys_machine;
    char machine[16];
    char status[100];
    SDL_Renderer *renderer;
} rr_options;
static RrAudioFilter rr_options_dsp;
static int rr_options_audio_epoch;
#define RR_HOST_AUDIO_FILTER rr_options_audio
#define RR_HOST_AUDIO_RESET rr_options_audio_reset

/* One key or a combination (up to three keys); the one-second hold guards
 * a stray press. Duplicates and out-of-range entries are ignored. */
static void rr_options_load_keys(const wchar_t *const entries[3], int out[3]) {
    int count = 0;
    for (int i = 0; i < 3; ++i) {
        int key = rr_ini_int(rr_options.section, entries[i], 0, rr_options.file);
        bool duplicate = false;
        for (int j = 0; j < i; ++j) if (out[j] == key) duplicate = true;
        if (key > 0 && key < SDL_NUM_SCANCODES && !duplicate) {out[i] = key; ++count;}
    }
    if (!count) memset(out, 0, 3 * sizeof *out);
}
/* A stored 0 is an explicitly cleared binding; a missing entry is the default. */
static int rr_options_load_pad(const wchar_t *entry, unsigned fallback) {
    unsigned mask = (unsigned)rr_ini_int(rr_options.section, entry, (int)fallback, rr_options.file);
    return (int)(mask & ((1u << SDL_CONTROLLER_BUTTON_MAX) - 1u));
}
static const wchar_t *const rr_options_quit_keys[3] = {L"quit_key0", L"quit_key1", L"quit_key2"};
static const wchar_t *const rr_options_restart_keys[3] = {L"restart_key0", L"restart_key1", L"restart_key2"};

static void rr_options_init(const wchar_t *console) {
    memset(&rr_options, 0, sizeof rr_options);
    memset(&rr_options_dsp, 0, sizeof rr_options_dsp);
    rr_options_audio_epoch = 0;
    rr_options.focused = 1;
    rr_options.pad = (int)RR_OPTIONS_QUIT_PAD; rr_options.rpad = (int)RR_OPTIONS_RESTART_PAD;
    for (int i = 0; i < 4; ++i) rr_options.pads[i].id = -1;
    if (!rr_executable_directory(rr_options.dir, 32600)) return;
    rr_wide_append(rr_options.dir, 32768, RR_SLASH_W L"datas");
    rr_wide_copy(rr_options.file, 32768, rr_options.dir);
    rr_wide_append(rr_options.file, 32768, RR_SLASH_W L"Retro-Recomp.ini");
    swprintf(rr_options.section, 64, L"%ls.Options", console);
    int mode = rr_ini_int(rr_options.section, L"audio_filter", 0, rr_options.file);
    SDL_AtomicSet(&rr_options.audio_mode, mode >= 0 && mode <= 2 ? mode : 0);
    rr_options_load_keys(rr_options_quit_keys, rr_options.key);
    rr_options_load_keys(rr_options_restart_keys, rr_options.rkey);
    rr_options.pad = rr_options_load_pad(L"quit_pad", RR_OPTIONS_QUIT_PAD);
    rr_options.rpad = rr_options_load_pad(L"restart_pad", RR_OPTIONS_RESTART_PAD);
}

/* Computers with their own function keys F1..F`count` can hand them to the
 * guest (off by default); Ctrl+F1-F12 then reach Retro-Recomp. */
static void rr_options_keyboard(const char *machine, int count) {
    snprintf(rr_options.machine, sizeof rr_options.machine, "%s", machine);
    rr_options.fkeys = count;
    rr_options.fkeys_machine = rr_options.file[0] &&
        rr_ini_int(rr_options.section, L"fkeys_machine", 0, rr_options.file) == 1;
}

/* True when this function key is a Retro-Recomp shortcut rather than a key
 * of the computer: always with Ctrl (not Ctrl+Alt) or inside a menu. */
static bool rr_options_host_fkey(int key, SDL_Keymod mod, bool menu) {
    if (key < SDL_SCANCODE_F1 || key > SDL_SCANCODE_F12) return false;
    if (menu || ((mod & KMOD_CTRL) && !(mod & KMOD_ALT))) return true;
    return !rr_options.fkeys_machine || key >= SDL_SCANCODE_F1 + rr_options.fkeys;
}

static bool rr_options_store(const wchar_t *entry, int value) {
    wchar_t text[24];
    swprintf(text, 24, L"%d", value);
    bool ok = rr_options.file[0] && rr_mkdir(rr_options.dir) &&
        rr_ini_set(rr_options.section, entry, text, rr_options.file);
    snprintf(rr_options.status, sizeof rr_options.status, "%s", rr_tr(ok ? "Settings saved" : "Config unavailable"));
    return ok;
}

/* Called only by the PCM consumer. Mode is the sole cross-thread field. */
static void rr_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate) {
    int epoch = SDL_AtomicGet(&rr_options.audio_epoch);
    if (epoch != rr_options_audio_epoch) {rr_options_dsp.ready = 0; rr_options_audio_epoch = epoch;}
    rr_audio_filter(pcm, frames, channels, floating, rate,
        SDL_AtomicGet(&rr_options.audio_mode), &rr_options_dsp);
}
static void rr_options_audio_reset(void) {SDL_AtomicAdd(&rr_options.audio_epoch, 1);}

static bool rr_options_any_down(void) {
    for (int i = 0; i < SDL_NUM_SCANCODES; ++i) if (rr_options.down[i]) return true;
    for (int i = 0; i < 4; ++i) if (rr_options.pads[i].mask) return true;
    return false;
}

/* Keys of either binding, and buttons of the quit binding, take priority
 * over host shortcuts. Restart buttons (Start/Select by default) keep their
 * cartridge and pause roles until the hold completes. */
static bool rr_options_component(int key, int button) {
    for (int i = 0; i < 3; ++i) if (key && (rr_options.key[i] == key || rr_options.rkey[i] == key)) return true;
    return button >= 0 && button < SDL_CONTROLLER_BUTTON_MAX && (rr_options.pad & (1u << button)) != 0;
}

static void rr_options_observe(const SDL_Event *e) {
    if (e->type == SDL_KEYDOWN || e->type == SDL_KEYUP) {
        int k = e->key.keysym.scancode;
        if (k > 0 && k < SDL_NUM_SCANCODES) rr_options.down[k] = e->type == SDL_KEYDOWN;
    } else if (e->type == SDL_CONTROLLERBUTTONDOWN || e->type == SDL_CONTROLLERBUTTONUP) {
        int index = -1;
        for (int i = 0; i < 4; ++i) if (rr_options.pads[i].id == e->cbutton.which) index = i;
        if (index < 0) for (int i = 0; i < 4; ++i) if (rr_options.pads[i].id < 0) {index = i; break;}
        if (index >= 0) {
            int i = index;
            rr_options.pads[i].id = e->cbutton.which;
            if (e->cbutton.button < SDL_CONTROLLER_BUTTON_MAX) {
                Uint32 bit = 1u << e->cbutton.button;
                if (e->type == SDL_CONTROLLERBUTTONDOWN) rr_options.pads[i].mask |= bit;
                else rr_options.pads[i].mask &= ~bit;
            }
        }
    } else if (e->type == SDL_CONTROLLERDEVICEREMOVED) {
        if ((rr_options.capture == 2 || rr_options.capture == 4) && rr_options.capture_pad == e->cdevice.which) rr_options.capture = 0;
        for (int i = 0; i < 4; ++i) if (rr_options.pads[i].id == e->cdevice.which) {
            rr_options.pads[i].id = -1; rr_options.pads[i].mask = 0;
        }
    } else if (e->type == SDL_WINDOWEVENT && e->window.event == SDL_WINDOWEVENT_FOCUS_LOST) {
        rr_options.capture = 0;
        rr_options.focused = 0; rr_options.suppressed = 1;
        memset(rr_options.down, 0, sizeof rr_options.down);
        for (int i = 0; i < 4; ++i) rr_options.pads[i].mask = 0;
        rr_options.held = rr_options.rheld = 0;
    } else if (e->type == SDL_WINDOWEVENT && e->window.event == SDL_WINDOWEVENT_FOCUS_GAINED) {
        rr_options.focused = 1;
    }
}

/* Rows 1/2 bind quit (keyboard/controller), rows 3/4 bind restart. */
static void rr_options_capture_done(void) {
    bool restart = rr_options.capture > 2;
    if ((rr_options.capture == 1 || rr_options.capture == 3) && rr_options.count) {
        int *keys = restart ? rr_options.rkey : rr_options.key;
        for (int i = 0; i < 3; ++i)
            if (rr_options_store((restart ? rr_options_restart_keys : rr_options_quit_keys)[i], rr_options.pending_key[i]))
                keys[i] = rr_options.pending_key[i];
    } else if ((rr_options.capture == 2 || rr_options.capture == 4) && rr_options.pending_pad) {
        if (rr_options_store(restart ? L"restart_pad" : L"quit_pad", (int)rr_options.pending_pad))
            *(restart ? &rr_options.rpad : &rr_options.pad) = (int)rr_options.pending_pad;
    } else snprintf(rr_options.status, sizeof rr_options.status, "%s", rr_tr("Press a control..."));
    rr_options.capture = 0;
    rr_options.suppressed = 1;
}

static bool rr_pages_open(int menu) {
    return menu == RR_CONTROLS_MENU || menu == RR_GUN_MENU || menu == RR_OPTIONS_MENU;
}
static int rr_pages_count(RrPages pages) {return pages.controls + (pages.gun ? 1 : 0) + 1;}
static int rr_pages_index(RrPages pages, int menu, int control) {
    if (menu == RR_CONTROLS_MENU) return control >= 0 && control < pages.controls ? control : 0;
    return pages.controls + (pages.gun && menu != RR_GUN_MENU ? 1 : 0);
}
/* Returns the menu of `page` (wrapping both ways) and sets its control page.
 * Each page opens on its first row. */
static int rr_pages_goto(RrPages pages, int page, int *control) {
    int count = rr_pages_count(pages);
    page = (page % count + count) % count;
    *control = page < pages.controls ? page : 0;
    rr_options.row = 0; rr_options.status[0] = 0;
    if (page < pages.controls) return RR_CONTROLS_MENU;
    return pages.gun && page == pages.controls ? RR_GUN_MENU : RR_OPTIONS_MENU;
}
/* -1 or 1 to turn the page, 0 otherwise. Hosts call it outside binding capture. */
static int rr_pages_step(const SDL_Event *e) {
    if (e->type == SDL_KEYDOWN && !e->key.repeat) {
        SDL_Scancode key = e->key.keysym.scancode;
        if (key == SDL_SCANCODE_LEFT) return -1;
        if (key == SDL_SCANCODE_RIGHT) return 1;
        if (key == SDL_SCANCODE_TAB) return (e->key.keysym.mod & KMOD_SHIFT) ? -1 : 1;
    } else if (e->type == SDL_CONTROLLERBUTTONDOWN) {
        int button = e->cbutton.button;
        if (button == SDL_CONTROLLER_BUTTON_LEFTSHOULDER || button == SDL_CONTROLLER_BUTTON_DPAD_LEFT) return -1;
        if (button == SDL_CONTROLLER_BUTTON_RIGHTSHOULDER || button == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) return 1;
    }
    return 0;
}

/* Quit and restart combinations (capture ids 1/2 quit with keyboard or
 * controller, 3/4 restart) sit below player 1's controls: keyboard ones on
 * the keyboard page, controller ones on the gamepad page. */
#define RR_COMBO_ROWS 2
static int rr_combo_id(int index, bool gamepad) {return (index ? 3 : 1) + (gamepad ? 1 : 0);}
static const char *rr_combo_label(int index) {return rr_tr(index ? "Restart" : "Quit");}
static void rr_combo_start(int index, bool gamepad) {
    rr_options.capture = rr_combo_id(index, gamepad);
    rr_options.armed = 0; rr_options.count = 0; rr_options.pending_pad = 0;
    memset(rr_options.pending_key, 0, sizeof rr_options.pending_key);
    rr_options.status[0] = 0; rr_options.suppressed = 1;
}
static void rr_combo_clear(int index, bool gamepad) {
    if (!gamepad) {
        const wchar_t *const *entries = index ? rr_options_restart_keys : rr_options_quit_keys;
        if (rr_options_store(entries[0], 0) && rr_options_store(entries[1], 0) && rr_options_store(entries[2], 0))
            memset(index ? rr_options.rkey : rr_options.key, 0, sizeof rr_options.key);
    } else if (rr_options_store(index ? L"restart_pad" : L"quit_pad", 0)) *(index ? &rr_options.rpad : &rr_options.pad) = 0;
}
/* "Ctrl + Q", "Start + Back", "Unassigned" or the capture prompt. */
static void rr_combo_value(char *out, size_t size, int index, bool gamepad) {
    out[0] = 0;
    if (rr_options.capture == rr_combo_id(index, gamepad)) {snprintf(out, size, "%s", rr_tr("Press combo, then release")); return;}
    if (!gamepad) {
        const int *keys = index ? rr_options.rkey : rr_options.key;
        for (int i = 0; i < 3; ++i) if (keys[i]) {
            size_t used = strlen(out);
            snprintf(out + used, size - used, "%s%s", used ? " + " : "", rr_keyboard_name((SDL_Scancode)keys[i]));
        }
    } else {
        int pad = index ? rr_options.rpad : rr_options.pad;
        for (int i = 0; i < SDL_CONTROLLER_BUTTON_MAX; ++i) if (pad & (1 << i)) {
            size_t used = strlen(out);
            const char *name = SDL_GameControllerGetStringForButton((SDL_GameControllerButton)i);
            snprintf(out + used, size - used, "%s%s", used ? " + " : "", name ? name : "?");
        }
    }
    if (!out[0]) snprintf(out, size, "%s", rr_tr("Unassigned"));
}
/* Hint line for a selected combination row. */
static const char *rr_combo_hint(int index) {
    if (rr_options.capture) return rr_tr("Esc: cancel binding");
    return rr_tr(index ? "Hold restart combo for 1 second" : "Hold quit combo for 1 second");
}

/* The options page: the function-key settings, the audio filter and, on
 * computers, the function-key choice. Each host builds its rows. */
#define RR_ROW_AUDIO (-1)
#define RR_ROW_FKEYS (-2)
/* The rows hold their own text and no pointer, so a host can build them in a
 * function and return the struct by value (a pointer to text[i] would point
 * into the callee's frame once copied, which GCC does not hide as MSVC does). */
typedef struct { char text[10][80]; int keys[10], count; } RrOptionRows;
static void rr_option_row(RrOptionRows *d, int key, const char *format, const char *value) {
    if (d->count >= 10) return;
    snprintf(d->text[d->count], sizeof d->text[0], rr_tr(format), value);
    d->keys[d->count] = key; ++d->count;
}
/* Rows every console shares, after its function-key rows. */
static void rr_option_shared_rows(RrOptionRows *d) {
    static const char *const modes[] = {"Off", "Light", "Soft"};
    char text[80];
    snprintf(text, sizeof text, "%s: %s", rr_tr("Audio filter"), rr_tr(modes[SDL_AtomicGet(&rr_options.audio_mode)]));
    rr_option_row(d, RR_ROW_AUDIO, "%s", text);
    if (rr_options.fkeys) {
        snprintf(text, sizeof text, rr_tr("F1-F%d keys: %s"), rr_options.fkeys,
            rr_options.fkeys_machine ? rr_options.machine : "Retro-Recomp");
        rr_option_row(d, RR_ROW_FKEYS, "%s", text);
    }
}
static const char *rr_option_filter_name(int filter) {
    static const char *const names[] = {"Sharp pixels", "xBR smooth", "Scale2x", "Scanlines"};
    return rr_tr(names[filter >= 0 && filter < 4 ? filter : 0]);
}
static const char *rr_option_mode_name(int mode) {
    static const char *const names[] = {"Windowed", "Pixel perfect", "Fit to screen"};
    return rr_tr(names[mode >= 0 && mode < 3 ? mode : 0]);
}
/* Rows of the options page: one menu line each, from the first line. */
static int rr_pages_row_at(const SDL_Event *e, int count) {
    if (e->type != SDL_MOUSEBUTTONDOWN || e->button.button != SDL_BUTTON_LEFT || !rr_options.renderer) return -1;
    SDL_Window *win = SDL_GetWindowFromID(e->button.windowID);
    if (!win) return -1;
    int x, y, scale, ww, wh, rw, rh;
    rr_menu_layout(rr_options.renderer, &x, &y, &scale);
    SDL_GetWindowSize(win, &ww, &wh); SDL_GetRendererOutputSize(rr_options.renderer, &rw, &rh);
    if (ww <= 0 || wh <= 0 || scale <= 0) return -1;
    int px = (e->button.x * rw / ww - x) / scale, py = (e->button.y * rh / wh - y) / scale;
    if (px < 12 || px >= 244 || py < RR_MENU_FIRST_LINE || py >= RR_MENU_FIRST_LINE + count * RR_MENU_LINE) return -1;
    return (py - RR_MENU_FIRST_LINE) / RR_MENU_LINE;
}
/* Function-key rows run their key exactly as the shortcut does; the audio
 * filter and computer rows change here. Enter / A / + choose the next value,
 * - the previous one. Returns the function key to run, -1 when the event was
 * used, 0 for events the host keeps (pages, shortcuts, Esc). */
static int rr_option_page_event(const SDL_Event *e, const RrOptionRows *d) {
    if (d->count <= 0) return 0;
    int *row = &rr_options.row;
    if (*row >= d->count) *row = 0;
    int key = e->type == SDL_KEYDOWN && !e->key.repeat ? e->key.keysym.scancode : 0;
    int button = e->type == SDL_CONTROLLERBUTTONDOWN ? e->cbutton.button : -1;
    int clicked = rr_pages_row_at(e, d->count);
    if (clicked >= 0) {*row = clicked; key = SDL_SCANCODE_RETURN;}
    if (key == SDL_SCANCODE_UP || button == SDL_CONTROLLER_BUTTON_DPAD_UP) {*row = (*row + d->count - 1) % d->count; return -1;}
    if (key == SDL_SCANCODE_DOWN || button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) {*row = (*row + 1) % d->count; return -1;}
    bool back = key == SDL_SCANCODE_MINUS || key == SDL_SCANCODE_KP_MINUS;
    bool next = key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER || key == SDL_SCANCODE_EQUALS ||
        key == SDL_SCANCODE_KP_PLUS || button == SDL_CONTROLLER_BUTTON_A;
    if (!back && !next) return 0;
    if (d->keys[*row] == RR_ROW_AUDIO) {
        int mode = (SDL_AtomicGet(&rr_options.audio_mode) + (back ? 2 : 1)) % 3;
        if (rr_options_store(L"audio_filter", mode)) SDL_AtomicSet(&rr_options.audio_mode, mode);
        return -1;
    }
    if (d->keys[*row] == RR_ROW_FKEYS) {
        if (rr_options_store(L"fkeys_machine", !rr_options.fkeys_machine)) rr_options.fkeys_machine = !rr_options.fkeys_machine;
        return -1;
    }
    return next ? d->keys[*row] : -1;
}
static void rr_option_page_draw(SDL_Renderer *r, const RrOptionRows *d, int page, int pages) {
    rr_options.renderer = r;
    int x, y, unit; rr_menu_layout(r, &x, &y, &unit);
    rr_menu_begin(r, x, y, unit);
    rr_menu_page_header(r, x, y, unit, rr_tr("Retro-Recomp - Options"), page, pages);
    if (rr_options.row >= d->count) rr_options.row = 0;
    for (int i = 0; i < d->count; ++i) {
        int line = RR_MENU_FIRST_LINE + i * RR_MENU_LINE;
        if (i == rr_options.row) rr_menu_box(r, x, y, unit, 12, line, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
        rr_menu_text(r, x, y, unit, 16, line, d->text[i], RR_MENU_GOLD);
    }
    bool computer = d->count && d->keys[rr_options.row] == RR_ROW_FKEYS;
    if (rr_options.status[0]) rr_menu_text(r, x, y, unit, 14, RR_MENU_HINT_LINE, rr_options.status, RR_MENU_GOLD);
    else rr_menu_text(r, x, y, unit, 14, RR_MENU_HINT_LINE,
        rr_tr(computer ? "Ctrl+F1-F12: Retro-Recomp shortcuts" : "Enter / A: change"), RR_MENU_HINT);
    rr_menu_text(r, x, y, unit, 14, RR_MENU_LAST_LINE, rr_tr("Left/Right: page | Esc: close"), RR_MENU_HINT);
    rr_menu_end(r);
}

/* Returns true when the host must not process the event again. A quit or
 * restart capture takes every event; an existing binding capture has
 * priority. Guide opens F2 on its options page and closes F2. */
static bool rr_options_event(const SDL_Event *e, int *menu, bool binding_capture) {
    rr_options_observe(e);
    if (binding_capture) rr_options.suppressed = 1;
    if (e->type == SDL_QUIT) return false;
    int key = e->type == SDL_KEYDOWN && !e->key.repeat ? e->key.keysym.scancode : 0;
    int button = e->type == SDL_CONTROLLERBUTTONDOWN ? e->cbutton.button : -1;
    if (rr_options.capture) {
        if (key == SDL_SCANCODE_ESCAPE) {rr_options.capture = 0; return true;}
        if (!rr_options.armed) {
            if (!rr_options_any_down()) rr_options.armed = 1;
            return true;
        }
        if ((rr_options.capture == 1 || rr_options.capture == 3) && key && rr_options.count < 3) {
            bool found = false;
            for (int i = 0; i < rr_options.count; ++i) if (rr_options.pending_key[i] == key) found = true;
            if (!found) rr_options.pending_key[rr_options.count++] = key;
        }
        if ((rr_options.capture == 2 || rr_options.capture == 4) && button >= 0 && button < SDL_CONTROLLER_BUTTON_MAX) {
            if (!rr_options.pending_pad) rr_options.capture_pad = e->cbutton.which;
            if (rr_options.capture_pad == e->cbutton.which) rr_options.pending_pad |= 1u << button;
        }
        if ((rr_options.count || rr_options.pending_pad) && !rr_options_any_down()) rr_options_capture_done();
        return true;
    }
    if (!binding_capture && !rr_options_component(key,button) && button == SDL_CONTROLLER_BUTTON_GUIDE) {
        *menu = rr_pages_open(*menu) ? 0 : RR_OPTIONS_MENU;
        rr_options.row = 0; rr_options.status[0] = 0; rr_options.suppressed = 1;
        return true;
    }
    /* An explicitly assigned quit chord takes priority over host-only
     * shortcuts; ordinary cartridge buttons keep their usual behavior. */
    return !binding_capture && rr_options_component(key,button) &&
        ((key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12) ||
         key == SDL_SCANCODE_P || button == SDL_CONTROLLER_BUTTON_GUIDE);
}

static bool rr_options_quit(int menu) {
    (void)menu;
    if (!rr_options.focused || rr_options.capture || rr_options.suppressed) {
        rr_options.held = 0;
        if (!rr_options_any_down()) rr_options.suppressed = 0;
        return false;
    }
    bool down = rr_options.key[0] != 0;
    for (int i = 0; i < 3; ++i) if (rr_options.key[i] && !rr_options.down[rr_options.key[i]]) down = false;
    int source = down ? 1 : 0;
    for (int i = 0; i < 4; ++i) if (rr_options.pad &&
        (rr_options.pads[i].mask & (Uint32)rr_options.pad) == (Uint32)rr_options.pad) source = i + 2;
    if (!source) {rr_options.held = 0; return false;}
    if (rr_options.held != source) {rr_options.held = source; rr_options.hold = SDL_GetTicks64();}
    return SDL_GetTicks64() - rr_options.hold >= 1000;
}

/* Restart binding: fires once after a one-second hold of the whole combination,
 * then re-arms only when it is released. Hosts poll it every frame. */
static bool rr_options_restart(int menu) {
    (void)menu;
    if (!rr_options.focused || rr_options.capture) {rr_options.rheld = 0; return false;}
    if (rr_options.suppressed && !rr_options_any_down()) rr_options.suppressed = 0;
    bool down = rr_options.rkey[0] != 0;
    for (int i = 0; i < 3; ++i) if (rr_options.rkey[i] && !rr_options.down[rr_options.rkey[i]]) down = false;
    int source = down ? 1 : 0;
    for (int i = 0; i < 4; ++i) if (rr_options.rpad &&
        (rr_options.pads[i].mask & (Uint32)rr_options.rpad) == (Uint32)rr_options.rpad) source = i + 2;
    if (!source) {rr_options.rheld = 0; return false;}
    /* A combination still held after a binding capture or a menu never fires. */
    if (rr_options.suppressed) {rr_options.rheld = source; rr_options.rfired = 1; return false;}
    if (rr_options.rheld != source) {rr_options.rheld = source; rr_options.rhold = SDL_GetTicks64(); rr_options.rfired = 0;}
    if (rr_options.rfired || SDL_GetTicks64() - rr_options.rhold < 1000) return false;
    rr_options.rfired = 1;
    return true;
}
#endif
