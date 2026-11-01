"""Evidence about the delivered Game Boy file: the liveness of each probe (gate G8) and the packed replay (gate G5).

Both come from the shared module `delivery_evidence`. What is the machine's own here is how a trace line is read (the per-frame
file `--frame-trace` of native/gb_frame_trace.h), which route must move, and what a replay is: the upstream's lockstep comparison
of the generated code with the reference interpreter (`--differential`), run on the compressed copy of the build with the same
scripts and frame counts as the comparison that made the reference, and judged by the same verdict line.

Nothing here says anything about hardware fidelity, about how deep a route goes into the game or about latency.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Callable

from .core import ConversionError
from .delivery_evidence import (LIVENESS_KEYS, DeliveredFile, FrameRow, deliver_packed, liveness_summary, replay_packed,
                                report_fields, require_moving_picture)

# The Game Boy writes all nine common keys of the liveness record under their common names (`final_checks[].liveness`).
LIVENESS_NAMES = {key: key for key in LIVENESS_KEYS}

# The one route that must show a moving picture: the richest one (menu, movement and buttons). The others may show a still
# picture when a game waits for a key or a button that their script does not give.
MAIN_ROUTE = 'varied'


def read_frame_rows(trace: Path) -> list[FrameRow]:
    """The rows of a `--frame-trace` file, in frame order. A sound block is audible when it holds a non-zero sample."""
    rows = []
    with Path(trace).open(newline='', encoding='ascii') as handle:
        for line in csv.DictReader(handle):
            rows.append(FrameRow(int(line['frame']), line['picture'], line['sound'], int(line['nonzero_samples']) > 0,
                                 line['ram'], line['pc']))
    return rows


def liveness_record(trace: Path) -> dict:
    """The liveness record of one probe, as the report keeps it."""
    return report_fields(liveness_summary(read_frame_rows(trace)), LIVENESS_NAMES)


def require_moving_main_route(final_checks: list[dict]) -> None:
    """Refuse a conversion whose main route never changed its picture; the other routes are only reported."""
    for check in final_checks:
        if check.get('scenario') == MAIN_ROUTE and check.get('liveness') is not None:
            require_moving_picture(check['liveness'], lambda check=check: ConversionError(
                f"Game Boy route '{MAIN_ROUTE}' never changed its picture in {check['liveness']['frames']} frames: "
                "the game is stuck or the route never started."))


def replay_delivered(executable: Path, project: Path, comparisons: list, references: dict[str, str],
                     compare: Callable[..., str], emit: Callable[[str], None], workers: int = 1) -> DeliveredFile:
    """Replay the compressed copy of the build on every comparison route and require the verdict of the reference.

    `comparisons` are the (scenario, frames) pairs of the lockstep comparison, `references` maps a scenario name to the
    verdict line its comparison of the build gave, `compare(executable, project, frames, scenario, tag)` runs one comparison
    and returns the verdict line."""
    packed = project / ('packed-game.exe' if os.name == 'nt' else 'packed-game')
    delivered = deliver_packed(executable, packed, 'Game Boy', emit)

    def replay(item):
        scenario, frames = item
        return compare(delivered.path, project, frames, scenario, 'packed')

    replay_packed(delivered, comparisons, replay,
                  same=lambda item, verdict: verdict == references[item[0].name],
                  mismatch=lambda item: ConversionError(
                      f"The compressed Game Boy executable differs from the reference on route '{item[0].name}'."),
                  workers=workers)
    return delivered
