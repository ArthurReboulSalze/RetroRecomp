/* The ZX Spectrum's headless run: a route's input events, one row per frame, the sound, the report. MIT, Retro-Recomp.
 * Included once by the reference runner (zxs_reference_main.c), the native check (zxs_native_main.c) and the game's headless mode,
 * so that all of them replay a route and report it the same way. The includer has `machine` (a ZxsMachine) in scope and defines,
 * before the include:
 *   - `static void headless_registers(uint16_t regs[16])`: AF BC DE HL IX IY SP PC, AF' BC' DE' HL', IR, IM|IFF1<<2|IFF2<<3|halted<<4,
 *     WZ, 0 (the order of the rows' CPU hash and of the report);
 *   - `static uint64_t headless_interrupts(void)`: the interrupts accepted so far;
 *   - `HEADLESS_ENGINE`, "reference" or "native", and optionally `HEADLESS_EXTRA(out)`, more members of the report (each followed
 *     by ", ").
 *
 * Options (headless_option): --frames N, --event FRAME:key:ROW:BIT:DOWN or FRAME:kempston:HEX, --script FILE (one event a line,
 * `FRAME key ROW BIT DOWN` or `FRAME kempston HEX`, frames not decreasing), --rows FILE, --frame FILE, --audio FILE, --report FILE.
 * An event applies at the start of its frame, from the machine's frame hook, so at the same instant on both CPUs (a frame begins
 * at a line boundary, between two instructions).
 *
 * Rows (`--rows FILE`, text, LF): `frame,cpu,ram,picture,sound,samples,audible,pc`, written at the service point (the first
 * instruction boundary after the frame counter rose): the registers' hash, the RAM's, the picture's, the frame's sound and its
 * sample count, whether it holds two different values, and the PC. The report is the JSON the conversion compares
 * (retrorecomp/zxs_build.COMPARED); it goes to --report FILE, or to the standard output. */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { unsigned long frame; int kempston; unsigned row, bit, down, value; } ZxsRouteEvent;
static ZxsRouteEvent *route_events;
static size_t route_event_count, route_event_cap, route_next_event;
static unsigned long frames_wanted = 120;
static const char *frame_out, *report_out, *audio_out, *rows_out;
static FILE *route_audio_file, *route_rows_file;
static uint32_t route_audio_hash = 2166136261u;
static uint64_t route_samples;
static uint32_t route_frame_sound = 2166136261u;
static uint64_t route_frame_samples;
static int route_frame_min = 32767, route_frame_max = -32768;
static uint64_t route_rows_done;
/* The sound of the frame that ended, closed by the machine's frame hook at the frame's boundary exactly (the samples up to that
 * cycle), so that each row holds the same samples whatever instruction the service point falls after. */
static uint32_t closed_sound = 2166136261u;
static uint64_t closed_samples;
static int closed_audible;

static uint32_t zxs_fnv(uint32_t h, const void *data, size_t size)
{
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * 16777619u;
    return h;
}

static uint32_t zxs_ram_hash(void) { return zxs_fnv(2166136261u, machine.ram, sizeof machine.ram); }
static uint32_t zxs_picture_hash(void) { return zxs_fnv(2166136261u, machine.picture, sizeof machine.picture); }

static uint32_t zxs_cpu_hash(void)
{
    uint16_t regs[16];
    headless_registers(regs);
    return zxs_fnv(2166136261u, regs, sizeof regs);
}

static int route_add(unsigned long frame, int kempston, unsigned row, unsigned bit, unsigned down, unsigned value)
{
    if (route_event_count && route_events[route_event_count - 1].frame > frame)
        return -1;                                           /* frames do not decrease */
    if (!kempston && (row > 7 || bit > 4 || down > 1))
        return -1;
    if (route_event_count == route_event_cap) {
        route_event_cap = route_event_cap ? route_event_cap * 2 : 64;
        route_events = (ZxsRouteEvent *)realloc(route_events, route_event_cap * sizeof *route_events);
        if (!route_events) exit(3);
    }
    route_events[route_event_count++] = (ZxsRouteEvent){ frame, kempston, row, bit, down, value };
    return 1;
}

static int route_event_text(const char *text)
{
    unsigned long frame; unsigned row, bit, down, value; char kind[16];
    if (sscanf(text, "%lu:%15[a-z]:%u:%u:%u", &frame, kind, &row, &bit, &down) == 5 && !strcmp(kind, "key"))
        return route_add(frame, 0, row, bit, down, 0);
    if (sscanf(text, "%lu:%15[a-z]:%x", &frame, kind, &value) == 3 && !strcmp(kind, "kempston"))
        return route_add(frame, 1, 0, 0, 0, value & 0x1F);
    return -1;
}

static int route_script(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    char line[128];
    int result = 1;
    while (result > 0 && fgets(line, sizeof line, f)) {
        unsigned long frame; unsigned row, bit, down, value; char kind[16];
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
        if (sscanf(line, "%lu %15s %u %u %u", &frame, kind, &row, &bit, &down) == 5 && !strcmp(kind, "key"))
            result = route_add(frame, 0, row, bit, down, 0);
        else if (sscanf(line, "%lu %15s %x", &frame, kind, &value) == 3 && !strcmp(kind, "kempston"))
            result = route_add(frame, 1, 0, 0, 0, value & 0x1F);
        else
            result = -1;
    }
    fclose(f);
    return result;
}

static void route_take_sound(void);

/* The machine's frame hook: the sound of the frame that ended is closed, then the events of the frame that begins apply. */
static void route_frame_start(void *user)
{
    if (user) {                                              /* NULL: the first frame, nothing ended */
        route_take_sound();
        closed_sound = route_frame_sound; closed_samples = route_frame_samples; closed_audible = route_frame_min != route_frame_max;
        route_frame_sound = 2166136261u; route_frame_samples = 0; route_frame_min = 32767; route_frame_max = -32768;
    }
    while (route_next_event < route_event_count && route_events[route_next_event].frame <= machine.frames) {
        const ZxsRouteEvent *e = &route_events[route_next_event++];
        if (e->kempston)
            machine.kempston = (uint8_t)e->value;
        else if (e->down)
            machine.keys[e->row] &= (uint8_t)~(1u << e->bit);
        else
            machine.keys[e->row] |= (uint8_t)(1u << e->bit);
    }
}

/* The sound produced so far, folded into the run's hash and the frame's. */
static void route_take_sound(void)
{
    int16_t samples[1024];
    unsigned n;
    while ((n = zxs_audio_take(&machine, samples, 1024)) != 0) {
        route_audio_hash = zxs_fnv(route_audio_hash, samples, n * sizeof samples[0]);
        route_frame_sound = zxs_fnv(route_frame_sound, samples, n * sizeof samples[0]);
        route_samples += n;
        route_frame_samples += n;
        for (unsigned i = 0; i < n; ++i) {
            if (samples[i] < route_frame_min) route_frame_min = samples[i];
            if (samples[i] > route_frame_max) route_frame_max = samples[i];
        }
        if (route_audio_file) fwrite(samples, sizeof samples[0], n, route_audio_file);
    }
}

static int headless_option(const char *a, const char *v)
{
    if (!strcmp(a, "--frames")) frames_wanted = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--event")) return route_event_text(v);
    else if (!strcmp(a, "--script")) return route_script(v);
    else if (!strcmp(a, "--rows")) rows_out = v;
    else if (!strcmp(a, "--frame")) frame_out = v;
    else if (!strcmp(a, "--audio")) audio_out = v;
    else if (!strcmp(a, "--report")) report_out = v;
    else return 0;
    return 1;
}

/* Once the options are read and the machine loaded. */
static void headless_start(void)
{
    machine.frame_hook = route_frame_start;
    machine.hook_user = &machine;
    machine.trace_frames = 1;
    if (audio_out && !(route_audio_file = fopen(audio_out, "wb"))) exit(3);
    if (rows_out) {
        if (!(route_rows_file = fopen(rows_out, "w"))) exit(3);
        fprintf(route_rows_file, "frame,cpu,ram,picture,sound,samples,audible,pc\n");
    }
    route_frame_start(NULL);                                 /* events of the first frame */
}

static void headless_report(void)
{
    route_take_sound();
    if (route_audio_file) fclose(route_audio_file);
    if (route_rows_file) fclose(route_rows_file);
    if (frame_out) {
        FILE *f = fopen(frame_out, "wb");
        if (f) { fwrite(machine.picture, 1, sizeof machine.picture, f); fclose(f); }
    }
    uint16_t r[16];
    headless_registers(r);
    FILE *out = report_out ? fopen(report_out, "w") : stdout;
    if (!out) exit(3);
    fprintf(out, "{\"engine\": \"%s\", \"model\": %d, \"frames\": %llu, \"cycles\": %llu, \"interrupts\": %llu, "
            "\"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, \"sp\": %u, \"pc\": %u, "
            "\"af2\": %u, \"bc2\": %u, \"de2\": %u, \"hl2\": %u, \"i\": %u, \"r\": %u, \"im\": %u, \"iff1\": %u, \"iff2\": %u, "
            "\"halted\": %u, \"wz\": %u, \"port_7ffd\": %u, \"border\": %u, \"out_fe\": %u, \"ay_latch\": %u, \"ay\": [",
            HEADLESS_ENGINE, machine.model, (unsigned long long)machine.frames, (unsigned long long)machine.cycles,
            (unsigned long long)headless_interrupts(), r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], r[11],
            r[12] >> 8, r[12] & 0xFF, r[13] & 3, (r[13] >> 2) & 1, (r[13] >> 3) & 1, (r[13] >> 4) & 1, r[14],
            machine.port_7ffd, machine.border, machine.out_fe, machine.ay_latch);
    for (int i = 0; i < 16; ++i) fprintf(out, "%s%u", i ? ", " : "", machine.ay_regs[i]);
    fprintf(out, "], \"ram_fnv\": %u, \"frame_fnv\": %u, \"frame_trace\": %u, \"audio_samples\": %llu, \"audio_fnv\": %u, "
            "\"dropped_samples\": %llu, ",
            zxs_ram_hash(), zxs_picture_hash(), machine.frame_trace, (unsigned long long)route_samples, route_audio_hash,
            (unsigned long long)machine.dropped);
#ifdef HEADLESS_EXTRA
    HEADLESS_EXTRA(out);
#endif
    fprintf(out, "\"rows\": %llu}\n", (unsigned long long)route_rows_done);
    fflush(out);
    if (out != stdout) fclose(out);
}

/* At each instruction boundary (the instruction and the interrupt it may accept complete): the row of a frame that ended. Returns
 * 1 when the run is over (the frame limit). */
static int headless_service(void)
{
    if (machine.frames > route_rows_done) {
        while (route_rows_done < machine.frames) {
            ++route_rows_done;
            if (route_rows_file) {
                uint16_t regs[16];
                headless_registers(regs);
                fprintf(route_rows_file, "%llu,%08x,%08x,%08x,%08x,%llu,%d,%04x\n", (unsigned long long)route_rows_done,
                        zxs_cpu_hash(), zxs_ram_hash(), zxs_picture_hash(), closed_sound,
                        (unsigned long long)closed_samples, closed_audible, regs[7]);
            }
        }
    }
    return machine.frames >= frames_wanted;
}
