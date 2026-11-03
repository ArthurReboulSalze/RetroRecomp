/* EEPROM saves of the CPS-1.5 (QSound) boards, see cps1_persistence.h. Original work: MIT.
 * One file per exact set, written atomically (temporary file, flush, replace). A file that does not belong to this set,
 * has another size or fails its checksum is never used and never overwritten: the game starts with a blank EEPROM. */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include <errno.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cps1_machine.h"
#include "cps1_persistence.h"
#include "retro16_state_config.h"

enum { HEADER = 96, PAYLOAD_MAX = 128 };
static const uint8_t magic[8] = {'R', 'R', 'C', 'P', 'S', 'E', '0', '1'};
static bool active, blocked;
static wchar_t save_path[32768];

static void put32(uint8_t *p, uint32_t v) { for (unsigned n = 0; n < 4; ++n) p[n] = (uint8_t)(v >> (8 * n)); }
static uint32_t get32(const uint8_t *p) { uint32_t v = 0; for (unsigned n = 0; n < 4; ++n) v |= (uint32_t)p[n] << (8 * n); return v; }
static uint64_t hash(const uint8_t *p, size_t n)
{
    uint64_t h = 14695981039346656037ull;
    for (size_t i = 0; i < n; ++i) h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

bool rr_cps1_save_path(wchar_t *path, size_t capacity)
{
    if (!path || capacity < 32768) return false;
    char tail[128];
    wchar_t wide_tail[128];
    snprintf(tail, sizeof tail, RR_SLASH "datas" RR_SLASH "saves" RR_SLASH "CPS1-%.64s.rrsave", RR16_STATE_ROM);
    return rr_executable_directory(path, capacity) && rr_from_utf8(tail, wide_tail, 128) && rr_wide_append(path, capacity, wide_tail) == 0;
}

/* 1 valid, 0 missing, -1 not usable. */
static int read_saved(uint8_t *data, size_t size)
{
    FILE *file = rr_fopen(save_path, L"rb");
    if (!file) return errno == ENOENT ? 0 : -1;
    uint8_t header[HEADER];
    bool valid = fread(header, 1, HEADER, file) == HEADER && !memcmp(header, magic, 8) && get32(header + 8) == 1 &&
                 get32(header + 12) == size && !memcmp(header + 24, RR16_STATE_ROM, 64);
    for (unsigned n = 88; valid && n < HEADER; ++n) valid = header[n] == 0;
    valid = valid && fread(data, 1, size, file) == size && fgetc(file) == EOF && !ferror(file);
    fclose(file);
    if (valid) {
        const uint64_t checksum = (uint64_t)get32(header + 20) << 32 | get32(header + 16);
        valid = hash(data, size) == checksum;
    }
    return valid ? 1 : -1;
}

static bool write_atomic(const uint8_t *data, size_t size)
{
    uint8_t header[HEADER] = {0};
    memcpy(header, magic, 8);
    put32(header + 8, 1);
    put32(header + 12, (uint32_t)size);
    const uint64_t checksum = hash(data, size);
    put32(header + 16, (uint32_t)checksum);
    put32(header + 20, (uint32_t)(checksum >> 32));
    memcpy(header + 24, RR16_STATE_ROM, 64);
    wchar_t parent[32768], temporary[32768];
    rr_wide_copy(parent, 32768, save_path);
    for (wchar_t *p = parent + 3; *p; ++p)
        if (*p == L'\\' || *p == L'/') {
            const wchar_t separator = *p;
            *p = 0;
            if (!rr_mkdir(parent)) return false;
            *p = separator;
        }
    swprintf(temporary, 32768, L"%ls.%lu.tmp", save_path, rr_process_id());
    FILE *file = rr_fopen(temporary, L"wb");
    if (!file) return false;
    bool okay = fwrite(header, 1, HEADER, file) == HEADER && fwrite(data, 1, size, file) == size;
    if (okay) okay = rr_flush_file(file);
    if (fclose(file)) okay = false;
    if (okay) okay = rr_replace(temporary, save_path);
    if (!okay) rr_remove(temporary);
    return okay;
}

bool rr_cps1_save_begin(void)
{
    active = blocked = false;
    const size_t size = cps1_eeprom_size();
    if (!size || size > PAYLOAD_MAX) return true;           /* a board without an EEPROM keeps nothing */
    if (!rr_cps1_save_path(save_path, 32768)) { blocked = true; return false; }
    uint8_t data[PAYLOAD_MAX];
    const int result = read_saved(data, size);
    if (result == 1 && !cps1_eeprom_load(data, size)) blocked = true;
    else if (result < 0) blocked = true;
    active = true;
    return !blocked;
}

void rr_cps1_save_frame(void)
{
    if (!active || blocked || !cps1_eeprom_changed()) return;
    if (!write_atomic(cps1_eeprom_data(), cps1_eeprom_size())) blocked = true;   /* a failed write stops further tries, play goes on */
}

bool rr_cps1_save_close(void)
{
    if (!active) return true;
    if (blocked) return false;
    if (cps1_eeprom_changed()) return write_atomic(cps1_eeprom_data(), cps1_eeprom_size());
    return true;
}
