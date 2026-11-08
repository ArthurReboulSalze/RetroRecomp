"""Nintendo 64 input: a cartridge image as the player dumped it, read without changing it (MIT).

The three byte orders of the dumps in circulation are told apart by the first word of the image, never by the extension (a file
named `.n64` is often byte-swapped `.v64` content): big-endian (`.z64`, 80 37 12 40), byte-swapped in 16-bit pairs (`.v64`,
37 80 40 12) and word-swapped (`.n64`, 40 12 37 80). The image is put back in big-endian order in memory; the game's identity is the
SHA-256 of that big-endian image, so the same cartridge dumped in two orders is one game in the library. The header gives the
internal name, the game code, the country (and so PAL or NTSC) and the revision. Nothing in the image is run here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from .core import ConversionError
from .paths import ASSETS

EXTENSIONS = ('.z64', '.v64', '.n64')
# A shared extension: claimed only when the content is an N64 image (`Zelda64.rom`, for one, is Ocarina of Time USA).
CONTENT_EXTENSIONS = ('.rom',)
MIN_BYTES = 0x101000          # the header, the boot code and the first megabyte the boot copies
MAX_BYTES = 64 * 1024 * 1024  # the largest cartridge (512 Mbit)
ORDERS = {bytes.fromhex('80371240'): 'z64', bytes.fromhex('37804012'): 'v64', bytes.fromhex('40123780'): 'n64'}
# Country codes of PAL cartridges (the rest are NTSC: A all, B Brazil, C China, E USA, G Gateway NTSC, J Japan, K Korea, N Canada).
PAL_COUNTRIES = frozenset('DFHILPSUWXYZ')


def converter_available() -> bool:
    """True when this installation carries the Nintendo 64 converter's own native files (the profile is offered only then)."""
    return all((ASSETS / name).is_file() for name in (
        'native/n64_machine/CMakeLists.txt', 'native/n64_machine/n64_session.cpp', 'native/n64_machine/glue/parallel_glue.cpp',
        'native/hostkit/adapters/rrhk_n64.inc'))


def byte_order(head: bytes) -> str | None:
    """'z64', 'v64' or 'n64' from the first word of an image; None when it is not an N64 cartridge image."""
    return ORDERS.get(bytes(head[:4]))


def to_big_endian(data: bytes, order: str) -> bytes:
    """The image in the console's own byte order."""
    if order == 'z64':
        return bytes(data)
    out = bytearray(data)
    if order == 'v64':
        out[0::2], out[1::2] = data[1::2], data[0::2]
    else:
        out[0::4], out[1::4], out[2::4], out[3::4] = data[3::4], data[2::4], data[1::4], data[0::4]
    return bytes(out)


@dataclass(frozen=True)
class N64Header:
    name: str
    game_code: str        # category + two letters + country, e.g. 'NSMP'
    country: str
    revision: int
    entry_point: int
    crc1: int
    crc2: int

    @property
    def pal(self) -> bool:
        return self.country in PAL_COUNTRIES


def parse_header(big: bytes) -> N64Header:
    def word(offset):
        return int.from_bytes(big[offset:offset + 4], 'big')
    name = big[0x20:0x34].decode('ascii', 'replace').rstrip(' \0').strip()
    code = big[0x3B:0x3F].decode('ascii', 'replace')
    return N64Header(name=name, game_code=code, country=code[3:4], revision=big[0x3F], entry_point=word(0x08),
                     crc1=word(0x10), crc2=word(0x14))


def recognise(path: Path) -> bool:
    """True when `path` holds an N64 cartridge image (any byte order, a plausible size and boot entry point)."""
    try:
        size = Path(path).stat().st_size
        with open(path, 'rb') as stream:
            head = stream.read(0x40)
    except OSError:
        return False
    order = byte_order(head)
    if order is None or not MIN_BYTES <= size <= MAX_BYTES or size % 4:
        return False
    header = parse_header(to_big_endian(head, order))
    return (header.entry_point >> 24) in (0x80, 0xA0)


@dataclass(frozen=True)
class N64Rom:
    path: Path
    order: str
    file_sha256: str
    sha256: str           # of the big-endian image: the game's identity
    size: int
    header: N64Header

    @property
    def game_key(self) -> str:
        return self.sha256

    @property
    def title(self) -> str:
        stem = self.path.stem.strip()
        return stem or self.header.name or 'Nintendo 64 game'

    def data(self) -> bytes:
        """The big-endian image (read again from the file, checked against the identity)."""
        raw = Path(self.path).read_bytes()
        big = to_big_endian(raw, self.order)
        if hashlib.sha256(big).hexdigest() != self.sha256:
            raise ConversionError('The Nintendo 64 image changed while it was being converted.')
        return big

    def metadata(self) -> dict:
        h = self.header
        return {'path': str(self.path), 'size': self.size, 'sha256': self.sha256, 'file_sha256': self.file_sha256,
                'byte_order': self.order, 'internal_name': h.name, 'game_code': h.game_code, 'country': h.country,
                'region': 'PAL' if h.pal else 'NTSC', 'revision': h.revision, 'entry_point': f'0x{h.entry_point:08x}',
                'crc1': f'0x{h.crc1:08x}', 'crc2': f'0x{h.crc2:08x}'}


def read_input(path) -> N64Rom:
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ConversionError(f'Cannot read the Nintendo 64 image: {exc.strerror or exc}') from None
    order = byte_order(raw)
    if order is None:
        raise ConversionError('This file is not a Nintendo 64 cartridge image (unknown first word).')
    if not MIN_BYTES <= len(raw) <= MAX_BYTES or len(raw) % 4:
        raise ConversionError('A Nintendo 64 image is 1 to 64 MiB, a multiple of four bytes.')
    big = to_big_endian(raw, order)
    header = parse_header(big)
    if (header.entry_point >> 24) not in (0x80, 0xA0):
        raise ConversionError('The Nintendo 64 header has no valid boot entry point.')
    return N64Rom(path=path, order=order, file_sha256=hashlib.sha256(raw).hexdigest(), sha256=hashlib.sha256(big).hexdigest(),
                  size=len(raw), header=header)


def video_mode(path) -> str:
    try:
        return 'pal' if read_input(path).header.pal else 'ntsc'
    except ConversionError:
        return 'ntsc'
