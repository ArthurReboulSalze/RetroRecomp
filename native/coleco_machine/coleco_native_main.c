/* Headless ColecoVision native run: the translated Z80 bodies of the BIOS and of the cartridge, the shared banked step loop
 * (native/banked_runtime.inc rendered for the ColecoVision by retrorecomp.z80_chain: eight 8 KiB regions, one wait state on every M1 cycle, /NMI read at the end of
 * each instruction), the counted fallback on the corrected reference interpreter, and the machine of coleco_machine.c, through
 * coleco_glue.inc (shared with the game, coleco_player.c). MIT, Retro-Recomp. The conversion runs it (headless) against the reference.
 *
 * Options: --bios FILE (the player's BIOS, 8 KiB) --cart FILE or - (the cartridge, from a file or standard input; the program pads it to whole 8 KiB
 * regions) [--pal] [--learn FILE] and the common ones of coleco_headless.inc (--frames --frame --vram --ram --report --watch --event --script --rows
 * --audio). It prints the same JSON as coleco_reference, plus the native and fallback step counts. */
#define SMSRECOMP_BANKED_AOT 1
#include "coleco_glue.inc"
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#define CV_HEADLESS_NATIVE 1                  /* the native side of the headless run (native_cpu, native_extra, headless_finish) */
#include "coleco_headless.inc"

/* At each instruction boundary the includer calls this when a frame may have ended (the native check: always; the game: after its
 * frame flag): the due row, the frame limit. */
static void cv_main_service(void)
{
    if (route_frame_due) {
        CvCpuView c = native_cpu();
        cv_route_row(&c);
    }
    if (machine.frames >= frames_wanted)
        headless_finish();
}

/* "-" reads standard input: a player's ROM taken from its archive in memory reaches the program with no file copy. */
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
    const char *cart_rom = NULL, *bios_rom = NULL;
    int pal = 0, route_result;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--bios")) bios_rom = v;
        else if (!strcmp(a, "--learn")) learn_out = v;
        else if ((route_result = headless_option(a, v)) != 0) {
            if (route_result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; }
        } else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!cart_rom || !bios_rom) { fprintf(stderr, "--bios and --cart are required\n"); return 2; }
    if (load(bios_rom, bios, CV_BIOS_SIZE) != CV_BIOS_SIZE) { fprintf(stderr, "%s is not an 8 KiB BIOS\n", bios_rom); return 2; }
    memset(cart, 0xFF, sizeof cart);
    long n = load(cart_rom, cart, (long)sizeof cart);
    uint32_t size = (uint32_t)((n + 0x1FFF) & ~0x1FFFL);
    if (!size) size = 0x2000;
    cv_init(&machine, bios, cart, size, pal ? CV_LINES_PAL : CV_LINES_NTSC);
    machine.trace_frames = 1;                    /* comparisons: the per-frame running hash */
    machine.line_hook = cv_route_line;
    memset(&g_z80, 0, sizeof g_z80);
    g_next_line_cyc = cv_next_event(&machine);
    smsrecomp_banked_run();                      /* returns through headless_finish() at the frame limit */
    return 0;
}
