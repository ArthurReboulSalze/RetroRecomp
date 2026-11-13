"""The gates that compare a built candidate with its fresh reference, shared by the converters that run them
(docs/STANDARDS.md rules 1 and 7): the packed candidate, equal traces, and the continuation of a saved state.

Neo Geo and CPS-1 each carried a copy of these steps. What differed stays a parameter: the exception raised (its class
and its text are each console's), the label of the message, what a trace is (a file or the rows of a table). Nothing
here runs a game, reads a ROM or knows a console: a gate is a decision on values the converter hands in, and the
converter keeps the order of its checks. `tests/test_conversion_gates.py` pins the decisions with values recorded
before the copies were removed.
"""
from __future__ import annotations

from pathlib import Path
import shutil
from typing import Callable, Sequence


def pack_candidate(executable: Path, packed: Path, emit: Callable[[str], None] | None) -> dict | None:
    """Copy the built `executable` to `packed` and compress that copy, as the game is delivered.

    The built file is never touched: only the copy is packed, and only the packed copy is compared with the reference.
    Returns what `compact_executable` returns: None when the copy was packed (or left as built on purpose), else
    `{'notice': reason}` when it stays unpacked.
    """
    from .packing import compact_executable
    shutil.copy2(executable, packed)
    return compact_executable(packed, emit)


def comparison_notice(label: str, notice: dict | None) -> str:
    """The line announcing the comparison of the delivered file with the reference ('Neo Geo: comparing the ...')."""
    return f'{label}: comparing the ' + ('unpacked' if notice else 'compressed') + ' executable with the fresh reference.'


def require(condition: bool, error: Callable[[], Exception]) -> None:
    """Raise `error()` unless `condition` holds: the one way a gate says no."""
    if not condition:
        raise error()


def require_equal(actual, expected, error: Callable[[], Exception]) -> None:
    """The shared 'traces equal or raise' step: `actual` (rows, bytes, hashes) must equal `expected`."""
    require(actual == expected, error)


def require_same_file(actual: Path, expected: Path, error: Callable[[], Exception]) -> None:
    """Two trace files must hold the same bytes."""
    require_equal(Path(actual).read_bytes(), Path(expected).read_bytes(), error)


def first_difference(left: Sequence, right: Sequence) -> int | None:
    """The position of the first row where the two differ; the length of the shorter when one is a prefix of the other;
    None when they are equal."""
    for index, (one, other) in enumerate(zip(left, right)):
        if one != other:
            return index
    return None if len(left) == len(right) else min(len(left), len(right))


def continuation_difference(timeline: Sequence, resumed: Sequence, start: int, length: int) -> int | None:
    """Where a process that loaded a saved state strays from the timeline it was saved from, or None if it does not.

    `timeline` is the uninterrupted run, `resumed` the rows of the fresh process that loaded the state saved at row
    `start`; it must continue the timeline for `length` rows. The result is the first differing row, counted from
    `start` (a resumed run of another length differs where the shorter one ends).
    """
    return first_difference(timeline[start:start + length], resumed)


def check_quick_states(folder: Path, state: Path, *, machine: str, route: str, at: int, settle: int,
                       continued: Callable[[], tuple[Sequence, Sequence]], refused: Callable[[Path], bool],
                       damaged: Callable[[bytes], dict], error: Callable[[str], Exception]) -> dict:
    """The fresh-process check of quick states (G6), lifted from the PC Engine on 12 November 2026 (STANDARDS rule 1).

    `continued()` saves `state` at row `at` of `route` in one process and loads it in a new one; it returns (the
    uninterrupted rows, the rows of the process that loaded it), which must agree for `settle` rows. Then every damaged copy
    of the state (`damaged(bytes)`: label -> bytes, the machine's own list of offsets) is written in `folder` and must be
    refused (`refused(path)`: the game's own exit code) and left byte for byte as it was; a missing state is refused and
    creates nothing. `error(text)` makes the machine's exception, whose texts begin with `machine`."""
    timeline, resumed = continued()
    require(continuation_difference(timeline, resumed, at, settle) is None,
            lambda: error(f'{machine} F9 continuation differs from its saved timeline; existing export preserved.'))
    original = state.read_bytes()
    variants = damaged(original)
    for label, data in variants.items():
        invalid = folder / f'invalid-{label}{state.suffix}'
        invalid.write_bytes(data)
        require(refused(invalid), lambda: error(f'{machine} accepted a damaged quick state ({label}).'))
        require(invalid.read_bytes() == data, lambda: error(f'{machine} rewrote a quick state it refused ({label}).'))
    missing = folder / f'missing{state.suffix}'
    missing.unlink(missing_ok=True)
    require(refused(missing), lambda: error(f'{machine} accepted a missing quick state.'))
    require(not missing.exists(), lambda: error('Loading a missing quick state created a file.'))
    return {'route': route, 'saved_at': at, 'continued_frames': settle, 'fresh_process_match': True,
            'truncated_state_rejected': True, 'damaged_states_refused': sorted(variants),
            'missing_state_creates_nothing': True, 'state_bytes': len(original)}


# ------------------------------------------------------------------ cartridge save files (native/cart_save.c)

CART_SAVE_HEADER = 112      # cart_save.c: magic, version 1, size, the hash, identity words, the ROM's SHA-256 in hex at 40


def fnv64(data: bytes) -> int:
    """FNV-1a 64 of a save's memory, as cart_save.c stores it in the header."""
    value = 14695981039346656037
    for byte in data:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value


def cart_save_file(magic: bytes, memory: bytes, rom_sha256: str) -> bytes:
    """A cartridge save file as cart_save.c writes it (hash at offset 16, no identity word): magic, version 1, size, FNV-1a of
    the memory, reserved, the ROM's SHA-256 in hex, reserved, the memory. Lifted from the PC Engine on 13 November 2026."""
    header = bytearray(CART_SAVE_HEADER)
    header[:8] = magic
    header[8:12] = (1).to_bytes(4, 'little')
    header[12:16] = len(memory).to_bytes(4, 'little')
    header[16:24] = fnv64(memory).to_bytes(8, 'little')
    header[40:104] = rom_sha256.encode('ascii')
    return bytes(header) + memory


def damaged_cart_saves(good: bytes) -> dict[str, bytes]:
    """Files a game cannot use, by what is wrong with them (cart_save.c): each must be set aside whole, and the game must start
    with its blank memory."""
    def flipped(offset: int) -> bytes:
        data = bytearray(good)
        data[offset] ^= 0x80
        return bytes(data)
    return {'empty': b'', 'header-cut': good[:40], 'one-byte-short': good[:-1], 'one-byte-long': good + b'\0',
            'raw-memory': good[CART_SAVE_HEADER:], 'magic': flipped(0), 'version': flipped(8), 'size': flipped(12),
            'hash': flipped(16), 'other-card': flipped(40), 'memory': flipped(len(good) - 1)}
