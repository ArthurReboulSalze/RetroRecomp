/* The SN76489A: see sn76489.h. MIT, Retro-Recomp.
 *
 * Written from the Texas Instruments SN76489A data sheet. The chip runs at the CPU clock; here it advances in ticks of 16 CPU cycles:
 * - a tone channel toggles every N ticks (N the 10-bit register, 0 acting as 1024), so its frequency is clock / (32 N);
 * - the noise channel toggles at 16, 32 or 64 ticks (clock / 512, / 1024, / 2048) or at the third tone's period, and shifts its 15-bit
 *   register on each rising edge: white noise feeds back the exclusive-or of bits 0 and 1, periodic noise bit 0; writing the noise
 *   register resets the register to 4000h;
 * - the attenuation is 2 dB a step, 15 is off.
 * The levels below and the mix (the four channels added at equal weight, headroom left) are our choice and not validated against the chip.
 * Output: box-filtered to SN_AUDIO_RATE, mono. */
#include "sn76489.h"

#include <string.h>

/* 6553 x 10^(-0.1 x step), rounded: 2 dB of amplitude a step. Four channels at full level add up to 26212 of 32767. */
static const int level[16] = { 6553, 5206, 4135, 3285, 2609, 2073, 1646, 1308, 1039, 825, 655, 520, 413, 328, 260, 0 };

enum { TICK = 16 };
#define SAMPLE_STEP ((uint64_t)SN_CPU_CLOCK * 65536u / SN_AUDIO_RATE)

void sn76489_reset(Sn76489 *s, uint64_t cycle)
{
    memset(s, 0, sizeof *s);
    for (int i = 0; i < 4; ++i)
        s->volume[i] = 15;
    s->lfsr = 0x4000;
    s->time = cycle;
    s->next_sample = (cycle << 16) + SAMPLE_STEP;
}

static unsigned tone_period(const Sn76489 *s, int channel)
{
    return s->tone[channel] ? s->tone[channel] : 0x400u;
}

static unsigned noise_period(const Sn76489 *s)
{
    return (s->noise & 3) == 3 ? tone_period(s, 2) : 16u << (s->noise & 3);
}

void sn76489_write(Sn76489 *s, uint8_t value)
{
    if (value & 0x80) {                         /* a latch byte: the register, then its low four bits */
        s->latch = (value >> 4) & 7;
        switch (s->latch) {
        case 0: case 2: case 4: {
            int c = s->latch >> 1;
            s->tone[c] = (uint16_t)((s->tone[c] & 0x3F0) | (value & 15));
            break;
        }
        case 6:
            s->noise = value & 7;
            s->lfsr = 0x4000;
            break;
        default:
            s->volume[s->latch >> 1] = value & 15;
            break;
        }
        return;
    }
    switch (s->latch) {                         /* a data byte: the high six bits of a tone, else the register again */
    case 0: case 2: case 4: {
        int c = s->latch >> 1;
        s->tone[c] = (uint16_t)((s->tone[c] & 15) | ((value & 0x3F) << 4));
        break;
    }
    case 6:
        s->noise = value & 7;
        s->lfsr = 0x4000;
        break;
    default:
        s->volume[s->latch >> 1] = value & 15;
        break;
    }
}

static int one_tick(Sn76489 *s)
{
    for (int c = 0; c < 3; ++c) {
        if (++s->count[c] >= tone_period(s, c)) {
            s->count[c] = 0;
            s->out[c] ^= 1;
        }
    }
    if (++s->count[3] >= noise_period(s)) {
        s->count[3] = 0;
        s->out[3] ^= 1;
        if (s->out[3]) {                        /* the register shifts on a rising edge */
            unsigned feedback = (s->noise & 4) ? ((s->lfsr ^ (s->lfsr >> 1)) & 1u) : (s->lfsr & 1u);
            s->lfsr = (uint16_t)((s->lfsr >> 1) | (feedback << 14));
        }
    }
    int sum = 0;
    for (int c = 0; c < 3; ++c)
        if (s->out[c])
            sum += level[s->volume[c]];
    if (s->lfsr & 1)
        sum += level[s->volume[3]];
    return sum;
}

void sn76489_run(Sn76489 *s, uint64_t cycle)
{
    if (cycle <= s->time)
        return;
    uint64_t now = s->time - s->tick_rest;      /* the end of the last tick */
    while (now + TICK <= cycle) {
        now += TICK;
        int value = one_tick(s);
        s->acc += value;
        ++s->acc_ticks;
        while ((now << 16) >= s->next_sample) {
            s->next_sample += SAMPLE_STEP;
            int sample = s->acc_ticks ? s->acc / (int32_t)s->acc_ticks : value;
            s->acc = 0;
            s->acc_ticks = 0;
            if (s->sample_count < SN_AUDIO_BUFFER)
                s->samples[s->sample_count++] = (int16_t)sample;
            else
                ++s->dropped;
        }
    }
    s->tick_rest = (unsigned)(cycle - now);
    s->time = cycle;
}

unsigned sn76489_take(Sn76489 *s, int16_t *out, unsigned max)
{
    unsigned n = s->sample_count < max ? s->sample_count : max;
    memcpy(out, s->samples, n * sizeof *out);
    memmove(s->samples, s->samples + n, (s->sample_count - n) * sizeof *out);
    s->sample_count -= n;
    return n;
}
