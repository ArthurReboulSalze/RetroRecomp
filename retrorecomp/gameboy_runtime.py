"""Apply small, checked RetroRecomp adaptations to a generated GB project.

The pinned upstream checkout is never edited. Changes live in the private
per-game build and fail if an upstream source marker changes.
"""
from __future__ import annotations

import re
from pathlib import Path
from shutil import copyfile

from .core import replace_once
from .paths import ASSETS
from . import __version__


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


def adapt_generated_project(project: Path, storage_id: str, rom_sha256: str, title: str) -> None:
    # Shared player shell first (menus, filters, platform), then the machine.
    from .gameboy_host import adapt_shell
    adapt_shell(project, title)
    for source_name, destination in (
        ('embedded_resources.h', project / 'runtime/include/embedded_resources.h'),
        ('gb_ram_helpers.h', project / 'runtime/include/gb_ram_helpers.h'),
        ('gb_tick_fast.h', project / 'runtime/include/gb_tick_fast.h'),
    ):
        copyfile(ASSETS / 'native' / source_name, destination)

    # Upstream flushes every cartridge with external RAM on exit, including
    # unchanged RAM. Track actual writes so a launch/quit stays file-free.
    header = project / "runtime/include/gbrt.h"
    source = header.read_text(encoding="utf-8")
    source = replace_once(source,
        'bool persistence_load_failed; /**< Invalid persisted data was rejected; automatic overwrite is suppressed */',
        'bool persistence_load_failed; /**< Invalid persisted data was rejected; automatic overwrite is suppressed */\n    bool eram_dirty; /**< Battery RAM changed since load/save; host-only state */\n    bool rtc_dirty; /**< RTC advanced or was written since load/save */')
    # Counters of the writable-code executors (rr_gb_try_ram_dispatch): host-only, outside every saved state.
    source = replace_once(source,
        '    uint64_t total_interpreter_cycles; /**< Total cycles executed in interpreter sessions */',
        '    uint64_t total_interpreter_cycles; /**< Total cycles executed in interpreter sessions */\n'
        '    uint64_t rr_ram_stub_instructions; /**< WRAM/HRAM instructions run one by one by the upstream RAM stub (host-only) */\n'
        '    uint64_t rr_ram_stub_cycles; /**< Guest cycles of those instructions */\n'
        '    uint64_t rr_ram_single_step_instructions; /**< WRAM/HRAM instructions run one by one by rr_gb_try_ram_instruction (host-only) */\n'
        '    uint64_t rr_ram_single_step_cycles; /**< Guest cycles of those instructions */\n'
        '    uint64_t rr_highmem_stub_instructions; /**< 0xFF00-0xFF7F instructions run one by one by the upstream high-memory stub (host-only) */\n'
        '    uint64_t rr_highmem_stub_cycles; /**< Guest cycles of those instructions */')
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
        '#include "gbrt.h"\n#include "gb_tick_fast.h"\n#include "gbrt_data_mod.h"')
    source = replace_once(source, 'void gb_tick(GBContext* ctx, uint32_t cycles) {\n    static uint32_t last_log = 0;',
        '#undef gb_tick\nvoid gb_tick(GBContext* ctx, uint32_t cycles) {\n    static uint32_t last_log = 0;')
    source = replace_once(source, 'uint32_t gb_run_cycles(GBContext* ctx, uint32_t max_cycles) {',
        '#ifndef GBRT_ENABLE_PERFORMANCE_COUNTERS\n#define gb_tick(ctx, cycles) rr_gb_tick((ctx), (cycles))\n#endif\n'
        'uint32_t gb_run_cycles(GBContext* ctx, uint32_t max_cycles) {')
    source = replace_once(source, 'gb_tick(ctx, ctx->cgb_double_speed ? 64u : 32u);',
        '(gb_tick)(ctx, ctx->cgb_double_speed ? 64u : 32u);')
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
    interpreter.write_text(code, encoding='utf-8')

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
