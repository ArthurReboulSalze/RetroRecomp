/* One line per completed frame of a headless run (--frame-trace FILE), for the liveness record of the delivered file
 * (retrorecomp/delivery_evidence.py): frame, picture, sound, non-zero samples, RAM, program counter.
 *
 * Included by gbrt.c (adapted in gameboy_runtime.py). The picture is the hash of the 160 x 144 pixels the host would show, the sound
 * is the hash of the stereo samples the APU produced since the previous line and `nonzero` counts those that were not zero, the
 * RAM is the hash of work RAM and high RAM, the program counter is the one at the end of the frame. Hashes are FNV-1a over the bytes
 * as they are in memory (little-endian x86-64 on both Windows and Linux). Nothing is written, and nothing is counted, unless the
 * flag is given: the game, its states and its saves do not change. A run with two contexts (the lockstep comparison) never gives
 * the flag.
 */
#ifndef RR_GB_FRAME_TRACE_H
#define RR_GB_FRAME_TRACE_H

#include <stdint.h>
#include <stdio.h>
#include "gbrt.h"

static const char* rr_gb_trace_path;
static FILE* rr_gb_trace_file;
static const GBContext* rr_gb_trace_owner;
static uint64_t rr_gb_trace_sound = 0xcbf29ce484222325ull;
static uint64_t rr_gb_trace_nonzero;

static uint64_t rr_gb_trace_hash(uint64_t hash, const void* data, size_t size) {
    const uint8_t* bytes = (const uint8_t*)data;
    for (size_t i = 0; i < size; ++i) hash = (hash ^ bytes[i]) * 0x100000001b3ull;
    return hash;
}

void rr_gb_frame_trace_open(const char* path) {
    rr_gb_trace_path = path;
}

/* Called for every stereo sample before the host callback. */
static void rr_gb_trace_sample(const GBContext* ctx, int16_t left, int16_t right) {
    if (!rr_gb_trace_path || (rr_gb_trace_owner && rr_gb_trace_owner != ctx)) return;
    const int16_t pair[2] = {left, right};
    rr_gb_trace_sound = rr_gb_trace_hash(rr_gb_trace_sound, pair, sizeof(pair));
    if (left != 0 || right != 0) ++rr_gb_trace_nonzero;
}

/* Called when a frame is complete (frame_done set), `frame` counting from 1. */
void rr_gb_frame_trace(GBContext* ctx, uint64_t frame) {
    if (!rr_gb_trace_path || !ctx) return;
    if (!rr_gb_trace_file) {
        rr_gb_trace_file = fopen(rr_gb_trace_path, "w");
        if (!rr_gb_trace_file) { rr_gb_trace_path = NULL; return; }
        rr_gb_trace_owner = ctx;
        fputs("frame,picture,sound,nonzero_samples,ram,pc\n", rr_gb_trace_file);
    }
    if (rr_gb_trace_owner != ctx) return;
    const uint32_t* pixels = gb_get_framebuffer(ctx);
    const uint64_t picture = pixels ? rr_gb_trace_hash(0xcbf29ce484222325ull, pixels, 160u * 144u * sizeof(uint32_t)) : 0;
    uint64_t ram = rr_gb_trace_hash(0xcbf29ce484222325ull, ctx->wram, 0x1000u * 8u);
    ram = rr_gb_trace_hash(ram, ctx->hram, 0x7Fu);
    fprintf(rr_gb_trace_file, "%llu,%016llx,%016llx,%llu,%016llx,%04x\n", (unsigned long long)frame,
            (unsigned long long)picture, (unsigned long long)rr_gb_trace_sound,
            (unsigned long long)rr_gb_trace_nonzero, (unsigned long long)ram, (unsigned)ctx->pc);
    fflush(rr_gb_trace_file);
    rr_gb_trace_sound = 0xcbf29ce484222325ull;
    rr_gb_trace_nonzero = 0;
}

#endif
