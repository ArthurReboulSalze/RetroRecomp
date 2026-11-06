"""Commodore Amiga input: a WHDLoad install archive (`.lha` holding one `.Slave`), read without changing it (MIT).

The game's identity is the SHA-256 of the archive the player gave: the report's rom.sha256, the export's marker, the library
key. The archive is read with `amiga_lha` (member names, then the slave and the data files) and described with
`amiga_whdload.install`; nothing in it is run here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from pathlib import Path

from .core import ConversionError
from .paths import ASSETS

# An install bigger than this is not a floppy game (the whole archive is read in memory).
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024


def converter_available() -> bool:
    """True when this installation carries the Amiga converter's own files (the profile is offered only then)."""
    return all((ASSETS / name).is_file() for name in (
        'native/amiga_machine/CMakeLists.txt', 'native/amiga_whdload/rr_resload.c',
        'native/hostkit/adapters/rrhk_amiga.inc', 'retrorecomp/amiga_conversion.py'))


def slave_member(path: Path) -> str | None:
    """The member name of the archive's only WHDLoad slave, or None (no slave, several slaves, not an LHA archive)."""
    from . import amiga_lha
    try:
        slaves = [m.name for m in amiga_lha.members(Path(path)) if m.name.lower().endswith('.slave')]
    except (OSError, ValueError):
        return None
    return slaves[0] if len(slaves) == 1 else None


@dataclass(frozen=True)
class AmigaInput:
    path: Path
    sha256: str
    size: int
    title: str
    slave_path: str
    slave_version: int
    kickemu: bool
    base_mem: int
    exp_mem: int

    @property
    def game_key(self) -> str:
        return self.sha256

    def data(self) -> bytes:
        """The archive's bytes, checked again against the identity read at the start."""
        blob = self.path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.sha256:
            raise ConversionError(f'{self.path.name} changed during the conversion.')
        return blob

    def metadata(self) -> dict:
        return {'name': self.path.name, 'path': str(self.path), 'sha256': self.sha256, 'size': self.size,
                'format': 'whdload-lha', 'slave': self.slave_path, 'slave_version': self.slave_version,
                'kickemu': self.kickemu}


def cover_title(name: str) -> str:
    """A slave's ws_name as a name to look its box up with: the frame around it dropped (`--> Pinball Dreams <--`,
    `-* ... *-`), letters spaced one by one joined again (`S P E E D B A L L  2`: words two spaces apart)."""
    text = re.sub(r'^[^0-9A-Za-z]+|[^0-9A-Za-z)]+$', '', (name or '').split('\n', 1)[0]).strip()
    words = re.split(r' {2,}', text)
    if len(text) > 4 and all(len(letter) == 1 for word in words for letter in word.split(' ')):
        text = ' '.join(word.replace(' ', '') for word in words)
    return text if len(text) < 120 else ''


def read_input(path) -> AmigaInput:
    from . import amiga_whdload
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_ARCHIVE_BYTES:
        raise ConversionError(f'{path.name} is larger than an Amiga floppy install ({size} bytes).')
    blob = path.read_bytes()
    try:
        install = amiga_whdload.install(blob)
    except ValueError as error:
        raise ConversionError(f'{path.name}: {error}') from None
    slave = install.slave
    title = (slave.name.split('\n', 1)[0].strip() or path.stem)[:160]
    return AmigaInput(path, hashlib.sha256(blob).hexdigest(), size, title, install.slave_path, slave.version,
                      slave.kickemu, slave.base_mem, slave.exp_mem)
