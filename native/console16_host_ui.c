/* RetroRecomp 16-bit presentation host. Linked console engines retain
 * its separate PolyForm Noncommercial terms; this UI is original code. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <windows.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include "retro_console16.h"
#include "retro_menu.h"
#include "retro_keyboard.h"
#include "display_settings.h"
#include "console16_state.h"
#include "scanline_sdl.h"
#include "scanlines.h"


#if RR16_MD
#if RR_MD_SIX_BUTTONS
enum { A, B, C, X, Y, Z, MODE, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
#define FACE_LAST Z
static const uint16_t bits[ACTIONS] = {64,16,32,256,512,1024,2048,128,1,2,4,8};
static const char *names[ACTIONS] = {"A","B","C","X","Y","Z","Mode","Start","Up","Down","Left","Right"};
static const wchar_t *settings[ACTIONS] = {L"A",L"B",L"C",L"X",L"Y",L"Z",L"Mode",L"Start",L"Up",L"Down",L"Left",L"Right"};
static SDL_Scancode keys[2][ACTIONS] = {
    {SDL_SCANCODE_W,SDL_SCANCODE_X,SDL_SCANCODE_C,SDL_SCANCODE_A,SDL_SCANCODE_S,SDL_SCANCODE_D,
     SDL_SCANCODE_RSHIFT,SDL_SCANCODE_RETURN,SDL_SCANCODE_UP,SDL_SCANCODE_DOWN,SDL_SCANCODE_LEFT,SDL_SCANCODE_RIGHT},
    {SDL_SCANCODE_KP_8,SDL_SCANCODE_KP_9,SDL_SCANCODE_KP_6,SDL_SCANCODE_KP_0,SDL_SCANCODE_KP_PERIOD,
     SDL_SCANCODE_KP_ENTER,SDL_SCANCODE_KP_4,SDL_SCANCODE_KP_7,SDL_SCANCODE_KP_5,SDL_SCANCODE_KP_2,SDL_SCANCODE_KP_1,SDL_SCANCODE_KP_3}};
static SDL_GameControllerButton buttons[2][ACTIONS] = {
    {SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_X,SDL_CONTROLLER_BUTTON_Y,
     SDL_CONTROLLER_BUTTON_LEFTSHOULDER,SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,SDL_CONTROLLER_BUTTON_BACK,
     SDL_CONTROLLER_BUTTON_START,SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT},
    {SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_X,SDL_CONTROLLER_BUTTON_Y,
     SDL_CONTROLLER_BUTTON_LEFTSHOULDER,SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,SDL_CONTROLLER_BUTTON_BACK,
     SDL_CONTROLLER_BUTTON_START,SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT}};
#else
enum { A, B, C, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
#define FACE_LAST C
static const uint16_t bits[ACTIONS] = {64,16,32,128,1,2,4,8};
static const char *names[ACTIONS] = {"A","B","C","Start","Up","Down","Left","Right"};
static const wchar_t *settings[ACTIONS] = {L"A",L"B",L"C",L"Start",L"Up",L"Down",L"Left",L"Right"};
static SDL_Scancode keys[2][ACTIONS] = {
    {SDL_SCANCODE_W,SDL_SCANCODE_X,SDL_SCANCODE_C,SDL_SCANCODE_RETURN,SDL_SCANCODE_UP,SDL_SCANCODE_DOWN,SDL_SCANCODE_LEFT,SDL_SCANCODE_RIGHT},
    {SDL_SCANCODE_KP_8,SDL_SCANCODE_KP_9,SDL_SCANCODE_KP_6,SDL_SCANCODE_KP_7,SDL_SCANCODE_KP_5,SDL_SCANCODE_KP_2,SDL_SCANCODE_KP_1,SDL_SCANCODE_KP_3}};
static SDL_GameControllerButton buttons[2][ACTIONS] = {
    {SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_X,SDL_CONTROLLER_BUTTON_START,SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT},
    {SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_X,SDL_CONTROLLER_BUTTON_START,SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT}};
#endif
#else
enum { A, B, X, Y, L, R, SELECT, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
#define FACE_LAST Y
static const uint16_t bits[ACTIONS] = {256,1,512,2,1024,2048,4,8,16,32,64,128};
static const char *names[ACTIONS] = {"A","B","X","Y","L","R","Select","Start","Up","Down","Left","Right"};
static const wchar_t *settings[ACTIONS] = {L"A",L"B",L"X",L"Y",L"L",L"R",L"Select",L"Start",L"Up",L"Down",L"Left",L"Right"};
static SDL_Scancode keys[2][ACTIONS] = {
    {SDL_SCANCODE_W,SDL_SCANCODE_X,SDL_SCANCODE_A,SDL_SCANCODE_S,SDL_SCANCODE_Q,SDL_SCANCODE_E,SDL_SCANCODE_RSHIFT,SDL_SCANCODE_RETURN,SDL_SCANCODE_UP,SDL_SCANCODE_DOWN,SDL_SCANCODE_LEFT,SDL_SCANCODE_RIGHT},
    {SDL_SCANCODE_KP_8,SDL_SCANCODE_KP_9,SDL_SCANCODE_KP_0,SDL_SCANCODE_KP_PERIOD,SDL_SCANCODE_KP_DIVIDE,SDL_SCANCODE_KP_MULTIPLY,SDL_SCANCODE_KP_4,SDL_SCANCODE_KP_7,SDL_SCANCODE_KP_5,SDL_SCANCODE_KP_2,SDL_SCANCODE_KP_1,SDL_SCANCODE_KP_3}};
static SDL_GameControllerButton buttons[2][ACTIONS] = {
    {SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_X,SDL_CONTROLLER_BUTTON_Y,SDL_CONTROLLER_BUTTON_LEFTSHOULDER,SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,SDL_CONTROLLER_BUTTON_BACK,SDL_CONTROLLER_BUTTON_START,SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT},
    {SDL_CONTROLLER_BUTTON_A,SDL_CONTROLLER_BUTTON_B,SDL_CONTROLLER_BUTTON_X,SDL_CONTROLLER_BUTTON_Y,SDL_CONTROLLER_BUTTON_LEFTSHOULDER,SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,SDL_CONTROLLER_BUTTON_BACK,SDL_CONTROLLER_BUTTON_START,SDL_CONTROLLER_BUTTON_DPAD_UP,SDL_CONTROLLER_BUTTON_DPAD_DOWN,SDL_CONTROLLER_BUTTON_DPAD_LEFT,SDL_CONTROLLER_BUTTON_DPAD_RIGHT}};
#endif
static SDL_GameController *pads[2];
static wchar_t ini_file[32768], data_dir[32768];
static int menu, player, row, gamepad_page, capturing, filter, fullscreen, french, autofire;
static char status[80];
static Uint64 status_until;
static int gun_shape, gun_size = 3, gun_color, scope_turbo = 1;
static Rr16GunInput mouse_gun;
static const char *tr(const char *en, const char *fr) { return french ? fr : en; }

static void settings_path(void) {
    DWORD n = GetModuleFileNameW(NULL, data_dir, 32600);
    wchar_t *slash = n ? wcsrchr(data_dir, L'\\') : NULL;
    if (!slash) { ini_file[0] = 0; return; }
    *slash = 0;
    wcscpy_s(ini_file, 32768, data_dir);
    wcscat_s(data_dir, 32768, L"\\datas");
    wcscat_s(ini_file, 32768, L"\\datas\\Retro-Recomp.ini");
}

static void section(wchar_t *out, int p, bool pad) {
    swprintf_s(out, 64, RR16_SECTION L".%s.Player%d", pad ? L"Gamepad" : L"Keyboard", p + 1);
}

static void load_bindings(void) {
    /* Resolve letters after SDL video initialization, before loading physical
     * bindings saved by the user. W must mean W on AZERTY and QWERTY alike. */
    keys[0][A] = rr_keyboard_letter(SDLK_w, SDL_SCANCODE_W);
    keys[0][B] = rr_keyboard_letter(SDLK_x, SDL_SCANCODE_X);
#if RR16_MD
    keys[0][C] = rr_keyboard_letter(SDLK_c, SDL_SCANCODE_C);
#if RR_MD_SIX_BUTTONS
    keys[0][X] = rr_keyboard_letter(SDLK_a, SDL_SCANCODE_A);
    keys[0][Y] = rr_keyboard_letter(SDLK_s, SDL_SCANCODE_S);
    keys[0][Z] = rr_keyboard_letter(SDLK_d, SDL_SCANCODE_D);
#endif
#else
    keys[0][X] = rr_keyboard_letter(SDLK_a, SDL_SCANCODE_A);
    keys[0][Y] = rr_keyboard_letter(SDLK_s, SDL_SCANCODE_S);
    keys[0][L] = rr_keyboard_letter(SDLK_q, SDL_SCANCODE_Q);
    keys[0][R] = rr_keyboard_letter(SDLK_e, SDL_SCANCODE_E);
#endif
    settings_path();
    if (!ini_file[0]) return;
    rr_display_load(ini_file, RR16_SECTION L".Video", &filter, &fullscreen);
    wchar_t sec[64];
    for (int p = 0; p < 2; ++p) for (int mode = 0; mode < 2; ++mode) {
        section(sec, p, mode != 0);
        for (int a = 0; a < ACTIONS; ++a) {
            int old = mode ? buttons[p][a] : keys[p][a];
            int value = GetPrivateProfileIntW(sec, settings[a], old, ini_file);
            if (mode && value >= 0 && value < SDL_CONTROLLER_BUTTON_MAX) buttons[p][a] = (SDL_GameControllerButton)value;
            if (!mode && value > 0 && value < SDL_NUM_SCANCODES) keys[p][a] = (SDL_Scancode)value;
        }
    }
    wchar_t language[12];
    GetPrivateProfileStringW(L"Interface", L"language", L"en", language, 12, ini_file);
    french = wcscmp(language, L"fr") == 0;
    autofire = GetPrivateProfileIntW(L"Manettes", L"autofire", 0, ini_file) != 0;
    gun_shape = GetPrivateProfileIntW(RR16_SECTION L".Gun", L"shape", 0, ini_file) == 1;
    gun_size = GetPrivateProfileIntW(RR16_SECTION L".Gun", L"size", 3, ini_file);
    if (gun_size < 1 || gun_size > 12) gun_size = 3;
    gun_color = GetPrivateProfileIntW(RR16_SECTION L".Gun", L"color", 0, ini_file);
    if (gun_color < 0 || gun_color > 2) gun_color = 0;
    scope_turbo = GetPrivateProfileIntW(RR16_SECTION L".Gun", L"turbo", 1, ini_file) != 0;
}

static void gun_option(int direction) {
    if (row == 0) gun_shape = !gun_shape;
    if (row == 1) gun_size = (gun_size - 1 + direction + 12) % 12 + 1;
    if (row == 2) gun_color = (gun_color + direction + 3) % 3;
    if (row == 3) scope_turbo = !scope_turbo;
    if (!ini_file[0]) return;
    const wchar_t *labels[] = {L"shape", L"size", L"color", L"turbo"};
    int values[] = {gun_shape, gun_size, gun_color, scope_turbo};
    wchar_t value[16]; swprintf_s(value, 16, L"%d", values[row]);
    CreateDirectoryW(data_dir, NULL);
    WritePrivateProfileStringW(RR16_SECTION L".Gun", labels[row], value, ini_file);
}

static void store_binding(void) {
    if (!ini_file[0]) return;
    CreateDirectoryW(data_dir, NULL);
    wchar_t sec[64], value[16];
    section(sec, player, gamepad_page != 0);
    swprintf_s(value, 16, L"%d", gamepad_page ? buttons[player][row] : keys[player][row]);
    WritePrivateProfileStringW(sec, settings[row], value, ini_file);
}

static void open_pads(void) {
    for (int i = 0; i < 2; ++i) if (pads[i] && !SDL_GameControllerGetAttached(pads[i])) {
        SDL_GameControllerClose(pads[i]); pads[i] = NULL;
    }
    for (int i = 0; i < SDL_NumJoysticks(); ++i) if (SDL_IsGameController(i)) {
        SDL_JoystickID id = SDL_JoystickGetDeviceInstanceID(i);
        bool known = false;
        for (int p = 0; p < 2; ++p) if (pads[p] && SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pads[p])) == id) known = true;
        if (known) continue;
        for (int p = 0; p < 2; ++p) if (!pads[p]) { pads[p] = SDL_GameControllerOpen(i); break; }
    }
}

static uint16_t controller_input(int p, uint64_t frame) {
    const Uint8 *state = SDL_GetKeyboardState(NULL);
    uint16_t value = 0;
    for (int a = 0; a < ACTIONS; ++a) {
        if (state[keys[p][a]]) value |= bits[a];
        if (pads[p] && SDL_GameControllerGetButton(pads[p], buttons[p][a])) {
            if (!autofire || a > FACE_LAST || (((uint64_t)(frame * 80.0 * RR16_FRAME_SECONDS)) & 1) == 0) value |= bits[a];
        }
    }
    if (pads[p]) {
        Sint16 x = SDL_GameControllerGetAxis(pads[p], SDL_CONTROLLER_AXIS_LEFTX);
        Sint16 y = SDL_GameControllerGetAxis(pads[p], SDL_CONTROLLER_AXIS_LEFTY);
        if (x < -16000) value |= bits[LEFT]; else if (x > 16000) value |= bits[RIGHT];
        if (y < -16000) value |= bits[UP]; else if (y > 16000) value |= bits[DOWN];
    }
    if ((value & (bits[LEFT] | bits[RIGHT])) == (bits[LEFT] | bits[RIGHT])) value &= ~(bits[LEFT] | bits[RIGHT]);
    if ((value & (bits[UP] | bits[DOWN])) == (bits[UP] | bits[DOWN])) value &= ~(bits[UP] | bits[DOWN]);
    return value;
}

static void scale2x(const uint32_t *source, uint32_t *target) {
    int width = rr16_visible_width(), height = rr16_visible_height();
    for (int y = 0; y < height; ++y) for (int x = 0; x < width; ++x) {
        uint32_t e = source[y * RR16_WIDTH + x];
        uint32_t b = source[(y ? y - 1 : y) * RR16_WIDTH + x];
        uint32_t d = source[y * RR16_WIDTH + (x ? x - 1 : x)];
        uint32_t f = source[y * RR16_WIDTH + (x < (width - 1) ? x + 1 : x)];
        uint32_t h = source[(y < (height - 1) ? y + 1 : y) * RR16_WIDTH + x];
        uint32_t *out = target + (y * 2) * (RR16_WIDTH * 2) + x * 2;
        if (b != h && d != f) {
            out[0] = d == b ? d : e; out[1] = b == f ? f : e;
            out[(RR16_WIDTH * 2)] = d == h ? d : e; out[(RR16_WIDTH * 2 + 1)] = h == f ? f : e;
        } else out[0] = out[1] = out[(RR16_WIDTH * 2)] = out[(RR16_WIDTH * 2 + 1)] = e;
    }
}

static SDL_Rect game_rect(SDL_Renderer *renderer) {
    int w, h; SDL_GetRendererOutputSize(renderer, &w, &h);
    int width = rr16_visible_width(), height = rr16_visible_height();
    double factor = (double)w / width;
    if ((double)h / height < factor) factor = (double)h / height;
    if (fullscreen == 1) { int integer = (int)factor; factor = integer > 0 ? integer : 1; }
    SDL_Rect rect = { (w - (int)(width * factor)) / 2, (h - (int)(height * factor)) / 2,
                      (int)(width * factor), (int)(height * factor) };
    return rect;
}

static void sample_gun(SDL_Window *window, SDL_Renderer *renderer, uint16_t pad) {
    Rr16GunInput in = {.x = -1, .y = -1, .offscreen = true};
    int x, y, w, h, rw, rh;
    Uint32 buttons = SDL_GetMouseState(&x, &y);
    SDL_GetWindowSize(window, &w, &h);
    SDL_GetRendererOutputSize(renderer, &rw, &rh);
    SDL_Rect dst = game_rect(renderer);
    if (!menu && w > 0 && h > 0 &&
        (SDL_GetWindowFlags(window) & SDL_WINDOW_INPUT_FOCUS) &&
        (SDL_GetWindowFlags(window) & SDL_WINDOW_MOUSE_FOCUS)) {
        x = (int)((int64_t)x * rw / w); y = (int)((int64_t)y * rh / h);
        in.offscreen = x < dst.x || y < dst.y || x >= dst.x + dst.w || y >= dst.y + dst.h;
        if (!in.offscreen && dst.w > 0 && dst.h > 0) {
            in.x = (int)((int64_t)(x - dst.x) * rr16_visible_width() / dst.w);
            in.y = (int)((int64_t)(y - dst.y) * rr16_visible_height() / dst.h);
        }
        in.fire = (buttons & SDL_BUTTON_LMASK) != 0;
        in.aux = (buttons & SDL_BUTTON_RMASK) != 0;
        in.secondary = (buttons & SDL_BUTTON_MMASK) != 0;
        in.start = (pad & bits[START]) != 0;
        in.pause = in.secondary || in.start;
        in.turbo = scope_turbo != 0;
    }
    mouse_gun = in;
    rr16_gun_input(in);
    SDL_ShowCursor(in.offscreen || menu ? SDL_ENABLE : SDL_DISABLE);
}

static void draw_gun(SDL_Renderer *renderer, const SDL_Rect *dst) {
    if (!RR16_GUN || menu || mouse_gun.offscreen) return;
    int x = dst->x + (int)((mouse_gun.x + 0.5) * dst->w / rr16_visible_width());
    int y = dst->y + (int)((mouse_gun.y + 0.5) * dst->h / rr16_visible_height());
    int sx = (int)((double)gun_size * dst->w / rr16_visible_width());
    int sy = (int)((double)gun_size * dst->h / rr16_visible_height());
    if (sx < 1) sx = 1; if (sy < 1) sy = 1;
    SDL_RenderSetClipRect(renderer, dst);
    SDL_SetRenderDrawColor(renderer, gun_color == 2 ? 0 : 255, gun_color ? 255 : 0, gun_color == 1 ? 255 : 0, 255);
    if (gun_shape == 1) {
        SDL_Rect dot = {x - sx / 2, y - sy / 2, sx, sy}; SDL_RenderFillRect(renderer, &dot);
    } else {
        SDL_Rect horizontal = {x - sx, y - 1, sx * 2 + 1, 2};
        SDL_Rect vertical = {x - 1, y - sy, 2, sy * 2 + 1};
        SDL_RenderFillRect(renderer, &horizontal);
        SDL_RenderFillRect(renderer, &vertical);
    }
    SDL_RenderSetClipRect(renderer, NULL);
}

static void draw_menu(SDL_Renderer *ren) {
    if (!menu) return;
    int ox, oy, unit; rr_menu_layout(ren, &ox, &oy, &unit);
    rr_menu_begin(ren, ox, oy, unit);
#define RR16_TEXT(y,s) rr_menu_text(ren,ox,oy,unit,14,y,s,230,240,250)
    RR16_TEXT(15, menu == 1 ? tr("RetroRecomp - Help", "RetroRecomp - Aide") :
         menu == 2 ? tr("RetroRecomp - Controls", "RetroRecomp - Commandes") :
         menu == 4 ? tr("RetroRecomp - Gun", "RetroRecomp - Pistolet") : "RetroRecomp - Pause");
    if (menu == 1) {
        RR16_TEXT(42, tr("F1 Restart  F2 Controls", "F1 Recommencer  F2 Commandes"));
        RR16_TEXT(56, tr("F3 Filter  F4 Fullscreen", "F3 Filtre  F4 Plein ecran"));
        RR16_TEXT(70, tr("F6 Autofire  F7 Language", "F6 Tir auto  F7 Langue"));
        RR16_TEXT(84, tr("P Pause  H Help  Esc Quit", "P Pause  H Aide  Esc Quitter"));
#if !RR16_GUN && RR16_MD && RR_MD_SIX_BUTTONS
        RR16_TEXT(108, tr("Arrows; W/X/C: A/B/C; Enter: Start", "Fleches; W/X/C : A/B/C; Entree : Start"));
        RR16_TEXT(122, tr("A/S/D: X/Y/Z; Right Shift: Mode", "A/S/D : X/Y/Z; Maj droite : Mode"));
#elif !RR16_GUN && RR16_MD
        RR16_TEXT(108, tr("Arrows + W/X/C; Enter Start", "Fleches + W/X/C; Entree Start"));
        RR16_TEXT(122, tr("Two controllers supported", "Deux manettes disponibles"));
#elif !RR16_GUN
        RR16_TEXT(108, tr("Arrows + W/X/A/S; Q/E shoulders", "Fleches + W/X/A/S; Q/E gachettes"));
        RR16_TEXT(122, tr("Enter Start; Shift Select", "Entree Start; Maj Select"));
#endif
        if (RR16_GUN) {
            RR16_TEXT(108, tr("Mouse: aim | Left: fire", "Souris : viser | Gauche : tirer"));
            RR16_TEXT(122, RR16_GUN == RR_GUN_SCOPE ? tr("Right: cursor | Middle/Enter: gun pause", "Droit : curseur | Milieu/Entree : pause gun") :
                tr("Right: B | Middle: C | Enter: Start", "Droit : B | Milieu : C | Entree : Start"));
            RR16_TEXT(146, tr("F5: gun options | Gun on port 2", "F5 : viseur | Pistolet sur port 2"));
        } else RR16_TEXT(146, tr("Quick states: coming soon", "Sauvegardes rapides : a venir"));
        RR16_TEXT(160, rr16_audio_interpreted() ? tr("Sound CPU: interpreter fallback", "CPU audio : secours interprete") :
                                                tr("Sound CPU: native code", "CPU audio : code natif"));
    } else if (menu == 2) {
        char line[96];
        snprintf(line, sizeof(line), "Player %d  |  %s  |  Tab / Left-Right", player + 1,
                 gamepad_page ? "Gamepad" : "Keyboard");
        RR16_TEXT(38, line);
        for (int a = (row / 8) * 8; a < ACTIONS && a < (row / 8) * 8 + 8; ++a) {
            if (a == row) rr_menu_box(ren, ox, oy, unit, 12, 52 + (a % 8) * 13, 232, 12, 35, 74, 110, 255);
            const char *bound = gamepad_page ? SDL_GameControllerGetStringForButton(buttons[player][a]) :
                rr_keyboard_name(keys[player][a]);
            snprintf(line, sizeof(line), "%c %-7s %s", a == row ? '>' : ' ', names[a],
                     capturing && a == row ? tr("Press a control...", "Appuie sur une touche...") : bound);
            RR16_TEXT(53 + (a % 8) * 13, line);
        }
        RR16_TEXT(164, tr("Enter: remap | Esc: close", "Entree : attribuer | Esc : fermer"));
    } else if (menu == 4) {
        char line[100];
        const char *colors[] = {"Red / Rouge", "White / Blanc", "Green / Vert"};
        const int rows = RR16_GUN == RR_GUN_SCOPE ? 4 : 3;
        for (int i = 0; i < rows; ++i) {
            if (row == i) rr_menu_box(ren, ox, oy, unit, 12, 49 + 23 * i, 232, 20, 35, 74, 110, 255);
            if (i == 0) snprintf(line, sizeof line, "%s: %s", tr("Shape", "Forme"), gun_shape ? tr("Dot", "Point") : tr("Cross", "Croix"));
            if (i == 1) snprintf(line, sizeof line, "%s: %d", tr("Size", "Taille"), gun_size);
            if (i == 2) snprintf(line, sizeof line, "%s: %s", tr("Color", "Couleur"), colors[gun_color]);
            if (i == 3) snprintf(line, sizeof line, "Scope turbo: %s", scope_turbo ? "On" : "Off");
            RR16_TEXT(53 + 23 * i, line);
        }
        RR16_TEXT(164, tr("Arrows: change | Tab: controls", "Fleches : regler | Tab : commandes"));
    } else {
        RR16_TEXT(58, tr("Game paused", "Jeu en pause"));
        RR16_TEXT(83, tr("P or gamepad left-stick click: resume", "P ou clic stick gauche : reprendre"));
        RR16_TEXT(110, tr("H: help | F2: controls", "H : aide | F2 : commandes"));
    }
    if (status[0]) RR16_TEXT(177, status);
#undef RR16_TEXT
    rr_menu_end(ren);
}

static void pause_audio_output(SDL_AudioDeviceID audio, bool *playing) {
    if (!audio) return;
    SDL_PauseAudioDevice(audio, 1);
    SDL_ClearQueuedAudio(audio);
    *playing = false;
}

int rr16_sdl_main(const char *title, int scale) {
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | SDL_INIT_AUDIO) != 0) return 1;
    load_bindings();
    const char *test_limit = getenv("RETRORECOMP_HOST_TEST_FRAMES");
    unsigned test_frames = test_limit ? (unsigned)atoi(test_limit) : 0;
    const char *test_no_audio = getenv("RETRORECOMP_HOST_TEST_NO_AUDIO");
    bool video_clock_test = test_frames && test_no_audio && test_no_audio[0] == '1';
    wchar_t state_path[32768] = {0}; rr16_state_path(state_path, 32768);
    if (scale < 1) scale = 3;
    char caption[256];
    snprintf(caption, sizeof(caption), "%s | %s", title, "Native code");
    SDL_Window *win = SDL_CreateWindow(caption, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        RR16_WIDTH * scale, rr16_visible_height() * scale, SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI |
        (test_frames ? SDL_WINDOW_HIDDEN : 0));
    if (win && fullscreen && SDL_SetWindowFullscreen(win, SDL_WINDOW_FULLSCREEN_DESKTOP) != 0) fullscreen = 0;
    SDL_Renderer *ren = win ? SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED) : NULL;
    if (!ren && win) ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
    SDL_Texture *tex = ren ? SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
        SDL_TEXTUREACCESS_STREAMING, filter == 2 ? RR16_WIDTH * 2 : RR16_WIDTH, filter == 2 ? RR16_HEIGHT * 2 : RR16_HEIGHT) : NULL;
    uint32_t *upscaled = (uint32_t *)malloc(RR16_WIDTH * 2 * RR16_HEIGHT * 2 * sizeof(uint32_t));
    if (!tex || !upscaled) { free(upscaled); if (ren) SDL_DestroyRenderer(ren); if (win) SDL_DestroyWindow(win); return 1; }
    SDL_SetTextureScaleMode(tex, filter == 1 ? SDL_ScaleModeLinear : SDL_ScaleModeNearest);
    rr_menu_init(ren);
    SDL_AudioSpec want = {0}, have = {0};
    want.freq = 48000; want.format = AUDIO_S16SYS; want.channels = 2; want.samples = 512;
    SDL_AudioDeviceID audio = 0;
#if !RR16_MD
    /* A dummy audio device's callback timer is not a calibrated 48 kHz
     * oscillator. The explicit test-only mode isolates the video deadline;
     * guest APU/DSP execution and PCM consumption still run normally. */
    if (!video_clock_test) audio = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
#endif
    /* One guest frame is shorter than two device callbacks. Start with a
     * frame plus one device period, so a callback at an unlucky phase does
     * not exhaust the queue before the next frame can provide its sound.
     * This is output priming only; the guest DSP buffer is unchanged. */
    Uint32 audio_preroll = ((Uint32)(have.freq * RR16_FRAME_SECONDS) + have.samples) * 4;
    bool audio_playing = false;
    open_pads();
    const Uint64 frequency = SDL_GetPerformanceFrequency();
    Uint64 next = SDL_GetPerformanceCounter();
    const Uint64 test_started = next;
    uint64_t frame = 0;
    int title_state = -1;
    bool running = true;
    RrScanlineMask scanlines = {0};
    const char *test_filter = test_frames ? getenv("RETRORECOMP_HOST_TEST_FILTER") : NULL;
    if (test_filter && !strcmp(test_filter, "3")) filter = 3;
    while (running) {
        /* Preserve every produced block. If the host catches up after a
         * scheduling delay, wait for a little room before sampling inputs
         * and running the next frame instead of discarding ~17 ms of sound.
         * SDL drains whole device periods. Keep a guest frame plus one such
         * period before starting work: a fixed 20 ms threshold could lose
         * 10.7 ms in one callback and leave too little for a costly frame. */
        if (audio && audio_playing && !menu) {
            Uint64 until = SDL_GetTicks64() + 20;
            while (SDL_GetQueuedAudioSize(audio) > audio_preroll && SDL_GetTicks64() < until)
                SDL_Delay(1);
        }
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = false;
            if (event.type == SDL_CONTROLLERDEVICEADDED || event.type == SDL_CONTROLLERDEVICEREMOVED) open_pads();
            if (event.type == SDL_CONTROLLERBUTTONDOWN && menu == 2 && capturing && gamepad_page == 1) {
                buttons[player][row] = (SDL_GameControllerButton)event.cbutton.button;
                store_binding(); capturing = 0; status[0] = 0; continue;
            }
            if (event.type == SDL_CONTROLLERBUTTONDOWN && event.cbutton.button == SDL_CONTROLLER_BUTTON_LEFTSTICK) {
                menu = menu == 3 ? 0 : 3; status[0] = 0;
            }
            if (event.type == SDL_CONTROLLERBUTTONDOWN && event.cbutton.button == SDL_CONTROLLER_BUTTON_RIGHTSTICK &&
                    pads[0] && event.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pads[0]))) {
                rr16_reset(); pause_audio_output(audio, &audio_playing);
            }
            if (event.type != SDL_KEYDOWN || event.key.repeat) continue;
            SDL_Scancode key = event.key.keysym.scancode;
            if (menu == 2 && capturing) {
                if (key == SDL_SCANCODE_ESCAPE) capturing = 0;
                else if (!gamepad_page && key > SDL_SCANCODE_UNKNOWN && key < SDL_NUM_SCANCODES &&
                         !(key >= SDL_SCANCODE_F1 && key <= SDL_SCANCODE_F12) &&
                         key != SDL_SCANCODE_H && key != SDL_SCANCODE_P) {
                    keys[player][row] = key; store_binding(); capturing = 0;
                }
                continue;
            }
            if (key == SDL_SCANCODE_ESCAPE) { if (menu) menu = 0; else running = false; }
            else if (key == SDL_SCANCODE_F1) {
                rr16_reset(); pause_audio_output(audio, &audio_playing);
            } else if (key == SDL_SCANCODE_H) menu = menu == 1 ? 0 : 1;
            else if (key == SDL_SCANCODE_P) menu = menu == 3 ? 0 : 3;
            else if (key == SDL_SCANCODE_F2) menu = menu == 2 ? 0 : 2;
            else if (key == SDL_SCANCODE_F3) {
                filter = (filter + 1) % 4;
                SDL_DestroyTexture(tex);
                tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING,
                    filter == 2 ? RR16_WIDTH * 2 : RR16_WIDTH, filter == 2 ? RR16_HEIGHT * 2 : RR16_HEIGHT);
                if (!tex) { running = false; break; }
                SDL_SetTextureScaleMode(tex, filter == 1 ? SDL_ScaleModeLinear : SDL_ScaleModeNearest);
                if (!rr_display_save(ini_file, data_dir, RR16_SECTION L".Video", L"filter", filter)) snprintf(status, sizeof(status), "%s", tr("Config unavailable", "Config inaccessible"));
            } else if (key == SDL_SCANCODE_F4) {
                int changed=rr_display_cycle(win,&fullscreen,ini_file,data_dir,RR16_SECTION L".Video");
                if (changed<0) snprintf(status,sizeof(status),"%s",tr("Config unavailable","Config inaccessible"));
            } else if (key == SDL_SCANCODE_F5 && RR16_GUN) {
                menu = menu == 4 ? 0 : 4; row = 0; capturing = 0;
            } else if (key == SDL_SCANCODE_F6) {
                autofire = !autofire;
                if (ini_file[0]) { CreateDirectoryW(data_dir, NULL);
                    WritePrivateProfileStringW(L"Manettes", L"autofire", autofire ? L"1" : L"0", ini_file); }
            }
            else if (key == SDL_SCANCODE_F7) {
                french = !french;
                if (ini_file[0]) { CreateDirectoryW(data_dir, NULL);
                    WritePrivateProfileStringW(L"Interface", L"language", french ? L"fr" : L"en", ini_file); }
            } else if (key == SDL_SCANCODE_F8 || key == SDL_SCANCODE_F9) {
                bool load = key == SDL_SCANCODE_F9;
                bool ok = rr16_state_file(state_path, load);
                const char *message = ok ? (load ? tr("Quick state loaded", "Partie chargee") : tr("Quick state saved", "Partie sauvegardee")) :
                    (load ? tr("No compatible quick state to load", "Aucune sauvegarde compatible") : tr("Cannot save game state", "Impossible de sauvegarder"));
                snprintf(status, sizeof(status), "%s", message);
                status_until = SDL_GetTicks64() + 1800;
                if (ok) { menu = 0; capturing = 0; }
                if (ok && load) { pause_audio_output(audio, &audio_playing); next = SDL_GetPerformanceCounter(); }
            } else if (menu == 4) {
                int rows = RR16_GUN == RR_GUN_SCOPE ? 4 : 3;
                if (key == SDL_SCANCODE_TAB) { menu = 2; gamepad_page = 0; row = 0; capturing = 0; }
                else if (key == SDL_SCANCODE_UP) row = (row + rows - 1) % rows;
                else if (key == SDL_SCANCODE_DOWN) row = (row + 1) % rows;
                else if (key == SDL_SCANCODE_LEFT) gun_option(-1);
                else if (key == SDL_SCANCODE_RIGHT || key == SDL_SCANCODE_RETURN) gun_option(1);
            } else if (menu == 2) {
                if (key == SDL_SCANCODE_TAB) {
                    if (gamepad_page && RR16_GUN) { menu = 4; gamepad_page = 0; }
                    else gamepad_page = !gamepad_page;
                    row = 0; capturing = 0;
                }
                else if (key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT) player = !player;
                else if (key == SDL_SCANCODE_UP) row = (row + ACTIONS - 1) % ACTIONS;
                else if (key == SDL_SCANCODE_DOWN) row = (row + 1) % ACTIONS;
                else if (key == SDL_SCANCODE_RETURN) capturing = 1;
            }
        }
        if (!running) break;
        rr16_pause(menu != 0);
        uint16_t pad1 = controller_input(0, frame);
        if (RR16_GUN) sample_gun(win, ren, pad1);
        if (!menu) {
            if (!rr16_frame(pad1, RR16_GUN ? 0 : controller_input(1, frame))) { running = false; break; }
            ++frame;
            int16_t pcm[4096]; size_t n = rr16_audio(pcm, 4096);
            if (n && audio) {
                if (SDL_QueueAudio(audio, pcm, (Uint32)(n * sizeof(int16_t))) != 0) {
                    SDL_CloseAudioDevice(audio); audio = 0; audio_playing = false;
                } else if (!audio_playing && SDL_GetQueuedAudioSize(audio) >= audio_preroll) {
                    SDL_PauseAudioDevice(audio, 0); audio_playing = true;
                }
            }
            if (test_frames && frame >= test_frames) running = false;
        } else if (audio_playing) pause_audio_output(audio, &audio_playing);
        if (filter == 2) { scale2x(rr16_pixels(), upscaled); SDL_UpdateTexture(tex, NULL, upscaled, RR16_WIDTH * 2 * 4); }
        else SDL_UpdateTexture(tex, NULL, rr16_pixels(), RR16_WIDTH * 4);
        SDL_Rect dst = game_rect(ren);
        SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
        int texture_scale = filter == 2 ? 2 : 1;
        SDL_Rect source = {0, 0, rr16_visible_width() * texture_scale, rr16_visible_height() * texture_scale};
        SDL_RenderCopy(ren, tex, &source, &dst);
        if (filter == 3) rr_scanlines_draw(ren, &scanlines, &dst, rr16_visible_height());
        draw_gun(ren, &dst);

        int current_title_state = (rr16_interpreted() || rr16_audio_interpreted() ? 1 : 0);
        if (current_title_state != title_state) {
            snprintf(caption, sizeof(caption), "%s | %s", title,
                     current_title_state ? "Interpreter fallback" : "Native code");
            SDL_SetWindowTitle(win, caption);
            title_state = current_title_state;
        }
        draw_menu(ren);
        if (!menu && status[0] && SDL_GetTicks64() < status_until) {
            int ox, oy, unit; rr_menu_layout(ren, &ox, &oy, &unit);
            rr_menu_text(ren, ox, oy, unit, 8, 183, status, 240, 240, 240);
        }
        SDL_RenderPresent(ren);
        Uint64 now = SDL_GetPerformanceCounter();
        if (menu) { next = now; SDL_Delay(16); continue; }
        next += (Uint64)(RR16_FRAME_SECONDS * frequency);
        if (audio && audio_playing) {
            /* Video and the sound device have independent clocks. Do not
             * sleep through the remaining audio reserve: recover the lead
             * before the next guest frame instead of inserting silence or
             * making the DSP run ahead. Retain the normal video deadline
             * whenever the device queue has enough sound. */
            Uint32 queued = SDL_GetQueuedAudioSize(audio);
            Uint64 spare = queued > audio_preroll ? queued - audio_preroll : 0;
            Uint64 audio_deadline = now + spare * frequency / ((Uint64)have.freq * 4);
            if (next > audio_deadline) next = audio_deadline;
        }
        if (next > now) {
            Uint32 ms = (Uint32)((next - now) * 1000 / frequency);
            if (ms > 1) SDL_Delay(ms - 1);
            while (SDL_GetPerformanceCounter() < next) {}
        } else if (now - next > frequency / 4) next = now;
    }
    if (test_frames) {
        double elapsed = (double)(SDL_GetPerformanceCounter() - test_started) / frequency;
        fprintf(stderr, "{\"host_frames\":%llu,\"wall_seconds\":%.6f,\"expected_seconds\":%.6f,"
                "\"measured_fps\":%.6f,\"target_fps\":%.6f,\"video_clock_only\":%s}\n",
                frame, elapsed, frame * RR16_FRAME_SECONDS, frame / elapsed, 1.0 / RR16_FRAME_SECONDS,
                video_clock_test ? "true" : "false");
    }
    if (audio) SDL_CloseAudioDevice(audio);
    for (int p = 0; p < 2; ++p) if (pads[p]) SDL_GameControllerClose(pads[p]);
    rr_menu_shutdown(); free(upscaled); if (tex) SDL_DestroyTexture(tex);
    rr_scanlines_destroy(&scanlines);
    SDL_ShowCursor(SDL_ENABLE);
    SDL_DestroyRenderer(ren); SDL_DestroyWindow(win); return 0;
}
