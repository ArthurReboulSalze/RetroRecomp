"""Stage private machine adapters; never modify the pinned NES checkout."""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

from .core import replace_once, ConversionError
from .paths import ASSETS


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
        source += '''
void ppu_dot(void) { rr_step_dot(); }
void ppu_half_dot(void) { rr_step_half(); }
void rr_ppu_dot_half(void) { rr_step_dot(); rr_step_half(); }
void rr_ppu_half_dot(void) { rr_step_half(); rr_step_dot(); }
'''
    source += '''
void rr_nes_ppu_aux_save(uint8_t *b) { b[0] = sm_rest; b[1] = dot_kind; }
void rr_nes_ppu_aux_load(const uint8_t *b) { sm_rest = b[0] != 0; dot_kind = b[1]; }
'''
    if fast_ppu:
        source = source.replace('dot_kind = b[1]; }',
            'dot_kind = b[1]; rr_ppu_steady = dot_kind == DOT_GENERAL && rr_ppu_can_steady(); }')
    return source


def _apu(source: str) -> str:
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
    source += '''
size_t rr_nes_apu_size(void) { return sizeof(apu) + sizeof(audio); }
void rr_nes_apu_save(uint8_t *b) {
    memcpy(b, &apu, sizeof(apu)); memcpy(b + sizeof(apu), &audio, sizeof(audio));
}
void rr_nes_apu_load(const uint8_t *b) {
    memcpy(&apu, b, sizeof(apu)); memcpy(&audio, b + sizeof(apu), sizeof(audio));
    /* Queued host audio belongs to the discarded timeline. */
    audio.head = audio.tail = 0;
}
'''
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


def prepare_machine(project: Path, engine: Path, *, fast_ppu: bool = True) -> Path:
    from .feedback import stage
    project.mkdir(parents=True, exist_ok=True)
    stage(project, 'nes', '0'*64, cmake=False)
    root = project / 'machine'
    transformed = {}
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
                    data += b'\nvoid rr_ppu_dot_half(void);\nvoid rr_ppu_half_dot(void);\n'
            elif name == 'runner/cyc/hw_apu.c':
                data = _apu(data.decode('utf-8')).encode('utf-8')
            elif name == 'runner/cyc/hw_palette.c':
                text = data.decode('utf-8').replace('#include "hw_internal.h"', '#include "hw_internal.h"\n#include "retro_nes.h"')
                text = replace_once(text, '        if (hue > 13) level = 1;',
                    '        if (RR_NES_PAL) emphasis = (emphasis & 4) | ((emphasis & 1) << 1) | ((emphasis & 2) >> 1);\n'
                    '        if (hue > 13) level = 1;')
                data = text.encode('utf-8')
            elif name == 'runner/cyc/hw_mapper.c':
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
            _write(root / name, data)
    identity = hashlib.sha256()
    for name, data in sorted(transformed.items()):
        identity.update(name.encode('utf-8')); identity.update(data)
    for name in ('retro_nes.h', 'nes_machine_state.inc', 'nes_mapper_state.inc', 'nes_state.c', 'nes_ppu_fast.inc'):
        identity.update((ASSETS / 'native' / name).read_bytes())
    _write(root / 'runner/cyc/nes_state_abi.h',
           f'#define RR_NES_STATE_ABI "{identity.hexdigest()}"\n'.encode('ascii'))
    return root / 'runner/cyc'
