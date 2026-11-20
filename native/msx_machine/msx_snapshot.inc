/* In-process snapshots of the MSX game for multiplayer (hostkit.h, "Multiplayer"): the rollback tier saves one a frame and loads one
 * a correction, the host's F8 / F9 for everyone are the same snapshots; and the digest the session compares. MIT, Retro-Recomp.
 * Included by msx_player.c after its disk code and the play's disk-request rule.
 *
 * A snapshot is a short head of what the player keeps beside the machine (the disk in drive A, the other disks the game has written
 * so far, the disk-request rule, the keyboard matrix and the joysticks the adapter set), then the quick state's body
 * (msx_state_file.inc: the build binding, the CPU, the whole machine with the disk in drive A). Fixed-width little-endian fields,
 * never a C layout or an address: the same bytes on Windows and Linux. Memory only, never a file, no envelope, no allocation per
 * call; taken and loaded at the service point (the frame's end), where the quick states already are. A load is checked whole
 * (the head, then the body on the machine's scratch copy) before anything is applied; a buffer of another size is refused. */

#define MSX_SNAP_MAGIC 0x31504E5358534D52ull       /* "RMSXSNP1" read little-endian */
static uint8_t msx_snap_scratch[MSX_STATE_CAPACITY];

/* The head, in the io's mode; in CHECK it only reads and validates (the values land in `want`). */
typedef struct { unsigned disk; uint32_t ever; } MsxSnapHead;

static void msx_snap_head(RetroStateIO *io, MsxSnapHead *want)
{
    if (rr_state_word(io, MSX_SNAP_MAGIC, 8, UINT64_MAX) != MSX_SNAP_MAGIC)
        io->ok = false;
#if RR_MSX_DISKS
    uint32_t ever = 0;
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n)
        if (disk_ever[n]) ever |= 1u << n;
    want->disk = (unsigned)rr_state_word(io, disk_index, 1, RR_MSX_DISKS - 1);
    want->ever = (uint32_t)rr_state_word(io, ever, 2, (1u << RR_MSX_DISKS) - 1);
    /* A write of this frame the service has not taken yet (fdc.disk[0].written): kept as it is, as the machine left it. */
    const uint8_t written = (uint8_t)rr_state_word(io, fdc.disk[0].written, 1, 1);
    /* The written disks other than the one in drive A (the body holds that one). */
    for (unsigned n = 0; n < RR_MSX_DISKS && io->ok; ++n)
        if ((want->ever >> n & 1) && n != want->disk)
            rr_state_bytes(io, disk_data[n], disk_sizes[n]);
    /* The drive's command counters, from which the disk-request rule takes each frame's commands (media_request.h). */
    const uint32_t commands = (uint32_t)rr_state_word(io, fdc.commands, 4, UINT32_MAX);
    const uint32_t boot_reads = (uint32_t)rr_state_word(io, fdc.boot_reads, 4, UINT32_MAX);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        fdc.disk[0].written = written;
        fdc.commands = commands;
        fdc.boot_reads = boot_reads;
    }
#if RR_MSX_DISKS > 1
    RrMediaRequest q = play_media;
    q.quiet = (uint32_t)rr_state_word(io, q.quiet, 4, UINT32_MAX);
    q.still = (uint32_t)rr_state_word(io, q.still, 4, UINT32_MAX);
    q.last_command = rr_state_word(io, q.last_command, 8, UINT64_MAX);
    q.pending = rr_state_word(io, q.pending, 8, UINT64_MAX);
    q.still_frames = (uint32_t)rr_state_word(io, q.still_frames, 4, UINT32_MAX);
    q.picture = (uint32_t)rr_state_word(io, q.picture, 4, UINT32_MAX);
    q.have_picture = (int)rr_state_word(io, (uint64_t)q.have_picture, 1, 1);
    q.answered = (uint32_t)rr_state_word(io, q.answered, 4, UINT32_MAX);
    uint32_t seen_commands = (uint32_t)rr_state_word(io, play_media_commands, 4, UINT32_MAX);
    uint32_t seen_boot = (uint32_t)rr_state_word(io, play_media_boot, 4, UINT32_MAX);
    int ready = (int)rr_state_word(io, (uint64_t)play_media_ready, 1, 1);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        play_media = q;
        play_media_commands = seen_commands;
        play_media_boot = seen_boot;
        play_media_ready = ready;
    }
#endif
#else
    want->disk = 0;
    want->ever = 0;
#endif
    uint8_t keys_now[16], joy_now[2];
    memcpy(keys_now, machine.keys, sizeof keys_now);
    memcpy(joy_now, machine.joystick, sizeof joy_now);
    rr_state_bytes(io, keys_now, sizeof keys_now);
    rr_state_bytes(io, joy_now, sizeof joy_now);
    if (io->mode == RR_STATE_APPLY && io->ok) {
        memcpy(machine.keys, keys_now, sizeof keys_now);
        memcpy(machine.joystick, joy_now, sizeof joy_now);
    }
}

static size_t msx_snap_save(void *buffer, size_t capacity)
{
    MsxSnapHead head;
    RetroStateIO io = {(uint8_t *)buffer, capacity, 0, RR_STATE_WRITE, true};
    msx_snap_head(&io, &head);
    msx_state_picture = 0;                       /* the next frame draws the picture again: not stored */
    msx_state_body(&io);
    msx_state_picture = 1;
    return io.ok ? io.pos : 0;
}

static bool msx_snap_load(const void *buffer, size_t size)
{
    MsxSnapHead head;
    RetroStateIO check = {(uint8_t *)buffer, size, 0, RR_STATE_CHECK, true};
    msx_snap_head(&check, &head);
    if (!check.ok)
        return false;
#if RR_MSX_DISKS
    /* The body's controller holds the disk in drive A: the snapshot's disk goes in before the body is checked. */
    const unsigned before = disk_index;
    if (head.disk != disk_index) {
        disk_take_written();
        disk_index = head.disk;
        msx_fdc_insert(&fdc, 0, disk_data[disk_index], disk_sizes[disk_index], 0);
    }
#endif
    msx_state_picture = 0;
    msx_state_body(&check);
    msx_state_picture = 1;
    if (!check.ok || check.pos != size) {
#if RR_MSX_DISKS
        if (before != disk_index) {
            disk_index = before;
            msx_fdc_insert(&fdc, 0, disk_data[disk_index], disk_sizes[disk_index], 0);
        }
#endif
        return false;
    }
    RetroStateIO apply = {(uint8_t *)buffer, size, 0, RR_STATE_APPLY, true};
    msx_snap_head(&apply, &head);
#if RR_MSX_DISKS
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n)
        disk_ever[n] = (uint8_t)(head.ever >> n & 1);
#endif
    msx_state_picture = 0;
    msx_state_body(&apply);
    msx_state_picture = 1;
    if (!apply.ok)
        return false;                                /* not reached: the same bytes passed the check */
    handed_this_frame = machine.line >= machine.vblank_line;
    return true;
}

static size_t msx_snap_bound(void)
{
    static size_t bound;
    if (!bound) {
        size_t now = msx_snap_save(msx_snap_scratch, sizeof msx_snap_scratch);
        if (!now)
            return 0;
        bound = now;
#if RR_MSX_DISKS
        /* Room for every disk written (each but the one in drive A, which the body already holds, at the largest size). */
        for (unsigned n = 0; n < RR_MSX_DISKS; ++n)
            bound += disk_sizes[n];
#endif
    }
    return bound;
}

/* FNV-1a 64 over a snapshot's bytes: the deterministic state after the last frame, in the order the snapshot names its fields. */
static uint64_t msx_snap_digest(void)
{
    const size_t n = msx_snap_save(msx_snap_scratch, sizeof msx_snap_scratch);
    uint64_t h = 1469598103934665603ull;
    for (size_t i = 0; i < n; ++i) { h ^= msx_snap_scratch[i]; h *= 1099511628211ull; }
    return n ? h : 0;
}

/* What a frame does outside the machine (msx_effects_allowed, msx_player.c): off for silent frames and for a guest during a session. */
static void msx_side_effects(bool allowed) { msx_effects_allowed = allowed; }

/* The game's own saves in a session (hostkit.h session_save, session ABI 8): the host's travel to every seat for the match, in
 * memory only (a guest writes no file, msx_effects_allowed). The image, little-endian: "RMSXSAV1", the battery SRAM (u16 size,
 * then its bytes), then the disks (u8 count; each as the sectors that differ from the embedded disk: u16 count, then u16 sector
 * and its 512 bytes each), so a disk game's few saved sectors travel, not its whole disks. Every seat then plays the same
 * bytes: the SRAM and the disk in drive A are in the digest (the quick state's body), the other disks are put the same
 * everywhere. A host whose rewritten sectors would pass the session's bound plays the embedded disks for the match like every
 * seat, keeps its copies untouched and is told. The MSX2 clock keeps no file (it starts at the same date on every machine). A
 * restart for everyone keeps these bytes, as the machine's own reset does (power_on leaves the SRAM and the disks). */
#include "hostkit/hostkit_session.h"
#define MSX_SAVE_MAGIC 0x3156415358534D52ull       /* "RMSXSAV1" read little-endian */

static void msx_save_word(uint8_t *out, size_t *at, size_t capacity, uint64_t value, unsigned bytes)
{
    for (unsigned i = 0; i < bytes; ++i, ++*at)
        if (out && *at < capacity) out[*at] = (uint8_t)(value >> 8 * i);
}

static bool msx_save_take(const uint8_t *in, size_t size, size_t *at, unsigned bytes, uint32_t *value)
{
    if (*at + bytes > size) return false;
    uint32_t v = 0;
    for (unsigned i = 0; i < bytes; ++i) v |= (uint32_t)in[*at + i] << 8 * i;
    *at += bytes;
    *value = v;
    return true;
}

/* The image's size, and its bytes when `out` has room; `disks` 0: the disks as embedded (no sector). */
static size_t msx_session_image(uint8_t *out, size_t capacity, int disks)
{
    size_t at = 0;
    msx_save_word(out, &at, capacity, MSX_SAVE_MAGIC, 8);
    msx_save_word(out, &at, capacity, sram_size, 2);
    if (out && at + sram_size <= capacity) memcpy(out + at, sram_bytes, sram_size);
    at += sram_size;
#if RR_MSX_DISKS
    size_t total = 0, base = 0;
    const uint8_t *embedded = rr_resource(106, &total);
    msx_save_word(out, &at, capacity, RR_MSX_DISKS, 1);
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) {
        const unsigned sectors = disk_sizes[n] / MSX_FDC_SECTOR;
        unsigned changed = 0;
        if (disks && embedded)
            for (unsigned k = 0; k < sectors; ++k)
                changed += memcmp(disk_data[n] + (size_t)k * MSX_FDC_SECTOR, embedded + base + (size_t)k * MSX_FDC_SECTOR,
                                  MSX_FDC_SECTOR) != 0;
        msx_save_word(out, &at, capacity, changed, 2);
        for (unsigned k = 0; changed && k < sectors; ++k) {
            const uint8_t *sector = disk_data[n] + (size_t)k * MSX_FDC_SECTOR;
            if (!memcmp(sector, embedded + base + (size_t)k * MSX_FDC_SECTOR, MSX_FDC_SECTOR)) continue;
            msx_save_word(out, &at, capacity, k, 2);
            if (out && at + MSX_FDC_SECTOR <= capacity) memcpy(out + at, sector, MSX_FDC_SECTOR);
            at += MSX_FDC_SECTOR;
        }
        base += disk_sizes[n];
    }
#else
    (void)disks;
#endif
    return at;
}

/* Checks the whole image (`apply` 0), or puts it in memory (`apply` 1, only after a check passed). */
static bool msx_session_image_take(const uint8_t *in, size_t size, int apply)
{
    size_t at = 0;
    uint32_t low = 0, high = 0, value = 0;
    if (!in || !msx_save_take(in, size, &at, 4, &low) || !msx_save_take(in, size, &at, 4, &high)
        || ((uint64_t)high << 32 | low) != MSX_SAVE_MAGIC)
        return false;
    if (!msx_save_take(in, size, &at, 2, &value) || value != sram_size || at + sram_size > size)
        return false;
    if (apply) memcpy(sram_bytes, in + at, sram_size);
    at += sram_size;
#if RR_MSX_DISKS
    size_t total = 0, base = 0;
    const uint8_t *embedded = rr_resource(106, &total);
    if (!embedded || !msx_save_take(in, size, &at, 1, &value) || value != RR_MSX_DISKS)
        return false;
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) {
        const unsigned sectors = disk_sizes[n] / MSX_FDC_SECTOR;
        uint32_t count = 0;
        if (!msx_save_take(in, size, &at, 2, &count) || count > sectors)
            return false;
        if (apply) memcpy(disk_data[n], embedded + base, disk_sizes[n]);     /* this seat's own copy never counts */
        for (uint32_t i = 0; i < count; ++i) {
            uint32_t k = 0;
            if (!msx_save_take(in, size, &at, 2, &k) || k >= sectors || at + MSX_FDC_SECTOR > size)
                return false;
            if (apply) memcpy(disk_data[n] + (size_t)k * MSX_FDC_SECTOR, in + at, MSX_FDC_SECTOR);
            at += MSX_FDC_SECTOR;
        }
        base += disk_sizes[n];
    }
    if (apply)
        for (unsigned n = 0; n < RR_MSX_DISKS; ++n) disk_dirty[n] = 0;     /* nothing of this seat's to write */
#endif
    return at == size;
}

/* The match's image (the host's own from msx_session_save, or the host's handed to a guest) and the machine at power-on, kept in a
 * session only. The guest's loop runs its first frame before SETUP comes, on this seat's own saves: session_begin (SETUP) puts
 * every seat back at power-on, then lays the match's image, so a game that reads its save in that first frame still starts from
 * the host's on every seat. */
static uint8_t *msx_session_held;
static size_t msx_session_held_size;
static uint8_t *msx_session_start;
static size_t msx_session_start_size;

static void msx_session_hold(const void *image, size_t size)
{
    uint8_t *copy = (uint8_t *)malloc(size);
    if (!copy) return;
    memcpy(copy, image, size);
    free(msx_session_held);
    msx_session_held = copy;
    msx_session_held_size = size;
}

/* Called once after power_on, before the guest's first instruction, when this game is in a session. */
static void msx_session_keep_start(void)
{
    const size_t bound = msx_snap_bound();
    msx_session_start = bound ? (uint8_t *)malloc(bound) : NULL;
    msx_session_start_size = msx_session_start ? msx_snap_save(msx_session_start, bound) : 0;
    if (!msx_session_start_size) { free(msx_session_start); msx_session_start = NULL; }
}

static void msx_session_begin(uint64_t clock)
{
    (void)clock;                                     /* the MSX2 clock starts on the same date on every machine (msx_rtc_reset) */
    if (msx_session_start) msx_snap_load(msx_session_start, msx_session_start_size);
    if (msx_session_held) msx_session_image_take(msx_session_held, msx_session_held_size, 1);
}

static size_t msx_session_save(void *out, size_t capacity)
{
    if (!sram_size && !RR_MSX_DISKS)
        return 0;                                    /* a game with no save */
    int disks = 1;
    size_t size = msx_session_image(NULL, 0, 1);
#if RR_MSX_DISKS
    if (size > RRHK_SESSION_MAX_SAVE) {
        /* Too many rewritten sectors to send: this match plays the embedded disks on every seat, the host's included, and the
         * host's copies stay as they are (nothing is written beside the game until it closes). */
        disks = 0;
        size = msx_session_image(NULL, 0, 0);
        static int told;
        if (out && !told) {
            told = 1;
            size_t total = 0, base = 0;
            const uint8_t *embedded = rr_resource(106, &total);
            for (unsigned n = 0; embedded && n < RR_MSX_DISKS; ++n) {
                memcpy(disk_data[n], embedded + base, disk_sizes[n]);
                disk_dirty[n] = 0;
                base += disk_sizes[n];
            }
            disk_copies = 0;
            fprintf(stderr, "[msx] the disks' saved sectors pass the session's bound: the match plays the original disks\n");
            rrhk_notice(rrhk_tr("Your disk saves are too large to share: this match plays the original disks",
                                "Sauvegardes disquette trop grandes a partager : la partie joue les disquettes d'origine"), 8000);
        }
    }
#endif
    if (!out)
        return size;
    if (capacity < size)
        return 0;
    if (msx_session_image((uint8_t *)out, capacity, disks) != size)
        return 0;
    msx_session_hold(out, size);                     /* the host plays the match on the bytes it sends */
    return size;
}

static bool msx_session_save_put(const void *in, size_t size)
{
    if (!msx_session_image_take((const uint8_t *)in, size, 0))
        return false;                                /* another game's image, or a broken one: nothing is changed */
    msx_session_hold(in, size);
    msx_session_image_take((const uint8_t *)in, size, 1);
    return true;                                     /* session_begin, which follows, lays it again over the power-on state */
}

/* The previous file kept as "<file>.bak" before the host's save is written back: a copy staged beside it, then a rename. No
 * file yet: nothing to keep. */
static bool msx_keep_backup(const wchar_t *path)
{
    if (!rr_exists(path))
        return true;
    static wchar_t staged[32800], backup[32800];
    swprintf(backup, sizeof backup / sizeof *backup, L"%ls.bak", path);
    swprintf(staged, sizeof staged / sizeof *staged, L"%ls.bak.tmp", path);
    rr_remove(staged);
    if (!rr_copy_new(path, staged))
        return false;
    if (rr_replace(staged, backup))
        return true;
    rr_remove(staged);
    return false;
}

/* The host, when a match ends cleanly (hostkit.h session_save_commit): nobody wrote a save file during the match, so the host's
 * own files take the match's save now, once: the SRAM file (written atomically by msx_sram.c) when the SRAM changed from what
 * the host sent, and the copy of each disk the game wrote (disks_save, a staged file then a rename), each previous file kept as
 * ".bak". A host whose disks were too large to share played the embedded disks: its copies are not touched. */
static bool msx_session_save_commit(void)
{
    bool ok = true;
    if (sram_size) {
        const bool changed = !msx_session_held || msx_session_held_size < 10u + sram_size
                             || memcmp(msx_session_held + 10, sram_bytes, sram_size) != 0;
        static wchar_t path[32768];
        if (changed && msx_sram_notice() == 2)
            ok = false;                                  /* the file was unreadable at the start: saving is off, nothing is written */
        else if (changed && msx_sram_path(path, sizeof path / sizeof *path))
            ok = msx_keep_backup(path) && msx_sram_flush(SDL_GetTicks64(), true) && ok;
    }
#if RR_MSX_DISKS
    disk_take_written();
    if (disk_copies) {
        for (unsigned n = 0; n < RR_MSX_DISKS; ++n) {
            wchar_t path[1100];
            if (disk_dirty[n] && disk_copy_path(n, path) && !msx_keep_backup(path)) {
                ok = false;                              /* no backup: this disk's copy is not rewritten */
                disk_dirty[n] = 0;
            }
        }
        disks_save();
        ok = !disk_dirty_any() && ok;
    }
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n)
        fprintf(stderr, "[msx] match end: disk %u %016llx\n", n + 1, (unsigned long long)msx_sram_hash(disk_data[n], disk_sizes[n]));
#endif
    if (sram_size)
        fprintf(stderr, "[msx] match end: SRAM %016llx\n", (unsigned long long)msx_sram_hash(sram_bytes, sram_size));
    return ok;
}

/* `--snap-probe AT:N` (headless, a development check): at the service of frame AT a snapshot is taken (and taken again over a
 * buffer of other bytes: the same bytes; a load of the wrong size is refused and changes nothing), the digest of each of the N
 * frames after it is kept, the snapshot is loaded back and the same N frames run again: every digest must be equal. The route's
 * own state (its next event, its disk-request rule) is put back with it, as a session's kit gives the same inputs again. Prints one
 * line on stderr; exit 0 when everything holds, 5 when anything differs. */
static unsigned long snap_probe_at, snap_probe_n;
static int snap_probe_phase;
static uint64_t *snap_probe_digests;
static uint32_t *snap_probe_pictures;
static unsigned long snap_probe_picture_mismatches;
static uint8_t *snap_probe_a, *snap_probe_b;
static size_t snap_probe_size, snap_probe_bound;
static int snap_probe_same, snap_probe_refused;
static unsigned long snap_probe_bad = ~0ul, snap_probe_mismatches;
static RrMediaRequest snap_probe_media;
static uint32_t snap_probe_commands, snap_probe_boot;
static unsigned snap_probe_disk;

static int snap_probe_option(const char *v)
{
    if (sscanf(v, "%lu:%lu", &snap_probe_at, &snap_probe_n) != 2 || !snap_probe_n || snap_probe_n > 100000)
        return -1;
    snap_probe_digests = (uint64_t *)calloc(snap_probe_n + 1, sizeof *snap_probe_digests);
    snap_probe_pictures = (uint32_t *)calloc(snap_probe_n + 1, sizeof *snap_probe_pictures);
    snap_probe_a = (uint8_t *)malloc(MSX_STATE_CAPACITY);
    snap_probe_b = (uint8_t *)malloc(MSX_STATE_CAPACITY);
    if (!snap_probe_digests || !snap_probe_pictures || !snap_probe_a || !snap_probe_b)
        return -1;
    snap_probe_phase = 1;
    return 1;
}

static void snap_probe_route(int save)
{
    if (save) {
        snap_probe_media = route_media; snap_probe_commands = route_media_commands; snap_probe_boot = route_media_boot;
        snap_probe_disk = route_disk_now;
        return;
    }
    route_media = snap_probe_media; route_media_commands = snap_probe_commands; route_media_boot = snap_probe_boot;
    route_disk_now = snap_probe_disk;
    route_next_event = 0;                        /* the events up to the loaded frame were applied before the snapshot */
    while (route_next_event < route_event_count && route_events[route_next_event].frame <= machine.frames)
        ++route_next_event;
}

static void snap_probe_service(void)
{
    if (!snap_probe_phase || machine.frames < snap_probe_at)
        return;
    const unsigned long k = (unsigned long)(machine.frames - snap_probe_at);
    if (snap_probe_phase == 1) {
        snap_probe_bound = msx_snap_bound();
        snap_probe_size = msx_snap_save(snap_probe_a, MSX_STATE_CAPACITY);
        memset(snap_probe_b, 0xA5, MSX_STATE_CAPACITY);
        snap_probe_same = snap_probe_size && msx_snap_save(snap_probe_b, MSX_STATE_CAPACITY) == snap_probe_size
                          && !memcmp(snap_probe_a, snap_probe_b, snap_probe_size) && snap_probe_size <= snap_probe_bound;
        const uint64_t before = msx_snap_digest();
        snap_probe_refused = !msx_snap_load(snap_probe_a, snap_probe_size - 1) && msx_snap_digest() == before;
        snap_probe_digests[0] = before;
        snap_probe_route(1);
        snap_probe_phase = 2;
    } else if (snap_probe_phase == 2) {
        snap_probe_digests[k] = msx_snap_digest();
        snap_probe_pictures[k] = msx_frame_hash(&machine);
        if (k >= snap_probe_n) {
            if (!msx_snap_load(snap_probe_a, snap_probe_size)) snap_probe_mismatches = ~0ul;
            snap_probe_route(0);
            if (msx_snap_digest() != snap_probe_digests[0]) { ++snap_probe_mismatches; snap_probe_bad = 0; }
            snap_probe_phase = 3;
        }
    } else if (snap_probe_phase == 3) {
        if (msx_snap_digest() != snap_probe_digests[k]) {
            ++snap_probe_mismatches;
            if (snap_probe_bad == ~0ul) snap_probe_bad = k;
        }
        if (k >= 1 && msx_frame_hash(&machine) != snap_probe_pictures[k])
            ++snap_probe_picture_mismatches;      /* from the first frame drawn again after the load */
        if (k >= snap_probe_n) {
            const int pass = snap_probe_same && snap_probe_refused && !snap_probe_mismatches && !snap_probe_picture_mismatches;
            fprintf(stderr, "snap-probe: %s at %lu, %lu frames, %zu bytes (bound %zu), same over other bytes %d, wrong size refused %d, "
                    "mismatches %lu, first at +%ld, pictures differing %lu\n", pass ? "PASS" : "FAIL", snap_probe_at, snap_probe_n,
                    snap_probe_size, snap_probe_bound, snap_probe_same, snap_probe_refused, snap_probe_mismatches,
                    snap_probe_bad == ~0ul ? -1L : (long)snap_probe_bad, snap_probe_picture_mismatches);
            exit(pass ? 0 : 5);
        }
    }
}
