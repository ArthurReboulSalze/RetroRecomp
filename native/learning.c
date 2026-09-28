/* Persistent per-ROM observations. No decoding/compiler/interpreter here:
 * append only newly seen (address, banks, byte hash) to the game library. */
#include "learning.h"
#include "embedded_rom.h"
#include "paths.h"
#include <windows.h>
#include <shlobj.h>
#include <share.h>
#include <stdlib.h>
#include <wchar.h>
#include <string.h>

static wchar_t journal[32768], code_journal[32768], lock_path[32768], directory[32768];
static int initialized, available, warned;

int smsrecomp_learning_enabled(void) {
    static int enabled = -1;
    if (enabled < 0) {
        const wchar_t *setting = _wgetenv(L"RETRO_RECOMP_LEARNING");
        enabled = setting && !wcscmp(setting, L"1");
    }
    return enabled;
}

static int initialize(void) {
    /* Only converter probes opt in. A distributed game neither reads nor
     * writes a compilation library during ordinary gameplay. */
    if (!smsrecomp_learning_enabled()) return 0;
    if (initialized) return available;
    initialized = 1;
    wchar_t root[32768], sha[65], label[128], pattern[32768];
    const wchar_t *custom = _wgetenv(L"RETRO_RECOMP_LIBRARY_DIR");
    if (!custom || !*custom) custom = _wgetenv(L"SMSRECOMP_LIBRARY_DIR");
    if (custom && *custom) {
        DWORD n = GetFullPathNameW(custom, 32768, root, NULL);
        if (!n || n >= 32500) return 0;
    } else {
        if (!retro_data_directory(root)) return 0;
        wcscat(root, L"\\library");
    }
    for (int i = 0; root[i]; ++i) if (root[i] == L'/') root[i] = L'\\';
    MultiByteToWideChar(CP_UTF8, 0, sms_rom_sha256, -1, sha, 65);
    if (wcslen(root) > 32500) return 0;
    /* Find by full embedded identity, so ROM/executable renames keep memory. */
    swprintf(pattern, 32768, L"%s\\*-%s", root, sha);
    WIN32_FIND_DATAW found;
    HANDLE search = FindFirstFileW(pattern, &found);
    int matched = 0;
    if (search != INVALID_HANDLE_VALUE) {
        do {
            if (found.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
                swprintf(directory, 32768, L"%s\\%s", root, found.cFileName);
                matched = 1; break;
            }
        } while (FindNextFileW(search, &found));
        FindClose(search);
    }
    if (!matched) {
        swprintf(directory, 32768, L"%s\\%s", root, sha); /* compatibility */
        DWORD attributes = GetFileAttributesW(directory);
        if (attributes == INVALID_FILE_ATTRIBUTES || !(attributes & FILE_ATTRIBUTE_DIRECTORY)) {
            if (!MultiByteToWideChar(CP_UTF8, 0, sms_game_slug, -1, label, 128)) return 0;
            swprintf(directory, 32768, L"%s\\%s-%s", root, label, sha);
        }
    }
    swprintf(journal, 32768, L"%s\\observations.log", directory);
    swprintf(code_journal, 32768, L"%s\\native.patterns", directory);
    swprintf(lock_path, 32768, L"%s\\entry.lock", directory);
    available = 1;
    return 1;
}

FILE *smsrecomp_observations_read(void) {
    if (!initialize()) return NULL;
    return _wfsopen(journal, L"rb", _SH_DENYNO);
}

static int append_record(const wchar_t *path, const char *line) {
    if (!initialize()) return 0;
    int ok = 0;
    if (initialize() && retro_make_directories(directory)) {
        HANDLE lock = CreateFileW(lock_path, GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
        if (lock != INVALID_HANDLE_VALUE) {
            OVERLAPPED overlap = {0};
            /* Same first-byte lock as Python's msvcrt.locking. */
            if (LockFileEx(lock, LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0, &overlap)) {
                FILE *file = _wfsopen(path, L"ab", _SH_DENYNO);
                if (file) {
                    ok = fputs(line, file) >= 0;
                    if (fflush(file) != 0) ok = 0;
                    if (fclose(file) != 0) ok = 0;
                }
                UnlockFileEx(lock, 0, 1, 0, &overlap);
            }
            CloseHandle(lock);
        }
    }
    if (!ok && !warned) {
        fprintf(stderr, "[learning] library unavailable: observation not saved\n"); warned = 1;
    }
    return ok;
}

int smsrecomp_observe(uint16_t address, uint8_t b0, uint8_t b1, uint8_t b2, uint32_t hash) {
    char line[80];
    snprintf(line, sizeof line, "%04X %02X %02X %02X %08X\n", address, b0, b1, b2, hash);
    return append_record(journal, line);
}

int smsrecomp_observe_code(const uint8_t bytes[4]) {
    /* Small data-only windows, independent of unrelated neighbouring RAM. */
    static uint32_t seen[4096];
    static unsigned count;
    static int loaded, full_warning;
    if (!initialize()) return 0;
    if (!loaded) {
        loaded = 1;
        FILE *file = _wfsopen(code_journal, L"rb", _SH_DENYNO);
        if (file) {
            char line[80], extra; unsigned raw;
            while (count < 4096 && fgets(line, sizeof line, file)) {
                if (strlen(line) != 9 || sscanf(line, "%8x %c", &raw, &extra) != 1) continue;
                unsigned i; for (i = 0; i < count && seen[i] != raw; ++i) {}
                if (i == count) seen[count++] = raw;
            }
            fclose(file);
        }
    }
    uint32_t raw = ((uint32_t)bytes[0]<<24) | ((uint32_t)bytes[1]<<16) | ((uint32_t)bytes[2]<<8) | bytes[3];
    for (unsigned i = 0; i < count; ++i) if (seen[i] == raw) return 1;
    if (count == 4096) {
        if (!full_warning) { fprintf(stderr, "[learning] native pattern limit reached (4096)\n"); full_warning = 1; }
        return 0;
    }
    char line[16]; snprintf(line, sizeof line, "%08X\n", raw);
    int ok = append_record(code_journal, line);
    if (ok) seen[count++] = raw;
    return ok;
}
