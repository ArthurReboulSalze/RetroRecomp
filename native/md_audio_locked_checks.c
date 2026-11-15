/* A Mega Drive game locked to the display (1.7.7, HOST_KIT D30), on the adapted bridge alone: authored signal, no ROM.
 * The machine makes its frames 1/base times faster than its own clock (59.9228 Hz paced at 60 Hz: base 0.99871); the
 * device still takes 48,000 frames a second. The bridge's feed-forward (rr_feed = 1/base, megadrive_audio.py) is on or off
 * (off: its fill controller works alone). 300 simulated seconds of 512-frame pulls, measured after a 10 s settle: the band
 * the fill stays in, and no stretch, underrun or overflow. A development check, outside the stamps: it is not compiled into
 * a game, so editing it never moves a stamp or a quick-state key. */
#define RECOMP_AUDIO_DRC_IMPL
#include "bridge.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef RR_MD_AUDIO_FEED
#error "the adapted Mega Drive bridge is needed (retrorecomp/megadrive_audio.bridge)"
#endif

static void tone(int16_t *pcm, int frames) {
    for (int i = 0; i < frames; ++i) {
        pcm[i * 2] = (int16_t)(12000 * sin(i * 0.017) + 5000 * sin(i * 0.039));
        pcm[i * 2 + 1] = (int16_t)(12000 * sin(i * 0.017) + 5000 * sin(i * 0.039 + 1.0));
    }
}

static int locked(double base, int feed, double *low, double *high, double *mean, uint64_t *events) {
    rab_config cfg; rab_config_defaults(&cfg);
    cfg.source_rate = 223721; cfg.host_rate = 48000; cfg.channels = 2; cfg.target_ms = 25; cfg.preroll_ms = 25;
    rab_bridge b; if (rab_init(&b, &cfg)) return 1;
    if (feed) b.rr_feed = 1.0 / base;
    int16_t *input = (int16_t *)malloc((size_t)b.cap * 2 * sizeof(int16_t)); if (!input) return 2;
    tone(input, (int)b.cap);
    rab_push(&b, input, (int)(cfg.source_rate * .03));
    int16_t pcm[512 * 2]; double credit = 0, sum = 0; unsigned measured = 0; *low = 1e9; *high = -1e9;
    const unsigned settle = (unsigned)(10.0 * 48000 / 512), total = (unsigned)(300.0 * 48000 / 512);
    for (unsigned block = 0; block < total; ++block) {
        credit += 223721.0 * 512 / 48000.0 / base; unsigned frames = (unsigned)credit; credit -= frames;
        rab_push(&b, input, (int)frames); rab_pull(&b, pcm, 512);
        if (block >= settle) {
            double fill = b.stats.last_fill_ms; sum += fill; ++measured;
            if (fill < *low) *low = fill;
            if (fill > *high) *high = fill;
        }
    }
    *mean = sum / measured;
    *events = b.stats.stretch_events + b.stats.underrun_events + b.stats.overflow_drops;
    free(input); rab_free(&b); return 0;
}

int main(void) {
    const double bases[] = {0.99871, 1.003, 1.0}; int failed = 0;
    printf("{\"locked\":[");
    for (unsigned i = 0; i < 3; ++i) for (int feed = 0; feed < 2; ++feed) {
        double low, high, mean; uint64_t events;
        if (locked(bases[i], feed, &low, &high, &mean, &events)) return 1;
        /* With the feed-forward the fill stays within 3 ms of its 25 ms target; nothing is ever concealed or dropped. */
        if (events || (feed && (low < 22.0 || high > 28.0))) failed = 1;
        printf("%s{\"base\":%.5f,\"feed_forward\":%s,\"fill_min_ms\":%.3f,\"fill_max_ms\":%.3f,\"fill_mean_ms\":%.3f,\"stretch_underrun_overflow\":%llu}",
               i || feed ? "," : "", bases[i], feed ? "true" : "false", low, high, mean, (unsigned long long)events);
    }
    printf("],\"passed\":%s}\n", failed ? "false" : "true");
    return failed;
}
