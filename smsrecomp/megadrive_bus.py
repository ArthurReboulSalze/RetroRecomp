"""Resumable CPU accesses to the DMA-owned main bus, in private copies."""
from .gun16_runtime import replace


def glue(source):
    # Machine and glue are separately compiled; fast32_t is not necessarily
    # uint32_t on the host. Their public rendezvous must share one exact type.
    source=replace(source,'void glue_run_game_chunk(cc_u32f cycles)',
                   'void glue_run_game_chunk(uint32_t cycles)')
    helper = '''static unsigned rr_cpu_bus_cycles;
uint64_t rr_md_bus_budget_misses;
uint32_t rr_md_bus_budget_pc;
static int rr_cpu_bus_locked;
static uint32_t rr_cpu_bus_pc;
void rr_md_cpu_control_yield(void) {
    /* A completed local-bus control write is a rendezvous with the sound
     * CPU, even when the 68000 is inside its last instruction of the line. */
    if(RR_MD_STEP_AOT && rr_step_running && s_interleave_active &&
       !s_in_vblank_service && fiber_current()==s_game_fiber) {
        s_yield_site=GLUE_YIELD_BUDGET;fiber_switch(s_main_fiber);
    }
}
static void rr_md_cpu_bus_wait(void) {
    if(!RR_MD_STEP_AOT || !rr_step_running)return;
    while(gvdp_dma_blocks_cpu(&g_machine.vdp) ||
          (!rr_cpu_bus_locked && machine_main_bus_split() && s_interleave_active && !s_in_vblank_service &&
           (uint32_t)(g_audio_cycle_counter-s_budget_cyc_seen)>=(uint32_t)s_cycle_budget)) {
        /* Preserve this expression on the live fiber. The host queues states
         * until both CPUs retire; disk never contains a C continuation. */
        s_yield_site=GLUE_YIELD_BUDGET;
        fiber_switch(s_main_fiber);
    }
    /* A word/byte transaction occupies four nominal 68000 clocks. Device
     * waits are charged separately. Commit occurs at this cycle's end; the
     * following transaction may yield without replaying this one. */
    g_audio_cycle_counter+=4;g_cycle_accumulator+=4;rr_cpu_bus_cycles+=4;
}
void rr_md_cpu_fetch_cycles(unsigned words,int locked) {
    rr_cpu_bus_cycles=0;rr_cpu_bus_locked=0;
    rr_cpu_bus_pc=g_cpu.PC;
    if(!RR_MD_STEP_AOT || !rr_step_running)return;
    /* Decoding/ROM guards are peeks. Account the omitted instruction words
     * identically in native/reference execution, without a second decode. */
    for(unsigned i=0;i<words;++i)rr_md_cpu_bus_wait();
    rr_cpu_bus_locked=locked;
}
int rr_md_prefetch_active(void) { return RR_MD_STEP_AOT && rr_step_running; }
unsigned rr_md_cpu_stop_cycles(void) {
    /* STOP releases the bus. Advance only to the host's next rendezvous;
     * four-clock pseudo-instructions would delay an unrelated Z80 request.
     * Poll/accept IRQs in the usual instruction-boundary path on return. */
    if(RR_MD_STEP_AOT && s_interleave_active && !s_in_vblank_service) {
        unsigned elapsed=g_audio_cycle_counter-s_budget_cyc_seen;
        return s_cycle_budget>0 && elapsed<(unsigned)s_cycle_budget
            ?(unsigned)s_cycle_budget-elapsed:0;
    }
    return 4; /* Standalone diagnostic interpreter has no host deadline. */
}
void rr_md_cpu_bus_lock(int locked) { rr_cpu_bus_locked=locked; }
void rr_md_cpu_idle(unsigned clocks) {
    if(!rr_md_prefetch_active())return;
    while(clocks) {
        unsigned part=clocks;
        if(!rr_cpu_bus_locked && machine_main_bus_split() && s_interleave_active && !s_in_vblank_service) {
            unsigned elapsed=g_audio_cycle_counter-s_budget_cyc_seen;
            if(elapsed>=(unsigned)s_cycle_budget) {
                /* Internal calculation does not reserve the bus. Retain its
                 * remaining work on the live fiber while the other CPU runs.
                 * Wall clocks charged by the arbiter overlap that work; only
                 * the excess is a stall, never pay the same clocks twice. */
                uint32_t before=g_audio_cycle_counter;
                s_yield_site=GLUE_YIELD_BUDGET;
                fiber_switch(s_main_fiber);
                unsigned overlap=g_audio_cycle_counter-before;
                if(overlap>clocks)overlap=clocks;
                clocks-=overlap;rr_cpu_bus_cycles+=overlap;g_cycle_accumulator+=overlap;
                continue;
            }
            unsigned available=(unsigned)s_cycle_budget-elapsed;
            if(part>available)part=available;
        }
        g_audio_cycle_counter+=part;g_cycle_accumulator+=part;rr_cpu_bus_cycles+=part;
        clocks-=part;
    }
}
uint16_t rr_md_read_instruction_word(uint32_t pc) { return m68k_read16(pc); }
void rr_md_cpu_iack(unsigned level) {
    rr_md_cpu_bus_wait();
    /* The source may change during this transaction, including a resumed
     * bus wait. Retire VDP events through the actual acknowledge boundary
     * before clearing its latch; the CPU vector remains the selected level. */
    gvdp_fifo_advance(&g_machine.vdp,machine_vdp_phase());
    gvdp_irq_ack(&g_machine.vdp,level);
    if(level==2)rr16_md_gun_irq_begin();
}
unsigned rr_md_cpu_retire_cycles(unsigned cycles) {
    unsigned paid=rr_cpu_bus_cycles;rr_cpu_bus_cycles=0;rr_cpu_bus_locked=0;
    if(paid>cycles) {
        ++rr_md_bus_budget_misses;rr_md_bus_budget_pc=rr_cpu_bus_pc;
    }
    return cycles>paid?cycles-paid:0;
}

'''
    source = replace(source, 'uint16_t m68k_read16(uint32_t byte_addr)\n{',
                     helper + 'uint16_t m68k_read16(uint32_t byte_addr)\n{')
    for signature in ('uint16_t m68k_read16(uint32_t byte_addr)',
                      'uint8_t m68k_read8(uint32_t byte_addr)',
                      'uint32_t m68k_read32(uint32_t byte_addr)',
                      'void m68k_write16(uint32_t byte_addr, uint16_t val)',
                      'void m68k_write8(uint32_t byte_addr, uint8_t val)',
                      'void m68k_write32(uint32_t byte_addr, uint32_t val)'):
        old = signature + '\n{\n    byte_addr &= 0xFFFFFFu;'
        source = replace(source, old, old + '\n    rr_md_cpu_bus_wait();')
    source = '#include "md_prefetch.h"\n#include "md_bus_scheduler.h"\n' + source
    for signature in ('void m68k_write16(uint32_t byte_addr, uint16_t val)',
                      'void m68k_write8(uint32_t byte_addr, uint8_t val)',
                      'void m68k_write32(uint32_t byte_addr, uint32_t val)'):
        anchor=signature+'\n{\n    byte_addr &= 0xFFFFFFu;'
        source=replace(source,anchor,anchor+'\n    rr_md_prefetch_before_write();')
    source = replace(source, '    uint16_t lo = gbus_read16(&g_machine.bus, byte_addr + 2);',
        '    rr_md_cpu_bus_wait();\n    uint16_t lo = gbus_read16(&g_machine.bus, byte_addr + 2);')
    source = replace(source, '    gbus_write16(&g_machine.bus, byte_addr + 2, (uint16_t)(val & 0xFFFF));',
        '    rr_md_cpu_bus_wait();\n    gbus_write16(&g_machine.bus, byte_addr + 2, (uint16_t)(val & 0xFFFF));')
    source = replace(source, '''        g_mem_write_trace_fn(byte_addr + 2u, (uint8_t)(val >> 8),  g_audio_cycle_counter);
        g_mem_write_trace_fn(byte_addr + 3u, (uint8_t)val,         g_audio_cycle_counter);
    }
    gbus_write16(&g_machine.bus, byte_addr,     (uint16_t)(val >> 16));
    rr_md_cpu_bus_wait();''', '''    }
    gbus_write16(&g_machine.bus, byte_addr,     (uint16_t)(val >> 16));
    rr_md_cpu_bus_wait();
    if(g_mem_write_trace_fn) {
        g_mem_write_trace_fn(byte_addr + 2u, (uint8_t)(val >> 8), g_audio_cycle_counter);
        g_mem_write_trace_fn(byte_addr + 3u, (uint8_t)val, g_audio_cycle_counter);
    }''')
    # The two halves are real transactions. The command latch survives a wait.
    source = replace(source, '''    /* Bump once for the whole 32-bit op — both halves at same cycle.
     * Critical for VDP control port: the VDP latches a 32-bit command
     * from two consecutive 16-bit writes. If VDP sync runs between
     * them, the half-written command corrupts VDP state. */''',
        '    /* Nominal bus time is charged per word; retirement pays the remainder. */')
    source = replace(source, '    audio_detour_write(byte_addr + 2,   (uint8_t)val);', '')
    source = replace(source, '    rr_md_cpu_bus_wait();\n    if(g_mem_write_trace_fn) {',
        '    rr_md_cpu_bus_wait();\n    audio_detour_write(byte_addr + 2, (uint8_t)val);\n'
        '    if(g_mem_write_trace_fn) {')
    # A live instruction can cross the diagnostic clock's 32-bit wrap.
    # Step-AOT keeps a bounded modular delta; legacy frame-reset semantics stay
    # on their existing path. Otherwise retirement runs past the host budget.
    source = replace(source, '        if (now > s_budget_cyc_seen)\n'
        '            s_cycle_budget -= (int32_t)(now - s_budget_cyc_seen);',
        '        if (RR_MD_STEP_AOT || now > s_budget_cyc_seen)\n'
        '            s_cycle_budget -= (int32_t)(now - s_budget_cyc_seen);')
    return source


def bus(source):
    source = '#include "md_bus_scheduler.h"\n' + source
    for prefix in ('uint16_t ack = (uint16_t)', 'return (uint16_t)'):
        source = replace(source, prefix+'(b->z80_busreq ? 0x0000 : 0x0100)',
            prefix+'(machine_z80_bus_acknowledged() ? 0x0000 : 0x0100)')
    # Word and byte register writes converge here. Only an actual combined
    # BUSREQ/reset release moves the paused clock; redundant writes do not.
    source = replace(source, 'if (a == 0xA11100u) { b->z80_busreq = (v & 0x0100) ? 1 : 0;',
        '''if (a == 0xA11100u) { int held=b->z80_busreq || !b->z80_reset_off;
        b->z80_busreq = (v & 0x0100) ? 1 : 0;
        if(held && !b->z80_busreq && b->z80_reset_off)machine_z80_bus_released();
        machine_z80_bus_control();''')
    source = replace(source, '        snd_trace_busreq("RESET_OFF", b->z80_reset_off);',
        '''        if(!o && b->z80_reset_off && !b->z80_busreq)machine_z80_bus_released();
        machine_z80_bus_control();
        snd_trace_busreq("RESET_OFF", b->z80_reset_off);''')
    source = replace(source, '    /* $8000-$FFFF: banked window into the 68K bus. */',
        '    machine_z80_bus_wait();\n    /* $8000-$FFFF: banked window into the 68K bus. */')
    return replace(source, '    if (addr >= 0x8000u) {',
        '    if (addr >= 0x8000u) {\n        machine_z80_bus_wait();')


def machine(source):
    source = '#include "md_bus_scheduler.h"\n' + source
    source = replace(source, 'static void machine_wire_pointers(void)\n{',
        'static void machine_wire_pointers(void)\n{\n    rr_md_z80_bus_reset();')
    source = replace(source, 'static void step_z80(GenesisMachine *m, uint32_t target)',
        '#include "md_z80_bus.inc"\n\nstatic void step_z80(GenesisMachine *m, uint32_t target)')
    source = replace(source, '        rr_md_z80_capture_driver();',
        '        rr_md_z80_bus_reset();\n        rr_md_z80_capture_driver();')
    source = replace(source, '    m->z80.cyc = 0;',
        '    if(!rr_z80_busy)m->z80.cyc = 0;')
    start = source.index('    while (done < target) {')
    end = source.index('    m->z80_cycle_debt = done - target;', start)
    old = source[start:end]
    source = replace(source, old, '#ifdef GENESIS_Z80_RECOMP\n' + old + '''#else
    if(done<target) {
        rr_z80_start();
        int64_t base=rr_gun_slice_base;
        if(!rr_z80_busy)rr_z80_time=base+done*MASTER_PER_Z80;
        rr_z80_limit=base+target*MASTER_PER_Z80;
        s_z80_off=rr_gun_slice_base+done*MASTER_PER_Z80;
        if(!(rr_z80_blocked && gvdp_dma_blocks_cpu(&m->vdp)))
            fiber_switch(rr_z80_fiber);
        done=rr_z80_blocked?target:(uint32_t)((rr_z80_time-base+14)/MASTER_PER_Z80);
    }
#endif
''')
    # The adapted DMA scheduler is now driven by external Z80 requests. Keep
    # legacy precompiled execution separate, and reject unexpected source drift.
    start = source.index('                unsigned rr_cpu_fraction=')
    end_marker = '                step_z80(m, (part + 1) * Z80_PER_LINE / 16 - part * Z80_PER_LINE / 16);'
    end = source.index(end_marker, start) + len(end_marker)
    source = replace(source, source[start:end], '''                unsigned fraction=(unsigned)line*MASTER_PER_LINE%7u;
                rr_bus_slice(m,part*MASTER_PER_LINE/16,(part+1)*MASTER_PER_LINE/16,before,fraction);''')
    source = replace(source, '        rr_gun_slice_base = 0;\n        if (RR_MD_STEP_AOT || RR16_GUN)',
        '''        rr_gun_slice_base = 0;
        if(!rr_z80_busy) {
            rr_z80_time=(int64_t)m->z80_cycle_debt*MASTER_PER_Z80;
            m->z80.cyc=0;
        }
        if (RR_MD_STEP_AOT || RR16_GUN)''')
    source = replace(source, '    const uint32_t rr_frame_cpu_base=g_audio_cycle_counter;',
        '    const uint32_t rr_frame_cpu_base=g_audio_cycle_counter;\n'
        '    const unsigned rr_frame_fraction=(unsigned)(m->master_cycle%7u);')
    source = replace(source, 'rr_frame_cpu_base+(unsigned)line*MASTER_PER_LINE/7u;',
        'rr_frame_cpu_base+((unsigned)line*MASTER_PER_LINE+rr_frame_fraction)/7u;')
    source = replace(source, 'unsigned fraction=(unsigned)line*MASTER_PER_LINE%7u;',
        'unsigned fraction=(unsigned)(m->master_cycle%7u);')
    source = replace(source, 'rr_frame_cpu_base+(unsigned)(line+1)*MASTER_PER_LINE/7u;',
        'rr_frame_cpu_base+((unsigned)(line+1)*MASTER_PER_LINE+rr_frame_fraction)/7u;')
    source = replace(source, 'unsigned fraction=(unsigned)g_machine.vdp.scanline*MASTER_PER_LINE%7u;',
        'unsigned fraction=(unsigned)(g_machine.master_cycle%7u);')
    source = replace(source, '        m->master_cycle += MASTER_PER_LINE;',
        '        rr_z80_time-=MASTER_PER_LINE;rr_z80_limit-=MASTER_PER_LINE;rr_z80_grant-=MASTER_PER_LINE;\n'
        '        rr_local_request_time-=MASTER_PER_LINE;rr_local_ack_time-=MASTER_PER_LINE;\n'
        '        m->master_cycle += MASTER_PER_LINE;')
    # Keep divider phase and instruction overrun independent of the legacy
    # 32-bit diagnostic clock. Pack them in the old tail's zeroed alignment
    # word: the guest section retains its size and explicit old migrations.
    source = replace(source, 'typedef struct MachineRbTail {',
        'static unsigned rr_main_fraction,rr_main_debt;\n'
        'typedef struct MachineRbTail {')
    source = replace(source, '    uint32_t unlimited_sprites; /* game-set sprite-limit bypass (status flags) */',
        '    uint32_t unlimited_sprites; /* game-set sprite-limit bypass (status flags) */\n'
        '    uint32_t main_clock; /* replaces old zeroed alignment padding */')
    source = replace(source, '} MachineRbTail;',
        '} MachineRbTail;\n_Static_assert(sizeof(MachineRbTail)==24,"machine tail layout changed");')
    source = replace(source, '    t.pending_stall = gvdp_rb_pending_stall();',
        '    t.main_clock=0x80000000u | (rr_main_debt<<3) | rr_main_fraction;\n'
        '    t.pending_stall = gvdp_rb_pending_stall();')
    source = replace(source, '    const uint8_t *i = (const uint8_t *)src;',
        '''    MachineRbTail clock_tail;
    memcpy(&clock_tail,(const uint8_t *)src+sizeof(GenesisMachine),sizeof clock_tail);
    uint32_t clock=clock_tail.main_clock;
    if((clock && !(clock&0x80000000u)) || (clock&7u)==7u ||
       ((clock&0x7fffffffu)>>3)>65536u) { free(expanded);return 0; }
    const uint8_t *i = (const uint8_t *)src;''')
    source = replace(source, '    g_snd_line = t.snd_line;',
        '    g_snd_line = t.snd_line;\n'
        '    rr_main_fraction=(t.main_clock&0x80000000u)?t.main_clock&7u:g_machine.master_cycle%7u;\n'
        '    rr_main_debt=(t.main_clock&0x7fffffffu)>>3;')
    source = replace(source, '    const uint32_t rr_frame_cpu_base=g_audio_cycle_counter;',
        '    const uint32_t rr_frame_cpu_base=g_audio_cycle_counter-rr_main_debt;')
    source = replace(source, 'const unsigned rr_frame_fraction=(unsigned)(m->master_cycle%7u);',
        'const unsigned rr_frame_fraction=rr_main_fraction;')
    source = replace(source, 'unsigned fraction=(unsigned)(m->master_cycle%7u);',
        'unsigned fraction=rr_main_fraction;')
    source = replace(source, 'unsigned fraction=(unsigned)(g_machine.master_cycle%7u);',
        'unsigned fraction=rr_main_fraction;')
    source = replace(source, '    if(g_audio_cycle_counter<rr_vdp_cpu_origin)return 0;\n'
        '    unsigned phase=(g_audio_cycle_counter-rr_vdp_cpu_origin)*7u;',
        '    int32_t delta=(int32_t)(g_audio_cycle_counter-rr_vdp_cpu_origin);\n'
        '    if(delta<0)return 0;\n    unsigned phase=(unsigned)delta*7u;')
    source = replace(source, 'if(g_audio_cycle_counter<rr_line_end)glue_charge_68k_stall(rr_line_end-g_audio_cycle_counter);',
        'if((int32_t)(g_audio_cycle_counter-rr_line_end)<0)glue_charge_68k_stall(rr_line_end-g_audio_cycle_counter);')
    source = replace(source, '        m->master_cycle += MASTER_PER_LINE;',
        '        rr_main_fraction=(rr_main_fraction+MASTER_PER_LINE)%7u;\n'
        '        rr_main_debt=g_audio_cycle_counter-rr_line_end;\n'
        '        m->master_cycle += MASTER_PER_LINE;')
    # Initial power-on clears residues; pointer rewiring after load does not.
    source = replace(source, '    memset(&g_machine, 0, sizeof(g_machine));',
        '    rr_main_fraction=rr_main_debt=0;\n    memset(&g_machine, 0, sizeof(g_machine));')
    # These globals must precede machine_init, whereas the tail is below it.
    source = source.replace('static unsigned rr_main_fraction,rr_main_debt;\n', '', 1)
    source = 'static unsigned rr_main_fraction,rr_main_debt;\n' + source
    return source
