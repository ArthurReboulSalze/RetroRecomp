/* The headless run of the Amstrad CPC, shared by the three programs that run the machine without a window: the reference runner
 * (cpc_reference_main.c), the native check (cpc_native_main.c) and the game's --headless mode (cpc_player.c). MIT, Retro-Recomp.
 * Included once, after boot_keys.h (the start command the game types: retrorecomp/cpc_keys.py; empty in the checks of authored
 * programs). The includer has `machine` (a CpcMachine) in scope; the reference runner defines CPC_HEADLESS_REFERENCE and (the
 * native programs get the chain's from here):
 *   static void headless_cpu(CpcCpuView *view);   the CPU's registers now;
 *   static void headless_counts(FILE *out);       its own report fields (the steps it ran, the interrupts it accepted), each
 *                                                 followed by ", ".
 * It calls headless_service() at every service point (an instruction and the interrupt it may accept complete: the chain's
 * smsrecomp_state_service, the reference runner's loop after each step), so the three programs see the machine at the same instants.
 *
 * At each VSYNC (the board's frame_ready), there: the frame's sound is taken from the board, the frame's row is written, and the
 * boot keys of the frame to come are put on the keyboard (cpc_boot_input.h). The run stops at the frame limit, or at the first
 * service point after the CPU halts with --until-halt, and writes one JSON object: the fields the conversion compares
 * (retrorecomp/cpc_build.py, COMPARED) and the includer's counts.
 *
 * Options (headless_option): --frames N, --until-halt, --picture FILE (the last frame, 768 x 272 x 0x00RRGGBB little endian),
 * --audio FILE (44,100 Hz 16-bit stereo), --watch ADDR (hexadecimal, up to 16), --report FILE (the JSON in FILE instead of the
 * standard output: a game linked for the Windows subsystem has none to rely on), --rows FILE (text, LF: `frame,cpu,ram,picture,
 * sound,samples,audible,pc` at each VSYNC: the registers' hash, the RAM's, the picture's, the frame's sound and its sample count,
 * whether it holds two different values, the PC), and in the native programs --learn FILE (the code the interpreter ran, for the
 * next generation). */
#include "cpc_boot_input.h"

typedef struct {
    uint16_t af, bc, de, hl, ix, iy, sp, pc, af2, bc2, de2, hl2, ir, wz;
    int iff1, iff2, im, halted;
} CpcCpuView;

#ifndef CPC_HEADLESS_REFERENCE
/* The native programs (the check and the game): the chain's CPU, its native and fallback step counts, its accepted interrupts. */
static void headless_cpu(CpcCpuView *v)
{
    const Z80State *z = &g_z80;
    v->af = (uint16_t)(z->a << 8 | z->f); v->bc = (uint16_t)(z->b << 8 | z->c); v->de = (uint16_t)(z->d << 8 | z->e);
    v->hl = (uint16_t)(z->h << 8 | z->l); v->ix = z->ix; v->iy = z->iy; v->sp = z->sp; v->pc = z->pc;
    v->af2 = (uint16_t)(z->a_ << 8 | z->f_); v->bc2 = (uint16_t)(z->b_ << 8 | z->c_); v->de2 = (uint16_t)(z->d_ << 8 | z->e_);
    v->hl2 = (uint16_t)(z->h_ << 8 | z->l_); v->ir = (uint16_t)(z->i << 8 | z->r); v->wz = z->wz;
    v->iff1 = z->iff1; v->iff2 = z->iff2; v->im = z->im; v->halted = z->halted;
}

/* The native programs' own counts: steps run natively (HALT steps and byte-guarded RAM steps among them), steps and cycles on the
 * counted interpreter and the addresses it ran most (up to 16), and the interrupts accepted (compared with the reference's). */
static void headless_counts(FILE *out)
{
    fprintf(out, "\"native_steps\": %llu, \"halt_steps\": %llu, \"guarded_steps\": %llu, \"fallback_steps\": %llu, "
            "\"fallback_cycles\": %llu, \"fallback_at\": {", (unsigned long long)banked_native_steps,
            (unsigned long long)banked_halt_steps, (unsigned long long)banked_guarded_steps,
            (unsigned long long)banked_fallback_steps, (unsigned long long)g_hybrid_cyc);
    for (int i = 0; i < 16 && fallback_count[i]; ++i)
        fprintf(out, "%s\"%04X\": %llu", i ? ", " : "", fallback_at[i], (unsigned long long)fallback_count[i]);
    fprintf(out, "}, \"interrupts\": %llu, ", (unsigned long long)g_irq_taken);
}
#else
static void headless_cpu(CpcCpuView *view);
static void headless_counts(FILE *out);
#endif

static uint32_t headless_picture[CPC_SCREEN_WIDTH * CPC_SCREEN_HEIGHT];
static unsigned long long headless_frames_wanted = 50;
static int headless_until_halt, headless_was_halted;
static const char *headless_picture_file, *headless_audio_file, *headless_report_file;
static FILE *headless_audio, *headless_rows;
/* --trace FILE --trace-from N (a development aid): from frame N, one line a service point (the board's time, PC, AF BC DE HL SP,
 * IFF1), at most HEADLESS_TRACE_MAX lines; the native check's and the reference runner's files compare line by line. */
#define HEADLESS_TRACE_MAX 400000ul
static FILE *headless_trace;
static unsigned long long headless_trace_from;
static unsigned long headless_trace_lines;

/* --script FILE: a route's inputs on top of the boot keys, one event a line, frames not decreasing:
 *   FRAME key CPCKEY 0|1      a key of the CPC's matrix (cpc_ppi.h CPC_KEY_*, row * 8 + bit) up or down
 *   FRAME joy PORT HEX        joystick PORT (0: row 9, 1: row 6) holding CPC_JOY_* bits
 * What a frame holds is a function of its number alone (every event up to it, in order), so a loaded state continues the
 * route; the keys add to the boot sequence's while it runs. */
typedef struct { unsigned long long frame; uint8_t joy, code, value; } HeadlessEvent;
static HeadlessEvent *headless_events;
static size_t headless_event_count;
static size_t headless_event_next;
static uint8_t headless_keys_held[CPC_KEY_ROWS], headless_joy_held[2];
static unsigned long long headless_events_frame;

static int headless_script(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) return 0;
    char line[128], kind[8];
    unsigned long long frame, last = 0;
    unsigned a, b;
    size_t cap = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n') continue;
        if (sscanf(line, "%llu %7s %u %x", &frame, kind, &a, &b) != 4 || frame < last) { fclose(f); return 0; }
        const int joy = !strcmp(kind, "joy");
        if ((!joy && strcmp(kind, "key")) || (joy && (a > 1 || b > 0x3F)) || (!joy && (a >= CPC_KEY_ROWS * 8 || b > 1))) {
            fclose(f);
            return 0;
        }
        if (headless_event_count == cap) {
            cap = cap ? cap * 2 : 256;
            HeadlessEvent *grown = (HeadlessEvent *)realloc(headless_events, cap * sizeof *grown);
            if (!grown) { fclose(f); return 0; }
            headless_events = grown;
        }
        headless_events[headless_event_count++] = (HeadlessEvent){ frame, (uint8_t)joy, (uint8_t)a, (uint8_t)b };
        last = frame;
    }
    fclose(f);
    return 1;
}

/* The route's held keys and sticks at the board's frame (replayed from the start when the frame went back: a loaded state). */
static void headless_script_inputs(void)
{
    if (!headless_event_count) return;
    if (machine.frames < headless_events_frame) {
        headless_event_next = 0;
        memset(headless_keys_held, 0, sizeof headless_keys_held);
        memset(headless_joy_held, 0, sizeof headless_joy_held);
    }
    headless_events_frame = machine.frames;
    for (; headless_event_next < headless_event_count && headless_events[headless_event_next].frame <= machine.frames;
         ++headless_event_next) {
        const HeadlessEvent *e = &headless_events[headless_event_next];
        if (e->joy) headless_joy_held[e->code] = e->value;
        else if (e->value) headless_keys_held[e->code >> 3] |= (uint8_t)(1u << (e->code & 7));
        else headless_keys_held[e->code >> 3] &= (uint8_t)~(1u << (e->code & 7));
    }
    for (unsigned key = 0; key < CPC_KEY_ROWS * 8; ++key)
        if (headless_keys_held[key >> 3] >> (key & 7) & 1) cpc_ppi_key(&machine.ppi, key, 1);
    machine.ppi.joystick[0] |= headless_joy_held[0];
    machine.ppi.joystick[1] |= headless_joy_held[1];
}
static unsigned headless_watch[16], headless_watches;
static uint32_t headless_audio_hash = 2166136261u, headless_frame_sound = 2166136261u;
static unsigned long long headless_audio_samples, headless_frame_samples;
static int headless_frame_min = 32767, headless_frame_max = -32768;

static uint32_t headless_fnv_add(uint32_t h, const void *data, size_t size)
{
    const uint8_t *bytes = (const uint8_t *)data;
    for (size_t i = 0; i < size; ++i) { h ^= bytes[i]; h *= 16777619u; }
    return h;
}

static uint32_t headless_fnv(const uint8_t *data, size_t size) { return headless_fnv_add(2166136261u, data, size); }

/* 1: the option (and its value, `*i` moved past it) was taken; 0: not a headless option. */
static int headless_option(int argc, char **argv, int *i)
{
    const char *a = argv[*i], *v = *i + 1 < argc ? argv[*i + 1] : "";
    if (!strcmp(a, "--frames")) { headless_frames_wanted = strtoull(v, NULL, 10); ++*i; }
    else if (!strcmp(a, "--until-halt")) headless_until_halt = 1;
    else if (!strcmp(a, "--picture")) { headless_picture_file = v; ++*i; }
    else if (!strcmp(a, "--audio")) { headless_audio_file = v; ++*i; }
    else if (!strcmp(a, "--watch") && headless_watches < 16) { headless_watch[headless_watches++] = (unsigned)strtoul(v, NULL, 16); ++*i; }
    else if (!strcmp(a, "--report")) { headless_report_file = v; ++*i; }
    else if (!strcmp(a, "--trace")) { headless_trace = fopen(v, "w"); if (!headless_trace) exit(3); ++*i; }
    else if (!strcmp(a, "--trace-from")) { headless_trace_from = strtoull(v, NULL, 10); ++*i; }
    else if (!strcmp(a, "--script")) { if (!headless_script(v)) { fprintf(stderr, "--script: not a route script\n"); exit(2); } ++*i; }
    else if (!strcmp(a, "--rows")) {
        headless_rows = fopen(v, "w");
        if (!headless_rows) exit(3);
        fputs("frame,cpu,ram,picture,sound,samples,audible,pc\n", headless_rows);
        ++*i;
    }
#ifndef CPC_HEADLESS_REFERENCE
    else if (!strcmp(a, "--learn")) { learn_out = v; ++*i; }
#endif
    else return 0;
    return 1;
}

/* The board draws into the headless picture; the sound file opens. */
static void headless_start(void)
{
    machine.picture = headless_picture;
    headless_audio = headless_audio_file ? fopen(headless_audio_file, "wb") : NULL;
}

/* The sound the board made so far: into the run's hash and file and the frame's hash, level range and count. */
static void headless_take_audio(void)
{
    static int16_t samples[CPC_AUDIO_BUFFER * 2];
    uint32_t n = cpc_audio_take(&machine, samples, CPC_AUDIO_BUFFER);
    if (!n) return;
    const size_t bytes = (size_t)n * 2 * sizeof *samples;
    if (headless_audio) fwrite(samples, bytes, 1, headless_audio);
    headless_audio_hash = headless_fnv_add(headless_audio_hash, samples, bytes);
    headless_frame_sound = headless_fnv_add(headless_frame_sound, samples, bytes);
    headless_audio_samples += n;
    headless_frame_samples += n;
    for (uint32_t s = 0; s < n * 2; ++s) {
        if (samples[s] < headless_frame_min) headless_frame_min = samples[s];
        if (samples[s] > headless_frame_max) headless_frame_max = samples[s];
    }
}

/* The CPU's registers as the rows hash them, in one order for both CPUs: AF BC DE HL IX IY SP PC, AF' BC' DE' HL', IR, WZ,
 * IM|IFF1|IFF2|halted. */
static uint32_t headless_cpu_hash(const CpcCpuView *c)
{
    const uint16_t regs[16] = { c->af, c->bc, c->de, c->hl, c->ix, c->iy, c->sp, c->pc, c->af2, c->bc2, c->de2, c->hl2, c->ir, c->wz,
                                (uint16_t)(c->im << 3 | c->iff1 << 2 | c->iff2 << 1 | c->halted), 0 };
    return headless_fnv_add(2166136261u, regs, sizeof regs);
}

static void headless_finish(void)
{
    CpcCpuView c;
    headless_cpu(&c);
    headless_take_audio();
#ifndef CPC_HEADLESS_REFERENCE
    if (learn_out) {                             /* --learn: the code the interpreter ran, for the next generation */
        FILE *f = fopen(learn_out, "w");
        for (int i = 0; f && i < learned_count; ++i) fprintf(f, "%08X\n", (unsigned)learned[i]);
        if (f) fclose(f);
    }
#endif
    if (headless_audio) fclose(headless_audio);
    if (headless_rows && fclose(headless_rows)) exit(3);
    if (headless_picture_file) {
        FILE *f = fopen(headless_picture_file, "wb");
        if (f) { fwrite(headless_picture, sizeof headless_picture, 1, f); fclose(f); }
    }
    FILE *out = headless_report_file ? fopen(headless_report_file, "w") : stdout;
    if (!out) exit(3);
    fprintf(out, "{\"frames\": %llu, \"cycles\": %llu, ", (unsigned long long)machine.frames, (unsigned long long)machine.cycles);
    headless_counts(out);
    fprintf(out, "\"pc\": %u, \"sp\": %u, \"af\": %u, \"bc\": %u, \"de\": %u, \"hl\": %u, \"ix\": %u, \"iy\": %u, \"iff1\": %d, "
            "\"im\": %d, \"halted\": %d, \"cpu_hash\": %u, \"ram_fnv\": %u, \"picture_fnv\": %u, \"audio_fnv\": %u, "
            "\"audio_samples\": %llu, \"mode\": %u, \"rom_config\": %u, \"ram_config\": %u, \"upper_rom\": %u, \"ay\": [",
            c.pc, c.sp, c.af, c.bc, c.de, c.hl, c.ix, c.iy, c.iff1, c.im, c.halted, headless_cpu_hash(&c),
            headless_fnv(machine.ram, sizeof machine.ram), headless_fnv((const uint8_t *)headless_picture, sizeof headless_picture),
            headless_audio_hash, headless_audio_samples, machine.ga.mode, machine.ga.rom_config, machine.ga.ram_config,
            machine.upper_rom);
    for (int r = 0; r < 16; ++r) fprintf(out, "%s%u", r ? ", " : "", machine.ay_reg[r]);
    const DskImage *disk = machine.fdc.drive[0].image;   /* drive A as it stands: what the game wrote on it included */
    fprintf(out, "], \"fdc_commands\": %u, \"disk_written\": %d, \"disk_fnv\": %u, ", machine.fdc.commands,
            machine.fdc.drive[0].written, disk ? headless_fnv(disk->bytes, disk->size) : 0u);
#ifdef CPC_HEADLESS_DISK_START
    fprintf(out, "\"disk_start_fnv\": %u, ", CPC_HEADLESS_DISK_START);   /* the game's: drive A when the run began, its copy read */
#endif
    fprintf(out, "\"watch\": {");
    for (unsigned w = 0; w < headless_watches; ++w)
        fprintf(out, "%s\"%04X\": %u", w ? ", " : "", headless_watch[w], cpc_read(&machine, (uint16_t)headless_watch[w]));
    fprintf(out, "}}\n");
    if (out == stdout) fflush(out);
    else if (fclose(out)) exit(3);
    exit(0);
}

/* At each service point: at a VSYNC the frame's sound, its row and the next frame's boot keys; then the stop. */
static void headless_service(void)
{
    if (machine.frame_ready) {
        machine.frame_ready = 0;
        headless_take_audio();
        if (headless_rows) {
            CpcCpuView c;
            headless_cpu(&c);
            fprintf(headless_rows, "%llu,%08x,%08x,%08x,%08x,%llu,%d,%04x\n", (unsigned long long)machine.frames,
                    headless_cpu_hash(&c), headless_fnv(machine.ram, sizeof machine.ram),
                    headless_fnv((const uint8_t *)headless_picture, sizeof headless_picture), headless_frame_sound,
                    headless_frame_samples, headless_frame_samples && headless_frame_min != headless_frame_max, c.pc);
        }
        headless_frame_sound = 2166136261u;
        headless_frame_samples = 0;
        headless_frame_min = 32767;
        headless_frame_max = -32768;
        cpc_boot_inputs(&machine, &rr_boot_keys);
        headless_script_inputs();
    }
    CpcCpuView c;
    headless_cpu(&c);
    if (headless_trace && machine.frames >= headless_trace_from && headless_trace_lines < HEADLESS_TRACE_MAX) {
        fprintf(headless_trace, "%llu %04x %04x %04x %04x %04x %04x %d\n", (unsigned long long)machine.cycles, c.pc, c.af, c.bc,
                c.de, c.hl, c.sp, c.iff1);
        if (++headless_trace_lines == HEADLESS_TRACE_MAX) fflush(headless_trace);
    }
    if ((headless_until_halt && c.halted && !headless_was_halted) || machine.frames >= headless_frames_wanted)
        headless_finish();
    headless_was_halted = c.halted;
}
