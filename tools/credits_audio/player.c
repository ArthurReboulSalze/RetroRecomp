/* Converter credits only. Real MOD replay, never a prerendered recording.
 * libxmp-lite 4.7.3 (MIT) + miniaudio 0.11.23 (MIT); see assets/credits/NOTICE.md.
 * Decoder/device lifetime belongs to one Python worker. The device callback
 * alone advances libxmp; a tiny mutex protects snapshots and the mute flag.
 */
#define MA_NO_DECODING
#define MA_NO_ENCODING
#define MA_NO_RESOURCE_MANAGER
#define MA_NO_NODE_GRAPH
#define MA_NO_ENGINE
#define MA_NO_GENERATION
#define MA_NO_NULL
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#include "xmp.h"
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif

typedef struct {
    xmp_context xmp;
    ma_device device;
    ma_mutex mutex;
    int device_ready, muted, failed;
    int info[10]; /* order, pattern, row, bpm, four voice levels, L/R peaks */
    unsigned char percussion[31]; /* kick/snare/hat bits, exact bundled samples */
    uint32_t beats[6]; /* three monotonic hit counters, three last-hit volumes */
    const char *pcm;
    int pcm_size, pcm_used;
} rr_music;

static void observe_frame(rr_music *p, const struct xmp_frame_info *f) {
    int i, kind;
    p->info[0] = f->pos; p->info[1] = f->pattern;
    p->info[2] = f->row; p->info[3] = f->bpm;
    for (i = 0; i < 4; ++i) {
        const struct xmp_channel_info *c = &f->channel_info[i];
        const struct xmp_event *e = &c->event;
        int trigger_tick = 0;
        p->info[4+i] = c->volume;
        if (e->fxt == 0x0e && (e->fxp >> 4) == 0x0d) trigger_tick = e->fxp & 15;
        /* A held note/volume slide is not a new percussion hit. Portamento
         * continues the old voice; note delay fires on its actual tick. */
        if (f->frame != trigger_tick || !e->note || e->note > 120 ||
            !c->volume || c->instrument >= 31 || e->fxt == 3 || e->fxt == 5) continue;
        for (kind = 0; kind < 3; ++kind) {
            if (p->percussion[c->instrument] & (1 << kind)) {
                ++p->beats[kind];
                p->beats[3+kind] = c->volume;
            }
        }
    }
}

static int render(rr_music *p, short *out, int frames) {
    struct xmp_frame_info f;
    int i, used = 0, bytes = frames * 4, peak[2] = {0, 0};
    /* Same frame-buffer assembly as xmp_play_buffer, observing each decoded
     * tick once. This does not change samples or skip hits in large buffers. */
    while (used < bytes) {
        int copy;
        if (p->pcm_used == p->pcm_size) {
            int result = xmp_play_frame(p->xmp);
            xmp_get_frame_info(p->xmp, &f);
            if (result < 0 || f.buffer_size <= 0) {
                memset(out, 0, bytes);
                p->failed = 1;
                return -1;
            }
            observe_frame(p, &f);
            p->pcm = (const char *)f.buffer;
            p->pcm_size = f.buffer_size;
            p->pcm_used = 0;
        }
        copy = p->pcm_size - p->pcm_used;
        if (copy > bytes - used) copy = bytes - used;
        memcpy((char *)out + used, p->pcm + p->pcm_used, copy);
        p->pcm_used += copy;
        used += copy;
    }
    for (i = 0; i < frames * 2; ++i) {
        int amplitude = out[i] < 0 ? -(int)out[i] : out[i];
        if (amplitude > peak[i&1]) peak[i&1] = amplitude;
    }
    p->info[8] = peak[0]; p->info[9] = peak[1];
    return 0;
}

static void callback(ma_device *device, void *out, const void *in, ma_uint32 frames) {
    rr_music *p = (rr_music *)device->pUserData;
    (void)in;
    ma_mutex_lock(&p->mutex);
    render(p, (short *)out, (int)frames);
    if (p->muted) memset(out, 0, frames * 4);
    ma_mutex_unlock(&p->mutex);
}

API rr_music *rr_music_open(const void *data, long size) {
    rr_music *p;
    struct xmp_module_info module;
    /* Only the supplied, small 4-channel M.K. modules enter this decoder. */
    if (!data || size < 1084 || size > 1024 * 1024 ||
        memcmp((const char *)data + 1080, "M.K.", 4)) return NULL;
    p = (rr_music *)calloc(1, sizeof(*p));
    if (!p) return NULL;
    if (ma_mutex_init(&p->mutex) != MA_SUCCESS) { free(p); return NULL; }
    p->xmp = xmp_create_context();
    if (!p->xmp) goto fail;
    if (xmp_load_module_from_memory(p->xmp, data, size) != 0) goto fail;
    xmp_get_module_info(p->xmp, &module);
    if (!module.mod || module.mod->chn != 4) goto release;
    if (xmp_start_player(p->xmp, 48000, 0) != 0) goto release;
    xmp_set_player(p->xmp, XMP_PLAYER_INTERP, XMP_INTERP_SPLINE);
    xmp_set_player(p->xmp, XMP_PLAYER_MIX, 70);
    return p;
release:
    xmp_release_module(p->xmp);
fail:
    if (p->xmp) xmp_free_context(p->xmp);
    ma_mutex_uninit(&p->mutex);
    free(p);
    return NULL;
}

API int rr_music_start(rr_music *p) {
    ma_device_config config;
    if (!p || p->device_ready) return -1;
    config = ma_device_config_init(ma_device_type_playback);
    config.playback.format = ma_format_s16;
    config.playback.channels = 2;
    config.sampleRate = 48000;
    config.periodSizeInMilliseconds = 20;
    config.periods = 3;
    config.dataCallback = callback;
    config.pUserData = p;
    if (ma_device_init(NULL, &config, &p->device) != MA_SUCCESS) return -2;
    p->device_ready = 1;
    ma_device_set_master_volume(&p->device, 0.55f);
    return ma_device_start(&p->device) == MA_SUCCESS ? 0 : -3;
}

API void rr_music_mute(rr_music *p, int mute) {
    ma_mutex_lock(&p->mutex);
    p->muted = mute != 0;
    ma_mutex_unlock(&p->mutex);
}

API int rr_music_info(rr_music *p, int *info) {
    int failed;
    ma_mutex_lock(&p->mutex);
    memcpy(info, p->info, sizeof(p->info));
    failed = p->failed;
    ma_mutex_unlock(&p->mutex);
    return failed ? -1 : 0;
}

API int rr_music_percussion(rr_music *p, const unsigned char *map) {
    if (!p || !map || p->device_ready) return -1;
    memcpy(p->percussion, map, sizeof(p->percussion));
    return 0;
}

API void rr_music_beats(rr_music *p, uint32_t *beats) {
    ma_mutex_lock(&p->mutex);
    memcpy(beats, p->beats, sizeof(p->beats));
    ma_mutex_unlock(&p->mutex);
}

/* Test hook: render the identical decoder without opening an audio device. */
API int rr_music_render(rr_music *p, short *out, int frames) {
    if (!p || !out || frames < 1 || frames > 48000 || p->device_ready) return -1;
    return render(p, out, frames);
}

API void rr_music_close(rr_music *p) {
    if (!p) return;
    if (p->device_ready) ma_device_uninit(&p->device); /* joins callback first */
    xmp_end_player(p->xmp);
    xmp_release_module(p->xmp);
    xmp_free_context(p->xmp);
    ma_mutex_uninit(&p->mutex);
    free(p);
}
