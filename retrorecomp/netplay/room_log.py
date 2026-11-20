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
COUNT_LINES = 16              # lines of counts per window; the rest is one line "and N other sources" (transport review N3)


def _plain(value, limit: int = 80) -> str:
    return ''.join(char if 32 <= ord(char) < 127 else '?' for char in str(value))[:limit]


class RoomLog:
    def __init__(self, path: Path | None, clock=time.monotonic):
        self.path, self._clock = Path(path) if path else None, clock
        self._next_counts = clock() + EVERY
        self.lines: list[str] = []         # the last lines, kept in memory too (tests, the converter's window)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def _write(self, text: str) -> None:
        self._write_all([text])

    def _write_all(self, texts: list[str]) -> None:
        """Several lines, one look at the file and one open."""
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [f'{stamp} {text}' for text in texts]
        self.lines.extend(lines)
        del self.lines[:-200]
        if self.path is None or not lines:
            return
        try:
            if self.path.exists() and self.path.stat().st_size > LIMIT:
                self.path.replace(self.path.with_suffix(self.path.suffix + '.1'))
            with open(self.path, 'a', encoding='utf-8', newline='\n') as stream:
                stream.write(''.join(line + '\n' for line in lines))
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

    def over(self, match_id: int, text: str) -> None:
        """How a match ended on this PC: the outcome, the game's exit code and its own reason line (game_logs.reason_line,
        a line of the converted game's stderr, never the room's secrets), longer than the other lines."""
        self._write(f'match {int(match_id)} over: {_plain(text, 400)}')

    def note(self, text: str) -> None:
        self._write(_plain(text))

    def counts(self, window: dict, now: float | None = None, force: bool = False) -> bool:
        """The drops and refusals of the last ten seconds, one line per (reason, address) for the `COUNT_LINES` largest
        and one line for all the others, written in one go (a flood from many addresses is one short write)."""
        now = self._clock() if now is None else now
        if not force and now < self._next_counts:
            return False
        self._next_counts = now + EVERY
        ranked = sorted(window.items(), key=lambda item: (-item[1], item[0]))
        lines = [f'refused {_plain(reason)} x{int(count)} from {_plain(address)} in the last {EVERY:g} s'
                 for (reason, address), count in sorted(ranked[:COUNT_LINES])]
        rest = ranked[COUNT_LINES:]
        if rest:
            lines.append(f'refused x{sum(int(count) for _key, count in rest)} more from {len(rest)} other (reason, address) '
                         f'pairs in the last {EVERY:g} s')
        self._write_all(lines)
        return True

    def due(self, now: float | None = None) -> bool:
        return (self._clock() if now is None else now) >= self._next_counts
