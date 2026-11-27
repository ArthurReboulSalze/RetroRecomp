/* Shared per-console settings; reading never creates a directory.
 * display_mode: 0 window, 1 pixel-perfect fullscreen, 2 fit fullscreen, 3 stretched fullscreen (1.7.4). The numbers of 0 to 2
 * never change, so a value saved by an earlier release means the same mode; an unknown value is the window. */
#define RR_DISPLAY_MODES 4
/* filter: 0 sharp pixels, 1 xBR, 2 Scale2x, 3 scanlines, 4 CRT flat, 5 CRT curved, 6 LCD grid (HOST_KIT D35; the handhelds only).
 * The numbers never change; an unknown value is sharp pixels, so an older release reads 4 to 6 as sharp pixels. */
#define RR_FILTERS 7
#define RR_FILTER_CRT_FLAT 4
#define RR_FILTER_CRT_CURVED 5
#define RR_FILTER_LCD 6
#ifndef RETRO_DISPLAY_SETTINGS_H
#define RETRO_DISPLAY_SETTINGS_H
#include "platform_io.h"
#include <wchar.h>
#include <SDL.h>
static void rr_display_load(const wchar_t *path, const wchar_t *section,
                            int *filter, int *mode) {
    int f = rr_ini_int(section, L"filter", 0, path);
    int m = rr_ini_int(section, L"display_mode", 0, path);
    *filter = f >= 0 && f < RR_FILTERS ? f : 0;
    *mode = m >= 0 && m < RR_DISPLAY_MODES ? m : 0;
}
static int rr_display_save(const wchar_t *path, const wchar_t *dir,
                           const wchar_t *section, const wchar_t *key, int value) {
    wchar_t text[16];
    if (!path[0]) return 0;
    swprintf(text, 16, L"%d", value);
    if (!rr_mkdir(dir)) return 0;
    return rr_ini_set(section, key, text, path) != 0;
}
/* Failure to enter fullscreen must leave both the setting and mode intact. */
static int rr_display_cycle(SDL_Window *window, int *mode, const wchar_t *path,
                             const wchar_t *dir, const wchar_t *section) {
    int wanted=(*mode+1)%RR_DISPLAY_MODES;
    if (SDL_SetWindowFullscreen(window,wanted ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0)!=0) return 0;
    *mode=wanted;
    return rr_display_save(path,dir,section,L"display_mode",wanted) ? 1 : -1;
}
#endif
