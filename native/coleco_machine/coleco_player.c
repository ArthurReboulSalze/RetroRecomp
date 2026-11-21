/* An exported ColecoVision game: the translated Z80 code of its cartridge and of the player's BIOS (coleco_glue.inc and the generated bodies), the ColecoVision machine
 * (coleco_machine.c, native/tms9918, native/sn76489) and the host kit's window through the ColecoVision adapter
 * (hostkit/adapters/rrhk_coleco.inc). MIT, Retro-Recomp.
 *
 * What the converter gives the game (retrorecomp/coleco_build.py, the game's packaging):
 *   - the generated bodies (generated/game_banked_*.c and game_banked.h) and `coleco_banked_loop.inc`, as the native check gets them;
 *   - `coleco_game.h`, written by the converter:
 *       RR_CV_TITLE      the game's title, a C string (the window's)
 *       RR_CV_IDENTITY   the cartridge file's SHA-256 as 64 lower-case hexadecimal characters, a C string (the quick state's identity
 *                        and the name of the game's own data folder, datas/games/coleco-<its first 12 characters>)
 *       RR_CV_PAL        1 for a PAL game (313 lines, 50 Hz), 0 for NTSC (262 lines, 60 Hz)
 *       RR_CV_STATE_ABI  the quick state's build binding, 32 bytes as a C initialiser { 0x.., ... }: the SHA-256 of the text
 *                        "coleco-state-1\n<ntsc|pal>\n<the cartridge's size as the machine sees it, whole 8 KiB regions>\n<the BIOS's SHA-256>" (retrorecomp/coleco_build.py
 *                        state_binding; coleco_state_file.inc names the layout);
 *   - the cartridge, as the checked runs saw it, as resource 103 (whole 8 KiB regions padded with FFh; the program pads again if it was
 *     not), the player's BIOS (8 KiB, the one the bodies were translated from) as 104, the notices of the compiled components as 203 and the identity file as 205 (the other games' resource numbers), the icon
 *     as 101 (Windows: the .rc's icon; elsewhere embedded_resources.c);
 *   - runtime_feedback_config.h (the kit's record of the run) and the Windows metadata (content.rc).
 * The guest owns the loop: at the end of each frame the game hands the picture and the sound to the kit and takes the pads back, at an
 * instruction boundary (cv_main_service, the glue's service point). The picture is whole and the TMS9918A raises its frame flag at the
 * first line after it (line 192): the frame is handed over there, so the pads taken back reach the game's own vertical-blank interrupt
 * that follows. A reset starts the machine and the CPU again from address 0.
 *
 * `game.exe --headless [options]` replays a route with no window, no sound device and nothing written beside the game: the cartridge is
 * the game's own resource, the options and the report those of the native check (coleco_headless.inc, with the native fields), so
 * the delivered (packed) file is compared with the reference as the check is. It adds the quick-state options below. The player's own
 * path keeps one test per instruction (frame_ended); the headless branch comes after it.
 *   --save-state FILE --save-at N   save a quick state at the service of frame N (after its row); N must be below --frames
 *   --load-state FILE               load a quick state at the first service of the run, then continue (the route's events up to the
 *                                   loaded frame apply at once)
 *   --snap-probe AT:N               a test of the multiplayer snapshots (hostkit.h): at frame AT take one, run N frames, load it, run the same N
 *                                   frames and compare the digest of every frame; N is at most 600, AT + 2N below --frames
 * Exit codes: 0 done, 2 a bad option, 3 a missing resource or a state that cannot be written, 4 a state refused (nothing is changed), 5 the
 * snapshot probe failed. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#define SMSRECOMP_BANKED_AOT 1
#include <SDL.h>
#include "coleco_glue.inc"
#include "coleco_game.h"
#include "embedded_resources.h"
#include "platform_io.h"

static char state_file_utf8[1100] = "quick.rrstate";
static uint32_t rom_bytes;                      /* the cartridge as the machine sees it: whole 8 KiB regions */

static int handed_this_frame;                   /* one hand-over per frame (the snapshots set it too) */

#include "coleco_state_file.inc"

/* Quick states for the host kit's F8/F9 (defined below, after the frame hand-over they reset). */
static bool cv_game_state_file(const wchar_t *path, bool load);
static bool cv_game_state_path(wchar_t *path, size_t capacity);

#include "hostkit/adapters/rrhk_coleco.inc"

#define CV_HEADLESS_NATIVE 1                    /* the native side of the report: native_cpu, native_extra, headless_finish */
#include "coleco_headless.inc"

static volatile int frame_ended;
static int headless;                            /* --headless: a route replayed, no host */

/* The picture is whole when the VDP raises its frame flag, at the first line after it: the frame is handed over there. */
static void line_hook(void)
{
    if (machine.line == 0)
        handed_this_frame = 0;
    if (!handed_this_frame && machine.line >= TMS_VBLANK_LINE) {
        handed_this_frame = 1;
        frame_ended = 1;
    }
}

/* Headless: the route's line hook, and the frame flag raised with the route's row so the service below sees it. */
static void headless_line(void)
{
    cv_route_line();
    if (route_frame_due)
        frame_ended = 1;
}

/* F8/F9 in play, at the service point (the kit calls this from the frame's end): after a load, the frame's hand-over follows the loaded
 * line, as line_hook would have left it. */
static bool cv_game_state_file(const wchar_t *path, bool load)
{
    if (!load)
        return cv_state_save(path) == RR_STATE_OK;
    if (cv_state_load(path) != RR_STATE_OK)
        return false;
    handed_this_frame = machine.line >= TMS_VBLANK_LINE;
    return true;
}

/* The machine and the CPU as at power on (a reset starts here too; the hooks and the trace switch are the run's, kept). */
static void power_on(void)
{
    void (*hook)(void) = machine.line_hook;
    uint8_t trace = machine.trace_frames;
    cv_init(&machine, bios, cart, rom_bytes, RR_CV_PAL ? CV_LINES_PAL : CV_LINES_NTSC);
    machine.line_hook = hook;
    machine.trace_frames = trace;
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = g_z80.f = 0xFF; g_z80.sp = 0xFFFF;   /* the reset values the step loop sets at its start */
    smsrecomp_measured_guest_cycles = 0;
    step_start = 0;
    handed_this_frame = 0;
    g_next_line_cyc = cv_next_event(&machine);
}

/* Headless states (the conversion's fresh-process check): see the header. */
static wchar_t state_save_file[32768], state_load_file[32768];
static unsigned long state_save_at;
static int state_save_due, state_load_due;

/* A path given on the command line: argv is in the ANSI code page on Windows (the game's manifest names no UTF-8 code page), as fopen
 * reads the other options' paths; UTF-8 elsewhere. */
static int headless_path(const char *v, wchar_t *out)
{
#ifdef _WIN32
    return MultiByteToWideChar(CP_ACP, 0, v, -1, out, 32768) != 0;
#else
    return rr_from_utf8(v, out, 32768);
#endif
}

#define SNAP_PROBE_MAX 600
static unsigned long snap_probe_at, snap_probe_n;
static int snap_probe_phase;                   /* 0 off, 1 take, 2 first run, 3 second run */
static uint8_t snap_probe_a[CV_STATE_CAPACITY], snap_probe_b[CV_STATE_CAPACITY];
static size_t snap_probe_size, snap_probe_bound;
static int snap_probe_same, snap_probe_refused;
static uint64_t snap_probe_digests[SNAP_PROBE_MAX + 1];
static uint32_t snap_probe_pictures[SNAP_PROBE_MAX + 1];
static unsigned long snap_probe_picture_mismatches;
static unsigned long snap_probe_mismatches;
static long snap_probe_bad = -1;

static int headless_state_option(const char *a, const char *v)
{
    if (!strcmp(a, "--save-state")) { if (!headless_path(v, state_save_file)) return -1; state_save_due = 1; }
    else if (!strcmp(a, "--save-at")) state_save_at = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--load-state")) { if (!headless_path(v, state_load_file)) return -1; state_load_due = 1; }
    else if (!strcmp(a, "--snap-probe")) {
        char *rest = NULL;
        snap_probe_at = strtoul(v, &rest, 10);
        if (!rest || *rest != ':') return -1;
        snap_probe_n = strtoul(rest + 1, NULL, 10);
        if (!snap_probe_n || snap_probe_n > SNAP_PROBE_MAX) return -1;
        snap_probe_phase = 1;
    }
    else return 0;
    return 1;
}


/* `--snap-probe AT:N` (headless, a test of the multiplayer snapshots): at the service of frame AT it takes a snapshot, checks it is the same
 * bytes twice, fits snap_bound and that a buffer one byte short is refused and changes nothing; records the digest of each of the next N
 * frames; loads the snapshot (the rollback), runs the same N frames again and compares every digest. Ends the process: 0 PASS, 5 FAIL (stderr
 * says what differed). The route's events up to the loaded frame are applied again after the load, as a fresh process does. */

static void snap_probe_service(void)
{
    if (!snap_probe_phase || machine.frames < snap_probe_at)
        return;
    const unsigned long k = (unsigned long)(machine.frames - snap_probe_at);
    if (snap_probe_phase == 1) {
        snap_probe_bound = cv_snap_bound();
        snap_probe_size = cv_snap_save(snap_probe_a, CV_STATE_CAPACITY);
        memset(snap_probe_b, 0xA5, sizeof snap_probe_b);
        snap_probe_same = snap_probe_size && cv_snap_save(snap_probe_b, CV_STATE_CAPACITY) == snap_probe_size
                          && !memcmp(snap_probe_a, snap_probe_b, snap_probe_size) && snap_probe_size <= snap_probe_bound;
        const uint64_t before = cv_snap_digest();
        snap_probe_refused = !cv_snap_load(snap_probe_a, snap_probe_size - 1) && cv_snap_digest() == before;
        snap_probe_digests[0] = before;
        snap_probe_phase = 2;
    } else if (snap_probe_phase == 2) {
        snap_probe_digests[k] = cv_snap_digest();
        snap_probe_pictures[k] = cv_frame_hash(&machine);
        if (k >= snap_probe_n) {
            if (!cv_snap_load(snap_probe_a, snap_probe_size)) snap_probe_mismatches = ~0ul;
            route_next_event = 0;                  /* the snapshot holds the pads: the events up to the loaded frame are skipped */
            while (route_next_event < route_event_count && route_events[route_next_event].frame <= machine.frames)
                ++route_next_event;
            if (cv_snap_digest() != snap_probe_digests[0]) { ++snap_probe_mismatches; snap_probe_bad = 0; }
            snap_probe_phase = 3;
        }
    } else if (snap_probe_phase == 3) {
        if (cv_snap_digest() != snap_probe_digests[k]) {
            ++snap_probe_mismatches;
            if (snap_probe_bad < 0) snap_probe_bad = (long)k;
        }
        if (k >= 1 && cv_frame_hash(&machine) != snap_probe_pictures[k])
            ++snap_probe_picture_mismatches;      /* from the first frame drawn again after the load */
        if (k >= snap_probe_n) {
            const int pass = snap_probe_same && snap_probe_refused && !snap_probe_mismatches && !snap_probe_picture_mismatches;
            uint64_t folded = 1469598103934665603ull;        /* every digest of the run folded in one number: the same on Windows and Linux */
            for (unsigned long i = 0; i <= snap_probe_n; ++i) { folded ^= snap_probe_digests[i]; folded *= 1099511628211ull; }
            fprintf(stderr, "snap-probe: %s at %lu, %lu frames, %zu bytes (bound %zu), same over other bytes %d, wrong size refused %d, "
                    "mismatches %lu, first at +%ld, pictures differing %lu, digests %016llx\n", pass ? "PASS" : "FAIL", snap_probe_at, snap_probe_n, snap_probe_size,
                    snap_probe_bound, snap_probe_same, snap_probe_refused, snap_probe_mismatches, snap_probe_bad, snap_probe_picture_mismatches, (unsigned long long)folded);
            exit(pass ? 0 : 5);
        }
    }
}

/* The glue's service point: an instruction and the interrupt it may accept are complete. */
static void cv_main_service(void)
{
    if (!frame_ended)
        return;
    frame_ended = 0;
    if (headless) {
        if (state_load_due) {
            state_load_due = 0;
            if (cv_state_load(state_load_file) != RR_STATE_OK)
                exit(4);
            /* The pads are host input, not part of a state: the route's events up to the loaded frame apply again. */
            cv_route_events();
            handed_this_frame = machine.line >= TMS_VBLANK_LINE;
            return;
        }
        if (route_frame_due) {
            CvCpuView c = native_cpu();
            cv_route_row(&c);
        }
        snap_probe_service();
        if (machine.frames >= frames_wanted)
            headless_finish();                  /* the report; it ends the process */
        if (state_save_due && machine.frames >= state_save_at) {
            state_save_due = 0;
            if (cv_state_save(state_save_file) != RR_STATE_OK)
                exit(3);
        }
        return;
    }
    switch (cv_host_frame(&machine)) {
    case 0: break;
    case 2: power_on(); break;
    default: cv_host_close(); exit(0);
    }
}

/* The game's own folder beside the executable, datas/games/coleco-<identity>, as on the other machines: its quick state lives there. */
static void prepare_data_folder(void)
{
    static char folder[1024];
    char *base = SDL_GetBasePath();
    size_t start = base ? strlen(base) : 0;
    int n = snprintf(folder, sizeof folder, "%sdatas/games/coleco-%.12s", base ? base : "", RR_CV_IDENTITY);
    SDL_free(base);
    if (n <= 0 || n >= (int)sizeof folder) return;              /* keep the state in the working folder */
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
    snprintf(state_file_utf8, sizeof state_file_utf8, "%s/quick.rrstate", folder);
}

/* The quick state's file in the game's folder (the kit asks when it opens the window). */
static bool cv_game_state_path(wchar_t *path, size_t capacity)
{
    return rr_from_utf8(state_file_utf8, path, capacity) != 0;
}

/* The machine from the game's own resource: the cartridge (103). */
static int setup_machine(void)
{
    size_t cart_size = 0, bios_size = 0;
    const uint8_t *cartridge = rr_resource(103, &cart_size), *firmware = rr_resource(104, &bios_size);
    if (!firmware || bios_size != CV_BIOS_SIZE) {
        fprintf(stderr, "[coleco] the game's BIOS resource is missing\n");
        return 3;
    }
    memcpy(bios, firmware, CV_BIOS_SIZE);
    if (!cartridge || !cart_size || cart_size > sizeof cart) {
        fprintf(stderr, "[coleco] the game's cartridge resource is missing\n");
        return 3;
    }
    memset(cart, 0xFF, sizeof cart);
    memcpy(cart, cartridge, cart_size);
    rom_bytes = (uint32_t)((cart_size + 0x1FFF) & ~(size_t)0x1FFF);
    cv_init(&machine, bios, cart, rom_bytes, RR_CV_PAL ? CV_LINES_PAL : CV_LINES_NTSC);
    return 0;
}

static int run(void)
{
    int status = setup_machine();
    if (status)
        return status;
    machine.line_hook = line_hook;
    prepare_data_folder();
    if (!cv_host_open(RR_CV_TITLE, 3, &machine)) return 4;
    power_on();
    smsrecomp_banked_run();                      /* returns through exit() when the player quits */
    return 0;
}

/* `--headless`: exit codes 0 done, 2 a bad option, 3 a missing resource or an unwritable file, 4 a refused state. */
static int run_headless(int argc, char **argv)
{
    for (int i = 2; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) return 2;
        ++i;
        int known = headless_state_option(a, v);
        if (!known) known = headless_option(a, v);
        if (known <= 0) return 2;
    }
    if (state_save_due && state_save_at >= frames_wanted) return 2;   /* the save would never happen */
    int status = setup_machine();
    if (status)
        return status;
    headless = 1;
    machine.trace_frames = 1;                  /* the per-frame running hash the comparison reads */
    machine.line_hook = headless_line;
    power_on();
    frame_ended = state_load_due || frames_wanted == 0;   /* a load waits for the first service, not for the first frame */
    smsrecomp_banked_run();                    /* returns through headless_finish() at the frame limit */
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--headless"))
        return run_headless(argc, argv);
    return run();
}
