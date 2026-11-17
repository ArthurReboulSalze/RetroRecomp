"""Multiplayer stage 1: the converter's netplay worker on the delay tier.

A game in a session is a commanded stepper (`native/hostkit/hostkit_session.h`): it opens no socket and decides
nothing. This package is the other end of its two pipes, in the converter:

* `session_pipe`: the pipe's messages, encoded and decoded (the same constants as the C header; a test compares
  them);
* `session_game`: one game executable started with the two inherited anonymous pipes, its reader thread, its end;
* `input_records`: what two drivers send each other (input records with redundancy, acknowledgement, digests,
  the delay rule, time sync), as bytes with bounded parsing;
* `session_transport`: the interface a link between seats gives a driver;
* `link_simulator`: its one implementation for now, in memory, inside one process (latency, jitter, loss,
  reordering, duplicates, a seat gone silent; the fate of every packet is fixed by a seed);
* `time_sync`: a steady estimate of how far ahead a game is, and the pace that follows it;
* `lockstep`: the delay-lockstep driver, one per player (a star: guests talk to the host, which forwards);
* `launch`: the one door through which settings that came from another PC become a `Settings` (every field checked);
* `worker_channel`, `worker`, `worker_client`, `scripted_inputs`: the driver in a process of its own (the converter
  starts `RetroRecomp.py _netplay-worker`; they talk over its two pipes), and the scripted controls tests give it.

Stage 2, the local-network room (`SECURITY_REVIEW.md` section 2 is its specification; the pure parts are tested without a
socket):

* `invitation`: the text a host shares (`rr1:lan:<address>:<port>:<secret>`), the address ranges a local room may use;
* `handshake`: the keys and the guest-proves-first handshake, as two state machines of bytes;
* `control`: the TCP control stream (framed, tagged messages) and the display names;
* `datagram`: the match datagrams (UDP) with their tag and replay window, and what a receiver does with one;
* `limits`: the numbers of the review's 2.7 as pure objects on a clock the caller gives;
* `room_log`: what the host of a room writes down (never a secret);
* `lan_transport`: the **only** module that imports `socket`: `RoomHost` and `RoomGuest`, whose `link()` is the `SeatLink`
  the driver already knows (the driver is handed the seat the key proved);
* `room_worker`, `room_cli`: the worker whose life is a room's (the game arrives in a `launch` call), and the command line
  of the two-PC test (`RetroRecomp.py _netplay-room`).

The lobby (`lobby.py` holds the rules; the wire is `control.py` types 10 to 17):

* `lobby`: the host's state machine (seats, ready flags, the host's pick, each guest's answer, chat limits and cleaning, the
  launch plan, the way back to the lobby after a match) and each guest's, as pure functions of a message and a clock, returning
  `Send` and `Event`; `RoomHost` and `RoomGuest` carry them, the room's worker turns the events into the converter's;
* `lobby_check`: the host's game as a `control.Game` (the identity without the learned paths on the machines whose mixed-build gate
  passed, the full simulation identity elsewhere) and a guest's look in its own compiled games (`LocalLibrary`);
* `lobby_client`: the converter's side, with no window: `LobbyModel` (events folded into what a window draws) and `LobbyController`
  (answers the host's pick from the library, resolves the launch to the executable it found, gives the host's window its calls).

Outside `lan_transport` nothing here opens a socket, a port or a file outside the game's own folder (and the room's log).
Nothing touches a firewall or any system setting. These modules are hashed by no stamp (`stamp_inputs.INTERFACE_MODULES`):
they drive finished games and change nothing a game is or does.
"""
from .input_records import choose_delay, pace_for
from .link_simulator import LinkSimulator
from .lockstep import LockstepDriver, Settings
from .session_game import SessionGame
from .session_pipe import ABI, Refused
from .time_sync import PaceController
from .worker_client import WorkerProcess, worker_command

__all__ = ['ABI', 'LinkSimulator', 'LockstepDriver', 'PaceController', 'Refused', 'SessionGame', 'Settings', 'WorkerProcess',
           'choose_delay', 'pace_for', 'worker_command']
