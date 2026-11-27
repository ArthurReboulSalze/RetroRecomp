"""PC Engine CD discs as the player gives them, read in place and never changed (Retro-Recomp's own code, MIT).

Containers: a CHD (version 4 or 5, read by `cd_chd`), a CUE sheet with its BIN files, and a bare `.iso` of 2,048-byte sectors. The
CUE and ISO readers are the PlayStation's generic ones (`psx_disc`, pure Python: tracks, sectors, the CUE grammar); a disc is the
same list of tracks over the same numbering of sectors, so this module only adds the CHD container and what is the PC Engine's.

A PC Engine CD is recognised by what it holds, never by its extension: the second sector of the first data track (the IPL) has the
text `PC Engine CD-ROM SYSTEM` at offset 32 and says where the boot program is, where it loads and where it starts (the layout the
engine's own tools read, docs/PC_ENGINE_CD.md). The CHD and the CUE are also the containers of other machines' discs: a file whose
IPL is missing belongs to somebody else and is left to them.

The disc's identity (`image_sha256`) is the SHA-256 of the file as given for a CHD or an ISO, and the engine's `PCE-CUE-1` record
(the sheet and every file it names) for a CUE: the value the engine's own consumer descriptor binds, so a pin made by the engine's
tools and ours name the same disc. It reads the whole file, so it is asked for once, when a conversion needs it.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

from . import cd_chd, psx_disc

DiscError = psx_disc.DiscError
IPL_SIGNATURE = b'PC Engine CD-ROM SYSTEM\x00'
OWN_EXTENSIONS = ('.chd',)             # only ever a disc of some machine: a refusal is said; .cue and .iso are claimed by content
EXTENSIONS = ('.chd', '.cue', '.iso')
CHUNK = 8 * 1024 * 1024


class _ChdSource:
    """The frames of a CHD as a sector source (the 2,448-byte stride of the format), read through its hunks."""

    stride = cd_chd.FRAME

    def __init__(self, chd: cd_chd.Chd):
        self.chd = chd
        self.path = chd.path
        self.size = chd.logical_bytes

    def read(self, offset: int, length: int) -> bytes:
        try:
            return self.chd.read(offset, length)
        except cd_chd.ChdError as error:
            raise DiscError(str(error)) from None

    def close(self) -> None:
        self.chd.close()


def chd_disc(path: Path) -> psx_disc.Disc:
    """The disc of a CHD, with the numbering of sectors of the engine's own provider (docs/PC_ENGINE_CD.md): the lead-in is not counted,
    a pregap is virtual unless the image stores it, and a track begins at its index 01."""
    path = Path(path)
    try:
        chd = cd_chd.Chd(path)
    except cd_chd.ChdError as error:
        raise DiscError(str(error)) from None
    modes = {'MODE1': 'MODE1/2048', 'MODE1_RAW': 'MODE1/2352', 'AUDIO': 'AUDIO'}
    odd = next((t for t in chd.tracks if t.type not in modes), None)
    if odd is not None:
        chd.close()
        raise DiscError(f'{path.name}: track {odd.number} is {odd.type}; a PC Engine CD holds MODE1 and AUDIO tracks')
    source = _ChdSource(chd)
    tracks = [psx_disc.Track(p.track.number, modes[p.track.type], p.start, p.length, p.pregap, source,
                             offset=(p.frame + p.stored) * cd_chd.FRAME, stored_pregap=p.stored) for p in cd_chd.layout(chd.tracks)]
    return psx_disc.Disc(path, 'chd', tracks, [source])


PACK_MAGIC = b'RRCDPCK1'
PACK_ROW = struct.Struct('<6IQ')    # start LBA, sectors from index 01, stored pregap sectors, flags (1 raw data, 2 audio), bytes per sector, 0, offset of index 01
PACK_SUFFIX = '.rrcd'


def _cue_text_rules(path: Path) -> int:
    """What the engine's CUE reader asks that the generic one does not (runtime/src/cue.cpp): BINARY files only, and the POSTGAP of the last track, which moves
    the lead-out. Returns that POSTGAP in sectors."""
    postgap = 0
    for line in path.read_bytes().decode('utf-8', errors='replace').lstrip('﻿').splitlines():
        words = line.split()
        if not words:
            continue
        key = words[0].upper()
        if key == 'FILE' and words[-1].upper() != 'BINARY':
            raise DiscError(f'{path.name}: only BINARY files are read in a PC Engine CD sheet')
        elif key == 'TRACK':
            postgap = 0
        elif key == 'POSTGAP' and len(words) > 1:
            postgap = psx_disc.msf_to_frames(words[1])
    return postgap


def write_pack(cue: Path, out: Path) -> Path:
    """A CUE sheet and its images as one file the game can hold and read in place (native/pcecd_disc.cpp): the tracks with the engine's numbering of sectors,
    then each track's stored pregap and sectors. Nothing is converted or compressed; the files of the player are only read."""
    cue, out = Path(cue), Path(out)
    postgap = _cue_text_rules(cue)
    disc = psx_disc.read_cue(cue)
    try:
        tracks = disc.tracks
        if tracks[0].start != 0 or tracks[0].pregap:
            raise DiscError(f'{cue.name}: the first track must start at the start of its file')
        for t in tracks:
            if t.mode not in ('MODE1/2048', 'MODE1/2352', 'AUDIO'):
                raise DiscError(f'{cue.name}: track {t.number} is {t.mode}; a PC Engine CD holds MODE1 and AUDIO tracks')
        offset = 16 + PACK_ROW.size * len(tracks)
        rows = []
        for t in tracks:
            stride = t.source.stride
            offset += t.stored_pregap * stride
            flags = 2 if t.audio else (1 if t.mode == 'MODE1/2352' else 0)
            rows.append(PACK_ROW.pack(t.start, t.length, t.stored_pregap, flags, stride, 0, offset))
            offset += t.length * stride
        leadout = tracks[-1].start + tracks[-1].length + postgap
        out.parent.mkdir(parents=True, exist_ok=True)
        partial = out.with_name(out.name + '.partial')
        with open(partial, 'wb') as stream:
            stream.write(PACK_MAGIC + struct.pack('<II', len(tracks), leadout) + b''.join(rows))
            for t in tracks:
                stride = t.source.stride
                at, left = t.offset - t.stored_pregap * stride, (t.stored_pregap + t.length) * stride
                while left:
                    block = min(left, stride * 1024)
                    stream.write(t.source.read(at, block))
                    at, left = at + block, left - block
        partial.replace(out)
    finally:
        disc.close()
    return out


def open_disc(path: Path) -> psx_disc.Disc:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.chd':
        return chd_disc(path)
    if suffix in ('.cue', '.iso'):
        return psx_disc.open_disc(path)
    raise DiscError(f'{path.name}: not a disc image the PC Engine CD reader knows')


def first_data_track(disc: psx_disc.Disc):
    return next((t for t in disc.tracks if not t.audio), None)


@dataclass(frozen=True)
class Ipl:
    """The boot record of a PC Engine CD (sector 1 of the first data track)."""
    start_sector: int
    sector_count: int
    load_address: int
    entry_address: int
    mpr_offsets: tuple
    opening_mode: int
    title: str

    @classmethod
    def parse(cls, sector: bytes) -> 'Ipl':
        if len(sector) != 2048 or sector[32:56] != IPL_SIGNATURE:
            raise DiscError('no PC Engine IPL in the second data sector')
        start = int.from_bytes(sector[:3], 'big')
        load, entry = struct.unpack_from('<HH', sector, 4)
        title = sector[0x6A:0x8A].split(b'\0', 1)[0].decode('shift_jis', 'replace').strip()
        return cls(start, sector[3], load, entry, tuple(sector[8:13]), sector[13], title)


def ipl_of(disc: psx_disc.Disc) -> Ipl:
    track = first_data_track(disc)
    if track is None:
        raise DiscError(f'{disc.path.name}: no data track')
    if track.length < 2:
        raise DiscError(f'{disc.path.name}: the first data track is too short to hold an IPL')
    return Ipl.parse(disc.user(track.start + 1))


@dataclass(frozen=True)
class DiscIdentity:
    container: str
    title: str
    tracks: int
    data_tracks: int
    audio_tracks: int
    leadout: int
    ipl: Ipl
    chd_version: int | None = None

    def metadata(self) -> dict:
        return {'container': self.container, 'title': self.title, 'tracks': self.tracks, 'data_tracks': self.data_tracks,
                'audio_tracks': self.audio_tracks, 'leadout': self.leadout, 'chd_version': self.chd_version,
                'ipl': {'start_sector': self.ipl.start_sector, 'sector_count': self.ipl.sector_count,
                        'load_address': self.ipl.load_address, 'entry_address': self.ipl.entry_address,
                        'opening_mode': self.ipl.opening_mode}}


def describe(path: Path) -> DiscIdentity:
    """What a file is as a PC Engine CD, or DiscError when it is not a readable disc or has no IPL."""
    path = Path(path)
    disc = open_disc(path)
    try:
        ipl = ipl_of(disc)
        version = disc.sources[0].chd.version if disc.container == 'chd' else None
        data = sum(1 for t in disc.tracks if not t.audio)
        return DiscIdentity(disc.container, ipl.title, len(disc.tracks), data, len(disc.tracks) - data, disc.leadout, ipl, version)
    finally:
        disc.close()


def _file_sha256(path: Path) -> tuple[int, str]:
    digest, size = hashlib.sha256(), 0
    with open(path, 'rb') as handle:
        while True:
            block = handle.read(CHUNK)
            if not block:
                return size, digest.hexdigest()
            digest.update(block)
            size += len(block)


def image_sha256(path: Path) -> str:
    """The disc's identity: the file for a CHD or an ISO, the engine's PCE-CUE-1 record for a CUE (docs/MEDIA.md of the engine)."""
    path = Path(path)
    if path.suffix.lower() != '.cue':
        return _file_sha256(path)[1]
    disc = psx_disc.read_cue(path)
    try:
        files = [Path(s.path) for s in disc.sources]
    finally:
        disc.close()
    size, digest = _file_sha256(path)
    lines = ['PCE-CUE-1', f'cue\t{size}\t{digest}']
    for name in files:
        size, digest = _file_sha256(name)
        relative = name.resolve().relative_to(path.resolve().parent).as_posix()
        lines.append(f'file\t{relative}\t{size}\t{digest}')
    return hashlib.sha256(('\n'.join(lines) + '\n').encode('utf-8')).hexdigest()


def files_of(path: Path) -> list[Path]:
    """The files a disc is made of (the CUE and its images, or the one file)."""
    path = Path(path)
    if path.suffix.lower() != '.cue':
        return [path]
    disc = psx_disc.read_cue(path)
    try:
        return [path] + [Path(s.path) for s in disc.sources]
    finally:
        disc.close()
