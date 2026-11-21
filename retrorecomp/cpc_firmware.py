"""The Amstrad CPC firmware the player may give (docs/AMSTRAD_CPC.md): the system ROM (the OS and Locomotive BASIC, 32 KiB) and the
AMSDOS ROM (16 KiB). No free replacement exists and none is shipped; when the player gives none, the converter fetches the pinned
files (retrorecomp/cpc_roms.py), which must have a SHA-1 of this table too. The converter accepts the images whose SHA-1 is in the
public table below, and the « Find firmware in a folder » search (retrorecomp/firmware_search.py) asks the same table.

Source of the digests: MAME 0.289, `mame -listxml cpc664 cpc6128 cpc6128f cpc6128s cpc6128sp` (the maincpu region's system
ROM and cpcados.rom), read on 21 Nov 2026 as facts. Rank: the English 6128 first (the machine modelled), then its French and
Spanish firmware and the later Spanish board, then the 664's (BASIC 1.1 on a 64 KiB machine, AMSDOS the same). The 464's
system ROM (BASIC 1.0, no disk interface of its own) is not accepted.

The system ROM is one 32 KiB file (MAME's layout) or its two 16 KiB halves, the OS then BASIC, as two files in one folder (the
layout of Clock Signal and of most CPC emulators: os6128.rom and basic6128.rom, os664.rom and basic664.rom). A half is recognised
by its content: an OS half is a 16 KiB file that, followed by a 16 KiB file of the same folder, gives a system ROM of the table;
the option then names the OS half, and the BASIC half is found beside it again. The names only choose which neighbour is tried
first.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
from pathlib import Path

SYSTEM_BYTES = 0x8000
AMSDOS_BYTES = 0x4000

# SHA-1 -> (option, label, rank)
DIGESTS = {
    '5977adbad3f7c1e0e082cd02fe76a700d9860c30': ('cpc_system', 'CPC 6128 system ROM (English)', 0),
    '200d59076dfef36db061d6d7d21d80021cab1237': ('cpc_system', 'CPC 6128 system ROM (French)', 1),
    '6765a91a42fed68a807325bf62a728e5ac5d622f': ('cpc_system', 'CPC 6128 system ROM (Spanish)', 2),
    '1acd01c2c03424a78b32c9440f4d890fb1104815': ('cpc_system', 'CPC 6128 system ROM (Spanish, 40038)', 3),
    '073a7665527b5bd8a148747a3947dbd3328682c8': ('cpc_system', 'CPC 664 system ROM', 4),
    '39102c8e9cb55fcc0b9b62098780ed4a3cb6a4bb': ('cpc_amsdos', 'AMSDOS ROM', 0),
}


@dataclass(frozen=True)
class Firmware:
    option: str
    label: str
    rank: int
    sha256: str
    data: bytes


HALF_BYTES = SYSTEM_BYTES // 2
NEIGHBOURS = 64                  # the 16 KiB files of a folder tried as the BASIC half, at most


@lru_cache(maxsize=8)
def _folder_halves(folder: str, stamp: int) -> tuple:
    """The 16 KiB files of a folder and their bytes (`stamp`: the folder's modification time, so a changed folder is read
    again); read once for every file of the folder a search asks about."""
    found = []
    try:
        for entry in sorted(Path(folder).iterdir(), key=lambda p: p.name.lower()):
            try:
                if entry.is_file() and entry.stat().st_size == HALF_BYTES:
                    found.append((entry, entry.read_bytes()))
            except OSError:
                continue
    except OSError:
        return ()
    return tuple(found)


def _neighbours(path: Path) -> list[tuple[Path, bytes]]:
    """The other 16 KiB files of `path`'s folder with their bytes, the likely BASIC half first (basic... beside os...)."""
    try:
        stamp = path.parent.stat().st_mtime_ns
    except OSError:
        return []
    stem = path.stem.lower()
    model = stem[2:] if stem.startswith('os') else ''
    files = [(other, data) for other, data in _folder_halves(str(path.parent), stamp) if other != path]
    files.sort(key=lambda item: (not item[0].stem.lower().startswith('basic'), item[0].stem.lower() != f'basic{model}'))
    return files[:NEIGHBOURS]


def _system_halves(path: Path, first: bytes) -> Firmware | None:
    """The system ROM whose OS half is `first` (the file at `path`) and whose BASIC half is a 16 KiB file beside it."""
    start = hashlib.sha1(first)
    for other, second in _neighbours(path):
        digest = start.copy()
        digest.update(second)
        known = DIGESTS.get(digest.hexdigest())
        if known is not None and known[0] == 'cpc_system':
            data = first + second
            return Firmware(known[0], f'{known[1]}: OS and BASIC in two files ({path.name}, {other.name})', known[2],
                            hashlib.sha256(data).hexdigest(), data)
    return None


def identify(path) -> Firmware | None:
    """The firmware a file is, by its size and SHA-1 (or, for a 16 KiB OS half, with the BASIC half beside it), or None (a file
    that is not in the table is never used). A system ROM's `data` is always the whole 32 KiB, OS then BASIC."""
    path = Path(path)
    try:
        if path.stat().st_size not in (SYSTEM_BYTES, AMSDOS_BYTES):
            return None
        data = path.read_bytes()
    except OSError:
        return None
    known = DIGESTS.get(hashlib.sha1(data).hexdigest())
    if known is None:
        return _system_halves(path, data) if len(data) == HALF_BYTES else None
    return Firmware(known[0], known[1], known[2], hashlib.sha256(data).hexdigest(), data)


def own_firmware(option: str, path) -> Firmware:
    """The player's file for `option` ('cpc_system' or 'cpc_amsdos'), checked; ValueError with the reason otherwise."""
    if not path:
        raise ValueError('The Amstrad CPC needs your own system ROM and AMSDOS ROM (Options, Amstrad CPC).')
    found = identify(path)
    if found is None or found.option != option:
        what = ('a CPC 6128 or 664 system ROM (32 KiB, or its 16 KiB OS half with the BASIC half beside it)'
                if option == 'cpc_system' else 'the AMSDOS ROM (16 KiB)')
        raise ValueError(f'{Path(path).name} is not {what} this converter knows.')
    return found
