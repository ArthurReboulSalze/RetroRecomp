/* The AY-3-8910 sound generator as a chip of its own. MIT, Retro-Recomp.
 *
 * Machine-neutral: the MSX family uses it now (native/msx_machine/msx_psg.c), the ZX Spectrum 128K and the Amstrad CPC next.
 * Written from the General Instrument AY-3-8910 data manual (moved unchanged from msx_psg.c on 21 November 2026). A YM2149 is
 * played with the AY's 16 levels and 16-step envelope here: its own 32-step envelope and DAC levels are not modelled.
 *
 * The chip advances in ticks of 8 chip clocks; the machine decides how many CPU cycles a tick is (16 on the MSX and on the
 * Spectrum 128K, whose chip runs at the CPU clock / 2; 32 on the CPC, 1 MHz against 4 MHz), mixes the three channel levels with
 * its own sounds and resamples them.
 * - a tone channel toggles every TP ticks (frequency clock / (16 TP)); a period of 0 acts as 1;
 * - the noise generator, a 17-bit shift register (taps 0 and 3), shifts every NP x 2 ticks;
 * - the envelope takes one of its 16 steps every EP x 2 ticks (a whole ramp lasts 256 EP / clock); writing R13 restarts
 *   it (ay38910_shape_written); shapes 0-7 fall to 0 and hold, 8 and 12 repeat, 10 and 14 alternate, 11 and 13 hold at the
 *   top, 9 and 15 hold at 0.
 * A channel sounds when (tone or tone disabled) and (noise or noise disabled), at its fixed level or the envelope's, on the
 * sixteen measured, normalised AY-3-8910 levels published with ayumi (MIT, Peter Sovietov), scaled to 0..32767.
 *
 * The registers stay with the machine (each one decodes the ports and the I/O pins R14/R15 its own way): the tick takes them
 * as `r`, the sixteen register values as written. The tick is inline here, as it was inside msx_psg.c: a machine runs it a few
 * thousand times a frame. */
#ifndef RR_AY38910_H
#define RR_AY38910_H

#include <stdint.h>

typedef struct {
    uint32_t ticks;                /* ticks run so far (noise and envelope run on every second one) */
    uint16_t tone_count[3];
    uint8_t tone_out[3];
    uint16_t noise_count;
    uint32_t lfsr;
    uint16_t env_count;
    uint8_t env_step, env_up, env_holding;
} Ay38910;

/* Power-on state: every counter at 0, the noise register at 1. */
void ay38910_reset(Ay38910 *ay);
/* A write of `value` to R13 (the envelope shape) restarts the envelope. Call it after storing the register. */
void ay38910_shape_written(Ay38910 *ay, uint8_t value);

static inline unsigned ay38910_period(const uint8_t *r, int fine)
{
    unsigned p = (unsigned)r[fine] | ((unsigned)(r[fine + 1] & 0x0F) << 8);
    return p ? p : 1;
}

static inline void ay38910_envelope_tick(Ay38910 *ay, uint8_t shape)
{
    if (ay->env_holding)
        return;
    if (++ay->env_step < 16)
        return;
    ay->env_step = 0;
    if (!(shape & 8) || shape == 9 || shape == 15) {          /* fall to 0 and hold */
        ay->env_up = 0; ay->env_step = 15; ay->env_holding = 1;
    } else if (shape == 11 || shape == 13) {                  /* hold at the top */
        ay->env_up = 1; ay->env_step = 15; ay->env_holding = 1;
    } else if (shape == 10 || shape == 14) {                  /* alternate */
        ay->env_up ^= 1;
    }                                                         /* 8 and 12 repeat the same ramp */
}

/* One tick: the counters move, then `levels` receives each channel's output (0..32767; 0 when the channel is silent). */
static inline void ay38910_tick(Ay38910 *ay, const uint8_t r[16], int levels[3])
{
    /* ayumi's normalised levels (0, 0.00999465934234, 0.0144502937362, ... 0.805584802014, 1.0) x 32767, rounded. */
    static const int level_scale[16] = { 0, 327, 473, 690, 1006, 1492, 2113, 3518, 4148, 6717, 9575, 12217, 16139, 20818,
                                         26397, 32767 };
    unsigned tick = ++ay->ticks;
    for (int c = 0; c < 3; ++c) {
        if (++ay->tone_count[c] >= ay38910_period(r, c * 2)) {
            ay->tone_count[c] = 0;
            ay->tone_out[c] ^= 1;
        }
    }
    if (tick & 1) {                                           /* noise and envelope run at half the tick rate */
        unsigned np = r[6] & 0x1F;
        if (++ay->noise_count >= (np ? np : 1)) {
            ay->noise_count = 0;
            ay->lfsr = (ay->lfsr >> 1) | (((ay->lfsr ^ (ay->lfsr >> 3)) & 1) << 16);
        }
        unsigned ep = (unsigned)r[11] | ((unsigned)r[12] << 8);
        if (++ay->env_count >= (ep ? ep : 1)) {
            ay->env_count = 0;
            ay38910_envelope_tick(ay, r[13] & 15);
        }
    }
    int noise = ay->lfsr & 1;
    for (int c = 0; c < 3; ++c) {
        int tone_on = (ay->tone_out[c] | ((r[7] >> c) & 1)) & (noise | ((r[7] >> (c + 3)) & 1));
        unsigned level = (r[8 + c] & 0x10) ? (ay->env_up ? ay->env_step : 15u - ay->env_step) : (r[8 + c] & 15u);
        levels[c] = tone_on ? level_scale[level] : 0;
    }
}

#endif
