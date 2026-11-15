"""Instruction lengths of the 68EC020 (MIT): how many bytes an instruction takes, from its words.

On a 68000 the first word decides the length (`m68k_media_knowledge.word_count`). On a 68020 it does not: an indexed addressing mode's
extension word may be a full one, followed by a base displacement and an outer displacement of 0, 1 or 2 words each, so the same first word
starts instructions of several lengths (up to 11 words). The length is the brief one (every extension word brief) plus what the full
extension words add.

The table below holds, for every first word, the brief word count and where the indexed modes' extension words sit (one or two of them, a
MOVE has one per operand). It is Moira's own (the Amiga's reference CPU, pinned with vAmiga): `native/amiga_machine/moira_map.cpp` writes
it for the 68EC020 (`amiga_moira_map <file> 68ec020`), from what Moira's disassembler consumes, and `tests/test_m68020_lengths.py` checks
lengths of the Motorola manual's encodings. One byte per first word: brief count in bits 0-2, first position in bits 3-4, second in bits 5-6.
"""
from __future__ import annotations

import base64
from functools import lru_cache
import zlib

LONGEST_INSTRUCTION = 22          # eleven words: a MOVE between two memory-indirect modes with long displacements

_TABLE = (
    'eNrt3cFygjAUBdAJCRvbHVv+qP//P7VjmHYcsUgQiTl31+oTr0dAmUK77pKQ080k5gw5MZ3v++f+a+en30/zcSYpZ8xJfbiZ6+dz'
    '/bi/y4/Dkrnr2085XexOXdH8suf97PmOP/+VflvM8+fPv0b/y+v36vdP6Tz/99z/8z/6+n+ZX++fxlL/yH+z9afGef7L81//Z6d0'
    '+c+af3T795Fz3v59/BBMjzfNn2YyvW+/coZx+Bo2WD7/uv0f3X9+5pz3n5+Jf/X+tbz+/Pnz58+fP3/+/Ov3j+ZnvZf4pzveS/zH'
    'DZbPv27/uDC3vv/3/Kr3t/3nz58/f/78+fPn39Lxl6Mc/1njHwv9hw2Wz79u/5Lv/4lf9f62//z58+fPnz9//vz38W99/rHjR0dc'
    '//jzb9mv48+ff7h1Hu4er/+S6zesPf9z7bz1v57P39H+v9i/5Pz9tMH8f+dvL71+y1bz1v9tnuede4Qu3zO8ePvF/30+/624fkPU'
    'X3/99ddff/31119//fXXX/9W+u95DYcDJuqvv/7666+//vrrr7/++uuvfwv9g4iIiIiIiIhIeNfzv0qXf/98o73mW77+Bn/+/Pnz'
    '58+fP3/+/Pnz57+Xf2jk+nX8+fPnz58/f/78+fPnz9/1y0VEREREREQk+Pv/4PiP43/8+fPnz58/f/78+fPnz58//xr//zV//vz5'
    '8+fPnz9//vz58+fP3/Ef/vz58+fPnz9//vz58+fv/P/w8vMXQgj666+//vrrr3/VveZ+nhJzhpyY4qB/y/29//nz5992/7hR+py5'
    '21POmJP61P98BEmF6QvzyuMvR3j/8OfPnz9//vz58+fPnz//Nvy/ARhjnng='
)
# Words a full extension word's base displacement (bits 5-4) and outer displacement (bits 2-0, with IS, bit 6) add; None: reserved.
_BASE = {0: None, 1: 0, 2: 1, 3: 2}
_OUTER = {(0, 0): 0, (0, 1): 0, (0, 2): 1, (0, 3): 2, (0, 4): None, (0, 5): 0, (0, 6): 1, (0, 7): 2,
          (1, 0): 0, (1, 1): 0, (1, 2): 1, (1, 3): 2, (1, 4): None, (1, 5): None, (1, 6): None, (1, 7): None}


@lru_cache(maxsize=1)
def table() -> bytes:
    data = zlib.decompress(base64.b64decode(''.join(_TABLE)))
    if len(data) != 65536 or not all(1 <= n & 7 <= 5 for n in data):
        raise ValueError('Invalid MC68EC020 length table.')
    return data


def brief_words(first_word: int) -> int:
    """The words of an instruction whose extension words are all brief (the most a first word alone tells)."""
    return table()[first_word] & 7


def extension_positions(first_word: int) -> tuple[int, ...]:
    """Where an indexed mode's extension word sits, in words after the first one, when every earlier extension word is brief."""
    entry = table()[first_word]
    return tuple(p for p in (entry >> 3 & 3, entry >> 5 & 3) if p)


def full_extra(extension: int) -> int | None:
    """The words a full extension word adds after itself (0 for a brief one); None for a reserved encoding."""
    if not extension & 0x100:
        return 0
    base, outer = _BASE[extension >> 4 & 3], _OUTER[(extension >> 6 & 1, extension & 7)]
    return None if base is None or outer is None else base + outer


def length(raw: bytes) -> int | None:
    """The bytes of the instruction `raw` starts with (an even number), or None when `raw` is shorter than it or uses a reserved
    extension word."""
    if len(raw) < 2:
        return None
    first = raw[0] << 8 | raw[1]
    if 0x0E00 <= first <= 0x0EBF and (len(raw) < 4 or (raw[2] << 8 | raw[3]) & 0x07FF):
        return None          # MOVES whose second word has its reserved bits set: Moira takes it as a one-word illegal instruction
    words, shift = brief_words(first), 0
    for position in extension_positions(first):
        at = 2 * (position + shift)
        if at + 2 > len(raw):
            return None
        extra = full_extra(raw[at] << 8 | raw[at + 1])
        if extra is None:
            return None
        shift += extra
    size = 2 * (words + shift)
    return size if size <= len(raw) else None


def _instruction_set():
    from .m68k_media_knowledge import InstructionSet
    return InstructionSet('68EC020', LONGEST_INSTRUCTION, length)


MC68EC020 = _instruction_set()
