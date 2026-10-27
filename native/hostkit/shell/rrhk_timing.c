/* Explicit diagnostic only. Accumulate in memory; write once after the user
 * closes the game. No per-frame logging or default sidecar file. */
#ifndef SDL_MAIN_HANDLED
#define SDL_MAIN_HANDLED
#endif
#include <SDL.h>
#include <stdio.h>
#ifndef _WIN32
#include <time.h>
#endif
#include "hostkit/hostkit_internal.h"

double rrhk_thread_cpu(void) {
#ifndef _WIN32
    struct timespec t;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t) == 0) return t.tv_sec + t.tv_nsec / 1000000000.0;
#endif
    return 0;
}

void rrhk_timing_write(const RrhkMachine *machine, const char *path, const RrhkTiming *timing,
                       SDL_Renderer *renderer, Uint64 frequency) {
    if (!path || !*path) return;
    FILE *file = fopen(path, "w"); if (!file) return;
    SDL_RendererInfo info = {0}; SDL_GetRendererInfo(renderer, &info);
    const char *names[] = {"events_and_audio_room", "engine_and_delivery", "audio_queue", "drawing", "present", "pacing"};
    fprintf(file, "{\"frames\":%llu,\"guest_seconds\":%.9f,\"main_thread_cpu_seconds\":%.9f,\"renderer\":\"%s\",\"vsync\":%s,\"sections\":{",
        (unsigned long long)timing->frames, timing->frames * machine->frame_seconds, timing->thread_cpu,
        info.name ? info.name : "unknown", info.flags & SDL_RENDERER_PRESENTVSYNC ? "true" : "false");
    for (unsigned n = 0; n < 6; ++n) fprintf(file, "%s\"%s\":{\"seconds\":%.9f,\"max_ms\":%.6f}",
        n ? "," : "", names[n], timing->total[n], timing->maximum[n] * 1000);
    fprintf(file, "}");
    if (machine->timing_report) machine->timing_report(file, frequency);
    fprintf(file, "}\n"); fclose(file);
}
