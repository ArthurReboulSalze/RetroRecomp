#include "icon.h"
#include <SDL_syswm.h>
#include <windows.h>

int smsrecomp_set_window_icon(SDL_Window *window) {
    SDL_SysWMinfo info;
    SDL_VERSION(&info.version);
    if (!SDL_GetWindowWMInfo(window, &info) || info.subsystem != SDL_SYSWM_WINDOWS) return 0;
    HINSTANCE instance = GetModuleHandleW(NULL);
    HICON big = (HICON)LoadImageW(instance, MAKEINTRESOURCEW(101), IMAGE_ICON,
        GetSystemMetrics(SM_CXICON), GetSystemMetrics(SM_CYICON), LR_SHARED);
    HICON small = (HICON)LoadImageW(instance, MAKEINTRESOURCEW(101), IMAGE_ICON,
        GetSystemMetrics(SM_CXSMICON), GetSystemMetrics(SM_CYSMICON), LR_SHARED);
    if (!big || !small) return 0;
    SendMessageW(info.info.win.window, WM_SETICON, ICON_BIG, (LPARAM)big);
    SendMessageW(info.info.win.window, WM_SETICON, ICON_SMALL, (LPARAM)small);
    return 1;
}
