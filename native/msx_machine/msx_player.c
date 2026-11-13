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
#include "msx_sram.h"

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

/* An MSX2+ disk game (RR_MSX_DISKS > 0): the disks are resource 106 in order (RR_MSX_DISK_SIZES), the player's disk ROM ends the
 * BIOS source at 10000h, the controller is msx_fdc.c. What the game writes goes to a copy beside its settings
 * (datas/games/msx2plus-<identity>/disk-<n>.dsk), read back at the next start when its size is right, written a few seconds
 * after the game last wrote and when the game closes; the embedded disks are never changed. Page Up / Page Down (the computers'
 * keys, rrhk_computer.inc) put the previous or next disk in drive A. */
#if RR_MSX_DISKS
static const uint32_t disk_sizes[RR_MSX_DISKS] = RR_MSX_DISK_SIZES;
static uint8_t disk_data[RR_MSX_DISKS][2u * MSX_FDC_TRACKS * MSX_FDC_SPT * MSX_FDC_SECTOR];
static uint8_t disk_dirty[RR_MSX_DISKS];
static unsigned disk_index;
static MsxFdc fdc;
static char disk_folder[1024];
static int disk_copies;                          /* 0 in a headless run: nothing is written beside the game */

static int disk_copy_path(unsigned n, wchar_t *out)
{
    char path[1100];
    snprintf(path, sizeof path, "%s/disk-%u.dsk", disk_folder, n + 1);
    return rr_from_utf8(path, out, 1100);
}

static void disks_load_copies(void)
{
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) {
        wchar_t path[1100];
        if (!disk_copy_path(n, path)) continue;
        FILE *f = rr_fopen(path, L"rb");
        if (!f) continue;
        static uint8_t copy[sizeof disk_data[0]];
        size_t got = fread(copy, 1, sizeof copy, f);
        fclose(f);
        if (got == disk_sizes[n])                /* a copy of another size is not this disk's: the embedded one is kept */
            memcpy(disk_data[n], copy, got);
    }
}

static void disks_save(void)
{
    if (!disk_copies) return;
    if (fdc.disk[0].written) { disk_dirty[disk_index] = 1; fdc.disk[0].written = 0; }
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) {
        if (!disk_dirty[n]) continue;
        wchar_t path[1100], staged[1100];
        if (!disk_copy_path(n, path)) continue;
        swprintf(staged, 1100, L"%ls.tmp", path);
        FILE *f = rr_fopen(staged, L"wb");
        if (!f) continue;
        int ok = fwrite(disk_data[n], 1, disk_sizes[n], f) == disk_sizes[n] && rr_flush_file(f);
        ok = fclose(f) == 0 && ok;
        if (ok && rr_replace(staged, path)) disk_dirty[n] = 0; else rr_remove(staged);
    }
}

static void disks_at_exit(void) { disks_save(); }

static int disk_dirty_any(void)
{
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) if (disk_dirty[n]) return 1;
    return 0;
}

static void disks_swap(void)
{
    if (want_eject) want_eject = false;          /* eject is not offered: a disk game always has a disk in drive A */
    if (!want_swap) return;
    want_swap = false;
    if (RR_MSX_DISKS < 2 || swap_drive) { player_notice(RR_MSX_DISKS < 2 ? "This game has one disk" : "Drive B is not used"); return; }
    if (fdc.disk[0].written) { disk_dirty[disk_index] = 1; fdc.disk[0].written = 0; }
    disk_index = (disk_index + RR_MSX_DISKS + (swap_direction < 0 ? RR_MSX_DISKS - 1u : 1u)) % RR_MSX_DISKS;
    msx_fdc_insert(&fdc, 0, disk_data[disk_index], disk_sizes[disk_index], 0);
    char text[96];
    snprintf(text, sizeof text, rrhk_tr("Disk %u of %u in drive A", "Disquette %u sur %u dans le lecteur A"), disk_index + 1u,
             (unsigned)RR_MSX_DISKS);
    rrhk_notice(text, 3500);
}

/* A route's disk change in a headless run (msx_route.inc): disk `index` of the embedded ones in drive A. */
static void msx_route_disk(unsigned index)
{
    if (index >= RR_MSX_DISKS) return;
    if (fdc.disk[0].written) { disk_dirty[disk_index] = 1; fdc.disk[0].written = 0; }
    disk_index = index;
    msx_fdc_insert(&fdc, 0, disk_data[index], disk_sizes[index], 0);
}
#else
static void msx_route_disk(unsigned index) { (void)index; }
#endif

/* The cartridge's battery SRAM (msx_cart.c, msx_sram.c), when the conversion found one (RR_MSX_SRAM_BIT): beside the game in a
 * window; a headless run touches no file unless --sram names one. Its report gives the memory's hash at the start and at the
 * end, and the file's notice. */
static uint8_t sram_bytes[MSX_SRAM_MAX];
static size_t sram_size;
static wchar_t sram_file[32768];
static int sram_given;
static uint64_t sram_start_hash;
#if RR_MSX_DISKS
static uint64_t disk_start_hash[RR_MSX_DISKS];
#endif

static void sram_report(FILE *out)
{
    fprintf(out, "\"sram_bytes\": %u, \"sram_start_hash\": \"%016llx\", \"sram_hash\": \"%016llx\", \"sram_notice\": %u, ",
            (unsigned)sram_size, (unsigned long long)sram_start_hash, (unsigned long long)msx_sram_hash(sram_bytes, sram_size),
            msx_sram_notice());
#if RR_MSX_DISKS
    fprintf(out, "\"disk_start_hashes\": [");
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) fprintf(out, "%s\"%016llx\"", n ? ", " : "", (unsigned long long)disk_start_hash[n]);
    fprintf(out, "], \"disk_hashes\": [");
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n)
        fprintf(out, "%s\"%016llx\"", n ? ", " : "", (unsigned long long)msx_sram_hash(disk_data[n], disk_sizes[n]));
    fprintf(out, "], \"disk_written\": %d, ", fdc.disk[0].written || disk_dirty_any());
#endif
}
#define MSX_HEADLESS_SAVE_FIELDS(out) sram_report(out)
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

static int headless_state_option(const char *a, const char *v)
{
    if (!strcmp(a, "--save-state")) { if (!headless_path(v, state_save_file)) return -1; state_save_due = 1; }
    else if (!strcmp(a, "--save-at")) state_save_at = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--load-state")) { if (!headless_path(v, state_load_file)) return -1; state_load_due = 1; }
    else if (!strcmp(a, "--sram")) { if (!headless_path(v, sram_file)) return -1; sram_given = 1; }
#if RR_MSX_DISKS
    else if (!strcmp(a, "--disk-copies")) {
        if (strlen(v) >= sizeof disk_folder) return -1;
        strcpy(disk_folder, v);
        disk_copies = 1;
    }
#endif
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
    if (sram_size) {
        /* A save the game could not use never stops it: it is set aside, the game starts blank, the player is told once. */
        static int told;
        if (!told) {
            told = 1;
            unsigned state = msx_sram_notice();
            if (state == 1) rrhk_notice(rr_tr("Save unreadable: set aside"), 6000);
            else if (state == 2) rrhk_notice(rr_tr("Save unreadable: saving is off"), 6000);
        }
        msx_sram_flush(SDL_GetTicks64(), false);
    }
#if RR_MSX_DISKS
    disks_swap();
    {   /* what the game wrote goes to its copy once the disk has been quiet for about three seconds */
        static unsigned quiet;
        if (fdc.disk[0].written) { disk_dirty[disk_index] = 1; fdc.disk[0].written = 0; quiet = 0; }
        else if (++quiet == 180) disks_save();
    }
#endif
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
    int n = snprintf(folder, sizeof folder, "%sdatas/games/%s-%.12s", base ? base : "",
                     RR_MSX_MODEL == 3 ? "msx2plus" : RR_MSX_MODEL == 2 ? "msx2" : "msx",
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
/* The SRAM is written at once when the process ends, whatever way it ends (the window closed, the headless frame limit). */
static void sram_at_exit(void) { msx_sram_flush(SDL_GetTicks64(), true); }

static void sram_open(const wchar_t *path)
{
    if (!sram_size) return;
    msx_sram_open(path, sram_bytes, sram_size);
    sram_start_hash = msx_sram_hash(sram_bytes, sram_size);
    atexit(sram_at_exit);
}

static int setup_machine(void)
{
    size_t cart_size = 0, bios_size = 0;
    const uint8_t *cartridge = rr_resource(103, &cart_size), *bios_image = rr_resource(104, &bios_size);
    if (!cartridge || !bios_image || !cart_size || cart_size > sizeof cart || bios_size > sizeof slot0
        || (RR_MSX_MODEL >= 2 && bios_size != (RR_MSX_DISKS ? 0x14000u : 0x10000u))) {
        fprintf(stderr, "[msx] the game's cartridge or BIOS resource is missing\n");
        return 3;
    }
    msx_init(&machine, RR_MSX_PAL ? MSX_LINES_PAL : MSX_LINES_NTSC);
    memset(slot0, 0xFF, sizeof slot0);
    memcpy(slot0, bios_image, bios_size);
    if (RR_MSX_MODEL >= 2) {                      /* the MSX2 board: main, logo page and sub-ROM in one BIOS source */
        (RR_MSX_MODEL == 3 ? msx_setup_msx2plus : msx_setup_msx2)(&machine, slot0, mapper_ram, RR_MSX_MAPPER_SEGMENTS, &v9938);
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
    if (RR_MSX_SRAM_BIT && (RR_MSX_MAPPER == MSX_MAPPER_ASCII8 || RR_MSX_MAPPER == MSX_MAPPER_ASCII16)) {
        sram_size = RR_MSX_MAPPER == MSX_MAPPER_ASCII8 ? MSX_SRAM_ASCII8 : MSX_SRAM_ASCII16;
        device.sram = sram_bytes;
        device.sram_size = (uint16_t)sram_size;
        device.sram_bit = RR_MSX_SRAM_BIT;
    }
    msx_set_device(&machine, 1, 0, device);
#if RR_MSX_DISKS
    size_t disks_size = 0;
    const uint8_t *disks = rr_resource(106, &disks_size);
    size_t at = 0;
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) at += disk_sizes[n];
    if (!disks || disks_size != at) {
        fprintf(stderr, "[msx] the game's disks resource is missing\n");
        return 3;
    }
    at = 0;
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) {
        memcpy(disk_data[n], disks + at, disk_sizes[n]);
        at += disk_sizes[n];
    }
    if (disk_copies)
        disks_load_copies();
    memset(&fdc, 0, sizeof fdc);
    msx_set_disk_interface(&machine, 2, slot0 + 0x10000, &fdc, 8);
    msx_fdc_insert(&fdc, 0, disk_data[0], disk_sizes[0], 0);
#endif
    return 0;
}

static int run(void)
{
    int status = setup_machine();
    if (status)
        return status;
    machine.line_hook = line_hook;
    prepare_data_folder();
#if RR_MSX_DISKS
    {   /* the copies of the disks live beside player.cfg; a copy the game wrote before is put back now */
        size_t n = strlen(player_config);
        if (n > 11 && n - 11 < sizeof disk_folder) {
            memcpy(disk_folder, player_config, n - 11);          /* without "/player.cfg" */
            disk_folder[n - 11] = 0;
            disk_copies = 1;
            disks_load_copies();
            msx_fdc_insert(&fdc, 0, disk_data[0], disk_sizes[0], 0);
            atexit(disks_at_exit);
        }
    }
#endif
    if (sram_size) {
        static wchar_t path[32768];
        if (msx_sram_path(path, sizeof path / sizeof *path)) sram_open(path);
    }
    if (!msx_host_open(RR_MSX_TITLE, RR_MSX_MODEL >= 2 ? 2 : 3, &machine)) return 4;
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
    sram_start_hash = msx_sram_hash(sram_bytes, sram_size);
    if (sram_given) sram_open(sram_file);
#if RR_MSX_DISKS
    for (unsigned n = 0; n < RR_MSX_DISKS; ++n) disk_start_hash[n] = msx_sram_hash(disk_data[n], disk_sizes[n]);
    if (disk_copies) atexit(disks_at_exit);
#endif
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
