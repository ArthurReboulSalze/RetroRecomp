"""ROM-specific 16-bit integration proofs, with pinned offline build inputs."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import sys
import time

from .paths import ROOT, ASSETS
from .core import ConversionError, run, serialized_setup, toolchain
from .cartridge16 import read_megadrive_rom, read_snes_rom
from . import __version__
from .library import atomic_json
from . import megadrive, supernintendo, guns16

REPOSITORIES = {
    'md': ('mstan/segagenesisrecomp', '00c60bc855a7998f92e5614585d52bca8fffcaf2', 'segagenesisrecomp'),
    'snes': ('RetroPortingToolKit/snesrecomp', 'a00df26a87831113fec91b9225bf16b049d40775', 'snesrecomp'),
    'smw': ('mstan/SuperMarioWorldRecomp', '8dedb2869414f20d1d86d34081be26594560cc15', 'smwrecomp'),
}
SUPPORTED_SYSTEMS = ('md', 'snes')
MD_AUDIO_FIELDS = ('fm_samples', 'fm_nonzero', 'fm_peak', 'fm_hash', 'fm_active_frames',
                   'psg_samples', 'psg_nonzero', 'psg_peak', 'psg_hash', 'psg_active_frames',
                   'z80_pc', 'z80_slice_cycles', 'z80_ram_hash', 'z80_cpu_hash', 'ym_timer_hash')


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
def dependencies16(system_id: str, emit, *, legacy_smw=True):
    cmake, generator = toolchain()
    sdl = ROOT / '.deps/SDL/install'
    if not (sdl / 'lib/SDL2-static.lib').is_file():
        from .core import dependencies
        _, sdl, cmake, generator = dependencies(emit)
    names = (system_id, 'smw') if system_id == 'snes' and legacy_smw else (system_id,)
    for key in names:
        repo, revision, directory = REPOSITORIES[key]
        checkout = ROOT / '.deps' / directory
        if not (checkout / '.git').exists():
            emit(f'Downloading pinned {repo} sources…')
            run(['git', 'clone', '--no-checkout', f'https://github.com/{repo}.git', checkout], timeout=600)
        if run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=checkout).strip():
            raise ConversionError(f'Dependency checkout has tracked edits: {checkout}')
        if run(['git', 'rev-parse', 'HEAD'], cwd=checkout).strip() != revision:
            run(['git', 'fetch', '--depth', '1', 'origin', revision], cwd=checkout, timeout=600)
            run(['git', 'checkout', '--detach', revision], cwd=checkout)
    engine = ROOT / '.deps' / REPOSITORIES[system_id][2]
    if system_id == 'md':
        run(['git', 'submodule', 'update', '--init', '--depth', '1',
             'external/m68k-recomp-core', 'external/rbengine', 'external/z80-recomp-core'], cwd=engine, timeout=600)
        build = ROOT / '.build/megadrive-compiler'
        compiler = build / 'Release/GenesisRecomp.exe'
        if not compiler.is_file():
            run([cmake, '-S', engine / 'recompiler', '-B', build, '-G', generator, '-A', 'x64'], log=build / 'configure.log')
            run([cmake, '--build', build, '--config', 'Release', '--parallel', '4'], log=build / 'build.log')
    else:
        compiler = engine / 'recompiler-rs/target/release/snesrecomp-analyze.exe'
        if legacy_smw and not compiler.is_file():
            # Use the installed stable toolchain instead of silently downloading
            # the upstream development pin. The crate requires Rust >= 1.85.
            emit('Building the SNES native analyzer with installed Rust…')
            if not shutil.which('cargo'):
                raise ConversionError('The experimental SNES analyzer requires installed Rust >= 1.85 (stable toolchain).')
            run(['cargo', '+stable', 'build', '--locked', '--release', '--bin', 'snesrecomp-analyze'],
                cwd=engine / 'recompiler-rs', log=ROOT / '.build/snes-analyzer.log', timeout=600)
    return engine, compiler, sdl, cmake, generator


def _write_build(project: Path, engine: Path, system_id: str, title: str) -> None:
    for name in ('retro_console16.h', 'console16_main.c', 'console16_host_ui.c', 'console16_state.c', 'console16_state.h', 'retro_menu.c', 'retro_menu.h', 'retro_keyboard.h', 'scanlines.h', 'scanline_sdl.h', 'display_settings.h', 'gun16.h', 'gun16.c', f'{system_id}_backend.c'):
        shutil.copy2(ASSETS / 'native' / name, project / name)
    native = project / 'native'
    native.mkdir(exist_ok=True)
    prefix = engine.as_posix()
    common = '''cmake_minimum_required(VERSION 3.20)
project(RetroRecomp16 LANGUAGES C CXX RC)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
find_package(SDL2 REQUIRED)
'''
    if system_id == 'md':
        shutil.copy2(ASSETS / 'native/md_ym_timers.h', project / 'md_ym_timers.h')
        shutil.copy2(ASSETS / 'native/md_timing.h', project / 'md_timing.h')
        from .megadrive_runtime import timing_source, timing_vdp
        from . import megadrive_z80
        rom = read_megadrive_rom(project / 'cartridge.bin')
        megadrive_z80.generate(project, engine, megadrive_z80.read_variants(rom))
        for name in ('md_z80_native.h', 'md_z80_runtime.c'):
            shutil.copy2(ASSETS / 'native' / name, project / name)
        (native / 'z80_reference.c').write_text(megadrive_z80.adapt_reference(
            (engine / 'runner/external/superzazu/z80.c').read_text(encoding='utf-8')), encoding='utf-8')
        step_aot = '#define RR_MD_STEP_AOT 1' in (project / 'retro_md_game.h').read_text(encoding='utf-8')
        if step_aot:
            for name in ('md_native_steps.h', 'md_step_dispatch.c'):
                shutil.copy2(ASSETS / 'native' / name, project / name)
        # Two host-only adaptations in private source copies. Never edit the
        # dependency checkout: count exact interpreter opcodes; remove legacy
        # sidecar deletion performed at game startup.
        glue = (engine / 'runner/glue.c').read_text(encoding='utf-8')
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
        (native / 'glue.c').write_text(glue, encoding='utf-8')
        interp = (engine / 'runner/m68k_interp.c').read_text(encoding='utf-8')
        interp = interp.replace('static void cov_mark(uint32_t pc) {',
            'extern void rr16_note_interpreted(void);\nstatic void cov_mark(uint32_t pc) {\n    rr16_note_interpreted();', 1)
        if step_aot:
            from .megadrive_codegen import adapt_interpreter, adapt_cpu_snapshot
            interp = adapt_interpreter(interp)
            shutil.copy2(ASSETS / 'native/md_portable_state.inc', project / 'md_portable_state.inc')
            (native / 'rb_state.c').write_text(adapt_cpu_snapshot(
                (engine / 'runner/rb_state.c').read_text(encoding='utf-8')) +
                '\n#include "md_portable_state.inc"\n', encoding='utf-8')
            from .gun16_runtime import md_interpreter
            interp = md_interpreter(interp)
        (native / 'm68k_interp.c').write_text(interp, encoding='utf-8')
        audio = (engine / 'runner/audio.c').read_text(encoding='utf-8')
        audio = audio.replace('want.samples  = 1024;', 'want.samples  = 512;')
        audio = audio.replace('cfg.preroll_ms     = 200.0;',
            'cfg.target_ms = 25.0; cfg.em_low_ms = 5.0; cfg.em_high_ms = 80.0;\n    cfg.preroll_ms = 25.0;')
        audio = audio.replace('a ~200 ms boot pre-roll', 'a 25 ms boot pre-roll')
        (native / 'audio.c').write_text(audio, encoding='utf-8')
        sources = ['fiber_compat.c', 'crash_report.c', 'chip_trace.c', 'cmd_server_stub.c',
                   *([] if step_aot else ['rb_state.c']),
                   'cosim_state.c', 'cosim_cycles.c', 'audio/event_queue.c',
                   'audio/mixer.c', 'audio/observability.c', 'audio/audio_shadow.c',
                   'audio/fm_shadow.cpp', 'video/color_lut.c']
        from .gun16_runtime import md_bus, md_vdp, md_machine
        from .megadrive_runtime import ym_bus
        for name, adapt in (('genesis_bus', lambda s: ym_bus(md_bus(s))), ('genesis_vdp', md_vdp), ('genesis_machine', md_machine)):
            text = adapt((engine / f'runner/video/{name}.c').read_text(encoding='utf-8'))
            text = (timing_vdp(text) if name == 'genesis_vdp' else
                    timing_source(text, 'machine' if name == 'genesis_machine' else 'bus'))
            if name == 'genesis_machine':
                from .gun16_runtime import replace
                text = '#include "md_z80_native.h"\n' + replace(text,
                    '        z80_step(&m->z80);', '        rr_md_z80_step(&m->z80);')
                text = replace(text, '        m->bus.z80_reset_pending = 0;',
                    '        rr_md_z80_capture_driver();\n        m->bus.z80_reset_pending = 0;')
            (native / f'{name}.c').write_text(text, encoding='utf-8')
        for path, component in (('sim_step.c', 'sim'), ('audio/ym2612_ymfm.cpp', 'fm'),
                                ('audio/sn76489.c', 'psg')):
            target = native / Path(path).name
            target.write_text(timing_source((engine / 'runner' / path).read_text(encoding='utf-8'), component),
                              encoding='utf-8')
        sources += [f'external/ymfm/src/{name}.cpp' for name in ('ymfm_opn', 'ymfm_ssg', 'ymfm_adpcm', 'ymfm_pcm')]
        source_text = '\n'.join(f'  "{prefix}/runner/{source}"' for source in sources)
        generated_glob = ('"steps/*.c" "generated/*_layout.c"' if step_aot else
                          '"generated/*_part*.c" "generated/*_dispatch.c" "generated/*_layout.c"')
        step_sources = 'md_step_dispatch.c native/rb_state.c' if step_aot else ''
        common += f'''file(GLOB GENERATED CONFIGURE_DEPENDS {generated_glob})
add_executable(game WIN32 console16_main.c console16_host_ui.c retro_menu.c gun16.c md_backend.c
  native/glue.c native/m68k_interp.c native/audio.c native/genesis_bus.c native/genesis_vdp.c
  native/genesis_machine.c native/z80_reference.c md_z80_runtime.c md_z80_generated.c
  native/sim_step.c native/ym2612_ymfm.cpp native/sn76489.c
  game_resources.rc {step_sources} ${{GENERATED}}
{source_text}
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(game PRIVATE . "{prefix}/runner" "{prefix}/runner/include"
  "{prefix}/runner/video" "{prefix}/runner/audio" "{prefix}/runner/external/superzazu" "{prefix}/runner/external/clowncommon"
  "{prefix}/runner/external/ymfm/src" "{prefix}/recompiler/src" "{prefix}/external/m68k-recomp-core/src")
target_compile_definitions(game PRIVATE RR16_MD=1 OWN_BACKEND=1 ENABLE_RECOMPILED_CODE=1 INCLUDE_GENERATED_CODE=1 GENESIS_BATCHED_PLANES=0)
target_link_options(game PRIVATE /CETCOMPAT:NO)
'''
    else:
        from .snes_codegen import generate, adapt_core, adapt_bridge, adapt_frame_driver
        from .cartridge16 import read_snes_rom
        rom = read_snes_rom(project / ('smw.sfc' if (project / 'smw.sfc').exists() else 'cartridge.sfc'))
        generate(engine, project, rom)
        shutil.copy2(ASSETS / 'native/snes_native_steps.h', project / 'snes_native_steps.h')
        from . import snes_spc
        snes_spc.generate(engine, project, rom)
        for name in ('snes_spc_native.h', 'snes_spc_runtime.c'):
            shutil.copy2(ASSETS / 'native' / name, project / name)
        if supernintendo.profile_for(rom)['legacy_functions']:
            shutil.copy2(ROOT / '.deps/smwrecomp/src/variables.h', project / 'variables.h')
        else:
            (project / 'variables.h').write_text('/* No foreign game RAM aliases. */\n', encoding='ascii')
        # Upstream uses one GCC alignment annotation in its PPU header.
        # Preserve the required alignment on MSVC in a private runtime copy.
        staged = project / 'engine'
        for directory in ('runner', 'third_party'):
            shutil.copytree(engine / directory, staged / directory, dirs_exist_ok=True)
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
        from .console16_state import snes_runtime as state_runtime, snes_frame_driver as state_driver
        for name, adapt in (('common_rtl.c', state_runtime), ('beam_frame_driver.c', state_driver)):
            state_source = staged / 'runner/src' / name
            state_source.write_text(adapt(state_source.read_text(encoding='utf-8')), encoding='utf-8')
        ppu = staged / 'runner/src/snes/ppu.h'
        text = ppu.read_text(encoding='utf-8')
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
add_executable(game WIN32 console16_main.c console16_host_ui.c retro_menu.c gun16.c snes_backend.c snes_spc_runtime.c
  game_resources.rc ${{GENERATED}} ${{SNESRECOMP_RUNNER_SOURCES}})
target_include_directories(game PRIVATE . generated ${{SNESRECOMP_RUNNER_INCLUDE_DIRS}} "{prefix}/runner/src/desktop")
target_link_libraries(game PRIVATE ${{SNESRECOMP_RUNNER_LIBRARIES}})
snesrecomp_target_mmx_config(game)
target_compile_definitions(game PRIVATE RR16_MD=0 SNESRECOMP_SDL3=0)
'''
    from .console16_state import write_config
    write_config(project, rom, system_id, title, REPOSITORIES)
    common += 'target_sources(game PRIVATE console16_state.c)\n'
    # CMake bracket literals do not interpret quotes/backslashes in a ROM title.
    title_literal = json.dumps(title, ensure_ascii=True)
    common += f'''target_compile_definitions(game PRIVATE [[RR_GAME_TITLE={title_literal}]] SDL_MAIN_HANDLED)
target_include_directories(game PRIVATE ${{SDL2_INCLUDE_DIRS}} "${{SDL2_INCLUDE_DIRS}}/..")
target_link_libraries(game PRIVATE SDL2::SDL2-static ws2_32 comdlg32)
target_compile_options(game PRIVATE /W2 /utf-8 /MP4 /wd4996 /wd4244 /wd4267 /wd4013)
'''
    (project / 'CMakeLists.txt').write_text(common, encoding='utf-8')


def prepare16(path: Path, system_id: str, *, emit=print, title=None, resources=None, standard_override=None):
    rom = conversion_rom(path, system_id, standard_override)
    cartridge_profile = (megadrive if system_id == 'md' else supernintendo).profile_for(rom)
    legacy_smw = cartridge_profile.get('legacy_functions', False)
    engine, compiler, sdl, cmake, generator = dependencies16(system_id, emit, legacy_smw=legacy_smw)
    md_profile = cartridge_profile if system_id == 'md' else None
    project = ROOT / '.build' / (system_id + '-' + cartridge_profile['id'])
    project.mkdir(parents=True, exist_ok=True)
    rom_file = project / ('cartridge.bin' if system_id == 'md' else 'smw.sfc' if legacy_smw else 'cartridge.sfc')
    rom_file.write_bytes(rom.data)
    title = title or cartridge_profile['title']
    guns16.write_header(project, rom)
    if system_id == 'snes':
        supernintendo.write_profile(project, rom, title)
    cache = project / 'generation-identity.json'
    identity = {'rom': rom.sha256, 'engine': REPOSITORIES[system_id][1],
                'game': REPOSITORIES['smw'][1] if system_id == 'snes' else REPOSITORIES['md'][1],
                'schema': 1}
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
        megadrive.generate(compiler, project, rom_file, instruction_map=True)
    elif legacy_smw:
        arguments = ['generate', '--rom', rom_file, '--cfg-dir', ROOT / '.deps/smwrecomp/recomp',
                     '--out-dir', project / 'generated', '--funcs-h', project / 'funcs.h',
                     '--project-root', ROOT / '.deps/smwrecomp', '--cfg-roots', '--json-progress',
                     '--expected-sha256', rom.sha256]
        command = ([sys.executable, '_snes-generate', engine] if getattr(sys, 'frozen', False) else
                   [sys.executable, engine / 'snesrecomp_cli.py'])
        run([*command, *arguments], log=project / 'generate.log', timeout=1200)
    atomic_json(cache, identity)
    if system_id == 'md':
        import re
        from .megadrive_codegen import generate_steps
        static_pcs = {int(value, 16) for value in re.findall(r'\{0x([0-9A-Fa-f]+)u,',
            (project / f'generated/{md_profile["prefix"]}_cycles.c').read_text(encoding='utf-8'))}
        analysis = generate_steps(engine, project, rom, static_pcs | entries | set(megadrive.vectors(rom)['roots']),
                                  megadrive.read_ram_variants(rom))
        emit(f'{analysis["translated_instructions"]} native instructions, '
             f'{analysis["guarded_ram_variants"]} guarded RAM variants; exact PC/stack control flow.')
    _write_build(project, engine, system_id, title)
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
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64',
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=project / 'build.log', timeout=600)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'],
        log=project / 'build.log', timeout=1200)
    return project / 'build/Release/game.exe'


def _notice(engine: Path, system_id: str, *, legacy_smw=True) -> str:
    components = [('RetroRecomp', ASSETS / 'LICENSE'), ('SDL2', ASSETS / 'licenses/SDL2.md'),
                  ('UPX', ASSETS / 'licenses/UPX.md')]
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
        if legacy_smw:
            components += [('SuperMarioWorldRecomp', ROOT / '.deps/smwrecomp/LICENSE')]
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


def probe16(executable: Path, directory: Path, frames: int, *, play=False, reference=False,
            gun_menu=None, scenario=None, input_script=None) -> dict:
    executable, directory = executable.resolve(), directory.resolve()
    scenario = scenario or ('play' if play else 'demo')
    report = directory / f'{scenario}{"-reference" if reference else ""}.json'
    command = [executable, '--frames', str(frames), '--report', report]
    if input_script is not None:
        command.extend(('--input-script', Path(input_script).resolve()))
    if play:
        command.append('--play')
        if gun_menu:
            command.extend(('--gun-menu', gun_menu))
    import os
    import subprocess
    env = os.environ.copy()
    if reference:
        env.update(GENESIS_FORCE_INTERP='1', SNESRECOMP_LLE_BOUNCE='0', RR_SNES_FORCE_INTERP='1')
    else:
        env.pop('GENESIS_FORCE_INTERP', None)
        env.pop('SNESRECOMP_LLE_BOUNCE', None)
        env.pop('RR_SNES_FORCE_INTERP', None)
    result = subprocess.run([str(arg) for arg in command], cwd=directory, env=env,
        capture_output=True, text=True, timeout=600, creationflags=subprocess.CREATE_NO_WINDOW)
    (directory / f'{scenario}{"-reference" if reference else ""}.log').write_text(
        result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise ConversionError(f'16-bit {scenario} probe failed (exit {result.returncode}). See {directory}.')
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
        fields += MD_AUDIO_FIELDS + ('console_version', 'cpu_sr', 'cpu_usp', 'cpu_ssp', 'cpu_stopped')
    else:
        fields += SNES_AUDIO_FIELDS
        if 'video_standard' in native or 'video_standard' in reference:
            fields += ('video_standard', 'field_lines', 'ppu_pal', 'overscan_seen',
                       'interlace_seen', 'hires_seen', 'beam_line', 'beam_column',
                       'irq_latches', 'irq_overshot', 'visible_frames')
    if 'gun_kind' in native or 'gun_kind' in reference:
        fields += ('gun_kind', 'gun_light_hits', 'gun_interrupts', 'gun_button_reads')
        fields += (('gun_latched_hv', 'gun_buttons_latched', 'gun_button_packets', 'gun_trigger_packets') if system_id == 'md' else
                   ('gun_packet', 'gun_latched_h', 'gun_latched_v'))
        if native.get('gun_kind') or reference.get('gun_kind'):
            fields += (('gun_port_control', 'gun_external_irq_enabled') if system_id == 'md' else
                       ('gun_latch_enabled',))
    differences = [field for field in fields if native.get(field) is None or reference.get(field) is None
                   or native[field] != reference[field]]
    counters = ('native_entries', 'interpreted_opcodes')
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
              standard_override=None, md_advanced_scan=False, publish_result=True, emit=print) -> Path:
    from .artwork import prepare_icon
    from .core import executable_name
    from .metadata import write_game_metadata
    from .paths import data_directory, games_root, boxart_cache_directory
    if profile is not None:
        raise ConversionError('16-bit profiles use pinned game-specific analysis, not Sega Z80 TOML files.')
    if not 1 <= frames <= 10000 or not 1 <= passes <= 10:
        raise ConversionError('Choose 1–10 passes and 1–10000 frames per test.')
    rom = conversion_rom(rom_path, system_id, standard_override)
    cartridge_profile = (megadrive if system_id == 'md' else supernintendo).profile_for(rom)
    standard = (megadrive if system_id == 'md' else supernintendo).video_standard(rom, standard_override)
    gun = guns16.gun_game(system_id, rom.crc32, rom.path.name)
    advanced = system_id == 'md' and bool(md_advanced_scan)
    if output is None:
        from .batch import identify, convert_batch
        item = identify(rom_path, system_id)
        item.title = title or cartridge_profile['title']
        item.cover = cover
        result = convert_batch([item], games_root(), frames=frames, passes=passes,
            language=language, boxart_dir=boxart_dir, online_cover=online_cover,
            use_cover=use_cover, icon_tags=icon_tags, standard_override=standard_override,
            md_advanced_scan=advanced, emit=emit)
        if result['failed']:
            raise ConversionError(result['games'][0]['message'])
        return Path(result['games'][0]['executable'])
    started = time.perf_counter()
    title = title or cartridge_profile['title']
    name = 'Mega Drive' if system_id == 'md' else 'Super Nintendo'
    emit(f'{name}: experimental {title} {standard.upper()} conversion; '
         + ('using exact-ROM catalogue settings.' if cartridge_profile.get('source') == 'catalogue'
            else 'generating a profile from this cartridge; no catalogue entry required.'))
    emit('68000 and Z80 sound CPU use guarded native code.' if system_id == 'md' else
         '65816 and SPC700 sound CPU use guarded native code. Hardware fidelity is a separate check.')
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
        (project / 'game_legal.md').write_text(_notice(engine, system_id,
            legacy_smw=cartridge_profile.get('legacy_functions', False)), encoding='utf-8')
        (project / 'game_identity.bin').write_bytes(b'[Retro-Recomp]\0' + rom.sha256.encode('ascii') + b'\0')
        with (project / 'game_resources.rc').open('a', encoding='utf-8') as rc:
            rc.write('102 RCDATA "game_legal.md"\n' + f'103 RCDATA "{rom_file.name}"\n' +
                     '104 RCDATA "game_identity.bin"\n')
    learn = megadrive.learn_entries if system_id == 'md' else supernintendo.learn_ram_variants
    gun_menu = 't2' if gun and gun.system == 'md' and gun.title == 'T2 - The Arcade Game' else None
    advanced_frames = max(frames, 6000) if advanced else 0
    early_start_frames = 1800 if advanced else 0
    if advanced:
        emit(f'Mega Drive advanced scan: adds a {advanced_frames}-frame varied-input replay '
             f'and a {early_start_frames}-frame early-start replay on every pass, '
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
            reference = probe16(executable, directory, native['frames'], **options)
            comparisons.append({'scenario': native['scenario'], 'frames': native['frames'],
                                'differences': reference_differences(system_id, native, reference)})
        if any(result['differences'] for result in comparisons):
            atomic_json(checks_dir / 'native-validation.json', {'comparisons': comparisons})
            raise ConversionError(f'{name} native CPU/video/audio reference comparison failed. '
                                  f'Previous export preserved; see {checks_dir}.')
        return comparisons

    for attempt in range(passes):
        executable = prepare16(rom_path, system_id, emit=emit, title=title, resources=resources,
                               standard_override=standard)
        checks_dir = executable.parents[2] / 'checks'
        checks_dir.mkdir(exist_ok=True)
        checks = []
        scenarios = [(frames, dict(play=play, gun_menu=gun_menu)) for play in (False, True)]
        scripts = {}
        if advanced:
            scripts['advanced'] = _md_scan_script(checks_dir, advanced_frames,
                six_buttons=cartridge_profile.get('six_buttons', 'street-fighter' in cartridge_profile['id']),
                gun_menu=gun_menu)
            scripts['early-start'] = _md_early_start_script(checks_dir, early_start_frames)
            scenarios.append((advanced_frames, dict(play=True, gun_menu=gun_menu,
                                                   scenario='advanced', input_script=scripts['advanced'])))
            scenarios.append((early_start_frames, dict(play=True, gun_menu=gun_menu,
                scenario='early-start', input_script=scripts['early-start'])))
        for budget, options in scenarios:
            check = probe16(executable, checks_dir, budget, **options)
            check['native_counter_unit'] = 'main CPU opcodes'
            checks.append(check)
            emit(f"{name} {check['scenario']}: {check['frames']} frames, "
                 f"{check['interpreted_opcodes']} interpreted main CPU opcodes. Sound CPU: " +
                 f"{check['audio_interpreted_opcodes']} interpreted {'Z80' if system_id == 'md' else 'SPC700'} opcodes.")
        history.append({'pass': attempt + 1, 'checks': [
            {key: check.get(key) for key in ('scenario', 'frames', 'native_entries', 'interpreted_opcodes',
             'rom_fallback_opcodes', 'ram_fallback_opcodes', 'audio_native_opcodes',
             'audio_interpreted_opcodes', 'audio_native_cycles', 'audio_interpreted_cycles')} for check in checks]})
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
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'status': 'experimental',
        'system': {'id': system_id, 'name': name}, 'rom': rom.metadata(),
        'cartridge_profile': {'source': cartridge_profile.get('source', 'cartridge'),
                              'id': cartridge_profile.get('id'),
                              'catalogue_required': False,
                              'limitations': cartridge_profile.get('limitations', [])},
        'compiler': {'repository': REPOSITORIES[system_id][0], 'revision': REPOSITORIES[system_id][1],
                     'license': 'PolyForm Noncommercial 1.0.0'},
        'final_checks': checks, 'passes': history, 'reference_vdp_trace_match': None,
        'advanced_scan': {'enabled': advanced, 'additional_frames': advanced_frames + early_start_frames,
                          'scenario': 'advanced' if advanced else None,
                          'scenario_frames': {'advanced': advanced_frames, 'early-start': early_start_frames} if advanced else {},
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
        'native_percentage': [round(100 * check['native_entries'] /
            max(1, check['native_entries'] + check['interpreted_opcodes']), 6) for check in checks],
        'peripheral': {'device': gun.device, 'port': 2, 'host_input': 'mouse'} if gun else None,
        'game_states': {'supported': True, 'save_key': 'F8', 'load_key': 'F9', 'slots': 1,
                        'compatibility': 'same ROM, video standard and runtime ABI'},
        'runtime_learning': False,
        'physical_latency_measured': False, 'artwork': artwork, 'windows_metadata': metadata,
        'executable': executable_name(title), 'build_executable': str(executable),
        'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
    atomic_json(output / 'conversion-report.json', report)
    return executable
