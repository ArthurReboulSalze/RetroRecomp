"""What the Master System / Game Gear conversion records about the delivered file: liveness (gate G8) and the packed replay (gate G5).

The shared steps are `delivery_evidence` (docs/QUALIFICATION.md, "Shared evidence helper"); this module is what is the Sega
consoles': how a line of the runner's `--vdp-trace` is read, which report keys the numbers go into, which route must show a
moving picture, and the text of the refusals. Nothing here runs a game itself: `core.convert` hands in the callback that starts the
delivered file on a route.

The trace (`runtime_glue.c`, `--vdp-trace FILE`) has one line per frame, with a header
`frame,vram_h,cram_h,reg_h,ram_h,r8,r9,r0,r1,sp,pixels_h,psg_h,psg_nz`. The picture is the hash of the frame as it is drawn
(`pixels_h`), the sound block is the hash of the PSG's stereo samples of the frame (`psg_h`), a frame is audible when the PSG
produced a non-zero sample in it (`psg_nz`), the RAM state is `ram_h`. The Z80 program counter is not in the trace, so the record
has no `distinct_program_counters` (None, never 0). A trace without the sound columns (an old build) gives None for the sound keys.

Only the `play` route must show a moving picture: it is the route that presses the buttons. The `demo` route presses none, and a game
that waits for a button on a still title shows one picture on it. A frozen `play` route means the game never started or is stuck.
Sound keeps the rule it had: a silent route is reported (`audible_frames`, `last_audible_frame`), never refused. The record is
evidence that the picture and the sound change on a route; it says nothing about what the picture shows or how far into the game the
route goes, and nothing about hardware fidelity or latency.
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
                   'distinct_ram_states': 'distinct_ram_states'}
MAIN_ROUTE = 'play'
TRACE_COLUMNS = ('frame', 'pixels_h', 'psg_h', 'psg_nz', 'ram_h')


def trace_rows(trace: Path) -> Iterator[FrameRow]:
    """The per-frame rows of a route's trace, for `delivery_evidence.liveness_summary`."""
    lines = Path(trace).read_text(encoding='ascii').splitlines()
    if not lines:
        return
    header = lines[0].split(',')
    column = {name: header.index(name) for name in TRACE_COLUMNS if name in header}
    for name in ('frame', 'pixels_h'):
        if name not in column:
            raise ConversionError(f'Sega trace {Path(trace).name} has no {name} column.')
    for line in lines[1:]:
        fields = line.split(',')
        if len(fields) != len(header) or not fields[column['frame']].isdigit():
            continue
        sound = fields[column['psg_h']] if 'psg_h' in column else None
        audible = None
        if 'psg_nz' in column and fields[column['psg_nz']].isdigit():
            audible = int(fields[column['psg_nz']]) > 0
        ram = fields[column['ram_h']] if 'ram_h' in column else None
        yield FrameRow(int(fields[column['frame']]), fields[column['pixels_h']], sound=sound, audible=audible, ram=ram)


def route_liveness(trace: Path) -> dict:
    """Picture and sound activity of one route, read from its trace (see the module text for what it does not say)."""
    return report_fields(liveness_summary(trace_rows(trace)), LIVENESS_FIELDS)


def require_main_route_moving(scenario: str, liveness: dict, directory: Path) -> None:
    """Refuse a conversion whose main (`play`) route showed a picture that never changed."""
    if scenario == MAIN_ROUTE:
        require_moving_picture(liveness, lambda: ConversionError(
            f'Master System / Game Gear {scenario}: the picture never changed during the route; the game is stuck or never '
            f'started. Previous export preserved; see {directory}.'))


def replay_delivered(executable: Path, packed: Path, directory: Path, checks: list, references: dict,
                     replay: Callable[[Path, Path, dict], dict], differences: Callable[[dict, dict], list],
                     emit: Callable[[str], None]):
    """Compress a copy of the build as publication does, replay it on every route and compare each result with the reference of
    the same route: the fresh reference run of the banked engine, or the final pass of the same build for the "functions" engine.

    `replay(packed, directory, check)` starts the copy on the route of `check` (the same arguments as the probe that made the native
    result), writing its trace in `directory`, and returns the probe's result; `differences(result, reference)` lists the checks
    that failed (empty when equal). Returns the delivered file (`validation_fields()` and `report_fields()` may be written only once
    it matched on every route) and the replay results by route, each with its `liveness`."""
    delivered = deliver_packed(executable, packed, 'Master System / Game Gear', emit)
    directory.mkdir(parents=True, exist_ok=True)
    results: dict = {}

    def run(check: dict) -> dict:
        run_directory = directory / check['scenario']
        result = replay(packed, run_directory, check)
        result['liveness'] = route_liveness(run_directory / 'vdp.csv')
        result['directory'] = str(run_directory)
        results[check['scenario']] = result
        return result

    def same(check: dict, result: dict) -> bool:
        return not differences(result, references[check['scenario']])

    def mismatch(check: dict) -> Exception:
        fields = ', '.join(differences(results[check['scenario']], references[check['scenario']])[:6])
        return ConversionError(f"Master System / Game Gear {check['scenario']}: the delivered (compressed) executable differs from "
                               f'its reference ({fields}). Previous export preserved; see {directory}.')

    replay_packed(delivered, checks, run, same=same, mismatch=mismatch)
    for check in checks:
        require_main_route_moving(check['scenario'], results[check['scenario']]['liveness'], directory)
    return delivered, results
