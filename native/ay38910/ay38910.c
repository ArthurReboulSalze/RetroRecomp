/* The AY-3-8910 sound generator (ay38910.h). MIT, Retro-Recomp. Moved unchanged from native/msx_machine/msx_psg.c. */
#include "ay38910.h"

#include <string.h>

/* ayumi's normalised levels (0, 0.00999465934234, 0.0144502937362, ... 0.805584802014, 1.0) x 32767, rounded. */
static const int level_scale[16] = { 0, 327, 473, 690, 1006, 1492, 2113, 3518, 4148, 6717, 9575, 12217, 16139, 20818,
                                     26397, 32767 };

void ay38910_reset(Ay38910 *ay)
{
    memset(ay, 0, sizeof *ay);
    ay->lfsr = 1;
}

static unsigned period(const uint8_t *r, int fine)
{
    unsigned p = (unsigned)r[fine] | ((unsigned)(r[fine + 1] & 0x0F) << 8);
    return p ? p : 1;
}

static unsigned envelope_level(const Ay38910 *ay)
{
    return ay->env_up ? ay->env_step : 15u - ay->env_step;
}

static void envelope_tick(Ay38910 *ay, uint8_t shape)
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

void ay38910_tick(Ay38910 *ay, const uint8_t r[16], int levels[3])
{
    unsigned tick = ++ay->ticks;
    for (int c = 0; c < 3; ++c) {
        if (++ay->tone_count[c] >= period(r, c * 2)) {
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
            envelope_tick(ay, r[13] & 15);
        }
    }
    int noise = ay->lfsr & 1;
    for (int c = 0; c < 3; ++c) {
        int tone_on = (ay->tone_out[c] | ((r[7] >> c) & 1)) & (noise | ((r[7] >> (c + 3)) & 1));
        unsigned level = (r[8 + c] & 0x10) ? envelope_level(ay) : (r[8 + c] & 15u);
        levels[c] = tone_on ? level_scale[level] : 0;
    }
}

void ay38910_shape_written(Ay38910 *ay, uint8_t value)
{
    ay->env_step = 0;
    ay->env_count = 0;
    ay->env_holding = 0;
    ay->env_up = (value & 4) ? 1 : 0;
}
