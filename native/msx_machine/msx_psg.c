/* The AY-3-8910 sound generator of the MSX and the key click. MIT, Retro-Recomp.
 *
 * The AY-3-8910 itself is native/ay38910 (shared with the other machines that have the chip since 21 November 2026, moved
 * there unchanged). The chip runs at the CPU clock / 2 (1,789,772.5 Hz); it advances in ticks of 16 CPU cycles (the chip
 * clock / 8):
 * - a tone channel toggles every TP ticks, so its frequency is clock / (16 TP); a period of 0 acts as 1;
 * - the noise generator, a 17-bit shift register (taps 0 and 3), shifts every NP x 2 ticks;
 * - the envelope takes one of its 16 steps every EP x 2 ticks (a whole ramp lasts 256 EP / clock); writing R#13
 *   restarts it; shapes 0-7 fall to 0 and hold, 8 and 12 repeat, 10 and 14 alternate, 11 and 13 hold at the top,
 *   9 and 15 hold at 0.
 * A channel sounds when (tone or tone disabled) and (noise or noise disabled), at its fixed level or the envelope's.
 * The sixteen output levels are the measured, normalised AY-3-8910 levels published with ayumi (MIT, Peter Sovietov).
 *
 * Mixing: the three channels at equal weight, and the key click (PPI port C bit 7) at 0.756 of a PSG channel at volume
 * 15: the ratio measured on 12 November 2026 from the outside in openMSX 22.0 run as a separate program (a black box),
 * from its recorded output of an authored cartridge playing PSG channel A alone (880.8 Hz, volume 15) then the click
 * alone (toggled at 878.6 Hz): the two fundamentals, 5,322 and 4,025. A Konami SCC cartridge's five channels at the
 * PSG's weight (its full scale equal to the PSG's: our choice; the same recording gave 0.800 for an SCC channel). The
 * mix is the same whether or not an SCC is plugged in, so the PSG keeps its level. Not measured on an MSX: not
 * validated.
 * Output: box-filtered to MSX_AUDIO_RATE. */
#include "msx_machine.h"

#include <string.h>

enum { TICK = 16, PSG_WEIGHT = 21000, CLICK_WEIGHT = 15876, SCC_WEIGHT = 21000 };   /* 15876 = 21000 x 0.756 */
/* MSX-MUSIC, when the machine has it, is added to the other sounds as openMSX adds its devices, at a gain set so that the YM2413
 * against the PSG has openMSX 22.0's balance on its C-BIOS MSX2+ machine (measured on tools/msx_fm_cart.py: one violin voice and
 * one PSG tone, each against openMSX's record). The sum is held within the output's range. A machine without it mixes exactly
 * as before. */
enum { FM_GAIN = 51200, FM_LIMIT = 40959 };                     /* 40959 x 4 / 5 = 32767 after the headroom */
#define SAMPLE_STEP ((uint64_t)MSX_CPU_CLOCK * 65536u / MSX_AUDIO_RATE)

void msx_psg_reset(MsxMachine *m)
{
    MsxPsgSynth *s = &m->synth;
    memset(s, 0, sizeof *s);
    ay38910_reset(&s->chip);
    s->time = m->cycles;
    s->next_sample = (m->cycles << 16) + SAMPLE_STEP;
}

static int one_tick(MsxMachine *m, uint64_t now)
{
    MsxPsgSynth *s = &m->synth;
    int levels[3];
    ay38910_tick(&s->chip, m->psg, levels);
    int sum = levels[0] + levels[1] + levels[2];
    int click = (m->port_c & 0x80) ? 32767 : 0;
    int scc = 0;
    for (int i = 0; i < m->scc_count; ++i)
        scc += msx_scc_step(&m->scc[i]->scc, TICK);
    if (m->scc_count)
        scc = scc * 32767 / 600 / m->scc_count; /* five channels at full volume = full scale */
    if (m->fm) {
        int fm = m->fm->sample(m->fm->chip, now);
        int64_t mixed = ((int64_t)sum / 3 * PSG_WEIGHT + (int64_t)click * CLICK_WEIGHT + (int64_t)scc * SCC_WEIGHT
                         + (int64_t)fm * FM_GAIN) / (PSG_WEIGHT + CLICK_WEIGHT + SCC_WEIGHT);
        return (int)(mixed > FM_LIMIT ? FM_LIMIT : mixed < -FM_LIMIT ? -FM_LIMIT : mixed);
    }
    return (int)(((int64_t)sum / 3 * PSG_WEIGHT + (int64_t)click * CLICK_WEIGHT + (int64_t)scc * SCC_WEIGHT)
                 / (PSG_WEIGHT + CLICK_WEIGHT + SCC_WEIGHT));
}

void msx_psg_catch_up(MsxMachine *m)
{
    msx_psg_catch_up_to(m, m->cycles);
}

/* The sound up to `cycle` (at most the machine's time): the stream is the same whatever the steps it is produced in. */
void msx_psg_catch_up_to(MsxMachine *m, uint64_t cycle)
{
    MsxPsgSynth *s = &m->synth;
    if (cycle > m->cycles)
        cycle = m->cycles;
    if (cycle <= s->time)
        return;
    uint64_t now = s->time - s->tick_rest;                   /* the end of the last tick */
    while (now + TICK <= cycle) {
        now += TICK;
        int value = one_tick(m, now);
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
    s->tick_rest = (unsigned)(cycle - now);
    s->time = cycle;
}

void msx_psg_write(MsxMachine *m, uint8_t reg, uint8_t value)
{
    msx_psg_catch_up(m);
    m->psg[reg] = value;
    if (reg == 13)                                            /* a write to the shape restarts the envelope */
        ay38910_shape_written(&m->synth.chip, value);
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
