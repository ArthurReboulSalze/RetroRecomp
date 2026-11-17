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
    msx_state_body(&io);
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
    msx_state_body(&check);
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
    msx_state_body(&apply);
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

/* What a frame does outside the machine (the cartridge's SRAM file, the copies of written disks): off for silent frames and for a
 * guest during a session. */
static bool msx_effects_allowed = true;
static void msx_side_effects(bool allowed) { msx_effects_allowed = allowed; }

/* `--snap-probe AT:N` (headless, a development check): at the service of frame AT a snapshot is taken (and taken again over a
 * buffer of other bytes: the same bytes; a load of the wrong size is refused and changes nothing), the digest of each of the N
 * frames after it is kept, the snapshot is loaded back and the same N frames run again: every digest must be equal. The route's
 * own state (its next event, its disk-request rule) is put back with it, as a session's kit gives the same inputs again. Prints one
 * line on stderr; exit 0 when everything holds, 5 when anything differs. */
static unsigned long snap_probe_at, snap_probe_n;
static int snap_probe_phase;
static uint64_t *snap_probe_digests;
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
    snap_probe_a = (uint8_t *)malloc(MSX_STATE_CAPACITY);
    snap_probe_b = (uint8_t *)malloc(MSX_STATE_CAPACITY);
    if (!snap_probe_digests || !snap_probe_a || !snap_probe_b)
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
        if (k >= snap_probe_n) {
            const int pass = snap_probe_same && snap_probe_refused && !snap_probe_mismatches;
            fprintf(stderr, "snap-probe: %s at %lu, %lu frames, %zu bytes (bound %zu), same over other bytes %d, wrong size refused %d, "
                    "mismatches %lu, first at +%ld\n", pass ? "PASS" : "FAIL", snap_probe_at, snap_probe_n, snap_probe_size,
                    snap_probe_bound, snap_probe_same, snap_probe_refused, snap_probe_mismatches,
                    snap_probe_bad == ~0ul ? -1L : (long)snap_probe_bad);
            exit(pass ? 0 : 5);
        }
    }
}
