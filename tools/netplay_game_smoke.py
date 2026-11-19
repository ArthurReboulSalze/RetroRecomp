"""A real converted game in a multiplayer session on one PC: N copies, N worker processes (each with its lockstep driver),
joined through the host (a star) by the in-memory link, which this process carries the workers' packets through.

    python -B tools/netplay_game_smoke.py GAME.exe [--seats 2] [--frames 3000] [--latency MS] [--jitter MS]
                                          [--loss RATE] [--delay FRAMES] [--rollback CAP] [--hold FRAMES] [--restart-at FRAME]
                                          [--save-at FRAME --load-at FRAME]
                                          [--output DIR]

Not part of the test suite: it needs a game the player converted (never in the repository). Each seat gets its own
copy of the executable in its own folder under DIR (default .build/netplay-game-smoke), so the copies share no file.
The games run hidden (SDL's dummy video and audio drivers: no window, no sound device) and are ended by the session's
STOP, never as a test run. Nothing is opened on the network: the workers talk to this process over their pipes and this
process passes the packets through `LinkSimulator`.

Every seat has a scripted pad (pseudo-random, held a few frames, fixed by the seat's number), so the games leave their
title screen and diverge at once if one input differs. The check: the boot digests (state after setup, before frame 0)
are equal, every seat was told to run the same port words for every frame, and the digests the games gave every
`--digest-every` frames are equal on all seats. It prints counts (frames, digests, late frames, waits), never a
duration or a speed.

`--rollback CAP` asks for the rollback tier (`retrorecomp/netplay/rollback.py`) with at most CAP frames run on a prediction;
a game that keeps no snapshot stays on the delay tier and the line of its seat says so. The history compared is then the
confirmed one, the digests are of confirmed frames, and the corrections are counted (how many, how many frames run again,
the deepest, by depth). `--hold` is how many frames the scripted pads keep a word (default 12; smaller: inputs that change
more often, so more wrong guesses). `--restart-at F`: the host restarts the game for everyone (its LOCAL of frame F asks, as its Shift+F1 would): every seat
must restart before the same frame (F plus the delay) and the digests stay equal. `--save-at F --load-at G`: the host saves the
match's state for everyone in its LOCAL of frame F and loads it back in that of G (its F8 and F9): every seat must save and
load before the same frames and the digests stay equal (on the rollback tier keep G - F above the snapshot ring).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.netplay import LinkSimulator, WorkerProcess, seat_map   # noqa: E402

HIDDEN = {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy', 'SDL_RENDER_VSYNC': '0',
          'SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT': '0x0000/0x0000'}
NAMES = ('Arthur', 'Nadia', 'Helene', 'Karl')


def route_events(path: Path) -> list:
    """The rows of a route file ("frame p1 p2 ...", hex words held from that frame; # comments) as [frame, p1, p2, ...]."""
    rows = []
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].split()
        if line:
            rows.append([int(line[0])] + [int(word, 16) for word in line[1:]])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('game', type=Path)
    parser.add_argument('--seats', type=int, default=2)
    parser.add_argument('--frames', type=int, default=3000)
    parser.add_argument('--latency', type=float, default=0.0, help='one way, milliseconds')
    parser.add_argument('--jitter', type=float, default=0.0)
    parser.add_argument('--loss', type=float, default=0.0)
    parser.add_argument('--delay', type=int, help='input delay in frames (default: measured and chosen by the host)')
    parser.add_argument('--rollback', type=int, default=0, help='prediction cap of the rollback tier (default 0: the delay tier)')
    parser.add_argument('--hold', type=int, default=12, help='frames a scripted pad keeps its word')
    parser.add_argument('--restart-at', type=int, default=0, help='the host asks a restart for everyone in its LOCAL of this frame')
    parser.add_argument('--save-at', type=int, default=0, help="the host saves the match's state for everyone in its LOCAL of this frame")
    parser.add_argument('--host-save', type=Path, help="the host's save image: copied into the host seat's folder (--save-name) "
                        'and given to every guest through SAVE_IN, as a room carries it (guests get no file of their own)')
    parser.add_argument('--save-image', type=Path, help='what the guests are handed instead of --host-save, when the machine session '
                        'session image (RrhkMachine.session_save) is not the save file itself')
    parser.add_argument('--save-name', default='', help='the file, relative to a seat folder, that the game reads its save from')
    parser.add_argument('--sticks', action='store_true', help='the scripted pads move the sticks too (a game with sticks)')
    parser.add_argument('--machine', default=None, help='the profile id (gb, gg, gba: a handheld is played in input sharing)')
    parser.add_argument('--sharing', choices=('per_player', 'everyone', 'turns'), default=None,
                        help='the input mode (a handheld plays in input sharing only: everyone by default)')
    parser.add_argument('--options', default='', help='the run-changing options every seat gets in SETUP ("key=value" lines '
                        'separated by ;), as a room pushes the host game\'s')
    parser.add_argument('--load-at', type=int, default=0, help='and loads it back in its LOCAL of this frame')
    parser.add_argument('--digest-every', type=int, default=60)
    parser.add_argument('--route', type=Path, help='a recorded route ("frame p1 p2" lines of hex pad words, # comments): the host '
                        'plays p1, the first guest p2, instead of random words (a game brought to a screen, a save)')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--limit', type=float, default=0.0, help='seconds before the games are ended (default: from --frames)')
    parser.add_argument('--output', type=Path, default=ROOT / '.build/netplay-game-smoke')
    parser.add_argument('--save-digests', type=Path, help='write the delay, digests and history fold of the first seat to this JSON file '
                        '(two runs with the same pads and delay, one on each tier, must give the same)')
    args = parser.parse_args()
    game = args.game.resolve()
    if not game.is_file():
        print('no such game:', game)
        return 2
    out = args.output.resolve()
    link = LinkSimulator(args.seats, seed=args.seed, latency_ms=args.latency, jitter_ms=args.jitter, loss=args.loss)
    workers, folders = [], []
    for seat in range(args.seats):
        folder = out / f'seat{seat + 1}'
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        copy = folder / game.name
        shutil.copy2(game, copy)
        if args.host_save and seat == 0:       # the host plays on its own save file, as a host does
            target = folder / args.save_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.host_save, target)
        script = {'kind': 'random', 'seat': seat, 'hold': args.hold, 'sticks': args.sticks}
        if args.route:   # every seat plays its column of a recorded route instead of random words
            script = {'kind': 'route', 'seat': seat, 'events': route_events(args.route)}
        if seat == 0 and args.restart_at:
            script['system_at'] = {str(args.restart_at): seat_map.SYS_RESTART}     # rides its record of F + delay
        if seat == 0 and (args.save_at or args.load_at):
            script.setdefault('system_at', {})
            if args.save_at:
                script['system_at'][str(args.save_at)] = seat_map.SYS_STATE_SAVE
            if args.load_at:
                script['system_at'][str(args.load_at)] = seat_map.SYS_STATE_LOAD
        settings = dict(seat=seat, seats=args.seats, names=list(NAMES[:args.seats]), digest_every=args.digest_every,
                        options='\n'.join(part for part in args.options.split(';') if part),
                        sharing=seat_map.effective(args.machine, seat_map.BY_NAME[args.sharing or 'per_player']),
                        last_frame=args.frames, local_source=script, keep_history=True, rollback=args.rollback)
        if args.host_save and seat > 0:        # a guest is handed the host's save before its SETUP (session ABI 8)
            settings['save'] = (args.save_image or args.host_save).read_bytes().hex()
        if seat == 0 and args.delay:
            settings['delay'] = args.delay
        config = dict(game=dict(exe=str(copy), cwd=str(folder), env=HIDDEN, stdout=str(folder / 'stdout.txt'),
                                stderr=str(folder / 'stderr.txt')), settings=settings, tests=True)
        worker = WorkerProcess(config, carry=lambda to, data, seat=seat: link.endpoint(seat).send(to, data),
                               log=folder / 'worker.txt')
        link.endpoint(seat).open(lambda source, data, worker=worker: worker.deliver(source, data))
        workers.append(worker)
        folders.append(folder)
    limit = args.limit or 60.0 + args.frames / 20.0        # generous: a hang, not a speed
    until = time.monotonic() + limit
    try:
        for worker in workers:
            worker.start()
        while time.monotonic() < until and not all(worker.done for worker in workers):
            threading.Event().wait(0.1)
        late = [worker.seat + 1 for worker in workers if not worker.done]
    finally:
        for worker in workers:
            worker.cleanup()
        link.close()
    problems = []
    if late:
        problems.append(f'seats {late} did not end within {limit:g} s')
    first = workers[0]
    for worker in workers:
        label = f'seat {worker.seat + 1}'
        hello = worker.hello
        print(f'{label}: {hello["name"] if hello else "no HELLO"}, {hello["players"] if hello else "?"} players, caps '
              f'{hello["caps"] if hello else "?"}, {hello["millihertz"] / 1000 if hello else 0:g} Hz; outcome '
              f'{worker.outcome} {worker.detail}; delay {worker.delay}; boot digest {worker.boot_digest}; '
              f'{len(worker.history)} frames, {len(worker.digests)} digests ({len(set(worker.digests.values()))} different '
              f'values); late frames {worker.stats["late_frames"]}, waits {worker.stats["waits"]}, pace changes '
              f'{worker.stats["pace_changes"]}; game exit code {worker.exit_code}, worker exit code {worker.exit_code_of_process}')
        if args.rollback:
            stats = worker.stats
            print(f'    tier {worker.tier}, prediction cap {args.rollback}: rollbacks {stats["rollbacks"]}, frames run again '
                  f'{stats["rollback_frames"]}, deepest {stats["rollback_depth_max"]}, by depth {list(worker.rollback_depths)}; '
                  f'frames run on a prediction {stats["predicted_frames"]}, waits at the cap {stats["cap_waits"]}, snapshots '
                  f'saved {stats["saves"]}, loaded {stats["loads"]}, digests skipped {stats["digests_skipped"]}')
            if worker.tier == 'rollback' and (stats['rollback_depth_max'] > args.rollback or stats['digests_skipped']):
                problems.append(f'{label}: a correction deeper than the cap, or a digest that could not be asked')
        if worker.outcome != 'ended':
            problems.append(f'{label}: {worker.outcome} {worker.detail}')
        if worker.boot_digest is None or worker.boot_digest != first.boot_digest:
            problems.append(f'{label}: boot digest {worker.boot_digest} against seat 1: {first.boot_digest}')
        if args.restart_at:
            print(f'    restarted before frames {list(worker.restarts)}')
            if list(worker.restarts) != list(first.restarts) or len(worker.restarts) != 1:
                problems.append(f'{label}: restarts {list(worker.restarts)} against seat 1: {list(first.restarts)}')
        if args.save_at or args.load_at:
            print(f"    match's state {[list(item) for item in worker.states]}")
            wanted = (1 if args.save_at else 0) + (1 if args.load_at else 0)
            if list(worker.states) != list(first.states) or len(worker.states) != wanted:
                problems.append(f"{label}: match's state {list(worker.states)} against seat 1: {list(first.states)}")
        if worker.history != first.history:
            problems.append(f'{label}: other port words than seat 1')
        if worker.digests != first.digests:
            differs = sorted(frame for frame in set(worker.digests) | set(first.digests)
                             if worker.digests.get(frame) != first.digests.get(frame))
            problems.append(f'{label}: digests differ from seat 1, first at frame {differs[0]}')
        if len(worker.history) != args.frames or not worker.stats['final_compared']:
            problems.append(f'{label}: {len(worker.history)} frames of {args.frames}, last digest compared: '
                            f'{worker.stats["final_compared"]}')
        if worker.exit_code != 0 or worker.exit_code_of_process != 0:
            problems.append(f'{label}: the game left with code {worker.exit_code}, the worker with {worker.exit_code_of_process}')
        tail = (folders[worker.seat] / 'stderr.txt').read_text(encoding='utf-8', errors='replace').strip().splitlines()[-4:]
        for line in tail:
            print(f'    {line}')
    if len(set(first.digests.values())) < 2:
        problems.append('the digest never changed: the game did not run, or its digest sees nothing')
    print(f'link: {link.counts}')
    if args.save_digests:
        import json
        args.save_digests.write_text(json.dumps({'delay': first.delay, 'frames': len(first.history), 'tier': first.tier,
                                                 'history_digest': first.history_digest, 'boot_digest': first.boot_digest,
                                                 'digests': first.digests}, indent=1, sort_keys=True), encoding='utf-8')
    for problem in problems:
        print('PROBLEM:', problem)
    print('PASS' if not problems else 'FAIL', f'({args.seats} seats, {args.frames} frames, digest every {args.digest_every})')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
