"""The room's limits, as pure objects on a clock the caller gives (no socket, no thread, no real time).

`SECURITY_REVIEW.md` section 2.7 holds the numbers; they are constants here, one place, each with the test that
holds it. Everything is bounded in memory: a table never has more entries than a room can have (a few addresses),
and an entry that expired is dropped.
"""
from __future__ import annotations

import collections

# what a stranger on the network may cost before it has proven anything
UNAUTHENTICATED_PER_ADDRESS = 2
UNAUTHENTICATED_IN_ROOM = 8
HANDSHAKE_SECONDS = 5.0
FAILURES_PER_MINUTE = 3
REFUSED_SECONDS = 300.0
FAILURE_WINDOW = 60.0
TABLE_LIMIT = 256                  # addresses remembered at once (a flood from many sources cannot grow the table)
# datagrams, before and after the tag check
ADDRESS_RATE, ADDRESS_BURST = 1000.0, 200.0
TOTAL_RATE, TOTAL_BURST = 4000.0, 800.0
SEAT_RATE, SEAT_BURST = 240.0, 60.0
SEAT_OVER_SECONDS = 5.0            # above the seat's limit for this long, running: the seat is dropped
SEAT_QUIET_SECONDS = 1.0           # a gap this long without an excess ends the streak
# control frames
FRAME_RATE, FRAME_BURST = 20.0, 40.0


class TokenBucket:
    """A rate limit: `rate` a second, `burst` at once; the clock is the caller's."""

    def __init__(self, rate: float, burst: float, now: float):
        self.rate, self.burst, self.tokens, self.at = rate, burst, float(burst), now

    def take(self, now: float) -> bool:
        self.tokens = min(self.burst, self.tokens + max(0.0, now - self.at) * self.rate)
        self.at = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class SeatLimit:
    """A seat's datagram bucket after the tag check, and the streak of excess that ends the seat (`over`)."""

    def __init__(self, now: float, rate: float = SEAT_RATE, burst: float = SEAT_BURST):
        self.bucket = TokenBucket(rate, burst, now)
        self.over_since: float | None = None
        self.last_excess = 0.0

    def take(self, now: float) -> bool:
        if self.bucket.take(now):
            return True
        if self.over_since is None or now - self.last_excess > SEAT_QUIET_SECONDS:
            self.over_since = now
        self.last_excess = now
        return False

    def over(self, now: float) -> bool:
        """The seat has been above its limit for `SEAT_OVER_SECONDS`, running."""
        return (self.over_since is not None and now - self.last_excess <= SEAT_QUIET_SECONDS
                and now - self.over_since >= SEAT_OVER_SECONDS)


class Admission:
    """Who may open a connection and how often one may fail: two unauthenticated connections per source address, eight
    in the room, three failed handshakes a minute and then five minutes of refusal for that address."""

    def __init__(self):
        self._open: dict[str, int] = {}
        self._failures: dict[str, list] = {}        # address -> failure times within the window
        self._refused_until: dict[str, float] = {}

    def refused(self, address: str, now: float) -> bool:
        until = self._refused_until.get(address)
        if until is None:
            return False
        if now >= until:
            del self._refused_until[address]
            return False
        return True

    def may_accept(self, address: str, now: float) -> bool:
        return (not self.refused(address, now) and self._open.get(address, 0) < UNAUTHENTICATED_PER_ADDRESS
                and sum(self._open.values()) < UNAUTHENTICATED_IN_ROOM)

    def opened(self, address: str) -> None:
        self._open[address] = self._open.get(address, 0) + 1

    def closed(self, address: str) -> None:
        """An unauthenticated connection ended (it was authenticated, failed, or timed out)."""
        left = self._open.get(address, 0) - 1
        if left > 0:
            self._open[address] = left
        else:
            self._open.pop(address, None)

    def failed(self, address: str, now: float) -> bool:
        """One failed handshake; True when that address is now refused."""
        times = [moment for moment in self._failures.get(address, []) if now - moment < FAILURE_WINDOW]
        times.append(now)
        if address not in self._failures and len(self._failures) >= TABLE_LIMIT:
            self._forget(now)
        self._failures[address] = times
        if len(times) >= FAILURES_PER_MINUTE:
            self._refused_until[address] = now + REFUSED_SECONDS
            del self._failures[address]
            return True
        return False

    def _forget(self, now: float) -> None:
        for address in [name for name, times in self._failures.items() if all(now - moment >= FAILURE_WINDOW for moment in times)]:
            del self._failures[address]
        for address in [name for name, until in self._refused_until.items() if now >= until]:
            del self._refused_until[address]
        while len(self._failures) >= TABLE_LIMIT:       # a flood of sources: the oldest are forgotten, the room stays bounded
            del self._failures[next(iter(self._failures))]


class NonceMemory:
    """The last handshake nonces: a message 1 replayed is refused."""

    def __init__(self, size: int = 64):
        self._order: collections.deque = collections.deque(maxlen=size)
        self._set: set = set()

    def seen(self, nonce: bytes) -> bool:
        return nonce in self._set

    def remember(self, nonce: bytes) -> None:
        if len(self._order) == self._order.maxlen:
            self._set.discard(self._order[0])
        self._order.append(nonce)
        self._set.add(nonce)


class Counters:
    """Drops and refusals by reason and by address, for the log's ten-second lines (`room_log`)."""

    def __init__(self):
        self.total: collections.Counter = collections.Counter()
        self._window: collections.Counter = collections.Counter()

    def count(self, reason: str, address: str = '-') -> None:
        self.total[reason] += 1
        if len(self._window) < TABLE_LIMIT or (reason, address) in self._window:
            self._window[(reason, address)] += 1

    def take_window(self) -> dict:
        window, self._window = dict(self._window), collections.Counter()
        return window
