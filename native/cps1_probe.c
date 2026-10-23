/* Headless CPS-1 reference runner: per-frame traces, frame images, audio.
 *
 *   cps1_probe BOARD_DIR --frames N [--trace FILE] [--wav FILE]
 *              [--image FRAME:FILE.ppm]... [--input FRAME:PORT:VALUE]...
 *
 * BOARD_DIR holds board.txt and the region files written by
 * smsrecomp/cps1_board.py. --input sets a raw (active-low) port value from
 * that frame on; PORT is IN0, IN1, IN2, IN3, DSWA, DSWB or DSWC.
 */
#include "cps1_machine.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_EVENTS 4096

typedef struct { unsigned frame; int port; unsigned value; } input_event;
typedef struct { unsigned frame; const char *path; } image_request;

static uint8_t *load_file(const char *directory, const char *name, size_t *size, int required)
{
    char path[1024];
    snprintf(path, sizeof path, "%s/%s", directory, name);
    FILE *file = fopen(path, "rb");
    if (!file) {
        if (required) fprintf(stderr, "cannot open %s\n", path);
        *size = 0;
        return NULL;
    }
    fseek(file, 0, SEEK_END);
    long length = ftell(file);
    fseek(file, 0, SEEK_SET);
    uint8_t *data = length > 0 ? malloc((size_t)length + 1) : NULL;
    if (!data || fread(data, 1, (size_t)length, file) != (size_t)length) {
        fclose(file); free(data);
        fprintf(stderr, "cannot read %s\n", path);
        *size = 0;
        return NULL;
    }
    fclose(file);
    data[length] = 0;
    *size = (size_t)length;
    return data;
}

static uint64_t fnv(uint64_t hash, const void *data, size_t size)
{
    const uint8_t *bytes = data;
    for (size_t i = 0; i < size; i++) { hash ^= bytes[i]; hash *= 0x100000001b3ull; }
    return hash;
}

static int port_index(const char *name)
{
    static const char *const names[CPS1_PORTS] = {"IN0", "IN1", "IN2", "IN3", "DSWA", "DSWB", "DSWC"};
    for (int i = 0; i < CPS1_PORTS; i++) if (!strcmp(name, names[i])) return i;
    return -1;
}

static int write_image(const char *path, const uint32_t *pixels)
{
    FILE *file = fopen(path, "wb");
    if (!file) return 0;
    fprintf(file, "P6\n%d %d\n255\n", CPS1_SCREEN_W, CPS1_SCREEN_H);
    for (int i = 0; i < CPS1_SCREEN_W * CPS1_SCREEN_H; i++) {
        const uint8_t rgb[3] = {(uint8_t)(pixels[i] >> 16), (uint8_t)(pixels[i] >> 8), (uint8_t)pixels[i]};
        fwrite(rgb, 1, 3, file);
    }
    return fclose(file) == 0;
}

static void put32(FILE *file, uint32_t value)
{
    const uint8_t bytes[4] = {(uint8_t)value, (uint8_t)(value >> 8), (uint8_t)(value >> 16), (uint8_t)(value >> 24)};
    fwrite(bytes, 1, 4, file);
}

int main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: cps1_probe BOARD_DIR --frames N [--trace FILE] [--wav FILE] "
                        "[--image FRAME:FILE] [--input FRAME:PORT:VALUE]\n");
        return 2;
    }
    const char *directory = argv[1], *trace_path = NULL, *wav_path = NULL, *ram_path = NULL, *fallback_path = NULL;
    unsigned frames = 600;
    static input_event events[MAX_EVENTS];
    static image_request images[1024];
    int event_count = 0, image_count = 0;
    for (int i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = (unsigned)strtoul(argv[++i], NULL, 10);
        else if (!strcmp(argv[i], "--trace") && i + 1 < argc) trace_path = argv[++i];
        else if (!strcmp(argv[i], "--wav") && i + 1 < argc) wav_path = argv[++i];
        else if (!strcmp(argv[i], "--ram") && i + 1 < argc) ram_path = argv[++i];
        else if (!strcmp(argv[i], "--fallback") && i + 1 < argc) fallback_path = argv[++i];
#ifdef CPS1_TRACE
        else if (!strcmp(argv[i], "--cpu-trace") && i + 1 < argc) {
            void cps1_trace_open(const char *path);
            cps1_trace_open(argv[++i]);
        }
#endif
        else if (!strcmp(argv[i], "--iack") && i + 1 < argc) {
            int enabled = 1, offset = 0, base = 0;
            sscanf(argv[++i], "%d,%d,%d", &enabled, &offset, &base);
            cps1_set_iack_model(enabled, offset, base);
        }
        else if (!strcmp(argv[i], "--image") && i + 1 < argc && image_count < 1024) {
            char *colon = strchr(argv[++i], ':');
            if (!colon) { fprintf(stderr, "bad --image\n"); return 2; }
            images[image_count].frame = (unsigned)strtoul(argv[i], NULL, 10);
            images[image_count++].path = colon + 1;
        } else if (!strcmp(argv[i], "--input") && i + 1 < argc && event_count < MAX_EVENTS) {
            char name[16]; unsigned frame, value;
            if (sscanf(argv[++i], "%u:%15[^:]:%i", &frame, name, (int *)&value) != 3 || port_index(name) < 0) {
                fprintf(stderr, "bad --input %s\n", argv[i]); return 2;
            }
            events[event_count++] = (input_event){frame, port_index(name), value};
        } else { fprintf(stderr, "unknown argument %s\n", argv[i]); return 2; }
    }

    size_t size;
    char *text = (char *)load_file(directory, "board.txt", &size, 1);
    if (!text) return 3;
    cps1_board board;
    char error[256];
    if (!cps1_board_parse(&board, text, error, sizeof error)) { fprintf(stderr, "%s\n", error); return 3; }
    free(text);
    cps1_regions regions = {0};
    uint8_t *maincpu = load_file(directory, "maincpu.bin", &regions.maincpu_size, 1);
    uint8_t *audiocpu = load_file(directory, "audiocpu.bin", &regions.audiocpu_size, 1);
    uint8_t *gfx = load_file(directory, "gfx.bin", &regions.gfx_size, 1);
    uint8_t *oki = load_file(directory, "oki.bin", &regions.oki_size, 1);
    uint8_t *stars = load_file(directory, "stars.bin", &regions.stars_size, 0);
    if (!maincpu || !audiocpu || !gfx || !oki) return 3;
    regions.maincpu = maincpu; regions.audiocpu = audiocpu; regions.gfx = gfx;
    regions.oki = oki; regions.stars = stars;
    if (!cps1_init(&board, &regions)) { fprintf(stderr, "cannot start the CPS-1 board\n"); return 4; }

    FILE *trace = trace_path ? fopen(trace_path, "w") : NULL;
    FILE *wav = wav_path ? fopen(wav_path, "wb") : NULL;
    FILE *ram = ram_path ? fopen(ram_path, "wb") : NULL;
    if ((trace_path && !trace) || (wav_path && !wav)) { fprintf(stderr, "cannot write outputs\n"); return 5; }
    if (wav) fwrite("RIFF\0\0\0\0WAVEfmt \x10\0\0\0\x01\0\x01\0\0\0\0\0\0\0\0\0\x02\0\x10\0data\0\0\0\0", 1, 44, wav);
    uint64_t video_all = 0xcbf29ce484222325ull, audio_all = video_all;
    size_t total_samples = 0;
    for (unsigned frame = 0; frame < frames; frame++) {
        for (int e = 0; e < event_count; e++)
            if (events[e].frame == frame) cps1_set_port(events[e].port, (uint16_t)events[e].value);
        cps1_run_frame();
        size_t samples;
        const int16_t *audio = cps1_audio(&samples);
        const uint32_t *pixels = cps1_framebuffer();
        uint64_t video = fnv(0xcbf29ce484222325ull, pixels, sizeof(uint32_t) * CPS1_SCREEN_W * CPS1_SCREEN_H);
        uint64_t sound = fnv(0xcbf29ce484222325ull, audio, samples * sizeof *audio);
        video_all = fnv(video_all, &video, sizeof video);
        audio_all = fnv(audio_all, &sound, sizeof sound);
        total_samples += samples;
        if (wav) fwrite(audio, sizeof *audio, samples, wav);
        if (ram) fwrite(cps1_work_ram(), 1, 0x10000, ram);
        if (trace) {
            cps1_cpu_state cpu;
            cps1_cpu_state_get(&cpu);
            fprintf(trace, "%u %016llx %016llx %zu %016llx %06x %04x\n", frame, (unsigned long long)video,
                    (unsigned long long)sound, samples, (unsigned long long)cps1_ram_hash(), cpu.m68k_pc, cpu.z80_pc);
        }
        for (int i = 0; i < image_count; i++)
            if (images[i].frame == frame && !write_image(images[i].path, pixels)) {
                fprintf(stderr, "cannot write %s\n", images[i].path); return 5;
            }
    }
    if (wav) {
        uint32_t bytes = (uint32_t)(total_samples * 2);
        fseek(wav, 4, SEEK_SET); put32(wav, 36 + bytes);
        fseek(wav, 24, SEEK_SET); put32(wav, CPS1_AUDIO_RATE); put32(wav, CPS1_AUDIO_RATE * 2);
        fseek(wav, 40, SEEK_SET); put32(wav, bytes);
        fclose(wav);
    }
    if (trace) fclose(trace);
    if (ram) fclose(ram);
    if (fallback_path) {
        void cps1_fallback_report(FILE *file);
        FILE *report = fopen(fallback_path, "w");
        if (!report) { fprintf(stderr, "cannot write %s\n", fallback_path); return 5; }
        cps1_fallback_report(report);
        fclose(report);
    }
    cps1_cpu_state cpu;
    cps1_cpu_state_get(&cpu);
    printf("{\"set\":\"%s\",\"frames\":%u,\"video\":\"%016llx\",\"audio\":\"%016llx\",\"samples\":%zu,"
           "\"ram\":\"%016llx\",\"m68k_pc\":%u,\"z80_pc\":%u}\n", board.set, frames,
           (unsigned long long)video_all, (unsigned long long)audio_all, total_samples,
           (unsigned long long)cps1_ram_hash(), cpu.m68k_pc, cpu.z80_pc);
    cps1_shutdown();
    free(maincpu); free(audiocpu); free(gfx); free(oki); free(stars);
    return 0;
}
