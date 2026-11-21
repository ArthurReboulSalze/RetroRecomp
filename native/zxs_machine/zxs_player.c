/* An exported ZX Spectrum game: the translated Z80 code of the ROM and the code learned from RAM (zxs_glue.inc and the generated
 * bodies), the Spectrum machine (zxs_machine.c), and the host kit's window through the Spectrum adapter
 * (hostkit/adapters/rrhk_zxs.inc). MIT, Retro-Recomp.
 *
 * Its inputs are its own resources (the ids are zxs_game.h's, written by retrorecomp/zxs_build.py, the one place they are named):
 * the ROM (16 KiB, or 32 KiB on the 128K) and the machine image the converted snapshot starts from (zxs_build.zxs_image). The
 * guest owns the loop: at the start of each frame (the machine's frame hook) the frame just drawn is due, and at the next
 * instruction boundary (zxs_main_service) the game hands its picture and sound to the kit and takes the inputs back. A reset
 * starts the snapshot again. The Spectrum has no battery save.
 *
 * `game.exe --headless [options]` replays a route with no window, no sound device and nothing written beside the game: the ROM
 * and the image are the game's own resources, the options and the report those of the native check (zxs_headless.inc, as
 * zxs_native_main.c uses it), so the delivered file is compared with the reference as the check is. Its own options:
 * --save-state FILE with --save-at N (saved at the service of frame N, after its row), --load-state FILE (loaded at the first
 * service of the run; the script's events up to the loaded frame then apply at once). Exit codes: 0 done, 2 a bad option,
 * 3 a missing resource or an unwritable file, 4 a refused state. */
#define SMSRECOMP_BANKED_AOT 1
#include <SDL.h>
/* The rendered step loop keeps two debugging helpers (its statistics, a final CPU record) the game does not call. */
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#endif
#include "zxs_glue.inc"
#if defined(__GNUC__) || defined(__clang__)
#pragma GCC diagnostic pop
#endif
#include "zxs_game.h"
#include "embedded_resources.h"
#include "platform_io.h"
#include "state_envelope.h"

/* The frontend variables rrhk_computer.inc reads (see its header). The fast-loading hold-off and the drive keys' choices are set
 * there and never read here (no tape, no drive). */
#if defined(__GNUC__) || defined(__clang__)
#define ZXS_KIT_SET_ONLY __attribute__((unused))
#else
#define ZXS_KIT_SET_ONLY
#endif
static bool guest_keyboard, mouse_grab, mouse_game, input_focus = true, fast_forward, want_swap, want_eject;
static int loading_holdoff ZXS_KIT_SET_ONLY, swap_drive ZXS_KIT_SET_ONLY, swap_direction ZXS_KIT_SET_ONLY;
static const Uint8 *keys;
static int mouse_dx, mouse_dy;
static Uint32 mouse_buttons;
static unsigned width, height;
static double aspect_ratio = 4.0 / 3.0;
static char player_config[1024] = "player.cfg";
static char state_file_utf8[1100] = "quick.rrstate";

static uint8_t image[ZXS_IMAGE_BYTES];          /* the machine image, kept for a reset */
static size_t rom_size;

/* Quick states for the host kit's F8/F9 (defined below). */
static bool zxs_game_state_file(const wchar_t *path, bool load);
static bool zxs_game_state_path(wchar_t *path, size_t capacity);

#include "hostkit/adapters/rrhk_zxs.inc"

/* ---- the headless route: the same registers, interrupts and extra report members as the native check (zxs_native_main.c) ---- */
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
    fprintf(out, "}, \"game\": 1, "); \
} while (0)
#include "zxs_headless.inc"

/* ---- quick states ----
 * The file is the envelope the Z80 machines share (state_envelope.h: magic RRZXSST, schema 1, machine 1 48K / 2 128K / 3 16K, the
 * identity zxs_game.h gives), then the body: (1) the build binding RR_ZXS_STATE_ABI, 32 bytes the converter writes (the state
 * layout, the ROM, the model), compared and never applied; (2) the CPU; (3) the machine: every field of ZxsMachine but the ROM
 * pointer, the hooks and the trace switch (the per-model constants are checked, not applied). A state is checked whole on
 * scratch copies and applied only then; saved and loaded at the service point (an instruction and the interrupt it may accept
 * complete), where the loop's own locals hold nothing a state would need. */
#define ZXS_STATE_SCHEMA 1u
#define ZXS_STATE_CAPACITY ((size_t)RR_STATE_ENVELOPE_HEADER + 32u + 256u + sizeof machine.ram + sizeof machine.picture \
                            + 2u * ZXS_AUDIO_BUFFER + 512u)
static const uint8_t zxs_state_binding[32] = RR_ZXS_STATE_ABI;
static ZxsMachine zxs_state_scratch;              /* the candidate machine of a check or a load */

static uint32_t zxs_state_model(void) { return machine.ram16k ? 3u : (uint32_t)machine.model + 1u; }

/* (2) The CPU, field for field as the MSX's (msx_state_file.inc), into `s`. */
static void zxs_cpu_state(RetroStateIO *io, Z80State *s)
{
    Z80State v = *s;
    RR_FIELD(v, a, 1, 255); RR_FIELD(v, f, 1, 255); RR_FIELD(v, b, 1, 255); RR_FIELD(v, c, 1, 255);
    RR_FIELD(v, d, 1, 255); RR_FIELD(v, e, 1, 255); RR_FIELD(v, h, 1, 255); RR_FIELD(v, l, 1, 255);
    RR_FIELD(v, a_, 1, 255); RR_FIELD(v, f_, 1, 255); RR_FIELD(v, b_, 1, 255); RR_FIELD(v, c_, 1, 255);
    RR_FIELD(v, d_, 1, 255); RR_FIELD(v, e_, 1, 255); RR_FIELD(v, h_, 1, 255); RR_FIELD(v, l_, 1, 255);
    RR_FIELD(v, pc, 2, 65535); RR_FIELD(v, sp, 2, 65535); RR_FIELD(v, ix, 2, 65535);
    RR_FIELD(v, iy, 2, 65535); RR_FIELD(v, wz, 2, 65535); RR_FIELD(v, i, 1, 255); RR_FIELD(v, r, 1, 255);
    RR_FIELD(v, iff1, 1, 1); RR_FIELD(v, iff2, 1, 1); RR_FIELD(v, im, 1, 2); RR_FIELD(v, halted, 1, 1);
    RR_FIELD(v, q, 1, 255); RR_FIELD(v, p, 1, 1); RR_FIELD(v, ei_block, 1, 1); RR_FIELD(v, cyc, 8, (1ULL << 60));
    *s = v;
}

/* A field that must equal the running machine's (fixed for the game): written, then compared on reading. */
static void zxs_state_same(RetroStateIO *io, uint64_t value, unsigned width)
{
    if (rr_state_word(io, value, width, UINT64_MAX >> (64 - 8 * width)) != value)
        io->ok = false;
}

/* (3) The machine, into `m` (the running machine when writing, the scratch copy when checking or loading). */
static void zxs_machine_state(RetroStateIO *io, ZxsMachine *m)
{
    zxs_state_same(io, (uint64_t)m->model, 1);
    zxs_state_same(io, (uint64_t)m->ram16k, 1);
    zxs_state_same(io, (uint64_t)m->kempston_present, 1);
    for (int bank = 0; bank < 8; ++bank)
        rr_state_bytes(io, m->ram[bank], sizeof m->ram[bank]);
    RR_FIELD(*m, port_7ffd, 1, 255); RR_FIELD(*m, border, 1, 7); RR_FIELD(*m, out_fe, 1, 255);
    for (int row = 0; row < 8; ++row) RR_FIELD(*m, keys[row], 1, 255);
    RR_FIELD(*m, kempston, 1, 0x1F);
    RR_FIELD(*m, ay_latch, 1, 15);
    for (int i = 0; i < 16; ++i) RR_FIELD(*m, ay_regs[i], 1, 255);
    RR_FIELD(*m, ay.ticks, 4, UINT32_MAX);
    for (int c = 0; c < 3; ++c) { RR_FIELD(*m, ay.tone_count[c], 2, 0x0FFF); RR_FIELD(*m, ay.tone_out[c], 1, 1); }
    RR_FIELD(*m, ay.noise_count, 2, 0x1F); RR_FIELD(*m, ay.lfsr, 4, 0x1FFFF); RR_FIELD(*m, ay.env_count, 2, 0xFFFF);
    RR_FIELD(*m, ay.env_step, 1, 15); RR_FIELD(*m, ay.env_up, 1, 1); RR_FIELD(*m, ay.env_holding, 1, 1);
    RR_FIELD(*m, ay_next, 8, 1ULL << 60);
    RR_FIELD(*m, ay_level, 4, 32767);
    RR_FIELD(*m, cycles, 8, 1ULL << 60); RR_FIELD(*m, frame_start, 8, 1ULL << 60); RR_FIELD(*m, frames, 8, 1ULL << 40);
    RR_FIELD(*m, line, 2, m->lines - 1);
    /* The picture's indices are colours 0-15: a damaged one is refused, never looked up. */
    if (io->mode == RR_STATE_CHECK && io->ok && io->pos <= io->size && sizeof m->picture <= io->size - io->pos)
        for (size_t i = 0; i < sizeof m->picture; ++i)
            if (io->data[io->pos + i] > 15) { io->ok = false; break; }
    rr_state_bytes(io, m->picture, sizeof m->picture);
    RR_FIELD(*m, frame_trace, 4, UINT32_MAX);
    /* The sound's box (native/audio_box.h): its time, the sample being built, the samples waiting; its step and buffer are the
     * machine's own (zxs_reset), not state. */
    RR_FIELD(*m, box.time, 8, 1ULL << 60); RR_FIELD(*m, box.next_sample, 8, UINT64_MAX);
    uint64_t acc = (uint64_t)m->box.acc[0];        /* levels are never negative: the sum is not either */
    acc = rr_state_word(io, acc, 8, 1ULL << 62);
    m->box.acc[0] = (int64_t)acc;
    RR_FIELD(*m, box.acc_cycles, 8, 1ULL << 60);
    RR_FIELD(*m, box.count, 2, ZXS_AUDIO_BUFFER);
    for (unsigned i = 0; i < m->box.count && io->ok; ++i)
        m->out[i] = (int16_t)(uint16_t)rr_state_word(io, (uint16_t)m->out[i], 2, 65535);
    RR_FIELD(*m, box.dropped, 4, UINT32_MAX);
    /* The frame position must be one the machine can be at: within the line it is drawing, the sound caught up to it. */
    if (m->cycles < m->frame_start + (uint64_t)m->line * m->t_line || m->cycles >= m->frame_start + (uint64_t)(m->line + 1) * m->t_line
        || m->box.time > m->cycles)
        io->ok = false;
}

static void zxs_state_body(RetroStateIO *io)
{
    /* (1) the build binding */
    for (int i = 0; i < 32; ++i)
        if (rr_state_word(io, zxs_state_binding[i], 1, 255) != zxs_state_binding[i])
            io->ok = false;
    /* (2) the CPU: into a candidate, applied last */
    Z80State cpu = g_z80;
    zxs_cpu_state(io, &cpu);
    /* (3) the machine */
    if (io->mode == RR_STATE_WRITE) {
        zxs_machine_state(io, &machine);
        return;
    }
    zxs_state_scratch = machine;
    zxs_machine_state(io, &zxs_state_scratch);
    if (!io->ok || zxs_state_scratch.cycles > cpu.cyc || cpu.cyc - zxs_state_scratch.cycles > 2u * machine.t_line) {
        io->ok = false;
        return;
    }
    if (io->mode == RR_STATE_APPLY) {
        machine = zxs_state_scratch;               /* the ROM, the hooks and the trace switch are the running machine's */
        g_z80 = cpu;
        smsrecomp_region_generation = 0;           /* the loop's region map is rebuilt before the next step */
        g_next_line_cyc = zxs_next_event(&machine);
        smsrecomp_measured_guest_cycles = g_z80.cyc;
        step_start = g_z80.cyc;
        smsrecomp_interp_depth = 0;                /* the fallback CPU is refilled from g_z80 at each use */
        /* Execution, fallback and learning counters stay cumulative across a load, as on the MSX. */
    }
}

static RetroStateEnvelope zxs_state_envelope(void)
{
    RetroStateEnvelope e = {"RRZXSST\0", ZXS_STATE_SCHEMA, zxs_state_model(), RR_ZXS_IDENTITY, zxs_state_body};
    return e;
}

/* Save to `path`: written beside it, flushed, then put in its place (the old state stays whole if anything fails). */
static int zxs_state_save(const wchar_t *path)
{
    uint8_t *data = (uint8_t *)malloc(ZXS_STATE_CAPACITY);
    if (!data) return RR_STATE_IO_ERROR;
    RetroStateEnvelope envelope = zxs_state_envelope();
    size_t size = 0;
    if (rr_state_envelope_write(&envelope, data, ZXS_STATE_CAPACITY, &size) != RR_STATE_OK) { free(data); return RR_STATE_INVALID; }
    wchar_t temporary[32768];
    swprintf(temporary, 32768, L"%ls.%lu.tmp", path, rr_process_id());
    FILE *f = rr_fopen(temporary, L"wb");
    bool ok = f && fwrite(data, size, 1, f) == 1;
    if (ok) ok = rr_flush_file(f) != 0;
    if (f && fclose(f) != 0) ok = false;
    free(data);
    if (ok) ok = rr_replace(temporary, path) != 0;
    if (!ok) rr_remove(temporary);
    return ok ? RR_STATE_OK : RR_STATE_IO_ERROR;
}

/* Load `path`: RR_STATE_OK, or a refusal that leaves the machine and the file as they were. */
static int zxs_state_load(const wchar_t *path)
{
    FILE *f = rr_fopen(path, L"rb");
    if (!f) return rr_exists(path) ? RR_STATE_IO_ERROR : RR_STATE_MISSING;
    uint8_t *data = (uint8_t *)malloc(ZXS_STATE_CAPACITY);
    if (!data) { fclose(f); return RR_STATE_IO_ERROR; }
    size_t size = fread(data, 1, ZXS_STATE_CAPACITY, f);
    int extra = fgetc(f); bool read_ok = !ferror(f); fclose(f);
    int result = RR_STATE_INVALID;
    if (read_ok && extra == EOF) {
        RetroStateEnvelope envelope = zxs_state_envelope();
        result = rr_state_envelope_read(&envelope, data, size);
        /* A whole, undamaged state of another build (another ROM, layout or model): incompatible, not damaged. */
        if (result == RR_STATE_INVALID && size >= RR_STATE_ENVELOPE_HEADER + 32
            && (size_t)(data[80] | data[81] << 8 | (uint32_t)data[82] << 16 | (uint32_t)data[83] << 24) == size - RR_STATE_ENVELOPE_HEADER
            && rr_state_crc(data + RR_STATE_ENVELOPE_HEADER, size - RR_STATE_ENVELOPE_HEADER)
               == (uint32_t)(data[84] | data[85] << 8 | (uint32_t)data[86] << 16 | (uint32_t)data[87] << 24)
            && memcmp(data + RR_STATE_ENVELOPE_HEADER, zxs_state_binding, 32))
            result = RR_STATE_INCOMPATIBLE;
    }
    free(data);
    return result;
}

/* F8/F9 in play, at the service point (the kit calls this from the frame's end). */
static bool zxs_game_state_file(const wchar_t *path, bool load)
{
    return (load ? zxs_state_load(path) : zxs_state_save(path)) == RR_STATE_OK;
}

/* The quick state's file beside player.cfg (the kit asks when it opens the window). */
static bool zxs_game_state_path(wchar_t *path, size_t capacity)
{
    return rr_from_utf8(state_file_utf8, path, capacity) != 0;
}

/* ---- the machine ---- */
static volatile int frame_ended;
static int headless;                           /* --headless: a route replayed, no host */

/* The frame hook, at the start of each frame: the frame just drawn is due at the next service. In a headless run the route's
 * events of the frame that begins come first (zxs_headless.inc). */
static void play_frame_hook(void *user) { (void)user; frame_ended = 1; }
static void headless_frame_hook(void *user) { route_frame_start(user); frame_ended = 1; }

/* The machine and the CPU as the image starts them (power-on and a reset alike). */
static int start_from_image(void)
{
    ZxsCpuStart cpu;
    if (zxs_load_image(&machine, image, sizeof image, rom, &cpu)) return -1;
    if (rom_size != (machine.model == ZXS_128K ? 0x8000u : 0x4000u)) return -1;
    zxs_cpu_from_image(&cpu);
    g_next_line_cyc = zxs_next_event(&machine);
    smsrecomp_region_generation = 0;
    smsrecomp_measured_guest_cycles = g_z80.cyc;
    step_start = g_z80.cyc;
    smsrecomp_interp_depth = 0;
    return 0;
}

/* The ROM and the image from the game's own resources. */
static int setup_machine(void)
{
    size_t image_size = 0;
    const uint8_t *rom_bytes = rr_resource(RR_ZXS_ROM_RESOURCE, &rom_size), *image_bytes = rr_resource(RR_ZXS_IMAGE_RESOURCE, &image_size);
    if (!rom_bytes || !image_bytes || (rom_size != 0x4000 && rom_size != 0x8000) || image_size != sizeof image) {
        fprintf(stderr, "[zxs] the game's ROM or machine image resource is missing\n");
        return 3;
    }
    memset(rom, 0xFF, sizeof rom);
    memcpy(rom, rom_bytes, rom_size);
    memcpy(image, image_bytes, sizeof image);
    if (start_from_image()) {
        fprintf(stderr, "[zxs] the game's machine image does not fit its ROM\n");
        return 3;
    }
    return 0;
}

/* Headless states (the conversion's fresh-process check). A refused state ends the process with exit 4, leaving the file as it
 * was; a state that cannot be written, with exit 3. */
static wchar_t state_save_file[32768], state_load_file[32768];
static unsigned long state_save_at;
static int state_save_due, state_load_due;

/* A path given on the command line: argv is in the ANSI code page on Windows (the game's manifest names no UTF-8 code page), as
 * fopen reads the other options' paths; UTF-8 elsewhere. */
static int headless_path(const char *v, wchar_t *out)
{
#ifdef _WIN32
    return MultiByteToWideChar(CP_ACP, 0, v, -1, out, 32768) != 0;
#else
    return rr_from_utf8(v, out, 32768);
#endif
}

static int headless_state_option(const char *a, const char *v)
{
    if (!strcmp(a, "--save-state")) { if (!headless_path(v, state_save_file)) return -1; state_save_due = 1; }
    else if (!strcmp(a, "--save-at")) state_save_at = strtoul(v, NULL, 10);
    else if (!strcmp(a, "--load-state")) { if (!headless_path(v, state_load_file)) return -1; state_load_due = 1; }
    else return 0;
    return 1;
}

static void headless_main_service(void)
{
    if (state_load_due) {
        /* The first service of the run (one instruction from the image, overwritten whole): the state, then the route as it
         * stands at the loaded frame (its events applied, its rows counted, the frame's sound begun empty). */
        state_load_due = 0;
        if (zxs_state_load(state_load_file) != RR_STATE_OK)
            exit(4);
        route_frame_start(NULL);
        route_rows_done = machine.frames;
        route_frame_sound = 2166136261u; route_frame_samples = 0; route_frame_min = 32767; route_frame_max = -32768;
        return;
    }
    int done = headless_service();             /* the row of the frame that ended */
    if (state_save_due && machine.frames >= state_save_at) {
        state_save_due = 0;
        if (zxs_state_save(state_save_file) != RR_STATE_OK)
            exit(3);
    }
    if (done) {
        /* The loop runs the machine up to its next line only when it reaches it: catch it up to the CPU's time, where the
         * reference, which runs it after every instruction, is (as zxs_native_main.c). */
        machine_to(g_z80.cyc);
        headless_report();
        exit(0);
    }
}

static void zxs_main_service(void)
{
    if (!frame_ended)
        return;
    frame_ended = 0;
    if (headless) {
        headless_main_service();
        return;
    }
    switch (zxs_host_frame(&machine)) {
    case 0: break;
    case 2:                                    /* a reset: the snapshot starts again */
        if (start_from_image()) exit(3);
        machine.frame_hook = play_frame_hook;
        break;
    default: zxs_host_close(); exit(0);
    }
}

/* The game's own folder beside the executable, datas/games/zxs-<identity>, as on the other machines: the player's settings of the
 * computer adapter (player.cfg) and the quick state live there, never in the export folder itself. */
static void prepare_data_folder(void)
{
    static char folder[1024];
    char *base = SDL_GetBasePath();
    size_t start = base ? strlen(base) : 0;
    int n = snprintf(folder, sizeof folder, "%sdatas/games/zxs-%.12s", base ? base : "", RR_ZXS_IDENTITY);
    SDL_free(base);
    if (n <= 0 || n >= (int)sizeof folder) return;              /* keep player.cfg in the working folder */
    for (size_t i = start; ; i++) {
        char c = folder[i];
        if (c == '/' || c == '\\' || c == 0) {
            wchar_t wide[1024];
            folder[i] = 0;
            if (rr_from_utf8(folder, wide, 1024)) rr_mkdir(wide);
            folder[i] = c;
            if (!c) break;
        }
    }
    snprintf(player_config, sizeof player_config, "%s/player.cfg", folder);
    snprintf(state_file_utf8, sizeof state_file_utf8, "%s/quick.rrstate", folder);
}

static int run(void)
{
    int status = setup_machine();
    if (status)
        return status;
    machine.frame_hook = play_frame_hook;
    prepare_data_folder();
    if (!zxs_host_open(RR_ZXS_TITLE, 3, &machine, image[6])) return 4;
    smsrecomp_banked_run();                      /* returns through exit() when the player quits */
    return 0;
}

/* `--headless`: exit codes 0 done, 2 a bad option, 3 a missing resource or an unwritable file, 4 a refused state. */
static int run_headless(int argc, char **argv)
{
    for (int i = 2; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) return 2;
        ++i;
        int known = headless_state_option(a, v);
        if (!known) known = headless_option(a, v);
        if (known <= 0) return 2;
    }
    if (state_save_due && state_save_at >= frames_wanted) return 2;   /* the save would never happen */
    int status = setup_machine();
    if (status)
        return status;
    headless = 1;
    headless_start();                          /* the route's frame hook, the trace, the rows and the first frame's events */
    machine.frame_hook = headless_frame_hook;
    frame_ended = state_load_due;              /* a load waits for the first service, not for the first frame */
    smsrecomp_banked_run();                    /* returns through exit() at the frame limit */
    return 0;
}

int main(int argc, char **argv)
{
    if (argc > 1 && !strcmp(argv[1], "--headless"))
        return run_headless(argc, argv);
    return run();
}
