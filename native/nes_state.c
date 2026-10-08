/* Lazy, atomic Windows quick-state persistence. */
#include <windows.h>
#include <wchar.h>
#include <stdio.h>
#include <stdlib.h>
#include "retro_nes.h"
#include "retro_nes_config.h"

void rr_nes_state_path(wchar_t *path, size_t capacity) {
    if (capacity < 260) { if (capacity) path[0] = 0; return; }
    DWORD n = GetModuleFileNameW(NULL, path, (DWORD)(capacity - 180));
    wchar_t *slash = n ? wcsrchr(path, L'\\') : NULL;
    if (!slash) { path[0] = 0; return; }
    *slash = 0;
    wcscat_s(path, capacity, L"\\datas\\states\\" RR_NES_STATE_NAME L".rrstate");
}

bool rr_nes_state_file(const wchar_t *path, bool load) {
    if (!path || !path[0]) return false;
    size_t size = rr_nes_state_size();
    uint8_t *buffer = (uint8_t *)malloc(size);
    if (!buffer) return false;
    bool ok = false;
    if (load) {
        /* In particular: missing F9 never creates datas or any file. */
        HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
        LARGE_INTEGER length;
        DWORD read = 0;
        if (file != INVALID_HANDLE_VALUE) {
            ok = GetFileSizeEx(file, &length) && length.QuadPart == (LONGLONG)size &&
                ReadFile(file, buffer, (DWORD)size, &read, NULL) && read == size;
            CloseHandle(file);
            if (ok) ok = rr_nes_state_load(buffer, size);
        }
    } else if (rr_nes_state_save(buffer, size)) {
        wchar_t directory[32768], temporary[32768];
        wcscpy_s(directory, 32768, path);
        wchar_t *last = wcsrchr(directory, L'\\');
        if (last) {
            *last = 0;
            wchar_t *parent = wcsrchr(directory, L'\\');
            if (parent) { *parent = 0; CreateDirectoryW(directory, NULL); *parent = L'\\'; }
            CreateDirectoryW(directory, NULL);
            swprintf_s(temporary, 32768, L"%s.tmp-%lu-%llu", path, GetCurrentProcessId(), GetTickCount64());
            HANDLE file = CreateFileW(temporary, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
            if (file != INVALID_HANDLE_VALUE) {
                DWORD wrote = 0;
                ok = WriteFile(file, buffer, (DWORD)size, &wrote, NULL) && wrote == size && FlushFileBuffers(file);
                CloseHandle(file);
                if (ok) ok = MoveFileExW(temporary, path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) != 0;
                if (!ok) DeleteFileW(temporary);
            }
        }
    }
    free(buffer);
    return ok;
}
