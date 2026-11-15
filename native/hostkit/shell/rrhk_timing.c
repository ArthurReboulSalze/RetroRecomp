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
    /* The graphics options in force (D14): a timing taken at another internal resolution says so. */
    if (machine->gfx_option_count > 0) {
        fprintf(file, ",\"gfx\":{");
        for (int i = 0; i < machine->gfx_option_count && i < RRHK_MAX_GFX_OPTIONS; ++i)
            fprintf(file, "%s\"%ls\":%d", i ? "," : "", machine->gfx_options[i].ini_key, rrhk.gfx[i]);
        fprintf(file, "}");
    }
    /* 1.7.7 (D30): Sync to display: the mode, the measured refresh, the decision and the cadence of the locked frames (how many
     * refreshes each was held: evenness of the picture, never a latency) */
    fprintf(file, ",\"sync\":{\"mode\":%d,\"active\":%s,\"refresh_hz\":%.6f,\"machine_hz\":%.6f,\"locked\":%s,\"held\":[%llu,%llu,%llu,%llu]}",
        rrhk_sync.mode, rrhk_sync.active ? "true" : "false", rrhk_sync.refresh_hz, rrhk_sync.machine_hz, rrhk_sync.lock ? "true" : "false",
        (unsigned long long)rrhk_sync.held[0], (unsigned long long)rrhk_sync.held[1], (unsigned long long)rrhk_sync.held[2],
        (unsigned long long)rrhk_sync.held[3]);
    if (machine->timing_report) machine->timing_report(file, frequency);
    fprintf(file, "}\n"); fclose(file);
}
