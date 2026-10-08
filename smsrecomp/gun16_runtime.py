"""Checked adaptations of private engine copies for 16-bit peripherals."""
from .core import ConversionError


def replace(source, old, new):
    if source.count(old) != 1:
        raise ConversionError('Pinned gun bus/timing hook changed; refusing an ambiguous patch.')
    return source.replace(old, new, 1)


def md_bus(source):
    source = '#include "retro_gun_game.h"\n#include "gun16.h"\n' + source
    source = replace(source, '    uint16_t p  = b->pad[port];',
        '    if (RR16_GUN && port == 1) return rr16_md_gun_read(b->io_data[1], b->io_ctrl[1]);\n'
        '    uint16_t p  = b->pad[port];')
    source = replace(source,
        'case 0x04: pad_io_tick(b, 1, v); b->io_data[1] = v; break;',
        'case 0x04: pad_io_tick(b, 1, v); b->io_data[1] = v;\n'
        '            rr16_md_gun_io_write(b->io_data[1], b->io_ctrl[1]); break;')
    return replace(source, 'case 0x0A: b->io_ctrl[1] = v; break;',
        'case 0x0A: b->io_ctrl[1] = v;\n'
        '            rr16_md_gun_io_write(b->io_data[1], b->io_ctrl[1]); break;')


def md_vdp(source):
    source = '#include "gun16.h"\n' + source
    return replace(source,
        'return (uint16_t)(((v->scanline & 0xFF) << 8) | (v->in_hblank ? 0x00 : 0x80));',
        'return rr16_md_gun_hv((uint16_t)(((v->scanline & 0xFF) << 8) | (v->in_hblank ? 0x00 : 0x80)));')


def md_machine(source):
    source = '#include "retro_md_game.h"\n#include "retro_gun_game.h"\n#include "gun16.h"\n' + source
    source = replace(source, 'static uint32_t s_z80_off     = 0;',
        'static uint32_t rr_gun_slice_base = 0;\nextern uint32_t g_audio_cycle_counter;\n'
        'static uint32_t s_z80_off     = 0;')
    source = replace(source, 's_z80_off = done * MASTER_PER_Z80;',
        's_z80_off = rr_gun_slice_base + done * MASTER_PER_Z80;')
    source = replace(source, '        unsigned irq = gvdp_begin_scanline(&m->vdp, line);',
        '        unsigned irq = gvdp_begin_scanline(&m->vdp, line);\n'
        '        rr16_md_gun_line(line);')
    source = replace(source, '        glue_run_game_chunk(M68K_PER_LINE);', '''        rr_gun_slice_base = 0;
        if (RR_MD_STEP_AOT || RR16_GUN) {
            /* Audio mailbox loops can release BUSREQ only briefly.
             * Sampling only at a whole-line boundary can miss every release
             * and starve the Z80 forever while the 68000 polls its reply.
             * Split the existing line budgets; never add audio CPU cycles.
             * Carry 68000 instruction overshoot between slices. */
            uint32_t before = g_audio_cycle_counter;
            for (unsigned part = 0; part < 16; ++part) {
                unsigned cpu_target = (part + 1) * M68K_PER_LINE / 16;
                unsigned elapsed = g_audio_cycle_counter - before;
                rr_gun_slice_base = (part * Z80_PER_LINE / 16) * MASTER_PER_Z80;
                s_z80_off = rr_gun_slice_base;
                if (elapsed < cpu_target) glue_run_game_chunk(cpu_target - elapsed);
                if (rr16_md_gun_pending()) glue_own_interrupt(2, &m->vdp);
                glue_own_vint_service_latched(&m->vdp);
                step_z80(m, (part + 1) * Z80_PER_LINE / 16 - part * Z80_PER_LINE / 16);
            }
            rr_gun_slice_base = 0;
        } else {
            glue_run_game_chunk(M68K_PER_LINE);
        }''')
    return replace(source, '        step_z80(m, Z80_PER_LINE);',
        '        if (!RR_MD_STEP_AOT && !RR16_GUN) step_z80(m, Z80_PER_LINE);')


def md_glue(source):
    source = '#include "retro_gun_game.h"\n#include "gun16.h"\n' + source
    source = replace(source, 'static void check_cycle_budget(void)\n{',
        'static void check_cycle_budget(void)\n{\n'
        '    if (rr16_md_instruction_busy()) return;')
    source = replace(source, 'static inline void spin_check(uint32_t byte_addr, int is_write)\n{',
        'static inline void spin_check(uint32_t byte_addr, int is_write)\n{\n'
        '    if (rr16_md_instruction_busy()) return;')
    source = replace(source,
        '    if (byte_addr == 0xA01FFDu || byte_addr == 0xA01FFFu || byte_addr == 0xA11100u) {',
        '    if (!RR_MD_STEP_AOT && !RR16_GUN && (byte_addr == 0xA01FFDu || byte_addr == 0xA01FFFu || byte_addr == 0xA11100u)) {')
    source = replace(source,
        'static void rr_md_service_irq(int level, uint32_t vector, GVDP *vdp) {',
        'static void rr_md_service_irq(int level, uint32_t vector, GVDP *vdp) {\n'
        '    if (RR_MD_STEP_AOT || RR16_GUN) {\n'
        '        /* Execute the handler on the normal instruction fiber: any\n'
        '         * IRQ may wait for audio, so the Z80/VDP must keep progressing. */\n'
        '        uint16_t sr = g_cpu.SR; uint32_t pc = g_cpu.PC;\n'
        '        rr_md_exception_frame(sr, pc, (uint16_t)((sr & ~0x8700u) | 0x2000u | ((unsigned)level << 8)));\n'
        '        g_cpu.PC = m68k_read32(vector) & 0xffffffu;\n'
        '        g_audio_cycle_counter += 44; g_cycle_accumulator += 44;\n'
        '        s_game_yielded_vblank = 0; return;\n'
        '    }')
    return replace(source, '} else if (level == 4 && imask < 4) {',
        '} else if (level == 2 && imask < 2) {\n'
        '        rr16_md_gun_irq_begin(); rr_md_service_irq(2, 0x68, vdp);\n'
        '        return;\n'
        '    } else if (level == 4 && imask < 4) {')


def md_interpreter(source):
    source = '#include "retro_gun_game.h"\n#include "gun16.h"\n' + source
    start = source.index('M68kiStatus m68k_interp_step(void)')
    end = source.index('\n}', start) + 2
    function = source[start:end]
    function = replace(function, '    M68kiStatus st = exec_one(&ins, &next);',
        '    uint16_t gun_irq_sr = g_cpu.SR;\n    M68kiStatus st = exec_one(&ins, &next);')
    function = replace(function, '    interp_account_cycles(&ins, retired_native);',
        '    if (RR16_GUN && ins.mnemonic == MN_RTE && (gun_irq_sr & 0x700) == 0x200)\n'
        '        rr16_md_gun_irq_end();\n    interp_account_cycles(&ins, retired_native);')
    function = function.replace('M68kiStatus m68k_interp_step(void)',
                                'static M68kiStatus rr_md_instruction_body(void)', 1)
    function += '''
M68kiStatus m68k_interp_step(void) {
    /* The scheduler may inject a real exception frame only between retired
     * instructions, including when an instruction performs a stalled DMA. */
    rr16_md_instruction(true);
    M68kiStatus status = rr_md_instruction_body();
    rr16_md_instruction(false);
    return status;
}
'''
    return source[:start] + function + source[end:]


def snes_joypad(source):
    source = '#include "retro_gun_game.h"\n#include "gun16.h"\n' + source
    source = replace(source, '    int next = (value & 1u) != 0;',
        '    int next = (value & 1u) != 0;\n    rr16_scope_write_strobe(value);')
    source = replace(source, '    bank = bank_for(port);\n    idx = g_jp.index[port][bank];',
        '    if (RR16_GUN == RR_GUN_SCOPE && port == 1) return rr16_scope_read();\n'
        '    bank = bank_for(port);\n    idx = g_jp.index[port][bank];')
    source = replace(source, '    g_jp.auto_valid = 1;',
        '    if (RR16_GUN == RR_GUN_SCOPE) rr16_scope_auto();\n    g_jp.auto_valid = 1;')
    source = replace(source, '    slot = (int)((reg - 0x4218u) >> 1);',
        '    if (RR16_GUN == RR_GUN_SCOPE && (reg == 0x421a || reg == 0x421b))\n'
        '        return rr16_scope_auto_reg(reg);\n'
        '    slot = (int)((reg - 0x4218u) >> 1);')
    return replace(source,
        '    return (uint8_t)((g_jp.iobit[0] ? 0x40u : 0u) |\n                     (g_jp.iobit[1] ? 0x80u : 0u));',
        '    return rr16_scope_iobit((uint8_t)((g_jp.iobit[0] ? 0x40u : 0u) |\n'
        '                     (g_jp.iobit[1] ? 0x80u : 0u)));')


def snes_bus(source):
    source = '#include "retro_gun_game.h"\n#include "gun16.h"\n' + source
    source = replace(source, '  snes->ppuLatch = false;',
        '  snes->ppuLatch = RR16_GUN == RR_GUN_SCOPE;\n'
        '  if (RR16_GUN == RR_GUN_SCOPE) joypad_write_iobit(snes, 0xff);')
    return replace(source, '    if (snes->autoJoyTimer) {',
        '    rr16_scope_beam(h, v, span);\n    if (snes->autoJoyTimer) {')


def snes_ppu(source):
    source = '#include "retro_gun_game.h"\n#include "gun16.h"\n' + source
    source = replace(source, '    case 0x37: {',
        '    case 0x37: {\n'
        '      if (RR16_GUN == RR_GUN_SCOPE && !g_snes->ppuLatch) return 0;')
    source = replace(source,
        '      ppu->hCountSecond = false;\n      ppu->vCountSecond = false;\n      ppu->countersLatched = true;',
        '      if (RR16_GUN != RR_GUN_SCOPE) {\n'
        '        ppu->hCountSecond = false; ppu->vCountSecond = false;\n'
        '      }\n      ppu->countersLatched = true;')
    return replace(source, '      ppu->countersLatched = false; // TODO: only when ppulatch is set',
        '      if (RR16_GUN != RR_GUN_SCOPE || g_snes->ppuLatch) ppu->countersLatched = false;')
