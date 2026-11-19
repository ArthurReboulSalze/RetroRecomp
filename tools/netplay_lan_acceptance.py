"""The multiplayer acceptance of a converted game between two real PCs, with no window and no player: the check Arthur's
two-PC tests of 17 November 2026 made by hand on the NES (the reference), run for any machine.

    python -B tools/netplay_lan_acceptance.py run --game GAME.exe --remote USER@HOST --remote-root DIR
        --remote-game GAME.exe --remote-address IP [--remote-python PYTHON] [--frames 3000] [--tier auto|delay|rollback]
        [--machine ID] [--seats 2|3|4] [--lag-ms MS] [--jitter-ms MS] [--save-at F --load-at G] [--restart-at F]
        [--report FILE]

`run` starts the host side on the remote PC over SSH (its converter folder, its own copy of the same export), reads the
invitation it prints, joins it from this PC, and compares what the two sides ran: both matches ended, the same number of frames,
the same boot digest, the same digests every `--digest-every` frames, the same history fold, the same frames for the host's
restart and its save and load of the match's state, the tier both sides played on. With `--seats 3` or `4` the host waits for
that many players and this PC runs every guest, each a process of its own with its own scripted pad, each compared with the
host: three or four seats across the two PCs. Both games run hidden (SDL's dummy video
and audio drivers) with scripted pads (pseudo-random, held a few frames, fixed by the seat), so they leave their title screen
and diverge at once if one input differs. Nothing here measures a duration or a latency; `--lag-ms` holds what this PC sends
(a far player), as the room command's option does.

The two sides are also commands of their own (`side host`, `side guest`), which `run` starts; they use the room command's
code (`retrorecomp.netplay.room_cli`) under its `tests` switch, which this tool alone sets: scripted pads, a hidden game and
the worker's whole result. The remote PC needs the same converter version (its tools folder included) and the inbound rule
for its Python on the room's port, which the player adds by hand (never this tool). No ROM is copied by this tool: each
side names its own export of the same dump.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.netplay import room_cli, seat_map  # noqa: E402

HIDDEN = {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy', 'SDL_RENDER_VSYNC': '0'}
RESULT_TAG = 'acceptance-json: '
KEPT = ('outcome', 'detail', 'tier', 'delay', 'history_frames', 'history_digest', 'boot_digest', 'digests', 'restarts', 'states',
        'desync', 'prediction_cap', 'hello')


def script(seat: int, args) -> dict:
    """The scripted pad of a seat, with the host's restart and its save and load of the match's state as record bits."""
    spec = {'kind': 'random', 'seat': seat, 'hold': args.hold, 'sticks': getattr(args, 'sticks', False)}
    if seat == 0:
        at = {}
        if args.restart_at:
            at[str(args.restart_at)] = seat_map.SYS_RESTART
        if args.save_at:
            at[str(args.save_at)] = seat_map.SYS_STATE_SAVE
        if args.load_at:
            at[str(args.load_at)] = seat_map.SYS_STATE_LOAD
        if at:
            spec['system_at'] = at
    return spec


def side(args) -> int:
    out = Path(args.out or tempfile.mkdtemp(prefix='rr-acceptance-'))
    out.mkdir(parents=True, exist_ok=True)
    common = ['--game', str(args.game), '--machine', args.machine, '--log-dir', str(out), '--name',
              'Host' if args.role == 'host' else 'Guest' if args.seat == 1 else f'Guest {args.seat}']
    if args.lag_ms:
        common += ['--lag-ms', str(args.lag_ms), '--jitter-ms', str(args.jitter_ms)]
    if args.role == 'host':
        argv = ['host', '--address', args.address, '--tier', args.tier, '--digest-every', str(args.digest_every),
                '--join-timeout', '120', '--guests', str(args.seats - 1), *common]
    else:
        text = args.invitation or sys.stdin.readline().strip()
        argv = ['guest', text, *common]
    parsed = room_cli._parser().parse_args(argv)
    settings = {'local_source': script(0 if args.role == 'host' else args.seat, args), 'last_frame': args.frames}
    results: list = []
    run = room_cli.run_host if args.role == 'host' else room_cli.run_guest
    code = run(parsed, True, settings, HIDDEN, results)
    result = results[0] if results else {}
    room_cli.say(RESULT_TAG + json.dumps({name: result.get(name) for name in KEPT}))
    return code


def compare(host: dict, guests: list[dict], args) -> list[str]:
    problems = []
    labelled = [('host', host)] + [(f'guest {n}' if len(guests) > 1 else 'guest', g) for n, g in enumerate(guests, 1)]
    for label, result in labelled:
        if result.get('outcome') != 'ended':
            problems.append(f'{label}: outcome {result.get("outcome")} {result.get("detail") or ""}'.rstrip())
        if result.get('history_frames') != args.frames:
            problems.append(f'{label}: {result.get("history_frames")} frames of {args.frames}')
    for label, guest in labelled[1:]:
        for name in ('boot_digest', 'history_digest', 'digests', 'restarts', 'states', 'tier'):
            if host.get(name) != guest.get(name):
                problems.append(f'{name} differs: host {host.get(name)!r:.80} {label} {guest.get(name)!r:.80}')
    if not host.get('digests'):
        problems.append('no digest was compared')
    wanted_states = (1 if args.save_at else 0) + (1 if args.load_at else 0)
    if len(host.get('states') or []) != wanted_states:
        problems.append(f'the match\'s state: {host.get("states")} (wanted {wanted_states})')
    if len(host.get('restarts') or []) != (1 if args.restart_at else 0):
        problems.append(f'restarts: {host.get("restarts")}')
    if args.tier == 'rollback' and host.get('tier') != 'rollback':
        problems.append(f'tier {host.get("tier")}, rollback asked')
    return problems


def run(args) -> int:
    """The host on the remote PC, the guest here; the verdict and both results in the report."""
    flags = ['--frames', str(args.frames), '--machine', args.machine, '--hold', str(args.hold), '--seats', str(args.seats),
             '--digest-every', str(args.digest_every), '--tier', args.tier] + (['--sticks'] if args.sticks else [])
    for name in ('save_at', 'load_at', 'restart_at'):
        if getattr(args, name):
            flags += ['--' + name.replace('_', '-'), str(getattr(args, name))]
    # The host's logs go beside its converter, where they can be read after a run.
    if args.remote_posix:          # a Linux PC: its shell, its separators, and SDL's dummy drivers in its environment
        remote_out = args.remote_out or (args.remote_root.rstrip('/') + '/../acceptance-logs/host')
        remote = (f'cd "{args.remote_root}" && "{args.remote_python}" -B tools/netplay_lan_acceptance.py side host '
                  f'--game "{args.remote_game}" --address {args.remote_address} --out "{remote_out}" ' + ' '.join(flags))
    else:
        remote_out = args.remote_out or (args.remote_root.rstrip('\\') + '\\..\\acceptance-logs\\host')
        remote = (f'cd /d "{args.remote_root}" && "{args.remote_python}" -B tools\\netplay_lan_acceptance.py side host '
                  f'--game "{args.remote_game}" --address {args.remote_address} --out "{remote_out}" ' + ' '.join(flags))
    print('remote host:', args.remote)
    host_lines: list[str] = []
    invitation = threading.Event()
    found = {}
    process = subprocess.Popen(['ssh', '-T', args.remote, remote], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')

    def read():
        for line in process.stdout:
            line = line.rstrip('\n')
            host_lines.append(line)
            if line.startswith('invitation: '):
                found['invitation'] = line[len('invitation: '):].strip()
                invitation.set()
            elif not line.startswith(RESULT_TAG):
                print('  [host]', line)
        invitation.set()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    if not invitation.wait(120) or 'invitation' not in found:
        process.kill()
        print('FAIL: the remote host printed no invitation')
        return 1
    # Each guest is a process of its own, as a player's converter is, in its own log folder and with its own scripted pad.
    # The room lets one address hold two connections in their handshake at most (`limits.Admission`): guests from this one
    # PC arrive a few seconds apart, as players do.
    guests = []
    for seat in range(1, args.seats):
        if seat > 1:
            time.sleep(3)
        guest_command = [sys.executable, '-B', str(Path(__file__).resolve()), 'side', 'guest', '--game', str(args.game),
                         '--invitation', found['invitation'], '--frames', str(args.frames), '--machine', args.machine,
                         '--hold', str(args.hold), '--digest-every', str(args.digest_every), '--tier', args.tier,
                         '--seats', str(args.seats), '--seat', str(seat)]
        if args.out:
            guest_command += ['--out', str(args.out if args.seats == 2 else args.out / f'guest{seat}')]
        if args.lag_ms:
            guest_command += ['--lag-ms', str(args.lag_ms), '--jitter-ms', str(args.jitter_ms)]
        if args.sticks:
            guest_command += ['--sticks']
        guests.append(subprocess.Popen(guest_command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace'))
    guest_lines: list[list[str]] = []
    for seat, guest in enumerate(guests, 1):
        label = 'guest' if args.seats == 2 else f'guest {seat}'
        try:
            stdout, stderr = guest.communicate(timeout=max(300, args.frames / 20 + 240))
        except subprocess.TimeoutExpired:
            guest.kill()
            stdout, stderr = guest.communicate()
        lines = stdout.splitlines()
        guest_lines.append(lines)
        for line in lines:
            if not line.startswith(RESULT_TAG):
                print(f'  [{label}]', line)
        if guest.returncode and stderr:
            print(f'  [{label} stderr]', stderr[-2000:])
    try:
        process.wait(timeout=180)
    except subprocess.TimeoutExpired:      # a host that never ended: its own result is missing, the verdict says so
        process.kill()
        process.wait()
    reader.join(10)

    def result_of(collected):
        for line in collected:
            if line.startswith(RESULT_TAG):
                return json.loads(line[len(RESULT_TAG):])
        return {}
    host, results = result_of(host_lines), [result_of(lines) for lines in guest_lines]
    problems = compare(host, results, args)
    verdict = 'PASS' if not problems else 'FAIL'
    summary = (f'{verdict}: {args.seats} seats, {args.frames} frames, tier {host.get("tier")}, delay {host.get("delay")}, '
               f'{len(host.get("digests") or {})} digests compared, restarts {host.get("restarts")}, '
               f'match state {host.get("states")}')
    print(summary)
    for problem in problems:
        print('  -', problem)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({'verdict': verdict, 'problems': problems, 'seats': args.seats, 'host': host,
                                           'guest': results[0] if len(results) == 1 else results},
                                          indent=1) + '\n', encoding='utf-8')
    return 0 if not problems else 1


def main() -> int:
    # A remote PC's messages may hold characters this console cannot show (a French Windows error): never a reader that dies.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(errors='replace')
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('run', 'side'):
        p = sub.add_parser(name)
        p.add_argument('--game', type=Path, required=True)
        p.add_argument('--frames', type=int, default=3000)
        p.add_argument('--machine', default=room_cli.DEFAULT_MACHINE)
        p.add_argument('--hold', type=int, default=4)
        p.add_argument('--digest-every', type=int, default=60)
        p.add_argument('--tier', choices=('auto', 'delay', 'rollback'), default='auto')
        p.add_argument('--save-at', type=int, default=0)
        p.add_argument('--load-at', type=int, default=0)
        p.add_argument('--restart-at', type=int, default=0)
        p.add_argument('--lag-ms', type=float, default=0.0)
        p.add_argument('--jitter-ms', type=float, default=0.0)
        p.add_argument('--out', type=Path)
        p.add_argument('--sticks', action='store_true', help='the scripted pads move the sticks too')
        p.add_argument('--seats', type=int, choices=(2, 3, 4), default=2, help='players in the match: the host and its guests')
    run_parser = sub.choices['run']
    run_parser.add_argument('--remote', required=True, help='USER@HOST of the PC that hosts (SSH, its key already trusted)')
    run_parser.add_argument('--remote-root', required=True, help='its converter folder')
    run_parser.add_argument('--remote-game', required=True, help='its copy of the same export')
    run_parser.add_argument('--remote-address', required=True, help='its address on the local network')
    run_parser.add_argument('--remote-python', default='python')
    run_parser.add_argument('--report', type=Path)
    run_parser.add_argument('--remote-out', help='the host side log folder on the remote PC (default: beside its converter)')
    run_parser.add_argument('--remote-posix', action='store_true', help='the remote PC is Linux (a POSIX shell): Windows and Linux in one match')
    side_parser = sub.choices['side']
    side_parser.add_argument('role', choices=('host', 'guest'))
    side_parser.add_argument('--address', help='host: its own address on the local network')
    side_parser.add_argument('--invitation', help='guest: the invitation (else one line on the standard input)')
    side_parser.add_argument('--seat', type=int, default=1, help='guest: the number its scripted pad is drawn from')
    args = parser.parse_args()
    return run(args) if args.command == 'run' else side(args)


if __name__ == '__main__':
    raise SystemExit(main())
