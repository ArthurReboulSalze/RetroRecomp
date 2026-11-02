"""The evidence about the delivered file that every machine gives the same way: liveness (gate G8) and the packed replay (gate G5).

docs/QUALIFICATION.md names the two gates; docs/STANDARDS.md (rule 1, no third copy; rule 7, unification with identical
results) is why they live here. CPS-1, the X68000 and Neo Geo each carried their own copy of the same steps. What differs
from one machine to the next stays a parameter of the caller: how a trace line is read, how a replay is started, what a
mismatch is called and which report fields the numbers go into. Nothing here runs a game, reads a ROM or knows a machine.

Liveness (G8). The machine already writes one row per frame (a picture hash, a sound hash or an audible flag, perhaps a
RAM hash and a program counter). `liveness_summary` turns those rows into one record, the same keys for every machine;
a key the machine cannot give is None, never 0, so "no sound evidence" is not read as "silent". `frozen_route` and
`require_moving_picture` are the one rule that refuses a route whose picture never changed. The record is evidence that
the picture and the sound change on a route (and, with RAM and PC, that the machine runs on); it says nothing about what
the picture shows or how deep into the game the route goes. Which routes must move and what a silent route means (CPS-1
refuses a route with no sound on every route, the X68000 accepts and reports it) are each machine's decision.

Report fields. A machine keeps its own names in its report (`final_checks[].liveness` for CPS-1 and Neo Geo, `liveness[]` for
the X68000): `report_fields` selects and renames from the common record. The names as they stand today:

    common key                  CPS-1 and Neo Geo report key X68000 report key
    frames                      frames                       frames
    distinct_pictures           distinct_pictures            distinct_pictures
    picture_changes             picture_changes              (not reported)
    last_picture_change_frame   last_picture_change_frame    (not reported)
    audible_frames              audible_frames               (not reported; `nonzero_samples` from the replay report)
    last_audible_frame          last_audible_frame           (not reported)
    distinct_sound_blocks       (not reported)               distinct_audio_blocks
    distinct_ram_states         (not reported)               distinct_ram_states
    distinct_program_counters   (not reported)               distinct_program_counters

Frame numbers are the machine's own (CPS-1 and Neo Geo count from 1, the X68000 from 0); the record keeps them as given.
`silent_sound_hash` is the per-frame sound hash of a frame of silence, for the machines (CPS-1, Neo Geo) whose runtime hashes
each sample of a frame and write that hash in their trace: a frame is audible when its hash differs from it.

Packed replay (G5). The delivered file is a compressed copy of the build: `deliver_packed` makes that copy (the build is
never touched) and takes its SHA-256; `replay_packed` replays the copy on every route through the machine's callback and
compares each result with the fresh reference. Only a copy that was replayed and matched may say so:
`DeliveredFile.validation_fields` raises until `replay_packed` has matched every route, which keeps
`native_validation.packed_reference_match` from being written for a file nobody replayed.
`tests/test_delivery_evidence.py` pins the decisions with synthetic rows; the conversions' recorded behaviour is pinned by
`tests/test_x68000_common.py` (golden), `tests/test_cps1_liveness.py` and `tests/test_conversion_gates.py` (golden).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Hashable, Iterable, Mapping, NamedTuple

from .conversion_gates import comparison_notice, pack_candidate, require

# The per-frame sound hash of native/cps1_main.c and native/neogeo_main.c: for each sample, xor it (as uint16) then multiply.
FNV_BASIS, FNV_PRIME, FNV_MASK = 14695981039346656037, 1099511628211, (1 << 64) - 1

LIVENESS_KEYS = ('frames', 'distinct_pictures', 'picture_changes', 'last_picture_change_frame', 'audible_frames',
                 'last_audible_frame', 'distinct_sound_blocks', 'distinct_ram_states', 'distinct_program_counters')


class FrameRow(NamedTuple):
    """What a machine knows of one frame of a route, as hashes it already computes.

    `picture` is the hash of the frame's picture (or of the video state that makes it). `sound` is the hash of the
    frame's audio block, used only to count distinct blocks; `audible` says whether the frame carried a non-silent sample.
    A machine that cannot tell leaves the field None and the record says None, not zero."""
    frame: int
    picture: Hashable
    sound: Hashable | None = None
    audible: bool | None = None
    ram: Hashable | None = None
    pc: Hashable | None = None


def silent_sound_hash(samples: int) -> int:
    """The per-frame sound hash of `samples` samples that are all zero (xor with zero changes nothing, so only the multiplies)."""
    value = FNV_BASIS
    for _ in range(samples):
        value = (value * FNV_PRIME) & FNV_MASK
    return value


def liveness_summary(rows: Iterable[FrameRow]) -> dict:
    """The liveness record of one route, read from its per-frame rows (in frame order).

    A picture change is a row whose picture differs from the previous row's. Counts of distinct sound blocks, RAM states
    and program counters are None when no row carries that value; `audible_frames` and `last_audible_frame` are None
    when no row says whether it was audible. `last_*_frame` is 0 when there was no such frame."""
    pictures: set = set()
    sounds: set = set()
    rams: set = set()
    counters: set = set()
    frames = changes = last_change = audible = last_audible = 0
    previous: Any = None
    started = judged = False
    for row in rows:
        frames += 1
        pictures.add(row.picture)
        if started and row.picture != previous:
            changes += 1
            last_change = row.frame
        previous, started = row.picture, True
        if row.audible is not None:
            judged = True
            if row.audible:
                audible += 1
                last_audible = row.frame
        if row.sound is not None:
            sounds.add(row.sound)
        if row.ram is not None:
            rams.add(row.ram)
        if row.pc is not None:
            counters.add(row.pc)
    return {'frames': frames, 'distinct_pictures': len(pictures), 'picture_changes': changes,
            'last_picture_change_frame': last_change,
            'audible_frames': audible if judged else None, 'last_audible_frame': last_audible if judged else None,
            'distinct_sound_blocks': len(sounds) or None, 'distinct_ram_states': len(rams) or None,
            'distinct_program_counters': len(counters) or None}


def report_fields(summary: Mapping[str, Any], names: Mapping[str, str]) -> dict:
    """The fields a machine reports from the common record: `names` maps the machine's report key to the common key,
    in the order the machine writes them."""
    unknown = [key for key in names.values() if key not in LIVENESS_KEYS]
    if unknown:
        raise KeyError(f'Unknown liveness key: {unknown[0]}')
    return {report: summary[common] for report, common in names.items()}


def frozen_route(record: Mapping[str, Any]) -> bool:
    """Whether a route's picture never changed: one picture or none, so the game is stuck (or the route never started).

    It reads `distinct_pictures`, which every machine's liveness record carries, whatever else it reports: a route with
    no picture change has one distinct picture and the reverse holds, so this is the rule CPS-1 stated as "no picture
    change" and the X68000 as "no more than one picture"."""
    return record['distinct_pictures'] <= 1


def require_moving_picture(record: Mapping[str, Any], error: Callable[[], Exception]) -> None:
    """Raise `error()` when `frozen_route(record)`. Which routes the machine requires this of is its decision (CPS-1: every
    route; X68000: the main route, because a game that waits for a click or a key shows a still picture on the others)."""
    require(not frozen_route(record), error)


class DeliveredFile:
    """The file the player receives, as the conversion compared it: a compressed copy of the build.

    `path` is the copy, `notice` is packing's `{'notice': reason}` when it stays unpacked (a large Linux game UPX cannot
    pack and test is delivered as built), `sha256` is the digest of the copy taken before any replay, so the report names
    the bytes that were replayed. `routes` and `matched` are set by `replay_packed`."""

    # The top-level report keys `report_fields` writes (tests/test_report_writers.py reads the writers' report keys).
    REPORT_KEYS = ('packed_candidate_sha256',)

    def __init__(self, path: Path, notice: dict | None, sha256: str):
        self.path, self.notice, self.sha256 = Path(path), notice, sha256
        self.routes: tuple = ()
        self.matched = False

    @property
    def kind(self) -> str:
        """'packed' normally, 'unpacked' when the copy is the build as it is."""
        return 'unpacked' if self.notice else 'packed'

    def record_match(self, routes: Iterable) -> None:
        """Say that the copy was replayed on `routes` and matched the reference on each (`replay_packed` does it; a machine
        whose replay callback already compared, and has no use for `replay_packed`'s own comparison, calls it itself)."""
        rows = tuple(routes)
        require(bool(rows), lambda: ValueError('A packed replay needs at least one route.'))
        self.routes, self.matched = rows, True

    def validation_fields(self) -> dict:
        """The `native_validation` field: `packed_reference_match`. Refused until every route was replayed and matched."""
        if not self.matched:
            raise ValueError('The delivered file was not replayed against the reference on every route.')
        return {'packed_reference_match': True}

    def report_fields(self) -> dict:
        """The report field that names the replayed bytes: `packed_candidate_sha256`."""
        return {key: self.sha256 for key in self.REPORT_KEYS}


def deliver_packed(executable: Path, packed: Path, label: str, emit: Callable[[str], None]) -> DeliveredFile:
    """Copy the build to `packed`, compress the copy as publication does, say which file is compared with the reference
    ('<label>: comparing the compressed executable with the fresh reference.') and take the copy's SHA-256."""
    from .library import file_sha256
    notice = pack_candidate(executable, packed, emit)
    emit(comparison_notice(label, notice))
    return DeliveredFile(packed, notice, file_sha256(packed))


def same_trace(actual: Path, expected: Path) -> bool:
    """Whether two trace files hold the same bytes: the usual `same` of a packed replay (the packed run's trace against the
    fresh reference's)."""
    return Path(actual).read_bytes() == Path(expected).read_bytes()


def replay_routes(routes: Iterable, replay: Callable[[Any], Any], *, workers: int = 1) -> list:
    """Run `replay(route)` on every route and return the results in route order.

    The replays run side by side when `workers` > 1 and there is more than one route; each one runs to its end, then the
    first failure in route order is the one raised (as a sequential loop would have raised it)."""
    rows = list(routes)
    if workers <= 1 or len(rows) <= 1:
        return [replay(row) for row in rows]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix='packed-replay') as pool:
        futures = [pool.submit(replay, row) for row in rows]
        return [future.result() for future in futures]


def replay_packed(delivered: DeliveredFile, routes: Iterable, replay: Callable[[Any], Any], *,
                  same: Callable[[Any, Any], bool] | None = None, mismatch: Callable[[Any], Exception] | None = None,
                  workers: int = 1) -> list:
    """Replay the delivered file on every route (`replay_routes`), judge each result and return the results in route order.

    `replay(route)` is the machine's: it starts the delivered file on the route and returns what it keeps of the run.
    With `same`, `same(route, result)` must hold for every route, else `mismatch(route)` is raised for the first that
    fails (the machine's exception class and text); every replay has run by then. Without it, the callback compares by
    itself and raises on a difference. When every route passed, the delivered file records the routes and may claim
    `packed_reference_match`."""
    rows = list(routes)
    require(same is None or mismatch is not None, lambda: ValueError('A comparison needs the error to raise.'))
    results = replay_routes(rows, replay, workers=workers)
    if same is not None:
        for row, result in zip(rows, results):
            require(same(row, result), lambda row=row: mismatch(row))
    delivered.record_match(rows)
    return results
