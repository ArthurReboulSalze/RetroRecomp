"""What the Super Nintendo conversion records about the delivered file: liveness (gate G8) and the packed replay (gate G5).

The shared steps are `delivery_evidence` (docs/QUALIFICATION.md, "Shared evidence helper"); this module is what is the Super
Nintendo's: how a line of the 16-bit host's `--trace` is read, which report keys the numbers go into, which route must show a
moving picture, and the text of the refusals. Nothing here runs a game itself: `console16.convert16` hands in the callback
that starts the delivered file on a route. It is the counterpart of `megadrive_evidence`, for every cartridge, with or
without a coprocessor (before, only a cartridge with a counted device had a liveness check, `supernintendo.validate_device_liveness`).

The trace (`native/console16_main.c`, `--trace FILE`) has one line per frame, with a header:
`frame,frame_hash,native,interpreted,audio_hash`. The Super Nintendo host writes no program counter, so that key is None
(never 0: "no evidence"). A frame is audible when its `audio_hash` is not the hash of silence: the host folds the frame's
16-bit samples into an FNV-1a hash, and all-zero samples leave only the multiplies (`delivery_evidence.silent_sound_hash`),
so a silent frame's hash is one of a short list, by its (even) number of samples; the Neo Geo and the CPS-1 read their traces
the same way. The route's own result adds `pcm_nonzero` (non-zero samples over the whole route) and `visible_frames`.

Only the `play` route must show a moving picture: it is the route that presses the buttons. The attract route presses none,
and a game that waits for Start on a still title shows one picture on it; the long and authored routes may sit in a menu.
A frozen `play` route means the game never started or is stuck. The record is evidence that the picture and the sound change
on a route; it says nothing about what the picture shows or how far into the game the route goes.
"""
from __future__ import annotations

from functools import cache
from pathlib import Path
from typing import Callable, Iterator

from .core import ConversionError
from .delivery_evidence import (FNV_BASIS, FNV_MASK, FNV_PRIME, FrameRow, deliver_packed, liveness_summary, replay_packed,
                                report_fields, require_moving_picture)

# The report keys of a route's liveness, from the common record of delivery_evidence.
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'picture_changes': 'picture_changes',
                   'last_picture_change_frame': 'last_picture_change_frame', 'audible_frames': 'audible_frames',
                   'last_audible_frame': 'last_audible_frame', 'distinct_sound_blocks': 'distinct_sound_blocks'}
# What the route's own result adds (the probe's report): not derived from the trace.
RESULT_FIELDS = ('pcm_nonzero', 'visible_frames')
MAIN_ROUTE = 'play'
TRACE_COLUMNS = ('frame', 'frame_hash', 'audio_hash')
# A frame is 48 kHz stereo: about 1,600 samples (NTSC) or 1,920 (PAL); the table goes well past both. A silent frame of more than this many
# samples (a host that would deliver 2,048 sample pairs or more in one frame) would not be found in the table and would read as audible.
MAX_FRAME_SAMPLES = 4096


@cache
def silent_blocks() -> frozenset:
    """The sound hash (16 hex digits, as the trace writes it) of a frame of silence, for every even number of samples a frame can
    carry. The multiplies of `silent_sound_hash` are taken once in a row."""
    value, blocks = FNV_BASIS, set()
    for samples in range(MAX_FRAME_SAMPLES + 1):
        if samples % 2 == 0:
            blocks.add(f'{value:016x}')
        value = (value * FNV_PRIME) & FNV_MASK
    return frozenset(blocks)


def trace_rows(trace: Path) -> Iterator[FrameRow]:
    """The per-frame rows of a route's trace, for `delivery_evidence.liveness_summary`."""
    lines = Path(trace).read_text(encoding='ascii').splitlines()
    if not lines:
        return
    header = lines[0].split(',')
    column = {name: header.index(name) for name in TRACE_COLUMNS if name in header}
    for name in ('frame', 'frame_hash'):
        if name not in column:
            raise ConversionError(f'Super Nintendo trace {Path(trace).name} has no {name} column.')
    for line in lines[1:]:
        fields = line.split(',')
        if len(fields) != len(header) or not fields[column['frame']].isdigit():
            continue
        sound = fields[column['audio_hash']] if 'audio_hash' in column else None
        audible = None if sound is None else sound not in silent_blocks()
        yield FrameRow(int(fields[column['frame']]), fields[column['frame_hash']], sound=sound, audible=audible)


def route_liveness(trace: Path, result: dict | None = None) -> dict:
    """Picture and sound activity of one route, read from its trace and from the route's own result (see the module text for
    what it does not say). A result key the probe did not report gives None."""
    record = report_fields(liveness_summary(trace_rows(trace)), LIVENESS_FIELDS)
    result = result or {}
    record.update({key: result.get(key) for key in RESULT_FIELDS})
    return record


def require_main_route_moving(scenario: str, liveness: dict, directory: Path) -> None:
    """Refuse a conversion whose main (`play`) route showed a picture that never changed."""
    if scenario == MAIN_ROUTE:
        require_moving_picture(liveness, lambda: ConversionError(
            f'Super Nintendo {scenario}: the picture never changed during the route; the game is stuck or never started. '
            f'Previous export preserved; see {directory}.'))


def replay_delivered(executable: Path, packed: Path, directory: Path, checks: list, references: dict,
                     replay: Callable[[Path, Path, dict], dict], differences: Callable[[dict, dict], list],
                     emit: Callable[[str], None]):
    """Compress a copy of the build as publication does, replay it on every route and compare each result with the fresh
    reference of the same route.

    `replay(packed, directory, check)` starts the copy on the route of `check` (the same arguments as the probe that made
    the native result), writing its trace in `directory`, and returns the probe's result; `differences(result, reference)`
    lists the fields that differ (empty when equal). Returns the delivered file (`validation_fields()` and `report_fields()`
    may be written only once it matched on every route) and the replay results by route, each with its `liveness`."""
    delivered = deliver_packed(executable, packed, 'Super Nintendo', emit)
    directory.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    def run(check: dict) -> dict:
        result = replay(packed, directory, check)
        result['liveness'] = route_liveness(directory / f"{check['scenario']}.trace.csv", result)
        results[check['scenario']] = result
        return result

    def same(check: dict, result: dict) -> bool:
        return not differences(result, references[check['scenario']])

    def mismatch(check: dict) -> Exception:
        fields = ', '.join(differences(results[check['scenario']], references[check['scenario']])[:6])
        return ConversionError(f"Super Nintendo {check['scenario']}: the delivered (compressed) executable differs from the "
                               f'fresh reference ({fields}). Previous export preserved; see {directory}.')

    replay_packed(delivered, checks, run, same=same, mismatch=mismatch)
    for check in checks:
        require_main_route_moving(check['scenario'], results[check['scenario']]['liveness'], directory)
    return delivered, results
