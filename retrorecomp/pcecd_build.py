"""The build of a PC Engine CD game (Retro-Recomp's own code, MIT). Stage 1a of docs/NEW_MACHINE.md: only the pinned components are named
here; the conversion loop and the game's build come with the next stages (docs/PC_ENGINE_CD.md).

A PC Engine CD game is the PC Engine's machine (retrorecomp/pce_build.py, the pinned pcenginerecomp engine and our copies of four of its
files) with a disc. The engine reads a CHD through libchdr, which the engine loads as a shared library by path; a standalone game
links it instead (BSD-3-Clause, with its LZMA SDK, miniz, zstd and dr_flac), fetched at this revision when a conversion needs it.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .core import serialized_setup

LIBCHDR_URL = 'https://github.com/rtissera/libchdr.git'
# The revision the engine itself pins for its CHD reading (its scripts/bootstrap_chd.py and THIRD_PARTY.md).
LIBCHDR_REV = '47d794151b2b64f6aba60304e6480f4f5a2bc24b'


def _core():
    from . import core
    return core


def libchdr_checkout() -> Path:
    return _core().ROOT / '.deps' / 'libchdr'


@serialized_setup
def ensure_libchdr(emit: Callable[[str], None] = print) -> Path:
    """A clean checkout of libchdr at the pinned revision (cloned when absent; never reset when it carries edits), under the shared setup
    gate like every dependency fetch."""
    core = _core()
    deps = core.ROOT / '.deps'
    deps.mkdir(exist_ok=True)
    checkout = libchdr_checkout()
    core.follow_pin(checkout, LIBCHDR_URL, LIBCHDR_REV, deps / 'libchdr-setup.log', emit)
    return checkout


def libchdr_cmake_lines(checkout: Path | None = None) -> list[str]:
    """The CMake lines that build libchdr as a static library for a game (target `chdr-static`): no tests, no shared library, its own bundled decoders."""
    source = (checkout or libchdr_checkout()).as_posix()
    return ['set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)', 'set(CHDR_WANT_TESTS OFF CACHE BOOL "" FORCE)',
            'set(WITH_SYSTEM_ZLIB OFF CACHE BOOL "" FORCE)', 'set(WITH_SYSTEM_ZSTD OFF CACHE BOOL "" FORCE)',
            f'add_subdirectory("{source}" libchdr EXCLUDE_FROM_ALL)']


# ------------------------------------------------------------------ the game project

# The files of native/ that a PC Engine CD game adds to the PC Engine's (pce_build.GAME_FILES): the disc provider (libchdr), the reader of the disc held by the executable.
GAME_FILES = ('pcecd_disc.cpp', 'pcecd_disc.h', 'pcecd_pack.c', 'pcecd_pack.h')
UNKNOWN_STATUS = {'fault': 0, 'gear-good': 1, 'nec-invalid': 2}


class PcecdBuildError(RuntimeError):
    pass


def prepare_game(project: Path, item, card, *, title: str, module: Path | None = None, players: int = 2, presentation: dict | None = None,
                 super_ram: bool = True, region_japan: bool = False, unknown: str = 'fault') -> dict:
    """A playable game project: the PC Engine's bridge and kit with the disc provider, the emitted `module` (or none: everything interpreted) and the player's
    System Card embedded as resource 103. The disc is not in the project: a run names it (`--disc`) and the delivered game holds it (`append_disc`)."""
    import json
    from . import __version__, hostkit, pce_build
    from .core import ASSETS, executable_name
    from .feedback import stage
    from .metadata import write_game_metadata
    from .notices import notice_text
    from .resources import embed_resources
    if unknown not in UNKNOWN_STATUS:
        raise PcecdBuildError(f'unknown CD command policy: {unknown}')
    project.mkdir(parents=True, exist_ok=True)
    for name in (*pce_build.GAME_FILES, *GAME_FILES):
        pce_build._write(project / name, (ASSETS / 'native' / name).read_text(encoding='utf-8'))
    pce_build.stage_engine_patch(project)
    hostkit.stage(project, 'pcecd')
    # The adapter of the CD machine includes the PC Engine's (rrhk_pce.c): both go to the project.
    pce_adapter = project / 'hostkit' / 'adapters' / 'rrhk_pce.c'
    data = (ASSETS / 'native/hostkit/adapters/rrhk_pce.c').read_bytes()
    if not pce_adapter.is_file() or pce_adapter.read_bytes() != data:
        pce_adapter.parent.mkdir(parents=True, exist_ok=True)
        pce_adapter.write_bytes(data)
    pce_build._write(project / 'notices.txt', notice_text('pcecd'))
    system_card = project / 'systemcard.pce'
    blob = card.data()
    if not system_card.is_file() or system_card.read_bytes() != blob:
        system_card.write_bytes(blob)
        if (project / 'content.rc').is_file():
            (project / 'content.rc').touch()      # the resource compiler does not track the file it includes
    icon, artwork = False, {'embedded': False, 'source': 'disabled'}
    if presentation is not None:
        from .artwork import prepare_icon
        from .paths import boxart_cache_directory
        artwork = prepare_icon(project, presentation['rom_path'], title,
                               presentation.get('boxart_dir') or pce_build._core().ROOT / 'BoxArt', explicit=presentation.get('cover'),
                               online=presentation.get('online_cover', True), enabled=presentation.get('use_cover', True),
                               cache_directory=boxart_cache_directory('pcecd'), system_id='pcecd', emit=presentation.get('emit', print))
        icon = artwork['embedded']
    (project / 'artwork.json').write_text(json.dumps(artwork, indent=2), encoding='utf-8')
    metadata = write_game_metadata(project, title, executable_name(title), light_phaser=False, icon=icon, standard='ntsc', system_id='pcecd')
    (project / 'export-identity.bin').write_bytes(b'[Retro-Recomp]\0' + item.sha256.encode('ascii') + b'\0')
    pce_build._write(project / 'content.rc', '#pragma code_page(65001)\n103 RCDATA "systemcard.pce"\n203 RCDATA "notices.txt"\n'
                                              '205 RCDATA "export-identity.bin"\n#include "game_resources.rc"\n')
    embed_resources(project, {103: system_card, 203: project / 'notices.txt', 205: project / 'export-identity.bin'})
    seats = max(1, min(players, 4))
    pce_build._write(project / 'pce_game.h', '#pragma once\n#include "pce_machine.h"\n'
                     f'#define RR_PCE_TITLE {json.dumps(title)}\n#define RR_PCE_VERSION {json.dumps(__version__)}\n'
                     '#define RR_PCE_BOARD PCE_BOARD_BASE\n#define RR_PCE_COPIER_HEADER 0\n#define RR_PCE_BIT_REVERSED 0\n'
                     f'#define RR_PCE_PAD_BUTTONS 2\n#define RR_PCE_MULTITAP {int(seats > 1)}\n#define RR_PCE_PLAYERS {seats}\n'
                     f'#define RR_PCE_SUPER_RAM {int(super_ram)}\n#define RR_PCE_REGION_JAPAN {int(region_japan)}\n'
                     f'#define RR_PCE_UNKNOWN_STATUS {UNKNOWN_STATUS[unknown]}\n')
    pce_build._write(project / 'retro16_state_config.h', pce_build.state_config(item, title, GAME_FILES))
    pce_build._write(project / 'CMakeLists.txt', pce_build.game_cmake(module, __version__, disc=True, family='pcecd'))
    stage(project, 'pcecd', item.sha256)
    return {'artwork': artwork, 'windows_metadata': metadata, 'pad_buttons': 2, 'multitap': seats > 1, 'players': seats}


def append_disc(executable: Path, image: Path, sha256: str) -> tuple[int, int]:
    """Append the disc to the linked game and its trailer (native/pcecd_pack.h): the game then holds the disc and reads it in place. A CHD or an ISO is
    appended as it is; (offset, length) of the disc in the file."""
    import shutil
    import struct
    if image.suffix.lower() not in ('.chd', '.iso'):
        raise PcecdBuildError(f'{image.name}: only a CHD or an ISO is held by the game so far (a CUE sheet and its images are not packed yet).')
    offset = executable.stat().st_size
    with open(executable, 'ab') as out, open(image, 'rb') as source:
        shutil.copyfileobj(source, out, 8 * 1024 * 1024)
    length = executable.stat().st_size - offset
    with open(executable, 'ab') as out:
        out.write(sha256.encode('ascii') + struct.pack('<QQ', offset, length) + b'RRPCECD1')
    return offset, length
