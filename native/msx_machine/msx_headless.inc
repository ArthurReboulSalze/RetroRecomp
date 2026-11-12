/* The headless run on the MSX glue (msx_glue.inc): the frame limit, the route (msx_route.inc), the report. MIT,
 * Retro-Recomp. Included by the native check (msx_native_main.c) and by the game (msx_player.c, `--headless`), so the
 * delivered file replays a route exactly as the check does and prints the same report.
 *
 * Options (headless_option): --frames N --frame FILE --vram FILE --watch ADDR --report FILE --trace-cycles A:B and the
 * route's (--event, --script, --rows, --audio). The report is the JSON the conversion compares (msx_build.COMPARED); it
 * goes to --report FILE, or to the standard output when none is given (the game is linked for the Windows subsystem, so
 * its standard output is not relied on). */

static unsigned long frames_wanted = 120;
static const char *frame_out, *vram_out, *report_out;
static unsigned watch[32];
static int watches;
static unsigned long long trace_from, trace_to;   /* tools: the instructions that start in a window of machine cycles */

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

/* The common options; returns 1 when `a` (with `v`) is one, -1 when its value is wrong, 0 when it is not. */
static int headless_option(const char *a, const char *v)
{
    if (!strcmp(a, "--frames")) frames_wanted = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--frame")) frame_out = v;
    else if (!strcmp(a, "--vram")) vram_out = v;
    else if (!strcmp(a, "--report")) report_out = v;
    else if (!strcmp(a, "--trace-cycles")) sscanf(v, "%llu:%llu", &trace_from, &trace_to);
    else if (!strcmp(a, "--watch")) { if (watches < 32) watch[watches++] = (unsigned)strtoul(v, NULL, 16) & 0xFFFF; }
    else return msx_route_option(a, v);
    return 1;
}

/* The end of the run: the dumps and the report, then the process ends. */
static void headless_finish(void)
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
    FILE *out = report_out ? fopen(report_out, "w") : stdout;
    if (!out) exit(3);
    fprintf(out, "{\"engine\": \"native\", \"frames\": %llu, \"cycles\": %llu, \"interrupts\": %llu, "
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
        fprintf(out, "%s\"%04X\": %llu", i ? ", " : "", fallback_at[i], (unsigned long long)fallback_count[i]);
    fprintf(out, "}, \"af2\": %u, \"bc2\": %u, \"de2\": %u, \"hl2\": %u, \"i\": %u, \"r\": %u, \"im\": %u, \"iff2\": %d, \"wz\": %u, ",
           (unsigned)(g_z80.a_ << 8 | g_z80.f_), (unsigned)(g_z80.b_ << 8 | g_z80.c_), (unsigned)(g_z80.d_ << 8 | g_z80.e_),
           (unsigned)(g_z80.h_ << 8 | g_z80.l_), g_z80.i, g_z80.r, g_z80.im, g_z80.iff2, g_z80.wz);
    msx_print_state(&machine, out);
    fprintf(out, "\"watch\": {");
    for (int i = 0; i < watches; ++i)
        fprintf(out, "%s\"%04X\": %u", i ? ", " : "", watch[i], msx_peek(&machine, (uint16_t)watch[i]));
    fprintf(out, "}}\n");
    fflush(out);
    if (out != stdout) fclose(out);
    exit(0);
}

/* At each instruction boundary the includer calls this when a frame may have ended (the native check: always; the game:
 * after its frame flag): the due row, the instruction trace, the frame limit. */
static void headless_service(void)
{
    if (route_frame_due)
        msx_route_row(native_cpu_hash(), g_z80.pc);
    if (trace_to && g_z80.cyc >= trace_from && g_z80.cyc < trace_to)
        fprintf(stderr, "T %llu %04X\n", (unsigned long long)g_z80.cyc, g_z80.pc);
    if (machine.frames >= frames_wanted)
        headless_finish();
}
