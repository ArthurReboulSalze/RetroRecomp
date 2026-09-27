/* One INI in datas beside the executable, shared by every game there.
 * Write only the changed entry so a second running game cannot erase it. */
#include "controls.h"
#include "glue.h"
#include "paths.h"
#include <windows.h>
#include <stdio.h>
#include <wchar.h>
#include <string.h>

Controls controls;
static const char *labels[2][CONTROL_ACTIONS] = {
    {"Up", "Down", "Left", "Right", "Button 1", "Button 2", "Start/Menu", "Select/Reset"},
    {"Haut", "Bas", "Gauche", "Droite", "Bouton 1", "Bouton 2", "Start/Menu", "Select/Reset"}};
static const char *filters[2][FILTER_COUNT] = {
    {"Sharp pixels", "Bilinear smoothing", "Scale2x", "Scanlines"},
    {"Pixels nets", "Lissage bilineaire", "Scale2x", "Scanlines"}};
static const wchar_t *entries[CONTROL_ACTIONS] = {L"haut", L"bas", L"gauche", L"droite", L"bouton1", L"bouton2", L"start", L"select"};
static const wchar_t *key_sections[CONTROL_PLAYERS] = {L"Clavier", L"ClavierJ2"};
static const wchar_t *button_sections[CONTROL_PLAYERS] = {L"Manette", L"ManetteJ2"};
static const SDL_Scancode default_keys[CONTROL_PLAYERS][CONTROL_ACTIONS] = {
    {SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT, SDL_SCANCODE_RIGHT,
     SDL_SCANCODE_Z, SDL_SCANCODE_X, SDL_SCANCODE_P, SDL_SCANCODE_F1},
    {SDL_SCANCODE_KP_5, SDL_SCANCODE_KP_2, SDL_SCANCODE_KP_1, SDL_SCANCODE_KP_3,
     SDL_SCANCODE_KP_8, SDL_SCANCODE_KP_9, SDL_SCANCODE_KP_7, SDL_SCANCODE_UNKNOWN}};
static const SDL_GameControllerButton default_buttons[CONTROL_PLAYERS][CONTROL_ACTIONS] = {
    {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
     SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
     SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_BACK},
    {SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
     SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
     SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_INVALID}};
static const uint8_t masks[6] = {SMS_PAD_UP, SMS_PAD_DOWN, SMS_PAD_LEFT, SMS_PAD_RIGHT, SMS_PAD_B1, SMS_PAD_B2};
static wchar_t config_path[32768];

const char *controls_text(const char *english, const char *french) { return controls.language ? french : english; }
const char *controls_label(int row) { return labels[controls.language][row]; }
const char *controls_filter_label(int filter) { return filters[controls.language][filter]; }
int controls_action_count(int player) { return player == 0 ? CONTROL_ACTIONS : player == 1 ? CONTROL_RESET : 0; }
bool controls_system_key(SDL_Scancode key, int action) {
    if (key == SDL_SCANCODE_UNKNOWN || (action != CONTROL_PAUSE && action != CONTROL_RESET)) return false;
    for (int p = 0; p < CONTROL_PLAYERS; ++p)
        if (action < controls_action_count(p) && controls.keys[p][action] == key) return true;
    return false;
}

bool controls_system_button(int player, int button, int action) {
    return player >= 0 && player < CONTROL_PLAYERS && action >= CONTROL_PAUSE &&
        action < controls_action_count(player) && button >= 0 && button < SDL_CONTROLLER_BUTTON_MAX &&
        controls.buttons[player][action] == button;
}

bool controls_reserved(SDL_Scancode key) {
    return key == SDL_SCANCODE_UNKNOWN || key == SDL_SCANCODE_H || key == SDL_SCANCODE_P ||
        key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER ||
        key == SDL_SCANCODE_ESCAPE || (key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12);
}

static void init_path(void) {
    if (config_path[0]) return;
    wchar_t root[RETRO_PATH_CAP], legacy[RETRO_PATH_CAP];
    if (!retro_data_directory(root)) {
        fprintf(stderr, "[config] datas unavailable; defaults remain available\n");
        return;
    }
    swprintf(config_path, RETRO_PATH_CAP, L"%s\\Retro-Recomp.ini", root);
    if (GetFileAttributesW(config_path) == INVALID_FILE_ATTRIBUTES && retro_executable_directory(legacy)) {
        wcscat(legacy, L"\\SMSRecomp.ini");
        CopyFileW(legacy, config_path, TRUE); /* Copy old settings once, preserve the original. */
    }
}

static void read_name(const wchar_t *section, const wchar_t *key, char *out, int size) {
    wchar_t value[128];
    GetPrivateProfileStringW(section, key, L"", value, 128, config_path);
    WideCharToMultiByte(CP_UTF8, 0, value, -1, out, size, NULL, NULL);
}

static bool write_name(const wchar_t *section, const wchar_t *key, const char *name) {
    if (!config_path[0]) return false;
    wchar_t value[128];
    MultiByteToWideChar(CP_UTF8, 0, name, -1, value, 128);
    return WritePrivateProfileStringW(section, key, value, config_path) != 0;
}

void controls_load(void) {
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
    if (GetFileAttributesW(config_path) == INVALID_FILE_ATTRIBUTES) {
        FILE *f = _wfopen(config_path, L"wb");
        if (f) {
            fputs("; Retro-Recomp - configuration commune aux jeux de ce dossier\r\n"
                "; F1 reset, F2 commandes, F3 filtre, F4 plein ecran, H aide, P/Entree pause\r\n"
                "; Manette : Start/Menu = pause, Select/Back = reset J1 ; configurables dans F2.\r\n"
                "; Le stick gauche reste disponible en plus des boutons de direction.\r\n"
                "[Clavier]\r\nhaut=Up\r\nbas=Down\r\ngauche=Left\r\ndroite=Right\r\nbouton1=Z\r\nbouton2=X\r\nstart=P\r\nselect=F1\r\n"
                "[Manette]\r\nhaut=dpup\r\nbas=dpdown\r\ngauche=dpleft\r\ndroite=dpright\r\nbouton1=a\r\nbouton2=b\r\nstart=start\r\nselect=back\r\n"
                "[ClavierJ2]\r\nhaut=Keypad 5\r\nbas=Keypad 2\r\ngauche=Keypad 1\r\ndroite=Keypad 3\r\nbouton1=Keypad 8\r\nbouton2=Keypad 9\r\nstart=Keypad 7\r\n"
                "[ManetteJ2]\r\nhaut=dpup\r\nbas=dpdown\r\ngauche=dpleft\r\ndroite=dpright\r\nbouton1=a\r\nbouton2=b\r\nstart=start\r\n"
                "[Manettes]\r\n; Premiere manette detectee : joueur 1 ou 2\r\npremier_joueur=1\r\n"
                "[Interface]\r\nlanguage=en\r\n"
                "[Video]\r\n; 0 pixels nets, 1 bilineaire, 2 Scale2x, 3 scanlines\r\nfiltre=0\r\n", f);
            fclose(f);
        } else fprintf(stderr, "[config] cannot create datas/Retro-Recomp.ini; defaults remain available\n");
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
    if (old_layout) for (int i = 0; i < CONTROL_GAME_ACTIONS; ++i)
        write_name(key_sections[1], entries[i], SDL_GetScancodeName(default_keys[1][i]));
    /* Load system keys first so gameplay keys cannot consume pause/reset. */
    for (int p = 0; p < CONTROL_PLAYERS; ++p) for (int i = CONTROL_PAUSE; i < controls_action_count(p); ++i) {
        read_name(key_sections[p], entries[i], value, sizeof(value));
        SDL_Scancode key = SDL_GetScancodeFromName(value);
        bool allowed = !controls_reserved(key) || key == default_keys[0][i] ||
            (i == CONTROL_PAUSE && (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER));
        controls.keys[p][i] = allowed ? key : default_keys[p][i];
        if (!value[0]) write_name(key_sections[p], entries[i], SDL_GetScancodeName(default_keys[p][i]));
        read_name(button_sections[p], entries[i], value, sizeof(value));
        SDL_GameControllerButton button = SDL_GameControllerGetButtonFromString(value);
        controls.buttons[p][i] = button == SDL_CONTROLLER_BUTTON_INVALID ? default_buttons[p][i] : button;
        if (!value[0]) write_name(button_sections[p], entries[i], SDL_GameControllerGetStringForButton(default_buttons[p][i]));
        if (i == CONTROL_RESET && controls.buttons[p][i] == controls.buttons[p][CONTROL_PAUSE])
            controls.buttons[p][i] = SDL_CONTROLLER_BUTTON_INVALID;
    }
    /* J2 cannot reset the game, including legacy INI bindings. */
    WritePrivateProfileStringW(key_sections[1], entries[CONTROL_RESET], NULL, config_path);
    WritePrivateProfileStringW(button_sections[1], entries[CONTROL_RESET], NULL, config_path);
    for (int p = 0; p < CONTROL_PLAYERS; ++p) for (int i = 0; i < CONTROL_GAME_ACTIONS; ++i) {
        read_name(key_sections[p], entries[i], value, sizeof(value));
        if (!value[0]) write_name(key_sections[p], entries[i], SDL_GetScancodeName(default_keys[p][i]));
        SDL_Scancode key = SDL_GetScancodeFromName(value);
        controls.keys[p][i] = controls_reserved(key) || controls_system_key(key, CONTROL_PAUSE) ||
            controls_system_key(key, CONTROL_RESET) ? default_keys[p][i] : key;
        if (controls_system_key(controls.keys[p][i], CONTROL_PAUSE) || controls_system_key(controls.keys[p][i], CONTROL_RESET))
            controls.keys[p][i] = SDL_SCANCODE_UNKNOWN;
        read_name(button_sections[p], entries[i], value, sizeof(value));
        if (!value[0]) write_name(button_sections[p], entries[i], SDL_GameControllerGetStringForButton(default_buttons[p][i]));
        SDL_GameControllerButton button = SDL_GameControllerGetButtonFromString(value);
        controls.buttons[p][i] = button == SDL_CONTROLLER_BUTTON_INVALID || controls_system_button(p, button, CONTROL_PAUSE) ||
            controls_system_button(p, button, CONTROL_RESET) ? default_buttons[p][i] : button;
        if (controls_system_button(p, controls.buttons[p][i], CONTROL_PAUSE) || controls_system_button(p, controls.buttons[p][i], CONTROL_RESET))
            controls.buttons[p][i] = SDL_CONTROLLER_BUTTON_INVALID;
    }
    int filter = (int)GetPrivateProfileIntW(L"Video", L"filtre", 0, config_path);
    controls.filter = filter >= 0 && filter < FILTER_COUNT ? filter : FILTER_NEAREST;
    /* Remove the obsolete manual switch; an old value must not disable the
     * automatic presentation. Read-only configs still work without migration. */
    read_name(L"Video", L"masquer_bord_gauche", value, sizeof(value));
    if (value[0]) WritePrivateProfileStringW(L"Video", L"masquer_bord_gauche", NULL, config_path);
    controls.first_controller_player = GetPrivateProfileIntW(L"Manettes", L"premier_joueur", 1, config_path) == 2 ? 1 : 0;
    read_name(L"Interface", L"language", value, sizeof(value));
    controls.language = !strcmp(value, "fr");
}

bool controls_bind(int player, int row, bool gamepad, int value) {
    if (player < 0 || player >= CONTROL_PLAYERS || row < 0 || row >= controls_action_count(player)) return false;
    if (gamepad) {
        if (value < 0 || value >= SDL_CONTROLLER_BUTTON_MAX) return false;
        if (row < CONTROL_GAME_ACTIONS && (controls_system_button(player, value, CONTROL_PAUSE) || controls_system_button(player, value, CONTROL_RESET))) return false;
        if (row >= CONTROL_PAUSE) {
            int other = row == CONTROL_PAUSE ? CONTROL_RESET : CONTROL_PAUSE;
            if (controls_system_button(player, value, other)) return false;
            for (int i = 0; i < CONTROL_GAME_ACTIONS; ++i) if (controls.buttons[player][i] == value) return false;
        }
        if (!write_name(button_sections[player], entries[row], SDL_GameControllerGetStringForButton(value))) return false;
        controls.buttons[player][row] = (SDL_GameControllerButton)value;
    } else {
        if (value < 0 || value >= SDL_NUM_SCANCODES) return false;
        SDL_Scancode key = (SDL_Scancode)value;
        bool system_alias = row == CONTROL_PAUSE && (key == SDL_SCANCODE_P || key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER);
        if (controls_reserved(key) && !system_alias && !(row == CONTROL_RESET && key == SDL_SCANCODE_F1)) return false;
        if (row < CONTROL_GAME_ACTIONS && (controls_system_key(key, CONTROL_PAUSE) || controls_system_key(key, CONTROL_RESET))) return false;
        if (row >= CONTROL_PAUSE) {
            int other = row == CONTROL_PAUSE ? CONTROL_RESET : CONTROL_PAUSE;
            if (controls_system_key(key, other)) return false;
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
    if (!write_name(L"Video", L"filtre", value)) return false;
    controls.filter = filter;
    return true;
}

bool controls_controller_order(int first_player) {
    if (first_player < 0 || first_player >= CONTROL_PLAYERS) return false;
    if (!write_name(L"Manettes", L"premier_joueur", first_player ? "2" : "1")) return false;
    controls.first_controller_player = first_player;
    return true;
}

bool controls_language(int language) {
    if (language < 0 || language > 1 || !write_name(L"Interface", L"language", language ? "fr" : "en")) return false;
    controls.language = language; return true;
}

static uint8_t read_controls(int player, SDL_GameController *controller, bool focused, const uint8_t *keys) {
    if (!focused || player < 0 || player >= CONTROL_PLAYERS) return 0;
    uint8_t result = 0;
    for (int i = 0; i < 6; ++i) {
        if ((controls.keys[player][i] != SDL_SCANCODE_UNKNOWN && keys[controls.keys[player][i]]) ||
            (controller && controls.buttons[player][i] >= 0 && SDL_GameControllerGetButton(controller, controls.buttons[player][i])))
            result |= masks[i];
    }
    if (controller) {
        int x = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTX);
        int y = SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTY);
        if (x < -12000) result |= SMS_PAD_LEFT;
        if (x > 12000) result |= SMS_PAD_RIGHT;
        if (y < -12000) result |= SMS_PAD_UP;
        if (y > 12000) result |= SMS_PAD_DOWN;
    }
    return result;
}

uint8_t controls_read(int player, SDL_GameController *controller, bool focused) {
    return read_controls(player, controller, focused, SDL_GetKeyboardState(NULL));
}
