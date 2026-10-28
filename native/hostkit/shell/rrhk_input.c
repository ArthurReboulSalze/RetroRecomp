/* Bindings, preferences file, controllers and the pad word of each player.
 * One implementation for every machine; the machine only lists its actions. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdlib.h>
#include <string.h>
#include "platform_io.h"
#include "retro_keyboard.h"
#include "autofire.h"
#include "display_settings.h"
#include "runtime_i18n.h"
#include "hostkit/hostkit_internal.h"

RrhkUi rrhk;
static RrAutofire fire_state[RRHK_MAX_PLAYERS][RRHK_MAX_ACTIONS];

RrhkUi *rrhk_ui(void) { return &rrhk; }
const char *rrhk_tr(const char *english, const char *french) {
    return rr_translate(rrhk.language, english, french);
}

/* A machine reset or load forgets which buttons were already held down. */
void rrhk_autofire_reset(void) { memset(fire_state, 0, sizeof fire_state); }

void rrhk_bind(const RrhkMachine *machine) {
    rrhk.machine = machine;
    memset(rrhk.keys, 0, sizeof rrhk.keys);
    memset(rrhk.buttons, 0, sizeof rrhk.buttons);
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) for (int a = 0; a < machine->action_count; ++a) {
        rrhk.keys[p][a] = machine->actions[a].key[p];
        rrhk.buttons[p][a] = machine->actions[a].pad[p];
    }
    swprintf(rrhk.video_section, 64, L"%ls.Video", machine->ini_section);
    if (machine->pointer_section) swprintf(rrhk.pointer_section, 64, L"%ls", machine->pointer_section);
    else swprintf(rrhk.pointer_section, 64, L"%ls.Gun", machine->ini_section);
    rrhk.pointer_size = 3;
    rrhk.pointer_turbo = 1;
}

void rrhk_settings_path(void) {
    if (!rr_executable_directory(rrhk.data_dir, 32600)) { rrhk.ini_file[0] = 0; return; }
    rr_wide_copy(rrhk.ini_file, 32768, rrhk.data_dir);
    rr_wide_append(rrhk.data_dir, 32768, RR_SLASH_W L"datas");
    rr_wide_append(rrhk.ini_file, 32768, RR_SLASH_W L"datas" RR_SLASH_W L"Retro-Recomp.ini");
}

static void section(wchar_t *out, int p, bool pad) {
    swprintf(out, 64, L"%ls.%ls.Player%d", rrhk.machine->ini_section, pad ? L"Gamepad" : L"Keyboard", p + 1);
}

static void load_choice(int p);

void rrhk_load_bindings(void) {
    const RrhkMachine *m = rrhk.machine;
    /* Resolve letters after SDL video initialization, before loading physical
     * bindings saved by the user. W must mean W on AZERTY and QWERTY alike. */
    for (int a = 0; a < m->action_count; ++a)
        if (m->actions[a].letter) rrhk.keys[0][a] = rr_keyboard_letter(m->actions[a].letter, m->actions[a].key[0]);
    rrhk_settings_path();
    if (!rrhk.ini_file[0]) return;
    rr_display_load(rrhk.ini_file, rrhk.video_section, &rrhk.filter, &rrhk.fullscreen);
    if (m->settings_loaded) m->settings_loaded(&rrhk);
    wchar_t sec[64];
    for (int p = 0; p < m->players(); ++p) for (int mode = 0; mode < 2; ++mode) {
        section(sec, p, mode != 0);
        for (int a = 0; a < m->action_count; ++a) {
            int old = mode ? rrhk.buttons[p][a] : rrhk.keys[p][a];
            int value = rr_ini_int(sec, m->actions[a].ini_key, old, rrhk.ini_file);
            if (mode && value >= 0 && value < SDL_CONTROLLER_BUTTON_MAX) rrhk.buttons[p][a] = (SDL_GameControllerButton)value;
            if (!mode && value > 0 && value < SDL_NUM_SCANCODES) rrhk.keys[p][a] = (SDL_Scancode)value;
        }
    }
    for (int p = 0; p < m->players(); ++p) load_choice(p);
    wchar_t language[12];
    rr_ini_get(L"Interface", L"language", L"en", language, 12, rrhk.ini_file);
    rrhk.language = rr_language_from_wide(language); rr_language_set(rrhk.language);
    rrhk.autofire = rr_ini_int(L"Manettes", L"autofire", 0, rrhk.ini_file) != 0;
    rrhk.pointer_shape = rr_ini_int(rrhk.pointer_section, L"shape", 0, rrhk.ini_file) == 1;
    rrhk.pointer_size = rr_ini_int(rrhk.pointer_section, L"size", 3, rrhk.ini_file);
    if (rrhk.pointer_size < 1 || rrhk.pointer_size > (m->pointer_max ? m->pointer_max : 12)) rrhk.pointer_size = 3;
    rrhk.pointer_color = rr_ini_int(rrhk.pointer_section, L"color", 0, rrhk.ini_file);
    if (rrhk.pointer_color < 0 || rrhk.pointer_color > 2) rrhk.pointer_color = 0;
    rrhk.pointer_turbo = rr_ini_int(rrhk.pointer_section, L"turbo", 1, rrhk.ini_file) != 0;
}

void rrhk_store_binding(void) {
    if (!rrhk.ini_file[0]) return;
    rr_mkdir(rrhk.data_dir);
    wchar_t sec[64], value[16];
    section(sec, rrhk.player, rrhk.gamepad_page != 0);
    swprintf(value, 16, L"%d", rrhk.gamepad_page ? rrhk.buttons[rrhk.player][rrhk.row] : rrhk.keys[rrhk.player][rrhk.row]);
    rr_ini_set(sec, rrhk.machine->actions[rrhk.row].ini_key, value, rrhk.ini_file);
}

/* Which gamepad each player uses (divergence 10, decided 28 October 2026). By default pads go to players in plug
 * order, the first free player (Automatic). A player may instead be pinned to one gamepad, by its SDL GUID, or set to
 * None (keyboard only). The choice is kept in the game's preferences, in the player's gamepad section:
 *   device=auto | none | <SDL joystick GUID string>      name=<name of the pinned gamepad, for display>
 * A pinned gamepad that is not plugged in leaves its player without a pad (never another pad) until it comes back;
 * automatic players never take a pad pinned to another player. Two identical pads share a GUID: the first unclaimed
 * one matches. */
enum { PAD_AUTO, PAD_NONE, PAD_PINNED };
static bool redeal;      /* a player went back to Automatic: the automatic players are dealt their pads again, as at start */
#define PAD_MAX 16
#define GUID_SIZE 40
#define CHOICE_TEXT (GUID_SIZE + 64)
typedef struct { int mode; char guid[GUID_SIZE]; char name[64]; } PadChoice;
static PadChoice choice[RRHK_MAX_PLAYERS];
typedef struct { int index; SDL_JoystickID id; char guid[GUID_SIZE]; char name[64]; int rank; } PadInfo;

static void plain_name(const char *source, char *out, size_t size) {
    size_t n = 0;
    if (!source) source = "";
    for (; *source && n + 1 < size; ++source) out[n++] = *source >= 32 && *source < 127 ? *source : '?';
    out[n] = 0;
}

static int list_pads(PadInfo *list) {
    int count = 0;
    for (int i = 0; i < SDL_NumJoysticks() && count < PAD_MAX; ++i) if (SDL_IsGameController(i)) {
        PadInfo *info = &list[count++];
        info->index = i; info->id = SDL_JoystickGetDeviceInstanceID(i); info->rank = 0;
        SDL_JoystickGetGUIDString(SDL_JoystickGetDeviceGUID(i), info->guid, GUID_SIZE);
        plain_name(SDL_GameControllerNameForIndex(i), info->name, sizeof info->name);
    }
    for (int i = 0; i < count; ++i) {
        int same = 0, before = 0;
        for (int j = 0; j < count; ++j) if (!strcmp(list[i].name, list[j].name)) { ++same; if (j < i) ++before; }
        list[i].rank = same > 1 ? before + 1 : 0;   /* numbered only when two pads share a name */
    }
    return count;
}

static SDL_JoystickID pad_id(SDL_GameController *pad) { return SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pad)); }
static int pad_position(const PadInfo *list, int count, SDL_GameController *pad) {
    if (!pad || !SDL_GameControllerGetAttached(pad)) return -1;
    for (int j = 0; j < count; ++j) if (list[j].id == pad_id(pad)) return j;
    return -1;
}

void rrhk_open_pads(void) {
    const RrhkMachine *m = rrhk.machine;
    PadInfo list[PAD_MAX];
    int count = list_pads(list), players = m->players();
    int target[RRHK_MAX_PLAYERS];     /* position in the list, -1: no pad */
    bool taken[PAD_MAX] = {false};
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) target[p] = -1;
    /* Every player first keeps the pad it holds: a pinned player when the pad still matches its GUID, an automatic
     * player unless another player claimed it. Only then does a pinned player without its pad look for an unclaimed
     * one of that GUID, so unplugging one of two identical pinned pads never moves the other to another player, and
     * a pinned pad that is missing is never replaced by an identical pad another player is using. */
    for (int p = 0; p < players; ++p) if (choice[p].mode == PAD_PINNED) {
        int held = pad_position(list, count, rrhk.pads[p]);
        if (held >= 0 && !taken[held] && !strcmp(list[held].guid, choice[p].guid)) { target[p] = held; taken[held] = true; }
    }
    for (int p = 0; p < players && !redeal; ++p) if (choice[p].mode == PAD_AUTO) {
        int held = pad_position(list, count, rrhk.pads[p]);
        if (held >= 0 && !taken[held]) { target[p] = held; taken[held] = true; }
    }
    redeal = false;
    for (int p = 0; p < players; ++p) if (choice[p].mode == PAD_PINNED && target[p] < 0) {
        for (int j = 0; j < count && target[p] < 0; ++j) if (!taken[j] && !strcmp(list[j].guid, choice[p].guid)) target[p] = j;
        if (target[p] >= 0) taken[target[p]] = true;
    }
    /* The pads that are left go to the first free automatic player, in plug order. */
    for (int j = 0; j < count; ++j) if (!taken[j])
        for (int p = 0; p < players; ++p) if (choice[p].mode == PAD_AUTO && target[p] < 0) { target[p] = j; taken[j] = true; break; }
    SDL_GameController *old[RRHK_MAX_PLAYERS], *now[RRHK_MAX_PLAYERS];
    memcpy(old, rrhk.pads, sizeof old);
    memset(now, 0, sizeof now);
    for (int p = 0; p < players; ++p) if (target[p] >= 0) {
        for (int q = 0; q < m->table_players && !now[p]; ++q)
            if (old[q] && SDL_GameControllerGetAttached(old[q]) && pad_id(old[q]) == list[target[p]].id) now[p] = old[q];
        if (!now[p]) now[p] = SDL_GameControllerOpen(list[target[p]].index);
    }
    for (int q = 0; q < m->table_players; ++q) if (old[q]) {
        bool kept = false;
        for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) if (now[p] == old[q]) kept = true;
        if (!kept) SDL_GameControllerClose(old[q]);
    }
    memcpy(rrhk.pads, now, sizeof now);
}

void rrhk_close_pads(void) {
    for (int p = 0; p < rrhk.machine->table_players; ++p) if (rrhk.pads[p]) SDL_GameControllerClose(rrhk.pads[p]);
}

/* Only a change made on the Gamepad row is written; the default (automatic) leaves the file as it was. */
static void store_choice(int p) {
    if (!rrhk.ini_file[0]) return;
    rr_mkdir(rrhk.data_dir);
    wchar_t sec[64], wide[CHOICE_TEXT];
    section(sec, p, true);
    const char *device = choice[p].mode == PAD_AUTO ? "auto" : choice[p].mode == PAD_NONE ? "none" : choice[p].guid;
    if (rr_from_utf8(device, wide, CHOICE_TEXT)) rr_ini_set(sec, L"device", wide, rrhk.ini_file);
    if (rr_from_utf8(choice[p].mode == PAD_PINNED ? choice[p].name : "", wide, CHOICE_TEXT)) rr_ini_set(sec, L"name", wide, rrhk.ini_file);
}

static void load_choice(int p) {
    wchar_t sec[64], wide[CHOICE_TEXT];
    char text[CHOICE_TEXT * 3];
    PadChoice *c = &choice[p];
    memset(c, 0, sizeof *c);
    section(sec, p, true);
    rr_ini_get(sec, L"device", L"auto", wide, CHOICE_TEXT, rrhk.ini_file);
    if (!rr_to_utf8(wide, text, sizeof text)) return;
    if (!strcmp(text, "none")) c->mode = PAD_NONE;
    else if (strlen(text) == 32 && strspn(text, "0123456789abcdefABCDEF") == 32) {
        c->mode = PAD_PINNED;
        for (int i = 0; i < 32; ++i) c->guid[i] = (char)(text[i] >= 'A' && text[i] <= 'F' ? text[i] + 32 : text[i]);
        rr_ini_get(sec, L"name", L"", wide, CHOICE_TEXT, rrhk.ini_file);
        if (!rr_to_utf8(wide, text, sizeof text)) text[0] = 0;
        plain_name(text, c->name, sizeof c->name);
    }
}

/* Pin the player to the gamepad at `position` of the list. It is taken from the player that holds it, who falls back to automatic. */
static void pin_pad(int p, const PadInfo *info) {
    SDL_GameController *chosen = NULL;
    for (int q = 0; q < rrhk.machine->table_players; ++q)
        if (rrhk.pads[q] && SDL_GameControllerGetAttached(rrhk.pads[q]) && pad_id(rrhk.pads[q]) == info->id) {
            chosen = rrhk.pads[q];
            if (q == p) continue;
            rrhk.pads[q] = NULL;
            if (choice[q].mode == PAD_PINNED) { memset(&choice[q], 0, sizeof choice[q]); store_choice(q); }
        }
    if (!chosen) chosen = SDL_GameControllerOpen(info->index);
    if (rrhk.pads[p] && rrhk.pads[p] != chosen) SDL_GameControllerClose(rrhk.pads[p]);
    rrhk.pads[p] = chosen;
    choice[p].mode = PAD_PINNED;
    snprintf(choice[p].guid, sizeof choice[p].guid, "%s", info->guid);
    snprintf(choice[p].name, sizeof choice[p].name, "%s", info->name);
}

/* Enter on the Gamepad row: Automatic, each connected gamepad in turn, None, Automatic... */
void rrhk_pad_next(int p) {
    PadInfo list[PAD_MAX];
    int count = list_pads(list), held = pad_position(list, count, rrhk.pads[p]);
    PadChoice *c = &choice[p];
    if (c->mode == PAD_NONE) memset(c, 0, sizeof *c);
    else if (c->mode == PAD_AUTO) { if (count) pin_pad(p, &list[0]); else c->mode = PAD_NONE; }
    else if (held >= 0 && held + 1 < count) pin_pad(p, &list[held + 1]);
    else if (held >= 0) { memset(c, 0, sizeof *c); c->mode = PAD_NONE; }
    /* A pinned gamepad that is not plugged in: the cycle goes on with the connected pads, then None. */
    else if (count) pin_pad(p, &list[0]);
    else { memset(c, 0, sizeof *c); c->mode = PAD_NONE; }
    store_choice(p);
    redeal = c->mode == PAD_AUTO;
    rrhk_open_pads();
}

void rrhk_pad_automatic(int p) {
    memset(&choice[p], 0, sizeof choice[p]);
    store_choice(p);
    redeal = true;
    rrhk_open_pads();
}

/* The value of the Gamepad row: Automatic (with the pad it gives), a pinned gamepad, a pinned gamepad that is missing, or None. */
void rrhk_pad_value(char *out, size_t size, int p) {
    PadInfo list[PAD_MAX];
    int count = list_pads(list), held = pad_position(list, count, rrhk.pads[p]);
    char name[80];
    name[0] = 0;
    if (held >= 0) {
        if (list[held].rank) snprintf(name, sizeof name, "%s #%d", list[held].name, list[held].rank);
        else snprintf(name, sizeof name, "%s", list[held].name);
    }
    if (choice[p].mode == PAD_NONE) snprintf(out, size, "%s", rr_tr("None"));
    else if (choice[p].mode == PAD_AUTO) {
        if (name[0]) snprintf(out, size, "%s (%s)", rr_tr("Automatic"), name);
        else snprintf(out, size, "%s", rr_tr("Automatic"));
    } else if (name[0]) snprintf(out, size, "%s", name);
    else snprintf(out, size, rr_tr("%s (disconnected)"), choice[p].name[0] ? choice[p].name : rr_tr("Gamepad"));
}

uint16_t rrhk_pad_word(int p, uint64_t frame) {
    const RrhkMachine *m = rrhk.machine;
    const Uint8 *state = SDL_GetKeyboardState(NULL);
    uint16_t value = 0;
    for (int a = 0; a < m->action_count; ++a) {
        const RrhkAction *action = &m->actions[a];
        /* Enter is Start and either Shift is Select/Coin (retro_keyboard.h). */
        bool down = rr_keyboard_held(state, rrhk.keys[p][a], &rrhk.keys[0][0], (int)(sizeof rrhk.keys / sizeof rrhk.keys[0][0])) ||
            (rrhk.pads[p] && SDL_GameControllerGetButton(rrhk.pads[p], rrhk.buttons[p][a]));
        if (action->group == RRHK_FACE) down = rr_autofire(&fire_state[p][a], down, rrhk.autofire != 0, frame);
        if (down) value |= action->bit;
    }
    const uint16_t left = m->actions[m->left].bit, right = m->actions[m->right].bit;
    const uint16_t up = m->actions[m->up].bit, down_bit = m->actions[m->down].bit;
    if (rrhk.pads[p]) {
        Sint16 x = SDL_GameControllerGetAxis(rrhk.pads[p], SDL_CONTROLLER_AXIS_LEFTX);
        Sint16 y = SDL_GameControllerGetAxis(rrhk.pads[p], SDL_CONTROLLER_AXIS_LEFTY);
        if (x < -16000) value |= left; else if (x > 16000) value |= right;
        if (y < -16000) value |= up; else if (y > 16000) value |= down_bit;
    }
    if ((value & (left | right)) == (left | right)) value &= ~(left | right);
    if ((value & (up | down_bit)) == (up | down_bit)) value &= ~(up | down_bit);
    return value;
}
