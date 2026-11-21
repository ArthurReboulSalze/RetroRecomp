"""The ColecoVision BIOS a converted cartridge runs on (docs/COLECOVISION.md, "The BIOS"). MIT, Retro-Recomp.

The ColecoVision cannot start a game without its 8 KiB operating system (OS7, at 0000h-1FFFh): the BIOS starts the machine, shows
the title screen, reads the cartridge's header word and calls the game, and the games call its fixed entry points (sound, VRAM and
sprite utilities, the NMI vector at 0066h). No free replacement exists, so, as for the MSX's own BIOS and unlike C-BIOS, the player
gives their own file in Options; it is never shipped, never fetched, never kept in this repository. It is accepted by content: its
size and its SHA-256, the digest of the image MAME's `coleco` set and the common sets carry (SHA-1 45bedc4c...86a92, CRC-32
3aa93ef3: numbers about the file, never its bytes). Any other file is refused with a sentence.

The converted game holds the BIOS's bytes translated beside the cartridge (the BIOS is the first source of the machine's region
map), so the game file is for its owner only, as the MSX's own-BIOS games are.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

BIOS_BYTES = 0x2000
# SHA-256 of the images accepted -> its name, in the order of preference.
KNOWN = {
    '990bf1956f10207d8781b619eb74f89b00d921c8d45c95c334c16c8cceca09ad': 'ColecoVision BIOS (OS7)',
}


def known_name(data: bytes) -> str | None:
    """The name of the BIOS `data` is, None when it is none the converter knows."""
    if len(data) != BIOS_BYTES:
        return None
    return KNOWN.get(hashlib.sha256(data).hexdigest())


def identify(path) -> tuple[str, str] | None:
    """(name, SHA-256) of the BIOS in the file at `path`, None when the file is none (used by Options' firmware search)."""
    try:
        path = Path(path)
        if path.stat().st_size != BIOS_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    name = known_name(data)
    return (name, hashlib.sha256(data).hexdigest()) if name else None


def own_bios(value) -> tuple[bytes, str]:
    """The player's own BIOS from the option's path: its bytes and SHA-256. ValueError (a sentence) when no path is given or the file
    is not the BIOS the converter knows."""
    if not value:
        raise ValueError('The ColecoVision needs its BIOS (8 KiB): choose your own copy in Options, ColecoVision. '
                         'No free replacement exists and none is shipped.')
    path = Path(value)
    try:
        size = path.stat().st_size
        data = path.read_bytes() if size == BIOS_BYTES else b''
    except OSError as error:
        raise ValueError(f'{path.name}: the BIOS file cannot be read ({error.strerror or error}).') from None
    if known_name(data) is None:
        raise ValueError(f'{path.name}: not the ColecoVision BIOS (8 KiB, the image of the common sets: SHA-1 45bedc4c...).')
    return data, hashlib.sha256(data).hexdigest()


def bios_identity(value) -> str:
    """The BIOS of a request, for its identity: the SHA-256 of the player's BIOS, or 'missing' when there is none the converter accepts."""
    try:
        return own_bios(value)[1]
    except (OSError, ValueError):
        return 'missing'
