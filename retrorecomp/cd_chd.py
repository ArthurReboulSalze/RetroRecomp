"""CHD disc images, read in place by pure Python (Retro-Recomp's own code, MIT): enough to identify a disc, shared by the PC Engine CD
and the PlayStation (moved from `pcecd_chd.py` for the PlayStation's CHD discs; the PC Engine CD reads exactly as before).

The converter has to say what a `.chd` holds before it converts anything, and a scan must not need a compiler or a DLL. This reader
decodes what the identification needs, the data track's first sectors, from the published layout of the format (MAME's `chd.h`
and `chdcodec`, which libchdr also follows): the version 4 and version 5 headers, the metadata chain (`CHT2` and `CHTR` track
records), the version 4 map, the version 5 map (uncompressed, or the Huffman-coded one), and the hunk codecs a CD image uses
(`cdzl`, `cdlz`, `zlib`, and raw hunks). A PC Engine CD game reads its disc through libchdr, linked into the executable
(docs/PC_ENGINE_CD.md); the PlayStation's converter decodes a whole disc through libchdr too (`chd_native`, for the audio codec and
Zstandard). Nothing here is in a game.

`layout()` is the one numbering of a CHD's sectors both machines use: LBA 0 at index 01 of track 1, a pregap the image stores
(`PGTYPE:V...`) part of its track (its INDEX 00 sectors), a pregap it does not store virtual, every track padded to four frames.

Every decoded hunk is checked against the CRC the map holds (CRC-16 of CCITT for version 5, CRC-32 for version 4), so a wrong
decode is an error and never a wrong answer. A hunk of a codec this reader does not implement (`cdfl`, the audio codec) raises
`ChdCodecError`: the identification reads data tracks only, and says so when a track it needs is not readable.

No byte of a disc is kept or written. A CHD with a parent, a legacy (`CHCD`) or GD-ROM metadata is refused.
"""
from __future__ import annotations

from binascii import crc_hqx
from dataclasses import dataclass
import lzma
import re
import struct
from pathlib import Path
import zlib

FRAME = 2448                      # a CD frame as a CHD stores it: 2,352 bytes of sector and 96 of sub-channel
SECTOR = 2352
SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
MAX_HUNKS = 1 << 22
MAX_METADATA = 1 << 20

# Compression types of a version 5 map entry.
_TYPE_0, _TYPE_1, _TYPE_2, _TYPE_3, _NONE, _SELF, _PARENT, _RLE_SMALL, _RLE_LARGE, _SELF_0, _SELF_1, _PARENT_SELF, _PARENT_0, _PARENT_1 = range(14)


class ChdError(ValueError):
    """A file that is not a CHD this reader understands, with the reason."""


class ChdCodecError(ChdError):
    """A hunk whose codec this reader does not implement (the audio codec of a track the identification never reads)."""


@dataclass(frozen=True)
class ChdTrack:
    number: int
    type: str            # 'MODE1', 'MODE1_RAW', 'MODE2_RAW', 'AUDIO'
    frames: int
    pregap: int
    postgap: int
    pregap_stored: bool  # the pregap's frames are in the image (PGTYPE V...)
    subtype: str

    @property
    def data(self) -> bool:
        return self.type != 'AUDIO'


def _tag(value: bytes) -> str:
    return value.decode('ascii', 'replace')


# ---- the parity the encoder left out of a raw sector ------------------------------------------------------------------------
# A Mode 1 raw sector holds, after its 2,048 data bytes, an EDC and the P and Q parity of the product code of ECMA-130 (a
# Reed-Solomon code over GF(2^8), polynomial 0x11D). The CD codecs drop them when they are regenerable (a flag per frame) and
# the decoder restores them, so a hunk's CRC covers them: they are rebuilt here to check every hunk.
_ECC_P_OFFSET, _ECC_P_BYTES, _ECC_P_COMPONENTS = 0x81C, 86, 24
_ECC_Q_OFFSET, _ECC_Q_BYTES, _ECC_Q_COMPONENTS = _ECC_P_OFFSET + 2 * _ECC_P_BYTES, 52, 43
_ecc_tables = None


def _gf_tables():
    global _ecc_tables
    if _ecc_tables is None:
        xtime = [((i << 1) ^ (0x1D if i & 0x80 else 0)) & 0xFF for i in range(256)]

        def multiply(a: int, b: int) -> int:
            result = 0
            while b:
                if b & 1:
                    result ^= a
                a = xtime[a]
                b >>= 1
            return result

        high = [multiply(i, 244) for i in range(256)]
        p_rows = [[row + _ECC_P_BYTES * c for c in range(_ECC_P_COMPONENTS)] for row in range(_ECC_P_BYTES)]
        q_rows = [[(_ECC_P_BYTES * (row >> 1) + (row & 1) + 88 * c) % 2236 for c in range(_ECC_Q_COMPONENTS)] for row in range(_ECC_Q_BYTES)]
        _ecc_tables = (xtime, high, p_rows, q_rows)
    return _ecc_tables


def _ecc_generate(sector: bytearray) -> None:
    """Write the P and Q parity of a Mode 1 (or Mode 2 form 1) raw sector, as libchdr's ecc_generate does."""
    xtime, high, p_rows, q_rows = _gf_tables()
    data = memoryview(sector)[12:]
    mode2 = sector[15] == 2
    for rows, parity, count in ((p_rows, _ECC_P_OFFSET, _ECC_P_BYTES), (q_rows, _ECC_Q_OFFSET, _ECC_Q_BYTES)):
        for row, offsets in enumerate(rows):
            v1 = v2 = 0
            for offset in offsets:
                byte = 0 if mode2 and offset < 4 else data[offset]
                v1 = xtime[v1 ^ byte]
                v2 ^= byte
            first = high[xtime[v1] ^ v2]
            sector[parity + row] = first
            sector[parity + count + row] = v2 ^ first


class _Bits:
    """The most significant bit first reader of the Huffman-coded map."""

    def __init__(self, data: bytes):
        self.data, self.pos, self.buffer, self.count = data, 0, 0, 0

    def read(self, width: int) -> int:
        if width == 0:
            return 0
        while self.count < width:
            byte = self.data[self.pos] if self.pos < len(self.data) else 0
            self.pos += 1
            self.buffer = (self.buffer << 8) | byte
            self.count += 8
        self.count -= width
        value = (self.buffer >> self.count) & ((1 << width) - 1)
        self.buffer &= (1 << self.count) - 1
        return value

    def peek(self, width: int) -> int:
        while self.count < width:
            byte = self.data[self.pos] if self.pos < len(self.data) else 0
            self.pos += 1
            self.buffer = (self.buffer << 8) | byte
            self.count += 8
        return (self.buffer >> (self.count - width)) & ((1 << width) - 1)

    def overflow(self) -> bool:
        return self.pos - self.count // 8 > len(self.data)


class _Huffman:
    """The map's decoder of 16 codes, at most 8 bits, with the tree stored as run-length-coded lengths."""

    def __init__(self, numcodes: int, maxbits: int, bits: _Bits):
        self.maxbits = maxbits
        numbits = 5 if maxbits >= 16 else 4 if maxbits >= 8 else 3
        lengths = []
        while len(lengths) < numcodes:
            nodebits = bits.read(numbits)
            if nodebits != 1:
                lengths.append(nodebits)
                continue
            nodebits = bits.read(numbits)
            if nodebits == 1:
                lengths.append(nodebits)
                continue
            repeat = bits.read(numbits) + 3
            if repeat + len(lengths) > numcodes:
                raise ChdError('invalid Huffman tree in the map')
            lengths += [nodebits] * repeat
        if len(lengths) != numcodes or any(n > maxbits for n in lengths):
            raise ChdError('invalid Huffman tree in the map')
        histogram = [0] * 33
        for n in lengths:
            histogram[n] += 1
        start = 0
        for codelen in range(32, 0, -1):
            nextstart = (start + histogram[codelen]) >> 1
            if codelen != 1 and nextstart * 2 != start + histogram[codelen]:
                raise ChdError('inconsistent Huffman tree in the map')
            histogram[codelen] = start
            start = nextstart
        self.table = [0] * (1 << maxbits)
        for symbol, n in enumerate(lengths):
            if not n:
                continue
            code = histogram[n]
            histogram[n] += 1
            low = code << (maxbits - n)
            for slot in range(low, low + (1 << (maxbits - n))):
                self.table[slot] = (symbol << 5) | n

    def decode(self, bits: _Bits) -> int:
        entry = self.table[bits.peek(self.maxbits)]
        bits.read(entry & 0x1F)
        return entry >> 5


@dataclass(frozen=True)
class TrackPlace:
    """Where a CHD track lies: its numbering on the disc and its frames in the image."""
    track: ChdTrack
    start: int           # LBA of index 01
    length: int          # sectors from index 01
    pregap: int          # sectors before index 01 that belong to the track (stored or virtual)
    stored: int          # of those, the sectors the image holds (before index 01, from `frame`)
    frame: int           # the image's first frame of the track (its first stored pregap frame, or index 01)


def layout(tracks: list[ChdTrack]) -> list[TrackPlace]:
    """The numbering of the tracks' sectors (the PC Engine CD engine's own provider and a CUE/BIN set of the same disc agree on it)."""
    places, lba, frame = [], 0, 0
    for track in tracks:
        stored = track.pregap if track.pregap_stored else 0
        places.append(TrackPlace(track, lba + track.pregap, track.frames - stored, track.pregap, stored, frame))
        lba += track.frames + track.postgap + (0 if track.pregap_stored else track.pregap)
        frame += -(-track.frames // 4) * 4
    return places


class Chd:
    """One CHD file opened for reading. `read(offset, length)` addresses its logical bytes; `close()` releases the file."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._file = open(self.path, 'rb')
        try:
            self._parse()
        except Exception:
            self._file.close()
            raise
        self._cache: dict[int, bytes] = {}

    def close(self) -> None:
        self._file.close()
        self._cache = {}

    # ---- header, map, metadata ----------------------------------------------------------------------------------------

    def _at(self, offset: int, size: int) -> bytes:
        self._file.seek(offset)
        data = self._file.read(size)
        if len(data) != size:
            raise ChdError(f'{self.path.name}: the file ends inside its tables')
        return data

    def _parse(self) -> None:
        head = self._at(0, 16)
        if head[:8] != b'MComprHD':
            raise ChdError(f'{self.path.name}: not a CHD file')
        length, self.version = struct.unpack('>II', head[8:16])
        self.file_size = self.path.stat().st_size
        if self.version == 5:
            if length != 124:
                raise ChdError(f'{self.path.name}: bad CHD version 5 header')
            raw = self._at(0, 124)
            self.compressors = tuple(_tag(raw[16 + 4 * i:20 + 4 * i]) if raw[16 + 4 * i:20 + 4 * i] != b'\0\0\0\0' else '' for i in range(4))
            self.logical_bytes, self.map_offset, self.meta_offset = struct.unpack('>QQQ', raw[32:56])
            self.hunk_bytes, self.unit_bytes = struct.unpack('>II', raw[56:64])
            self.raw_sha1 = raw[64:84].hex()
            if any(raw[104:124]):
                raise ChdError(f'{self.path.name}: a CHD with a parent is not supported')
            if not self.hunk_bytes or not self.unit_bytes or self.hunk_bytes % self.unit_bytes:
                raise ChdError(f'{self.path.name}: bad CHD hunk geometry')
            self.total_hunks = -(-self.logical_bytes // self.hunk_bytes)
        elif self.version == 4:
            if length != 108:
                raise ChdError(f'{self.path.name}: bad CHD version 4 header')
            raw = self._at(0, 108)
            flags, compression, self.total_hunks = struct.unpack('>III', raw[16:28])
            self.logical_bytes, self.meta_offset = struct.unpack('>QQ', raw[28:44])
            self.hunk_bytes, = struct.unpack('>I', raw[44:48])
            self.unit_bytes = FRAME
            self.raw_sha1 = raw[88:108].hex()
            if flags & 2 or any(raw[68:88]):
                raise ChdError(f'{self.path.name}: a CHD with a parent is not supported')
            if compression not in (0, 1, 2):
                raise ChdError(f'{self.path.name}: CHD compression {compression} is not supported')
            self.compressors = ({0: '', 1: 'zlib', 2: 'zlib'}[compression],)
            self.header_bytes = 108
        else:
            raise ChdError(f'{self.path.name}: CHD version {self.version} is not supported')
        if not 0 < self.total_hunks <= MAX_HUNKS or self.hunk_bytes > 1 << 20 or self.hunk_bytes % FRAME:
            raise ChdError(f'{self.path.name}: bad CHD size')
        if self.version == 5:
            self._read_map_v5()
        else:
            self._read_map_v4()
        self.tracks = self._read_tracks()

    def _read_map_v4(self) -> None:
        raw = self._at(self.header_bytes, 16 * self.total_hunks)
        self.map = []
        for n in range(self.total_hunks):
            entry = raw[16 * n:16 * n + 16]
            offset, crc = struct.unpack('>QI', entry[:12])
            length = struct.unpack('>H', entry[12:14])[0] | (entry[14] << 16)
            self.map.append((entry[15] & 0x0F, offset, length, crc, bool(entry[15] & 0x10)))

    def _read_map_v5(self) -> None:
        if not self.compressors[0]:
            raw = self._at(self.map_offset, 4 * self.total_hunks)
            self.map = [(_NONE, struct.unpack('>I', raw[4 * n:4 * n + 4])[0] * self.hunk_bytes, self.hunk_bytes, None) for n in range(self.total_hunks)]
            return
        head = self._at(self.map_offset, 16)
        mapbytes, = struct.unpack('>I', head[:4])
        first = int.from_bytes(head[4:10], 'big')
        mapcrc, = struct.unpack('>H', head[10:12])
        lengthbits, selfbits, parentbits = head[12], head[13], head[14]
        if max(lengthbits, selfbits, parentbits) > 32 or self.map_offset + 16 + mapbytes > self.file_size:
            raise ChdError(f'{self.path.name}: bad CHD map')
        bits = _Bits(self._at(self.map_offset + 16, mapbytes))
        huff = _Huffman(16, 8, bits)
        kinds, repeat, last = [], 0, 0
        for _ in range(self.total_hunks):
            if repeat > 0:
                kinds.append(last)
                repeat -= 1
                continue
            value = huff.decode(bits)
            if value == _RLE_SMALL:
                kinds.append(last)
                repeat = 2 + huff.decode(bits)
            elif value == _RLE_LARGE:
                kinds.append(last)
                repeat = 2 + 16 + (huff.decode(bits) << 4)
                repeat += huff.decode(bits)
            else:
                kinds.append(value)
                last = value
        self.map = []
        offset_cursor, last_self, last_parent = first, 0, 0
        raw_map = bytearray()
        for number, kind in enumerate(kinds):
            offset, length, crc = offset_cursor, 0, 0
            if kind in (_TYPE_0, _TYPE_1, _TYPE_2, _TYPE_3):
                length = bits.read(lengthbits)
                offset_cursor += length
                crc = bits.read(16)
            elif kind == _NONE:
                length = self.hunk_bytes
                offset_cursor += length
                crc = bits.read(16)
            elif kind == _SELF:
                last_self = offset = bits.read(selfbits)
            elif kind == _PARENT:
                last_parent = offset = bits.read(parentbits)
            elif kind in (_SELF_0, _SELF_1):
                if kind == _SELF_1:
                    last_self += 1
                kind, offset = _SELF, last_self
            elif kind == _PARENT_SELF:
                kind = _PARENT
                last_parent = offset = number * self.hunk_bytes // self.unit_bytes
            elif kind in (_PARENT_0, _PARENT_1):
                if kind == _PARENT_1:
                    last_parent += self.hunk_bytes // self.unit_bytes
                kind, offset = _PARENT, last_parent
            else:
                raise ChdError(f'{self.path.name}: bad CHD map entry')
            raw_map += bytes([kind]) + length.to_bytes(3, 'big') + offset.to_bytes(6, 'big') + crc.to_bytes(2, 'big')
            self.map.append((kind, offset, length, crc))
        if crc_hqx(bytes(raw_map), 0xFFFF) != mapcrc:
            raise ChdError(f'{self.path.name}: the CHD map fails its checksum')

    def _read_tracks(self) -> list[ChdTrack]:
        tracks, seen, offset, total = [], set(), self.meta_offset, 0
        while offset:
            if offset in seen or offset + 16 > self.file_size or len(seen) >= 1024:
                raise ChdError(f'{self.path.name}: bad CHD metadata chain')
            seen.add(offset)
            record = self._at(offset, 16)
            tag, flags_length, following = struct.unpack('>4sIQ', record)
            size = flags_length & 0xFFFFFF
            total += size
            if size > 65536 or total > MAX_METADATA:
                raise ChdError(f'{self.path.name}: CHD metadata exceeds its bounds')
            if tag in (b'CHT2', b'CHTR'):
                text = self._at(offset + 16, size).split(b'\0', 1)[0].decode('ascii', 'replace')
                fields = dict(re.findall(r'(\w+):(\S+)', text))
                try:
                    number, frames = int(fields['TRACK']), int(fields['FRAMES'])
                    kind = fields['TYPE']
                    pregap, postgap = int(fields.get('PREGAP', 0)), int(fields.get('POSTGAP', 0))
                except (KeyError, ValueError):
                    raise ChdError(f'{self.path.name}: bad CHD track metadata') from None
                if number != len(tracks) + 1 or kind not in ('MODE1', 'MODE1_RAW', 'MODE2_RAW', 'AUDIO'):
                    raise ChdError(f'{self.path.name}: a CHD track layout this reader does not know ({kind})')
                stored = fields.get('PGTYPE', '').startswith('V') and pregap > 0
                if stored and pregap >= frames:
                    raise ChdError(f'{self.path.name}: bad CHD track pregap')
                tracks.append(ChdTrack(number, kind, frames, pregap, postgap, stored, fields.get('SUBTYPE', 'NONE')))
            elif tag in (b'CHCD', b'CHGT', b'CHGD'):
                raise ChdError(f'{self.path.name}: legacy or GD-ROM CHD metadata is not supported')
            offset = following
        if not tracks:
            raise ChdError(f'{self.path.name}: a CHD without a CD track table')
        if sum(-(-t.frames // 4) * 4 for t in tracks) * FRAME != self.logical_bytes:
            raise ChdError(f'{self.path.name}: the track table disagrees with the CHD size')
        return tracks

    # ---- hunks --------------------------------------------------------------------------------------------------------

    def _decode_cd(self, packed: bytes, base) -> bytes:
        frames = self.hunk_bytes // FRAME
        ecc = (frames + 7) // 8
        length_bytes = 2 if self.hunk_bytes < 65536 else 3
        if len(packed) < ecc + length_bytes:
            raise ChdError(f'{self.path.name}: a truncated CD hunk')
        base_length = int.from_bytes(packed[ecc:ecc + length_bytes], 'big')
        header = ecc + length_bytes
        if len(packed) < header + base_length:
            raise ChdError(f'{self.path.name}: a truncated CD hunk')
        sectors = base(packed[header:header + base_length], frames * SECTOR)
        out = bytearray(self.hunk_bytes)
        for number in range(frames):
            out[number * FRAME:number * FRAME + SECTOR] = sectors[number * SECTOR:(number + 1) * SECTOR]
            if packed[number // 8] & (1 << (number % 8)):
                # the sync and the parity were left out of the stream: put them back as the decoder of the format does
                sector = bytearray(out[number * FRAME:number * FRAME + SECTOR])
                sector[:12] = SYNC
                _ecc_generate(sector)
                out[number * FRAME:number * FRAME + SECTOR] = sector
        return bytes(out)

    @staticmethod
    def _inflate(data: bytes, size: int) -> bytes:
        try:
            out = zlib.decompressobj(-15).decompress(data, size)
        except zlib.error as error:
            raise ChdError(f'a CHD hunk does not inflate: {error}') from None
        if len(out) != size:
            raise ChdError('a CHD hunk inflates to the wrong size')
        return out

    @staticmethod
    def _lzma(data: bytes, size: int) -> bytes:
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA1, 'dict_size': 1 << 24, 'lc': 3, 'lp': 0, 'pb': 2}])
        try:
            out = decoder.decompress(data, max_length=size)
        except lzma.LZMAError as error:
            raise ChdError(f'a CHD hunk does not decode: {error}') from None
        if len(out) != size:
            raise ChdError('a CHD hunk decodes to the wrong size')
        return out

    def _compressed(self, codec: str, packed: bytes) -> bytes:
        if codec == 'cdzl':
            return self._decode_cd(packed, self._inflate)
        if codec == 'cdlz':
            return self._decode_cd(packed, self._lzma)
        if codec == 'zlib':
            return self._inflate(packed, self.hunk_bytes)
        raise ChdCodecError(f'{self.path.name}: the CHD codec {codec or "?"} is not read here')

    def hunk(self, number: int) -> bytes:
        if not 0 <= number < self.total_hunks:
            raise ChdError(f'{self.path.name}: hunk {number} is outside the image')
        cached = self._cache.get(number)
        if cached is not None:
            return cached
        data = self._decode(number)
        if len(self._cache) >= 8:
            self._cache.pop(next(iter(self._cache)))
        self._cache[number] = data
        return data

    def _decode(self, number: int, depth: int = 0) -> bytes:
        if depth > 64:
            raise ChdError(f'{self.path.name}: a CHD hunk refers to itself')
        if self.version == 4:
            kind, offset, length, crc, no_crc = self.map[number]
            if kind == 1:
                data = self._compressed(self.compressors[0], self._at(offset, length))
            elif kind == 2:
                data = self._at(offset, self.hunk_bytes)
            elif kind == 3:
                data = (struct.pack('>Q', offset) * (self.hunk_bytes // 8))
            elif kind == 4:
                if offset >= number:
                    raise ChdError(f'{self.path.name}: a CHD hunk refers forward')
                return self._decode(offset, depth + 1)
            else:
                raise ChdError(f'{self.path.name}: a CHD hunk type this reader does not know')
            if not no_crc and zlib.crc32(data) != crc:
                raise ChdError(f'{self.path.name}: hunk {number} fails its checksum')
            return data
        kind, offset, length, crc = self.map[number]
        if not self.compressors[0]:
            return self._at(offset, self.hunk_bytes)
        if kind in (_TYPE_0, _TYPE_1, _TYPE_2, _TYPE_3):
            data = self._compressed(self.compressors[kind], self._at(offset, length))
        elif kind == _NONE:
            data = self._at(offset, length)
        elif kind == _SELF:
            if offset >= number:
                raise ChdError(f'{self.path.name}: a CHD hunk refers forward')
            return self._decode(offset, depth + 1)
        else:
            raise ChdError(f'{self.path.name}: a CHD hunk of a parent is not supported')
        if crc_hqx(data, 0xFFFF) != crc:
            raise ChdError(f'{self.path.name}: hunk {number} fails its checksum')
        return data

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.logical_bytes:
            raise ChdError(f'{self.path.name}: a read outside the image')
        out = bytearray()
        while length:
            number, inside = divmod(offset, self.hunk_bytes)
            take = min(length, self.hunk_bytes - inside)
            out += self.hunk(number)[inside:inside + take]
            offset += take
            length -= take
        return bytes(out)
