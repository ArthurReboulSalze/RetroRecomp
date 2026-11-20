"""Time sync: a steady estimate of how far ahead this game is, and a pace that moves one small step at a time.

Two PCs never run at exactly the same speed. In delay lockstep the faster one is held back by the records of the
slower one, frame after frame, which stutters; the cure is to slow the faster game by a fraction of a per cent
(`PACE`, parts per million added to its frame period, never negative here and never above 2 %) so that it does not
reach the wait. The estimate this needs is noisy: every packet says where its sender's game was, and the way
there takes a time that jitters by tens of milliseconds, which is more than a frame. A rule that reads each
estimate flips with the noise (28 changes in 1,800 frames on a 120 +- 20 ms link, before this module).

`PaceController` keeps, per other seat, the advantage samples of the last `window` seconds and works on their
median (one late packet is one sample among many). It asks for a change only when the slowest seat's median calls
for it by the proportional rule `input_records.pace_for` (a dead band of half a frame), changes the pace by one step
(0.25 %) at most, never twice within `hold` seconds, and needs the median to pass a threshold by 0.15 frame to step up and to fall 0.25 frame below it
to step back down (hysteresis: a median sitting on a boundary does not flip, and a pace that matches the drift stays). It reads a clock the caller gives it
and never sleeps, so it is tested with time it makes up.
"""
from __future__ import annotations

from collections import deque
from statistics import median

from .input_records import PACE_LIMIT, PACE_STEP, pace_for

STEP = PACE_STEP             # parts per million per change: 0.25 %
LIMIT = PACE_LIMIT           # 2 %, the study's bound and the pipe's
ATTACK = 0.15                # frames above a threshold before the pace steps up
RELEASE = 0.25               # frames below a threshold before the pace steps back down



class PaceController:
    def __init__(self, window: float = 3.0, min_samples: int = 12, hold: float = 1.0, deadband: float = 0.5):
        self.window, self.min_samples, self.hold, self.deadband = window, min_samples, hold, deadband
        self.ppm = 0
        self.changes = 0
        self.median = 0.0                   # the slowest seat's median advantage at the last update, frames
        self._samples: dict[int, deque] = {}
        self._changed_at = float('-inf')

    def observe(self, seat: int, now: float, advantage: float) -> None:
        """One sample: this game's frame minus where `seat`'s game is estimated to be now, in frames."""
        samples = self._samples.setdefault(seat, deque(maxlen=512))
        samples.append((now, advantage))

    def forget(self) -> None:
        """Drops what was seen (a pause, a start): the frames did not move meanwhile, the samples would lie."""
        self._samples.clear()

    def update(self, now: float) -> int | None:
        """The new pace when it changes, else None."""
        medians = []
        for samples in self._samples.values():
            while samples and now - samples[0][0] > self.window:
                samples.popleft()
            if len(samples) >= self.min_samples:
                medians.append(median(value for _when, value in samples))
        if not medians:
            return None
        self.median = max(medians)              # ahead of the slowest seat
        wanted = pace_for(self.median - ATTACK, self.deadband)
        if wanted > self.ppm:
            new = min(self.ppm + STEP, wanted)
        elif pace_for(self.median + RELEASE, self.deadband) < self.ppm:
            new = max(self.ppm - STEP, pace_for(self.median + RELEASE, self.deadband))
        else:
            return None
        if now - self._changed_at < self.hold:
            return None
        self.ppm, self._changed_at = min(new, LIMIT), now
        self.changes += 1
        return self.ppm
