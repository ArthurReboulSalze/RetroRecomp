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


def _machine(source: str) -> str:
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
    source = replace_once(source, 'apu_read_controller((int)reg - 0x16) | (hw.data_bus & 0xE0)',
                          'apu_read_controller((int)reg - 0x16) | rr_nes_zapper_read((int)reg - 0x16) | (hw.data_bus & 0xE0)')
    return source + '\n#include "nes_machine_state.inc"\n'


def _ppu(source: str) -> str:
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
    source += '''
void rr_nes_ppu_aux_save(uint8_t *b) { b[0] = sm_rest; b[1] = dot_kind; }
void rr_nes_ppu_aux_load(const uint8_t *b) { sm_rest = b[0] != 0; dot_kind = b[1]; }
'''
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


def prepare_machine(project: Path, engine: Path) -> Path:
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
                data = _machine(data.decode('utf-8')).encode('utf-8')
            elif name == 'runner/cyc/hw_ppu.c':
                data = _ppu(data.decode('utf-8')).encode('utf-8')
            elif name == 'runner/cyc/hw_internal.h':
                text = replace_once(data.decode('utf-8'), '    uint8_t  tick;',
                    '    uint8_t  pal_bus_pending; /* New bus cycle before cycle-count commit. */\n    uint8_t  tick;')
                data = text.encode('utf-8')
            elif name == 'runner/cyc/hw_apu.c':
                data = _apu(data.decode('utf-8')).encode('utf-8')
            elif name == 'runner/cyc/hw_palette.c':
                text = data.decode('utf-8').replace('#include "hw_internal.h"', '#include "hw_internal.h"\n#include "retro_nes.h"')
                text = replace_once(text, '        if (hue > 13) level = 1;',
                    '        if (RR_NES_PAL) emphasis = (emphasis & 4) | ((emphasis & 1) << 1) | ((emphasis & 2) >> 1);\n'
                    '        if (hue > 13) level = 1;')
                data = text.encode('utf-8')
            elif name == 'runner/cyc/hw_mapper.c':
                data += b'\n#include "nes_mapper_state.inc"\n'
            elif name == 'runner/cyc/vendor/emu2413/emu2413.c':
                data += b'''
unsigned rr_opll_wave_index(const OPLL_SLOT *slot) {
    return slot->wave_table == wave_table_map[1] ? 1u : 0u;
}
void rr_opll_restore_wave(OPLL_SLOT *slot, unsigned index) {
    slot->wave_table = wave_table_map[index & 1];
}
'''
            transformed[name] = data
            _write(root / name, data)
    identity = hashlib.sha256()
    for name, data in sorted(transformed.items()):
        identity.update(name.encode('utf-8')); identity.update(data)
    for name in ('retro_nes.h', 'nes_machine_state.inc', 'nes_mapper_state.inc', 'nes_state.c'):
        identity.update((ASSETS / 'native' / name).read_bytes())
    _write(root / 'runner/cyc/nes_state_abi.h',
           f'#define RR_NES_STATE_ABI "{identity.hexdigest()}"\n'.encode('ascii'))
    return root / 'runner/cyc'
