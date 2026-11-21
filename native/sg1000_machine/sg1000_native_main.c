/* Headless SG-1000 native run: the translated Z80 bodies of the cartridge, the shared banked step loop (native/banked_runtime.inc
 * rendered for the SG-1000 by retrorecomp.z80_chain: eight 8 KiB regions, no wait state, /INT and /NMI read at the end of each
 * instruction), the counted fallback on the corrected reference interpreter, and the machine of sg1000_machine.c, through
 * sg1000_glue.inc (shared with the game, sg1000_player.c). MIT, Retro-Recomp. The conversion runs it (headless) against the reference.
 *
 * Options: --cart FILE or - (the cartridge, from a file or standard input; the program pads it to whole 8 KiB regions) [--pal] [--learn FILE] and the common ones of
 * sg1000_headless.inc (--frames --frame --vram --report --watch --event --script --rows --audio). It prints the same JSON as
 * sg1000_reference, plus the native and fallback step counts. */
#define SMSRECOMP_BANKED_AOT 1
#include "sg1000_glue.inc"
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#include "sg1000_headless.inc"

static SgCpuView native_cpu(void)
{
    SgCpuView c;
    c.af = z80_af(&g_z80); c.bc = z80_bc(&g_z80); c.de = z80_de(&g_z80); c.hl = z80_hl(&g_z80);
    c.ix = g_z80.ix; c.iy = g_z80.iy; c.sp = g_z80.sp; c.pc = g_z80.pc;
    c.af2 = (uint16_t)(g_z80.a_ << 8 | g_z80.f_); c.bc2 = (uint16_t)(g_z80.b_ << 8 | g_z80.c_);
    c.de2 = (uint16_t)(g_z80.d_ << 8 | g_z80.e_); c.hl2 = (uint16_t)(g_z80.h_ << 8 | g_z80.l_);
    c.ir = (uint16_t)(g_z80.i << 8 | g_z80.r);
    c.flags = (uint16_t)(g_z80.im | (g_z80.iff1 ? 4 : 0) | (g_z80.iff2 ? 8 : 0) | (g_z80.halted ? 16 : 0));
    c.wz = g_z80.wz; c.iff1 = g_z80.iff1; c.iff2 = g_z80.iff2; c.halted = g_z80.halted; c.im = g_z80.im;
    c.i = g_z80.i; c.r = g_z80.r;
    return c;
}

static void native_extra(FILE *out)
{
    fprintf(out, "\"native_steps\": %llu, \"halt_steps\": %llu, \"fallback_steps\": %llu, \"guarded_steps\": %llu, \"fallback_cycles\": %llu, "
            "\"fallback_at\": {", (unsigned long long)banked_native_steps, (unsigned long long)banked_halt_steps,
            (unsigned long long)banked_fallback_steps, (unsigned long long)banked_guarded_steps, (unsigned long long)g_hybrid_cyc);
    for (int i = 0; i < 16 && fallback_count[i]; ++i)
        fprintf(out, "%s\"%04X\": %llu", i ? ", " : "", fallback_at[i], (unsigned long long)fallback_count[i]);
    fprintf(out, "}, ");
}

/* The end of the run: the learned code, the dumps and the report, then the process ends. */
static void headless_finish(void)
{
    if (learn_out) {
        FILE *f = fopen(learn_out, "w");
        for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
        if (f) fclose(f);
    }
    SgCpuView c = native_cpu();
    headless_report("native", &c, g_irq_taken, native_extra);
    exit(0);
}

/* At each instruction boundary the includer calls this when a frame may have ended (the native check: always; the game: after its
 * frame flag): the due row, the frame limit. */
static void sg_main_service(void)
{
    if (route_frame_due) {
        SgCpuView c = native_cpu();
        sg_route_row(&c);
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
    const char *cart_rom = NULL;
    int pal = 0, route_result;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--pal")) { pal = 1; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--learn")) learn_out = v;
        else if ((route_result = headless_option(a, v)) != 0) {
            if (route_result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; }
        } else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!cart_rom) { fprintf(stderr, "--cart is required\n"); return 2; }
    memset(cart, 0xFF, sizeof cart);
    long n = load(cart_rom, cart, (long)sizeof cart);
    uint32_t size = (uint32_t)((n + 0x1FFF) & ~0x1FFFL);
    if (!size) size = 0x2000;
    sg_init(&machine, cart, size, pal ? SG_LINES_PAL : SG_LINES_NTSC);
    machine.trace_frames = 1;                    /* comparisons: the per-frame running hash */
    machine.line_hook = sg_route_line;
    memset(&g_z80, 0, sizeof g_z80);
    g_next_line_cyc = sg_next_event(&machine);
    smsrecomp_banked_run();                      /* returns through headless_finish() at the frame limit */
    return 0;
}
