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

static unsigned long frames_wanted = 120;
static void finish(void);

/* The run stops at the frame limit once an instruction and the interrupt it may accept are complete, as the reference
 * does. */
static unsigned long long trace_from, trace_to;   /* tools: the instructions that start in a window of machine cycles */
static uint32_t native_cpu_hash(void);
static void msx_route_row(uint32_t cpu, uint16_t pc);
static int route_frame_due;
static void msx_main_service(void)
{
    if (route_frame_due)
        msx_route_row(native_cpu_hash(), g_z80.pc);
    if (trace_to && g_z80.cyc >= trace_from && g_z80.cyc < trace_to)
        fprintf(stderr, "T %llu %04X\n", (unsigned long long)g_z80.cyc, g_z80.pc);
    if (machine.frames >= frames_wanted)
        finish();
}

/* ---- options, report ---- */
static const char *frame_out, *vram_out;
static unsigned watch[32];
static int watches;

#include "msx_route.inc"

/* The registers in the rows' order (msx_route_cpu_hash): AF BC DE HL IX IY SP PC, AF' BC' DE' HL', IR, IM|IFF1|IFF2|halted,
 * WZ, 0. */
static uint32_t native_cpu_hash(void)
{
    const uint16_t regs[16] = {
        z80_af(&g_z80), z80_bc(&g_z80), z80_de(&g_z80), z80_hl(&g_z80), g_z80.ix, g_z80.iy, g_z80.sp, g_z80.pc,
        (uint16_t)(g_z80.a_ << 8 | g_z80.f_), (uint16_t)(g_z80.b_ << 8 | g_z80.c_), (uint16_t)(g_z80.d_ << 8 | g_z80.e_),
        (uint16_t)(g_z80.h_ << 8 | g_z80.l_), (uint16_t)(g_z80.i << 8 | g_z80.r),
        (uint16_t)(g_z80.im | (g_z80.iff1 ? 4 : 0) | (g_z80.iff2 ? 8 : 0) | (g_z80.halted ? 16 : 0)), g_z80.wz, 0 };
    return msx_route_cpu_hash(regs);
}

static void finish(void)
{
    msx_route_finish();
    if (learn_out) {
        FILE *f = fopen(learn_out, "w");
        for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
        if (f) fclose(f);
    }
    uint32_t frame_hash = msx_frame_hash(&machine);
    if (frame_out) {
        FILE *f = fopen(frame_out, "wb");
        if (f) { msx_dump_frame(&machine, f); fclose(f); }
    }
    if (vram_out) {
        FILE *f = fopen(vram_out, "wb");
        if (f) { msx_dump_vram(&machine, f); fclose(f); }
    }
    printf("{\"engine\": \"native\", \"frames\": %llu, \"cycles\": %llu, \"interrupts\": %llu, "
           "\"pc\": %u, \"pc_slot\": %u, \"sp\": %u, \"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, "
           "\"iff1\": %d, \"halted\": %d, \"primary\": %u, \"secondary\": [%u, %u, %u, %u], "
           "\"vdp_regs\": [%u, %u, %u, %u, %u, %u, %u, %u], \"vdp_status\": %u, \"vram_fnv\": %u, \"ram_fnv\": %u, "
           "\"frame_fnv\": %u, \"audio_samples\": %llu, \"audio_fnv\": %u, "
           "\"native_steps\": %llu, \"halt_steps\": %llu, \"fallback_steps\": %llu, \"guarded_steps\": %llu, "
           "\"fallback_cycles\": %llu, \"fallback_at\": {",
           (unsigned long long)machine.frames, (unsigned long long)machine.cycles, (unsigned long long)g_irq_taken,
           g_z80.pc, msx_slot_of(&machine, g_z80.pc), g_z80.sp, z80_af(&g_z80), z80_bc(&g_z80), z80_de(&g_z80),
           z80_hl(&g_z80), g_z80.ix, g_z80.iy, g_z80.iff1, g_z80.halted, machine.primary, machine.secondary[0],
           machine.secondary[1], machine.secondary[2], machine.secondary[3], machine.vdp.reg[0], machine.vdp.reg[1],
           machine.vdp.reg[2], machine.vdp.reg[3], machine.vdp.reg[4], machine.vdp.reg[5], machine.vdp.reg[6],
           machine.vdp.reg[7], machine.vdp.status, msx_vram_hash(&machine), msx_ram_hash(&machine, ram), frame_hash, (unsigned long long)route_samples, route_audio_hash,
           (unsigned long long)banked_native_steps, (unsigned long long)banked_halt_steps,
           (unsigned long long)banked_fallback_steps, (unsigned long long)banked_guarded_steps,
           (unsigned long long)g_hybrid_cyc);
    for (int i = 0; i < 16 && fallback_count[i]; ++i)
        printf("%s\"%04X\": %llu", i ? ", " : "", fallback_at[i], (unsigned long long)fallback_count[i]);
    printf("}, \"af2\": %u, \"bc2\": %u, \"de2\": %u, \"hl2\": %u, \"i\": %u, \"r\": %u, \"im\": %u, \"iff2\": %d, \"wz\": %u, ",
           (unsigned)(g_z80.a_ << 8 | g_z80.f_), (unsigned)(g_z80.b_ << 8 | g_z80.c_), (unsigned)(g_z80.d_ << 8 | g_z80.e_),
           (unsigned)(g_z80.h_ << 8 | g_z80.l_), g_z80.i, g_z80.r, g_z80.im, g_z80.iff2, g_z80.wz);
    msx_print_state(&machine, stdout);
    printf("\"watch\": {");
    for (int i = 0; i < watches; ++i)
        printf("%s\"%04X\": %u", i ? ", " : "", watch[i], msx_peek(&machine, (uint16_t)watch[i]));
    printf("}}\n");
    fflush(stdout);
    exit(0);
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
        else if (!strcmp(a, "--frames")) frames_wanted = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--frame")) frame_out = v;
        else if (!strcmp(a, "--vram")) vram_out = v;
        else if (!strcmp(a, "--learn")) learn_out = v;
        else if (!strcmp(a, "--trace-cycles")) sscanf(v, "%llu:%llu", &trace_from, &trace_to);
        else if (!strcmp(a, "--watch") && watches < 32) watch[watches++] = (unsigned)strtoul(v, NULL, 16) & 0xFFFF;
        else if (!strcmp(a, "--mapper")) {
            int found = -1;
            for (int k = 0; k < MSX_MAPPER_COUNT; ++k) if (!strcmp(v, mapper_names[k])) found = k;
            if (found < 0) { fprintf(stderr, "unknown mapper %s\n", v); return 2; }
            mapper = (MsxMapper)found;
        } else if ((route_result = msx_route_option(a, v)) != 0) {
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
    smsrecomp_banked_run();                      /* returns through finish() at the frame limit */
    return 0;
}
