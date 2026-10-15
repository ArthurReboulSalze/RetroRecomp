/* SMSRecomp standalone launcher. ROM and SDL are linked into the executable. */
#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#include <locale.h>
#include "embedded_icon.h"
#define _putenv_s(k,v) ((v)[0] ? setenv(k,v,1) : unsetenv(k))
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "embedded_rom.h"
#include "host_control.h"
#include "paths.h"
#include "platform_io.h"

int sms_backend_main(int argc, char **argv);

#ifdef _WIN32
int WINAPI WinMain(HINSTANCE instance, HINSTANCE previous, LPSTR command, int show) {
    (void)instance; (void)previous; (void)command; (void)show;
#else
int main(int __argc, char **__argv) {
    setlocale(LC_CTYPE, "");
#endif
    char **args = (char **)calloc((size_t)__argc + 6, sizeof(char *));
    if (!args) return 1;
    int count = 0, headless = 0, window = 0, log_requested = 0;
    args[count++] = __argv[0];
#ifdef RETRO_GAME_GEAR
    args[count++] = "embedded.gg";
#else
    args[count++] = "embedded.sms";
#endif
    for (int i = 1; i < __argc; ++i) {
#ifndef _WIN32
        if (strcmp(__argv[i], "--credits") == 0) { puts(rr_game_legal); free(args); return 0; }
#endif
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
    if (!headless) _putenv_s("RETRO_RECOMP_LEARNING", "");
    if (!headless) {
#ifdef _WIN32
        wchar_t executable_path[32768];
        if (GetModuleFileNameW(NULL, executable_path, 32768)) {
            wchar_t *separator = wcsrchr(executable_path, L'\\');
            if (separator) { *separator = 0; SetCurrentDirectoryW(executable_path); }
        }
#else
        wchar_t executable_path[RETRO_PATH_CAP];
        char utf8[RETRO_PATH_CAP];
        if (retro_executable_directory(executable_path) && rr_to_utf8(executable_path, utf8, sizeof utf8)) chdir(utf8);
#endif
    }
    if (!log_requested) {
        /* Normal gameplay has no persistent diagnostic log. --log is reserved
         * for explicitly requested diagnostics and converter checks. */
#ifdef _WIN32
        _wfreopen(L"NUL", L"w", stderr);
#else
        freopen("/dev/null", "w", stderr);
#endif
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
