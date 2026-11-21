"""Amstrad CPC disks as the converter reads them (docs/AMSTRAD_CPC.md): one DSK or EXTENDED DSK image (.dsk), or a ZIP holding
exactly one, never changed. The identity of a disk is the SHA-256 of the image's bytes.

The reader follows the same rules as the runtime's (native/upd765/dsk_image.c): a 256-byte disk block, then one block per track
("Track-Info"), each listing its sector IDs (C, H, R, N) and, in an extended image, the controller status recorded with each
sector and its stored length (several copies of a weak sector). On top of the sectors it reads the AMSDOS catalogue (the
data format, IDs C1h-C9h, directory in cylinder 0; the system format, IDs 41h-49h, directory in cylinder 2 after the two
CP/M tracks) to propose the command that starts the disk from BASIC: `RUN"DISC` when the disk has a DISC file, the one
program it shows otherwise, `|CPM` for a disk that boots CP/M and lists nothing. A disk whose catalogue does not decide is
left undecided with its candidates: the conversion never guesses between two programs."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import struct
import zipfile

SIGNATURES = (b'MV - CPC', b'EXTENDED')
MAX_IMAGE = 2 * 1024 * 1024            # far above the largest image a 3" or 3.5" CPC drive can hold
MAX_CYLINDERS = 84
MAX_SECTORS_PER_TRACK = 29

# The AMSDOS formats, by the sector IDs of a track: first sector R, the cylinder of the directory.
FORMATS = {0xC1: ('data', 0), 0x41: ('system', 2), 0x01: ('ibm', 1)}


@dataclass(frozen=True)
class Sector:
    c: int
    h: int
    r: int
    n: int
    st1: int
    st2: int
    copies: int
    stored: int            # bytes of one copy
    offset: int            # of the first copy in the image

    @property
    def weak(self) -> bool:
        return self.copies > 1


@dataclass(frozen=True)
class Track:
    cylinder: int
    side: int
    sectors: tuple         # Sector, in the image's order (the order they pass under the head)


@dataclass(frozen=True)
class CatalogueFile:
    user: int
    name: str              # NAME.EXT as AMSDOS shows it, attribute bits removed
    hidden: bool           # the system attribute: CAT does not show it
    read_only: bool
    records: int           # 128-byte records, over every extent
    type: str | None = None   # from its AMSDOS header: 'basic', 'protected', 'binary', None (no header)


@dataclass(frozen=True)
class CpcDisk:
    path: Path
    member: str            # the image's name in a ZIP, '' for a .dsk
    data: bytes
    sha256: str
    extended: bool
    cylinders: int
    sides: int
    tracks: tuple          # Track, cylinder * sides + side
    format: str            # 'data', 'system', 'ibm' or 'other' (from cylinder 0's first ID)
    files: tuple = ()      # CatalogueFile, in directory order
    run_command: str | None = None      # RUN"DISC, |CPM, or None: undecided
    candidates: tuple = field(default=())   # the programs a player could start when run_command is None

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def title(self) -> str:
        return self.path.stem

    @property
    def sector_count(self) -> int:
        return sum(len(track.sectors) for track in self.tracks)

    def features(self) -> dict:
        """Numbers about the image, for the inventory and the reports (no byte of it)."""
        sectors = [sector for track in self.tracks for sector in track.sectors]
        sizes = sorted({sector.n for sector in sectors})
        return {
            'extended': self.extended,
            'cylinders': self.cylinders,
            'sides': self.sides,
            'format': self.format,
            'unformatted_tracks': sum(1 for track in self.tracks if not track.sectors),
            'sector_sizes': sizes,
            'weak_sectors': sum(1 for sector in sectors if sector.weak),
            'error_sectors': sum(1 for sector in sectors if (sector.st1 | sector.st2) & 0x21),
            'deleted_sectors': sum(1 for sector in sectors if sector.st2 & 0x40),
            'odd_tracks': sum(1 for track in self.tracks if track.sectors and not _standard_track(track)),
        }


def _standard_track(track: Track) -> bool:
    """Nine 512-byte sectors of one AMSDOS format, IDs in its range, the track's own C and H: a disk no protection touched."""
    if len(track.sectors) != 9:
        return False
    first = min(sector.r for sector in track.sectors)
    if first not in FORMATS:
        return False
    return sorted(sector.r for sector in track.sectors) == list(range(first, first + 9)) and all(
        sector.n == 2 and sector.c == track.cylinder and sector.h == track.side and sector.copies == 1
        and sector.stored == 512 and not (sector.st1 | sector.st2) for sector in track.sectors)


def parse_image(data: bytes) -> tuple[bool, int, int, tuple]:
    """(extended, cylinders, sides, tracks) of a DSK / EXTENDED DSK image; ValueError for anything else."""
    if len(data) < 256 or data[:8] not in SIGNATURES:
        raise ValueError('not a CPC disk image (no "MV - CPC" or "EXTENDED" signature)')
    extended = data[:8] == b'EXTENDED'
    cylinders, sides = data[0x30], data[0x31]
    if not 1 <= cylinders <= MAX_CYLINDERS or sides not in (1, 2):
        raise ValueError(f'a disk of {cylinders} cylinders and {sides} sides')
    standard_size = struct.unpack_from('<H', data, 0x32)[0]
    at, tracks = 256, []
    for index in range(cylinders * sides):
        cylinder, side = divmod(index, sides)
        size = data[0x34 + index] << 8 if extended else standard_size
        if not size:
            tracks.append(Track(cylinder, side, ()))
            continue
        if size < 256 or at + size > len(data) or data[at:at + 10] != b'Track-Info':
            raise ValueError(f'track {cylinder} side {side}: its block is missing or past the end of the image')
        count = data[at + 0x15]
        if count > MAX_SECTORS_PER_TRACK:
            raise ValueError(f'track {cylinder} side {side}: {count} sectors')
        track_n = data[at + 0x14]
        offset, sectors = at + 256, []
        # An early extended image left every stored length out (0); a track with some lengths given means a 0 is no data.
        lengths_given = any(data[at + 0x18 + 8 * s + 6] | data[at + 0x18 + 8 * s + 7] for s in range(count))
        for s in range(count):
            c, h, r, n, st1, st2, length = struct.unpack_from('<6BH', data, at + 0x18 + 8 * s)
            nominal = 128 << (n & 7)
            if extended:
                stored = length
                if not lengths_given:
                    stored = min(nominal, 0x1800)
            else:
                st1 = st2 = 0
                stored = min(128 << (track_n & 7), 0x1800)
            copies = stored // nominal if extended and stored > nominal and stored % nominal == 0 and stored // nominal <= 255 else 1
            if offset + stored > at + size or offset + stored > len(data):
                raise ValueError(f'track {cylinder} side {side}: sector {r:02X}h runs past its track')
            sectors.append(Sector(c, h, r, n, st1, st2, copies, stored // copies, offset))
            offset += stored
        tracks.append(Track(cylinder, side, tuple(sectors)))
        at += size
    return extended, cylinders, sides, tuple(tracks)


def _sector_bytes(data: bytes, tracks: tuple, sides: int, cylinder: int, r: int) -> bytes | None:
    if cylinder * sides >= len(tracks):
        return None
    for sector in tracks[cylinder * sides].sectors:
        if sector.r == r and sector.c == cylinder and sector.n == 2 and sector.stored >= 512:
            return data[sector.offset:sector.offset + 512]
    return None


def _logical_sector(data: bytes, tracks: tuple, sides: int, cylinder: int, base: int, index: int) -> bytes | None:
    """The `index`-th 512-byte sector counted from the directory (nine a track, side 0), as AMSDOS numbers its blocks."""
    return _sector_bytes(data, tracks, sides, cylinder + index // 9, base + index % 9)


def _header_type(record: bytes) -> str | None:
    """The type of an AMSDOS file from its 128-byte header (bytes 0-42h summed in 43h-44h): 'basic', 'protected' (a BASIC
    program saved with ,P), 'binary', or None for a file with no header (ASCII)."""
    if len(record) < 128 or sum(record[:0x43]) & 0xFFFF != record[0x43] | record[0x44] << 8 or not any(record[:0x43]):
        return None
    kind = record[0x12] & 0x0F
    return {0: 'basic', 1: 'protected', 2: 'binary'}.get(kind)


def read_catalogue(data: bytes, tracks: tuple, sides: int) -> tuple[str, tuple]:
    """(format, files) from the AMSDOS directory: 64 entries of 32 bytes in the first four sectors of the directory cylinder,
    1 KiB blocks numbered from there (block 0 and 1 the directory). A format that is not AMSDOS's, or a directory that cannot
    be read, gives no file."""
    first = min((sector.r for sector in tracks[0].sectors), default=None) if tracks else None
    kind, cylinder = FORMATS.get(first, ('other', None))
    if cylinder is None:
        return kind, ()
    directory = b''
    for k in range(4):
        sector = _logical_sector(data, tracks, sides, cylinder, first, k)
        if sector is None:
            return kind, ()
        directory += sector
    files: dict[tuple, dict] = {}
    for entry in range(64):
        raw = directory[entry * 32:entry * 32 + 32]
        user = raw[0]
        if user > 15:
            continue                                          # E5h: free (also the filler of a blank directory)
        name_bytes = bytes(b & 0x7F for b in raw[1:9])
        ext_bytes = bytes(b & 0x7F for b in raw[9:12])
        if any(b < 0x20 for b in name_bytes + ext_bytes):
            continue                                          # not a directory entry (a protection's own data)
        name = name_bytes.decode('latin-1').rstrip()
        ext = ext_bytes.decode('latin-1').rstrip()
        found = files.setdefault((user, name, ext), {'hidden': bool(raw[10] & 0x80), 'read_only': bool(raw[9] & 0x80),
                                                     'records': 0, 'type': None})
        found['records'] += raw[15]
        if raw[12] == 0 and raw[16]:                          # extent 0: the header is the first record of its first block
            sector = _logical_sector(data, tracks, sides, cylinder, first, raw[16] * 2)
            found['type'] = _header_type(sector[:128]) if sector else None
    return kind, tuple(CatalogueFile(user, name + ('.' + ext if ext else ''), f['hidden'], f['read_only'], f['records'],
                                     f['type']) for (user, name, ext), f in files.items())


def run_command(kind: str, files: tuple) -> tuple[str | None, tuple]:
    """The command that starts the disk from BASIC, or (None, candidates). AMSDOS's RUN"name loads NAME, NAME. or NAME.BAS
    first, then NAME.BIN, so the command names a program without its extension. In order: a DISC program (the convention of
    the disk releases); the one command the programs give; the one BASIC program among those CAT shows (the loader of the
    others); the one name every other program's name starts with (GAME before GAME1, GAME2); a disk with no file in the
    system format boots CP/M (|CPM). Anything else stays undecided: the conversion never picks one of two programs."""
    programs = [f for f in files if f.user == 0 and f.name.partition('.')[2] in ('', 'BAS', 'BIN')]
    shown = [f for f in programs if not f.hidden]

    def command(f: CatalogueFile) -> str:
        return 'RUN"' + f.name.partition('.')[0]

    def unique(chosen) -> list:
        return list(dict.fromkeys(command(f) for f in chosen))

    if 'RUN"DISC' in unique(programs):
        return 'RUN"DISC', ()
    pool = shown or programs
    commands = unique(pool)
    if len(commands) == 1:
        return commands[0], ()
    basic = unique(f for f in pool if f.type in ('basic', 'protected'))
    if len(basic) == 1:
        return basic[0], ()
    stems = [c[4:] for c in commands]
    prefixes = [c for c, stem in zip(commands, stems) if stem and all(other.startswith(stem) for other in stems)]
    if len(prefixes) == 1:
        return prefixes[0], ()
    if not files and kind == 'system':
        return '|CPM', ()
    return None, tuple(commands)


def disk_from_bytes(path: Path, member: str, data: bytes) -> CpcDisk:
    extended, cylinders, sides, tracks = parse_image(data)
    kind, files = read_catalogue(data, tracks, sides)
    command, candidates = run_command(kind, files)
    return CpcDisk(path, member, data, hashlib.sha256(data).hexdigest(), extended, cylinders, sides, tracks, kind,
                   files, command, candidates)


def _zip_member(path: Path) -> tuple[str, bytes]:
    try:
        with zipfile.ZipFile(path) as bundle:
            members = [info for info in bundle.infolist() if info.filename.casefold().endswith('.dsk') and not info.is_dir()]
            if len(members) != 1:
                raise ValueError(f'{path.name}: a CPC disk archive holds exactly one .dsk ({len(members)} here).')
            if members[0].file_size > MAX_IMAGE:
                raise ValueError(f'{path.name}: {members[0].filename} is larger than any CPC disk.')
            return members[0].filename, bundle.read(members[0])
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError(f'{path.name}: cannot be read ({error}).') from None


def looks_like_cpc(path: Path) -> bool:
    """A .dsk with the CPCEMU signature, or a ZIP whose one .dsk has it (eight bytes read; nothing else of a ZIP)."""
    suffix = path.suffix.casefold()
    try:
        if suffix == '.dsk':
            with path.open('rb') as source:
                return source.read(8) in SIGNATURES
        if suffix == '.zip':
            with zipfile.ZipFile(path) as bundle:
                members = [info for info in bundle.infolist() if info.filename.casefold().endswith('.dsk')]
                if len(members) != 1 or members[0].file_size > MAX_IMAGE:
                    return False
                with bundle.open(members[0]) as source:
                    return source.read(8) in SIGNATURES
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return False
    return False


def read_disk(path) -> CpcDisk:
    """A .dsk image, or a ZIP holding exactly one; ValueError with the reason otherwise."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == '.zip':
        member, data = _zip_member(path)
    elif suffix == '.dsk':
        try:
            if path.stat().st_size > MAX_IMAGE:
                raise ValueError(f'{path.name}: larger than any CPC disk.')
            data = path.read_bytes()
        except OSError as error:
            raise ValueError(f'{path.name}: cannot be read ({error.strerror or error}).') from None
        member = ''
    else:
        raise ValueError(f'{path.name}: a CPC disk is a .dsk image or a ZIP holding one.')
    try:
        return disk_from_bytes(path, member, data)
    except ValueError as error:
        raise ValueError(f'{path.name}: {error}.') from None
