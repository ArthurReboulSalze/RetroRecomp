"""The local channel between the converter and its netplay worker process: two anonymous pipes (the worker's stdin
and stdout), nothing else. No socket, no port, not even on loopback.

Every message, both ways: `u8 kind, u32 length, payload` (little-endian, at most MAX_PAYLOAD bytes). A length above
the limit or an unknown kind breaks the channel: the reader raises `Broken`.

    converter -> worker   CONFIG  json: the game, this seat's settings, test sources (once, first)
                          NET     u8 from_seat, packet bytes: a packet another seat sent, as the link delivered it
                          CALL    json {"call": "stop" | "resume" | "close_game_pipe"}
    worker -> converter   STATUS  json: what the driver shows now (phase, frame, outcome, counts), when it changes
                          NET     u8 to_seat, packet bytes: a packet for another seat; the converter side carries it
                          RESULT  json: the final state with the history and the digests (once, last)

In stage 1 the converter side stands for the network: it carries the NET messages of the workers to each other
(through `link_simulator` in the tests). In stage 2 the worker opens the room's one endpoint itself and this
channel keeps CONFIG, CALL, STATUS and RESULT: the NET messages disappear, nothing else changes.
"""
from __future__ import annotations

import os
import struct
import threading

MAX_PAYLOAD = 16 * 1024 * 1024       # a RESULT carries every frame's port words; a packet is at most 508 bytes
CONFIG, NET_IN, CALL = 1, 2, 3
STATUS, NET_OUT, RESULT = 16, 17, 18
KINDS = {CONFIG, NET_IN, CALL, STATUS, NET_OUT, RESULT}
_HEAD = struct.Struct('<BI')


class Broken(Exception):
    """A message that breaks the channel's rules."""


def frame(kind: int, payload: bytes = b'') -> bytes:
    if kind not in KINDS or len(payload) > MAX_PAYLOAD:
        raise ValueError('a channel message of an unknown kind or above MAX_PAYLOAD')
    return _HEAD.pack(kind, len(payload)) + payload


class Reader:
    """Whole messages out of the bytes read so far."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[tuple[int, bytes]]:
        self.buffer += chunk
        messages = []
        while len(self.buffer) >= _HEAD.size:
            kind, size = _HEAD.unpack_from(self.buffer)
            if kind not in KINDS or size > MAX_PAYLOAD:
                raise Broken(f'channel message kind {kind}, {size} bytes')
            if len(self.buffer) < _HEAD.size + size:
                break
            messages.append((kind, bytes(self.buffer[_HEAD.size:_HEAD.size + size])))
            del self.buffer[:_HEAD.size + size]
        return messages


class Writer:
    """Writes whole messages to a file descriptor, from any thread; `closed` once the other end is gone."""

    def __init__(self, fd: int):
        self.fd = fd
        self.closed = False
        self._lock = threading.Lock()

    def send(self, kind: int, payload: bytes = b'') -> bool:
        data = frame(kind, payload)
        with self._lock:
            if self.closed:
                return False
            try:
                view = memoryview(data)
                while view:
                    view = view[os.write(self.fd, view):]
                return True
            except OSError:
                self.closed = True
                return False
