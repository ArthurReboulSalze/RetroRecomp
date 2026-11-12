"""The walk of a player's own record on a 68000 machine that keeps one (the Amiga, kind 22; the Atari ST, kind 24), and the Atari ST's sweep over images of memory: one copy (MIT).

A record is a list of windows, (pc, bytes), each noted at an instruction that ran on the interpreter (native/runtime_feedback.c). The walk turns a window into instructions: the first
is the one that ran there ("started"), the others are those a walk through the rest of the window finds ("walked"). A walk goes on past a jump, because the recorder relies on it for
what follows in the window; it stops at what cannot be an instruction. A guess that is not code is only a routine that never runs: on both machines the native code is guarded by the
opcode the CPU has latched. Nothing here says the walked ones ran.

What an instruction is differs by machine and is given by the caller: `words(opcode)`, its length in 16-bit words, and `stops(opcode)`, true for an opcode that never becomes native
code there (an illegal opcode, line A, line F). `observed.check_sample` keeps an instruction inside the machine's apertures. `whole`: stop at an instruction the window cuts (the
Amiga keeps the cut words, as it always has).
"""
from __future__ import annotations

from typing import Callable


def walk_windows(records: list, *, observed, words: Callable[[int], int], stops: Callable[[int], bool], whole: bool = False) -> tuple[list, list]:
    """(started, walked): the (pc, words in hex) of the instruction each window starts with, and of those a walk through the rest finds, the started ones left out of walked."""
    started: dict[tuple[int, int], str] = {}
    walked: dict[tuple[int, int], str] = {}
    for pc, data in records:
        at = 0
        while at + 2 <= len(data):
            opcode = data[at] << 8 | data[at + 1]
            if stops(opcode):
                break
            size = 2 * words(opcode)
            if whole and at + size > len(data):
                break
            text = data[at:at + size].hex()
            text = text[:len(text) // 4 * 4]
            try:
                observed.check_sample(pc + at, text)
            except ValueError:
                break
            (started if at == 0 else walked).setdefault((pc + at, opcode), text)
            at += size
    return (sorted((pc, text) for (pc, _), text in started.items()),
            sorted((key[0], text) for key, text in walked.items() if key not in started))


# ------------------------------------------------------------------------------------------------ the sweep over images of memory
# Beyond a record, code the game loaded or unpacked after the conversion's routes ended is reached from what the routes did run: images of memory taken at the routes' end are walked
# from the observed instructions, following branches and what falls through. What an image holds is not proof: a swept instruction is compiled with the same guard on the latched opcode and
# is counted apart when it runs.

def static_target(pc: int, words: list) -> int | None:
    """The address a 68000 instruction names without reading a register: Bcc, BRA, BSR (8- and 16-bit displacement), DBcc, and JMP or JSR with (xxx).W, (xxx).L or (d16,PC). A guess for a
    chain only: the pc is still compared at run time. None for anything else, or when the words given do not hold the extension it needs."""
    opcode = words[0]
    if opcode & 0xf000 == 0x6000:
        displacement = opcode & 0xff
        if displacement == 0:
            return pc + 2 + _signed(words[1], 16) if len(words) > 1 else None
        return pc + 2 + _signed(displacement, 8) if displacement != 0xff else None
    if opcode & 0xf0f8 == 0x50c8:
        return pc + 2 + _signed(words[1], 16) if len(words) > 1 else None
    if opcode & 0xff80 == 0x4e80:        # JSR 4e80-4ebf, JMP 4ec0-4eff
        mode = opcode & 0x3f
        if mode == 0x38 and len(words) > 1:
            return _signed(words[1], 16)
        if mode == 0x39 and len(words) > 2:
            return words[1] << 16 | words[2]
        if mode == 0x3a and len(words) > 1:
            return pc + 2 + _signed(words[1], 16)
    return None


def falls_through(opcode: int) -> bool:
    """False after the instructions that never go on to the next one: BRA, JMP, RTS, RTE, RTR, STOP and ILLEGAL."""
    return not (opcode & 0xff00 == 0x6000 or opcode & 0xffc0 == 0x4ec0 or opcode in (0x4e75, 0x4e73, 0x4e77, 0x4e72, 0x4afc))


def _signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def _word(image: list, address: int) -> int | None:
    for start, data in image:
        at = address - start
        if 0 <= at and at + 1 < len(data):
            return data[at] << 8 | data[at + 1]
    return None


def sweep_images(samples: list, images: list, *, observed, words: Callable[[int], int], stops: Callable[[int], bool], target: Callable[[int, list], int | None],
                 falls: Callable[[int], bool], fill: bool = False, page_bits: int = 12, limit: int, known=(), fill_below: int | None = None) -> tuple[list, dict]:
    """(found, info): the (pc, words in hex) of the instructions reached from the observed `samples` ((pc, words in hex) each) over `images` (each a list of (start address, bytes) regions,
    in the order of the routes: the first image that reaches an instruction keeps it), and not themselves in `samples` or `known`.

    A root is an observed instruction an image still holds as it was observed (same opcode at that pc); the others are stale and start nothing. From a root the walk follows
    `target(pc, words)` and, when `falls(opcode)`, the next instruction; odd addresses are dropped, `observed.check_sample` keeps the machine's apertures, `stops(opcode)` ends a path
    (an opcode that never becomes native code). `fill`: then, in every 4 KiB page (`page_bits`) below `fill_below` where code was observed, every even address that holds an opcode that
    does not stop. Bounded by `limit` instructions found: info says if the walk was cut (`capped`) and how much was queued (`left_at_cap`). Deterministic: sorted samples, images in order,
    first in first out. info: images, roots, stale_roots, reached, added, added_by_fill, limit, capped, left_at_cap."""
    seen = {(pc, int(text[:4], 16)) for pc, text in samples} | {(pc, int(text[:4], 16)) for pc, text in known}
    found: dict[tuple[int, int], str] = {}
    reached: set[tuple[int, int]] = set()
    info = {'images': len(images), 'roots': 0, 'stale_roots': 0, 'reached': 0, 'added': 0, 'added_by_fill': 0, 'limit': limit, 'capped': False, 'left_at_cap': 0}
    by_address = sorted(set(samples))
    pages = sorted({pc >> page_bits for pc, _ in by_address if fill_below is None or pc < fill_below})
    from_fill = 0
    for image in images:
        def read(address):
            return _word(image, address)

        def add(pc):
            """The words of an instruction an image holds at this address, recorded unless it is native already; None when it is not one."""
            opcode = read(pc)
            if opcode is None or stops(opcode):
                return None
            parts = [read(pc + 2 * n) for n in range(max(1, words(opcode)))]
            if None in parts:
                return None
            text = ''.join(f'{part:04x}' for part in parts)
            try:
                observed.check_sample(pc, text)
            except ValueError:
                return None
            reached.add((pc, opcode))
            if (pc, opcode) not in seen:
                found.setdefault((pc, opcode), text)
            return parts
        visited: set[int] = set()
        queue: list[int] = []

        def follow(pc, parts):
            place = target(pc, parts)
            places = [] if place is None else [place & 0xffffff]
            if falls(parts[0]):
                places.append((pc + 2 * len(parts)) & 0xffffff)
            queue.extend(place for place in places if not place & 1)
        for pc, text in by_address:
            if read(pc) == int(text[:4], 16):
                info['roots'] += 1
                follow(pc, [int(text[n:n + 4], 16) for n in range(0, len(text) - 3, 4)])
            else:
                info['stale_roots'] += 1
        position = 0
        while position < len(queue):
            if len(found) >= limit:
                left = len({place for place in queue[position:] if place not in visited})
                info['capped'] |= left > 0
                info['left_at_cap'] += left
                break
            pc = queue[position]
            position += 1
            if pc in visited:
                continue
            visited.add(pc)
            parts = add(pc)
            if parts is not None:
                follow(pc, parts)
        if fill:
            for page in pages:
                for pc in range(page << page_bits, (page + 1) << page_bits, 2):
                    if len(found) >= limit:
                        info['capped'] = True
                        info['left_at_cap'] += ((page + 1) << page_bits) - pc >> 1
                        break
                    before = len(found)
                    add(pc)
                    from_fill += len(found) - before
                if len(found) >= limit:
                    break
    info.update(reached=len(reached), added=len(found), added_by_fill=from_fill)
    return sorted((pc, text) for (pc, _), text in found.items()), info
