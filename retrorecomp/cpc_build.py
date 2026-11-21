"""The Amstrad CPC on the banked Z80 chain: the generated bodies of the player's firmware, the staging of the machine's files
beside them (docs/AMSTRAD_CPC.md). MIT, Retro-Recomp.

* The generator is the shared banked Z80 generator built for the CPC's own machine description (systems/amstrad_cpc.py,
  `CPC_MACHINE`: a region map of four 16 KiB regions, the system ROM as source 0 and AMSDOS as source 1, the CPC's costs in
  whole microseconds), in its own folders (`z80_chain_build.generator`).
* Source 0 is the player's 32 KiB system ROM as it is: bank 0 the OS (shown at 0000h), bank 1 BASIC (shown at C000h); the
  machine takes its two halves. Source 1 is AMSDOS (the upper ROM 7). A CPC game runs from RAM, loaded from its disk: what the
  interpreter runs there is learned (`--learn`) and translated with byte guards on the next generation, as the MSX does.
* The reference copy of the interpreter counts the CPC's costs (`z80_chain_build.generate_bodies` passes `Z80Machine.costs`).

Game role, the cpc group of retrorecomp/stamp_inputs.py. It imports nothing of the converter at load time.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import z80_chain_build

GAME_TOML = '''# Amstrad CPC: the system ROM is source 0 of the region map; AMSDOS is named in banked.sources.
[game]
output_prefix = "game"
platform = "sms"
rom = "rom.sms"
crc32 = 0x00000000
[mapper]
kind = "sega"
[functions]
extra = []
blacklist = []
'''
# The machine's C sources, compiled into every program, and the files they include; the uPD765 and the DSK reader, from
# native/upd765 (machine-neutral), staged with them.
MACHINE_SOURCES = ('cpc_machine.c', 'cpc_crtc.c', 'cpc_gate_array.c', 'cpc_ppi.c', 'cpc_state.c')
MACHINE_FILES = (*MACHINE_SOURCES, 'cpc_machine.h', 'cpc_bus.h', 'cpc_crtc.h', 'cpc_gate_array.h', 'cpc_ppi.h', 'cpc_state.h', 'cpc_glue.inc', 'cpc_headless.inc')
DISK_SOURCES = ('upd765.c', 'dsk_image.c')
DISK_FILES = (*DISK_SOURCES, 'upd765.h', 'dsk_image.h')
CHAIN_FILES = ('z80_chain_glue.inc', 'audio_box.h', 'state_io.h')
# The shared chips, each a folder of native/: (folder, the sources compiled into every program, the other files staged with them).
SHARED_MODULES = (('ay38910', ('ay38910.c',), ('ay38910.h',)),)
SHARED_SOURCES = tuple(name for _, sources, _ in SHARED_MODULES for name in sources)
LOOP = 'cpc_banked_loop.inc'
ACCEPT = 'cpc_reference_accept'
# The three programs of a work folder: the native check, the reference runner, the game.
MAINS = ('cpc_native_main.c', 'cpc_reference_main.c', 'cpc_player.c')
# The host kit's companions the game compiles or includes beside it, from native/, and the computers' adapter files staged with
# the CPC's adapter (native/hostkit/adapters: the shared keyboard and mouse, the boot key sequence, the CPC's key table).
KIT_FILES = ('retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc',
             'retro_keyboard.h', 'display_settings.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h',
             'stereo_fir.h', 'audio_output.inc', 'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h',
             'platform_io.c', 'platform_io.h', 'embedded_resources.h', 'console16_video.h', 'runtime_feedback.h',
             'runtime_feedback.c', 'runtime_feedback_sdl.h', 'state_envelope.h', 'gamestate.h')
ADAPTER_FILES = ('rrhk_computer.inc', 'rrhk_boot_keys.h', 'rrhk_cpc_keys.h')
# The game's resources (native/cpc_machine/cpc_player.c): its disks, then the player's own system ROM and AMSDOS.
RESOURCE_DISKS, RESOURCE_SYSTEM, RESOURCE_AMSDOS = 103, 104, 105
BUILD_TIMEOUT = 2 * 3600


class CpcBuildError(RuntimeError):
    """The generator, the build or a run failed."""


def sources(system: bytes, amsdos: bytes) -> tuple[bytes, tuple[tuple[str, bytes], ...]]:
    """(source 0, the other sources) as the generator reads them: the 32 KiB system ROM, then AMSDOS. Their sizes are checked
    (retrorecomp/cpc_firmware.py has already checked their digests)."""
    from .cpc_firmware import AMSDOS_BYTES, SYSTEM_BYTES
    if len(system) != SYSTEM_BYTES or len(amsdos) != AMSDOS_BYTES:
        raise CpcBuildError('The CPC firmware is a 32 KiB system ROM and a 16 KiB AMSDOS ROM.')
    from .systems.amstrad_cpc import CPC_MACHINE
    return CPC_MACHINE.regions.image(system), (('amsdos.rom', CPC_MACHINE.regions.image(amsdos)),)


def generate(work: Path, system: bytes, amsdos: bytes, emit: Callable[[str], None] = print, *, keep_rom: bool = True) -> None:
    """The bodies of the firmware in `work/generated`, with the learned patterns; the reference copy and the loop beside them."""
    from .systems.amstrad_cpc import CPC_MACHINE
    first, others = sources(system, amsdos)
    z80_chain_build.generate_bodies(work, CPC_MACHINE, first, others, GAME_TOML, emit, loop_name=LOOP, accept=ACCEPT,
                                    keep_rom=keep_rom, error=CpcBuildError)


def stage_sources(work: Path, game: bool = False) -> None:
    """The machine's files, the disk controller's, the chain's glue and the three mains beside the generated bodies; with
    `game` the host kit too (its shell, the CPC's adapter and the computers' adapter files, the kit's companions)."""
    from .paths import ASSETS
    native = ASSETS / 'native'
    z80_chain_build.stage_files(work, ((native / 'cpc_machine', (*MACHINE_FILES, *MAINS)), (native / 'upd765', DISK_FILES),
                                       (native, (*CHAIN_FILES, *(KIT_FILES if game else ()))),
                                       *((native / folder, (*sources, *files)) for folder, sources, files in SHARED_MODULES)))
    if game:
        from . import hostkit
        hostkit.stage(work, 'cpc')
        z80_chain_build.stage_files(work / 'hostkit' / 'adapters', ((native / 'hostkit' / 'adapters', ADAPTER_FILES),))


def project_cmake(version: str, game: bool) -> str:
    """The project: `cpc_reference` (the reference interpreter on the board) and `cpc_check` (the generated bodies, the step
    loop, the headless native run); with `game` the game too (the same bodies and board, the host kit, SDL2)."""
    machine = ' '.join((*MACHINE_SOURCES, *DISK_SOURCES, *SHARED_SOURCES))
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroCpc LANGUAGES C)',
        'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        f'add_executable(cpc_reference cpc_reference_main.c {machine} runtime_reference.c)',
        'file(GLOB bodies "generated/game_banked_ops_*.c")',
        'add_library(cpc_bodies OBJECT generated/game_banked_index.c ${bodies})',
        'target_include_directories(cpc_bodies PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        'target_compile_definitions(cpc_bodies PRIVATE SMSRECOMP_BANKED_AOT)',
        f'add_executable(cpc_check cpc_native_main.c {machine} runtime_reference.c $<TARGET_OBJECTS:cpc_bodies>)',
        'foreach(target cpc_reference cpc_check)',
        '  target_include_directories(${target} PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated")',
        '  target_compile_definitions(${target} PRIVATE SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS)',
        '  if(NOT WIN32)', '    target_link_libraries(${target} PRIVATE m)', '  endif()',
        'endforeach()',
    ]
    if game:
        from . import hostkit
        kit = ' '.join(hostkit.sources('cpc'))
        lines += [
            'if(WIN32)', '  enable_language(RC)', 'else()', '  enable_language(ASM)', 'endif()',
            'find_package(SDL2 CONFIG REQUIRED)',
            f'add_executable(game cpc_player.c {machine} runtime_reference.c retro_menu.c platform_io.c runtime_feedback.c {kit}',
            '  $<TARGET_OBJECTS:cpc_bodies>)',
            'target_include_directories(game PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "${CMAKE_CURRENT_SOURCE_DIR}/generated"',
            '  "${CMAKE_CURRENT_SOURCE_DIR}/hostkit/adapters")',
            'if(WIN32)', '  target_sources(game PRIVATE content.rc)',
            '  target_link_libraries(game PRIVATE shell32 user32 gdi32)',
            'else()', '  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)',
            '  target_link_libraries(game PRIVATE m)', 'endif()',
            'target_link_libraries(game PRIVATE SDL2::SDL2-static)',
            f'target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED SMSRECOMP_BANKED_AOT _CRT_SECURE_NO_WARNINGS '
            f'[[RR_RECOMP_VERSION="{version}"]])',
            'if(MSVC)', '  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)', 'endif()',
            'if(WIN32 AND NOT MSVC)',
            '  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)', 'endif()',
        ]
    return '\n'.join(lines) + '\n'


def build(work: Path, targets: tuple[str, ...], emit: Callable[[str], None] = print) -> dict[str, Path]:
    """Configure and build `targets` of the project in `work` (the converter's SDL2 for the game)."""
    from . import __version__, core
    from .platforms import build_executable, sdl_install
    game = 'game' in targets
    z80_chain_build.write_if_changed(work / 'CMakeLists.txt', project_cmake(__version__, game).encode('utf-8'))
    cmake, generator_kind = core.toolchain()
    log = work / 'build.log'
    extra = [f'-DCMAKE_PREFIX_PATH={Path(sdl_install()).as_posix()}'] if game else []
    core.run([cmake, '-S', work, '-B', work / 'build', '-G', generator_kind, *core.cmake_target_args(),
              '-DCMAKE_BUILD_TYPE=Release', *extra], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    for target in targets:
        core.run([cmake, '--build', work / 'build', '--config', 'Release', '--target', target, '--parallel',
                  core.build_jobs()], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    return {target: build_executable(work / 'build', target) for target in targets}


def prepare_game(work: Path, title: str, identity: str, disks: list[bytes], system: bytes, amsdos: bytes, start_text: str, *,
                 crtc: int = 1, boot_frame: int | None = None, presentation: dict | None = None,
                 emit: Callable[[str], None] = print) -> dict:
    """The game's resources beside the project: its disks (103, one image after the other), the player's system ROM (104) and
    AMSDOS (105), the notices (203), the identity (205), the Windows metadata and icon, cpc_game.h and boot_keys.h (the start
    command `start_text`, typed from frame `boot_frame`). `identity` is the SHA-256 of the game's first disk. `presentation`
    (rom_path, cover, use_cover, online_cover, boxart_dir) gives the icon its cover as on the other machines."""
    import json
    from . import cpc_keys
    from .core import executable_name
    from .metadata import write_game_metadata
    from .notices import notice_text
    from .resources import embed_resources
    if not disks:
        raise CpcBuildError('A CPC game has at least one disk.')
    sources(system, amsdos)                                  # the sizes
    write = z80_chain_build.write_if_changed
    write(work / 'disks.bin', b''.join(disks))
    write(work / 'system.rom', system)
    write(work / 'amsdos.rom', amsdos)
    write(work / 'notices.txt', notice_text('cpc').encode('utf-8'))
    write(work / 'runtime_feedback_config.h',
          f'#define RR_FEEDBACK_SYSTEM "cpc"\n#define RR_FEEDBACK_IDENTITY "{identity}"\n'.encode('ascii'))
    write(work / 'export-identity.bin', b'[Retro-Recomp]\0' + identity.encode('ascii') + b'\0')
    artwork = {'embedded': False, 'source': 'disabled'}
    if presentation is not None:
        from .artwork import prepare_icon
        from .core import ROOT
        from .paths import boxart_cache_directory
        artwork = prepare_icon(work, presentation['rom_path'], title, presentation.get('boxart_dir') or ROOT / 'BoxArt',
                               explicit=presentation.get('cover'), online=presentation.get('online_cover', True),
                               enabled=presentation.get('use_cover', True), cache_directory=boxart_cache_directory('cpc'),
                               system_id='cpc', emit=emit)
    (work / 'artwork.json').write_text(json.dumps(artwork, indent=2), encoding='utf-8')
    metadata = write_game_metadata(work, title, executable_name(title), light_phaser=False, icon=bool(artwork['embedded']),
                                   standard='pal', system_id='cpc')
    write(work / 'content.rc', (f'#pragma code_page(65001)\n{RESOURCE_DISKS} RCDATA "disks.bin"\n'
                                f'{RESOURCE_SYSTEM} RCDATA "system.rom"\n{RESOURCE_AMSDOS} RCDATA "amsdos.rom"\n'
                                '203 RCDATA "notices.txt"\n205 RCDATA "export-identity.bin"\n#include "game_resources.rc"\n')
          .encode('utf-8'))
    embed_resources(work, {RESOURCE_DISKS: work / 'disks.bin', RESOURCE_SYSTEM: work / 'system.rom',
                           RESOURCE_AMSDOS: work / 'amsdos.rom', 203: work / 'notices.txt', 205: work / 'export-identity.bin'})
    write(work / 'cpc_game.h', ('#pragma once\n'
          f'#define RR_CPC_TITLE {json.dumps(title)}\n#define RR_CPC_IDENTITY "{identity}"\n#define RR_CPC_CRTC {int(crtc)}\n'
          f'#define RR_CPC_DISKS {len(disks)}\n#define RR_CPC_DISK_MAX {max(len(disk) for disk in disks)}\n'
          f'#define RR_CPC_DISK_SIZES {{{", ".join(str(len(disk)) for disk in disks)}}}\n').encode('utf-8'))
    frame = cpc_keys.BOOT_FRAME if boot_frame is None else boot_frame
    write(work / 'boot_keys.h', cpc_keys.boot_keys_header(start_text, frame).encode('utf-8'))
    return {'artwork': artwork, 'windows_metadata': metadata}
