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
static void msx_main_service(void)
{
    if (machine.frames >= frames_wanted)
        finish();
}

/* ---- options, report ---- */
static const char *frame_out, *audio_out, *vram_out;
static unsigned watch[32];
static int watches;
typedef struct { unsigned long frame; int joy, a, b, c; } Event;
static Event events[64];
static int event_count, next_event;
static FILE *audio;
static uint32_t audio_hash = 2166136261u;
static uint64_t samples;
static int16_t chunk[MSX_AUDIO_BUFFER];

static uint32_t fnv_add(uint32_t h, const uint8_t *data, size_t size)
{
    for (size_t i = 0; i < size; ++i) h = (h ^ data[i]) * 16777619u;
    return h;
}

static void drain_audio(void)
{
    unsigned n = msx_audio_take(&machine, chunk, MSX_AUDIO_BUFFER);
    audio_hash = fnv_add(audio_hash, (const uint8_t *)chunk, n * sizeof *chunk);
    samples += n;
    if (audio) fwrite(chunk, sizeof *chunk, n, audio);
}

/* Called from the step loop's time path: apply input events, collect sound. */
static void frame_service(void)
{
    for (; next_event < event_count && events[next_event].frame <= machine.frames; ++next_event) {
        const Event *e = &events[next_event];
        if (e->joy) msx_joystick(&machine, e->a, (uint8_t)e->b);
        else msx_key(&machine, e->a, e->b, e->c);
    }
    if (machine.synth.out_count >= MSX_AUDIO_BUFFER / 2)
        drain_audio();
}

static void finish(void)
{
    drain_audio();
    if (audio) fclose(audio);
    if (learn_out) {
        FILE *f = fopen(learn_out, "w");
        for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
        if (f) fclose(f);
    }
    uint32_t frame_hash = fnv_add(fnv_add(2166136261u, &machine.vdp.frame[0][0], sizeof machine.vdp.frame),
                                  machine.vdp.border, sizeof machine.vdp.border);
    if (frame_out) {
        FILE *f = fopen(frame_out, "wb");
        if (f) { fwrite(machine.vdp.frame, 1, sizeof machine.vdp.frame, f); fwrite(machine.vdp.border, 1, sizeof machine.vdp.border, f); fclose(f); }
    }
    if (vram_out) {
        FILE *f = fopen(vram_out, "wb");
        if (f) { fwrite(machine.vdp.vram, 1, sizeof machine.vdp.vram, f); fclose(f); }
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
           machine.vdp.reg[7], machine.vdp.status, fnv_add(2166136261u, machine.vdp.vram, sizeof machine.vdp.vram),
           fnv_add(2166136261u, ram, sizeof ram), frame_hash, (unsigned long long)samples, audio_hash,
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
    const char *main_rom = NULL, *logo_rom = NULL, *cart_rom = NULL, *layout = "basic";
    unsigned long cart_base = 0x4000;
    int pal = 0, mirrored = 0;
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
        else if (!strcmp(a, "--cart")) cart_rom = v;
        else if (!strcmp(a, "--cart-base")) cart_base = strtoul(v, NULL, 16);
        else if (!strcmp(a, "--layout")) layout = v;
        else if (!strcmp(a, "--frames")) frames_wanted = strtoul(v, NULL, 10);
        else if (!strcmp(a, "--frame")) frame_out = v;
        else if (!strcmp(a, "--audio")) audio_out = v;
        else if (!strcmp(a, "--vram")) vram_out = v;
        else if (!strcmp(a, "--learn")) learn_out = v;
        else if (!strcmp(a, "--watch") && watches < 32) watch[watches++] = (unsigned)strtoul(v, NULL, 16) & 0xFFFF;
        else if (!strcmp(a, "--mapper")) {
            int found = -1;
            for (int k = 0; k < MSX_MAPPER_COUNT; ++k) if (!strcmp(v, mapper_names[k])) found = k;
            if (found < 0) { fprintf(stderr, "unknown mapper %s\n", v); return 2; }
            mapper = (MsxMapper)found;
        } else if (!strcmp(a, "--event") && event_count < 64) {
            Event *e = &events[event_count];
            unsigned long f; int r, b, d; unsigned port, bits;
            if (sscanf(v, "%lu:key:%d:%d:%d", &f, &r, &b, &d) == 4) *e = (Event){ f, 0, r, b, d };
            else if (sscanf(v, "%lu:joy:%u:%x", &f, &port, &bits) == 3) *e = (Event){ f, 1, (int)port, (int)bits, 0 };
            else { fprintf(stderr, "bad event %s\n", v); return 2; }
            ++event_count;
        } else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!main_rom) { fprintf(stderr, "--main is required\n"); return 2; }
    msx_init(&machine, pal ? MSX_LINES_PAL : MSX_LINES_NTSC);
    machine.trace_frames = 1;                    /* comparisons: the per-frame running hash */
    memset(slot0, 0xFF, sizeof slot0);
    load(main_rom, slot0, 0x8000);
    if (logo_rom) load(logo_rom, slot0 + 0x8000, 0x4000);
    MsxDevice bios = { MSX_DEV_ROM, slot0, logo_rom ? 0xC000u : 0x8000u, 0, NULL };
    bios.source = 1;                             /* the BIOS is the second translated source (banked.sources) */
    msx_set_device(&machine, 0, 0, bios);
    memset(ram, 0, sizeof ram);
    if (!strcmp(layout, "expanded")) {
        msx_set_expanded(&machine, 3, 1);
        msx_set_device(&machine, 3, 2, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else if (!strcmp(layout, "basic")) {
        msx_set_device(&machine, 3, 0, (MsxDevice){ MSX_DEV_RAM, NULL, 0, 0, ram });
    } else { fprintf(stderr, "unknown layout %s\n", layout); return 2; }
    if (cart_rom) {
        memset(cart, 0xFF, sizeof cart);
        long n = load(cart_rom, cart, (long)sizeof cart);
        MsxDevice device = { MSX_DEV_ROM, cart, (uint32_t)n, (uint16_t)cart_base, NULL };
        device.mapper = mapper;
        device.mirrored = (uint8_t)mirrored;
        device.source = 0;                       /* the cartridge is the first translated source (game.toml) */
        msx_set_device(&machine, 1, 0, device);
    }
    if (audio_out && !(audio = fopen(audio_out, "wb"))) { fprintf(stderr, "cannot write %s\n", audio_out); return 3; }
    machine.line_hook = frame_service;
    memset(&g_z80, 0, sizeof g_z80);
    g_next_line_cyc = machine.next_line;
    smsrecomp_banked_run();                      /* returns through finish() at the frame limit */
    return 0;
}
