"""A real converted game in a multiplayer session on one PC: N copies, N worker processes (each with its lockstep driver),
joined through the host (a star) by the in-memory link, which this process carries the workers' packets through.

    python -B tools/netplay_game_smoke.py GAME.exe [--seats 2] [--frames 3000] [--latency MS] [--jitter MS]
                                          [--loss RATE] [--delay FRAMES] [--output DIR]

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

from retrorecomp.netplay import LinkSimulator, WorkerProcess   # noqa: E402

HIDDEN = {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy', 'SDL_RENDER_VSYNC': '0',
          'SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT': '0x0000/0x0000'}
NAMES = ('Arthur', 'Nadia', 'Helene', 'Karl')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('game', type=Path)
    parser.add_argument('--seats', type=int, default=2)
    parser.add_argument('--frames', type=int, default=3000)
    parser.add_argument('--latency', type=float, default=0.0, help='one way, milliseconds')
    parser.add_argument('--jitter', type=float, default=0.0)
    parser.add_argument('--loss', type=float, default=0.0)
    parser.add_argument('--delay', type=int, help='input delay in frames (default: measured and chosen by the host)')
    parser.add_argument('--digest-every', type=int, default=60)
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--limit', type=float, default=0.0, help='seconds before the games are ended (default: from --frames)')
    parser.add_argument('--output', type=Path, default=ROOT / '.build/netplay-game-smoke')
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
        settings = dict(seat=seat, seats=args.seats, names=list(NAMES[:args.seats]), digest_every=args.digest_every,
                        last_frame=args.frames, local_source={'kind': 'random', 'seat': seat})
        if seat == 0 and args.delay:
            settings['delay'] = args.delay
        config = dict(game=dict(exe=str(copy), cwd=str(folder), env=HIDDEN, stdout=str(folder / 'stdout.txt'),
                                stderr=str(folder / 'stderr.txt')), settings=settings)
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
        if worker.outcome != 'ended':
            problems.append(f'{label}: {worker.outcome} {worker.detail}')
        if worker.boot_digest is None or worker.boot_digest != first.boot_digest:
            problems.append(f'{label}: boot digest {worker.boot_digest} against seat 1: {first.boot_digest}')
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
    for problem in problems:
        print('PROBLEM:', problem)
    print('PASS' if not problems else 'FAIL', f'({args.seats} seats, {args.frames} frames, digest every {args.digest_every})')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
