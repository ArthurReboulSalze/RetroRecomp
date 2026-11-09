/* Native driver of the Atari ST hardware checks (gate G11, independent hardware evidence). Original Retro-Recomp code, MIT; it is
 * linked with Hatari (GPL-2.0, licenses/hatari.md), so a program built with it is distributed under the GPL.
 *
 * The checks themselves are tiny 68000 programs authored in tools/atarist_hardware_check.py (no ROM, no TOS, no game): each one is
 * a TOS image of 192 KiB built in memory, in which the machine's reset code sets the MMU up and runs the program. The program
 * measures a named behaviour of the machine from inside it (the MFP's timers against the video frame, the IKBD's packets, the
 * WD1772's index pulse...) and writes what it measured to ST RAM. This driver only runs the session frame by frame, feeds the
 * scripted inputs, and hands the outside view to the Python tool: the RAM, the last picture, the sound and the clocks. It never
 * decides a verdict; the expected values are computed in tools/atarist_hardware_check.py from the hardware's documentation.
 *
 *   atarist_hardware_checks --tos tos.bin --out prefix [--disk image.st] [--frames N] [--events file] [--done ADDRESS]
 *                           [--tail N] [--dump BYTES] [--machine st|megast|ste] [--ram-kb KB]
 *
 * --done ADDRESS: the run ends (after --tail more frames, default 2) when the long word at ADDRESS reads 0x444F4E45 ("DONE").
 * --events: lines "FRAME joy PORT BITS" | "FRAME mouse DX DY LEFT RIGHT" | "FRAME key RETROK DOWN", applied before that frame (the
 * first frame is 0). Outputs: prefix.ram (the first --dump bytes of ST RAM), prefix.picture (the last picture, width*height
 * 32-bit 0x00RRGGBB words, row after row), prefix.pcm (all the sound, interleaved stereo int16), and one JSON line on stdout. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#include "main.h"
#include "configuration.h"
#include "m68000.h"
#include "stMemory.h"
#include "cycles.h"
#include "sysconfig.h"
#include "sysdeps.h"
#include "options_cpu.h"
#include "memory.h"
#include "newcpu.h"
#include "events.h"

#include "atarist_session.h"

#define MAX_EVENTS 4096
#define DONE_MAGIC 0x444F4E45u

typedef struct { unsigned frame; char kind; int a, b, c, d; } Event;
static Event events[MAX_EVENTS];
static unsigned event_count;

static uint8_t *read_file(const char *path, uint32_t *size) {
    FILE *f = fopen(path, "rb");
    long n;
    uint8_t *data;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); n = ftell(f); fseek(f, 0, SEEK_SET);
    data = (uint8_t *)malloc((size_t)n + 1);
    if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(data); return NULL; }
    fclose(f);
    *size = (uint32_t)n;
    return data;
}

static int read_events(const char *path) {
    FILE *f = fopen(path, "r");
    char line[256];
    if (!f) return 0;
    while (fgets(line, sizeof line, f) && event_count < MAX_EVENTS) {
        Event e;
        char word[16];
        int a = 0, b = 0, c = 0, d = 0, n;
        unsigned frame;
        memset(&e, 0, sizeof e);
        n = sscanf(line, "%u %15s %d %d %d %d", &frame, word, &a, &b, &c, &d);
        if (n < 3) continue;
        e.frame = frame; e.a = a; e.b = b; e.c = c; e.d = d;
        e.kind = !strcmp(word, "joy") ? 'j' : !strcmp(word, "mouse") ? 'm' : !strcmp(word, "key") ? 'k' : 0;
        if (e.kind) events[event_count++] = e;
    }
    fclose(f);
    return 1;
}

static void log_line(const char *line) { (void)line; }

int main(int argc, char **argv) {
    const char *tos_path = NULL, *disk_path = NULL, *out = NULL, *events_path = NULL, *machine = "st";
    unsigned frames = 60, tail = 2, dump = 0x40000, ram_kb = 4096, n;
    uint32_t done_address = 0;
    int have_done = 0, i;
    uint32_t tos_size = 0, disk_size = 0;
    uint8_t *tos, *disk = NULL;
    RrStDisk disk_entry;
    RrStGame game;
    RrStSession *session;
    char error[256] = "", path[1024];
    FILE *pcm;
    unsigned frame, ran = 0, done_at = 0;
    unsigned *audio_counts;
    uint64_t *clock_deltas;
    int16_t samples[8192 * 2];
    size_t audio_total = 0;
    int width = 0, height = 0, stride = 0, refresh;
    const uint32_t *picture;
    size_t ram_size;
    const uint8_t *ram;
    FILE *file;

    for (i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--tos") && i + 1 < argc) tos_path = argv[++i];
        else if (!strcmp(argv[i], "--disk") && i + 1 < argc) disk_path = argv[++i];
        else if (!strcmp(argv[i], "--out") && i + 1 < argc) out = argv[++i];
        else if (!strcmp(argv[i], "--events") && i + 1 < argc) events_path = argv[++i];
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--tail") && i + 1 < argc) tail = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--dump") && i + 1 < argc) dump = (unsigned)strtoul(argv[++i], NULL, 0);
        else if (!strcmp(argv[i], "--ram-kb") && i + 1 < argc) ram_kb = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--machine") && i + 1 < argc) machine = argv[++i];
        else if (!strcmp(argv[i], "--done") && i + 1 < argc) { done_address = (uint32_t)strtoul(argv[++i], NULL, 0); have_done = 1; }
        else { fprintf(stderr, "unknown argument %s\n", argv[i]); return 2; }
    }
    if (!tos_path || !out) {
        fprintf(stderr, "usage: atarist_hardware_checks --tos tos.bin --out prefix [--disk image.st] [--frames N] [--events file] [--done ADDRESS]\n");
        return 2;
    }
    tos = read_file(tos_path, &tos_size);
    if (!tos) { fprintf(stderr, "cannot read the TOS image\n"); return 2; }
    if (disk_path) {
        disk = read_file(disk_path, &disk_size);
        if (!disk) { fprintf(stderr, "cannot read the disk image\n"); return 2; }
    } else {   /* a blank 720 KiB floppy: the session needs one disk */
        disk_size = 737280u;
        disk = (uint8_t *)calloc(1, disk_size);
    }
    if (events_path && !read_events(events_path)) { fprintf(stderr, "cannot read the events\n"); return 2; }

    disk_entry.name = "check.st"; disk_entry.data = disk; disk_entry.size = disk_size;
    memset(&game, 0, sizeof game);
    game.disks = &disk_entry; game.disk_count = 1; game.tos = tos; game.tos_size = tos_size;
    game.machine = machine; game.memory_kb = ram_kb; game.log = log_line;
    session = rr_st_open(&game, error, sizeof error);
    if (!session) { fprintf(stderr, "the session did not open: %s\n", error); return 2; }

    snprintf(path, sizeof path, "%s.pcm", out);
    pcm = fopen(path, "wb");
    audio_counts = (unsigned *)calloc(frames + 1, sizeof *audio_counts);
    clock_deltas = (uint64_t *)calloc(frames + 1, sizeof *clock_deltas);
    if (!pcm || !audio_counts || !clock_deltas) { fprintf(stderr, "cannot create the outputs\n"); return 2; }

    for (frame = 0; frame < frames; ++frame) {
        uint64_t before;
        size_t got;
        for (n = 0; n < event_count; ++n) {
            const Event *e = &events[n];
            if (e->frame != frame) continue;
            if (e->kind == 'j') rr_st_joystick(session, (unsigned)e->a, (unsigned)e->b);
            else if (e->kind == 'm') rr_st_mouse(session, e->a, e->b, e->c, e->d);
            else if (e->kind == 'k') rr_st_key(session, (unsigned)e->a, e->b);
        }
        before = CyclesGlobalClockCounter;
        if (rr_st_frame(session) != 0) { fprintf(stderr, "frame %u failed: %s\n", frame, rr_st_error(session)); return 2; }
        clock_deltas[frame] = CyclesGlobalClockCounter - before;
        ++ran;
        while ((got = rr_st_audio(session, samples, 8192)) > 0) {
            fwrite(samples, 4, got, pcm);
            audio_counts[frame] += (unsigned)got;
            audio_total += got;
        }
        if (have_done && !done_at) {
            size_t size;
            const uint8_t *r = rr_st_ram(session, &size);
            if (done_address + 4 <= size && ((uint32_t)r[done_address] << 24 | (uint32_t)r[done_address + 1] << 16 |
                                             (uint32_t)r[done_address + 2] << 8 | r[done_address + 3]) == DONE_MAGIC) done_at = frame + 1;
        }
        if (done_at && frame + 1 >= done_at + tail) break;
    }
    fclose(pcm);

    ram = rr_st_ram(session, &ram_size);
    if (dump > ram_size) dump = (unsigned)ram_size;
    snprintf(path, sizeof path, "%s.ram", out);
    file = fopen(path, "wb");
    if (!file || fwrite(ram, 1, dump, file) != dump) { fprintf(stderr, "cannot write the RAM\n"); return 2; }
    fclose(file);

    picture = rr_st_picture(session, &width, &height, &stride);
    snprintf(path, sizeof path, "%s.picture", out);
    file = fopen(path, "wb");
    if (!file) return 2;
    for (i = 0; i < height; ++i) fwrite(picture + (size_t)i * (size_t)stride, 4, (size_t)width, file);
    fclose(file);
    refresh = rr_st_refresh_rate(session);

    printf("{\"frames\":%u,\"done_at\":%u,\"width\":%d,\"height\":%d,\"refresh\":%d,\"audio_rate\":%u,\"audio_frames\":%llu,"
           "\"interpreted\":%llu,\"pc\":%u,\"frame_cycles\":[", ran, done_at, width, height, refresh, rr_st_audio_rate(session),
           (unsigned long long)audio_total, (unsigned long long)rr_st_interpreted_count(session), (unsigned)M68000_GetPC());
    for (n = 0; n < ran; ++n) printf("%s%llu", n ? "," : "", (unsigned long long)clock_deltas[n]);
    printf("],\"audio_counts\":[");
    for (n = 0; n < ran; ++n) printf("%s%u", n ? "," : "", audio_counts[n]);
    printf("]}\n");
    return 0;
}
