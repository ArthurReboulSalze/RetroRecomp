"""An in-memory link between seats, for several lockstep drivers inside one Python process.

No socket, no port, nothing outside this process. Every directed link (from one seat to another) has its own
latency, jitter, loss, duplicate and reorder rates. The fate of the n-th packet of a link (lost, repeated, held
back, how much jitter) comes from a generator seeded by (seed, from, to) and is drawn the same way for every
packet, so two runs with one seed treat the n-th packet of each link identically. The moments of delivery are real
time (one scheduler thread sleeps until the next packet is due): they are not reproducible to the microsecond, and
nothing here is a measure of speed.

`silence(seat, True)` cuts a seat off, both ways, until `silence(seat, False)`: a burst of loss, or a seat gone.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import heapq
import random
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class LinkRules:
    latency_ms: float = 0.0      # one way
    jitter_ms: float = 0.0       # added to the latency, uniform in [-jitter, +jitter]
    loss: float = 0.0            # probability, per packet
    duplicate: float = 0.0
    reorder: float = 0.0         # probability of being held back `reorder_ms` more
    reorder_ms: float = 30.0


class _Endpoint:
    def __init__(self, simulator: 'LinkSimulator', seat: int):
        self.simulator, self.seat = simulator, seat
        self.sink: Callable[[int, bytes], None] | None = None

    def open(self, sink):
        self.sink = sink

    def send(self, to_seat: int, data: bytes) -> None:
        self.simulator._send(self.seat, to_seat, bytes(data))

    def close(self):
        self.sink = None


class LinkSimulator:
    def __init__(self, seats: int, seed: int = 1, **rules):
        self.seats = seats
        self.seed = seed
        self._rules = {(a, b): LinkRules(**rules) for a in range(seats) for b in range(seats) if a != b}
        self._random = {link: random.Random(f'{seed}:{link[0]}:{link[1]}') for link in self._rules}
        self._endpoints = [_Endpoint(self, seat) for seat in range(seats)]
        self._silent: set[int] = set()
        self._heap: list = []
        self._order = 0
        self._wake = threading.Condition()
        self._closed = False
        # per link: what happened to each packet, in order ('.' sent, 'L' lost, 'D' duplicated, 'R' held back, 'S' silenced)
        self.fates = {link: [] for link in self._rules}
        self.counts = {'sent': 0, 'delivered': 0, 'lost': 0, 'duplicated': 0, 'reordered': 0, 'silenced': 0}
        self._thread = threading.Thread(target=self._deliver, name='netplay-link-simulator', daemon=True)
        self._thread.start()

    def endpoint(self, seat: int) -> _Endpoint:
        return self._endpoints[seat]

    def set_link(self, a: int, b: int, **rules) -> None:
        """Both directions between two seats."""
        with self._wake:
            for link in ((a, b), (b, a)):
                self._rules[link] = replace(self._rules[link], **rules)

    def set_seat(self, seat: int, **rules) -> None:
        """Every link that touches a seat."""
        for other in range(self.seats):
            if other != seat:
                self.set_link(seat, other, **rules)

    def silence(self, seat: int, on: bool) -> None:
        with self._wake:
            (self._silent.add if on else self._silent.discard)(seat)

    def _send(self, source: int, target: int, data: bytes) -> None:
        link = (source, target)
        with self._wake:
            if self._closed or link not in self._rules:
                return
            rules, chance = self._rules[link], self._random[link]
            # four draws per packet, always, in this order: the n-th packet's fate does not depend on the others'
            lost, twice, held, spread = chance.random(), chance.random(), chance.random(), chance.uniform(-1.0, 1.0)
            self.counts['sent'] += 1
            if source in self._silent or target in self._silent:
                self.counts['silenced'] += 1
                self.fates[link].append('S')
                return
            if lost < rules.loss:
                self.counts['lost'] += 1
                self.fates[link].append('L')
                return
            delay = max(0.0, rules.latency_ms + spread * rules.jitter_ms)
            fate = '.'
            if held < rules.reorder:
                delay += rules.reorder_ms
                self.counts['reordered'] += 1
                fate = 'R'
            due = time.monotonic() + delay / 1000.0
            copies = [due]
            if twice < rules.duplicate:
                copies.append(due + 0.002)
                self.counts['duplicated'] += 1
                fate = 'D'
            self.fates[link].append(fate)
            for moment in copies:
                self._order += 1
                heapq.heappush(self._heap, (moment, self._order, target, source, data))
            self._wake.notify()

    def _deliver(self):
        while True:
            with self._wake:
                while not self._closed:
                    if self._heap:
                        wait = self._heap[0][0] - time.monotonic()
                        if wait <= 0:
                            break
                        self._wake.wait(wait)
                    else:
                        self._wake.wait()
                if self._closed:
                    return
                _moment, _order, target, source, data = heapq.heappop(self._heap)
                silent = source in self._silent or target in self._silent      # cut while the packet was on its way
                if silent:
                    self.counts['silenced'] += 1
                sink = None if silent else self._endpoints[target].sink
            if sink is not None:
                self.counts['delivered'] += 1
                sink(source, data)

    def close(self) -> None:
        with self._wake:
            self._closed = True
            self._heap.clear()
            self._wake.notify_all()
        self._thread.join(timeout=5)
