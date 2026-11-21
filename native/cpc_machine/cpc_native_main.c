/* Headless Amstrad CPC native run: the translated Z80 bodies of the system ROM and AMSDOS, the shared banked step loop
 * (native/banked_runtime.inc rendered for the CPC by retrorecomp.z80_chain: a region map of four 16 KiB regions, the CPC's
 * costs in whole microseconds, the full 16-bit port, /INT read at the end of each instruction), the counted fallback on the
 * corrected reference interpreter, and the board of cpc_machine.c, through cpc_glue.inc. MIT, Retro-Recomp. A development
 * check (tools/cpc_native.py): it is compared field by field with cpc_reference_main.c, which takes the same options and
 * prints the same JSON; this one adds the native and fallback step counts. With --learn FILE it writes the code the interpreter
 * ran (the 4 bytes at each address, as the chain learns), translated with byte guards by the next generation. */
#define SMSRECOMP_BANKED_AOT 1
#include "cpc_glue.inc"

static uint8_t system_rom[0x8000], amsdos_rom[0x4000];
static uint8_t disk_bytes[2u << 20];
static uint32_t picture[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];
static unsigned long long frames_wanted = 50;
static int until_halt, was_halted;
static const char *picture_file, *audio_file;
static FILE *audio;
static unsigned watch[16], watches;

static uint32_t fnv(const uint8_t *data, size_t size)
{
    uint32_t h = 2166136261u;
    for (size_t i = 0; i < size; ++i) { h ^= data[i]; h *= 16777619u; }
    return h;
}

static size_t load(const char *path, uint8_t *into, size_t room)
{
    FILE *f = fopen(path, "rb");
    if (!f) { fprintf(stderr, "cannot read %s\n", path); exit(2); }
    size_t n = fread(into, 1, room, f);
    fclose(f);
    return n;
}

static void finish(void)
{
    if (learn_out) {                             /* --learn: the code the interpreter ran, for the next generation */
        FILE *f = fopen(learn_out, "w");
        for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
        if (f) fclose(f);
    }
    if (audio) fclose(audio);
    if (picture_file) {
        FILE *f = fopen(picture_file, "wb");
        if (f) { fwrite(picture, sizeof picture, 1, f); fclose(f); }
    }
    printf("{\"frames\": %llu, \"cycles\": %llu, \"native_steps\": %llu, \"fallback_steps\": %llu, \"interrupts\": %llu, "
           "\"pc\": %u, \"sp\": %u, \"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, \"iff1\": %d, "
           "\"im\": %d, \"halted\": %d, \"ram_fnv\": %u, \"picture_fnv\": %u, \"mode\": %u, \"rom_config\": %u, "
           "\"ram_config\": %u, \"upper_rom\": %u, \"ay\": [", (unsigned long long)machine.frames,
           (unsigned long long)machine.cycles, (unsigned long long)banked_native_steps,
           (unsigned long long)banked_fallback_steps, (unsigned long long)g_irq_taken, g_z80.pc, g_z80.sp,
           (unsigned)(g_z80.a << 8 | g_z80.f), (unsigned)(g_z80.b << 8 | g_z80.c), (unsigned)(g_z80.d << 8 | g_z80.e),
           (unsigned)(g_z80.h << 8 | g_z80.l), g_z80.ix, g_z80.iy, g_z80.iff1, g_z80.im, g_z80.halted,
           fnv(machine.ram, sizeof machine.ram), fnv((const uint8_t *)picture, sizeof picture), machine.ga.mode,
           machine.ga.rom_config, machine.ga.ram_config, machine.upper_rom);
    for (int r = 0; r < 16; ++r) printf("%s%u", r ? ", " : "", machine.ay_reg[r]);
    printf("], \"fdc_commands\": %u, \"disk_written\": %d, \"watch\": {", machine.fdc.commands, machine.fdc.drive[0].written);
    for (unsigned w = 0; w < watches; ++w)
        printf("%s\"%04X\": %u", w ? ", " : "", watch[w], cpc_read(&machine, (uint16_t)watch[w]));
    printf("}}\n");
    fflush(stdout);
    exit(0);
}

/* At each instruction boundary (the instruction and the interrupt it may accept complete): the frame's sound, the stop. */
static void cpc_main_service(void)
{
    if (machine.frame_ready) {
        static int16_t samples[CPC_AUDIO_BUFFER * 2];
        machine.frame_ready = 0;
        uint32_t n = cpc_audio_take(&machine, samples, CPC_AUDIO_BUFFER);
        if (audio) fwrite(samples, sizeof *samples * 2, n, audio);
    }
    if ((until_halt && g_z80.halted && !was_halted) || machine.frames >= frames_wanted)
        finish();
    was_halted = g_z80.halted;
}

int main(int argc, char **argv)
{
    const char *system_file = NULL, *amsdos_file = NULL, *disk_file = NULL;
    int crtc = CPC_CRTC_TYPE1;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : "";
        if (!strcmp(a, "--system")) { system_file = v; ++i; }
        else if (!strcmp(a, "--amsdos")) { amsdos_file = v; ++i; }
        else if (!strcmp(a, "--disk")) { disk_file = v; ++i; }
        else if (!strcmp(a, "--frames")) { frames_wanted = strtoull(v, NULL, 10); ++i; }
        else if (!strcmp(a, "--until-halt")) until_halt = 1;
        else if (!strcmp(a, "--picture")) { picture_file = v; ++i; }
        else if (!strcmp(a, "--audio")) { audio_file = v; ++i; }
        else if (!strcmp(a, "--crtc")) { crtc = atoi(v); ++i; }
        else if (!strcmp(a, "--watch") && watches < 16) { watch[watches++] = (unsigned)strtoul(v, NULL, 16); ++i; }
        else if (!strcmp(a, "--learn")) { learn_out = v; ++i; }
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!system_file || load(system_file, system_rom, sizeof system_rom) != sizeof system_rom) {
        fprintf(stderr, "--system: a 32 KiB system ROM (OS then BASIC)\n");
        return 2;
    }
    machine.os = system_rom;
    machine.basic = system_rom + 0x4000;
    machine.amsdos = amsdos_file && load(amsdos_file, amsdos_rom, sizeof amsdos_rom) == sizeof amsdos_rom ? amsdos_rom : NULL;
    machine.picture = picture;
    cpc_reset(&machine, (uint8_t)crtc);
    if (disk_file) {
        size_t n = load(disk_file, disk_bytes, sizeof disk_bytes);
        if (cpc_insert_disk(&machine, 0, disk_bytes, (uint32_t)n, 0) != DSK_OK) { fprintf(stderr, "--disk: not a DSK image\n"); return 2; }
    }
    audio = audio_file ? fopen(audio_file, "wb") : NULL;
    smsrecomp_banked_run();                      /* returns through finish() */
    return 0;
}
