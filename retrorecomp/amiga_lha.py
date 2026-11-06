"""LHA archives of Amiga WHDLoad installs: member list and extraction (MIT, written from the public format).

A WHDLoad install is shipped as one LHA archive that holds a folder with the slave, the game files or `Disk.N` images, the
icons and the documents. This module lists the members (name, Amiga file comment, sizes, method) from their headers and
extracts one member when asked, checking its CRC-16. It reads header levels 0, 1 and 2 and the methods `-lh0-` (stored)
and `-lh5-`, `-lh6-`, `-lh7-` (LZSS with static Huffman blocks, 8, 32 and 64 KiB windows); every other method or header
level is refused with its name. The 4,999 installs measured on 5 November 2026 use `-lh0-`, `-lh5-` and level 1 only.

No member is decompressed by `members()`: payloads are skipped. The game's files stay the player's and are read in place.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct

FORMAT = 1
METHODS = ('-lh0-', '-lh5-', '-lh6-', '-lh7-')
# Dictionary bits of the LZSS window per method; the distance code table has (bits + 1) symbols.
_DICT_BITS = {'-lh5-': 13, '-lh6-': 15, '-lh7-': 16}
_NC, _NT, _TBIT, _CBIT = 510, 19, 5, 9
_MAX_HEADER_CHAIN = 64


class LhaError(ValueError):
    """An archive the reader cannot use, with the reason."""


@dataclass(frozen=True)
class Member:
    name: str            # path inside the archive, '/' separated, without the file comment
    comment: str         # Amiga file comment (text after a NUL in the stored name), '' if none
    method: str
    packed_size: int
    size: int
    crc: int             # CRC-16 (ARC) of the extracted bytes, as stored
    level: int
    data_offset: int     # where the packed payload starts in the archive


def _ext_chain(blob: bytes, pos: int, size: int) -> tuple[dict[int, bytes], int]:
    """Extended headers starting at `pos` with a first size of `size`; returns {type: data} and the bytes used."""
    found: dict[int, bytes] = {}
    used = 0
    for _ in range(_MAX_HEADER_CHAIN):
        if not size:
            return found, used
        if size < 3 or pos + size > len(blob):
            raise LhaError('truncated extended header')
        kind = blob[pos]
        found.setdefault(kind, blob[pos + 1:pos + size - 2])
        used += size
        pos += size
        size = struct.unpack_from('<H', blob, pos - 2)[0]
    raise LhaError('too many extended headers')


def _split_name(raw: bytes, directory: bytes | None) -> tuple[str, str]:
    full = (directory.replace(b'\xff', b'/') if directory else b'') + raw
    name, _, comment = full.partition(b'\x00')
    return name.decode('latin-1').replace('\\', '/'), comment.decode('latin-1')


def members(source: bytes | str | Path) -> list[Member]:
    """The members of an archive, in stored order, from their headers only."""
    blob = source if isinstance(source, bytes) else Path(source).read_bytes()
    out: list[Member] = []
    pos = 0
    while pos < len(blob) and blob[pos] != 0:
        if pos + 22 > len(blob):
            raise LhaError('truncated header at %d' % pos)
        method = blob[pos + 2:pos + 7].decode('latin-1')
        if not (method.startswith('-') and method.endswith('-')):
            raise LhaError('no LHA header at %d' % pos)
        packed, size = struct.unpack_from('<II', blob, pos + 7)
        level = blob[pos + 20]
        if level in (0, 1):
            header = blob[pos] + 2
            nlen = blob[pos + 21]
            raw = blob[pos + 22:pos + 22 + nlen]
            crc = struct.unpack_from('<H', blob, pos + 22 + nlen)[0]
            directory = None
            data = pos + header
            if level == 1:
                first = struct.unpack_from('<H', blob, pos + header - 2)[0]
                found, used = _ext_chain(blob, data, first)
                raw = found.get(1, raw)
                directory = found.get(2)
                data += used
                packed -= used          # level 1 counts its extended headers in the packed size
        elif level == 2:
            header = struct.unpack_from('<H', blob, pos)[0]
            crc = struct.unpack_from('<H', blob, pos + 21)[0]
            found, _ = _ext_chain(blob, pos + 26, struct.unpack_from('<H', blob, pos + 24)[0])
            raw, directory = found.get(1, b''), found.get(2)
            data = pos + header
        else:
            raise LhaError('header level %d is not read' % level)
        if packed < 0 or data + packed > len(blob):
            raise LhaError('member payload outside the archive')
        name, comment = _split_name(raw, directory)
        out.append(Member(name, comment, method, packed, size, crc, level, data))
        pos = data + packed
    return out


def crc16(data: bytes) -> int:
    """CRC-16/ARC (polynomial 0xA001, reflected), the checksum LHA stores for every member."""
    table = _CRC_TABLE
    crc = 0
    for byte in data:
        crc = (crc >> 8) ^ table[(crc ^ byte) & 0xFF]
    return crc


def _crc_table() -> list[int]:
    table = []
    for n in range(256):
        c = n
        for _ in range(8):
            c = (c >> 1) ^ 0xA001 if c & 1 else c >> 1
        table.append(c)
    return table


_CRC_TABLE = _crc_table()


class _Bits:
    """MSB-first bit reader with a peek window of up to 16 bits."""

    __slots__ = ('data', 'pos', 'buf', 'count')

    def __init__(self, data: bytes):
        self.data, self.pos, self.buf, self.count = data, 0, 0, 0

    def _fill(self, need: int) -> None:
        while self.count < need:
            byte = self.data[self.pos] if self.pos < len(self.data) else 0
            self.pos += 1
            self.buf = ((self.buf << 8) | byte) & 0xFFFFFFFF
            self.count += 8

    def peek(self, n: int) -> int:
        self._fill(n)
        return (self.buf >> (self.count - n)) & ((1 << n) - 1)

    def skip(self, n: int) -> None:
        self._fill(n)
        self.count -= n

    def get(self, n: int) -> int:
        if n == 0:
            return 0
        v = self.peek(n)
        self.count -= n
        return v


class _Table:
    """Canonical Huffman decoder (LHA's code order: by length, then by symbol), table-driven up to `bits` bits."""

    def __init__(self, lengths: list[int], bits: int):
        self.single = None
        self.bits = bits
        self.lengths = lengths
        self.fast = [None] * (1 << bits)
        self.slow: dict[tuple[int, int], int] = {}
        code = 0
        for ln in range(1, 17):
            for sym, l in enumerate(lengths):
                if l == ln:
                    if ln <= bits:
                        start = code << (bits - ln)
                        for k in range(start, start + (1 << (bits - ln))):
                            self.fast[k] = sym
                    else:
                        self.slow[(ln, code)] = sym
                    code += 1
            code <<= 1
        if code > (1 << 17):
            raise LhaError('invalid Huffman table')

    @classmethod
    def constant(cls, symbol: int) -> '_Table':
        t = cls.__new__(cls)
        t.single = symbol
        return t

    def decode(self, bits: _Bits) -> int:
        if self.single is not None:
            return self.single
        sym = self.fast[bits.peek(self.bits)]
        if sym is not None:
            bits.skip(self.lengths[sym])
            return sym
        code, ln = bits.get(self.bits), self.bits
        while ln < 16:
            code = (code << 1) | bits.get(1)
            ln += 1
            sym = self.slow.get((ln, code))
            if sym is not None:
                return sym
        raise LhaError('invalid Huffman code')


def _read_pt(bits: _Bits, count: int, nbit: int, special: int) -> _Table:
    n = bits.get(nbit)
    if n == 0:
        return _Table.constant(bits.get(nbit))
    if n > count:
        raise LhaError('invalid code length table')
    lengths, i = [0] * count, 0
    while i < n:
        c = bits.peek(3)
        if c == 7:
            bits.skip(3)
            while bits.get(1):
                c += 1
                if c > 16:
                    raise LhaError('invalid code length')
        else:
            bits.skip(3)
        lengths[i] = c
        i += 1
        if i == special:
            for _ in range(bits.get(2)):
                if i < count:
                    lengths[i] = 0
                i += 1
    return _Table(lengths, 8)


def _read_c(bits: _Bits, pt: _Table) -> _Table:
    n = bits.get(_CBIT)
    if n == 0:
        return _Table.constant(bits.get(_CBIT))
    if n > _NC:
        raise LhaError('invalid literal table')
    lengths, i = [0] * _NC, 0
    while i < n:
        c = pt.decode(bits)
        if c <= 2:
            i += 1 if c == 0 else (bits.get(4) + 3 if c == 1 else bits.get(_CBIT) + 20)
        else:
            lengths[i] = c - 2
            i += 1
    return _Table(lengths[:_NC], 12)


def _lzh(data: bytes, size: int, dict_bits: int) -> bytes:
    bits = _Bits(data)
    out = bytearray()
    np_, pbit = dict_bits + 1, (4 if dict_bits == 13 else 5)
    while len(out) < size:
        block = bits.get(16)
        if block == 0:
            raise LhaError('empty block')
        pt = _read_pt(bits, _NT, _TBIT, 3)
        ct = _read_c(bits, pt)
        dt = _read_pt(bits, np_, pbit, -1)
        for _ in range(block):
            if len(out) >= size:
                break
            c = ct.decode(bits)
            if c < 256:
                out.append(c)
                continue
            length = c - 253
            p = dt.decode(bits)
            if p:
                p = (1 << (p - 1)) + bits.get(p - 1)
            src = len(out) - p - 1
            if src < 0:
                raise LhaError('match before the start of the data')
            if p + 1 >= length:
                out += out[src:src + length]
            else:
                for k in range(length):
                    out.append(out[src + k])
        if bits.pos > len(data) + 4:
            raise LhaError('packed data ends early')
    return bytes(out[:size])


def extract(source: bytes | str | Path, member: Member) -> bytes:
    """The bytes of one member, checked against its stored CRC-16."""
    blob = source if isinstance(source, bytes) else Path(source).read_bytes()
    payload = blob[member.data_offset:member.data_offset + member.packed_size]
    if member.method == '-lh0-':
        data = payload[:member.size]
    elif member.method in _DICT_BITS:
        data = _lzh(payload, member.size, _DICT_BITS[member.method])
    else:
        raise LhaError('method %s is not read' % member.method)
    if len(data) != member.size or crc16(data) != member.crc:
        raise LhaError('CRC mismatch in ' + member.name)
    return data
