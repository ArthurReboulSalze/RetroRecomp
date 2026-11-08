"""Sony PlayStation input: the player's disc, read in place and never changed (Retro-Recomp's own code, MIT).

The game's identity (`PsxInput.sha256`, the report's rom.sha256, the library key) is the digest of the disc as raw sectors
(psx_disc.Disc.digest): two containers of the same dump (an EBOOT and a CUE/BIN) are the same game. A multi-disc game (an EBOOT
holding several discs, or a playlist) is one game whose identity covers every disc in order. The digest reads the whole disc, so it
is computed once, when the conversion asks for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
import hashlib
from pathlib import Path

from . import psx_bios, psx_disc
from .core import ConversionError
from .paths import ASSETS

# A file of one of these extensions that is not a PlayStation disc is left to the other machines (None from `recognise`); an
# EBOOT is only ever a PlayStation (or a PSP) file, so its refusal is said.
OWN_EXTENSIONS = ('.pbp',)


def converter_available() -> bool:
    """True when this installation carries the PlayStation converter's own native files (the profile is offered only then).
    Native files only: a frozen converter keeps its Python modules inside the executable, never as .py files."""
    return all((ASSETS / name).is_file() for name in (
        'native/psx_machine/CMakeLists.txt', 'native/psx_machine/psx_session.c', 'native/hostkit/adapters/rrhk_psx.c'))


def described_by_sheet(path: Path) -> Path | None:
    """The CUE or CloneCD sheet beside a .bin/.img that names it (the sheet is the disc; the image is one of its files)."""
    path = Path(path)
    if path.suffix.lower() not in ('.bin', '.img'):
        return None
    for sheet in path.parent.iterdir():
        if sheet.suffix.lower() not in ('.cue', '.ccd') or not sheet.is_file():
            continue
        if sheet.suffix.lower() == '.ccd':
            if sheet.stem.lower() == path.stem.lower():
                return sheet
            continue
        try:
            disc = psx_disc.read_cue(sheet)
        except (psx_disc.DiscError, OSError, ValueError):
            continue
        try:
            if any(Path(s.path).resolve() == path.resolve() for s in disc.sources):
                return sheet
        finally:
            disc.close()
    return None


def recognise(path: Path):
    """None: not a PlayStation disc. True: a PlayStation disc. A string: a PlayStation file that cannot be converted (why)."""
    path = Path(path)
    suffix = path.suffix.lower()
    sheet = described_by_sheet(path)
    if sheet is not None:
        try:
            psx_disc.describe(sheet)
        except (psx_disc.DiscError, OSError, ValueError):
            return None
        return f'{path.name} is a file of {sheet.name}: convert the sheet.'
    try:
        identities = psx_disc.describe(path)
    except psx_disc.DiscError as error:
        return f'{path.name}: {error}' if suffix in OWN_EXTENSIONS else None
    except (OSError, ValueError):
        return None
    if not all(i.system_id.upper().startswith('PLAYSTATION') for i in identities):
        return f'{path.name} is not a PlayStation disc.' if suffix in OWN_EXTENSIONS else None
    return True


@dataclass
class PsxInput:
    path: Path
    size: int
    title: str
    discs: tuple            # psx_disc.DiscIdentity per disc

    @cached_property
    def sha256(self) -> str:
        """The digest of every disc in order (each disc's psx_disc digest)."""
        h = hashlib.sha256(b'rr-psx-game\0')
        for index in range(len(self.discs)):
            disc = psx_disc.open_disc(self.path, index)
            try:
                h.update(disc.digest().encode() + b'\0')
            finally:
                disc.close()
        return h.hexdigest()

    @property
    def game_key(self) -> str:
        return self.sha256

    @property
    def region(self) -> str | None:
        return self.discs[0].region

    @property
    def serial(self) -> str | None:
        return self.discs[0].serial

    def metadata(self) -> dict:
        return {'name': self.path.name, 'path': str(self.path), 'sha256': self.sha256, 'size': self.size,
                'format': self.discs[0].container, 'serial': self.serial, 'region': self.region,
                'discs': [d.metadata() for d in self.discs]}


def read_input(path) -> PsxInput:
    path = Path(path)
    try:
        identities = tuple(psx_disc.describe(path))
    except psx_disc.DiscError as error:
        raise ConversionError(f'{path.name}: {error}') from None
    if not identities:
        raise ConversionError(f'{path.name}: no disc.')
    if len({d.region for d in identities}) > 1:
        raise ConversionError(f'{path.name}: its discs are of different regions.')
    size = sum(p.stat().st_size for p in {Path(path)} | set(_files(path)))
    title = path.stem
    return PsxInput(path, size, title, identities)


def _files(path: Path) -> list[Path]:
    """Every file a disc reads (the sheet's images, a playlist's discs), for the size of the input."""
    out = []
    for index in range(psx_disc.disc_count(path)):
        disc = psx_disc.open_disc(path, index)
        try:
            out += [Path(s.path) for s in disc.sources]
        finally:
            disc.close()
    return out


def video_mode(path) -> str:
    try:
        region = psx_disc.describe(Path(path))[0].region
    except (psx_disc.DiscError, OSError, ValueError):
        return 'ntsc'
    return 'pal' if region == 'pal' else 'ntsc'


def bios_for(item, bios_option) -> psx_bios.Bios | None:
    """The player's BIOS for this disc (a file or a folder in the option), or None: the game then runs on OpenBIOS.

    `item` is the conversion's input or the batch's item (which knows only the disc's path)."""
    if not bios_option:
        return None
    region = getattr(item, 'region', None)
    if region is None:
        try:
            region = psx_disc.describe(Path(item.path))[0].region
        except (psx_disc.DiscError, OSError, ValueError):
            region = None
    return psx_bios.choose([Path(bios_option)], region)


def machine_identity(item: PsxInput, bios_option) -> str:
    """What the export depends on besides the disc: the BIOS chosen for it (its hash), or the free BIOS."""
    bios = bios_for(item, bios_option)
    tag = f'bios:{bios.sha256}' if bios else 'bios:openbios'
    return hashlib.sha256(b'rr-psx-machine\0' + tag.encode()).hexdigest()
