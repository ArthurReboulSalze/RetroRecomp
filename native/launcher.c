/* SMSRecomp standalone launcher. ROM and SDL are linked into the executable. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "embedded_rom.h"
#include "host_control.h"
#include "paths.h"

int sms_backend_main(int argc, char **argv);

int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show) {
    (void)instance; (void)previous; (void)command; (void)show;
    char **args = (char **)calloc((size_t)__argc + 6, sizeof(char *));
    if (!args) return 1;
    int count = 0, headless = 0, window = 0, log_requested = 0;
    args[count++] = __argv[0];
    args[count++] = "embedded.sms";
    for (int i = 1; i < __argc; ++i) {
        if (strcmp(__argv[i], "--strict") == 0) { _putenv_s("SMSRECOMP_STRICT", "1"); continue; }
        if (strcmp(__argv[i], "--headless") == 0) { headless = 1; continue; }
        if (strcmp(__argv[i], "--log") == 0 && i + 1 < __argc) {
            if (!freopen(__argv[++i], "w", stderr)) { free(args); return 2; }
            log_requested = 1;
            continue;
        }
        if (strcmp(__argv[i], "--window") == 0) window = 1;
        args[count++] = __argv[i];
    }
    if (!headless && !window) {
        args[count++] = "--window";
        args[count++] = "3";
    }
    if (!headless) {
        wchar_t executable_path[32768];
        if (GetModuleFileNameW(NULL, executable_path, 32768)) {
            wchar_t *separator = wcsrchr(executable_path, L'\\');
            if (separator) { *separator = 0; SetCurrentDirectoryW(executable_path); }
        }
    }
    if (!log_requested) {
        wchar_t directory[RETRO_PATH_CAP], log_path[RETRO_PATH_CAP], slug[128];
        if (retro_game_directory(directory) && MultiByteToWideChar(CP_UTF8, 0, sms_game_slug, -1, slug, 128)) {
            swprintf(log_path, RETRO_PATH_CAP, L"%s\\%s-last-run.log", directory, slug);
            if (!_wfreopen(log_path, L"w", stderr)) OutputDebugStringW(L"Retro-Recomp: journal indisponible\n");
        }
    }
    fprintf(stderr, "[Retro-Recomp] %s | ROM CRC32 %08X | embedded ROM\n",
            sms_game_title, sms_rom_crc32);
    int result;
    do {
        result = sms_backend_main(count, args);
    } while (result == 0 && smsrecomp_take_reset_request());
    free(args);
    return result;
}
