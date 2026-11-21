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
