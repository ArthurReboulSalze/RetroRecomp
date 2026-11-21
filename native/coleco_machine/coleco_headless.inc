/* The headless run of the ColecoVision, shared by the three programs that run the machine without a window: the reference runner
 * (coleco_reference_main.c), the native check (coleco_native_main.c) and the game's headless mode (coleco_player.c). MIT,
 * Retro-Recomp. Included once; the includer has `machine` (an CvMachine) in scope.
 *
 * It holds the route (the pad events, the sound taken from the machine, one row per frame), the options that make a run and the
 * report, a JSON object whose fields the conversion compares (retrorecomp/coleco_build.py, COMPARED) between the native run and the
 * reference run, so both print it the same way.
 *
 * Events: `--script FILE` with one event per line, `FRAME pad PORT HEX` (the buttons held on controller PORT 0 or 1, CV_PAD_* bits: the pad word of the
 * host kit, the keypad's lines included), frames not decreasing, or `--event FRAME:pad:PORT:HEX`. An event applies at the first line hook at
 * which the frame counter has reached its frame, so at the same instant on both CPUs (the frame wraps at a line boundary, between two
 * instructions).
 *
 * Rows (`--rows FILE`, text, LF): `frame,cpu,ram,picture,sound,samples,audible,pc`, written at the service point (the first instruction
 * boundary after the frame counter rose): the CPU registers' hash, the RAM, the picture, the frame's sound (cut at the frame's boundary),
 * their count, whether they hold two different values (the chip has no DC removal: silence is a constant) and the PC. */

typedef struct { unsigned long frame; int kind, a, b; } CvRouteEvent;           /* kind: 0 pad */

static CvRouteEvent *route_events;
static size_t route_event_count, route_event_cap, route_next_event;
static FILE *route_audio_file, *route_trace_file;
static uint32_t route_audio_hash = 2166136261u;
static uint64_t route_samples;
static uint32_t route_frame_hash = 2166136261u;
static uint64_t route_frame_samples;
static int route_frame_min = 32767, route_frame_max = -32768;
static int route_frame_due;
static uint32_t route_due_sound;
static uint64_t route_due_samples;
static int route_due_audible;

static unsigned long frames_wanted = 120;
static const char *frame_out, *vram_out, *ram_out, *report_out;
static unsigned watch[32];
static int watches;

static int route_add_event(CvRouteEvent e)
{
    if (route_event_count == route_event_cap) {
        size_t cap = route_event_cap ? route_event_cap * 2 : 64;
        CvRouteEvent *grown = (CvRouteEvent *)realloc(route_events, cap * sizeof *grown);
        if (!grown) return 0;
        route_events = grown;
        route_event_cap = cap;
    }
    if (route_event_count && e.frame < route_events[route_event_count - 1].frame) return 0;   /* frames not decreasing */
    route_events[route_event_count++] = e;
    return 1;
}

static int route_event_text(const char *v, int spaced)
{
    CvRouteEvent e;
    unsigned long f; unsigned port, bits;
    if (spaced ? sscanf(v, "%lu pad %u %x", &f, &port, &bits) == 3 : sscanf(v, "%lu:pad:%u:%x", &f, &port, &bits) == 3)
        e = (CvRouteEvent){ f, 0, (int)port, (int)bits };
    else
        return 0;
    return route_add_event(e);
}

/* The common options; returns 1 when `a` (with `v`) is one, -1 when its value is wrong, 0 when it is not. */
static int headless_option(const char *a, const char *v)
{
    if (!strcmp(a, "--frames")) frames_wanted = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--frame")) frame_out = v;
    else if (!strcmp(a, "--vram")) vram_out = v;
    else if (!strcmp(a, "--ram")) ram_out = v;
    else if (!strcmp(a, "--report")) report_out = v;
    else if (!strcmp(a, "--watch")) { if (watches < 32) watch[watches++] = (unsigned)strtoul(v, NULL, 16) & 0xFFFF; }
    else if (!strcmp(a, "--event")) return route_event_text(v, 0) ? 1 : -1;
    else if (!strcmp(a, "--audio")) { route_audio_file = fopen(v, "wb"); return route_audio_file ? 1 : -1; }
    else if (!strcmp(a, "--rows")) {
        route_trace_file = fopen(v, "wb");
        if (!route_trace_file) return -1;
        fputs("frame,cpu,ram,picture,sound,samples,audible,pc\n", route_trace_file);
    } else if (!strcmp(a, "--script")) {
        FILE *f = fopen(v, "rb");
        char line[128];
        if (!f) return -1;
        while (fgets(line, sizeof line, f))
            if (line[0] != '\n' && line[0] != '#' && !route_event_text(line, 1)) { fclose(f); return -1; }
        fclose(f);
    } else return 0;
    return 1;
}

static uint32_t route_fnv(uint32_t h, const void *data, size_t size)
{
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * 16777619u;
    return h;
}

/* The samples the machine has made so far, into the stream's hash (and file) and into the current frame's block. */
static void route_take_audio(void)
{
    static int16_t chunk[CV_AUDIO_BUFFER];
    unsigned n = cv_audio_take(&machine, chunk, CV_AUDIO_BUFFER);
    route_audio_hash = route_fnv(route_audio_hash, chunk, n * sizeof *chunk);
    route_samples += n;
    if (route_audio_file) fwrite(chunk, sizeof *chunk, n, route_audio_file);
    route_frame_hash = route_fnv(route_frame_hash, chunk, n * sizeof *chunk);
    route_frame_samples += n;
    for (unsigned i = 0; i < n; ++i) {
        if (chunk[i] < route_frame_min) route_frame_min = chunk[i];
        if (chunk[i] > route_frame_max) route_frame_max = chunk[i];
    }
}

/* The events whose frame the frame counter has reached, in order (a loaded state calls it at once: the pads are host input, not part
 * of a state, and the script sets them again). */
static void cv_route_events(void)
{
    for (; route_next_event < route_event_count && route_events[route_next_event].frame <= machine.frames; ++route_next_event) {
        const CvRouteEvent *e = &route_events[route_next_event];
        if (e->a == 0 || e->a == 1) machine.pad[e->a] = (uint16_t)(e->b & CV_PAD_MASK);
    }
}

/* The machine's line hook: due events; at the frame's boundary, the frame's sound cut there and its row made due. */
static void cv_route_line(void)
{
    cv_route_events();
    if (machine.line == 0 && machine.frames) {
        sn76489_run(&machine.psg, machine.next_line - CV_CYCLES_PER_LINE);
        route_take_audio();
        route_due_sound = route_frame_hash;
        route_due_samples = route_frame_samples;
        route_due_audible = route_frame_samples && route_frame_min != route_frame_max;
        route_frame_hash = 2166136261u;
        route_frame_samples = 0;
        route_frame_min = 32767;
        route_frame_max = -32768;
        route_frame_due = 1;
    } else if (machine.psg.box.count >= CV_AUDIO_BUFFER / 2) {
        route_take_audio();
    }
}

/* The CPU's registers as the rows hash them, in one order for both CPUs: AF BC DE HL IX IY SP PC, AF' BC' DE' HL', IR,
 * IM|IFF1|IFF2|halted, WZ, 0. */
typedef struct {
    uint16_t af, bc, de, hl, ix, iy, sp, pc, af2, bc2, de2, hl2, ir, flags, wz;
    int iff1, iff2, halted, im;
    unsigned i, r;
} CvCpuView;

static uint32_t cv_route_cpu_hash(const CvCpuView *c)
{
    const uint16_t regs[16] = { c->af, c->bc, c->de, c->hl, c->ix, c->iy, c->sp, c->pc, c->af2, c->bc2, c->de2, c->hl2, c->ir, c->flags, c->wz, 0 };
    return route_fnv(2166136261u, regs, sizeof regs);
}

/* At the service point: the due row. */
static void cv_route_row(const CvCpuView *c)
{
    if (!route_frame_due)
        return;
    route_frame_due = 0;
    if (route_trace_file)
        fprintf(route_trace_file, "%llu,%08x,%08x,%08x,%08x,%llu,%d,%04x\n", (unsigned long long)machine.frames, cv_route_cpu_hash(c),
                cv_ram_hash(&machine), cv_frame_hash(&machine), route_due_sound, (unsigned long long)route_due_samples, route_due_audible, c->pc);
}

/* The end of the run: the remaining sound into the stream, the files closed. */
static void cv_route_finish(void)
{
    route_take_audio();
    if (route_audio_file) { fclose(route_audio_file); route_audio_file = NULL; }
    if (route_trace_file) { fclose(route_trace_file); route_trace_file = NULL; }
}

/* The report: the JSON the conversion compares. `extra` writes the members only one engine has (the native step counts), between the
 * common ones and the watched bytes. */
static void headless_report(const char *engine, const CvCpuView *c, uint64_t interrupts, void (*extra)(FILE *))
{
    cv_route_finish();
    if (frame_out) {
        FILE *f = fopen(frame_out, "wb");
        if (f) { cv_dump_frame(&machine, f); fclose(f); }
    }
    if (vram_out) {
        FILE *f = fopen(vram_out, "wb");
        if (f) { fwrite(machine.vdp.vram, 1, sizeof machine.vdp.vram, f); fclose(f); }
    }
    if (ram_out) {
        FILE *f = fopen(ram_out, "wb");
        if (f) { fwrite(machine.ram, 1, sizeof machine.ram, f); fclose(f); }
    }
    FILE *out = report_out ? fopen(report_out, "w") : stdout;
    if (!out) exit(3);
    fprintf(out, "{\"engine\": \"%s\", \"frames\": %llu, \"cycles\": %llu, \"interrupts\": %llu, \"pc\": %u, \"sp\": %u, \"af\": %u, \"bc\": %u, "
            "\"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, \"iff1\": %d, \"halted\": %d, \"af2\": %u, \"bc2\": %u, \"de2\": %u, \"hl2\": %u, "
            "\"i\": %u, \"r\": %u, \"im\": %d, \"iff2\": %d, \"wz\": %u, "
            "\"vdp_regs\": [%u, %u, %u, %u, %u, %u, %u, %u], \"vdp_status\": %u, \"vram_fnv\": %u, \"ram_fnv\": %u, \"frame_fnv\": %u, "
            "\"audio_samples\": %llu, \"audio_fnv\": %u, ",
            engine, (unsigned long long)machine.frames, (unsigned long long)machine.cycles, (unsigned long long)interrupts, c->pc, c->sp, c->af,
            c->bc, c->de, c->hl, c->ix, c->iy, c->iff1, c->halted, c->af2, c->bc2, c->de2, c->hl2, c->i, c->r, c->im, c->iff2, c->wz,
            machine.vdp.reg[0], machine.vdp.reg[1], machine.vdp.reg[2], machine.vdp.reg[3], machine.vdp.reg[4], machine.vdp.reg[5],
            machine.vdp.reg[6], machine.vdp.reg[7], machine.vdp.status, cv_vram_hash(&machine), cv_ram_hash(&machine), cv_frame_hash(&machine),
            (unsigned long long)route_samples, route_audio_hash);
    cv_print_state(&machine, out);
    if (extra) extra(out);
    fprintf(out, "\"watch\": {");
    for (int i = 0; i < watches; ++i)
        fprintf(out, "%s\"%04X\": %u", i ? ", " : "", watch[i], cv_peek(&machine, (uint16_t)watch[i]));
    fprintf(out, "}}\n");
    fflush(out);
    if (out != stdout) fclose(out);
}

#ifdef CV_HEADLESS_NATIVE
/* The native side, for the programs that run the translated bodies (the check, coleco_native_main.c, and the game's headless mode,
 * coleco_player.c): they define CV_HEADLESS_NATIVE and have g_z80 and the glue's counters in scope; the reference runner does not. */

static CvCpuView native_cpu(void)
{
    CvCpuView c;
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
    CvCpuView c = native_cpu();
    headless_report("native", &c, g_irq_taken, native_extra);
    exit(0);
}
#endif
