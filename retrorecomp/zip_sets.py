"""Bounded reads of the arcade set ZIPs, shared by Neo Geo and CPS-1.

The consoles keep their own limits, per-member rules and record layouts;
these helpers carry only what they word identically: the container bounds
checked before any decompression, flattened member names, and streamed
digest reads that verify the announced size.
"""
from __future__ import annotations
import hashlib
from contextlib import contextmanager
from pathlib import Path
from zipfile import BadZipFile, ZipFile, ZipInfo

CHUNK_BYTES = 1024 * 1024


@contextmanager
def zip_errors(label: str):
    """The consoles' single translation of zipfile and OS failures."""
    try:
        yield
    except (BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError(f'Cannot read {label} ZIP: {exc}') from exc


def check_size(path: Path, max_bytes: int, *, label: str) -> None:
    """The container's own size bound, checked before the archive is opened."""
    if path.stat().st_size > max_bytes:
        raise ValueError(f'{label} archive exceeds the size limit.')


def bounded_entries(archive: ZipFile, *, label: str, max_members: int, max_expanded: int) -> list[ZipInfo]:
    """The non-directory members, once the count and expanded-size bounds hold."""
    entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    if not entries or len(entries) > max_members:
        raise ValueError(f'Invalid {label} archive member count.')
    if sum(entry.file_size for entry in entries) > max_expanded:
        raise ValueError(f'{label} archive exceeds the expanded size limit.')
    return entries


def flat_name(filename: str) -> str:
    """A member's flattened name: its last path component, casefolded."""
    return filename.replace('\\', '/').rsplit('/', 1)[-1].casefold()


def read_member_digests(archive: ZipFile, member: str | ZipInfo, expected_bytes: int,
                        algorithms: tuple[str, ...], *, label: str) -> dict:
    """Hash one member by streaming chunks; the read length must be the announced one."""
    digests = {name: hashlib.new(name) for name in algorithms}
    count = 0
    with archive.open(member) as source:
        while chunk := source.read(CHUNK_BYTES):
            count += len(chunk)
            if count > expected_bytes:
                raise ValueError(f'{label} member size changed while reading.')
            for digest in digests.values():
                digest.update(chunk)
    if count != expected_bytes:
        raise ValueError(f'Truncated {label} archive member.')
    return {name: digest.hexdigest() for name, digest in digests.items()}
