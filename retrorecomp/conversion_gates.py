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
