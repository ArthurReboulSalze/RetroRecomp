/* PC Engine Backup RAM file (docs/PC_ENGINE.md, "Saves"): a versioned header, then the 2,048 bytes the game wrote. It survives a
 * rebuild of the game: only the exact HuCard is checked, not the engine or the bridge. Quick states are separate files.
 * A file the game cannot use is never deleted, overwritten or a reason not to start: it moves to "<file>.unusable-N" and the game
 * starts formatted; if it cannot move, it stays untouched and nothing is saved this session. Original RetroRecomp code: MIT. */
#include "platform_io.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "pce_backup.h"
#include "pce_machine.h"
#include "retro16_state_config.h"

enum { HEADER_BYTES = 112, QUIET_MS = 2000, CHECK_MS = 500, RETRY_MS = 10000 };
static const uint8_t magic[8] = {'R', 'R', 'P', 'C', 'E', 'B', 'R', '1'};
static uint8_t saved[PCE_BACKUP_BYTES], observed[PCE_BACKUP_BYTES];
static wchar_t save_path[32768];
static bool active;
static unsigned notice_state;
static uint64_t last_check, last_changed, retry_at;

unsigned rr_pce_backup_notice(void) { return notice_state; }

static void put32(uint8_t *p, uint32_t n) { for (unsigned i = 0; i < 4; i++) p[i] = (uint8_t)(n >> (i * 8)); }
static uint32_t get32(const uint8_t *p) { uint32_t n = 0; for (unsigned i = 0; i < 4; i++) n |= (uint32_t)p[i] << (i * 8); return n; }
static uint64_t hash(const uint8_t *p, size_t n)
{
    uint64_t h = 14695981039346656037ull;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}

/* "<file>.unusable-N", the first N from 1 to 99 that is free: nothing already set aside is replaced. */
static bool set_aside(const wchar_t *file)
{
    wchar_t aside[32768 + 16];
    for (unsigned n = 1; n <= 99; n++) {
        if (swprintf(aside, 32768 + 16, L"%ls.unusable-%u", file, n) < 0) return false;
        FILE *taken = rr_fopen(aside, L"rb");
        if (taken) { fclose(taken); continue; }
        return rr_replace(file, aside) != 0;
    }
    return false;
}

bool rr_pce_backup_path(wchar_t *path, size_t capacity)
{
    return rr_game_data_file(path, capacity, "saves", RR16_STATE_NAME, RR16_STATE_ROM, ".rrsram");
}

void rr_pce_backup_open(const wchar_t *path)
{
    active = false; last_check = last_changed = retry_at = 0; save_path[0] = 0; notice_state = 0;
    if (!path || !path[0] || wcslen(path) > 32000) return;
    rr_wide_copy(save_path, 32768, path);
    FILE *file = rr_fopen(path, L"rb");
    if (file) {
        uint8_t header[HEADER_BYTES], payload[PCE_BACKUP_BYTES];
        bool valid = fread(header, 1, sizeof header, file) == sizeof header && !memcmp(header, magic, sizeof magic) &&
                     get32(header + 8) == 1 && get32(header + 12) == PCE_BACKUP_BYTES &&
                     !memcmp(header + 40, RR16_STATE_ROM, 64) && fread(payload, 1, sizeof payload, file) == sizeof payload &&
                     fgetc(file) == EOF && !ferror(file) &&
                     hash(payload, sizeof payload) == ((uint64_t)get32(header + 20) << 32 | get32(header + 16));
        if (fclose(file) != 0) valid = false;
        if (valid) pce_machine_set_backup(payload);
        else if (!set_aside(path)) { notice_state = 2; return; }
        else notice_state = 1;
    } else if (errno != ENOENT) {
        notice_state = 2;   /* it exists and cannot be read: left alone, nothing written over it */
        return;
    }
    memcpy(saved, pce_machine_backup(), sizeof saved);
    memcpy(observed, saved, sizeof observed);
    active = true;
}

static bool write_atomic(const uint8_t *memory)
{
    uint8_t header[HEADER_BYTES] = {0};
    memcpy(header, magic, sizeof magic);
    put32(header + 8, 1);
    put32(header + 12, PCE_BACKUP_BYTES);
    const uint64_t h = hash(memory, PCE_BACKUP_BYTES);
    put32(header + 16, (uint32_t)h);
    put32(header + 20, (uint32_t)(h >> 32));
    memcpy(header + 40, RR16_STATE_ROM, 64);
    wchar_t parent[32768], staged[32768];
    rr_wide_copy(parent, 32768, save_path);
    for (wchar_t *p = parent + 3; *p; p++)
        if (*p == L'\\' || *p == L'/') {
            const wchar_t separator = *p;
            *p = 0;
            if (!rr_mkdir(parent)) return false;
            *p = separator;
        }
    swprintf(staged, 32768, L"%ls.%lu.tmp", save_path, rr_process_id());
    FILE *file = rr_fopen(staged, L"wb");
    if (!file) return false;
    bool ok = fwrite(header, 1, sizeof header, file) == sizeof header && fwrite(memory, 1, PCE_BACKUP_BYTES, file) == PCE_BACKUP_BYTES;
    if (ok) ok = rr_flush_file(file);
    if (fclose(file) != 0) ok = false;
    if (ok) ok = rr_replace(staged, save_path);
    if (!ok) rr_remove(staged);
    return ok;
}

bool rr_pce_backup_flush(uint64_t now_ms, bool force)
{
    if (!active) return true;
    if (!force && (now_ms - last_check < CHECK_MS || now_ms < retry_at)) return true;
    last_check = now_ms;
    const uint8_t *memory = pce_machine_backup();
    if (!memory) return true;
    if (memcmp(observed, memory, sizeof observed)) { memcpy(observed, memory, sizeof observed); last_changed = now_ms; }
    if (!memcmp(saved, memory, sizeof saved) || (!force && now_ms - last_changed < QUIET_MS)) return true;
    if (!write_atomic(memory)) { retry_at = now_ms + RETRY_MS; return false; }
    memcpy(saved, memory, sizeof saved);
    retry_at = 0;
    return true;
}
