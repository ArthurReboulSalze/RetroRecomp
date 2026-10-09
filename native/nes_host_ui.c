/* RetroRecomp's NES presentation host. The linked NESRecomp machine retains
 * its separate PolyForm Noncommercial terms; this UI is original code. */
#define SDL_MAIN_HANDLED
#include <SDL.h>
#include <windows.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include "cyc_core.h"
#include "cyc_run.h"
#include "retro_menu.h"
#include "retro_keyboard.h"
#include "display_settings.h"
#include "scanline_sdl.h"
#include "retro_nes.h"

enum { A, B, SELECT, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const uint8_t bits[ACTIONS] = {128, 64, 32, 16, 8, 4, 2, 1};
static const char *names[ACTIONS] = {"A", "B", "Select", "Start", "Up", "Down", "Left", "Right"};
static const wchar_t *settings[ACTIONS] = {L"A", L"B", L"Select", L"Start", L"Up", L"Down", L"Left", L"Right"};
static SDL_Scancode keys[2][ACTIONS] = {
    {SDL_SCANCODE_W, SDL_SCANCODE_X, SDL_SCANCODE_RSHIFT, SDL_SCANCODE_RETURN,
     SDL_SCANCODE_UP, SDL_SCANCODE_DOWN, SDL_SCANCODE_LEFT, SDL_SCANCODE_RIGHT},
    {SDL_SCANCODE_KP_8, SDL_SCANCODE_KP_9, SDL_SCANCODE_KP_4, SDL_SCANCODE_KP_7,
     SDL_SCANCODE_KP_5, SDL_SCANCODE_KP_2, SDL_SCANCODE_KP_1, SDL_SCANCODE_KP_3}
};
static SDL_GameControllerButton buttons[2][ACTIONS] = {
    {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_BACK,
     SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
     SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT},
    {SDL_CONTROLLER_BUTTON_A, SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_BACK,
     SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_DPAD_UP, SDL_CONTROLLER_BUTTON_DPAD_DOWN,
     SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT}
};
static SDL_GameController *pads[2];
static wchar_t ini_file[32768], data_dir[32768];
static int menu, player, row, gamepad_page, capturing, filter, fullscreen, french, autofire;
static char status[80];
static Uint64 status_until;
static int gun_x = -1, gun_y = -1, gun_shape, gun_size = 3, gun_color;

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
    swprintf_s(out, 64, L"NES.%s.Player%d", pad ? L"Gamepad" : L"Keyboard", p + 1);
}

static void load_bindings(void) {
    keys[0][A] = rr_keyboard_letter(SDLK_w, SDL_SCANCODE_W);
    keys[0][B] = rr_keyboard_letter(SDLK_x, SDL_SCANCODE_X);
    settings_path();
    if (!ini_file[0]) return;
    rr_display_load(ini_file, L"NES.Video", &filter, &fullscreen);
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
    gun_shape = GetPrivateProfileIntW(L"NES.Zapper", L"shape", 0, ini_file) == 1;
    gun_size = (int)GetPrivateProfileIntW(L"NES.Zapper", L"size", 3, ini_file);
    if (gun_size < 1 || gun_size > 8) gun_size = 3;
    gun_color = (int)GetPrivateProfileIntW(L"NES.Zapper", L"color", 0, ini_file);
    if (gun_color < 0 || gun_color > 2) gun_color = 0;
}

static void store_gun(void) {
    if (!ini_file[0]) return;
    CreateDirectoryW(data_dir, NULL);
    wchar_t value[16];
    swprintf_s(value, 16, L"%d", gun_shape); WritePrivateProfileStringW(L"NES.Zapper", L"shape", value, ini_file);
    swprintf_s(value, 16, L"%d", gun_size); WritePrivateProfileStringW(L"NES.Zapper", L"size", value, ini_file);
    swprintf_s(value, 16, L"%d", gun_color); WritePrivateProfileStringW(L"NES.Zapper", L"color", value, ini_file);
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

static uint8_t controller_input(int p, uint64_t frame) {
    const Uint8 *state = SDL_GetKeyboardState(NULL);
    uint8_t value = 0;
    for (int a = 0; a < ACTIONS; ++a) {
        if (state[keys[p][a]]) value |= bits[a];
        if (pads[p] && SDL_GameControllerGetButton(pads[p], buttons[p][a])) {
            if (!autofire || a > B || (((uint64_t)(frame * 80.0 * RR_FRAME_SECONDS)) & 1) == 0) value |= bits[a];
        }
    }
    if (pads[p]) {
        Sint16 x = SDL_GameControllerGetAxis(pads[p], SDL_CONTROLLER_AXIS_LEFTX);
        Sint16 y = SDL_GameControllerGetAxis(pads[p], SDL_CONTROLLER_AXIS_LEFTY);
        if (x < -16000) value |= bits[LEFT]; else if (x > 16000) value |= bits[RIGHT];
        if (y < -16000) value |= bits[UP]; else if (y > 16000) value |= bits[DOWN];
    }
    if ((value & 12) == 12) value &= ~12;
    if ((value & 3) == 3) value &= ~3;
    return value;
}

static void scale2x(const uint32_t *source, uint32_t *target) {
    for (int y = 0; y < 240; ++y) for (int x = 0; x < 256; ++x) {
        uint32_t e = source[y * 256 + x];
        uint32_t b = source[(y ? y - 1 : y) * 256 + x];
        uint32_t d = source[y * 256 + (x ? x - 1 : x)];
        uint32_t f = source[y * 256 + (x < 255 ? x + 1 : x)];
        uint32_t h = source[(y < 239 ? y + 1 : y) * 256 + x];
        uint32_t *out = target + (y * 2) * 512 + x * 2;
        if (b != h && d != f) {
            out[0] = d == b ? d : e; out[1] = b == f ? f : e;
            out[512] = d == h ? d : e; out[513] = h == f ? f : e;
        } else out[0] = out[1] = out[512] = out[513] = e;
    }
}

static SDL_Rect game_rect(SDL_Renderer *renderer) {
    int w, h; SDL_GetRendererOutputSize(renderer, &w, &h);
    double factor = (double)w / 256.0;
    if ((double)h / 240.0 < factor) factor = (double)h / 240.0;
    if (fullscreen == 1) { int integer = (int)factor; factor = integer > 0 ? integer : 1; }
    SDL_Rect rect = { (w - (int)(256 * factor)) / 2, (h - (int)(240 * factor)) / 2,
                      (int)(256 * factor), (int)(240 * factor) };
    return rect;
}

static void sample_gun(SDL_Window *win, SDL_Renderer *ren) {
    if (!RR_NES_ZAPPER) return;
    int x, y, w, h, rw, rh;
    Uint32 pressed = SDL_GetMouseState(&x, &y);
    SDL_GetWindowSize(win, &w, &h); SDL_GetRendererOutputSize(ren, &rw, &rh);
    SDL_Rect r = game_rect(ren);
    x = w ? x * rw / w : -1; y = h ? y * rh / h : -1;
    bool outside = x < r.x || y < r.y || x >= r.x + r.w || y >= r.y + r.h ||
        !(SDL_GetWindowFlags(win) & SDL_WINDOW_MOUSE_FOCUS);
    gun_x = outside ? -1 : (x - r.x) * 256 / r.w;
    gun_y = outside ? -1 : (y - r.y) * 240 / r.h;
    bool right = (pressed & SDL_BUTTON_RMASK) != 0;
    rr_nes_zapper_aim(gun_x, gun_y, (pressed & SDL_BUTTON_LMASK) != 0 || right, outside || right);
}

static void draw_gun(SDL_Renderer *ren, SDL_Rect r) {
    if (!RR_NES_ZAPPER || menu || gun_x < 0 || gun_y < 0) return;
    Uint8 red = gun_color == 2 ? 0 : 255;
    Uint8 green = gun_color == 0 ? 0 : 255, blue = gun_color == 1 ? 255 : 0;
    SDL_SetRenderDrawColor(ren, red, green, blue, 255);
    int px = r.w / 256; if (px < 1) px = 1;
    int py = r.h / 240; if (py < 1) py = 1;
    int x = r.x + gun_x * r.w / 256, y = r.y + gun_y * r.h / 240;
    SDL_RenderSetClipRect(ren, &r);
    SDL_Rect horizontal = {x - gun_size * px, y, (2 * gun_size + 1) * px, py};
    if (gun_shape) {
        horizontal.y -= gun_size * py;
        horizontal.h = (2 * gun_size + 1) * py;
    }
    SDL_RenderFillRect(ren, &horizontal);
    if (!gun_shape) {
        SDL_Rect vertical = {x, y - gun_size * py, px, (2 * gun_size + 1) * py};
        SDL_RenderFillRect(ren, &vertical);
    }
    SDL_RenderSetClipRect(ren, NULL);
}

static void draw_menu(SDL_Renderer *ren) {
    if (!menu) return;
    int ox, oy, unit; rr_menu_layout(ren, &ox, &oy, &unit);
    rr_menu_begin(ren, ox, oy, unit);
#define RR_NES_TEXT(y,s) rr_menu_text(ren,ox,oy,unit,14,y,s,230,240,250)
    RR_NES_TEXT(15, menu == 1 ? tr("RetroRecomp - Help", "RetroRecomp - Aide") :
         menu == 2 ? tr("RetroRecomp - Controls", "RetroRecomp - Commandes") : "RetroRecomp - Pause");
    if (menu == 1) {
        RR_NES_TEXT(42, tr("F1 Restart  F2 Controls", "F1 Recommencer  F2 Commandes"));
        RR_NES_TEXT(56, tr("F3 Filter  F4 Fullscreen", "F3 Filtre  F4 Plein ecran"));
        RR_NES_TEXT(70, tr("F6 Autofire  F7 Language", "F6 Tir auto  F7 Langue"));
        RR_NES_TEXT(84, tr("P Pause  H Help  Esc Quit", "P Pause  H Aide  Esc Quitter"));
        RR_NES_TEXT(108, tr("NES: arrows + W/X; Enter Start", "NES : fleches + W/X; Entree Start"));
        RR_NES_TEXT(122, tr("Shift Select; two controllers", "Maj Select; deux manettes"));
        RR_NES_TEXT(146, tr("F8 Save state  F9 Load state", "F8 Sauvegarder  F9 Charger"));
        if (RR_NES_ZAPPER) {
            RR_NES_TEXT(160, tr("Mouse: aim/fire; right: offscreen", "Souris : viser/tirer; droit : hors ecran"));
            RR_NES_TEXT(96, tr("F5 Zapper options", "F5 Options du Zapper"));
        }
    } else if (menu == 2 && gamepad_page == 2) {
        char line[96];
        RR_NES_TEXT(38, tr("Zapper | Tab: controls", "Zapper | Tab : commandes"));
        const char *labels[] = {tr("Shape", "Forme"), tr("Size", "Taille"), tr("Color", "Couleur")};
        const char *colors[] = {tr("Red", "Rouge"), tr("White", "Blanc"), tr("Green", "Vert")};
        for (int a = 0; a < 3; a++) {
            char size[16]; snprintf(size, sizeof(size), "%d", gun_size);
            const char *value = a == 0 ? (gun_shape ? tr("Dot", "Point") : tr("Cross", "Croix")) : a == 1 ? size : colors[gun_color];
            if (row == a) rr_menu_box(ren, ox, oy, unit, 12, 52 + a * 23, 232, 20, 35, 74, 110, 255);
            snprintf(line, sizeof(line), "%c %s: %s", row == a ? '>' : ' ', labels[a], value);
            RR_NES_TEXT(58 + a * 23, line);
        }
        RR_NES_TEXT(150, tr("Up/Down: select | Left/Right: change", "Haut/Bas : choisir | Gauche/Droite : changer"));
    } else if (menu == 2) {
        char line[96];
        snprintf(line, sizeof(line), "Player %d  |  %s  |  Tab / Left-Right", player + 1,
                 gamepad_page ? "Gamepad" : "Keyboard");
        RR_NES_TEXT(38, line);
        for (int a = 0; a < ACTIONS; ++a) {
            if (a == row) rr_menu_box(ren, ox, oy, unit, 12, 52 + a * 13, 232, 12, 35, 74, 110, 255);
            const char *bound = gamepad_page ? SDL_GameControllerGetStringForButton(buttons[player][a]) :
                rr_keyboard_name(keys[player][a]);
            snprintf(line, sizeof(line), "%c %-7s %s", a == row ? '>' : ' ', names[a],
                     capturing && a == row ? tr("Press a control...", "Appuie sur une touche...") : bound);
            RR_NES_TEXT(53 + a * 13, line);
        }
        RR_NES_TEXT(164, tr("Enter: remap | Esc: close", "Entree : attribuer | Esc : fermer"));
    } else {
        RR_NES_TEXT(58, tr("Game paused", "Jeu en pause"));
        RR_NES_TEXT(83, tr("P or gamepad left-stick click: resume", "P ou clic stick gauche : reprendre"));
        RR_NES_TEXT(110, tr("H: help | F2: controls", "H : aide | F2 : commandes"));
    }
    if (status[0]) RR_NES_TEXT(177, status);
#undef RR_NES_TEXT
    rr_menu_end(ren);
}

int cyc_sdl_main(const char *title, int scale) {
    SDL_SetMainReady();
    if (SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMECONTROLLER | SDL_INIT_AUDIO) != 0) return 1;
    load_bindings();
    wchar_t state_path[32768]; rr_nes_state_path(state_path, 32768);
    if (scale < 1) scale = 3;
    char caption[256];
    snprintf(caption, sizeof(caption), "%s | %s", title, "Native code");
    SDL_Window *win = SDL_CreateWindow(caption, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        256 * scale, 240 * scale, SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    if (win && fullscreen && SDL_SetWindowFullscreen(win, SDL_WINDOW_FULLSCREEN_DESKTOP) != 0) fullscreen = 0;
    SDL_Renderer *ren = win ? SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED) : NULL;
    if (!ren && win) ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
    SDL_Texture *tex = ren ? SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
        SDL_TEXTUREACCESS_STREAMING, filter == 2 ? 512 : 256, filter == 2 ? 480 : 240) : NULL;
    uint32_t *upscaled = (uint32_t *)malloc(512 * 480 * sizeof(uint32_t));
    if (!tex || !upscaled) { free(upscaled); if (ren) SDL_DestroyRenderer(ren); if (win) SDL_DestroyWindow(win); SDL_Quit(); return 1; }
    SDL_SetTextureScaleMode(tex, filter == 1 ? SDL_ScaleModeLinear : SDL_ScaleModeNearest);
    rr_menu_init(ren);
    SDL_AudioSpec want = {0}, have = {0};
    want.freq = 48000; want.format = AUDIO_S16SYS; want.channels = 1; want.samples = 512;
    SDL_AudioDeviceID audio = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
    if (audio && cyc_audio_enable(have.freq)) SDL_PauseAudioDevice(audio, 0);
    open_pads();
    const Uint64 frequency = SDL_GetPerformanceFrequency();
    Uint64 next = SDL_GetPerformanceCounter();
    uint64_t frame = 0;
    int title_state = french ? 2 : 0;
    bool running = true;
    RrScanlineMask scanlines = {0};
    while (running) {
        SDL_Event event;
        while (SDL_PollEvent(&event)) {
            if (event.type == SDL_QUIT) running = false;
            if (event.type == SDL_CONTROLLERDEVICEADDED || event.type == SDL_CONTROLLERDEVICEREMOVED) open_pads();
            if (event.type == SDL_CONTROLLERBUTTONDOWN && menu == 2 && capturing && gamepad_page) {
                buttons[player][row] = (SDL_GameControllerButton)event.cbutton.button;
                store_binding(); capturing = 0; status[0] = 0; continue;
            }
            if (event.type == SDL_CONTROLLERBUTTONDOWN && event.cbutton.button == SDL_CONTROLLER_BUTTON_LEFTSTICK) {
                menu = menu == 3 ? 0 : 3; status[0] = 0;
            }
            if (event.type == SDL_CONTROLLERBUTTONDOWN && event.cbutton.button == SDL_CONTROLLER_BUTTON_RIGHTSTICK &&
                    pads[0] && event.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pads[0]))) {
                cyc_power_on(0); cyc_run_power_on(); if (audio) SDL_ClearQueuedAudio(audio);
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
                cyc_power_on(0); cyc_run_power_on(); if (audio) SDL_ClearQueuedAudio(audio);
            } else if (key == SDL_SCANCODE_H) menu = menu == 1 ? 0 : 1;
            else if (key == SDL_SCANCODE_P) menu = menu == 3 ? 0 : 3;
            else if (key == SDL_SCANCODE_F2) menu = menu == 2 ? 0 : 2;
            else if (key == SDL_SCANCODE_F3) {
                filter = (filter + 1) % 4;
                SDL_DestroyTexture(tex);
                tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING,
                    filter == 2 ? 512 : 256, filter == 2 ? 480 : 240);
                if (!tex) { running = false; break; }
                SDL_SetTextureScaleMode(tex, filter == 1 ? SDL_ScaleModeLinear : SDL_ScaleModeNearest);
                if (!rr_display_save(ini_file, data_dir, L"NES.Video", L"filter", filter)) snprintf(status, sizeof(status), "%s", tr("Config unavailable", "Config inaccessible"));
            } else if (key == SDL_SCANCODE_F4) {
                int changed=rr_display_cycle(win,&fullscreen,ini_file,data_dir,L"NES.Video");
                if (changed<0) snprintf(status,sizeof(status),"%s",tr("Config unavailable","Config inaccessible"));
            } else if (key == SDL_SCANCODE_F5 && RR_NES_ZAPPER) {
                menu = 2; gamepad_page = 2; row = capturing = 0;
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
                bool ok = rr_nes_state_file(state_path, load);
                const char *message = ok ? (load ? tr("Quick state loaded", "Partie chargee") : tr("Quick state saved", "Partie sauvegardee")) :
                    (load ? tr("No compatible quick state to load", "Aucune sauvegarde compatible") : tr("Unable to save quick state", "Impossible de sauvegarder"));
                snprintf(status, sizeof(status), "%s", message);
                status_until = SDL_GetTicks64() + 1800;
                if (ok) { menu = 0; capturing = 0; }
                if (ok && load) { if (audio) SDL_ClearQueuedAudio(audio); next = SDL_GetPerformanceCounter(); }
            } else if (menu == 2) {
                if (key == SDL_SCANCODE_TAB) { gamepad_page = (gamepad_page + 1) % (RR_NES_ZAPPER ? 3 : 2); row = 0; }
                else if (gamepad_page == 2) {
                    if (key == SDL_SCANCODE_UP) row = (row + 2) % 3;
                    else if (key == SDL_SCANCODE_DOWN) row = (row + 1) % 3;
                    else if (key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT || key == SDL_SCANCODE_RETURN) {
                        int delta = key == SDL_SCANCODE_LEFT ? -1 : 1;
                        if (row == 0) gun_shape = !gun_shape;
                        else if (row == 1) gun_size = (gun_size - 1 + delta + 8) % 8 + 1;
                        else gun_color = (gun_color + delta + 3) % 3;
                        store_gun();
                    }
                }
                else if (key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT) player = !player;
                else if (key == SDL_SCANCODE_UP) row = (row + ACTIONS - 1) % ACTIONS;
                else if (key == SDL_SCANCODE_DOWN) row = (row + 1) % ACTIONS;
                else if (key == SDL_SCANCODE_RETURN) capturing = 1;
            }
        }
        if (!running) break;
        SDL_ShowCursor(RR_NES_ZAPPER && !menu ? SDL_DISABLE : SDL_ENABLE);
        if (!menu) {
            sample_gun(win, ren);
            cyc_set_controller(0, controller_input(0, frame));
            cyc_set_controller(1, controller_input(1, frame));
            cyc_run_frame(); ++frame;
            int16_t pcm[4096]; size_t n;
            while ((n = cyc_audio_read(pcm, 4096)) > 0)
                if (audio && SDL_GetQueuedAudioSize(audio) < (Uint32)(have.freq / 50) * 2)
                    SDL_QueueAudio(audio, pcm, (Uint32)(n * sizeof(int16_t)));
        } else if (audio) SDL_ClearQueuedAudio(audio);
        if (filter == 2) { scale2x(cyc_frame_argb(), upscaled); SDL_UpdateTexture(tex, NULL, upscaled, 512 * 4); }
        else SDL_UpdateTexture(tex, NULL, cyc_frame_argb(), 256 * 4);
        SDL_Rect dst = game_rect(ren);
        SDL_SetRenderDrawColor(ren, 0, 0, 0, 255); SDL_RenderClear(ren);
        SDL_RenderCopy(ren, tex, NULL, &dst);
        if (filter == 3) rr_scanlines_draw(ren, &scanlines, &dst, 240);
        draw_gun(ren, dst);
        int current_title_state = (cyc_run_interp_rom_cycles || cyc_run_interp_ram_cycles || cyc_run_interp_other_cycles ? 1 : 0);
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
        next += (Uint64)(RR_FRAME_SECONDS * frequency);
        if (next > now) {
            Uint32 ms = (Uint32)((next - now) * 1000 / frequency);
            if (ms > 1) SDL_Delay(ms - 1);
            while (SDL_GetPerformanceCounter() < next) {}
        } else if (now - next > frequency / 4) next = now;
    }
    if (audio) SDL_CloseAudioDevice(audio);
    for (int p = 0; p < 2; ++p) if (pads[p]) SDL_GameControllerClose(pads[p]);
    rr_scanlines_destroy(&scanlines);
    rr_menu_shutdown(); free(upscaled); if (tex) SDL_DestroyTexture(tex);
    SDL_DestroyRenderer(ren); SDL_DestroyWindow(win); SDL_Quit(); return 0;
}
