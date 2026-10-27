"""Stage authored fixtures on a PRIVATE copy of a supplied Human68k floppy.

This deliberately small FAT12 editor only accepts the initial 77-cylinder,
two-sided, eight-1024-byte-sector profile. It is not a disk repair tool or a
general filesystem importer. Source media is read-only. Outputs are confined
to this checkout's ignored .build directory, and never overwritten.

The original Cho Ren Sha disk has a stale second FAT. Existing differences are
preserved: allocation requires a cluster to be free in BOTH FATs, and only new
chains are mirrored. An old replaced AUTOEXEC chain stays allocated in this
short-lived test copy, avoiding any unrelated chain repair or reclamation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from retrorecomp.x68000_media import identify_disk
from tools.x68000_fixtures import human68k_hello

SECTOR_BYTES = 1024
TOTAL_SECTORS = 1232
DISK_BYTES = SECTOR_BYTES * TOTAL_SECTORS
AUTOEXEC = (
    b"ECHO RRHELLO\r\nRRHELLO\r\n"
    b"ECHO RRRELOC\r\nRRRELOC\r\n"
    b"ECHO RETRORECOMP FIXTURES COMPLETE\r\n\x1a"
)


def _short_name(name: str) -> bytes:
    if not name.isascii():
        raise ValueError("Fixture disk requires an ASCII 8.3 root filename.")
    pieces = name.upper().split(".")
    if len(pieces) > 2 or not pieces[0] or len(pieces[0]) > 8:
        raise ValueError("Fixture disk requires an ASCII 8.3 root filename.")
    extension = pieces[1] if len(pieces) == 2 else ""
    if len(extension) > 3 or any(
            not (char.isascii() and (char.isalnum() or char in "_-"))
            for char in pieces[0] + extension):
        raise ValueError("Fixture disk requires an ASCII 8.3 root filename.")
    return (pieces[0].ljust(8) + extension.ljust(3)).encode("ascii")


class FixtureFat12:
    """Bounded root-file reader/editor for the single stage-1 geometry."""
    def __init__(self, payload: bytes):
        if len(payload) != DISK_BYTES:
            raise ValueError("Fixture floppy must contain exactly 1232 KiB.")
        bps, spc, reserved, fats, entries, total, media, fat_sectors = (
            struct.unpack_from("<HBHBHHBH", payload, 11))
        sectors, heads = struct.unpack_from("<HH", payload, 24)
        if (bps, spc, reserved, fats, entries, total, fat_sectors, sectors,
                heads) != (1024, 1, 1, 2, 192, 1232, 2, 8, 2):
            raise ValueError("Unsupported Human68k FAT12 geometry.")
        if media != 0xFE or payload[0x36:0x3E] != b"FAT12   ":
            raise ValueError("Expected the stage-1 Human68k FAT12 volume.")
        self.data = bytearray(payload)
        self.fat_offsets = (1024, 3072)
        self.fat_bytes = 2048
        self.root_offset = 5120
        self.root_entries = entries
        self.data_offset = 11264
        self.cluster_limit = 2 + (len(payload) - self.data_offset) // bps
        for fat in (0, 1):
            if self._fat(0, fat) != 0xFFE or self._fat(1, fat) < 0xFF8:
                raise ValueError("Invalid FAT12 reserved entries.")

    def _fat(self, cluster: int, fat: int = 0) -> int:
        if not 0 <= cluster < self.cluster_limit:
            raise ValueError("FAT12 cluster lies outside the stage-1 volume.")
        offset = self.fat_offsets[fat] + cluster * 3 // 2
        word = self.data[offset] | self.data[offset + 1] << 8
        return (word >> (4 if cluster & 1 else 0)) & 0xFFF

    def _set_fat(self, cluster: int, value: int, fat: int) -> None:
        # Preserve the neighbouring cluster's shared nibble.
        offset = self.fat_offsets[fat] + cluster * 3 // 2
        word = self.data[offset] | self.data[offset + 1] << 8
        if cluster & 1:
            word = (word & 0x000F) | (value << 4)
        else:
            word = (word & 0xF000) | value
        struct.pack_into("<H", self.data, offset, word)

    def _entries(self):
        for index in range(self.root_entries):
            offset = self.root_offset + index * 32
            marker = self.data[offset]
            if marker == 0:
                break
            if marker != 0xE5 and self.data[offset + 11] != 0x0F:
                yield offset

    def _find(self, name: str) -> int | None:
        short = _short_name(name)
        found = [offset for offset in self._entries()
                 if self.data[offset:offset + 11] == short]
        if len(found) > 1:
            raise ValueError(f"Duplicate root filename: {name}")
        return found[0] if found else None

    def _chain(self, first: int) -> list[int]:
        seen = set()
        chain = []
        current = first
        while current < 0xFF8:
            if current < 2 or current >= self.cluster_limit or current in seen:
                raise ValueError("Invalid or looping FAT12 chain.")
            seen.add(current)
            chain.append(current)
            current = self._fat(current)
        return chain

    def read(self, name: str) -> bytes:
        offset = self._find(name)
        if offset is None:
            raise FileNotFoundError(name)
        if self.data[offset + 11] & 0x18:
            raise ValueError("Expected a regular root file.")
        first, size = struct.unpack_from("<HI", self.data, offset + 26)
        if not size:
            if first:
                raise ValueError("Empty file unexpectedly owns a cluster.")
            return b""
        chain = self._chain(first)
        if size > len(chain) * SECTOR_BYTES:
            raise ValueError("File is larger than its cluster chain.")
        return b"".join(bytes(self.data[
            self.data_offset + (cluster - 2) * SECTOR_BYTES:
            self.data_offset + (cluster - 1) * SECTOR_BYTES])
            for cluster in chain)[:size]

    def write(self, name: str, contents: bytes) -> None:
        """Allocate a fresh chain; leave any old chain allocated in this copy."""
        short = _short_name(name)
        offset = self._find(name)
        if offset is not None:
            self.read(name)  # Validate an old chain before replacing its entry.
        else:
            offset = next((self.root_offset + index * 32
                           for index in range(self.root_entries)
                           if self.data[self.root_offset + index * 32]
                           in (0, 0xE5)), None)
            if offset is None:
                raise ValueError("No free root directory entry.")
        needed = (len(contents) + SECTOR_BYTES - 1) // SECTOR_BYTES
        free = [cluster for cluster in range(2, self.cluster_limit)
                if self._fat(cluster, 0) == self._fat(cluster, 1) == 0]
        if needed > len(free):
            raise ValueError("Insufficient clusters free in both original FATs.")
        chain = free[:needed]
        for index, cluster in enumerate(chain):
            following = chain[index + 1] if index + 1 < len(chain) else 0xFFF
            for fat in (0, 1):
                self._set_fat(cluster, following, fat)
            start = self.data_offset + (cluster - 2) * SECTOR_BYTES
            part = contents[index * SECTOR_BYTES:(index + 1) * SECTOR_BYTES]
            self.data[start:start + SECTOR_BYTES] = part.ljust(SECTOR_BYTES, b"\0")
        was_end = self.data[offset] == 0
        entry = bytearray(32)
        entry[:11] = short
        entry[11] = 0x20
        struct.pack_into("<HHHI", entry, 22, 0, 0x21,
                         chain[0] if chain else 0, len(contents))
        self.data[offset:offset + 32] = entry
        if was_end and offset + 32 < self.root_offset + self.root_entries * 32:
            self.data[offset + 32] = 0


def prepare_fixture_disk(source: Path, output: Path) -> dict:
    disk = identify_disk(source)
    if (disk.sector_bytes != 1024 or disk.sectors_per_track != 8
            or disk.present_tracks != tuple(range(154)) or disk.overtrack):
        raise ValueError("Fixture disk requires all 154 standard tracks.")
    output = output.resolve()
    build_root = (ROOT / ".build").resolve()
    if not output.is_relative_to(build_root):
        raise ValueError("Private fixture disks must stay inside project .build.")
    if output.suffix.casefold() != disk.path.suffix.casefold():
        raise ValueError("Fixture disk must retain its source container format.")
    report_path = output.with_suffix(output.suffix + ".json")
    if output.exists() or report_path.exists():
        raise FileExistsError("Private fixture output already exists; preserved.")
    source_data = disk.path.read_bytes()
    if hashlib.sha256(source_data).hexdigest() != disk.sha256:
        raise ValueError("Source changed before fixture staging.")
    header_bytes = 256 if disk.format == "dim" else 0
    volume = FixtureFat12(source_data[header_bytes:])
    system_files = {name: hashlib.sha256(volume.read(name)).hexdigest()
                    for name in ("HUMAN.SYS", "COMMAND.X", "CONFIG.SYS")}
    original_autoexec = hashlib.sha256(volume.read("AUTOEXEC.BAT")).hexdigest()
    fat_differences = sum(a != b for a, b in zip(
        volume.data[1024:3072], volume.data[3072:5120]))
    additions = {"RRHELLO.X": human68k_hello(),
                 "RRRELOC.X": human68k_hello(relocated=True),
                 "AUTOEXEC.BAT": AUTOEXEC}
    for name, payload in additions.items():
        volume.write(name, payload)
        if volume.read(name) != payload:
            raise ValueError(f"Fixture verification failed: {name}")
    for name, digest in system_files.items():
        if hashlib.sha256(volume.read(name)).hexdigest() != digest:
            raise ValueError(f"System file unexpectedly changed: {name}")
    result = source_data[:header_bytes] + bytes(volume.data)
    source_after = identify_disk(disk.path)
    if source_after.sha256 != disk.sha256:
        raise ValueError("Source changed during fixture staging.")
    report = {
        "schema": "retrorecomp.x68000.private-fixture-disk.v1",
        "private_contains_user_supplied_system": True,
        "source": str(disk.path), "source_sha256_before": disk.sha256,
        "source_sha256_after": source_after.sha256,
        "output": str(output), "output_sha256": hashlib.sha256(result).hexdigest(),
        "system_file_sha256_preserved": system_files,
        "original_autoexec_sha256": original_autoexec,
        "original_fat_byte_differences_preserved": fat_differences,
        "replaced_file_old_clusters": "retained; no unrelated FAT repairs",
        "injected": {name: hashlib.sha256(payload).hexdigest()
                     for name, payload in additions.items()},
        "expected": "RRHELLO and RRRELOC each print RETRORECOMP X68000 FIXTURE OK",
        "qualification": "prepared input; guest execution still to validate",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(result)
    with report_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=(
        ROOT / ".build/x68000-stage1/fixture-disk/fixtures.dim"))
    args = parser.parse_args()
    print(json.dumps(prepare_fixture_disk(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
