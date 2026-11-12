"""MSX cartridge images: which mapper, and where a plain image sits. MIT, Retro-Recomp.

An MSX cartridge has no header that names its mapper. This guess is our own, written from the mappers' documented
register addresses (stage 4 of the MSX plan; it moves into the converter with the MSX profile):

- **Up to 32 KB: plain; 48 and 64 KB: plain unless at least two writes go to mapper registers (below).** A plain image
  sits where its "AB" header's routine pointers point: every non-zero pointer (INIT,
  STATEMENT, DEVICE, TEXT) of a header at offset 0 or 4000h votes for the page it falls in, and the image starts at
  4000h if that page has the most votes (ties go to 4000h), else at 0000h, else at 8000h; with no vote, at 4000h. A
  plain image is mirrored over the slot. (openMSX places plain images the same way; nothing was copied from it.)
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
