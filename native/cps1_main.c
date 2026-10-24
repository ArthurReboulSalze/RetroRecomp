/* CPS-1 game: native 68000 and Z80 code on the CPS-1 board model, with every
 * interpreted instruction counted. No user data or diagnostics are written
 * unless explicitly requested on the command line.
 * Original RetroRecomp contributions: MIT; component notices keep their own. */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include "embedded_resources.h"
#ifdef _WIN32
#include <shellapi.h>
#endif
#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include "miniz.h"
#include "cps1_machine.h"
#include "retro_console16.h"
#include "console16_state.h"
#include "console16_video.h"
#include "runtime_feedback.h"
int rr16_sdl_main(const char *title, int scale);
void rr16_shutdown(void);

extern uint64_t rr_cps1_native_instructions, rr_cps1_interpreted_68k;
extern uint64_t rr_cps1_native_z80, rr_cps1_interpreted_z80;
extern int rr_cps1_force_reference, rr_cps1_force_z80_reference, rr_cps1_observe;
void cps1_fallback_report(FILE *file);

static unsigned frame;
static const int16_t *frame_audio;
static size_t frame_audio_count;
static int audio_taken = 1;
static uint64_t pcm_hash = 14695981039346656037ull, image_hash = 14695981039346656037ull;
static uint64_t samples, nonzero, pcm_energy;
static unsigned peak, nonuniform_frames;
static int headless, frames, scripted, diagnostics, performance_only;
static const char *report_path, *trace_path, *save_path, *load_path, *capture_dir, *pcm_path;
static unsigned save_at, capture_every = 600, measure_from;
static struct { unsigned frame; const char *path; } checkpoints[8];
static unsigned checkpoint_count;
static int ignore_load_error, state_loaded, load_rejected, save_failed, dips_given;
static uint16_t dips[3];
static FILE *trace_file, *pcm;
static unsigned measured_frames, over_budget_frames;
static double simulation_ms, simulation_max_ms, loop_wall_seconds;
static uint64_t performance_frequency;
typedef struct { unsigned frame, p1, p2, p3, p4; } Input;
static Input script[8192];
static unsigned script_count, script_pos;
static uint16_t script_p1, script_p2, script_p3, script_p4;

static wchar_t *wide(const char *text)
{
    size_t n = strlen(text) + 1;
    wchar_t *result = calloc(n, sizeof *result);
    if (result && !rr_from_utf8(text, result, n)) { free(result); result = NULL; }
    return result;
}
static FILE *file_open(const char *path, const wchar_t *mode)
{
    wchar_t *name = wide(path);
    FILE *f = name ? rr_fopen(name, mode) : NULL;
    free(name);
    return f;
}
static int state_file(const char *path, int load)
{
    wchar_t *name = wide(path);
    int ok = name && rr16_state_file(name, load != 0);
    free(name);
    return ok;
}
static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }

/* "frame p1 p2 [p3 p4]": host pad bits in hex, held from that frame on;
 * players 3 and 4 stay released when their columns are absent. */
static int load_script(const char *path)
{
    FILE *f = file_open(path, L"rb");
    if (!f) return 0;
    char line[256];
    unsigned last = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
        if (script_count >= 8192) { fclose(f); return 0; }
        Input *row = &script[script_count];
        row->p3 = row->p4 = 0;
        int fields = sscanf(line, "%u %x %x %x %x", &row->frame, &row->p1, &row->p2, &row->p3, &row->p4);
        if ((fields != 3 && fields != 5) || row->frame < last ||
            row->p1 > 0xfff || row->p2 > 0xfff || row->p3 > 0xfff || row->p4 > 0xfff) { fclose(f); return 0; }
        last = row->frame;
        script_count++;
    }
    fclose(f);
    scripted = 1;
    return script_count != 0;
}

static void capture(void)
{
    if (!capture_dir || frame % capture_every) return;
    char path[4096];
    snprintf(path, sizeof path, "%s/frame-%06u.bmp", capture_dir, frame);
    SDL_Surface *surface = SDL_CreateRGBSurfaceWithFormatFrom((void *)rr16_pixels(), rr16_visible_width(),
        rr16_visible_height(), 32, RR16_WIDTH * 4, SDL_PIXELFORMAT_RGB888);
    SDL_RWops *rw = SDL_RWFromFile(path, "wb");
    if (!surface || !rw || SDL_SaveBMP_RW(surface, rw, 1)) { fprintf(stderr, "Frame capture failed: %s\n", SDL_GetError()); exit(3); }
    SDL_FreeSurface(surface);
}

static void step_frame(void)
{
    uint64_t begun = performance_only ? SDL_GetPerformanceCounter() : 0;
    cps1_run_frame();
    frame++;
    frame_audio = cps1_audio(&frame_audio_count);
    audio_taken = 0;
    uint64_t image = 0, sound = 14695981039346656037ull;
    if (diagnostics) {
        const uint32_t *pixels = cps1_framebuffer();
        image = rr16_video_hash(pixels, CPS1_SCREEN_W, CPS1_SCREEN_W, CPS1_SCREEN_H, CPS1_SCREEN_H);
        image_hash = (image_hash ^ image) * 1099511628211ull;
        for (unsigned n = 1; n < CPS1_SCREEN_W * CPS1_SCREEN_H; n++)
            if (pixels[n] != pixels[0]) { nonuniform_frames++; break; }
        for (size_t n = 0; n < frame_audio_count; n++) {
            int sample = frame_audio[n], magnitude = sample < 0 ? -sample : sample;
            pcm_hash = (pcm_hash ^ (uint16_t)sample) * 1099511628211ull;
            sound = (sound ^ (uint16_t)sample) * 1099511628211ull;
            samples++; nonzero += sample != 0;
            pcm_energy += (uint64_t)((int64_t)sample * sample);
            if ((unsigned)magnitude > peak) peak = (unsigned)magnitude;
        }
    }
    if (pcm && fwrite(frame_audio, sizeof *frame_audio, frame_audio_count, pcm) != frame_audio_count) {
        fprintf(stderr, "PCM write failed.\n"); exit(3);
    }
    if (trace_file)
        fprintf(trace_file, "%u,%016llx,%016llx,%016llx,%016llx,%llu\n", frame, (unsigned long long)cps1_cpu_hash(),
                (unsigned long long)cps1_ram_hash(), (unsigned long long)image, (unsigned long long)sound,
                (unsigned long long)frame_audio_count);
    capture();
    if (save_path && save_at == frame && !state_file(save_path, 0)) save_failed = 1;
    for (unsigned i = 0; i < checkpoint_count; i++)
        if (checkpoints[i].frame == frame && !state_file(checkpoints[i].path, 0)) save_failed = 1;
    if (performance_only && frame > measure_from) {
        double ms = 1000.0 * (double)(SDL_GetPerformanceCounter() - begun) / (double)performance_frequency;
        measured_frames++; simulation_ms += ms;
        if (ms > simulation_max_ms) simulation_max_ms = ms;
        if (ms > 1000.0 * RR16_FRAME_SECONDS) over_budget_frames++;
    }
}

static void scripted_pads(void)
{
    while (script_pos < script_count && script[script_pos].frame <= frame) {
        script_p1 = (uint16_t)script[script_pos].p1; script_p2 = (uint16_t)script[script_pos].p2;
        script_p3 = (uint16_t)script[script_pos].p3; script_p4 = (uint16_t)script[script_pos].p4;
        script_pos++;
    }
    rr_cps1_set_extra_pads(script_p3, script_p4);
    rr_cps1_apply_pads(script_p1, script_p2);
}

void rr_cps1_host_frame(uint16_t p1, uint16_t p2)
{
    if (scripted) scripted_pads();
    else rr_cps1_apply_pads(p1, p2);
    step_frame();
}
uint32_t rr_cps1_frame_index(void) { return frame; }
void rr_cps1_restore_frame(uint32_t value)
{
    frame = value; script_pos = 0; script_p1 = script_p2 = script_p3 = script_p4 = 0;
    audio_taken = 1; frame_audio_count = 0;
}
void rr_cps1_reset_machine(void) { cps1_reset(); rr_cps1_restore_frame(0); }
const int16_t *rr_cps1_take_audio(size_t *count)
{
    *count = audio_taken ? 0 : frame_audio_count;
    audio_taken = 1;
    return frame_audio;
}
void rr16_host_discontinuity(void);

static int report(const char *set)
{
    if (!report_path) return 1;
    FILE *f = file_open(report_path, L"wb");
    if (!f) return 0;
    cps1_cpu_state cpu;
    cps1_cpu_state_get(&cpu);
    fprintf(f, "{\"stage\":\"cps1\",\"set\":\"%s\",\"frames\":%u,\"native_68000\":%llu,\"interpreted_68000\":%llu,"
               "\"native_z80\":%llu,\"interpreted_z80\":%llu,\"reference\":%s,\"pc\":%u,\"z80_pc\":%u,"
               "\"image_hash\":\"%016llx\",\"pcm_hash\":\"%016llx\",\"pcm_samples\":%llu,\"nonzero_samples\":%llu,"
               "\"peak\":%u,\"rms\":%.4f,\"nonuniform_frames\":%u,\"video_hz\":%.6f,\"pcm_rate\":%u,"
               "\"rotation\":%d,\"cpu_hash\":\"%016llx\",\"ram_hash\":\"%016llx\",\"state_loaded\":%s,"
               "\"load_rejected\":%s,\"save_failed\":%s,\"loop_wall_seconds\":%.6f,\"performance_only\":%s,"
               "\"measured_frames\":%u,\"simulation_ms_mean\":%.6f,\"simulation_ms_max\":%.6f,"
               "\"simulation_over_budget_frames\":%u,\"fallback\":",
            set, frame, (unsigned long long)rr_cps1_native_instructions, (unsigned long long)rr_cps1_interpreted_68k,
            (unsigned long long)rr_cps1_native_z80, (unsigned long long)rr_cps1_interpreted_z80,
            rr_cps1_force_reference ? "true" : "false", cpu.m68k_pc, cpu.z80_pc,
            (unsigned long long)image_hash, (unsigned long long)pcm_hash, (unsigned long long)samples,
            (unsigned long long)nonzero, peak, samples ? sqrt((double)pcm_energy / (double)samples) : 0.0,
            nonuniform_frames, 1.0 / RR16_FRAME_SECONDS, CPS1_AUDIO_RATE, RR_CPS1_ROTATION,
            (unsigned long long)cps1_cpu_hash(), (unsigned long long)cps1_ram_hash(),
            state_loaded ? "true" : "false", load_rejected ? "true" : "false", save_failed ? "true" : "false",
            loop_wall_seconds, performance_only ? "true" : "false", measured_frames,
            measured_frames ? simulation_ms / measured_frames : 0.0, simulation_max_ms, over_budget_frames);
    cps1_fallback_report(f);
    fputs("}\n", f);
    int okay = !ferror(f);
    return fclose(f) == 0 && okay;
}

/* Resource 201: "CPZ1", raw size, zlib("CPS1PACK", count, {name[16], size}..., data...). */
typedef struct { const uint8_t *data; size_t size; } Region;
static int unpack(uint8_t **content, Region *regions, const char *const *names, unsigned count)
{
    size_t packed_size;
    const uint8_t *source = rr_resource(201, &packed_size);
    if (!source || packed_size < 8 || memcmp(source, "CPZ1", 4)) return 0;
    size_t size = le32(source + 4);
    if (size < 16 || size > (256u << 20)) return 0;
    uint8_t *raw = malloc(size);
    if (!raw) return 0;
    mz_ulong expanded = (mz_ulong)size;
    if (mz_uncompress(raw, &expanded, source + 8, (mz_ulong)(packed_size - 8)) != MZ_OK || expanded != size ||
        memcmp(raw, "CPS1PACK", 8)) { free(raw); return 0; }
    uint32_t entries = le32(raw + 8);
    size_t offset = 12 + (size_t)entries * 20;
    if (entries > 16 || offset > size) { free(raw); return 0; }
    for (uint32_t e = 0; e < entries; e++) {
        const uint8_t *entry = raw + 12 + e * 20;
        uint32_t length = le32(entry + 16);
        if (length > size - offset) { free(raw); return 0; }
        for (unsigned n = 0; n < count; n++)
            if (!strncmp((const char *)entry, names[n], 16)) { regions[n].data = raw + offset; regions[n].size = length; }
        offset += length;
    }
    if (offset != size) { free(raw); return 0; }
    *content = raw;
    return 1;
}

static int execute(int argc, char **argv)
{
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--headless")) headless = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--frames")) frames = atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--report")) report_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--performance-report")) { report_path = argv[++i]; performance_only = 1; }
        else if (i + 1 < argc && !strcmp(argv[i], "--measure-from")) measure_from = (unsigned)atoi(argv[++i]);
        else if (!strcmp(argv[i], "--reference")) rr_cps1_force_reference = rr_cps1_force_z80_reference = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--pcm")) pcm_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-state")) save_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-at")) save_at = (unsigned)atoi(argv[++i]);
        else if (i + 2 < argc && !strcmp(argv[i], "--checkpoint") && checkpoint_count < 8) {
            unsigned at = (unsigned)atoi(argv[++i]);
            if (!at || at > 1000000) return 2;
            checkpoints[checkpoint_count].frame = at; checkpoints[checkpoint_count++].path = argv[++i];
        }
        else if (i + 1 < argc && !strcmp(argv[i], "--load-state")) load_path = argv[++i];
        else if (!strcmp(argv[i], "--ignore-load-error")) ignore_load_error = 1;
        /* Development checks only (conversions keep the defaults): DSWA,DSWB,DSWC. */
        else if (i + 1 < argc && !strcmp(argv[i], "--dips")) {
            unsigned a, b, c;
            if (sscanf(argv[++i], "%i,%i,%i", (int *)&a, (int *)&b, (int *)&c) != 3 || (a | b | c) > 0xffff) return 2;
            dips[0] = (uint16_t)a; dips[1] = (uint16_t)b; dips[2] = (uint16_t)c; dips_given = 1;
        }
        else if (i + 1 < argc && !strcmp(argv[i], "--trace")) trace_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture")) capture_dir = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture-every")) capture_every = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--script")) { if (!load_script(argv[++i])) return 2; }
        else return 2;
    }
    if (frames < 0 || frames > 1000000 || !capture_every || (headless && !frames)) return 2;
    /* Normal play keeps honest native/fallback counters, without coverage
     * discovery or per-pixel hashing; qualification reports keep both. */
    diagnostics = (report_path && !performance_only) || trace_path;
    rr_cps1_observe = diagnostics;
    rr_feedback_start(!headless);
    if (SDL_Init(SDL_INIT_TIMER)) return 3;
    performance_frequency = SDL_GetPerformanceFrequency();
    static const char *const names[] = {"board.txt", "maincpu.bin", "audiocpu.bin", "gfx.bin", "oki.bin", "stars.bin"};
    Region regions[6] = {{0}};
    uint8_t *content = NULL;
    if (!unpack(&content, regions, names, 6) || !regions[0].data || !regions[1].data || !regions[2].data ||
        !regions[3].data || !regions[4].data) { SDL_Quit(); return 3; }
    char *text = malloc(regions[0].size + 1);
    if (!text) { free(content); SDL_Quit(); return 3; }
    memcpy(text, regions[0].data, regions[0].size); text[regions[0].size] = 0;
    cps1_board board;
    char error[256];
    int parsed = cps1_board_parse(&board, text, error, sizeof error);
    free(text);
    if (!parsed) { fprintf(stderr, "%s\n", error); free(content); SDL_Quit(); return 3; }
    cps1_regions rom = {regions[1].data, regions[1].size, regions[2].data, regions[2].size, regions[3].data,
                        regions[3].size, regions[4].data, regions[4].size, regions[5].data, regions[5].size};
    if (!cps1_init(&board, &rom)) { free(content); SDL_Quit(); return 3; }
    if (dips_given) rr_cps1_set_dip_values(dips);
    rr_cps1_apply_pads(0, 0);
    if (pcm_path && !(pcm = file_open(pcm_path, L"wb"))) return 3;
    if (trace_path) {
        if (!(trace_file = file_open(trace_path, L"wb"))) return 3;
        fprintf(trace_file, "frame,cpu,ram,image,pcm,samples\n");
    }
    if (load_path) {
        state_loaded = state_file(load_path, 1);
        load_rejected = !state_loaded;
        if (!state_loaded && !ignore_load_error) return 4;
    }
    uint64_t begun = SDL_GetPerformanceCounter();
    int host_result = 0;
    if (headless) {
        for (int n = 0; n < frames; n++) {
            if (scripted) scripted_pads();
            step_frame();
        }
        loop_wall_seconds = (double)(SDL_GetPerformanceCounter() - begun) / (double)performance_frequency;
    } else {
        host_result = rr16_sdl_main(RR_CPS1_TITLE, rr_cps1_rotated() ? 2 : 3);
        rr16_shutdown();
    }
    if (save_path && !save_at && !state_file(save_path, 0)) save_failed = 1;
    int okay = report(board.set) && !save_failed && !host_result;
    if (pcm && fclose(pcm)) okay = 0;
    if (trace_file && fclose(trace_file)) okay = 0;
    cps1_shutdown();
    free(content);
    SDL_Quit();
    return okay ? 0 : 3;
}

#ifdef _WIN32
int main(void)
{
    int argc = 0;
    wchar_t **wide_argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    char **argv = calloc((size_t)argc, sizeof *argv);
    if (!wide_argv || !argv) return 3;
    for (int i = 0; i < argc; i++) {
        int n = WideCharToMultiByte(CP_UTF8, 0, wide_argv[i], -1, NULL, 0, NULL, NULL);
        argv[i] = malloc(n);
        WideCharToMultiByte(CP_UTF8, 0, wide_argv[i], -1, argv[i], n, NULL, NULL);
    }
    int result = execute(argc, argv);
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "CPS-1", "Unable to start this CPS-1 game.", NULL);
    for (int i = 0; i < argc; i++) free(argv[i]);
    free(argv);
    LocalFree(wide_argv);
    return result;
}
#else
int main(int argc, char **argv)
{
    int result = execute(argc, argv);
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "CPS-1", "Unable to start this CPS-1 game.", NULL);
    return result;
}
#endif
