"""Read-only X68000 media identities for the first machine prototype.

This module identifies containers; it does not claim that their filesystems or
games are bootable. Originals are only opened in binary read mode. Local source
paths are deliberately kept out of the shareable identity, and no source bytes
are serialized. A runtime must use private working copies for guest disk writes.

DIM geometry and its compacted track map are checked against the format used by
PX68k's disk_dim.c at 0ad84d7058a12b7db4f7f7a906e87fad4e2f26f6. This is an
independent parser, not an imported disk emulator.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Sequence


SCHEMA = 'retrorecomp.x68000.sources.v1'
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

    def identity_record(self) -> dict:
        record = {'format': self.format, 'bytes': self.size, 'sha256': self.sha256,
                  'sector_bytes': self.sector_bytes,
                  'sectors_per_track': self.sectors_per_track,
                  'present_tracks': list(self.present_tracks)}
        if self.dim_type is not None:
            record.update(dim_type=self.dim_type, overtrack=self.overtrack)
        return record

    def local_record(self) -> dict:
        return dict(self.identity_record(), path=str(self.path))


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


def _inspect(path: str | Path, *, max_bytes: int, exact_bytes: int | None = None
             ) -> tuple[Path, int, str, bytes]:
    """Hash a bounded regular file, detecting normal concurrent replacement/write."""
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
                digest.update(chunk)
            if (total != initial.st_size or _stamp(os.fstat(source.fileno())) != _stamp(initial)
                    or _stamp(resolved.stat()) != _stamp(initial)):
                raise ValueError('X68000 source changed while reading.')
        return resolved, total, digest.hexdigest(), header
    except OSError as exc:
        raise ValueError(f'Cannot read X68000 source: {exc}') from exc


def identify_disk(path: str | Path) -> DiskImage:
    """Identify exact standard XDF or track-mapped DIM without extracting data.

    XDF has no signature: extension plus the exact 77-cylinder layout are
    required. DIM accepts the legacy header variant without a DIFC signature
    when its media type, track map and payload length agree exactly, as PX68k
    does. Unknown trailing data, truncated tracks and unsupported formats fail.
    """
    suffix = Path(path).suffix.casefold()
    if suffix not in ('.xdf', '.dim'):
        raise ValueError('X68000 prototype supports .xdf and .dim disks only; command files are not executed.')
    resolved, size, digest, header = _inspect(
        path, max_bytes=MAX_DISK_BYTES,
        exact_bytes=XDF_BYTES if suffix == '.xdf' else None)
    if suffix == '.xdf':
        return DiskImage(resolved, 'xdf', size, digest, 1024, 8, tuple(range(154)))
    if len(header) != DIM_HEADER_BYTES:
        raise ValueError('Truncated X68000 DIM header.')
    kind = header[0]
    if kind not in DIM_GEOMETRIES:
        raise ValueError(f'Unsupported X68000 DIM media type {kind}.')
    sector_bytes, sectors_per_track, _normal_tracks = DIM_GEOMETRIES[kind]
    present = tuple(i for i, flag in enumerate(header[1:171]) if flag)
    if not present:
        raise ValueError('X68000 DIM has no stored tracks.')
    overtrack = bool(header[255])
    # The track map is authoritative, including padded 170-track dumps whose
    # legacy overtrack byte is zero. The pinned DIM_SetFD reads all 170 map
    # entries independently of that byte. Preserve it as metadata, but do not
    # reject a complete image merely because the dumper left it unset.
    expected = DIM_HEADER_BYTES + len(present) * sector_bytes * sectors_per_track
    if size != expected:
        raise ValueError(f'X68000 DIM track map requires {expected} bytes; found {size}.')
    return DiskImage(resolved, 'dim', size, digest, sector_bytes,
                     sectors_per_track, present, kind, overtrack)


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
