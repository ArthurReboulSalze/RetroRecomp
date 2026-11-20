/* Deferred APU cycles. Included into the staged hw_apu.c after apu_cycle().
 *
 * apu_cycle() runs once per CPU cycle, and on most cycles nothing the CPU can see changes: the frame counter counts, the
 * channel timers count, the sound accumulator adds the same level again. The machine counts those cycles (rr_apu_pend)
 * and runs them together, up to the first cycle where something else can happen (rr_apu_horizon): a frame counter step,
 * the DMC timer, a delay, a DMA, a controller strobe, or a channel timer whose step changes the output. That cycle, and
 * every cycle while one of those is pending, goes through apu_cycle() itself. A register access, a state observation or a
 * save runs the pending cycles first (rr_apu_flush_sync) and leaves the next cycle to apu_cycle(): the state at every
 * access is the one the cycle-by-cycle machine has there, and the frame, state and sound digests are the same.
 *
 * What is computed in closed form is only what the cycles would have done without an event: counters and timers stepped by
 * the number of cycles, the channel steps and the noise register of a channel whose output is silent, and the sound
 * accumulator, which keeps its floating-point additions in the order of the single cycles. */

#define RR_FC(ntsc, pal) ((unsigned)(RR_NES_PAL ? (pal) : (ntsc)))

/* The number of cycles before the s-th cycle on which the APU's timers count (a get cycle: put is 0 there), seen from now. */
static inline unsigned rr_apu_before_get(unsigned s)
{
    return apu.put ? 2u * s - 1u : 2u * s - 2u;
}

/* How many of the next cycles are certain to be quiet (see above), at most 0xFFFF. */
static unsigned rr_apu_horizon(void)
{
    if (apu.strobe | apu.shift_delay[0] | apu.shift_delay[1] | apu.dmc_dma | apu.oam_dma | apu.dmc_dma_cooldown |
        apu.frame_irq_clear | apu.dmc_start_delay | apu.dmc_enable_delay | (uint8_t)!(apu.reset_delay & 0x80) |
        apu.len[0].reload | apu.len[1].reload | apu.len[2].reload | apu.len[3].reload | apu.quarter | apu.half)
        return 0;
    if (audio.on && hw_cart.watch_cpu) return 0;   /* expansion sound is sampled on every cycle */
    unsigned h = 0xFFFFu - apu.counter;            /* the counter is 16 bits */
    unsigned specials[5], n = 0, c = apu.counter;
    specials[n++] = RR_FC(7457, 8313);
    specials[n++] = RR_FC(14913, 16627);
    specials[n++] = RR_FC(22371, 24939);
    if (apu.five_step) {
        specials[n++] = RR_FC(37281, 41565);
        specials[n++] = RR_FC(37282, 41566);
    } else {
        specials[n++] = RR_FC(29828, 33252);
        specials[n++] = RR_FC(29829, 33253);
    }
    for (unsigned i = 0; i < n; i++)
        if (specials[i] > c && specials[i] - c - 1 < h) h = specials[i] - c - 1;
    if (!apu.five_step) {
        unsigned last = RR_FC(29830, 33254);
        if (last > c && last - c - 1 < h) h = last - c - 1;
    }
    /* The DMC timer counts down by two on get cycles; the cycle it reaches 0 is an event. */
    if (!(apu.dmc_timer & 1u)) {
        unsigned s = apu.dmc_timer ? apu.dmc_timer / 2u : 32768u;
        unsigned before = rr_apu_before_get(s);
        if (before < h) h = before;
    }
    if (audio.on) {
        if (!apu.noise_period) return 0;
        for (int ch = 0; ch < 2; ch++) {
            if (!apu.len[ch].count) continue;
            unsigned before = rr_apu_before_get((unsigned)apu.pulse[ch].timer + 1u);
            if (before < h) h = before;
        }
        if (apu.len[CH_NOISE].count && apu.noise_timer < h) h = apu.noise_timer;
        if (apu.len[CH_TRIANGLE].count && apu.tri_linear && apu.tri_timer < h) h = apu.tri_timer;
    }
    return h;
}

/* A timer that counts down by one per tick, reloads to `reload` and steps on reaching 0 after a tick at 0 ("0, reload" is one
 * step of length reload + 1): its state after `ticks` ticks, and how many times it stepped. */
static inline unsigned rr_apu_timer_run(uint16_t *timer, unsigned reload_period, unsigned ticks)
{
    unsigned t = *timer;
    if (ticks <= t) {
        *timer = (uint16_t)(t - ticks);
        return 0;
    }
    unsigned rest = ticks - (t + 1u);
    unsigned steps = 1u + rest / (reload_period + 1u);
    *timer = (uint16_t)(reload_period - rest % (reload_period + 1u));
    return steps;
}

/* k cycles with no event (rr_apu_horizon() >= k when they were counted). */
static void rr_apu_bulk(unsigned k)
{
    const unsigned gets = apu.put ? k / 2u : (k + 1u) / 2u;
    if (gets) apu.strobed = 0;
    apu.dmc_timer = (uint16_t)(apu.dmc_timer - 2u * gets);
    apu.counter = (uint16_t)(apu.counter + k);
    apu.len[CH_PULSE1].halt = (apu.reg[0] & 0x20) != 0;
    apu.len[CH_PULSE2].halt = (apu.reg[4] & 0x20) != 0;
    apu.len[CH_TRIANGLE].halt = (apu.reg[8] & 0x80) != 0;
    apu.len[CH_NOISE].halt = (apu.reg[12] & 0x20) != 0;
    if (audio.on) {
        for (int ch = 0; ch < 2; ch++) {
            Pulse *p = &apu.pulse[ch];
            unsigned steps = rr_apu_timer_run(&p->timer, p->period, gets);
            p->step = (uint8_t)((p->step + steps) & 7u);
        }
        /* Active noise and triangle steps are events; what is left only moves their timers and the noise register. */
        unsigned steps = rr_apu_timer_run(&apu.noise_timer, (unsigned)apu.noise_period - 1u, k);
        if (steps) {
            const unsigned tap = (apu.reg[14] & 0x80) ? 6u : 1u;
            uint16_t lfsr = apu.noise_lfsr;
            while (steps--) lfsr = (uint16_t)((lfsr >> 1) | (((lfsr ^ (lfsr >> tap)) & 1u) << 14));
            apu.noise_lfsr = lfsr;
        }
        rr_apu_timer_run(&apu.tri_timer, apu.tri_period, k);
        if (rr_mix_dirty) {
            uint8_t out[5];
            apu_channel_levels(out);
            rr_mix_level = audio.pulse_mix[out[0] + out[1]] + audio.tnd_mix[3 * out[2] + 2 * out[3] + out[4]];
            rr_mix_dirty = false;
        }
        const double level = rr_mix_level;
        double acc = audio.acc, phase = audio.phase;
        uint32_t count = audio.count;
        for (unsigned i = 0; i < k; i++) {
            acc += level;
            count++;
            phase += 1.0;
            if (phase >= audio.cycles_per_sample) {
                phase -= audio.cycles_per_sample;
                audio_emit(acc / count);
                acc = 0;
                count = 0;
            }
        }
        audio.acc = acc;
        audio.phase = phase;
        audio.count = count;
    }
    apu.put ^= (uint8_t)(k & 1u);
}

/* Run the pending cycles before the machine looks at the APU or changes it. The next cycle is a plain apu_cycle(). */
void rr_apu_flush_sync(void)
{
    unsigned n = rr_apu_pend;
    rr_apu_pend = 0;
    rr_apu_room = 1;
    if (n) rr_apu_bulk(n);
}

/* The cycle that ends the run: the pending ones before it, then this one. */
void rr_apu_run(void)
{
    unsigned n = rr_apu_pend - 1u;
    rr_apu_pend = 0;
    rr_apu_room = 1;
    if (n) rr_apu_bulk(n);
    apu_cycle();
    rr_apu_room = rr_apu_horizon() + 1u;
}

/* The state was replaced (power on, a loaded state): nothing is pending, the next cycle is a plain one. */
void rr_apu_reset(void)
{
    rr_apu_pend = 0;
    rr_apu_room = 1;
}

/* Observation or access: pending cycles first, and the access may change what the next cycles do. */
void rr_apu_touch(void)
{
    if (rr_apu_pend) rr_apu_flush_sync();
    rr_apu_room = 1;
}
