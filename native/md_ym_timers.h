/* CPU-visible YM2612 timers. The queued audio renderer has its own clock;
 * polling must see flags now, not when that queue is drained at frame end.
 * See Sega's YM2612 registers $24-$27 and docs/CONSOLES_16BIT.md. */
#ifndef RR_MD_YM_TIMERS_H
#define RR_MD_YM_TIMERS_H
#include <stdint.h>
#include <stdbool.h>
typedef struct RrMdYmTimers {
    uint16_t a;
    uint8_t b, mode, status;
    uint64_t deadline[2];
    bool running[2];
} RrMdYmTimers;
static uint64_t rr_md_ym_period(const RrMdYmTimers *t, unsigned index) {
    return index ? (256u - t->b) * 16128ull : (1024u - t->a) * 1008ull;
}
static void rr_md_ym_advance(RrMdYmTimers *t, uint64_t now) {
    for (unsigned i = 0; i < 2; ++i) {
        if (!t->running[i] || now < t->deadline[i]) continue;
        if (t->mode & (4u << i)) t->status |= (uint8_t)(1u << i);
        /* A frequency write changes the next reload, not the current count. */
        uint64_t period = rr_md_ym_period(t, i);
        t->deadline[i] += ((now - t->deadline[i]) / period + 1u) * period;
    }
}
static void rr_md_ym_write(RrMdYmTimers *t, uint8_t reg, uint8_t value, uint64_t now) {
    rr_md_ym_advance(t, now);
    if (reg == 0x24) t->a = (uint16_t)((t->a & 3u) | (value << 2));
    else if (reg == 0x25) t->a = (uint16_t)((t->a & 0x3fcu) | (value & 3u));
    else if (reg == 0x26) t->b = value;
    else if (reg == 0x27) {
        for (unsigned i = 0; i < 2; ++i) {
            if (value & (0x10u << i)) t->status &= (uint8_t)~(1u << i);
            bool load = (value & (1u << i)) != 0;
            /* Clearing an overflow flag must not restart a running timer. */
            if (load && !t->running[i]) {
                uint64_t tick = i ? 16128ull : 1008ull;
                t->deadline[i] = now - now % tick + rr_md_ym_period(t, i);
            }
            t->running[i] = load;
        }
        t->mode = value;
    }
}
void rr16_md_ym_reset(void);
const RrMdYmTimers *rr16_md_ym_state(void);
#endif
