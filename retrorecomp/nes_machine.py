"""Stage private machine adapters; never modify the pinned NES checkout."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .core import replace_once, ConversionError
from .paths import ASSETS
from . import nes_state_layout


def _write(path: Path, data: bytes) -> None:
    if not path.is_file() or path.read_bytes() != data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def _machine(source: str, *, fast_ppu: bool = True) -> str:
    source = replace_once(source, '#include "hw_internal.h"',
                          '#include "hw_internal.h"\n#include "retro_nes.h"')
    source = replace_once(source, 'if (k == 4) sample_nmi();',
                          'if (k == (RR_NES_PAL ? 5u : 4u)) sample_nmi();')
    source = replace_once(source, 'else if (k == 7) apu_sample_irq();',
                          'else if (k == (RR_NES_PAL ? 9u : 7u)) apu_sample_irq();')
    source = replace_once(source, 'unsigned q = (hw.align + k) & 3;',
                          'unsigned q = RR_NES_PAL ? (unsigned)(((hw.cycles + hw.pal_bus_pending) * 16 + hw.align + k) % 5) : (hw.align + k) & 3;')
    # PPU register accesses can clock part of the *new* CPU cycle before
    # hw_cycle_finish increments hw.cycles. Preserve the same PAL phase on
    # both sides of that increment (16 master ticks is not divisible by 5).
    source = replace_once(source, '        hw.tick = 0;', '        hw.tick = 0;\n        hw.pal_bus_pending = 1;')
    source = source.replace('hw.cycles++;', 'hw.cycles++; hw.pal_bus_pending = 0;')
    source = replace_once(source, 'static inline void run_tick_0(void)\n{',
                          'static inline void run_tick_0(void)\n{\n    if (RR_NES_PAL) { run_tick(0); return; }')
    source = replace_once(source, 'if (hw.tick == 1) run_ticks_1_to_11();',
                          'if (!RR_NES_PAL && hw.tick == 1) run_ticks_1_to_11();')
    source = replace_once(source, 'while (hw.tick < 12)', 'while (hw.tick < RR_CPU_DIV)')
    source = replace_once(source, '    apu_power_on();',
                          '    apu_power_on();\n    rr_nes_zapper_reset();')
    source = replace_once(source, '        !nes_cart_variant_supported(&info)) return false;',
        '        !nes_cart_variant_supported(&info)) return false;\n'
        '#ifdef RR_NES_STATIC_MAPPER\n'
        '    if (info.mapper != RR_NES_STATIC_MAPPER) return false;\n'
        '#endif')
    source = replace_once(source, 'apu_read_controller((int)reg - 0x16) | (hw.data_bus & 0xE0)',
                          'apu_read_controller((int)reg - 0x16) | rr_nes_zapper_read((int)reg - 0x16) | (hw.data_bus & 0xE0)')
    if fast_ppu:
        # Pair only adjacent PPU edges with no CPU/APU/NMI event between them.
        # Partial register cycles and the rational PAL path retain run_tick.
        pairs = (
            ('        ppu_dot();\n        ppu_half_dot();   /* 6 */', '        rr_ppu_dot_half(); /* 4, 6 */'),
            ('        ppu_dot();        /* 8 */\n        ppu_half_dot();   /* 10 */', '        rr_ppu_dot_half(); /* 8, 10 */'),
            ('        ppu_half_dot();   /* 1 */\n        ppu_dot();        /* 3 */', '        rr_ppu_half_dot(); /* 1, 3 */'),
            ('        ppu_dot();\n        ppu_half_dot();   /* 9 */', '        rr_ppu_dot_half(); /* 7, 9 */'),
            ('        ppu_half_dot();\n        ppu_dot();        /* 6 */', '        rr_ppu_half_dot(); /* 4, 6 */'),
            ('        ppu_half_dot();   /* 8 */\n        ppu_dot();        /* 10 */', '        rr_ppu_half_dot(); /* 8, 10 */'),
            ('        ppu_dot();        /* 1 */\n        ppu_half_dot();   /* 3 */', '        rr_ppu_dot_half(); /* 1, 3 */'),
            ('        ppu_dot();        /* 9 */\n        ppu_half_dot();   /* 11 */', '        rr_ppu_dot_half(); /* 9, 11 */'),
        )
        for old, new in pairs:
            source = replace_once(source, old, new)
        # Deferred PPU edges (nes_ppu_lazy.inc): counted here, run in order
        # before anything can observe them. NMI sampling keeps its tick.
        source = replace_once(source, '    if (q == 0) ppu_dot();\n    else if (q == 2) ppu_half_dot();',
            '    if (rr_ppu_lazy) { if (q == 0 || q == 2) rr_ppu_edges(1); }\n'
            '    else if (q == 0) ppu_dot();\n    else if (q == 2) ppu_half_dot();')
        source = replace_once(source, 'static void run_ticks_1_to_11(void)\n{\n',
            'static void run_ticks_1_to_11(void)\n{\n'
            '    if (rr_ppu_lazy) {\n'
            '        unsigned odd = hw.align & 1;\n'
            '        rr_ppu_edges(1 + odd); sample_nmi();      /* 4 */\n'
            '        rr_ppu_edges(2 - odd); apu_sample_irq();  /* 7 */\n'
            '        rr_ppu_edges(2 + odd);\n'
            '        return;\n'
            '    }\n')
        source = replace_once(source, '    if (hw.align == 0) ppu_dot();\n    else if (hw.align == 2) ppu_half_dot();\n    clock_cpu_devices();',
            '    if (rr_ppu_lazy) { if (!(hw.align & 1)) rr_ppu_edges(1); }\n'
            '    else if (hw.align == 0) ppu_dot();\n    else if (hw.align == 2) ppu_half_dot();\n    clock_cpu_devices();')
        # Cartridge accesses can change what the PPU fetches.
        source = replace_once(source, 'uint8_t hw_bus_read(uint16_t addr)\n{\n',
            'uint8_t hw_bus_read(uint16_t addr)\n{\n    if (addr >= 0x4020 && addr < 0x8000) rr_ppu_sync();\n')
        source = replace_once(source, 'void hw_bus_write(uint16_t addr, uint8_t value)\n{\n',
            'void hw_bus_write(uint16_t addr, uint8_t value)\n{\n    if (addr >= 0x4020) rr_ppu_sync();\n')
        source = replace_once(source, '    hw.tick = 1;\n}\n', '    hw.tick = 1;\n    rr_ppu_lazy_reset();\n}\n')
        for signature in ('const uint16_t *cyc_frame_index(void) {', 'const uint32_t *cyc_frame_argb(void)\n{',
                          'uint64_t cyc_mem_state_hash(void)\n{', 'void cyc_mem_state_dump(void *file)\n{',
                          'uint64_t cyc_hw_state_hash(void)\n{', 'void cyc_hw_state_dump(void *file)\n{'):
            source = replace_once(source, signature, signature + '\n    rr_ppu_sync();')
    return source + '\n#include "nes_machine_state.inc"\n'


def _ppu(source: str, *, fast_ppu: bool = True) -> str:
    source = replace_once(source, '#include "hw_internal.h"',
                          '#include "hw_internal.h"\n#include "retro_nes.h"')
    # Scanline constants are code values, not the positions of the visible
    # viewport. Output remains 256x240 for both television systems.
    source = re.sub(r'\b261\b', 'RR_PRERENDER', source)
    source = replace_once(source, 'ppu.scanline == 260 && ppu.dot == 340',
                          'ppu.scanline == RR_PRERENDER - 1 && ppu.dot == 340')
    source = replace_once(source, 'if (ppu.odd_frame && rendering() && sl == 0)',
                          'if (!RR_NES_PAL && ppu.odd_frame && rendering() && sl == 0)')
    source = source.replace('hw_clock_run_ticks(7);', 'hw_clock_run_ticks(RR_READ_TICKS);')
    source = replace_once(source, 'hw_clock_run_ticks(2);',
                          'hw_clock_run_ticks(RR_NES_PAL ? 3 : 2);')
    source = replace_once(source,
        'if (!rendering() || (ppu.scanline >= 240 && ppu.scanline < RR_PRERENDER)) {',
        'if ((!rendering() || (ppu.scanline >= 240 && ppu.scanline < RR_PRERENDER)) &&\n'
        '            !(RR_NES_PAL && ppu.scanline >= 265 && ppu.scanline < RR_PRERENDER)) {')
    output = 'hw_frame_index[sl * 256 + dot - 4] = (uint16_t)(c | ppu.emphasis << 6);'
    if source.count(output) != 2:
        raise ConversionError('NES pixel output changed; Zapper adapter needs updating.')
    source = source.replace(output, output + '\n'
        '        if (RR_NES_ZAPPER) rr_nes_zapper_pixel(dot - 4, sl, (uint16_t)(c | ppu.emphasis << 6));')
    if fast_ppu:
        source = replace_once(source, '''static void shift_sprites(void)
{
    if (sprite_units_idle()) return;
    for (int i = 0; i < 8; i++) {
        if (ppu.spr_x[i] > 0 && !ppu.skipped_dot) {
            ppu.spr_x[i]--;
        } else if (rendering()) {
            ppu.spr_lo[i] <<= 1;
            ppu.spr_hi[i] <<= 1;
        }
    }
}''', '''#include "nes_sprite_shift.h"
static void shift_sprites(void)
{
    rr_nes_sprite_shift(ppu.spr_x,ppu.spr_lo,ppu.spr_hi,ppu.skipped_dot!=0,rendering());
}''')
        # The previous fast path computed an eligible-unit mask, then repeated
        # the eight-unit scalar search. Reuse the first set bit directly while
        # leaving composition, priority and sprite-zero-hit handling intact.
        source = replace_once(source, '''    if (ppu.show_spr && (ppu.dot > 8 || ppu.show_spr8) && !sprite_units_idle()) {
        int i;
        uint8_t sc = 0;
        for (i = 0; i < 8; i++) {
            if (ppu.spr_x[i] != 0 && !ppu.skipped_dot) continue;
            sc = (uint8_t)((ppu.spr_lo[i] >> 7) | ((ppu.spr_hi[i] >> 7) << 1));
            if (sc) break;
        }''', '''    unsigned i = ppu.show_spr && (ppu.dot > 8 || ppu.show_spr8)
        ? rr_nes_sprite_first(ppu.spr_x,ppu.spr_lo,ppu.spr_hi,ppu.skipped_dot!=0) : 8u;
    if (i < 8) {
        uint8_t sc = (uint8_t)((ppu.spr_lo[i] >> 7) | ((ppu.spr_hi[i] >> 7) << 1));''')
        # Host-only extra sprite units (F5): prepared after the original units
        # were loaded for the next scanline, composed only behind them.
        source = replace_once(source, 'static void eval_load(void)\n{',
            '#include "nes_sprite_extra.inc"\nstatic void eval_load(void)\n{')
        source = replace_once(source, '''    if (ppu.ale && !ppu.rd) ppu.octal_latch = (uint8_t)ppu.vbus;
}

static void sprite_evaluation(void)''', '''    if (ppu.ale && !ppu.rd) ppu.octal_latch = (uint8_t)ppu.vbus;
    if (ppu.dot == 320) rr_xs_prepare();
}

static void sprite_evaluation(void)''')
        source = replace_once(source, '''            pal = (uint8_t)((ppu.spr_attr[i] & 3) | 4);
        }
    }
    uint8_t addr;''', '''            pal = (uint8_t)((ppu.spr_attr[i] & 3) | 4);
        }
    } else if (rr_xs.count) rr_xs_pixel(&color, &pal);
    uint8_t addr;''')
        source = replace_once(source, 'void ppu_dot(void)\n{',
            '#include "nes_ppu_fast.inc"\nHW_ALWAYS_INLINE void rr_step_dot(void)\n{')
        source = replace_once(source, 'void ppu_half_dot(void)\n{',
            'HW_ALWAYS_INLINE void rr_step_half(void)\n{')
        classify = '    if (dot_kind == DOT_UNKNOWN) dot_kind = is_blank() ? DOT_BLANK : DOT_GENERAL;'
        if source.count(classify) != 2:
            raise ConversionError('NES PPU clock classification changed; review the settled-latch path.')
        source = source.replace(classify, '''    if (dot_kind == DOT_UNKNOWN) {
        dot_kind = is_blank() ? DOT_BLANK : DOT_GENERAL;
        rr_ppu_steady = dot_kind == DOT_GENERAL && rr_ppu_can_steady();
    }''')
        for general, steady in (('general_dot', 'rr_ppu_steady_dot'), ('general_half_dot', 'rr_ppu_steady_half')):
            source = replace_once(source,
                '    } else {\n        ' + general + '();\n        if (!rendering()) dot_kind = DOT_UNKNOWN;',
                '    } else if (rr_ppu_steady) {\n        ' + steady + '();\n    } else {\n        ' +
                general + '();\n        if (!rendering()) dot_kind = DOT_UNKNOWN;\n'
                '        else rr_ppu_steady = rr_ppu_can_steady();')
        source = replace_once(source, '/* ---- registers ---- */',
                              '#include "nes_ppu_lazy.inc"\n\n/* ---- registers ---- */')
        for name, call in (('uint8_t ppu_read(uint16_t addr)', 'uint8_t value = read_register(addr);'),
                           ('void ppu_write(uint16_t addr, uint8_t value)', 'write_register(addr, value);')):
            source = replace_once(source,
                f'{name}\n{{\n    dot_kind = DOT_UNKNOWN;\n    {call}\n    dot_kind = DOT_UNKNOWN;\n',
                f'{name}\n{{\n    rr_ppu_access_begin();\n    dot_kind = DOT_UNKNOWN;\n    {call}\n'
                '    dot_kind = DOT_UNKNOWN;\n    rr_ppu_access_end();\n')
        source = replace_once(source, '    memset(&ppu, 0, sizeof(ppu));\n    sm_rest = false;',
                              '    rr_ppu_lazy_stop();\n    memset(&ppu, 0, sizeof(ppu));\n    sm_rest = false;')
        source += '''
void ppu_dot(void) { rr_step_dot(); }
void ppu_half_dot(void) { rr_step_half(); }
void rr_ppu_dot_half(void)
{
    /* Eager boards also take the visible-scanline pair when it applies. */
    if (dot_kind == DOT_GENERAL && rr_ppu_steady && ppu.scanline < 240 && ppu.dot != 340) {
        rr_ppu_visible_pair();
        return;
    }
    rr_step_dot();
    rr_step_half();
}
void rr_ppu_half_dot(void) { rr_step_half(); rr_step_dot(); }
'''
    source += '''
void rr_nes_ppu_aux_save(uint8_t *b) { b[0] = sm_rest; b[1] = dot_kind; }
void rr_nes_ppu_aux_load(const uint8_t *b) { sm_rest = b[0] != 0; dot_kind = b[1]; }
'''
    if fast_ppu:
        source = source.replace('dot_kind = b[1]; }',
            'dot_kind = b[1]; rr_ppu_steady = dot_kind == DOT_GENERAL && rr_ppu_can_steady(); rr_ppu_lazy_reset(); }')
    return source


def _apu(source: str, *, fast_audio: bool = True) -> str:
    source = replace_once(source, '#include "hw_internal.h"',
                          '#include "hw_internal.h"\n#include "retro_nes.h"')
    source = replace_once(source, '21477272.0 / 12.0', 'RR_CPU_HZ')
    source = replace_once(source, 'apu.dmc_rate = 428;', 'apu.dmc_rate = dmc_rate_table[0];')
    source = replace_once(source,
        '    428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142, 128, 106, 84, 72, 54,',
        '#if RR_NES_PAL\n    398, 354, 316, 298, 276, 236, 210, 198, 176, 148, 132, 118, 98, 78, 66, 50,\n#else\n'
        '    428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142, 128, 106, 84, 72, 54,\n#endif')
    source = replace_once(source,
        '    4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068,',
        '#if RR_NES_PAL\n    4, 8, 14, 30, 60, 88, 118, 148, 188, 236, 354, 472, 708, 944, 1890, 3778,\n#else\n'
        '    4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068,\n#endif')
    for ntsc, pal in ((7457, 8313), (14913, 16627), (22371, 24939), (37281, 41565),
                      (37282, 41566), (29828, 33252), (29829, 33253), (29830, 33254)):
        source = re.sub(rf'\b{ntsc}\b', f'(RR_NES_PAL ? {pal} : {ntsc})', source)
    # PAL fixes the extra controller reads caused by DMC halt cycles.
    source = replace_once(source, '    hw_bus_read(hw.cpu_addr);',
        '    if (!RR_NES_PAL || hw.cpu_addr < 0x4016 || hw.cpu_addr > 0x4017 || apu.oam_dma)\n'
        '        hw_bus_read(hw.cpu_addr);')
    # The audio state becomes a named type so that its serialiser can be written from its definition.
    source = replace_once(source, 'static struct {\n    bool     on;', 'typedef struct {\n    bool     on;')
    source = replace_once(source, '} audio;', '} RrAudio;\nstatic RrAudio audio;')
    source += '''
#include "nes_state_apu.inc"
size_t rr_nes_apu_size(void) { return rr_size_HwApu() + rr_size_RrAudio(); }
void rr_nes_apu_save(uint8_t *b) {
    b = rr_ser_HwApu(b, &apu); rr_ser_RrAudio(b, &audio);
}
void rr_nes_apu_load(const uint8_t *b) {
    b = rr_de_HwApu(b, &apu); rr_de_RrAudio(b, &audio);
    /* Queued host audio belongs to the discarded timeline. */
    audio.head = audio.tail = 0;
}
'''
    if fast_audio:
        # Cache only the base DAC level. Timers, DMA, IRQs, expansion sound and
        # the floating-point accumulation still advance on every CPU cycle.
        source = replace_once(source, 'void apu_audio_enable(bool on, int sample_rate)',
            '''static bool rr_mix_dirty = true;
static double rr_mix_level;
void apu_audio_enable(bool on, int sample_rate)''')
        for signature in (
            'void apu_audio_enable(bool on, int sample_rate)',
            'static void audio_quarter_frame(void)',
            'static void audio_half_frame(void)',
            'static void clock_length_counters(void)',
            'void apu_debug_set_noise(uint16_t lfsr, uint16_t timer)',
            'void apu_write(uint16_t addr, uint8_t value)',
            'void apu_power_on(void)',
        ):
            source = replace_once(source, signature + '\n{',
                                  signature + '\n{\n    rr_mix_dirty = true;')
        source = replace_once(source, 'void rr_nes_apu_load(const uint8_t *b) {',
                              'void rr_nes_apu_load(const uint8_t *b) {\n    rr_mix_dirty = true;')
        source = replace_once(source, '                p->step = (p->step + 1) & 7;',
            '                p->step = (p->step + 1) & 7;\n'
            '                if (apu.len[ch].count) rr_mix_dirty = true;')
        source = replace_once(source, '        apu.noise_timer = (uint16_t)(apu.noise_period - 1);',
            '        if (apu.len[CH_NOISE].count) rr_mix_dirty = true;\n'
            '        apu.noise_timer = (uint16_t)(apu.noise_period - 1);')
        source = replace_once(source, '            if (!apu.dmc_out_silent) {',
            '            if (!apu.dmc_out_silent) {\n                rr_mix_dirty = true;')
        source = replace_once(source,
            '    if (apu.tri_period >= 2) apu.tri_out = (uint8_t)(apu.tri_step < 16 ? 15 - apu.tri_step : apu.tri_step - 16);',
            '''    if (apu.tri_period >= 2) {
        uint8_t next = (uint8_t)(apu.tri_step < 16 ? 15 - apu.tri_step : apu.tri_step - 16);
        if (next != apu.tri_out) rr_mix_dirty = true;
        apu.tri_out = next;
    }''')
        source = replace_once(source,
            '    uint8_t out[5];\n    apu_channel_levels(out);\n'
            '    double level = audio.pulse_mix[out[0] + out[1]] + audio.tnd_mix[3 * out[2] + 2 * out[3] + out[4]];',
            '''    if (rr_mix_dirty) {
        uint8_t out[5];
        apu_channel_levels(out);
        /* Preserve the original float sum before conversion to double. */
        rr_mix_level = audio.pulse_mix[out[0] + out[1]] + audio.tnd_mix[3 * out[2] + 2 * out[3] + out[4]];
        rr_mix_dirty = false;
    }
    double level = rr_mix_level;''')
    return source


def _interpreter(source: str) -> str:
    source = replace_once(source,
        'void cpu_interp_step(void) {\n    uint16_t pc = cpu.pc;\n'
        '    uint8_t opcode, b1 = 0, b2 = 0;\n'
        '    if (cpu_fetch(pc, &opcode)) { cpu_interrupt(false); return; }',
        'void cpu_interp_fetched(uint8_t opcode) {\n    uint16_t pc = cpu.pc;\n'
        '    uint8_t b1 = 0, b2 = 0;')
    return source + '''
void cpu_interp_step(void) {
    uint16_t pc = cpu.pc; uint8_t opcode;
    if (cpu_fetch(pc, &opcode)) { cpu_interrupt(false); return; }
    rr_nes_feedback(pc, opcode);
    rr_nes_note_ram(pc, opcode);
    cpu_interp_fetched(opcode);
}
'''


def _run(source: str) -> str:
    source = '#include "runtime_feedback.h"\n' + source
    source = replace_once(source,
        '            cyc_native_run();\n            cyc_run_native_cycles += cyc_cycle_count() - before;',
        '            uint64_t interpreted = cyc_run_interp_rom_cycles + cyc_run_interp_ram_cycles + cyc_run_interp_other_cycles;\n'
        '            cyc_native_run();\n'
        '            interpreted = cyc_run_interp_rom_cycles + cyc_run_interp_ram_cycles + cyc_run_interp_other_cycles - interpreted;\n'
        '            cyc_run_native_cycles += cyc_cycle_count() - before - interpreted;')
    return source + '''
void rr_nes_interp_fetched(uint16_t pc, uint8_t op, uint64_t before, bool rom, unsigned bank) {
    rr_nes_feedback(pc, op);
    /* The pinned seed format has only $8000-$FFFF slots. A lower ROM alias
     * is covered densely; never mislabel it as a seed at $E000/$F000. */
    if (rom && pc >= 0x8000 && cyc_run_miss && bank < hw_cart.prg_slots) {
        unsigned index = ((bank * 8 + ((pc >> 12) & 7)) << 12) | (pc & 0xFFF);
        cyc_run_miss[index]++;
    }
    cpu_interp_fetched(op);
    uint64_t took = cyc_cycle_count() - before;
    if (pc < 0x2000) cyc_run_interp_ram_cycles += took;
    else if (rom) cyc_run_interp_rom_cycles += took;
    else cyc_run_interp_other_cycles += took;
}
'''


def _mmc1_a12(source: str) -> str:
    """MMC1: a PPU A12 change rebuilds the bank tables only when it can change them.

    A12 picks CHR register 0 or 1 for the board's CPU-side signals (SxROM: the outer 256 KiB PRG
    bank, the work RAM bank and its enable), which `mmc1_apply` derives from bits 2 to 4 of that
    register only; the PRG and CHR windows always use their own registers, and in 8 KiB CHR mode
    register 0 serves both phases. Where those bits are equal the rebuild produces the tables it
    already holds, so it is skipped; the pin is still recorded for the next CPU write. This is the
    condition of the upstream's later change (nesrecomp 67691b9), carried here without moving the pin."""
    return replace_once(source,
        '        if (hw_cart.m.a12!=a12) { hw_cart.m.a12=(uint8_t)a12; mmc1_apply(); }',
        '        if (hw_cart.m.a12!=a12) {\n'
        '            hw_cart.m.a12=(uint8_t)a12;\n'
        '            if ((hw_cart.m.ctrl & MMC1_CTRL_CHR_4K) && ((hw_cart.m.chr0 ^ hw_cart.m.chr1) & 0x1C)) mmc1_apply();\n'
        '        }')


_MACHINE_STRUCTS = {'Cpu6502', 'HwMachine', 'HwCart', 'HwPpu', 'HwVrc6Audio', 'HwNamco', 'HwRambo', 'HwJaleco',
                    'HwFme7', 'Hw5B', 'NesCartInfo', 'NesEeprom', 'NesBarcode', 'Mmc5State', 'Mmc5Pulse',
                    'RrZapper', 'RrStateHeader', 'RrMachineState'}
_APU_STRUCTS = {'LengthCounter', 'Envelope', 'Pulse', 'HwApu', 'RrAudio'}
_VRC7_STRUCTS = {'OPLL_PATCH', 'OPLL_SLOT', 'OPLL'}


def _state_layouts(transformed: dict[str, bytes]) -> dict[str, str]:
    """The quick-state serialisers, written from the struct definitions of the staged sources."""
    def text(name: str) -> str:
        return transformed[name].decode('utf-8')
    machine, apu, vrc7 = {}, {}, {}
    for name in ('runner/cyc/hw_internal.h', 'runner/cyc/cpu6502.h', 'runner/cyc/mmc5_state.h', 'common/nes_cart.h',
                 'common/nes_eeprom.h', 'common/nes_barcode.h'):
        machine.update(nes_state_layout.parse(text(name), _MACHINE_STRUCTS))
    machine.update(nes_state_layout.parse((ASSETS / 'native/nes_machine_state.inc').read_text(encoding='utf-8'),
                                          _MACHINE_STRUCTS))
    apu.update(nes_state_layout.parse(text('runner/cyc/hw_apu.c'), _APU_STRUCTS))
    vrc7.update(nes_state_layout.parse(text('runner/cyc/vendor/emu2413/emu2413.h'), _VRC7_STRUCTS))
    return {'runner/cyc/nes_state_main.inc': nes_state_layout.generate(machine, ['RrStateHeader', 'RrMachineState']),
            'runner/cyc/nes_state_apu.inc': nes_state_layout.generate(apu, ['HwApu', 'RrAudio']),
            'runner/cyc/nes_state_vrc7.inc': nes_state_layout.generate(vrc7, ['OPLL'])}


def prepare_machine(project: Path, engine: Path, *, fast_ppu: bool = True,
                    fast_audio: bool = True, fast_mmc1: bool = True) -> Path:
    from .feedback import stage
    project.mkdir(parents=True, exist_ok=True)
    stage(project, 'nes', '0'*64, cmake=False)
    root = project / 'machine'
    transformed = {}
    identity_inputs = {}
    for relative in ('runner/cyc', 'common'):
        for path in (engine / relative).rglob('*'):
            if not path.is_file():
                continue
            name = path.relative_to(engine).as_posix()
            data = path.read_bytes()
            if path.suffix in ('.c', '.h', '.inc', '.cmake'):
                data = data.replace(b'\r\n', b'\n')
            if name == 'runner/cyc/hw_machine.c':
                data = _machine(data.decode('utf-8'), fast_ppu=fast_ppu).encode('utf-8')
            elif name == 'runner/cyc/hw_ppu.c':
                data = _ppu(data.decode('utf-8'), fast_ppu=fast_ppu).encode('utf-8')
            elif name == 'runner/cyc/hw_internal.h':
                text = replace_once(data.decode('utf-8'), '    uint8_t  tick;',
                    '    uint8_t  pal_bus_pending; /* New bus cycle before cycle-count commit. */\n    uint8_t  tick;')
                data = text.encode('utf-8')
                if fast_ppu:
                    data += b'''
void rr_ppu_dot_half(void);
void rr_ppu_half_dot(void);
/* Deferred PPU edges (nes_ppu_lazy.inc). */
extern unsigned rr_ppu_due, rr_ppu_room;
extern bool rr_ppu_lazy;
void rr_ppu_flush(void);
void rr_ppu_lazy_reset(void);
static inline void rr_ppu_edges(unsigned n) { rr_ppu_due += n; if (rr_ppu_due >= rr_ppu_room) rr_ppu_flush(); }
static inline void rr_ppu_sync(void) { if (rr_ppu_due) rr_ppu_flush(); }
'''
                else:
                    data += b'\nstatic inline void rr_ppu_sync(void) {}\n'
            elif name == 'runner/cyc/hw_apu.c':
                data = _apu(data.decode('utf-8'), fast_audio=fast_audio).encode('utf-8')
            elif name == 'runner/cyc/hw_palette.c':
                text = data.decode('utf-8').replace('#include "hw_internal.h"', '#include "hw_internal.h"\n#include "retro_nes.h"')
                text = replace_once(text, '        if (hue > 13) level = 1;',
                    '        if (RR_NES_PAL) emphasis = (emphasis & 4) | ((emphasis & 1) << 1) | ((emphasis & 2) >> 1);\n'
                    '        if (hue > 13) level = 1;')
                data = text.encode('utf-8')
            elif name == 'runner/cyc/hw_mapper.c':
                if fast_mmc1:
                    data = _mmc1_a12(data.decode('utf-8')).encode('utf-8')
                data += b'\n#include "nes_mapper_state.inc"\n' + (ASSETS / 'native/nes_ram.inc').read_bytes()
            elif name == 'runner/cyc/hw.h':
                text = data.decode('utf-8')
                text = replace_once(text, 'bool hw_prg_is_rom(uint16_t addr);', '''bool hw_prg_is_rom(uint16_t addr);
bool rr_nes_rom_bank4(uint16_t pc, unsigned *bank);
bool rr_nes_ram_peek(uint16_t pc, uint8_t *value);
void rr_nes_feedback(uint16_t pc, uint8_t op);
void rr_nes_note_ram(uint16_t pc, uint8_t op);
void rr_nes_ram_trace_enable(void);
void rr_nes_ram_trace_merge(const char *path);
void rr_nes_ram_trace_write(void *file);
void rr_nes_interp_fetched(uint16_t pc, uint8_t op, uint64_t before, bool rom, unsigned bank);''')
                data = text.encode('utf-8')
            elif name == 'runner/cyc/cpu6502.h':
                data = replace_once(data.decode('utf-8'), 'void cpu_interp_step(void);',
                                    'void cpu_interp_step(void);\nvoid cpu_interp_fetched(uint8_t opcode);').encode('utf-8')
            elif name == 'runner/cyc/cpu6502_interp.c':
                data = _interpreter(data.decode('utf-8')).encode('utf-8')
            elif name == 'runner/cyc/cyc_run.c':
                data = _run(data.decode('utf-8')).encode('utf-8')
                # The host observes the whole machine between frames.
                data = replace_once(data.decode('utf-8'),
                    '            else cyc_run_interp_other_cycles += took;\n        }\n    }\n}',
                    '            else cyc_run_interp_other_cycles += took;\n        }\n    }\n    rr_ppu_sync();\n}').encode('utf-8')
            elif name == 'runner/cyc/vendor/emu2413/emu2413.c':
                data += b'''
unsigned rr_opll_wave_index(const OPLL_SLOT *slot) {
    return slot->wave_table == wave_table_map[1] ? 1u : 0u;
}
void rr_opll_restore_wave(OPLL_SLOT *slot, unsigned index) {
    slot->wave_table = wave_table_map[index & 1];
}
'''
            if name == 'runner/cyc/cyc.cmake':
                # The key must not depend on where the project is: hash the engine's own file.
                identity_inputs[name] = data
                data += ('\nlist(APPEND NESRECOMP_CYC_SOURCES "' + (project/'runtime_feedback.c').as_posix() + '")\n'
                         'list(APPEND NESRECOMP_CYC_INCLUDE_DIRS "' + project.as_posix() + '")\n').encode('utf-8')
            if path.suffix in ('.c', '.h', '.inc'):
                # The cartridge's mapper identity is immutable. Preserve its
                # stored metadata and every assignment; only reads may fold.
                text = re.sub(r'\bhw_cart\.mapper\b(?!\s*=(?!=))', 'RR_NES_MAPPER', data.decode('utf-8'))
                if name == 'runner/cyc/hw_internal.h':
                    text = replace_once(text, 'HW_ALWAYS_INLINE uint8_t hw_cart_prg_read',
                        '#ifdef RR_NES_STATIC_MAPPER\n#define RR_NES_MAPPER RR_NES_STATIC_MAPPER\n'
                        '#else\n#define RR_NES_MAPPER hw_cart.mapper\n#endif\n\n'
                        'HW_ALWAYS_INLINE uint8_t hw_cart_prg_read')
                data = text.encode('utf-8')
            transformed[name] = data
            identity_inputs.setdefault(name, data)
            _write(root / name, data)
    layouts = _state_layouts(transformed)
    for name, text in layouts.items():
        data = text.encode('utf-8')
        identity_inputs[name] = data
        _write(root / name, data)
    identity = hashlib.sha256()
    for name, data in sorted(identity_inputs.items()):
        identity.update(name.encode('utf-8')); identity.update(data)
    for name in ('retro_nes.h', 'nes_machine_state.inc', 'nes_mapper_state.inc', 'nes_state.c', 'nes_ppu_fast.inc', 'nes_ppu_lazy.inc', 'nes_sprite_extra.inc', 'nes_sprite_shift.h'):
        identity.update((ASSETS / 'native' / name).read_bytes())
    _write(root / 'runner/cyc/nes_state_abi.h',
           f'#define RR_NES_STATE_ABI "{identity.hexdigest()}"\n'.encode('ascii'))
    return root / 'runner/cyc'
