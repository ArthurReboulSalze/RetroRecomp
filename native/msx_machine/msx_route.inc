/* An MSX route for the headless programs (the reference runner, the native check, the game's headless mode): the input
 * events of the route, the sound taken from the machine, and one row per frame. MIT, Retro-Recomp. Included once; the
 * includer has `machine` (an MsxMachine) in scope.
 *
 * Events: `--event FRAME:key:ROW:BIT:DOWN` or `FRAME:joy:PORT:HEX` (tools), or `--script FILE` with one event per line,
 * `FRAME key ROW BIT DOWN` or `FRAME joy PORT HEX` (routes, msx_routes.py), frames not decreasing. An event applies at the
 * first line hook at which the frame counter has reached its frame, so at the same instant on both CPUs (the frame wraps at
 * a line boundary, between two instructions).
 *
 * Rows (`--rows FILE`, text, LF): `frame,cpu,ram,picture,sound,samples,audible,pc`, written at the service point (the
 * first instruction boundary after the frame counter rose, where the native loop stops and the reference tests its frame
 * count): the CPU registers' hash, the RAM, the picture, the frame's sound (the samples up to the frame's boundary, cut
 * there exactly: msx_psg_catch_up_to; the sound stream itself does not depend on when it is taken), their count, whether
 * they hold two different values (the AY output has no DC removal: silence is a constant, not zero), and the PC. */

typedef struct { unsigned long frame; int joy, a, b, c; } MsxRouteEvent;

static MsxRouteEvent *route_events;
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

static int route_add_event(MsxRouteEvent e)
{
    if (route_event_count == route_event_cap) {
        size_t cap = route_event_cap ? route_event_cap * 2 : 64;
        MsxRouteEvent *grown = (MsxRouteEvent *)realloc(route_events, cap * sizeof *grown);
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
    MsxRouteEvent e;
    unsigned long f; int r, b, d; unsigned port, bits;
    if (spaced ? sscanf(v, "%lu key %d %d %d", &f, &r, &b, &d) == 4 : sscanf(v, "%lu:key:%d:%d:%d", &f, &r, &b, &d) == 4)
        e = (MsxRouteEvent){ f, 0, r, b, d };
    else if (spaced ? sscanf(v, "%lu joy %u %x", &f, &port, &bits) == 3 : sscanf(v, "%lu:joy:%u:%x", &f, &port, &bits) == 3)
        e = (MsxRouteEvent){ f, 1, (int)port, (int)bits, 0 };
    else
        return 0;
    return route_add_event(e);
}

/* The route's options; returns 1 when `a` (with its value `v`) is one of them, -1 when its value is wrong. */
static int msx_route_option(const char *a, const char *v)
{
    if (!strcmp(a, "--event")) return route_event_text(v, 0) ? 1 : -1;
    if (!strcmp(a, "--audio")) { route_audio_file = fopen(v, "wb"); return route_audio_file ? 1 : -1; }
    if (!strcmp(a, "--rows")) {
        route_trace_file = fopen(v, "wb");
        if (!route_trace_file) return -1;
        fputs("frame,cpu,ram,picture,sound,samples,audible,pc\n", route_trace_file);
        return 1;
    }
    if (!strcmp(a, "--script")) {
        FILE *f = fopen(v, "rb");
        char line[128];
        if (!f) return -1;
        while (fgets(line, sizeof line, f))
            if (line[0] != '\n' && line[0] != '#' && !route_event_text(line, 1)) { fclose(f); return -1; }
        fclose(f);
        return 1;
    }
    return 0;
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
    static int16_t chunk[MSX_AUDIO_BUFFER];
    unsigned n = msx_audio_take(&machine, chunk, MSX_AUDIO_BUFFER);
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

/* The machine's line hook: due events; at the frame's boundary, the frame's sound cut there and its row made due. */
static void msx_route_line(void)
{
    for (; route_next_event < route_event_count && route_events[route_next_event].frame <= machine.frames; ++route_next_event) {
        const MsxRouteEvent *e = &route_events[route_next_event];
        if (e->joy) msx_joystick(&machine, e->a, (uint8_t)e->b);
        else msx_key(&machine, e->a, e->b, e->c);
    }
    if (machine.line == 0 && machine.frames) {
        msx_psg_catch_up_to(&machine, machine.next_line - MSX_CYCLES_PER_LINE);
        route_take_audio();
        route_due_sound = route_frame_hash;
        route_due_samples = route_frame_samples;
        route_due_audible = route_frame_samples && route_frame_min != route_frame_max;
        route_frame_hash = 2166136261u;
        route_frame_samples = 0;
        route_frame_min = 32767;
        route_frame_max = -32768;
        route_frame_due = 1;
    } else if (machine.synth.out_count >= MSX_AUDIO_BUFFER / 2) {
        route_take_audio();
    }
}

/* The CPU's registers as the rows hash them, in one order for both CPUs. */
static uint32_t msx_route_cpu_hash(const uint16_t regs[16])
{
    return route_fnv(2166136261u, regs, 16 * sizeof regs[0]);
}

/* At the service point: the due row, with the CPU's hash and PC given by the includer. */
static void msx_route_row(uint32_t cpu, uint16_t pc)
{
    if (!route_frame_due)
        return;
    route_frame_due = 0;
    if (route_trace_file)
        fprintf(route_trace_file, "%llu,%08x,%08x,%08x,%08x,%llu,%d,%04x\n", (unsigned long long)machine.frames, cpu,
                msx_ram_hash(&machine, ram), msx_frame_hash(&machine), route_due_sound,
                (unsigned long long)route_due_samples, route_due_audible, pc);
}

/* The end of the run: the remaining sound into the stream, the files closed. */
static void msx_route_finish(void)
{
    route_take_audio();
    if (route_audio_file) { fclose(route_audio_file); route_audio_file = NULL; }
    if (route_trace_file) { fclose(route_trace_file); route_trace_file = NULL; }
}
