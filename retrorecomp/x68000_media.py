"""Read-only X68000 media identities for the first machine prototype.

This module identifies containers; it does not claim that their filesystems or
games are bootable. Originals are only opened in binary read mode. Local source
paths are deliberately kept out of the shareable identity, and no source bytes
are serialized. A runtime must use private working copies for guest disk writes.

The format of a floppy image is read from its content, never from its name: a D88 image by its header and
sector records, a DIM image by its 256-byte header (a media type, 170 track flags and, optionally, a
"DIFC HEADER" signature), a raw 2HD image (XDF) by its exact size. The layouts are the public descriptions of
these formats: the DIM media types and track counts (the table below) agree with the loader of the pinned
hissorii/px68k (74ddbb3, `x68k/disk_dim.c`, which the machine runtime compiles), and the D88 header and sector
record are the commonly published ones. Nothing here was taken from the source of px68k-libretro (GPL), and this is
an independent parser, not an imported disk emulator.

A D88 image of the standard 2HD layout (77 cylinders, 2 heads, 8 sectors of 1,024 bytes, no error or deleted mark)
is stored as the equivalent raw XDF, so that the machine and its saved states see the one format they know: it is
the same game as an XDF dump of the same disk. Any other D88 layout (a protection, another geometry) is refused
with its reason.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Sequence


SCHEMA = 'retrorecomp.x68000.sources.v1'
# Names a floppy image may carry; the content decides what it is.
DISK_EXTENSIONS = ('.dim', '.xdf', '.d88', '.88d', '.hdm', '.2hd', '.dup')
D88_HEADER_BYTES = 0x2B0
D88_TRACKS = 164
D88_MEDIA = {0x00: '2D', 0x10: '2DD', 0x20: '2HD', 0x30: '1D', 0x40: '1DD'}
D88_SECTOR_HEADER_BYTES = 16
XDF_BYTES = 77 * 2 * 8 * 1024
DIM_HEADER_BYTES = 256
DIM_TRACKS = 170
# type: (bytes per sector, sectors per track, normal logical track count)
DIM_GEOMETRIES = {0: (1024, 8, 154), 1: (1024, 9, 160),
                  2: (512, 15, 160), 3: (1024, 9, 160),
                  9: (512, 18, 160)}
MAX_DISK_BYTES = DIM_HEADER_BYTES + DIM_TRACKS * 9 * 1024
MAX_MEDIA = 32
IPL_BYTES = 128 * 1024
CGROM_BYTES = 768 * 1024
HASH_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class MachineConfig:
    """Initial MC68000 profile; other CPUs/clocks need their own qualification."""
    model: str = 'x68000'
    cpu: str = 'm68000'
    clock_hz: int = 10_000_000
    ram_bytes: int = 2 * 1024 * 1024

    def __post_init__(self):
        if self.model != 'x68000' or self.cpu != 'm68000':
            raise ValueError('The initial X68000 profile requires an MC68000.')
        if type(self.clock_hz) is not int or self.clock_hz != 10_000_000:
            raise ValueError('The initial X68000 profile requires a 10 MHz CPU.')
        if (type(self.ram_bytes) is not int or self.ram_bytes % (1024 * 1024)
                or not 1024 * 1024 <= self.ram_bytes <= 12 * 1024 * 1024):
            raise ValueError('X68000 RAM must be a whole number of MiB from 1 to 12.')

    def identity_record(self) -> dict:
        return {'model': self.model, 'cpu': self.cpu, 'clock_hz': self.clock_hz,
                'ram_bytes': self.ram_bytes}


@dataclass(frozen=True)
class DiskImage:
    path: Path
    format: str
    size: int
    sha256: str
    sector_bytes: int
    sectors_per_track: int
    present_tracks: tuple[int, ...]
    dim_type: int | None = None
    overtrack: bool = False
    # The stored bytes of an image that is not kept as it is (a standard D88, stored as its raw XDF equivalent).
    converted: bytes | None = field(default=None, repr=False, compare=False)

    def content(self) -> bytes:
        """The bytes the machine stores for this disk: the file itself, or its raw equivalent."""
        return self.converted if self.converted is not None else self.path.read_bytes()

    def identity_record(self) -> dict:
        record = {'format': self.format, 'bytes': self.size, 'sha256': self.sha256,
                  'sector_bytes': self.sector_bytes,
                  'sectors_per_track': self.sectors_per_track,
                  'present_tracks': list(self.present_tracks)}
        if self.dim_type is not None:
            record.update(dim_type=self.dim_type, overtrack=self.overtrack)
        return record

    def local_record(self) -> dict:
        record = dict(self.identity_record(), path=str(self.path))
        if self.converted is not None:
            record['stored_from'] = 'd88'
        return record


@dataclass(frozen=True)
class FirmwareImage:
    path: Path
    role: str
    size: int
    sha256: str

    def identity_record(self) -> dict:
        return {'role': self.role, 'bytes': self.size, 'sha256': self.sha256}

    def local_record(self) -> dict:
        return dict(self.identity_record(), path=str(self.path))


@dataclass(frozen=True)
class FirmwareSet:
    ipl: FirmwareImage
    cgrom: FirmwareImage

    def identity_record(self) -> dict:
        return {'ipl': self.ipl.identity_record(), 'cgrom': self.cgrom.identity_record()}

    def local_record(self) -> dict:
        return {'ipl': self.ipl.local_record(), 'cgrom': self.cgrom.local_record()}


@dataclass(frozen=True)
class X68000Manifest:
    media: tuple[DiskImage, ...]
    firmware: FirmwareSet
    config: MachineConfig
    initial_drives: tuple[int | None, int | None]

    def identity_record(self) -> dict:
        """Path-free, numeric metadata only; not a qualified compilation hint."""
        return {'schema': SCHEMA, 'system': 'x68000',
                'machine': self.config.identity_record(),
                'media': [disk.identity_record() for disk in self.media],
                'firmware': self.firmware.identity_record(),
                'initial_drives': list(self.initial_drives)}

    def public_record(self) -> dict:
        return self.identity_record()

    @property
    def sha256(self) -> str:
        encoded = json.dumps(self.identity_record(), sort_keys=True,
                             separators=(',', ':'), ensure_ascii=True).encode('ascii')
        return hashlib.sha256(encoded).hexdigest()

    def local_record(self) -> dict:
        record = self.identity_record()
        record.update(sha256=self.sha256,
                      media=[disk.local_record() for disk in self.media],
                      firmware=self.firmware.local_record())
        return record

    def verify_sources(self) -> None:
        """Recheck originals before staging, refusing changed media/firmware."""
        actual = build_manifest([disk.path for disk in self.media],
                                self.firmware.ipl.path, self.firmware.cgrom.path,
                                config=self.config, initial_drives=self.initial_drives)
        if actual.sha256 != self.sha256:
            raise ValueError('X68000 sources changed after the manifest was created.')


def _stamp(info: os.stat_result) -> tuple:
    # Windows change-time can advance just by opening a newly created file
    # (observed with Python 3.14/NTFS). It is not a portable content-change test.
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    return identity + ((info.st_ctime_ns,) if os.name != 'nt' else ())


def _inspect(path: str | Path, *, max_bytes: int, exact_bytes: int | None = None, keep: bool = False
             ) -> tuple[Path, int, str, bytes]:
    """Hash a bounded regular file, detecting normal concurrent replacement/write.

    The last item is the first DIM_HEADER_BYTES of the file, or the whole file when `keep` (floppy images are small)."""
    try:
        resolved = Path(path).expanduser().resolve(strict=True)
        initial = resolved.stat()
        if not stat.S_ISREG(initial.st_mode):
            raise ValueError('X68000 sources must be regular files.')
        if initial.st_size > max_bytes:
            raise ValueError('X68000 source exceeds its size limit.')
        if exact_bytes is not None and initial.st_size != exact_bytes:
            raise ValueError(f'X68000 source must contain exactly {exact_bytes} bytes.')
        digest = hashlib.sha256()
        total = 0
        header = b''
        kept = bytearray()
        with resolved.open('rb') as source:
            opened = os.fstat(source.fileno())
            if not stat.S_ISREG(opened.st_mode) or _stamp(opened) != _stamp(initial):
                raise ValueError('X68000 source changed before reading.')
            while chunk := source.read(HASH_CHUNK_BYTES):
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError('X68000 source exceeds its size limit.')
                if not header:
                    header = chunk[:DIM_HEADER_BYTES]
                if keep:
                    kept += chunk
                digest.update(chunk)
            if (total != initial.st_size or _stamp(os.fstat(source.fileno())) != _stamp(initial)
                    or _stamp(resolved.stat()) != _stamp(initial)):
                raise ValueError('X68000 source changed while reading.')
        return resolved, total, digest.hexdigest(), bytes(kept) if keep else header
    except OSError as exc:
        raise ValueError(f'Cannot read X68000 source: {exc}') from exc


class _NotThisFormat(ValueError):
    """The content does not look like the format a reader handles; the next reader may."""


def _u16(data: bytes, at: int) -> int:
    return int.from_bytes(data[at:at + 2], 'little')


def _u32(data: bytes, at: int) -> int:
    return int.from_bytes(data[at:at + 4], 'little')


def _read_d88(resolved: Path, size: int, digest: str, data: bytes) -> DiskImage:
    """A D88 image: a 0x2B0-byte header (name, write protect, media type, disk size, 164 track offsets), then the sector
    records of each track, a 16-byte header (C, H, R, N, sectors in the track, density, deleted mark, status, data size)
    followed by the data. Stored as its raw XDF equivalent when it is a standard 2HD disk."""
    looks = (size >= D88_HEADER_BYTES and data[0x1A] in (0x00, 0x10) and data[0x1B] in D88_MEDIA
             and not any(data[0x11:0x1A]) and _u32(data, 0x1C) == size)
    offsets = [_u32(data, 0x20 + 4 * track) for track in range(D88_TRACKS)] if looks else []
    stored = [track for track, offset in enumerate(offsets) if offset]
    if not looks or not stored or min(offsets[track] for track in stored) < D88_HEADER_BYTES:
        raise _NotThisFormat('Not a D88 image.')
    if data[0x1B] != 0x20:
        raise ValueError(f'X68000 D88 image is a {D88_MEDIA[data[0x1B]]} disk; only 2HD is supported.')
    if stored != list(range(154)):
        raise ValueError('X68000 D88 image does not store the 154 tracks of a 77-cylinder two-sided disk.')
    record = D88_SECTOR_HEADER_BYTES + 1024
    track_bytes = 8 * record
    if D88_HEADER_BYTES + 154 * track_bytes != size:
        raise ValueError('X68000 D88 image is not the standard 2HD layout (8 sectors of 1,024 bytes on each of 154 tracks).')
    content = bytearray()
    for track in range(154):
        if offsets[track] != D88_HEADER_BYTES + track * track_bytes:
            raise ValueError(f'X68000 D88 track {track} is not stored in order.')
        sectors = {}
        for index in range(8):
            at = offsets[track] + index * record
            cylinder, head, number, shift = data[at:at + 4]
            count, density, deleted, status, length = _u16(data, at + 4), data[at + 6], data[at + 7], data[at + 8], _u16(data, at + 14)
            standard = (cylinder, head, shift, count, length) == (track // 2, track % 2, 3, 8, 1024)
            if not standard or density not in (0x00, 0x01) or deleted or status or not 1 <= number <= 8 or number in sectors:
                raise ValueError(f'X68000 D88 track {track} sector {index + 1} is not a standard 2HD sector '
                                 '(a protected or unusual disk is not supported).')
            sectors[number] = data[at + D88_SECTOR_HEADER_BYTES:at + record]
        content += b''.join(sectors[number] for number in range(1, 9))
    content = bytes(content)
    return DiskImage(resolved, 'xdf', len(content), hashlib.sha256(content).hexdigest(), 1024, 8, tuple(range(154)), converted=content)


def _read_dim(resolved: Path, size: int, digest: str, data: bytes) -> DiskImage:
    """A DIM image: 256-byte header (media type, 170 track flags, an optional signature, the overtrack byte), then the
    stored tracks in order. The track map must agree with the length exactly."""
    header = data[:DIM_HEADER_BYTES]
    if len(header) != DIM_HEADER_BYTES:
        raise _NotThisFormat('Truncated X68000 DIM header.')
    kind = header[0]
    if kind not in DIM_GEOMETRIES:
        raise _NotThisFormat(f'Unsupported X68000 DIM media type {kind}.')
    sector_bytes, sectors_per_track, _normal_tracks = DIM_GEOMETRIES[kind]
    present = tuple(i for i, flag in enumerate(header[1:171]) if flag)
    if not present:
        raise _NotThisFormat('X68000 DIM has no stored tracks.')
    overtrack = bool(header[255])
    # The track map is authoritative, including padded 170-track dumps whose legacy overtrack byte is zero: the pinned
    # hissorii loader reads all 170 map entries whatever that byte says. Preserve it as metadata, but do not reject a
    # complete image merely because the dumper left it unset.
    expected = DIM_HEADER_BYTES + len(present) * sector_bytes * sectors_per_track
    if size != expected:
        raise _NotThisFormat(f'X68000 DIM track map requires {expected} bytes; found {size}.')
    return DiskImage(resolved, 'dim', size, digest, sector_bytes, sectors_per_track, present, kind, overtrack)


def _read_raw(resolved: Path, size: int, digest: str, data: bytes) -> DiskImage:
    """A raw 2HD image (XDF, HDM, 2HD, DUP): no header, 77 cylinders of 2 heads of 8 sectors of 1,024 bytes."""
    if size != XDF_BYTES:
        raise _NotThisFormat(f'X68000 source must contain exactly {XDF_BYTES} bytes.')
    return DiskImage(resolved, 'xdf', size, digest, 1024, 8, tuple(range(154)))


def identify_disk(path: str | Path) -> DiskImage:
    """Identify a floppy image from its content: D88, DIM (with or without its signature) or raw 2HD.

    The name only has to be one a floppy image may carry (DISK_EXTENSIONS); it never decides the format, so a raw image
    named .dim, a DIM named .xdf or a D88 with any of them is read for what it is. A file that is none of them fails with
    the reason of the format its name suggests. Unknown trailing data, truncated tracks and unsupported formats fail.
    """
    suffix = Path(path).suffix.casefold()
    if suffix not in DISK_EXTENSIONS:
        raise ValueError('X68000 supports DIM, XDF and D88 floppy images only (%s); command files are not executed.'
                         % ', '.join(DISK_EXTENSIONS))
    resolved, size, digest, data = _inspect(path, max_bytes=MAX_DISK_BYTES, keep=True)
    reasons = {}
    for name, reader in (('d88', _read_d88), ('dim', _read_dim), ('xdf', _read_raw)):
        try:
            return reader(resolved, size, digest, data)
        except _NotThisFormat as reason:
            reasons[name] = str(reason)
    preferred = {'.dim': 'dim', '.d88': 'd88', '.88d': 'd88'}.get(suffix, 'xdf')
    raise ValueError(reasons[preferred] if preferred != 'd88' else
                     'X68000 D88 image is not recognised (its header does not describe this file).')


def validate_firmware(ipl: str | Path, cgrom: str | Path) -> FirmwareSet:
    """Check full user-supplied images; hashes identify a variant, not its license."""
    def image(path, role, size):
        resolved, count, digest, _ = _inspect(path, max_bytes=size, exact_bytes=size)
        return FirmwareImage(resolved, role, count, digest)
    return FirmwareSet(image(ipl, 'ipl', IPL_BYTES), image(cgrom, 'cgrom', CGROM_BYTES))


def build_manifest(disks: Sequence[str | Path], ipl: str | Path, cgrom: str | Path,
                   *, config: MachineConfig | None = None,
                   initial_drives: Sequence[int | None] = (0, None)) -> X68000Manifest:
    """Build the ordered source identity; drive entries are indexes into disks.

    Disk ordering, boot-drive assignment, firmware and machine settings all
    influence identity. Names and local folders do not. No file is created.
    """
    if isinstance(disks, (str, bytes, Path)) or not 1 <= len(disks) <= MAX_MEDIA:
        raise ValueError(f'Provide an ordered list of 1 to {MAX_MEDIA} X68000 disks.')
    if (len(initial_drives) != 2 or any(
            entry is not None and (type(entry) is not int or not 0 <= entry < len(disks))
            for entry in initial_drives)):
        raise ValueError('X68000 requires two drive slots containing valid disk indexes or None.')
    if initial_drives[0] is None:
        raise ValueError('The initial X68000 boot disk must be inserted in drive 0.')
    if config is None:
        config = MachineConfig()
    if not isinstance(config, MachineConfig):
        raise ValueError('Provide an X68000 MachineConfig.')
    media = tuple(identify_disk(path) for path in disks)
    firmware = validate_firmware(ipl, cgrom)
    return X68000Manifest(media, firmware, config, tuple(initial_drives))
