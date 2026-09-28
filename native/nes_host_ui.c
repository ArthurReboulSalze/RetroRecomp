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

enum { A, B, SELECT, START, UP, DOWN, LEFT, RIGHT, ACTIONS };
static const uint8_t bits[ACTIONS] = {128, 64, 32, 16, 8, 4, 2, 1};
static const char *names[ACTIONS] = {"A", "B", "Select", "Start", "Up", "Down", "Left", "Right"};
static const wchar_t *settings[ACTIONS] = {L"A", L"B", L"Select", L"Start", L"Up", L"Down", L"Left", L"Right"};
static SDL_Scancode keys[2][ACTIONS] = {
    {SDL_SCANCODE_Z, SDL_SCANCODE_X, SDL_SCANCODE_RSHIFT, SDL_SCANCODE_RETURN,
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
    settings_path();
    if (!ini_file[0]) return;
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
            if (!autofire || a > B || ((frame * 80 / 60) & 1) == 0) value |= bits[a];
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
        RR_NES_TEXT(108, tr("NES: arrows + Z/X; Enter Start", "NES : fleches + Z/X; Entree Start"));
        RR_NES_TEXT(122, tr("Shift Select; two controllers", "Maj Select; deux manettes"));
        RR_NES_TEXT(146, tr("F8/F9 states: not yet available", "F8/F9 etats : pas encore dispo"));
    } else if (menu == 2) {
        char line[96];
        snprintf(line, sizeof(line), "Player %d  |  %s  |  Tab / Left-Right", player + 1,
                 gamepad_page ? "Gamepad" : "Keyboard");
        RR_NES_TEXT(38, line);
        for (int a = 0; a < ACTIONS; ++a) {
            if (a == row) rr_menu_box(ren, ox, oy, unit, 12, 52 + a * 13, 232, 12, 35, 74, 110, 255);
            const char *bound = gamepad_page ? SDL_GameControllerGetStringForButton(buttons[player][a]) :
                SDL_GetScancodeName(keys[player][a]);
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
    if (scale < 1) scale = 3;
    SDL_Window *win = SDL_CreateWindow(title, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
        256 * scale, 240 * scale, SDL_WINDOW_RESIZABLE | SDL_WINDOW_ALLOW_HIGHDPI);
    SDL_Renderer *ren = win ? SDL_CreateRenderer(win, -1, SDL_RENDERER_ACCELERATED) : NULL;
    if (!ren && win) ren = SDL_CreateRenderer(win, -1, SDL_RENDERER_SOFTWARE);
    SDL_Texture *tex = ren ? SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
        SDL_TEXTUREACCESS_STREAMING, 256, 240) : NULL;
    uint32_t *upscaled = (uint32_t *)malloc(512 * 480 * sizeof(uint32_t));
    if (!tex || !upscaled) { free(upscaled); if (ren) SDL_DestroyRenderer(ren); if (win) SDL_DestroyWindow(win); SDL_Quit(); return 1; }
    rr_menu_init(ren);
    SDL_AudioSpec want = {0}, have = {0};
    want.freq = 48000; want.format = AUDIO_S16SYS; want.channels = 1; want.samples = 512;
    SDL_AudioDeviceID audio = SDL_OpenAudioDevice(NULL, 0, &want, &have, 0);
    if (audio && cyc_audio_enable(have.freq)) SDL_PauseAudioDevice(audio, 0);
    open_pads();
    const Uint64 frequency = SDL_GetPerformanceFrequency();
    Uint64 next = SDL_GetPerformanceCounter(), mark = next;
    uint64_t frame = 0, native_mark = cyc_run_native_cycles, cycle_mark = cyc_cycle_count();
    bool running = true;
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
                native_mark = cyc_run_native_cycles; cycle_mark = cyc_cycle_count();
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
                native_mark = cyc_run_native_cycles; cycle_mark = cyc_cycle_count();
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
            } else if (key == SDL_SCANCODE_F4) {
                fullscreen = (fullscreen + 1) % 3;
                SDL_SetWindowFullscreen(win, fullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
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
                snprintf(status, sizeof(status), "%s", tr("NES quick states are not available yet", "Etats NES indisponibles pour le moment"));
                if (!menu) menu = 3;
            } else if (menu == 2) {
                if (key == SDL_SCANCODE_TAB) gamepad_page = !gamepad_page;
                else if (key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT) player = !player;
                else if (key == SDL_SCANCODE_UP) row = (row + ACTIONS - 1) % ACTIONS;
                else if (key == SDL_SCANCODE_DOWN) row = (row + 1) % ACTIONS;
                else if (key == SDL_SCANCODE_RETURN) capturing = 1;
            }
        }
        if (!running) break;
        if (!menu) {
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
        if (filter == 3) {
            SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_BLEND);
            SDL_SetRenderDrawColor(ren, 0, 0, 0, 85);
            for (int y = 1; y < 240; y += 2) {
                SDL_Rect line = {dst.x, dst.y + y * dst.h / 240, dst.w,
                                 dst.h / 240 > 0 ? dst.h / 240 : 1};
                SDL_RenderFillRect(ren, &line);
            }
            SDL_SetRenderDrawBlendMode(ren, SDL_BLENDMODE_NONE);
        }
        draw_menu(ren);
        SDL_RenderPresent(ren);
        Uint64 now = SDL_GetPerformanceCounter();
        if (now - mark >= frequency) {
            uint64_t cycles = cyc_cycle_count() - cycle_mark;
            double percent = cycles ? 100.0 * (cyc_run_native_cycles - native_mark) / cycles : 0.0;
            char caption[256];
            snprintf(caption, sizeof(caption), "%s | NES | %.4f%% native | ROM fallback %llu cycles",
                     title, percent, (unsigned long long)cyc_run_interp_rom_cycles);
            SDL_SetWindowTitle(win, caption);
            mark = now; cycle_mark = cyc_cycle_count(); native_mark = cyc_run_native_cycles;
        }
        if (menu) { next = now; SDL_Delay(16); continue; }
        next += (Uint64)((1.0 / 60.0988) * frequency);
        if (next > now) {
            Uint32 ms = (Uint32)((next - now) * 1000 / frequency);
            if (ms > 1) SDL_Delay(ms - 1);
            while (SDL_GetPerformanceCounter() < next) {}
        } else if (now - next > frequency / 4) next = now;
    }
    if (audio) SDL_CloseAudioDevice(audio);
    for (int p = 0; p < 2; ++p) if (pads[p]) SDL_GameControllerClose(pads[p]);
    rr_menu_shutdown(); free(upscaled); if (tex) SDL_DestroyTexture(tex);
    SDL_DestroyRenderer(ren); SDL_DestroyWindow(win); SDL_Quit(); return 0;
}
