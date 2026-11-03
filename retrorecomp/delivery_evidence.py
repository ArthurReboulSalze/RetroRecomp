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

Unpacked fallback of the packed replay. A compressed copy can fail on the system that converts (a Linux X68000 game whose
build runs and passes `upx -t`, but whose compressed copy stops at start). When the replay of a copy that really was
compressed fails (the machine's replay raises, or the comparison does not hold), `replay_packed` keeps the compressed copy
aside (`<path>.upx-failed`), copies the build as built over the delivered path and replays every route on it. A failure is
blamed on the compression only when it is reproduced: once the build has passed every route, the compressed copy is put back
and replayed again on the first route that failed. If it fails again, the build is delivered unpacked
(`DeliveredFile.confirm_unpacked`: the notice, the digest of the build, the registration with `packing.refuse_compression`, so
that the publication, which packs the same build again, leaves it unpacked and `packing_record` reports `unpacked_reason`);
that route is replayed once more on the build so that its outputs are the build's, and `packed_reference_match` is true for
the file actually delivered. If the compressed copy passes the second time, the failure was not reproducible (a flaky host, a
race): the first error is raised with a note saying so, nothing is delivered and nothing is registered. If the build fails
too, the first error is raised, chained to the second. Nothing is retried when the file was not compressed (the option
"Compress games" is off, or UPX left the build as it was) or when the user stopped the conversion. A file that has not passed
every route is never delivered. A genuine native mismatch costs one more replay of every route before the conversion is
refused, as before.
`tests/test_delivery_evidence.py` pins the decisions with synthetic rows; the conversions' recorded behaviour is pinned by
`tests/test_x68000_common.py` (golden), `tests/test_cps1_liveness.py` and `tests/test_conversion_gates.py` (golden).
"""
from __future__ import annotations

from pathlib import Path
import shutil
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


def _reason(error: BaseException) -> str:
    """The first line of an error, short, without its final full stop: what the log and the notice say went wrong."""
    lines = str(error).strip().splitlines()
    return (lines[0].strip() if lines else '')[:160].rstrip('. ') or type(error).__name__


class DeliveredFile:
    """The file the player receives, as the conversion compared it: a compressed copy of the build.

    `path` is the copy, `notice` is packing's `{'notice': reason}` when it stays unpacked (a large Linux game UPX cannot
    pack and test is delivered as built), `sha256` is the digest of the copy taken before any replay, so the report names
    the bytes that were replayed. `routes` and `matched` are set by `replay_packed`.

    `build` is the executable exactly as built (the file `deliver_packed` copied); with it, a compressed copy that fails
    its replay twice can be replaced by the build (`keep_compressed_aside` and `confirm_unpacked`, called by
    `replay_packed`). `label` and `emit` say it in the conversion log. Without `build` there is nothing to fall back to
    and a failed replay fails the conversion."""

    # The top-level report keys `report_fields` writes (tests/test_report_writers.py reads the writers' report keys).
    REPORT_KEYS = ('packed_candidate_sha256',)

    def __init__(self, path: Path, notice: dict | None, sha256: str, *, build: Path | None = None, label: str = '',
                 emit: Callable[[str], None] | None = None):
        self.path, self.notice, self.sha256 = Path(path), notice, sha256
        self.build = Path(build) if build is not None else None
        self.label, self.emit = label, emit
        self.routes: tuple = ()
        self.matched = False

    @property
    def kind(self) -> str:
        """'packed' normally, 'unpacked' when the copy is the build as it is."""
        return 'unpacked' if self.notice else 'packed'

    @property
    def aside(self) -> Path:
        """Where the compressed copy waits while the build takes its place (`<path>.upx-failed`)."""
        return self.path.with_name(self.path.name + '.upx-failed')

    def keep_compressed_aside(self, error: BaseException) -> bool:
        """Put the build where the compressed copy was, keeping that copy aside; False when there is no such copy.

        Only a copy that really was compressed (`kind` 'packed') and whose build is known is replaced: the compressed copy
        is kept in `aside`, the build is copied over `path` (callbacks that captured the path keep working) and one line says
        that the replay goes on with the unpacked build. Nothing is claimed yet: the notice, the digest and the registration
        with packing wait for `confirm_unpacked`, after the compression was shown to be at fault. A copy that cannot be moved
        (an OSError) is not a fallback: False, the failure stands."""
        if self.kind != 'packed' or self.build is None:
            return False
        try:
            shutil.copy2(self.path, self.aside)
            shutil.copy2(self.build, self.path)
        except OSError:
            self.restore_compressed()
            self.drop_aside()
            return False        # the copy cannot be replaced (still in use?): the original failure stands
        self.say(f'the compressed copy failed its replay on this system ({_reason(error)}); replaying the unpacked build '
                 'instead.')
        return True

    def use_build(self) -> None:
        """The build as built is the delivered path's content."""
        shutil.copy2(self.build, self.path)

    def restore_compressed(self) -> None:
        """The compressed copy kept aside is the delivered path's content again (best effort; nothing aside, nothing done)."""
        try:
            if self.aside.is_file():
                shutil.copy2(self.aside, self.path)
        except OSError:
            pass

    def drop_aside(self) -> None:
        """Delete the compressed copy kept aside."""
        self.aside.unlink(missing_ok=True)

    def say(self, text: str) -> None:
        """One line of the conversion log, in this machine's name."""
        if self.emit is not None:
            self.emit(f'{self.label or "The delivered file"}: {text}')

    def confirm_unpacked(self, error: BaseException) -> None:
        """The compressed copy failed its replay twice and the build passed every route: deliver the build, unpacked.

        The notice and the digest are the build's, the build is registered with packing so that the publication leaves it
        unpacked too (`packing_record` then reports `unpacked_reason`), and the match is withdrawn until `replay_packed`
        records it for the unpacked file. This is the only place that registers a refusal."""
        from .library import file_sha256
        from .packing import UPX_VERSION, refuse_compression
        text = (f'The compressed copy (UPX {UPX_VERSION}) did not replay correctly on this system, twice '
                f'({_reason(error)}). It is published unpacked, exactly as built and validated: a larger file, '
                'the same program.')
        self.sha256 = file_sha256(self.path)
        refuse_compression(self.sha256, text)
        self.notice, self.routes, self.matched = {'notice': text}, (), False

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
    return DeliveredFile(packed, notice, file_sha256(packed), build=executable, label=label, emit=emit)


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
    `packed_reference_match`.

    When the replay of a copy that really was compressed fails (the callback raises, or `same` does not hold on a route),
    the compressed copy is kept aside, the build as built takes its place and every route is replayed again on it, through
    the same callback: the callback must start `delivered.path` (or the path it was given, which is the same file) every
    time and must not keep the first attempt's copy. If the build passes every route, the compressed copy is put back and
    replayed once more on the first route that failed. Only if it fails again is the compression blamed: the build is
    delivered unpacked (`DeliveredFile.confirm_unpacked`), the other results are those of the unpacked replays, and the
    outputs of that route are those of one more replay of the build. If the compressed copy passes this time, the failure
    cannot be reproduced and is not blamed on the compression: the first error is raised with a note saying so, nothing
    is registered and the compressed copy stays the delivered path. If the build fails too, the first error is raised,
    chained to the second. A file that has not passed every route is never delivered. A user stop (`StopRequested`) is
    never retried. Nothing is retried when the file was not compressed (the option "Compress games" is off, or UPX left
    the build as it was) or when the build is not known."""
    rows = list(routes)
    require(same is None or mismatch is not None, lambda: ValueError('A comparison needs the error to raise.'))
    failed: list[int] = []
    try:
        results = _replay_and_judge(rows, replay, same, mismatch, workers, failed)
    except Exception as first:
        from .core import StopRequested
        if isinstance(first, StopRequested) or not delivered.keep_compressed_aside(first):
            raise
        results = _fall_back(delivered, rows, replay, same, mismatch, workers, first, min(failed, default=0))
    delivered.record_match(rows)
    return results


def _fall_back(delivered: DeliveredFile, rows: list, replay, same, mismatch, workers: int, first: Exception,
               index: int) -> list:
    """The second half of `replay_packed`: the build replaced the compressed copy, which waits aside; `index` is the first
    route the compressed copy failed on. Returns the results to deliver, or raises (and then the compressed copy is back)."""
    from .core import StopRequested
    confirmed = False
    try:
        try:
            results = _replay_and_judge(rows, replay, same, mismatch, workers)
        except StopRequested:
            raise
        except Exception as second:
            raise first from second
        # The build passed every route. Is the compression at fault, or was the first failure a fluke? Replay the compressed
        # copy once more on the route it failed on.
        delivered.restore_compressed()
        try:
            _replay_and_judge([rows[index]], replay, same, mismatch, 1)
        except StopRequested:
            raise
        except Exception:
            pass        # it failed again: reproducible, so the fault is the compression's
        else:
            note = ('The first replay of the compressed copy failed (' + _reason(first) + ') but it passed when replayed '
                    'again on the same route, and the unpacked build passed every route: the failure could not be '
                    'reproduced (non-deterministic), so it is not blamed on the compression and nothing is delivered.')
            delivered.say(note)
            first.add_note(note)
            raise first
        delivered.use_build()
        try:
            results[index] = _replay_and_judge([rows[index]], replay, same, mismatch, 1)[0]
        except StopRequested:
            raise
        except Exception as third:
            raise first from third
        delivered.confirm_unpacked(first)
        confirmed = True
        return results
    finally:
        if not confirmed:
            delivered.restore_compressed()
        delivered.drop_aside()


def _replay_and_judge(rows: list, replay: Callable[[Any], Any], same, mismatch, workers: int,
                      failed: list | None = None) -> list:
    """One attempt of `replay_packed`: every route replayed, then each result judged by `same` when there is one.

    The positions of the routes that failed (the replay raised, or `same` did not hold) are appended to `failed`."""
    def track(item):
        try:
            return replay(item[1])
        except BaseException:
            if failed is not None:
                failed.append(item[0])
            raise
    results = replay_routes(list(enumerate(rows)), track, workers=workers)
    if same is not None:
        for index, (row, result) in enumerate(zip(rows, results)):
            if not same(row, result):
                if failed is not None:
                    failed.append(index)
                raise mismatch(row)
    return results
