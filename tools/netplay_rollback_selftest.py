"""The rollback tier of the netplay driver against real games in sessions, ROM-free (retrorecomp/netplay/rollback.py).

    python -B tools/netplay_rollback_selftest.py [--output DIR] [--only NAME] [--inproc]

The harness is the delay tier's (tools/netplay_lockstep_selftest.py: copies of the fake machine of
tools/hostkit_session/fake.c, each driven by its own worker process, the packets carried through the in-memory
`LinkSimulator`; no socket, no port). The fake machine keeps snapshots, so a worker asked for rollback (`rollback` = the
prediction cap k) drives it on the rollback tier: a small fixed delay, missing records predicted, corrections as one batch
(LOAD, silent frames, the live frame).

"In step" on this tier: every seat's **confirmed** history of port words is the scripts shifted by the delay (the same on
every seat), every game's final digest is the fold of that history (whatever it ran on predictions in between was
corrected), the digests given during the match (of confirmed frames only) are equal on every seat, each game ran every
frame live exactly once and as many silent frames as its driver counts re-run, and no correction is deeper than the cap.

Scenarios: a local network (0 ms, delay 1) on two and four seats; 30 ms with jitter on two seats, and on four with loss,
reordering and duplicates; 120 +- 20 ms on two seats, and on three with loss (through the host a guest's records travel two
links: beyond the cap, the games wait as on the delay tier); a misprediction storm (pads that change on every frame, so
every guess is wrong); input sharing with turns (the token moves on confirmed records only); a pause the host resumes; two
games forced out of step (found by the digests of confirmed frames); and a machine without snapshots, which stays on the
delay tier when rollback is asked. The counts printed (rollbacks, frames run again, the deepest correction, frames run on a
prediction, waits at the cap) are events, never durations: nothing here measures speed.
"""
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from retrorecomp.netplay import scripted_inputs, session_pipe as pipe      # noqa: E402

_spec = importlib.util.spec_from_file_location('netplay_lockstep_selftest', ROOT / 'tools/netplay_lockstep_selftest.py')
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
fake, Match = base.fake, base.Match

CAP = 8                 # the study's default prediction cap


def held(seat: int, hold: int) -> dict:
    return {'kind': 'pad', 'seat': seat, 'hold': hold}


def expected(seats: int, delay: int, frames: int, hold: int = 1) -> list[tuple]:
    """One controller per player: seat s's record of frame F is its script's pad of frame F - delay (neutral before)."""
    return [tuple(scripted_inputs.pad(seat, (frame - delay) // hold) if frame >= delay else 0 for seat in range(seats))
            for frame in range(frames)]


def stat(driver, key: str) -> int:
    return int(driver.stats[key])


def tier(driver) -> str:
    return base.state_of(driver).get('tier', 'delay')


def counts(match: Match, key: str) -> str:
    return '/'.join(str(stat(driver, key)) for driver in match.drivers)


def rolled(match: Match, frames: int, wanted: list, cap: int = CAP, delay: int | None = None) -> str:
    """Every seat is on the rollback tier, its confirmed history is `wanted`, its game ends in the state that history
    folds to, and the counts of the driver are the counts of the game."""
    drivers = match.drivers
    for driver in drivers:
        assert driver.outcome == 'ended', (match.name, driver.seat, driver.outcome, driver.detail)
        assert driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED, (driver.exit_code, driver.exit_reason)
        assert tier(driver) == 'rollback', (match.name, driver.seat, tier(driver))
    delays = {driver.delay for driver in drivers}
    assert len(delays) == 1 and (delay is None or delays == {delay}), delays
    boots = {driver.boot_digest for driver in drivers}
    assert len(boots) == 1 and None not in boots, f'{match.name}: the boot digests are not one: {boots}'
    final = base.fold(wanted)
    every = drivers[0].config['settings']['digest_every'] if not base.INPROC else drivers[0].settings.digest_every
    for driver in drivers:
        label = f'{match.name}: seat {driver.seat + 1}'
        assert driver.history == wanted, f'{label}: the confirmed history is not the scripts'
        result = match.result(driver.seat)
        silent, again = int(result['silent']), stat(driver, 'rollback_frames')
        assert int(result['frames']) == frames and int(result['live']) == frames, (label, result)
        assert silent == again, f'{label}: the game ran {silent} silent frames, the driver counts {again}'
        assert int(result['digest'], 16) == final, f'{label}: the game does not end in the state of the confirmed history'
        # side effects: off on silent frames for the host, on every frame for a guest (it writes no save)
        assert int(result['effects_off']) == silent + (frames if driver.seat else 0), (label, result)
        assert driver.digests == drivers[0].digests, f'{label}: the digests of confirmed frames differ between seats'
        assert driver.desync is None and driver.stats['final_compared'], (label, driver.desync, dict(driver.stats))
        assert stat(driver, 'rollback_depth_max') <= cap, (label, dict(driver.stats))
        assert stat(driver, 'digests_skipped') == 0, (label, dict(driver.stats))
        depths = list(base.state_of(driver)['rollback_depths'])
        assert sum(depths) == stat(driver, 'rollbacks') and sum(n * count for n, count in enumerate(depths)) == again, depths
    assert len(drivers[0].digests) == frames // every + (1 if frames % every else 0), sorted(drivers[0].digests)
    assert drivers[0].digests[frames - 1] == final
    # every digest given during the match is the fold of the confirmed history up to its frame
    for frame, value in drivers[0].digests.items():
        assert value == base.fold(wanted[:frame + 1]), f'{match.name}: the digest of frame {frame} is not of confirmed frames'
    return (f'{frames} frames, delay {delays.pop()}, cap {cap}, {len(drivers[0].digests)} digests of confirmed frames equal on '
            f'{match.seats} seats and equal to the fold of the confirmed history; per seat: rollbacks {counts(match, "rollbacks")}, '
            f'frames run again {counts(match, "rollback_frames")}, deepest {counts(match, "rollback_depth_max")}, frames run on a '
            f'prediction {counts(match, "predicted_frames")}, waits at the cap {counts(match, "cap_waits")}')


def plain(name, seats, frames, limit, delay, hold=6, hz=60, cap=CAP, **link):
    def scenario(executable, out):
        match = Match(executable, out, name, seats, link=link, hz=hz, delay=delay, rollback=cap, last_frame=frames,
                      digest_every=60, per_seat={seat: {'local_source': held(seat, hold)} for seat in range(seats)}).start()
        match.finish(limit)
        line = rolled(match, frames, expected(seats, delay, frames, hold), cap, delay)
        lost = match.link.counts
        if link.get('loss'):
            assert lost['lost'], lost
            line += f'; packets lost {lost["lost"]} of {lost["sent"]}'
        return line
    return name, limit, scenario


def storm(executable, out):
    # Pads that change on every frame over 120 +- 20 ms: every frame run on a guess is wrong, so every arrival corrects.
    # The corrections stay within the cap and the games still end in the state of the confirmed history.
    frames, delay = 600, 2
    match = Match(executable, out, 'rollback-storm', 2, hz=60, delay=delay, rollback=CAP, last_frame=frames, digest_every=60,
                  link={'latency_ms': 120.0, 'jitter_ms': 20.0}).start()
    match.finish(90)
    line = rolled(match, frames, expected(2, delay, frames), CAP, delay)
    for driver in match.drivers:
        assert stat(driver, 'rollbacks') >= frames // 4, f'a storm of {stat(driver, "rollbacks")} corrections only'
        assert stat(driver, 'rollback_depth_max') >= 3, dict(driver.stats)
    return 'every prediction wrong (pads change on every frame): ' + line


def auto_delay(name, latency, jitter, want):
    def scenario(executable, out):
        # No delay given: the host measures the links and takes the small fixed delay of the tier (1 or 2), not the delay rule.
        frames = 300
        match = Match(executable, out, name, 2, hz=60, rollback=CAP, last_frame=frames, digest_every=60,
                      link={'latency_ms': latency, 'jitter_ms': jitter},
                      per_seat={seat: {'local_source': held(seat, 6)} for seat in range(2)}).start()
        match.finish(60)
        return f'the host measured its link and chose delay {want}; ' + rolled(match, frames, expected(2, want, frames, 6), CAP, want)
    return name, 60, scenario


def shared_turns(executable, out):
    # Turns over a slow link, on the rollback tier: the same requests as the delay tier's scenario. The token moves only on
    # confirmed records, so the confirmed history is the one the rules give, whatever was guessed in between.
    delay, frames = 2, 320
    sys_pass, to_seat3, set_all, set_turns = 0x2, 0x2 | 3 << 8, 0x1000, 0x2000
    scripts = {0: {40: sys_pass, 160: to_seat3, 200: set_all, 260: set_turns}, 1: {80: sys_pass, 220: set_turns, 280: sys_pass},
               2: {60: sys_pass, 120: sys_pass}}
    match = Match(executable, out, 'rollback-shared-turns', 3, hz=60, delay=delay, rollback=CAP, last_frame=frames,
                  digest_every=60, sharing=2, link={'latency_ms': 25.0, 'jitter_ms': 10.0, 'loss': 0.02},
                  per_seat={seat: {'local_source': base.script(seat, system_at=at)} for seat, at in scripts.items()}).start()
    match.finish(90)
    after = delay + 1
    events = [(40 + after, 'token', 1), (80 + after, 'token', 2), (120 + after, 'token', 0), (160 + after, 'token', 2),
              (200 + after, 'mode', 1), (260 + after, 'mode', 2)]
    wanted = base.shared_expected(3, delay, frames, events, mode=2)
    for driver in match.drivers:
        state = base.state_of(driver)
        assert (state['sharing'], state['token']) == ('turns', 2), state
    return 'turns on three seats, the token and the mode moved on confirmed records only; ' + rolled(match, frames, wanted, CAP, delay)


def pause_host_resumes(executable, out):
    # Seat 2 holds a pause from its frame 60 on (its record of frame 62). Each seat pauses once that frame is confirmed,
    # which may be a few frames after it ran; no frame runs while paused; the host resumes; the games end in step.
    delay, frames = 2, 240
    match = Match(executable, out, 'rollback-pause', 2, hz=60, delay=delay, rollback=CAP, last_frame=frames, digest_every=60,
                  link={'latency_ms': 60.0, 'jitter_ms': 10.0},
                  per_seat={0: {'local_source': held(0, 6)}, 1: {'local_source': {**held(1, 6), 'pause_from': 60}}}).start()
    try:
        for driver in match.drivers:
            assert driver.wait_for(lambda d: d.paused is not None, 30), f'seat {driver.seat + 1} never paused'
            assert driver.paused == (62, [1]), driver.paused
        threading.Event().wait(0.5)
        stood = [driver.next_run for driver in match.drivers]
        threading.Event().wait(0.5)
        assert stood == [driver.next_run for driver in match.drivers], 'a frame ran while paused'
        assert all(62 <= at <= 62 + CAP for at in stood), stood
        match.drivers[0].resume()
    finally:
        match.finish(60)
    for driver in match.drivers:
        assert driver.pauses == [(62, 1, 0)], (driver.seat, driver.pauses)
    return (f'the pause asked in the record of frame 62 took effect on its confirmation (the seats stood before frames '
            f'{stood[0]} and {stood[1]}), resumed by the host; ' + rolled(match, frames, expected(2, delay, frames, 6), CAP, delay))


def forced_desync(executable, out):
    # Seat 2's driver tells its own game another word at frame 77, in every mapping of that frame (a correction runs it the
    # same wrong way): the digests of frame 119, taken on confirmed frames, differ, and the match stops for everyone.
    match = Match(executable, out, 'rollback-desync', 3, hz=60, delay=2, rollback=CAP, digest_every=60, drop_after=8.0,
                  link={'latency_ms': 20.0, 'jitter_ms': 5.0},
                  per_seat={1: {'words_filter': {'kind': 'xor', 'frame': 77, 'port': 0, 'mask': 0x40}}}).start()
    match.finish(60)
    found = [driver.desync for driver in match.drivers if driver.desync]
    assert found and all(item[0] == 119 for item in found), found
    for driver in match.drivers:
        assert driver.outcome == 'desync' and tier(driver) == 'rollback', (driver.seat, driver.outcome, driver.detail)
        assert driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED
        assert 'stopped by Retro-Recomp (2)' in match.stderr(driver.seat)
        assert 59 in driver.digests and len(driver.history) < 600, len(driver.history)
    assert match.drivers[0].digests[59] == match.drivers[1].digests[59] == match.drivers[2].digests[59]
    return f'a word changed at frame 77 on seat 2: found at the digest of frame 119 by {len(found)} seats, three games stopped (out of step)'


def without_snapshots(executable, out):
    # A machine that keeps no snapshot: rollback is asked, every seat stays on the delay tier (no frame on a guess, no
    # silent frame), and the delay tier's own check passes.
    env = {seat: {'SESSION_FAKE_NO_SNAPSHOT': '1'} for seat in range(3)}
    match = Match(executable, out, 'rollback-asked-no-snapshot', 3, delay=3, rollback=CAP, last_frame=400, digest_every=50,
                  env=env, link={'latency_ms': 3.0, 'loss': 0.02}).start()
    match.finish(60)
    for driver in match.drivers:
        state = base.state_of(driver)
        assert state['tier'] == 'delay' and not (state['hello']['caps'] & pipe.CAP_SNAPSHOT), state
        assert stat(driver, 'rollbacks') == 0 and stat(driver, 'predicted_frames') == 0, dict(driver.stats)
    return 'the game reports no snapshot: the delay tier, by itself; ' + base.in_step(match, 400, 3)


SCENARIOS = [
    plain('rollback-lan-two-seats', 2, 600, 60, 1),
    plain('rollback-lan-four-seats', 4, 600, 60, 1),
    plain('rollback-two-seats-30ms', 2, 600, 60, 2, latency_ms=30.0, jitter_ms=5.0),
    plain('rollback-four-seats-30ms-loss', 4, 600, 90, 2, latency_ms=30.0, jitter_ms=5.0, loss=0.02, reorder=0.02, duplicate=0.02),
    plain('rollback-two-seats-120ms', 2, 600, 90, 2, latency_ms=120.0, jitter_ms=20.0),
    plain('rollback-three-seats-120ms-loss', 3, 600, 120, 2, latency_ms=120.0, jitter_ms=20.0, loss=0.02),
    ('rollback-storm', 90, storm),
    auto_delay('rollback-delay-chosen-lan', 0.0, 0.0, 1),
    auto_delay('rollback-delay-chosen-far', 40.0, 5.0, 2),
    ('rollback-shared-turns', 90, shared_turns),
    ('rollback-pause', 60, pause_host_resumes),
    ('rollback-desync', 60, forced_desync),
    ('rollback-asked-no-snapshot', 60, without_snapshots),
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
    parser.add_argument('--output', type=Path, default=ROOT / '.build/netplay-rollback-selftest')
    parser.add_argument('--only', help='run the scenarios whose name contains this')
    parser.add_argument('--inproc', action='store_true', help='drivers as threads of this process (no worker processes)')
    args = parser.parse_args()
    base.INPROC = args.inproc
    reason = fake.ready()
    if reason:
        print('skipped:', reason)
        return 0
    code, output, seconds = run_checks(args.output.resolve(), args.only)
    print(f'exit {code}, {seconds:.1f} s\n{output.strip()}')
    return code


if __name__ == '__main__':
    sys.exit(main())
