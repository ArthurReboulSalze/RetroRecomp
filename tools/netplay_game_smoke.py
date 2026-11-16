"""A real converted game in a multiplayer session on one PC: N copies, N lockstep drivers, the in-memory link.

    python -B tools/netplay_game_smoke.py GAME.exe [--seats 2] [--frames 3000] [--latency MS] [--jitter MS]
                                          [--loss RATE] [--delay FRAMES] [--output DIR]

Not part of the test suite: it needs a game the player converted (never in the repository). Each seat gets its own
copy of the executable in its own folder under DIR (default .build/netplay-game-smoke), so the copies share no file.
The games run hidden (SDL's dummy video and audio drivers: no window, no sound device) and are ended by the session's
STOP, never as a test run. Nothing is opened on the network: the seats are joined by `LinkSimulator`.

Every seat has a scripted pad (pseudo-random, held a few frames, fixed by the seat's number), so the games leave their
title screen and diverge at once if one input differs. The check: every seat was told to run the same port words for
every frame, and the digests the games gave every `--digest-every` frames are equal on all seats. It prints counts
(frames, digests, late frames, waits), never a duration or a speed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import random
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.netplay import LinkSimulator, LockstepDriver, SessionGame, Settings   # noqa: E402

HIDDEN = {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy', 'SDL_RENDER_VSYNC': '0'}
NAMES = ('Arthur', 'Nadia', 'Helene', 'Karl')
HOLD = 12       # frames a scripted pad word is held


def script(seat: int):
    def source(frame, _word, system):
        return random.Random(seat * 100003 + frame // HOLD).getrandbits(8), system
    return source


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
    games, drivers, folders = [], [], []
    for seat in range(args.seats):
        folder = out / f'seat{seat + 1}'
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)
        copy = folder / game.name
        shutil.copy2(game, copy)
        session = SessionGame(copy, cwd=folder, env=HIDDEN, stdout=folder / 'stdout.txt', stderr=folder / 'stderr.txt')
        games.append(session)
        folders.append(folder)
        drivers.append(LockstepDriver(session, link.endpoint(seat), Settings(
            seat=seat, seats=args.seats, names=NAMES[:args.seats], delay=args.delay, digest_every=args.digest_every,
            last_frame=args.frames, local_source=script(seat))))
    limit = args.limit or 60.0 + args.frames / 20.0        # generous: a hang, not a speed
    until = time.monotonic() + limit
    try:
        for driver in drivers:
            driver.start()
        late = [driver.seat + 1 for driver in drivers if not driver.join(max(0.0, until - time.monotonic()))]
    finally:
        for session in games:
            if session.alive():
                session.process.kill()
        link.close()
    problems = []
    if late:
        problems.append(f'seats {late} did not end within {limit:g} s')
    first = drivers[0]
    for driver in drivers:
        label = f'seat {driver.seat + 1}'
        hello = driver.hello
        print(f'{label}: {hello.name if hello else "no HELLO"}, {hello.players if hello else "?"} players, caps '
              f'{hello.caps if hello else "?"}, {hello.frame_rate_millihertz / 1000 if hello else 0:g} Hz; outcome '
              f'{driver.outcome} {driver.detail}; delay {driver.delay}; {len(driver.history)} frames, '
              f'{len(driver.digests)} digests ({len(set(driver.digests.values()))} different values); late frames '
              f'{driver.stats["late_frames"]}, waits {driver.stats["waits"]}, pace changes {driver.stats["pace_changes"]}; '
              f'exit code {driver.exit_code}')
        if driver.outcome != 'ended':
            problems.append(f'{label}: {driver.outcome} {driver.detail}')
        if driver.history != first.history:
            problems.append(f'{label}: other port words than seat 1')
        if driver.digests != first.digests:
            differs = sorted(frame for frame in set(driver.digests) | set(first.digests)
                             if driver.digests.get(frame) != first.digests.get(frame))
            problems.append(f'{label}: digests differ from seat 1, first at frame {differs[0]}')
        if len(driver.history) != args.frames or not driver.stats['final_compared']:
            problems.append(f'{label}: {len(driver.history)} frames of {args.frames}, last digest compared: '
                            f'{driver.stats["final_compared"]}')
        if driver.exit_code != 0:
            problems.append(f'{label}: the game left with code {driver.exit_code}')
        tail = (folders[driver.seat] / 'stderr.txt').read_text(encoding='utf-8', errors='replace').strip().splitlines()[-4:]
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
