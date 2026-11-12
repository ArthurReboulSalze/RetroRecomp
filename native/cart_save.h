/* The cartridge save file beside the game, shared by the Mega Drive (md_battery.c), the Super Nintendo (snes_battery.c) and the
 * PC Engine (pce_backup.c): a versioned 112-byte header, then the bytes the game wrote. Load at start, save when the memory has
 * been quiet for two seconds or at once with force, atomic write (a staged file, then a replace). A machine file describes its
 * format (RrCartSaveFormat) and owns one RrCartSave; the rules are written once, here. Original RetroRecomp code: MIT. */
#ifndef RR_CART_SAVE_H
#define RR_CART_SAVE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <wchar.h>

enum {
    /* A file the game cannot use is moved to "<file>.unusable-N" and the game starts blank, with notice 1 (notice 2 when it
     * cannot be moved: the file stays untouched and nothing is saved this session). Without the flag such a file is left
     * alone, the open fails and nothing is saved. Never deleted, never overwritten. */
    RR_CART_SAVE_SET_ASIDE = 1,
    /* A file that exists and cannot be read: notice 2, left alone, nothing written over it. */
    RR_CART_SAVE_NOTICE_UNREADABLE = 2
};

typedef struct {
    uint8_t magic[8];
    unsigned flags;            /* RR_CART_SAVE_* */
    size_t capacity;           /* the largest memory (and the size of the two buffers below) */
    unsigned identity_words;   /* 32-bit words stored from header offset 16 that the file must repeat (0 or 3) */
    unsigned hash_offset;      /* the FNV-1a 64 of the memory: low word here, high word 4 bytes after */
} RrCartSaveFormat;

typedef struct {
    const RrCartSaveFormat *format;
    uint8_t *saved, *observed;   /* `format->capacity` bytes each, owned by the machine file */
    wchar_t path[32768];
    bool active;
    unsigned notice;             /* 0 nothing to say; 1 an unusable file was set aside; 2 it could not be, saving is off */
    uint64_t last_check, last_changed, retry_at;
} RrCartSave;

/* "<exe folder>/datas/saves/<game>-<card>.rrsram" */
bool rr_cart_save_path(wchar_t *path, size_t capacity);
/* Back to "nothing opened": inactive, no notice. */
void rr_cart_save_reset(RrCartSave *save);
/* Called once with the checked file's bytes (NULL when there is nothing to load: no file, or one set aside) so the machine
 * takes them; it returns the machine's memory, which is what is saved from then on. */
typedef const uint8_t *(*RrCartSaveInstall)(void *context, const uint8_t *payload);
/* Opens the file for a memory of `size` bytes. `words` are the identity words of the format. True: saving is on, or `path` is
 * NULL (off by design). False: refused (size, path or an unusable or unreadable file), the game starts anyway. */
bool rr_cart_save_open(RrCartSave *save, const wchar_t *path, size_t size, const uint32_t *words,
                       RrCartSaveInstall install, void *context);
/* True once a file is open. */
bool rr_cart_save_active(const RrCartSave *save);
/* Writes the memory when it has been quiet for two seconds, or at once with force. False: this write failed (retried later).
 * Call only when active. `memory` NULL: only the pacing is applied. */
bool rr_cart_save_flush(RrCartSave *save, const uint8_t *memory, size_t size, const uint32_t *words, uint64_t now_ms, bool force);
#endif
