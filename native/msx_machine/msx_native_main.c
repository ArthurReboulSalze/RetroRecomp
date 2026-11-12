/* Headless MSX native run: the translated Z80 bodies of the cartridge and of the BIOS, the shared banked step loop
 * (native/banked_runtime.inc rendered for the MSX by retrorecomp.z80_chain: a region map, one wait state per M1 cycle,
 * /INT read at the end of each instruction), the counted fallback on the corrected reference interpreter, and the MSX
 * machine of msx_machine.c, through msx_glue.inc (shared with the game, msx_player.c). MIT, Retro-Recomp. The
 * conversion runs it (headless) against the reference; tools/msx_native.py too.
 *
 * Timing contract, the same as msx_reference_main.c so the two runs can be compared state for state: an instruction's
 * I/O and its writes to a cartridge device happen at the instruction's start time; the machine's lines are run at
 * instruction boundaries; /INT is read once the machine has caught up with the instruction.
 *
 * Same options as msx_reference: --main --logo --cart [--mapper --cart-base --mirrored] --layout --frames --pal
 * --watch --event --frame --audio --vram. It prints the same JSON, plus the native and fallback step counts. */
#define SMSRECOMP_BANKED_AOT 1
#include "msx_glue.inc"

#include "msx_headless.inc"

/* The run stops at the frame limit once an instruction and the interrupt it may accept are complete, as the reference
 * does. */
static void msx_main_service(void)
{
    headless_service();
}

static long load(const char *path, uint8_t *into, long limit)
{
    int piped = !strcmp(path, "-");
#ifdef _WIN32
    if (piped) _setmode(_fileno(stdin), _O_BINARY);
#endif
    FILE *f = piped ? stdin : fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot open %s\n", path); exit(2); }
    long n = (long)fread(into, 1, (size_t)limit, f);
    int more = fgetc(f) != EOF;
    if (!piped) fclose(f);
    if (more) { fprintf(stderr, "%s is larger than %ld bytes\n", path, limit); exit(2); }
    return n;
}

int main(int argc, char **argv)
{
    const char *main_rom = NULL, *logo_rom = NULL, *sub_rom = NULL, *cart_rom = NULL, *layout = "basic";
    unsigned long mapper_kib = 256;
    unsigned long cart_base = 0x4000;
    int pal = 0, mirrored = 0, route_result;
    MsxMapper mapper = MSX_MAPPER_PLAIN;
    static const char *const mapper_names[MSX_MAPPER_COUNT] = { "plain", "konami", "konami-scc", "ascii8", "ascii16" };
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!strcmp(a, "--mirrored")) { mirrored = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--main")) main_rom = v;
        else if (!strcmp(a, "--logo")) logo_rom = v;
        else if (!strcmp(a, "--sub")) sub_rom = v;
        else if (!strcmp(a, "--mapper-kib")) mapper_kib = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--cart-base")) cart_base = strtoul(v, NULL, 16);
        else if (!strcmp(a, "--layout")) layout = v;
        else if (!strcmp(a, "--learn")) learn_out = v;
        else if (!strcmp(a, "--mapper")) {
            int found = -1;
            for (int k = 0; k < MSX_MAPPER_COUNT; ++k) if (!strcmp(v, mapper_names[k])) found = k;
            if (found < 0) { fprintf(stderr, "unknown mapper %s\n", v); return 2; }
            mapper = (MsxMapper)found;
        } else if ((route_result = headless_option(a, v)) != 0) {
            if (route_result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; }
        } else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!main_rom) { fprintf(stderr, "--main is required\n"); return 2; }
    msx_init(&machine, pal ? MSX_LINES_PAL : MSX_LINES_NTSC);
    machine.trace_frames = 1;                    /* comparisons: the per-frame running hash */
    memset(slot0, 0xFF, sizeof slot0);
    load(main_rom, slot0, 0x8000);
    if (logo_rom) load(logo_rom, slot0 + 0x8000, 0x4000);
    memset(ram, 0, sizeof ram);
    if (sub_rom) {                               /* MSX2: the sub-ROM ends the BIOS source; the board of msx_setup_msx2 */
        uint32_t segments = (uint32_t)(mapper_kib / 16);
        if (segments < 4 || segments > 256 || (segments & (segments - 1))) { fprintf(stderr, "bad --mapper-kib\n"); return 2; }
        load(sub_rom, slot0 + 0xC000, 0x4000);
        msx_setup_msx2(&machine, slot0, mapper_ram, segments, &v9938);
    } else {
    MsxDevice bios = { MSX_DEV_ROM, slot0, logo_rom ? 0xC000u : 0x8000u, 0, NULL };
    bios.source = 1;                             /* the BIOS is the second translated source (banked.sources) */
    msx_set_device(&machine, 0, 0, bios);
    if (!strcmp(layout, "expanded")) {
        msx_set_expanded(&machine, 3, 1);
        msx_set_device(&machine, 3, 2, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else if (!strcmp(layout, "basic")) {
        msx_set_device(&machine, 3, 0, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else { fprintf(stderr, "unknown layout %s\n", layout); return 2; }
    }
    if (cart_rom) {
        memset(cart, 0xFF, sizeof cart);
        long n = load(cart_rom, cart, (long)sizeof cart);
        MsxDevice device = { MSX_DEV_ROM, cart, (uint32_t)n, (uint16_t)cart_base, NULL };
        device.mapper = mapper;
        device.mirrored = (uint8_t)mirrored;
        device.source = 0;                       /* the cartridge is the first translated source (game.toml) */
        msx_set_device(&machine, 1, 0, device);
    }
    machine.line_hook = msx_route_line;
    memset(&g_z80, 0, sizeof g_z80);
    g_next_line_cyc = msx_next_event(&machine);
    smsrecomp_banked_run();                      /* returns through headless_finish() at the frame limit */
    return 0;
}
