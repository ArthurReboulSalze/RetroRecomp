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
/* The host's combinations, one table (1.7.5): Quit and Restart (keys or buttons), Quick save and Quick load (buttons only, F8 and
 * F9 stay their keys; unassigned by default, so that no game saves or loads by accident). Each fires after its hold: Quit while
 * it is held, the others once per hold. The quick ones' holds are the owner's choice (14 November 2026): a stray save destroys
 * the one quick slot as surely as a stray load, so both need a hold, and the load the longer one. */
#define RR_COMBO_ROWS 4
enum { RR_COMBO_QUIT, RR_COMBO_RESTART, RR_COMBO_SAVE, RR_COMBO_LOAD };
#define RR_COMBO_SAVE_MS 500
#define RR_COMBO_LOAD_MS 1000
typedef struct { int key[3], pad, held, fired; Uint64 hold; } RrCombo;
static const struct {
    const wchar_t *keys[3];      /* the keyboard entries; NULL: the row's key is fixed (fixed_key) */
    const wchar_t *pad;          /* the gamepad entry */
    unsigned pad_default;        /* a missing gamepad entry; a stored 0 is an explicitly cleared one */
    SDL_Scancode fixed_key;
    Uint64 hold_ms;
    const char *label, *hint;
} rr_combo_info[RR_COMBO_ROWS] = {
    {{L"quit_key0", L"quit_key1", L"quit_key2"}, L"quit_pad", RR_OPTIONS_QUIT_PAD, SDL_SCANCODE_UNKNOWN, 1000,
     "Quit", "Hold quit combo for 1 second"},
    {{L"restart_key0", L"restart_key1", L"restart_key2"}, L"restart_pad", RR_OPTIONS_RESTART_PAD, SDL_SCANCODE_UNKNOWN, 1000,
     "Restart", "Hold restart combo for 1 second"},
    {{NULL, NULL, NULL}, L"quick_save_pad", 0, SDL_SCANCODE_F8, RR_COMBO_SAVE_MS, "Quick save", "Hold quick save combo"},
    {{NULL, NULL, NULL}, L"quick_load_pad", 0, SDL_SCANCODE_F9, RR_COMBO_LOAD_MS, "Quick load", "Hold quick load combo"}};
static struct {
    wchar_t file[32768], dir[32768], section[64];
    SDL_atomic_t audio_mode;
    SDL_atomic_t audio_epoch;
    /* Sound controls of every console (docs/HOST_KIT.md, decision D12): the volume in percent (0..200), the mute, the
     * speed hold (the speed is not 100%: the sound is dropped by the producers and silent here) and the output device
     * asked for ("" is the system default). The device name is written by the main thread only; the serial moves when
     * it changes. The three numbers are read by the audio callback. */
    SDL_atomic_t volume, muted, speed_held, device_serial;
    char device[256];
    RrCombo combo[RR_COMBO_ROWS];
    int row, capture, armed, pending_key[3], count;
    Uint32 pending_pad;
    SDL_JoystickID capture_pad;
    /* When set by the host, a gamepad combination is captured from this pad only (the selected player's, as the
     * button bindings are: docs/HOST_KIT.md, divergence 3); rr_combo_start clears it, so other hosts take any pad. */
    Uint8 capture_guard;
    SDL_JoystickID capture_from;
    Uint8 down[SDL_NUM_SCANCODES];
    struct { SDL_JoystickID id; Uint32 mask; } pads[4];
    int suppressed, focused;
    int fkeys, fkeys_machine;
    char machine[16];
    char status[100];
    int notice;      /* 1.7.5: the status says why a binding was not taken; the host shows it (the control pages draw no status) */
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

static void rr_options_init(const wchar_t *console) {
    memset(&rr_options, 0, sizeof rr_options);
    memset(&rr_options_dsp, 0, sizeof rr_options_dsp);
    rr_options_audio_epoch = 0;
    SDL_AtomicSet(&rr_options.volume, 100);
    rr_options.focused = 1;
    for (int c = 0; c < RR_COMBO_ROWS; ++c) rr_options.combo[c].pad = (int)rr_combo_info[c].pad_default;
    for (int i = 0; i < 4; ++i) rr_options.pads[i].id = -1;
    if (!rr_executable_directory(rr_options.dir, 32600)) return;
    rr_wide_append(rr_options.dir, 32768, RR_SLASH_W L"datas");
    rr_wide_copy(rr_options.file, 32768, rr_options.dir);
    rr_wide_append(rr_options.file, 32768, RR_SLASH_W L"Retro-Recomp.ini");
    swprintf(rr_options.section, 64, L"%ls.Options", console);
    int mode = rr_ini_int(rr_options.section, L"audio_filter", 0, rr_options.file);
    SDL_AtomicSet(&rr_options.audio_mode, mode >= 0 && mode <= 2 ? mode : 0);
    for (int c = 0; c < RR_COMBO_ROWS; ++c) {
        if (rr_combo_info[c].keys[0]) rr_options_load_keys(rr_combo_info[c].keys, rr_options.combo[c].key);
        rr_options.combo[c].pad = rr_options_load_pad(rr_combo_info[c].pad, rr_combo_info[c].pad_default);
    }
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

/* ---- The sound controls of every console: volume, mute, output device (decision D12) ----
 * They are kept in `[<Console>.Options]` as audio_volume (0..200), audio_muted (0 or 1) and audio_device (the name SDL gives
 * the device, empty for the system default). Every console's output goes through rr_options_audio below. */
#define RR_VOLUME_MAX 200
#define RR_VOLUME_STEP 10
#define RR_DEVICE_MAX 32     /* the devices of the cycle; SDL's list is cut there */
static bool rr_options_store_text(const wchar_t *entry, const char *utf8) {
    wchar_t text[300];
    bool ok = rr_from_utf8(utf8, text, 300) && rr_options.file[0] && rr_mkdir(rr_options.dir) &&
        rr_ini_set(rr_options.section, entry, text, rr_options.file);
    snprintf(rr_options.status, sizeof rr_options.status, "%s", rr_tr(ok ? "Settings saved" : "Config unavailable"));
    return ok;
}
/* The values read at start (by the host, from the preferences or from the machine's former file). */
static void rr_sound_load(int volume, int muted, const char *device) {
    SDL_AtomicSet(&rr_options.volume, volume < 0 ? 0 : volume > RR_VOLUME_MAX ? RR_VOLUME_MAX : volume);
    SDL_AtomicSet(&rr_options.muted, muted != 0);
    snprintf(rr_options.device, sizeof rr_options.device, "%s", device ? device : "");
}
static int rr_sound_volume(void) {return SDL_AtomicGet(&rr_options.volume);}
static bool rr_sound_muted(void) {return SDL_AtomicGet(&rr_options.muted) != 0;}
static void rr_sound_set_volume(int volume) {
    volume = volume < 0 ? 0 : volume > RR_VOLUME_MAX ? RR_VOLUME_MAX : volume;
    SDL_AtomicSet(&rr_options.volume, volume);      /* applied first: a folder that cannot be written only loses the choice at the next start */
    rr_options_store(L"audio_volume", volume);
}
static bool rr_sound_toggle_mute(void) {
    const int muted = !rr_sound_muted();
    SDL_AtomicSet(&rr_options.muted, muted);
    rr_options_store(L"audio_muted", muted);
    return rr_sound_muted();
}
/* The output devices SDL lists now (none before the audio subsystem is started), at most RR_DEVICE_MAX. */
static int rr_sound_devices(char names[][256]) {
    if (!(SDL_WasInit(SDL_INIT_AUDIO) & SDL_INIT_AUDIO)) return 0;
    int total = SDL_GetNumAudioDevices(0), count = 0;
    for (int i = 0; i < total && count < RR_DEVICE_MAX; ++i) {
        const char *name = SDL_GetAudioDeviceName(i, 0);
        if (name && name[0]) snprintf(names[count++], 256, "%s", name);
    }
    return count;
}
static const char *rr_sound_device(void) {return rr_options.device;}
static unsigned rr_sound_device_serial(void) {return (unsigned)SDL_AtomicGet(&rr_options.device_serial);}
static void rr_sound_set_device(const char *name) {
    snprintf(rr_options.device, sizeof rr_options.device, "%s", name);
    SDL_AtomicAdd(&rr_options.device_serial, 1);
    rr_options_store_text(L"audio_device", name);   /* says "Config unavailable" when it cannot be kept */
}
/* The next (or previous) choice of the cycle: the system default, then each device SDL lists. */
static void rr_sound_cycle_device(int step) {
    char names[RR_DEVICE_MAX][256];
    const int count = rr_sound_devices(names);
    int position = 0;
    for (int i = 0; i < count && rr_options.device[0]; ++i) if (!strcmp(names[i], rr_options.device)) position = i + 1;
    position = ((position + step) % (count + 1) + count + 1) % (count + 1);
    rr_sound_set_device(position ? names[position - 1] : "");
}
/* The name on the options page (the menu drops the accents itself). */
static void rr_sound_device_label(char *out, size_t size) {
    const char *name = rr_options.device[0] ? rr_options.device : rr_tr("System default");
    size_t n = 0;
    for (; *name && n + 1 < size; ++name) out[n++] = (unsigned char)*name >= 32 ? *name : '?';
    out[n] = 0;
}

/* The volume of the host sound, in percent: 100 leaves the samples as they are (byte for byte), more or less scales them
 * and clamps, 0 is silence. A multiplication in integers for 16-bit samples, in floating point for the device format F32. */
static void rr_audio_gain(void *pcm, unsigned frames, int channels, int floating, int volume) {
    const unsigned count = frames * (unsigned)channels;
    if (floating) {
        const float gain = volume / 100.0f;
        for (unsigned i = 0; i < count; ++i) ((float *)pcm)[i] = SDL_clamp(((float *)pcm)[i] * gain, -1.0f, 1.0f);
    } else {
        for (unsigned i = 0; i < count; ++i)
            ((int16_t *)pcm)[i] = (int16_t)SDL_clamp((int32_t)((int16_t *)pcm)[i] * volume / 100, -32768, 32767);
    }
}

/* Called only by the PCM consumer. The mode, the volume, the mute and the hold are the cross-thread fields: the sound
 * stage runs on every console's output, before the audio filter (the order of the former Game Boy callback). Silence
 * resets the filter, which starts again from the first sample that follows. */
static void rr_options_audio(void *pcm, unsigned frames, int channels, int floating, int rate) {
    int epoch = SDL_AtomicGet(&rr_options.audio_epoch);
    if (epoch != rr_options_audio_epoch) {rr_options_dsp.ready = 0; rr_options_audio_epoch = epoch;}
    const int volume = SDL_AtomicGet(&rr_options.volume);
    if (volume <= 0 || SDL_AtomicGet(&rr_options.muted) || SDL_AtomicGet(&rr_options.speed_held)) {
        memset(pcm, 0, (size_t)frames * (size_t)channels * (floating ? sizeof(float) : sizeof(int16_t)));
        rr_options_dsp.ready = 0;
        return;
    }
    if (volume != 100) rr_audio_gain(pcm, frames, channels, floating, volume);
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
    for (int i = 0; i < 3; ++i)
        if (key && (rr_options.combo[RR_COMBO_QUIT].key[i] == key || rr_options.combo[RR_COMBO_RESTART].key[i] == key)) return true;
    return button >= 0 && button < SDL_CONTROLLER_BUTTON_MAX && (rr_options.combo[RR_COMBO_QUIT].pad & (1u << button)) != 0;
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
        if (rr_options.capture && rr_options.capture % 2 == 0 && rr_options.capture_pad == e->cdevice.which) rr_options.capture = 0;
        for (int i = 0; i < 4; ++i) if (rr_options.pads[i].id == e->cdevice.which) {
            rr_options.pads[i].id = -1; rr_options.pads[i].mask = 0;
        }
    } else if (e->type == SDL_WINDOWEVENT && e->window.event == SDL_WINDOWEVENT_FOCUS_LOST) {
        rr_options.capture = 0;
        rr_options.focused = 0; rr_options.suppressed = 1;
        memset(rr_options.down, 0, sizeof rr_options.down);
        for (int i = 0; i < 4; ++i) rr_options.pads[i].mask = 0;
        for (int c = 0; c < RR_COMBO_ROWS; ++c) rr_options.combo[c].held = 0;
    } else if (e->type == SDL_WINDOWEVENT && e->window.event == SDL_WINDOWEVENT_FOCUS_GAINED) {
        rr_options.focused = 1;
    }
}

/* Capture ids: 2 * index + 1 with the keyboard, + 1 more with a gamepad (quit 1/2, restart 3/4, quick save 5/6, quick load 7/8).
 * A capture that equals another combination of the same kind is refused and says which: one hold must never do two things. */
static int rr_combo_used_by(int index, bool gamepad, const int *keys, Uint32 pad) {
    for (int c = 0; c < RR_COMBO_ROWS; ++c) {
        if (c == index) continue;
        if (gamepad) { if (rr_options.combo[c].pad && (Uint32)rr_options.combo[c].pad == pad) return c; continue; }
        if (!rr_combo_info[c].keys[0] || !rr_options.combo[c].key[0]) continue;
        int same = 0, mine = 0, theirs = 0;
        for (int i = 0; i < 3; ++i) {
            if (keys[i]) ++mine;
            if (rr_options.combo[c].key[i]) ++theirs;
            for (int j = 0; j < 3; ++j) if (keys[i] && keys[i] == rr_options.combo[c].key[j]) ++same;
        }
        if (same == mine && mine == theirs) return c;
    }
    return -1;
}
static void rr_options_capture_done(void) {
    const int index = (rr_options.capture - 1) / 2;
    const bool gamepad = rr_options.capture % 2 == 0;
    RrCombo *combo = &rr_options.combo[index];
    const int used = rr_combo_used_by(index, gamepad, rr_options.pending_key, rr_options.pending_pad);
    if ((gamepad ? rr_options.pending_pad != 0 : rr_options.count != 0) && used >= 0) {
        snprintf(rr_options.status, sizeof rr_options.status, rr_tr("Already used by %s"), rr_tr(rr_combo_info[used].label));
        rr_options.notice = 1;
    } else if (!gamepad && rr_options.count) {
        for (int i = 0; i < 3; ++i)
            if (rr_options_store(rr_combo_info[index].keys[i], rr_options.pending_key[i])) combo->key[i] = rr_options.pending_key[i];
    } else if (gamepad && rr_options.pending_pad) {
        if (rr_options_store(rr_combo_info[index].pad, (int)rr_options.pending_pad)) combo->pad = (int)rr_options.pending_pad;
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

/* The combinations sit below player 1's controls: keyboard ones on the keyboard page, controller ones on the gamepad page. The
 * quick ones show their fixed key on the keyboard page, which Enter does not change. */
static int rr_combo_id(int index, bool gamepad) {return 2 * index + 1 + (gamepad ? 1 : 0);}
static bool rr_combo_fixed(int index, bool gamepad) {return !gamepad && !rr_combo_info[index].keys[0];}
static const char *rr_combo_label(int index) {return rr_tr(rr_combo_info[index].label);}
static void rr_combo_start(int index, bool gamepad) {
    if (rr_combo_fixed(index, gamepad)) {
        snprintf(rr_options.status, sizeof rr_options.status, "%s", rr_tr("F8 and F9: fixed keys"));
        rr_options.notice = 1;
        return;
    }
    rr_options.capture = rr_combo_id(index, gamepad);
    rr_options.armed = 0; rr_options.count = 0; rr_options.pending_pad = 0; rr_options.capture_guard = 0;
    memset(rr_options.pending_key, 0, sizeof rr_options.pending_key);
    rr_options.status[0] = 0; rr_options.suppressed = 1;
}
static void rr_combo_clear(int index, bool gamepad) {
    RrCombo *combo = &rr_options.combo[index];
    if (rr_combo_fixed(index, gamepad)) return;
    if (!gamepad) {
        const wchar_t *const *entries = rr_combo_info[index].keys;
        if (rr_options_store(entries[0], 0) && rr_options_store(entries[1], 0) && rr_options_store(entries[2], 0))
            memset(combo->key, 0, sizeof combo->key);
    } else if (rr_options_store(rr_combo_info[index].pad, 0)) combo->pad = 0;
}
/* The combination has keys or buttons (a fixed key counts). */
static bool rr_combo_set(int index, bool gamepad) {
    if (rr_combo_fixed(index, gamepad)) return true;
    return gamepad ? rr_options.combo[index].pad != 0 : rr_options.combo[index].key[0] != 0;
}
/* "Ctrl + Q", "Start + Back", "Unassigned" or the capture prompt. */
static void rr_combo_value(char *out, size_t size, int index, bool gamepad) {
    out[0] = 0;
    if (rr_options.capture == rr_combo_id(index, gamepad)) {snprintf(out, size, "%s", rr_tr("Press combo, then release")); return;}
    if (rr_combo_fixed(index, gamepad)) {snprintf(out, size, "%s", rr_keyboard_name(rr_combo_info[index].fixed_key)); return;}
    if (!gamepad) {
        const int *keys = rr_options.combo[index].key;
        for (int i = 0; i < 3; ++i) if (keys[i]) {
            size_t used = strlen(out);
            snprintf(out + used, size - used, "%s%s", used ? " + " : "", rr_keyboard_name((SDL_Scancode)keys[i]));
        }
    } else {
        int pad = rr_options.combo[index].pad;
        for (int i = 0; i < SDL_CONTROLLER_BUTTON_MAX; ++i) if (pad & (1 << i)) {
            size_t used = strlen(out);
            snprintf(out + used, size - used, "%s%s", used ? " + " : "", rr_menu_pad_name(i));
        }
    }
    if (!out[0]) snprintf(out, size, "%s", rr_tr("Unassigned"));
}
/* Hint line for a selected combination row. */
static const char *rr_combo_hint(int index, bool gamepad) {
    if (rr_options.capture) return rr_tr("Esc: cancel binding");
    return rr_tr(rr_combo_fixed(index, gamepad) ? "F8 and F9: fixed keys" : rr_combo_info[index].hint);
}

/* The options page: the function-key settings, the audio filter and, on
 * computers, the function-key choice. Each host builds its rows. */
#define RR_ROW_AUDIO (-1)
#define RR_ROW_FKEYS (-2)
#define RR_ROW_VOLUME (-3)
#define RR_ROW_DEVICE (-4)
/* The rows hold their own text and no pointer, so a host can build them in a
 * function and return the struct by value (a pointer to text[i] would point
 * into the callee's frame once copied, which GCC does not hide as MSVC does). */
/* 1.7.5: each row may have its icon (retro_menu.h's RR_ICON_ROW_*, -1 none), drawn at its left; the host chooses them. */
typedef struct { char text[14][80]; int keys[14], icons[14], count; } RrOptionRows;
static void rr_option_row(RrOptionRows *d, int key, const char *format, const char *value) {
    if (d->count >= 14) return;
    snprintf(d->text[d->count], sizeof d->text[0], rr_tr(format), value);
    d->keys[d->count] = key; d->icons[d->count] = -1; ++d->count;
}
/* Rows every console shares, after its function-key rows. */
static void rr_option_shared_rows(RrOptionRows *d) {
    static const char *const modes[] = {"Off", "Light", "Soft"};
    char text[80];
    snprintf(text, sizeof text, "%s: %s", rr_tr("Audio filter"), rr_tr(modes[SDL_AtomicGet(&rr_options.audio_mode)]));
    rr_option_row(d, RR_ROW_AUDIO, "%s", text);
    char value[100];
    snprintf(value, sizeof value, "%d%%", rr_sound_volume());
    rr_option_row(d, RR_ROW_VOLUME, "Volume: %s", value);
    rr_option_row(d, SDL_SCANCODE_M, "M Sound: %s", rr_tr(rr_sound_muted() ? "OFF" : "ON"));
    rr_sound_device_label(value, sizeof value);
    rr_option_row(d, RR_ROW_DEVICE, "Output device: %s", value);
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
    static const char *const names[] = {"Windowed", "Pixel perfect", "Fit to screen", "Stretched"};
    return rr_tr(names[mode >= 0 && mode < 4 ? mode : 0]);
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
    if (d->keys[*row] == RR_ROW_VOLUME) {
        int volume = rr_sound_volume() + (back ? -RR_VOLUME_STEP : RR_VOLUME_STEP);
        rr_sound_set_volume(volume < 0 ? RR_VOLUME_MAX : volume > RR_VOLUME_MAX ? 0 : volume);
        return -1;
    }
    if (d->keys[*row] == RR_ROW_DEVICE) {rr_sound_cycle_device(back ? -1 : 1); return -1;}
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
    (void)page; (void)pages;      /* 1.7.4: the pages are tiles of the F2 menu, no longer squares in this head */
    rr_menu_header_compact(r, x, y, unit, rr_tr("Retro-Recomp - Options"), RR_ICON_OPTIONS_SMALL);
    if (rr_options.row >= d->count) rr_options.row = 0;
    for (int i = 0; i < d->count; ++i) {
        int line = RR_MENU_FIRST_LINE + i * RR_MENU_LINE;
        if (i == rr_options.row) rr_menu_box(r, x, y, unit, 12, line, 232, RR_MENU_LINE, RR_MENU_SELECT, 255);
        if (d->icons[i] >= 0) {     /* the icon, then the text, narrowed rather than past the row */
            rr_menu_icon(r, x, y, unit, 18, line, d->icons[i], false);
            rr_menu_text_fit(r, x, y, unit, 30, line, 212, d->text[i], RR_MENU_GOLD);
        } else rr_menu_text(r, x, y, unit, 16, line, d->text[i], RR_MENU_GOLD);
    }
    bool computer = d->count && d->keys[rr_options.row] == RR_ROW_FKEYS;
    if (rr_options.status[0]) rr_menu_text(r, x, y, unit, 14, RR_MENU_HINT_LINE, rr_options.status, RR_MENU_GOLD);
    else rr_menu_hints(r, x, y, unit, 14, RR_MENU_HINT_LINE, 228,
        rr_tr(computer ? "Ctrl+F1-F12: Retro-Recomp shortcuts" : "Enter / A: change"), RR_MENU_HINT);
    rr_menu_hints(r, x, y, unit, 14, RR_MENU_LAST_LINE, 228, rr_tr("Left/Right: page | Esc: close"), RR_MENU_HINT);
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
        if (rr_options.capture % 2 == 1 && key && rr_options.count < 3) {
            bool found = false;
            for (int i = 0; i < rr_options.count; ++i) if (rr_options.pending_key[i] == key) found = true;
            if (!found) rr_options.pending_key[rr_options.count++] = key;
        }
        if (rr_options.capture % 2 == 0 && button >= 0 && button < SDL_CONTROLLER_BUTTON_MAX
            && !(rr_options.capture_guard && e->cbutton.which != rr_options.capture_from)) {
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

/* Who holds a whole combination now: 1 the keyboard, 2 + n the n-th pad seen, 0 nobody. */
static int rr_combo_source(const RrCombo *combo) {
    bool down = combo->key[0] != 0;
    for (int i = 0; i < 3; ++i) if (combo->key[i] && !rr_options.down[combo->key[i]]) down = false;
    int source = down ? 1 : 0;
    for (int i = 0; i < 4; ++i)
        if (combo->pad && (rr_options.pads[i].mask & (Uint32)combo->pad) == (Uint32)combo->pad) source = i + 2;
    return source;
}

static bool rr_options_quit(int menu) {
    (void)menu;
    RrCombo *quit = &rr_options.combo[RR_COMBO_QUIT];
    if (!rr_options.focused || rr_options.capture || rr_options.suppressed) {
        quit->held = 0;
        if (!rr_options_any_down()) rr_options.suppressed = 0;
        return false;
    }
    const int source = rr_combo_source(quit);
    if (!source) {quit->held = 0; return false;}
    if (quit->held != source) {quit->held = source; quit->hold = SDL_GetTicks64();}
    return SDL_GetTicks64() - quit->hold >= rr_combo_info[RR_COMBO_QUIT].hold_ms;
}

/* Restart, Quick save, Quick load: each fires once after its hold of the whole combination, then re-arms only when it is
 * released. Hosts poll them every frame. */
static bool rr_options_fired(int index) {
    RrCombo *combo = &rr_options.combo[index];
    if (!rr_options.focused || rr_options.capture) {combo->held = 0; return false;}
    if (rr_options.suppressed && !rr_options_any_down()) rr_options.suppressed = 0;
    const int source = rr_combo_source(combo);
    if (!source) {combo->held = 0; return false;}
    /* A combination still held after a binding capture or a menu never fires. */
    if (rr_options.suppressed) {combo->held = source; combo->fired = 1; return false;}
    if (combo->held != source) {combo->held = source; combo->hold = SDL_GetTicks64(); combo->fired = 0;}
    if (combo->fired || SDL_GetTicks64() - combo->hold < rr_combo_info[index].hold_ms) return false;
    combo->fired = 1;
    return true;
}
static bool rr_options_restart(int menu) {(void)menu; return rr_options_fired(RR_COMBO_RESTART);}
static bool rr_options_quick_save(int menu) {(void)menu; return rr_options_fired(RR_COMBO_SAVE);}
static bool rr_options_quick_load(int menu) {(void)menu; return rr_options_fired(RR_COMBO_LOAD);}
#endif
