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

/* Default keys of players 3 and 4 when the adapter lists none for them (a board with more players than the two keyboard layouts
 * of player 1 and 2): free physical keys, the same letters on QWERTY and AZERTY, clear of player 1's letters (W X C A S D V Q E
 * and their AZERTY places Z and Q), player 2's numeric keypad and the kit's keys (function keys, Esc, Enter, Shift, Tab, `, M,
 * P, the arrows). Directions, the first three buttons (FACE, in table order), Start and the button player 1 has on Shift (Coin,
 * Select, Mode); the arcade convention puts Start 3-4 on 3 and 4 and their coins on 7 and 8. F2 binds the rest. */
enum { EXTRA_BUTTONS = 3 };
static const struct { SDL_Scancode up, down, left, right, button[EXTRA_BUTTONS], start, coin; } extra_keys[RRHK_MAX_PLAYERS - 2] = {
    {SDL_SCANCODE_T, SDL_SCANCODE_G, SDL_SCANCODE_F, SDL_SCANCODE_H, {SDL_SCANCODE_R, SDL_SCANCODE_Y, SDL_SCANCODE_B}, SDL_SCANCODE_3, SDL_SCANCODE_7},
    {SDL_SCANCODE_I, SDL_SCANCODE_K, SDL_SCANCODE_J, SDL_SCANCODE_L, {SDL_SCANCODE_U, SDL_SCANCODE_O, SDL_SCANCODE_N}, SDL_SCANCODE_4, SDL_SCANCODE_8}};

static bool kit_key[RRHK_MAX_PLAYERS][RRHK_MAX_ACTIONS];   /* the key is one of these defaults, not the adapter's or the player's */

static bool key_listed(SDL_Scancode key) {
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) for (int a = 0; a < RRHK_MAX_ACTIONS; ++a) if (rrhk.keys[p][a] == key) return true;
    return false;
}

static void extra_player_keys(const RrhkMachine *m, int p) {
    for (int a = 0; a < m->action_count; ++a) if (rrhk.keys[p][a] != SDL_SCANCODE_UNKNOWN) return;   /* the adapter chose */
    int face = 0;
    bool coin = false;
    for (int a = 0; a < m->action_count; ++a) {
        const RrhkAction *action = &m->actions[a];
        SDL_Scancode key = SDL_SCANCODE_UNKNOWN;
        if (a == m->up) key = extra_keys[p - 2].up;
        else if (a == m->down) key = extra_keys[p - 2].down;
        else if (a == m->left) key = extra_keys[p - 2].left;
        else if (a == m->right) key = extra_keys[p - 2].right;
        else if (a == m->start) key = extra_keys[p - 2].start;
        else if (action->group == RRHK_FACE) { if (face < EXTRA_BUTTONS) key = extra_keys[p - 2].button[face]; ++face; }
        /* Select, Coin or Mode: the action player 1 has on Shift (CONTROLS.md); a host action (bit 0) gets none. */
        else if (action->bit && !coin && rr_keyboard_shift_twin(action->key[0]) != SDL_SCANCODE_UNKNOWN) {
            key = extra_keys[p - 2].coin; coin = true;
        }
        if (key != SDL_SCANCODE_UNKNOWN && !key_listed(key)) { rrhk.keys[p][a] = key; kit_key[p][a] = true; }
    }
}

/* Once player 1's letters follow the layout and the saved bindings are read: a default of players 3 and 4 that another binding
 * now uses (a key saved before these defaults existed, a letter of player 1 on another layout) is dropped, never shared. */
static void drop_shadowed_extras(const RrhkMachine *m) {
    for (int p = 2; p < m->table_players && p < RRHK_MAX_PLAYERS; ++p) for (int a = 0; a < m->action_count; ++a) {
        if (!kit_key[p][a] || rrhk.keys[p][a] == SDL_SCANCODE_UNKNOWN) continue;
        for (int q = 0; q < m->table_players && q < RRHK_MAX_PLAYERS; ++q) for (int b = 0; b < m->action_count; ++b)
            if ((q != p || b != a) && !kit_key[q][b] && rrhk.keys[q][b] == rrhk.keys[p][a]) { rrhk.keys[p][a] = SDL_SCANCODE_UNKNOWN; kit_key[p][a] = false; }
    }
}

void rrhk_bind(const RrhkMachine *machine) {
    rrhk.machine = machine;
    memset(rrhk.keys, 0, sizeof rrhk.keys);
    memset(rrhk.buttons, 0, sizeof rrhk.buttons);
    memset(kit_key, 0, sizeof kit_key);
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) for (int a = 0; a < machine->action_count; ++a) {
        rrhk.keys[p][a] = machine->actions[a].key[p];
        rrhk.buttons[p][a] = machine->actions[a].pad[p];
    }
    /* Pads are laid out alike: a player whose buttons the adapter leaves empty (every one 0, SDL's A) gets player 1's, so raising
     * a machine's player count never maps all its actions to A. A column the adapter wrote (CPS-1's PADS) stays as it is. */
    for (int p = 1; p < RRHK_MAX_PLAYERS; ++p) {
        bool empty = machine->action_count > 1;
        for (int a = 0; a < machine->action_count; ++a) if (machine->actions[a].pad[p] != 0) empty = false;
        if (empty) for (int a = 0; a < machine->action_count; ++a) rrhk.buttons[p][a] = rrhk.buttons[0][a];
    }
    for (int p = 2; p < machine->table_players && p < RRHK_MAX_PLAYERS; ++p) extra_player_keys(machine, p);
    if (machine->video_section) swprintf(rrhk.video_section, 64, L"%ls", machine->video_section);
    else swprintf(rrhk.video_section, 64, L"%ls.Video", machine->ini_section);
    if (machine->pointer_section) swprintf(rrhk.pointer_section, 64, L"%ls", machine->pointer_section);
    else swprintf(rrhk.pointer_section, 64, L"%ls.Gun", machine->ini_section);
    rrhk.pointer_shape = rrhk.pointer_color = 0;
    rrhk.pointer_size = 3;
    rrhk.pointer_turbo = 1;
    rrhk.audio_volume = 100; rrhk.audio_muted = 0; rrhk.audio_device[0] = 0;
    rrhk.max_speed = rrhk.fast_hold = 0;
    /* 1.7.0: no dead zone (the raw sticks), every graphics option at its default (the reference setting), vibration on. */
    memset(rrhk.deadzone, 0, sizeof rrhk.deadzone);
    memset(rrhk.gfx, 0, sizeof rrhk.gfx);
    for (int i = 0; i < machine->gfx_option_count && i < RRHK_MAX_GFX_OPTIONS; ++i) rrhk.gfx[i] = machine->gfx_options[i].def;
    rrhk.gfx_row = 0;
    rrhk.rumble = 1;
}

/* The machine's former preferences file (RrhkMachine.legacy_ini), beside the executable. It is read only while datas holds
 * no Retro-Recomp.ini, and copied to it before the first write (the copy-before-first-write rule of the Master System host). */
static wchar_t legacy_file[32768];

void rrhk_settings_path(void) {
    legacy_file[0] = 0;
    if (!rr_executable_directory(rrhk.data_dir, 32600)) { rrhk.ini_file[0] = rrhk.read_file[0] = 0; return; }
    rr_wide_copy(rrhk.ini_file, 32768, rrhk.data_dir);
    if (rrhk.machine->legacy_ini) {
        rr_wide_copy(legacy_file, 32768, rrhk.data_dir);
        rr_wide_append(legacy_file, 32768, RR_SLASH_W);
        rr_wide_append(legacy_file, 32768, rrhk.machine->legacy_ini);
    }
    rr_wide_append(rrhk.data_dir, 32768, RR_SLASH_W L"datas");
    rr_wide_append(rrhk.ini_file, 32768, RR_SLASH_W L"datas" RR_SLASH_W L"Retro-Recomp.ini");
    rr_wide_copy(rrhk.read_file, 32768, legacy_file[0] && !rr_exists(rrhk.ini_file) && rr_exists(legacy_file) ? legacy_file : rrhk.ini_file);
}

/* Before any write: the folder exists, and a machine's former file becomes the file that is written. false: it cannot be written. */
bool rrhk_write_ready(void) {
    if (!rrhk.ini_file[0]) return false;
    if (!rr_mkdir(rrhk.data_dir) && !rr_exists(rrhk.data_dir)) return false;
    if (legacy_file[0] && !rr_exists(rrhk.ini_file) && rr_exists(legacy_file) && !rr_copy_new(legacy_file, rrhk.ini_file)) return false;
    return true;
}

static void section(wchar_t *out, int p, bool pad) {
    swprintf(out, 64, L"%ls.%ls.Player%d", rrhk.machine->ini_section, pad ? L"Gamepad" : L"Keyboard", p + 1);
}

/* Where a binding lives: the kit's section and the action's own name, or, for a machine that keeps the layout
 * of its earlier host (X68000, divergence 14 pending), [<ini_section>] and p<player>_key<index> / p<player>_pad<index>. */
static void binding_entry(wchar_t *sec, wchar_t *key, int p, int action, bool pad) {
    if (rrhk.machine->indexed_bindings) {
        swprintf(sec, 64, L"%ls", rrhk.machine->ini_section);
        swprintf(key, 48, pad ? L"p%d_pad%d" : L"p%d_key%d", p, action);
    } else {
        section(sec, p, pad);
        swprintf(key, 48, L"%ls", rrhk.machine->actions[action].ini_key);
    }
}

static void load_choice(int p);
static void load_capabilities(void);
static const wchar_t *autofire_section(void) { return rrhk.machine->autofire_section ? rrhk.machine->autofire_section : L"Manettes"; }

void rrhk_load_bindings(void) {
    const RrhkMachine *m = rrhk.machine;
    /* Resolve letters after SDL video initialization, before loading physical
     * bindings saved by the user. W must mean W on AZERTY and QWERTY alike. */
    for (int a = 0; a < m->action_count; ++a)
        if (m->actions[a].letter) rrhk.keys[0][a] = rr_keyboard_letter(m->actions[a].letter, m->actions[a].key[0]);
    rrhk_settings_path();
    if (!rrhk.ini_file[0]) { drop_shadowed_extras(m); return; }
    rr_display_load(rrhk.read_file, rrhk.video_section, &rrhk.filter, &rrhk.fullscreen);
    if (m->settings_loaded) m->settings_loaded(&rrhk);
    wchar_t sec[64], entry[48];
    /* A stored key 0 or button -1 is "no binding" on every machine: F2 writes it when a swap leaves an action without its key
     * (rrhk_assign), and the Delete of a clearable machine (X68000) writes it too. A missing entry keeps the default. */
    enum { MISSING = -1000000 };
    for (int p = 0; p < m->players(); ++p) for (int mode = 0; mode < 2; ++mode) {
        for (int a = 0; a < m->action_count; ++a) {
            binding_entry(sec, entry, p, a, mode != 0);
            const int value = rr_ini_int(sec, entry, MISSING, rrhk.read_file);
            if (mode && value >= -1 && value < (m->trigger_buttons ? RRHK_PAD_RIGHT_TRIGGER + 1 : SDL_CONTROLLER_BUTTON_MAX))
                rrhk.buttons[p][a] = (SDL_GameControllerButton)value;
            if (!mode && value >= 0 && value < SDL_NUM_SCANCODES) { rrhk.keys[p][a] = (SDL_Scancode)value; kit_key[p][a] = false; }
        }
    }
    drop_shadowed_extras(m);
    for (int p = 0; p < m->players(); ++p) load_choice(p);
    /* A machine that read its former preferences in settings_loaded (Game Boy: its own file) has set the language and the
     * autofire these start from; the kit's keys win when present. */
    wchar_t language[12];
    rr_ini_get(L"Interface", L"language", rr_language_wide(rrhk.language), language, 12, rrhk.read_file);
    rrhk.language = rr_language_from_wide(language); rr_language_set(rrhk.language);
    rrhk.autofire = rr_ini_int(autofire_section(), L"autofire", rrhk.autofire != 0, rrhk.read_file) != 0;
    /* A machine that read its former keys in settings_loaded has set the values these start from; the kit's keys win when present. */
    rrhk.pointer_shape = rr_ini_int(rrhk.pointer_section, L"shape", rrhk.pointer_shape, rrhk.read_file) == 1;
    rrhk.pointer_size = rr_ini_int(rrhk.pointer_section, L"size", rrhk.pointer_size, rrhk.read_file);
    if (rrhk.pointer_size < 1 || rrhk.pointer_size > (m->pointer_max ? m->pointer_max : 12)) rrhk.pointer_size = 3;
    rrhk.pointer_color = rr_ini_int(rrhk.pointer_section, L"color", rrhk.pointer_color, rrhk.read_file);
    if (rrhk.pointer_color < 0 || rrhk.pointer_color > 2) rrhk.pointer_color = 0;
    rrhk.pointer_turbo = rr_ini_int(rrhk.pointer_section, L"turbo", rrhk.pointer_turbo, rrhk.read_file) != 0;
    /* The sound controls (decision D12). A machine that read its former keys in settings_loaded (Game Boy) has set the values
     * these start from. They are kept in [<Console>.Options] beside the audio filter. */
    wchar_t options[64], fallback[300], device[300];
    char text[sizeof rrhk.audio_device];
    swprintf(options, 64, L"%ls.Options", m->ini_section);
    rrhk.audio_volume = rr_ini_int(options, L"audio_volume", rrhk.audio_volume, rrhk.read_file);
    if (rrhk.audio_volume < 0 || rrhk.audio_volume > 200) rrhk.audio_volume = 100;
    rrhk.audio_muted = rr_ini_int(options, L"audio_muted", rrhk.audio_muted, rrhk.read_file) != 0;
    if (!rr_from_utf8(rrhk.audio_device, fallback, 300)) fallback[0] = 0;
    rr_ini_get(options, L"audio_device", fallback, device, 300, rrhk.read_file);
    if (rr_to_utf8(device, text, sizeof text)) snprintf(rrhk.audio_device, sizeof rrhk.audio_device, "%s", text);
    load_capabilities();
}

static void store_entry(int p, int action, bool pad) {
    if (!rrhk_write_ready()) return;
    wchar_t sec[64], entry[48], value[16];
    binding_entry(sec, entry, p, action, pad);
    swprintf(value, 16, L"%d", pad ? rrhk.buttons[p][action] : rrhk.keys[p][action]);
    rr_ini_set(sec, entry, value, rrhk.ini_file);
}

void rrhk_store_binding(void) { store_entry(rrhk.player, rrhk.row, rrhk.gamepad_page != 0); }

/* F2 binds a key or a pad button to one action. The keyboard is shared: a key that already drives another action, of any player
 * in play, would make both act at once, so the two actions swap their keys (the other one gets the key this action had, perhaps
 * none). A pad belongs to its player: a button another action of the same player uses swaps the same way. Both are kept. */
void rrhk_assign(int p, int action, bool pad, int value) {
    const RrhkMachine *m = rrhk.machine;
    const int old = pad ? (int)rrhk.buttons[p][action] : (int)rrhk.keys[p][action];
    if (old != value) for (int q = 0; q < m->players(); ++q) for (int a = 0; a < m->action_count; ++a) {
        if ((pad && q != p) || (q == p && a == action)) continue;
        if (pad && rrhk.buttons[q][a] == (SDL_GameControllerButton)value) { rrhk.buttons[q][a] = (SDL_GameControllerButton)old; store_entry(q, a, true); }
        if (!pad && rrhk.keys[q][a] == (SDL_Scancode)value) { rrhk.keys[q][a] = (SDL_Scancode)old; kit_key[q][a] = false; store_entry(q, a, false); }
    }
    if (pad) rrhk.buttons[p][action] = (SDL_GameControllerButton)value;
    else { rrhk.keys[p][action] = (SDL_Scancode)value; kit_key[p][action] = false; }
    store_entry(p, action, pad);
}

/* Delete on a binding row (machines with clearable bindings): no key, no button. */
void rrhk_clear_binding(void) {
    if (rrhk.gamepad_page) rrhk.buttons[rrhk.player][rrhk.row] = (SDL_GameControllerButton)-1;
    else rrhk.keys[rrhk.player][rrhk.row] = SDL_SCANCODE_UNKNOWN;
    rrhk_store_binding();
}

const wchar_t *rrhk_autofire_section(void) { return autofire_section(); }

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

/* The slots are emptied too: a driven machine (SMS/GG) closes and opens the shell again on every restart, after
 * SDL_Quit, and the next rrhk_open_pads must never see a freed controller. */
void rrhk_close_pads(void) {
    for (int p = 0; p < rrhk.machine->table_players; ++p) if (rrhk.pads[p]) {
        SDL_GameControllerClose(rrhk.pads[p]);
        rrhk.pads[p] = NULL;
    }
}

/* Only a change made on the Gamepad row is written; the default (automatic) leaves the file as it was. */
static void store_choice(int p) {
    if (!rrhk_write_ready()) return;
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
    rr_ini_get(sec, L"device", L"auto", wide, CHOICE_TEXT, rrhk.read_file);
    if (!rr_to_utf8(wide, text, sizeof text)) return;
    if (!strcmp(text, "none")) c->mode = PAD_NONE;
    else if (strlen(text) == 32 && strspn(text, "0123456789abcdefABCDEF") == 32) {
        c->mode = PAD_PINNED;
        for (int i = 0; i < 32; ++i) c->guid[i] = (char)(text[i] >= 'A' && text[i] <= 'F' ? text[i] + 32 : text[i]);
        rr_ini_get(sec, L"name", L"", wide, CHOICE_TEXT, rrhk.read_file);
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

/* A pad button held; on a machine whose triggers are buttons (trigger_buttons), a trigger past the stick threshold (D1). */
static bool pad_held(SDL_GameController *pad, SDL_GameControllerButton button) {
    if (!pad || button < 0) return false;
    if (button < SDL_CONTROLLER_BUTTON_MAX) return SDL_GameControllerGetButton(pad, button) != 0;
    if (!rrhk.machine->trigger_buttons || button > RRHK_PAD_RIGHT_TRIGGER) return false;
    return SDL_GameControllerGetAxis(pad, button == RRHK_PAD_LEFT_TRIGGER ? SDL_CONTROLLER_AXIS_TRIGGERLEFT : SDL_CONTROLLER_AXIS_TRIGGERRIGHT) > 16000;
}

/* A trigger of player 1's pad (0 right, 1 left) bound to a control of a machine with trigger_buttons: no speed control then. */
bool rrhk_trigger_bound(int side) {
    const RrhkMachine *m = rrhk.machine;
    if (!m || !m->trigger_buttons) return false;
    const SDL_GameControllerButton trigger = side ? RRHK_PAD_LEFT_TRIGGER : RRHK_PAD_RIGHT_TRIGGER;
    for (int a = 0; a < m->action_count; ++a) if (rrhk.buttons[0][a] == trigger) return true;
    return false;
}

uint16_t rrhk_pad_word(int p, uint64_t frame) {
    const RrhkMachine *m = rrhk.machine;
    const Uint8 *state = SDL_GetKeyboardState(NULL);
    uint16_t value = 0;
    const bool keyboard = !m->keyboard_pad || m->keyboard_pad();
    for (int a = 0; a < m->action_count; ++a) {
        const RrhkAction *action = &m->actions[a];
        /* Enter is Start and either Shift is Select/Coin (retro_keyboard.h). */
        bool down = (keyboard && rr_keyboard_held(state, rrhk.keys[p][a], &rrhk.keys[0][0], (int)(sizeof rrhk.keys / sizeof rrhk.keys[0][0]))) ||
            pad_held(rrhk.pads[p], rrhk.buttons[p][a]) ||
            (m->action_held && m->action_held(p, a));
        if (action->group == RRHK_FACE) down = rr_autofire(&fire_state[p][a], down, rrhk.autofire != 0, frame);
        if (down) value |= action->bit;
    }
    const uint16_t left = m->actions[m->left].bit, right = m->actions[m->right].bit;
    const uint16_t up = m->actions[m->up].bit, down_bit = m->actions[m->down].bit;
    /* The left stick is the four directions (D1), unless the machine reads the sticks themselves (rrhk_pad_axes). */
    if (rrhk.pads[p] && !m->analog_sticks) {
        Sint16 x = SDL_GameControllerGetAxis(rrhk.pads[p], SDL_CONTROLLER_AXIS_LEFTX);
        Sint16 y = SDL_GameControllerGetAxis(rrhk.pads[p], SDL_CONTROLLER_AXIS_LEFTY);
        if (x < -16000) value |= left; else if (x > 16000) value |= right;
        if (y < -16000) value |= up; else if (y > 16000) value |= down_bit;
    }
    if ((value & (left | right)) == (left | right)) value &= ~(left | right);
    if ((value & (up | down_bit)) == (up | down_bit)) value &= ~(up | down_bit);
    return value;
}

/* ---- 1.7.0: sticks, graphics options, vibration (HOST_KIT.md section 2.4). Nothing below runs for a machine that declares
 * none of them: their preferences are not read, and the loop never calls these functions for it. ---- */

static void load_capabilities(void) {
    const RrhkMachine *m = rrhk.machine;
    wchar_t sec[64];
    /* [<Console>.Gamepad.PlayerN] deadzone=<percent>, 0..30; anything else is the default, 0 (the raw sticks). */
    if (m->analog_sticks) for (int p = 0; p < m->players() && p < RRHK_MAX_PLAYERS; ++p) {
        section(sec, p, true);
        const int value = rr_ini_int(sec, L"deadzone", 0, rrhk.read_file);
        rrhk.deadzone[p] = value >= 0 && value <= RRHK_DEADZONE_MAX ? value : 0;
    }
    /* [<Console>.Video] <ini_key>=<value index>; an unknown or out-of-range value keeps the default, never an error. */
    for (int i = 0; i < m->gfx_option_count && i < RRHK_MAX_GFX_OPTIONS; ++i) {
        const RrhkGfxOption *option = &m->gfx_options[i];
        const int value = rr_ini_int(rrhk.video_section, option->ini_key, option->def, rrhk.read_file);
        rrhk.gfx[i] = value >= 0 && value < option->count ? value : option->def;
    }
    /* [Manettes] rumble, shared by every machine that vibrates (the section of the kit's own controller settings). */
    if (m->rumble) rrhk.rumble = rr_ini_int(L"Manettes", L"rumble", 1, rrhk.read_file) != 0;
}

/* A round dead zone on one stick: inside it the stick is centred; outside, the travel that is left is spread over the whole
 * range, so that the edge still gives full scale. 0 % leaves the values as SDL gives them. */
static void dead_zone(int16_t *x, int16_t *y, int percent) {
    if (percent <= 0) return;
    const double fx = *x, fy = *y, length = SDL_sqrt(fx * fx + fy * fy), zone = 32767.0 * percent / 100.0;
    if (length <= zone) { *x = *y = 0; return; }
    const double reach = (length < 32767.0 ? length : 32767.0) - zone;
    const double factor = reach / (32767.0 - zone) * 32767.0 / length;
    const double nx = fx * factor, ny = fy * factor;
    *x = (int16_t)(nx > 32767.0 ? 32767 : nx < -32768.0 ? -32768 : nx);
    *y = (int16_t)(ny > 32767.0 ? 32767 : ny < -32768.0 ? -32768 : ny);
}

bool rrhk_pad_axes(int p, uint64_t frame, int16_t axes[RRHK_AXES]) {
    const RrhkMachine *m = rrhk.machine;
    static const SDL_GameControllerAxis source[RRHK_AXES] = {SDL_CONTROLLER_AXIS_LEFTX, SDL_CONTROLLER_AXIS_LEFTY,
                                                             SDL_CONTROLLER_AXIS_RIGHTX, SDL_CONTROLLER_AXIS_RIGHTY};
    for (int i = 0; i < RRHK_AXES; ++i) axes[i] = 0;
    if (!m || p < 0 || p >= RRHK_MAX_PLAYERS) return false;
    /* A replay inside the window: the recorded sticks, as they were recorded (after the dead zone of that run). */
    if (m->script_axes && m->script_axes(p, frame, axes)) return true;
    for (int i = 0; i < RRHK_AXES; ++i) axes[i] = 0;
    SDL_GameController *pad = rrhk.pads[p];
    if (!pad || !SDL_GameControllerGetAttached(pad)) return false;
    for (int i = 0; i < RRHK_AXES; ++i) axes[i] = SDL_GameControllerGetAxis(pad, source[i]);
    dead_zone(&axes[RRHK_AXIS_LX], &axes[RRHK_AXIS_LY], rrhk.deadzone[p]);
    dead_zone(&axes[RRHK_AXIS_RX], &axes[RRHK_AXIS_RY], rrhk.deadzone[p]);
    return true;
}

/* Enter on the Stick dead zone row: 0, 5, 10 ... 30 %, then 0 again; Delete: 0. Kept in the player's gamepad section. */
void rrhk_deadzone_step(int p, bool reset) {
    if (p < 0 || p >= RRHK_MAX_PLAYERS) return;
    rrhk.deadzone[p] = reset || rrhk.deadzone[p] + 5 > RRHK_DEADZONE_MAX ? 0 : rrhk.deadzone[p] + 5;
    wchar_t sec[64], value[16];
    section(sec, p, true);
    swprintf(value, 16, L"%d", rrhk.deadzone[p]);
    if (!rrhk_write_ready() || !rr_ini_set(sec, L"deadzone", value, rrhk.ini_file))
        snprintf(rrhk.status, sizeof rrhk.status, "%s", rr_tr("Config unavailable"));
}

void rrhk_rumble(int p, uint16_t low, uint16_t high, uint32_t milliseconds) {
    const RrhkMachine *m = rrhk.machine;
    if (!m || !m->rumble || !rrhk.rumble || p < 0 || p >= RRHK_MAX_PLAYERS || !rrhk.pads[p]) return;
    SDL_GameControllerRumble(rrhk.pads[p], low, high, milliseconds);
}

void rrhk_rumble_stop(void) {
    if (!rrhk.machine || !rrhk.machine->rumble) return;
    for (int p = 0; p < RRHK_MAX_PLAYERS; ++p) if (rrhk.pads[p]) SDL_GameControllerRumble(rrhk.pads[p], 0, 0, 0);
}

void rrhk_toggle_rumble(void) {
    rrhk.rumble = !rrhk.rumble;
    if (!rrhk.rumble) rrhk_rumble_stop();
    if (!rrhk_write_ready() || !rr_ini_set(L"Manettes", L"rumble", rrhk.rumble ? L"1" : L"0", rrhk.ini_file))
        snprintf(rrhk.status, sizeof rrhk.status, "%s", rr_tr("Config unavailable"));
}

/* The graphics options (D14). `--gfx` asks a value for this run only; a hidden-window test run starts from the defaults (the
 * reference setting every gate uses), never from the player's saved choice. */
static int gfx_forced[RRHK_MAX_GFX_OPTIONS];     /* 1 + the value `--gfx` asked for, 0: none */

bool rrhk_gfx_override(const RrhkMachine *machine, const char *assignment) {
    const char *equals = assignment ? strchr(assignment, '=') : NULL;
    if (!machine || !equals || equals == assignment || !equals[1]) return false;
    char *end = NULL;
    const long value = strtol(equals + 1, &end, 10);
    if (!end || *end) return false;
    const size_t length = (size_t)(equals - assignment);
    for (int i = 0; i < machine->gfx_option_count && i < RRHK_MAX_GFX_OPTIONS; ++i) {
        const RrhkGfxOption *option = &machine->gfx_options[i];
        size_t k = 0;
        while (k < length && option->ini_key[k] && option->ini_key[k] == (wchar_t)(unsigned char)assignment[k]) ++k;
        if (k != length || option->ini_key[k]) continue;
        if (value < 0 || value >= option->count) return false;
        gfx_forced[i] = (int)value + 1;
        return true;
    }
    return false;
}

int rrhk_gfx_value(int option) { return option >= 0 && option < RRHK_MAX_GFX_OPTIONS ? rrhk.gfx[option] : 0; }

void rrhk_gfx_start(bool test_run) {
    const RrhkMachine *m = rrhk.machine;
    for (int i = 0; i < m->gfx_option_count && i < RRHK_MAX_GFX_OPTIONS; ++i) {
        if (test_run) rrhk.gfx[i] = m->gfx_options[i].def;
        if (gfx_forced[i]) rrhk.gfx[i] = gfx_forced[i] - 1;
        if (m->gfx_apply) m->gfx_apply(i, rrhk.gfx[i]);
    }
}

void rrhk_gfx_set(int option, int value) {
    const RrhkMachine *m = rrhk.machine;
    if (option < 0 || option >= m->gfx_option_count || option >= RRHK_MAX_GFX_OPTIONS) return;
    const RrhkGfxOption *o = &m->gfx_options[option];
    if (value < 0 || value >= o->count) return;
    rrhk.gfx[option] = value;
    if (m->gfx_apply) m->gfx_apply(option, value);
    wchar_t text[16];
    swprintf(text, 16, L"%d", value);
    if (!rrhk_write_ready() || !rr_ini_set(rrhk.video_section, o->ini_key, text, rrhk.ini_file))
        snprintf(rrhk.status, sizeof rrhk.status, "%s", rr_tr("Config unavailable"));
}

void rrhk_gfx_defaults(void) {
    const RrhkMachine *m = rrhk.machine;
    for (int i = 0; i < m->gfx_option_count && i < RRHK_MAX_GFX_OPTIONS; ++i) rrhk_gfx_set(i, m->gfx_options[i].def);
}
