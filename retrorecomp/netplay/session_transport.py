"""The link between seats, as a lockstep driver sees it.

A driver owns one `SeatLink`: it sends bytes to another seat and is handed the bytes that arrive, with the seat
they came from. Nothing more is promised: a packet may be late, lost, repeated or out of order, and the driver's
records, acknowledgements and timeouts are built for that. The link never blocks the caller of `send`, and it
calls the sink from a thread of its own.

One implementation exists in stage 1: `link_simulator.LinkSimulator`, in memory. The real network (stage 2, on the
owner's word) is another implementation of the same three methods; the driver does not change.
"""
from __future__ import annotations

from typing import Callable, Protocol


class SeatLink(Protocol):
    seat: int

    def open(self, sink: Callable[[int, bytes], None]) -> None:
        """Packets for this seat go to `sink(from_seat, data)` from now on."""

    def send(self, to_seat: int, data: bytes) -> None:
        """Best effort, never waits."""

    def close(self) -> None:
        """Nothing is sent or handed after this."""
