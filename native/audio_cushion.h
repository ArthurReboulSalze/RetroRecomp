/* Host-only adaptive output reserve shared by the console players.
 * A device period that finds no PCM while the guest is still producing raises
 * the start/keep reserve by one step. A step comes back after a clean wait of
 * twice the interval between the last two gaps (4 s minimum, 2 min maximum):
 * a machine with headroom returns to +0 ms within seconds, whereas recurring
 * scheduling hitches or a borderline machine keep the reserve they need.
 * Guest audio, its sample rate and its timeline never change. The reserve adds
 * bounded, reported output latency; physical latency stays unmeasured.
 * One thread raises and relaxes; others only read 32-bit values. */
#ifndef RR_AUDIO_CUSHION_H
#define RR_AUDIO_CUSHION_H
#include <SDL.h>
#include <stdbool.h>

#define RR_CUSHION_STEP_MS 5
#define RR_CUSHION_MAX_MS 60
#define RR_CUSHION_RELAX_SECONDS 4u
#define RR_CUSHION_RELAX_MAX_SECONDS 120u
/* A block pushed this recently means the guest is running: a paused menu,
 * a load or shutdown also empties the queue and must not raise the reserve. */
#define RR_CUSHION_ACTIVE_MS 100u

typedef struct {
    SDL_atomic_t extra_ms, last_push, raises;
    Uint32 clean_frames, since_gap, interval;
    bool seen_gap;
} RrAudioCushion;

/* Milliseconds from the performance counter: SDL_GetTicks needs the timer
 * subsystem, which some players and checks never initialize. */
static inline Uint32 rr_cushion_now_ms(void) {
    Uint64 per_ms = SDL_GetPerformanceFrequency() / 1000u;
    return (Uint32)(SDL_GetPerformanceCounter() / (per_ms ? per_ms : 1u));
}
/* Producer thread, once per delivered block. */
static inline void rr_cushion_pushed(RrAudioCushion *c) {
    SDL_AtomicSet(&c->last_push, (int)(rr_cushion_now_ms() | 1u));
}
static inline int rr_cushion_ms(RrAudioCushion *c) { return SDL_AtomicGet(&c->extra_ms); }
static inline Uint32 rr_cushion_frames(RrAudioCushion *c, Uint32 rate) {
    return (Uint32)((Uint64)rate * (Uint32)rr_cushion_ms(c) / 1000u);
}
/* A period found no PCM after playback had started. */
static inline bool rr_cushion_gap(RrAudioCushion *c) {
    Uint32 last = (Uint32)SDL_AtomicGet(&c->last_push);
    c->clean_frames = 0;
    /* Signed: the stored stamp is odd, possibly one millisecond ahead. */
    if (!last || (Sint32)(rr_cushion_now_ms() - last) > (Sint32)RR_CUSHION_ACTIVE_MS) return false;
    if (c->seen_gap) c->interval = c->since_gap;
    c->seen_gap = true; c->since_gap = 0;
    int extra = SDL_AtomicGet(&c->extra_ms);
    if (extra + RR_CUSHION_STEP_MS > RR_CUSHION_MAX_MS) return false;
    SDL_AtomicSet(&c->extra_ms, extra + RR_CUSHION_STEP_MS);
    SDL_AtomicIncRef(&c->raises);
    return true;
}
/* Frames played without a gap. Returns true when the reserve stepped down. */
static inline bool rr_cushion_clean(RrAudioCushion *c, Uint32 frames, Uint32 rate) {
    if (c->since_gap < 0xf0000000u) c->since_gap += frames;
    int extra = SDL_AtomicGet(&c->extra_ms);
    if (!extra) { c->clean_frames = 0; return false; }
    c->clean_frames += frames;
    Uint64 wait = (Uint64)rate * RR_CUSHION_RELAX_SECONDS, twice = 2ull * c->interval;
    if (twice > wait) wait = SDL_min(twice, (Uint64)rate * RR_CUSHION_RELAX_MAX_SECONDS);
    if (c->clean_frames < wait) return false;
    c->clean_frames = 0;
    SDL_AtomicSet(&c->extra_ms, extra - RR_CUSHION_STEP_MS);
    return true;
}
#endif
