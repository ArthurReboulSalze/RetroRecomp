/* Hidden Windows/SDL test: no game execution, focus or visible window. */
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <SDL.h>
#include <SDL_syswm.h>
#include <windows.h>
#include "icon.h"

int main(void) {
    SDL_SetMainReady();
    assert(SDL_Init(SDL_INIT_VIDEO) == 0);
    SDL_Window *window = SDL_CreateWindow("SMSRecomp icon check", 0, 0, 32, 32, SDL_WINDOW_HIDDEN);
    assert(window);
    assert(smsrecomp_set_window_icon(window));
    SDL_SysWMinfo info; SDL_VERSION(&info.version);
    assert(SDL_GetWindowWMInfo(window, &info) && info.subsystem == SDL_SYSWM_WINDOWS);
    assert(!(GetWindowLongW(info.info.win.window, GWL_STYLE) & WS_VISIBLE));
    for (int kind = ICON_SMALL; kind <= ICON_BIG; ++kind) {
        HICON icon = (HICON)SendMessageW(info.info.win.window, WM_GETICON, kind, 0);
        assert(icon);
        ICONINFO details;
        assert(GetIconInfo(icon, &details));
        BITMAP bitmap;
        assert(GetObjectW(details.hbmColor, sizeof(bitmap), &bitmap));
        assert(bitmap.bmWidth == GetSystemMetrics(kind == ICON_BIG ? SM_CXICON : SM_CXSMICON));
        assert(bitmap.bmHeight == GetSystemMetrics(kind == ICON_BIG ? SM_CYICON : SM_CYSMICON));
        DeleteObject(details.hbmColor); DeleteObject(details.hbmMask);
    }
    SDL_DestroyWindow(window); SDL_Quit();
    puts("PASS: embedded icons installed on a hidden SDL window (small and big Win32 icons).");
    return 0;
}
