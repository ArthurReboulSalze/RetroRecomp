"""Timed transfers and level-sensitive IRQs in checked private engine copies."""
from .gun16_runtime import replace


def header(source):
    source = '#include "md_vdp_dma.h"\n' + source
    source = replace(source, '    RrMdVdpFifo rr_fifo;\n} GVDP;',
                     '    RrMdVdpFifo rr_fifo;\n    RrMdVdpDma rr_dma;\n    RrMdVdpIrq rr_irq;\n} GVDP;')
    return source + ('\nint gvdp_dma_blocks_cpu(const GVDP *v);\n'
                     'unsigned gvdp_dma_wait_until(GVDP *v,unsigned phase);\n'
                     'int gvdp_dma_migrate(GVDP *v);\nint gvdp_timing_valid(const GVDP *v);\n'
                     'unsigned gvdp_irq_level(const GVDP *v);\nvoid gvdp_irq_ack(GVDP *v,unsigned level);\n')


def vdp(source):
    source = replace(source, '    memset(&v->rr_fifo,0,sizeof v->rr_fifo);',
        '    memset(&v->rr_fifo,0,sizeof v->rr_fifo);\n'
        '    memset(&v->rr_dma,0,sizeof v->rr_dma);\n    memset(&v->rr_irq,0,sizeof v->rr_irq);')
    # The FIFO helpers are compiled first; the unified advance lives in DMA.
    source = replace(source, '#include "md_vdp_fifo.inc"',
        '#define RR_MD_TIMED_DMA 1\n#include "md_vdp_fifo.inc"')
    start = source.index('static uint32_t dma_length(')
    end = source.index('/* ---- 68K port interface', start)
    source = source[:start] + '''#include "md_vdp_dma.inc"
uint32_t gvdp_rb_pending_stall(void) { return s_pending_68k_stall; }
void gvdp_rb_set_pending_stall(uint32_t v) { s_pending_68k_stall=v; }
uint32_t gvdp_consume_68k_stall(GVDP *v) {
    (void)v;uint32_t s=s_pending_68k_stall;s_pending_68k_stall=0;return s;
}

''' + source[end:]
    source = replace(source, 'rr_fifo_wait(v,0); dma_run_vram_fill_data(v,value); return;',
                             'dma_run_vram_fill_data(v,value); return;')
    source = replace(source, '    v->vint_pending = 0;\n    v->sprite_overflow',
                             '    v->sprite_overflow')
    source = replace(source, 'Reading the control port resets the write FSM and clears the V-int flag.',
                             'Reading status resets the write FSM; IRQ flags clear only on CPU acknowledge.')
    start = source.index('unsigned gvdp_begin_scanline(')
    end = source.index('/* ---- Rendering', start)
    source = source[:start] + '''unsigned gvdp_begin_scanline(GVDP *v,int line) {
    if(v->rr_fifo.clock>=RR_MD_MASTER_PER_LINE)v->rr_fifo.clock-=RR_MD_MASTER_PER_LINE;
    v->scanline=(uint16_t)line;
    int height=gvdp_screen_height(v);
    if(line<=height) {
        if(!v->hint_counter) { v->hint_counter=REG_HINT_RATE(v);v->rr_irq.hint_pending=1; }
        else --v->hint_counter;
    } else v->hint_counter=REG_HINT_RATE(v);
    if(line==height) { v->in_vblank=1;v->rr_irq.vint_stage=1; }
    if(!line)v->in_vblank=0;
    return 0; /* Latched events are polled at instruction boundaries, not delivered here. */
}

''' + source[end:]
    return source


def snapshot(source):
    source = replace(source, 'sizeof(GVDP) == 65872', 'sizeof(GVDP) == 65912')
    return replace(source, 'sizeof(GenesisMachine) == 139776', 'sizeof(GenesisMachine) == 139816')


def machine(source):
    # Qualified old layouts: ABI-3 has FIFO, ABI-2 does not. Insert zeroed
    # DMA/IRQ state at its old boundary and preserve all later machine fields.
    source = replace(source, '    if(len==need-sizeof(RrMdVdpFifo)) {', '''    size_t extra=sizeof(RrMdVdpDma)+sizeof(RrMdVdpIrq);
    if(len==need-extra || len==need-extra-sizeof(RrMdVdpFifo)) {''')
    source = replace(source, '        size_t prefix=offsetof(GVDP,rr_fifo);',
        '        size_t added=need-len;\n'
        '        size_t prefix=added==extra?offsetof(GVDP,rr_dma):offsetof(GVDP,rr_fifo);')
    source = replace(source, 'expanded+prefix+sizeof(RrMdVdpFifo)', 'expanded+prefix+added')
    source = replace(source, '!gvdp_fifo_valid(&((const GenesisMachine *)src)->vdp)',
                     '!gvdp_timing_valid(&((const GenesisMachine *)src)->vdp)')
    # Keep source snapshots immutable. ABI-4's directly fetched partial word
    # migrates to a FIFO tail; the pointer-free layout itself has not grown.
    source = replace(source, '    const uint8_t *i = (const uint8_t *)src;', '''    if(!expanded) {
        expanded=malloc(need);if(!expanded)return 0;
        memcpy(expanded,src,need);src=expanded;
    }
    if(!gvdp_dma_migrate(&((GenesisMachine *)expanded)->vdp)) { free(expanded);return 0; }
    const uint8_t *i = (const uint8_t *)src;''')
    source = replace(source, 'return size==n || size==n-sizeof(RrMdVdpFifo);',
        'size_t extra=sizeof(RrMdVdpDma)+sizeof(RrMdVdpIrq);\n'
        '    return size==n || size==n-extra || size==n-extra-sizeof(RrMdVdpFifo);')
    source = replace(source, '        unsigned irq = gvdp_begin_scanline(&m->vdp, line);',
                             '        gvdp_begin_scanline(&m->vdp, line);')
    source = replace(source, '    GenesisMachine *m = &g_machine;\n    int active_h',
        '    GenesisMachine *m = &g_machine;\n'
        '    const uint32_t rr_frame_cpu_base=g_audio_cycle_counter;\n    int active_h')
    source = replace(source, '        rr_vdp_cpu_origin = g_audio_cycle_counter;',
        '        rr_vdp_cpu_origin=rr_frame_cpu_base+(unsigned)line*MASTER_PER_LINE/7u;')
    source = replace(source, '            uint32_t before = g_audio_cycle_counter;',
        '            uint32_t before=rr_vdp_cpu_origin;')
    source = replace(source, 'unsigned cpu_target = (part + 1) * M68K_PER_LINE / 16;',
        'unsigned rr_cpu_fraction=(unsigned)line*MASTER_PER_LINE%7u;\n'
        '                unsigned cpu_target=((part+1)*MASTER_PER_LINE/16+rr_cpu_fraction)/7u;')
    source = replace(source, '                if (elapsed < cpu_target) glue_run_game_chunk(cpu_target - elapsed);', '''                unsigned begin_master=part*MASTER_PER_LINE/16;
                unsigned end_master=(part+1)*MASTER_PER_LINE/16;
                unsigned begin_cpu=(begin_master+rr_cpu_fraction)/7u;
                if(elapsed<begin_cpu) {
                    /* Waiting/parked CPU time still advances the wall clock.
                     * Otherwise a late IRQ/DMA runs several idle slices at once. */
                    glue_charge_68k_stall(begin_cpu-elapsed);elapsed=begin_cpu;
                }
                gvdp_fifo_advance(&m->vdp,begin_master);
                while(elapsed<cpu_target) {
                    if(gvdp_dma_blocks_cpu(&m->vdp)) {
                        unsigned release=gvdp_dma_wait_until(&m->vdp,end_master);
                        unsigned wait=gvdp_dma_blocks_cpu(&m->vdp)?cpu_target:
                            (release+rr_cpu_fraction+6u)/7u;
                        if(wait>cpu_target)wait=cpu_target;
                        if(wait>elapsed)glue_charge_68k_stall(wait-elapsed);
                        elapsed=g_audio_cycle_counter-before;
                        if(gvdp_dma_blocks_cpu(&m->vdp) || elapsed>=cpu_target)break;
                        glue_own_vint_service_latched(&m->vdp);
                        elapsed=g_audio_cycle_counter-before;
                        if(elapsed>=cpu_target)break;
                    }
                    unsigned prior=elapsed;
                    glue_run_game_chunk(cpu_target-elapsed);
                    elapsed=g_audio_cycle_counter-before;
                    if(elapsed==prior && !gvdp_dma_blocks_cpu(&m->vdp))break;
                }
                gvdp_fifo_advance(&m->vdp,end_master);''')
    source = replace(source,
        '    return rr_vdp_z80_active ? s_z80_off :\n'
        '        (g_audio_cycle_counter >= rr_vdp_cpu_origin ? (g_audio_cycle_counter - rr_vdp_cpu_origin) * 7u : 0u);',
        '''    if(rr_vdp_z80_active)return s_z80_off;
    if(g_audio_cycle_counter<rr_vdp_cpu_origin)return 0;
    unsigned phase=(g_audio_cycle_counter-rr_vdp_cpu_origin)*7u;
    unsigned fraction=(unsigned)g_machine.vdp.scanline*MASTER_PER_LINE%7u;
    return phase>=fraction?phase-fraction:0;''')
    source = replace(source, '        m->master_cycle += MASTER_PER_LINE;',
        '        unsigned rr_line_end=rr_frame_cpu_base+(unsigned)(line+1)*MASTER_PER_LINE/7u;\n'
        '        if(g_audio_cycle_counter<rr_line_end)glue_charge_68k_stall(rr_line_end-g_audio_cycle_counter);\n'
        '        m->master_cycle += MASTER_PER_LINE;')
    start = source.index('        /* Deliver interrupts to the 68K')
    end = source.index('        gvdp_fifo_advance', start)
    source = source[:start] + source[end:]
    return source + '''
void machine_vdp_z80_irq(int asserted) { g_machine.z80.int_pending=!!asserted; }
'''


def glue(source):
    source = replace(source, 'static void check_cycle_budget(void);',
        'static void rr_md_poll_vdp_irq(void);\nstatic void check_cycle_budget(void);')
    # Guards from the normal portable/native instruction wrappers run first.
    source = replace(source, '    if (RR_MD_STEP_AOT && rr_step_running) return;\n'
                            '    if (rr16_md_instruction_busy()) return;',
        '    if (RR_MD_STEP_AOT && rr_step_running) return;\n'
        '    if (rr16_md_instruction_busy()) return;\n'
        '    gvdp_fifo_advance(&g_machine.vdp,machine_vdp_phase());\n'
        '    if(!gvdp_dma_blocks_cpu(&g_machine.vdp))rr_md_poll_vdp_irq();')
    source = replace(source, '        if (s_cycle_budget <= 0) {',
        '        if (s_cycle_budget <= 0 || gvdp_dma_blocks_cpu(&g_machine.vdp)) {')
    start = source.index('void glue_own_interrupt(int level, GVDP *vdp)')
    end = source.index('/* Non-clearing read', start)
    source = source[:start] + '''static void rr_md_poll_vdp_irq(void) {
    if(!s_game_running || rr16_md_instruction_busy())return;
    /* Step execution accepts IRQs on its live fiber, where bus waits resume.
     * Host polls leave guest pending flags intact, including for F8/F9. */
    if(RR_MD_STEP_AOT && !rr_md_prefetch_active())return;
    GVDP *v=&g_machine.vdp;
    if(s_own_vint_latched) { v->vint_pending=1;s_own_vint_latched=0; }
    unsigned level=gvdp_irq_level(v);
    if(level<2 && rr16_md_gun_pending())level=2;
    if(!level || level<=((g_cpu.SR>>8)&7) || gvdp_dma_blocks_cpu(v))return;
    if(!RR_MD_STEP_AOT) {
        gvdp_irq_ack(v,level);
        if(level==2)rr16_md_gun_irq_begin();
    }
    s_own_vint_latched=0;
    rr_md_service_irq((int)level,0x60u+4u*level,v);
}
void glue_own_interrupt(int level,GVDP *vdp) {
    (void)level;(void)vdp;rr_md_poll_vdp_irq();
}
int glue_own_vint_service_latched(GVDP *vdp) {
    (void)vdp;rr_md_poll_vdp_irq();return 0;
}

''' + source[end:]
    return '#include "retro_md_game.h"\n#include "genesis_machine.h"\nextern unsigned machine_vdp_phase(void);\n' + source
