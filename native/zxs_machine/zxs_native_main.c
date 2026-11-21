/* Headless ZX Spectrum native run: the translated Z80 bodies of the ROM, the code learned from RAM run through the byte guards,
 * the shared banked step loop and the counted fallback on the corrected reference interpreter, on the machine of zxs_machine.c
 * (zxs_glue.inc). MIT, Retro-Recomp. The conversion runs it against zxs_reference_main.c.
 *
 * Usage: zxs_check --rom FILE --image FILE [--learn FILE] and the route's options (zxs_headless.inc). "-" for --image reads the
 * standard input. It prints the same JSON as the reference, plus the native, guarded and fallback step counts. */
#define SMSRECOMP_BANKED_AOT 1
#include "zxs_glue.inc"

static void headless_registers(uint16_t r[16])
{
    const uint16_t regs[16] = {
        z80_af(&g_z80), z80_bc(&g_z80), z80_de(&g_z80), z80_hl(&g_z80), g_z80.ix, g_z80.iy, g_z80.sp, g_z80.pc,
        (uint16_t)(g_z80.a_ << 8 | g_z80.f_), (uint16_t)(g_z80.b_ << 8 | g_z80.c_), (uint16_t)(g_z80.d_ << 8 | g_z80.e_),
        (uint16_t)(g_z80.h_ << 8 | g_z80.l_), (uint16_t)(g_z80.i << 8 | g_z80.r),
        (uint16_t)(g_z80.im | (g_z80.iff1 ? 4 : 0) | (g_z80.iff2 ? 8 : 0) | (g_z80.halted ? 16 : 0)), g_z80.wz, 0 };
    memcpy(r, regs, sizeof regs);
}
static uint64_t headless_interrupts(void) { return g_irq_taken; }
#define HEADLESS_ENGINE "native"
#define HEADLESS_EXTRA(out) do { \
    fprintf(out, "\"native_steps\": %llu, \"halt_steps\": %llu, \"fallback_steps\": %llu, \"guarded_steps\": %llu, " \
            "\"fallback_cycles\": %llu, \"fallback_at\": {", (unsigned long long)banked_native_steps, \
            (unsigned long long)banked_halt_steps, (unsigned long long)banked_fallback_steps, \
            (unsigned long long)banked_guarded_steps, (unsigned long long)g_hybrid_cyc); \
    for (int i_ = 0; i_ < 16 && fallback_count[i_]; ++i_) \
        fprintf(out, "%s\"%04X\": %llu", i_ ? ", " : "", fallback_at[i_], (unsigned long long)fallback_count[i_]); \
    fprintf(out, "}, "); \
} while (0)
#include "zxs_headless.inc"

static void zxs_main_service(void)
{
    if (headless_service()) {
        headless_report();
        if (learn_out) {
            FILE *f = fopen(learn_out, "w");
            for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
            if (f) fclose(f);
        }
        exit(0);
    }
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
    const char *rom_file = NULL, *image_file = NULL;
    static uint8_t image[ZXS_IMAGE_BYTES];
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        ++i;
        int result;
        if (!strcmp(a, "--rom")) rom_file = v;
        else if (!strcmp(a, "--image")) image_file = v;
        else if (!strcmp(a, "--learn")) learn_out = v;
        else if ((result = headless_option(a, v)) != 0) { if (result < 0) { fprintf(stderr, "bad value for %s\n", a); return 2; } }
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!rom_file || !image_file) { fprintf(stderr, "--rom and --image are required\n"); return 2; }
    memset(rom, 0xFF, sizeof rom);
    long rom_size = load(rom_file, rom, (long)sizeof rom);
    long size = load(image_file, image, (long)sizeof image);
    ZxsCpuStart cpu;
    if (zxs_load_image(&machine, image, (size_t)size, rom, &cpu)) { fprintf(stderr, "not a machine image\n"); return 2; }
    if (rom_size != (machine.model == ZXS_128K ? 0x8000 : 0x4000)) { fprintf(stderr, "the ROM is not the model's\n"); return 2; }
    headless_start();
    zxs_cpu_from_image(&cpu);
    g_next_line_cyc = zxs_next_event(&machine);
    smsrecomp_banked_run();                      /* returns through exit() at the frame limit */
    return 0;
}
