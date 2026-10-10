"""Validated 16-bit cartridge identities. Inputs are always read-only."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import zlib


@dataclass(frozen=True)
class Cartridge16:
    path: Path
    data: bytes
    system_id: str
    title: str
    standard: str
    mapping: str
    copier_header: bool = False

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()

    @property
    def crc32(self) -> int:
        return zlib.crc32(self.data)

    def metadata(self) -> dict:
        return {"name": self.path.name, "bytes": len(self.data),
                "system_id": self.system_id, "sha256": self.sha256,
                "crc32": f"{self.crc32:08X}", "title": self.title,
                "standard": self.standard, "mapping": self.mapping,
                "copier_header_removed": self.copier_header}


def cartridge_bytes(path: Path, extensions: tuple[str, ...]) -> bytes:
    from .systems import archive_rom
    from .core import ConversionError
    if path.suffix.casefold() == '.zip':
        suffix, data = archive_rom(path)
        if suffix not in extensions:
            raise ConversionError('The ZIP contains a cartridge for another console.')
        return data
    if path.suffix.casefold() not in extensions:
        raise ConversionError('Unsupported cartridge format.')
    if path.stat().st_size > 8 * 1024 * 1024 + 512:
        raise ConversionError('Cartridge exceeds the 8 MiB input limit.')
    return path.read_bytes()


def is_megadrive(data: bytes) -> bool:
    return len(data) >= 0x400 and data[0x100:0x104] == b'SEGA'


def megadrive_regions(data: bytes) -> int:
    """Read letter codes or the ASCII hexadecimal region bit mask.

    Only the three region bytes are defined; the rest of $1F0-$1FF is reserved.
    A lone E is ambiguous between the two formats and retains its usual PAL
    meaning. See https://plutiedev.com/rom-header.
    """
    # Some older commercial headers spell out one region. Accept only the
    # complete, padded label seen in cartridge bytes, never a filename guess.
    legacy_region = data[0x1f0:0x200].rstrip(b'\0 ').upper()
    if legacy_region in (b'JAPAN', b'USA', b'EUROPE'):
        return {b'JAPAN': 1, b'USA': 4, b'EUROPE': 8}[legacy_region]
    regions = ''.join(data[0x1f0:0x1f3].decode('ascii', errors='replace')
                      .upper().replace('\0', ' ').split())
    if len(regions) == 1 and regions in '0123456789ABCDF':
        return int(regions, 16)
    if regions and all(letter in 'JUE' for letter in regions):
        return (1 if 'J' in regions else 0) | (4 if 'U' in regions else 0) | (8 if 'E' in regions else 0)
    return 0


def megadrive_standard(data: bytes) -> str:
    mask = megadrive_regions(data)
    ntsc, pal = bool(mask & 5), bool(mask & 10)
    return 'multi' if ntsc and pal else 'pal' if pal else 'ntsc' if ntsc else 'unknown'


def read_megadrive_rom(path: Path) -> Cartridge16:
    from .core import ConversionError
    path = path.resolve()
    data = cartridge_bytes(path, ('.md', '.gen', '.bin', '.rom'))
    if len(data) < 0x8000 or len(data) > 8 * 1024 * 1024 or len(data) % 2 or not is_megadrive(data):
        raise ConversionError('Expected a linear Mega Drive cartridge with a SEGA header; interleaved SMD is not supported.')
    standard = megadrive_standard(data)
    title = data[0x150:0x180].decode('ascii', errors='replace').strip('\0 ') or path.stem
    return Cartridge16(path, data, 'md', ' '.join(title.split()), standard, 'linear')


def snes_title(data: bytes) -> str | None:
    """Validate the header's JIS X 0201 ASCII and single-byte katakana title."""
    raw = data.rstrip(b'\0 ')
    if not raw or not all(0x20 <= value <= 0x7e or 0xa1 <= value <= 0xdf for value in raw):
        return None
    return raw.decode('shift_jis')


def snes_header(data: bytes) -> tuple[int, str] | None:
    """Require a credible title, ROM map, reset vector and checksum pair."""
    matches = []
    for offset, mapping in ((0x7fc0, 'lorom'), (0xffc0, 'hirom'), (0x40ffc0, 'exhirom')):
        if offset + 64 > len(data):
            continue
        title = snes_title(data[offset:offset + 21])
        mode = data[offset + 21] & 0x2f
        allowed = (0x20, 0x22) if mapping == 'lorom' else (0x21,) if mapping == 'hirom' else (0x25,)
        complement = int.from_bytes(data[offset + 28:offset + 30], 'little')
        checksum = int.from_bytes(data[offset + 30:offset + 32], 'little')
        vector = int.from_bytes(data[offset + 60:offset + 62], 'little')
        if (title and mode in allowed
                and checksum ^ complement == 0xffff and checksum != 0
                and vector >= 0x8000 and data[offset + 23] <= 13):
            matches.append((offset, mapping))
    return matches[0] if len(matches) == 1 else None


def read_snes_rom(path: Path) -> Cartridge16:
    from .core import ConversionError
    path = path.resolve()
    data = cartridge_bytes(path, ('.sfc', '.smc', '.bin', '.rom'))
    copier = len(data) % 0x8000 == 512
    if copier:
        data = data[512:]
    header = snes_header(data)
    if not header or len(data) % 0x8000 or len(data) > 8 * 1024 * 1024:
        raise ConversionError('SNES cartridge header could not be validated.')
    offset, mapping = header
    region = data[offset + 25]
    standard = 'ntsc' if region in (0, 1, 13, 15, 16) else 'pal'
    title = snes_title(data[offset:offset + 21])
    assert title is not None  # The same title was validated in snes_header.
    return Cartridge16(path, data, 'snes', title, standard, mapping, copier)
