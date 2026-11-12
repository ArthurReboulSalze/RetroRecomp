/* The cartridge save file shared by the Mega Drive, the Super Nintendo and the PC Engine (see cart_save.h). It survives a rebuild
 * of the game: only the exact cartridge is checked (the ROM's SHA-256 and the format's identity words), not the engine or the
 * bridge. Quick states are separate files. Original RetroRecomp code: MIT. */
#include "platform_io.h"
#include <errno.h>
#include <stdio.h>
#include <string.h>

#include "cart_save.h"
#include "retro16_state_config.h"

enum { HEADER_BYTES = 112, QUIET_MS = 2000, CHECK_MS = 500, RETRY_MS = 10000 };

static void put32(uint8_t *p, uint32_t n) { for (unsigned i = 0; i < 4; i++) p[i] = (uint8_t)(n >> (i * 8)); }
static uint32_t get32(const uint8_t *p) { uint32_t n = 0; for (unsigned i = 0; i < 4; i++) n |= (uint32_t)p[i] << (i * 8); return n; }
static uint64_t hash(const uint8_t *p, size_t n)
{
    uint64_t h = 14695981039346656037ull;
    for (size_t i = 0; i < n; i++) { h ^= p[i]; h *= 1099511628211ull; }
    return h;
}

/* Moves an unusable file to "<file>.unusable-N" (the first N from 1 to 99 that is free), like the X68000 does with a disk. Never
 * deletes it, and never replaces a file already set aside: with all 99 names taken it returns false and the file stays where it is. */
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

bool rr_cart_save_path(wchar_t *path, size_t capacity)
{
    return rr_game_data_file(path, capacity, "saves", RR16_STATE_NAME, RR16_STATE_ROM, ".rrsram");
}

void rr_cart_save_reset(RrCartSave *save)
{
    save->active = false; save->last_check = save->last_changed = save->retry_at = 0; save->path[0] = 0; save->notice = 0;
}

bool rr_cart_save_active(const RrCartSave *save) { return save->active; }

/* The file at `file` holds this cartridge's save: the format's magic, version 1, the size, the identity words, the ROM's SHA-256, then
 * exactly `size` bytes whose hash is the stored one. The bytes are read into `payload`. The other header bytes are not looked at. */
static bool read_valid(FILE *file, const RrCartSaveFormat *format, size_t size, const uint32_t *words, uint8_t *payload)
{
    uint8_t header[HEADER_BYTES];
    if (fread(header, 1, sizeof header, file) != sizeof header || memcmp(header, format->magic, sizeof format->magic) ||
        get32(header + 8) != 1 || get32(header + 12) != size)
        return false;
    for (unsigned i = 0; i < format->identity_words; i++)
        if (get32(header + 16 + i * 4) != words[i]) return false;
    if (memcmp(header + 40, RR16_STATE_ROM, 64) || fread(payload, 1, size, file) != size || fgetc(file) != EOF || ferror(file))
        return false;
    return hash(payload, size) == ((uint64_t)get32(header + format->hash_offset + 4) << 32 | get32(header + format->hash_offset));
}

bool rr_cart_save_open(RrCartSave *save, const wchar_t *path, size_t size, const uint32_t *words,
                       RrCartSaveInstall install, void *context)
{
    const RrCartSaveFormat *format = save->format;
    rr_cart_save_reset(save);
    if (!path) return true;
    if (!size || size > format->capacity || !path[0] || wcslen(path) > 32000) return false;
    rr_wide_copy(save->path, 32768, path);
    FILE *file = rr_fopen(path, L"rb");
    if (!file && errno != ENOENT) {
        if (format->flags & RR_CART_SAVE_NOTICE_UNREADABLE) save->notice = 2;   /* it exists and cannot be read: left alone */
        return false;
    }
    const uint8_t *payload = NULL;
    if (file) {
        /* The bytes are read into the buffer that is only filled in from the machine's memory once this is over. */
        bool valid = read_valid(file, format, size, words, save->observed);
        if (fclose(file) != 0) valid = false;
        if (valid) payload = save->observed;
        /* A damaged or wrong-cartridge file never blocks the game and is never deleted or overwritten. */
        else if (!(format->flags & RR_CART_SAVE_SET_ASIDE)) return false;
        else if (!set_aside(path)) { save->notice = 2; return false; }
        else save->notice = 1;
    }
    const uint8_t *memory = install(context, payload);
    if (!memory) return false;   /* the machine is not there to be saved */
    memcpy(save->saved, memory, size); memcpy(save->observed, save->saved, size);
    save->active = true;
    return true;
}

static bool write_atomic(const RrCartSave *save, const uint8_t *memory, size_t size, const uint32_t *words)
{
    const RrCartSaveFormat *format = save->format;
    uint8_t header[HEADER_BYTES] = {0};
    memcpy(header, format->magic, sizeof format->magic);
    put32(header + 8, 1);
    put32(header + 12, (uint32_t)size);
    for (unsigned i = 0; i < format->identity_words; i++) put32(header + 16 + i * 4, words[i]);
    const uint64_t h = hash(memory, size);
    put32(header + format->hash_offset, (uint32_t)h);
    put32(header + format->hash_offset + 4, (uint32_t)(h >> 32));
    memcpy(header + 40, RR16_STATE_ROM, 64);
    wchar_t parent[32768], staged[32768];
    rr_wide_copy(parent, 32768, save->path);
    for (wchar_t *p = parent + 3; *p; p++)
        if (*p == L'\\' || *p == L'/') {
            const wchar_t separator = *p;
            *p = 0;
            if (!rr_mkdir(parent)) return false;
            *p = separator;
        }
    swprintf(staged, 32768, L"%ls.%lu.tmp", save->path, rr_process_id());
    FILE *file = rr_fopen(staged, L"wb");
    if (!file) return false;
    bool ok = fwrite(header, 1, sizeof header, file) == sizeof header && fwrite(memory, 1, size, file) == size;
    if (ok) ok = rr_flush_file(file);
    if (fclose(file) != 0) ok = false;
    if (ok) ok = rr_replace(staged, save->path);
    if (!ok) rr_remove(staged);
    return ok;
}

bool rr_cart_save_flush(RrCartSave *save, const uint8_t *memory, size_t size, const uint32_t *words, uint64_t now_ms, bool force)
{
    if (!force && (now_ms - save->last_check < CHECK_MS || now_ms < save->retry_at)) return true;
    save->last_check = now_ms;
    if (!memory) return true;
    if (memcmp(save->observed, memory, size)) { memcpy(save->observed, memory, size); save->last_changed = now_ms; }
    if (!memcmp(save->saved, memory, size) || (!force && now_ms - save->last_changed < QUIET_MS)) return true;
    if (!write_atomic(save, memory, size, words)) { save->retry_at = now_ms + RETRY_MS; return false; }
    memcpy(save->saved, memory, size);
    save->retry_at = 0;
    return true;
}
