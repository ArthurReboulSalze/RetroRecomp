/* Multiplayer checks of the Super Nintendo adapter: the rollback snapshot and the digest, over an authored cartridge or a game
 * the player converted. Save at a frame, run N frames, load, run the same N frames: every digest, picture and sound block of the
 * second run equals the first; a save over a buffer of other bytes equals the first save; a load then a save gives the same
 * bytes; a load of a wrong size or a too small capacity is refused and leaves the machine alone.
 * Usage: checks [frames-per-run] [warm-up frames]. */
#ifdef _WIN32
#include <windows.h>
#endif
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "retro_console16.h"
#include "cpu_state.h"
#include "snes/ppu.h"
#include "snes/snes.h"
#include "snes/cart.h"
extern Snes *g_snes;
uint64_t rr16_snes_digest(void);
size_t rr16_snes_snap_bound(void);
size_t rr16_snes_snap_save(void *buffer, size_t capacity);
bool rr16_snes_snap_load(const void *buffer, size_t size);
void rr16_snes_side_effects(bool allowed);
size_t rr16_snes_session_save(void *out, size_t capacity);
bool rr16_snes_session_save_put(const void *in, size_t size);
uint64_t rr16_audio_frame_fingerprint(void);
extern uint64_t rr16_snes_digest_parts[7];
static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr, "line %u: %s\n", __LINE__, #x); exit(1); } } while (0)

/* A scripted pad per seat, held four frames: the machine leaves its idle loop and diverges at once if one input differs. */
static uint16_t pad(unsigned seat, unsigned frame) {
    uint32_t x = (frame / 4) * 2654435761u + (seat + 1) * 40503u;
    x ^= x >> 15; x *= 2246822519u; x ^= x >> 13;
    return (uint16_t)((x >> 4) & 0xfff);
}
static uint64_t picture_hash(void) {
    const uint32_t *pixels = rr16_pixels();
    uint64_t hash = 14695981039346656037ull;
    const size_t count = (size_t)RR16_WIDTH * RR16_HEIGHT;
    for (size_t i = 0; i < count; ++i) { hash ^= pixels[i]; hash *= 1099511628211ull; }
    return hash;
}
typedef struct { uint64_t digest, picture, sound, parts[7]; } Seen;
static unsigned frame_index;
static void run(unsigned count, Seen *seen) {
    for (unsigned n = 0; n < count; ++n, ++frame_index) {
        CHECK(rr16_frame(pad(0, frame_index), pad(1, frame_index)));
        seen[n] = (Seen){.digest = rr16_snes_digest(), .picture = picture_hash(), .sound = rr16_audio_frame_fingerprint()};
        memcpy(seen[n].parts, rr16_snes_digest_parts, sizeof seen[n].parts);
    }
}
/* The digest is the guest: it must be equal frame for frame. The picture and the sound block are presentation (the S-DSP output ring
 * is the live audio consumer's, a rollback keeps it): they are counted and told, with the first frame each differs on. */
static unsigned picture_differences, sound_differences, first_picture = ~0u, first_sound = ~0u;
static void same(const Seen *a, const Seen *b, unsigned count) {
    for (unsigned n = 0; n < count; ++n) {
        if (a[n].digest != b[n].digest) {
            fprintf(stderr, "frame %u of the run: digest %016llx/%016llx\n", n, (unsigned long long)a[n].digest,
                    (unsigned long long)b[n].digest);
            for (unsigned part = 0; part < 7; ++part)
                if (a[n].parts[part] != b[n].parts[part]) fprintf(stderr, "  partition %u (cpu wram apu ppu ppu-ports dma cart) differs\n", part);
        }
        CHECK(a[n].digest == b[n].digest);
        if (a[n].picture != b[n].picture) { ++picture_differences; if (first_picture == ~0u) first_picture = n; }
        if (a[n].sound != b[n].sound) { ++sound_differences; if (first_sound == ~0u) first_sound = n; }
    }
}
/* `checks trace N`: the digest of every frame of the scripted route, one line each (frame, digest, the seven partitions), for the
 * comparison of two systems (tools/snes_digest_cross_os.py). Hashes only: no ROM byte, no picture. */
static int trace(unsigned frames) {
    CHECK(rr16_init(true));
    rr16_reset();
    for (unsigned n = 0; n < frames; ++n) {
        CHECK(rr16_frame(pad(0, n), pad(1, n)));
        const uint64_t digest = rr16_snes_digest();
        printf("%u %016llx", n, (unsigned long long)digest);
        for (unsigned part = 0; part < 7; ++part) printf(" %016llx", (unsigned long long)rr16_snes_digest_parts[part]);
        printf("\n");
    }
    rr16_shutdown();
    return 0;
}
int main(int argc, char **argv) {
    if (argc > 2 && !strcmp(argv[1], "trace")) return trace((unsigned)atoi(argv[2]));
    const unsigned length = argc > 1 ? (unsigned)atoi(argv[1]) : 40;
    const unsigned warm = argc > 2 ? (unsigned)atoi(argv[2]) : 30;
    CHECK(length >= 4 && length <= 600);
    CHECK(rr16_init(true));
    rr16_reset();
    const size_t bound = rr16_snes_snap_bound();
    CHECK(bound > 0 && bound < (size_t)8 << 20);
    uint8_t *first = malloc(bound), *other = malloc(bound);
    Seen *one = malloc(length * sizeof *one), *two = malloc(length * sizeof *two), *burn = malloc(8 * sizeof *burn);
    CHECK(first && other && one && two && burn);
    Seen warmup[1];
    for (unsigned n = 0; n < warm; ++n) run(1, warmup);
    size_t snapshot_bytes = 0, saved_ram = 0;
    /* Three save points: right after the warm-up, then after 1 and 7 more frames, so the snapshot meets different phases of
     * the machine (the pending interrupt, the DMA and HDMA set up, the sound chip mid-sample). */
    static const unsigned gaps[3] = {0, 1, 7};
    for (unsigned point = 0; point < 3; ++point) {
        for (unsigned n = 0; n < gaps[point]; ++n) run(1, warmup);
        const size_t saved = rr16_snes_snap_save(first, bound);
        CHECK(saved > 0 && saved <= bound);
        snapshot_bytes = saved;
        memset(other, 0xa5, bound);
        CHECK(rr16_snes_snap_save(other, bound) == saved);
        CHECK(!memcmp(first, other, saved));                    /* a save is a function of the state, not of the buffer */
        CHECK(rr16_snes_snap_save(other, saved - 1) == 0);      /* a capacity too small: refused */
        const uint64_t digest_before = rr16_snes_digest();
        const unsigned at = frame_index;
        run(length, one);
        CHECK(rr16_snes_snap_load(first, saved));
        CHECK(rr16_snes_digest() == digest_before);             /* the load put every digested byte back */
        memset(other, 0x5a, bound);
        CHECK(rr16_snes_snap_save(other, bound) == saved);
        CHECK(!memcmp(first, other, saved));                    /* load then save: the same bytes */
        frame_index = at;
        run(length, two);
        same(one, two, length);                                 /* the replay equals the first run */
        /* A load that is refused leaves the machine alone. */
        const uint64_t digest_after = rr16_snes_digest();
        CHECK(!rr16_snes_snap_load(first, saved - 1));
        CHECK(!rr16_snes_snap_load(first, saved + 1));
        CHECK(!rr16_snes_snap_load(first, 0));
        CHECK(!rr16_snes_snap_load(first, bound + 1));
        CHECK(!rr16_snes_snap_load(NULL, saved));
        CHECK(rr16_snes_digest() == digest_after);
        /* Back again: load, run a few frames, load the same snapshot once more, run the whole span: still the first run. */
        CHECK(rr16_snes_snap_load(first, saved));
        frame_index = at;
        run(8 < length ? 8 : length, burn);
        CHECK(rr16_snes_snap_load(first, saved));
        frame_index = at;
        run(length, two);
        same(one, two, length);
        /* A silent frame does what a live frame does to the guest (the kit then drops its picture and sound). */
        rr16_snes_side_effects(false);
        CHECK(rr16_snes_snap_load(first, saved));
        frame_index = at;
        run(length, two);
        rr16_snes_side_effects(true);
        same(one, two, length);
    }
    /* The cartridge save of a session: the battery RAM out, the same bytes back in, a wrong size refused; none on a board without one. */
    {
        const size_t size = rr16_snes_session_save(NULL, 0);
        if (size) {
            uint8_t *image = malloc(size);
            CHECK(image && g_snes->cart->ram && g_snes->cart->ramSize == size);
            CHECK(rr16_snes_session_save(image, size) == size);
            CHECK(!memcmp(image, g_snes->cart->ram, size));
            CHECK(rr16_snes_session_save(image, size - 1) == 0);
            memset(g_snes->cart->ram, 0x5a, size);
            CHECK(rr16_snes_session_save_put(image, size));
            CHECK(!memcmp(image, g_snes->cart->ram, size));
            CHECK(!rr16_snes_session_save_put(image, size - 1));
            CHECK(!rr16_snes_session_save_put(NULL, size));
            free(image);
        }
        saved_ram = size;
    }
    printf("{\"checks\":%u,\"passed\":true,\"snapshot_bytes\":%zu,\"bound\":%zu,\"frames_per_run\":%u,"
           "\"picture_differences\":%u,\"first_picture_difference\":%d,\"sound_differences\":%u,\"first_sound_difference\":%d,\"session_save_bytes\":%zu}\n",
           checks, snapshot_bytes, bound, length, picture_differences, (int)first_picture, sound_differences, (int)first_sound, saved_ram);
    rr16_shutdown();
    return 0;
}
#ifdef _WIN32
int WINAPI WinMain(HINSTANCE a, HINSTANCE b, LPSTR c, int d) { (void)a; (void)b; (void)c; (void)d; return main(__argc, __argv); }
#endif
