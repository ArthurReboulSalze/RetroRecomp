/* A sound chip's levels over guest cycles, turned into samples at the machine's stream rate: the box filter every machine on a
 * level-driven chip shares (the Amstrad CPC's AY-3-8912 first; the ZX Spectrum's AY and beeper, the SG-1000 and ColecoVision's
 * SN76489 next; the MSX's PSG later, with its identity proof). MIT, Retro-Recomp. Header-only, machine-neutral.
 *
 * What it does and nothing more: the caller says which level (one channel, or a left / right pair) its chip outputs for how
 * many guest cycles (audio_box_feed), or until which cycle (audio_box_hold); the box gives each output sample the mean level
 * over the sample's interval, weighted by cycles, clamped to int16, and keeps the samples until the caller takes them
 * (audio_box_take). A sample that finds the buffer full is counted (`dropped`) and lost. The host kit's resampling to the
 * device's rate, its FIR, its ring and the device are after it (audio_output.inc, rrhk_audio), never here.
 *
 * Time: the sample boundaries are kept in fixed point, `next_sample` in guest cycles x 65536 (the form of the MSX's and the
 * ZX Spectrum's loops), one sample every `step` = clock x 65536 / rate of them, so a rate that does not divide the clock keeps
 * its fraction and the stream never drifts. A sample ends at the first whole cycle at or past its boundary
 * (ceil(next_sample / 65536)). The stream depends only on the levels and their cycles: feeding one long span or the same
 * levels cut in many short ones gives the same samples, byte for byte (the caller's partial chip tick is its own: it feeds the
 * level its chip holds for the cycles it ran).
 *
 * Note for a machine that moves onto it: the MSX's loop averages its ticks with equal weight and gives a whole tick to the
 * sample its end falls in; this box weighs each level by its cycles, so a sample that cuts a tick differs. That difference is
 * the move's to measure (its identity proof), not hidden here.
 *
 * State for a quick state or a rollback snapshot: every field but `out` (the buffer stays the caller's). */
#ifndef RR_AUDIO_BOX_H
#define RR_AUDIO_BOX_H
#include <stdint.h>
#include <string.h>

typedef struct {
    uint64_t time;          /* the guest cycle the stream has reached */
    uint64_t next_sample;   /* the end of the sample being built, guest cycles x 65536 */
    uint64_t step;          /* guest cycles x 65536 per sample */
    int64_t acc[2];         /* the levels x cycles of the sample being built */
    uint64_t acc_cycles;
    uint32_t count;         /* samples (frames of `channels` values) waiting in `out` */
    uint32_t capacity;      /* the most `out` holds */
    uint32_t dropped;       /* samples lost to a full buffer */
    uint8_t channels;       /* 1 (mono) or 2 (left, right interleaved) */
    int16_t *out;           /* the caller's buffer: capacity x channels values */
} AudioBox;

/* Start (or restart) the stream at guest cycle `cycle`, empty, with `channels` (1 or 2), the guest clock and the output rate
 * (both in Hz) and the caller's buffer of `capacity` samples. */
static inline void audio_box_init(AudioBox *box, unsigned channels, uint64_t clock_hz, unsigned rate, int16_t *buffer,
                                  uint32_t capacity, uint64_t cycle)
{
    memset(box, 0, sizeof *box);
    box->channels = (uint8_t)(channels == 2 ? 2 : 1);
    box->step = rate ? clock_hz * 65536u / rate : 0;
    box->out = buffer;
    box->capacity = capacity;
    box->time = cycle;
    box->next_sample = (cycle << 16) + box->step;
}

/* Restart at guest cycle `cycle` with the same clock, rate and buffer: nothing waiting, nothing being built, the drops cleared. */
static inline void audio_box_reset(AudioBox *box, uint64_t cycle)
{
    box->time = cycle;
    box->next_sample = (cycle << 16) + box->step;
    box->acc[0] = box->acc[1] = 0;
    box->acc_cycles = 0;
    box->count = 0;
    box->dropped = 0;
}

static inline int16_t audio_box_clamp(int64_t value)
{
    return (int16_t)(value > 32767 ? 32767 : value < -32768 ? -32768 : value);
}

/* The levels `left` and `right` (a mono box takes `left`) held from the stream's time up to guest cycle `until`. */
static inline void audio_box_hold(AudioBox *box, int left, int right, uint64_t until)
{
    if (!box->step)
        return;
    while (box->time < until) {
        uint64_t sample_end = (box->next_sample + 65535u) >> 16;     /* the first whole cycle at or past the boundary */
        uint64_t end = sample_end < until ? sample_end : until;
        if (end <= box->time)
            end = box->time + 1;
        uint64_t span = end - box->time;
        box->acc[0] += (int64_t)left * (int64_t)span;
        box->acc[1] += (int64_t)right * (int64_t)span;
        box->acc_cycles += span;
        box->time = end;
        if ((box->time << 16) >= box->next_sample) {
            if (box->count < box->capacity) {
                int16_t *at = box->out + (size_t)box->count * box->channels;
                at[0] = audio_box_clamp(box->acc[0] / (int64_t)box->acc_cycles);
                if (box->channels == 2)
                    at[1] = audio_box_clamp(box->acc[1] / (int64_t)box->acc_cycles);
                ++box->count;
            } else {
                ++box->dropped;
            }
            box->acc[0] = box->acc[1] = 0;
            box->acc_cycles = 0;
            box->next_sample += box->step;
        }
    }
}

/* The levels held for `cycles` more guest cycles. */
static inline void audio_box_feed(AudioBox *box, int left, int right, uint64_t cycles)
{
    audio_box_hold(box, left, right, box->time + cycles);
}

/* One level on a mono box (or on both sides of a stereo one), for `cycles` guest cycles. */
static inline void audio_box_feed_mono(AudioBox *box, int level, uint64_t cycles)
{
    audio_box_hold(box, level, level, box->time + cycles);
}

/* Move up to `max` waiting samples (each `channels` values) to `out`, oldest first; how many were moved. */
static inline uint32_t audio_box_take(AudioBox *box, int16_t *out, uint32_t max)
{
    uint32_t n = box->count < max ? box->count : max;
    size_t values = (size_t)n * box->channels;
    memcpy(out, box->out, values * sizeof *out);
    memmove(box->out, box->out + values, ((size_t)(box->count - n) * box->channels) * sizeof *out);
    box->count -= n;
    return n;
}
#endif
