/* An exported SG-1000 game: the translated Z80 code of its cartridge (sg1000_glue.inc and the generated bodies), the SG-1000 machine
 * (sg1000_machine.c, native/tms9918, native/sn76489) and the host kit's window through the SG-1000 adapter
 * (hostkit/adapters/rrhk_sg1000.inc). MIT, Retro-Recomp.
 *
 * What the converter gives the game (retrorecomp/sg1000_build.py, the game's packaging):
 *   - the generated bodies (generated/game_banked_*.c and game_banked.h) and `sg1000_banked_loop.inc`, as the native check gets them;
 *   - `sg1000_game.h`, written by the converter:
 *       RR_SG_TITLE      the game's title, a C string (the window's)
 *       RR_SG_IDENTITY   the cartridge file's SHA-256 as 64 lower-case hexadecimal characters, a C string (the quick state's identity
 *                        and the name of the game's own data folder, datas/games/sg1000-<its first 12 characters>)
 *       RR_SG_PAL        1 for a PAL game (313 lines, 50 Hz), 0 for NTSC (262 lines, 60 Hz)
 *       RR_SG_STATE_ABI  the quick state's build binding, 32 bytes as a C initialiser { 0x.., ... }: the SHA-256 of the text
 *                        "sg1000-state-1\n<ntsc|pal>\n<the cartridge's size as the machine sees it, whole 8 KiB regions>" (retrorecomp/sg1000_build.py
 *                        state_binding; sg1000_state_file.inc names the layout);
 *   - the cartridge, as the checked runs saw it, as resource 103 (whole 8 KiB regions padded with FFh; the program pads again if it was
 *     not), the notices of the compiled components as 203 and the identity file as 205 (the other games' resource numbers), the icon
 *     as 101 (Windows: the .rc's icon; elsewhere embedded_resources.c);
 *   - runtime_feedback_config.h (the kit's record of the run) and the Windows metadata (content.rc).
 * The guest owns the loop: at the end of each frame the game hands the picture and the sound to the kit and takes the pads back, at an
 * instruction boundary (sg_main_service, the glue's service point). The picture is whole and the TMS9918A raises its frame flag at the
 * first line after it (line 192): the frame is handed over there, so the pads taken back reach the game's own vertical-blank interrupt
 * that follows. A reset starts the machine and the CPU again from address 0.
 *
 * `game.exe --headless [options]` replays a route with no window, no sound device and nothing written beside the game: the cartridge is
 * the game's own resource, the options and the report those of the native check (sg1000_headless.inc, with the native fields), so
 * the delivered (packed) file is compared with the reference as the check is. It adds the quick-state options below. The player's own
 * path keeps one test per instruction (frame_ended); the headless branch comes after it.
 *   --save-state FILE --save-at N   save a quick state at the service of frame N (after its row); N must be below --frames
 *   --load-state FILE               load a quick state at the first service of the run, then continue (the route's events up to the
 *                                   loaded frame apply at once; a Pause already taken is not taken again)
 * Exit codes: 0 done, 2 a bad option, 3 a missing resource or a state that cannot be written, 4 a state refused (nothing is changed). */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#define SMSRECOMP_BANKED_AOT 1
#include <SDL.h>
#include "sg1000_glue.inc"
#include "sg1000_game.h"
#include "embedded_resources.h"
#include "platform_io.h"

static char state_file_utf8[1100] = "quick.rrstate";
static uint32_t rom_bytes;                      /* the cartridge as the machine sees it: whole 8 KiB regions */

#include "sg1000_state_file.inc"

/* Quick states for the host kit's F8/F9 (defined below, after the frame hand-over they reset). */
static bool sg_game_state_file(const wchar_t *path, bool load);
static bool sg_game_state_path(wchar_t *path, size_t capacity);

#include "hostkit/adapters/rrhk_sg1000.inc"

#define SG_HEADLESS_NATIVE 1                    /* the native side of the report: native_cpu, native_extra, headless_finish */
#include "sg1000_headless.inc"

static volatile int frame_ended;
static int headless;                            /* --headless: a route replayed, no host */
static int handed_this_frame;                   /* one hand-over per frame */

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
    sg_route_line();
    if (route_frame_due)
        frame_ended = 1;
}

/* F8/F9 in play, at the service point (the kit calls this from the frame's end): after a load, the frame's hand-over follows the loaded
 * line, as line_hook would have left it. */
static bool sg_game_state_file(const wchar_t *path, bool load)
{
    if (!load)
        return sg_state_save(path) == RR_STATE_OK;
    if (sg_state_load(path) != RR_STATE_OK)
        return false;
    handed_this_frame = machine.line >= TMS_VBLANK_LINE;
    return true;
}

/* The machine and the CPU as at power on (a reset starts here too; the hooks and the trace switch are the run's, kept). */
static void power_on(void)
{
    void (*hook)(void) = machine.line_hook;
    uint8_t trace = machine.trace_frames;
    sg_init(&machine, cart, rom_bytes, RR_SG_PAL ? SG_LINES_PAL : SG_LINES_NTSC);
    machine.line_hook = hook;
    machine.trace_frames = trace;
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = g_z80.f = 0xFF; g_z80.sp = 0xFFFF;   /* the reset values the step loop sets at its start */
    smsrecomp_measured_guest_cycles = 0;
    step_start = 0;
    handed_this_frame = 0;
    g_next_line_cyc = sg_next_event(&machine);
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

static int headless_state_option(const char *a, const char *v)
{
    if (!strcmp(a, "--save-state")) { if (!headless_path(v, state_save_file)) return -1; state_save_due = 1; }
    else if (!strcmp(a, "--save-at")) state_save_at = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--load-state")) { if (!headless_path(v, state_load_file)) return -1; state_load_due = 1; }
    else return 0;
    return 1;
}

/* The glue's service point: an instruction and the interrupt it may accept are complete. */
static void sg_main_service(void)
{
    if (!frame_ended)
        return;
    frame_ended = 0;
    if (headless) {
        if (state_load_due) {
            state_load_due = 0;
            if (sg_state_load(state_load_file) != RR_STATE_OK)
                exit(4);
            /* The pads are host input, not part of a state: the route's events up to the loaded frame apply again. A Pause among them
             * was taken before the state was saved (the state holds the /NMI edge as it was): it is not taken a second time. */
            const uint8_t edge = machine.nmi_edge;
            sg_route_events();
            machine.nmi_edge = edge;
            handed_this_frame = machine.line >= TMS_VBLANK_LINE;
            return;
        }
        if (route_frame_due) {
            SgCpuView c = native_cpu();
            sg_route_row(&c);
        }
        if (machine.frames >= frames_wanted)
            headless_finish();                  /* the report; it ends the process */
        if (state_save_due && machine.frames >= state_save_at) {
            state_save_due = 0;
            if (sg_state_save(state_save_file) != RR_STATE_OK)
                exit(3);
        }
        return;
    }
    switch (sg_host_frame(&machine)) {
    case 0: break;
    case 2: power_on(); break;
    default: sg_host_close(); exit(0);
    }
}

/* The game's own folder beside the executable, datas/games/sg1000-<identity>, as on the other machines: its quick state lives there. */
static void prepare_data_folder(void)
{
    static char folder[1024];
    char *base = SDL_GetBasePath();
    size_t start = base ? strlen(base) : 0;
    int n = snprintf(folder, sizeof folder, "%sdatas/games/sg1000-%.12s", base ? base : "", RR_SG_IDENTITY);
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
static bool sg_game_state_path(wchar_t *path, size_t capacity)
{
    return rr_from_utf8(state_file_utf8, path, capacity) != 0;
}

/* The machine from the game's own resource: the cartridge (103). */
static int setup_machine(void)
{
    size_t cart_size = 0;
    const uint8_t *cartridge = rr_resource(103, &cart_size);
    if (!cartridge || !cart_size || cart_size > sizeof cart) {
        fprintf(stderr, "[sg1000] the game's cartridge resource is missing\n");
        return 3;
    }
    memset(cart, 0xFF, sizeof cart);
    memcpy(cart, cartridge, cart_size);
    rom_bytes = (uint32_t)((cart_size + 0x1FFF) & ~(size_t)0x1FFF);
    sg_init(&machine, cart, rom_bytes, RR_SG_PAL ? SG_LINES_PAL : SG_LINES_NTSC);
    return 0;
}

static int run(void)
{
    int status = setup_machine();
    if (status)
        return status;
    machine.line_hook = line_hook;
    prepare_data_folder();
    if (!sg_host_open(RR_SG_TITLE, 3, &machine)) return 4;
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
