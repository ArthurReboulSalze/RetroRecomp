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
from . import megadrive

REPOSITORIES = {
    'md': ('mstan/segagenesisrecomp', '00c60bc855a7998f92e5614585d52bca8fffcaf2', 'segagenesisrecomp'),
    'snes': ('RetroPortingToolKit/snesrecomp', 'a00df26a87831113fec91b9225bf16b049d40775', 'snesrecomp'),
    'smw': ('mstan/SuperMarioWorldRecomp', '8dedb2869414f20d1d86d34081be26594560cc15', 'smwrecomp'),
}
SUPPORTED = {
    'md': ('46160baa06362c711c9f1a5017cb7371026444936c8af5e93a78996cf32ff2a6', 'Sonic the Hedgehog'),
    'snes': ('0838e531fe22c077528febe14cb3ff7c492f1f5fa8de354192bdff7137c27f5b', 'Super Mario World'),
}


def qualified_rom(path: Path, system_id: str, standard_override: str | None = None):
    if system_id not in SUPPORTED:
        raise ConversionError('Unknown 16-bit console profile.')
    rom = (read_megadrive_rom if system_id == 'md' else read_snes_rom)(path)
    if system_id == 'md':
        megadrive.profile_for(rom)
        megadrive.vectors(rom)
    elif rom.sha256 != SUPPORTED[system_id][0]:
        raise ConversionError(f'{system_id.upper()} integration is experimental: only the verified '
                              f'{SUPPORTED[system_id][1]} ROM is currently supported. '
                              'This cartridge was identified, but will not be compiled with another game\'s profile.')
    if standard_override and standard_override != 'ntsc':
        raise ConversionError('This 16-bit integration proof is qualified for NTSC only; PAL is not enabled yet.')
    return rom


@serialized_setup
def dependencies16(system_id: str, emit):
    cmake, generator = toolchain()
    sdl = ROOT / '.deps/SDL/install'
    if not (sdl / 'lib/SDL2-static.lib').is_file():
        from .core import dependencies
        _, sdl, cmake, generator = dependencies(emit)
    names = (system_id, 'smw') if system_id == 'snes' else (system_id,)
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
        if not compiler.is_file():
            # Use the installed stable toolchain instead of silently downloading
            # the upstream development pin. The crate requires Rust >= 1.85.
            emit('Building the SNES native analyzer with installed Rust…')
            if not shutil.which('cargo'):
                raise ConversionError('The experimental SNES analyzer requires installed Rust >= 1.85 (stable toolchain).')
            run(['cargo', '+stable', 'build', '--locked', '--release', '--bin', 'snesrecomp-analyze'],
                cwd=engine / 'recompiler-rs', log=ROOT / '.build/snes-analyzer.log', timeout=600)
    return engine, compiler, sdl, cmake, generator


def _write_build(project: Path, engine: Path, system_id: str, title: str) -> None:
    for name in ('retro_console16.h', 'console16_main.c', 'console16_host_ui.c', 'retro_menu.c', 'retro_menu.h', 'retro_keyboard.h', 'scanlines.h', f'{system_id}_backend.c'):
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
        step_aot = '#define RR_MD_STEP_AOT 1' in (project / 'retro_md_game.h').read_text(encoding='utf-8')
        if step_aot:
            for name in ('md_native_steps.h', 'md_step_dispatch.c'):
                shutil.copy2(ASSETS / 'native' / name, project / name)
        # Two host-only adaptations in private source copies. Never edit the
        # dependency checkout: count exact interpreter opcodes; remove legacy
        # sidecar deletion performed at game startup.
        glue = (engine / 'runner/glue.c').read_text(encoding='utf-8')
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
            glue = glue.replace('    if (genesis_force_interp()) {\n        uint32_t entry',
                '    if (genesis_force_interp() || RR_MD_STEP_AOT) {\n        uint32_t entry', 1)
            glue = glue.replace('        /* NOTE: no per-instruction check_cycle_budget()',
                '        check_cycle_budget();\n        /* NOTE: legacy function-AOT has no per-instruction check_cycle_budget()', 1)
        (native / 'glue.c').write_text(glue, encoding='utf-8')
        interp = (engine / 'runner/m68k_interp.c').read_text(encoding='utf-8')
        interp = interp.replace('static void cov_mark(uint32_t pc) {',
            'extern void rr16_note_interpreted(void);\nstatic void cov_mark(uint32_t pc) {\n    rr16_note_interpreted();', 1)
        if step_aot:
            from .megadrive_codegen import adapt_interpreter
            interp = adapt_interpreter(interp)
        (native / 'm68k_interp.c').write_text(interp, encoding='utf-8')
        audio = (engine / 'runner/audio.c').read_text(encoding='utf-8')
        audio = audio.replace('want.samples  = 1024;', 'want.samples  = 512;')
        audio = audio.replace('cfg.preroll_ms     = 200.0;',
            'cfg.target_ms = 25.0; cfg.em_low_ms = 5.0; cfg.em_high_ms = 80.0;\n    cfg.preroll_ms = 25.0;')
        audio = audio.replace('a ~200 ms boot pre-roll', 'a 25 ms boot pre-roll')
        (native / 'audio.c').write_text(audio, encoding='utf-8')
        sources = ['sim_step.c', 'fiber_compat.c', 'crash_report.c', 'chip_trace.c', 'cmd_server_stub.c',
                   'rb_state.c',
                   'cosim_state.c', 'cosim_cycles.c', 'audio/event_queue.c', 'audio/ym2612_ymfm.cpp',
                   'audio/sn76489.c', 'audio/mixer.c', 'audio/observability.c', 'audio/audio_shadow.c',
                   'audio/fm_shadow.cpp', 'video/color_lut.c', 'video/genesis_vdp.c', 'video/genesis_bus.c',
                   'video/genesis_machine.c', 'external/superzazu/z80.c']
        sources += [f'external/ymfm/src/{name}.cpp' for name in ('ymfm_opn', 'ymfm_ssg', 'ymfm_adpcm', 'ymfm_pcm')]
        source_text = '\n'.join(f'  "{prefix}/runner/{source}"' for source in sources)
        generated_glob = ('"steps/*.c" "generated/*_layout.c"' if step_aot else
                          '"generated/*_part*.c" "generated/*_dispatch.c" "generated/*_layout.c"')
        step_sources = 'md_step_dispatch.c' if step_aot else ''
        common += f'''file(GLOB GENERATED CONFIGURE_DEPENDS {generated_glob})
add_executable(game WIN32 console16_main.c console16_host_ui.c retro_menu.c md_backend.c
  native/glue.c native/m68k_interp.c native/audio.c game_resources.rc {step_sources} ${{GENERATED}}
{source_text}
  "{prefix}/recompiler/src/m68k_decoder.c" "{prefix}/recompiler/src/rom_parser.c")
target_include_directories(game PRIVATE . "{prefix}/runner" "{prefix}/runner/include"
  "{prefix}/runner/video" "{prefix}/runner/external/superzazu" "{prefix}/runner/external/clowncommon"
  "{prefix}/runner/external/ymfm/src" "{prefix}/recompiler/src" "{prefix}/external/m68k-recomp-core/src")
target_compile_definitions(game PRIVATE RR16_MD=1 OWN_BACKEND=1 ENABLE_RECOMPILED_CODE=1 INCLUDE_GENERATED_CODE=1 GENESIS_BATCHED_PLANES=0)
target_link_options(game PRIVATE /CETCOMPAT:NO)
'''
    else:
        from .snes_codegen import generate, adapt_core, adapt_bridge
        from .cartridge16 import read_snes_rom
        generate(engine, project, read_snes_rom(project / 'smw.sfc'))
        shutil.copy2(ASSETS / 'native/snes_native_steps.h', project / 'snes_native_steps.h')
        shutil.copy2(ROOT / '.deps/smwrecomp/src/variables.h', project / 'variables.h')
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
add_executable(game WIN32 console16_main.c console16_host_ui.c retro_menu.c snes_backend.c
  game_resources.rc ${{GENERATED}} ${{SNESRECOMP_RUNNER_SOURCES}})
target_include_directories(game PRIVATE . generated ${{SNESRECOMP_RUNNER_INCLUDE_DIRS}} "{prefix}/runner/src/desktop")
target_link_libraries(game PRIVATE ${{SNESRECOMP_RUNNER_LIBRARIES}})
snesrecomp_target_mmx_config(game)
target_compile_definitions(game PRIVATE RR16_MD=0 SNESRECOMP_SDL3=0)
'''
    # CMake bracket literals do not interpret quotes/backslashes in a ROM title.
    title_literal = json.dumps(title, ensure_ascii=True)
    common += f'''target_compile_definitions(game PRIVATE [[RR_GAME_TITLE={title_literal}]] SDL_MAIN_HANDLED)
target_include_directories(game PRIVATE ${{SDL2_INCLUDE_DIRS}} "${{SDL2_INCLUDE_DIRS}}/..")
target_link_libraries(game PRIVATE SDL2::SDL2-static ws2_32 comdlg32)
target_compile_options(game PRIVATE /W2 /utf-8 /MP4 /wd4996 /wd4244 /wd4267 /wd4013)
'''
    (project / 'CMakeLists.txt').write_text(common, encoding='utf-8')


def prepare16(path: Path, system_id: str, *, emit=print, title=None, resources=None):
    rom = qualified_rom(path, system_id)
    engine, compiler, sdl, cmake, generator = dependencies16(system_id, emit)
    md_profile = megadrive.profile_for(rom) if system_id == 'md' else None
    project = ROOT / '.build' / ('md-' + md_profile['id'] if md_profile else 'snes-smw')
    project.mkdir(parents=True, exist_ok=True)
    rom_file = project / ('cartridge.bin' if system_id == 'md' else 'smw.sfc')
    rom_file.write_bytes(rom.data)
    title = title or (md_profile['title'] if md_profile else SUPPORTED[system_id][1])
    cache = project / 'generation-identity.json'
    identity = {'rom': rom.sha256, 'engine': REPOSITORIES[system_id][1],
                'game': REPOSITORIES['smw'][1] if system_id == 'snes' else REPOSITORIES['md'][1],
                'schema': 1}
    if system_id == 'md':
        entries = megadrive.read_entries(rom)
        megadrive.write_profile(project, engine, rom, entries)
        megadrive.write_spec(project, rom, title)
        identity = megadrive.analysis_identity(project, REPOSITORIES[system_id][1], rom)
    try:
        reuse = json.loads(cache.read_text(encoding='utf-8')) == identity and any((project / 'generated').glob('*.c'))
    except (OSError, ValueError):
        reuse = False
    if reuse:
        emit('Reusing native source analysis for this exact ROM and pinned engine.')
    elif system_id == 'md':
        megadrive.generate(compiler, project, rom_file)
    else:
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
    if resources:
        resources(project, engine, rom, rom_file)
    else:
        (project / 'game_resources.rc').write_text(f'103 RCDATA "{rom_file.name}"\n', encoding='utf-8')
    run([cmake, '-S', project, '-B', project / 'build', '-G', generator, '-A', 'x64',
         f'-DCMAKE_PREFIX_PATH={sdl.as_posix()}'], log=project / 'build.log', timeout=600)
    run([cmake, '--build', project / 'build', '--config', 'Release', '--parallel', '4'],
        log=project / 'build.log', timeout=1200)
    return project / 'build/Release/game.exe'


def _notice(engine: Path, system_id: str) -> str:
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
                       ('SuperMarioWorldRecomp', ROOT / '.deps/smwrecomp/LICENSE'),
                       ('SNES third-party attribution', engine / 'THIRD_PARTY_ATTRIBUTION.md')]
        components += [('Color-science core ' + name, engine / 'third_party/psxrecomp_color_lut' / name)
                       for name in ('LICENSE-MIT.txt', 'LICENSE-APACHE-2.0.txt',
                                    'LICENSE-POLYFORM-NONCOMMERCIAL-1.0.0.txt')]
        assembly_notice = ''
    return ('RetroRecomp 16-bit test executable. Component licences remain separate.\n\n' +
            '\n\n'.join(f'## {name}\n\n{source.read_text(encoding="utf-8")}' for name, source in components) +
            '\n\n' + assembly_notice)


def probe16(executable: Path, directory: Path, frames: int, *, play=False, reference=False) -> dict:
    executable, directory = executable.resolve(), directory.resolve()
    scenario = 'play' if play else 'demo'
    report = directory / f'{scenario}{"-reference" if reference else ""}.json'
    command = [executable, '--frames', str(frames), '--report', report]
    if play:
        command.append('--play')
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
    return {'scenario': scenario, **data}


def reference_differences(system_id: str, native: dict, reference: dict) -> list[str]:
    """Require every diagnostic field; absent data must never validate an export."""
    fields = ('frame_hash', 'sequence_hash', 'cpu_hash', 'ram_hash', 'vram_hash', 'cram_hash', 'cpu_pc')
    fields += (('vsram_hash', 'vdp_register_hash') if system_id == 'md' else
               ('oam_hash', 'high_oam_hash', 'apu_ram_hash', 'cpu_cycles', 'master_cycles', 'apu_cycles'))
    differences = [field for field in fields if native.get(field) is None or reference.get(field) is None
                   or native[field] != reference[field]]
    counters = ('native_entries', 'interpreted_opcodes')
    if (any(check.get(key) is None for check in (native, reference) for key in counters)
            or sum(native[key] for key in counters) != sum(reference[key] for key in counters)):
        differences.append('retired_instruction_count')
    return differences


def convert16(rom_path: Path, *, system_id: str, title=None, output=None, profile=None,
              passes=3, frames=3600, backend='banked', language='en', cover=None,
              boxart_dir=None, online_cover=True, use_cover=True, icon_tags=True,
              standard_override=None, publish_result=True, emit=print) -> Path:
    from .artwork import prepare_icon
    from .core import executable_name
    from .metadata import write_game_metadata
    from .paths import data_directory, games_root
    if profile is not None:
        raise ConversionError('16-bit profiles use pinned game-specific analysis, not Sega Z80 TOML files.')
    if not 1 <= frames <= 10000 or not 1 <= passes <= 10:
        raise ConversionError('Choose 1–10 passes and 1–10000 frames per test.')
    rom = qualified_rom(rom_path, system_id, standard_override)
    if output is None:
        from .batch import identify, convert_batch
        item = identify(rom_path, system_id)
        item.title = title or (megadrive.profile_for(rom)['title'] if system_id == 'md' else SUPPORTED[system_id][1])
        item.cover = cover
        result = convert_batch([item], games_root(), frames=frames, passes=passes,
            language=language, boxart_dir=boxart_dir, online_cover=online_cover,
            use_cover=use_cover, icon_tags=icon_tags, standard_override=standard_override, emit=emit)
        if result['failed']:
            raise ConversionError(result['games'][0]['message'])
        return Path(result['games'][0]['executable'])
    started = time.perf_counter()
    title = title or (megadrive.profile_for(rom)['title'] if system_id == 'md' else SUPPORTED[system_id][1])
    name = 'Mega Drive' if system_id == 'md' else 'Super Nintendo'
    emit(f'{name}: experimental {title} NTSC integration; exact cartridge profile verified.')
    emit('Sound CPU remains interpreted. Native CPU coverage and hardware fidelity are separate checks.')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    artwork = {}
    metadata = {}
    def resources(project, engine, cartridge, rom_file):
        artwork.update(prepare_icon(project, cartridge.path, title,
            (boxart_dir or ROOT / 'BoxArt' / name).resolve(), explicit=cover,
            online=online_cover, enabled=use_cover, cache_directory=data_directory() / 'BoxArt' / system_id,
            system_id=system_id, emit=emit))
        metadata.update(write_game_metadata(project, title, executable_name(title),
            light_phaser=False, icon=artwork['embedded'], standard='ntsc', system_id=system_id))
        (project / 'game_legal.md').write_text(_notice(engine, system_id), encoding='utf-8')
        (project / 'game_identity.bin').write_bytes(b'[Retro-Recomp]\0' + rom.sha256.encode('ascii') + b'\0')
        with (project / 'game_resources.rc').open('a', encoding='utf-8') as rc:
            rc.write('102 RCDATA "game_legal.md"\n' + f'103 RCDATA "{rom_file.name}"\n' +
                     '104 RCDATA "game_identity.bin"\n')
    from . import supernintendo
    learn = megadrive.learn_entries if system_id == 'md' else supernintendo.learn_ram_variants
    history, comparisons = [], []
    for attempt in range(passes):
        executable = prepare16(rom_path, system_id, emit=emit, title=title, resources=resources)
        checks_dir = executable.parents[2] / 'checks'
        checks_dir.mkdir(exist_ok=True)
        checks = []
        for play in (False, True):
            check = probe16(executable, checks_dir, frames, play=play)
            check['native_counter_unit'] = 'main CPU opcodes'
            checks.append(check)
            emit(f"{name} {check['scenario']}: {check['frames']} frames, "
                 f"{check['interpreted_opcodes']} interpreted main CPU opcodes. Sound CPU: interpreted.")
        history.append({'pass': attempt + 1, 'checks': [
            {key: check.get(key) for key in ('scenario', 'frames', 'native_entries', 'interpreted_opcodes',
             'rom_fallback_opcodes', 'ram_fallback_opcodes')} for check in checks]})
        if not any(check.get('rom_entries') or check.get('ram_variants') for check in checks) or attempt + 1 == passes:
            break
        added = learn(rom, checks)
        if not added:
            break
        observations = 'ROM entries/RAM byte variants' if system_id == 'md' else 'RAM byte variants'
        emit(f'Pass {attempt + 1}/{passes}: {added} {observations} learned; regenerating native code.')
    reference_dir = checks_dir / 'reference'
    reference_dir.mkdir(exist_ok=True)
    for native in checks:
        reference = probe16(executable, reference_dir, frames,
                            play=native['scenario'] == 'play', reference=True)
        comparisons.append({'scenario': native['scenario'], 'frames': frames,
                            'differences': reference_differences(system_id, native, reference)})
    if any(result['differences'] for result in comparisons):
        atomic_json(checks_dir / 'native-validation.json', {'comparisons': comparisons})
        raise ConversionError(f'{name} native CPU/video reference comparison failed. '
                              f'Previous export preserved; see {checks_dir}.')
    learn(rom, checks)
    emit('Internal CPU/memory/visible-frame reference comparison: matches.')
    report = {'tool': 'Retro-Recomp', 'version': __version__, 'status': 'experimental',
        'system': {'id': system_id, 'name': name}, 'rom': rom.metadata(),
        'compiler': {'repository': REPOSITORIES[system_id][0], 'revision': REPOSITORIES[system_id][1],
                     'license': 'PolyForm Noncommercial 1.0.0'},
        'final_checks': checks, 'passes': history, 'reference_vdp_trace_match': None,
        'native_validation': {'passed': True, 'visible_sequence_match': True,
                              'comparisons': comparisons,
                              'reference_frames': frames, 'reference_kind': 'internal_shared_semantics',
                              'cpu_fidelity_validated': False,
                              'hardware_fidelity_validated': False, 'full_game_validated': False},
        'video_model': {'standard': 'ntsc', 'visible_pixels': [checks[-1].get('visible_width', 320) if system_id == 'md' else 256, 224]},
        'audio_cpu': 'interpreted', 'native_percentage': [round(100 * check['native_entries'] /
            max(1, check['native_entries'] + check['interpreted_opcodes']), 6) for check in checks],
        'game_states': {'supported': False}, 'runtime_learning': False,
        'physical_latency_measured': False, 'artwork': artwork, 'windows_metadata': metadata,
        'executable': executable_name(title), 'build_executable': str(executable),
        'conversion_wall_seconds': round(time.perf_counter() - started, 3)}
    atomic_json(output / 'conversion-report.json', report)
    return executable
