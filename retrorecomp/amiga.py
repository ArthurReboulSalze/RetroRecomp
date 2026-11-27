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
    """True when this installation carries the Amiga converter's own native files (the profile is offered only then).
    Native files only: a frozen converter keeps its Python modules inside the executable, never as .py files."""
    return all((ASSETS / name).is_file() for name in (
        'native/amiga_machine/CMakeLists.txt', 'native/amiga_whdload/rr_resload.c',
        'native/hostkit/adapters/rrhk_amiga.inc'))


def slave_members(path: Path) -> list[str]:
    """The member names of the archive's WHDLoad slaves (empty: none, or not an LHA archive)."""
    from . import amiga_lha
    try:
        return [m.name for m in amiga_lha.members(Path(path)) if m.name.lower().endswith('.slave')]
    except (OSError, ValueError):
        return []


def slave_member(path: Path) -> str | None:
    """The member name of the archive's only WHDLoad slave, or None (no slave, several slaves, not an LHA archive)."""
    slaves = slave_members(path)
    return slaves[0] if len(slaves) == 1 else None


# The sentence of an archive that holds several slaves (interface string `amiga_several_slaves`, translated at display time).
SEVERAL_SLAVES = 'holds several WHDLoad slaves ({log}): one install per archive is expected.'


def no_install_reason(path: Path) -> str:
    """Why an .lha that slave_member refused is no Amiga install: no slave at all, or several (one install per archive)."""
    slaves = slave_members(path)
    if len(slaves) > 1:
        names = ', '.join(Path(name).name for name in slaves[:3]) + (', …' if len(slaves) > 3 else '')
        return f'{Path(path).name} ' + SEVERAL_SLAVES.format(log=names)
    return f'{Path(path).name} holds no WHDLoad slave (.Slave): not an Amiga WHDLoad install.'


def slave_wants_a1200(path: Path) -> bool:
    """True when the install's slave asks for a 68020 or for AGA (its WHDLF_Req68020 or WHDLF_ReqAGA flag): it is an Amiga 1200's.
    A slave that tests the machine itself without either flag is told by the folder or the player's choice instead."""
    from . import amiga_whdload
    path = Path(path)
    try:
        if path.stat().st_size > MAX_ARCHIVE_BYTES:
            return False
        install = amiga_whdload.install(path.read_bytes())
    except (OSError, ValueError):
        return False
    return bool({'Req68020', 'ReqAGA'} & set(install.slave.flag_names))


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


def archive_title(stem: str) -> str:
    """A WHDLoad archive's name as a title (`ChaosEngine_v1.2_AGA_1324`, `Zool2_v1.0_AGA_0415`, `Turrican2_v1.4`): the version,
    the chipset and the number dropped, the joined words split (`Chaos Engine`, `Zool 2`). '' for a name of another shape."""
    if not (re.fullmatch(r'[A-Za-z0-9&!\'+-]+(?:_[A-Za-z0-9.&+-]+)*_\d{3,5}', stem or '')
            or re.fullmatch(r'[A-Za-z0-9&!\'+-]+_v\d+(?:\.\d+)*[a-z]?(?:_[A-Za-z0-9.&+-]+)*', stem or '')):
        return ''
    words = re.sub(r'(?<=[a-z])(?=[A-Z0-9])|(?<=[0-9])(?=[A-Z][a-z])', ' ', stem.split('_', 1)[0])
    return words.strip() if len(words) < 120 else ''


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
