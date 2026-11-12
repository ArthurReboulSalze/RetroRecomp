/* The AY-3-8910 sound generator of the MSX and the key click. MIT, Retro-Recomp.
 *
 * Written from the General Instrument AY-3-8910 data manual. The chip runs at the CPU clock / 2 (1,789,772.5 Hz);
 * here it advances in ticks of 16 CPU cycles (the chip clock / 8):
 * - a tone channel toggles every TP ticks, so its frequency is clock / (16 TP); a period of 0 acts as 1;
 * - the noise generator, a 17-bit shift register (taps 0 and 3), shifts every NP x 2 ticks;
 * - the envelope takes one of its 16 steps every EP x 2 ticks (a whole ramp lasts 256 EP / clock); writing R#13
 *   restarts it; shapes 0-7 fall to 0 and hold, 8 and 12 repeat, 10 and 14 alternate, 11 and 13 hold at the top,
 *   9 and 15 hold at 0.
 * A channel sounds when (tone or tone disabled) and (noise or noise disabled), at its fixed level or the envelope's.
 * The sixteen output levels are the measured, normalised AY-3-8910 levels published with ayumi (MIT, Peter Sovietov).
 *
 * Mixing: the three channels at equal weight and the key click (PPI port C bit 7) in the ratio of openMSX's C-BIOS
 * machine files (PSG 21000, click 16000), and a Konami SCC cartridge's five channels at the PSG's weight (its full
 * scale equal to the PSG's). The mix is the same whether or not an SCC is plugged in, so the PSG keeps its level.
 * These ratios are stated choices, not measurements of an MSX: not validated.
 * Output: box-filtered to MSX_AUDIO_RATE. */
#include "msx_machine.h"

#include <string.h>

/* ayumi's normalised levels (0, 0.00999465934234, 0.0144502937362, ... 0.805584802014, 1.0) x 32767, rounded. */
static const int level_scale[16] = { 0, 327, 473, 690, 1006, 1492, 2113, 3518, 4148, 6717, 9575, 12217, 16139, 20818,
                                     26397, 32767 };

enum { TICK = 16, PSG_WEIGHT = 21000, CLICK_WEIGHT = 16000, SCC_WEIGHT = 21000 };
#define SAMPLE_STEP ((uint64_t)MSX_CPU_CLOCK * 65536u / MSX_AUDIO_RATE)

void msx_psg_reset(MsxMachine *m)
{
    MsxPsgSynth *s = &m->synth;
    memset(s, 0, sizeof *s);
    s->lfsr = 1;
    s->time = m->cycles;
    s->next_sample = (m->cycles << 16) + SAMPLE_STEP;
}

static unsigned period(const uint8_t *r, int fine)
{
    unsigned p = (unsigned)r[fine] | ((unsigned)(r[fine + 1] & 0x0F) << 8);
    return p ? p : 1;
}

static unsigned envelope_level(const MsxPsgSynth *s)
{
    return s->env_up ? s->env_step : 15u - s->env_step;
}

static void envelope_tick(MsxPsgSynth *s, uint8_t shape)
{
    if (s->env_holding)
        return;
    if (++s->env_step < 16)
        return;
    s->env_step = 0;
    if (!(shape & 8) || shape == 9 || shape == 15) {          /* fall to 0 and hold */
        s->env_up = 0; s->env_step = 15; s->env_holding = 1;
    } else if (shape == 11 || shape == 13) {                  /* hold at the top */
        s->env_up = 1; s->env_step = 15; s->env_holding = 1;
    } else if (shape == 10 || shape == 14) {                  /* alternate */
        s->env_up ^= 1;
    }                                                         /* 8 and 12 repeat the same ramp */
}

static int one_tick(MsxMachine *m, unsigned tick)
{
    MsxPsgSynth *s = &m->synth;
    const uint8_t *r = m->psg;
    for (int c = 0; c < 3; ++c) {
        if (++s->tone_count[c] >= period(r, c * 2)) {
            s->tone_count[c] = 0;
            s->tone_out[c] ^= 1;
        }
    }
    if (tick & 1) {                                           /* noise and envelope run at half the tick rate */
        unsigned np = r[6] & 0x1F;
        if (++s->noise_count >= (np ? np : 1)) {
            s->noise_count = 0;
            s->lfsr = (s->lfsr >> 1) | (((s->lfsr ^ (s->lfsr >> 3)) & 1) << 16);
        }
        unsigned ep = (unsigned)r[11] | ((unsigned)r[12] << 8);
        if (++s->env_count >= (ep ? ep : 1)) {
            s->env_count = 0;
            envelope_tick(s, r[13] & 15);
        }
    }
    int noise = s->lfsr & 1, sum = 0;
    for (int c = 0; c < 3; ++c) {
        int tone_on = (s->tone_out[c] | ((r[7] >> c) & 1)) & (noise | ((r[7] >> (c + 3)) & 1));
        if (!tone_on)
            continue;
        unsigned level = (r[8 + c] & 0x10) ? envelope_level(s) : (r[8 + c] & 15u);
        sum += level_scale[level];
    }
    int click = (m->port_c & 0x80) ? 32767 : 0;
    int scc = 0;
    for (int i = 0; i < m->scc_count; ++i)
        scc += msx_scc_step(&m->scc[i]->scc, TICK);
    if (m->scc_count)
        scc = scc * 32767 / 600 / m->scc_count; /* five channels at full volume = full scale */
    return (int)(((int64_t)sum / 3 * PSG_WEIGHT + (int64_t)click * CLICK_WEIGHT + (int64_t)scc * SCC_WEIGHT)
                 / (PSG_WEIGHT + CLICK_WEIGHT + SCC_WEIGHT));
}

void msx_psg_catch_up(MsxMachine *m)
{
    MsxPsgSynth *s = &m->synth;
    if (m->cycles <= s->time)
        return;
    uint64_t now = s->time - s->tick_rest;                   /* the end of the last tick */
    while (now + TICK <= m->cycles) {
        now += TICK;
        int value = one_tick(m, ++s->ticks);
        s->acc += value;
        ++s->acc_ticks;
        while ((now << 16) >= s->next_sample) {
            s->next_sample += SAMPLE_STEP;
            int sample = s->acc_ticks ? s->acc / (int32_t)s->acc_ticks : value;
            s->acc = 0;
            s->acc_ticks = 0;
            int scaled = sample * 4 / 5;                     /* headroom */
            if (s->out_count < MSX_AUDIO_BUFFER)
                s->out[s->out_count++] = (int16_t)scaled;
            else
                ++s->dropped;
        }
    }
    s->tick_rest = (unsigned)(m->cycles - now);
    s->time = m->cycles;
}

void msx_psg_write(MsxMachine *m, uint8_t reg, uint8_t value)
{
    msx_psg_catch_up(m);
    m->psg[reg] = value;
    if (reg == 13) {                                          /* a write to the shape restarts the envelope */
        MsxPsgSynth *s = &m->synth;
        s->env_step = 0;
        s->env_count = 0;
        s->env_holding = 0;
        s->env_up = (value & 4) ? 1 : 0;
    }
}

unsigned msx_audio_take(MsxMachine *m, int16_t *out, unsigned max)
{
    MsxPsgSynth *s = &m->synth;
    unsigned n = s->out_count < max ? s->out_count : max;
    memcpy(out, s->out, n * sizeof *out);
    memmove(s->out, s->out + n, (s->out_count - n) * sizeof *out);
    s->out_count -= n;
    return n;
}
