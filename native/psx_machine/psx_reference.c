/* Headless PlayStation reference tool of the conversion (MIT, ours; linked with Beetle PSX, GPL-2.0, the program is GPL-2.0).
 *
 *   psx_reference --pack <file> [--bios <file>] [--frames <n>] [--events <file>] [--trace <file>] [--shot <frame>:<file.ppm>]...
 *                 [--save-state <frame>:<file>] [--load-state <file>] [--abi <text>]
 *
 * Runs the pack's first disc for <n> frames with the inputs of the events file (lines "<frame> <player> <bits> <lx> <ly> <rx>
 * <ry>", in frame order; a line holds until the next one of that player) and writes one trace line per frame:
 *   <frame> <width>x<height> <video> <pcm> <samples> <ram> <nonblack> <audible>
 * No window, no sound device, no clock: two runs of the same inputs give the same lines. Errors go to stderr; exit 2. */
#include "psx_session.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#endif

#define MAX_SHOTS 32

typedef struct { long frame; int player; unsigned bits; int16_t sticks[4]; } Event;

static uint8_t *read_file(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    uint8_t *data = n > 0 ? (uint8_t *)malloc((size_t)n) : NULL;
    if (data && fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); data = NULL; }
    fclose(f);
    if (data && size) *size = (size_t)n;
    return data;
}

static Event *read_events(const char *path, size_t *count) {
    FILE *f = fopen(path, "r");
    Event *events = NULL;
    size_t n = 0, cap = 0;
    char line[256];
    if (!f) return NULL;
    while (fgets(line, sizeof line, f)) {
        Event e;
        int a, b, c, d;
        if (line[0] == '#' || sscanf(line, "%ld %d %u %d %d %d %d", &e.frame, &e.player, &e.bits, &a, &b, &c, &d) != 7) continue;
        e.sticks[0] = (int16_t)a; e.sticks[1] = (int16_t)b; e.sticks[2] = (int16_t)c; e.sticks[3] = (int16_t)d;
        if (n == cap) {
            cap = cap ? cap * 2 : 256;
            Event *grown = (Event *)realloc(events, cap * sizeof *events);
            if (!grown) { free(events); fclose(f); return NULL; }
            events = grown;
        }
        events[n++] = e;
    }
    fclose(f);
    *count = n;
    return events;
}

static int write_ppm(const char *path, const uint32_t *pixels, int width, int height, int pitch) {
    FILE *f = fopen(path, "wb");
    if (!f) return 0;
    fprintf(f, "P6\n%d %d\n255\n", width, height);
    for (int i = 0; i < width * height; ++i) {
        const uint32_t pixel = pixels[(size_t)(i / width) * pitch + i % width];
        uint8_t rgb[3] = {(uint8_t)(pixel >> 16), (uint8_t)(pixel >> 8), (uint8_t)pixel};
        fwrite(rgb, 1, 3, f);
    }
    return fclose(f) == 0;
}

int main(int argc, char **argv) {
#ifdef _WIN32
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX);
#endif
    const char *pack = NULL, *bios_path = NULL, *events_path = NULL, *trace_path = NULL, *load_state = NULL, *abi = "dev";
    long frames = 600, save_frame = -1;
    const char *save_path = NULL;
    long shot_frame[MAX_SHOTS];
    const char *shot_path[MAX_SHOTS];
    int shots = 0;
    for (int i = 1; i < argc; ++i) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) { fprintf(stderr, "psx_reference: %s needs a value\n", a); return 2; }
        if (!strcmp(a, "--pack")) pack = v;
        else if (!strcmp(a, "--bios")) bios_path = v;
        else if (!strcmp(a, "--frames")) frames = strtol(v, NULL, 10);
        else if (!strcmp(a, "--events")) events_path = v;
        else if (!strcmp(a, "--trace")) trace_path = v;
        else if (!strcmp(a, "--abi")) abi = v;
        else if (!strcmp(a, "--load-state")) load_state = v;
        else if (!strcmp(a, "--save-state") || !strcmp(a, "--shot")) {
            const char *colon = strchr(v, ':');
            if (!colon || colon == v) { fprintf(stderr, "psx_reference: %s wants <frame>:<file>\n", a); return 2; }
            long frame = strtol(v, NULL, 10);
            if (!strcmp(a, "--save-state")) { save_frame = frame; save_path = colon + 1; }
            else if (shots < MAX_SHOTS) { shot_frame[shots] = frame; shot_path[shots++] = colon + 1; }
        } else { fprintf(stderr, "psx_reference: unknown option %s\n", a); return 2; }
        ++i;
    }
    if (!pack) { fprintf(stderr, "psx_reference: --pack is required\n"); return 2; }
    uint8_t *bios = NULL;
    size_t bios_size = 0;
    if (bios_path && !(bios = read_file(bios_path, &bios_size))) { fprintf(stderr, "psx_reference: cannot read %s\n", bios_path); return 2; }
    if (bios && bios_size != RR_PSX_BIOS_BYTES) { fprintf(stderr, "psx_reference: %s is not a 512 KiB BIOS\n", bios_path); return 2; }
    size_t event_count = 0, next = 0;
    Event *events = NULL;
    if (events_path && !(events = read_events(events_path, &event_count))) {
        fprintf(stderr, "psx_reference: cannot read %s\n", events_path);
        return 2;
    }
    char error[256];
    RrPsxGame game = {pack, bios, NULL, 0};
    RrPsxSession *s = rr_psx_open(&game, error, sizeof error);
    free(bios);
    if (!s) { fprintf(stderr, "psx_reference: %s\n", error); return 2; }
    if (load_state) {
        int result = rr_psx_state_load(s, load_state, abi);
        if (result) { fprintf(stderr, "psx_reference: state not loaded (%d)\n", result); rr_psx_close(s); return 2; }
    }
    FILE *trace = trace_path ? fopen(trace_path, "w") : NULL;
    if (trace_path && !trace) { fprintf(stderr, "psx_reference: cannot write %s\n", trace_path); rr_psx_close(s); return 2; }
    unsigned bits[2] = {0, 0};
    int16_t sticks[2][4] = {{0}};
    for (long frame = 0; frame < frames; ++frame) {
        while (next < event_count && events[next].frame <= frame) {
            const Event *e = &events[next++];
            if (e->player < 0 || e->player > 1) continue;
            bits[e->player] = e->bits;
            memcpy(sticks[e->player], e->sticks, sizeof sticks[0]);
        }
        rr_psx_pad(s, 0, bits[0], sticks[0]);
        rr_psx_pad(s, 1, bits[1], sticks[1]);
        if (rr_psx_frame(s) != 0) { fprintf(stderr, "psx_reference: %s\n", rr_psx_error(s)); break; }
        RrPsxFrameInfo info;
        rr_psx_frame_info(s, &info);
        if (trace)
            fprintf(trace, "%llu %dx%d %016llx %016llx %u %016llx %d %d\n", (unsigned long long)info.frame, info.width,
                    info.height, (unsigned long long)info.video, (unsigned long long)info.pcm, info.samples,
                    (unsigned long long)info.ram, info.nonblack, info.audible);
        for (int i = 0; i < shots; ++i)
            if (shot_frame[i] == frame) {
                int w, h;
                const uint32_t *pixels = rr_psx_picture(s, &w, &h, NULL);
                if (!write_ppm(shot_path[i], pixels, w, h, rr_psx_picture_pitch(s))) fprintf(stderr, "psx_reference: cannot write %s\n", shot_path[i]);
            }
        if (frame == save_frame && rr_psx_state_save(s, save_path, abi) != 0)
            fprintf(stderr, "psx_reference: state not saved\n");
    }
    if (trace) fclose(trace);
    free(events);
    rr_psx_close(s);
    return 0;
}
