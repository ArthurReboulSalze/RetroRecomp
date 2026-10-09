"""Checked hardware adaptations of the pinned Mega Drive engine."""
from .gun16_runtime import replace


def timing_source(source, component):
    """Apply the same qualified clock to CPU, raster, status and audio copies."""
    source = '#include "retro_md_game.h"\n#include "md_timing.h"\n' + source
    changes = {
        'machine': [('#define LINES_TOTAL     262', '#define LINES_TOTAL     RR_MD_LINES')],
        'bus': [('#define MASTER_CYCLES_PER_FRAME  (262ull * 3420ull)',
                 '#define MASTER_CYCLES_PER_FRAME  ((uint64_t)RR_MD_FRAME_MASTER)')],
        'sim': [('#define GENESIS_SIM_WALL_FRAME_MASTER_CYCLES 895780u',
                 '#define GENESIS_SIM_WALL_FRAME_MASTER_CYCLES RR_MD_FRAME_MASTER')],
        'glue': [('#define NTSC_CYCLES_PER_WALL_FRAME 127856u',
                  '#define NTSC_CYCLES_PER_WALL_FRAME (RR_MD_LINES * 488u)')],
        'fm': [('constexpr uint32_t YM_CLOCK = 7670453u;',
                'constexpr uint32_t YM_CLOCK = RR_MD_MASTER_HZ / 7u;')],
        'psg': [('return (uint32_t)(GENESIS_MASTER_CLOCK_NTSC / PSG_SAMPLE_DIVISOR_MASTER);',
                 'return (uint32_t)(RR_MD_MASTER_HZ / PSG_SAMPLE_DIVISOR_MASTER);')],
    }
    for old, new in changes[component]:
        source = replace(source, old, new)
    return source


def timing_vdp(source):
    source = '#include "retro_md_game.h"\n#include "md_timing.h"\n' + source
    # Both read and peek expose PAL; only the read retains status side effects.
    for text in ('uint16_t s = 0x3400 | 0x0200;', 'uint16_t s = 0x3400;'):
        source = replace(source, text, text + ' s |= RR_MD_PAL;')
    return replace(source, '((v->scanline & 0xFF) << 8)',
                   '(rr_md_vcounter(v->scanline, (v->reg[1] & 8) != 0) << 8)')


def ym_bus(source):
    source = '#include "md_ym_timers.h"\n' + source
    start = source.index('static void ym_timer_update(')
    end = source.index('\nvoid gbus_init(', start)
    source = replace(source, source[start:end], '''static RrMdYmTimers rr_ym_timers;
void rr16_md_ym_reset(void) { memset(&rr_ym_timers, 0, sizeof rr_ym_timers); }
const RrMdYmTimers *rr16_md_ym_state(void) { return &rr_ym_timers; }
void rr16_md_ym_restore(const RrMdYmTimers *state) { rr_ym_timers = *state; }
static void ym_timer_update(GenesisBus *b, uint64_t now) {
    rr_md_ym_advance(&rr_ym_timers, now);
    b->ym_status = rr_ym_timers.status;
}
static void ym_write_side_effect(GenesisBus *b, uint8_t port, uint8_t val, uint64_t now) {
    ym_timer_update(b, now);
    unsigned bank = (port >> 1) & 1u;
    if (!(port & 1u)) { b->ym_addr[bank] = val; return; }
    if (bank) return;
    rr_md_ym_write(&rr_ym_timers, b->ym_addr[0], val, now);
    b->ym_status = rr_ym_timers.status;
    b->ym_mode = rr_ym_timers.mode;
}
''')
    start = source.index('/* YM2612 timer B ----')
    end = source.index('#define MASTER_CYCLES_PER_FRAME', start)
    source = source[:start] + '''/* CPU-visible timers A/B advance in master clocks. BUSY remains clear.
 * The independent queue-driven synth still renders FM/PSG at frame end. */
''' + source[end:]
    return source
