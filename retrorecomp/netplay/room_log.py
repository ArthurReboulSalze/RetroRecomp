"""What the host of a room logs: one file per room, at most 1 MiB, one older file kept, never uploaded.

`SECURITY_REVIEW.md` 2.10: the room opened and closed with its bound address and port; each authenticated join and
leave (name, address, reason); handshake failures and dropped datagrams as **counts per address per ten seconds, by
reason** (never a line per packet); each launch (match number, machine, the first 8 hex digits of the stamp, seats,
delay); stalls, desyncs, a seat dropped for its rate, every end with its reason.

Never in it: the invitation, the secret, a key, a nonce, a tag, a ROM digest in full, a packet's contents, chat. The
log has no method that takes such a value: its entries are a fixed sentence plus fields it formats itself (a stamp is
cut to eight hex digits here, a name is cleaned of control characters).
"""
from __future__ import annotations

from pathlib import Path
import time

LIMIT = 1024 * 1024
EVERY = 10.0                  # seconds between two lines of counts


def _plain(value) -> str:
    return ''.join(char if 32 <= ord(char) < 127 else '?' for char in str(value))[:80]


class RoomLog:
    def __init__(self, path: Path | None, clock=time.monotonic):
        self.path, self._clock = Path(path) if path else None, clock
        self._next_counts = clock() + EVERY
        self.lines: list[str] = []         # the last lines, kept in memory too (tests, the converter's window)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, text: str) -> None:
        line = f'{time.strftime("%Y-%m-%d %H:%M:%S")} {text}'
        self.lines.append(line)
        del self.lines[:-200]
        if self.path is None:
            return
        try:
            if self.path.exists() and self.path.stat().st_size > LIMIT:
                self.path.replace(self.path.with_suffix(self.path.suffix + '.1'))
            with open(self.path, 'a', encoding='utf-8', newline='\n') as stream:
                stream.write(line + '\n')
        except OSError:
            pass                            # a log that cannot be written never stops a room

    def room(self, state: str, address: str, port: int) -> None:
        self._write(f'room {_plain(state)} on {_plain(address)}:{int(port)}')

    def joined(self, name: str, address: str) -> None:
        self._write(f'join {_plain(name)} from {_plain(address)}')

    def left(self, name: str, address: str, reason: str) -> None:
        self._write(f'leave {_plain(name)} from {_plain(address)}: {_plain(reason)}')

    def launch(self, match_id: int, machine: str, stamp: bytes, seats: int, delay: int) -> None:
        self._write(f'launch match {int(match_id)}: {_plain(machine)} stamp {bytes(stamp[:4]).hex()}, {int(seats)} seats, '
                    f'delay {"measured" if not delay else int(delay)}')

    def match(self, match_id: int, text: str) -> None:
        self._write(f'match {int(match_id)}: {_plain(text)}')

    def note(self, text: str) -> None:
        self._write(_plain(text))

    def counts(self, window: dict, now: float | None = None, force: bool = False) -> bool:
        """The drops and refusals of the last ten seconds, one line per (reason, address)."""
        now = self._clock() if now is None else now
        if not force and now < self._next_counts:
            return False
        self._next_counts = now + EVERY
        for (reason, address), count in sorted(window.items()):
            self._write(f'refused {_plain(reason)} x{int(count)} from {_plain(address)} in the last {EVERY:g} s')
        return True

    def due(self, now: float | None = None) -> bool:
        return (self._clock() if now is None else now) >= self._next_counts
