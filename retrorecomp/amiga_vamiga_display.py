"""The display-pipeline changes to the adapted vAmiga Core (MIT script; the files it changes stay MPL-2.0).

`amiga_vamiga` adapts the pinned Core and is one of the Amiga's generator sources: the native steps specialise its 68000, so an
edit there makes every qualified path wait again (`amiga_knowledge.GENERATOR_REVISION`). Two kinds of change cannot be noticed by
a path, because they decide nothing the code a path becomes runs on: what colour a pixel gets, and how fast the display pipeline
reaches the state vAmiga's own path reaches (a shortcut that `tools/amiga_display_selftest.py` replays against vAmiga's path, slot
by slot). Those are kept here, outside the generator pins, and they may only touch the functions of `DISPLAY_FUNCTIONS`: Denise's
drawing, and Agnus's bitplane and sprite slots of a line. Never the CPU, the memory, the CIAs, Paula, the Copper or the Blitter.
`tests/test_amiga_vamiga_display.py` holds that line.

The build stamp still moves with them (`adaptation_digest`): a game built before and after shows different pictures.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import amiga_vamiga

# The only files a replacement of this module may change, each with the functions it may change in it (the text of the replacement
# must sit inside one of them, or in the comment just above it). Denise's colour indices go to the pixel engine only; the
# shortcuts of Agnus and Denise are replayed against vAmiga's own path by tools/amiga_display_selftest.py.
DISPLAY_FUNCTIONS = {
    'Components/Denise/Denise.cpp': ('Denise::translateDPF(Pixel from, Pixel to, PFState &state)', 'Denise::drawLoresBoth()',
                                     'Denise::drawHiresBoth()', 'Denise::drawShresBoth()', 'Denise::rrQuietLine(isize vpos)'),
    'Components/Denise/Denise.h': ('class Denise',),
    'Components/Agnus/AgnusEvents.cpp': ('Agnus::rrSprLineStart()', 'Agnus::rrBplLineStart()', 'Agnus::rrBplCatchUp(isize to)',
                                         'Agnus::rrBplRangeOk()'),
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
    # The four AGA speed shortcuts (1.7.7, owner's decision of 16 November 2026, « c'est quelque chose qui est important »): the display
    # shortcuts of the Amiga 500 (stages 1 to 7), switched off under AGA until they were checked there, open to it. One pass for both
    # parities of a line (on AGA both are prepared first), the bitplane slots of a line in a batch (on AGA the range is taken for the
    # widest FMODE fetch), the quiet line (BPLCON4's XOR and BPLCON3's playfield 2 offset are in its key) and the idle sprites. Each is
    # checked against vAmiga's own path by tools/amiga_display_selftest.py, AGA scenarios included (--per-slot runs vAmiga's).
    ('Components/Agnus/AgnusEvents.cpp',
     '\n// Retro-Recomp modification (MPL-2.0, like this file): the idle sprites of the line (Agnus.h). Not on line 0, not on AGA.\nvoid\n',
     "\n// Retro-Recomp modification (MPL-2.0, like this file): the idle sprites of the line (Agnus.h). Not on line 0. On AGA too: an\n// idle sprite's slots do nothing there either (SSCAN2 only acts on a sprite whose DMA is on).\nvoid\n"),
    ('Components/Agnus/AgnusEvents.cpp',
     '    rrSprIdle = 0;\n    if (!rrSprSkip || pos.v == 0 || isAGA()) return;\n    for (isize n = 0; n < 8; n++) {\n',
     '    rrSprIdle = 0;\n    if (!rrSprSkip || pos.v == 0) return;\n    for (isize n = 0; n < 8; n++) {\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     "\n// Retro-Recomp modification (MPL-2.0, like this file): a line's bitplane slots in a batch (Agnus.h). The guard: no AGA, not\n// line 0, every bitplane DMA slot in $18-$E1 (away from the refresh slots), no super-hires fetch, each plane's modulo on its\n// last fetch, every fetch of the line in chip RAM. Else the line runs on vAmiga's events, as before.\nvoid\n",
     "\n// Retro-Recomp modification (MPL-2.0, like this file): a line's bitplane slots in a batch (Agnus.h). The guard: not line 0,\n// every bitplane DMA slot in $18-$E1 (away from the refresh slots), no super-hires fetch, each plane's modulo on its last\n// fetch, every fetch of the line in chip RAM (on AGA, as wide as FMODE can make it). Else the line runs on vAmiga's events.\nvoid\n"),
    ('Components/Agnus/AgnusEvents.cpp',
     '    bool closed[8] = { };\n    bool fits = rrBplBatching && !isAGA() && pos.v != 0;\n    for (isize h = first; fits && h < HPOS_MAX; h = sequencer.nextBplEvent[h]) {\n',
     '    bool closed[8] = { };\n    bool fits = rrBplBatching && pos.v != 0;\n    for (isize h = first; fits && h < HPOS_MAX; h = sequencer.nextBplEvent[h]) {\n'),
    ('Components/Agnus/AgnusEvents.cpp',
     '        if (!rrRemain[p]) continue;\n        const u32 start = bplpt[p] & ptrMask;\n        const u32 size = 2 * u32(rrRemain[p]);\n        if (start + size - 1 > ptrMask) return false;\n',
     "        if (!rrRemain[p]) continue;\n        // AGA: a fetch reads up to four words of an aligned group of 8 bytes (FMODE, which a write within the line may change),\n        // so the range is taken for the widest fetch, from the start of the pointer's group.\n        const u32 start = (isAGA() ? bplpt[p] & ~7u : bplpt[p]) & ptrMask;\n        const u32 size = isAGA() ? 8 * u32(rrRemain[p]) + 8 : 2 * u32(rrRemain[p]);\n        if (start + size - 1 > ptrMask) return false;\n"),
    ('Components/Denise/Denise.cpp',
     '{\n    // Retro-Recomp modification (MPL-2.0, like this file): one pass when both parities are armed at the same offset.\n    if (!isAGA() && armedOdd && armedEven && pixelOffsetOdd == pixelOffsetEven) {\n        updateShiftRegistersOdd();\n        updateShiftRegistersEven();\n        drawBoth <Resolution::LORES> (pixelOffsetOdd);\n        armedOdd = false;\n        armedEven = false;\n        return;\n    }\n',
     '{\n    // Retro-Recomp modification (MPL-2.0, like this file): one pass when both parities are armed at the same offset. On AGA both\n    // parities are prepared first: prepareOdd and prepareEven touch disjoint state, and drawing the odd planes reads nothing\n    // prepareEven writes; when the pass does not apply, each armed parity is then drawn as vAmiga draws it.\n    if (rrBothOnce) {\n        const bool aga = isAGA();\n        if (aga) { prepareOdd(); prepareEven(); }\n        if (armedOdd && armedEven && pixelOffsetOdd == pixelOffsetEven) {\n            updateShiftRegistersOdd();\n            updateShiftRegistersEven();\n            drawBoth <Resolution::LORES> (pixelOffsetOdd);\n            armedOdd = false;\n            armedEven = false;\n            return;\n        }\n        if (aga) {\n            if (armedOdd) { updateShiftRegistersOdd(); drawOdd <Resolution::LORES> (pixelOffsetOdd); armedOdd = false; }\n            if (armedEven) { updateShiftRegistersEven(); drawEven <Resolution::LORES> (pixelOffsetEven); armedEven = false; }\n            return;\n        }\n    }\n'),
    ('Components/Denise/Denise.cpp',
     '{\n    // Retro-Recomp modification (MPL-2.0, like this file): one pass when both parities are armed at the same offset.\n    if (!isAGA() && armedOdd && armedEven && pixelOffsetOdd == pixelOffsetEven) {\n        updateShiftRegistersOdd();\n        updateShiftRegistersEven();\n        drawBoth <Resolution::HIRES> (pixelOffsetOdd);\n        armedOdd = false;\n        armedEven = false;\n        return;\n    }\n',
     '{\n    // Retro-Recomp modification (MPL-2.0, like this file): one pass when both parities are armed at the same offset. On AGA both\n    // parities are prepared first: prepareOdd and prepareEven touch disjoint state, and drawing the odd planes reads nothing\n    // prepareEven writes; when the pass does not apply, each armed parity is then drawn as vAmiga draws it.\n    if (rrBothOnce) {\n        const bool aga = isAGA();\n        if (aga) { prepareOdd(); prepareEven(); }\n        if (armedOdd && armedEven && pixelOffsetOdd == pixelOffsetEven) {\n            updateShiftRegistersOdd();\n            updateShiftRegistersEven();\n            drawBoth <Resolution::HIRES> (pixelOffsetOdd);\n            armedOdd = false;\n            armedEven = false;\n            return;\n        }\n        if (aga) {\n            if (armedOdd) { updateShiftRegistersOdd(); drawOdd <Resolution::HIRES> (pixelOffsetOdd); armedOdd = false; }\n            if (armedEven) { updateShiftRegistersEven(); drawEven <Resolution::HIRES> (pixelOffsetEven); armedEven = false; }\n            return;\n        }\n    }\n'),
    ('Components/Denise/Denise.cpp',
     '{\n    // Retro-Recomp modification (MPL-2.0, like this file): one pass when both parities are armed at the same offset.\n    if (!isAGA() && armedOdd && armedEven && pixelOffsetOdd == pixelOffsetEven) {\n        updateShiftRegistersOdd();\n        updateShiftRegistersEven();\n        drawBoth <Resolution::SHRES> (pixelOffsetOdd);\n        armedOdd = false;\n        armedEven = false;\n        return;\n    }\n',
     '{\n    // Retro-Recomp modification (MPL-2.0, like this file): one pass when both parities are armed at the same offset. On AGA both\n    // parities are prepared first: prepareOdd and prepareEven touch disjoint state, and drawing the odd planes reads nothing\n    // prepareEven writes; when the pass does not apply, each armed parity is then drawn as vAmiga draws it.\n    if (rrBothOnce) {\n        const bool aga = isAGA();\n        if (aga) { prepareOdd(); prepareEven(); }\n        if (armedOdd && armedEven && pixelOffsetOdd == pixelOffsetEven) {\n            updateShiftRegistersOdd();\n            updateShiftRegistersEven();\n            drawBoth <Resolution::SHRES> (pixelOffsetOdd);\n            armedOdd = false;\n            armedEven = false;\n            return;\n        }\n        if (aga) {\n            if (armedOdd) { updateShiftRegistersOdd(); drawOdd <Resolution::SHRES> (pixelOffsetOdd); armedOdd = false; }\n            if (armedEven) { updateShiftRegistersEven(); drawEven <Resolution::SHRES> (pixelOffsetEven); armedEven = false; }\n            return;\n        }\n    }\n'),
    ('Components/Denise/Denise.cpp',
     '// no BPLCON change (conChanges), no BPLCON0 or BPLCON2 change for the pixel engine, no HAM, no super-hires, no border sprites,\n// no hidden bitplanes or X-ray layers, not AGA, and the next line visible (the VBLANK branch reads the buffers translate leaves).\nbool\n',
     "// no BPLCON change (conChanges), no BPLCON0 or BPLCON2 change for the pixel engine, no HAM, no super-hires, no border sprites,\n// no hidden bitplanes or X-ray layers, and the next line visible (the VBLANK branch reads the buffers translate leaves). On AGA,\n// translate also reads BPLCON4's colour XOR (in the key, from the line's start) and BPLCON3's playfield 2 offset (in the key,\n// read where translate reads it); a change of BPLCON4 within the line is in conChanges.\nbool\n"),
    ('Components/Denise/Denise.cpp',
     '{\n    if (!rrQuiet || isAGA() || wasArmed || config.hiddenBitplanes || borderSprites()) return false;\n    if (!conChanges.isEmpty()) return false;\n',
     '{\n    if (!rrQuiet || wasArmed || config.hiddenBitplanes || borderSprites()) return false;\n    if (!conChanges.isEmpty()) return false;\n'),
    ('Components/Denise/Denise.h',
     "    static inline bool rrQuiet = true;           // false: every line on vAmiga's line pass\n    u64 rrQuietLines[2] = { };                   // visible lines in one pass, on vAmiga's pass\n",
     "    static inline bool rrQuiet = true;           // false: every line on vAmiga's line pass\n    static inline bool rrBothOnce = true;        // false: each parity of a line drawn in its own pass (vAmiga's)\n    u64 rrQuietLines[2] = { };                   // visible lines in one pass, on vAmiga's pass\n"),
    # The batch's catch-up on AGA: a wide fetch (FMODE 1 or 3) reads two or four words in one slot, and vAmiga's own path leaves the last
    # of them on the data bus (what a read of a write-only register returns). The catch-up stamps each write to the bus with its slot's
    # clock and keeps the first of equal stamps, so the last word is put back (tools/amiga_display_selftest.py, AGA scenario 8008).
    ('Components/Agnus/AgnusEvents.cpp',
     '        rrBplDo(event);\n        if (k) {\n',
     '        rrBplDo(event);\n'
     '        // Retro-Recomp modification (MPL-2.0, like this file): on AGA a wide fetch (FMODE 1 or 3) reads two or four words in this\n'
     '        // slot and vAmiga leaves the last on the data bus; the deferred bus kept the first (same clock), so the last is put back.\n'
     '        if (k && isAGA() && (fmode & 1) && mem.dataBus.at == mem.dataBus.deferred)\n'
     '            mem.dataBus.v = mem.spypeek16<Accessor::AGNUS>(busAddr[at] | ((fmode & 2) ? 6u : 2u));\n'
     '        if (k) {\n'),
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
