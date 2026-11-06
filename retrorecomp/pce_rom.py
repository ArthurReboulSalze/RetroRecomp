"""PC Engine HuCard images: read, decode and identify (docs/PC_ENGINE.md). No game byte is kept or written.

The engine (pcenginerecomp, pinned in upstreams.py) takes the dump policy as explicit options and guesses
nothing. This reader is where Retro-Recomp chooses them, with three written rules:

* **Header.** A file of 8 KiB banks plus exactly 512 bytes carries a copier header (`copier512`); the 512 bytes
  are skipped. Any other size that is not whole 8 KiB banks is refused.
* **Encoding.** The reset vector of bank 0 (bytes $1FFE/$1FFF) must point into $E000..$FFFF, where the CPU
  starts with every MPR at 0. A dump whose vector fails that test linearly but passes once each byte's bits are
  reversed is `bit-reversed` (some US TurboGrafx-16 dumps); one that passes neither is refused. One that passes both
  ways (a high byte of $E7, $EF, $F7 or $FF) is decided by the first instruction at the vector: `bit-reversed` only
  when it is SEI, NOP or CSH once the bits are turned and is none of them as given, `linear` otherwise (all such
  cards of the maintainer's library are linear, and they start with SEI).
* **Board.** 8 KiB to 1 MiB decoded is the standard map (`base`); exactly 2.5 MiB is the Street Fighter II
  mapper (`sf2`). The Populous RAM board, the SuperGrafx and CD images are not recognised: a size decides
  nothing else, and no title or checksum list is consulted.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

BANK = 0x2000
HEADER = 512
MAX_BASE_BYTES = 1024 * 1024
SF2_BYTES = 2621440
MAX_FILE_BYTES = SF2_BYTES + HEADER
_REVERSED = bytes(int(f'{value:08b}'[::-1], 2) for value in range(256))
# The first instruction of the reset code: SEI ($78), NOP ($EA) or CSH ($D4) starts 282 of the 286 HuCards of the
# maintainer's library (176, 94 and 12); only a tie between the two bit orders is decided by it.
_RESET_OPCODES = frozenset((0x78, 0xEA, 0xD4))


class PcEngineRomError(ValueError):
    """The file is not a HuCard image this converter reads."""


# What a PC Engine conversion needs from the installation itself (the engine's sources are fetched at their pinned
# revision on the first conversion, like the other machines' dependencies; the HuCard always comes from the player).
CONVERTER_FILES = ('native/pce_machine.cpp', 'native/pce_machine.h', 'native/pce_main.c',
                   'native/hostkit/adapters/rrhk_pce.c')


def converter_available() -> bool:
    """True when this installation carries the PC Engine converter's own native files."""
    from .paths import ASSETS
    return all((ASSETS / name).is_file() for name in CONVERTER_FILES)


@dataclass(frozen=True)
class HuCard:
    path: Path
    sha256: str              # the file as given (header included): the game's key
    size: int
    decoded_sha256: str      # the ROM the engine maps (header removed, bits in linear order)
    rom_bytes: int
    header: str              # 'none' or 'copier512'
    encoding: str            # 'linear' or 'bit-reversed'
    board: str               # 'base' or 'sf2'
    reset_vector: int
    title: str

    @property
    def game_key(self) -> str:
        return self.sha256

    @property
    def banks(self) -> int:
        return self.rom_bytes // BANK

    def engine_options(self) -> list[str]:
        """The explicit options of the engine's HuCard reset (`pce-headless --hucard-reset`)."""
        return ['--hucard-reset', self.board, '--rom-header', self.header, '--rom-encoding', self.encoding]

    def metadata(self) -> dict:
        return {'name': self.path.name, 'path': str(self.path), 'sha256': self.sha256, 'size': self.size,
                'decoded_sha256': self.decoded_sha256, 'rom_bytes': self.rom_bytes, 'header': self.header,
                'encoding': self.encoding, 'board': self.board, 'reset_vector': self.reset_vector, 'system': 'pce'}


def _vector(rom: bytes) -> int:
    return rom[0x1FFE] | rom[0x1FFF] << 8


def _plausible(vector: int) -> bool:
    return 0xE000 <= vector <= 0xFFFF


def decode(data: bytes) -> tuple[bytes, str, str]:
    """(decoded ROM, header, encoding) of a HuCard file's bytes, by the rules of the module docstring."""
    if len(data) % BANK == HEADER:
        header, rom = 'copier512', data[HEADER:]
    elif len(data) % BANK == 0:
        header, rom = 'none', data
    else:
        raise PcEngineRomError('A HuCard image is whole 8 KiB banks, with at most a 512-byte copier header.')
    if not rom:
        raise PcEngineRomError('The HuCard image holds no ROM bank.')
    if not (len(rom) <= MAX_BASE_BYTES or len(rom) == SF2_BYTES):
        raise PcEngineRomError('A HuCard is 8 KiB to 1 MiB, or 2.5 MiB for the Street Fighter II board.')
    first = rom[:BANK]
    flipped = first.translate(_REVERSED)
    linear, reversed_ = _plausible(_vector(first)), _plausible(_vector(flipped))
    if linear and reversed_:
        # Both orders point into $E000-$FFFF (a high byte of $E7, $EF, $F7 or $FF does it: 4 of the 91 US cards of the
        # maintainer's library). The code the vector points at tells them apart: reversed only when it starts with
        # SEI, NOP or CSH once the bits are turned and does not in the order given.
        reversed_ = (first[_vector(first) - 0xE000] not in _RESET_OPCODES
                     and flipped[_vector(flipped) - 0xE000] in _RESET_OPCODES)
        linear = not reversed_
    if linear:
        return rom, header, 'linear'
    if reversed_:
        return rom.translate(_REVERSED), header, 'bit-reversed'
    raise PcEngineRomError('The reset vector of bank 0 does not point into $E000-$FFFF in either bit order: '
                           'not a HuCard image.')


def board_for(rom_bytes: int) -> str:
    return 'sf2' if rom_bytes == SF2_BYTES else 'base'


def file_bytes(path) -> bytes:
    """The HuCard file's bytes: a loose .pce, or the one .pce of a ZIP (the common reader, systems.archive_rom: a
    ZIP with several cartridges or none is refused there; a SuperGrafx .sgx is not a cartridge it reads)."""
    path = Path(path).resolve(strict=True)
    suffix = path.suffix.casefold()
    if suffix == '.zip':
        from .systems import archive_rom
        suffix, data = archive_rom(path)
    elif suffix == '.pce':
        with path.open('rb') as source:
            data = source.read(MAX_FILE_BYTES + 1)
    if suffix != '.pce':
        raise PcEngineRomError('The PC Engine profile reads .pce HuCard images, loose or alone in a ZIP.')
    if len(data) > MAX_FILE_BYTES:
        raise PcEngineRomError('The HuCard image exceeds 2.5 MiB (plus a 512-byte header).')
    return data


def read_hucard(path) -> HuCard:
    path = Path(path).resolve(strict=True)
    data = file_bytes(path)
    rom, header, encoding = decode(data)
    return HuCard(path, hashlib.sha256(data).hexdigest(), len(data), hashlib.sha256(rom).hexdigest(), len(rom),
                  header, encoding, board_for(len(rom)), _vector(rom), path.stem)
