"""What the Mega Drive conversion records about the delivered file: liveness (gate G8) and the packed replay (gate G5).

The shared steps are `delivery_evidence` (docs/QUALIFICATION.md, "Shared evidence helper"); this module is what is the Mega
Drive's: how a line of the 16-bit host's `--trace` is read, which report keys the numbers go into, which route must show a
moving picture, and the text of the refusals. Nothing here runs a game itself: `console16.convert16` hands in the callback
that starts the delivered file on a route.

The trace (`native/console16_main.c`, `--trace FILE`) has one line per frame, with a header:
`frame,frame_hash,native,interpreted,audio_hash,pc,sr,sp,z80_pc,busreq,reset_off,fm_nonzero,psg_nonzero`. A frame is audible
when the FM or the PSG produced a non-zero sample in it (`fm_nonzero + psg_nonzero`). A column the file does not have gives
None to the record, never 0.

Only the `play` route must show a moving picture: it is the route that presses the buttons. The attract route presses
none, and a game that waits for Start on a still title shows one picture on it; the long and authored routes may sit in a
menu. A frozen `play` route means the game never started or is stuck. The record is evidence that the picture and the sound
change on a route; it says nothing about what the picture shows or how far into the game the route goes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterator

from .core import ConversionError
from .delivery_evidence import (FrameRow, deliver_packed, liveness_summary, replay_packed, report_fields,
                                require_moving_picture)

# The report keys of a route's liveness, from the common record of delivery_evidence.
LIVENESS_FIELDS = {'frames': 'frames', 'distinct_pictures': 'distinct_pictures', 'picture_changes': 'picture_changes',
                   'last_picture_change_frame': 'last_picture_change_frame', 'audible_frames': 'audible_frames',
                   'last_audible_frame': 'last_audible_frame', 'distinct_sound_blocks': 'distinct_sound_blocks',
                   'distinct_program_counters': 'distinct_program_counters'}
MAIN_ROUTE = 'play'
TRACE_COLUMNS = ('frame', 'frame_hash', 'audio_hash', 'pc', 'fm_nonzero', 'psg_nonzero')


def trace_rows(trace: Path) -> Iterator[FrameRow]:
    """The per-frame rows of a route's trace, for `delivery_evidence.liveness_summary`."""
    lines = Path(trace).read_text(encoding='ascii').splitlines()
    if not lines:
        return
    header = lines[0].split(',')
    column = {name: header.index(name) for name in TRACE_COLUMNS if name in header}
    for name in ('frame', 'frame_hash'):
        if name not in column:
            raise ConversionError(f'Mega Drive trace {Path(trace).name} has no {name} column.')
    for line in lines[1:]:
        fields = line.split(',')
        if len(fields) != len(header) or not fields[column['frame']].isdigit():
            continue
        sound = fields[column['audio_hash']] if 'audio_hash' in column else None
        pc = fields[column['pc']] if 'pc' in column else None
        audible = None
        if 'fm_nonzero' in column and 'psg_nonzero' in column:
            audible = int(fields[column['fm_nonzero']]) + int(fields[column['psg_nonzero']]) > 0
        yield FrameRow(int(fields[column['frame']]), fields[column['frame_hash']], sound=sound, audible=audible, pc=pc)


def route_liveness(trace: Path) -> dict:
    """Picture and sound activity of one route, read from its trace (see the module text for what it does not say)."""
    return report_fields(liveness_summary(trace_rows(trace)), LIVENESS_FIELDS)


def require_main_route_moving(scenario: str, liveness: dict, directory: Path) -> None:
    """Refuse a conversion whose main (`play`) route showed a picture that never changed."""
    if scenario == MAIN_ROUTE:
        require_moving_picture(liveness, lambda: ConversionError(
            f'Mega Drive {scenario}: the picture never changed during the route; the game is stuck or never started. '
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
    delivered = deliver_packed(executable, packed, 'Mega Drive', emit)
    directory.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    def run(check: dict) -> dict:
        result = replay(packed, directory, check)
        result['liveness'] = route_liveness(directory / f"{check['scenario']}.trace.csv")
        results[check['scenario']] = result
        return result

    def same(check: dict, result: dict) -> bool:
        return not differences(result, references[check['scenario']])

    def mismatch(check: dict) -> Exception:
        fields = ', '.join(differences(results[check['scenario']], references[check['scenario']])[:6])
        return ConversionError(f"Mega Drive {check['scenario']}: the delivered (compressed) executable differs from the "
                               f'fresh reference ({fields}). Previous export preserved; see {directory}.')

    replay_packed(delivered, checks, run, same=same, mismatch=mismatch)
    for check in checks:
        require_main_route_moving(check['scenario'], results[check['scenario']]['liveness'], directory)
    return delivered, results
