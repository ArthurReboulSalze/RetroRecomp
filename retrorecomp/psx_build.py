"""The project of a PlayStation game and its build (Retro-Recomp's own code, MIT).

A game is native/psx_machine/psx_main.c and psx_session.c with the host kit (adapters/rrhk_psx.c), the shared menu and quick-state
files, the prepared Beetle PSX tree (retrorecomp/psx_beetle.py) and the static SDL2 of the converter. The player's BIOS, when he
gave one, is embedded as resource 104; the notices (the GPL text first) as resource 203. The disc is appended to the linked
program afterwards (retrorecomp/psx_pack.py): the executable reads it from itself.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Callable

from . import psx_beetle

BUILD_TIMEOUT = 3600
GAME_FILES = ('platform_io.c', 'platform_io.h', 'embedded_resources.h', 'console16_state.c', 'console16_state.h',
              'console16_video.h', 'retro_menu.c', 'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h',
              'runtime_catalog.inc', 'retro_keyboard.h', 'display_settings.h', 'autofire.h', 'game_options.h',
              'audio_filter.h', 'audio_cushion.h', 'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h')
MACHINE_FILES = ('psx_main.c', 'psx_session.c', 'psx_session.h')
NOTICE_FILES = ('licenses/beetle-psx.md', 'LICENSE', 'licenses/SDL2.md', 'licenses/xbr.md', 'licenses/Noto.md',
                'licenses/UPX.md', 'licenses/llvm-mingw.md')
STATE_SYSTEM = 6      # the quick-state header's machine number (1 MD, 2 SNES, 3 Neo Geo, 4 CPS-1, 5 PC Engine)
FPS = {'ntsc': 59.826, 'pal': 49.761}     # Beetle's frame rates (core_timing_fps), NTSC and PAL


class PsxBuildError(RuntimeError):
    pass


def _write(path: Path, text: str) -> bool:
    from .conversion_common import write_if_changed
    return write_if_changed(path, text.encode('utf-8'))


def state_config(game_sha256: str, title: str, video_mode: str, bios_sha256: str | None) -> str:
    """Quick states load only into the same disc, BIOS, machine revision and session sources."""
    from .core import ASSETS, executable_name
    abi = hashlib.sha256(b'PSX-frame-state-v1:' + psx_beetle.adaptation_digest().encode() + b':' + (bios_sha256 or 'free').encode())
    for name in MACHINE_FILES:
        abi.update((ASSETS / 'native' / 'psx_machine' / name).read_bytes())
    if os.name != 'nt':
        from .platforms import target_id
        abi.update(target_id().encode())
    stem = Path(executable_name(title)).stem if os.name == 'nt' else executable_name(title)
    return (f'#pragma once\n#define RR16_STATE_SYSTEM {STATE_SYSTEM}\n#define RR16_STATE_PAL {int(video_mode == "pal")}\n'
            f'#define RR16_STATE_ROM {json.dumps(game_sha256)}\n#define RR16_STATE_ABI {json.dumps(abi.hexdigest())}\n'
            f'#define RR16_STATE_NAME {json.dumps(stem)}\n')


def game_cmake(tree: Path, version: str) -> str:
    from . import hostkit
    kit = ' '.join(hostkit.sources('psx'))
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPsx LANGUAGES C)',
        'set(CMAKE_C_STANDARD 99)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        f'set(RR_BEETLE_TREE "{tree.as_posix()}")',
        'include("${RR_BEETLE_TREE}/rr_sources.cmake")',
        'add_library(rr_beetle STATIC ${RR_BEETLE_SOURCES})',
        'target_include_directories(rr_beetle PUBLIC ${RR_BEETLE_INCLUDES})',
        'target_compile_definitions(rr_beetle PUBLIC ${RR_BEETLE_DEFINES})',
        'if(MSVC)', '  target_compile_options(rr_beetle PRIVATE /O2 /w)',
        'else()', '  target_compile_options(rr_beetle PRIVATE -O2 -w -fwrapv -fno-strict-aliasing -fno-fast-math)', 'endif()',
        'if(WIN32)', '  enable_language(RC)', 'else()', '  enable_language(ASM)', 'endif()',
        'find_package(SDL2 CONFIG REQUIRED)',
        f'add_executable(game psx_main.c psx_session.c {kit} console16_state.c retro_menu.c)',
        'target_include_directories(game PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")',
        'if(WIN32)', '  target_sources(game PRIVATE content.rc)',
        '  target_link_libraries(game PRIVATE shell32 user32 gdi32)',
        'else()', '  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)',
        '  target_link_libraries(game PRIVATE m)', 'endif()',
        'target_link_libraries(game PRIVATE rr_beetle SDL2::SDL2-static)',
        f'target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED [[RR_RECOMP_VERSION="{version}"]])',
        'if(MSVC)', '  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)', 'endif()',
        'if(WIN32 AND NOT MSVC)',
        '  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)', 'endif()',
    ]
    return '\n'.join(lines) + '\n'


def prepare_game(project: Path, tree: Path, *, title: str, game_sha256: str, video_mode: str, bios=None,
                 presentation: dict | None = None) -> dict:
    """A game project: the session, the kit, the prepared Beetle tree, the player's BIOS (`psx_bios.Bios`, or None: OpenBIOS)."""
    from . import __version__, hostkit
    from .core import ASSETS, executable_name
    from .metadata import write_game_metadata
    project.mkdir(parents=True, exist_ok=True)
    for name in GAME_FILES:
        _write(project / name, (ASSETS / 'native' / name).read_text(encoding='utf-8'))
    for name in MACHINE_FILES:
        _write(project / name, (ASSETS / 'native' / 'psx_machine' / name).read_text(encoding='utf-8'))
    hostkit.stage(project, 'psx')
    notices = [(ASSETS / name).read_text(encoding='utf-8') for name in NOTICE_FILES if (ASSETS / name).is_file()]
    _write(project / 'notices.txt', '\n\n'.join(notices))
    resources = {203: project / 'notices.txt', 205: project / 'export-identity.bin'}
    rc = ['#pragma code_page(65001)', '203 RCDATA "notices.txt"', '205 RCDATA "export-identity.bin"']
    bios_file = project / 'bios.bin'
    if bios is not None:
        data = bios.data()
        if not bios_file.is_file() or bios_file.read_bytes() != data:
            bios_file.write_bytes(data)
        resources[104] = bios_file
        rc.insert(1, '104 RCDATA "bios.bin"')
    elif bios_file.exists():
        bios_file.unlink()
    icon, artwork = False, {'embedded': False, 'source': 'disabled'}
    if presentation is not None:
        from .artwork import prepare_icon
        from .paths import boxart_cache_directory
        from .core import ROOT
        artwork = prepare_icon(project, presentation['rom_path'], title,
            presentation.get('boxart_dir') or ROOT / 'BoxArt', explicit=presentation.get('cover'),
            online=presentation.get('online_cover', True), enabled=presentation.get('use_cover', True),
            cache_directory=boxart_cache_directory('psx'), system_id='psx', emit=presentation.get('emit', print))
        icon = artwork['embedded']
    (project / 'artwork.json').write_text(json.dumps(artwork, indent=2), encoding='utf-8')
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False, icon=icon,
                                   standard=video_mode, system_id='psx')
    (project / 'export-identity.bin').write_bytes(b'[Retro-Recomp]\0' + game_sha256.encode('ascii') + b'\0')
    _write(project / 'content.rc', '\n'.join(rc) + '\n#include "game_resources.rc"\n')
    (project / 'content.rc').touch()   # the resource compiler does not track the files it includes
    from .resources import embed_resources
    embed_resources(project, resources)
    _write(project / 'psx_game.h', '#pragma once\n'
           f'#define RR_PSX_TITLE {json.dumps(title)}\n#define RR_PSX_VERSION {json.dumps(__version__)}\n'
           f'#define RR_PSX_FPS {FPS["pal" if video_mode == "pal" else "ntsc"]}\n')
    _write(project / 'retro16_state_config.h',
           state_config(game_sha256, title, video_mode, bios.sha256 if bios is not None else None))
    _write(project / 'CMakeLists.txt', game_cmake(tree, __version__))
    from .feedback import stage
    stage(project, 'psx', game_sha256)   # the exit-only runtime recorder every game carries (adds its sources to the project)
    return {'artwork': artwork, 'windows_metadata': metadata, 'bios': 'player' if bios is not None else 'free'}


def build_game(project: Path, emit: Callable[[str], None] = print, *, cmake_args: list | None = None) -> Path:
    """Build the project's `game` target against the static SDL2 of the converter; returns the linked program (no disc yet)."""
    from . import core
    from .platforms import build_executable, sdl_install, sdl_library
    sdl = sdl_install()
    if not (sdl / sdl_library()).exists():
        _, sdl, _, _ = core.dependencies(emit)
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *(cmake_args or core.cmake_target_args()),
              f'-DCMAKE_PREFIX_PATH={Path(sdl).as_posix()}'], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'game', '--parallel',
              core.build_jobs()], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    return build_executable(project / 'build', 'game')
