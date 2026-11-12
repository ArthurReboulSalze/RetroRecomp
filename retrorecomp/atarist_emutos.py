"""EmuTOS for the Atari ST (MIT; EmuTOS itself is GPL-2.0-or-later): the TOS a game boots when the player gives none.

EmuTOS is not part of Retro-Recomp's files. The first conversion that needs it fetches the two files of its pinned release from
the EmuTOS project on SourceForge: the 192 KiB images (`emutos-192k-1.4.zip`) and their complete source (`emutos-src-1.4.tar.gz`),
into the converter's dependency folder. Their sizes and SHA-256 are pinned here and checked on every use, not only after the
download, so a changed or truncated file is refused and fetched again. The machine boots the United Kingdom image (PAL, English).
An exported game that boots EmuTOS embeds that image and the source archive, which the game writes out on request
(`--write-sources DIR`), as the GPL asks of whoever passes the executable on.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import zipfile

VERSION = '1.4'
RETRY_SECONDS = 3
# The commit of the release's tag VERSION_1_4 in github.com/emutos/emutos (the release files themselves come from SourceForge).
RELEASE_REV = '978e37569bff95841e42675d11fcc6799aad8483'
_SITE = f'https://downloads.sourceforge.net/project/emutos/emutos/{VERSION}/'
BINARY = (f'emutos-192k-{VERSION}.zip', 2260230, '59abac06a2d29b0864c5a7cfb2af65f022c337aed34188e174a9a08cc737e4bc')
SOURCE = (f'emutos-src-{VERSION}.tar.gz', 1299705, '98977ab2593d9ab81d6fcf9629f6781369912e3fe05c224a35147d5665749702')
IMAGE = (f'emutos-192k-{VERSION}/etos192uk.img', 196608, '2d6f3f6f304c9ba340aff8d47ba72b274ae29b8fbe6214138846dada97edf0f3')
LIMIT = 8 * 1024 * 1024
MAGIC_OFFSET = 0x2C     # "ETOS" in the OS header of an EmuTOS image (a real TOS has other bytes there)


def directory() -> Path:
    from .paths import ROOT
    return ROOT / '.deps' / f'emutos-{VERSION}'


def is_emutos(blob: bytes) -> bool:
    return blob[MAGIC_OFFSET:MAGIC_OFFSET + 4] == b'ETOS'


def _checked(path: Path, size: int, digest: str) -> bool:
    try:
        if path.stat().st_size != size:
            return False
        hasher = hashlib.sha256()
        with path.open('rb') as stream:
            while block := stream.read(1 << 20):
                hasher.update(block)
        return hasher.hexdigest() == digest
    except OSError:
        return False


def _fetch(name: str, size: int, digest: str, emit) -> Path:
    from .updater import download_pinned
    target = directory() / name
    if _checked(target, size, digest):
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(name + '.part')
    emit(f'Atari ST: fetching {name} (EmuTOS {VERSION}, {size // 1024} KiB) from the EmuTOS project.')
    try:
        mismatch = f'{name}: the downloaded file is not the pinned one.'
        download_pinned(_SITE + name, partial, size, digest, LIMIT, mismatch, wait=RETRY_SECONDS)
        partial.replace(target)
    except Exception as exc:  # noqa: BLE001 - every failure is the same sentence for the player
        partial.unlink(missing_ok=True)
        raise ValueError(f'EmuTOS {VERSION} could not be fetched ({exc.__class__.__name__}): choose your own TOS in Options, '
                         'or try again once online.') from None
    if not _checked(target, size, digest):
        raise ValueError(f'{name}: the stored file is not the pinned one.')
    return target


@dataclass(frozen=True)
class EmuTos:
    """The EmuTOS image the machine boots, with the same reading side as a player's TosImage."""
    archive: Path
    source: Path
    sha256: str               # the image's (IMAGE)
    size: int
    version: int = 0x0104     # what its header says to programs (EmuTOS presents itself as TOS 1.04)
    country: int = 3
    pal: bool = True
    player_supplied = False
    key = f'emutos-{VERSION}'

    def label(self) -> str:
        return f'EmuTOS {VERSION} (United Kingdom)'

    def version_text(self) -> str:
        return f'EmuTOS {VERSION}'

    def data(self) -> bytes:
        if not _checked(self.archive, BINARY[1], BINARY[2]):
            raise ValueError(f'{BINARY[0]} changed while the converter was reading it.')
        with zipfile.ZipFile(self.archive) as archive:
            blob = archive.read(IMAGE[0])
        if len(blob) != IMAGE[1] or hashlib.sha256(blob).hexdigest() != IMAGE[2] or not is_emutos(blob):
            raise ValueError(f'{BINARY[0]}: the EmuTOS image is not the pinned one.')
        return blob


def require(emit=print) -> EmuTos:
    """EmuTOS at its pin: fetched on first use, both files checked now; a ValueError with a sentence otherwise."""
    archive = _fetch(*BINARY, emit)
    source = _fetch(*SOURCE, emit)
    tos = EmuTos(archive, source, IMAGE[2], IMAGE[1])
    tos.data()
    return tos
