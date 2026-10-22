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

/* Returns true when the host must not process the event again. Existing
 * binding capture has priority. O / Y inside any menu, or Guide, opens options.
 * F10 is also available except on the SMS Light Phaser host. */
static bool rr_options_event(const SDL_Event *e, int *menu, bool binding_capture, bool f10) {
    rr_options_observe(e);
    if (binding_capture) rr_options.suppressed = 1;
    if (e->type == SDL_QUIT) return false;
    int key = e->type == SDL_KEYDOWN && !e->key.repeat ? e->key.keysym.scancode : 0;
    int button = e->type == SDL_CONTROLLERBUTTONDOWN ? e->cbutton.button : -1;
    if (*menu == RR_OPTIONS_MENU && rr_options.capture) {
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
    if (!binding_capture && !rr_options_component(key,button) && ((f10 && key == SDL_SCANCODE_F10) ||
            (key == SDL_SCANCODE_O && *menu) || button == SDL_CONTROLLER_BUTTON_GUIDE ||
            (button == SDL_CONTROLLER_BUTTON_Y && *menu))) {
        *menu = *menu == RR_OPTIONS_MENU ? 0 : RR_OPTIONS_MENU;
        rr_options.row = 0; rr_options.status[0] = 0; rr_options.suppressed = 1;
        return true;
    }
    if (*menu != RR_OPTIONS_MENU) {
        /* An explicitly assigned quit chord takes priority over host-only
         * shortcuts; ordinary cartridge buttons keep their usual behavior. */
        return !binding_capture && rr_options_component(key,button) &&
            ((key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12) ||
             key == SDL_SCANCODE_P || button == SDL_CONTROLLER_BUTTON_GUIDE);
    }
    if (e->type == SDL_MOUSEBUTTONDOWN && e->button.button == SDL_BUTTON_LEFT && rr_options.renderer) {
        SDL_Window *win = SDL_GetWindowFromID(e->button.windowID);
        if (win) {
            int x,y,scale,ww,wh,rw,rh;
            rr_menu_layout(rr_options.renderer,&x,&y,&scale);
            SDL_GetWindowSize(win,&ww,&wh); SDL_GetRendererOutputSize(rr_options.renderer,&rw,&rh);
            if (ww <= 0 || wh <= 0 || scale <= 0) return true;
            int px = (e->button.x * rw / ww - x) / scale;
            int py = (e->button.y * rh / wh - y) / scale;
            if (px >= 12 && px < 244 && py >= 32 && py < 32 + 6 * 17 && (py - 32) % 17 < 15) {
                rr_options.row = (py - 32) / 17; key = SDL_SCANCODE_RETURN;
            }
        }
    }
    if (key == SDL_SCANCODE_ESCAPE || button == SDL_CONTROLLER_BUTTON_B) *menu = 0;
    else if (key == SDL_SCANCODE_UP || button == SDL_CONTROLLER_BUTTON_DPAD_UP) rr_options.row = (rr_options.row + 5) % 6;
    else if (key == SDL_SCANCODE_DOWN || button == SDL_CONTROLLER_BUTTON_DPAD_DOWN) rr_options.row = (rr_options.row + 1) % 6;
    else if ((key == SDL_SCANCODE_DELETE || key == SDL_SCANCODE_BACKSPACE || button == SDL_CONTROLLER_BUTTON_X) && rr_options.row) {
        if (rr_options.row == 1 || rr_options.row == 3) {
            const wchar_t *const *entries = rr_options.row == 1 ? rr_options_quit_keys : rr_options_restart_keys;
            if (rr_options_store(entries[0], 0) && rr_options_store(entries[1], 0) && rr_options_store(entries[2], 0))
                memset(rr_options.row == 1 ? rr_options.key : rr_options.rkey, 0, sizeof rr_options.key);
        } else if (rr_options.row == 2 && rr_options_store(L"quit_pad", 0)) rr_options.pad = 0;
        else if (rr_options.row == 4 && rr_options_store(L"restart_pad", 0)) rr_options.rpad = 0;
    } else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT ||
            button == SDL_CONTROLLER_BUTTON_A || button == SDL_CONTROLLER_BUTTON_DPAD_LEFT || button == SDL_CONTROLLER_BUTTON_DPAD_RIGHT) {
        if (!rr_options.row) {
            int mode = (SDL_AtomicGet(&rr_options.audio_mode) +
                ((key == SDL_SCANCODE_LEFT || button == SDL_CONTROLLER_BUTTON_DPAD_LEFT) ? 2 : 1)) % 3;
            if (rr_options_store(L"audio_filter", mode)) SDL_AtomicSet(&rr_options.audio_mode, mode);
        } else if (rr_options.row == 5) *menu = 0;
        else {
            rr_options.capture = rr_options.row;
            rr_options.armed = 0; rr_options.count = 0; rr_options.pending_pad = 0;
            memset(rr_options.pending_key, 0, sizeof rr_options.pending_key);
            rr_options.status[0] = 0;
        }
    }
    return true;
}

static bool rr_options_quit(int menu) {
    if (!rr_options.focused || menu == RR_OPTIONS_MENU || rr_options.suppressed) {
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
    if (!rr_options.focused || menu == RR_OPTIONS_MENU) {rr_options.rheld = 0; return false;}
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

static void rr_options_draw(SDL_Renderer *renderer) {
    rr_options.renderer = renderer;
    int x, y, scale; rr_menu_layout(renderer, &x, &y, &scale);
    rr_menu_begin(renderer, x, y, scale);
#define RR_OPT_TEXT(px,py,t) rr_menu_text(renderer,x,y,scale,px,py,rr_tr(t),RR_MENU_GOLD)
    RR_OPT_TEXT(14, 15, "Retro-Recomp - Options");
    const char *modes[] = {"Off", "Light", "Soft"};
    char lines[6][100];
    snprintf(lines[0], 100, "%s: %s", rr_tr("Audio filter"), rr_tr(modes[SDL_AtomicGet(&rr_options.audio_mode)]));
    snprintf(lines[1], 100, "%s: %s", rr_tr("Quit: keyboard"), rr_tr(rr_options.key[0] ? "Configured" : "Unassigned"));
    snprintf(lines[2], 100, "%s: %s", rr_tr("Quit: gamepad"), rr_tr(rr_options.pad ? "Configured" : "Unassigned"));
    snprintf(lines[3], 100, "%s: %s", rr_tr("Restart: keyboard"), rr_tr(rr_options.rkey[0] ? "Configured" : "Unassigned"));
    snprintf(lines[4], 100, "%s: %s", rr_tr("Restart: gamepad"), rr_tr(rr_options.rpad ? "Configured" : "Unassigned"));
    snprintf(lines[5], 100, "%s", rr_tr("Close"));
    for (int i = 0; i < 6; ++i) {
        if (i == rr_options.row) rr_menu_box(renderer,x,y,scale,12,32+i*17,232,15,RR_MENU_SELECT,255);
        rr_menu_text(renderer,x,y,scale,16,35+i*17,lines[i],RR_MENU_GOLD);
    }
    RR_OPT_TEXT(14, 138, rr_options.capture ? "Press combo, then release" :
        rr_options.row == 3 || rr_options.row == 4 ? "Hold restart combo for 1 second" : "Hold quit combo for 1 second");
    RR_OPT_TEXT(14, 150, rr_options.capture ? "Esc: cancel binding" : "Enter / A: change | X: clear");
    char combo[100] = "";
    const int *keys = rr_options.row == 3 ? rr_options.rkey : rr_options.key;
    int pad = rr_options.row == 4 ? rr_options.rpad : rr_options.pad;
    if (!rr_options.status[0] && (rr_options.row == 1 || rr_options.row == 3)) {
        for (int i = 0; i < 3; ++i) if (keys[i]) {
            size_t used = strlen(combo);
            snprintf(combo + used, sizeof combo - used, "%s%s", used ? " + " : "", rr_keyboard_name((SDL_Scancode)keys[i]));
        }
    } else if (!rr_options.status[0] && (rr_options.row == 2 || rr_options.row == 4)) {
        for (int i = 0; i < SDL_CONTROLLER_BUTTON_MAX; ++i) if (pad & (1u << i)) {
            size_t used = strlen(combo);
            const char *name = SDL_GameControllerGetStringForButton((SDL_GameControllerButton)i);
            snprintf(combo + used, sizeof combo - used, "%s%s", used ? " + " : "", name ? name : "?");
        }
    }
    RR_OPT_TEXT(14, 162, rr_options.status[0] ? rr_options.status : combo);
    RR_OPT_TEXT(14, 174, "Esc / B: close");
#undef RR_OPT_TEXT
    rr_menu_end(renderer);
}
#endif
