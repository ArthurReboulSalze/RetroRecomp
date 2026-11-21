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
 * Not yet here (the CPC's step 3, in order): the quick states and the multiplayer snapshot (waiting for the shared Z80 state
 * piece, so that the MSX's is not copied a second time), the copies of a disk the game wrote, the disk keys for a game of
 * several disks. Until then F8/F9 say the state could not be written or read, the session hooks are left out (the kit then
 * does not offer the game in multiplayer), and a disk the game writes is written in memory only. */
#define SMSRECOMP_BANKED_AOT 1
#include <SDL.h>
#include "cpc_glue.inc"
#include "cpc_headless.inc"
#include "cpc_game.h"
#include "boot_keys.h"
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

/* Quick states and the multiplayer hooks: not yet (see the header); the session ones are taken off the kit's table in run(). */
static bool cpc_game_state_file(const wchar_t *path, bool load) { (void)path; (void)load; return false; }
static bool cpc_game_state_path(wchar_t *path, size_t capacity) { (void)path; (void)capacity; return false; }
static size_t cpc_snap_bound(void) { return 0; }
static size_t cpc_snap_save(void *buffer, size_t capacity) { (void)buffer; (void)capacity; return 0; }
static bool cpc_snap_load(const void *buffer, size_t size) { (void)buffer; (void)size; return false; }
static uint64_t cpc_snap_digest(void) { return 0; }
static void cpc_side_effects(bool allowed) { (void)allowed; }

#include "hostkit/adapters/rrhk_cpc.inc"

static uint8_t system_rom[0x8000], amsdos_rom[0x4000];
static const uint32_t disk_sizes[RR_CPC_DISKS] = RR_CPC_DISK_SIZES;
static uint8_t disk_data[RR_CPC_DISKS][RR_CPC_DISK_MAX];
static uint32_t picture[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];
static int headless;                             /* --headless: the start replayed, no host */

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

/* Headless: the boot keys of the frame that just ended, as the adapter's input function writes them in the window (the
 * matrix is the sequence's keys alone while it owns the keyboard, nothing after it; no joystick). */
static void headless_inputs(void)
{
    static uint8_t state[SDL_NUM_SCANCODES];
    memset(machine.ppi.keys, 0, sizeof machine.ppi.keys);
    machine.ppi.joystick[0] = machine.ppi.joystick[1] = 0;
    if (!rrhk_boot_keys_frame(&rr_boot_keys, (uint32_t)machine.frames, state))
        return;
    for (unsigned i = 0; i < sizeof RRHK_CPC_KEYS / sizeof RRHK_CPC_KEYS[0]; ++i)
        if (state[RRHK_CPC_KEYS[i].scancode]) cpc_ppi_key(&machine.ppi, RRHK_CPC_KEYS[i].cpc_key, 1);
}

static void cpc_main_service(void)
{
    if (headless) {
        if (machine.frame_ready)
            headless_inputs();
        headless_service();                      /* the frame's sound, the stop (it ends the process there) */
        return;
    }
    if (!machine.frame_ready)
        return;
    machine.frame_ready = 0;
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
    RrhkMachine *table = (RrhkMachine *)rrhk_adapter();
    table->snap_bound = NULL; table->snap_save = NULL; table->snap_load = NULL;   /* not yet: see the header */
    table->digest = NULL; table->side_effects = NULL;
    if (!cpc_host_open(RR_CPC_TITLE, 2)) return 4;
    power_on();
    smsrecomp_banked_run();                      /* returns through exit() when the player quits */
    return 0;
}

/* `--headless`: exit codes 0 done, 2 a bad option, 3 a missing resource or an unwritable file. */
static int run_headless(int argc, char **argv)
{
    for (int i = 2; i < argc; ++i)
        if (!headless_option(argc, argv, &i)) { fprintf(stderr, "unknown option %s\n", argv[i]); return 2; }
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
