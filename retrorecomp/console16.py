"""ROM-specific 16-bit integration proofs, with pinned offline build inputs."""
from __future__ import annotations
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import time

from .paths import ROOT, ASSETS
from .platforms import build_executable, cmake_target_args, build_jobs, sdl_install, sdl_library
from .toolchain import active as active_toolchain, describe as toolchain_description
from .conversion_common import (check_exit, check_run_budget, convert_single, pinned_checkout, probe_environment,
                                resolve_scan_level, spawn)
from .core import ConversionError, run, serialized_setup, toolchain
from .cartridge16 import read_megadrive_rom, read_snes_rom
from . import __version__, timings
from .library import atomic_json
from .report_schema import write_report
from .snes_chips import device_entry
from . import hostkit, megadrive, supernintendo, guns16, megadrive_sram, megadrive_memory, megadrive_cart, snes_cart

REPOSITORIES = {
    'md': ('mstan/segagenesisrecomp', '00c60bc855a7998f92e5614585d52bca8fffcaf2', 'segagenesisrecomp'),
    'snes': ('RetroPortingToolKit/snesrecomp', 'a00df26a87831113fec91b9225bf16b049d40775', 'snesrecomp'),
}
SUPPORTED_SYSTEMS = ('md', 'snes')
# Later pseudo-random routes may continue from the saved end state of the
# previous one. Off: measured on 23 October 2026 (Sonic, Donkey Kong Country)
# without any new opcode variant, because the routes do not progress past the
# first screen; the chained second route then wastes its budget at the title.
CHAIN_LONG_ROUTES = False
MD_AUDIO_FIELDS = ('fm_samples', 'fm_nonzero', 'fm_peak', 'fm_hash', 'fm_active_frames',
                   'psg_samples', 'psg_nonzero', 'psg_peak', 'psg_hash', 'psg_active_frames',
                   'z80_pc', 'z80_slice_cycles', 'z80_ram_hash', 'z80_cpu_hash', 'ym_timer_hash')
MD_SRAM_FIELDS = megadrive_sram.REPORT_FIELDS + megadrive_cart.REPORT_FIELDS


def conversion_rom(path: Path, system_id: str, standard_override: str | None = None):
    """Check cartridge hardware, not membership in the regression catalogue."""
    if system_id not in SUPPORTED_SYSTEMS:
        raise ConversionError('Unknown 16-bit console profile.')
    rom = (read_megadrive_rom if system_id == 'md' else read_snes_rom)(path)
    adapter = megadrive if system_id == 'md' else supernintendo
    adapter.validate_cartridge(rom)
    adapter.video_standard(rom, standard_override)
    adapter.profile_for(rom)
    if system_id == 'md':
        megadrive.vectors(rom)
    return rom


@serialized_setup
def dependencies16(system_id: str, emit):
    from .platforms import require_backend
    require_backend(system_id)
    cmake, generator = toolchain()
    sdl = sdl_install()
    if not (sdl / sdl_library()).is_file():
        from .core import dependencies
        _, sdl, cmake, generator = dependencies(emit)
    repo, revision, directory = REPOSITORIES[system_id]
    checkout = ROOT / '.deps' / directory

    def git(*arguments, **options):
        return run(['git', *arguments], cwd=checkout, **options)

    def clone():
        emit(f'Downloading pinned {repo} sources…')
        run(['git', 'clone', '--no-checkout', f'https://github.com/{repo}.git', checkout], timeout=600)

    def pin():
        git('fetch', '--depth', '1', 'origin', revision, timeout=600)
        git('checkout', '--detach', revision)
    # A --no-checkout clone has an empty index/worktree, which Git reports as staged deletions. Populate our new
    # cache before the tracked-edit guard; never reset an existing source checkout.
    pinned_checkout(checkout, revision, git, present=(checkout / '.git').exists(), clone=clone, fill=pin,
                    moved=lambda head: pin(),
                    dirty=lambda: ConversionError(f'Dependency checkout has tracked edits: {checkout}'), dirty_first=True)
    engine = checkout
    if system_id == 'md':
        run(['git', 'submodule', 'update', '--init', '--depth', '1',
             'external/m68k-recomp-core', 'external/rbengine', 'external/z80-recomp-core'], cwd=engine, timeout=600)
        build = ROOT / '.build/megadrive-compiler'
        compiler = build_executable(build,'GenesisRecomp')
        if not compiler.is_file():
            run([cmake, '-S', engine / 'recompiler', '-B', build, '-G', generator, *cmake_target_args()], log=build / 'configure.log')
            run([cmake, '--build', build, '--config', 'Release', '--parallel', build_jobs()], log=build / 'build.log')
    else:
        compiler = None   # the Super Nintendo analysis runs inside the converter
    return engine, compiler, sdl, cmake, generator


def _write_build(project: Path, engine: Path, system_id: str, title: str, rom) -> None:
    shutil.copy2(ASSETS / 'native/console16_video.h', project / 'console16_video.h')
    for name in ('retro_console16.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h', 'console16_main.c', 'console16_state.c', 'console16_state.h', 'platform_io.c', 'platform_io.h', 'embedded_resources.h', 'retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc', 'retro_keyboard.h', 'scanlines.h', 'scanline_sdl.h', 'xbr_filter.h', 'xbr_sdl.h', 'scale2x.h', 'planar_rows.h', 'display_settings.h', 'gun16.h', 'gun16.c', f'{system_id}_backend.c'):
        shutil.copy2(ASSETS / 'native' / name, project / name)
    hostkit.stage(project, system_id)
    native = project / 'native'
    native.mkdir(exist_ok=True)
    prefix = engine.as_posix()
    common = '''cmake_minimum_required(VERSION 3.20)
project(RetroRecomp16 LANGUAGES C CXX)
if(WIN32)
  enable_language(RC)
  set(RESOURCE_SOURCES game_resources.rc)
else()
  enable_language(ASM)
  set(RESOURCE_SOURCES embedded_resources.c embedded_resources.S)
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 REQUIRED)
'''
    if system_id == 'md':
        # Private headers and sources must agree on the expanded, pointer-free
        from . import megadrive_fifo, megadrive_dma, megadrive_read
        # cartridge RAM image. Upstream includes resolve beside their source.
        runtime = project / 'engine'
        shutil.copytree(engine / 'runner', runtime / 'runner', dirs_exist_ok=True)
        bus_header = runtime / 'runner/video/genesis_bus.h'
        bus_header.write_text(megadrive_sram.bus_header(bus_header.read_text(encoding='utf-8')), encoding='utf-8')
        vdp_header = runtime / 'runner/video/genesis_vdp.h'
        vdp_header.write_text(megadrive_read.header(megadrive_dma.header(megadrive_fifo.header(vdp_header.read_text(encoding='utf-8')))), encoding='utf-8')
        rollback = runtime / 'runner/rb_state.c'
        rollback.write_text(megadrive_read.snapshot(megadrive_dma.snapshot(megadrive_fifo.snapshot(megadrive_sram.snapshot_source(rollback.read_text(encoding='utf-8'))))), encoding='utf-8')
        runner = (runtime / 'runner').as_posix()
        for name in ('md_battery.h', 'md_battery.c', 'md_eeprom.h', 'md_cart.h', 'md_cart.inc'):
            shutil.copy2(ASSETS / 'native' / name, project / name)
        shutil.copy2(ASSETS / 'native/md_ym_timers.h', project / 'md_ym_timers.h')
        shutil.copy2(ASSETS / 'native/md_timing.h', project / 'md_timing.h')
        for name in ('md_vdp_fifo.h', 'md_vdp_fifo.inc', 'md_vdp_dma.h', 'md_vdp_dma.inc', 'md_vdp_read.h', 'md_vdp_read.inc', 'md_bus_scheduler.h', 'md_z80_bus.inc', 'md_vdp_pixels.inc'):
            shutil.copy2(ASSETS / 'native' / name, project / name)
        from .megadrive_runtime import timing_source, timing_vdp, raster_machine
        from . import megadrive_z80
        rom = read_megadrive_rom(project / 'cartridge.bin')
        megadrive_z80.generate(project, engine, megadrive_z80.read_variants(rom))
        for name in ('md_z80_native.h', 'md_z80_runtime.c'):
            shutil.copy2(ASSETS / 'native' / name, project / name)
        (native / 'z80_reference.c').write_text(megadrive_z80.adapt_reference(
            (engine / 'runner/external/superzazu/z80.c').read_text(encoding='utf-8')), encoding='utf-8')
        step_aot = '#define RR_MD_STEP_AOT 1' in (project / 'retro_md_game.h').read_text(encoding='utf-8')
        if step_aot:
            from .megadrive_bus import fiber as md_fiber
            fiber_path=runtime/'runner/fiber_compat.c'
            fiber_path.write_text(md_fiber(fiber_path.read_text(encoding='utf-8')),encoding='utf-8')
            for name in ('md_native_steps.h', 'm68000_state_helpers.h', 'md_exception_decode.h', 'md_step_dispatch.c', 'md_prefetch.h', 'md_prefetch.inc'):
                shutil.copy2(ASSETS / 'native' / name, project / name)
        # Two host-only adaptations in private source copies. Never edit the
        # dependency checkout: count exact interpreter opcodes; remove legacy
        # sidecar deletion performed at game startup.
        glue = (engine / 'runner/glue.c').read_text(encoding='utf-8')
        glue = megadrive_memory.runtime_source(glue, 'glue')
        glue = timing_source(glue, 'glue')
        start = glue.index('    {\n        extern const char *exe_relative', glue.index('void glue_init('))
        end = glue.index('\n    }', start) + len('\n    }')
        glue = glue[:start] + glue[end:]
        glue = glue.replace('#include "game_spec.h"',
            '#include "game_spec.h"\n#include "retro_md_game.h"\nextern void rr16_note_fault(void);', 1)
        glue = glue.replace('g_cpu = floor_cpu_checkpoint;',
                            'g_cpu = floor_cpu_checkpoint; rr16_note_fault();')
        glue = glue.replace('if (st != M68KI_OK) {', 'if (st != M68KI_OK) { rr16_note_fault();', 1)
        glue = glue.replace('    fprintf(stderr, "[GAME] %s entry point returned unexpectedly!',
                            '    rr16_note_fault();\n    fprintf(stderr, "[GAME] %s entry point returned unexpectedly!', 1)
        if step_aot:
            from .megadrive_codegen import adapt_irq_glue
            glue = adapt_irq_glue(glue)
            from .gun16_runtime import md_glue
            glue = md_glue(glue)
            glue = glue.replace('    if (genesis_force_interp()) {\n        uint32_t entry',
                '    if (genesis_force_interp() || RR_MD_STEP_AOT) {\n        uint32_t entry', 1)
            glue = glue.replace('        /* NOTE: no per-instruction check_cycle_budget()',
                '        check_cycle_budget();\n        /* NOTE: legacy function-AOT has no per-instruction check_cycle_budget()', 1)
            from .console16_state import md_glue as state_glue
            glue = state_glue(glue)
            glue = megadrive_dma.glue(glue)
            from . import megadrive_bus
            glue = megadrive_bus.glue(glue)
        (native / 'glue.c').write_text(glue, encoding='utf-8')
        interp = (engine / 'runner/m68k_interp.c').read_text(encoding='utf-8')
        if not step_aot:
            interp = megadrive_memory.runtime_source(interp, 'interpreter')
        interp = interp.replace('static void cov_mark(uint32_t pc) {',
            'extern void rr16_note_interpreted(void);\nstatic void cov_mark(uint32_t pc) {\n    rr16_note_interpreted();', 1)
        if step_aot:
            from .megadrive_codegen import adapt_interpreter, adapt_cpu_snapshot
            interp = adapt_interpreter(interp)
            shutil.copy2(ASSETS / 'native/md_portable_state.inc', project / 'md_portable_state.inc')
            (native / 'rb_state.c').write_text(adapt_cpu_snapshot(
                megadrive_read.snapshot(megadrive_dma.snapshot(megadrive_fifo.snapshot(megadrive_sram.snapshot_source((engine / 'runner/rb_state.c').read_text(encoding='utf-8')))))) +
                '\n#include "md_portable_state.inc"\n', encoding='utf-8')
            from .gun16_runtime import md_interpreter
            interp = md_interpreter(interp)
        (native / 'm68k_interp.c').write_text(interp, encoding='utf-8')
        audio = (engine / 'runner/audio.c').read_text(encoding='utf-8')
        audio = audio.replace('want.samples  = 1024;', 'want.samples  = 512;')
        audio = audio.replace('cfg.preroll_ms     = 200.0;',
            'cfg.target_ms = 25.0; cfg.em_low_ms = 5.0; cfg.em_high_ms = 80.0;\n    cfg.preroll_ms = 25.0;')
        audio = audio.replace('a ~200 ms boot pre-roll', 'a 25 ms boot pre-roll')
        from .megadrive_audio import output
        audio = output(audio)
        (native / 'audio.c').write_text(audio, encoding='utf-8')
        from .megadrive_audio import bridge
        (native / 'recomp_audio_drc.h').write_text(bridge(
            (engine / 'runner/recomp_audio_drc.h').read_text(encoding='utf-8')), encoding='utf-8')
        for name in ('md_audio_loop.inc', 'md_audio_resample.inc', 'md_audio_mix.h', 'audio_cushion.h'):
            shutil.copy2(ASSETS / 'native' / name, native / name)
        sources = ['fiber_compat.c', 'crash_report.c', 'chip_trace.c', 'cmd_server_stub.c',
                   *([] if step_aot else ['rb_state.c']),
                   'cosim_state.c', 'cosim_cycles.c', 'audio/event_queue.c',
                   'audio/mixer.c', 'audio/observability.c', 'audio/audio_shadow.c',
                   'audio/fm_shadow.cpp', 'video/color_lut.c']
        from .gun16_runtime import md_bus, md_vdp, md_machine
        from .megadrive_runtime import ym_bus
        for name, adapt in (('genesis_bus', lambda s: megadrive_sram.bus_source(ym_bus(md_bus(s)))),
                            ('genesis_vdp', md_vdp), ('genesis_machine', md_machine)):
            text = adapt((engine / f'runner/video/{name}.c').read_text(encoding='utf-8'))
            if name == 'genesis_machine':
                text = raster_machine(text)
            if name == 'genesis_bus':
                text = megadrive_memory.runtime_source(text, 'bus')
                text = megadrive_fifo.bus(text)
                from . import megadrive_bus
                text = megadrive_bus.bus(text)
                text = megadrive_cart.bus(text)
            text = (timing_vdp(text) if name == 'genesis_vdp' else
                    timing_source(text, 'machine' if name == 'genesis_machine' else 'bus'))
            if name == 'genesis_bus':
                text = megadrive_bus.main_access(text)
            if name == 'genesis_machine':
                text = megadrive_sram.machine_source(text)
                text = megadrive_fifo.machine(text)
                text = megadrive_dma.machine(text)
                text = megadrive_read.machine(text)
                from .gun16_runtime import replace
                text = '#include "md_z80_native.h"\n' + replace(text,
                    '        z80_step(&m->z80);', '        rr_md_z80_step(&m->z80);')
                text = replace(text, '        m->bus.z80_reset_pending = 0;',
                    '        rr_md_z80_capture_driver();\n        m->bus.z80_reset_pending = 0;')
                text = megadrive_bus.machine(text)
                text = megadrive_cart.machine(text)
                from .megadrive_runtime import host_timing
                text = host_timing(text)
            if name == 'genesis_vdp':
                text = megadrive_fifo.vdp(text)
                text = megadrive_dma.vdp(text)
                text = megadrive_read.vdp(text)
            (native / f'{name}.c').write_text(text, encoding='utf-8')
        for path, component in (('sim_step.c', 'sim'), ('audio/ym2612_ymfm.cpp', 'fm'),
                                ('audio/sn76489.c', 'psg')):
            target = native / Path(path).name
            target.write_text(timing_source((engine / 'runner' / path).read_text(encoding='utf-8'), component),
                              encoding='utf-8')
        sources += [f'external/ymfm/src/{name}.cpp' for name in ('ymfm_opn', 'ymfm_ssg', 'ymfm_adpcm', 'ymfm_pcm')]
        source_text = '\n'.join(f'  "{runner}/{source}"' for source in sources)
        generated_glob = ('"steps/*.c" "generated/*_layout.c"' if step_aot else
                          '"generated/*_part*.c" "generated/*_dispatch.c" "generated/*_layout.c"')
        step_sources = 'md_step_dispatch.c native/rb_state.c' if step_aot else ''
        common += f'''file(GLOB GENERATED CONFIGURE_DEPENDS {generated_glob})
add_executable(game WIN32 console16_main.c {' '.join(hostkit.sources(system_id))} retro_menu.c gun16.c md_backend.c md_battery.c
  native/glue.c native/m68k_interp.c native/audio.c native/genesis_bus.c native/genesis_vdp.c
  native/genesis_machine.c native/z80_reference.c md_z80_runtime.c md_z80_generated.c
  native/sim_step.c native/ym2612_ymfm.cpp native/sn76489.c
  ${{RESOURCE_SOURCES}} {step_sources} ${{GENERATED}}
{source_text}
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(game PRIVATE . "{runner}" "{runner}/include"
  "{runner}/video" "{runner}/audio" "{runner}/external/superzazu" "{runner}/external/clowncommon"
  "{runner}/external/ymfm/src" "{prefix}/recompiler/src" "{prefix}/external/m68k-recomp-core/src")
target_compile_definitions(game PRIVATE RR16_MD=1 OWN_BACKEND=1 ENABLE_RECOMPILED_CODE=1 INCLUDE_GENERATED_CODE=1 GENESIS_BATCHED_PLANES=1)
# Both guest CPU fibers stay on the one emulation thread (fiber_compat already
# uses plain static current/thread pointers). Avoid migration-safe TLS lookups.
set_property(SOURCE "{runner}/fiber_compat.c" APPEND PROPERTY COMPILE_DEFINITIONS MCO_NO_MULTITHREAD)
set_property(SOURCE native/genesis_machine.c APPEND PROPERTY COMPILE_DEFINITIONS RR_MD_ENGINE_TIMING=1)
if(MSVC)
  target_link_options(game PRIVATE /CETCOMPAT:NO)
endif()
'''
    else:
        from .snes_codegen import generate, adapt_core, adapt_bridge, adapt_frame_driver
        from .cartridge16 import read_snes_rom
        rom = read_snes_rom(project / 'cartridge.sfc')
        generate(engine, project, rom)
        shutil.copy2(ASSETS / 'native/snes_native_steps.h', project / 'snes_native_steps.h')
        from . import snes_spc
        snes_spc.generate(engine, project, rom)
        for name in ('snes_spc_native.h', 'snes_spc_runtime.c'):
            shutil.copy2(ASSETS / 'native' / name, project / name)
        from .snes_cart import adapt_cart, adapt_loader, adapt_cpu
        for name in ('snes_cart.h', 'snes_battery.h', 'snes_battery.c'):
            shutil.copy2(ASSETS / 'native' / name, project / name)
        (project / 'variables.h').write_text('/* No foreign game RAM aliases. */\n', encoding='ascii')
        # Upstream uses one GCC alignment annotation in its PPU header.
        # Preserve the required alignment on MSVC in a private runtime copy.
        staged = project / 'engine'
        for directory in ('runner', 'third_party'):
            shutil.copytree(engine / directory, staged / directory, dirs_exist_ok=True)
        cpu_bus=staged / 'runner/src/cpu_state.c'
        cpu_bus.write_text(adapt_cpu(cpu_bus.read_text(encoding='utf-8')),encoding='utf-8')
        for name, adapt in (('cart', adapt_cart), ('snes_other', adapt_loader)):
            path = staged / f'runner/src/snes/{name}.c'
            path.write_text(adapt(path.read_text(encoding='utf-8')), encoding='utf-8')
        (staged / 'runner/src/snes/interp816.c').write_text(
            adapt_core((engine / 'runner/src/snes/interp816.c').read_text(encoding='utf-8')),
            encoding='utf-8')
        (staged / 'runner/src/snes/interp_bridge.c').write_text(
            adapt_bridge((engine / 'runner/src/snes/interp_bridge.c').read_text(encoding='utf-8')),
            encoding='utf-8')
        (staged / 'runner/src/beam_frame_driver.c').write_text(
            adapt_frame_driver((engine / 'runner/src/beam_frame_driver.c').read_text(encoding='utf-8')),
            encoding='utf-8')
        (staged / 'runner/src/snes/spc.c').write_text(
            snes_spc.adapt_core((engine / 'runner/src/snes/spc.c').read_text(encoding='utf-8')),
            encoding='utf-8')
        (staged / 'runner/src/common_rtl.c').write_text(
            snes_spc.adapt_audio_reset((engine / 'runner/src/common_rtl.c').read_text(encoding='utf-8')),
            encoding='utf-8')
        from .gun16_runtime import snes_joypad, snes_bus, snes_ppu
        for name, adapt in (('joypad', snes_joypad), ('snes', snes_bus), ('ppu', snes_ppu)):
            (staged / f'runner/src/snes/{name}.c').write_text(
                adapt((engine / f'runner/src/snes/{name}.c').read_text(encoding='utf-8')), encoding='utf-8')
        from .snes_timing import adapt_engine
        shutil.copy2(ASSETS / 'native/snes_timing.h', project / 'snes_timing.h')
        adapt_engine(staged)
        from .snes_video import adapt_engine as adapt_video
        shutil.copy2(ASSETS / 'native/snes_ppu_cache.inc', project / 'snes_ppu_cache.inc')
        adapt_video(staged)
        from .snes_dma import adapt_engine as adapt_dma
        shutil.copy2(ASSETS / 'native/snes_dma.h', project / 'snes_dma.h')
        shutil.copy2(ASSETS / 'native/snes_hdma.inc', project / 'snes_hdma.inc')
        adapt_dma(staged)
        from .snes_bus import adapt_engine as adapt_bus
        for name in ('snes_bus.h','snes_bus.inc'):
            shutil.copy2(ASSETS/'native'/name,project/name)
        adapt_bus(staged)
        from .snes_ppu_bus import adapt_engine as adapt_ppu_bus
        shutil.copy2(ASSETS/'native/snes_ppu_bus.inc',project/'snes_ppu_bus.inc')
        adapt_ppu_bus(staged)
        from .snes_chips import adapt_engine as adapt_chips
        shutil.copy2(ASSETS / 'native/snes_dsp1_projection.inc', project / 'snes_dsp1_projection.inc')
        adapt_chips(staged)
        from .console16_state import snes_runtime as state_runtime, snes_frame_driver as state_driver
        for name, adapt in (('common_rtl.c', state_runtime), ('beam_frame_driver.c', state_driver)):
            state_source = staged / 'runner/src' / name
            state_source.write_text(adapt(state_source.read_text(encoding='utf-8')), encoding='utf-8')
        ppu = staged / 'runner/src/snes/ppu.h'
        text = ppu.read_text(encoding='utf-8')
        if os.name == 'nt' and active_toolchain() == 'msvc':
            text = text.replace('typedef struct PpuPixelPrioBufs {',
                                'typedef struct __declspec(align(8)) PpuPixelPrioBufs {')
            text = text.replace('} __attribute__((aligned(8))) PpuPixelPrioBufs;', '} PpuPixelPrioBufs;')
        ppu.write_text(text, encoding='utf-8')
        prefix = staged.as_posix()
        common += f'''set(SNESRECOMP_SDL_BACKEND SDL2 CACHE STRING "" FORCE)
set(SNESRECOMP_FRAME_IMPL LLE CACHE STRING "" FORCE)
include("{prefix}/runner/runner.cmake")
list(FILTER SNESRECOMP_RUNNER_SOURCES EXCLUDE REGEX "/snes_savestate_menu\\.c$")
file(GLOB GENERATED CONFIGURE_DEPENDS "generated/*.c")
add_executable(game WIN32 console16_main.c {' '.join(hostkit.sources(system_id))} retro_menu.c gun16.c snes_backend.c snes_spc_runtime.c snes_battery.c
  ${{RESOURCE_SOURCES}} ${{GENERATED}} ${{SNESRECOMP_RUNNER_SOURCES}})
target_include_directories(game PRIVATE . generated ${{SNESRECOMP_RUNNER_INCLUDE_DIRS}} "{prefix}/runner/src/desktop")
target_link_libraries(game PRIVATE ${{SNESRECOMP_RUNNER_LIBRARIES}})
snesrecomp_target_mmx_config(game)
target_compile_definitions(game PRIVATE RR16_MD=0 SNESRECOMP_SDL3=0)
'''
    from .console16_state import write_config
    write_config(project, rom, system_id, title, REPOSITORIES)
    common += 'target_sources(game PRIVATE console16_state.c platform_io.c)\n'
    common += f'target_compile_definitions(game PRIVATE [[RR_RECOMP_VERSION="{__version__}"]])\n'
    # CMake bracket literals do not interpret quotes/backslashes in a ROM title.
    title_literal = json.dumps(title, ensure_ascii=True)
    common += f'''target_compile_definitions(game PRIVATE [[RR_GAME_TITLE={title_literal}]] SDL_MAIN_HANDLED)
target_include_directories(game PRIVATE ${{SDL2_INCLUDE_DIRS}} "${{SDL2_INCLUDE_DIRS}}/..")
target_link_libraries(game PRIVATE SDL2::SDL2-static)
if(WIN32)
  target_link_libraries(game PRIVATE ws2_32 comdlg32)
else()
  target_link_libraries(game PRIVATE m)
endif()
if(MSVC)
  target_compile_options(game PRIVATE /W2 /utf-8 /MP{build_jobs()} /wd4996 /wd4244 /wd4267 /wd4013)
endif()
'''
    if system_id == 'md':
        # The imported sources keep their warning policy, but the adapted bus
        # boundary must never rely on implicit int or mismatched prototypes.
        common += '''if(MSVC)
  set_source_files_properties(native/glue.c native/genesis_bus.c
    native/genesis_machine.c PROPERTIES COMPILE_OPTIONS "/we4013;/we4028")
else()
  set_source_files_properties(native/glue.c native/genesis_bus.c
    native/genesis_machine.c PROPERTIES COMPILE_OPTIONS "-Werror=implicit-function-declaration;-Werror=incompatible-pointer-types")
endif()
'''
    (project / 'CMakeLists.txt').write_text(common, encoding='utf-8')
    from .feedback import stage
    stage(project, system_id, rom.sha256)
    from .console16_optimization import CMAKE
    with (project / 'CMakeLists.txt').open('a', encoding='utf-8') as file:
        file.write(CMAKE)


def prepare16(path: Path, system_id: str, *, emit=print, title=None, resources=None, standard_override=None):
    rom = conversion_rom(path, system_id, standard_override)
    cartridge_profile = (megadrive if system_id == 'md' else supernintendo).profile_for(rom)
    engine, compiler, sdl, cmake, generator = dependencies16(system_id, emit)
    md_profile = cartridge_profile if system_id == 'md' else None
    project = (supernintendo.project_path(ROOT,rom,cartridge_profile) if system_id=='snes' else
               ROOT / '.build' / (system_id + '-' + cartridge_profile['id']))
    project.mkdir(parents=True, exist_ok=True)
    rom_file = project / ('cartridge.bin' if system_id == 'md' else 'cartridge.sfc')
    rom_file.write_bytes(rom.data)
    title = title or cartridge_profile['title']
    guns16.write_header(project, rom)
    if system_id == 'snes':
        supernintendo.write_profile(project, rom, title)
    cache = project / 'generation-identity.json'
    identity = {'rom': rom.sha256, 'engine': REPOSITORIES[system_id][1], 'schema': 2}
    if system_id == 'md':
        entries = megadrive.read_entries(rom)
        megadrive.write_profile(project, engine, rom, entries)
        megadrive.write_spec(project, rom, title, megadrive.video_standard(rom, standard_override))
        identity = megadrive.analysis_identity(project, REPOSITORIES[system_id][1], rom)
    try:
        reuse = json.loads(cache.read_text(encoding='utf-8')) == identity and any((project / 'generated').glob('*.c'))
    except (OSError, ValueError):
        reuse = False
    if reuse:
        emit('Reusing native source analysis for this exact ROM and pinned engine.')
    elif system_id == 'md':
        with timings.phase('code_generation'):
            megadrive.generate(compiler, project, rom_file, instruction_map=True)
    atomic_json(cache, identity)
    if system_id == 'md':
        import re
        from .megadrive_codegen import generate_steps
        static_pcs = {int(value, 16) for value in re.findall(r'\{0x([0-9A-Fa-f]+)u,',
            (project / f'generated/{md_profile["prefix"]}_cycles.c').read_text(encoding='utf-8'))}
        with timings.phase('code_generation'):
            analysis = generate_steps(engine, project, rom, static_pcs | entries | set(megadrive.vectors(rom)['roots']),
                                      megadrive.read_ram_variants(rom))
        emit(f'{analysis["translated_instructions"]} native instructions, '
             f'{analysis["guarded_ram_variants"]} guarded RAM variants; exact PC/stack control flow.')
    with timings.phase('code_generation'):
        _write_build(project, engine, system_id, title, rom)
    if system_id == 'md':
        audio_analysis = json.loads((project / 'z80-native-analysis.json').read_text(encoding='utf-8'))
        emit(f"Z80 sound: {audio_analysis['guarded_positions']} guarded positions, "
             f"{audio_analysis['shared_native_bodies']} shared native bodies.")
    else:
        audio_analysis = json.loads((project / 'spc-native-analysis.json').read_text(encoding='utf-8'))
        emit(f"SPC700 sound: {audio_analysis['guarded_ram_variants']} opcode variants at "
             f"{audio_analysis['guarded_ram_addresses']} RAM positions, "
             f"{audio_analysis['boot_positions']} boot positions.")
    if resources:
        resources(project, engine, rom, rom_file)
    else:
        (project / 'game_resources.rc').write_text(f'103 RCDATA "{rom_file.name}"\n', encoding='utf-8')
    from .resources import embed_resources
    resource_map={103:rom_file}
    if (project/'game_legal.md').is_file():resource_map[102]=project/'game_legal.md'
    if (project/'game_identity.bin').is_file():resource_map[104]=project/'game_identity.bin'
    embed_resources(project,resource_map)
    from .console16_optimization import build_game
    build_game(project, cmake, generator, sdl, emit, system_id)
    return build_executable(project / 'build','game')


def _notice(engine: Path, system_id: str) -> str:
    components = [('RetroRecomp', ASSETS / 'LICENSE'), ('SDL2', ASSETS / 'licenses/SDL2.md'), ('xBR', ASSETS / 'licenses/xbr.md'), ('Noto fonts', ASSETS / 'licenses/Noto.md'),
                  ('UPX', ASSETS / 'licenses/UPX.md'), ('Portable compiler runtime', ASSETS / 'licenses/llvm-mingw.md')]
    if system_id == 'md':
        components += [('GenesisRecomp', engine / 'LICENSE.md'),
                       ('GenesisRecomp recompiler', engine / 'LICENSE-recompiler'),
                       ('Third-party attribution', engine / 'THIRD-PARTY-LICENSES.md'),
                       ('m68k-recomp-core', engine / 'external/m68k-recomp-core/LICENSE')]
        components += [(name, engine / 'runner/external' / name / filename)
                       for name, filename in [('ymfm', 'LICENSE'), ('superzazu', 'LICENSE'),
                                              ('clowncommon', 'LICENCE.txt'), ('minicoro', 'LICENSE')]]
        # Retain the assembly's separate MIT notice as well.
        header = (engine / 'runner/external/minicoro/minicoro.h').read_text(encoding='utf-8')
        first = header.index('Copyright (C) 2004-2016 Mike Pall.')
        assembly_notice = header[first:header.index('*/', first)]
    else:
        components += [('SNESRecomp', engine / 'LICENSE'),
                       ('SNES third-party attribution', engine / 'THIRD_PARTY_ATTRIBUTION.md')]
        components += [('Color-science core ' + name, engine / 'third_party/psxrecomp_color_lut' / name)
                       for name in ('LICENSE-MIT.txt', 'LICENSE-APACHE-2.0.txt',
                                    'LICENSE-POLYFORM-NONCOMMERCIAL-1.0.0.txt')]
        assembly_notice = ''
    return ('RetroRecomp 16-bit test executable. Component licences remain separate.\n\n' +
            '\n\n'.join(f'## {name}\n\n{source.read_text(encoding="utf-8")}' for name, source in components) +
            '\n\n' + assembly_notice)


def _md_scan_script(directory: Path, frames: int, *, six_buttons=False, gun_menu=None) -> Path:
    """Reproducible host input only: never patch guest memory or game code."""
    events = {0: (0, 0)}
    starts = (300, 480, 660, 900, 1200, 1500, 1800, 2100, 2400, 2700) if gun_menu == 't2' else (300, 480, 660)
    for frame in starts:
        events[frame] = (128, 0)
        events[frame + 2] = (0, 0)
    if gun_menu == 't2':
        for frame in (1600, 1640):
            events[frame] = (2, 0)
            events[frame + 2] = (0, 0)
    begin = 2800 if gun_menu == 't2' else 800
    for frame in range(begin, frames, 12):
        phase = (frame - begin) // 12
        direction = (8, 4, 8, 1, 8, 2)[(phase // 40) % 6]
        button = (64, 16, 32, 0)[phase % 4]
        extra = (256, 512, 1024, 0)[phase % 4] if six_buttons else 0
        p2 = (4 if direction == 8 else 8) | (32 if phase % 3 == 0 else 0)
        events[frame] = (direction | button | extra, p2)
    if gun_menu != 't2':
        events[1000], events[1002] = (0, 128), (0, 0)
        for frame in (4800, 4860):
            events[frame], events[frame + 2] = (128, 0), (0, 0)
    path = directory / 'advanced-inputs.txt'
    path.write_text(''.join(f'{frame} {p1} {p2}\n' for frame, (p1, p2) in sorted(events.items())
                            if frame < frames), encoding='ascii')
    return path


def _md_early_start_script(directory: Path, frames: int) -> Path:
    """Explore skipped intros and early menu entry from a fresh boot."""
    events = {0: 0}
    for frame in (10, 60, 120, 240, 360, 480, 600, 720, 840, 960, 1080):
        events[frame], events[frame + 2] = 128, 0
    events.update({1200: 8, 1260: 24, 1290: 8, 1380: 40, 1410: 8,
                   1500: 72, 1530: 8, 1650: 24, 1680: 8})
    path = directory / 'early-start-inputs.txt'
    path.write_text(''.join(f'{frame} {buttons} 0\n' for frame, buttons in sorted(events.items())
                            if frame < frames), encoding='ascii')
    return path


def _md_menu_confirm_script(directory: Path, frames: int) -> Path:
    """Reach games whose menus/dialogue need A/C rather than repeated Start."""
    events = {0: 0}
    for frame in (10, 300, 480, 660):
        events[frame], events[frame + 2] = 128, 0
    for frame in range(800, frames, 60):
        # Released confirmation buttons let name entry and dialogue advance.
        # Explore directions later, after a neutral-input menu phase.
        direction = (0, 8, 2, 4, 1)[min(4, (frame - 800) // 1200)]
        events[frame] = direction | (16 if (frame // 60) % 2 else 64)
        events[frame + 3] = direction
    path = directory / 'menu-confirm-inputs.txt'
    path.write_text(''.join(f'{frame} {buttons} 0\n' for frame, buttons in sorted(events.items())
                            if frame < frames), encoding='ascii')
    return path


def probe16(executable: Path, directory: Path, frames: int, *, play=False, reference=False,
            gun_menu=None, scenario=None, input_script=None, save_state=None, load_state=None) -> dict:
    executable, directory = executable.resolve(), directory.resolve()
    scenario = scenario or ('play' if play else 'demo')
    report = directory / f'{scenario}{"-reference" if reference else ""}.json'
    command = [executable, '--frames', str(frames), '--report', report]
    if input_script is not None:
        command.extend(('--input-script', Path(input_script).resolve()))
    # Chained scenarios: restore the previous scenario's end state before the
    # first frame and keep this one's end state for the next. The script still
    # counts frames from 0 (no --frame-offset), and the headless host only
    # accepts a state written by the same executable and ROM.
    if load_state is not None:
        command.extend(('--load-state', Path(load_state).resolve()))
    if save_state is not None:
        command.extend(('--save-state', Path(save_state).resolve()))
    if play:
        command.append('--play')
        if gun_menu:
            command.extend(('--gun-menu', gun_menu))
    names = ('GENESIS_FORCE_INTERP', 'SNESRECOMP_LLE_BOUNCE', 'RR_SNES_FORCE_INTERP')
    env = probe_environment(**dict(zip(names, ('1', '0', '1')))) if reference else probe_environment(remove=names)
    result = spawn(command, cwd=directory, env=env, timeout=600, phase='reference_runs' if reference else 'native_runs',
                   capture_output=True, text=True)
    (directory / f'{scenario}{"-reference" if reference else ""}.log').write_text(
        result.stdout + result.stderr, encoding='utf-8')

    def failure(result):
        if report.exists():
            try:failed=json.loads(report.read_text(encoding='utf-8'))
            except (OSError,ValueError):failed={}
            if failed.get('coprocessor_failed'):
                chip=failed.get('cartridge_chip','cartridge circuit').upper()
                command=failed.get('coprocessor_failed_command',0)
                return ConversionError(f'{chip} validation stopped at unsupported device command ${command:02X}. '
                                       f'Previous export preserved; see {directory}.')
        if result.returncode == 7 and load_state is not None:
            return ConversionError(f'16-bit {scenario} probe could not restore the saved state '
                                   f'{Path(load_state).name} of the previous scenario. See {directory}.')
        if result.returncode == 8 and save_state is not None:
            return ConversionError(f'16-bit {scenario} probe could not save its end state for the next scenario. '
                                   f'See {directory}.')
        return ConversionError(f'16-bit {scenario} probe failed (exit {result.returncode}). See {directory}.')
    check_exit(result, failure)
    data = json.loads(report.read_text(encoding='utf-8'))
    if data.get('frames') != frames:
        raise ConversionError('16-bit probe did not complete the requested frames.')
    if play and gun_menu == 't2' and frames >= 3000:
        if not all(data.get(key, 0) > 0 for key in ('gun_light_hits', 'gun_interrupts', 'gun_trigger_packets')):
            raise ConversionError('T2 gun test did not receive aim interrupts and trigger packets. Previous export preserved.')
    return {'scenario': scenario, **data}


SNES_AUDIO_FIELDS = ('spc_pc', 'spc_cpu_hash', 'apu_state_hash', 'dsp_state_hash',
                     'pcm_samples', 'pcm_nonzero', 'pcm_peak', 'pcm_hash', 'spc_idle_cycles',
                     'audio_output_underflows', 'audio_output_missing_frames', 'audio_output_priming',
                     'audio_ring_dropped', 'audio_ring_dropped_audible',
                     'audio_ring_highwater', 'audio_ring_current')


def reference_differences(system_id: str, native: dict, reference: dict) -> list[str]:
    """Require every diagnostic field; absent data must never validate an export."""
    fields = ('frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash', 'cpu_pc')
    fields += (('vsram_hash', 'vdp_register_hash') if system_id == 'md' else
               ('oam_hash', 'high_oam_hash', 'apu_ram_hash', 'cpu_cycles', 'master_cycles', 'apu_cycles'))
    if system_id == 'md':
        fields += MD_AUDIO_FIELDS + MD_SRAM_FIELDS + ('console_version', 'cpu_sr', 'cpu_usp', 'cpu_ssp', 'cpu_stopped', 'cpu_prefetch_hash')
        # Previous reports did not expose capture geometry; new reports must
        # agree on it too, including all lower interlace rows and mode history.
        if 'captured_rows' in native or 'captured_rows' in reference:
            fields += ('visible_width', 'visible_height', 'active_raster_height', 'interlace_mode',
                       'output_row_density', 'captured_rows', 'video_modes_seen', 'interlace_frames')
    else:
        fields += SNES_AUDIO_FIELDS
        from .snes_cart import REPORT_FIELDS
        fields += REPORT_FIELDS
        from .snes_chips import REPORT_FIELDS as CHIP_FIELDS
        fields += CHIP_FIELDS
        if 'video_standard' in native or 'video_standard' in reference:
            fields += ('video_standard', 'field_lines', 'ppu_pal', 'overscan_seen',
                       'interlace_seen', 'hires_seen', 'beam_line', 'beam_column',
                       'irq_latches', 'irq_overshot', 'visible_frames')
        if 'captured_rows' in native or 'captured_rows' in reference:
            fields += ('visible_width', 'visible_height', 'active_raster_height',
                       'output_row_density', 'captured_rows', 'field_parity')
    if 'gun_kind' in native or 'gun_kind' in reference:
        fields += ('gun_kind', 'gun_light_hits', 'gun_interrupts', 'gun_button_reads')
        fields += (('gun_latched_hv', 'gun_buttons_latched', 'gun_button_packets', 'gun_trigger_packets') if system_id == 'md' else
                   ('gun_packet', 'gun_latched_h', 'gun_latched_v'))
        if native.get('gun_kind') or reference.get('gun_kind'):
            fields += (('gun_port_control', 'gun_external_irq_enabled') if system_id == 'md' else
                       ('gun_latch_enabled',))
    differences = [field for field in fields if native.get(field) is None or reference.get(field) is None
                   or native[field] != reference[field]]
    if system_id == 'md' and ('bus_budget_misses' in native or 'bus_budget_misses' in reference):
        # Matching engines can share an incorrect cycle table. A retired
        # instruction must pay at least the bus transactions it performed.
        if native.get('bus_budget_misses') != 0 or reference.get('bus_budget_misses') != 0:
            differences.append('bus_timing_budget')
    if system_id == 'md' and ('z80_timing_misses' in native or 'z80_timing_misses' in reference):
        if native.get('z80_timing_misses') != 0 or reference.get('z80_timing_misses') != 0:
            differences.append('z80_timing_budget')
    counters = ('native_entries', 'interpreted_opcodes')
    # A bus rendezvous can suspend an interpreted instruction after its
    # entry signal but before retirement. Keep that signal visible, while
    # comparing the same completed-instruction boundary on both CPU paths.
    if system_id == 'md' and any('retired_interpreted_opcodes' in check for check in (native, reference)):
        counters = ('native_entries', 'retired_interpreted_opcodes')
    if (any(check.get(key) is None for check in (native, reference) for key in counters)
            or sum(native[key] for key in counters) != sum(reference[key] for key in counters)):
        differences.append('retired_instruction_count')
    cpu = 'z80' if system_id == 'md' else 'spc'
    for keys, label in ((('audio_native_opcodes', 'audio_interpreted_opcodes'), f'{cpu}_instruction_count'),
                        (('audio_native_cycles', 'audio_interpreted_cycles'), f'{cpu}_cycle_count')):
        if (any(check.get(key) is None for check in (native, reference) for key in keys)
                or sum(native[key] for key in keys) != sum(reference[key] for key in keys)):
            differences.append(label)
    return differences


def convert16(rom_path: Path, *, system_id: str, title=None, output=None, profile=None,
              passes=3, frames=3600, backend='banked', language='en', cover=None,
              boxart_dir=None, online_cover=True, use_cover=True, icon_tags=True,
              standard_override=None, md_advanced_scan=False, scan_level=None, publish_result=True,
              emit=print) -> Path:
    from .artwork import prepare_icon
    from .core import executable_name
    from .metadata import write_game_metadata
    from .paths import data_directory, games_root, boxart_cache_directory
    if profile is not None:
        raise ConversionError('16-bit profiles use pinned game-specific analysis, not Sega Z80 TOML files.')
    check_run_budget(passes, frames, 'Choose 1–10 passes and 1–10000 frames per test.')
    rom = conversion_rom(rom_path, system_id, standard_override)
    cartridge_profile = (megadrive if system_id == 'md' else supernintendo).profile_for(rom)
    standard = (megadrive if system_id == 'md' else supernintendo).video_standard(rom, standard_override)
    gun = guns16.gun_game(system_id, rom.crc32, rom.path.name)
    # The scan level decides how long discovery runs on both 16-bit consoles:
    # extended and thorough add a long attract sequence plus reproducible
    # pseudo-random play routes seeded from the exact ROM. The authored Mega
    # Drive replays stay Mega Drive only. The former switch means thorough.
    from .scan_levels import console16_budget, legacy_level
    level = resolve_scan_level(scan_level, legacy_level(system_id, md_advanced_scan=bool(md_advanced_scan)))
    budget = console16_budget(level, frames)
    advanced = budget['advanced']
    fixed_scripts = advanced and system_id == 'md'
    if output is None:
        return convert_single(rom_path, games_root(), title=title or cartridge_profile['title'], cover=cover,
            identify_arguments=(system_id,), frames=frames, passes=passes, language=language, boxart_dir=boxart_dir,
            online_cover=online_cover, use_cover=use_cover, icon_tags=icon_tags, standard_override=standard_override,
            scan_level=level, emit=emit)
    started = time.perf_counter()
    from .feedback import ingest
    gameplay_feedback = ingest(system_id, rom.sha256, output, emit=emit)
    title = title or cartridge_profile['title']
    name = 'Mega Drive' if system_id == 'md' else 'Super Nintendo'
    stage = 'supported' if system_id == 'md' else supernintendo.support_stage(rom)
    emit(f'{name}: {stage} {title} {standard.upper()} conversion; '
         + ('using exact-ROM catalogue settings.' if cartridge_profile.get('source') == 'catalogue'
            else 'generating a profile from this cartridge; no catalogue entry required.'))
    emit('68000 and Z80 sound CPU use guarded native code.' if system_id == 'md' else
         '65816 and SPC700 sound CPU use guarded native code. Hardware fidelity is a separate check.')
    if system_id=='snes':
        from .snes_chips import identify
        chip=identify(rom.data)
        if chip=='cx4':emit('CX4 device uses its counted instruction interpreter; main/audio native coverage is measured separately.')
        elif chip=='superfx':emit('Super FX (GSU) uses its counted instruction interpreter; main/audio native coverage is measured separately.')
        elif chip.startswith('dsp1'):emit('DSP-1 uses a firmware-free command model; unsupported commands stop validation.')
    for limitation in cartridge_profile.get('limitations', ()):
        emit('Limitation: ' + limitation)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    artwork = {}
    metadata = {}
    def resources(project, engine, cartridge, rom_file):
        artwork.update(prepare_icon(project, cartridge.path, title,
            (boxart_dir or ROOT / 'BoxArt' / name).resolve(), explicit=cover,
            online=online_cover, enabled=use_cover, cache_directory=boxart_cache_directory(system_id),
            system_id=system_id, tags=('shooting',) if gun and icon_tags else (), emit=emit))
        metadata.update(write_game_metadata(project, title, executable_name(title),
            light_phaser=False, icon=artwork['embedded'], standard=standard, system_id=system_id,
            gun_device=gun.device if gun else None))
        (project / 'game_legal.md').write_text(_notice(engine, system_id), encoding='utf-8')
        (project / 'game_identity.bin').write_bytes(b'[Retro-Recomp]\0' + rom.sha256.encode('ascii') + b'\0')
        with (project / 'game_resources.rc').open('a', encoding='utf-8') as rc:
            rc.write('102 RCDATA "game_legal.md"\n' + f'103 RCDATA "{rom_file.name}"\n' +
                     '104 RCDATA "game_identity.bin"\n')
    learn = megadrive.learn_entries if system_id == 'md' else supernintendo.learn_ram_variants
    gun_menu = 't2' if gun and gun.system == 'md' and gun.title == 'T2 - The Arcade Game' else None
    advanced_frames = max(frames, 6000) if fixed_scripts else 0
    # Later attract scenes can introduce code after the former 18,000-frame
    # scan. Keep the optional advanced route bounded and validate it against
    # the reference CPU before retaining any new observations.
    demo_frames = budget['demo_frames']
    early_start_frames = 1800 if fixed_scripts else 0
    menu_confirm_frames = advanced_frames if not gun else 0
    six_buttons = system_id == 'md' and bool(cartridge_profile.get(
        'six_buttons', 'street-fighter' in (cartridge_profile.get('id') or '')))
    # Long pseudo-random routes (host inputs only, never guest patches) reach
    # later stages and code the game builds after minutes of play. The seed is
    # the exact ROM identity, so every conversion replays the same routes and
    # the reference run receives the same script. Gun games keep their own
    # authored mouse routes.
    long_routes = ()
    if advanced and not gun and budget['route_count']:
        from .random_routes import long_routes as pseudo_random_routes
        long_routes = pseudo_random_routes(system_id, rom.sha256, count=budget['route_count'],
                                           frames=budget['route_frames'], six_buttons=six_buttons,
                                           chain=CHAIN_LONG_ROUTES)
    # An exact ROM with an authored gameplay route (snes_routes: the Super FX
    # cartridges whose random route stays in the menus) replays it as one more
    # scenario from the Extended level on, after the random routes.
    authored_routes = ()
    if advanced and not gun and system_id == 'snes':
        from .snes_routes import authored_routes as exact_rom_routes
        authored_routes = exact_rom_routes(rom.sha256)
    play_routes = long_routes + authored_routes
    long_frames = sum(route.frames for route in play_routes)
    route_metadata = {route.name: route.metadata() for route in play_routes}
    # When chaining is enabled, every route after the first continues from the
    # state the previous route saved at its last frame. Each engine chains from
    # its own state file: the native export under `checks`, the reference under
    # `checks/reference`, both written and read by the executable of the same
    # pass. The field-by-field comparison is unchanged.
    chained = {route.name: route.continues_from for route in long_routes if route.continues_from}

    def route_states(scenario, directory):
        options = {}
        if scenario in chained.values():
            options['save_state'] = directory / f'{scenario}.state'
        if scenario in chained:
            options['load_state'] = directory / f'{chained[scenario]}.state'
        return options

    if advanced:
        emit(f'{name} advanced scan: tests the original attract sequence for {demo_frames} frames' +
             (f', adds a {advanced_frames}-frame varied-input replay '
              f'and a {early_start_frames}-frame early-start replay' if fixed_scripts else '') +
             (f' and a {menu_confirm_frames}-frame menu/dialogue replay' if menu_confirm_frames else '') +
             (f' and {len(long_routes)} reproducible pseudo-random play routes of '
              f'{long_routes[0].frames} frames' if long_routes else '') +
             (f', plus the {authored_routes[0].frames}-frame authored gameplay route of this exact ROM'
              if authored_routes else '') +
             (', each later route continuing from the saved end state of the previous one'
              if chained else '') +
             ' on every pass, '
             'with reference CPU/video/audio comparison before learning. Conversion takes longer.')
    history, comparisons = [], []
    reference_before_learning = True

    def compare(checks, directory, scripts):
        directory.mkdir(exist_ok=True)
        comparisons = []
        for native in checks:
            scenario = native['scenario']
            options = dict(play=scenario != 'demo', reference=True, gun_menu=gun_menu, scenario=scenario)
            if scenario in scripts:
                options['input_script'] = scripts[scenario]
                options.update(route_states(scenario, directory))
            reference = probe16(executable, directory, native['frames'], **options)
            comparisons.append({'scenario': native['scenario'], 'frames': native['frames'],
                                'differences': reference_differences(system_id, native, reference)})
        if any(result['differences'] for result in comparisons):
            atomic_json(checks_dir / 'native-validation.json', {'comparisons': comparisons})
            raise ConversionError(f'{name} native CPU/video/audio reference comparison failed. '
                                  f'Previous export preserved; see {checks_dir}.')
        return comparisons

    for attempt in range(passes):
        timings.begin_pass(attempt + 1)
        executable = prepare16(rom_path, system_id, emit=emit, title=title, resources=resources,
                               standard_override=standard)
        checks_dir = executable.parents[2 if os.name == 'nt' and executable.parent.name == 'Release' else 1] / 'checks'
        checks_dir.mkdir(exist_ok=True)
        checks = []
        scenarios = [(demo_frames if not play else frames, dict(play=play, gun_menu=gun_menu))
                     for play in (False, True)]
        scripts = {}
        if fixed_scripts:
            scripts['advanced'] = _md_scan_script(checks_dir, advanced_frames, six_buttons=six_buttons,
                                                  gun_menu=gun_menu)
            scripts['early-start'] = _md_early_start_script(checks_dir, early_start_frames)
            if menu_confirm_frames:
                scripts['menu-confirm'] = _md_menu_confirm_script(checks_dir, menu_confirm_frames)
            scenarios.append((advanced_frames, dict(play=True, gun_menu=gun_menu,
                                                   scenario='advanced', input_script=scripts['advanced'])))
            scenarios.append((early_start_frames, dict(play=True, gun_menu=gun_menu,
                scenario='early-start', input_script=scripts['early-start'])))
            if menu_confirm_frames:
                scenarios.append((menu_confirm_frames, dict(play=True, gun_menu=gun_menu,
                    scenario='menu-confirm', input_script=scripts['menu-confirm'])))
        if play_routes:
            from .random_routes import write_route
            for route in play_routes:
                scripts[route.name] = write_route(route, checks_dir)
                scenarios.append((route.frames, dict(play=True, gun_menu=gun_menu,
                    scenario=route.name, input_script=scripts[route.name],
                    **route_states(route.name, checks_dir))))
        for budget, options in scenarios:
            check = probe16(executable, checks_dir, budget, **options)
            check['native_counter_unit'] = 'main CPU opcodes'
            if check['scenario'] in route_metadata:
                check['input_route'] = route_metadata[check['scenario']]
            checks.append(check)
            emit(f"{name} {check['scenario']}: {check['frames']} frames, "
                 f"{check.get('main_interpreted_opcodes',check['interpreted_opcodes'])} interpreted main CPU opcodes. Sound CPU: " +
                 f"{check['audio_interpreted_opcodes']} interpreted {'Z80' if system_id == 'md' else 'SPC700'} opcodes.")
            if system_id=='snes' and check.get('coprocessor_instructions'):
                emit(f"{check['cartridge_chip'].upper()}: {check['coprocessor_instructions']} counted interpreted device instructions.")
        history.append({'pass': attempt + 1, 'checks': [
            {key: check.get(key) for key in ('scenario', 'frames', 'native_entries', 'interpreted_opcodes',
             'rom_fallback_opcodes', 'ram_fallback_opcodes', 'audio_native_opcodes',
             'audio_interpreted_opcodes', 'audio_native_cycles', 'audio_interpreted_cycles')} for check in checks]})
        if system_id == 'snes':
            # A stuck game is refused before the (long) reference replays.
            supernintendo.validate_device_liveness(checks)
        if reference_before_learning:
            comparisons = compare(checks, checks_dir / 'reference', scripts)
        if system_id == 'snes':
            supernintendo.validate_activity(cartridge_profile, checks)
        if not any(check.get('rom_entries') or check.get('ram_variants') or check.get('z80_variants') or check.get('z80_driver_images')
                   or check.get('spc_variants') or check.get('spc_driver_images')
                   for check in checks) or attempt + 1 == passes:
            break
        added = learn(rom, checks)
        if system_id == 'md':
            from .megadrive_z80 import learn_variants
            added += learn_variants(rom, checks)
        else:
            from .snes_spc import learn as learn_spc
            added += learn_spc(rom, checks)
        if not added:
            break
        observations = '68000 ROM/RAM entries and Z80 opcode variants' if system_id == 'md' else '65816 RAM and SPC700 opcode variants'
        emit(f'Pass {attempt + 1}/{passes}: {added} {observations} learned; regenerating native code.')
    timings.end_passes()
    if not reference_before_learning:
        comparisons = compare(checks, checks_dir / 'reference', {})
    learn(rom, checks)
    if system_id == 'md':
        from .megadrive_z80 import learn_variants
        learn_variants(rom, checks)
    else:
        from .snes_spc import learn as learn_spc
        learn_spc(rom, checks)
    emit('Internal CPU/memory/visible-frame/audio PCM reference comparison: matches.')
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'status': stage,
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'system': {'id': system_id, 'name': name}, 'scan_level': level, 'rom': rom.metadata(),
        'cartridge_profile': {'source': cartridge_profile.get('source', 'cartridge'),
                              'id': cartridge_profile.get('id'),
                              'catalogue_required': False,
                              'limitations': cartridge_profile.get('limitations', [])},
        'compiler': {'repository': REPOSITORIES[system_id][0], 'revision': REPOSITORIES[system_id][1],
                     'license': 'PolyForm Noncommercial 1.0.0'},
        'final_checks': checks, 'passes': history, 'reference_vdp_trace_match': None,
        'advanced_scan': {'enabled': advanced, 'level': level,
                          'additional_frames': (demo_frames - frames + advanced_frames + early_start_frames
                                                + menu_confirm_frames + long_frames),
                          'demo_frames': demo_frames,
                          'scenario': 'advanced' if fixed_scripts else (play_routes[0].name if play_routes else None),
                          'scenario_frames': ({**({'advanced': advanced_frames, 'early-start': early_start_frames}
                                                 if fixed_scripts else {}),
                                              **({'menu-confirm': menu_confirm_frames} if menu_confirm_frames else {}),
                                              **{route.name: route.frames for route in play_routes}}
                                              if advanced else {}),
                          'long_routes': [route.metadata() for route in long_routes],
                          'authored_routes': [route.metadata() for route in authored_routes],
                          'reference_before_learning': advanced},
        'native_validation': {'passed': True, 'visible_sequence_match': True,
                              'audio_pcm_match': True,
                              'comparisons': comparisons,
                              'reference_frames': max(check['frames'] for check in checks),
                              'reference_kind': 'internal_shared_semantics',
                              'reference_before_learning': reference_before_learning,
                              'cpu_fidelity_validated': False,
                              'hardware_fidelity_validated': False, 'full_game_validated': False},
        'video_model': {'standard': standard, 'visible_pixels': [checks[-1].get('visible_width', 320) if system_id == 'md' else 256,
                        checks[-1].get('visible_height', 224)],
                        'console_version': checks[-1].get('console_version') if system_id == 'md' else None},
        'audio_cpu': checks[-1].get('audio_cpu', 'interpreted'),
        'audio_counter_unit': 'sound CPU cycles',
        'audio_native_percentage': [round(100 * check.get('audio_native_cycles', 0) /
            max(1, check.get('audio_native_cycles', 0) + check.get('audio_interpreted_cycles', 0)), 6)
            for check in checks],
        # Main CPU only. A cartridge device (GSU, CX4, DSP-1) has its own entry below.
        'native_percentage': [round(100 * check['native_entries'] /
            max(1, check['native_entries'] + check.get('main_interpreted_opcodes', check['interpreted_opcodes'])), 6)
            for check in checks],
        **({'cartridge_device': device} if system_id == 'snes' and (device := device_entry(checks)) else {}),
        'peripheral': {'device': gun.device, 'port': 2, 'host_input': 'mouse'} if gun else None,
        'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'slots': 1,
                        'compatibility': 'same ROM, video standard and runtime ABI'},
        'cartridge_memory': megadrive_sram.layout(rom) if system_id == 'md' else snes_cart.layout(rom),
        'runtime_learning': True, 'runtime_feedback': gameplay_feedback,
        'physical_latency_measured': False, 'artwork': artwork, 'windows_metadata': metadata,
        'executable': executable_name(title), 'build_executable': str(executable), 'toolchain': toolchain_description(),
        'build_directory': str(executable.parents[2 if os.name == 'nt' and executable.parent.name == 'Release' else 1]),
        'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
    write_report(output / 'conversion-report.json', report)
    return executable
