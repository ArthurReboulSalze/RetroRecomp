"""Evidence about the delivered Game Boy file: the liveness of each probe (gate G8) and the packed replay (gate G5).

Both come from the shared module `delivery_evidence`. What is the machine's own here is how a trace line is read (the per-frame
file `--frame-trace` of native/gb_frame_trace.h), which route must move, and what a replay is: the upstream's lockstep comparison
of the generated code with the reference interpreter (`--differential`), run on the compressed copy of the build with the same
scripts and frame counts as the comparison that made the reference, and judged by the same verdict line.

The states of the delivered file (gate G6) are here too: a state taken in one process must continue the game in a fresh one, and a
damaged or missing state must be refused. They are checked on the same compressed copy.

Nothing here says anything about hardware fidelity, about how deep a route goes into the game or about latency.
"""
from __future__ import annotations

import csv
import json
import os
import shutil
import struct
import subprocess
import tempfile
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


# ---------------------------------------------------------------- states (gate G6)

# The start of the runtime's state file (GBSavestateFileHeader in gbrt.c): magic, version, ROM hash, ROM size, then the size of the
# battery RAM and of the other memories that follow. The load reads the whole file into buffers and checks all of this before it
# touches the running game.
STATE_HEADER = struct.Struct('<IIQII')
STATE_FRAMES = (60, 60)          # frames before the state is taken, and frames run after it is loaded
STATE_TIMEOUT = 300
CUT_STATES = ('empty', 'cut inside the header', 'cut inside the body', 'one byte short')


def launch(game: Path, folder: Path, *args) -> tuple[int, str]:
    """One headless run of a delivered file in `folder`: the exit code and what it printed.

    The data folder beside the file is emptied first: a game with battery RAM writes its save when it ends, and the next run of the
    same folder would start from it, so that two runs meant to be the same would not begin in the same state."""
    shutil.rmtree(folder / 'datas', ignore_errors=True)
    environment = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    result = subprocess.run([str(game), '--headless', *map(str, args)], cwd=folder, env=environment, capture_output=True,
                            text=True, timeout=STATE_TIMEOUT)
    return result.returncode, result.stdout + result.stderr


def dump_run(game: Path, folder: Path, tag: str, frames: int, *args) -> tuple[int, str, dict | None]:
    """`launch` with `--limit-frames` and `--dump-state`: the exit code, the output and the state dump (None when none was written)."""
    path = folder / f'dump-{tag}.json'
    path.unlink(missing_ok=True)
    code, output = launch(game, folder, '--limit-frames', frames, '--dump-state', path, *args)
    return code, output, json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def dump_differences(left: dict, right: dict) -> list[str]:
    """The names of the dump fields that differ."""
    return [key for key in sorted(set(left) | set(right)) if left.get(key) != right.get(key)]


def damaged_states(state: bytes) -> dict[str, bytes]:
    """Damaged copies of a state file, by what is wrong with them: every one must be refused."""
    cases = {'empty': state[:0], 'cut inside the header': state[:10], 'cut inside the body': state[:len(state) // 2],
             'one byte short': state[:-1], 'not a state': b'this is not a state file\n' * 3000}
    if len(state) >= STATE_HEADER.size:
        fields = STATE_HEADER.unpack_from(state, 0)
        for label, index, change in (('wrong magic', 0, 1), ('wrong version', 1, 1), ('another ROM', 2, 0x100),
                                     ('wrong ROM size', 3, 16), ('wrong memory size', 4, 8)):
            changed = list(fields)
            changed[index] = changed[index] ^ change if index in (0, 2) else changed[index] + change
            cases[label] = STATE_HEADER.pack(*changed) + state[STATE_HEADER.size:]
    return cases


def state_checks(delivered: Path, scratch: Path, emit: Callable[[str], None], frames: int = STATE_FRAMES[0],
                 more: int = STATE_FRAMES[1]) -> dict:
    """Fresh-process states of the delivered file, in an empty folder so that no battery file of an earlier run is read.

    A run of `frames` + `more` frames is dumped; a run of `frames` frames saves a state; a fresh process loads it, runs `more`
    frames and must give the same dump (registers, cycles, work and high RAM, LY and PPU mode). Every damaged copy of the
    state and a state that does not exist must be refused (exit 1) and create nothing. Returns the `game_states` fields:
    `fresh_process_verified` and `validation`, with `problems` naming what failed (empty when nothing did). The picture and the
    sound are not part of this comparison, the F8 and F9 keys are not driven, and a changed byte inside a state of the right
    length is not detected (the file has no checksum)."""
    scratch.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='states-', dir=scratch))
    problems: list[str] = []
    try:
        game = folder / delivered.name
        shutil.copy2(delivered, game)
        emit('Game Boy: checking the quick state in fresh processes.')
        state = folder / 'one.state'
        _, _, whole = dump_run(game, folder, 'continuous', frames + more)
        code, _, early = dump_run(game, folder, 'first', frames, '--save-state-file', state)
        saved = state.read_bytes() if state.is_file() else b''
        if code or not saved or not whole or not early:
            problems.append('the state could not be saved')
        else:
            code, output, resumed = dump_run(game, folder, 'resumed', more, '--load-state-file', state)
            if code or resumed is None or 'Loaded execution state' not in output:
                problems.append('a fresh process could not load the state')
            else:
                wrong = dump_differences(resumed, whole)
                if wrong:
                    problems.append(f'the dump after the load differs from a continuous run in: {", ".join(wrong)}')
                if not dump_differences(early, whole):
                    problems.append('the game did not move between the state and the end of the run: nothing was proven')
        refused = {}
        for label, data in damaged_states(saved).items():
            damaged = folder / 'damaged.state'
            damaged.write_bytes(data)
            code, output, snapshot = dump_run(game, folder, 'damaged', more, '--load-state-file', damaged)
            refused[label] = code != 0 and snapshot is None and 'Failed to load execution state' in output \
                and damaged.read_bytes() == data and not (folder / 'datas').exists()       # a refused state creates nothing
            if not refused[label]:
                problems.append(f'a state with the defect "{label}" was not refused')
        missing = folder / 'nowhere' / 'none.state'
        code, _, snapshot = dump_run(game, folder, 'missing', more, '--load-state-file', missing)
        read_only = code != 0 and snapshot is None and not missing.parent.exists() and not (folder / 'datas').exists()
        if not read_only:
            problems.append('loading a state that does not exist was not refused cleanly')
        for problem in problems:
            emit(f'Game Boy states: {problem}.')
        return {'fresh_process_verified': not problems,
                'validation': {'frames_before_state': frames, 'frames_after_load': more, 'state_bytes': len(saved),
                               'compared': 'registers, cycles, work RAM, high RAM, LY and PPU mode',
                               'invalid_states_tried': len(refused), 'invalid_states_rejected': sum(refused.values()),
                               'truncated_state_rejected': bool(refused) and all(refused.get(label) for label in CUT_STATES),
                               'missing_load_is_read_only': read_only, 'problems': problems}}
    finally:
        shutil.rmtree(folder, ignore_errors=True)
