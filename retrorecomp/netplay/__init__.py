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

Nothing here opens a socket, a port or a file outside the game's own folder: the real network is a later stage.
These modules are hashed by no stamp (`stamp_inputs.INTERFACE_MODULES`): they drive finished games and change
nothing a game is or does.
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
