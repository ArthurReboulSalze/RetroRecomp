"""Checked fixes to the pinned GB runtime for the Game Boy Color only (docs/GAME_BOY_COLOR.md): applied after the Game Boy's own, to the program of the
`gbc` profile (`model == 'cgb'` in retrorecomp/gameboy_hardware.adapt_hardware); the original Game Boy's sources never go through them.

Each fix is named by the test it was measured against (Mooneye's all-model and Color tests, blargg's cgb_sound; test ROMs of the player's downloads, not
kept here) or by the document it follows. They show what the engine does after the change, not what a console does: hardware fidelity stays unproved."""
from .core import replace_once


def adapt_color_audio(source: str) -> str:
    """The sound unit (audio.c): power-off, the wave channel's byte writes, its timer."""
    return adapt_color_wave_timer(adapt_color_wave_write(adapt_color_power_off(source)))


def adapt_color_ppu(source: str) -> str:
    """The picture unit (ppu.c)."""
    return adapt_color_expansion(source)


def adapt_color_cpu(source: str) -> str:
    """The machine (gbrt.c): the bus during an OAM transfer, the timer's disable edge, the registers a cartridge finds."""
    return adapt_color_audio_order(adapt_color_registers(adapt_color_timer(adapt_color_oam_dma(source))))


def adapt_color_expansion(source: str) -> str:
    """Game Boy Color only: a 5-bit colour channel widens to 8 bits as (x << 3) | (x >> 2), the expansion every test reference of the colour
    hardware uses (the pinned runtime scales it as x * 255 / 31, which differs by one on most levels). The same function draws the Color's
    compatibility palettes for a Game Boy cartridge, so those follow. Neutral colours: no corrected LCD curve (docs/GAME_BOY_COLOR.md)."""
    for shift in (0, 5, 10):
        channel = f'((color >> {shift}) & 0x1F)'
        source = replace_once(source, f'(uint8_t)({channel} * 255 / 31);',
                              f'(uint8_t)(({channel} << 3) | ({channel} >> 2));')
    return source


def adapt_color_timer(source: str) -> str:
    """Game Boy Color only: turning the timer off (TAC bit 2 from 1 to 0) while its selected divider bit is high increments TIMA, on the colour
    hardware as on the original console. The pinned runtime suppressed that increment for the colour hardware (`cgb_disable_edge`), which failed
    Mooneye's `timer/rapid_toggle` (an all-model test) and nothing else: with the exception removed the thirteen timer tests pass on --model cgb."""
    return replace_once(source, '    const bool cgb_disable_edge = gb_is_cgb_hardware(ctx) &&',
                        '    const bool cgb_disable_edge = false &&')


def adapt_color_power_off(source: str) -> str:
    """Game Boy Color only: switching the sound unit off clears the length counters too, and the length part of NR11, NR21, NR31 and NR41 is not
    writable while it is off (blargg cgb_sound 08 and 11). It is the original console that keeps them (adapt_power_off)."""
    for number in (1, 2, 3, 4):
        source = replace_once(source, f'            apu->ch{number}.length_counter = kept_length[{number - 1}];\n', '')
    return replace_once(source,
        '    if (!power_on) {\n        /* The length part of NRx1 is writable while the unit is off (the duty bits are not). */\n',
        '    if (false) {\n        /* The original console writes the length part of NRx1 while the unit is off; the colour hardware does not. */\n')


def adapt_color_wave_write(source: str) -> str:
    """Game Boy Color only: while channel 3 plays, a write to any wave RAM address goes to the byte it is playing (a read already returns it);
    the pinned runtime ignored the write (blargg cgb_sound 12, "Write test"). With the channel off the write goes where it is aimed."""
    return replace_once(source,
        '        if (!apu->ch3.enabled) {\n            apu->ch3.wave_ram[addr - 0xFF30] = value;\n        }\n',
        '        if (!apu->ch3.enabled) {\n            apu->ch3.wave_ram[addr - 0xFF30] = value;\n'
        '        } else {\n            apu->ch3.wave_ram[apu->ch3.wave_pos / 2] = value;   /* the byte being played */\n        }\n')


def adapt_color_wave_timer(source: str) -> str:
    """Game Boy Color only: channel 3's timer keeps the period it was loaded with until it runs out; writing NR33 or NR34 changes the period of the
    next reload, not of the one in progress (blargg cgb_sound 12, "Timer period change"). The pinned runtime compared the running count with the live
    register. The period in use lives in the channel's unused `freq` field (set by a trigger, 0 until then), so that the saved state keeps its size."""
    source = replace_once(source,
        '                apu->ch3.timer = 0;\n                apu->ch3.wave_pos = 0;\n',
        '                apu->ch3.timer = 0;\n                apu->ch3.wave_pos = 0;\n'
        '                apu->ch3.freq = (uint16_t)((2048 - (apu->ch3.nr33 | ((apu->ch3.nr34 & 0x07) << 8))) * 2 + 6);   /* the period in use, and the first sample comes 6 clocks late */\n')
    return replace_once(source,
        '        apu->ch3.timer += cycles;\n        while (apu->ch3.timer >= period) {\n            apu->ch3.timer -= period;\n'
        '            apu->ch3.wave_pos = (apu->ch3.wave_pos + 1) & 31;\n        }\n',
        '        if (apu->ch3.freq == 0) apu->ch3.freq = (uint16_t)period;\n'
        '        apu->ch3.timer += cycles;\n        while (apu->ch3.timer >= apu->ch3.freq) {\n            apu->ch3.timer -= apu->ch3.freq;\n'
        '            apu->ch3.wave_pos = (apu->ch3.wave_pos + 1) & 31;\n            apu->ch3.freq = (uint16_t)period;       /* the reload takes the live period */\n        }\n')


def adapt_color_registers(source: str) -> str:
    """Game Boy Color only: the I/O registers a cartridge without the Color flag finds (the colour hardware in compatibility mode) and the joypad's
    start, against the tables of Mooneye's boot_hwio-C and unused_hwio-C (test data): the joypad selection lines start high ($FF, not the original
    console's $CF), the serial control register reads $7E where its speed bit does not exist (compatibility mode), VBK reads $FE and the two palette
    index ports read $C8 and $D0 there (what the Color's boot ROM leaves). The runtime has no boot ROM: these are the values it leaves, not its steps."""
    source = replace_once(source, '        ctx->io[0x00] = 0xCF; /* JOYP */', '        ctx->io[0x00] = 0xFF; /* JOYP: the selection lines start high */')
    source = replace_once(source, '        ctx->io[0x02] = gb_is_cgb_hardware(ctx) ? 0x7F : 0x7E; /* SC */',
                          '        ctx->io[0x02] = gb_is_cgb_mode(ctx) ? 0x7F : 0x7E; /* SC */')
    source = replace_once(source, '        if (addr == 0xFF02) return (uint8_t)(ctx->io[0x02] | (gb_is_cgb_hardware(ctx) ? 0x7Cu : 0x7Eu));',
                          '        if (addr == 0xFF02) return (uint8_t)(ctx->io[0x02] | (gb_is_cgb_mode(ctx) ? 0x7Cu : 0x7Eu));')
    source = replace_once(source, '            if (!gb_is_cgb_mode(ctx)) return 0xFF;\n            return (uint8_t)(ctx->vram_bank | 0xFE);',
                          '            if (!gb_is_cgb_mode(ctx)) return 0xFE;\n            return (uint8_t)(ctx->vram_bank | 0xFE);')
    return replace_once(source, '        if (addr >= 0xFF68 && addr <= 0xFF6B) {\n            if (!gb_is_cgb_mode(ctx)) return 0xFF;\n',
                        '        if (addr >= 0xFF68 && addr <= 0xFF6B) {\n'
                        '            if (!gb_is_cgb_mode(ctx)) return addr == 0xFF68 ? 0xC8 : addr == 0xFF6A ? 0xD0 : 0xFF;\n')


def adapt_color_audio_order(source: str) -> str:
    """A tick hands its cycles to the sound unit before the picture unit is synchronised, not after. In double speed a transfer of the HDMA stalls the CPU
    from inside that synchronisation, with a tick of its own that reaches the sound unit first: the unit then received the stall before the cycles of the tick
    that caused it, with the half-cycle carry of the wrong end, and the generated code (which splits an instruction's cycles around its memory access) and
    the interpreter (which does not) ended one system cycle apart, for good. Shantae, frame 17 of its boot route: from there the lock-step comparison with the
    interpreter saw a different sound sample at every sample boundary and stopped at frame 1,117. With this order the full 3,600 frames compare equal
    (54.7 million steps). The sound unit is unchanged; only the point where a tick delivers its cycles moves, for the Color's build only."""
    call = ('    gbrt_audio_schedule(ctx,\n                        old_div,\n                        cpu_cycles,\n                        system_cycles,\n'
            '                        ctx->cgb_double_speed != 0,\n                        previous_system_cycle_remainder);\n')
    anchor = '    /* The reference execution path must publish PPU mode/LY/STAT events at\n'
    source = replace_once(source, call, '')
    return replace_once(source, anchor, '    /* The sound unit gets this tick before a stall tick can nest inside gb_sync (retrorecomp/gameboy_color_hardware.py) */\n' + call + anchor)


def adapt_color_oam_dma(source: str) -> str:
    """Game Boy Color only: during an OAM transfer the CPU is locked out of OAM and the unusable area as on the original console; the pinned runtime
    let the colour hardware reach them (FE00-FEFF), which failed the sixteen all-model timing tests of the Mooneye suite that read the bus through a transfer
    (add_sp_e_timing ... rst_timing, oam_dma_restart, oam_dma_start, oam_dma_timing): with this one clause they pass on --model cgb. The split of the
    transfer's source bus (cartridge, video, work RAM) is the runtime's own, as Pan Docs describes it for the Color; no test discriminates it from the Game Boy's."""
    return replace_once(source,
        '    if (addr >= 0xFE00) {\n        return false;\n    }\n\n    const uint8_t source_high',
        '    if (addr >= 0xFF00) {\n        return false;\n    }\n'
        '    if (addr >= 0xFE00) {\n        return true;     /* OAM and the unusable area conflict with the transfer */\n    }\n\n'
        '    const uint8_t source_high')
