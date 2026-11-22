/* The copies of the disks a game writes, kept beside the game: machine-neutral, MIT, Retro-Recomp. Included by a disk machine's
 * player (the Amstrad CPC first; the MSX2+'s disks later, with a proof that its files stay the same), compiled with platform_io.c.
 *
 * A disk game's disks are embedded in the game and never changed there. What the game writes goes to the disk in memory (the
 * machine's controller writes `data`), and to a copy beside the game's settings, `<folder>/disk-<n>.dsk`:
 *   - at the start, a copy whose size is the disk's replaces the embedded bytes in memory (a copy of another size is not this
 *     disk's: the embedded one is kept);
 *   - a write marks the disk (rr_disk_copies_written); once the disks have been quiet for RR_DISK_COPY_QUIET frames, the marked
 *     ones are written (rr_disk_copies_frame), and again when the game closes (rr_disk_copies_save);
 *   - each copy is written beside its file (`.tmp`), flushed, then put in its place: a write that fails leaves the old copy
 *     whole and the disk marked, to be tried again;
 *   - at the clean end of a multiplayer match the host writes the match's disks once (rr_disk_copies_commit), each previous copy
 *     kept as `.bak` first; a copy whose `.bak` cannot be made is not rewritten.
 * Whether a frame may write at all (a silent frame, a guest in a session: never) is the machine's `allowed`. A copies folder that
 * is empty (a headless run) reads and writes nothing. */
#ifndef RETRO_RECOMP_DISK_COPIES_INC
#define RETRO_RECOMP_DISK_COPIES_INC
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

#include "platform_io.h"

#define RR_DISK_COPIES_MAX 16
#define RR_DISK_COPY_QUIET 180                   /* frames with no write before the copies are written: about three seconds */

typedef struct {
    uint8_t *data;                               /* the disk the machine reads and writes, in memory */
    uint32_t size;
    uint8_t dirty;                               /* written since its copy was last written */
} RrDiskImage;

typedef struct {
    RrDiskImage disk[RR_DISK_COPIES_MAX];
    unsigned count;
    char folder[1024];                           /* UTF-8; empty: no copies */
    unsigned quiet;                              /* frames since the last write */
} RrDiskCopies;

/* `folder` NULL or empty: a run that keeps no copy. Returns 0 when the folder's name is too long (no copies then). */
static int rr_disk_copies_init(RrDiskCopies *c, const char *folder)
{
    c->folder[0] = 0;
    c->quiet = 0;
    if (!folder || !folder[0]) return 1;
    if (strlen(folder) >= sizeof c->folder) return 0;
    strcpy(c->folder, folder);
    return 1;
}

static int rr_disk_copies_enabled(const RrDiskCopies *c) { return c->folder[0] != 0; }

static int rr_disk_copy_path(const RrDiskCopies *c, unsigned n, wchar_t *out, size_t capacity)
{
    char path[1100];
    if (!rr_disk_copies_enabled(c) || snprintf(path, sizeof path, "%s/disk-%u.dsk", c->folder, n + 1) >= (int)sizeof path) return 0;
    return rr_from_utf8(path, out, capacity);
}

/* The copies the game wrote in earlier runs, into memory; the number of disks that took one. */
static unsigned rr_disk_copies_load(RrDiskCopies *c)
{
    unsigned taken = 0;
    for (unsigned n = 0; n < c->count; ++n) {
        wchar_t path[1100];
        if (!rr_disk_copy_path(c, n, path, sizeof path / sizeof *path)) continue;
        FILE *f = rr_fopen(path, L"rb");
        if (!f) continue;
        static uint8_t copy[4u << 20];
        size_t got = c->disk[n].size <= sizeof copy ? fread(copy, 1, c->disk[n].size + 1u, f) : 0;
        fclose(f);
        if (got == c->disk[n].size) {            /* a copy of another size is not this disk's: the embedded one is kept */
            memcpy(c->disk[n].data, copy, got);
            ++taken;
        }
    }
    return taken;
}

static void rr_disk_copies_written(RrDiskCopies *c, unsigned n)
{
    if (n < c->count) c->disk[n].dirty = 1;
    c->quiet = 0;
}

static int rr_disk_copies_dirty_any(const RrDiskCopies *c)
{
    for (unsigned n = 0; n < c->count; ++n) if (c->disk[n].dirty) return 1;
    return 0;
}

/* Every marked disk to its copy; 1 when none is left marked (a run without copies forgets the marks: it writes nothing). */
static int rr_disk_copies_save(RrDiskCopies *c)
{
    if (!rr_disk_copies_enabled(c)) {
        for (unsigned n = 0; n < c->count; ++n) c->disk[n].dirty = 0;
        return 1;
    }
    for (unsigned n = 0; n < c->count; ++n) {
        if (!c->disk[n].dirty) continue;
        wchar_t path[1100], staged[1110];
        if (!rr_disk_copy_path(c, n, path, sizeof path / sizeof *path)) continue;
        swprintf(staged, sizeof staged / sizeof *staged, L"%ls.tmp", path);
        FILE *f = rr_fopen(staged, L"wb");
        if (!f) continue;
        int ok = fwrite(c->disk[n].data, 1, c->disk[n].size, f) == c->disk[n].size && rr_flush_file(f);
        ok = fclose(f) == 0 && ok;
        if (ok && rr_replace(staged, path)) c->disk[n].dirty = 0;
        else rr_remove(staged);
    }
    return !rr_disk_copies_dirty_any(c);
}

/* Once a frame, after the machine marked this frame's writes: `written_now`, a disk was written this frame; `allowed`, this frame
 * may write files. The marked disks are written once the disks have been quiet for RR_DISK_COPY_QUIET frames; a frame that may not
 * write keeps them due for the next one that may. */
static void rr_disk_copies_frame(RrDiskCopies *c, int written_now, int allowed)
{
    if (written_now) { c->quiet = 0; return; }
    if (++c->quiet < RR_DISK_COPY_QUIET) return;
    if (!rr_disk_copies_dirty_any(c)) { c->quiet = RR_DISK_COPY_QUIET; return; }
    if (allowed) rr_disk_copies_save(c);
    c->quiet = RR_DISK_COPY_QUIET - 1;           /* due again at the next frame while a disk is still marked */
}

/* The previous file kept as "<file>.bak": a copy staged beside it, then a rename. No file yet: nothing to keep. */
static int rr_keep_backup(const wchar_t *path)
{
    if (!rr_exists(path)) return 1;
    static wchar_t staged[1120], backup[1120];
    swprintf(backup, sizeof backup / sizeof *backup, L"%ls.bak", path);
    swprintf(staged, sizeof staged / sizeof *staged, L"%ls.bak.tmp", path);
    rr_remove(staged);
    if (!rr_copy_new(path, staged)) return 0;
    if (rr_replace(staged, backup)) return 1;
    rr_remove(staged);
    return 0;
}

/* The host, at the clean end of a match: each marked disk's previous copy kept as ".bak", then the match's disk written. A disk
 * whose ".bak" cannot be made is not rewritten (its mark is dropped). 1 when every marked disk was written. */
static int rr_disk_copies_commit(RrDiskCopies *c)
{
    if (!rr_disk_copies_enabled(c)) return 1;
    int ok = 1;
    for (unsigned n = 0; n < c->count; ++n) {
        wchar_t path[1100];
        if (c->disk[n].dirty && rr_disk_copy_path(c, n, path, sizeof path / sizeof *path) && !rr_keep_backup(path)) {
            c->disk[n].dirty = 0;
            ok = 0;
        }
    }
    return rr_disk_copies_save(c) && ok;
}
#endif
