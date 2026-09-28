#include "paths.h"
#include "embedded_rom.h"
#include <windows.h>
#include <stdio.h>

int retro_make_directories(wchar_t *path) {
    for (size_t i = 3; path[i]; ++i) if (path[i] == L'\\') {
        path[i] = 0;
        int ok = CreateDirectoryW(path, NULL) || GetLastError() == ERROR_ALREADY_EXISTS;
        path[i] = L'\\'; if (!ok) return 0;
    }
    if (CreateDirectoryW(path, NULL)) return 1;
    return GetLastError() == ERROR_ALREADY_EXISTS &&
        (GetFileAttributesW(path) & FILE_ATTRIBUTE_DIRECTORY) != 0;
}

int retro_executable_directory(wchar_t *out) {
    DWORD n = GetModuleFileNameW(NULL, out, RETRO_PATH_CAP);
    if (!n || n >= RETRO_PATH_CAP - 512) return 0;
    wchar_t *slash = wcsrchr(out, L'\\');
    if (!slash) return 0;
    *slash = 0;
    return 1;
}

int retro_data_directory(wchar_t *out) {
    if (!retro_executable_directory(out)) return 0;
    wcscat(out, L"\\datas");
    return 1; /* Resolve only. Reading a setting/state must not create folders. */
}

int retro_game_directory(wchar_t *out) {
    wchar_t root[RETRO_PATH_CAP], slug[128], sha[65];
    if (!retro_data_directory(root)) return 0;
    if (!MultiByteToWideChar(CP_UTF8, 0, sms_game_slug, -1, slug, 128) ||
        !MultiByteToWideChar(CP_UTF8, 0, sms_rom_sha256, -1, sha, 65)) return 0;
    swprintf(out, RETRO_PATH_CAP, L"%s\\games\\%s-%.12s", root, slug, sha);
    return 1;
}

static int game_file_path(wchar_t *out, const wchar_t *suffix) {
    wchar_t directory[RETRO_PATH_CAP], slug[128];
    if (!retro_game_directory(directory) || !MultiByteToWideChar(CP_UTF8, 0, sms_game_slug, -1, slug, 128)) return 0;
    swprintf(out, RETRO_PATH_CAP, L"%s\\%s%s", directory, slug, suffix);
    return 1;
}

FILE *retro_game_file(const wchar_t *suffix, const wchar_t *mode) {
    wchar_t path[RETRO_PATH_CAP];
    if (!game_file_path(path, suffix)) return NULL;
    if (mode[0] == L'w' || mode[0] == L'a') {
        wchar_t directory[RETRO_PATH_CAP];
        if (!retro_game_directory(directory) || !retro_make_directories(directory)) return NULL;
    }
    return _wfopen(path, mode);
}

void retro_game_file_reset(const wchar_t *suffix) {
    wchar_t path[RETRO_PATH_CAP];
    if (game_file_path(path, suffix)) _wremove(path);
}

int retro_game_file_replace(const wchar_t *temporary, const wchar_t *destination) {
    wchar_t from[RETRO_PATH_CAP], to[RETRO_PATH_CAP];
    return game_file_path(from, temporary) && game_file_path(to, destination) &&
        MoveFileExW(from, to, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
}
