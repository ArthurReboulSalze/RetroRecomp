/* PC Engine game: the HuCard on the pinned pcenginerecomp runtime (pce_machine.cpp), native code from the
 * game's emitted module with every interpreted instruction counted. Windowed play goes through the host kit
 * (adapters/rrhk_pce.c); the converter's checks run the same executable headless. No user data or diagnostics
 * are written unless explicitly asked for on the command line, except, in a window, the player's own record
 * (native/runtime_feedback.c, F12 switches it off): numbers about what the interpreter ran, for the next conversion.
 * Original RetroRecomp code: MIT; the engine keeps its own MIT terms (licenses/pcenginerecomp.md). */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include "embedded_resources.h"
#ifdef _WIN32
#include <shellapi.h>
#endif
#include <SDL.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console16_state.h"
#include "retro16_state_config.h"
#include "pce_game.h"
#include "pce_machine.h"
#include "pce_backup.h"
#include "runtime_i18n.h"
#include "runtime_feedback.h"

int rr_pce_sdl_main(const char *title, int scale);
void rrhk_notice(const char *text, Uint64 milliseconds);

#define FNV_BASIS 14695981039346656037ull
#define FNV_PRIME 1099511628211ull

static unsigned frame;
static int headless, frames, scripted, diagnostics, reference, native_only;
static const char *report_path, *trace_path, *save_path, *load_path, *pcm_path, *code_capture_path, *capture_dir, *backup_path;
static unsigned save_at, capture_every = 600, capture_limit;
static uint64_t backup_start_hash;
static int ignore_load_error, state_loaded, load_rejected, save_failed;
static FILE *trace_file, *pcm;
static uint64_t pcm_hash = FNV_BASIS, image_hash = FNV_BASIS, samples, nonzero, energy;
static unsigned peak, nonuniform_frames;
static char fault[256];
static uint64_t capture_identities, capture_dropped, capture_first_drop_frame;
typedef struct { unsigned frame, pads[4]; } Input;
static Input script[8192];
static unsigned script_count, script_pos;
static uint16_t script_pads[4];
static int16_t frame_audio[48000];
static size_t frame_audio_count, audio_read;

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

/* "frame p1 p2 [p3 p4]": the engine's 12-bit pad masks in hex, held from that frame on. */
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
        row->pads[2] = row->pads[3] = 0;
        int fields = sscanf(line, "%u %x %x %x %x", &row->frame, &row->pads[0], &row->pads[1], &row->pads[2], &row->pads[3]);
        if ((fields != 3 && fields != 5) || row->frame < last || row->pads[0] > 0xfff || row->pads[1] > 0xfff ||
            row->pads[2] > 0xfff || row->pads[3] > 0xfff) { fclose(f); return 0; }
        last = row->frame;
        script_count++;
    }
    fclose(f);
    scripted = 1;
    return script_count != 0;
}

static uint64_t backup_hash(void)
{
    const uint8_t *memory = pce_machine_backup();
    uint64_t hash = FNV_BASIS;
    for (unsigned n = 0; memory && n < PCE_BACKUP_BYTES; n++) hash = (hash ^ memory[n]) * FNV_PRIME;
    return hash;
}

static uint64_t picture_hash(void)
{
    unsigned width, height;
    const uint32_t *pixels = pce_machine_pixels(&width, &height);
    uint64_t hash = FNV_BASIS;
    hash = (hash ^ width) * FNV_PRIME;
    hash = (hash ^ height) * FNV_PRIME;
    int uniform = 1;
    for (unsigned y = 0; y < height; y++)
        for (unsigned x = 0; x < width; x++) {
            uint32_t value = pixels[y * PCE_MAX_WIDTH + x];
            for (unsigned b = 0; b < 4; b++) hash = (hash ^ ((value >> (8 * b)) & 0xffu)) * FNV_PRIME;
            if (value != pixels[0]) uniform = 0;
        }
    if (!uniform && width && height) nonuniform_frames++;
    return hash;
}

/* One frame of the machine with the pads of the script or of the window; 0 on an engine fault. */
int rr_pce_host_frame(const uint16_t pads[4])
{
    uint16_t masks[PCE_PADS] = {0};
    if (scripted) {
        while (script_pos < script_count && script[script_pos].frame <= frame) {
            for (int p = 0; p < 4; p++) script_pads[p] = (uint16_t)script[script_pos].pads[p];
            script_pos++;
        }
        memcpy(masks, script_pads, sizeof script_pads);
    } else {
        memcpy(masks, pads, 4 * sizeof *pads);
    }
    pce_machine_set_pads(masks);
    if (!pce_machine_run_frame(fault, sizeof fault)) return 0;
    frame++;
    if (!headless) {
        /* A save the game could not use never stops it: it is set aside, the game starts formatted, the player is told once. */
        static int told;
        if (!told) {
            told = 1;
            unsigned state = rr_pce_backup_notice();
            if (state == 1) rrhk_notice(rr_tr("Save unreadable: set aside"), 6000);
            else if (state == 2) rrhk_notice(rr_tr("Save unreadable: saving is off"), 6000);
        }
        rr_pce_backup_flush(SDL_GetTicks64(), false);
    }
    frame_audio_count = pce_machine_audio(frame_audio, sizeof frame_audio / sizeof *frame_audio);
    audio_read = 0;
    uint64_t image = 0, sound = FNV_BASIS;
    if (diagnostics) {
        image = picture_hash();
        image_hash = (image_hash ^ image) * FNV_PRIME;
        for (size_t n = 0; n < frame_audio_count; n++) {
            int sample = frame_audio[n], magnitude = sample < 0 ? -sample : sample;
            pcm_hash = (pcm_hash ^ (uint16_t)sample) * FNV_PRIME;
            sound = (sound ^ (uint16_t)sample) * FNV_PRIME;
            samples++; nonzero += sample != 0;
            energy += (uint64_t)((int64_t)sample * sample);
            if ((unsigned)magnitude > peak) peak = (unsigned)magnitude;
        }
    }
    if (pcm && fwrite(frame_audio, sizeof *frame_audio, frame_audio_count, pcm) != frame_audio_count) {
        snprintf(fault, sizeof fault, "PCM write failed"); return 0;
    }
    if (trace_file)
        fprintf(trace_file, "%u,%016llx,%016llx,%016llx,%016llx,%llu\n", frame,
                (unsigned long long)pce_machine_cpu_hash(), (unsigned long long)pce_machine_ram_hash(),
                (unsigned long long)image, (unsigned long long)sound, (unsigned long long)frame_audio_count);
    if (save_path && save_at == frame && !state_file(save_path, 0)) save_failed = 1;
    if (capture_dir && !(frame % capture_every)) {
        /* A binary PPM of the visible picture: headless checks look at it, no window is opened. */
        char path[4096];
        unsigned width, height;
        const uint32_t *pixels = pce_machine_pixels(&width, &height);
        snprintf(path, sizeof path, "%s/frame-%06u.ppm", capture_dir, frame);
        FILE *image = file_open(path, L"wb");
        if (!image) { snprintf(fault, sizeof fault, "picture capture failed"); return 0; }
        fprintf(image, "P6\n%u %u\n255\n", width, height);
        for (unsigned y = 0; y < height; y++)
            for (unsigned x = 0; x < width; x++) {
                uint32_t value = pixels[y * PCE_MAX_WIDTH + x];
                unsigned char rgb[3] = {(unsigned char)(value >> 16), (unsigned char)(value >> 8), (unsigned char)value};
                fwrite(rgb, 1, 3, image);
            }
        if (fclose(image)) { snprintf(fault, sizeof fault, "picture capture failed"); return 0; }
    }
    return 1;
}

/* The PCM of the last frame, read once by the window's audio. */
size_t rr_pce_take_audio(int16_t *out, size_t capacity)
{
    size_t count = frame_audio_count - audio_read;
    if (count > capacity) count = capacity & ~(size_t)1;
    memcpy(out, frame_audio + audio_read, count * sizeof *out);
    audio_read += count;
    return count;
}
unsigned rr_pce_frame_index(void) { return frame; }
const char *rr_pce_fault(void) { return fault; }
int rr_pce_reset(void)
{
    frame = 0; script_pos = 0; memset(script_pads, 0, sizeof script_pads);
    frame_audio_count = audio_read = 0;
    return pce_machine_reset(fault, sizeof fault);
}

/* ------------------------------------------------------------ quick states (console16_state.c) */

enum { STATE_HEADER = 16 };
static void put32(uint8_t *p, uint32_t v) { for (unsigned n = 0; n < 4; n++) p[n] = (uint8_t)(v >> (8 * n)); }
static uint32_t get32(const uint8_t *p) { uint32_t v = 0; for (unsigned n = 0; n < 4; n++) v |= (uint32_t)p[n] << (8 * n); return v; }

/* Frames end on a published picture, with the CPU between instructions. */
bool rr16_state_ready(void) { return true; }
uint8_t *rr16_state_capture(size_t *size)
{
    size_t machine = 0;
    uint8_t *payload = pce_machine_state_save(&machine);
    if (!size || !payload || !machine || machine > (24u << 20)) { pce_machine_free(payload); return NULL; }
    uint8_t *data = malloc(STATE_HEADER + machine);
    if (!data) { pce_machine_free(payload); return NULL; }
    memcpy(data, "RRPCEST1", 8);
    put32(data + 8, frame);
    put32(data + 12, (uint32_t)machine);
    memcpy(data + STATE_HEADER, payload, machine);
    pce_machine_free(payload);
    *size = STATE_HEADER + machine;
    return data;
}
bool rr16_state_restore(const uint8_t *data, size_t size)
{
    if (!data || size < STATE_HEADER || memcmp(data, "RRPCEST1", 8) || get32(data + 12) != size - STATE_HEADER)
        return false;
    if (!pce_machine_state_load(data + STATE_HEADER, size - STATE_HEADER)) return false;
    frame = get32(data + 8);
    script_pos = 0; memset(script_pads, 0, sizeof script_pads);
    while (script_pos < script_count && script[script_pos].frame < frame) {
        for (int p = 0; p < 4; p++) script_pads[p] = (uint16_t)script[script_pos].pads[p];
        script_pos++;
    }
    frame_audio_count = audio_read = 0;
    return true;
}

/* ------------------------------------------------------------ the report */

static int report(void)
{
    if (!report_path) return 1;
    FILE *f = file_open(report_path, L"wb");
    if (!f) return 0;
    PceCounters counters;
    pce_machine_counters(&counters);
    char escaped[sizeof fault * 2];
    size_t e = 0;
    for (size_t n = 0; fault[n] && e + 2 < sizeof escaped; n++) {
        char c = fault[n];
        if (c == '"' || c == '\\') escaped[e++] = '\\';
        escaped[e++] = (c >= 32 && c < 127) ? c : '?';
    }
    escaped[e] = 0;
    fprintf(f, "{\"stage\":\"pce\",\"board\":\"%s\",\"frames\":%u,\"native_instructions\":%llu,"
               "\"interpreted_instructions\":%llu,\"guard_misses\":%llu,\"irq_entries\":%llu,\"reference\":%s,"
               "\"native_only\":%s,\"image_hash\":\"%016llx\",\"pcm_hash\":\"%016llx\",\"pcm_samples\":%llu,"
               "\"nonzero_samples\":%llu,\"peak\":%u,\"rms\":%.4f,\"nonuniform_frames\":%u,\"pcm_rate\":%u,"
               "\"pcm_channels\":2,\"cpu_hash\":\"%016llx\",\"ram_hash\":\"%016llx\",\"cropped_frames\":%llu,"
               "\"state_loaded\":%s,\"load_rejected\":%s,\"save_failed\":%s,\"capture_identities\":%llu,"
               "\"capture_dropped\":%llu,\"capture_first_drop_frame\":%llu,\"backup_start_hash\":\"%016llx\","
               "\"backup_hash\":\"%016llx\",\"backup_beyond\":%u,\"backup_notice\":%u,\"fault\":\"%s\"}\n",
            RR_PCE_BOARD == PCE_BOARD_SF2 ? "sf2" : "base", frame, (unsigned long long)counters.native,
            (unsigned long long)counters.interpreted, (unsigned long long)counters.guard_misses,
            (unsigned long long)counters.irq_entries, reference ? "true" : "false", native_only ? "true" : "false",
            (unsigned long long)image_hash, (unsigned long long)pcm_hash, (unsigned long long)samples,
            (unsigned long long)nonzero, peak, samples ? sqrt((double)energy / (double)samples) : 0.0,
            nonuniform_frames, PCE_AUDIO_RATE, (unsigned long long)pce_machine_cpu_hash(),
            (unsigned long long)pce_machine_ram_hash(), (unsigned long long)counters.cropped_frames,
            state_loaded ? "true" : "false", load_rejected ? "true" : "false", save_failed ? "true" : "false",
            (unsigned long long)capture_identities, (unsigned long long)capture_dropped,
            (unsigned long long)capture_first_drop_frame, (unsigned long long)backup_start_hash,
            (unsigned long long)backup_hash(), pce_machine_backup_beyond(), rr_pce_backup_notice(), escaped);
    int okay = !ferror(f);
    return fclose(f) == 0 && okay;
}

/* What the interpreter ran, as the host's recorder keeps it (kind 20). */
static void record_instruction(uint32_t pc, const uint8_t *bytes, unsigned size)
{
    rr_feedback_note(RR_FB_PCE, pc, 0, bytes, size);
}

static int execute(int argc, char **argv)
{
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--headless")) headless = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--frames")) frames = atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--report")) report_path = argv[++i];
        else if (!strcmp(argv[i], "--reference")) reference = 1;
        else if (!strcmp(argv[i], "--native-only")) native_only = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--pcm")) pcm_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-state")) save_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-at")) save_at = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--load-state")) load_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--backup")) backup_path = argv[++i];
        else if (!strcmp(argv[i], "--ignore-load-error")) ignore_load_error = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--trace")) trace_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture")) capture_dir = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture-every")) capture_every = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--code-capture")) code_capture_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture-limit")) capture_limit = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--script")) { if (!load_script(argv[++i])) return 2; }
        else return 2;
    }
    if (frames < 0 || frames > 1000000 || (headless && !frames) || (reference && native_only) || !capture_every) return 2;
    diagnostics = report_path || trace_path;
    if (SDL_Init(SDL_INIT_TIMER)) return 3;
    size_t size = 0;
    const uint8_t *rom = rr_resource(103, &size);
    if (!rom || !size || !pce_machine_init(rom, size, RR_PCE_COPIER_HEADER, RR_PCE_BIT_REVERSED, RR_PCE_BOARD,
                                           RR_PCE_PAD_BUTTONS, RR_PCE_MULTITAP, fault, sizeof fault)) {
        fprintf(stderr, "%s\n", fault[0] ? fault : "no HuCard in this executable");
        SDL_Quit();
        return 3;
    }
    pce_machine_policy(reference ? PCE_POLICY_REFERENCE : native_only ? PCE_POLICY_NATIVE_ONLY : PCE_POLICY_HYBRID);
    /* The player's own record: in a window by default (F12 switches it), in a headless run only with RETRO_RECOMP_FEEDBACK=1. Standard boards only:
     * the Street Fighter II board never records, so its F12 line stays off and the report says so. */
    if (RR_PCE_BOARD != PCE_BOARD_SF2) {
        rr_feedback_start(!headless);
        if (!reference && !native_only) pce_machine_set_recorder(record_instruction, rr_feedback_enabled);
    }
    /* The player's save: beside the game in a window. A headless run touches no file unless --backup names one. */
    static wchar_t backup_file[32768];
    if (backup_path) {
        wchar_t *name = wide(backup_path);
        rr_pce_backup_open(name);
        free(name);
    } else if (!headless && rr_pce_backup_path(backup_file, sizeof backup_file / sizeof *backup_file)) {
        rr_pce_backup_open(backup_file);
    }
    backup_start_hash = backup_hash();
    if (code_capture_path && !pce_machine_capture_begin(code_capture_path, capture_limit ? capture_limit : 65536, capture_limit != 0, fault, sizeof fault)) {
        fprintf(stderr, "%s\n", fault); SDL_Quit(); return 3;
    }
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
    int ran = 1, host_result = 0;
    if (headless) {
        static const uint16_t released[4];
        for (int n = 0; n < frames && ran; n++) ran = rr_pce_host_frame(released);
    } else {
        host_result = rr_pce_sdl_main(RR_PCE_TITLE, 3);
        ran = !fault[0];
    }
    if (save_path && !save_at && !state_file(save_path, 0)) save_failed = 1;
    rr_pce_backup_flush(SDL_GetTicks64(), true);
    if (code_capture_path) pce_machine_capture_status(&capture_identities, &capture_dropped, &capture_first_drop_frame);
    if (code_capture_path && !pce_machine_capture_finish(fault, sizeof fault)) ran = 0;
    if (!ran) fprintf(stderr, "%s\n", fault);
    int okay = report() && ran && !save_failed && !host_result;
    if (pcm && fclose(pcm)) okay = 0;
    if (trace_file && fclose(trace_file)) okay = 0;
    pce_machine_shutdown();
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
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "PC Engine", "Unable to start this PC Engine game.", NULL);
    for (int i = 0; i < argc; i++) free(argv[i]);
    free(argv);
    LocalFree(wide_argv);
    return result;
}
#else
int main(int argc, char **argv)
{
    int result = execute(argc, argv);
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "PC Engine", "Unable to start this PC Engine game.", NULL);
    return result;
}
#endif
