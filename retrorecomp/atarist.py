"""Atari ST input: a game's floppy images (one image, or a ZIP holding only floppy images), read without changing them (MIT).

The game's identity is the SHA-256 of the file the player gave: the report's rom.sha256, the export's marker, the library key.
The disks are the ZIP's members in disk order (atarist_disk.disk_order_key: the boot disk first, then Disk 1, Disk 2... or Disk A, Disk B..., Side, Reel, Volume), every one an image
Hatari reads: IPF (the preservation format: a disk's protection data stays in the image; whether it runs is per game), STX (Pasti), MSA or a plain sector image (.st). Nothing in them is
run here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import re
import zipfile
from pathlib import Path

from .atarist_disk import order_disks
from .core import ConversionError
from .paths import ASSETS

DISK_EXTENSIONS = ('.ipf', '.stx', '.msa', '.st')
MAX_DISKS = 8
# A game bigger than this is not a floppy game (the whole file is read in memory); one IPF is at most a few MiB.
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_DISK_BYTES = 8 * 1024 * 1024


def converter_available() -> bool:
    """True when this installation carries the Atari ST converter's own native files (the profile is offered only then).
    Native files only: a frozen converter keeps its Python modules inside the executable, never as .py files."""
    return all((ASSETS / name).is_file() for name in (
        'native/atarist_machine/CMakeLists.txt', 'native/atarist_machine/atarist_session.c',
        'native/hostkit/adapters/rrhk_atarist.inc'))


def disk_members(path: Path) -> list[str] | None:
    """The member names of a ZIP that holds only Atari ST floppy images (1 to MAX_DISKS of them), in disk order; None
    otherwise (another archive, a folder inside, any other member)."""
    try:
        with zipfile.ZipFile(path) as archive:
            names = [info.filename for info in archive.infolist() if not info.is_dir()]
    except (OSError, zipfile.BadZipFile):
        return None
    if not names or len(names) > MAX_DISKS:
        return None
    if any(Path(name).suffix.casefold() not in DISK_EXTENSIONS or '/' in name.strip('/') or '\\' in name for name in names):
        return None
    return order_disks(names)


def is_disk_image(path: Path) -> bool:
    return Path(path).suffix.casefold() in DISK_EXTENSIONS


@dataclass(frozen=True)
class AtariStDisk:
    name: str
    sha256: str
    size: int
    format: str


@dataclass(frozen=True)
class AtariStInput:
    path: Path
    sha256: str
    size: int
    title: str
    disks: tuple[AtariStDisk, ...]

    @property
    def game_key(self) -> str:
        return self.sha256

    def disk_data(self) -> list[bytes]:
        """The disks' bytes, in order, checked again against the identity read at the start."""
        blob = self.path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.sha256:
            raise ConversionError(f'{self.path.name} changed during the conversion.')
        return [data for _, data in _disks(self.path, blob)]

    def metadata(self) -> dict:
        return {'name': self.path.name, 'path': str(self.path), 'sha256': self.sha256, 'size': self.size,
                'format': 'atarist-zip' if self.path.suffix.casefold() == '.zip' else 'atarist-disk',
                'disks': [{'name': d.name, 'sha256': d.sha256, 'size': d.size, 'format': d.format} for d in self.disks]}


def clean_title(name: str) -> str:
    """A file name as a game title: the extension and the bracketed tags of preservation sets dropped
    ("Turrican II - The Final Fight (Europe) (Budget - Kixx).ipf" -> "Turrican II - The Final Fight")."""
    text = re.sub(r'\s*[\(\[][^\)\]]*[\)\]]', '', Path(name).stem).strip()
    return text[:160] or Path(name).stem[:160]


def _disks(path: Path, blob: bytes) -> list[tuple[str, bytes]]:
    if path.suffix.casefold() != '.zip':
        if path.suffix.casefold() not in DISK_EXTENSIONS:
            raise ConversionError(f'{path.name} is not an Atari ST floppy image.')
        return [(path.name, blob)]
    names = disk_members(path)
    if names is None:
        raise ConversionError(f'{path.name} does not hold Atari ST floppy images only (IPF, STX, MSA or ST).')
    out = []
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for name in names:
            info = archive.getinfo(name)
            if info.file_size > MAX_DISK_BYTES:
                raise ConversionError(f'{name} is larger than an Atari ST floppy image ({info.file_size} bytes).')
            out.append((Path(name).name, archive.read(info)))
    return out


def read_input(path) -> AtariStInput:
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise ConversionError(f'{path.name} is larger than an Atari ST floppy game ({size} bytes).')
    blob = path.read_bytes()
    disks = tuple(AtariStDisk(name, hashlib.sha256(data).hexdigest(), len(data), Path(name).suffix.casefold().lstrip('.'))
                  for name, data in _disks(path, blob))
    if any(not d.size for d in disks):
        raise ConversionError(f'{path.name}: an empty floppy image.')
    return AtariStInput(path, hashlib.sha256(blob).hexdigest(), size, clean_title(path.name), disks)
