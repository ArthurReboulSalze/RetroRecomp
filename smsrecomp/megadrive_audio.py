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
static void genesis_audio_callback(void *user, Uint8 *stream, int len)''')
    replace('    rab_pull(&s_bridge, (int16_t *)stream, frames);',
        '''    Uint64 started=rr_md_audio_timed?SDL_GetPerformanceCounter():0;
    rab_pull(&s_bridge, (int16_t *)stream, frames);
    if(started) {rr_md_audio_pull_ticks+=SDL_GetPerformanceCounter()-started;++rr_md_audio_pulls;}''')
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
    source+='''
void rr_md_audio_delivery_timing(uint64_t *wait,uint64_t *pull,uint64_t *calls,uint64_t *stretches) {
    if(s_dev)SDL_LockAudioDevice(s_dev);
    *wait=rr_md_audio_lock_ticks;*pull=rr_md_audio_pull_ticks;*calls=rr_md_audio_pulls;
    *stretches=s_bridge.stats.stretch_events;
    if(s_dev)SDL_UnlockAudioDevice(s_dev);
}
'''
    return '#include "md_audio_mix.h"\n' + source


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
