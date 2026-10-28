"""Where the time of a conversion goes: one recorder, one vocabulary of phases, the same for every console.

``batch._convert_one`` starts a recorder for each game (``start``), the converters mark the work they do
(``phase`` around a step, ``begin_pass`` and ``end_passes`` around their learning loop) and the batch writes
the figures into the report as ``timings`` and into the log as one line (``describe``). Nothing here starts a
process or changes what is generated or checked; without a recorder (a converter called directly, a unit
test) every call does nothing.

The phases are disjoint and measured in wall-clock seconds (``time.perf_counter``): while a phase runs,
the time belongs to it alone, and a phase opened inside another takes its time from it. What is not inside a
named phase is ``other`` (reading the ROM, artwork, dependency checks, hashing, writing the report), so the
phases add up to ``total`` within the rounding (0.1 s each).

The vocabulary, in the order a conversion meets it:

* ``code_generation``: the translators and the analysis that write the C sources of the game.
* ``compile``: the C build of the player, configure and build together. The build is one CMake target that
  compiles the host and runtime files and the game's generated code side by side, so the two are not told
  apart (a build that reuses unchanged objects is simply shorter).
* ``profile_training``: the short native run that guides the compiler (Mega Drive, Super Nintendo, NES).
* ``native_runs``: the generated executable played on the tested routes (coverage and learning runs,
  strict-mode runs).
* ``reference_runs``: the same routes on the reference interpreter and the comparison with it. A converter
  whose single run does both (a differential run, Game Boy's instruction-by-instruction comparison, CPS-1's
  parallel reference and native replays) says so in docs/COMPILATION_LIBRARY.md.
* ``packed_replays``: the delivered, compressed executable replayed against the reference (Neo Geo, CPS-1).
* ``state_checks``: F8/F9 in fresh processes. ``save_checks``: ordinary saves (Neo Geo).
* ``packing``: UPX, wherever the packer runs (during the conversion or at publication).
* ``publication``: placing the executable in the export folder, without its packing.
* ``discovery``: the learning passes after the first, whole (generation, build, runs and comparisons of each).
  0.0 when the game was converted in one pass, which is what a quick check does.
* ``failed_quick_attempt``: the time of a quick check that did not pass, before the full conversion that
  followed it.
* ``reference_and_native_runs``: CPS-1 only, its first pass, where the reference and the native replays share
  one pool and cannot be told apart.
* ``other`` and ``total``: see above. ``total`` is the wall time of the game from the start of its conversion
  to the last report written (before the cleanup of its build folder).
"""
from __future__ import annotations

import contextlib
import contextvars
import functools
import threading
import time

DISCOVERY = 'discovery'
OTHER = 'other'
TOTAL = 'total'
FAILED_QUICK = 'failed_quick_attempt'
PRECISION = 1   # decimals: 0.1 s
# The order the figures are written and told in, the same for every console; a phase not listed follows them.
ORDER = (FAILED_QUICK, 'code_generation', 'compile', 'profile_training', 'native_runs', 'reference_runs',
         'reference_and_native_runs', 'packed_replays', 'state_checks', 'save_checks', 'packing', 'publication',
         DISCOVERY)

_CURRENT: contextvars.ContextVar = contextvars.ContextVar('retro_recomp_timings', default=None)


class Recorder:
    """The time of one game's conversion, by phase.

    It belongs to the thread that created it, the one that converts the game: a call from another thread (a pool
    worker of the converter, which Python 3.14 gives a copy of the context) is ignored, so concurrent helpers can
    neither disturb the figures nor be counted twice; the converter times the pool from its own thread."""

    def __init__(self, clock=None):
        self._clock = clock or time.perf_counter
        self._owner = threading.get_ident()
        self._started = self._last = self._clock()
        self._seconds: dict[str, float] = {}
        self._stack: list[str] = []
        self._forced = False

    def _label(self) -> str:
        return DISCOVERY if self._forced else self._stack[-1] if self._stack else OTHER

    def _flush(self) -> None:
        now = self._clock()
        label = self._label()
        self._seconds[label] = self._seconds.get(label, 0.0) + max(0.0, now - self._last)
        self._last = now

    @contextlib.contextmanager
    def phase(self, name: str):
        """The time inside belongs to ``name`` (to ``discovery`` inside a learning pass)."""
        if threading.get_ident() != self._owner:
            yield
            return
        self._flush()
        self._stack.append(name)
        try:
            yield
        finally:
            self._flush()
            self._stack.pop()

    def begin_pass(self, number: int) -> None:
        """Pass ``number`` (1 is the first) of a learning loop starts: from the second on, all its time is
        ``discovery``. ``discovery`` is in the figures as 0.0 from the first pass on."""
        if threading.get_ident() != self._owner:
            return
        self._flush()
        self._seconds.setdefault(DISCOVERY, 0.0)
        self._forced = number > 1

    def end_passes(self) -> None:
        if threading.get_ident() != self._owner:
            return
        self._flush()
        self._forced = False

    def collapse(self, name: str) -> None:
        """What was measured so far becomes one phase (a quick check that failed, before the full conversion)."""
        if threading.get_ident() != self._owner:
            return
        self._flush()
        spent = sum(self._seconds.values())
        self._seconds = {name: spent}
        self._stack.clear()
        self._forced = False

    def snapshot(self) -> dict[str, float]:
        """``{phase: seconds}`` at 0.1 s, in the order of ``ORDER``, then ``other`` and ``total``."""
        self._flush()
        names = sorted((name for name in self._seconds if name != OTHER),
                       key=lambda name: ORDER.index(name) if name in ORDER else len(ORDER))
        figures = {name: round(self._seconds[name], PRECISION) for name in names}
        figures[OTHER] = round(self._seconds.get(OTHER, 0.0), PRECISION)
        figures[TOTAL] = round(self._clock() - self._started, PRECISION)
        return figures


def start(clock=None):
    """A new recorder for the game this thread is about to convert; give the token back to ``stop``."""
    recorder = Recorder(clock)
    return recorder, _CURRENT.set(recorder)


def stop(token) -> None:
    _CURRENT.reset(token)


def current() -> Recorder | None:
    return _CURRENT.get()


@contextlib.contextmanager
def phase(name: str):
    """``current().phase(name)``, or nothing at all when no recorder is running."""
    recorder = _CURRENT.get()
    if recorder is None:
        yield
    else:
        with recorder.phase(name):
            yield


def instrument(module, name: str, phase_name: str) -> None:
    """Make ``module.name`` count its time in ``phase_name``, from now on. For a step buried in a module whose
    code is hashed for another purpose (the Neo Geo quick-state key hashes neogeo_build), so that the step is named
    from outside. Done once per function and left in place: the wrapper does nothing without a recorder."""
    function = getattr(module, name)
    if getattr(function, '_timings_phase', None) is not None:
        return

    @functools.wraps(function)
    def timed(*args, **kwargs):
        with phase(phase_name):
            return function(*args, **kwargs)

    timed._timings_phase = phase_name
    setattr(module, name, timed)


def begin_pass(number: int) -> None:
    recorder = _CURRENT.get()
    if recorder is not None:
        recorder.begin_pass(number)


def end_passes() -> None:
    recorder = _CURRENT.get()
    if recorder is not None:
        recorder.end_passes()


def collapse(name: str) -> None:
    recorder = _CURRENT.get()
    if recorder is not None:
        recorder.collapse(name)


def snapshot() -> dict[str, float] | None:
    recorder = _CURRENT.get()
    return None if recorder is None else recorder.snapshot()


def describe(figures) -> str | None:
    """The one log line of a game: ``times: compile 42.1 s, reference runs 18.3 s, ..., total 120.4 s``.

    A phase under 0.05 s is left out, except ``discovery`` (its 0.0 says the passes were skipped) and ``total``.
    None when there is nothing to say (a report from before the figures, or no recorder)."""
    if not isinstance(figures, dict) or not isinstance(figures.get(TOTAL), (int, float)):
        return None
    parts = [f'{name.replace("_", " ")} {value:.1f} s' for name, value in figures.items()
             if name != TOTAL and isinstance(value, (int, float)) and not isinstance(value, bool)
             and (value >= 0.05 or name == DISCOVERY)]
    parts.append(f'total {figures[TOTAL]:.1f} s')
    return 'times: ' + ', '.join(parts)
