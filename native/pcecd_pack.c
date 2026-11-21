/* The disc a PC Engine CD game holds (native/pcecd_pack.h). Original RetroRecomp code: MIT. */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <unistd.h>
#endif
#include <stdio.h>
#include <string.h>

#include "pcecd_pack.h"

static uint64_t le64(const unsigned char *p)
{
    uint64_t value = 0;
    for (int n = 7; n >= 0; n--) value = (value << 8) | p[n];
    return value;
}

static int own_path(char *out, size_t size)
{
#ifdef _WIN32
    wchar_t wide[32768];
    DWORD length = GetModuleFileNameW(NULL, wide, (DWORD)(sizeof wide / sizeof *wide));
    if (!length || length >= sizeof wide / sizeof *wide) return 0;
    return WideCharToMultiByte(CP_UTF8, 0, wide, -1, out, (int)size, NULL, NULL) > 0;
#else
    ssize_t length = readlink("/proc/self/exe", out, size - 1);
    if (length <= 0) return 0;
    out[length] = 0;
    return 1;
#endif
}

int rr_pcecd_find_embedded(char *path, size_t path_size, uint64_t *offset, uint64_t *length, char sha256[65])
{
    if (!path || !path_size || !offset || !length || !sha256 || !own_path(path, path_size)) return 0;
    FILE *file;
#ifdef _WIN32
    wchar_t wide[32768];
    if (!MultiByteToWideChar(CP_UTF8, 0, path, -1, wide, (int)(sizeof wide / sizeof *wide))) return 0;
    file = _wfopen(wide, L"rb");
#else
    file = fopen(path, "rb");
#endif
    if (!file) return 0;
    unsigned char trailer[RR_PCECD_TRAILER];
    int found = 0;
#ifdef _WIN32
    if (_fseeki64(file, -(long long)RR_PCECD_TRAILER, SEEK_END) == 0)
#else
    if (fseeko(file, -(off_t)RR_PCECD_TRAILER, SEEK_END) == 0)
#endif
        found = fread(trailer, 1, sizeof trailer, file) == sizeof trailer && !memcmp(trailer + 80, "RRPCECD1", 8);
    fclose(file);
    if (!found) return 0;
    for (int n = 0; n < 64; n++) {
        char c = (char)trailer[n];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return 0;
        sha256[n] = c;
    }
    sha256[64] = 0;
    *offset = le64(trailer + 64);
    *length = le64(trailer + 72);
    return *length != 0;
}
