"""Host audio adaptations; never change guest PSG/YM generation or timing."""
from .core import ConversionError


def output(source: str) -> str:
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ConversionError('Mega Drive audio delivery source changed; adaptation refused.')
        source = source.replace(old, new)

    begin = '    #define MIX_INTO(out_n)'
    end = '    MIX_INTO(psg_frames);'
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ConversionError('Mega Drive audio mixer source changed; adaptation refused.')
    start, stop = source.index(begin), source.index(end) + len(end)
    source = source[:start] + '    rr_md_audio_mix(s_out,fm_buf,fm_frames,psg_buf,psg_frames,s_psg_vol_div);' + source[stop:]
    replace('static void genesis_audio_callback(void *user, Uint8 *stream, int len)',
        '''/* Opt-in host timings only: no per-sample clock, file write or new
 * synchronization. The existing SDL device lock protects callback counters. */
static int rr_md_audio_timed;
static Uint64 rr_md_audio_lock_ticks,rr_md_audio_pull_ticks,rr_md_audio_pulls;
/* The host kit's sound stage (volume, mute, audio filter) runs on what the device is given, and the host asks for the
 * output device by name: both are set by the host adapter, NULL until it does. */
void (*rr_md_audio_stage)(void *pcm,unsigned frames,int channels,int floating,int rate);
const char *rr_md_audio_device_name;
static int rr_md_psg_rate,rr_md_device_rate;
static void genesis_audio_callback(void *user, Uint8 *stream, int len)''')
    replace('    rab_pull(&s_bridge, (int16_t *)stream, frames);',
        '''    Uint64 started=rr_md_audio_timed?SDL_GetPerformanceCounter():0;
    rab_pull(&s_bridge, (int16_t *)stream, frames);
    if(started) {rr_md_audio_pull_ticks+=SDL_GetPerformanceCounter()-started;++rr_md_audio_pulls;}
    if(rr_md_audio_stage) rr_md_audio_stage(stream,(unsigned)frames,2,0,rr_md_device_rate);''')
    replace('int audio_init(int psg_sample_rate)\n{',
        '''int audio_init(int psg_sample_rate)
{
    const char *timing=getenv("RETRORECOMP_TIMING_REPORT");
    rr_md_audio_timed=timing && *timing;
    rr_md_audio_lock_ticks=rr_md_audio_pull_ticks=rr_md_audio_pulls=0;''')
    replace('''        SDL_LockAudioDevice(s_dev);
        rab_push(&s_bridge, s_out, (int)psg_frames);''',
        '''        Uint64 started=rr_md_audio_timed?SDL_GetPerformanceCounter():0;
        SDL_LockAudioDevice(s_dev);
        if(started)rr_md_audio_lock_ticks+=SDL_GetPerformanceCounter()-started;
        rab_push(&s_bridge, s_out, (int)psg_frames);''')
    # Adaptive host reserve: a pull that starved while frames kept arriving
    # moves the DRC target up one step; a long clean run moves it back.
    replace('    cfg.preroll_ms = 25.0;',
        '    cfg.preroll_ms = 25.0;\n'
        '    if (cfg.ring_ms < 230.0) cfg.ring_ms = 230.0; /* room for the adaptive reserve */')
    replace('    s_bridge_ready   = 1;',
        '    rr_md_device_rate = got.freq; rr_md_psg_rate = psg_sample_rate;\n'
        '    s_bridge_ready   = 1;\n'
        '    rr_md_target_base = s_bridge.cfg.target_ms; rr_md_high_base = s_bridge.cfg.em_high_ms;\n'
        '    memset(&rr_md_cushion, 0, sizeof(rr_md_cushion));')
    replace('''        s_prev_underruns = bst.underrun_events;
    }''', '''        if (bst.underrun_events != s_prev_underruns) {
            if (rr_cushion_gap(&rr_md_cushion)) rr_md_apply_cushion();
        } else if (rr_cushion_clean(&rr_md_cushion, (Uint32)psg_frames, (Uint32)s_bridge.cfg.source_rate))
            rr_md_apply_cushion();
        rr_cushion_pushed(&rr_md_cushion);
        s_prev_underruns = bst.underrun_events;
    }''')
    replace('int audio_init(int psg_sample_rate)\n{',
        '''/* The device the host asked for, or the system default when there is none or it cannot be opened. */
static SDL_AudioDeviceID rr_md_audio_open(const SDL_AudioSpec *want, SDL_AudioSpec *have) {
    SDL_AudioDeviceID id = rr_md_audio_device_name ?
        SDL_OpenAudioDevice(rr_md_audio_device_name, 0, want, have, SDL_AUDIO_ALLOW_FREQUENCY_CHANGE) : 0;
    if (rr_md_audio_device_name && !id)
        fprintf(stderr, "[host] audio device '%s' cannot be opened: %s; using the system default\\n", rr_md_audio_device_name, SDL_GetError());
    return id ? id : SDL_OpenAudioDevice(NULL, 0, want, have, SDL_AUDIO_ALLOW_FREQUENCY_CHANGE);
}
static RrAudioCushion rr_md_cushion;
static double rr_md_target_base, rr_md_high_base;
static void rr_md_apply_cushion(void) {
    SDL_LockAudioDevice(s_dev);
    s_bridge.cfg.target_ms = rr_md_target_base + rr_cushion_ms(&rr_md_cushion);
    s_bridge.cfg.em_high_ms = rr_md_high_base + rr_cushion_ms(&rr_md_cushion);
    SDL_UnlockAudioDevice(s_dev);
}
int audio_init(int psg_sample_rate)
{''')
    replace('    s_dev = SDL_OpenAudioDevice(NULL, 0, &want, &got,\n                                SDL_AUDIO_ALLOW_FREQUENCY_CHANGE);',
            '    s_dev = rr_md_audio_open(&want, &got);')
    source+='''
/* The player chose another output device: the engine's sound closed and opened again on it, from an empty ring. */
int rr_md_audio_reopen(void) {
    if(!s_dev) return 0;
    audio_close();
    return audio_init(rr_md_psg_rate)==0;
}
/* The id SDL gave the device (0 without one): the host tells which device an SDL_AUDIODEVICEREMOVED is about. */
unsigned rr_md_audio_device_id(void) { return (unsigned)s_dev; }
void rr_md_audio_delivery_timing(uint64_t *wait,uint64_t *pull,uint64_t *calls,uint64_t *stretches) {
    if(s_dev)SDL_LockAudioDevice(s_dev);
    *wait=rr_md_audio_lock_ticks;*pull=rr_md_audio_pull_ticks;*calls=rr_md_audio_pulls;
    *stretches=s_bridge.stats.stretch_events;
    if(s_dev)SDL_UnlockAudioDevice(s_dev);
}
'''
    return '#include "md_audio_mix.h"\n#include "audio_cushion.h"\n' + source


def bridge(source: str) -> str:
    def replace(old, new):
        nonlocal source
        if source.count(old) != 1:
            raise ConversionError('Mega Drive audio bridge source changed; refusing an incomplete adaptation.')
        source = source.replace(old, new)

    replace('    float *ring;            /* cap_frames*channels, interleaved float          */',
            '    float *ring;            /* cap_frames*channels, interleaved float          */\n'
            '    float *loop_history;    /* scratch allocated at init, never in callback    */\n'
            '    int16_t *loop_pcm;      /* exact packed correlation scratch               */\n'
            '    uint32_t *loop_transform, *loop_roots;\n'
            '    unsigned loop_transform_size;')
    replace('int rab_init(rab_bridge *b, const rab_config *cfg) {',
            'static void rr_md_loop_prepare(rab_bridge *b);\n\n'
            'int rab_init(rab_bridge *b, const rab_config *cfg) {')
    replace('    rab_reset(b);\n    return 0;',
            '    b->loop_history = (float *)malloc((size_t)b->cap * sizeof(float));\n'
            '    if (!b->loop_history) {\n'
            '        free(b->ring); b->ring = NULL; free(b->coeffs); b->coeffs = NULL; return 8;\n'
            '    }\n'
            '    b->loop_pcm = (int16_t *)malloc((size_t)b->cap * sizeof(int16_t));\n'
            '    rr_md_loop_prepare(b);\n    rab_reset(b);\n    return 0;')
    replace('    free(b->ring);   b->ring   = NULL;',
            '    free(b->ring);   b->ring   = NULL;\n'
            '    free(b->loop_history); b->loop_history = NULL;\n'
            '    free(b->loop_pcm); b->loop_pcm = NULL;\n'
            '    free(b->loop_transform); b->loop_transform = NULL;\n'
            '    free(b->loop_roots); b->loop_roots = NULL;')
    # Ring cursor is invariant across a producer burst; wrap it by comparison.
    replace('    int ch = b->cfg.channels;\n    for (int f = 0; f < frames; ++f) {',
            '    int ch = b->cfg.channels;\n'
            '    int64_t w=(int64_t)(b->in_count % (uint64_t)b->cap);\n'
            '    for (int f = 0; f < frames; ++f) {')
    replace('        int64_t w = (int64_t)(b->in_count % (uint64_t)b->cap);\n', '')
    replace('        b->in_count++;\n', '        b->in_count++;\n        if(++w==b->cap)w=0;\n')
    sample_begin='static void rab__sample_at(const rab_bridge *b, double pos, float *s) {'
    sample_end='\n/* Choose a loop length (source frames)'
    if source.count(sample_begin)!=1 or source.count(sample_end)!=1:
        raise ConversionError('Mega Drive audio sampler boundaries changed.')
    first,last=source.index(sample_begin),source.index(sample_end)
    source=source[:first]+'#include "md_audio_resample.inc"\n'+source[last:]
    normal_begin='            double fr = b->out_pos - (double)i;'
    normal_end='            b->out_pos += step;'
    if source.count(normal_begin)!=1 or source.count(normal_end)!=1:
        raise ConversionError('Mega Drive normal resampling boundaries changed.')
    first,last=source.index(normal_begin),source.index(normal_end)
    source=source[:first]+'            rab__sample_at(b,b->out_pos,s);\n'+source[last:]
    begin = 'static double rab__find_loop_len(const rab_bridge *b, int64_t end_i) {'
    end = '\nvoid rab_pull(rab_bridge *b, int16_t *out, int frames) {'
    if source.count(begin) != 1 or source.count(end) != 1:
        raise ConversionError('Mega Drive audio bridge search boundaries changed.')
    start, stop = source.index(begin), source.index(end)
    if stop <= start:
        raise ConversionError('Mega Drive audio bridge search boundaries are invalid.')
    return source[:start] + '#include "md_audio_loop.inc"\n' + source[stop:]
