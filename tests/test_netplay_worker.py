"""The netplay worker's parts that need no compiler (retrorecomp/netplay, multiplayer stage 1b).

The channel between the converter and a worker process (framing, bounds), the scripted controls, the time sync
controller on made-up time (noise, a hitch, a real drift in a closed loop), the star and the boot digest with lockstep
drivers over a pure-Python game that speaks the pipe's protocol (three seats through the host with loss and jitter, a
launch refused for another boot state), and a real worker process started the way the converter starts it (a bad
config is reported and exits 2; the channel closing before the config is not a hang). The matches with the C fake game
and real worker processes are in tests/test_netplay_lockstep.py. No ROM, no visible window, no socket."""
import json
from pathlib import Path
import os
import queue
import random
import struct
import subprocess
import sys
import threading
import time
import unittest

from retrorecomp.netplay import (LinkSimulator, LockstepDriver, PaceController, Settings, WorkerProcess,
                                 input_records as wire, scripted_inputs, session_pipe as pipe, worker_channel as channel)

ROOT = Path(__file__).resolve().parents[1]


class ChannelTests(unittest.TestCase):
    def test_messages_are_framed_one_byte_at_a_time_and_bounded(self):
        reader = channel.Reader()
        data = channel.frame(channel.CONFIG, b'{}') + channel.frame(channel.NET_IN, b'\x01abc') + channel.frame(channel.CALL, b'')
        got = []
        for index in range(len(data)):
            got += reader.feed(data[index:index + 1])
        self.assertEqual(got, [(channel.CONFIG, b'{}'), (channel.NET_IN, b'\x01abc'), (channel.CALL, b'')])
        with self.assertRaises(channel.Broken):
            channel.Reader().feed(struct.pack('<BI', 99, 0))                    # an unknown kind
        with self.assertRaises(channel.Broken):
            channel.Reader().feed(struct.pack('<BI', channel.CALL, channel.MAX_PAYLOAD + 1))
        with self.assertRaises(ValueError):
            channel.frame(channel.STATUS, b'\0' * (channel.MAX_PAYLOAD + 1))

    def test_a_writer_survives_the_other_end_going_away(self):
        read, write = os.pipe()
        writer = channel.Writer(write)
        self.assertTrue(writer.send(channel.STATUS, b'{}'))
        self.assertEqual(os.read(read, 100), channel.frame(channel.STATUS, b'{}'))
        os.close(read)
        self.assertFalse(writer.send(channel.STATUS, b'{}'))
        self.assertTrue(writer.closed)
        self.assertFalse(writer.send(channel.STATUS, b'{}'))
        os.close(write)


class ScriptedInputsTests(unittest.TestCase):
    def test_a_script_is_a_function_of_the_frame_and_ignores_the_games_system_bits(self):
        source = scripted_inputs.local_source({'kind': 'pad', 'seat': 1})
        self.assertEqual(source(7, 0xffff, pipe.SYS_PAUSE), (scripted_inputs.pad(1, 7), 0))
        self.assertEqual(source(7, 0, 0), source(7, 0xaaaa, 0))
        self.assertNotEqual(source(7, 0, 0)[0], source(8, 0, 0)[0])
        paused = scripted_inputs.local_source({'kind': 'pad', 'seat': 2, 'pause_from': 60})
        self.assertEqual((paused(59, 0, 0)[1], paused(60, 0, 0)[1]), (0, pipe.SYS_PAUSE))
        menu = scripted_inputs.local_source({'kind': 'pad', 'seat': 0, 'system': 'game'})
        self.assertEqual(menu(3, 0, pipe.SYS_PAUSE)[1], pipe.SYS_PAUSE)
        random_pad = scripted_inputs.local_source({'kind': 'random', 'seat': 0})
        self.assertEqual(random_pad(5, 0, 0), random_pad(11, 0, 0))             # held 12 frames
        self.assertIsNone(scripted_inputs.local_source(None))
        with self.assertRaises(ValueError):
            scripted_inputs.local_source({'kind': 'nothing'})

    def test_the_words_filter_changes_one_word_of_one_frame(self):
        tamper = scripted_inputs.words_filter({'kind': 'xor', 'frame': 77, 'port': 1, 'mask': 0x40})
        self.assertEqual(tamper(76, (1, 2, 3)), (1, 2, 3))
        self.assertEqual(tamper(77, (1, 2, 3)), (1, 2 ^ 0x40, 3))
        self.assertIsNone(scripted_inputs.words_filter(None))


class TimeSyncTests(unittest.TestCase):
    """The controller on time the test makes up: samples arrive 60 times a second, updates four times a second."""

    @staticmethod
    def run_loop(seconds, advantage_at, noise=0.0, deadband=0.5, seed=3, drift_ppm=None):
        """`advantage_at(t)`: the true advantage in frames; with `drift_ppm`, instead a plant: the advantage grows by
        what the seat's clock gains on the other and shrinks by the pace the controller asked for."""
        chance = random.Random(seed)
        controller = PaceController(deadband=deadband)
        advantage, history, peak = 0.0, [], 0.0
        for step in range(int(seconds * 60)):
            now = step / 60.0
            if drift_ppm is not None:
                advantage += (drift_ppm - controller.ppm) * 1e-6 * 60 / 60.0      # frames gained in 1/60 s
                advantage = min(advantage, 20.0)
                seen = advantage
            else:
                seen = advantage_at(now)
            peak = max(peak, seen)
            controller.observe(0, now, seen + chance.uniform(-noise, noise))
            if step % 15 == 14:
                new = controller.update(now)
                if new is not None:
                    history.append((round(now, 2), new))
        return controller, history, peak

    def test_noise_around_a_steady_advantage_changes_nothing(self):
        for steady in (0.0, 0.2, -2.0):
            controller, history, _ = self.run_loop(600, lambda _t, steady=steady: steady, noise=1.3)
            self.assertEqual(history, [], steady)
            self.assertEqual(controller.ppm, 0)

    def test_a_steady_lead_steps_the_pace_up_one_step_per_hold_and_back_down(self):
        controller = PaceController()
        times = []
        for step in range(60 * 30):
            now = step / 60.0
            controller.observe(0, now, 1.5)             # a seat that stays 1.5 frames ahead
            if step % 15 == 14 and (new := controller.update(now)) is not None:
                times.append((round(now, 2), new))
        self.assertEqual([ppm for _t, ppm in times], [2500, 5000])      # pace_for(1.5 - 0.15) = 5000, one step each
        gaps = [b[0] - a[0] for a, b in zip(times, times[1:])]
        self.assertTrue(all(gap >= controller.hold for gap in gaps), gaps)
        for step in range(60 * 30, 60 * 60):            # then level with the other seat
            now = step / 60.0
            controller.observe(0, now, 0.0)
            if step % 15 == 14 and (new := controller.update(now)) is not None:
                times.append((round(now, 2), new))
        self.assertEqual([ppm for _t, ppm in times[2:]], [2500, 0])
        self.assertEqual(controller.ppm, 0)
        self.assertTrue(all(0 <= ppm <= pipe.PACE_LIMIT for _t, ppm in times))

    def test_a_lead_of_a_frame_that_goes_away_is_answered_once_and_released(self):
        # A game that hitches ahead by nine tenths of a frame for half a minute is really ahead: the pace answers in one step and comes
        # back when the lead is gone, in two changes, not one for every noisy sample.
        controller, history, _ = self.run_loop(120, lambda t: 0.9 if 40 <= t < 70 else 0.0, noise=1.2)
        self.assertEqual([ppm for _when, ppm in history], [2500, 0])
        self.assertTrue(40 <= history[0][0] <= 46 and 70 <= history[1][0] <= 76, history)

    def test_real_drift_of_half_a_per_cent_is_followed_and_the_gap_stays_bounded(self):
        # A closed loop: the seat's clock gains 0.5 % on the other, the pace it asks for takes that much back, the
        # samples are noisy by +-1.2 frames. The pace finds the drift (5000 ppm) in two steps; a quantised pace on a
        # plant that holds whatever gap it has cannot sit still for ever, so a step up and back now and then is
        # allowed, never a run away (a few changes in two minutes, the gap within a frame and a bit of the dead band).
        for deadband in (0.5, 1.0):
            for seed in (1, 2, 3):
                controller, history, peak = self.run_loop(120, None, noise=1.2, deadband=deadband, drift_ppm=5000, seed=seed)
                self.assertEqual(controller.ppm, 5000, (deadband, seed, history))
                self.assertEqual([ppm for _when, ppm in history[:2]], [2500, 5000], (deadband, seed, history))
                self.assertLessEqual(len(history), 10, (deadband, seed, history))
                self.assertLess(peak, deadband + 1.5, (deadband, seed, peak))

    def test_a_pause_forgets_what_was_seen(self):
        controller = PaceController()
        for step in range(120):
            controller.observe(0, step / 60.0, 3.0)
        controller.forget()
        self.assertIsNone(controller.update(2.0))


class FakeGame:
    """A game that speaks its end of the session pipe in Python: HELLO, one LOCAL per frame, RUN, DIGEST, STOP. Its state
    folds the port words of every frame, so a frame run on another word shows in its digest (as tools/hostkit_session)."""

    def __init__(self, hz=500, salt=0):
        self.broken = None
        self.hz, self.acc = hz, 0x9e3779b97f4a7c15 ^ salt
        self.frames = 0
        self.live = 0
        self.history = []
        self._inbox: queue.Queue = queue.Queue()
        self._sink = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def attach(self, sink):
        self._sink = sink
        self._thread.start()

    def send(self, data):
        self._inbox.put(data)
        return True

    def close_pipe(self):
        self._inbox.put(None)

    def finish(self, timeout=10.0):
        self._inbox.put(None)
        self._thread.join(timeout)
        return 0

    def _say(self, kind, payload=b''):
        self._sink((kind, payload))

    def _run(self):
        name = b'FAKE'
        self._say(pipe.MSG_HELLO, struct.pack('<HBBIIB', pipe.ABI, 4, pipe.CAP_DIGEST, 0, self.hz * 1000, len(name)) + name)
        reader = pipe.MessageReader()
        ready = False
        while True:
            chunk = self._inbox.get()
            if chunk is None:
                break
            for kind, payload in reader.feed(chunk):
                if kind == pipe.MSG_SETUP:
                    ready = True
                    self._say(pipe.MSG_LOCAL, struct.pack('<IHH', 0, 0, 0))
                elif kind == pipe.MSG_DIGEST:
                    self._say(pipe.MSG_DIGEST_OF, struct.pack('<IQ', self.live, self.acc ^ self.frames))
                elif kind == pipe.MSG_RUN and ready:
                    frame, _flags, count = struct.unpack_from('<IBB', payload)
                    words = struct.unpack_from(f'<{count}H', payload, 6)
                    self.history.append(tuple(words))
                    value = sum(word << (16 * port) for port, word in enumerate(words))
                    self.acc = ((self.acc * 1000003) ^ value ^ (frame << 7)) & 0xffffffffffffffff
                    self.frames += 1
                    self.live = frame
                    time.sleep(1.0 / self.hz)
                    self._say(pipe.MSG_LOCAL, struct.pack('<IHH', frame + 1, 0, 0))
                elif kind == pipe.MSG_STOP:
                    self._say(pipe.MSG_EXIT, struct.pack('<H', pipe.EXIT_STOPPED))
                    self._sink(None)
                    return
        self._sink(None)


class StarTests(unittest.TestCase):
    def match(self, seats, *, link=None, salts=None, **settings):
        simulator = LinkSimulator(seats, seed=2, **(link or {}))
        games = [FakeGame(salt=(salts or {}).get(seat, 0)) for seat in range(seats)]
        drivers = [LockstepDriver(games[seat], simulator.endpoint(seat), Settings(
            seat=seat, seats=seats, delay=2, digest_every=25, keep_history=True, local_source=scripted_inputs.local_source(
                {'kind': 'pad', 'seat': seat}), **settings)) for seat in range(seats)]
        for driver in drivers:
            driver.start()
        try:
            for driver in drivers:
                self.assertTrue(driver.join(60), f'seat {driver.seat + 1} did not end: {driver.snapshot()}')
        finally:
            simulator.close()
        return simulator, games, drivers

    def test_three_and_four_seats_stay_in_step_through_the_host_with_loss_and_jitter(self):
        for seats in (3, 4):
            simulator, games, drivers = self.match(
                seats, link=dict(latency_ms=4.0, jitter_ms=3.0, loss=0.03, duplicate=0.02, reorder=0.02), last_frame=200)
            for driver in drivers:
                self.assertEqual(driver.outcome, 'ended', (seats, driver.seat, driver.detail))
                self.assertEqual(driver.history, drivers[0].history)
                self.assertEqual(len(driver.history), 200)
                self.assertEqual(driver.digests, drivers[0].digests)
                self.assertTrue(driver.stats['final_compared'])
            self.assertEqual(len({game.acc ^ game.frames for game in games}), 1)
            self.assertEqual(len({driver.boot_digest for driver in drivers}), 1)
            for a in range(1, seats):                       # a guest never speaks to another guest
                for b in range(1, seats):
                    self.assertTrue(a == b or not simulator.fates[(a, b)], (a, b))
            self.assertGreater(drivers[0].stats['records_forwarded'], 0)
            self.assertEqual(drivers[0].history[5], tuple(scripted_inputs.pad(seat, 3) for seat in range(seats)))
            self.assertTrue(simulator.counts['lost'] > 0)

    def test_a_boot_state_that_differs_refuses_the_launch_before_frame_0(self):
        simulator, games, drivers = self.match(3, link=dict(latency_ms=2.0, loss=0.2), salts={1: 5}, last_frame=100)
        for driver in drivers:
            self.assertEqual(driver.outcome, 'boot_mismatch', (driver.seat, driver.detail))
            self.assertEqual((driver.next_run, driver.history), (0, []))
        for game in games:
            self.assertEqual(game.frames, 0)
        self.assertIn('Player 2', drivers[0].detail)
        self.assertIn('boot digest', drivers[0].detail)
        self.assertIn('Player 2', drivers[2].detail)

    def test_a_guest_leaving_is_told_to_the_other_guests_by_the_host(self):
        simulator = LinkSimulator(3, seed=2)
        games = [FakeGame() for _ in range(3)]
        drivers = [LockstepDriver(games[seat], simulator.endpoint(seat), Settings(
            seat=seat, seats=3, delay=2, local_source=scripted_inputs.local_source({'kind': 'pad', 'seat': seat})))
            for seat in range(3)]
        for driver in drivers:
            driver.start()
        try:
            self.assertTrue(drivers[1].reached(40, 20))
            drivers[1].stop()
            for driver in drivers:
                self.assertTrue(driver.join(30), driver.snapshot())
        finally:
            simulator.close()
        self.assertEqual([driver.outcome for driver in drivers], ['seat_left', 'left', 'seat_left'])
        self.assertIn('Player 2', drivers[2].detail)


class WorkerProcessTests(unittest.TestCase):
    def test_a_bad_config_is_reported_and_the_worker_exits_with_2(self):
        worker = WorkerProcess({'game': {'exe': str(ROOT / 'no-such-game.exe')}, 'settings': {'seat': 0, 'seats': 2}},
                               carry=lambda to, data: None)
        worker.start()
        try:
            self.assertTrue(worker.join(60), worker.summary())
        finally:
            worker.cleanup()
        self.assertEqual(worker.exit_code_of_process, 2)
        self.assertEqual(worker.outcome, 'error')
        self.assertIn('could not start', worker.detail)
        self.assertEqual(worker.history, [])

    def test_the_channel_closing_before_the_config_ends_the_worker_at_once(self):
        from retrorecomp.netplay.worker_client import worker_command
        process = subprocess.Popen(worker_command(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        try:
            process.stdin.close()
            self.assertEqual(process.wait(timeout=60), 2)
            reader = channel.Reader()
            kinds = [kind for kind, _payload in reader.feed(process.stdout.read())]
            self.assertEqual(kinds, [channel.RESULT])           # it said why, on the channel, and nothing else
        finally:
            process.kill()
            process.stdout.close()

    def test_the_worker_is_the_converters_own_entry(self):
        from retrorecomp.netplay.worker_client import COMMAND, worker_command
        command = worker_command()
        self.assertEqual(command[-1], COMMAND)
        self.assertEqual(COMMAND, '_netplay-worker')
        self.assertTrue(Path(command[-2]).name == 'RetroRecomp.py' or getattr(sys, 'frozen', False))
        text = (ROOT / 'RetroRecomp.py').read_text(encoding='utf-8')
        self.assertIn("sys.argv[1:] == ['_netplay-worker']", text)
        self.assertLess(text.index("'_netplay-worker'"), text.index('from retrorecomp.core import'))     # before the heavy imports


if __name__ == '__main__':
    unittest.main()
