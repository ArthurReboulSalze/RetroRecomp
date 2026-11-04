"""Apply small, checked RetroRecomp adaptations to a generated GB project.

The pinned upstream checkout is never edited. Changes live in the private
per-game build and fail if an upstream source marker changes.
"""
from __future__ import annotations

import re
from pathlib import Path
from shutil import copyfile

from .core import ConversionError, replace_once
from .paths import ASSETS
from . import __version__


def adapt_wisdom_tree(source: str) -> str:
    """The Wisdom Tree mapper in the pinned runtime (gbrt.c).

    Sources: Pan Docs ("Wisdom Tree": a 74LS377 latch, the 32 KiB ROM window switched as a whole, the bank taken from the low
    eight address lines of a write to 0000-7FFF, the data ignored, no RAM) and the detection of mGBA (the words WISDOM and TREE
    in a ROM whose header says ROM only). No code of either is used. The cartridges are header type 00 with more than 32 KiB,
    so the pinned runtime kept them on a fixed second bank. The latch is undefined at power-on; bank 0 is the choice here, and
    the cartridges repeat the header and the switching code in every bank.
    """
    source = replace_once(source, 'bool gb_context_load_rom(GBContext* ctx, const uint8_t* data, size_t size) {',
        '/* Header type 00, a ROM of whole 32 KiB banks larger than 32 KiB, and both words in it: a Wisdom Tree cartridge. */\n'
        'static bool rr_gb_detect_wisdom_tree(const uint8_t* rom, size_t size) {\n'
        '    if (!rom || size <= 0x8000u || (size & 0x7FFFu) != 0 || rom[0x147] != 0x00) return false;\n'
        '    bool wisdom = false, tree = false;\n'
        '    for (size_t i = 0; i + 4 <= size && !(wisdom && tree); ++i) {\n'
        '        if (!wisdom && i + 6 <= size && memcmp(rom + i, "WISDOM", 6) == 0) wisdom = true;\n'
        '        if (!tree && memcmp(rom + i, "TREE", 4) == 0) tree = true;\n'
        '    }\n'
        '    return wisdom && tree;\n'
        '}\n\n'
        'bool gb_context_load_rom(GBContext* ctx, const uint8_t* data, size_t size) {')
    source = replace_once(source, '    /* Parse Header for RAM/Battery info */',
        '    ctx->rr_wisdom_tree = size > 0x149 && rr_gb_detect_wisdom_tree(ctx->rom, size) ? 1 : 0;\n'
        '    /* Parse Header for RAM/Battery info */')
    source = replace_once(source,
        '    if (ctx->mbc_type >= 0x01 && ctx->mbc_type <= 0x03) {\n        const uint8_t raw_low = ctx->rom_bank_low & 0x1F;',
        '    if (ctx->rr_wisdom_tree) {\n'
        '        /* The latch holds a 32 KiB bank: both windows change together (16 KiB banks 2n and 2n+1). */\n'
        '        const uint32_t banks = (uint32_t)(ctx->rom_size / 0x8000u);\n'
        '        return banks ? (uint16_t)(((uint32_t)ctx->rom_bank % banks) * 2u + (addr >= 0x4000 ? 1u : 0u)) : 0;\n'
        '    }\n'
        '    if (ctx->mbc_type >= 0x01 && ctx->mbc_type <= 0x03) {\n        const uint8_t raw_low = ctx->rom_bank_low & 0x1F;')
    source = replace_once(source, '    /* MBC Write Handling */\n    if (addr < 0x8000) {',
        '    /* MBC Write Handling */\n    if (addr < 0x8000) {\n'
        '        if (ctx->rr_wisdom_tree) {\n'
        '            ctx->rom_bank = (uint16_t)(addr & 0xFFu);   /* the address selects the bank, the value is ignored */\n'
        '            return;\n'
        '        }')
    return replace_once(source, '    ctx->rom_bank = 1;\n    ctx->ram_bank = 0;',
        '    ctx->rom_bank = 1;\n    if (ctx->rr_wisdom_tree) ctx->rom_bank = 0;\n    ctx->ram_bank = 0;')


# EI enables IME after the instruction that follows it (Pan Docs, "Interrupts"; the vectors of SingleStepTests/sm83; EI followed by DI
# lets no interrupt in between). The pinned runtime stored ime_pending = 1 for EI and turned it into IME at the END of the same tick
# (EI's own), in the interpreter, in the generated code and in the stubs alike. Its interrupt test, which runs inside gb_tick before
# that line, lagged one tick behind, which put the interrupt after the next instruction in ordinary flow, but IME itself was already
# set after EI: the state the vectors see, and what the dispatch loop sees when EI is the last instruction of a block or a
# single-step is taken.
# ime_pending now has three values: 0, 1 (EI just ran) and 2 (the instruction after EI is next). The FIRST thing every tick does is
# move 1 to 2 (that is EI's own tick, its only one) and 2 to IME (the first tick of the next instruction); the interrupt test then
# runs with IME already set, so the interrupt is taken right after that instruction. DI clears the flag. An EI that finds it
# already armed leaves it (EI, EI: IME is on after the second, as on the console).
EI_PROMOTE = 'if (ctx->ime_pending) { ctx->ime = 1; ctx->ime_pending = 0; }'
EI_PROMOTE_FIRST = ('if (ctx->ime_pending) { if (ctx->ime_pending == 1) ctx->ime_pending = 2; '
                    'else { ctx->ime = 1; ctx->ime_pending = 0; } }')
EI_ARM = 'ctx->ime_pending = 1;'
EI_ARM_ONCE = 'if (!ctx->ime_pending) ctx->ime_pending = 1;'


def adapt_ei_delay(source: str) -> str:
    """The delayed EI in gbrt.c: the promotion moves from the three ends of gb_tick to its start, and the upstream high-memory stub,
    which set IME directly (and whose DI left a pending EI standing), follows the same rule."""
    line = re.compile(r'^[ ]+' + re.escape(EI_PROMOTE) + r'\n', re.M)
    if len(line.findall(source)) != 3 or source.count(EI_PROMOTE) != 3:
        raise ConversionError(f'gbrt.c has {source.count(EI_PROMOTE)} IME promotions in gb_tick, expected 3.')
    source = line.sub('', source)
    source = replace_once(source, '    static uint32_t last_log = 0;\n',
                          '    static uint32_t last_log = 0;\n    ' + EI_PROMOTE_FIRST + '\n')
    source = replace_once(source, '        case 0xF3: /* DI */\n            ctx->ime = 0;\n',
                          '        case 0xF3: /* DI */\n            ctx->ime = 0;\n            ctx->ime_pending = 0;\n')
    source = replace_once(source, '        case 0xFB: /* EI */\n            ctx->ime = 1;\n',
                          '        case 0xFB: /* EI */\n            ' + EI_ARM_ONCE + '\n')
    # EI ; HALT with an interrupt already pending and IME still off: the flag is armed (2), IME comes with the tick of the HALT itself, so
    # this is not the HALT bug (which needs IME off and nothing about to turn it on): the interrupt is taken after the HALT, once, as before.
    source = replace_once(source, '    if (!ctx->ime &&\n        (gb_read8(ctx, 0xFFFF) & gb_read8(ctx, 0xFF0F) & 0x1F)) {\n        ctx->halted = 0;\n        ctx->halt_bug = 1;',
                          '    if (!ctx->ime && ctx->ime_pending != 2 &&\n        (gb_read8(ctx, 0xFFFF) & gb_read8(ctx, 0xFF0F) & 0x1F)) {\n        ctx->halted = 0;\n        ctx->halt_bug = 1;')
    # An interrupt taken with the flag armed (EI while IME was already on, the interrupt pending at once): the dispatch switches IME off and the
    # armed EI must not switch it back on in the middle of the dispatch (a nested interrupt in the handler). On the console that EI does nothing.
    return replace_once(source, '        ctx->ime = 0; ctx->halted = 0; ctx->stop_mode_active = 0;\n        const uint16_t return_pc = ctx->pc;',
                        '        ctx->ime = 0; ctx->ime_pending = 0; ctx->halted = 0; ctx->stop_mode_active = 0;\n        const uint16_t return_pc = ctx->pc;')


def adapt_halt_mode3(source: str) -> str:
    """The halted fast-forward of gb_run_cycles (gb_halt_fast_forward_cycles in gbrt.c) jumps to the next PPU event in every mode but the
    pixel transfer, where it steps one M-cycle at a time because the end of the mode depends on the pixel FIFO (sprites, window,
    scroll). A game that waits for vertical blank in HALT therefore issues about 43 steps per line in mode 3 alone. The transfer
    ends when the 160th pixel has been pushed, at best one pixel per dot; the extra dots only come later. So the step may go up to one
    dot before that, rounded down to a four-cycle boundary: the dot where the mode ends, and the interrupt it may raise, are still
    reached by a four-cycle step, as before. Until the mode is published as 3, or with four pixels left or fewer, the step stays one
    M-cycle. tools/gameboy_halt_selftest.py compares it with plain four-cycle stepping, byte for byte, frame by frame."""
    return replace_once(source,
        '        /* Mode 3 ends on a dynamic FIFO event; advance only one CPU M-cycle. */\n'
        '        case PPU_MODE_DRAW: target = ppu->mode_cycles + 4u; break;\n',
        '        /* Mode 3 ends when the 160th pixel is pushed, at best one pixel per dot; sprites, the window and the scroll only add\n'
        '         * dots. Step to at most one dot before that, on a four-cycle boundary (the dot where the mode ends, and the interrupt\n'
        '         * it may raise, is still reached by a four-cycle step). Before the mode is published as 3, advance one CPU M-cycle. */\n'
        '        case PPU_MODE_DRAW: {\n'
        '            const uint32_t pixels_left = ppu->draw_x < GB_SCREEN_WIDTH ? (uint32_t)(GB_SCREEN_WIDTH - ppu->draw_x) : 0u;\n'
        '            target = ppu->mode_cycles + (ppu->visible_mode == PPU_MODE_DRAW && pixels_left > 4u ? pixels_left - 1u : 4u);\n'
        '            break;\n'
        '        }\n')


def adapt_unused_io_bits(source: str) -> str:
    """The pinned runtime returns the stored value for the registers it does not model, so a bit that is not wired reads back as it was
    written. On the original Game Boy such a bit reads 1: the serial control (bits 6 to 1), the timer control (bits 7 to 3), the
    unmapped registers $FF03 and $FF08-$FF0E, and, outside colour mode, the registers of the colour models ($FF4C, $FF4E, $FF50,
    $FF57-$FF67, $FF6D-$FF6F, $FF71, $FF78-$FF7F). Two anchors in the register read of gbrt.c: its last fall-through, which gets the masks
    above, and the branch of the colour palette ports $FF68-$FF6B, which the LCD code answers with the stored value and which now returns
    $FF outside colour mode before gb_sync. The joypad, DIV, IF, the LCD and the sound registers keep their own paths. The engine already
    reads $FF by itself outside colour mode at $FF4D, $FF4F, $FF51-$FF56, $FF6C, $FF70 and $FF72-$FF77 (gbrt.c:2691-2744). Mooneye's
    unused_hwio-GS proves it; boot_hwio goes past $FF03 with it and still stops at $FF26 (the sound state after the boot ROM)."""
    source = replace_once(source,
        '        if (addr >= 0xFF68 && addr <= 0xFF6B) {\n            gb_sync(ctx);\n            return ppu_read_register((GBPPU*)ctx->ppu, addr);',
        '        if (addr >= 0xFF68 && addr <= 0xFF6B) {\n            if (!gb_is_cgb_mode(ctx)) return 0xFF;\n            gb_sync(ctx);\n            return ppu_read_register((GBPPU*)ctx->ppu, addr);')
    return replace_once(source,
        '            return gb_audio_read(ctx, addr);\n        }\n        return ctx->io[addr - 0xFF00];\n    }\n    if (addr < 0xFFFF) return ctx->hram[addr - 0xFF80];',
        '            return gb_audio_read(ctx, addr);\n        }\n'
        '        if (addr == 0xFF02) return (uint8_t)(ctx->io[0x02] | (gb_is_cgb_hardware(ctx) ? 0x7Cu : 0x7Eu));\n'
        '        if (addr == 0xFF07) return (uint8_t)(ctx->io[0x07] | 0xF8u);\n'
        '        if (addr == 0xFF03 || (addr >= 0xFF08 && addr <= 0xFF0E)) return 0xFF;\n'
        '        if (!gb_is_cgb_mode(ctx) && (addr == 0xFF4C || addr == 0xFF4E || addr == 0xFF50 || (addr >= 0xFF57 && addr <= 0xFF67) ||\n'
        '                                     (addr >= 0xFF6D && addr <= 0xFF6F) || addr == 0xFF71 || addr >= 0xFF78)) {\n'
        '            return 0xFF;\n'
        '        }\n'
        '        return ctx->io[addr - 0xFF00];\n    }\n    if (addr < 0xFFFF) return ctx->hram[addr - 0xFF80];')


def adapt_boot_ppu_phase(source: str) -> str:
    """The pinned reset puts the LCD where the first revision of the console (DMG0) has it at the end of the boot ROM: line 145 in vertical
    blank. The original console in common use (DMG ABC) leaves it in vertical blank with LY already reading 0 (STAT $85, Pan Docs "Power Up
    Sequence"), that is in line 153 after its fourth dot, late in the frame. Mooneye's boot_hwio-dmgABCmgb reads LY and STAT at its first
    registers and constrains that phase to a window: it passes at the steps tried from 3,950 to 4,108 dots after the reset (line 153 from its dot 306
    to line 0 dot 8) and fails at 3,900 and below and at 4,150 and above. The step is 4,096 dots, inside the window and still in line 153 (dot 452,
    mode 1, LY reading 0); the exact dot within the window is not measured. The PPU is stepped in a DMG that skips the boot ROM, so every internal
    field comes out of its own state machine; no vertical-blank edge is crossed (the vertical blank began at line 144, behind), so no interrupt
    is raised. Only the PPU is stepped: the divider keeps its value, so the phase between DIV and the PPU is not measured."""
    return replace_once(source,
        '    if (ctx->ppu) {\n        ppu_reset((GBPPU*)ctx->ppu, ctx);\n    }\n}',
        '    if (ctx->ppu) {\n        ppu_reset((GBPPU*)ctx->ppu, ctx);\n'
        '        if (skip_bootrom && !gb_is_cgb_mode(ctx) && !gb_is_cgb_compat_mode(ctx)) {\n'
        '            ppu_tick((GBPPU*)ctx->ppu, ctx, 4096u);\n'
        '        }\n    }\n}')


def adapt_serial_phase(source: str) -> str:
    """A transfer with the internal clock shifts a bit at every falling edge of bit 8 of the divider (every 512 dots), so it ends after
    4,096 dots only when it starts on an edge; otherwise the first bit comes sooner by the phase of the divider. Mooneye's
    boot_sclk_align-dmgABCmgb measures that phase right after the boot ROM."""
    return replace_once(source,
        'ctx->serial_transfer.fast_clock ? 128u : 4096u;',
        'ctx->serial_transfer.fast_clock ? 128u : 4096u - (uint32_t)(ctx->div_counter & 0x1FFu);')


def adapt_ei_delay_interpreter(code: str) -> str:
    return replace_once(code, 'case 0xFB: ctx->ime_pending = 1; break; /* EI */',
                        'case 0xFB: ' + EI_ARM_ONCE + ' break; /* EI */')


def adapt_ei_delay_generated(project: Path) -> int:
    """The generated bodies store the same arming for every EI they translate; the same rule. Returns how many were changed."""
    changed = 0
    for path in sorted(project.glob('game_funcs_*.c')):
        source = path.read_text(encoding='utf-8').replace(EI_ARM_ONCE, EI_ARM)       # so that a second run changes nothing
        count = source.count(EI_ARM)
        if count:
            path.write_text(source.replace(EI_ARM, EI_ARM_ONCE), encoding='utf-8', newline='')
            changed += count
    return changed


def adapt_differential(project: Path) -> None:
    """Keep byte-exact checks while making their common equal case fast."""
    path = project / 'runtime/src/differential.c'
    source = path.read_text(encoding='utf-8')
    source = replace_once(source, '''    for (size_t i = 0; i < size; i++) {
        if (generated[i] != interpreted[i]) {
            snprintf(message, message_size,
                     "%s mismatch at offset 0x%zX: %02X != %02X",
                     name, i, generated[i], interpreted[i]);
            return false;
        }
    }

    return true;
}

static bool gb_diff_compare_ppu''', '''    // Validate every byte at every step. Locate the first mismatch only on failure.
    if (memcmp(generated, interpreted, size) == 0) {
        return true;
    }
    for (size_t i = 0; i < size; i++) {
        if (generated[i] != interpreted[i]) {
            snprintf(message, message_size,
                     "%s mismatch at offset 0x%zX: %02X != %02X",
                     name, i, generated[i], interpreted[i]);
            return false;
        }
    }

    return true;
}

static bool gb_diff_compare_ppu''')
    path.write_text(source, encoding='utf-8')


def adapt_generated_project(project: Path, storage_id: str, rom_sha256: str, title: str, halt_mode3_bound: bool = True) -> None:
    """`halt_mode3_bound=False` leaves the halted fast-forward as the pinned runtime has it: only tools/gameboy_halt_selftest.py asks for it,
    to compare the two."""
    # Shared player shell first (menus, filters, platform), then the machine.
    from .gameboy_host import adapt_shell
    adapt_shell(project, title)
    for source_name, destination in (
        ('embedded_resources.h', project / 'runtime/include/embedded_resources.h'),
        ('gb_ram_helpers.h', project / 'runtime/include/gb_ram_helpers.h'),
        ('gb_tick_fast.h', project / 'runtime/include/gb_tick_fast.h'),
        ('gb_frame_trace.h', project / 'runtime/include/gb_frame_trace.h'),
    ):
        copyfile(ASSETS / 'native' / source_name, destination)

    # Upstream flushes every cartridge with external RAM on exit, including
    # unchanged RAM. Track actual writes so a launch/quit stays file-free.
    header = project / "runtime/include/gbrt.h"
    source = header.read_text(encoding="utf-8")
    source = replace_once(source,
        'bool persistence_load_failed; /**< Invalid persisted data was rejected; automatic overwrite is suppressed */',
        'bool persistence_load_failed; /**< Invalid persisted data was rejected; automatic overwrite is suppressed */\n    bool eram_dirty; /**< Battery RAM changed since load/save; host-only state */\n    bool rtc_dirty; /**< RTC advanced or was written since load/save */\n'
        '    uint8_t rr_wisdom_tree; /**< Wisdom Tree mapper: the ROM is switched by 32 KiB, by the address of a write; derived from the ROM, host-only */')
    # Counters of the writable-code executors (rr_gb_try_ram_dispatch): host-only, outside every saved state.
    source = replace_once(source,
        '    uint64_t total_interpreter_cycles; /**< Total cycles executed in interpreter sessions */',
        '    uint64_t total_interpreter_cycles; /**< Total cycles executed in interpreter sessions */\n'
        '    uint64_t rr_ram_stub_instructions; /**< WRAM/HRAM instructions run one by one by the upstream RAM stub (host-only) */\n'
        '    uint64_t rr_ram_stub_cycles; /**< Guest cycles of those instructions */\n'
        '    uint64_t rr_ram_single_step_instructions; /**< WRAM/HRAM instructions run one by one by rr_gb_try_ram_instruction (host-only) */\n'
        '    uint64_t rr_ram_single_step_cycles; /**< Guest cycles of those instructions */\n'
        '    uint64_t rr_highmem_stub_instructions; /**< 0xFF00-0xFF7F instructions run one by one by the upstream high-memory stub (host-only) */\n'
        '    uint64_t rr_highmem_stub_cycles; /**< Guest cycles of those instructions */\n'
        '    uint64_t rr_helper_entries[4]; /**< Entries of the guarded helpers (store, copy, DMA page, interrupt-bracketed DMA), host-only */\n'
        '    uint64_t rr_helper_cycles[4]; /**< Guest cycles spent in those entries */')
    # `--frame-trace FILE` (native/gb_frame_trace.h): one line per completed frame, for the liveness record of the delivered file.
    source = replace_once(source, 'uint16_t gb_resolve_rom_bank(const GBContext* ctx, uint16_t addr);',
        'uint16_t gb_resolve_rom_bank(const GBContext* ctx, uint16_t addr);\n'
        'void rr_gb_frame_trace_open(const char* path); /**< Start the per-frame trace of a headless run (host-only) */\n'
        'void rr_gb_frame_trace(GBContext* ctx, uint64_t frame); /**< One line for the frame just completed (host-only) */')
    header.write_text(source, encoding="utf-8")

    runtime_cpu = project / "runtime/src/gbrt.c"
    source = runtime_cpu.read_text(encoding="utf-8")
    # The runtime's own functions (timed jumps, calls, returns, stack and bus accesses and the HALT loop of
    # gb_run_cycles, which issues most of the calls while a game waits for vblank) call gb_tick. gb_tick_fast.h runs the
    # ordinary case of gb_tick inline in those callers, with the same effects in the same order, and hands every other
    # case to the real gb_tick. The macro is off around the definition of gb_tick and around gb_handle_interrupts (four
    # ticks of a cold path, kept as real calls to limit the growth of the code), and back on for gb_run_cycles. It exists
    # only when the runtime is built without its performance counters, as the header itself does. The CGB HDMA stall of
    # gbrt.c stays a real call too. The generated sources keep calling the real gb_tick: inlining it into every body adds
    # about 400 bytes at each of thousands of call sites.
    source = replace_once(source, '#include "gbrt.h"\n#include "gbrt_data_mod.h"',
        '#include "gbrt.h"\n#include "gb_tick_fast.h"\n#include "gb_frame_trace.h"\n#include "gbrt_data_mod.h"')
    source = replace_once(source, '    if (ctx && ctx->callbacks.on_audio_sample) {\n        ctx->callbacks.on_audio_sample(ctx, l, r);',
        '    rr_gb_trace_sample(ctx, l, r);\n    if (ctx && ctx->callbacks.on_audio_sample) {\n        ctx->callbacks.on_audio_sample(ctx, l, r);')
    source = replace_once(source, 'void gb_tick(GBContext* ctx, uint32_t cycles) {\n    static uint32_t last_log = 0;',
        '#undef gb_tick\nvoid gb_tick(GBContext* ctx, uint32_t cycles) {\n    static uint32_t last_log = 0;')
    source = replace_once(source, 'uint32_t gb_run_cycles(GBContext* ctx, uint32_t max_cycles) {',
        '#ifndef GBRT_ENABLE_PERFORMANCE_COUNTERS\n#define gb_tick(ctx, cycles) rr_gb_tick((ctx), (cycles))\n#endif\n'
        'uint32_t gb_run_cycles(GBContext* ctx, uint32_t max_cycles) {')
    source = replace_once(source, 'gb_tick(ctx, ctx->cgb_double_speed ? 64u : 32u);',
        '(gb_tick)(ctx, ctx->cgb_double_speed ? 64u : 32u);')
    # With the LCD off there is no vblank, so no frame ever completed: a game that waits for a key with the screen off
    # (The Ren & Stimpy Show: Veediots!) stopped every headless probe and every frame-anchored input script, since the
    # frame counter and the script clock only advance at a completed frame. A frame lasts 70,224 cycles with the LCD
    # off as well; the picture is the last one, as the PPU keeps it. gb_tick_fast.h does the same in its copy of
    # gb_add_cycles.
    source = replace_once(source,
        '    if (ctx->lcd_off_active) {\n        ctx->frame_lcd_off_cycles += cycles;\n        ctx->total_lcd_off_cycles += cycles;\n    }\n}',
        '    if (ctx->lcd_off_active) {\n        ctx->frame_lcd_off_cycles += cycles;\n        ctx->total_lcd_off_cycles += cycles;\n'
        '        if (ctx->frame_cycles >= 70224u) ctx->frame_done = 1;\n    }\n}')
    source = replace_once(source,
        '''    /* Save RAM before destroying if available */
    if (ctx->eram && ctx->callbacks.save_battery_ram && !ctx->persistence_load_failed) {
        gb_context_save_ram(ctx);
    } else if (ctx->persistence_load_failed) {''',
        '''    /* No data folder on an unchanged launch; preserve actual battery/RTC changes. */
    if (!ctx->persistence_load_failed && ctx->rom && ctx->rom_size > 0x147u &&
        gb_cart_type_has_battery(ctx->rom[0x147])) {
        if (ctx->eram && ctx->eram_dirty && ctx->callbacks.save_battery_ram)
            gb_context_save_battery_snapshot(ctx, ctx->eram, ctx->eram_size);
        if (ctx->rtc_dirty && gb_cart_type_has_rtc(ctx->rom[0x147]) && ctx->callbacks.save_rtc_data)
            gb_context_save_rtc(ctx);
    } else if (ctx->persistence_load_failed) {''')
    source = replace_once(source,
        '''    if (!ctx || elapsed_seconds == 0) {
        return;
    }

    uint64_t total''',
        '''    if (!ctx || elapsed_seconds == 0) {
        return;
    }
    ctx->rtc_dirty = true;

    uint64_t total''')
    source = replace_once(source,
        '''        if (ctx->rtc_mode) {
            /* RTC Register Write */
            switch (ctx->rtc_reg) {''',
        '''        if (ctx->rtc_mode) {
            /* RTC Register Write */
            ctx->rtc_dirty = true;
            switch (ctx->rtc_reg) {''')
    source = replace_once(source,
        '''    while (ctx->rtc.last_time >= 4194304) { /* 1 second at 4.194304 MHz */
        ctx->rtc.last_time -= 4194304;''',
        '''    while (ctx->rtc.last_time >= 4194304) { /* 1 second at 4.194304 MHz */
        ctx->rtc.last_time -= 4194304;
        ctx->rtc_dirty = true;''')
    source = replace_once(source,
        'ctx->eram[(addr - 0xA000) & 0x1FF] = value & 0x0F;',
        'const size_t index = (addr - 0xA000) & 0x1FF;\n                const uint8_t next = value & 0x0F;\n                if (ctx->eram[index] != next) ctx->eram_dirty = true;\n                ctx->eram[index] = next;')
    source = replace_once(source,
        'ctx->eram[gb_eram_index(ctx, addr)] = value;',
        'const size_t index = gb_eram_index(ctx, addr);\n            if (ctx->eram[index] != value) ctx->eram_dirty = true;\n            ctx->eram[index] = value;')
    source = replace_once(source,
        'if (ctx->eram_size > 0) memcpy(ctx->eram, eram_data, ctx->eram_size);',
        'if (ctx->eram_size > 0) {\n        if (memcmp(ctx->eram, eram_data, ctx->eram_size) != 0) ctx->eram_dirty = true;\n        memcpy(ctx->eram, eram_data, ctx->eram_size);\n    }')
    source = replace_once(source, '    gbrt_restore_core_state(ctx, &core_state);',
        '    gbrt_restore_core_state(ctx, &core_state);\n    if (ctx->rom && ctx->rom_size > 0x147u && gb_cart_type_has_rtc(ctx->rom[0x147]))\n        ctx->rtc_dirty = true;')
    source = replace_once(source,
        '    return ram_result && rtc_result;\n}',
        '    if (ram_result && rtc_result) { ctx->eram_dirty = false; ctx->rtc_dirty = false; }\n    return ram_result && rtc_result;\n}')
    source = adapt_wisdom_tree(source)
    source = adapt_ei_delay(source)
    source = adapt_unused_io_bits(source)
    source = adapt_boot_ppu_phase(source)
    source = adapt_serial_phase(source)
    if halt_mode3_bound:
        source = adapt_halt_mode3(source)
    runtime_cpu.write_text(source, encoding="utf-8")

    # Capture only true interpreter instructions, after native RAM helpers have
    # declined them. Peek ordinary memory directly; never tick/read MMIO twice.
    interpreter = project / 'runtime/src/interpreter.c'
    code = interpreter.read_text(encoding='utf-8')
    code = '#include "runtime_feedback.h"\n' + code
    helper = '''
static void rr_gb_feedback(GBContext *ctx) {
    if(!rr_feedback_enabled())return;
    uint8_t bytes[4];uint16_t pc=ctx->pc,bank=gb_resolve_rom_bank(ctx,pc);
    unsigned length=0;
    for(unsigned n=0;n<4;++n) {
        uint16_t addr=(uint16_t)(pc+n);
        if(addr<0x8000) {
            size_t offset=(size_t)gb_resolve_rom_bank(ctx,addr)*0x4000+(addr&0x3fff);
            if(offset>=ctx->rom_size)break;bytes[n]=ctx->rom[offset];
        } else if(addr>=0xc000 && addr<0xd000)bytes[n]=ctx->wram[addr-0xc000];
        else if(addr>=0xd000 && addr<0xe000)bytes[n]=ctx->wram[ctx->wram_bank*0x1000u+addr-0xd000];
        else if(addr>=0xff80 && addr<0xffff)bytes[n]=ctx->hram[addr-0xff80];
        else break;
        ++length;
    }
    rr_feedback_note(RR_FB_GB,pc,bank,bytes,length);
}
'''
    code = replace_once(code, 'void gb_interpret(GBContext* ctx, uint16_t addr) {',
                        helper + '\nvoid gb_interpret(GBContext* ctx, uint16_t addr) {')
    code = replace_once(code, '        uint8_t opcode;\n        if (ctx->halt_bug)',
                        '        rr_gb_feedback(ctx);\n        uint8_t opcode;\n        if (ctx->halt_bug)')
    code = adapt_ei_delay_interpreter(code)
    interpreter.write_text(code, encoding='utf-8')
    adapt_ei_delay_generated(project)

    # Writable code keeps live byte guards, one instruction per dispatch and
    # the normal interrupt/frame safepoints. Unknown or modified RAM stays
    # observable through the original interpreter path.
    game = project / 'game.c'
    source = game.read_text(encoding='utf-8')
    source = replace_once(source, '#include "game_internal.h"',
                          '#include "game_internal.h"\n#include "gb_ram_helpers.h"')
    # Order: the guarded multi-instruction helpers, the upstream stub, then the
    # remaining single opcodes (rr_gb_try_ram_instruction); only what all of
    # them decline reaches the interpreter. The stub and the single opcodes run
    # one instruction at a time: rr_gb_try_ram_dispatch counts them, and the
    # report shows them apart from the interpreter.
    source = replace_once(source, 'if (gbrt_try_execute_ram_stub(ctx, addr)) {',
                          'if (rr_gb_try_ram_dispatch(ctx, addr)) {')
    # The generated dispatch also calls the upstream stub for code run from 0xFF00-0xFF7F (a per-opcode executor)
    # before that line; it is counted the same way. The HRAM stub (signature-matched OAM-DMA wait routine) is a
    # guarded helper like ours and stays uncounted. Inside an interpreter session the pinned interpreter calls the
    # stubs itself: those instructions are part of the session (one counted instruction per loop iteration).
    source = replace_once(source, 'if (gbrt_try_execute_highmem_stub(ctx, addr)) {',
                          'if (rr_gb_try_highmem_dispatch(ctx, addr)) {')
    source = replace_once(source, '        if (ctx->single_step_mode) break;\n    }\n}',
                          '        if (ctx->single_step_mode || gbrt_generated_safepoint(ctx)) break;\n    }\n}')
    game.write_text(source, encoding='utf-8')

    # Cross-body guest jumps/calls must not consume the host C stack. The
    # emitter has already set PC and performed the timed guest stack/bus work.
    # Yield to the outer ROM-PC dispatch loop; wrappers still enter their body.
    for generated in project.glob('game_funcs_*.c'):
        source = generated.read_text(encoding='utf-8')
        source = re.sub(r'\bfunc_[A-Za-z0-9_]+\(ctx\);',
                        'return; /* next native body via outer PC dispatch */', source)
        generated.write_text(source, encoding='utf-8')

    main = project / "game_main.c"
    source = main.read_text(encoding="utf-8")
    source = '#include "runtime_feedback.h"\n#include "embedded_resources.h"\n' + source
    source = replace_once(source, 'int main(int argc, char* argv[]) {', '''int main(int argc, char* argv[]) {
    for(int i=1;i<argc;++i)if(!strcmp(argv[i],"--credits")) {
        size_t length=0;const void *notice=rr_resource(102,&length);
        return notice && fwrite(notice,1,length,stdout)==length?0:1;
    }''')
    source = replace_once(source, '    GBContext* ctx = gb_context_create(&runtime_config);',
        '    rr_feedback_start(!headless_mode && !benchmark_mode);\n'
        '    GBContext* ctx = gb_context_create(&runtime_config);')
    source = diagnostic_limit_snapshot(source)
    source = adapt_frame_trace_main(source)
    # The counted one-by-one execution of writable code is printed with the interpreter summary, also when
    # no interpreter session happened (the probe reads this line in every case).
    source = replace_once(source, '''    fprintf(stderr,
            "[INTERP] Fallback inventory: sites=%u''', '''    fprintf(stderr,
            "[RR-RAM] ram_stub_instructions=%llu ram_stub_cycles=%llu ram_single_step_instructions=%llu ram_single_step_cycles=%llu "
            "highmem_stub_instructions=%llu highmem_stub_cycles=%llu\\n",
            (unsigned long long)ctx->rr_ram_stub_instructions, (unsigned long long)ctx->rr_ram_stub_cycles,
            (unsigned long long)ctx->rr_ram_single_step_instructions, (unsigned long long)ctx->rr_ram_single_step_cycles,
            (unsigned long long)ctx->rr_highmem_stub_instructions, (unsigned long long)ctx->rr_highmem_stub_cycles);
    fprintf(stderr,
            "[RR-HELPERS] store_entries=%llu store_cycles=%llu copy_entries=%llu copy_cycles=%llu "
            "dma_page_entries=%llu dma_page_cycles=%llu interrupt_dma_entries=%llu interrupt_dma_cycles=%llu\\n",
            (unsigned long long)ctx->rr_helper_entries[0], (unsigned long long)ctx->rr_helper_cycles[0],
            (unsigned long long)ctx->rr_helper_entries[1], (unsigned long long)ctx->rr_helper_cycles[1],
            (unsigned long long)ctx->rr_helper_entries[2], (unsigned long long)ctx->rr_helper_cycles[2],
            (unsigned long long)ctx->rr_helper_entries[3], (unsigned long long)ctx->rr_helper_cycles[3]);
    fprintf(stderr,
            "[INTERP] Fallback inventory: sites=%u''')
    source = replace_once(source, '''        while (!ctx->frame_done) {
            bool smooth_lcd_transitions''',
        '''        while (!ctx->frame_done) {
            if (!gb_platform_wait_while_menu(ctx)) { running = false; break; }
            bool smooth_lcd_transitions''')
    source = replace_once(source, 'const char* model_override = "auto";',
                          'const char* model_override = "dmg";')
    source = replace_once(source, '''    if (persistence_dir && !gb_platform_set_persistence_dir(persistence_dir)) {''',
        f'''    char rr_save_dir[2048] = {{0}};
#ifdef GB_HAS_SDL2
    if (!persistence_dir) {{
        char* rr_base = SDL_GetBasePath();
        if (rr_base) {{
            snprintf(rr_save_dir, sizeof(rr_save_dir), "%sdatas/games/{storage_id}", rr_base);
            SDL_free(rr_base);
            persistence_dir = rr_save_dir;
        }}
    }}
#endif
    if (persistence_dir && !gb_platform_set_persistence_dir(persistence_dir)) {{''')
    source = replace_once(source, 'gb_context_set_save_id(ctx, "game");',
                          f'gb_context_set_save_id(ctx, "{storage_id}");')
    source += (f'\n#ifdef _WIN32\n'
               f'__declspec(dllexport) const char retrorecomp_marker[] = "[Retro-Recomp]";\n'
               f'__declspec(dllexport) const char retrorecomp_rom_sha256[] = "{rom_sha256}";\n'
               f'#endif\n')
    main.write_text(source, encoding="utf-8")

    cmake = project / "CMakeLists.txt"
    source = cmake.read_text(encoding="utf-8")
    source = replace_once(source, 'project(game C CXX)',
                          'project(game C CXX)\nif(MSVC)\n    set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")\nendif()')
    source = replace_once(source, '''    ${GBRT_DIR}/src/platform_sdl.cpp
)''',
        '''    ${GBRT_DIR}/src/platform_sdl.cpp
    ${GBRT_DIR}/src/retro_menu.c
    ${GBRT_DIR}/src/platform_io.c
)''')
    source += '\nif(WIN32)\n    target_link_libraries(gbrt PUBLIC gdi32)\nendif()\n'
    # The kit's shell in gbrt reads the resources (rrhk_main.c): they go with it, so that every program that links
    # gbrt (the game, the self-tests' checks) finds rr_resource.
    source += '\nif(NOT WIN32)\n    enable_language(ASM)\n    target_sources(gbrt PRIVATE embedded_resources.c embedded_resources.S)\nendif()\n'
    source += f'target_compile_definitions(gbrt PRIVATE [[RR_RECOMP_VERSION="{__version__}"]])\n'
    source += '\n# RetroRecomp Windows identity and box-art icon.\n'
    source += 'if(WIN32)\n    target_sources(game PRIVATE game_resources.rc)\nendif()\n'
    source += 'if(WIN32)\n    set_target_properties(game PROPERTIES WIN32_EXECUTABLE TRUE)\nendif()\n'
    # MSBuild's project-level --parallel does not parallelize these large C
    # translation units. /MP uses the bounded job count passed by the converter.
    source += ('if(MSVC AND GBRECOMP_GENERATED_COMPILE_JOBS GREATER 1)\n'
               '    target_compile_options(game PRIVATE "/MP${GBRECOMP_GENERATED_COMPILE_JOBS}")\n'
               'endif()\n')
    from .gameboy_host import kit_cmake
    cmake.write_text(kit_cmake(source), encoding="utf-8")   # the host kit's shell, beside the platform layer
    from .feedback import stage
    stage(project, 'gb', rom_sha256, target='gbrt')
    adapt_input_refresh_hook(project)
    from .gameboy_hardware import adapt_hardware
    adapt_hardware(project)
    adapt_differential(project)
    deduplicate_entry_trace(project)


def adapt_input_refresh_hook(project: Path) -> None:
    """Guest side of the host's low-latency input refresh (the Game Boy adapter, rrhk_gb.inc):
    a JOYP read with no scripted pad asks the host for fresh input."""
    path = project / 'runtime/include/gbrt.h'
    source = path.read_text(encoding='utf-8')
    source = replace_once(source, '''} GBPlatformCallbacks;''', '''    /* Host-only input refresh; absent from serialized guest state. */
    void (*refresh_input)(GBContext* ctx);
} GBPlatformCallbacks;''')
    path.write_text(source, encoding='utf-8')
    path = project / 'runtime/src/gbrt.c'
    source = path.read_text(encoding='utf-8')
    source = replace_once(source, '''        if (addr == 0xFF00) {
            const GBJoypadState* joypad''', '''        if (addr == 0xFF00) {
            if (!ctx->joypad && ctx->callbacks.refresh_input) ctx->callbacks.refresh_input(ctx);
            const GBJoypadState* joypad''')
    path.write_text(source, encoding='utf-8')


def deduplicate_entry_trace(project: Path) -> None:
    """An entry set needs each (bank, PC) once, not once per loop iteration.

    A bounded bitset is allocated only during conversion diagnostics. No
    instruction, fallback counter, validation step or game timing is skipped.
    """
    header = project / 'runtime/include/gbrt.h'
    source = header.read_text(encoding='utf-8')
    source = replace_once(source, '    bool trace_entries_enabled;',
                          '    bool trace_entries_enabled;\n    uint8_t* rr_trace_seen;')
    header.write_text(source, encoding='utf-8')
    runtime = project / 'runtime/src/gbrt.c'
    source = runtime.read_text(encoding='utf-8')
    source = replace_once(source, '    if (ctx->trace_file) fclose((FILE*)ctx->trace_file);',
                          '    if (ctx->trace_file) fclose((FILE*)ctx->trace_file);\n    free(ctx->rr_trace_seen);')
    source = replace_once(source, '''    if (ctx->trace_entries_enabled && ctx->trace_file) {
        fprintf((FILE*)ctx->trace_file, "%d:%04x\\n", (int)bank, (int)addr);
    }''', '''    if (ctx->trace_entries_enabled && ctx->trace_file) {
        /* Complete unique entry set, including writable addresses. A failed
           allocation preserves the original unfiltered diagnostic behavior. */
        if (bank < 512u) {
            if (!ctx->rr_trace_seen) ctx->rr_trace_seen = (uint8_t*)calloc(512u * 8192u, 1);
            if (ctx->rr_trace_seen) {
                const size_t index = (size_t)bank * 8192u + (addr >> 3);
                const uint8_t mask = (uint8_t)(1u << (addr & 7));
                if (ctx->rr_trace_seen[index] & mask) return;
                ctx->rr_trace_seen[index] |= mask;
            }
        }
        fprintf((FILE*)ctx->trace_file, "%d:%04x\\n", (int)bank, (int)addr);
    }''')
    runtime.write_text(source, encoding='utf-8')


def adapt_frame_trace_main(source: str) -> str:
    """`--frame-trace FILE` in the generated main: one line per completed frame (native/gb_frame_trace.h), in both loops."""
    source = replace_once(source, '        } else if (strcmp(argv[i], "--dump-state") == 0 && i + 1 < argc) {',
        '        } else if (strcmp(argv[i], "--frame-trace") == 0 && i + 1 < argc) {\n'
        '            rr_gb_frame_trace_open(argv[++i]);\n'
        '        } else if (strcmp(argv[i], "--dump-state") == 0 && i + 1 < argc) {')
    anchor = '            frame_index++;\n#ifdef GBRT_ENABLE_PORT_MODULE'
    if source.count(anchor) != 2:   # the benchmark loop and the windowed loop
        raise ValueError(f'Unexpected frame loops in the generated main: {source.count(anchor)} marks.')
    return source.replace(anchor, '            frame_index++;\n            rr_gb_frame_trace(ctx, frame_index);\n#ifdef GBRT_ENABLE_PORT_MODULE')


def diagnostic_limit_snapshot(source: str) -> str:
    """Keep a requested snapshot when a hotspot-report probe hits --limit."""
    source = replace_once(source, 'static const GBContext* gbrt_interpreter_summary_ctx = NULL;',
        'static const char* rr_limit_state_path = NULL;\nstatic const GBContext* gbrt_interpreter_summary_ctx = NULL;')
    source = replace_once(source,
        '    gbrt_print_interpreter_summary(gbrt_interpreter_summary_ctx, gbrt_interpreter_summary_limit);',
        '    if (rr_limit_state_path) gb_context_write_state_json(gbrt_interpreter_summary_ctx, rr_limit_state_path);\n'
        '    gbrt_print_interpreter_summary(gbrt_interpreter_summary_ctx, gbrt_interpreter_summary_limit);')
    return replace_once(source, '            state_dump_file = argv[++i];',
        '            state_dump_file = argv[++i];\n            rr_limit_state_path = state_dump_file;')
