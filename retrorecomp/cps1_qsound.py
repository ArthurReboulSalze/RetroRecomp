"""The QSound DSP ROM of the CPS-1.5 boards: the player's own dump, found, checked and handed to the board.

The QSound chip (DL-1425) holds a 4,096-word internal ROM that its model reads for the filter, pan and ADPCM tables (and that the DSP16
runs): `dl-1425.bin` in MAME, 24,576 bytes of which the first 8,192 are the internal ROM. It is a part of the player's hardware like a
BIOS: the converter never ships it and never downloads it. It is chosen in Options (or with `--qsound-rom`), as a file or as the
`qsound.zip` that MAME and Batocera keep it in, and recognised by its CRC and SHA-1, never by its name. A conversion of a QSound set
without it is refused with a named reason; the exported game carries the player's own copy of its first 8,192 bytes, as it carries the
rest of the player's ROMs.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import zlib
from zipfile import BadZipFile, ZipFile

from .paths import selected_bios_path

NAME = 'dl-1425.bin'
CRC32 = 0xd6cf5ef5
SHA1 = '555f50fe5cdf127619da7d854c03f4a244a0c501'
SIZE = 0x6000              # the file: MAME loads the first 0x2000 bytes and ignores the rest
INTERNAL_BYTES = 0x2000    # the chip's internal ROM
MAX_ARCHIVE = 8 * 1024 * 1024


def _check(data: bytes) -> bool:
    return len(data) == SIZE and zlib.crc32(data) == CRC32 and hashlib.sha1(data).hexdigest() == SHA1


def read_dump(path: str | Path | None) -> bytes:
    """The 24,576 bytes of the DSP ROM file, from a file or from a ZIP whose member has this CRC and size (the name is not looked at).
    ValueError, with the reason, when there is none."""
    path = selected_bios_path(path)
    if path is None:
        raise ValueError('No QSound DSP ROM selected.')
    try:
        if path.suffix.lower() == '.zip':
            if path.stat().st_size > MAX_ARCHIVE:
                raise ValueError('The archive is too large for a QSound DSP ROM.')
            with ZipFile(path) as archive:
                for entry in archive.infolist():
                    if entry.file_size == SIZE and entry.CRC == CRC32 and not entry.flag_bits & 1:
                        data = archive.read(entry)
                        if _check(data):
                            return data
            raise ValueError('The archive holds no file with the CRC of the QSound DSP ROM (dl-1425.bin, CRC d6cf5ef5).')
        if path.stat().st_size != SIZE:
            raise ValueError('This file is not the QSound DSP ROM (dl-1425.bin, 24,576 bytes).')
        data = path.read_bytes()
    except (OSError, BadZipFile) as error:
        raise ValueError(f'The QSound DSP ROM cannot be read: {error}') from error
    if not _check(data):
        raise ValueError('This file is not the QSound DSP ROM (dl-1425.bin, CRC d6cf5ef5).')
    return data


def validate_dsp_rom(path) -> dict:
    """What the Options window checks: the identity of the dump, or ValueError."""
    data = read_dump(path)
    return {'name': NAME, 'bytes': len(data), 'crc32': f'{CRC32:08x}', 'sha1': SHA1, 'sha256': hashlib.sha256(data).hexdigest()}


def internal_rom(path) -> bytes:
    """The chip's internal ROM (the first 8,192 bytes), what the board needs."""
    return read_dump(path)[:INTERNAL_BYTES]


def needs_dsp_rom(game: dict) -> bool:
    return game.get('machine') == 'qsound'


def path_needs_dsp_rom(path: Path) -> bool:
    """Whether the romset at `path` is a QSound set (False for anything the CPS-1 reader does not recognise)."""
    from . import cps1, cps1_catalogue
    try:
        return needs_dsp_rom(cps1_catalogue.by_set()[cps1.identify_set(Path(path))['set']])
    except (ValueError, KeyError, OSError):
        return False
