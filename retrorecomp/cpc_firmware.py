"""The Amstrad CPC firmware the player gives (docs/AMSTRAD_CPC.md): the system ROM (the OS and Locomotive BASIC, 32 KiB) and the
AMSDOS ROM (16 KiB). No free replacement exists and none is shipped: the converter accepts the images whose SHA-1 is in the
public table below, and the « Find firmware in a folder » search (retrorecomp/firmware_search.py) asks the same table.

Source of the digests: MAME 0.289, `mame -listxml cpc664 cpc6128 cpc6128f cpc6128s cpc6128sp` (the maincpu region's system
ROM and cpcados.rom), read on 21 Nov 2026 as facts. Rank: the English 6128 first (the machine modelled), then its French and
Spanish firmware and the later Spanish board, then the 664's (BASIC 1.1 on a 64 KiB machine, AMSDOS the same). The 464's
system ROM (BASIC 1.0, no disk interface of its own) is not accepted.
"""
from __future__ import annotations

from dataclasses import dataclass
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


def identify(path) -> Firmware | None:
    """The firmware a file is, by its size and SHA-1, or None (a file that is not in the table is never used)."""
    path = Path(path)
    try:
        if path.stat().st_size not in (SYSTEM_BYTES, AMSDOS_BYTES):
            return None
        data = path.read_bytes()
    except OSError:
        return None
    known = DIGESTS.get(hashlib.sha1(data).hexdigest())
    if known is None:
        return None
    return Firmware(known[0], known[1], known[2], hashlib.sha256(data).hexdigest(), data)


def own_firmware(option: str, path) -> Firmware:
    """The player's file for `option` ('cpc_system' or 'cpc_amsdos'), checked; ValueError with the reason otherwise."""
    if not path:
        raise ValueError('The Amstrad CPC needs your own system ROM and AMSDOS ROM (Options, Amstrad CPC).')
    found = identify(path)
    if found is None or found.option != option:
        what = 'a CPC 6128 or 664 system ROM (32 KiB)' if option == 'cpc_system' else 'the AMSDOS ROM (16 KiB)'
        raise ValueError(f'{Path(path).name} is not {what} this converter knows.')
    return found
