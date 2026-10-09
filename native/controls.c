/* One INI in datas beside the executable, shared by every game there.
 * Write only the changed entry so a second running game cannot erase it. */
#include "controls.h"
#include "glue.h"
#include "host_control.h"
#include "paths.h"
#include "retro_keyboard.h"
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>

Controls controls;
#ifdef RETRO_GAME_GEAR
static const wchar_t *video_section = L"GameGear.Video";
static const char *labels[2][CONTROL_ACTIONS] = {
    {"Up", "Down", "Left", "Right", "Button 1", "Button 2", "Pause/Menu", "Game Start"},
    {"Haut", "Bas", "Gauche", "Droite", "Bouton 1", "Bouton 2", "Pause/Menu", "Start jeu"}};
static const wchar_t *key_sections[CONTROL_PLAYERS] = {L"ClavierGameGear", L"ClavierGameGearJ2"};
static const wchar_t *button_sections[CONTROL_PLAYERS] = {L"ManetteGameGear", L"ManetteGameGearJ2"};
static const wchar_t *entries[CONTROL_ACTIONS] = {L"haut", L"bas", L"gauche", L"droite", L"bouton1", L"bouton2", L"menu", L"start"};
#else
static const wchar_t *video_section = L"MasterSystem.Video";
static const char *labels[2][CONTROL_ACTIONS] = {
    {"Up", "Down", "Left", "Right", "Button 1", "Button 2", "Start/Menu", "Select/Reset"},
    {"Haut", "Bas", "Gauche", "Droite", "Bouton 1", "Bouton 2", "Start/Menu", "Select/Reset"}};
static const wchar_t *key_sections[CONTROL_PLAYERS] = {L"Clavier", L"ClavierJ2"};
static const wchar_t *button_sections[CONTROL_PLAYERS] = {L"Manette", L"ManetteJ2"};
static const wchar_t *entries[CONTROL_ACTIONS] = {L"haut", L"bas", L"gauche", L"droite", L"bouton1", L"bouton2", L"start", L"select"};
#endif
static const char *filters[2][FILTER_COUNT] = {
    {"Sharp pixels", "Bilinear smoothing", "Scale2x", "Scanlines"},
    {"Pixels nets", "Lissage bilineaire", "Scale2x", "Scanlines"}};
static SDL_Scancode default_keys[CONTROL_PLAYERS][CONTROL_ACTIONS] = {
#ifdef RETRO_GAME_GEAR
    {SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT, SDL_SCANCODE_RIGHT,
     SDL_SCANCODE_W, SDL_SCANCODE_X, SDL_SCANCODE_P, SDL_SCANCODE_S},
#else
    {SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT, SDL_SCANCODE_RIGHT,
     SDL_SCANCODE_W, SDL_SCANCODE_X, SDL_SCANCODE_P, SDL_SCANCODE_F1},
#endif
    {SDL_SCANCODE_KP_5, SDL_SCANCODE_KP_2, SDL_SCANCODE_KP_1, SDL_SCANCODE_KP_3,
     SDL_SCANCODE_KP_8, SDL_SCANCODE_KP_9, SDL_SCANCODE_KP_7, SDL_SCANCODE_UNKNOWN}};
static const SDL_GameControllerButton default_buttons[CONTROL_PLAYERS][CONTROL_ACTIONS] = {
#ifdef RETRO_GAME_GEAR
    {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
     SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
     SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_START},
#else
    {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
     SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
     SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_BACK},
#endif
    {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
     SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
     SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_INVALID}};
static const uint8_t masks[6] = {SMS_PAD_UP, SMS_PAD_DOWN, SMS_PAD_LEFT, SMS_PAD_RIGHT, SMS_PAD_B1, SMS_PAD_B2};
static wchar_t config_path[32768];
static wchar_t legacy_config_path[32768];
static bool autofire_held[CONTROL_PLAYERS][2];
static uint64_t autofire_started[CONTROL_PLAYERS][2];

void controls_reset_autofire(void) {
    memset(autofire_held, 0, sizeof(autofire_held));
}

/* Each new press starts on immediately. Never pulse directions or system
 * actions, and keep each player's two buttons independent. */
static uint8_t pulse_gamepad(int player, uint8_t buttons, uint64_t time_us) {
    if (player < 0 || player >= CONTROL_PLAYERS) return 0;
    for (int i = 0; i < 2; ++i) {
        uint8_t mask = masks[4 + i];
        if (!controls.autofire || !(buttons & mask)) autofire_held[player][i] = false;
        else {
            if (!autofire_held[player][i] || time_us < autofire_started[player][i]) {
                autofire_started[player][i] = time_us; autofire_held[player][i] = true;
            }
            /* 12.5 ms pressed / 12.5 ms released: forty pulses per guest second. */
            if ((time_us - autofire_started[player][i]) % 25000 >= 12500) buttons &= (uint8_t)~mask;
        }
    }
    return buttons;
}

const char *controls_text(const char *english, const char *french) { return controls.language ? french : english; }
const char *controls_label(int row) { return labels[controls.language][row]; }
const char *controls_filter_label(int filter) { return filters[controls.language][filter]; }
int controls_action_count(int player) {
#ifdef RETRO_GAME_GEAR
    return player == 0 ? CONTROL_ACTIONS : 0;
#else
    return player == 0 ? CONTROL_ACTIONS : player == 1 ? CONTROL_RESET : 0;
#endif
}
bool controls_system_key(SDL_Scancode key, int action) {
#ifdef RETRO_GAME_GEAR
    if (action == CONTROL_RESET) return false; /* F1 is the only reset shortcut. */
#endif
    if (key == SDL_SCANCODE_UNKNOWN || (action != CONTROL_PAUSE && action != CONTROL_RESET)) return false;
    for (int p = 0; p < CONTROL_PLAYERS; ++p)
        if (action < controls_action_count(p) && controls.keys[p][action] == key) return true;
    return false;
}

bool controls_system_button(int player, int button, int action) {
#ifdef RETRO_GAME_GEAR
    if (action == CONTROL_RESET) return false; /* Start belongs to the cartridge. */
#endif
    return player >= 0 && player < CONTROL_PLAYERS && action >= CONTROL_PAUSE &&
        action < controls_action_count(player) && button >= 0 && button < SDL_CONTROLLER_BUTTON_MAX &&
        controls.buttons[player][action] == button;
}

static bool controls_guest_start_key(int player, SDL_Scancode key) {
#ifdef RETRO_GAME_GEAR
    return player == 0 && key != SDL_SCANCODE_UNKNOWN && controls.keys[0][CONTROL_RESET] == key;
#else
    (void)player; (void)key; return false;
#endif
}

static bool controls_guest_start_button(int player, int button) {
#ifdef RETRO_GAME_GEAR
    return player == 0 && button >= 0 && controls.buttons[0][CONTROL_RESET] == button;
#else
    (void)player; (void)button; return false;
#endif
}

bool controls_reserved(SDL_Scancode key) {
    return key == SDL_SCANCODE_UNKNOWN || key == SDL_SCANCODE_H || key == SDL_SCANCODE_P ||
        key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER ||
        key == SDL_SCANCODE_ESCAPE || (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12);
}

static void init_path(void) {
    if (config_path[0]) return;
    wchar_t root[RETRO_PATH_CAP];
    if (!retro_data_directory(root)) {
        fprintf(stderr, "[config] datas unavailable; defaults remain available\n");
        return;
    }
    swprintf(config_path, RETRO_PATH_CAP, L"%s\\Retro-Recomp.ini", root);
    if (retro_executable_directory(legacy_config_path)) {
        wcscat(legacy_config_path, L"\\SMSRecomp.ini");
    }
}

static const wchar_t *read_path(void) {
    if (GetFileAttributesW(config_path) != INVALID_FILE_ATTRIBUTES) return config_path;
    return legacy_config_path[0] && GetFileAttributesW(legacy_config_path) != INVALID_FILE_ATTRIBUTES ?
        legacy_config_path : config_path;
}

static void read_name(const wchar_t *section, const wchar_t *key, char *out, int size) {
    wchar_t value[128];
    GetPrivateProfileStringW(section, key, L"", value, 128, read_path());
    WideCharToMultiByte(CP_UTF8, 0, value, -1, out, size, NULL, NULL);
}

static bool write_name(const wchar_t *section, const wchar_t *key, const char *name) {
    init_path();
    if (!config_path[0]) return false;
    wchar_t parent[RETRO_PATH_CAP]; wcscpy(parent, config_path);
    wchar_t *slash = wcsrchr(parent, L'\\');
    if (!slash) slash = wcsrchr(parent, L'/');
    if (!slash) return false;
    *slash = 0;
    if (!retro_make_directories(parent)) return false;
    if (GetFileAttributesW(config_path) == INVALID_FILE_ATTRIBUTES && legacy_config_path[0] &&
        GetFileAttributesW(legacy_config_path) != INVALID_FILE_ATTRIBUTES &&
        !CopyFileW(legacy_config_path, config_path, TRUE)) return false;
    wchar_t value[128];
    MultiByteToWideChar(CP_UTF8, 0, name, -1, value, 128);
    return WritePrivateProfileStringW(section, key, value, config_path) != 0;
}

static void keyboard_defaults(void) {
    default_keys[0][4] = rr_keyboard_letter(SDLK_w, SDL_SCANCODE_W);
    default_keys[0][5] = rr_keyboard_letter(SDLK_x, SDL_SCANCODE_X);
}

void controls_load(void) {
    keyboard_defaults();
    controls.filter = FILTER_NEAREST; controls.display_mode = 0;
    controls.first_controller_player = 0; controls.language = 0;
    controls.autofire = false;
    controls.phaser_dot_size = 1;
    controls.phaser_shape = PHASER_CROSS;
    controls.phaser_color = PHASER_RED;
    for (int p = 0; p < CONTROL_PLAYERS; ++p) for (int i = 0; i < CONTROL_ACTIONS; ++i) {
        controls.keys[p][i] = default_keys[p][i];
        controls.buttons[p][i] = default_buttons[p][i];
    }
    init_path();
    if (!config_path[0]) {
        controls.filter = FILTER_NEAREST;
        controls.first_controller_player = 0;
        controls.language = 0;
        return;
    }
    char value[128];
    /* Only migrate the complete, unchanged 0.8 default layout. A customized
     * layout is preserved, even if some individual keys match old defaults. */
    const SDL_Scancode old_defaults[6] = {SDL_SCANCODE_I, SDL_SCANCODE_K, SDL_SCANCODE_J,
        SDL_SCANCODE_L, SDL_SCANCODE_N, SDL_SCANCODE_M};
    bool old_layout = true;
    for (int i = 0; i < CONTROL_GAME_ACTIONS; ++i) {
        read_name(key_sections[1], entries[i], value, sizeof(value));
        if (SDL_GetScancodeFromName(value) != old_defaults[i]) old_layout = false;
    }
    /* Load system keys first so gameplay keys cannot consume pause/reset. */
    for (int p = 0; p < CONTROL_PLAYERS; ++p) for (int i = CONTROL_PAUSE; i < controls_action_count(p); ++i) {
        read_name(key_sections[p], entries[i], value, sizeof(value));
        SDL_Scancode key = SDL_GetScancodeFromName(value);
        bool allowed = !controls_reserved(key) || key == default_keys[0][i] ||
            (i == CONTROL_PAUSE && (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER));
        controls.keys[p][i] = allowed ? key : default_keys[p][i];
        read_name(button_sections[p], entries[i], value, sizeof(value));
        SDL_GameControllerButton button = SDL_GameControllerGetButtonFromString(value);
        controls.buttons[p][i] = button == SDL_CONTROLLER_BUTTON_INVALID ? default_buttons[p][i] : button;
        if (i == CONTROL_RESET && controls.buttons[p][i] == controls.buttons[p][CONTROL_PAUSE])
            controls.buttons[p][i] = SDL_CONTROLLER_BUTTON_INVALID;
    }
    /* J2 cannot reset the game, including legacy INI bindings. */
    for (int p = 0; p < CONTROL_PLAYERS; ++p) for (int i = 0; i < CONTROL_GAME_ACTIONS; ++i) {
        read_name(key_sections[p], entries[i], value, sizeof(value));
        if (p == 1 && old_layout) snprintf(value, sizeof(value), "%s", SDL_GetScancodeName(default_keys[p][i]));
        SDL_Scancode key = SDL_GetScancodeFromName(value);
        controls.keys[p][i] = controls_reserved(key) || controls_system_key(key, CONTROL_PAUSE) ||
            controls_system_key(key, CONTROL_RESET) || controls_guest_start_key(p, key) ? default_keys[p][i] : key;
        if (controls_system_key(controls.keys[p][i], CONTROL_PAUSE) || controls_system_key(controls.keys[p][i], CONTROL_RESET) ||
                controls_guest_start_key(p, controls.keys[p][i]))
            controls.keys[p][i] = SDL_SCANCODE_UNKNOWN;
        read_name(button_sections[p], entries[i], value, sizeof(value));
        SDL_GameControllerButton button = SDL_GameControllerGetButtonFromString(value);
        controls.buttons[p][i] = button == SDL_CONTROLLER_BUTTON_INVALID || controls_system_button(p, button, CONTROL_PAUSE) ||
            controls_system_button(p, button, CONTROL_RESET) || controls_guest_start_button(p, button) ? default_buttons[p][i] : button;
        if (controls_system_button(p, controls.buttons[p][i], CONTROL_PAUSE) || controls_system_button(p, controls.buttons[p][i], CONTROL_RESET) ||
                controls_guest_start_button(p, controls.buttons[p][i]))
            controls.buttons[p][i] = SDL_CONTROLLER_BUTTON_INVALID;
    }
    int filter = (int)GetPrivateProfileIntW(L"Video", L"filtre", 0, read_path());
    int mode = (int)GetPrivateProfileIntW(L"Video", L"display_mode", 0, read_path());
    filter = (int)GetPrivateProfileIntW(video_section, L"filter", filter, read_path());
    mode = (int)GetPrivateProfileIntW(video_section, L"display_mode", mode, read_path());
    controls.display_mode = mode >= 0 && mode < 3 ? mode : 0;
    controls.filter = filter >= 0 && filter < FILTER_COUNT ? filter : FILTER_NEAREST;
    /* Obsolete border/J2-reset settings are ignored without rewriting the INI. */
#ifndef RETRO_GAME_GEAR
    controls.first_controller_player = GetPrivateProfileIntW(L"Manettes", L"premier_joueur", 1, read_path()) == 2 ? 1 : 0;
#endif
    controls.autofire = GetPrivateProfileIntW(L"Manettes", L"autofire", 0, read_path()) == 1;
    read_name(L"Interface", L"language", value, sizeof(value));
    controls.language = !strcmp(value, "fr");
    int dot = (int)GetPrivateProfileIntW(L"LightPhaser", L"dot_size", 1, read_path());
    if (dot >= 1 && dot <= 5) controls.phaser_dot_size = dot;
    read_name(L"LightPhaser", L"shape", value, sizeof(value));
    if (!strcmp(value, "dot")) controls.phaser_shape = PHASER_DOT;
    read_name(L"LightPhaser", L"color", value, sizeof(value));
    if (!strcmp(value, "white")) controls.phaser_color = PHASER_WHITE;
    else if (!strcmp(value, "green")) controls.phaser_color = PHASER_GREEN;
}

bool controls_bind(int player, int row, bool gamepad, int value) {
    if (player < 0 || player >= CONTROL_PLAYERS || row < 0 || row >= controls_action_count(player)) return false;
    if (gamepad) {
        if (value < 0 || value >= SDL_CONTROLLER_BUTTON_MAX) return false;
        if (row < CONTROL_GAME_ACTIONS && (controls_system_button(player, value, CONTROL_PAUSE) ||
            controls_system_button(player, value, CONTROL_RESET) || controls_guest_start_button(player, value))) return false;
        if (row >= CONTROL_PAUSE) {
            int other = row == CONTROL_PAUSE ? CONTROL_RESET : CONTROL_PAUSE;
            if (controls_system_button(player, value, other) ||
                    (row == CONTROL_PAUSE && controls_guest_start_button(player, value))) return false;
            for (int i = 0; i < CONTROL_GAME_ACTIONS; ++i) if (controls.buttons[player][i] == value) return false;
        }
        if (!write_name(button_sections[player], entries[row], SDL_GameControllerGetStringForButton(value))) return false;
        controls.buttons[player][row] = (SDL_GameControllerButton)value;
    } else {
        if (value < 0 || value >= SDL_NUM_SCANCODES) return false;
        SDL_Scancode key = (SDL_Scancode)value;
        bool system_alias = row == CONTROL_PAUSE && (key == SDL_SCANCODE_P || key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER);
#ifdef RETRO_GAME_GEAR
        if (controls_reserved(key) && !system_alias) return false;
#else
        if (controls_reserved(key) && !system_alias && !(row == CONTROL_RESET && key == SDL_SCANCODE_F1)) return false;
#endif
        if (row < CONTROL_GAME_ACTIONS && (controls_system_key(key, CONTROL_PAUSE) ||
            controls_system_key(key, CONTROL_RESET) || controls_guest_start_key(player, key))) return false;
        if (row >= CONTROL_PAUSE) {
            int other = row == CONTROL_PAUSE ? CONTROL_RESET : CONTROL_PAUSE;
            if (controls_system_key(key, other) ||
                    (row == CONTROL_PAUSE && controls_guest_start_key(player, key))) return false;
            for (int p = 0; p < CONTROL_PLAYERS; ++p) for (int i = 0; i < CONTROL_GAME_ACTIONS; ++i)
                if (controls.keys[p][i] == key) return false;
        }
        if (!write_name(key_sections[player], entries[row], SDL_GetScancodeName((SDL_Scancode)value))) return false;
        controls.keys[player][row] = (SDL_Scancode)value;
    }
    return true;
}

bool controls_defaults(int player, bool gamepad) {
    if (player < 0 || player >= CONTROL_PLAYERS) return false;
    keyboard_defaults();
    bool ok = true;
    /* A complete preset can free a button currently used by a custom system
     * action; validating against the old layout would reject its own defaults. */
    for (int i = 0; i < controls_action_count(player); ++i) {
        if (gamepad) {
            if (write_name(button_sections[player], entries[i], SDL_GameControllerGetStringForButton(default_buttons[player][i])))
                controls.buttons[player][i] = default_buttons[player][i];
            else ok = false;
        } else {
            if (write_name(key_sections[player], entries[i], SDL_GetScancodeName(default_keys[player][i])))
                controls.keys[player][i] = default_keys[player][i];
            else ok = false;
        }
    }
    return ok;
}

bool controls_filter(int filter) {
    if (filter < 0 || filter >= FILTER_COUNT) return false;
    char value[16]; snprintf(value, sizeof(value), "%d", filter);
    if (!write_name(video_section, L"filter", value)) return false;
    controls.filter = filter;
    return true;
}

bool controls_display_mode(int mode) {
    if (mode < 0 || mode > 2) return false;
    char value[16]; snprintf(value, sizeof(value), "%d", mode);
    if (!write_name(video_section, L"display_mode", value)) return false;
    controls.display_mode = mode; return true;
}

bool controls_controller_order(int first_player) {
#ifdef RETRO_GAME_GEAR
    if (first_player != 0) return false;
#endif
    if (first_player < 0 || first_player >= CONTROL_PLAYERS) return false;
    if (!write_name(L"Manettes", L"premier_joueur", first_player ? "2" : "1")) return false;
    controls.first_controller_player = first_player;
    return true;
}

bool controls_language(int language) {
    if (language < 0 || language > 1 || !write_name(L"Interface", L"language", language ? "fr" : "en")) return false;
    controls.language = language; return true;
}

bool controls_autofire(bool enabled) {
    if (!write_name(L"Manettes", L"autofire", enabled ? "1" : "0")) return false;
    controls.autofire = enabled; controls_reset_autofire(); return true;
}

bool controls_phaser_dot_size(int size) {
    if (size < 1 || size > 5) return false;
    char value[16]; snprintf(value, sizeof(value), "%d", size);
    if (!write_name(L"LightPhaser", L"dot_size", value)) return false;
    controls.phaser_dot_size = size; return true;
}

bool controls_phaser_shape(int shape) {
    if (shape < 0 || shape >= PHASER_SHAPE_COUNT) return false;
    if (!write_name(L"LightPhaser", L"shape", shape == PHASER_DOT ? "dot" : "cross")) return false;
    controls.phaser_shape = shape; return true;
}

bool controls_phaser_color(int color) {
    static const char *names[] = {"red", "white", "green"};
    if (color < 0 || color >= PHASER_COLOR_COUNT) return false;
    if (!write_name(L"LightPhaser", L"color", names[color])) return false;
    controls.phaser_color = color; return true;
}

static uint8_t read_controls(int player, SDL_GameController *controller, bool focused, const uint8_t *keys) {
    if (player < 0 || player >= CONTROL_PLAYERS) return 0;
    if (!focused) { pulse_gamepad(player, 0, 0); return 0; }
    uint8_t result = 0, gamepad = 0;
    for (int i = 0; i < 6; ++i) {
        if (controls.keys[player][i] != SDL_SCANCODE_UNKNOWN && keys[controls.keys[player][i]])
            result |= masks[i];
        if (controller && controls.buttons[player][i] >= 0 && SDL_GameControllerGetButton(controller, controls.buttons[player][i]))
            gamepad |= masks[i];
    }
    if (controller) {
        int x = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTX);
        int y = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTY);
        if (x < -12000) gamepad |= SMS_PAD_LEFT;
        if (x > 12000) gamepad |= SMS_PAD_RIGHT;
        if (y < -12000) gamepad |= SMS_PAD_UP;
        if (y > 12000) gamepad |= SMS_PAD_DOWN;
    }
#ifdef RETRO_GAME_GEAR
    if (player == 0) {
        if (controls.keys[0][CONTROL_RESET] != SDL_SCANCODE_UNKNOWN && keys[controls.keys[0][CONTROL_RESET]])
            result |= SMS_PAD_START;
        if (controller && controls.buttons[0][CONTROL_RESET] >= 0 &&
                SDL_GameControllerGetButton(controller, controls.buttons[0][CONTROL_RESET]))
            result |= SMS_PAD_START;
    }
#endif
    return result | pulse_gamepad(player, gamepad, controls.autofire ? smsrecomp_input_time_us() : 0);
}

uint8_t controls_read(int player, SDL_GameController *controller, bool focused) {
    return read_controls(player, controller, focused, SDL_GetKeyboardState(NULL));
}
