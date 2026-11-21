"""ColecoVision cartridge images: recognising and reading one. MIT, Retro-Recomp.

A ColecoVision cartridge is a plain ROM mapped from 8000h to the top of the address space (up to 32 KiB, no bank register in the
retail library). Its first two bytes are a header word the console's BIOS reads: 55h AAh or AAh 55h (the BIOS tells the two orders
apart; this reader only reports which one a file has). The dumps in circulation are a `.col` (the extension of the common sets),
sometimes a `.bin` or a `.rom`, alone or in a ZIP, and carry no copier header, so none is removed here.

What the reader accepts is what the machine can hold without a mapper: a whole number of kilobytes from 4 KiB to 32 KiB (the
cartridge window is 8000h-FFFFh). A larger file is a bank-switched board (MegaCart and others, homebrew) or unknown and is refused
with a sentence, not guessed at. The extension `.col`, the folder or the player's choice decides that a file is the ColecoVision's
(retrorecomp/systems/coleco.py); a `.bin`, a `.rom` or a ZIP member must also begin with a header word.

Nothing in the cartridge is kept but its bytes' SHA-256 and the bytes themselves, in memory, for the conversion.
"""
from __future__ import annotations

from dataclasses import dataclass

# The file names the reader takes, alone or as the one member of a ZIP.
EXTENSIONS = ('.col', '.bin', '.rom')
MIN_CARTRIDGE = 0x1000        # 4 KiB
MAX_CARTRIDGE = 0x8000        # 32 KiB: the cartridge window 8000h-FFFFh, with no bank switching
UNIT = 0x400                  # a cartridge is a whole number of kilobytes
# The header word at the cartridge's first two bytes: which order the file has.
HEADER_WORDS = {b'\x55\xAA': 'title', b'\xAA\x55': 'direct'}


@dataclass(frozen=True)
class Cartridge:
    """A cartridge as the converter reads it: its bytes (from a file or from a ZIP member) and their SHA-256."""
    path: object
    data: bytes
    sha256: str
    member: str = ''        # the cartridge's name inside a ZIP, '' for a file

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def header(self) -> str:
        """'title' (55h AAh), 'direct' (AAh 55h), or '' when the file begins with neither word."""
        return header_kind(self.data)


def header_kind(data: bytes) -> str:
    """Which header word `data` begins with: 'title' (55h AAh), 'direct' (AAh 55h), or '' for neither."""
    return HEADER_WORDS.get(bytes(data[:2]), '')


def size_problem(size: int) -> str | None:
    """Why a file of `size` bytes is not a ColecoVision cartridge this reader takes, as a sentence; None when it is one."""
    if size > MAX_CARTRIDGE:
        return (f'{size} bytes is larger than 32 KiB, the cartridge window of the ColecoVision: a bigger file is a bank-switched or '
                'unknown board (MegaCart and others), which is not converted.')
    if size < MIN_CARTRIDGE:
        return f'{size} bytes is smaller than 4 KiB, the smallest ColecoVision cartridge read.'
    if size % UNIT:
        return f'{size} bytes is not a whole number of kilobytes (a ColecoVision cartridge is 4 to 32 KiB in 1 KiB steps).'
    return None


def read_cartridge(path, *, require_header: bool = False) -> Cartridge:
    """The cartridge at `path` (a .col, a .bin or .rom, or a ZIP holding exactly one of them), refused with a sentence when it is none.

    `require_header`: the file must begin with a header word (asked of a .bin, a .rom or a ZIP member, which say nothing by their name)."""
    import hashlib
    import zipfile
    from pathlib import Path
    path = Path(path)
    if path.suffix.lower() == '.zip':
        import zlib
        # A ZIP that cannot be read whole is refused with a sentence, as the other readers refuse it: a damaged one (BadZipFile: a bad
        # CRC too), an encrypted member (RuntimeError), a compression Python does not read (NotImplementedError, a RuntimeError), a
        # broken deflate stream (zlib.error) or a cut file (EOFError).
        try:
            with zipfile.ZipFile(path) as bundle:
                names = [n for n in bundle.namelist() if not n.endswith('/') and n.lower().endswith(EXTENSIONS)]
                if len(names) != 1:
                    raise ValueError(f'{path.name}: the ZIP must hold exactly one ColecoVision cartridge (.col, .bin or .rom).')
                problem = size_problem(bundle.getinfo(names[0]).file_size)
                if problem:
                    raise ValueError(f'{path.name}: {problem}')
                data = bundle.read(names[0])
                member = names[0]
        except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError) as error:
            raise ValueError(f'{path.name}: not a readable ZIP ({error}).') from None
        require_header = require_header or not member.lower().endswith('.col')
    else:
        if path.suffix.lower() not in EXTENSIONS:
            raise ValueError(f'{path.name}: not a ColecoVision cartridge name (.col, .bin, .rom or a ZIP holding one).')
        problem = size_problem(path.stat().st_size)
        if problem:
            raise ValueError(f'{path.name}: {problem}')
        data = path.read_bytes()
        member = ''
        require_header = require_header or path.suffix.lower() != '.col'
    if require_header and not header_kind(data):
        raise ValueError(f'{path.name}: it does not begin with a ColecoVision header word (55h AAh or AAh 55h).')
    return Cartridge(path, data, hashlib.sha256(data).hexdigest(), member)
