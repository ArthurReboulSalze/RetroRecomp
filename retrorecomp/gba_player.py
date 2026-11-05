"""The Game Boy Advance player: the engine's machine, driven one frame at a time by the host kit (docs/HOST_KIT.md).

The executable of an exported game links four things: the engine's runtime with the cartridge's generated code and the
player's own BIOS code (both derived from files the player owns, so the export stays private to them), the host kit's shell
with the machine's adapter (`native/hostkit/adapters/rrhk_gba.c`), and `native/gba_machine.cpp`, which carries the cartridge
and the system ROM as resources and hands the engine a driver in place of its own window loop (the anchored patches of
`gba_patches.py`, `native/gba_driver.h`). Nothing here changes what the generated code does: this module is a host input.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from . import hostkit
from .conversion_common import write_if_changed
from .core import ConversionError, run
from .paths import ASSETS
from .platforms import build_executable, build_jobs, cmake_target_args

# The shell's own support files (menus, fonts, languages, filters, options) and the machine's two, copied beside the project.
SUPPORT = ('platform_io.c', 'platform_io.h', 'embedded_resources.h', 'retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h',
           'runtime_i18n.h', 'runtime_catalog.inc', 'retro_keyboard.h', 'display_settings.h', 'autofire.h', 'game_options.h',
           'audio_filter.h', 'audio_cushion.h', 'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h',
           'console16_video.h', 'runtime_feedback.h', 'runtime_feedback.c', 'runtime_feedback_sdl.h',
           'gba_machine.h', 'gba_machine.cpp')
ROM_RESOURCE, BIOS_RESOURCE, NOTICES_RESOURCE, IDENTITY_RESOURCE = 201, 202, 203, 205
NOTICE_FILES = (('RetroRecomp', 'LICENSE'), ('gbarecomp', 'licenses/gbarecomp.md'), ('SDL2', 'licenses/SDL2.md'),
                ('xBR', 'licenses/xbr.md'), ('Noto fonts', 'licenses/Noto.md'),
                ('Portable compiler runtime', 'licenses/llvm-mingw.md'))

CMAKE = '''cmake_minimum_required(VERSION 3.20)
project(gba_game C CXX)
if(WIN32)
  enable_language(RC)
else()
  enable_language(ASM)
endif()
set(CMAKE_C_STANDARD 11)
set(GBARECOMP_COMPILER_CACHE OFF CACHE STRING "")
set(GBARECOMP_GENERATED_BIOS_DIR "@BIOS@" CACHE PATH "")
add_subdirectory("@ENGINE@" engine EXCLUDE_FROM_ALL)
include("${CMAKE_CURRENT_BINARY_DIR}/engine/runtime.cmake")
gbarecomp_add_runtime_target(game GAME_GENERATED_DIR "@GAME@")
find_package(SDL2 CONFIG REQUIRED)
target_sources(game PRIVATE gba_machine.cpp retro_menu.c platform_io.c runtime_feedback.c @KIT@)
target_include_directories(game PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}" "@ENGINE@/src/runtime")
target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED RR_RECOMP_VERSION="@VERSION@")
if(WIN32)
  target_sources(game PRIVATE content.rc)
  target_link_libraries(game PRIVATE shell32 user32 gdi32)
else()
  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)
  target_link_libraries(game PRIVATE m)
endif()
target_link_libraries(game PRIVATE SDL2::SDL2-static)
if(WIN32 AND NOT MSVC)
  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)
endif()
'''


def prepare(player: Path, stage: Path, game: Path, bios_code: Path, rom_file: Path, bios_file: Path, *, title: str, name: str,
            sha1: str, sha256: str, version: str, presentation: dict | None = None) -> dict | None:
    """Write the player's project: the sources, the generated header and resources, and the CMake file."""
    player.mkdir(parents=True, exist_ok=True)
    artwork = icon = None
    if presentation is not None:
        from .conversion_common import prepare_game_icon
        from .paths import ROOT, boxart_cache_directory
        artwork = prepare_game_icon(player, presentation['rom_path'], title,
                                    presentation.get('boxart_dir') or ROOT / 'BoxArt/Game Boy Advance',
                                    explicit=presentation.get('cover'), online=presentation.get('online_cover', True),
                                    enabled=presentation.get('use_cover', True), cache_directory=boxart_cache_directory('gba'),
                                    system_id='gba', emit=presentation.get('emit', print))
        icon = artwork['embedded']
    player.mkdir(parents=True, exist_ok=True)
    kit = hostkit.stage(player, 'gba')
    for file in SUPPORT:
        data = (ASSETS / 'native' / file).read_bytes()
        write_if_changed(player / file, data)
    write_if_changed(player / 'gba_game.h', ('#pragma once\n#define RR_GBA_TITLE %s\n#define RR_GBA_NAME %s\n#define RR_GBA_ROM_SHA1 "%s"\n'
                                              '#define RR_GBA_ROM_RESOURCE %d\n#define RR_GBA_BIOS_RESOURCE %d\n'
                                              % (json.dumps(title), json.dumps(name), sha1, ROM_RESOURCE, BIOS_RESOURCE)).encode('utf-8'))
    write_if_changed(player / 'runtime_feedback_config.h', f'#define RR_FEEDBACK_SYSTEM "gba"\n#define RR_FEEDBACK_IDENTITY "{sha256}"\n'.encode('ascii'))
    notices = []
    for label, file in NOTICE_FILES:
        notices.append(f'## {label}\n\n' + (ASSETS / file).read_text(encoding='utf-8'))
    arm_core = stage / 'external/arm-recomp-core/LICENSE'
    if arm_core.is_file():
        notices.append('## arm-recomp-core\n\n' + arm_core.read_text(encoding='utf-8'))
    write_if_changed(player / 'notices.txt', '\n\n'.join(notices).encode('utf-8'))
    write_if_changed(player / 'export-identity.bin', b'[Retro-Recomp]\0' + sha256.encode('ascii') + b'\0')
    from .metadata import write_game_metadata
    metadata = player / 'game_resources.rc'
    previous = (metadata.read_bytes(), metadata.stat().st_mtime_ns) if metadata.is_file() else None
    write_game_metadata(player, title, name + '.exe', light_phaser=False, icon=bool(icon), system_id='gba')
    if previous and metadata.read_bytes() == previous[0]:
        os.utime(metadata, ns=(previous[1], previous[1]))      # the same resource keeps its time: nothing rebuilds
    resources = {ROM_RESOURCE: rom_file, BIOS_RESOURCE: bios_file, NOTICES_RESOURCE: player / 'notices.txt',
                 IDENTITY_RESOURCE: player / 'export-identity.bin'}
    rc = '#pragma code_page(65001)\n' + ''.join(f'{number} RCDATA "{path.resolve().as_posix()}"\n' for number, path in resources.items())
    write_if_changed(player / 'content.rc', (rc + '#include "game_resources.rc"\n').encode('utf-8'))
    from .resources import embed_resources
    embed_resources(player, resources)
    cmake = (CMAKE.replace('@ENGINE@', (stage / 'engine').as_posix()).replace('@GAME@', game.as_posix())
             .replace('@BIOS@', bios_code.as_posix()).replace('@VERSION@', version).replace('@KIT@', ' '.join(kit)))
    write_if_changed(player / 'CMakeLists.txt', cmake.encode('utf-8'))
    return artwork


def build(player: Path, cmake, generator: str, sdl: Path, emit: Callable[[str], None]) -> Path:
    """Compile the player; returns the executable."""
    folder = player / 'build'
    configuration = sdl / 'lib/cmake/SDL2'
    run([cmake, '-S', player, '-B', folder, '-G', generator, *cmake_target_args(), f'-DSDL2_DIR={configuration.as_posix()}',
         '-DCMAKE_BUILD_TYPE=Release'], log=player / 'build.log', timeout=900)
    emit('Building the Game Boy Advance player…')
    run([cmake, '--build', folder, '--target', 'game', '--parallel', build_jobs()], log=player / 'build.log', timeout=7200)
    program = build_executable(folder, 'game')
    if not program.is_file():
        raise ConversionError('The Game Boy Advance player was not built.')
    return program
