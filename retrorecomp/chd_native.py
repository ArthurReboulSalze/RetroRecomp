"""A CHD's hunks decoded by libchdr, for the converter (Retro-Recomp's own code, MIT; libchdr is BSD-3-Clause).

A CHD keeps a disc's sectors in compressed hunks, and the audio tracks of a CD in FLAC (`cdfl`), which the Python standard library
cannot decode. A PlayStation game's key is the digest of every sector of its discs, audio included (psx_disc.Disc.digest), and it must
be the same for a CHD and for the CUE/BIN set it was made from. So the converter decodes a CHD through libchdr, at the revision the PC
Engine CD's games already link (pcecd_build.LIBCHDR_REV): `native/chd_sectors/chd_sectors.c` is built once with the converter's own
toolchain, kept under `.deps`, and run as a child process that answers hunk numbers with decoded hunks (every hunk checked by libchdr
against the CRC of its map). Nothing of it is in a game.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .core import ASSETS, ROOT, ConversionError, run, serialized_setup, toolchain
from .platforms import build_executable, cmake_target_args

SOURCE = Path('native') / 'chd_sectors' / 'chd_sectors.c'
FORMAT_LINE = 'RRCHD 1'
QUIT = 0xFFFFFFFF
BUILD_TIMEOUT = 900


class ChdError(ValueError):
    """A CHD the reader cannot open or read, with the reason."""


def _key() -> str:
    from . import pcecd_build
    text = (ASSETS / SOURCE).read_bytes() + b'\0' + pcecd_build.LIBCHDR_REV.encode()
    return hashlib.sha256(text).hexdigest()[:12]


def tool_folder() -> Path:
    from .toolchain import suffix
    return ROOT / '.deps' / f'chd-sectors-{_key()}{suffix()}'


def tool_path() -> Path:
    return build_executable(tool_folder() / 'build', 'chd_sectors')


@serialized_setup
def ensure_tool(emit: Callable[[str], None] = print) -> Path:
    """The reader, built when absent (libchdr fetched at its pin; a few seconds with the portable toolchain)."""
    exe = tool_path()
    if exe.is_file():
        return exe
    from . import pcecd_build
    emit('CHD: building the converter\'s CHD reader (first use)...')
    checkout = pcecd_build.ensure_libchdr(emit)
    folder = tool_folder()
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'chd_sectors.c'
    source.write_bytes((ASSETS / SOURCE).read_bytes())
    lines = ['cmake_minimum_required(VERSION 3.16)', 'project(chd_sectors C)',
             *pcecd_build.libchdr_cmake_lines(checkout),
             'add_executable(chd_sectors chd_sectors.c)', 'target_link_libraries(chd_sectors PRIVATE chdr-static)']
    (folder / 'CMakeLists.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
    cmake, generator = toolchain()
    log = folder / 'build.log'
    build = folder / 'build'
    run([cmake, '-S', folder, '-B', build, '-G', generator, *cmake_target_args()], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    run([cmake, '--build', build, '--config', 'Release', '--target', 'chd_sectors'], log=log, emit=emit, timeout=BUILD_TIMEOUT)
    if not exe.is_file():
        raise ConversionError(f'The CHD reader was not built (see {log}).')
    return exe


@dataclass(frozen=True)
class Header:
    hunk_bytes: int
    total_hunks: int
    unit_bytes: int
    logical_bytes: int


class ChdHunks:
    """One CHD opened by the reader: its header, its metadata records (tag, text) and its hunks."""

    def __init__(self, path: Path, emit: Callable[[str], None] = print):
        self.path = Path(path)
        try:
            exe = ensure_tool(emit)
        except ConversionError as error:
            raise ChdError(f'{self.path.name}: {error}') from None
        self._process = subprocess.Popen([str(exe), str(self.path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        first = self._process.stdout.readline().decode('ascii', 'replace').split()
        if len(first) != 6 or ' '.join(first[:2]) != FORMAT_LINE:
            reason = self._process.stderr.read().decode('utf-8', 'replace').strip() or 'not a CHD'
            self.close()
            raise ChdError(f'{self.path.name}: {reason}')
        self.header = Header(*(int(v) for v in first[2:]))
        self.metadata: list[tuple[str, str]] = []
        while True:
            line = self._process.stdout.readline().decode('ascii', 'replace').rstrip('\r\n')
            if not line:
                break
            tag, _, text = line.partition(' ')
            self.metadata.append((tag, text.strip()))
        self._cache: tuple[int, bytes] | None = None

    def hunk(self, number: int) -> bytes:
        if self._cache is not None and self._cache[0] == number:
            return self._cache[1]
        process = self._process
        if process is None or process.poll() is not None:
            raise ChdError(f'{self.path.name}: the CHD reader stopped')
        process.stdin.write(struct.pack('<I', number))
        process.stdin.flush()
        status = process.stdout.read(1)
        if status != b'\0':
            raise ChdError(f'{self.path.name}: hunk {number} cannot be read (damaged or truncated CHD)')
        data = process.stdout.read(self.header.hunk_bytes)
        if len(data) != self.header.hunk_bytes:
            raise ChdError(f'{self.path.name}: the CHD reader stopped in hunk {number}')
        self._cache = (number, data)
        return data

    def read(self, offset: int, length: int) -> bytes:
        """`length` bytes of the CHD's logical data from `offset`."""
        size = self.header.hunk_bytes
        out = bytearray()
        while length > 0:
            number, within = divmod(offset, size)
            piece = self.hunk(number)[within:within + length]
            if not piece:
                raise ChdError(f'{self.path.name}: a read past the end of the CHD')
            out += piece
            offset += len(piece)
            length -= len(piece)
        return bytes(out)

    def close(self) -> None:
        process, self._process = getattr(self, '_process', None), None
        if process is None:
            return
        try:
            if process.poll() is None:
                process.stdin.write(struct.pack('<I', QUIT))
                process.stdin.flush()
        except OSError:
            pass
        for stream in (process.stdin, process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
