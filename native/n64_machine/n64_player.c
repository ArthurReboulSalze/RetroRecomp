/* Retro-Recomp Nintendo 64 player: the windowed game (host kit) and the headless runs the conversion validates with. Original
 * Retro-Recomp code, MIT; linked with Mupen64Plus-Next, the program is GPL-3.0 as a whole (licenses/mupen64plus-next.md).
 *
 * One executable for both: an exported game embeds its cartridge image (a resource); a development build reads it from a file
 * (`--rom FILE`, any of the three byte orders). Headless runs write one trace line per frame (the evidence the conversion
 * compares), a JSON report, the observed VR4300 code and a capture of the last picture; inputs come from a bounded event file
 * keyed on the machine's frame. The cartridge's saves and the controller paks are kept in the game's data folder (windowed play
 * only; a headless run writes nothing it was not asked for). */
#include <SDL.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "n64_session.h"
#include "platform_io.h"
#ifdef _WIN32
#include <windows.h>
#endif
#ifdef RR_N64_LINKED
#include "embedded_resources.h"
#include "n64_payload.h"
#endif
#ifndef RR_N64_STATE_ABI
#define RR_N64_STATE_ABI "n64-development"
#endif

#define PATH_CAP 2048
#define MAX_FRAMES 360000u
#define MAX_EVENTS 8192u

static RrN64Session *session;
static unsigned frame_limit, frame_number;
static bool quit_requested, restart_requested, failed;
static char state_slot[PATH_CAP], save_path[PATH_CAP];
static uint64_t save_hash;
static int16_t frame_audio[2 * 8192];
static size_t frame_audio_count, frame_audio_read;

static void fail(const char *message) {
    if (!failed) fprintf(stderr, "%s\n", message ? message : "failed");
    failed = true;
}
static void log_line(const char *line) { fputs(line, stderr); }

/* The kit's calls into the fallback-hint feedback: this experimental player records none yet. */
void rr_feedback_start(int gameplay) { (void)gameplay; }
int rr_feedback_enabled(void) { return 0; }
int rr_feedback_toggle(void) { return 0; }
const char *rr_feedback_label(void) { return "Fallback hints unavailable"; }
int rr_feedback_pending(void) { return 0; }
void rr_feedback_finish(void) {}
#if !defined(_WIN32) && !defined(RR_N64_LINKED)
const void *rr_resource(unsigned id, size_t *size) { (void)id; *size = 0; return NULL; }
#endif

static FILE *open_utf8(const char *path, const wchar_t *mode) {
    wchar_t wide[PATH_CAP];
    return rr_from_utf8(path, wide, PATH_CAP) ? rr_fopen(wide, mode) : NULL;
}

static uint8_t *read_file(const char *path, size_t *size, size_t limit) {
    FILE *f = open_utf8(path, L"rb");
    long n;
    uint8_t *data;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) || (n = ftell(f)) < 0 || (size_t)n > limit || fseek(f, 0, SEEK_SET)) { fclose(f); return NULL; }
    data = (uint8_t *)malloc((size_t)n + 1);
    if (data && fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); data = NULL; }
    fclose(f);
    *size = (size_t)n;
    return data;
}

static uint64_t fnv(const void *data, size_t size) {
    const uint8_t *p = (const uint8_t *)data;
    uint64_t h = 1469598103934665603ull;
    size_t i;
    for (i = 0; i < size; i++) h = (h ^ p[i]) * 1099511628211ull;
    return h;
}

/* The image in the console's own byte order: big-endian (.z64), byte-swapped pairs (.v64) and swapped words (.n64) are told
 * apart by the first word. 0: not an N64 image. */
static int to_big_endian(uint8_t *data, size_t size) {
    size_t i;
    if (size < 4 || size % 4) return 0;
    if (data[0] == 0x80 && data[1] == 0x37 && data[2] == 0x12 && data[3] == 0x40) return 1;
    if (data[0] == 0x37 && data[1] == 0x80 && data[2] == 0x40 && data[3] == 0x12) {
        for (i = 0; i < size; i += 2) { uint8_t t = data[i]; data[i] = data[i + 1]; data[i + 1] = t; }
        return 1;
    }
    if (data[0] == 0x40 && data[1] == 0x12 && data[2] == 0x37 && data[3] == 0x80) {
        for (i = 0; i < size; i += 4) {
            uint8_t a = data[i], b = data[i + 1];
            data[i] = data[i + 3]; data[i + 1] = data[i + 2]; data[i + 2] = b; data[i + 3] = a;
        }
        return 1;
    }
    return 0;
}

/* ---- quick states: the session captures and restores in memory, the player keeps the file ---- */
static int state_save(const char *slot) {
    uint8_t *data;
    size_t size;
    FILE *f;
    int ok;
    if (rr_n64_state_capture(session, RR_N64_STATE_ABI, &data, &size)) return 4;
    if (!(f = open_utf8(slot, L"wb"))) { free(data); return 4; }
    ok = fwrite(data, 1, size, f) == size;
    free(data);
    return fclose(f) == 0 && ok ? 0 : 4;
}

static int state_load(const char *slot) {
    size_t size;
    uint8_t *data = read_file(slot, &size, 256u << 20);
    int result;
    if (!data) return 1;
    result = rr_n64_state_restore(session, RR_N64_STATE_ABI, data, size);
    free(data);
    return result;
}

/* ---- the cartridge's saves and the paks: read before the first frame, written when they changed (windowed play) ---- */
static void saves_load(void) {
    size_t size = 0, got = 0;
    uint8_t *memory = rr_n64_save_memory(session, &size);
    uint8_t *data;
    if (!memory || !size || !save_path[0]) return;
    data = read_file(save_path, &got, size);
    /* A file of another size is not this machine's: it is left alone, never loaded and never overwritten. */
    if (data && got == size) memcpy(memory, data, size);
    else if (data) save_path[0] = 0;
    free(data);
    save_hash = fnv(memory, size);
}

static void saves_store(void) {
    size_t size = 0;
    uint8_t *memory = rr_n64_save_memory(session, &size);
    char temporary[PATH_CAP + 8];
    wchar_t from[PATH_CAP + 8], to[PATH_CAP];
    uint64_t h;
    FILE *f;
    int ok;
    if (!memory || !size || !save_path[0] || (h = fnv(memory, size)) == save_hash) return;
    snprintf(temporary, sizeof temporary, "%s.tmp", save_path);
    if (!(f = open_utf8(temporary, L"wb"))) return;
    ok = fwrite(memory, 1, size, f) == size;
    ok = fclose(f) == 0 && ok;
    if (ok && rr_from_utf8(temporary, from, PATH_CAP + 8) && rr_from_utf8(save_path, to, PATH_CAP) && rr_replace(from, to)) save_hash = h;
}

/* ---- what the adapter calls ---- */
static void player_inputs(int player, uint16_t word, const int16_t axes[4]) { rr_n64_pad(session, player, word, axes); }
static bool player_frame(void) {
    if (rr_n64_frame(session) != 0) { fail(rr_n64_error(session)); return false; }
    frame_number++;
    frame_audio_count = rr_n64_audio(session, frame_audio, sizeof frame_audio / sizeof frame_audio[0] / 2) * 2;
    frame_audio_read = 0;
    if (frame_number % 120 == 0) saves_store();
    return true;
}
/* The ring drains the frame's sound: `capacity` samples, returns stereo frames. */
static size_t player_audio(int16_t *pcm, size_t capacity) {
    size_t count = frame_audio_count - frame_audio_read;
    if (count > capacity) count = capacity & ~(size_t)1;
    memcpy(pcm, frame_audio + frame_audio_read, count * sizeof *pcm);
    frame_audio_read += count;
    return count / 2;
}

#ifdef RR_N64_WINDOWED
#include "hostkit/adapters/rrhk_n64.inc"
#else
static void n64_gfx_defaults(void) {}
static bool n64_gfx_assign(const char *assignment, bool windowed) { (void)assignment; (void)windowed; return false; }
#endif

/* Makes every folder of `path` (UTF-8). */
static bool make_dirs(const char *path) {
    char part[PATH_CAP];
    wchar_t wide[PATH_CAP];
    size_t n, len = strlen(path);
    if (len >= PATH_CAP) return false;
    for (n = 1; n <= len; n++) {
        if (n < len && path[n] != '/' && path[n] != '\\') continue;
        memcpy(part, path, n); part[n] = 0;
        if (n == 2 && part[1] == ':') continue;
        if (!rr_from_utf8(part, wide, PATH_CAP) || !rr_mkdir(wide)) return false;
    }
    return true;
}

/* ---- headless runs: the input events, the trace, the report ---- */
typedef struct { unsigned begin, end; char kind; int code, value; } Event;
static Event events[MAX_EVENTS];
static unsigned event_count;

/* "begin end kind code value" per line: kind pad (code = bit 0..13 of RR_N64_PAD_*, value = player 0..3) or stick (code = 4 *
 * player + axis: left X, left Y, right X, right Y; value -32768..32767); frames are the machine's own (absolute, so that a
 * resumed state sees the same inputs). */
static bool load_events(const char *path) {
    FILE *f = open_utf8(path, L"rb");
    char kind[8];
    unsigned begin, end;
    int code, value, fields;
    if (!f) return false;
    while ((fields = fscanf(f, "%u %u %7s %d %d", &begin, &end, kind, &code, &value)) == 5) {
        Event *e = &events[event_count];
        if (event_count >= MAX_EVENTS || begin >= end || end > MAX_FRAMES) { fclose(f); return false; }
        e->begin = begin; e->end = end; e->code = code; e->value = value;
        if (!strcmp(kind, "pad") && code >= 0 && code < 14 && value >= 0 && value < 4) e->kind = 'p';
        else if (!strcmp(kind, "stick") && code >= 0 && code < 16 && value >= -32768 && value <= 32767) e->kind = 's';
        else { fclose(f); return false; }
        event_count++;
    }
    fclose(f);
    return fields == EOF;
}

static void scripted_inputs(uint64_t frame) {
    unsigned bits[4] = {0, 0, 0, 0}, n;
    int16_t sticks[4][4];
    int p;
    memset(sticks, 0, sizeof sticks);
    for (n = 0; n < event_count; n++) {
        const Event *e = &events[n];
        if (frame < e->begin || frame >= e->end) continue;
        if (e->kind == 'p') bits[e->value] |= 1u << e->code;
        else sticks[e->code / 4][e->code % 4] = (int16_t)e->value;
    }
    for (p = 0; p < 4; p++) rr_n64_pad(session, p, bits[p], sticks[p]);
}

static bool write_capture(const char *path) {
    int w, h, i;
    const uint32_t *px = rr_n64_picture(session, &w, &h);
    FILE *f = open_utf8(path, L"wb");
    if (!f || !px) { if (f) fclose(f); return false; }
    fprintf(f, "P6\n%d %d\n255\n", w, h);
    for (i = 0; i < w * h; i++) {
        unsigned char rgb[3] = {(unsigned char)(px[i] >> 16), (unsigned char)(px[i] >> 8), (unsigned char)px[i]};
        fwrite(rgb, 1, 3, f);
    }
    return fclose(f) == 0;
}

static void json_text(FILE *f, const char *text) {
    const char *c;
    fputc('"', f);
    for (c = text ? text : ""; *c; c++) {
        if (*c == '"' || *c == '\\') fputc('\\', f);
        fputc((unsigned char)*c < 32 ? ' ' : *c, f);
    }
    fputc('"', f);
}

static int run_headless(const char *trace_path, const char *report_path, const char *capture_path, const char *observe_path,
                        const char *times_path, unsigned save_at, bool load_start) {
    FILE *trace = trace_path ? open_utf8(trace_path, L"wb") : NULL;
    FILE *times = times_path ? open_utf8(times_path, L"wb") : NULL;
    unsigned nonblack = 0, audible = 0, n;
    bool stopped = false;
    const char *error = "";
    const Uint64 frequency = SDL_GetPerformanceFrequency();
    if ((trace_path && !trace) || (times_path && !times)) { fail("Cannot write the trace"); return 1; }
    if (trace) fputs("frame\tvideo\tpcm\tram\tcpu\tPC\tsamples\tsize\n", trace);
    if (load_start && state_load(state_slot)) { fail("The quick state could not be loaded"); if (trace) fclose(trace); return 1; }
    for (n = 0; n < frame_limit; n++) {
        RrN64FrameInfo info;
        int16_t pcm[2 * 4096];
        const uint64_t frame = rr_n64_frame_index(session);
        Uint64 start;
        scripted_inputs(frame);
        start = SDL_GetPerformanceCounter();
        if (rr_n64_frame(session)) { stopped = true; error = rr_n64_error(session); break; }
        /* The frame's cost as the machine ran it (no pacing: a headless run is not a timing of play). */
        if (times) fprintf(times, "%llu\t%.4f\n", (unsigned long long)frame + 1,
                           1000.0 * (double)(SDL_GetPerformanceCounter() - start) / (double)frequency);
        rr_n64_frame_info(session, &info);
        nonblack += info.nonblack != 0;
        audible += info.audible != 0;
        if (trace)
            fprintf(trace, "%llu\t%016llx\t%016llx\t%016llx\t%016llx\t%08x\t%u\t%dx%d\n", (unsigned long long)info.frame,
                    (unsigned long long)info.video, (unsigned long long)info.pcm, (unsigned long long)info.ram,
                    (unsigned long long)info.cpu, info.pc, info.samples, info.width, info.height);
        while (rr_n64_audio(session, pcm, 4096)) {}
        if (save_at && info.frame == save_at && state_save(state_slot)) {
            fail("The quick state could not be saved"); stopped = true; error = "state save failed"; break;
        }
    }
    if (trace && fclose(trace)) { fail("Cannot write the trace"); return 1; }
    if (times && fclose(times)) { fail("Cannot write the frame times"); return 1; }
    if (capture_path && !write_capture(capture_path)) { fail("Cannot write the capture"); return 1; }
    if (observe_path) {
        FILE *o = open_utf8(observe_path, L"wb");
        if (!o || !rr_n64_observations_write(session, o) || fclose(o)) { fail("Cannot write the observations"); return 1; }
    }
    if (report_path) {
        FILE *r = open_utf8(report_path, L"wb");
        int w, h;
        if (!r) { fail("Cannot write the report"); return 1; }
        rr_n64_picture(session, &w, &h);
        fprintf(r, "{\"frames\":%u,\"stopped\":%s,\"error\":", n, stopped ? "true" : "false");
        json_text(r, error);
        fprintf(r, ",\"native\":%llu,\"interpreted\":%llu,\"block_entries\":%llu,\"guard_misses\":%llu,\"observed\":%llu,"
                   "\"nonblack_frames\":%u,\"audible_frames\":%u,\"fps\":%.4f,\"audio_rate\":%u,\"picture\":[%d,%d],"
                   "\"state_loaded\":%s,\"gpu\":",
                (unsigned long long)rr_n64_native_count(session), (unsigned long long)rr_n64_interpreted_count(session),
                (unsigned long long)rr_n64_block_entry_count(session), (unsigned long long)rr_n64_guard_miss_count(session),
                (unsigned long long)rr_n64_observed_count(session), nonblack, audible, rr_n64_fps(session),
                rr_n64_audio_rate(session), w, h, load_start ? "true" : "false");
        json_text(r, rr_n64_gpu_name(session));
        fputs("}\n", r);
        if (fclose(r)) { fail("Cannot write the report"); return 1; }
    }
    return stopped ? 2 : 0;
}

static void restart_self(void) {
#ifdef _WIN32
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    wchar_t *line = _wcsdup(GetCommandLineW());
    memset(&si, 0, sizeof si); si.cb = sizeof si;
    if (line && CreateProcessW(NULL, line, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) { CloseHandle(pi.hThread); CloseHandle(pi.hProcess); }
    free(line);
#endif
}

#ifdef _WIN32
/* A crash in a headless run says where (offsets into the executable), for the conversion's diagnostics; nothing else is read. */
static LONG WINAPI crash_filter(EXCEPTION_POINTERS *e) {
    uintptr_t base = (uintptr_t)GetModuleHandleW(NULL), end, *sp;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    int i, shown = 0;
    end = base + nt->OptionalHeader.SizeOfImage;
    fprintf(stderr, "Nintendo 64 player: exception %08lx at +%llx; stack:", e->ExceptionRecord->ExceptionCode,
            (unsigned long long)((uintptr_t)e->ExceptionRecord->ExceptionAddress - base));
    sp = (uintptr_t *)e->ContextRecord->Rsp;
    for (i = 0; i < 4096 && shown < 24; i++) if (sp[i] >= base && sp[i] < end) { fprintf(stderr, " +%llx", (unsigned long long)(sp[i] - base)); shown++; }
    fputc('\n', stderr);
    fflush(stderr);
    _Exit(9);
}
#endif

static int cpu_mode(const char *name) {
    if (!strcmp(name, "cached")) return RR_N64_CPU_CACHED;
    if (!strcmp(name, "pure")) return RR_N64_CPU_PURE;
    if (!strcmp(name, "observe")) return RR_N64_CPU_OBSERVE;
    if (!strcmp(name, "native")) return RR_N64_CPU_NATIVE;
    return -1;
}

int main(int argc, char **argv) {
    const char *trace_path = NULL, *report_path = NULL, *capture_path = NULL, *events_path = NULL, *rom_path = NULL, *slot = NULL;
    const char *observe_path = NULL, *times_path = NULL, *gfx[16];
    unsigned save_at = 0, gfx_count = 0, k;
    bool headless = false, load_start = false, verbose = false;
    RrN64Game game;
    uint8_t *rom = NULL;
    size_t rom_size = 0;
    char base_path[PATH_CAP], game_dir[PATH_CAP], error[256], *base;
    int i, result;
    memset(&game, 0, sizeof game);
#ifdef RR_N64_LINKED
    game.cpu = RR_N64_CPU_DEFAULT;
#else
    game.cpu = RR_N64_CPU_CACHED;
#endif
    SDL_SetMainReady();
#ifdef RR_N64_LINKED
    (void)rr_n64_export_marker[0];
#endif
    for (i = 1; i < argc; i++) {
        const char *a = argv[i];
        if (!strcmp(a, "--headless")) headless = true;
        else if (!strcmp(a, "--verbose")) verbose = true;
        else if (!strcmp(a, "--state-load-start")) load_start = true;
        else if (!strcmp(a, "--threaded-rdp")) game.threaded_rdp = 1;
        else if (!strcmp(a, "--help")) {
            puts("Retro-Recomp Nintendo 64 player\n--headless --frames N --input-events FILE --trace TSV --report JSON --capture PPM\n"
                 "--observations FILE --frame-times TSV --cpu cached|pure|observe|native --gpu NAME --gfx KEY=INDEX --threaded-rdp\n"
                 "--pak memory|rumble|none --state-slot FILE --state-save-at FRAME --state-load-start --verbose\n"
                 "a build without an embedded game: --rom FILE");
            return 0;
        } else if (i + 1 < argc) {
            const char *v = argv[++i];
            if (!strcmp(a, "--frames")) { char *end; unsigned long n = strtoul(v, &end, 10); if (*end || !n || n > MAX_FRAMES) { fail("Invalid frame limit"); return 1; } frame_limit = (unsigned)n; }
            else if (!strcmp(a, "--input-events")) events_path = v;
            else if (!strcmp(a, "--trace")) trace_path = v;
            else if (!strcmp(a, "--report")) report_path = v;
            else if (!strcmp(a, "--capture")) capture_path = v;
            else if (!strcmp(a, "--observations")) observe_path = v;
            else if (!strcmp(a, "--frame-times")) times_path = v;
            else if (!strcmp(a, "--cpu")) { if ((game.cpu = cpu_mode(v)) < 0) { fail("Unknown CPU mode"); return 1; } }
            else if (!strcmp(a, "--gpu")) game.gpu = v;
            else if (!strcmp(a, "--pak")) game.pak = v;
            else if (!strcmp(a, "--gfx")) { if (gfx_count == 16) { fail("Too many --gfx"); return 1; } gfx[gfx_count++] = v; }
            else if (!strcmp(a, "--rom")) rom_path = v;
            else if (!strcmp(a, "--state-slot")) slot = v;
            else if (!strcmp(a, "--state-save-at")) { char *end; unsigned long n = strtoul(v, &end, 10); if (*end || !n || n > MAX_FRAMES) { fail("Invalid state frame"); return 1; } save_at = (unsigned)n; }
            else { fail("Unknown option"); return 1; }
        } else { fail("Unknown option or missing value"); return 1; }
    }
    if (headless && !frame_limit) { fail("Headless mode requires a bounded --frames"); return 1; }
#ifdef _WIN32
    if (headless) SetUnhandledExceptionFilter(crash_filter);
#endif
    if (observe_path) game.cpu = RR_N64_CPU_OBSERVE;
    if (SDL_Init(SDL_INIT_TIMER) != 0) { fprintf(stderr, "%s\n", SDL_GetError()); return 1; }
    base = SDL_GetBasePath();
    if (!base || strlen(base) >= PATH_CAP - 200) { fail("Executable directory unavailable"); return 1; }
    snprintf(base_path, sizeof base_path, "%s", base);
    SDL_free(base);
#ifdef RR_N64_LINKED
    if (rom_path) { fail("An embedded game cannot load another cartridge"); return 1; }
    {
        size_t size = 0;
        const uint8_t *embedded = (const uint8_t *)rr_resource(RR_N64_ROM_RESOURCE, &size);
        if (!embedded || !size || !(rom = (uint8_t *)malloc(size))) { fail("The embedded game is unreadable"); return 1; }
        memcpy(rom, embedded, size);
        rom_size = size;
    }
    snprintf(game_dir, sizeof game_dir, "%sdatas/games/n64-%s", base_path, RR_N64_SOURCE_IDENTITY);
#else
    if (!rom_path || !(rom = read_file(rom_path, &rom_size, 64u << 20))) { fail("This build needs --rom FILE"); return 1; }
    snprintf(game_dir, sizeof game_dir, "%sdatas/games/n64-development", base_path);
#endif
    if (!to_big_endian(rom, rom_size)) { fail("This is not a Nintendo 64 cartridge image"); return 1; }
    if (!headless && !make_dirs(game_dir)) { fail("Cannot prepare the game's data folder"); return 1; }
    snprintf(state_slot, sizeof state_slot, "%s", slot ? slot : "");
    if (!slot) snprintf(state_slot, sizeof state_slot, "%s/quick.rrstate", game_dir);
    if (headless && (save_at || load_start) && !slot) { fail("States need --state-slot"); return 1; }
    if (!headless) snprintf(save_path, sizeof save_path, "%s/saves.bin", game_dir);
    if (events_path && !load_events(events_path)) { fail("Invalid input event file"); return 1; }
    game.rom = rom;
    game.rom_size = rom_size;
    game.evidence = headless;
    if (verbose) game.log = log_line;
    session = rr_n64_open(&game, error, sizeof error);
    free(rom);
    if (!session) { fail(error); return 1; }
    saves_load();
    if (headless) {
        n64_gfx_defaults();
        for (k = 0; k < gfx_count; k++) if (!n64_gfx_assign(gfx[k], false)) { fail("Unknown --gfx option or value"); return 1; }
        result = run_headless(trace_path, report_path, capture_path, observe_path, times_path, save_at, load_start);
    } else {
#ifdef RR_N64_WINDOWED
        for (k = 0; k < gfx_count; k++) if (!n64_gfx_assign(gfx[k], true)) { fail("Unknown --gfx option or value"); return 1; }
#ifdef RR_N64_LINKED
        result = player_run_windowed(RR_N64_GAME_TITLE " | Nintendo 64");
#else
        result = player_run_windowed("Retro-Recomp Nintendo 64 (development)");
#endif
        saves_store();
        if (restart_requested) restart_self();
#else
        fail("This build has no window (RR_N64_SDL off)");
        result = 1;
#endif
    }
    fflush(stdout); fflush(stderr);
    /* The core's threads and coroutines are torn down with the process. */
    _Exit(failed ? 1 : result);
}
