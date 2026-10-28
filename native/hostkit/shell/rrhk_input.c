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

void rrhk_open_pads(void) {
    const RrhkMachine *m = rrhk.machine;
    for (int i = 0; i < m->table_players; ++i) if (rrhk.pads[i] && !SDL_GameControllerGetAttached(rrhk.pads[i])) {
        SDL_GameControllerClose(rrhk.pads[i]); rrhk.pads[i] = NULL;
    }
    for (int i = 0; i < SDL_NumJoysticks(); ++i) if (SDL_IsGameController(i)) {
        SDL_JoystickID id = SDL_JoystickGetDeviceInstanceID(i);
        bool known = false;
        for (int p = 0; p < m->table_players; ++p)
            if (rrhk.pads[p] && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(rrhk.pads[p])) == id) known = true;
        if (known) continue;
        for (int p = 0; p < m->players(); ++p) if (!rrhk.pads[p]) { rrhk.pads[p] = SDL_GameControllerOpen(i); break; }
    }
}

void rrhk_close_pads(void) {
    for (int p = 0; p < rrhk.machine->table_players; ++p) if (rrhk.pads[p]) SDL_GameControllerClose(rrhk.pads[p]);
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
