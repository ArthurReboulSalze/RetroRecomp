"""Game Boy Advance cartridge reader (experimental profile: see docs/GAME_BOY_ADVANCE.md).

Identification only: the header is checked, the cartridge is hashed and the save chip named from the library
identification strings the Nintendo SDK links into a game ("SRAM_V", "FLASH1M_V", "EEPROM_V"...). Nothing is
converted here. A cartridge image is never copied or stored: the reader keeps numbers and names about it.

The player's BIOS is a firmware the player supplies (like the Neo Geo BIOS and the X68000 IPL). Only its size
and its hash are used here: the one known image is recognised by its SHA-1, a public identification value.
"""
from __future__ import annotations

import hashlib
import zlib
from dataclasses import dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from .core import ConversionError

MIN_ROM_BYTES = 0xC0
MAX_ROM_BYTES = 32 * 1024 * 1024
# SHA-1 of the one 16 KiB system ROM the pinned engine recognises (an identification value, not content).
KNOWN_BIOS_SHA1 = '300c20df6731a33952ded8c436f7f186d25d3492'
BIOS_BYTES = 16 * 1024
# Save library identification strings, longest first so that FLASH1M_V is not read as FLASH_V.
SAVE_SIGNATURES = (('FLASH1M_V', 'flash128'), ('FLASH512_V', 'flash64'), ('FLASH_V', 'flash64'),
                   ('SRAM_F_V', 'sram'), ('SRAM_V', 'sram'), ('EEPROM_V', 'eeprom'))
SAVE_LABELS = {'none': 'no save chip found', 'sram': 'SRAM', 'flash64': 'Flash 64 KiB', 'flash128': 'Flash 128 KiB',
               'eeprom': 'EEPROM'}


@dataclass(frozen=True)
class GbaRom:
    path: Path
    size: int
    crc32: int
    sha256: str
    header_title: str
    game_code: str
    maker: str
    version: int
    save_type: str
    save_signature: str
    system_id: str = 'gba'

    @property
    def game_key(self) -> str:
        return self.sha256

    def metadata(self) -> dict:
        return {'name': self.path.name, 'bytes': self.size, 'crc32': f'{self.crc32:08X}', 'sha256': self.sha256,
                'header_title': self.header_title, 'game_code': self.game_code, 'maker': self.maker,
                'version': self.version, 'save_type': self.save_type, 'save_signature': self.save_signature,
                'system_id': self.system_id}


def complement_check(data: bytes) -> int:
    """The header checksum of bytes 0xA0 to 0xBC, as the system ROM computes it (a value about the header)."""
    return (-sum(data[0xA0:0xBD]) - 0x19) & 0xFF


def _text(raw: bytes) -> str:
    return raw.split(b'\0', 1)[0].decode('ascii', errors='replace').strip()


def save_type(data: bytes) -> tuple[str, str]:
    """('sram' | 'flash64' | 'flash128' | 'eeprom' | 'none', the identification string found)."""
    for signature, kind in SAVE_SIGNATURES:
        if data.find(signature.encode('ascii')) >= 0:
            return kind, signature
    return 'none', ''


def parse_header(data: bytes) -> dict:
    """The fields of a valid cartridge header; ConversionError when this is not a Game Boy Advance cartridge."""
    if not MIN_ROM_BYTES <= len(data) <= MAX_ROM_BYTES:
        raise ConversionError('Invalid Game Boy Advance cartridge size (expected 192 bytes to 32 MiB).')
    if data[0xB2] != 0x96:
        raise ConversionError('This file has no Game Boy Advance cartridge header (fixed byte 0xB2 is not 0x96).')
    if data[3] != 0xEA and data[3] != 0xEB:
        raise ConversionError('This file does not begin with an ARM branch: it is not a Game Boy Advance cartridge.')
    if complement_check(data) != data[0xBD]:
        raise ConversionError('The Game Boy Advance header checksum does not match.')
    code = data[0xAC:0xB0]
    if not all(0x20 <= value < 0x7F for value in code):
        raise ConversionError('The Game Boy Advance game code is not text.')
    return {'title': _text(data[0xA0:0xAC]), 'game_code': code.decode('ascii'), 'maker': _text(data[0xB0:0xB2]),
            'version': data[0xBC]}


def _rom_from_zip(path: Path) -> bytes:
    """The one `.gba` member of a ZIP, read without extracting it beside the source.

    The shared reader of cartridges in ZIPs (`systems.archive_rom`) is limited to the extensions of
    `systems.MAX_ARCHIVED_ROM_BYTES`; `.gba` joins that table when the maintainer takes the one edit that moves every game stamp."""
    try:
        with ZipFile(path) as archive:
            members = [entry for entry in archive.infolist()
                       if not entry.is_dir() and Path(entry.filename).suffix.casefold() == '.gba']
            if len(members) != 1:
                raise ConversionError('ZIP must contain exactly one Game Boy Advance cartridge (.gba).')
            if members[0].file_size > MAX_ROM_BYTES:
                raise ConversionError('Archived ROM exceeds the cartridge size limit.')
            with archive.open(members[0]) as source:
                data = source.read(MAX_ROM_BYTES + 1)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ConversionError(f'Cannot read cartridge ZIP: {exc}') from exc
    if len(data) > MAX_ROM_BYTES:
        raise ConversionError('Archived ROM exceeds the cartridge size limit.')
    return data


def zip_holds_cartridge(path: Path) -> bool:
    """True for a ZIP with exactly one `.gba` member (the names only; nothing is extracted)."""
    try:
        with ZipFile(path) as archive:
            return sum(not name.endswith('/') and Path(name).suffix.casefold() == '.gba'
                       for name in archive.namelist()) == 1
    except (BadZipFile, OSError):
        return False


def read_bytes(path) -> bytes:
    """The cartridge image of a `.gba` file or a single-ROM ZIP, header checked (a conversion writes it to its project)."""
    path = Path(path).resolve()
    suffix = path.suffix.casefold()
    if suffix == '.zip':
        data = _rom_from_zip(path)
    elif suffix == '.gba':
        with path.open('rb') as source:
            data = source.read(MAX_ROM_BYTES + 1)
    else:
        raise ConversionError('Choose a Game Boy Advance .gba cartridge or a single-ROM ZIP.')
    parse_header(data)
    return data


def read_rom(path) -> GbaRom:
    path = Path(path).resolve()
    data = read_bytes(path)
    header = parse_header(data)
    kind, signature = save_type(data)
    return GbaRom(path, len(data), zlib.crc32(data), hashlib.sha256(data).hexdigest(), header['title'],
                  header['game_code'], header['maker'], header['version'], kind, signature)


def bios_identity(value) -> str | None:
    """The SHA-256 of the player's system ROM when the file is there (the request names the firmware, not its path),
    else None."""
    from .paths import selected_bios_path
    chosen = selected_bios_path(value)
    if not chosen or not chosen.is_file():
        return None
    return hashlib.sha256(chosen.read_bytes()).hexdigest()


def bios_status(value) -> str:
    """'known' (size and SHA-1 of the supported image), 'unknown' (another file) or 'missing'."""
    from .paths import selected_bios_path
    chosen = selected_bios_path(value)
    if not chosen or not chosen.is_file():
        return 'missing'
    data = chosen.read_bytes()
    return 'known' if len(data) == BIOS_BYTES and hashlib.sha1(data).hexdigest() == KNOWN_BIOS_SHA1 else 'unknown'


def developer_available() -> bool:
    """True when this installation carries the Game Boy Advance converter files.

    Stage 2 of the profile: nothing converts yet, so no installation does. The conversion files will be listed here
    (the engine itself is fetched at its pinned revision on first conversion, like the other machines')."""
    return False
