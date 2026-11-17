"""A test of a far player on a local network: the packets this PC sends to the match are held a fixed time (and a jitter)
before they leave. Nothing else changes: the same transport, the same game, the same driver.

Asked only by the room command's `--lag-ms` (a check between two of the owner's PCs, 17 November 2026: "a player at 150 ms").
Each side delays what it sends, so lag 75 on both PCs is a round trip of 150 ms. One thread waits on a condition for the next
packet's time (no busy loop); packets keep the order a real link with that jitter could give. Original Retro-Recomp code, MIT.
"""
from __future__ import annotations

import heapq
import itertools
import random
import threading
import time
from typing import Callable

MAX_LAG_MS = 500.0


class LagLink:
    """A SeatLink whose `send` hands the packet to the wrapped link `lag_ms` (plus 0 to `jitter_ms`) later."""

    def __init__(self, link, lag_ms: float, jitter_ms: float = 0.0, seed: int = 1):
        if not 0.0 <= lag_ms <= MAX_LAG_MS or not 0.0 <= jitter_ms <= MAX_LAG_MS:
            raise ValueError(f'a lag of 0 to {MAX_LAG_MS:g} ms')
        self.link, self.seat = link, getattr(link, 'seat', 0)
        self.lag, self.jitter = lag_ms / 1000.0, jitter_ms / 1000.0
        self._random = random.Random(seed)
        self._queue: list = []
        self._order = itertools.count()
        self._changed = threading.Condition()
        self._closed = False
        self._thread = threading.Thread(target=self._run, name='netplay-lag-link', daemon=True)
        self._thread.start()

    def open(self, sink: Callable[[int, bytes], None]) -> None:
        self.link.open(sink)

    def send(self, to_seat: int, data: bytes) -> None:
        due = time.monotonic() + self.lag + (self._random.uniform(0.0, self.jitter) if self.jitter else 0.0)
        with self._changed:
            if self._closed:
                return
            heapq.heappush(self._queue, (due, next(self._order), to_seat, data))
            self._changed.notify()

    def close(self) -> None:
        with self._changed:
            self._closed = True
            self._queue.clear()
            self._changed.notify()
        self.link.close()

    def _run(self) -> None:
        while True:
            with self._changed:
                while not self._closed and (not self._queue or self._queue[0][0] > time.monotonic()):
                    wait = self._queue[0][0] - time.monotonic() if self._queue else None
                    self._changed.wait(wait)
                if self._closed:
                    return
                _due, _order, to_seat, data = heapq.heappop(self._queue)
            self.link.send(to_seat, data)

    def __getattr__(self, name):            # anything else the driver reads from its link
        return getattr(self.link, name)
