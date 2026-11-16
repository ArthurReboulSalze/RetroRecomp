"""The converter's delay-lockstep driver against real games in sessions, ROM-free (retrorecomp/netplay).

    python -B tools/netplay_lockstep_selftest.py [--output DIR] [--only NAME]

Two, three or four copies of the fake machine of tools/hostkit_session/fake.c (built by
tools/hostkit_session_selftest.py: its state folds the four ports' words of every frame) are each driven by their own
`LockstepDriver` through real anonymous pipes, and the drivers are joined by the in-memory link simulator: no socket,
no port. Every seat has a scripted pad (a hidden game has no player) that changes every frame, so a frame run on a
guessed input would show in the history.

Scenarios: links at 0 ms, at 30 ms with jitter, reordering and duplicates, with 2 % loss, three and four seats; a
pause from one seat's menu, a pause the host resumes; the host stopping; two games forced out of step; a pipe lost; a
seat gone silent; and three slow links on a 60 Hz machine (one seat at 120 ms, everyone at 150 ms, a seat silent for
2 s), where the host chooses the delay from what the seats measured.

"In step" means: every seat's history of port words is the same and is the scripts shifted by the delay, every
game's final digest is the fold of that history, and the digests the games gave during the match are equal. The
counts printed (late frames, waits) are events, not durations: nothing here measures speed. Every scenario has a
time limit, after which its games are ended and it fails. Needs the C toolchain and the pinned static SDL2 of
`.deps`; nothing is written outside DIR (default .build/netplay-lockstep-selftest). About a minute.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import re
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.netplay import LinkSimulator, LockstepDriver, SessionGame, Settings   # noqa: E402
from retrorecomp.netplay import input_records as wire                                   # noqa: E402
from retrorecomp.netplay import session_pipe as pipe                                    # noqa: E402

_spec = importlib.util.spec_from_file_location('hostkit_session_selftest', ROOT / 'tools/hostkit_session_selftest.py')
fake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake)

NAMES = ('Arthur', 'Nadia', 'Hélène', 'Karl')
HIDDEN = {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy', 'SDL_RENDER_VSYNC': '0'}


def pad(seat: int, frame: int) -> int:
    """A seat's scripted pad word: different for every seat, different on every frame."""
    return (frame * (7 + 6 * seat) + 0x31 * (seat + 1)) & 0xff


def script(seat: int, pause_from: int | None = None):
    def source(frame, _word, system):
        if pause_from is not None and frame >= pause_from:
            system |= pipe.SYS_PAUSE
        return pad(seat, frame), system
    return source


def expected(seats: int, delay: int, frames: int) -> list[tuple]:
    return [tuple(pad(seat, frame - delay) if frame >= delay else 0 for seat in range(seats)) for frame in range(frames)]


def fold(history) -> int:
    return fake.digest_of([tuple(words) + (0,) * (4 - len(words)) for words in history])


class Match:
    """N hidden games, N drivers, one simulated link; ended, whatever happens, within its time limit."""

    def __init__(self, executable: Path, out: Path, name: str, seats: int, *, seed: int = 1, link: dict | None = None,
                 hz: int | None = None, env: dict | None = None, per_seat: dict | None = None, **settings):
        self.name, self.seats = name, seats
        self.link = LinkSimulator(seats, seed=seed, **(link or {}))
        self.games, self.drivers, self.folders = [], [], []
        for seat in range(seats):
            folder = out / name / f'seat{seat + 1}'
            folder.mkdir(parents=True, exist_ok=True)
            environment = dict(HIDDEN)
            if hz:
                environment['SESSION_FAKE_HZ'] = str(hz)
            environment.update((env or {}).get(seat, {}))
            game = SessionGame(executable, cwd=folder, env=environment, stdout=folder / 'stdout.txt',
                               stderr=folder / 'stderr.txt')
            values = dict(seat=seat, seats=seats, names=NAMES[:seats], options='speed=1', local_source=script(seat))
            values.update(settings)
            values.update((per_seat or {}).get(seat, {}))
            self.games.append(game)
            self.folders.append(folder)
            self.drivers.append(LockstepDriver(game, self.link.endpoint(seat), Settings(**values)))

    def start(self):
        for driver in self.drivers:
            driver.start()
        return self

    def finish(self, limit: float) -> None:
        until = time.monotonic() + limit
        try:
            late = [driver.seat + 1 for driver in self.drivers if not driver.join(max(0.0, until - time.monotonic()))]
            if late:
                where = '; '.join(f'seat {d.seat + 1}: {d._phase}, delay {d.delay}, next frame {d.next_run}, game at '
                                  f'{d.game_frame}, records held {[len(r) for r in d._records]}, paused {d.paused}, '
                                  f'{d.outcome} {d.detail}' for d in self.drivers)
                raise AssertionError(f'{self.name}: seats {late} did not end within {limit:g} s ({where})')
        finally:
            for game in self.games:
                if game.alive():
                    game.process.kill()
            self.link.close()

    def result(self, seat: int) -> dict:
        text = (self.folders[seat] / 'stdout.txt').read_text(encoding='utf-8', errors='replace')
        found = re.search(r'RESULT (.*)', text)
        return dict(item.split('=') for item in found.group(1).split()) if found else {}

    def stderr(self, seat: int) -> str:
        return (self.folders[seat] / 'stderr.txt').read_text(encoding='utf-8', errors='replace')

    def counts(self, key: str) -> str:
        return '/'.join(str(driver.stats[key]) for driver in self.drivers)


def in_step(match: Match, frames: int, delay: int | None = None) -> str:
    """Every seat ran the same `frames` frames with the same words, and the games agree with the drivers."""
    drivers = match.drivers
    for driver in drivers:
        assert driver.outcome == 'ended', (match.name, driver.seat, driver.outcome, driver.detail)
        assert driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED, (driver.exit_code, driver.exit_reason)
    delays = {driver.delay for driver in drivers}
    assert len(delays) == 1, delays
    used = delays.pop()
    assert delay is None or used == delay, (used, delay)
    wanted = expected(match.seats, used, frames)
    for driver in drivers:
        assert driver.history == wanted, f'{match.name}: seat {driver.seat + 1} ran other words than the scripts'
        result = match.result(driver.seat)
        assert int(result['frames']) == frames and int(result['live']) == frames and int(result['silent']) == 0, result
        assert int(result['digest'], 16) == fold(wanted), f'{match.name}: seat {driver.seat + 1}: the game ran other words'
        assert int(result['effects_off']) == (frames if driver.seat else 0), result      # a guest writes no save
        assert driver.digests == drivers[0].digests, 'the digests differ between seats'
        assert driver.desync is None and driver.stats['final_compared'], (driver.desync, driver.stats)
    every = drivers[0].settings.digest_every
    assert len(drivers[0].digests) == frames // every + (1 if frames % every else 0), drivers[0].digests.keys()
    assert drivers[0].digests[frames - 1] == fold(wanted)
    return (f'{frames} frames, delay {used}, {len(drivers[0].digests)} digests equal on {match.seats} seats; '
            f'late frames {match.counts("late_frames")}, waits {match.counts("waits")}')


# ---- the scenarios: (name, time limit in seconds, function(executable, out) -> line) ----

def plain(name, seats, frames, limit, delay, **link):
    def scenario(executable, out):
        match = Match(executable, out, name, seats, link=link, delay=delay, last_frame=frames, digest_every=50).start()
        match.finish(limit)
        lost = match.link.counts
        line = in_step(match, frames, delay)
        if link.get('loss') or link.get('duplicate') or link.get('reorder'):
            assert (not link.get('loss') or lost['lost']) and (not link.get('duplicate') or lost['duplicated'])
            line += f'; packets lost {lost["lost"]}, repeated {lost["duplicated"]}, held back {lost["reordered"]} of {lost["sent"]}'
        return line
    return name, limit, scenario


def pause_by_menu(executable, out):
    # Seat 2 opens Help during frame 39: its LOCAL of frame 40 asks for a pause, which every seat applies before frame
    # 40 + D; the menu closes by itself thirty iterations later and the same seat's word resumes everyone.
    match = Match(executable, out, 'pause-menu', 2, delay=2, last_frame=200, digest_every=50,
                  env={1: {'SESSION_FAKE_MENU_AT': '40'}}).start()
    match.finish(40)
    for driver in match.drivers:
        assert driver.pauses == [(42, 1, 1)], (driver.seat, driver.pauses)
    return 'paused by seat 2 before frame 42 on both seats, resumed by seat 2; ' + in_step(match, 200, 2)


def pause_host_resumes(executable, out):
    # Seat 3 holds a pause from its frame 60 on. Seat 2 may not resume it; the host may.
    match = Match(executable, out, 'pause-host', 3, delay=3, last_frame=200, digest_every=50,
                  per_seat={2: {'local_source': script(2, pause_from=60)}}).start()
    try:
        for driver in match.drivers:
            assert driver.wait_for(lambda d: d.paused is not None, 20), f'seat {driver.seat + 1} never paused'
            assert driver.paused == (63, [2]), driver.paused
        match.drivers[1].resume()
        assert match.drivers[1].wait_for(lambda d: d.stats['resumes_refused'] == 1, 10)
        threading.Event().wait(0.3)
        assert all(driver.paused is not None and driver.next_run == 63 for driver in match.drivers), 'a frame ran while paused'
        match.drivers[0].resume()
    finally:
        match.finish(40)
    for driver in match.drivers:
        assert driver.pauses == [(63, 2, 0)], (driver.seat, driver.pauses)
    return 'paused by seat 3 before frame 63 on three seats, seat 2 refused, resumed by the host; ' + in_step(match, 200, 3)


def host_stops(executable, out):
    match = Match(executable, out, 'host-stops', 3, delay=2, digest_every=50).start()
    try:
        assert match.drivers[0].reached(150, 20), 'frame 150 never came'
        match.drivers[0].stop()
    finally:
        match.finish(40)
    shortest = min(len(driver.history) for driver in match.drivers)
    assert shortest >= 150
    for driver in match.drivers:
        assert driver.outcome == 'ended' and driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED, \
            (driver.seat, driver.outcome, driver.exit_code, driver.exit_reason)
        assert driver.history[:shortest] == expected(3, 2, shortest)
        result = match.result(driver.seat)
        assert int(result['frames']) == len(driver.history) and int(result['digest'], 16) == fold(driver.history), result
        assert 'stopped by Retro-Recomp (3)' in match.stderr(driver.seat)
    return f'the host stopped after frame 150: three games stopped (match over), {shortest} common frames in step'


def forced_desync(executable, out):
    # Seat 2's driver tells its own game another word for player 1 at frame 77: the digests of frame 99 differ.
    def tamper(frame, words):
        return (words[0] ^ 0x40, *words[1:]) if frame == 77 else words
    match = Match(executable, out, 'desync', 3, delay=2, digest_every=50, drop_after=8.0,
                  per_seat={1: {'words_filter': tamper}}).start()
    match.finish(40)
    found = [driver.desync for driver in match.drivers if driver.desync]
    assert found and all(item[0] == 99 for item in found), found
    for driver in match.drivers:
        assert driver.outcome == 'desync', (driver.seat, driver.outcome, driver.detail)
        assert driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED
        assert 'stopped by Retro-Recomp (2)' in match.stderr(driver.seat)
        assert 50 - 1 in driver.digests and len(driver.history) < 400, len(driver.history)
    assert match.drivers[0].digests[49] == match.drivers[1].digests[49] == match.drivers[2].digests[49]
    return f'a word changed at frame 77 on seat 2: found at the digest of frame 99 by {len(found)} seats, three games stopped (out of step)'


def pipe_lost(executable, out):
    # Seat 2's worker loses its game: the pipe closes, that game says so and closes by itself, the others are stopped.
    match = Match(executable, out, 'pipe-lost', 3, delay=2, digest_every=50).start()
    try:
        assert match.drivers[1].reached(100, 20), 'frame 100 never came'
        match.games[1].close_pipe()
    finally:
        match.finish(40)
    outcomes = [driver.outcome for driver in match.drivers]
    assert outcomes == ['seat_left', 'pipe_lost', 'seat_left'], (outcomes, [driver.detail for driver in match.drivers])
    # (the game cannot say EXIT once its pipe is broken: the closed pipe is the only sign the worker gets)
    assert match.drivers[1].exit_reason is None and 'pipe is closed' in match.stderr(1)
    for driver in match.drivers:
        assert driver.exit_code == 0, (driver.seat, driver.exit_code)
        result = match.result(driver.seat)
        assert int(result['digest'], 16) == fold(driver.history[:int(result['frames'])]), result
    assert all(match.drivers[seat].exit_reason == pipe.EXIT_STOPPED for seat in (0, 2))
    return 'seat 2 lost its pipe: its game closed by itself, the two others were stopped, every game left with code 0'


def seat_silent(executable, out):
    # Seat 2 is cut off for good: the games wait (notice), then the seat is counted gone and the match ends.
    match = Match(executable, out, 'seat-silent', 2, delay=2, digest_every=50, waiting_after=0.3, drop_after=1.5).start()
    try:
        assert match.drivers[0].reached(100, 20), 'frame 100 never came'
        match.link.silence(1, True)
    finally:
        match.finish(40)
    for driver in match.drivers:
        assert driver.outcome == 'seat_silent', (driver.seat, driver.outcome, driver.detail)
        assert driver.stats['waits'] == 1 and driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED, driver.stats
        result = match.result(driver.seat)
        assert int(result['digest'], 16) == fold(driver.history), result
    return f'seat 2 silent: one wait on each seat, both games stopped after 1.5 s of silence (waits {match.counts("waits")})'


FRAME_60 = 1000.0 / 60.0


def slow(name, seats, frames, limit, rules, worst):
    """A 60 Hz machine; the host chooses the delay from what the seats measured."""
    def scenario(executable, out):
        match = Match(executable, out, name, seats, hz=60, last_frame=frames, digest_every=60, waiting_after=0.5)
        rules(match.link)
        match.start()
        match.finish(limit)
        line = in_step(match, frames)
        delay = match.drivers[0].delay
        assert wire.covers(delay, worst[0], worst[1], FRAME_60), (delay, worst)
        assert all(driver.stats['waits'] == 0 for driver in match.drivers), match.counts('waits')
        measured = ', '.join(f'{driver.measured[0]:.0f}+{driver.measured[1]:.0f}' for driver in match.drivers)
        return f'delay {delay} chosen (covers {worst[0]} ms +- {worst[1]} ms; measured one-way+jitter ms per seat: {measured}); {line}'
    return name, limit, scenario


def burst(executable, out):
    # 20 ms links; seat 2 silent for 2 s from frame 90: every game waits with a notice, then goes on by itself.
    match = Match(executable, out, 'lag-burst', 2, hz=60, last_frame=300, digest_every=60, waiting_after=0.5,
                  drop_after=8.0, link={'latency_ms': 20.0}).start()
    try:
        assert match.drivers[0].reached(90, 30), 'frame 90 never came'
        match.link.silence(1, True)
        threading.Event().wait(2.0)
        match.link.silence(1, False)
    finally:
        match.finish(60)
    line = in_step(match, 300)
    for driver in match.drivers:
        assert driver.stats['waits'] == 1, (driver.seat, driver.stats)
    return f'seat 2 silent for 2 s: one wait with its notice on each seat, then resumed; {line}'


def one_far(link):
    link.set_seat(2, latency_ms=120.0, jitter_ms=20.0)


def all_far(link):
    for seat in range(link.seats):
        link.set_seat(seat, latency_ms=150.0)


SCENARIOS = [
    plain('two-seats-0ms', 2, 600, 40, 1),
    plain('two-seats-30ms-jitter', 2, 600, 40, 15, latency_ms=30.0, jitter_ms=10.0, reorder=0.02, duplicate=0.02),
    plain('two-seats-loss', 2, 1000, 40, 2, latency_ms=2.0, loss=0.02),
    plain('three-seats-loss-jitter', 3, 500, 40, 6, latency_ms=10.0, jitter_ms=5.0, loss=0.02),
    plain('four-seats-0ms', 4, 500, 40, 1),
    ('pause-menu', 40, pause_by_menu),
    ('pause-host', 40, pause_host_resumes),
    ('host-stops', 40, host_stops),
    ('desync', 40, forced_desync),
    ('pipe-lost', 40, pipe_lost),
    ('seat-silent', 40, seat_silent),
    slow('lag-one-seat-120ms', 3, 240, 60, one_far, (120.0, 20.0)),
    slow('lag-all-150ms', 2, 240, 60, all_far, (150.0, 0.0)),
    ('lag-burst', 60, burst),
]


def run_checks(out: Path, only: str | None = None) -> tuple[int, str, float]:
    started = time.perf_counter()
    lines = []
    try:
        executable = fake.build(ROOT / '.build/hostkit-session-selftest')      # the build of the session's own check
        for name, _limit, scenario in SCENARIOS:
            if only and only not in name:
                continue
            lines.append(f'{name}: {scenario(executable, out)}')
    except Exception as error:   # report, do not hide
        import traceback
        return 1, '\n'.join(lines) + f'\nFAIL: {error}\n{traceback.format_exc()}', time.perf_counter() - started
    return 0, '\n'.join(lines) + f'\nPASS: {len(lines)} scenarios', time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/netplay-lockstep-selftest')
    parser.add_argument('--only', help='run the scenarios whose name contains this')
    args = parser.parse_args()
    reason = fake.ready()
    if reason:
        print('skipped:', reason)
        return 0
    code, output, seconds = run_checks(args.output.resolve(), args.only)
    print(f'exit {code}, {seconds:.1f} s\n{output.strip()}')
    return code


if __name__ == '__main__':
    sys.exit(main())
