"""A command line for the first test between two PCs, with no window and no change to the machine.

    python -B RetroRecomp.py _netplay-room addresses
    python -B RetroRecomp.py _netplay-room host  --address 192.168.1.20 --game "C:\\path\\to\\game.exe" [--guests 1]
    python -B RetroRecomp.py _netplay-room guest "rr1:lan:192.168.1.20:24611:...." --game "C:\\path\\to\\game.exe"
    python -B RetroRecomp.py _netplay-room guest - --game ...        (the invitation is read from the keyboard)
    python -B RetroRecomp.py _netplay-room guest --invitation-file FILE --game ...

The converter's window does not have the multiplayer view yet: this is its stand-in, built on the same pieces (a
`WorkerProcess` that owns the room and the game, `launch` and `launch_request` as the window will use them). The host
prints its invitation (it holds the secret: share it only with the friend), waits until `--guests` guests have joined,
launches, and prints how the match went; each guest gives its own copy of the same game. The games open their own
windows, as a game does.

What this does not do: it never touches a firewall or any system setting (the rule to add by hand is in the room's
notes), never opens a port but the room's one (on the address given), never asks a router for one, never reaches the
Internet. The invitation on a command line is visible to the other users of that PC: `-` or `--invitation-file` keep it
out of the process list.

The game's identity for the check "same game on both PCs" is `--machine`, `--stamp` and `--rom-sha256` (defaults: a
test word and zeros, the same on both sides); the host's launch names them, a guest whose own differ answers "not the
same game". What really proves the two games start alike is the boot digest the drivers compare before frame 0.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile

from . import control, invitation
from .worker_client import WorkerProcess

DEFAULT_MACHINE = 'cli'
ZERO = '00' * 32


def say(text: str) -> None:
    encoding = sys.stdout.encoding or 'ascii'
    print(text.encode(encoding, 'replace').decode(encoding), flush=True)


def _hex32(text: str) -> str:
    value = text.lower()
    if len(value) != 64 or any(char not in '0123456789abcdef' for char in value):
        raise argparse.ArgumentTypeError('64 hexadecimal digits')
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='_netplay-room', description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('addresses', help='print this PC\'s addresses a local room may use')
    for name in ('host', 'guest'):
        sub = commands.add_parser(name)
        sub.add_argument('--game', required=True, type=Path, help='the game executable (an export built with the session pipe)')
        sub.add_argument('--name', default='Host' if name == 'host' else 'Guest')
        sub.add_argument('--machine', default=DEFAULT_MACHINE)
        sub.add_argument('--stamp', type=_hex32, default=ZERO)
        sub.add_argument('--rom-sha256', type=_hex32, default=ZERO)
        sub.add_argument('--log-dir', type=Path, default=Path(tempfile.gettempdir()) / 'retro-recomp-netplay',
                         help='the worker\'s text, the room\'s log and the game\'s own output go here')
    host = commands.choices['host']
    host.add_argument('--address', required=True, help='this PC\'s own IPv4 address on the local network (see `addresses`)')
    host.add_argument('--port', type=int, default=invitation.DEFAULT_PORT)
    host.add_argument('--guests', type=int, default=1, choices=(1, 2, 3), help='launch when this many guests have joined')
    host.add_argument('--delay', type=int, default=None, help='input delay in frames (default: measured, chosen by the host)')
    host.add_argument('--digest-every', type=int, default=60)
    host.add_argument('--option', action='append', default=[], metavar='KEY=VALUE', help='a run-changing option of the game')
    host.add_argument('--join-timeout', type=float, default=600.0, help='seconds to wait for the guests')
    host.add_argument('--frames', type=int, default=0, help='stop the match for everyone after about this many frames (a timed check)')
    guest = commands.choices['guest']
    guest.add_argument('invitation', nargs='?', help='the invitation, or - to read it from the keyboard')
    guest.add_argument('--invitation-file', type=Path)
    return parser


def _describe(event: dict) -> str | None:
    name = event.get('event')
    if name == 'room_open':
        return f'room open on {event["address"]}:{event["port"]} for {event["capacity"]} seats'
    if name == 'joined_room':
        return f'joined the room as guest {event["guest"]} of {event["capacity"] - 1}'
    if name == 'joined':
        return f'{event["name"]} joined from {event["address"]}'
    if name == 'left':
        return f'{event["name"]} left: {event.get("detail", "")}'
    if name == 'launching':
        return f'match {event["match_id"]}: launching with {", ".join(event["names"])}'
    if name == 'launch_request':
        return f'match {event["match_id"]}: the host launches seat {event["seat"] + 1} of {event["seats"]}'
    if name == 'slow_link':
        return event['detail']
    if name == 'match_over':
        return f'match {event["match_id"]} over: {event["outcome"]} {event.get("detail", "")}'.rstrip()
    if name in ('room_error', 'launch_error', 'launch_failed', 'launch_refused', 'host_gone', 'seat_dropped'):
        return f'{name.replace("_", " ")}: {event.get("detail", "")}'
    return None


def _game_config(path: Path, folder: Path, prefix: str) -> dict:
    return {'exe': str(path.resolve()), 'cwd': str(path.resolve().parent), 'stdout': str(folder / f'{prefix}-stdout.txt'),
            'stderr': str(folder / f'{prefix}-stderr.txt')}


def _summary(worker: WorkerProcess) -> str:
    result = worker.result or {}
    return (f'outcome {result.get("outcome")}, {result.get("history_frames", 0)} frames, delay {result.get("delay")}, '
            f'history digest {result.get("history_digest")}, boot digest {result.get("boot_digest")}, '
            f'desync {result.get("desync")}, waits {result.get("stats", {}).get("waits")}, late frames {result.get("stats", {}).get("late_frames")}'
            + (f', {result["detail"]}' if result.get('detail') else ''))


def version_numbers(text: str) -> tuple:
    """The version the HELLO carries: always three numbers, whatever the text ('1.8.0rc1' gives 1, 8, 0)."""
    numbers = [int(part) for part in text.split('.')[:3] if part.isascii() and part.isdigit() and int(part) <= 0xffff]
    return tuple((numbers + [0, 0, 0])[:3])


def _wait_until_over(worker: WorkerProcess, match_events_from: int, frames: int = 0) -> bool:
    stopped = False
    try:
        while True:
            if worker.wait_event('match_over', 1.0, after=match_events_from):
                return True
            if worker.done:
                return False
            if frames and not stopped and worker.status.get('next_run', 0) >= frames:
                stopped = True
                say(f'{frames} frames: stopping the match')
                worker.stop()
    except KeyboardInterrupt:
        say('stopping the match...')
        worker.stop()
        return worker.wait_event('match_over', 60.0, after=match_events_from) is not None


def _show(event: dict) -> None:
    line = _describe(event)
    if line:
        say(line)


def run_host(args, tests: bool = False) -> int:
    args.log_dir.mkdir(parents=True, exist_ok=True)
    secret = invitation.new_secret()
    try:
        invitation.check_bind_address(args.address, tests)
    except ValueError as error:
        say(f'--address: {error}')
        return 1
    config = {'room': {'role': 'host', 'address': args.address, 'port': args.port, 'secret': secret.hex(),
                       'capacity': args.guests + 1, 'name': args.name, 'log': str(args.log_dir / 'room.log')}, 'tests': tests}
    worker = WorkerProcess(config, log=args.log_dir / 'worker.txt', on_event=_show).start()
    try:
        opened = worker.wait_event('room_open', 20.0)
        if opened is None:
            say('the room did not open (see the lines above, and ' + str(args.log_dir / 'worker.txt') + ')')
            return 1
        say('invitation: ' + invitation.format_invitation(opened['address'], opened['port'], secret, tests))
        say(f'share it with your friend only; waiting for {args.guests} guest(s) (Ctrl+C to give up)')
        def count(worker):
            return worker.event_totals['joined'] - worker.event_totals['left'] >= args.guests
        try:
            if not worker.wait_for(count, args.join_timeout) or worker.done:
                say('not enough guests joined: closing the room')
                return 1
        except KeyboardInterrupt:
            return 1
        mark = worker.event_count
        settings = {'delay': args.delay, 'digest_every': args.digest_every, 'redundancy': 3, 'options': '\n'.join(args.option)}
        worker.call('launch', game=_game_config(args.game, args.log_dir, 'host'),
                    identity={'machine': args.machine, 'stamp': args.stamp, 'rom': args.rom_sha256}, settings=settings)
        _wait_until_over(worker, mark, args.frames)
        worker.wait_for(lambda w: w.result is not None, 10.0)
        say('result: ' + _summary(worker))
        return 0 if (worker.result or {}).get('outcome') in ('ended', 'host_closed') else 1
    finally:
        worker.call('close_room')
        worker.join(15.0)
        worker.cleanup()


def run_guest(args, tests: bool = False) -> int:
    args.log_dir.mkdir(parents=True, exist_ok=True)
    text = args.invitation
    if args.invitation_file is not None:
        text = args.invitation_file.read_text(encoding='utf-8')
    elif text == '-' or text is None:
        text = input('invitation: ')
    try:
        invitation.parse(text, tests)
    except invitation.InvitationError as error:
        say(error.reason)
        return 1

    def resolve(event: dict) -> dict | None:
        if event['machine'] != args.machine:
            return {'call': 'launch_refused', 'match_id': event['match_id'], 'status': control.LAUNCHED_NOT_OWNED}
        if event['stamp'] != args.stamp or event['rom'] != args.rom_sha256:
            return {'call': 'launch_refused', 'match_id': event['match_id'], 'status': control.LAUNCHED_OTHER_STAMP}
        return {'call': 'launch', 'match_id': event['match_id'], 'game': _game_config(args.game, args.log_dir, 'guest')}

    from .. import __version__
    version = version_numbers(__version__)
    config = {'room': {'role': 'guest', 'invitation': text.strip(), 'name': args.name, 'version': list(version)}, 'tests': tests}
    worker = WorkerProcess(config, log=args.log_dir / 'worker.txt', on_event=_show, resolve=resolve).start()
    try:
        say('joining the room...')
        if worker.wait_event('joined_room', 20.0) is None:
            if worker.wait_event('room_error', 1.0) is None:
                say('no answer: check the invitation, or the host\'s firewall')
            return 1
        say('in the room; waiting for the host to launch (Ctrl+C to leave)')
        try:
            while worker.wait_event('match_over', 1.0) is None:
                if worker.done or worker.wait_event('host_gone', 0.0):
                    say('the host is gone')
                    return 1
        except KeyboardInterrupt:
            worker.stop()
            worker.wait_event('match_over', 60.0)
        worker.wait_for(lambda w: w.result is not None, 10.0)
        say('result: ' + _summary(worker))
        return 0 if (worker.result or {}).get('outcome') in ('ended', 'host_closed') else 1
    finally:
        worker.call('close_room')
        worker.join(15.0)
        worker.cleanup()


def main(argv: list[str], tests: bool = False) -> int:
    """`tests` is for the code that tests this command line (127.0.0.1 is then accepted); the command `RetroRecomp.py
    _netplay-room` never sets it and the command line has no flag for it."""
    args = _parser().parse_args(argv)
    if args.command == 'addresses':
        from .lan_transport import local_addresses
        found = local_addresses()
        say('\n'.join(found) if found else 'no address of a local network was found on this PC')
        return 0
    return run_host(args, tests) if args.command == 'host' else run_guest(args, tests)
