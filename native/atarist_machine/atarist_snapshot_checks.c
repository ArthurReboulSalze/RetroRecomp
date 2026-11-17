/* Native driver of the Atari ST snapshot checks (multiplayer rollback). Original Retro-Recomp code, MIT; it is linked with Hatari (GPL-2.0, licenses/hatari.md), so a program built
 * with it is distributed under the GPL.
 *
 * The programs are the tiny 68000 programs authored for the hardware checks (tools/atarist_hardware_check.py: no ROM, no TOS, no game), booted as the TOS image of a session; this
 * driver runs the checks of the snapshot contract (docs/HOST_KIT.md, multiplayer) on the very functions a match calls (atarist_snapshot.h):
 *
 *   atarist_snapshot_checks --tos tos.bin [--disk image.st] [--events file] --frames N --save-at S --span M [--writes]
 *
 *   1. run S frames; the digest D0; save A;
 *   2. run M frames, the digest of each (the timeline T);
 *   3. load A: the digest is D0 at once (before any frame); a save right after the load gives the same digest after a load of it; the wrong size, a damaged header and a snapshot of
 *      another disk are refused and the machine is untouched (D0);
 *   4. run the same M frames with the same events: every digest equals T;
 *   5. a save over a buffer of other bytes is byte for byte the save into a clean one;
 *   6. with --writes: sectors the game wrote (the session's table) are saved, more are written, the load brings the table back (its count and its digest).
 * One JSON line on stdout: "ok" and the numbers (the size of a snapshot, the digests, what failed). The events are applied before the frame they name (the first frame is 0), also
 * after a load (the frame numbers are the machine's own: the frame a snapshot was taken before). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "atarist_session.h"
#include "atarist_snapshot.h"
#ifdef _WIN32
#include <windows.h>
static LONG WINAPI crash_report(EXCEPTION_POINTERS *info) {
    void **sp = (void **)info->ContextRecord->Rsp;
    fprintf(stderr, "[crash %08lx at %p base %p ret %p %p %p]", (unsigned long)info->ExceptionRecord->ExceptionCode, info->ExceptionRecord->ExceptionAddress, (void *)GetModuleHandleA(NULL), sp[0], sp[1], sp[2]);
    return EXCEPTION_EXECUTE_HANDLER;
}
#endif

#define MAX_EVENTS 4096
#define MAX_SPAN 4096
typedef struct { unsigned frame; char kind; int a, b, c, d; } Event;
static Event events[MAX_EVENTS];
static unsigned event_count;

/* The session writes a sector of its own table when Hatari hands one over (src/fdc.c, retrorecomp/atarist_hatari.py); the check hands one over the same way. */
extern void (*rr_fdc_sector_written)(int drive, int track, int side, int sector, const uint8_t *data, int size);

static uint8_t *read_file(const char *path, uint32_t *size) {
    FILE *f = fopen(path, "rb");
    long n;
    uint8_t *data;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    data = (uint8_t *)malloc((size_t)n + 1);
    if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(data); return NULL; }
    fclose(f);
    *size = (uint32_t)n;
    return data;
}

static int read_events(const char *path) {
    FILE *f = fopen(path, "r");
    char line[256];
    if (!f) return 0;
    while (fgets(line, sizeof line, f) && event_count < MAX_EVENTS) {
        Event e;
        char word[16];
        int a = 0, b = 0, c = 0, d = 0, n;
        unsigned frame;
        memset(&e, 0, sizeof e);
        n = sscanf(line, "%u %15s %d %d %d %d", &frame, word, &a, &b, &c, &d);
        if (n < 3) continue;
        e.frame = frame; e.a = a; e.b = b; e.c = c; e.d = d;
        e.kind = !strcmp(word, "joy") ? 'j' : !strcmp(word, "mouse") ? 'm' : !strcmp(word, "key") ? 'k' : 0;
        if (e.kind) events[event_count++] = e;
    }
    fclose(f);
    return 1;
}

static void log_line(const char *line) { (void)line; }

static int run_frame(RrStSession *session, unsigned frame) {
    unsigned n;
    int16_t samples[8192 * 2];
    unsigned bits[2] = {0, 0};
    /* the pads are set at every frame, as the host kit does in a session: the level of the last event at or before this frame (a replay from a load starts from the machine's state, not from a
     * level left by the frames run before it) */
    for (n = 0; n < event_count; ++n) {
        const Event *e = &events[n];
        if (e->kind == 'j' && e->frame <= frame && e->a >= 0 && e->a < 2) bits[e->a] = (unsigned)e->b;
    }
    rr_st_joystick(session, 0, bits[0]);
    rr_st_joystick(session, 1, bits[1]);
    if (rr_st_frame(session) != 0) return 1;
    while (rr_st_audio(session, samples, 8192) > 0) {}
    return 0;
}

static int failures;
static char failed[1024];
static void expect(int condition, const char *what) {
    if (condition) return;
    failures++;
    if (strlen(failed) + strlen(what) + 3 < sizeof failed) { if (failed[0]) strcat(failed, "; "); strcat(failed, what); }
}

int main(int argc, char **argv) {
    const char *tos_path = NULL, *disk_path = NULL, *events_path = NULL, *machine = "st";
    unsigned frames = 200, save_at = 60, span = 40, ram_kb = 1024, frame, n;
    int i, writes_check = 0;
    uint32_t tos_size = 0, disk_size = 0;
    uint8_t *tos, *disk = NULL, *a, *b, *c;
    size_t bound, size_a, size_b, boot_size = 0;
    uint8_t *boot;
    RrStDisk disk_entry;
    RrStGame game;
    RrStSession *session;
    char error[256] = "";
    uint64_t d0, timeline[MAX_SPAN + 1], again[MAX_SPAN + 1], after_load, after_second;
    unsigned diverged_at = 0;
    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--tos") && i + 1 < argc) tos_path = argv[++i];
        else if (!strcmp(argv[i], "--disk") && i + 1 < argc) disk_path = argv[++i];
        else if (!strcmp(argv[i], "--events") && i + 1 < argc) events_path = argv[++i];
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--save-at") && i + 1 < argc) save_at = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--span") && i + 1 < argc) span = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--machine") && i + 1 < argc) machine = argv[++i];
        else if (!strcmp(argv[i], "--writes")) writes_check = 1;
        else { fprintf(stderr, "unknown argument %s\n", argv[i]); return 2; }
    }
    if (!tos_path || span > MAX_SPAN || save_at + span > frames + MAX_SPAN) { fprintf(stderr, "usage: atarist_snapshot_checks --tos tos.bin [--disk image.st] [--events file] --frames N --save-at S --span M [--writes]\n"); return 2; }
    tos = read_file(tos_path, &tos_size);
    if (!tos) { fprintf(stderr, "cannot read the TOS image\n"); return 2; }
    if (disk_path) {
        disk = read_file(disk_path, &disk_size);
        if (!disk) { fprintf(stderr, "cannot read the disk image\n"); return 2; }
    } else {
        disk_size = 737280u;
        disk = (uint8_t *)calloc(1, disk_size);
    }
    if (events_path && !read_events(events_path)) { fprintf(stderr, "cannot read the events\n"); return 2; }
    disk_entry.name = "check.st"; disk_entry.data = disk; disk_entry.size = disk_size;
    memset(&game, 0, sizeof game);
    game.disks = &disk_entry; game.disk_count = 1; game.tos = tos; game.tos_size = tos_size;
    game.machine = machine; game.memory_kb = ram_kb; game.log = log_line;
#ifdef _WIN32
    SetUnhandledExceptionFilter(crash_report);
#endif
    session = rr_st_open(&game, error, sizeof error);
    if (!session) { fprintf(stderr, "the session did not open: %s\n", error); return 2; }
    bound = rr_st_snapshot_bound();
    if (!bound) { printf("{\"ok\":false,\"failed\":\"this machine cannot be saved: the bound is 0\"}\n"); return 1; }
    a = (uint8_t *)malloc(bound); b = (uint8_t *)malloc(bound); c = (uint8_t *)malloc(bound);
    if (!a || !b || !c) { fprintf(stderr, "no memory\n"); return 2; }

    boot = (uint8_t *)malloc(bound);
    if (!boot) { fprintf(stderr, "no memory\n"); return 2; }
    for (frame = 0; frame < save_at; ++frame) {
        if (run_frame(session, frame)) { fprintf(stderr, "frame %u failed: %s\n", frame, rr_st_error(session)); return 2; }
        if (frame == 0) boot_size = rr_st_snapshot_save(session, boot, bound);          /* what the adapter keeps after a match's first frame */
    }
    d0 = rr_st_snapshot_digest(session);
    if (writes_check && rr_fdc_sector_written) {
        uint8_t sector[512];
        memset(sector, 0x5A, sizeof sector);
        rr_fdc_sector_written(0, 1, 0, 3, sector, 512);
        rr_fdc_sector_written(0, 1, 1, 4, sector, 512);
        d0 = rr_st_snapshot_digest(session);
    }
    size_a = rr_st_snapshot_save(session, a, bound);
    expect(size_a > 0 && size_a <= bound, "the save returned 0 or more than the bound");
    for (n = 0; n < span; ++n) {
        timeline[n] = rr_st_snapshot_digest(session);
        if (writes_check && n == span / 2 && rr_fdc_sector_written) {         /* the game writes another sector: the table grows after the snapshot */
            uint8_t sector[512];
            memset(sector, 0xA5, sizeof sector);
            rr_fdc_sector_written(0, 2, 0, 5, sector, 512);
        }
        if (run_frame(session, save_at + n)) { fprintf(stderr, "frame failed: %s\n", rr_st_error(session)); return 2; }
    }
    timeline[span] = rr_st_snapshot_digest(session);
    expect(timeline[span] != d0 || span == 0, "the run did not change the machine (the check proves nothing)");

    /* the load is complete at once: the digest, and a save right after it, before any frame */
    expect(rr_st_snapshot_load(session, a, size_a) == 1, "the load of a snapshot was refused");
    after_load = rr_st_snapshot_digest(session);
    expect(after_load == d0, "the digest after the load is not the digest at the save");
    size_b = rr_st_snapshot_save(session, b, bound);
    expect(size_b == size_a, "a save after a load has another size");
    expect(size_b == size_a && memcmp(a, b, size_a) == 0, "a save right after a load is not byte for byte the first one");
    if (size_b == size_a && memcmp(a, b, size_a) != 0) {
        size_t k, shown = 0;
        for (k = 0; k < size_a && shown < 8; ++k) if (a[k] != b[k]) { fprintf(stderr, "[differs at %zu: %02x %02x]", k, a[k], b[k]); ++shown; }
    }
    /* refusals leave the machine untouched */
    expect(rr_st_snapshot_load(session, a, size_a - 1) == 0, "a snapshot cut by one byte was accepted");
    expect(rr_st_snapshot_load(session, a, size_a + 1) == 0, "a snapshot longer by one byte was accepted");
    memcpy(c, a, size_a); c[0] ^= 0x01;
    expect(rr_st_snapshot_load(session, c, size_a) == 0, "a snapshot with a damaged header was accepted");
    memcpy(c, a, size_a); c[12] ^= 0x01;                                        /* the index of the disk in drive A */
    expect(rr_st_snapshot_load(session, c, size_a) == 0, "a snapshot of another disk was accepted");
    expect(rr_st_snapshot_digest(session) == d0, "a refused load changed the machine");
    /* a save over a buffer of other bytes is byte for byte the save into a clean one */
    memset(c, 0xAA, bound);
    expect(rr_st_snapshot_save(session, c, bound) == size_a && memcmp(a, c, size_a) == 0, "a save over other bytes differs from the first");
    /* the same frames again: every digest equals the timeline */
    for (n = 0; n < span; ++n) {
        again[n] = rr_st_snapshot_digest(session);
        if (writes_check && n == span / 2 && rr_fdc_sector_written) {
            uint8_t sector[512];
            memset(sector, 0xA5, sizeof sector);
            rr_fdc_sector_written(0, 2, 0, 5, sector, 512);
        }
        if (run_frame(session, save_at + n)) { fprintf(stderr, "frame failed: %s\n", rr_st_error(session)); return 2; }
        if (again[n] != timeline[n] && !diverged_at) diverged_at = n + 1;
    }
    again[span] = rr_st_snapshot_digest(session);
    expect(!diverged_at && again[span] == timeline[span], "the frames run again after a load give other digests");
    /* a second load of the same snapshot, now from the end of the timeline, and once more the same frames */
    expect(rr_st_snapshot_load(session, a, size_a) == 1 && rr_st_snapshot_digest(session) == d0, "the second load does not give the saved digest");
    after_second = 0;
    for (n = 0; n < span; ++n) {
        if (writes_check && n == span / 2 && rr_fdc_sector_written) {
            uint8_t sector[512];
            memset(sector, 0xA5, sizeof sector);
            rr_fdc_sector_written(0, 2, 0, 5, sector, 512);
        }
        if (run_frame(session, save_at + n)) { fprintf(stderr, "frame failed: %s\n", rr_st_error(session)); return 2; }
    }
    after_second = rr_st_snapshot_digest(session);
    expect(after_second == timeline[span], "the second replay ends on another digest");
    if (writes_check) {
        /* the table: the snapshot holds 2 sectors; the timeline wrote a third; the load of the snapshot brings the table back to 2 */
        expect(rr_st_writes_count(session) == 3, "the replay did not write the third sector");
        expect(rr_st_snapshot_load(session, a, size_a) == 1 && rr_st_writes_count(session) == 2, "the load did not bring the table of writes back to its count");
        expect(rr_st_snapshot_digest(session) == d0, "the digest after the table's load differs");
    }
    /* a restart in a match: from two different moments the machine goes back to the same state and runs the same frames */
    {
        uint64_t r1, r2, e1 = 0, e2 = 0;
        unsigned k;
        expect(boot_size > 0, "no snapshot of the first frame");
        expect(rr_st_snapshot_load(session, a, size_a) == 1, "the load before the restarts was refused");
        for (k = 0; k < 7; ++k) run_frame(session, save_at + k);
        expect(rr_st_snapshot_restart(session, boot, boot_size, c, bound) == 1, "the first restart was refused");
        r1 = rr_st_snapshot_digest(session);
        for (k = 0; k < 20; ++k) { run_frame(session, k + 1); e1 = rr_st_snapshot_digest(session); }
        for (k = 0; k < 11; ++k) run_frame(session, 21 + k);
        expect(rr_st_snapshot_restart(session, boot, boot_size, c, bound) == 1, "the second restart was refused");
        r2 = rr_st_snapshot_digest(session);
        for (k = 0; k < 20; ++k) { run_frame(session, k + 1); e2 = rr_st_snapshot_digest(session); }
        expect(r1 == r2, "two restarts from different moments do not give the same machine");
        expect(e1 == e2, "the frames after two restarts differ");
        expect(rr_st_snapshot_restart(session, boot, boot_size - 1, c, bound) == 0, "a cut boot snapshot was accepted");
    }
    printf("{\"ok\":%s,\"failures\":%d,\"failed\":\"%s\",\"snapshot_bytes\":%llu,\"bound\":%llu,\"d0\":\"%016llx\",\"end\":\"%016llx\",\"diverged_at\":%u,\"span\":%u,\"save_at\":%u}\n",
           failures ? "false" : "true", failures, failed, (unsigned long long)size_a, (unsigned long long)bound, (unsigned long long)d0, (unsigned long long)timeline[span], diverged_at, span, save_at);
    return failures ? 1 : 0;
}
