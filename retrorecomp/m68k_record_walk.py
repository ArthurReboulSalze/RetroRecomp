"""The walk of a player's own record on a 68000 machine that keeps one (the Amiga, kind 22; the Atari ST, kind 24): one copy for both (MIT).

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
