"""Write a standard 2HD X68000 floppy image in another container: raw XDF or D88 (for the owner's checks of the D88 reader).

    python tools/x68000_disk_rewrite.py <disk.dim|.xdf|.d88> --format d88|xdf <output file>

Only the container changes: the 154 tracks of eight 1,024-byte sectors are copied byte for byte (a DIM with every track
present, an XDF or a standard D88 is accepted; a disk with another geometry or with missing tracks is refused). The D88 is
laid out as `retrorecomp/x68000_media.py` reads it: a 0x2B0-byte header (name, media type 0x20 for 2HD, the size of the file
and 164 track offsets), then each track's eight sector records of 16 bytes followed by their data. The output holds the
whole content of the disk: keep it as private as the disk it comes from, and outside the repository.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from retrorecomp.x68000_media import D88_HEADER_BYTES, XDF_BYTES, identify_disk

TRACKS = 154
SECTORS = 8
SECTOR_BYTES = 1024
DIM_HEADER_BYTES = 256


def raw_disk(path: Path) -> bytes:
    """The raw 2HD bytes of a standard full disk, from any of the three containers."""
    image = identify_disk(path)
    if (image.sector_bytes, image.sectors_per_track, image.present_tracks) != (SECTOR_BYTES, SECTORS, tuple(range(TRACKS))):
        raise ValueError('Only a standard 2HD disk (154 tracks of eight 1,024-byte sectors, none missing) can be rewritten.')
    data = image.content()
    raw = data[DIM_HEADER_BYTES:] if image.format == 'dim' else data
    if len(raw) != XDF_BYTES:
        raise ValueError('The disk does not hold exactly the bytes of a standard 2HD disk.')
    return raw


def d88_disk(raw: bytes, name: bytes = b'RETRO-RECOMP') -> bytes:
    header = bytearray(D88_HEADER_BYTES)
    header[:len(name)] = name
    header[0x1B] = 0x20
    body = bytearray()
    for track in range(TRACKS):
        header[0x20 + 4 * track:0x24 + 4 * track] = (D88_HEADER_BYTES + len(body)).to_bytes(4, 'little')
        for sector in range(SECTORS):
            start = (track * SECTORS + sector) * SECTOR_BYTES
            body += (bytes([track // 2, track % 2, sector + 1, 3]) + SECTORS.to_bytes(2, 'little') + bytes([0, 0, 0]) + bytes(5)
                     + SECTOR_BYTES.to_bytes(2, 'little') + raw[start:start + SECTOR_BYTES])
    header[0x1C:0x20] = (D88_HEADER_BYTES + len(body)).to_bytes(4, 'little')
    return bytes(header) + bytes(body)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('disk', type=Path)
    parser.add_argument('--format', choices=('d88', 'xdf'), required=True)
    parser.add_argument('output', type=Path)
    options = parser.parse_args(argv)
    if options.output.exists():
        parser.error(f'{options.output} exists: nothing is overwritten.')
    raw = raw_disk(options.disk)
    data = d88_disk(raw) if options.format == 'd88' else raw
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_bytes(data)
    # The result must read back as the same disk.
    if raw_disk(options.output) != raw:
        options.output.unlink()
        raise SystemExit('The written image does not read back as the same disk; it was removed.')
    print(f'{options.output}: {len(data)} bytes, {options.format}, same disk content')


if __name__ == '__main__':
    main()
