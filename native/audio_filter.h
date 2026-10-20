/* Optional host tone control. Off is a byte-exact bypass, with no lookahead,
 * buffering, resampling or change to the emulated audio hardware. */
#ifndef RR_AUDIO_FILTER_H
#define RR_AUDIO_FILTER_H
#include <math.h>
#include <stdint.h>
typedef struct {
    double first[2], second[2], alpha;
    int mode, rate, channels, floating, ready;
} RrAudioFilter;
static inline void rr_audio_filter(void *pcm, unsigned frames, int channels,
        int floating, int rate, int mode, RrAudioFilter *s) {
    if (!mode || mode > 2 || rate <= 0 || channels < 1 || channels > 2) {
        s->ready = 0; return;
    }
    if (mode != s->mode || rate != s->rate || channels != s->channels || floating != s->floating) s->ready = 0;
    if (!s->ready) {
        s->mode = mode; s->rate = rate; s->channels = channels; s->floating = floating;
        s->alpha = 1.0 - exp(-6.283185307179586 * (mode == 1 ? 12000.0 : 6000.0) / rate);
    }
    for (unsigned i = 0; i < frames; ++i) {
        for (int ch = 0; ch < channels; ++ch) {
            unsigned n = i * channels + ch;
            double x = floating ? ((float *)pcm)[n] : ((int16_t *)pcm)[n];
            if (!s->ready) s->first[ch] = s->second[ch] = x;
            s->first[ch] += s->alpha * (x - s->first[ch]);
            s->second[ch] += s->alpha * (s->first[ch] - s->second[ch]);
            if (floating) ((float *)pcm)[n] = (float)s->second[ch];
            else ((int16_t *)pcm)[n] = (int16_t)(s->second[ch] >= 0 ? s->second[ch] + .5 : s->second[ch] - .5);
        }
        s->ready = 1;
    }
}
#endif
