/* PlayStation game: the player's disc appended to this executable, run on Beetle PSX (psx_session.c) with the player's BIOS
 * embedded as resource 104 (none: OpenBIOS, built into the core). Windowed play goes through the host kit
 * (adapters/rrhk_psx.c); the converter's checks run the same executable headless. Nothing is written unless asked for on the
 * command line, except the memory card of slot 1 in the game's data folder.
 * Original Retro-Recomp code, MIT; linked with Beetle PSX, the program is GPL-2.0 as a whole (licenses/beetle-psx.md). */
#define WIN32_LEAN_AND_MEAN
#include "platform_io.h"
#include "embedded_resources.h"
#ifdef _WIN32
#include <shellapi.h>
#else
#include <unistd.h>
#endif
#include <SDL.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "console16_state.h"
#include "retro16_state_config.h"
#include "psx_game.h"
#include "psx_session.h"

int rr_psx_sdl_main(const char *title, int scale);

#define FNV_BASIS 14695981039346656037ull
#define FNV_PRIME 1099511628211ull
#define BIOS_RESOURCE 104
#define MAX_SCRIPT 65536

static RrPsxSession *session;
static unsigned frame;
static int headless, frames, scripted, diagnostics;
static const char *report_path, *trace_path, *save_path, *load_path, *capture_dir, *pack_override;
#ifdef RR_PSX_OBSERVE
static const char *observe_path;
int rr_psx_observe_write(FILE *f);    /* psx_observe.c: the conversion's observing build only */
#endif
static unsigned save_at, capture_every = 600;
static int state_loaded, load_rejected, save_failed;
static FILE *trace_file;
static uint64_t pcm_hash = FNV_BASIS, image_hash = FNV_BASIS, samples, nonzero;
static unsigned nonuniform_frames;
static char fault[256];
typedef struct { unsigned frame, pads[2]; } Input;
static Input *script;
static unsigned script_count, script_pos;
static uint16_t script_pads[2];
static int16_t frame_audio[2 * 8192];
static size_t frame_audio_count, audio_read;
static wchar_t card_path[4096];
static uint64_t card_hash;

RrPsxSession *rr_psx_host_session(void) { return session; }

static FILE *file_open(const char *path, const wchar_t *mode) {
    wchar_t name[4096];
    return rr_from_utf8(path, name, 4096) ? rr_fopen(name, mode) : NULL;
}

static int state_file(const char *path, int load) {
    wchar_t name[4096];
    return rr_from_utf8(path, name, 4096) && rr16_state_file(name, load != 0);
}

/* "frame p1 p2": the pad words (hex, the session's bits), held from that frame on. */
static int load_script(const char *path) {
    FILE *f = file_open(path, L"rb");
    if (!f) return 0;
    if (!(script = (Input *)calloc(MAX_SCRIPT, sizeof *script))) { fclose(f); return 0; }
    char line[256];
    unsigned last = 0;
    while (fgets(line, sizeof line, f)) {
        if (line[0] == '#' || line[0] == '\n' || line[0] == '\r') continue;
        if (script_count >= MAX_SCRIPT) { fclose(f); return 0; }
        Input *row = &script[script_count];
        if (sscanf(line, "%u %x %x", &row->frame, &row->pads[0], &row->pads[1]) != 3 || row->frame < last ||
            row->pads[0] > 0xffff || row->pads[1] > 0xffff) { fclose(f); return 0; }
        last = row->frame;
        script_count++;
    }
    fclose(f);
    scripted = 1;
    return script_count != 0;
}

static uint64_t fnv(const void *data, size_t size, uint64_t h) {
    const uint8_t *p = (const uint8_t *)data;
    for (size_t i = 0; i < size; ++i) h = (h ^ p[i]) * FNV_PRIME;
    return h;
}

/* The memory card of slot 1 is written to the game's data folder when it changed (the core keeps it in memory). */
static void card_sync(int load) {
    size_t size = 0;
    uint8_t *card = rr_psx_card(session, &size);
    if (!card || !size || !card_path[0]) return;
    if (load) {
        FILE *f = rr_fopen(card_path, L"rb");
        if (f) {
            /* A card of another size is not this machine's: it is left alone, never loaded and never overwritten. */
            fseek(f, 0, SEEK_END);
            long n = ftell(f);
            fseek(f, 0, SEEK_SET);
            if (n == (long)size && fread(card, 1, size, f) != size) memset(card, 0, size);
            if (n != (long)size) card_path[0] = 0;
            fclose(f);
        }
        card_hash = fnv(card, size, FNV_BASIS);
        return;
    }
    uint64_t h = fnv(card, size, FNV_BASIS);
    if (h == card_hash) return;
    wchar_t temporary[4100], folder[4096];
    /* datas/ and datas/saves/ beside the game, created on the first write. */
    wcsncpy(folder, card_path, 4095);
    folder[4095] = 0;
    for (int level = 0; level < 2; ++level) {
        wchar_t *slash = wcsrchr(folder, L'/');
        wchar_t *back = wcsrchr(folder, L'\\');
        if (back > slash) slash = back;
        if (!slash) break;
        *slash = 0;
    }
    rr_mkdir(folder);
    wcsncpy(folder, card_path, 4095);
    {
        wchar_t *slash = wcsrchr(folder, L'/'), *back = wcsrchr(folder, L'\\');
        if (back > slash) slash = back;
        if (slash) { *slash = 0; rr_mkdir(folder); }
    }
    swprintf(temporary, 4100, L"%ls.tmp", card_path);
    FILE *f = rr_fopen(temporary, L"wb");
    if (!f) return;
    int ok = fwrite(card, 1, size, f) == size;
    ok = (fclose(f) == 0) && ok;
    if (ok && rr_replace(temporary, card_path)) card_hash = h;
}

/* One frame with the pads of the script or of the window; 0 when the machine stopped. */
int rr_psx_host_frame(const uint16_t pads[2]) {
    unsigned words[2] = {pads[0], pads[1]};
    if (scripted) {
        while (script_pos < script_count && script[script_pos].frame <= frame) {
            script_pads[0] = (uint16_t)script[script_pos].pads[0];
            script_pads[1] = (uint16_t)script[script_pos].pads[1];
            script_pos++;
        }
        words[0] = script_pads[0];
        words[1] = script_pads[1];
    }
    rr_psx_pad(session, 0, words[0], NULL);
    rr_psx_pad(session, 1, words[1], NULL);
    if (rr_psx_frame(session) != 0) { snprintf(fault, sizeof fault, "%s", rr_psx_error(session)); return 0; }
    frame++;
    frame_audio_count = rr_psx_audio(session, frame_audio, sizeof frame_audio / sizeof frame_audio[0] / 2) * 2;
    audio_read = 0;
    if (diagnostics) {
        RrPsxFrameInfo info;
        rr_psx_frame_info(session, &info);
        image_hash = (image_hash ^ info.video) * FNV_PRIME;
        pcm_hash = (pcm_hash ^ info.pcm) * FNV_PRIME;
        samples += info.samples;
        for (size_t n = 0; n < frame_audio_count; n++) nonzero += frame_audio[n] != 0;
        if (info.nonblack) nonuniform_frames++;
        if (trace_file)
            fprintf(trace_file, "%u,%016llx,%016llx,%016llx,%u,%d,%dx%d\n", frame, (unsigned long long)info.ram,
                    (unsigned long long)info.video, (unsigned long long)info.pcm, info.samples, info.audible, info.width,
                    info.height);
    }
    if (save_path && save_at == frame && !state_file(save_path, 0)) save_failed = 1;
    if (capture_dir && !(frame % capture_every)) {
        char path[4096];
        int w, h;
        const uint32_t *pixels = rr_psx_picture(session, &w, &h, NULL);
        snprintf(path, sizeof path, "%s/frame-%06u.ppm", capture_dir, frame);
        FILE *image = file_open(path, L"wb");
        if (!image) { snprintf(fault, sizeof fault, "picture capture failed"); return 0; }
        fprintf(image, "P6\n%d %d\n255\n", w, h);
        for (int i = 0; i < w * h; i++) {
            unsigned char rgb[3] = {(unsigned char)(pixels[i] >> 16), (unsigned char)(pixels[i] >> 8), (unsigned char)pixels[i]};
            fwrite(rgb, 1, 3, image);
        }
        if (fclose(image)) { snprintf(fault, sizeof fault, "picture capture failed"); return 0; }
    }
    if (!headless && !(frame % 300)) card_sync(0);
    return 1;
}

size_t rr_psx_take_audio(int16_t *out, size_t capacity) {
    size_t count = frame_audio_count - audio_read;
    if (count > capacity) count = capacity & ~(size_t)1;
    memcpy(out, frame_audio + audio_read, count * sizeof *out);
    audio_read += count;
    return count;
}
unsigned rr_psx_frame_index(void) { return frame; }

static int open_session(void);
int rr_psx_host_reset(void) {
    card_sync(0);
    rr_psx_close(session);
    session = NULL;
    frame = 0; script_pos = 0; memset(script_pads, 0, sizeof script_pads);
    frame_audio_count = audio_read = 0;
    return open_session();
}

/* ------------------------------------------------------------ quick states (console16_state.c) */

enum { STATE_HEADER = 16 };
static void put32(uint8_t *p, uint32_t v) { for (unsigned n = 0; n < 4; n++) p[n] = (uint8_t)(v >> (8 * n)); }
static uint32_t get32(const uint8_t *p) { uint32_t v = 0; for (unsigned n = 0; n < 4; n++) v |= (uint32_t)p[n] << (8 * n); return v; }

bool rr16_state_ready(void) { return true; }   /* a frame ends with the CPU between instructions */
uint8_t *rr16_state_capture(size_t *size) {
    size_t machine = 0;
    uint8_t *payload = rr_psx_state_capture(session, &machine);
    if (!size || !payload || !machine || machine > (64u << 20)) { free(payload); return NULL; }
    uint8_t *data = (uint8_t *)malloc(STATE_HEADER + machine);
    if (!data) { free(payload); return NULL; }
    memcpy(data, "RRPSXST2", 8);
    put32(data + 8, frame);
    put32(data + 12, (uint32_t)machine);
    memcpy(data + STATE_HEADER, payload, machine);
    free(payload);
    *size = STATE_HEADER + machine;
    return data;
}
bool rr16_state_restore(const uint8_t *data, size_t size) {
    if (!data || size < STATE_HEADER || memcmp(data, "RRPSXST2", 8) || get32(data + 12) != size - STATE_HEADER) return false;
    if (rr_psx_state_restore(session, data + STATE_HEADER, size - STATE_HEADER) != 0) return false;
    frame = get32(data + 8);
    script_pos = 0; memset(script_pads, 0, sizeof script_pads);
    while (script_pos < script_count && script[script_pos].frame < frame) {
        script_pads[0] = (uint16_t)script[script_pos].pads[0];
        script_pads[1] = (uint16_t)script[script_pos].pads[1];
        script_pos++;
    }
    frame_audio_count = audio_read = 0;
    return true;
}

/* ------------------------------------------------------------ the session and the report */

static int self_path(char *out, size_t capacity) {
#ifdef _WIN32
    wchar_t wide[4096];
    DWORD n = GetModuleFileNameW(NULL, wide, 4096);
    return n > 0 && n < 4096 && rr_to_utf8(wide, out, capacity);
#else
    ssize_t n = readlink("/proc/self/exe", out, capacity - 1);
    if (n <= 0) return 0;
    out[n] = 0;
    return 1;
#endif
}

static int open_session(void) {
    char pack[4096];
    size_t bios_size = 0;
    const uint8_t *bios = (const uint8_t *)rr_resource(BIOS_RESOURCE, &bios_size);
    if (bios && bios_size != RR_PSX_BIOS_BYTES) bios = NULL;
    if (pack_override) snprintf(pack, sizeof pack, "%s", pack_override);
    else if (!self_path(pack, sizeof pack)) { snprintf(fault, sizeof fault, "cannot find this executable's path"); return 0; }
    RrPsxGame game = {pack, bios, NULL, 0};
    session = rr_psx_open(&game, fault, sizeof fault);
    if (!session) return 0;
    if (!headless) card_sync(1);
    return 1;
}

static int report(void) {
    if (!report_path) return 1;
    FILE *f = file_open(report_path, L"wb");
    if (!f) return 0;
    char escaped[sizeof fault * 2];
    size_t e = 0;
    for (size_t n = 0; fault[n] && e + 2 < sizeof escaped; n++) {
        char c = fault[n];
        if (c == '"' || c == '\\') escaped[e++] = '\\';
        escaped[e++] = (c >= 32 && c < 127) ? c : '?';
    }
    escaped[e] = 0;
    size_t bios_size = 0;
    int player_bios = rr_resource(BIOS_RESOURCE, &bios_size) != NULL && bios_size == RR_PSX_BIOS_BYTES;
    fprintf(f, "{\"stage\":\"psx\",\"frames\":%u,\"interpreted_instructions\":%llu,\"native_instructions\":%llu,\"unrun_fetches\":%llu,"
               "\"bios\":\"%s\",\"discs\":%d,\"image_hash\":\"%016llx\",\"pcm_hash\":\"%016llx\",\"pcm_samples\":%llu,"
               "\"nonzero_samples\":%llu,\"nonuniform_frames\":%u,\"pcm_rate\":%u,\"pcm_channels\":2,"
               "\"state_loaded\":%s,\"load_rejected\":%s,\"save_failed\":%s,\"fault\":\"%s\"}\n",
            frame, (unsigned long long)(session ? rr_psx_interpreted(session) : 0),
            (unsigned long long)(session ? rr_psx_native(session) : 0),
            (unsigned long long)(session ? rr_psx_unrun(session) : 0), player_bios ? "player" : "free",
            session ? rr_psx_disc_count(session) : 0, (unsigned long long)image_hash, (unsigned long long)pcm_hash,
            (unsigned long long)samples, (unsigned long long)nonzero, nonuniform_frames, RR_PSX_AUDIO_RATE,
            state_loaded ? "true" : "false", load_rejected ? "true" : "false", save_failed ? "true" : "false", escaped);
    int okay = !ferror(f);
    return fclose(f) == 0 && okay;
}

static int execute(int argc, char **argv) {
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--headless")) headless = 1;
        else if (i + 1 < argc && !strcmp(argv[i], "--frames")) frames = atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--report")) report_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-state")) save_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--save-at")) save_at = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--load-state")) load_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--trace")) trace_path = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture")) capture_dir = argv[++i];
        else if (i + 1 < argc && !strcmp(argv[i], "--capture-every")) capture_every = (unsigned)atoi(argv[++i]);
        else if (i + 1 < argc && !strcmp(argv[i], "--pack")) pack_override = argv[++i];
#ifdef RR_PSX_OBSERVE
        else if (i + 1 < argc && !strcmp(argv[i], "--observe")) observe_path = argv[++i];
#endif
        else if (i + 1 < argc && !strcmp(argv[i], "--script")) { if (!load_script(argv[++i])) return 2; }
        else return 2;
    }
    if (frames < 0 || frames > 1000000 || (headless && !frames) || !capture_every) return 2;
    diagnostics = report_path || trace_path;
    if (!headless) rr_game_data_file(card_path, 4096, "saves", RR16_STATE_NAME, RR16_STATE_ROM, ".mcr");
    if (SDL_Init(SDL_INIT_TIMER)) return 3;
    if (!open_session()) { fprintf(stderr, "%s\n", fault[0] ? fault : "no PlayStation disc in this executable"); SDL_Quit(); return 3; }
    if (trace_path) {
        if (!(trace_file = file_open(trace_path, L"wb"))) return 3;
        fprintf(trace_file, "frame,ram,image,pcm,samples,audible,size\n");
    }
    if (load_path) {
        state_loaded = state_file(load_path, 1);
        load_rejected = !state_loaded;
        if (!state_loaded) return 4;
    }
    int ran = 1, host_result = 0;
    if (headless) {
        static const uint16_t released[2];
        for (int n = 0; n < frames && ran; n++) ran = rr_psx_host_frame(released);
    } else {
        host_result = rr_psx_sdl_main(RR_PSX_TITLE, 3);
        ran = !fault[0];
        card_sync(0);
    }
    if (save_path && !save_at && !state_file(save_path, 0)) save_failed = 1;
    if (!ran) fprintf(stderr, "%s\n", fault);
    int okay = report() && ran && !save_failed && !host_result;
#ifdef RR_PSX_OBSERVE
    if (observe_path) {
        FILE *f = file_open(observe_path, L"wb");
        if (!f || !rr_psx_observe_write(f)) okay = 0;
        if (f && fclose(f)) okay = 0;
    }
#endif
    if (trace_file && fclose(trace_file)) okay = 0;
    rr_psx_close(session);
    SDL_Quit();
    return okay ? 0 : 3;
}

#ifdef _WIN32
int main(void) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
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
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "PlayStation", "Unable to start this PlayStation game.", NULL);
    for (int i = 0; i < argc; i++) free(argv[i]);
    free(argv);
    LocalFree(wide_argv);
    return result;
}
#else
int main(int argc, char **argv) {
    int result = execute(argc, argv);
    if (result && argc == 1) SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "PlayStation", "Unable to start this PlayStation game.", NULL);
    return result;
}
#endif
