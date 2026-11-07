"""The player's own Atari ST TOS (MIT): one image or a folder of images, recognised by content, never changed or copied anywhere
but the conversion's own work folder and the player's own export (as the X68000 IPL and the Amiga Kickstart).

The plain ST, STF and Mega ST of the first scope boot TOS 1.00, 1.02 or 1.04: 192 KiB images mapped at $FC0000. An image is
recognised by its header (the branch at offset 0, the version word at 2, the base address at 8, the country code at $1D),
never by its name. EmuTOS, the default for a player without his own TOS, is fetched by the converter (atarist_emutos); an
EmuTOS image (it presents itself as TOS 1.04) is not taken for the player's own TOS.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

TOS_SIZE = 192 * 1024
TOS_BASE = 0xFC0000
VERSIONS = (0x0100, 0x0102, 0x0104)
# TOS country codes (header byte $1D, the low bit is the PAL/NTSC flag in TOS 1.02 and later): the names shown to the player.
COUNTRIES = {0: 'USA', 1: 'Germany', 2: 'France', 3: 'United Kingdom', 4: 'Spain', 5: 'Italy', 6: 'Sweden', 7: 'Switzerland (French)',
             8: 'Switzerland (German)', 9: 'Turkey', 10: 'Finland', 11: 'Norway', 12: 'Denmark', 13: 'Saudi Arabia', 14: 'Netherlands'}
MAX_FOLDER_FILES = 400


@dataclass(frozen=True)
class TosImage:
    path: Path
    version: int          # 0x0104 for TOS 1.04
    country: int
    pal: bool
    sha256: str
    size: int
    player_supplied = True

    @property
    def key(self) -> str:
        """The TOS part of a game's private memory: the first 16 digits of the image's SHA-256."""
        return self.sha256[:16]

    def version_text(self) -> str:
        return f'{self.version >> 8}.{self.version & 0xff:02x}'

    def label(self) -> str:
        return f'TOS {self.version >> 8}.{self.version & 0xff:02x} ({COUNTRIES.get(self.country, "country %d" % self.country)})'

    def data(self) -> bytes:
        blob = self.path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != self.sha256:
            raise ValueError(f'{self.path.name} changed while the converter was reading it.')
        return blob


def identify(path: Path) -> TosImage | None:
    """The TOS image a file holds, or None (another file, another TOS, a TOS of a later model)."""
    path = Path(path)
    try:
        if path.stat().st_size != TOS_SIZE:
            return None
        blob = path.read_bytes()
    except OSError:
        return None
    if len(blob) != TOS_SIZE or blob[0] != 0x60:
        return None
    version = int.from_bytes(blob[2:4], 'big')
    base = int.from_bytes(blob[8:12], 'big')
    if version not in VERSIONS or base != TOS_BASE or blob[0x2C:0x30] == b'ETOS':
        return None
    country = blob[0x1D] >> 1
    pal = bool(blob[0x1D] & 1) if version >= 0x0102 else country != 0
    return TosImage(path, version, country, pal, hashlib.sha256(blob).hexdigest(), len(blob))


def candidates(path) -> list[TosImage]:
    """Every TOS 1.0x image of a file or a folder (its files only, not its subfolders), best first: the latest version, then
    the United Kingdom, the USA and the other countries in their code order, then the file name."""
    path = Path(path)
    files = [path] if path.is_file() else sorted(p for p in path.iterdir() if p.is_file())[:MAX_FOLDER_FILES] if path.is_dir() else []
    found = [image for image in map(identify, files) if image is not None]
    preference = {3: 0, 0: 1}
    return sorted(found, key=lambda t: (-t.version, preference.get(t.country, 2 + t.country), t.path.name.casefold()))


def require(option, language: str = 'en') -> TosImage | None:
    """The player's TOS chosen by the Options path (a file or a folder): None when no path is set (EmuTOS is used); a
    ValueError with a sentence when the path holds no TOS 1.00-1.04 image."""
    if not option:
        return None
    path = Path(option)
    found = candidates(path)
    if not found:
        raise ValueError(f'{path.name or path}: no Atari ST TOS 1.00, 1.02 or 1.04 image (192 KiB) was found there.')
    return found[0]
