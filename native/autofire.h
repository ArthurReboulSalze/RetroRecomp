/* RetroRecomp rapid fire, shared by all console hosts. MIT. */
#ifndef RR_AUTOFIRE_H
#define RR_AUTOFIRE_H
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint64_t start, last;
    bool held;
} RrAutofire;

/* One guest frame pressed, one released: the fastest regular cadence a game
 * polling once per frame can distinguish. Never use display/wall-clock time.
 * Repeated reads stay identical; a new press or rewind starts immediately. */
static inline bool rr_autofire(RrAutofire *fire, bool down, bool enabled, uint64_t frame) {
    if (!enabled || !down) { fire->held = false; return down; }
    if (!fire->held || frame < fire->last) fire->start = frame;
    fire->held = true;
    fire->last = frame;
    return ((frame - fire->start) & 1) == 0;
}
#endif
