"""The pinned PC Engine engine (pcenginerecomp): fetch it, build its hosts, emit a game's native module.

Everything the engine does is driven from here, through its own documented interfaces only:

* the checkout is `.deps/pcenginerecomp` at `pce_conversion.ENGINE_REV` (`core.follow_pin`, like the other engines);
* a game's module is emitted from the code its runs observed (`compose-observations`, then `emit-profile`, run inside
  the converter's own Python with the checkout on the import path);
* the game itself (native/pce_main.c, pce_machine.cpp and the host kit) is built with the pinned engine as a CMake
  subproject (`pce-runtime` and `pce_add_native_module`), in the game's project folder.

No engine source is patched. The engine names the object library of a module after a 64-digit hash, and Visual Studio
writes `<name>.dir/Release/<name>.lib` below the build folder (166 characters): the game compiles the module's sources in an
object library of its own short name instead (`game_cmake`), so a deep application folder still links. The engine refuses what it does not model (an unsupported I/O access faults), and the
converter reports that refusal; it never hides it.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path
from typing import Callable

ENGINE_URL = 'https://github.com/rages4calm/pcenginerecomp.git'
BUILD_TIMEOUT = 4 * 3600     # the Street Fighter II board's module takes an hour of eight compiler jobs: two jobs on a small machine need much longer


class PceBuildError(RuntimeError):
    """The engine could not be fetched, built or asked to emit."""


def _core():
    from . import core
    return core


def checkout_path() -> Path:
    return _core().ROOT / '.deps' / 'pcenginerecomp'


def ensure_engine(emit: Callable[[str], None] = print) -> Path:
    """A clean checkout of the pinned revision (cloned when absent; never reset when it carries edits)."""
    from .pce_conversion import ENGINE_REV
    core = _core()
    deps = core.ROOT / '.deps'
    deps.mkdir(exist_ok=True)
    checkout = checkout_path()
    core.follow_pin(checkout, ENGINE_URL, ENGINE_REV, deps / 'pcenginerecomp-setup.log', emit)
    return checkout


@contextlib.contextmanager
def _engine_on_path():
    source = str(checkout_path())
    sys.path.insert(0, source)
    try:
        yield
    finally:
        with contextlib.suppress(ValueError):
            sys.path.remove(source)


def engine_cli(arguments: list[str]) -> str:
    """Run one `python -m pcerecomp` command in this process; its output, or PceBuildError with it."""
    output = io.StringIO()
    with _engine_on_path(), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
        from pcerecomp import cli
        try:
            status = cli.main([str(argument) for argument in arguments])
        except SystemExit as stop:
            status = stop.code
    if status not in (None, 0):
        raise PceBuildError(f'pcerecomp {arguments[0]} failed ({status}):\n{output.getvalue()[-4000:]}')
    return output.getvalue()


def emit_module(profile: Path, module: Path) -> dict:
    """Emit the guarded native module of a composed observation profile (`compose`) into the new folder `module`."""
    engine_cli(['emit-profile', profile, '--out', module])
    return json.loads((module / 'module.json').read_text(encoding='utf-8'))


def compose_history(captures: list[Path], out: Path, capacity: int) -> Path:
    """Several captures, of the engine's larger format or not, as one version 2 history in the new folder `out`. Returns its index."""
    engine_cli(['compose-history', *captures, '--history-version', '2', '--capacity', capacity, '--out', out])
    return out / 'history.json'


def emit_history_module(history: Path, module: Path) -> dict:
    """Emit the guarded native module of a version 2 history into the new folder `module`, in large translation units: a catalogue this size in small ones
    repeats the compiler's header work thousands of times."""
    engine_cli(['emit-history', history, '--out', module, '--partition-layout', 'balanced', '--partition-size', 4096])
    return json.loads((module / 'module.json').read_text(encoding='utf-8'))


def emit_roots_module(roots: Path, image: Path, history: Path, module: Path) -> dict:
    """Emit the guarded native module of a history and of received paths declared as roots (their format holds numbers; the engine reads the bytes from `image`)."""
    engine_cli(['emit-roots', roots, '--image', image, '--history', history, '--out', module, '--partition-layout', 'balanced', '--partition-size', 4096])
    return json.loads((module / 'module.json').read_text(encoding='utf-8'))


def compose(captures: list[Path], out: Path) -> Path:
    """Several captures of one game as one observation profile (`compose-observations`), for one module."""
    engine_cli(['compose-observations', *captures, '--out', out])
    return out


# ------------------------------------------------------------------ the game project

# Files of native/ a PC Engine game is built from beside the host kit (hostkit.stage) and the feedback recorder
# (feedback.stage): the bridge to the engine, the game's entry, the quick-state file of the 16-bit family, the menu.
GAME_FILES = ('pce_main.c', 'pce_machine.cpp', 'pce_machine.h', 'pce_backup.c', 'pce_backup.h', 'console16_state.c', 'console16_state.h',
              'console16_video.h', 'platform_io.c', 'platform_io.h', 'embedded_resources.h', 'retro_menu.c',
              'retro_menu.h', 'font6x10.h', 'font10x20.h', 'runtime_i18n.h', 'runtime_catalog.inc', 'retro_keyboard.h',
              'display_settings.h', 'autofire.h', 'game_options.h', 'audio_filter.h', 'audio_cushion.h',
              'scanline_sdl.h', 'scanlines.h', 'xbr_sdl.h', 'xbr_filter.h', 'scale2x.h')
NOTICE_FILES = ('LICENSE', 'licenses/pcenginerecomp.md', 'licenses/SDL2.md', 'licenses/xbr.md', 'licenses/Noto.md',
                'licenses/UPX.md', 'licenses/llvm-mingw.md')
STATE_SYSTEM = 5      # the quick-state header's machine number (1 Mega Drive, 2 Super Nintendo, 3 Neo Geo, 4 CPS-1)


def _write(path: Path, text: str) -> bool:
    from .conversion_common import write_if_changed
    return write_if_changed(path, text.encode('utf-8'))


def state_config(card, title: str) -> str:
    """Quick states load only into the same HuCard, the same engine revision and the same bridge sources."""
    import hashlib
    from .core import ASSETS, executable_name
    from .pce_conversion import ENGINE_REV
    abi = hashlib.sha256(b'PCE-frame-state-v1:' + ENGINE_REV.encode())
    for name in ('pce_machine.cpp', 'pce_machine.h', 'pce_main.c'):
        abi.update((ASSETS / 'native' / name).read_bytes())
    if os.name != 'nt':
        from .platforms import target_id
        abi.update(target_id().encode())
    stem = Path(executable_name(title)).stem if os.name == 'nt' else executable_name(title)
    return (f'#pragma once\n#define RR16_STATE_SYSTEM {STATE_SYSTEM}\n#define RR16_STATE_PAL 0\n'
            f'#define RR16_STATE_ROM {json.dumps(card.sha256)}\n#define RR16_STATE_ABI {json.dumps(abi.hexdigest())}\n'
            f'#define RR16_STATE_NAME {json.dumps(stem)}\n')


def game_cmake(module: Path | None, version: str) -> str:
    """The game's CMake project: the pinned engine as a subproject, its module, the bridge, the kit, SDL2."""
    from . import hostkit
    engine = checkout_path().as_posix()
    if module is None:
        module_line = f'pce_add_native_module(PCE_MODULE MODULE "{engine}/runtime/src/no_module.cpp")'
    else:
        module_line = (f'pce_add_native_module(PCE_MODULE MODULE "{(module / "module.cpp").as_posix()}" '
                       f'MANIFEST "{(module / "module.json").as_posix()}")')
    kit = ' '.join(hostkit.sources('pce'))
    lines = [
        'cmake_minimum_required(VERSION 3.20)',
        'project(RetroPce LANGUAGES C CXX)',
        'set(CMAKE_C_STANDARD 11)',
        'set(CMAKE_CXX_STANDARD 20)',
        'set(CMAKE_CXX_STANDARD_REQUIRED ON)',
        'set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")',
        'if(MSVC)', '  add_compile_options(/utf-8 /wd4996 /wd4244 /wd4267)', 'endif()',
        'set(PCE_BUILD_TOOLS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_TESTS OFF CACHE BOOL "" FORCE)',
        'set(PCE_BUILD_DESKTOP OFF CACHE BOOL "" FORCE)',
        f'add_subdirectory("{engine}" engine EXCLUDE_FROM_ALL)',
        module_line,
        # The engine's own target (named after a SHA-256, 75 characters) validates the manifest and lists the sources; it is
        # never built. Its object folder and library (166 characters under the build folder) passed Windows' 260-character
        # limit in a deep application folder (LNK1104), so the sources are compiled in an object library with a short name.
        'get_target_property(PCE_MODULE_SOURCES ${PCE_MODULE} SOURCES)',
        'add_library(pce_module OBJECT ${PCE_MODULE_SOURCES})',
        'target_link_libraries(pce_module PUBLIC pce-runtime)',
        'set_target_properties(pce_module PROPERTIES CXX_EXTENSIONS OFF)',
        'if(WIN32)', '  enable_language(RC)', 'else()', '  enable_language(ASM)', 'endif()',
        'find_package(SDL2 CONFIG REQUIRED)',
        f'add_executable(game pce_main.c pce_machine.cpp pce_backup.c {kit} console16_state.c retro_menu.c',
        '  $<TARGET_OBJECTS:pce_module>)',
        'target_include_directories(game PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}")',
        'if(WIN32)', '  target_sources(game PRIVATE content.rc)',
        '  target_link_libraries(game PRIVATE shell32 user32 gdi32)',
        'else()', '  target_sources(game PRIVATE embedded_resources.c embedded_resources.S)',
        '  target_link_libraries(game PRIVATE m)', 'endif()',
        'target_link_libraries(game PRIVATE pce-runtime SDL2::SDL2-static)',
        f'target_compile_definitions(game PRIVATE SDL_MAIN_HANDLED [[RR_RECOMP_VERSION="{version}"]])',
        'if(MSVC)', '  target_link_options(game PRIVATE /SUBSYSTEM:WINDOWS /ENTRY:mainCRTStartup)', 'endif()',
        'if(WIN32 AND NOT MSVC)',
        '  target_link_options(game PRIVATE -Wl,--subsystem,windows -Wl,--entry,mainCRTStartup)', 'endif()',
    ]
    return '\n'.join(lines) + '\n'


def prepare_game(project: Path, card, *, title: str, module: Path | None = None, players: int = 2,
                 presentation: dict | None = None) -> dict:
    """A playable game project: the bridge, the kit, the emitted `module` (or none: everything interpreted) and the
    HuCard file embedded as resource 103, decoded by the engine with the reader's explicit header and bit order."""
    import hashlib
    from . import __version__, hostkit
    from .core import ASSETS, executable_name
    from .feedback import stage
    from .metadata import write_game_metadata
    project.mkdir(parents=True, exist_ok=True)
    for name in GAME_FILES:
        _write(project / name, (ASSETS / 'native' / name).read_text(encoding='utf-8'))
    hostkit.stage(project, 'pce')
    notices = [(ASSETS / name).read_text(encoding='utf-8') for name in NOTICE_FILES if (ASSETS / name).is_file()]
    _write(project / 'notices.txt', '\n\n'.join(notices))
    rom = project / 'hucard.pce'
    from .pce_rom import file_bytes
    data = file_bytes(card.path)
    if hashlib.sha256(data).hexdigest() != card.sha256:
        raise PceBuildError('The HuCard changed while it was being converted.')
    rom_changed = not rom.is_file() or rom.read_bytes() != data
    if rom_changed:
        rom.write_bytes(data)
    icon, artwork = False, {'embedded': False, 'source': 'disabled'}
    if presentation is not None:
        from .artwork import prepare_icon
        from .paths import boxart_cache_directory
        artwork = prepare_icon(project, presentation['rom_path'], title,
            presentation.get('boxart_dir') or _core().ROOT / 'BoxArt', explicit=presentation.get('cover'),
            online=presentation.get('online_cover', True), enabled=presentation.get('use_cover', True),
            cache_directory=boxart_cache_directory('pce'), system_id='pce', emit=presentation.get('emit', print))
        icon = artwork['embedded']
    (project / 'artwork.json').write_text(json.dumps(artwork, indent=2), encoding='utf-8')
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False, icon=icon,
                                   standard='ntsc', system_id='pce')
    (project / 'export-identity.bin').write_bytes(b'[Retro-Recomp]\0' + card.sha256.encode('ascii') + b'\0')
    _write(project / 'content.rc', '#pragma code_page(65001)\n103 RCDATA "hucard.pce"\n203 RCDATA "notices.txt"\n'
                                   '205 RCDATA "export-identity.bin"\n#include "game_resources.rc"\n')
    if rom_changed and (project / 'content.rc').is_file():
        (project / 'content.rc').touch()   # the resource compiler does not track the file it includes
    from .resources import embed_resources
    embed_resources(project, {103: rom, 203: project / 'notices.txt', 205: project / 'export-identity.bin'})
    six = card.board == 'sf2'
    seats = max(1, min(players, 4))
    _write(project / 'pce_game.h', '#pragma once\n#include "pce_machine.h"\n'
           f'#define RR_PCE_TITLE {json.dumps(title)}\n#define RR_PCE_VERSION {json.dumps(__version__)}\n'
           f'#define RR_PCE_BOARD {"PCE_BOARD_SF2" if six else "PCE_BOARD_BASE"}\n'
           f'#define RR_PCE_COPIER_HEADER {int(card.header == "copier512")}\n'
           f'#define RR_PCE_BIT_REVERSED {int(card.encoding == "bit-reversed")}\n'
           f'#define RR_PCE_PAD_BUTTONS {6 if six else 2}\n#define RR_PCE_MULTITAP {int(seats > 2)}\n'
           f'#define RR_PCE_PLAYERS {seats}\n')
    _write(project / 'retro16_state_config.h', state_config(card, title))
    _write(project / 'CMakeLists.txt', game_cmake(module, __version__))
    stage(project, 'pce', card.sha256)
    return {'artwork': artwork, 'windows_metadata': metadata, 'pad_buttons': 6 if six else 2,
            'multitap': seats > 2, 'players': seats}


def build_game(project: Path, emit: Callable[[str], None] = print) -> Path:
    """Build the game project's `game` target against the static SDL2 of the converter."""
    from .platforms import build_executable, sdl_install, sdl_library
    core = _core()
    sdl = sdl_install()
    if not (sdl / sdl_library()).exists():
        _, sdl, _, _ = core.dependencies(emit)
    cmake, generator = core.toolchain()
    log = project / 'build.log'
    core.run([cmake, '-S', project, '-B', project / 'build', '-G', generator, *core.cmake_target_args(),
              f'-DCMAKE_PREFIX_PATH={Path(sdl).as_posix()}'], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    core.run([cmake, '--build', project / 'build', '--config', 'Release', '--target', 'game', '--parallel',
              core.build_jobs()], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    return build_executable(project / 'build', 'game')
