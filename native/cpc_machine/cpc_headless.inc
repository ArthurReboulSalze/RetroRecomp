/* The headless run of the Amstrad CPC on the banked Z80 chain, shared by the native check (cpc_native_main.c) and the game's
 * --headless mode (cpc_player.c), included after cpc_glue.inc. MIT, Retro-Recomp.
 *
 * Options (headless_option): --frames N, --until-halt, --picture FILE (the last frame, 768 x 272 x 0x00RRGGBB little endian),
 * --audio FILE (44,100 Hz 16-bit stereo), --watch ADDR (hexadecimal, up to 16), --learn FILE (the code the interpreter ran,
 * for the next generation), --report FILE (the JSON line in FILE instead of the standard output: a game linked for the Windows
 * subsystem has none to rely on). The run stops at the frame limit, or after the first instruction that halts the CPU with
 * --until-halt, once an instruction and the interrupt it may accept are complete, and prints one JSON line: the fields of
 * tools/cpc_reference.py's runner, plus the native and fallback step counts. */

static uint32_t headless_picture[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];
static unsigned long long headless_frames_wanted = 50;
static int headless_until_halt, headless_was_halted;
static const char *headless_picture_file, *headless_audio_file, *headless_report_file;
static FILE *headless_audio;
static unsigned headless_watch[16], headless_watches;

static uint32_t headless_fnv(const uint8_t *data, size_t size)
{
    uint32_t h = 2166136261u;
    for (size_t i = 0; i < size; ++i) { h ^= data[i]; h *= 16777619u; }
    return h;
}

/* 1: the option (and its value, `*i` moved past it) was taken; 0: not a headless option. */
static int headless_option(int argc, char **argv, int *i)
{
    const char *a = argv[*i], *v = *i + 1 < argc ? argv[*i + 1] : "";
    if (!strcmp(a, "--frames")) { headless_frames_wanted = strtoull(v, NULL, 10); ++*i; }
    else if (!strcmp(a, "--until-halt")) headless_until_halt = 1;
    else if (!strcmp(a, "--picture")) { headless_picture_file = v; ++*i; }
    else if (!strcmp(a, "--audio")) { headless_audio_file = v; ++*i; }
    else if (!strcmp(a, "--watch") && headless_watches < 16) { headless_watch[headless_watches++] = (unsigned)strtoul(v, NULL, 16); ++*i; }
    else if (!strcmp(a, "--learn")) { learn_out = v; ++*i; }
    else if (!strcmp(a, "--report")) { headless_report_file = v; ++*i; }
    else return 0;
    return 1;
}

/* The board draws into the headless picture; the sound file opens. */
static void headless_start(void)
{
    machine.picture = headless_picture;
    headless_audio = headless_audio_file ? fopen(headless_audio_file, "wb") : NULL;
}

static void headless_finish(void)
{
    if (learn_out) {                             /* --learn: the code the interpreter ran, for the next generation */
        FILE *f = fopen(learn_out, "w");
        for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
        if (f) fclose(f);
    }
    if (headless_audio) fclose(headless_audio);
    if (headless_picture_file) {
        FILE *f = fopen(headless_picture_file, "wb");
        if (f) { fwrite(headless_picture, sizeof headless_picture, 1, f); fclose(f); }
    }
    FILE *out = headless_report_file ? fopen(headless_report_file, "w") : stdout;
    if (!out) exit(3);
    fprintf(out, "{\"frames\": %llu, \"cycles\": %llu, \"native_steps\": %llu, \"fallback_steps\": %llu, \"interrupts\": %llu, "
           "\"pc\": %u, \"sp\": %u, \"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, \"iff1\": %d, "
           "\"im\": %d, \"halted\": %d, \"ram_fnv\": %u, \"picture_fnv\": %u, \"mode\": %u, \"rom_config\": %u, "
           "\"ram_config\": %u, \"upper_rom\": %u, \"ay\": [", (unsigned long long)machine.frames,
           (unsigned long long)machine.cycles, (unsigned long long)banked_native_steps,
           (unsigned long long)banked_fallback_steps, (unsigned long long)g_irq_taken, g_z80.pc, g_z80.sp,
           (unsigned)(g_z80.a << 8 | g_z80.f), (unsigned)(g_z80.b << 8 | g_z80.c), (unsigned)(g_z80.d << 8 | g_z80.e),
           (unsigned)(g_z80.h << 8 | g_z80.l), g_z80.ix, g_z80.iy, g_z80.iff1, g_z80.im, g_z80.halted,
           headless_fnv(machine.ram, sizeof machine.ram), headless_fnv((const uint8_t *)headless_picture, sizeof headless_picture),
           machine.ga.mode, machine.ga.rom_config, machine.ga.ram_config, machine.upper_rom);
    for (int r = 0; r < 16; ++r) fprintf(out, "%s%u", r ? ", " : "", machine.ay_reg[r]);
    fprintf(out, "], \"fdc_commands\": %u, \"disk_written\": %d, \"watch\": {", machine.fdc.commands, machine.fdc.drive[0].written);
    for (unsigned w = 0; w < headless_watches; ++w)
        fprintf(out, "%s\"%04X\": %u", w ? ", " : "", headless_watch[w], cpc_read(&machine, (uint16_t)headless_watch[w]));
    fprintf(out, "}}\n");
    if (out == stdout) fflush(out);
    else if (fclose(out)) exit(3);
    exit(0);
}

/* At each instruction boundary (the instruction and the interrupt it may accept complete): the frame's sound, the stop. */
static void headless_service(void)
{
    if (machine.frame_ready) {
        static int16_t samples[CPC_AUDIO_BUFFER * 2];
        machine.frame_ready = 0;
        uint32_t n = cpc_audio_take(&machine, samples, CPC_AUDIO_BUFFER);
        if (headless_audio) fwrite(samples, sizeof *samples * 2, n, headless_audio);
    }
    if ((headless_until_halt && g_z80.halted && !headless_was_halted) || machine.frames >= headless_frames_wanted)
        headless_finish();
    headless_was_halted = g_z80.halted;
}
