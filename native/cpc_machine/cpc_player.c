/* An exported Amstrad CPC game: the translated Z80 code of the player's system ROM and AMSDOS (cpc_glue.inc and the generated
 * bodies), the CPC 6128 board of cpc_machine.c with the game's disk in drive A, and the host kit's window through the CPC adapter
 * (hostkit/adapters/rrhk_cpc.inc). MIT, Retro-Recomp.
 *
 * Resources: 103 the game's disks (DSK or EDSK images one after the other, RR_CPC_DISK_SIZES), 104 the player's 32 KiB system
 * ROM (OS then BASIC), 105 the player's AMSDOS ROM; none is shipped with Retro-Recomp. cpc_game.h, written by the converter,
 * gives the title, the identity, the CRTC type and the disks; boot_keys.h (retrorecomp/cpc_keys.py) the start command the
 * player would type (RUN"name and RETURN), typed by the adapter from the machine's own frame count. The guest owns the loop: at
 * each VSYNC the game hands the picture and the sound to the kit and takes the inputs back, at an instruction boundary
 * (cpc_main_service). A reset starts the board and the CPU again from address 0, the disk still in drive A.
 *
 * `game.exe --headless [options]` replays the start with no window, no sound device and nothing written beside the game: the
 * ROMs and the disk are the game's own resources, the options and the report those of the native check (cpc_headless.inc), the
 * boot keys typed at the same frames as in the window, so the delivered file is compared with the reference as the check is.
 *
 * Quick states (F8/F9, quick.rrstate beside player.cfg) and the multiplayer snapshots and digest: cpc_state_file.inc, on the
 * chain's shared CPU state and state file. --headless also takes --save-state FILE --save-at N (saved at the end of frame N) and
 * --load-state FILE (loaded at the first service), for the conversion's fresh-process check, and --snap-probe AT:N (the snapshots
 * and the digest checked in one process).
 *
 * The disk's saves: what the game writes on drive A's disk goes to a copy beside player.cfg (native/disk_copies.inc:
 * datas/games/cpc-<identity>/disk-1.dsk, read back at the next start when its size is right, written a few seconds after the last
 * write and when the game closes; the embedded disk is never changed). In a multiplayer match the host's disk A, as it stands,
 * travels to every seat and is played in memory (session_save / session_save_put), laid again at the match's start and at every
 * restart; nobody writes a copy during the match, the host writes its own once at a clean end (the previous copy kept as .bak),
 * and a guest never writes one for the rest of its run.
 *
 * Not yet here: the disk keys for a game of several disks. */
#define SMSRECOMP_BANKED_AOT 1
#include <SDL.h>
#include "cpc_glue.inc"
#include "boot_keys.h"
#include "cpc_headless.inc"
#include "cpc_game.h"
#include "embedded_resources.h"
#include "platform_io.h"
#include "disk_copies.inc"

/* The frontend variables rrhk_computer.inc reads (see its header). */
static bool guest_keyboard, mouse_grab, mouse_game, input_focus = true, fast_forward, want_swap, want_eject;
static int loading_holdoff, swap_drive, swap_direction;
static const Uint8 *keys;
static int mouse_dx, mouse_dy;
static Uint32 mouse_buttons;
static unsigned width, height;
static double aspect_ratio = 4.0 / 3.0;
static char player_config[1024] = "player.cfg";
static char state_file_utf8[1100] = "quick.rrstate";

/* Quick states for the kit's F8/F9 and the multiplayer hooks (cpc_state_file.inc, below, after the disks). */
static bool cpc_game_state_file(const wchar_t *path, bool load);
static bool cpc_game_state_path(wchar_t *path, size_t capacity);
static size_t cpc_snap_bound(void);
static size_t cpc_snap_save(void *buffer, size_t capacity);
static bool cpc_snap_load(const void *buffer, size_t size);
static uint64_t cpc_snap_digest(void);
/* What a frame does outside the machine (the disk's copy): off for silent frames and for every seat during a match. */
static bool cpc_effects_allowed = true;
static void cpc_side_effects(bool allowed) { cpc_effects_allowed = allowed; }
/* The disk's save in a match (below, after the disks). */
static size_t cpc_session_save(void *out, size_t capacity);
static bool cpc_session_save_put(const void *in, size_t size);
static void cpc_session_begin(uint64_t clock);
static bool cpc_session_save_commit(void);

#include "hostkit/adapters/rrhk_cpc.inc"

static uint8_t system_rom[0x8000], amsdos_rom[0x4000];
static const uint32_t disk_sizes[RR_CPC_DISKS] = RR_CPC_DISK_SIZES;
static uint8_t disk_data[RR_CPC_DISKS][RR_CPC_DISK_MAX];
static const uint8_t *disk_original[RR_CPC_DISKS];  /* the embedded disks as they came (a load puts drive A's back) */
static uint32_t picture[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];
static int headless;                             /* --headless: the start replayed, no host */

#include "cpc_state_file.inc"

/* ---- the disk's copy and its save in a match ---- */
static RrDiskCopies copies;                      /* drive A's disk: its copy beside player.cfg (none in a headless run) */

/* What the game wrote on drive A this frame: the copy is due, and the disk's bytes travel with every state from now on. */
static int disk_take_written(void)
{
    if (!machine.fdc.drive[0].written) return 0;
    machine.fdc.drive[0].written = 0;
    rr_disk_copies_written(&copies, 0);
    disk_ever = 1;
    return 1;
}

static void disk_at_exit(void) { if (cpc_effects_allowed && !rrhk_session_active()) rr_disk_copies_save(&copies); }

/* The match's disk image: a magic word, the disk's size, then its bytes. Which disk a seat plays (laid at the match's start and at
 * every restart, over the power-on state): the host's image when the host sent one (session_save_put: on a guest, and on the host
 * itself at a restart); else, on the host, the image it sent (session_save at HELLO); else, on a guest, the EMBEDDED disk, never its
 * own copy (a guest that saved earlier would start the match on another disk than everyone else). */
#define CPC_SESSION_MAGIC "RCPCDSK1"
static uint8_t *session_mine, *session_given;    /* this PC's image as sent at HELLO; the host's as received */
static size_t session_mine_size, session_given_size;
static uint8_t *session_start;                   /* the machine at power-on, for session_begin */
static size_t session_start_size;

static size_t cpc_session_image_size(void) { return 8u + 4u + disk_sizes[0]; }

static void cpc_session_keep(uint8_t **held, size_t *held_size, const void *image, size_t size)
{
    uint8_t *copy = (uint8_t *)malloc(size);
    if (!copy) return;
    memcpy(copy, image, size);
    free(*held);
    *held = copy;
    *held_size = size;
}

static bool cpc_session_valid(const uint8_t *image, size_t size)
{
    if (size != cpc_session_image_size() || memcmp(image, CPC_SESSION_MAGIC, 8)) return false;
    const uint32_t bytes = (uint32_t)image[8] | (uint32_t)image[9] << 8 | (uint32_t)image[10] << 16 | (uint32_t)image[11] << 24;
    return bytes == disk_sizes[0];
}

/* Drive A's disk for the match (NULL: the embedded disk), in memory only; the disk then travels with every snapshot. */
static bool cpc_session_lay(const uint8_t *image)
{
    memcpy(disk_data[0], image ? image + 12 : disk_original[0], disk_sizes[0]);
    disk_ever = 1;
    return cpc_insert_disk(&machine, 0, disk_data[0], disk_sizes[0], 0) == DSK_OK;
}

static size_t cpc_session_save(void *out, size_t capacity)
{
    const size_t size = cpc_session_image_size();
    if (!out) return size;
    if (capacity < size) return 0;
    uint8_t *image = (uint8_t *)out;
    memcpy(image, CPC_SESSION_MAGIC, 8);
    for (int i = 0; i < 4; ++i) image[8 + i] = (uint8_t)(disk_sizes[0] >> (8 * i));
    memcpy(image + 12, disk_data[0], disk_sizes[0]);
    cpc_session_keep(&session_mine, &session_mine_size, out, size);   /* the host plays the match on the bytes it sends */
    return size;
}

static bool cpc_session_save_put(const void *in, size_t size)
{
    if (!cpc_session_valid((const uint8_t *)in, size)) return false;   /* another game's image, or a broken one: nothing changes */
    cpc_session_keep(&session_given, &session_given_size, in, size);
    if (rrhk_session_guest()) {                  /* a guest never writes its own disk's copy, not even after the match */
        copies.folder[0] = 0;
        for (unsigned n = 0; n < copies.count; ++n) copies.disk[n].dirty = 0;
    }
    return cpc_session_lay(session_given);       /* session_begin, which follows, lays it again over the power-on state */
}

/* Called once after power_on when the game starts in a session: the machine at power-on, laid again by session_begin. */
static void cpc_session_keep_start(void)
{
    const size_t bound = cpc_snap_bound();
    session_start = (uint8_t *)malloc(bound);
    session_start_size = session_start ? cpc_snap_save(session_start, bound) : 0;
    if (!session_start_size) { free(session_start); session_start = NULL; }
}

/* The match starts, and at each restart: every seat back at power-on, then the match's disk (the CPC has no clock to set). */
static void cpc_session_begin(uint64_t clock)
{
    (void)clock;
    const bool reset = session_start && cpc_snap_load(session_start, session_start_size);
    const uint8_t *image = session_given ? session_given : rrhk_session_guest() ? NULL : session_mine;
    if (!image && rrhk_session_guest()) {        /* the host sent none: this guest plays the embedded disk, and writes nothing */
        copies.folder[0] = 0;
        for (unsigned n = 0; n < copies.count; ++n) copies.disk[n].dirty = 0;
    }
    const bool laid = cpc_session_lay(image);
    fprintf(stderr, "[cpc] match start: power-on state %s; drive A: %s%s\n", reset ? "back" : "not kept",
            image == session_given && image ? "the host's disk" : image ? "this host's own disk" : "the embedded disk",
            laid ? "" : " (not a disk: refused)");
}

/* The host, at a clean end of a match: the disk as it is now to this PC's copy, the previous copy kept as .bak. */
static bool cpc_session_save_commit(void)
{
    disk_take_written();
    const bool ok = rr_disk_copies_commit(&copies);
    fprintf(stderr, "[cpc] match end: disk A %s\n", ok ? "written" : "not written");
    return ok;
}

/* F8/F9 in play, at the service point (the kit calls this from the frame's end). */
static bool cpc_game_state_file(const wchar_t *path, bool load)
{
    return (load ? cpc_quick_load(path) : cpc_quick_save(path)) == RR_STATE_OK;
}

/* The quick state's file beside player.cfg (the kit asks when it opens the window). */
static bool cpc_game_state_path(wchar_t *path, size_t capacity)
{
    return rr_from_utf8(state_file_utf8, path, capacity) != 0;
}

/* Headless states (the conversion's fresh-process check): --save-state FILE with --save-at N saves at the end of frame N, after
 * its boot keys; --load-state FILE loads at the first service of the run (the one instruction run before it is overwritten
 * whole). A refused state ends the process with exit 4, leaving the file as it was; a state that cannot be written, with exit 3. */
static wchar_t state_save_file[32768], state_load_file[32768];
static unsigned long long state_save_at;
static int state_save_due, state_load_due;

/* A path given on the command line: argv is in the ANSI code page on Windows (the game's manifest names no UTF-8 code page),
 * as fopen reads the other options' paths; UTF-8 elsewhere. */
static int headless_path(const char *v, wchar_t *out)
{
#ifdef _WIN32
    return MultiByteToWideChar(CP_ACP, 0, v, -1, out, 32768) != 0;
#else
    return rr_from_utf8(v, out, 32768);
#endif
}

/* 1 taken, 0 not a state option, -1 a bad value. */
static int headless_state_option(int argc, char **argv, int *i)
{
    const char *a = argv[*i], *v = *i + 1 < argc ? argv[*i + 1] : NULL;
    if (strcmp(a, "--save-state") && strcmp(a, "--save-at") && strcmp(a, "--load-state")) return 0;
    if (!v) return -1;
    ++*i;
    if (!strcmp(a, "--save-at")) { state_save_at = strtoull(v, NULL, 10); return 1; }
    if (!headless_path(v, !strcmp(a, "--save-state") ? state_save_file : state_load_file)) return -1;
    if (!strcmp(a, "--save-state")) state_save_due = 1; else state_load_due = 1;
    return 1;
}

/* The board and the CPU from power-on: the disk stays in drive A (cpc_reset keeps the drives' images). */
static void power_on(void)
{
    cpc_reset(&machine, RR_CPC_CRTC);
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = g_z80.f = 0xFF; g_z80.sp = 0xFFFF;   /* the reset values the step loop sets at its start */
    g_z80.cyc = 0;
    step_start = 0;
    g_next_line_cyc = cpc_next_event(&machine);
}


/* --snap-probe AT:N (headless): the multiplayer snapshots checked in one process, as the MSX's probe does. At the end of frame AT a
 * snapshot is taken twice (the same bytes, within its bound), a load one byte short is refused with nothing changed; the next N
 * frames record the digest and the picture's hash; the snapshot is loaded and the same N frames must give the same digests and,
 * from the first frame drawn again, the same pictures. The process ends there: exit 0 PASS, 5 FAIL (one line on stderr). */
static unsigned long long snap_probe_at, snap_probe_n;
static int snap_probe_phase, snap_probe_same, snap_probe_refused;
static uint64_t *snap_probe_digests;
static uint32_t *snap_probe_pictures;
static uint8_t *snap_probe_a, *snap_probe_b;
static size_t snap_probe_size;
static unsigned long snap_probe_mismatches, snap_probe_picture_mismatches;
static long snap_probe_bad = -1;

static int snap_probe_option(int argc, char **argv, int *i)
{
    if (strcmp(argv[*i], "--snap-probe")) return 0;
    if (*i + 1 >= argc || sscanf(argv[++*i], "%llu:%llu", &snap_probe_at, &snap_probe_n) != 2 || !snap_probe_n
        || snap_probe_n > 100000)
        return -1;
    snap_probe_digests = (uint64_t *)calloc(snap_probe_n + 1, sizeof *snap_probe_digests);
    snap_probe_pictures = (uint32_t *)calloc(snap_probe_n + 1, sizeof *snap_probe_pictures);
    snap_probe_a = (uint8_t *)malloc(CPC_STATE_CAPACITY);
    snap_probe_b = (uint8_t *)malloc(CPC_STATE_CAPACITY);
    if (!snap_probe_digests || !snap_probe_pictures || !snap_probe_a || !snap_probe_b) return -1;
    snap_probe_phase = 1;
    return 1;
}

/* At the end of a frame, its boot keys written (the inputs of the next frame, which the snapshot carries). */
static void snap_probe_service(void)
{
    if (!snap_probe_phase || machine.frames < snap_probe_at) return;
    const unsigned long long k = machine.frames - snap_probe_at;
    const uint32_t shown = headless_fnv((const uint8_t *)headless_picture, sizeof headless_picture);
    if (snap_probe_phase == 1) {
        snap_probe_size = cpc_snap_save(snap_probe_a, CPC_STATE_CAPACITY);
        memset(snap_probe_b, 0xA5, CPC_STATE_CAPACITY);
        snap_probe_same = snap_probe_size && cpc_snap_save(snap_probe_b, CPC_STATE_CAPACITY) == snap_probe_size
                          && !memcmp(snap_probe_a, snap_probe_b, snap_probe_size) && snap_probe_size <= cpc_snap_bound();
        const uint64_t before = cpc_snap_digest();
        snap_probe_refused = !cpc_snap_load(snap_probe_a, snap_probe_size - 1) && cpc_snap_digest() == before;
        snap_probe_digests[0] = before;
        snap_probe_phase = 2;
    } else if (snap_probe_phase == 2) {
        snap_probe_digests[k] = cpc_snap_digest();
        snap_probe_pictures[k] = shown;
        if (k >= snap_probe_n) {
            if (!cpc_snap_load(snap_probe_a, snap_probe_size)) snap_probe_mismatches = ~0ul;
            if (cpc_snap_digest() != snap_probe_digests[0]) { ++snap_probe_mismatches; snap_probe_bad = 0; }
            snap_probe_phase = 3;
        }
    } else {
        if (cpc_snap_digest() != snap_probe_digests[k]) { ++snap_probe_mismatches; if (snap_probe_bad < 0) snap_probe_bad = (long)k; }
        if (k >= 1 && shown != snap_probe_pictures[k]) ++snap_probe_picture_mismatches;   /* from the first frame drawn again */
        if (k >= snap_probe_n) {
            const int pass = snap_probe_same && snap_probe_refused && !snap_probe_mismatches && !snap_probe_picture_mismatches;
            fprintf(stderr, "snap-probe: %s at %llu, %llu frames, %zu bytes (bound %zu), same over other bytes %d, wrong size "
                    "refused %d, mismatches %lu, first at +%ld, pictures differing %lu\n", pass ? "PASS" : "FAIL", snap_probe_at,
                    snap_probe_n, snap_probe_size, cpc_snap_bound(), snap_probe_same, snap_probe_refused, snap_probe_mismatches,
                    snap_probe_bad, snap_probe_picture_mismatches);
            exit(pass ? 0 : 5);
        }
    }
}

static void cpc_main_service(void)
{
    if (headless) {
        if (state_load_due) {
            state_load_due = 0;
            if (cpc_quick_load(state_load_file) != RR_STATE_OK) exit(4);
            return;
        }
        const int frame_end = machine.frame_ready;
        headless_service();                      /* the frame's sound, row and next boot keys; the stop (it ends the process) */
        if (frame_end)
            snap_probe_service();
        if (frame_end && state_save_due && machine.frames >= state_save_at) {
            state_save_due = 0;
            if (cpc_quick_save(state_save_file) != RR_STATE_OK) exit(3);
        }
        return;
    }
    if (!machine.frame_ready)
        return;
    machine.frame_ready = 0;
    /* What the game wrote goes to its copy once the disk has been quiet for about three seconds; never in a match. */
    rr_disk_copies_frame(&copies, disk_take_written(), cpc_effects_allowed && !rrhk_session_active());
    switch (cpc_host_frame(&machine)) {
    case 0: break;
    case 2: power_on(); break;
    default: cpc_host_close(); exit(0);
    }
}

/* The game's own folder beside the executable, datas/games/cpc-<identity>, as on the other machines: the player's settings of
 * the computer adapter (player.cfg) live there, never in the export folder itself. */
static void prepare_data_folder(void)
{
    static char folder[1024];
    char *base = SDL_GetBasePath();
    size_t start = base ? strlen(base) : 0;
    int n = snprintf(folder, sizeof folder, "%sdatas/games/cpc-%.12s", base ? base : "", RR_CPC_IDENTITY);
    SDL_free(base);
    if (n <= 0 || n >= (int)sizeof folder) return;              /* keep player.cfg in the working folder */
    for (size_t i = start; ; i++) {
        char c = folder[i];
        if (c == '/' || c == '\\' || c == 0) {
            wchar_t wide[1024];
            folder[i] = 0;
            if (rr_from_utf8(folder, wide, 1024)) rr_mkdir(wide);
            folder[i] = c;
            if (!c) break;
        }
    }
    snprintf(player_config, sizeof player_config, "%s/player.cfg", folder);
    snprintf(state_file_utf8, sizeof state_file_utf8, "%s/quick.rrstate", folder);
    rr_disk_copies_init(&copies, folder);        /* the disk's copy lives beside player.cfg */
}

/* The machine from the game's own resources: the ROMs (104, 105) and the disks (103), the first in drive A. */
static int setup_machine(void)
{
    size_t disks_size = 0, system_size = 0, amsdos_size = 0;
    const uint8_t *disks = rr_resource(103, &disks_size), *system = rr_resource(104, &system_size),
                  *amsdos = rr_resource(105, &amsdos_size);
    size_t total = 0;
    for (unsigned n = 0; n < RR_CPC_DISKS; ++n) total += disk_sizes[n];
    if (!disks || disks_size != total || !system || system_size != sizeof system_rom || !amsdos || amsdos_size != sizeof amsdos_rom) {
        fprintf(stderr, "[cpc] the game's disk or ROM resource is missing\n");
        return 3;
    }
    memcpy(system_rom, system, sizeof system_rom);
    memcpy(amsdos_rom, amsdos, sizeof amsdos_rom);
    size_t at = 0;
    for (unsigned n = 0; n < RR_CPC_DISKS; ++n) {
        memcpy(disk_data[n], disks + at, disk_sizes[n]);
        disk_original[n] = disks + at;
        at += disk_sizes[n];
    }
    machine.os = system_rom;
    machine.basic = system_rom + 0x4000;
    machine.amsdos = amsdos_rom;
    machine.picture = picture;
    cpc_reset(&machine, RR_CPC_CRTC);
    if (cpc_insert_disk(&machine, 0, disk_data[0], disk_sizes[0], 0) != DSK_OK) {
        fprintf(stderr, "[cpc] the game's disk is not a DSK image\n");
        return 3;
    }
    return 0;
}

static int run(void)
{
    int status = setup_machine();
    if (status)
        return status;
    prepare_data_folder();
    copies.disk[0] = (RrDiskImage){ disk_data[0], disk_sizes[0], 0 };
    copies.count = 1;
    if (rr_disk_copies_load(&copies)) {          /* a copy the game wrote before: in drive A, and in every state from now on */
        disk_ever = 1;
        if (cpc_insert_disk(&machine, 0, disk_data[0], disk_sizes[0], 0) != DSK_OK) {
            memcpy(disk_data[0], disk_original[0], disk_sizes[0]);      /* not a disk any more: the embedded one */
            disk_ever = 0;
            cpc_insert_disk(&machine, 0, disk_data[0], disk_sizes[0], 0);
        }
    }
    atexit(disk_at_exit);
    if (!cpc_host_open(RR_CPC_TITLE, 2)) return 4;
    power_on();
    if (rrhk_session_active()) cpc_session_keep_start();   /* session_begin puts every seat back here */
    smsrecomp_banked_run();                      /* returns through exit() when the player quits */
    return 0;
}

/* `--headless`: exit codes 0 done, 2 a bad option, 3 a missing resource or an unwritable file, 4 a refused state, 5 a snapshot
 * probe that failed. */
static int run_headless(int argc, char **argv)
{
    for (int i = 2; i < argc; ++i) {
        int known = headless_state_option(argc, argv, &i);
        if (!known) known = snap_probe_option(argc, argv, &i);
        if (!known) known = headless_option(argc, argv, &i);
        if (known <= 0) { fprintf(stderr, "bad option %s\n", argv[i]); return 2; }
    }
    if (state_save_due && state_save_at >= headless_frames_wanted) return 2;   /* the save would never happen */
    if (snap_probe_phase && snap_probe_at + 2 * snap_probe_n >= headless_frames_wanted) return 2;   /* nor the probe's end */
    int status = setup_machine();
    if (status)
        return status;
    headless = 1;
    headless_start();                            /* the board draws into the headless picture from here */
    power_on();
    smsrecomp_banked_run();                      /* returns through headless_finish() at the frame limit */
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--headless"))
        return run_headless(argc, argv);
    return run();
}
