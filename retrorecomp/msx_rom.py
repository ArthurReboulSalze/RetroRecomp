"""MSX cartridge images: which mapper, and where a plain image sits; reading a cartridge. MIT, Retro-Recomp.

An MSX cartridge has no header that names its mapper. This guess is our own, written from the mappers' documented
register addresses:

- **Up to 32 KB: plain; 48 and 64 KB: plain unless at least two writes go to mapper registers (below).** A plain image
  sits where its "AB" header's routine pointers point: every non-zero pointer (INIT,
  STATEMENT, DEVICE, TEXT) of a header at offset 0 or 4000h votes for the page it falls in, and the image starts at
  4000h if that page has the most votes (ties go to 4000h), else at 0000h, else at 8000h; with no vote, at 4000h. A
  plain image is mirrored over the slot. (Checked against openMSX run as a separate program, which places them the same way.)
- **Larger: a mapper**, by the bank-register writes the program makes. Every `LD (nn),A` (32h, nn), and every
  `LD HL,nn` (21h, nn) followed at once by a write through HL (`LD (HL),r` 70h-75h, 77h, or `LD (HL),n` 36h), whose nn
  is a register address of a mapper (as their documentation gives them) votes for each mapper that has a register
  there: Konami 6000h, 8000h, A000h; Konami SCC 5000h, 7000h, 9000h, B000h; ASCII 8 KB 6000h, 6800h, 7000h, 7800h;
  ASCII 16 KB 6000h, 7000h, 77FFh. The most votes win. Ties go to ASCII 16, then ASCII 8, then Konami SCC, then Konami:
  the shared addresses are 6000h and 7000h, and a program that writes only those (often 7000h alone, to switch page 2)
  is an ASCII one; a Konami program also writes 8000h / A000h, a Konami SCC one 9000h / B000h. 8000h-BFFFh can also be
  plain RAM writes, so the Konami SCC counts only when the program addresses the SCC (`refers_to_scc`). No vote at all: no guess (`mapper` None): the conversion must be told,
  or try each. `candidates` lists every mapper with a vote, best first, for the conversion to try in that order.

Measured on the player's library (12 Nov 2026, private cross-check against openMSX's database for the titles matched
exactly by name): see the MSX study notes. The guess is a first layer only.

The guess reads the player's image at conversion time and keeps nothing of it but the result. It is a guess: the
conversion confirms it when the game boots and matches the reference run; a known image can be named by its hash.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

MAPPERS = ('plain', 'konami', 'konami-scc', 'ascii8', 'ascii16')
REGISTERS = {
    'konami-scc': (0x5000, 0x7000, 0x9000, 0xB000),
    'konami': (0x6000, 0x8000, 0xA000),
    'ascii16': (0x6000, 0x7000, 0x77FF),
    'ascii8': (0x6000, 0x6800, 0x7000, 0x7800),
}
TIE_ORDER = ('ascii16', 'ascii8', 'konami-scc', 'konami')
PLAIN_LIMIT = 0x8000          # up to this size an image is plain whatever it writes
MAYBE_PLAIN = 0x10000         # up to this size it is plain unless it writes to a mapper register


@dataclass(frozen=True)
class Guess:
    mapper: str | None
    base: int = 0x4000
    mirrored: bool = True
    votes: tuple = ()
    reason: str = ''
    candidates: tuple = ()

    def arguments(self) -> list[str]:
        """The reference runner's options for this guess."""
        if self.mapper is None:
            raise ValueError('no mapper guessed: ' + self.reason)
        if self.mapper == 'plain':
            return ['--mapper', 'plain', '--cart-base', f'{self.base:04X}'] + (['--mirrored'] if self.mirrored else [])
        return ['--mapper', self.mapper]


def _header_votes(image: bytes, offset: int, pages: list[int]) -> None:
    if image[offset:offset + 2] != b'AB':
        return
    for i in range(4):
        pointer = int.from_bytes(image[offset + 2 + 2 * i:offset + 4 + 2 * i], 'little')
        if pointer:
            page = (pointer >> 14) - (offset >> 14)
            if 0 <= page <= 2:
                pages[page] += 1


def plain_base(image: bytes) -> tuple[int, str]:
    pages = [0, 0, 0]
    if len(image) >= 0x10:
        _header_votes(image, 0, pages)
    if len(image) >= 0x4010:
        _header_votes(image, 0x4000, pages)
    if pages[1] and pages[1] >= pages[0] and pages[1] >= pages[2]:
        return 0x4000, f'header pointers by page {pages}'
    if pages[0] and pages[0] >= pages[2]:
        return 0x0000, f'header pointers by page {pages}'
    if pages[2]:
        return 0x8000, f'header pointers by page {pages}'
    return 0x4000, 'no header pointer: 4000h'


def register_writes(image: bytes) -> Counter:
    """Counts of `LD (nn),A` targets that are a register address of some mapper."""
    wanted = {address for addresses in REGISTERS.values() for address in addresses}
    counts: Counter = Counter()
    position = image.find(0x32)
    while 0 <= position < len(image) - 2:
        target = image[position + 1] | image[position + 2] << 8
        if target in wanted:
            counts[target] += 1
        position = image.find(0x32, position + 1)
    position = image.find(0x21)
    while 0 <= position < len(image) - 3:
        target = image[position + 1] | image[position + 2] << 8
        if target in wanted and (image[position + 3] in (0x36, 0x77) or 0x70 <= image[position + 3] <= 0x75):
            counts[target] += 1
        position = image.find(0x21, position + 1)
    return counts


SCC_POINTERS = (0x9800, 0x9820, 0x9840, 0x9860, 0x9880, 0x988A, 0x988F)


def refers_to_scc(image: bytes) -> bool:
    """The program addresses the SCC: LD (nn),A or LD A,(nn) (32h, 3Ah) with nn in 9800h-989Fh (waves, periods,
    volumes, enable), or LD HL/DE/BC,nn (21h, 11h, 01h) with nn the start of a wave or of the frequency block."""
    for opcode in (0x32, 0x3A):
        position = image.find(opcode)
        while 0 <= position < len(image) - 2:
            if image[position + 2] == 0x98 and image[position + 1] < 0xA0:
                return True
            position = image.find(opcode, position + 1)
    for opcode in (0x21, 0x11, 0x01):
        position = image.find(opcode)
        while 0 <= position < len(image) - 2:
            if (image[position + 1] | image[position + 2] << 8) in SCC_POINTERS:
                return True
            position = image.find(opcode, position + 1)
    return False


def guess(image: bytes) -> Guess:
    size = len(image)
    if size == 0 or size % 0x2000:
        rounded = (size + 0x1FFF) & ~0x1FFF
    else:
        rounded = size
    if rounded <= PLAIN_LIMIT:
        base, why = plain_base(image)
        return Guess('plain', base, True, (), f'{size // 1024} KB: plain, {why}')
    counts = register_writes(image)
    votes = {mapper: sum(counts[address] for address in addresses) for mapper, addresses in REGISTERS.items()}
    scc = refers_to_scc(image)
    if not scc:
        votes['konami-scc'] = 0
    best = max(votes.values())
    table = tuple((mapper, votes[mapper]) for mapper in TIE_ORDER)
    ranked = tuple(sorted((m for m in TIE_ORDER if votes[m]), key=lambda m: (-votes[m], TIE_ORDER.index(m))))
    writes = {f'{a:04X}h': n for a, n in sorted(counts.items())}
    if best < 2 and rounded <= MAYBE_PLAIN:
        base, why = plain_base(image)
        return Guess('plain', base, True, table, f'{size // 1024} KB, {best} register write(s): plain, {why}', ranked)
    if best == 0:
        return Guess(None, votes=table, reason=f'{size // 1024} KB and no write to a mapper register')
    return Guess(ranked[0], votes=table, candidates=ranked,
                 reason=f'{size // 1024} KB, register writes {writes}, SCC referred to: {"yes" if scc else "no"}')


# ---- recognising and reading a cartridge ----

MAX_CARTRIDGE = 0x200000      # 2 MiB: the largest MegaROM the first scope reads


def _pointers_fit(image: bytes, offset: int) -> bool:
    """A credible "AB" header at `offset`: at least one routine pointer (INIT, STATEMENT, DEVICE, TEXT), every one either
    zero or inside the cartridge window its page allows (0000h-BFFFh), and the six reserved bytes after them zero or FFh."""
    if image[offset:offset + 2] != b'AB':
        return False
    pointers = [int.from_bytes(image[offset + 2 + 2 * i:offset + 4 + 2 * i], 'little') for i in range(4)]
    if not any(pointers) or any(p >= 0xC000 for p in pointers):
        return False
    reserved = image[offset + 10:offset + 16]
    return reserved in (bytes(6), b'\xFF' * 6)


def system_rom(image: bytes) -> str | None:
    """What kind of MSX system ROM an "AB"-headed image is, or None for a cartridge to play. A player's BIOS folder holds
    them beside the main ROMs, and their header is a cartridge's:
    - the MSX-MUSIC and FM-PAC ROMs: their signature at +18h ("APRLOPLL", "PAC2OPLL", the MSX-MUSIC standard's);
    - the disk, IDE and DOS2 kernels: a STATEMENT routine (their CALL commands) that is not a jump opcode, and a table of
      5 to 8 jumps from +10h (DSKIO, DSKCHG, GETDPB, CHOICE, DSKFMT...);
    - a pure BASIC extension (Kanji BASIC, MSX-MUSIC BASIC): no INIT, a STATEMENT routine and nothing at +10h-+1Fh.
    Measured on 12 November 2026 on a player's BIOS folder (24 of its 37 "AB" images) and two MSX game libraries (0 of 522
    cartridges caught: games whose header bytes are code have C3h, JP, where STATEMENT sits, or longer jump tables).
    Firmware, word processors, RS-232C and other language extensions stay listed: no header pattern tells them apart."""
    for offset in (0, 0x4000):
        if offset + 0x20 > len(image) or image[offset:offset + 2] != b'AB':
            continue
        init = int.from_bytes(image[offset + 2:offset + 4], 'little')
        statement = int.from_bytes(image[offset + 4:offset + 6], 'little')
        if image[offset + 0x18:offset + 0x20] in (b'APRLOPLL', b'PAC2OPLL'):
            return 'MSX-MUSIC or FM-PAC ROM'
        jumps = 0
        while jumps < 9 and image[offset + 0x10 + 3 * jumps] == 0xC3:
            jumps += 1
        if statement and (statement & 0xFF) != 0xC3 and 5 <= jumps <= 8:
            return 'disk or DOS kernel ROM'
        if statement and not init and not any(image[offset + 0x10:offset + 0x20]):
            return 'BASIC extension ROM'
    return None


def looks_like_cartridge(image: bytes) -> bool:
    """The bytes of a .rom are an MSX cartridge: 8 KiB to 2 MiB, whole kilobytes, and an "AB" header at the start (or at
    4000h of an image whose first page belongs to the game), and not a system ROM (system_rom). Asked after the other
    machines' sniffers, which recognise their own headers first."""
    size = len(image)
    if not 0x2000 <= size <= MAX_CARTRIDGE or size % 0x400:
        return False
    if not (_pointers_fit(image, 0) or (size >= 0x8000 and _pointers_fit(image, 0x4000))):
        return False
    return system_rom(image) is None


def has_header(image: bytes) -> bool:
    """What the BIOS itself reads of a cartridge already known to be the MSX's (a .mx1/.mx2, a file chosen as MSX or found in
    an MSX folder): 8 KiB to 2 MiB, whole kilobytes, "AB" at the start (or at 4000h) and an INIT or TEXT pointer below
    C000h. Some games put text in the other header fields (Hydlide 3 spells its name over them), which the strict sniff of
    looks_like_cartridge refuses."""
    size = len(image)
    if not 0x2000 <= size <= MAX_CARTRIDGE or size % 0x400:
        return False
    for offset in (0, 0x4000):
        if offset + 16 > size or image[offset:offset + 2] != b'AB':
            continue
        init = int.from_bytes(image[offset + 2:offset + 4], 'little')
        text = int.from_bytes(image[offset + 8:offset + 10], 'little')
        if 0 < init < 0xC000 or (not init and 0 < text < 0xC000):
            return True
    return False


@dataclass(frozen=True)
class Cartridge:
    """A cartridge as the converter reads it: its bytes (from a file or from a ZIP member), their SHA-256 and the guess."""
    path: object
    data: bytes
    sha256: str
    guess: Guess
    member: str = ''        # the cartridge's name inside a ZIP, '' for a file

    @property
    def size(self) -> int:
        return len(self.data)


def read_cartridge(path) -> Cartridge:
    """The cartridge at `path` (.rom, .mx1, .mx2, or a ZIP holding one), refused with a sentence when it is none."""
    import hashlib
    import zipfile
    from pathlib import Path
    path = Path(path)
    if path.suffix.lower() == '.zip':
        import zlib
        # A ZIP that cannot be read whole is refused with a sentence, as systems.archive_rom refuses it: a damaged one
        # (BadZipFile: a bad CRC too), an encrypted member (RuntimeError), a compression Python does not read
        # (NotImplementedError, a RuntimeError), a broken deflate stream (zlib.error) or a cut file (EOFError).
        try:
            with zipfile.ZipFile(path) as bundle:
                names = [n for n in bundle.namelist() if n.lower().endswith(('.rom', '.mx1', '.mx2'))]
                if len(names) != 1:
                    raise ValueError(f'{path.name}: the ZIP must hold exactly one MSX cartridge (.rom, .mx1 or .mx2).')
                if bundle.getinfo(names[0]).file_size > MAX_CARTRIDGE:
                    raise ValueError(f'{path.name}: larger than 2 MiB, the largest MSX cartridge read.')
                data = bundle.read(names[0])
                member = names[0]
        except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError) as error:
            raise ValueError(f'{path.name}: not a readable ZIP ({error}).') from None
    else:
        if path.stat().st_size > MAX_CARTRIDGE:
            raise ValueError(f'{path.name}: larger than 2 MiB, the largest MSX cartridge read.')
        data = path.read_bytes()
        member = ''
    if not has_header(data):
        raise ValueError(f'{path.name}: no MSX cartridge header ("AB" and its routine pointers).')
    return Cartridge(path, data, hashlib.sha256(data).hexdigest(), guess(data), member)
