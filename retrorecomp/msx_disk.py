"""MSX2+ disks as the converter reads them (docs/MSX.md section 9): one raw image (.dsk: 512-byte sectors, nine a track, 80 tracks,
one side or two, 360 or 720 KiB) or a set of them in an M3U (rom_sources.disk_sets writes one for "(Disk n of m)" files),
never changed. The identity of a single disk is its SHA-256; a set's is the SHA-256 of its disks' in order."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

DISK_SIZES = {368640: 1, 737280: 2}          # bytes -> sides
MAX_DISKS = 10


@dataclass(frozen=True)
class MsxDisks:
    path: Path
    disks: tuple                              # the image files, in order
    images: tuple                             # their bytes
    sha256: str

    @property
    def size(self) -> int:
        return sum(len(image) for image in self.images)

    @property
    def title(self) -> str:
        return self.path.stem


def _image(path: Path) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as error:
        raise ValueError(f'{path.name}: cannot be read ({error.strerror or error}).') from None
    if size not in DISK_SIZES:
        raise ValueError(f'{path.name}: not an MSX disk image (360 or 720 KiB of raw sectors; this file has {size} bytes).')
    return path.read_bytes()


def read_disks(path) -> MsxDisks:
    """A .dsk, or an M3U listing one to ten distinct local .dsk files."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == '.dsk':
        image = _image(path)
        return MsxDisks(path, (path,), (image,), hashlib.sha256(image).hexdigest())
    if suffix != '.m3u':
        raise ValueError(f'{path.name}: an MSX2+ disk is a .dsk image or an M3U of them.')
    if path.stat().st_size > 32768:
        raise ValueError(f'{path.name}: a disk playlist is at most 32 KiB.')
    disks = []
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '\x00' in line or '://' in line:
            raise ValueError('Only local disk paths are accepted in an MSX2+ playlist.')
        value = Path(line)
        disks.append(value if value.is_absolute() else path.parent / value)
    if not 1 <= len(disks) <= MAX_DISKS or len(set(disks)) != len(disks):
        raise ValueError('An MSX2+ disk set is one to ten distinct disks.')
    if any(disk.suffix.casefold() != '.dsk' for disk in disks):
        raise ValueError('An MSX2+ disk set lists .dsk images only.')
    images = tuple(_image(disk) for disk in disks)
    digests = [hashlib.sha256(image).hexdigest() for image in images]
    identity = digests[0] if len(digests) == 1 else hashlib.sha256(
        ('msx-disk-set-v1\0' + '\0'.join(digests)).encode('ascii')).hexdigest()
    return MsxDisks(path, tuple(disks), images, identity)
