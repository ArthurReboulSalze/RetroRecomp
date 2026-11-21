/* The AY-3-8910 (and YM2149 in its AY mode) sound generator as a chip of its own. MIT, Retro-Recomp.
 *
 * Machine-neutral: the MSX family uses it now (native/msx_machine/msx_psg.c), the ZX Spectrum 128K and the Amstrad CPC next.
 * Written from the General Instrument AY-3-8910 data manual (moved unchanged from msx_psg.c on 21 November 2026).
 *
 * The chip advances in ticks of 8 chip clocks; the machine decides how many CPU cycles a tick is (16 on the MSX and the
 * Spectrum 128K, whose chip runs at the CPU clock / 2), mixes the three channel levels with its own sounds and resamples.
 * - a tone channel toggles every TP ticks (frequency clock / (16 TP)); a period of 0 acts as 1;
 * - the noise generator, a 17-bit shift register (taps 0 and 3), shifts every NP x 2 ticks;
 * - the envelope takes one of its 16 steps every EP x 2 ticks (a whole ramp lasts 256 EP / clock); writing R13 restarts
 *   it (ay38910_shape_written); shapes 0-7 fall to 0 and hold, 8 and 12 repeat, 10 and 14 alternate, 11 and 13 hold at the
 *   top, 9 and 15 hold at 0.
 * A channel sounds when (tone or tone disabled) and (noise or noise disabled), at its fixed level or the envelope's, on the
 * sixteen measured, normalised AY-3-8910 levels published with ayumi (MIT, Peter Sovietov), scaled to 0..32767.
 *
 * The registers stay with the machine (each one decodes the ports and the I/O pins R14/R15 its own way): every call takes
 * them as `r`, the sixteen register values as written. */
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
/* One tick: the counters move, then `levels` receives each channel's output (0..32767; 0 when the channel is silent). */
void ay38910_tick(Ay38910 *ay, const uint8_t r[16], int levels[3]);

#endif
