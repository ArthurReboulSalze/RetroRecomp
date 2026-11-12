/* An exported MSX game: the translated Z80 code of its cartridge and of its BIOS (msx_glue.inc and the generated bodies), the
 * MSX machine, and the host kit's window through the MSX adapter (hostkit/adapters/rrhk_msx.inc). MIT, Retro-Recomp.
 *
 * The cartridge is resource 103 and the slot-0 BIOS image resource 104 (C-BIOS's main and logo ROMs, or the player's own
 * 32 KiB BIOS); msx_game.h, written by the converter, gives the title, the mapper and where a plain cartridge sits. The guest
 * owns the loop: at the end of each frame the game hands the picture and the sound to the kit and takes the inputs back,
 * at an instruction boundary (msx_main_service). A reset starts the machine and the CPU again from address 0.
 *
 * `game.exe --headless [options]` replays a route with no window, no sound device and nothing written beside the game: the
 * cartridge and the BIOS are the game's own resources, the options and the report those of the native check
 * (msx_headless.inc), so the delivered (packed) file is compared with the reference as the check is. The player's own
 * path is unchanged: its per-instruction service keeps its one test (frame_ended); the headless branch comes after it. */
#define SMSRECOMP_BANKED_AOT 1
#include <SDL.h>
#include "msx_glue.inc"
#include "msx_game.h"
#include "embedded_resources.h"
#include "platform_io.h"

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

#include "msx_state_file.inc"

/* Quick states for the host kit's F8/F9 (defined below, after the frame hand-over they reset). */
static bool msx_game_state_file(const wchar_t *path, bool load);
static bool msx_game_state_path(wchar_t *path, size_t capacity);

#include "hostkit/adapters/rrhk_msx.inc"
#include "msx_headless.inc"

static volatile int frame_ended;
static int headless;                           /* --headless: a route replayed, no host */
/* The picture is whole and the VDP raises its frame flag at the first line after the picture (192, or 212 on a V9938 set
 * so): the frame is handed over there, so the inputs taken back reach the game's own vertical-blank interrupt that follows
 * (not one frame later). */
static int handed_this_frame;                  /* one hand-over per frame even when R#9 LN changes mid-frame */
static void line_hook(void)
{
    if (machine.line == 0)
        handed_this_frame = 0;
    if (!handed_this_frame && machine.line >= machine.vblank_line) {
        handed_this_frame = 1;
        frame_ended = 1;
    }
}

/* F8/F9 in play, at the service point (the kit calls this from the frame's end): after a load, the frame's hand-over
 * follows the loaded line, as line_hook would have left it. */
static bool msx_game_state_file(const wchar_t *path, bool load)
{
    if (!load)
        return msx_state_save(path) == RR_STATE_OK;
    if (msx_state_load(path) != RR_STATE_OK)
        return false;
    handed_this_frame = machine.line >= machine.vblank_line;
    return true;
}

static void power_on(void)
{
    msx_reset(&machine);
    memset(ram, 0, sizeof ram);
    if (machine.mapper.segments)
        memset(mapper_ram, 0, (size_t)machine.mapper.segments * 0x4000u);
    if (machine.video == MSX_VIDEO_V9938)
        memset(v9938.vram, 0, sizeof v9938.vram);
    memset(&g_z80, 0, sizeof g_z80);
    g_z80.a = g_z80.f = 0xFF; g_z80.sp = 0xFFFF;   /* the reset values the step loop sets at its start */
    machine.cycles = 0;
    g_next_line_cyc = msx_next_event(&machine);
}

/* Headless: the route's line hook, and the frame flag raised with the route's row so the service below sees it. */
static void headless_line(void)
{
    msx_route_line();
    if (route_frame_due)
        frame_ended = 1;
}

/* Headless states (the conversion's fresh-process check): --save-state FILE with --save-at N saves at the service of
 * frame N, after its row; --load-state FILE loads at the first service of the run (the one instruction run before it is
 * overwritten whole), then the script's events up to the loaded frame apply at once. A refused state ends the process with
 * exit 4, leaving the file as it was; a state that cannot be written, with exit 3. */
static wchar_t state_save_file[32768], state_load_file[32768];
static unsigned long state_save_at;
static int state_save_due, state_load_due;

static int headless_state_option(const char *a, const char *v)
{
    if (!strcmp(a, "--save-state")) { if (!rr_from_utf8(v, state_save_file, 32768)) return -1; state_save_due = 1; }
    else if (!strcmp(a, "--save-at")) state_save_at = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--load-state")) { if (!rr_from_utf8(v, state_load_file, 32768)) return -1; state_load_due = 1; }
    else return 0;
    return 1;
}

static void msx_main_service(void)
{
    if (!frame_ended)
        return;
    frame_ended = 0;
    if (headless) {
        if (state_load_due) {
            state_load_due = 0;
            if (msx_state_load(state_load_file) != RR_STATE_OK)
                exit(4);
            msx_route_events();
            return;
        }
        headless_service();                    /* the row, the frame limit (it ends the process there) */
        if (state_save_due && machine.frames >= state_save_at) {
            state_save_due = 0;
            if (msx_state_save(state_save_file) != RR_STATE_OK)
                exit(3);
        }
        return;
    }
    switch (msx_host_frame(&machine)) {
    case 0: break;
    case 2: power_on(); g_z80.cyc = 0; step_start = 0; break;
    default: msx_host_close(); exit(0);
    }
}

/* The game's own folder beside the executable, datas/games/msx-<identity>, as on the other machines: the player's settings
 * of the computer adapter (player.cfg) live there, never in the export folder itself. */
static void prepare_data_folder(void)
{
    static char folder[1024];
    char *base = SDL_GetBasePath();
    size_t start = base ? strlen(base) : 0;
    int n = snprintf(folder, sizeof folder, "%sdatas/games/%s-%.12s", base ? base : "", RR_MSX_MODEL == 2 ? "msx2" : "msx",
                     RR_MSX_IDENTITY);
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
}

/* The quick state's file beside player.cfg (the kit asks when it opens the window). */
static bool msx_game_state_path(wchar_t *path, size_t capacity)
{
    return rr_from_utf8(state_file_utf8, path, capacity) != 0;
}

/* The machine from the game's own resources: the cartridge (103) and the BIOS source (104), as msx_game.h describes them. */
static int setup_machine(void)
{
    size_t cart_size = 0, bios_size = 0;
    const uint8_t *cartridge = rr_resource(103, &cart_size), *bios_image = rr_resource(104, &bios_size);
    if (!cartridge || !bios_image || !cart_size || cart_size > sizeof cart || bios_size > sizeof slot0
        || (RR_MSX_MODEL == 2 && bios_size != 0x10000)) {
        fprintf(stderr, "[msx] the game's cartridge or BIOS resource is missing\n");
        return 3;
    }
    msx_init(&machine, RR_MSX_PAL ? MSX_LINES_PAL : MSX_LINES_NTSC);
    memset(slot0, 0xFF, sizeof slot0);
    memcpy(slot0, bios_image, bios_size);
    if (RR_MSX_MODEL == 2) {                      /* the MSX2 board: main, logo page and sub-ROM in one BIOS source */
        msx_setup_msx2(&machine, slot0, mapper_ram, RR_MSX_MAPPER_SEGMENTS, &v9938);
    } else {
        MsxDevice bios = { MSX_DEV_ROM, slot0, (uint32_t)bios_size, 0, NULL };
        bios.source = 1;
        msx_set_device(&machine, 0, 0, bios);
        msx_set_device(&machine, 3, 0, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    }
    memset(cart, 0xFF, sizeof cart);
    memcpy(cart, cartridge, cart_size);
    MsxDevice device = { MSX_DEV_ROM, cart, (uint32_t)cart_size, RR_MSX_CART_BASE, NULL };
    device.mapper = RR_MSX_MAPPER;
    device.mirrored = RR_MSX_MIRRORED;
    device.source = 0;
    msx_set_device(&machine, 1, 0, device);
    return 0;
}

static int run(void)
{
    int status = setup_machine();
    if (status)
        return status;
    machine.line_hook = line_hook;
    prepare_data_folder();
    if (!msx_host_open(RR_MSX_TITLE, RR_MSX_MODEL == 2 ? 2 : 3, &machine)) return 4;
    power_on();
    smsrecomp_banked_run();                       /* returns through exit() when the player quits */
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
    frame_ended = state_load_due;              /* a load waits for the first service, not for the first frame */
    smsrecomp_banked_run();                    /* returns through headless_finish() at the frame limit */
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--headless"))
        return run_headless(argc, argv);
    return run();
}
