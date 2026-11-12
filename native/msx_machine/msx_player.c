/* An exported MSX game: the translated Z80 code of its cartridge and of its BIOS (msx_glue.inc and the generated bodies), the
 * MSX machine, and the host kit's window through the MSX adapter (hostkit/adapters/rrhk_msx.inc). MIT, Retro-Recomp.
 *
 * The cartridge is resource 103 and the slot-0 BIOS image resource 104 (C-BIOS's main and logo ROMs, or the player's own
 * 32 KiB BIOS); msx_game.h, written by the converter, gives the title, the mapper and where a plain cartridge sits. The guest
 * owns the loop: at the end of each frame the game hands the picture and the sound to the kit and takes the inputs back,
 * at an instruction boundary (msx_main_service). A reset starts the machine and the CPU again from address 0. */
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

#include "hostkit/adapters/rrhk_msx.inc"

static volatile int frame_ended;
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

static void msx_main_service(void)
{
    if (!frame_ended)
        return;
    frame_ended = 0;
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
    int n = snprintf(folder, sizeof folder, "%sdatas/games/msx-%.12s", base ? base : "", RR_MSX_IDENTITY);
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

static int run(void)
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
    machine.line_hook = line_hook;
    prepare_data_folder();
    if (!msx_host_open(RR_MSX_TITLE, RR_MSX_MODEL == 2 ? 2 : 3, &machine)) return 4;
    power_on();
    smsrecomp_banked_run();                       /* returns through exit() when the player quits */
    return 0;
}

#ifdef _WIN32
int main(void) { return run(); }
#else
int main(int argc, char **argv) { (void)argc; (void)argv; return run(); }
#endif
