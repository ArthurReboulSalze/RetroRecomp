"""PlayStation discs as the player gives them, read in place and never changed (Retro-Recomp's own code, MIT).

Containers: CUE sheets with their BIN files (one BIN for the disc or one per track), CloneCD (`.ccd` + `.img` + `.sub`), a bare
`.bin`/`.img` of raw sectors (one data track), an `.iso` of 2,048-byte sectors (the file system only: XA, CD audio and the
sub-channel are not in such a dump), and the PSP "PS1 Classics" EBOOT (`.pbp`, one to five discs, 16 raw sectors per deflate
block). A signed EBOOT (`\\0PGD`) is refused: decrypting it would be DRM circumvention. Nothing here uses GPL code: the formats are
read from their published or observed layout.

A disc is a list of tracks over a numbering of sectors where sector 0 is the first sector of track 1 (MSF 00:02:00, the usual
LBA). `raw(lba)` returns the 2,352-byte sector (`None` for a dump of 2,048-byte sectors), `user(lba)` the 2,048 bytes of a data
sector (Mode 1, or Mode 2 Form 1), `subq(lba)` the 12 bytes of sub-channel Q when the dump kept them.

The disc's identity (`identity()`) is the serial of SYSTEM.CNF, the SHA-256 of the main executable and the geometry; its
`digest()` is the SHA-256 of the geometry followed by every sector of every track as raw sectors (audio as 16-bit little-endian
samples): two containers of the same dump have the same digest.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import io
import json
import re
import struct
import zlib
from pathlib import Path

SECTOR = 2352
USER = 2048
SUB = 96
PREGAP = 150                       # MSF 00:02:00
SYNC = b'\x00' + b'\xff' * 10 + b'\x00'
PBP_BLOCK_SECTORS = 16
PBP_BLOCK = PBP_BLOCK_SECTORS * SECTOR
PBP_MAX_DISCS = 5
MAX_TRACKS = 99
EXTENSIONS = ('.cue', '.ccd', '.pbp', '.iso', '.bin', '.img', '.m3u')


class DiscError(ValueError):
    """A file that is not a PlayStation disc this reader understands, with the reason."""


def msf_to_frames(text: str) -> int:
    m = re.fullmatch(r'\s*(\d{1,3}):(\d{1,2}):(\d{1,2})\s*', text)
    if not m:
        raise DiscError(f'bad time {text!r}')
    mm, ss, ff = (int(v) for v in m.groups())
    if ss >= 60 or ff >= 75:
        raise DiscError(f'bad time {text!r}')
    return (mm * 60 + ss) * 75 + ff


def bcd(value: int) -> int:
    if (value & 0x0f) > 9 or (value >> 4) > 9:
        raise DiscError(f'bad BCD byte {value:#04x}')
    return (value >> 4) * 10 + (value & 0x0f)


# ---- sector sources -------------------------------------------------------------------------------------------------

class _FileSource:
    """Sectors stored one after the other in a file (raw 2,352, raw + 96 sub-channel bytes, or 2,048 user bytes)."""

    def __init__(self, path: Path, stride: int, swap: bool = False):
        self.path = Path(path)
        self.stride = stride
        self.swap = swap               # big-endian CD audio (MOTOROLA)
        self.size = self.path.stat().st_size
        self._file = None

    def _handle(self):
        if self._file is None:
            self._file = open(self.path, 'rb')
        return self._file

    def frames(self) -> int:
        return self.size // self.stride

    def read(self, offset: int, length: int) -> bytes:
        f = self._handle()
        f.seek(offset)
        data = f.read(length)
        if len(data) != length:
            raise DiscError(f'{self.path.name}: short read at {offset}')
        if self.swap:
            a = bytearray(data)
            a[0::2], a[1::2] = data[1::2], data[0::2]
            data = bytes(a)
        return data

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None


class _PbpSource:
    """The raw sectors of one disc of an EBOOT, inflated block by block (16 sectors per block, raw deflate or stored)."""

    def __init__(self, path: Path, blocks: list[tuple[int, int]]):
        self.path = Path(path)
        self.blocks = blocks           # (file offset, stored size) per block
        self.stride = SECTOR
        self.swap = False
        self._file = None
        self._cache: tuple[int, bytes] | None = None

    def frames(self) -> int:
        return len(self.blocks) * PBP_BLOCK_SECTORS

    def block(self, index: int) -> bytes:
        if self._cache and self._cache[0] == index:
            return self._cache[1]
        offset, size = self.blocks[index]
        if self._file is None:
            self._file = open(self.path, 'rb')
        self._file.seek(offset)
        stored = self._file.read(size)
        if len(stored) != size:
            raise DiscError(f'{self.path.name}: block {index} is cut short')
        if size == PBP_BLOCK:
            data = stored
        else:
            try:
                data = zlib.decompress(stored, -15)
            except zlib.error as error:
                raise DiscError(f'{self.path.name}: block {index} does not inflate ({error})') from None
        if len(data) != PBP_BLOCK:
            data = data.ljust(PBP_BLOCK, b'\0')[:PBP_BLOCK]
        self._cache = (index, data)
        return data

    def read(self, offset: int, length: int) -> bytes:
        out = bytearray()
        while length:
            index, within = divmod(offset, PBP_BLOCK)
            if index >= len(self.blocks):
                raise DiscError(f'{self.path.name}: read past the image')
            chunk = self.block(index)[within:within + length]
            out += chunk
            offset += len(chunk)
            length -= len(chunk)
        return bytes(out)

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None


# ---- the disc ---------------------------------------------------------------------------------------------------------

@dataclass
class Track:
    number: int
    mode: str              # 'MODE2/2352', 'MODE1/2352', 'MODE1/2048', 'MODE2/2336', 'AUDIO'
    start: int             # LBA of index 01
    length: int            # sectors from index 01 to the next track (or the lead-out)
    pregap: int            # sectors before index 01 that belong to this track
    source: object = field(repr=False)
    offset: int = 0        # byte offset of the index 01 sector in the source
    stored_pregap: int = 0 # pregap sectors present in the source before `offset`
    sub: object = field(default=None, repr=False)   # (source, byte offset of the index 01 record) for CloneCD

    @property
    def audio(self) -> bool:
        return self.mode == 'AUDIO'

    @property
    def raw(self) -> bool:
        return self.mode in ('MODE1/2352', 'MODE2/2352', 'AUDIO')

    def geometry(self) -> list:
        return [self.number, self.mode, self.start, self.length, self.pregap]


class Disc:
    def __init__(self, path: Path, container: str, tracks: list[Track], sources: list, index: int = 0, count: int = 1):
        if not tracks:
            raise DiscError(f'{Path(path).name}: no track')
        if len(tracks) > MAX_TRACKS:
            raise DiscError(f'{Path(path).name}: more than {MAX_TRACKS} tracks')
        self.path = Path(path)
        self.container = container
        self.tracks = tracks
        self.sources = sources
        self.index = index             # disc number inside a multi-disc EBOOT (0-based)
        self.count = count
        self.leadout = tracks[-1].start + tracks[-1].length

    # sector access
    def track_at(self, lba: int) -> Track | None:
        for t in self.tracks:
            if t.start - t.stored_pregap <= lba < t.start + t.length:
                return t
        return None

    def raw(self, lba: int) -> bytes | None:
        t = self.track_at(lba)
        if t is None:
            raise DiscError(f'sector {lba} is outside the disc')
        if not t.raw:
            return None
        return t.source.read(t.offset + (lba - t.start) * t.source.stride, SECTOR)

    def user(self, lba: int) -> bytes:
        t = self.track_at(lba)
        if t is None or t.audio:
            raise DiscError(f'sector {lba} is not a data sector')
        if t.mode == 'MODE1/2048':
            return t.source.read(t.offset + (lba - t.start) * t.source.stride, USER)
        if t.mode == 'MODE2/2336':
            data = t.source.read(t.offset + (lba - t.start) * t.source.stride, 2336)
            return data[8:8 + USER]
        raw = self.raw(lba)
        if raw[15] == 1:
            return raw[16:16 + USER]
        if raw[15] == 2:
            return raw[24:24 + USER]
        raise DiscError(f'sector {lba}: mode {raw[15]}')

    def subq(self, lba: int) -> bytes | None:
        t = self.track_at(lba)
        if t is None or t.sub is None:
            return None
        source, offset = t.sub
        record = source.read(offset + (lba - t.start) * SUB, SUB)
        return record[12:24]

    def close(self):
        for s in self.sources:
            s.close()

    # geometry, identity
    def geometry(self) -> dict:
        return {'tracks': [t.geometry() for t in self.tracks], 'leadout': self.leadout}

    def digest(self) -> str:
        """SHA-256 of the geometry then every sector of every track (raw, or user data for a 2,048-byte dump)."""
        h = hashlib.sha256(b'rr-psx-disc\0' + json.dumps(self.geometry(), sort_keys=True).encode() + b'\0')
        for t in self.tracks:
            stride = t.source.stride
            unit = SECTOR if t.raw else (USER if t.mode == 'MODE1/2048' else 2336)
            step = 256
            for first in range(0, t.length, step):
                n = min(step, t.length - first)
                data = t.source.read(t.offset + first * stride, (n - 1) * stride + unit)
                if stride == unit:
                    h.update(data)
                else:
                    for i in range(n):
                        h.update(data[i * stride:i * stride + unit])
        return h.hexdigest()

    def data_track(self) -> Track:
        if self.tracks[0].audio:
            raise DiscError(f'{self.path.name}: track 1 is CD audio (not a PlayStation disc)')
        return self.tracks[0]


# ---- containers -------------------------------------------------------------------------------------------------------

_MODES = {'MODE1/2352': 2352, 'MODE2/2352': 2352, 'MODE1/2048': 2048, 'MODE2/2336': 2336, 'AUDIO': 2352}


def glob_escape(text: str) -> str:
    return re.sub(r'([\[\]*?])', r'[\1]', text)


def _cue_tokens(line: str) -> list[str]:
    return [m.group(1) if m.group(1) is not None else m.group(2) for m in re.finditer(r'"([^"]*)"|(\S+)', line)]


def read_cue(path: Path) -> Disc:
    path = Path(path)
    text = path.read_bytes()
    if len(text) > 1 << 20:
        raise DiscError(f'{path.name}: too large for a cue sheet')
    files: list[dict] = []
    cur_file = None
    cur_track = None
    for raw_line in text.decode('utf-8', errors='replace').splitlines():
        tok = _cue_tokens(raw_line)
        if not tok:
            continue
        key = tok[0].upper()
        if key == 'FILE':
            if len(tok) < 3:
                raise DiscError(f'{path.name}: FILE without a type')
            kind = tok[-1].upper()
            if kind not in ('BINARY', 'MOTOROLA'):
                raise DiscError(f'{path.name}: FILE type {kind} is not supported (BINARY or MOTOROLA only)')
            target = (path.parent / tok[1])
            if not target.is_file():
                # Some sheets keep a path from another computer: the file name beside the sheet is accepted.
                target = path.parent / Path(tok[1].replace('\\', '/')).name
            cur_file = {'path': target if target.is_file() else None, 'name': tok[1], 'swap': kind == 'MOTOROLA',
                        'tracks': []}
            files.append(cur_file)
        elif key == 'TRACK':
            if cur_file is None or len(tok) < 3:
                raise DiscError(f'{path.name}: TRACK before FILE')
            mode = tok[2].upper()
            if mode not in _MODES:
                raise DiscError(f'{path.name}: track mode {mode} is not supported')
            cur_track = {'number': int(tok[1]), 'mode': mode, 'index': {}, 'pregap': 0, 'postgap': 0}
            cur_file['tracks'].append(cur_track)
        elif key == 'INDEX' and cur_track is not None:
            cur_track['index'][int(tok[1])] = msf_to_frames(tok[2])
        elif key == 'PREGAP' and cur_track is not None:
            cur_track['pregap'] = msf_to_frames(tok[1])
        elif key == 'POSTGAP' and cur_track is not None:
            cur_track['postgap'] = msf_to_frames(tok[1])
    # A sheet whose only file was renamed (the sheet names "SCUS-94424.img", the folder holds "BloodyRoarII.img"): the image
    # that carries the sheet's own name stands for it.
    if len(files) == 1 and files[0]['path'] is None:
        twins = [p for p in path.parent.glob(glob_escape(path.stem) + '.*') if p.suffix.lower() in ('.bin', '.img')]
        if len(twins) == 1:
            files[0]['path'] = twins[0]
    for f in files:
        if f['path'] is None:
            raise DiscError(f'{path.name}: {f["name"]} is missing')
    tracks: list[Track] = []
    sources = []
    lba = 0
    for f in files:
        if not f['tracks']:
            continue
        stride = _MODES[f['tracks'][0]['mode']]
        source = _FileSource(f['path'], stride, f['swap'])
        sources.append(source)
        frames = source.frames()
        for i, t in enumerate(f['tracks']):
            if 1 not in t['index']:
                raise DiscError(f'{path.name}: track {t["number"]} has no INDEX 01')
            if _MODES[t['mode']] != stride:
                raise DiscError(f'{path.name}: tracks of different sector sizes in one file')
            index1 = t['index'][1]
            index0 = t['index'].get(0, index1)
            nxt = f['tracks'][i + 1] if i + 1 < len(f['tracks']) else None
            end = (nxt['index'].get(0, nxt['index'].get(1)) if nxt else frames)
            if end is None or end < index1 or index1 > frames:
                raise DiscError(f'{path.name}: track {t["number"]} lies outside its file')
            stored = index1 - index0
            if tracks:       # track 1's index 01 is sector 0; a pregap stored before it lies at negative sectors
                lba += t['pregap'] + stored
            start = lba
            length = end - index1
            tracks.append(Track(t['number'], t['mode'], start, length, t['pregap'] + stored, source,
                                offset=index1 * stride, stored_pregap=stored))
            lba = start + length + t['postgap']
    if [t.number for t in tracks] != list(range(1, len(tracks) + 1)):
        raise DiscError(f'{path.name}: track numbers are not 1, 2, 3...')
    return Disc(path, 'cue', tracks, sources)


def _ini(text: str) -> dict:
    out, section = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        m = re.fullmatch(r'\[(.+)\]', line)
        if m:
            section = m.group(1).strip().upper()
            out.setdefault(section, {})
        elif '=' in line and section is not None:
            k, v = line.split('=', 1)
            out[section][k.strip().upper()] = v.strip()
    return out


def _int(value: str) -> int:
    value = value.strip()
    return int(value, 16) if value.lower().startswith('0x') else int(value)


def read_ccd(path: Path) -> Disc:
    path = Path(path)
    ini = _ini(path.read_bytes()[:1 << 20].decode('latin-1'))
    if 'CLONECD' not in ini:
        raise DiscError(f'{path.name}: not a CloneCD control file')
    img = path.with_suffix('.img')
    if not img.is_file():
        found = [p for p in path.parent.glob(glob_escape(path.stem) + '.*') if p.suffix.lower() == '.img']
        if not found:
            raise DiscError(f'{path.name}: the .img file is missing')
        img = found[0]
    source = _FileSource(img, SECTOR)
    sources = [source]
    sub_path = next((p for p in path.parent.glob(glob_escape(path.stem) + '.*') if p.suffix.lower() == '.sub'), None)
    sub = _FileSource(sub_path, SUB) if sub_path else None
    if sub:
        sources.append(sub)
    starts, leadout, controls = {}, None, {}
    for name, sec in ini.items():
        if not name.startswith('ENTRY'):
            continue
        point = _int(sec.get('POINT', '0'))
        if 'PLBA' not in sec:
            continue
        plba = _int(sec['PLBA'])
        if 1 <= point <= MAX_TRACKS:
            starts[point] = plba
            controls[point] = _int(sec.get('CONTROL', '0'))
        elif point == 0xA2:
            leadout = plba
    if not starts:
        raise DiscError(f'{path.name}: no track in the table of contents')
    if leadout is None:
        leadout = source.frames()
    numbers = sorted(starts)
    tracks = []
    for i, n in enumerate(numbers):
        sec = ini.get(f'TRACK {n}', {})
        mode_number = _int(sec.get('MODE', '0' if controls.get(n, 0) & 4 == 0 else '2'))
        mode = {0: 'AUDIO', 1: 'MODE1/2352', 2: 'MODE2/2352'}.get(mode_number)
        if mode is None:
            raise DiscError(f'{path.name}: track {n} mode {mode_number}')
        index1 = _int(sec.get('INDEX 1', str(starts[n])))
        index0 = _int(sec['INDEX 0']) if 'INDEX 0' in sec else index1
        end = starts[numbers[i + 1]] if i + 1 < len(numbers) else leadout
        nxt_sec = ini.get(f'TRACK {numbers[i + 1]}', {}) if i + 1 < len(numbers) else {}
        if 'INDEX 0' in nxt_sec:
            end = _int(nxt_sec['INDEX 0'])
        tracks.append(Track(n, mode, index1, end - index1, index1 - index0, source, offset=index1 * SECTOR,
                            stored_pregap=index1 - index0, sub=(sub, index1 * SUB) if sub else None))
    if tracks[-1].start + tracks[-1].length > source.frames():
        raise DiscError(f'{path.name}: the image is shorter than its table of contents')
    return Disc(path, 'ccd', tracks, sources)


def read_raw_image(path: Path) -> Disc:
    """A bare .bin/.img (raw 2,352-byte sectors, one data track) or .iso (2,048-byte sectors)."""
    path = Path(path)
    size = path.stat().st_size
    if path.suffix.lower() == '.iso' and size % USER == 0:
        with open(path, 'rb') as f:
            head = f.read(16)
        if head[:12] == SYNC and size % SECTOR == 0:
            pass
        else:
            source = _FileSource(path, USER)
            return Disc(path, 'iso', [Track(1, 'MODE1/2048', 0, size // USER, 0, source)], [source])
    if size % SECTOR:
        raise DiscError(f'{path.name}: not a whole number of 2,352-byte sectors')
    source = _FileSource(path, SECTOR)
    first = source.read(0, 16)
    if first[:12] != SYNC:
        raise DiscError(f'{path.name}: the first sector has no CD sync pattern')
    mode = 'MODE2/2352' if first[15] == 2 else 'MODE1/2352'
    return Disc(path, 'bin', [Track(1, mode, 0, size // SECTOR, 0, source)], [source])


@dataclass(frozen=True)
class PbpInfo:
    discs: int
    psar: int
    images: tuple          # file offset of each PSISOIMG0000


def pbp_info(path: Path) -> PbpInfo:
    with open(path, 'rb') as f:
        head = f.read(0x28)
        if len(head) < 0x28 or head[:4] != b'\0PBP':
            raise DiscError(f'{Path(path).name}: not an EBOOT (no PBP header)')
        psar = struct.unpack_from('<I', head, 0x24)[0]
        f.seek(psar)
        magic = f.read(16)
        if magic.startswith(b'PSTITLEIMG'):
            f.seek(psar + 0x200)
            table = struct.unpack('<%dI' % PBP_MAX_DISCS, f.read(4 * PBP_MAX_DISCS))
            images = tuple(psar + t for t in table if t)
            if not images:
                raise DiscError(f'{Path(path).name}: a multi-disc EBOOT with no disc')
        elif magic.startswith(b'PSISOIMG'):
            images = (psar,)
        else:
            raise DiscError(f'{Path(path).name}: the EBOOT holds no PlayStation disc image (PSISOIMG)')
        for image in images:
            f.seek(image)
            if not f.read(16).startswith(b'PSISOIMG'):
                raise DiscError(f'{Path(path).name}: a disc entry of the EBOOT is not a disc image')
            f.seek(image + 0x400)
            if f.read(4) == b'\0PGD':
                raise DiscError(f'{Path(path).name}: a signed (encrypted) EBOOT from the PlayStation Store is not supported')
    return PbpInfo(len(images), psar, images)


def read_pbp(path: Path, index: int = 0) -> Disc:
    path = Path(path)
    info = pbp_info(path)
    if not 0 <= index < info.discs:
        raise DiscError(f'{path.name}: the EBOOT holds {info.discs} disc(s)')
    base = info.images[index]
    size = path.stat().st_size
    with open(path, 'rb') as f:
        f.seek(base + 0x800)
        toc = f.read(10 * 102)
        f.seek(base + 0xBFC)
        data_offset = struct.unpack('<I', f.read(4))[0]
        f.seek(base + 0x4000)
        table = f.read(0x100000 - 0x4000)
    entries = [toc[i * 10:(i + 1) * 10] for i in range(102)]
    # Entries 0-2: A0 (first track), A1 (last track), A2 (lead-out); then one per track:
    # type (0x41 data / 0x01 audio), 0, track (BCD), index 00 MSF (BCD, x3), 0, index 01 MSF (BCD, x3).
    last = bcd(entries[1][7])
    leadout = (bcd(entries[2][7]) * 60 + bcd(entries[2][8])) * 75 + bcd(entries[2][9]) - PREGAP
    if not 1 <= last <= MAX_TRACKS:
        raise DiscError(f'{path.name}: bad track count in the EBOOT table of contents')
    starts = []
    for n in range(1, last + 1):
        e = entries[2 + n]
        audio = (e[0] & 0x40) == 0
        index1 = (bcd(e[7]) * 60 + bcd(e[8])) * 75 + bcd(e[9]) - PREGAP
        starts.append((n, audio, index1))
    base_data = base + (data_offset if data_offset else 0x100000)
    blocks = []
    for i in range(len(table) // 32):
        off, sz = struct.unpack_from('<IH', table, i * 32)
        if sz == 0:
            break
        if base_data + off + sz > size:
            raise DiscError(f'{path.name}: block {i} lies outside the file')
        blocks.append((base_data + off, sz))
    if not blocks:
        raise DiscError(f'{path.name}: the EBOOT disc has no data block')
    source = _PbpSource(path, blocks)
    leadout = min(leadout, source.frames()) if leadout > 0 else source.frames()
    tracks = []
    for i, (n, audio, index1) in enumerate(starts):
        end = starts[i + 1][2] if i + 1 < len(starts) else leadout
        if index1 < 0 or end < index1:
            raise DiscError(f'{path.name}: track {n} has a bad position')
        tracks.append(Track(n, 'AUDIO' if audio else 'MODE2/2352', index1, end - index1, 0, source,
                            offset=index1 * SECTOR))
    return Disc(path, 'pbp', tracks, [source], index=index, count=info.discs)


def read_m3u(path: Path) -> list[Path]:
    path = Path(path)
    out = []
    for line in path.read_bytes()[:1 << 16].decode('utf-8', errors='replace').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            target = path.parent / line
            if not target.is_file():
                raise DiscError(f'{path.name}: {line} is missing')
            out.append(target)
    if not out:
        raise DiscError(f'{path.name}: an empty playlist')
    return out


def open_disc(path: Path, index: int = 0) -> Disc:
    """The disc of a file (the `index`-th disc of a multi-disc EBOOT or playlist)."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.cue':
        return read_cue(path)
    if suffix == '.ccd':
        return read_ccd(path)
    if suffix == '.pbp':
        return read_pbp(path, index)
    if suffix == '.m3u':
        items = read_m3u(path)
        if not 0 <= index < len(items):
            raise DiscError(f'{path.name}: no disc {index + 1}')
        disc = open_disc(items[index])
        disc.index, disc.count = index, len(items)
        return disc
    if suffix in ('.bin', '.img', '.iso'):
        sheet = next((p for p in (path.with_suffix('.cue'), path.with_suffix('.ccd')) if p.is_file()), None)
        if sheet is not None:
            return open_disc(sheet)
        return read_raw_image(path)
    raise DiscError(f'{path.name}: not a disc image the PlayStation reader knows')


def disc_count(path: Path) -> int:
    path = Path(path)
    if path.suffix.lower() == '.pbp':
        return pbp_info(path).discs
    if path.suffix.lower() == '.m3u':
        return len(read_m3u(path))
    return 1


# ---- ISO 9660, SYSTEM.CNF, PS-X EXE -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class IsoEntry:
    name: str
    lba: int
    size: int
    directory: bool


class Iso9660:
    def __init__(self, disc: Disc):
        self.disc = disc
        track = disc.data_track()
        pvd = disc.user(track.start + 16)
        if pvd[0] != 1 or pvd[1:6] != b'CD001':
            raise DiscError(f'{disc.path.name}: no ISO 9660 volume descriptor at sector 16')
        self.system_id = pvd[8:40].decode('ascii', errors='replace').strip()
        self.volume_id = pvd[40:72].decode('ascii', errors='replace').strip()
        self.base = track.start
        self.root = self._record(pvd[156:156 + 34])

    @staticmethod
    def _record(rec: bytes) -> IsoEntry:
        lba = struct.unpack_from('<I', rec, 2)[0]
        size = struct.unpack_from('<I', rec, 10)[0]
        n = rec[32]
        name = rec[33:33 + n].decode('ascii', errors='replace')
        return IsoEntry(name.split(';', 1)[0], lba, size, bool(rec[25] & 2))

    def listdir(self, entry: IsoEntry) -> list[IsoEntry]:
        if not entry.directory or entry.size > 64 * USER:
            raise DiscError('not a directory')
        out = []
        for s in range((entry.size + USER - 1) // USER):
            data = self.disc.user(self.base + entry.lba + s)
            pos = 0
            while pos < USER:
                length = data[pos]
                if length == 0:
                    break
                rec = self._record(data[pos:pos + length])
                if data[pos + 32] == 1 and data[pos + 33] in (0, 1):
                    pass   # '.' and '..'
                else:
                    out.append(rec)
                pos += length
        return out

    def find(self, path: str) -> IsoEntry | None:
        entry = self.root
        for part in [p for p in re.split(r'[\\/]+', path) if p]:
            part = part.split(';', 1)[0].upper()
            entry = next((e for e in self.listdir(entry) if e.name.upper() == part), None)
            if entry is None:
                return None
        return entry

    def read(self, entry: IsoEntry, limit: int = 4 << 20) -> bytes:
        if entry.size > limit:
            raise DiscError(f'{entry.name} is larger than {limit} bytes')
        out = bytearray()
        for s in range((entry.size + USER - 1) // USER):
            out += self.disc.user(self.base + entry.lba + s)
        return bytes(out[:entry.size])


def parse_system_cnf(text: bytes) -> dict:
    out = {}
    for line in text.decode('latin-1').replace('\r', '\n').split('\n'):
        if '=' in line:
            k, v = line.split('=', 1)
            out[k.strip().upper()] = v.strip()
    return out


def boot_path(cnf: dict) -> str | None:
    """`cdrom:\\SLUS_005.94;1` -> `SLUS_005.94`; a subfolder is kept (`DIR\\FILE.EXE`)."""
    value = cnf.get('BOOT')
    if not value:
        return None
    value = value.split()[0]
    if value.lower().startswith('cdrom:'):
        value = value[6:]
    value = value.lstrip('\\/').split(';', 1)[0]
    return value.replace('/', '\\') or None


def serial_of(boot: str) -> str | None:
    name = boot.replace('/', '\\').rsplit('\\', 1)[-1].upper()
    m = re.fullmatch(r'([A-Z]{4})[_-]?(\d{3})\.?(\d{2})', name)
    return f'{m.group(1)}-{m.group(2)}{m.group(3)}' if m else None


@dataclass(frozen=True)
class PsExe:
    pc: int
    gp: int
    load: int
    size: int
    sp: int
    marker: str

    @classmethod
    def parse(cls, data: bytes) -> 'PsExe':
        if len(data) < 0x800 or data[:8] != b'PS-X EXE':
            raise DiscError('not a PS-X EXE')
        pc, gp, load, size = struct.unpack_from('<4I', data, 0x10)
        sp_base, sp_off = struct.unpack_from('<2I', data, 0x30)
        marker = data[0x4C:0x800].split(b'\0', 1)[0].decode('latin-1', errors='replace')[:80]
        if size == 0 or size % 0x800 or size > 0x200000:
            raise DiscError(f'PS-X EXE with a text size of {size:#x}')
        if (load & 0x1fffffff) + size > 0x800000:
            raise DiscError(f'PS-X EXE loaded at {load:#010x} does not fit in RAM')
        return cls(pc, gp, load, size, sp_base + sp_off, marker)


REGION_LICENCES = (
    (b'Sony Computer Entertainment Amer', 'ntsc-u'),
    (b'Sony Computer Entertainment Inc.', 'ntsc-j'),
    (b'Sony Computer Entertainment Euro', 'pal'),
)
SERIAL_REGIONS = {'SCUS': 'ntsc-u', 'SLUS': 'ntsc-u', 'SCES': 'pal', 'SLES': 'pal', 'SCED': 'pal', 'SLED': 'pal',
                  'SCPS': 'ntsc-j', 'SLPS': 'ntsc-j', 'SLPM': 'ntsc-j', 'SCPM': 'ntsc-j', 'SCZS': 'ntsc-j',
                  'PAPX': 'ntsc-j', 'SIPS': 'ntsc-j'}


@dataclass(frozen=True)
class DiscIdentity:
    serial: str | None
    boot: str
    region: str | None
    exe_sha256: str
    exe: PsExe
    system_id: str
    volume_id: str
    geometry: dict
    container: str
    disc_index: int
    disc_count: int

    def metadata(self) -> dict:
        return {'serial': self.serial, 'boot': self.boot, 'region': self.region, 'exe_sha256': self.exe_sha256,
                'exe': {'pc': self.exe.pc, 'load': self.exe.load, 'size': self.exe.size}, 'system_id': self.system_id,
                'volume_id': self.volume_id, 'tracks': len(self.geometry['tracks']),
                'audio_tracks': sum(1 for t in self.geometry['tracks'] if t[1] == 'AUDIO'),
                'leadout': self.geometry['leadout'], 'container': self.container,
                'disc': self.disc_index + 1, 'discs': self.disc_count}


def identity(disc: Disc) -> DiscIdentity:
    iso = Iso9660(disc)
    cnf_entry = iso.find('SYSTEM.CNF')
    boot = None
    if cnf_entry is not None:
        boot = boot_path(parse_system_cnf(iso.read(cnf_entry, 1 << 16)))
    if boot is None:
        boot = 'PSX.EXE'
    exe_entry = iso.find(boot)
    if exe_entry is None:
        raise DiscError(f'{disc.path.name}: the boot file {boot} is not on the disc')
    exe_data = iso.read(exe_entry, 4 << 20)
    exe = PsExe.parse(exe_data)
    region = None
    try:
        licence = disc.user(disc.data_track().start + 4)
        region = next((r for key, r in REGION_LICENCES if key in licence), None)
    except DiscError:
        pass
    serial = serial_of(boot)
    if region is None and serial:
        region = SERIAL_REGIONS.get(serial[:4])
    return DiscIdentity(serial, boot, region, hashlib.sha256(exe_data).hexdigest(), exe, iso.system_id, iso.volume_id,
                        disc.geometry(), disc.container, disc.index, disc.count)


def describe(path: Path) -> list[DiscIdentity]:
    """The identity of every disc of a file (several for a multi-disc EBOOT or playlist)."""
    out = []
    for i in range(disc_count(path)):
        disc = open_disc(path, i)
        try:
            out.append(identity(disc))
        finally:
            disc.close()
    return out
