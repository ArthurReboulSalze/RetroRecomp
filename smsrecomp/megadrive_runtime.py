"""Checked hardware adaptations of the pinned Mega Drive engine."""
from .gun16_runtime import replace


def ym_bus(source):
    source = '#include "md_ym_timers.h"\n' + source
    start = source.index('static void ym_timer_update(')
    end = source.index('\nvoid gbus_init(', start)
    source = replace(source, source[start:end], '''static RrMdYmTimers rr_ym_timers;
void rr16_md_ym_reset(void) { memset(&rr_ym_timers, 0, sizeof rr_ym_timers); }
const RrMdYmTimers *rr16_md_ym_state(void) { return &rr_ym_timers; }
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
