"""Checked hardware adaptations of the pinned Mega Drive engine."""
from .gun16_runtime import replace
from .core import ConversionError


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
    # Full-plane scrolling is fetched before this line's H interrupt changes
    # VSRAM. The CPU-visible words remain live for subsequent bus accesses.
    # Two-cell scrolling retains its column fetch path. No serialized state
    # or cartridge-specific display adjustment is introduced.
    source = replace(source, 'int gvdp_render_scanline(GVDP *v, int line, uint8_t *out)',
        'int gvdp_render_scanline_latched(GVDP *v, int line, uint8_t *out,\n'
        '                                 uint16_t line_vs_a, uint16_t line_vs_b)')
    source = replace(source, 'int full_vs_a = v->vsram[0] & vs_mask;',
                     'int full_vs_a = line_vs_a & vs_mask;')
    source = replace(source, 'int full_vs_b = v->vsram[1] & vs_mask;',
                     'int full_vs_b = line_vs_b & vs_mask;')
    source += '''
int gvdp_render_scanline(GVDP *v, int line, uint8_t *out) {
    return gvdp_render_scanline_latched(v,line,out,v->vsram[0],v->vsram[1]);
}
'''
    # Both read and peek expose PAL; only the read retains status side effects.
    for text in ('uint16_t s = 0x3400 | 0x0200;', 'uint16_t s = 0x3400;'):
        source = replace(source, text, text + ' s |= RR_MD_PAL;')
    source = replace(source, '((v->scanline & 0xFF) << 8)',
                   '(rr_md_vcounter(v->scanline, (v->reg[1] & 8) != 0) << 8)')
    source = 'extern unsigned machine_vdp_phase(void);\n' + source
    if source.count('if (v->in_hblank)        s |= 0x0004;') != 2:
        raise ConversionError('Pinned VDP status hooks changed; refusing an ambiguous clock adaptation.')
    source = source.replace('if (v->in_hblank)        s |= 0x0004;',
        'if (rr_md_hblank(machine_vdp_phase(), MODE4_H40(v))) s |= 0x0004;')
    start = source.index('    /* Advance a phantom H-blank')
    end = source.index('    return s;', start)
    source = source[:start] + source[end:]
    source = replace(source, '    v->vint_pending = 0;\n    return s;',
        '    v->vint_pending = 0;\n    v->sprite_overflow = v->sprite_collision = 0;\n    return s;')
    return replace(source, '(v->in_hblank ? 0x00 : 0x80)',
                   'rr_md_hcounter(machine_vdp_phase(), MODE4_H40(v))')


def raster_machine(source):
    """Expose current CPU/Z80 slice phase; derived state is rebuilt each line.

    Instruction reads are timestamped at instruction start. This removes
    read-driven HBlank without claiming bus-cycle, FIFO or field accuracy.
    """
    source = replace(source, 'static uint32_t s_z80_off     = 0;',
        '''extern int gvdp_render_scanline_latched(GVDP *,int,uint8_t *,uint16_t,uint16_t);
static uint32_t rr_vdp_cpu_origin;
static int rr_vdp_z80_active;
static uint32_t rr_vdp_z80_wait;
extern uint32_t g_audio_cycle_counter;
extern void glue_charge_68k_stall(uint32_t cycles);
static uint32_t s_z80_off     = 0;''')
    source = replace(source, '        unsigned irq = gvdp_begin_scanline(&m->vdp, line);',
        '        const uint16_t rr_line_vs_a=m->vdp.vsram[0], rr_line_vs_b=m->vdp.vsram[1];\n'
        '        unsigned irq = gvdp_begin_scanline(&m->vdp, line);')
    source = replace(source, 'int n = gvdp_render_scanline(&m->vdp, row, idxbuf);',
        'int n = gvdp_render_scanline_latched(&m->vdp,row,idxbuf,rr_line_vs_a,rr_line_vs_b);')
    source = replace(source, 'static void step_z80(GenesisMachine *m, uint32_t target)\n{',
        'static void step_z80(GenesisMachine *m, uint32_t target)\n{\n    rr_vdp_z80_active = 0;')
    source = replace(source, '    int pend_before =', '    rr_vdp_z80_active = 1;\n    int pend_before =')
    source = replace(source, '    while (done < target) {',
        '    while (done < target) {\n        rr_vdp_z80_wait = 0;')
    source = replace(source, '    }\n    m->z80_cycle_debt = done - target;',
        '        done += rr_vdp_z80_wait;\n    }\n    m->z80_cycle_debt = done - target;')
    source = replace(source, '    m->z80_cycle_debt = done - target;',
        '    m->z80_cycle_debt = done - target;\n    rr_vdp_z80_active = 0;')
    source = replace(source, '        s_line_base = (uint32_t)line * MASTER_PER_LINE;',
        '        rr_vdp_cpu_origin = g_audio_cycle_counter;\n'
        '        rr_vdp_z80_active = 0;\n'
        '        s_line_base = (uint32_t)line * MASTER_PER_LINE;')
    return source + '''
unsigned machine_vdp_phase(void) {
    /* The frame-end driver resets the CPU counter before host inspection. */
    return rr_vdp_z80_active ? s_z80_off :
        (g_audio_cycle_counter >= rr_vdp_cpu_origin ? (g_audio_cycle_counter - rr_vdp_cpu_origin) * 7u : 0u);
}
void machine_vdp_wait(unsigned cycles_68k) {
    if(rr_vdp_z80_active) {
        /* A Z80 VDP access must not charge the unrelated main CPU. */
        unsigned cycles=(cycles_68k*7u+14u)/15u;
        rr_vdp_z80_wait+=cycles;
        s_z80_off+=cycles*15u;
    } else {
        glue_charge_68k_stall(cycles_68k);
    }
}
'''


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
