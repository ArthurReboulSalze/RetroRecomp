/* Shared per-console settings; reading never creates a directory. */
#ifndef RETRO_DISPLAY_SETTINGS_H
#define RETRO_DISPLAY_SETTINGS_H
#include <windows.h>
#include <wchar.h>
#include <SDL.h>
static void rr_display_load(const wchar_t *path, const wchar_t *section,
                            int *filter, int *mode) {
    int f = (int)GetPrivateProfileIntW(section, L"filter", 0, path);
    int m = (int)GetPrivateProfileIntW(section, L"display_mode", 0, path);
    *filter = f >= 0 && f < 4 ? f : 0;
    *mode = m >= 0 && m < 3 ? m : 0;
}
static int rr_display_save(const wchar_t *path, const wchar_t *dir,
                           const wchar_t *section, const wchar_t *key, int value) {
    wchar_t text[16];
    if (!path[0]) return 0;
    swprintf_s(text, 16, L"%d", value);
    if (!CreateDirectoryW(dir, NULL) && GetLastError() != ERROR_ALREADY_EXISTS) return 0;
    return WritePrivateProfileStringW(section, key, text, path) != 0;
}
/* Failure to enter fullscreen must leave both the setting and mode intact. */
static int rr_display_cycle(SDL_Window *window, int *mode, const wchar_t *path,
                             const wchar_t *dir, const wchar_t *section) {
    int wanted=(*mode+1)%3;
    if (SDL_SetWindowFullscreen(window,wanted ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0)!=0) return 0;
    *mode=wanted;
    return rr_display_save(path,dir,section,L"display_mode",wanted) ? 1 : -1;
}
#endif
