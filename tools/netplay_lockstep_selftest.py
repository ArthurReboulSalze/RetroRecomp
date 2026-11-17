"""The converter's netplay worker against real games in sessions, ROM-free (retrorecomp/netplay).

    python -B tools/netplay_lockstep_selftest.py [--output DIR] [--only NAME] [--inproc]

Two, three or four copies of the fake machine of tools/hostkit_session/fake.c (built by
tools/hostkit_session_selftest.py: its state folds the four ports' words of every frame) are each driven by their own
**worker process** (`RetroRecomp.py _netplay-worker`, retrorecomp/netplay/worker.py) that owns the game's two anonymous
pipes and a `LockstepDriver`, and talks to this process over its own two pipes (stdin and stdout). The packets between
the seats are carried by this process: each worker hands them out over its pipe and this test side passes them through
the in-memory `LinkSimulator` (latency, jitter, loss) into the pipe of the target worker. No socket, no port, not even
on loopback: the hub is plain Python, in memory. `--inproc` runs the same drivers as threads of this process instead
(faster to debug, not what the suite runs). Every seat has a scripted pad (a hidden game has no player) that changes
every frame, so a frame run on a guessed input would show in the history.

The topology is a star: guests talk to the host only and the host forwards (the checks assert that no packet ever went
from one guest to another). Scenarios: links at 0 ms, at 30 ms with jitter, reordering and duplicates, with 2 % loss,
three and four seats through the host, one mesh run; a boot-digest mismatch that refuses the launch; a pause from one
seat's menu, a pause the host resumes; the host stopping; two games forced out of step; a pipe lost; a seat gone
silent; the converter going away; three slow links on a 60 Hz machine, where the host chooses the delay from what the
seats measured; and time sync: few PACE changes on a link of 120 +- 20 ms, and two game clocks that really differ by
0.5 % (the faster seat slows, the frame gap stays bounded, against a run with time sync off).

"In step" means: every seat's history of port words is the same and is the scripts shifted by the delay, every
game's final digest is the fold of that history, and the digests the games gave during the match are equal. The
counts printed (late frames, waits) are events, not durations: nothing here measures speed. Every scenario has a
time limit, after which its games are ended and it fails. Needs the C toolchain and the pinned static SDL2 of
`.deps`; nothing is written outside DIR (default .build/netplay-lockstep-selftest).
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

from retrorecomp.netplay import LinkSimulator, SessionGame, Settings, WorkerProcess, driver_for      # noqa: E402
from retrorecomp.netplay import input_records as wire                                                # noqa: E402
from retrorecomp.netplay import scripted_inputs, session_pipe as pipe                               # noqa: E402
from retrorecomp.netplay.worker import settings_from                                                 # noqa: E402

_spec = importlib.util.spec_from_file_location('hostkit_session_selftest', ROOT / 'tools/hostkit_session_selftest.py')
fake = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fake)

NAMES = ('Arthur', 'Nadia', 'Hélène', 'Karl')
# A hidden game reads no pad of the PC it runs on (a stray gamepad would open its menu on every copy at once).
HIDDEN = {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy', 'SDL_RENDER_VSYNC': '0',
          'SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT': '0x0000/0x0000'}
INPROC = False          # --inproc: drivers as threads of this process, not worker processes


def pad(seat: int, frame: int) -> int:
    return scripted_inputs.pad(seat, frame)


def script(seat: int, pause_from: int | None = None, menu: bool = False, system_at: dict | None = None) -> dict:
    spec = {'kind': 'pad', 'seat': seat}
    if system_at:
        spec['system_at'] = system_at       # control bits on the LOCAL of a frame: what the worker's request would add
    if pause_from is not None:
        spec['pause_from'] = pause_from
    if menu:
        spec['system'] = 'game'         # the game's own menu is the one that pauses
    return spec


def expected(seats: int, delay: int, frames: int) -> list[tuple]:
    return [tuple(pad(seat, frame - delay) if frame >= delay else 0 for seat in range(seats)) for frame in range(frames)]


def fold(history) -> int:
    return fake.digest_of([tuple(words) + (0,) * (4 - len(words)) for words in history])


# The fake machine's pad bits (tools/hostkit_session/fake.c): Right 1, Left 2, Down 4, Up 8, and four buttons. The kit cancels
# opposite directions held together in every word it is given (rrhk_session.inc `clean_word`), so a game folds the cleaned word.
def kit_clean(word: int) -> int:
    word &= 0xff
    if word & 3 == 3:
        word &= ~3
    if word & 12 == 12:
        word &= ~12
    return word


def shared_expected(seats: int, delay: int, frames: int, events=(), mode: int = 1) -> list[tuple]:
    """The one word of port 0 on every frame of a shared match, written from the rules and not from `seat_map`: seat s's record of
    frame F is its script's pad of frame F - delay (neutral before); in "everyone" (mode 1) the port gets the OR of them, in "turns"
    (mode 2) the token holder's. `events`: (frame, 'token', seat) or (frame, 'mode', mode), each in force from that frame on."""
    token, words, pending = 0, [], sorted(events)
    for frame in range(frames):
        while pending and pending[0][0] <= frame:
            _at, what, value = pending.pop(0)
            if what == 'token':
                token = value
            else:
                mode = value
        record = [pad(seat, frame - delay) if frame >= delay else 0 for seat in range(seats)]
        merged = 0
        for word in record:
            merged |= word
        words.append((merged if mode == 1 else record[token],))
    return words


def describe(driver) -> str:
    return driver.summary() if hasattr(driver, 'summary') else str(driver.snapshot())


class Match:
    """N hidden games, each with its worker process (or driver thread), one simulated link the test side carries the
    workers' packets through; ended, whatever happens, within its time limit."""

    def __init__(self, executable: Path, out: Path, name: str, seats: int, *, seed: int = 1, link: dict | None = None,
                 hz: int | None = None, env: dict | None = None, per_seat: dict | None = None, **settings):
        self.name, self.seats = name, seats
        self.link = LinkSimulator(seats, seed=seed, **(link or {}))
        self.drivers, self.folders, self.games = [], [], []
        for seat in range(seats):
            folder = out / name / f'seat{seat + 1}'
            folder.mkdir(parents=True, exist_ok=True)
            environment = dict(HIDDEN)
            if hz:
                environment['SESSION_FAKE_HZ'] = str(hz)
            environment.update((env or {}).get(seat, {}))
            values = dict(seat=seat, seats=seats, names=list(NAMES[:seats]), options='speed=1', local_source=script(seat), keep_history=True)
            values.update(settings)
            values.update((per_seat or {}).get(seat, {}))
            game = dict(exe=str(executable), cwd=str(folder), env=environment, stdout=str(folder / 'stdout.txt'),
                        stderr=str(folder / 'stderr.txt'))
            self.folders.append(folder)
            if INPROC:
                session = SessionGame(executable, cwd=folder, env=environment, stdout=folder / 'stdout.txt',
                                      stderr=folder / 'stderr.txt')
                self.games.append(session)
                self.drivers.append(driver_for(session, self.link.endpoint(seat), settings_from(values, tests=True)))
            else:
                worker = WorkerProcess(dict(game=game, settings=values, tests=True), carry=self._carry(seat), log=folder / 'worker.txt')
                self.drivers.append(worker)
                self.link.endpoint(seat).open(lambda source, data, worker=worker: worker.deliver(source, data))

    def _carry(self, seat: int):
        return lambda to_seat, data: self.link.endpoint(seat).send(to_seat, data)

    def start(self):
        for driver in self.drivers:
            driver.start()
        return self

    def finish(self, limit: float) -> None:
        until = time.monotonic() + limit
        try:
            while True:
                if all(driver.done for driver in self.drivers):
                    break
                if time.monotonic() >= until:
                    where = '; '.join(describe(driver) for driver in self.drivers)
                    late = [driver.seat + 1 for driver in self.drivers if not driver.done]
                    raise AssertionError(f'{self.name}: seats {late} did not end within {limit:g} s ({where})')
                threading.Event().wait(0.05)
            for driver in self.drivers:         # (in-process drivers are done as soon as their thread is)
                if not INPROC:
                    assert driver.join(10), f'{self.name}: the worker of seat {driver.seat + 1} never exited'
        finally:
            for driver in self.drivers:
                if INPROC:
                    if driver.game.alive():
                        driver.game.process.kill()
                else:
                    driver.cleanup()
            self.link.close()
        if not INPROC:
            for driver in self.drivers:
                assert driver.exit_code_of_process == 0, (
                    f'{self.name}: the worker of seat {driver.seat + 1} exited with {driver.exit_code_of_process}: '
                    + (self.folders[driver.seat] / 'worker.txt').read_text(encoding='utf-8', errors='replace'))

    def result(self, seat: int) -> dict:
        text = (self.folders[seat] / 'stdout.txt').read_text(encoding='utf-8', errors='replace')
        found = re.search(r'RESULT (.*)', text)
        return dict(item.split('=') for item in found.group(1).split()) if found else {}

    def stderr(self, seat: int) -> str:
        return (self.folders[seat] / 'stderr.txt').read_text(encoding='utf-8', errors='replace')

    def counts(self, key: str) -> str:
        return '/'.join(str(driver.stats[key]) for driver in self.drivers)

    def only_through_the_host(self) -> int:
        """In a star no packet goes from one guest to another: the fates of those links are empty. Returns the
        number of packets that did go through the host's links."""
        for a in range(1, self.seats):
            for b in range(1, self.seats):
                assert a == b or not self.link.fates[(a, b)], f'{self.name}: a packet went from seat {a + 1} to seat {b + 1}'
        return sum(len(self.link.fates[(0, seat)]) + len(self.link.fates[(seat, 0)]) for seat in range(1, self.seats))


def in_step(match: Match, frames: int, delay: int | None = None, wanted: list | None = None, seen: list | None = None) -> str:
    """Every seat ran the same `frames` frames with the same words, and the games agree with the drivers. `wanted`: the port
    words the drivers must have told their games (else one controller per player: the scripts, shifted by the delay); `seen`:
    the words the games folded (else the same: a game cleans what it is given)."""
    drivers = match.drivers
    for driver in drivers:
        assert driver.outcome == 'ended', (match.name, driver.seat, driver.outcome, driver.detail)
        assert driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED, (driver.exit_code, driver.exit_reason)
    delays = {driver.delay for driver in drivers}
    assert len(delays) == 1, delays
    used = delays.pop()
    assert delay is None or used == delay, (used, delay)
    wanted = expected(match.seats, used, frames) if wanted is None else wanted
    seen = wanted if seen is None else seen
    boots = {driver.boot_digest for driver in drivers}
    assert len(boots) == 1 and None not in boots, f'{match.name}: the boot digests are not one: {boots}'
    for driver in drivers:
        assert driver.history == wanted, f'{match.name}: seat {driver.seat + 1} ran other words than the scripts'
        result = match.result(driver.seat)
        assert int(result['frames']) == frames and int(result['live']) == frames and int(result['silent']) == 0, result
        assert int(result['digest'], 16) == fold(seen), f'{match.name}: seat {driver.seat + 1}: the game ran other words'
        assert int(result['effects_off']) == (frames if driver.seat else 0), result      # a guest writes no save
        assert driver.digests == drivers[0].digests, 'the digests differ between seats'
        assert driver.desync is None and driver.stats['final_compared'], (driver.desync, driver.stats)
    every = drivers[0].settings.digest_every if INPROC else drivers[0].config['settings']['digest_every']
    assert len(drivers[0].digests) == frames // every + (1 if frames % every else 0), drivers[0].digests.keys()
    assert drivers[0].digests[frames - 1] == fold(seen)
    topology = ''
    if match.seats > 2 and not mesh_run(match):
        through = match.only_through_the_host()
        assert drivers[0].stats['records_forwarded'] > 0, 'the host forwarded nothing'
        topology = f'; star: no packet between guests, {through} through the host'
    return (f'{frames} frames, delay {used}, {len(drivers[0].digests)} digests equal on {match.seats} seats; '
            f'late frames {match.counts("late_frames")}, waits {match.counts("waits")}{topology}')


def mesh_run(match: Match) -> bool:
    driver = match.drivers[0]
    settings = driver.settings if INPROC else driver.config['settings']
    return (settings.topology if INPROC else settings.get('topology', 'star')) == 'mesh'


# ---- the scenarios: (name, time limit in seconds, function(executable, out) -> line) ----

def plain(name, seats, frames, limit, delay, **link):
    extra = link.pop('extra', {})

    def scenario(executable, out):
        match = Match(executable, out, name, seats, link=link, delay=delay, last_frame=frames, digest_every=50, **extra).start()
        match.finish(limit)
        lost = match.link.counts
        line = in_step(match, frames, delay)
        if link.get('loss') or link.get('duplicate') or link.get('reorder'):
            assert (not link.get('loss') or lost['lost']) and (not link.get('duplicate') or lost['duplicated'])
            line += f'; packets lost {lost["lost"]}, repeated {lost["duplicated"]}, held back {lost["reordered"]} of {lost["sent"]}'
        return line
    return name, limit, scenario


def state_of(driver) -> dict:
    return driver.snapshot() if hasattr(driver, 'snapshot') else driver.status


def shared_everyone(executable, out):
    # Three seats on the controls of port 0: every game is told the OR of the three pads, the same on all three PCs; the kit
    # cancels the opposite directions the merge makes (seat words that differ on every frame make plenty). A lossy link.
    delay, frames = 2, 400
    match = Match(executable, out, 'shared-everyone', 3, delay=delay, last_frame=frames, digest_every=50, sharing=1,
                  link={'latency_ms': 5.0, 'jitter_ms': 2.0, 'loss': 0.02}).start()
    match.finish(60)
    wanted = shared_expected(3, delay, frames)
    seen = [(kit_clean(word),) for (word,) in wanted]
    cleaned = sum(1 for (a,), (b,) in zip(wanted, seen) if a != b)
    assert cleaned >= 20, f'the scripts made opposite directions on only {cleaned} frames: the cleaning is not tested'
    assert len({word for (word,) in wanted}) >= 20, 'the merged pads took too few different values'
    for driver in match.drivers:
        assert state_of(driver)['sharing'] == 'everyone', state_of(driver)
        assert all(len(words) == 1 for words in driver.history), 'a shared match runs one port word a frame'
    line = in_step(match, frames, delay, wanted, seen)
    return f'three seats share port 0 (OR of the pads, {cleaned} frames with opposite directions cleaned by the kit); {line}'


def shared_turns(executable, out):
    # Turns: the token starts at the host and moves by records only. Scripted requests (a LOCAL's control bits, as the worker's
    # pass_token / share_mode would add them), with their LOCAL frame; a record of frame f + delay, in force from f + delay + 1:
    #   40 the host passes (token 1)            60 seat 3 passes: not the holder, nothing     80 seat 2 passes (token 2)
    #  120 seat 3 passes: wraps to the host     160 the host gives the token to seat 3        200 the host: everyone
    #  220 seat 2 asks for turns: not the host  260 the host: turns again (token still seat 3)  280 seat 2 passes: not the holder
    delay, frames = 2, 320
    sys_pass, to_seat3, set_all, set_turns = 0x2, 0x2 | 3 << 8, 0x1000, 0x2000
    scripts = {0: {40: sys_pass, 160: to_seat3, 200: set_all, 260: set_turns}, 1: {80: sys_pass, 220: set_turns, 280: sys_pass},
               2: {60: sys_pass, 120: sys_pass}}
    match = Match(executable, out, 'shared-turns', 3, delay=delay, last_frame=frames, digest_every=50, sharing=2,
                  link={'latency_ms': 5.0, 'jitter_ms': 2.0, 'loss': 0.02},
                  per_seat={seat: {'local_source': script(seat, system_at=at)} for seat, at in scripts.items()}).start()
    match.finish(60)
    after = delay + 1
    events = [(40 + after, 'token', 1), (80 + after, 'token', 2), (120 + after, 'token', 0), (160 + after, 'token', 2),
              (200 + after, 'mode', 1), (260 + after, 'mode', 2)]
    wanted = shared_expected(3, delay, frames, events, mode=2)
    assert len({word for (word,) in wanted}) > 50, 'the scripts gave the games too few different words'
    for driver in match.drivers:
        state = state_of(driver)
        assert (state['sharing'], state['token']) == ('turns', 2), state          # where the last requests left the mapper
    line = in_step(match, frames, delay, wanted, [(kit_clean(word),) for (word,) in wanted])
    return (f'turns on three seats: the token went host, seat 2, seat 3, host, seat 3 and the mode everyone and back, only on the '
            f'records of the right seat (a pass from a seat that did not hold the token and a mode asked by a guest changed nothing); {line}')


def boot_mismatch(executable, out):
    # Seat 3's copy starts from another state (a stand-in for another battery or an option the seal missed): the host
    # compares the boot digests before frame 0 and refuses the launch with a reason; no game ran a frame. The link
    # loses a fifth of its packets: the verdict still reaches everyone.
    match = Match(executable, out, 'boot-mismatch', 3, delay=2, last_frame=100, digest_every=50, link={'loss': 0.2},
                  env={2: {'SESSION_FAKE_BOOT_SALT': '5'}}).start()
    match.finish(40)
    for driver in match.drivers:
        assert driver.outcome == 'boot_mismatch', (driver.seat, driver.outcome, driver.detail)
        assert driver.next_run == 0 and driver.history == [] and driver.delay is None, (driver.seat, driver.next_run)
        assert driver.exit_code == 0 and driver.exit_reason == pipe.EXIT_STOPPED, (driver.exit_code, driver.exit_reason)
        result = match.result(driver.seat)
        assert int(result['frames']) == 0 and int(result['live']) == 0, result          # no frame ever ran
        # RRHK_STOP_BOOT_MISMATCH (4) « Your game differs from the host's » only for the seat whose game differs; the others are ended (3)
        assert f'stopped by Retro-Recomp ({4 if driver.seat == 2 else 3})' in match.stderr(driver.seat), match.stderr(driver.seat)
    assert 'Helene' in match.drivers[0].detail and 'boot digest' in match.drivers[0].detail, match.drivers[0].detail
    assert 'Helene' in match.drivers[1].detail, match.drivers[1].detail
    return f'seat 3 starts from another state: the launch was refused before frame 0 on all three seats ({match.drivers[0].detail})'


def pause_by_menu(executable, out):
    # Seat 2 opens Help during frame 39: its LOCAL of frame 40 asks for a pause, which every seat applies before frame
    # 40 + D; the menu closes by itself thirty iterations later and the same seat's word resumes everyone.
    match = Match(executable, out, 'pause-menu', 2, delay=2, last_frame=200, digest_every=50,
                  env={1: {'SESSION_FAKE_MENU_AT': '40'}}, per_seat={1: {'local_source': script(1, menu=True)}}).start()
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
        threading.Event().wait(0.5)
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
    # Seat 2's driver tells its own game another word for player 1 at frame 77: the digests of frame 99 differ. The
    # host compares with every guest and tells the third seat.
    match = Match(executable, out, 'desync', 3, delay=2, digest_every=50, drop_after=8.0,
                  per_seat={1: {'words_filter': {'kind': 'xor', 'frame': 77, 'port': 0, 'mask': 0x40}}}).start()
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
    # Seat 2's worker loses its game: the pipe closes, that game says so and closes by itself, the host stops its own
    # and tells seat 3, which stops too.
    match = Match(executable, out, 'pipe-lost', 3, delay=2, digest_every=50).start()
    try:
        assert match.drivers[1].reached(100, 20), 'frame 100 never came'
        match.drivers[1].close_game_pipe()
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
    return 'seat 2 lost its pipe: its game closed by itself, the host and seat 3 were told and stopped, every game left with code 0'


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


def converter_gone(executable, out):
    # The converter side of seat 2 goes away (its pipes close): that worker ends the match as a seat leaving, its game
    # stops, and the host, told by the link, stops its own. Nothing is left running.
    match = Match(executable, out, 'converter-gone', 2, delay=2, digest_every=50).start()
    try:
        assert match.drivers[1].reached(100, 20), 'frame 100 never came'
        match.drivers[1].close()        # its stdin: the worker sees the converter go
    finally:
        match.finish(40)
    host, guest = match.drivers
    assert host.outcome == 'seat_left' and host.exit_code == 0, (host.outcome, host.detail, host.exit_code)
    assert guest.outcome == 'left' and guest.exit_code == 0, (guest.outcome, guest.detail, guest.exit_code)
    assert 'stopped by Retro-Recomp' in match.stderr(1), match.stderr(1)
    result = match.result(1)
    assert int(result['digest'], 16) == fold(host.history[:int(result['frames'])]), result
    return 'seat 2\'s converter went away: its worker left the match, its game stopped and the host stopped too, both processes exit 0'


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


def pace_jitter(name, latency, jitter, frames, limit):
    # Both clocks the same on a 60 Hz machine: the estimate of the frame advantage is noisy by more than a frame, and the
    # pace must stay (almost) where it is. Before the median, the dead band by the delay and the hold time, the pace
    # flipped 28 times on the host in 1,800 frames at 120 +- 20 ms.
    def scenario(executable, out):
        match = Match(executable, out, name, 2, hz=60, last_frame=frames, digest_every=60, waiting_after=0.5,
                      link={'latency_ms': latency, 'jitter_ms': jitter}).start()
        match.finish(limit)
        line = in_step(match, frames)
        changes = [driver.stats['pace_changes'] for driver in match.drivers]
        # At most one change every 150 frames (2.5 s): the flapping this guards against was 28 in 1,800 frames (about 14 per
        # 900); real worker processes on a busy PC see scheduler noise, and 4 in 900 was seen once there.
        assert max(changes) <= frames // 150, f'the pace changed {changes} times in {frames} frames'
        assert all(driver.stats['waits'] == 0 for driver in match.drivers), match.counts('waits')
        # The median advantage over the slowest seat, as each seat's time sync saw it every quarter second: wide while
        # the match starts (the seats start apart by what the host measured), then within a fraction of a frame.
        medians = [item[1] for driver in match.drivers for item in driver.pace_trace]
        settled = [item[1] for driver in match.drivers for item in driver.pace_trace if item[0] >= frames // 3]
        return (f'PACE changes {changes[0]}/{changes[1]} in {frames} frames (largest pace {match.counts("pace_ppm_max")} ppm; '
                f'the median advantage {min(medians):.2f} to {max(medians):.2f} frames, from frame {frames // 3} on '
                f'{min(settled):.2f} to {max(settled):.2f}); {line}')
    return name, limit, scenario


def drift(name, fast_seat, frames, limit, pace=True):
    """Two game clocks that differ by 0.5 %: the fast seat's PACE slows it, in a star, whichever seat it is."""
    def scenario(executable, out):
        # The delay is set (4 frames: a link of 10 ms needs 2, so two frames of lead cost nothing): what is tested is the
        # pace, not the host's choice of the delay. At the floor delay (the measured one on a quiet LAN) a 0.5 % drift
        # has almost no slack to use: time sync then halves the waits instead of removing them (see STAGE1.md, stage 1b).
        match = Match(executable, out, name, 2, hz=60, last_frame=frames, digest_every=60, waiting_after=0.5, pace=pace,
                      delay=4, link={'latency_ms': 10.0, 'jitter_ms': 2.0}, per_seat={fast_seat: {'clock_ppm': -5000}}).start()
        match.finish(limit)
        line = in_step(match, frames)
        fast, slow_seat = match.drivers[fast_seat], match.drivers[1 - fast_seat]
        delay = fast.delay
        late = fast.stats['late_frames']
        # How far ahead each seat found itself of the other, as its time sync saw it (the median of the samples of the
        # last three seconds, every quarter second): lockstep bounds it by the delay, time sync keeps it well below.
        ahead = max((item[1] for driver in match.drivers for item in driver.pace_trace), default=0.0)
        assert ahead <= delay, f'a seat found itself {ahead} frames ahead of the other (delay {delay})'
        if pace:
            assert fast.stats['pace_ppm_max'] >= 2500, f'the faster seat never slowed: {fast.pace_trace[-5:]}'
            assert slow_seat.stats['pace_ppm_max'] <= 2500, f'the slower seat was slowed: {slow_seat.stats["pace_ppm_max"]}'
            assert late <= frames // 4, (f'the faster seat waited for records on {late} of {frames} frames; delay {delay}; its time sync '
                                          f'(frame, median, ppm): {fast.pace_trace[::4]}')
            assert not fast.stats['waits'], fast.stats
            return (f'seat {fast_seat + 1} runs 0.5 % fast: it slowed to {fast.pace["ppm"]} ppm ({fast.stats["pace_changes"]} changes, '
                    f'the slower seat {slow_seat.stats["pace_ppm_max"]} ppm); no seat was more than {ahead:.2f} frames '
                    f'ahead of the other (delay {delay}); the faster seat found its records late on {late} of {frames} frames; {line}')
        assert fast.stats['pace_changes'] == 0 and late >= 100, f'without time sync: late frames {late}'
        return (f'time sync off, seat {fast_seat + 1} 0.5 % fast: it found its records late on {late} of {frames} frames '
                f'(it waits for the slower seat once the gap is the delay of {delay} frames: about frame {delay * 200}); {line}')
    return name, limit, scenario


SCENARIOS = [
    plain('two-seats-0ms', 2, 600, 40, 1),
    plain('two-seats-30ms-jitter', 2, 600, 40, 15, latency_ms=30.0, jitter_ms=10.0, reorder=0.02, duplicate=0.02),
    plain('two-seats-loss', 2, 1000, 40, 2, latency_ms=2.0, loss=0.02),
    plain('three-seats-loss-jitter', 3, 500, 40, 6, latency_ms=10.0, jitter_ms=5.0, loss=0.02),
    plain('four-seats-loss-jitter', 4, 500, 60, 6, latency_ms=10.0, jitter_ms=5.0, loss=0.02, reorder=0.02, duplicate=0.02),
    plain('four-seats-0ms', 4, 500, 40, 1),
    plain('three-seats-mesh', 3, 400, 40, 3, latency_ms=5.0, loss=0.02, extra={'topology': 'mesh'}),
    ('shared-everyone', 60, shared_everyone),
    ('shared-turns', 60, shared_turns),
    ('boot-mismatch', 40, boot_mismatch),
    ('pause-menu', 40, pause_by_menu),
    ('pause-host', 40, pause_host_resumes),
    ('host-stops', 40, host_stops),
    ('desync', 40, forced_desync),
    ('pipe-lost', 40, pipe_lost),
    ('seat-silent', 40, seat_silent),
    ('converter-gone', 40, converter_gone),
    slow('lag-one-seat-120ms', 3, 240, 60, one_far, (120.0, 20.0)),
    slow('lag-all-150ms', 2, 240, 60, all_far, (150.0, 0.0)),
    ('lag-burst', 60, burst),
    pace_jitter('pace-jitter-30ms', 30.0, 10.0, 900, 60),
    pace_jitter('pace-jitter-120ms', 120.0, 20.0, 1800, 120),
    drift('pace-drift-host-fast', 0, 900, 80),
    drift('pace-drift-guest-fast', 1, 900, 80),
    drift('pace-drift-without-time-sync', 0, 1100, 80, pace=False),
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
    global INPROC
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/netplay-lockstep-selftest')
    parser.add_argument('--only', help='run the scenarios whose name contains this')
    parser.add_argument('--inproc', action='store_true', help='drivers as threads of this process (no worker processes)')
    args = parser.parse_args()
    INPROC = args.inproc
    reason = fake.ready()
    if reason:
        print('skipped:', reason)
        return 0
    code, output, seconds = run_checks(args.output.resolve(), args.only)
    print(f'exit {code}, {seconds:.1f} s\n{output.strip()}')
    return code


if __name__ == '__main__':
    sys.exit(main())
