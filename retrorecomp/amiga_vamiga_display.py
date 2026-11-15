"""The picture-only changes to the adapted vAmiga Core (MIT script; the files it changes stay MPL-2.0).

`amiga_vamiga` adapts the pinned Core and is one of the Amiga's generator sources: the native steps specialise its 68000, so an
edit there makes every qualified path wait again (`amiga_knowledge.GENERATOR_REVISION`). A change that only decides which colour a
pixel gets cannot be noticed by a path. Those changes are kept here, outside the generator pins, and they may only touch the files
of `PICTURE_FILES`: the part of Denise that turns bitplane bits into colour indices and colours, which neither the CPU, the
copper, the blitter nor the collision registers read back. `tests/test_amiga_vamiga_display.py` holds that line.

The build stamp still moves with them (`adaptation_digest`): a game built before and after shows different pictures.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import amiga_vamiga

# The only files a replacement of this module may change, each with the functions it may change in it (the text of the replacement
# must sit inside one of them). Nothing here is read by the machine again: colour indices (mBuffer) go to the pixel engine only.
PICTURE_FILES = {
    'Components/Denise/Denise.cpp': ('Denise::translateDPF(Pixel from, Pixel to, PFState &state)',),
}

REPLACEMENTS = [
    # Upstream gap (vAmiga f51a6bf, Denise.cpp): in dual-playfield mode a playfield whose priority in BPLCON2 is above 4 is drawn
    # transparent. That is what OCS and ECS Denise do; AGA's Lisa draws it (upstream already limits the single-playfield form of
    # this to OCS and ECS). An AGA game that writes 7 to both priorities showed colour 0 everywhere: a black screen with sound.
    ('Components/Denise/Denise.cpp',
     '    u8 mask1 = state.zpf1 ? 0xFF : 0x00;\n    u8 mask2 = state.zpf2 ? 0xFF : 0x00;\n',
     '    // Retro-Recomp modification (MPL-2.0, like this file): OCS and ECS only. On AGA a priority above 4 leaves the playfield\'s\n'
     '    // pixels as they are; its place among the sprites (zpf1, zpf2: behind all of them) is unchanged.\n'
     '    u8 mask1 = state.zpf1 || isAGA() ? 0xFF : 0x00;\n    u8 mask2 = state.zpf2 || isAGA() ? 0xFF : 0x00;\n'),
]

MARKER = 'rr-picture.json'      # inside Core/, so it goes when `amiga_vamiga.adapt` makes the folder again


def adaptation_digest() -> str:
    """What the adapted tree depends on: `amiga_vamiga`'s own digest and the replacements of this module."""
    value = hashlib.sha256(b'amiga-vamiga-picture\0' + amiga_vamiga.adaptation_digest().encode())
    for rel, old, new in REPLACEMENTS:
        value.update(b'\0' + rel.encode() + b'\0' + old.encode() + b'\0' + new.encode())
    return value.hexdigest()


def adapt(checkout: Path, target: Path) -> Path:
    """`amiga_vamiga.adapt`, then the replacements of this module; returns the adapted Core folder. Done once per digest: a tree made
    for another digest is made again from the checkout, never patched twice."""
    digest = adaptation_digest()
    core = target / 'Core'
    marker = core / MARKER
    try:
        if json.loads(marker.read_text(encoding='utf-8')).get('adaptation') == digest:
            return core
    except (OSError, ValueError):
        pass
    (target / 'ready.json').unlink(missing_ok=True)
    core = amiga_vamiga.adapt(checkout, target)
    for rel, old, new in REPLACEMENTS:
        path = core / rel
        text = path.read_text(encoding='utf-8')
        if text.count(old) != 1:
            raise ValueError(f'vAmiga {rel}: the pinned text was not found exactly once.')
        path.write_text(text.replace(old, new), encoding='utf-8', newline='\n')
    marker.write_text(json.dumps({'adaptation': digest, 'replacements': len(REPLACEMENTS)}) + '\n', encoding='utf-8')
    return core
