"""The rollback tier of the netplay driver (`retrorecomp/netplay/rollback.py`): what its batches are made of, frame by frame,
against a game stepped by the test, and then the real thing (tools/netplay_rollback_selftest.py: worker processes, the
fake machine of the host kit's session check, a simulated link).

No socket, no ROM, no visible window. The stepped game is a model of the kit's session in Python (the same rules as
`rrhk_session.inc`: a ring of snapshots by frame, silent frames in order after a LOAD, a live RUN only for the frame it
reported): a command the kit would refuse fails the test. Every wait has a bound (a hang, not a speed).
"""
import importlib.util
from pathlib import Path
import re
import struct
import threading
import unittest

from retrorecomp.netplay import LockstepDriver, RollbackDriver, Settings, driver_for, input_records as wire
from retrorecomp.netplay import control, lockstep, rollback, scripted_inputs, seat_map, session_pipe as pipe
from retrorecomp.netplay.launch import Refusal, launch_settings

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'retrorecomp' / 'netplay'
NO_ACKS = [wire.NONE] * 4
MASK = 0xffffffffffffffff

_spec = importlib.util.spec_from_file_location('netplay_rollback_selftest', ROOT / 'tools/netplay_rollback_selftest.py')
selftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(selftest)


RESTART = 0x5245534554       # what a restart mixes into the stepped game's state


def fold(state, frame, words):
    value = sum(word << (16 * port) for port, word in enumerate(words))
    return ((state * 1000003) ^ value ^ (frame << 7)) & MASK


def fold_all(history, start=1):
    state = start
    for frame, words in enumerate(history):
        state = fold(state, frame, words)
    return state


class SteppedGame:
    """The game's end of the pipe, stepped by the test: `local(frame)` is the game asking for a frame; the commands the
    driver sends are executed as the kit would and kept in `commands` (name, frame, ...)."""

    def __init__(self, caps=pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT, bound=16, cost_us=0):
        self.cost_us = cost_us        # with it, every live frame answers DONE with that cost (the kit measures run_frame)
        self.broken = None
        self.caps, self.bound = caps, bound
        self.state, self.live, self.asked = 1, 0, False
        self.ring, self.depth = {}, 0
        self.slot = None              # the match's state (the host's F8 / F9 for everyone, session ABI 4)
        self.commands, self.errors = [], []
        self.notices, self.chat = [], []
        self.live_runs, self.silent_runs = 0, 0
        self._sink = None
        self._reader = pipe.MessageReader()
        self._lock = threading.Lock()

    def attach(self, sink):
        self._sink = sink
        name = b'STEPPED'
        sink((pipe.MSG_HELLO, struct.pack('<HBBIIB', pipe.ABI, 4, self.caps, self.bound, 60000, len(name)) + name))

    def local(self, frame, word=0, system=0, axes=None):
        self.asked = True
        payload = struct.pack('<IHH', frame, word, system)
        if axes is not None:
            payload += struct.pack('<4b', *axes)
        self._sink((pipe.MSG_LOCAL, payload))

    def close_pipe(self):
        pass

    def finish(self, timeout=10.0):
        return 0

    def _fail(self, text):
        self.errors.append(text)

    def send(self, data):
        with self._lock:
            for kind, payload in self._reader.feed(data):
                self._execute(kind, payload)
        return True

    def _execute(self, kind, payload):
        if kind == pipe.MSG_SETUP:
            self.depth = payload[2]
            self.commands.append(('SETUP', payload[2]))
        elif kind == pipe.MSG_DIGEST:
            self.commands.append(('DIGEST', self.live))
            self._sink((pipe.MSG_DIGEST_OF, struct.pack('<IQ', max(self.live - 1, 0), self.state)))
        elif kind in (pipe.MSG_SAVE, pipe.MSG_LOAD):
            frame = struct.unpack('<I', payload)[0]
            if not self.depth:
                return self._fail('a snapshot without a ring')
            slot = frame % self.depth
            if kind == pipe.MSG_SAVE:
                self.ring[slot] = (frame, self.state)
                self.commands.append(('SAVE', frame))
            else:
                if slot not in self.ring or self.ring[slot][0] != frame:
                    return self._fail(f'LOAD {frame}: no such snapshot')
                self.state, self.live = self.ring[slot][1], frame
                self.commands.append(('LOAD', frame))
        elif kind == pipe.MSG_RUN:
            frame, flags, count = struct.unpack_from('<IBB', payload)
            words = struct.unpack_from(f'<{count}H', payload, 6)
            sticks = None
            if flags & pipe.RUN_AXES:
                values = struct.unpack_from(f'<{4 * count}b', payload, 6 + 2 * count)
                sticks = tuple(tuple(values[4 * port:4 * port + 4]) for port in range(count))
            silent = bool(flags & pipe.RUN_SILENT)
            if frame != self.live:
                return self._fail(f'RUN {frame} when the game is at {self.live}')
            if silent and not self.depth:
                return self._fail('a silent frame without snapshots')
            if not silent and not self.asked and self.depth:     # (the delay tier may answer before the game asks: the pipe keeps it)
                return self._fail(f'a live RUN {frame} the game did not ask for')
            if flags & ~(pipe.RUN_SILENT | pipe.RUN_RESET | pipe.RUN_STATE_SAVE | pipe.RUN_STATE_LOAD | pipe.RUN_AXES):
                return self._fail(f'RUN {frame} with unknown flags {flags}')
            if bin(flags & ~(pipe.RUN_SILENT | pipe.RUN_AXES)).count('1') > 1:
                return self._fail(f'RUN {frame} with two actions {flags}')
            if flags & pipe.RUN_RESET:
                self.state = fold(self.state ^ RESTART, frame, ())      # the machine restarts before the frame
                self.commands.append(('RESET', frame))
            if flags & pipe.RUN_STATE_SAVE:
                self.slot = self.state
                self.commands.append(('STATE_SAVE', frame))
            if flags & pipe.RUN_STATE_LOAD:
                if self.slot is None:
                    return self._fail(f'RUN {frame}: a load without a saved state')
                self.state = self.slot
                self.commands.append(('STATE_LOAD', frame))
            self.state = fold(self.state, frame, words)
            if sticks is not None:      # the sticks fold in after the words, as a machine with sticks reads them
                self.state = fold(self.state, frame, tuple((value & 0xff) for port in sticks for value in port))
            self.live = frame + 1
            if silent:
                self.silent_runs += 1
            else:
                self.live_runs += 1
                self.asked = False
                if self.cost_us:
                    self._sink((pipe.MSG_DONE, struct.pack('<II', frame, self.cost_us)))
            self.commands.append(('SILENT' if silent else 'RUN', frame, words) + ((sticks,) if sticks is not None else ()))
        elif kind == pipe.MSG_PAUSE:
            self.commands.append(('PAUSE', payload[0]))
        elif kind == pipe.MSG_NOTICE:
            code, size = struct.unpack_from('<HB', payload)
            self.notices.append((code, payload[3:3 + size].decode('ascii')))
        elif kind == pipe.MSG_CHAT_SHOW:
            phrase, size = payload[0], payload[1]
            name, rest = payload[2:2 + size].decode('ascii'), payload[2 + size:]
            if len(rest) != 1 + rest[0] or (phrase and rest[0]) or (not phrase and not rest[0]):
                return self._fail('a CHAT_SHOW the kit would refuse')
            self.chat.append((phrase, name, rest[1:].decode('ascii')))
        elif kind == pipe.MSG_STOP:
            self.commands.append(('STOP',))
            self._sink((pipe.MSG_EXIT, struct.pack('<H', pipe.EXIT_STOPPED)))
            self._sink(None)

    def since(self, mark):
        return [command for command in self.commands[mark:] if command[0] not in ('PAUSE',)]


class PongLink:
    """The driver's link, held by the test; it answers the driver's pings at once (a link of no latency)."""

    def __init__(self, peers=(1,)):
        self.sink = None
        self.sent = []
        self.opened = threading.Event()
        self.peers = peers

    def open(self, sink):
        self.sink = sink
        self.opened.set()

    def send(self, to_seat, data):
        packet = wire.decode(data, 4)
        sink = self.sink
        if packet is not None and packet.kind == wire.PING and sink is not None:
            sink(to_seat, wire.encode_pong(to_seat, packet.time))
        else:
            self.sent.append((to_seat, data))

    def close(self):
        self.sink = None


def settle(driver, timeout=10.0):
    done = threading.Event()
    driver._events.put(('call', done.set))
    if not done.wait(timeout):
        raise AssertionError(f'the driver did not settle: {driver.snapshot()}')


def own(frame, delay=1):
    """The host's scripted record word of a frame (its pad of frame - delay; neutral before)."""
    return scripted_inputs.pad(0, frame - delay) if frame >= delay else 0


class Host:
    """A host driver of two seats past its gate (delay 1), its game stepped by the test, seat 2 spoken by the test."""

    def __init__(self, test, cap=4, game=None, **settings):
        self.test = test
        self.game = game or SteppedGame()
        self.link = PongLink()
        values = dict(seat=0, seats=2, delay=1, digest_every=1000, packet_rate=1e9, probe_seconds=0.0, rollback=cap,
                      keep_history=True, pace=False, local_source=scripted_inputs.local_source({'kind': 'pad', 'seat': 0}))
        values.update(settings)
        self.driver = driver_for(self.game, self.link, Settings(**values))

    def __enter__(self):
        self.driver.start()
        self.test.assertTrue(self.link.opened.wait(10))
        self.test.assertTrue(self.driver.wait_for(lambda driver: driver.boot_digest is not None, 10))
        self.link.sink(1, wire.encode_boot(1, self.driver.boot_digest))
        # The match has started, not only been given its delay: the host holds its start for its measured one-way time, which a
        # busy PC stretches; frames asked during that hold are kept and run in one burst (22 Nov 2026: the safety-floor test
        # failed so in a loaded full suite, its stepped game seeing live frames it had not asked for).
        self.test.assertTrue(self.driver.wait_for(lambda driver: driver.delay is not None and not driver._holding, 20),
                             self.driver.snapshot())
        return self

    def __exit__(self, *_exc):
        self.driver.stop()
        self.driver.join(30)
        return False

    def ask(self, frame):
        """The game asks for `frame`; returns the commands the driver answered with."""
        mark = len(self.game.commands)
        self.game.local(frame)
        settle(self.driver)
        return self.game.since(mark)

    def peer(self, first, *records):
        """Seat 2's records from frame `first` arrive."""
        self.link.sink(1, wire.encode_input(1, 0, NO_ACKS, [(1, first, list(records))]))
        settle(self.driver)


class TierTests(unittest.TestCase):
    def test_a_game_with_snapshots_is_asked_a_ring_of_the_cap_and_two(self):
        with Host(self, cap=5) as host:
            self.assertIsInstance(host.driver, RollbackDriver)
            self.assertIn(('SETUP', 7), host.game.commands)
            state = host.driver.snapshot()
            self.assertEqual((state['tier'], state['prediction_cap'], state['ring']), ('rollback', 5, 7))
            self.assertEqual(host.game.errors, [])

    def test_a_game_without_snapshots_stays_on_the_delay_tier_and_never_runs_on_a_guess(self):
        with Host(self, cap=5, game=SteppedGame(caps=pipe.CAP_DIGEST, bound=0)) as host:
            self.assertIn(('SETUP', 0), host.game.commands)
            self.assertEqual(host.driver.snapshot()['tier'], 'delay')
            host.ask(0)
            self.assertEqual(host.game.commands[-1], ('RUN', 0, (0, 0)))    # frame 0 is known: nobody's controls exist before the delay
            self.assertEqual(host.ask(1), [])                        # seat 2's record of frame 1 is not known: the game waits
            host.peer(1, (0x21, 0))
            self.assertEqual(host.game.commands[-1], ('RUN', 1, (own(1), 0x21)))
            self.assertEqual((host.game.silent_runs, host.driver.stats['predicted_frames'], host.game.errors), (0, 0, []))

    def test_a_game_without_snapshots_or_a_bound_does_not_roll_back_and_a_driven_one_with_them_does(self):
        hello = lambda caps, bound: pipe.Hello(pipe.ABI, 2, caps, bound, 60000, 'x')    # noqa: E731
        self.assertTrue(rollback.can_roll_back(hello(pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT, 1000)))
        self.assertFalse(rollback.can_roll_back(hello(pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT, 0)))
        self.assertFalse(rollback.can_roll_back(hello(pipe.CAP_DIGEST, 1000)))
        # a driven machine with snapshots rolls back too (session ABI 5: its guest runs the silent frames)
        self.assertTrue(rollback.can_roll_back(hello(pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT | pipe.CAP_DRIVEN, 1000)))
        self.assertFalse(rollback.can_roll_back(hello(pipe.CAP_DIGEST | pipe.CAP_DRIVEN, 1000)))

    def test_rollback_not_asked_is_the_delay_driver_itself(self):
        settings = Settings(seat=0, seats=2)
        self.assertIs(type(driver_for(SteppedGame(), PongLink(), settings)), LockstepDriver)
        self.assertEqual(settings.rollback, 0)
        with self.assertRaises(ValueError):
            RollbackDriver(SteppedGame(), PongLink(), Settings(seat=0, seats=2, rollback=lockstep.MAX_PREDICTION + 1))

    def test_the_small_delay_is_one_on_a_local_network_and_two_otherwise(self):
        frame = 1000.0 / 60
        self.assertEqual(rollback.rollback_delay(0.3, 0.2, frame), 1)
        self.assertEqual(rollback.rollback_delay(8.0, 0.3, frame), 1)
        self.assertEqual(rollback.rollback_delay(8.0, 0.5, frame), 2)
        # a far link gets a larger d rather than deeper guesses: 140 ms needs 10 frames to be covered, 5 are guessed
        self.assertEqual(rollback.rollback_delay(120.0, 20.0, frame), 5)
        self.assertEqual(rollback.rollback_delay(120.0, 20.0, frame, cap=8), 2)
        self.assertEqual(rollback.rollback_delay(40.0, 5.0, frame), 2)
        for one_way in range(0, 400, 7):
            d = rollback.rollback_delay(float(one_way), 10.0, frame)
            self.assertLessEqual(wire.choose_delay(float(one_way), 10.0, frame) - d, rollback.DEFAULT_PREDICTION)
        self.assertEqual((rollback.DEFAULT_PREDICTION, rollback.RING_MARGIN), (5, 2))   # the quiet-PC measure of 17 Nov 2026
        self.assertLessEqual(lockstep.MAX_PREDICTION + rollback.RING_MARGIN, pipe.MAX_RING)
        # the records an honest seat on this tier may be ahead by fit in the window the driver takes them in
        self.assertLessEqual(lockstep.MAX_PREDICTION + 2 * rollback.DELAY_ELSE, lockstep.RECORD_WINDOW)
        self.assertLess(lockstep.MAX_PREDICTION + 2, lockstep.TRIM_BEHIND)

    def test_the_launch_takes_a_prediction_cap_within_its_bounds(self):
        message = {'seat': 1, 'seats': 2}
        self.assertEqual(launch_settings(message).rollback, 0)
        for cap in (0, 1, 8, lockstep.MAX_PREDICTION):
            self.assertEqual(launch_settings({**message, 'rollback': cap}).rollback, cap)
        for bad in (-1, lockstep.MAX_PREDICTION + 1, True, '8', 2.0, None, [8]):
            self.assertIsInstance(launch_settings({**message, 'rollback': bad}), Refusal, bad)

    def test_the_pipe_speaks_save_and_load_as_the_header_says(self):
        self.assertEqual(pipe.save(7), struct.pack('<HHI', pipe.HEADER_NAMES['RRHK_MSG_SAVE'], 4, 7))
        self.assertEqual(pipe.load(0x01020304), struct.pack('<HHI', pipe.HEADER_NAMES['RRHK_MSG_LOAD'], 4, 0x01020304))

    def test_a_desync_is_still_decided_in_the_parent_only(self):
        text = (PACKAGE / 'rollback.py').read_text(encoding='utf-8')
        self.assertNotIn('STOP_DESYNC', text)
        self.assertNotRegex(text, r'def _(desync|compare|claim_desync|desync_reported)\b')
        self.assertNotRegex(text, r'(?m)^\s*(import|from)\s+(socket|socketserver|asyncio|http|urllib|ssl|selectors)\b')
        self.assertEqual(len(re.findall(r'STOP_DESYNC', (PACKAGE / 'lockstep.py').read_text(encoding='utf-8'))), 2)


class BatchTests(unittest.TestCase):
    def test_a_missing_record_is_predicted_and_a_wrong_guess_is_one_batch_of_load_silent_frames_and_the_live_frame(self):
        with Host(self, cap=4) as host:
            self.assertEqual(host.ask(0), [('SAVE', 0), ('RUN', 0, (0, 0))])
            # seat 2's records of frames 1 and 2 are not here: its last known word (neutral) is repeated
            self.assertEqual(host.ask(1), [('SAVE', 1), ('RUN', 1, (own(1), 0))])
            self.assertEqual(host.ask(2), [('SAVE', 2), ('RUN', 2, (own(2), 0))])
            self.assertEqual(host.driver.history, [(0, 0)])                     # only frame 0 is confirmed
            host.peer(1, (0x40, 0), (0x40, 0))                                  # the truth: another word on both
            self.assertEqual(host.game.commands[-1][:2], ('RUN', 2))            # nothing is sent before the game asks
            self.assertEqual(host.ask(3), [
                ('LOAD', 1), ('SILENT', 1, (own(1), 0x40)), ('SAVE', 2), ('SILENT', 2, (own(2), 0x40)),
                ('SAVE', 3), ('RUN', 3, (own(3), 0x40))])                       # frame 3 on the new last known word
            self.assertEqual(host.driver.history, [(0, 0), (own(1), 0x40), (own(2), 0x40)])
            stats = host.driver.stats
            self.assertEqual((stats['rollbacks'], stats['rollback_frames'], stats['rollback_depth_max']), (1, 2, 2))
            self.assertEqual(host.driver.rollback_depths, [0, 0, 1, 0, 0])
            self.assertEqual(stats['predicted_frames'], 3)
            # a guess that was right costs nothing
            host.peer(3, (0x40, 0))
            self.assertEqual(host.ask(4), [('SAVE', 4), ('RUN', 4, (own(4), 0x40))])
            self.assertEqual(stats['rollbacks'], 1)
            self.assertEqual(host.game.state, fold_all(host.driver.history + [(own(4), 0x40)]))
            self.assertEqual((host.game.silent_runs, host.game.errors), (2, []))

    def test_only_the_wrong_frames_are_run_again(self):
        with Host(self, cap=6) as host:
            for frame in range(5):
                host.ask(frame)
            host.peer(1, (0, 0), (0, 0), (0x08, 0))         # the guesses of frames 1 and 2 were right, frame 3 was not
            self.assertEqual(host.ask(5), [
                ('LOAD', 3), ('SILENT', 3, (own(3), 0x08)), ('SAVE', 4), ('SILENT', 4, (own(4), 0x08)),
                ('SAVE', 5), ('RUN', 5, (own(5), 0x08))])
            self.assertEqual(len(host.driver.history), 4)
            self.assertEqual(host.game.errors, [])

    def test_beyond_the_cap_the_game_waits_and_goes_on_when_the_records_come(self):
        with Host(self, cap=3) as host:
            for frame in range(4):                          # frame 0 is confirmed; 1, 2 and 3 run on a guess: the cap
                self.assertEqual(host.ask(frame)[-1][:2], ('RUN', frame))
            self.assertEqual(host.ask(4), [])
            self.assertEqual((host.driver.next_run, host.driver.stats['cap_waits'], host.driver._blocked_on), (4, 1, 1))
            host.peer(1, (0, 0))                            # one more confirmed frame: one more frame may run
            self.assertEqual(host.game.commands[-2:], [('SAVE', 4), ('RUN', 4, (own(4), 0))])
            self.assertEqual(host.ask(5), [])
            self.assertEqual(host.driver.stats['cap_waits'], 2)
            self.assertLessEqual(host.driver.stats['rollback_depth_max'], 3)
            self.assertEqual(host.game.errors, [])

    def test_a_pause_is_never_guessed_and_acts_when_its_frame_is_confirmed(self):
        with Host(self, cap=4) as host:
            host.ask(0)
            host.peer(1, (0x10, pipe.SYS_PAUSE))            # seat 2 pauses in its record of frame 1...
            self.assertEqual(host.ask(1), [])               # ...which is confirmed: the game pauses before frame 1
            self.assertEqual(host.driver.paused, (1, [1]))
            self.assertIn(('PAUSE', 1), host.game.commands)
        with Host(self, cap=4) as host:
            for frame in range(3):
                host.ask(frame)                             # frames 1 and 2 ran on a guess, without any pause
            self.assertIsNone(host.driver.paused)
            host.peer(1, (0, pipe.SYS_PAUSE))
            self.assertEqual(host.ask(3), [])               # the request of frame 1 is now confirmed: no frame 3
            self.assertEqual((host.driver.paused, host.driver.next_run), ((1, [1]), 3))
            self.assertEqual(rollback.predicted(host.driver._records[1]), (0, 0))      # and what is guessed next carries no pause
            host.driver.resume()
            settle(host.driver)
            settle(host.driver)
            self.assertIsNone(host.driver.paused)
            self.assertEqual(host.game.commands[-1], ('RUN', 3, (own(3), 0)))
            self.assertEqual(host.driver.pauses, [(1, 1, 0)])
            self.assertEqual(host.game.errors, [])

    def test_a_digest_is_of_a_confirmed_frame_even_when_the_game_is_ahead(self):
        with Host(self, cap=6, digest_every=2) as host:
            for frame in range(5):
                host.ask(frame)
            self.assertEqual(host.driver.digests, {})       # frame 1's digest is due, frame 1 is not confirmed: not asked
            host.peer(1, (0x02, 0), (0x02, 0))              # frames 1 and 2 confirmed (and wrong: corrected first)
            answer = host.ask(5)
            self.assertEqual([command[:2] for command in answer], [
                ('LOAD', 1), ('SILENT', 1), ('SAVE', 2), ('SILENT', 2), ('SAVE', 3), ('SILENT', 3), ('SAVE', 4), ('SILENT', 4),
                ('SAVE', 5), ('LOAD', 2), ('DIGEST', 2), ('LOAD', 5), ('RUN', 5)])
            confirmed = [(0, 0), (own(1), 0x02), (own(2), 0x02)]
            self.assertEqual(host.driver.history, confirmed)
            self.assertEqual(host.driver.digests, {1: fold_all(confirmed[:2])})
            # frames 3 to 6 confirmed (guessed right): the digest of frame 3 from its snapshot, the one of frame 5 as the game stands
            host.peer(3, (0x02, 0), (0x02, 0), (0x02, 0), (0x02, 0))
            self.assertEqual([command[:2] for command in host.ask(6)],
                             [('SAVE', 6), ('LOAD', 4), ('DIGEST', 4), ('LOAD', 6), ('DIGEST', 6), ('RUN', 6)])
            self.assertEqual(sorted(host.driver.digests), [1, 3, 5])
            confirmed += [(own(frame), 0x02) for frame in (3, 4, 5)]
            self.assertEqual(host.driver.digests[3], fold_all(confirmed[:4]))
            self.assertEqual(host.driver.digests[5], fold_all(confirmed))
            # all known: the digest of the frame just run is asked at once, no snapshot loaded
            host.peer(7, (0x02, 0))
            self.assertEqual(host.ask(7), [('SAVE', 7), ('RUN', 7, (own(7), 0x02)), ('DIGEST', 8)])
            self.assertEqual(host.driver.digests[7], host.game.state)
            self.assertEqual((host.driver.stats['digests_skipped'], host.game.errors), (0, []))

    def test_in_turns_the_token_moves_on_confirmed_records_and_a_guess_is_mapped_like_a_record(self):
        from retrorecomp.netplay import seat_map
        with Host(self, cap=4, sharing=seat_map.SHARED_TURNS) as host:
            host.ask(0)
            self.assertEqual(host.ask(1), [('SAVE', 1), ('RUN', 1, (own(1),))])        # the host holds the token: one port word
            self.assertEqual(host.ask(2), [('SAVE', 2), ('RUN', 2, (own(2),))])
            host.driver.pass_token()                        # rides the host's next record (frame 4), in force from frame 5
            settle(host.driver)
            host.ask(3)
            host.peer(1, (0x80, 0), (0x80, 0), (0x80, 0), (0x80, 0))
            self.assertEqual(host.ask(4), [('SAVE', 4), ('RUN', 4, (own(4),))])        # seat 2's words changed nothing: no correction
            self.assertEqual(host.driver.stats['rollbacks'], 0)
            self.assertEqual(host.ask(5), [('SAVE', 5), ('RUN', 5, (0x80,))])           # seat 2 holds it: its guessed word, mapped
            self.assertEqual(host.driver.snapshot()['token'], 1)
            host.peer(5, (0x01, 0))
            self.assertEqual(host.ask(6), [('LOAD', 5), ('SILENT', 5, (0x01,)), ('SAVE', 6), ('RUN', 6, (0x01,))])
            self.assertEqual(host.game.errors, [])


def hello_of(caps, bound=1000):
    return pipe.Hello(pipe.ABI, 2, caps, bound, 60000, 'x')


SNAP = hello_of(pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT)
PLAIN = hello_of(pipe.CAP_DIGEST, 0)


class RestartTests(unittest.TestCase):
    """The host's restart (session ABI 2): its game's restart bit is a request that rides the host's next record, and every
    game restarts before that frame; a guest's record never restarts anyone, and a restart is never guessed."""

    def test_the_pipe_and_the_mapper_speak_restart_as_the_header_says(self):
        header = (ROOT / 'native/hostkit/hostkit_session.h').read_text(encoding='utf-8')
        self.assertIn('RRHK_RUN_RESET = 2', header)
        self.assertIn('RRHK_SYS_RESTART = 2', header)
        self.assertEqual(pipe.run(5, (1, 2), silent=True, reset=True)[4 + 4], pipe.RUN_SILENT | pipe.RUN_RESET)
        self.assertEqual(pipe.run(5, (1, 2))[4 + 4], 0)
        self.assertTrue(seat_map.restart([(0, seat_map.SYS_RESTART), (0, 0)]))
        self.assertFalse(seat_map.restart([(0, 0), (0, seat_map.SYS_RESTART)]))       # a guest's bit restarts nobody
        self.assertFalse(seat_map.restart([]))
        self.assertEqual(rollback.predicted([(5, seat_map.SYS_RESTART)]), (5, 0))     # never guessed
        self.assertFalse(seat_map.SYS_RESTART & (seat_map.SYS_GAME_MASK | seat_map.SYS_CONTROL_MASK))

    def test_the_hosts_game_asks_once_and_every_frame_after_restarts_nothing(self):
        with Host(self, cap=4) as host:
            host.ask(0)
            host.peer(1, (0, 0), (0, 0), (0, 0), (0, 0), (0, 0), (0, 0))
            host.ask(1)
            mark = len(host.game.commands)
            host.game.local(2, system=pipe.SYS_RESTART)          # pressed during frame 1: in the LOCAL of frame 2
            settle(host.driver)
            host.game.local(2, system=pipe.SYS_RESTART)          # the same LOCAL again (a menu bit changed): no second request
            settle(host.driver)
            self.assertEqual(host.driver._records[0][3][1] & seat_map.SYS_RESTART, seat_map.SYS_RESTART)
            self.assertEqual(host.ask(3)[-2:], [('RESET', 3), ('RUN', 3, (own(3), 0))])
            for frame in range(4, 7):
                self.assertNotIn('RESET', [command[0] for command in host.ask(frame)])
            self.assertEqual(host.driver.restarts, [3])
            self.assertEqual([c for c in host.game.commands[mark:] if c[0] == 'RESET'], [('RESET', 3)])
            self.assertEqual(host.game.errors, [])

    def test_a_guest_driver_never_turns_its_games_bit_into_a_request(self):
        class NoGame:
            def attach(self, _sink):
                pass
        link = type('Link', (), {'open': lambda self, sink: None, 'send': lambda self, *a: None})()
        guest = LockstepDriver(NoGame(), link, Settings(seat=1, seats=2, delay=2))
        guest._phase, guest._holding = 'play', False
        guest._set_delay(2, 0.0)
        guest._holding = False
        guest._local(0, 0, pipe.SYS_RESTART)
        self.assertEqual(guest._records[1][2], (0, 0))


class MatchStateTests(unittest.TestCase):
    """The host's F8 / F9 for everyone (session ABI 4): its game's state bit is a request that rides one of the host's records,
    every game saves or loads the match's state (memory only, this match only) before that frame, a correction runs it again,
    and two of them are kept a snapshot ring apart on the rollback tier."""

    def test_the_pipe_and_the_mapper_speak_it_as_the_header_says(self):
        header = (ROOT / 'native/hostkit/hostkit_session.h').read_text(encoding='utf-8')
        for name in ('RRHK_RUN_STATE_SAVE = 4', 'RRHK_RUN_STATE_LOAD = 8', 'RRHK_SYS_STATE_SAVE = 4', 'RRHK_SYS_STATE_LOAD = 8',
                     f'RRHK_SESSION_ABI {pipe.ABI}'):
            self.assertIn(name, header)
        self.assertEqual(pipe.run(5, (1, 2), silent=True, action=pipe.RUN_STATE_LOAD)[8], pipe.RUN_SILENT | pipe.RUN_STATE_LOAD)
        with self.assertRaises(ValueError):
            pipe.run(5, (1, 2), action=pipe.RUN_STATE_LOAD | pipe.RUN_STATE_SAVE)
        with self.assertRaises(ValueError):
            pipe.run(5, (1, 2), reset=True, action=pipe.RUN_STATE_SAVE)
        self.assertEqual(seat_map.action([(0, seat_map.SYS_STATE_SAVE), (0, 0)]), pipe.RUN_STATE_SAVE)
        self.assertEqual(seat_map.action([(0, seat_map.SYS_STATE_SAVE | seat_map.SYS_STATE_LOAD), (0, 0)]), pipe.RUN_STATE_LOAD)
        self.assertEqual(seat_map.action([(0, seat_map.SYS_RESTART | seat_map.SYS_STATE_LOAD), (0, 0)]), pipe.RUN_RESET)
        self.assertEqual(seat_map.action([(0, 0), (0, seat_map.SYS_STATE_LOAD)]), 0)        # a guest's bit does nothing
        self.assertEqual(seat_map.action([]), 0)
        self.assertEqual(rollback.predicted([(5, seat_map.SYS_STATE_SAVE)]), (5, 0))        # never guessed
        bits = seat_map.SYS_STATE_SAVE | seat_map.SYS_STATE_LOAD
        self.assertFalse(bits & (seat_map.SYS_GAME_MASK | seat_map.SYS_CONTROL_MASK | seat_map.SYS_RESTART))

    def test_a_save_run_again_by_a_correction_and_a_load_a_ring_later_give_one_state_everywhere(self):
        with Host(self, cap=4) as host:
            host.ask(0)
            host.ask(1)
            host.game.local(2, system=pipe.SYS_STATE_SAVE)      # F8 pressed during frame 1: in the LOCAL of frame 2
            settle(host.driver)
            host.game.local(2, system=pipe.SYS_STATE_SAVE)      # the same LOCAL again: no second request
            settle(host.driver)
            self.assertEqual(host.ask(3)[-2:], [('STATE_SAVE', 3), ('RUN', 3, (own(3), 0))])
            # seat 2's true records differ from the guesses since frame 1: the correction saves the match's state again
            host.peer(1, *[(0x40, 0)] * 4)
            again = host.ask(4)
            self.assertIn(('STATE_SAVE', 3), again)
            self.assertLess(again.index(('STATE_SAVE', 3)), again.index(('SILENT', 3, (own(3), 0x40))))
            # F9 at once: it waits for a record a ring after the save (frames run again never see a later save)
            host.game.local(5, system=pipe.SYS_STATE_LOAD)
            settle(host.driver)
            host.peer(5, *[(0x40, 0)] * 10)
            seen = []
            for frame in range(5, 13):
                seen += host.ask(frame)
            spacing = host.driver.ring + 1
            loads = [command for command in seen if command[0] == 'STATE_LOAD']
            self.assertEqual(loads, [('STATE_LOAD', 3 + spacing)])
            self.assertEqual(host.driver.states, [(3, 'save'), (3 + spacing, 'load')])
            # the game's state is the history run with the save and the load at their frames
            state, slot = 1, None
            for frame, words in enumerate(host.driver.history):
                if frame == 3:
                    slot = state
                if frame == 3 + spacing:
                    state = slot
                state = fold(state, frame, words)
            ran = [command for command in host.game.commands if command[0] == 'RUN']
            for _name, frame, words in ran:
                if frame >= len(host.driver.history):
                    state = fold(state, frame, words)
            self.assertEqual(host.game.state, state)
            self.assertEqual(host.game.errors, [])

    def test_on_the_delay_tier_the_save_and_the_load_ride_the_next_records(self):
        with Host(self, cap=0) as host:
            host.peer(0, *[(0, 0)] * 12)
            host.ask(0)
            host.game.local(1, system=pipe.SYS_STATE_SAVE)
            settle(host.driver)
            host.game.local(2, system=pipe.SYS_STATE_LOAD)
            settle(host.driver)
            for frame in range(3, 6):
                host.ask(frame)
            self.assertEqual(host.driver.states, [(2, 'save'), (3, 'load')])
            self.assertEqual(host.game.errors, [])

    def test_a_guests_bits_never_become_a_request(self):
        class NoGame:
            def attach(self, _sink):
                pass
        link = type('Link', (), {'open': lambda self, sink: None, 'send': lambda self, *a: None})()
        guest = LockstepDriver(NoGame(), link, Settings(seat=1, seats=2, delay=2))
        guest._phase, guest._holding = 'play', False
        guest._set_delay(2, 0.0)
        guest._holding = False
        guest._local(0, 0, pipe.SYS_STATE_SAVE | pipe.SYS_STATE_LOAD)
        self.assertEqual(guest._records[1][2], (0, 0))


class SticksTests(unittest.TestCase):
    """The sticks travel (session ABI 7): a game with sticks says CAP_AXES, its LOCAL carries four int8 values, every record of the
    match carries them (on the wire too, FLAG_AXES), a missing seat's sticks are guessed as its last ones, a wrong guess is
    corrected like a wrong word, and the RUN gives every port's sticks to the game."""

    def test_the_pipe_and_the_wire_carry_them_as_the_header_says(self):
        header = (ROOT / 'native/hostkit/hostkit_session.h').read_text(encoding='utf-8')
        self.assertIn('RRHK_RUN_AXES = 16', header)
        self.assertIn(f'RRHK_SESSION_ABI {pipe.ABI}', header)
        self.assertEqual(pipe.parse_local(struct.pack('<IHH4b', 5, 1, 0, -128, 127, 0, -3)), (5, 1, 0, (-127, 127, 0, -3), None))
        self.assertEqual(pipe.parse_local(struct.pack('<IHH', 5, 1, 0)), (5, 1, 0, None, None))
        with self.assertRaises(pipe.Broken):
            pipe.parse_local(b'\0' * 10)
        payload = pipe.run(7, (1, 2), axes=((1, -2, 3, -4), (0, 0, 127, -127)))[4:]
        self.assertEqual(payload[4], pipe.RUN_AXES)
        self.assertEqual(struct.unpack_from('<8b', payload, 6 + 4), (1, -2, 3, -4, 0, 0, 127, -127))
        with self.assertRaises(ValueError):
            pipe.run(7, (1, 2), axes=((1, 2, 3, 4),))
        records = [(5, 0, (10, -10, 0, 0)), (6, 1, (-127, 127, 1, -1))]
        packet = wire.decode(wire.encode_input(1, 9, wire._NO_ACKS, [(1, 3, records)]), 2)
        self.assertEqual(packet.sections[0].records, tuple(records))
        plain = wire.decode(wire.encode_input(1, 9, wire._NO_ACKS, [(1, 3, [(5, 0)])]), 2)
        self.assertEqual(plain.sections[0].records, ((5, 0),))
        data = bytearray(wire.encode_input(1, 9, wire._NO_ACKS, [(1, 3, [(5, 0)])]))
        data[7] = 2                                     # a flag that has no meaning yet: the packet is dropped
        self.assertIsNone(wire.decode(bytes(data), 2))
        self.assertEqual(wire.records_that_fit(1, False), wire.MAX_RECORDS)
        for sections in (1, 2, 3, 4):                   # whatever the sections, a full packet fits
            fit = wire.records_that_fit(sections, True)
            full = [(seat, 0, [(1, 0, (1, 1, 1, 1))] * fit) for seat in range(sections)]
            self.assertLessEqual(len(wire.encode_input(0, 0, wire._NO_ACKS, full)), wire.MAX_PACKET)

    def test_the_mapper_gives_each_port_its_seats_sticks_and_the_shared_controls_one(self):
        a, b = (1, 2, 3, 4), (-5, 0, 0, 0)
        state = seat_map.SeatState(seat_map.PER_PLAYER, 0, ())
        self.assertEqual(seat_map.sticks(state, [(0, 0, a), (0, 0, b)]), (a, b))
        self.assertEqual(seat_map.sticks(state, [(0, 0, a), (0, 0)]), (a, (0, 0, 0, 0)))
        turns = seat_map.SeatState(seat_map.SHARED_TURNS, 1, ())
        self.assertEqual(seat_map.sticks(turns, [(0, 0, a), (0, 0, b)]), (b,))
        everyone = seat_map.SeatState(seat_map.SHARED_ALL, 0, ())
        self.assertEqual(seat_map.sticks(everyone, [(0, 0, (0, 0, 0, 0)), (0, 0, b)]), (b,))
        self.assertEqual(rollback.predicted([(5, seat_map.SYS_RESTART, a)]), (5, 0, a))

    def test_a_wrong_guess_of_a_seats_sticks_is_corrected_and_the_game_runs_the_true_ones(self):
        game = SteppedGame(caps=pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT | pipe.CAP_AXES)
        with Host(self, cap=4, game=game) as host:
            mine = (20, -20, 0, 0)
            ran = []
            for frame in range(3):
                mark = len(game.commands)
                game.local(frame, axes=mine)
                settle(host.driver)
                ran += game.since(mark)
            self.assertEqual(ran[1], ('RUN', 0, (0, 0), ((0, 0, 0, 0), (0, 0, 0, 0))))     # frame 0: nobody's record before
            self.assertEqual(ran[-1], ('RUN', 2, (own(2), 0), (mine, (0, 0, 0, 0))))        # the guest's guessed centred
            theirs = (-100, 50, 0, 7)
            host.link.sink(1, wire.encode_input(1, 0, NO_ACKS, [(1, 1, [(0, 0, theirs), (0, 0, theirs)])]))
            settle(host.driver)
            mark = len(game.commands)
            game.local(3, axes=mine)
            settle(host.driver)
            fixed = game.since(mark)
            self.assertEqual(fixed[0], ('LOAD', 1))
            self.assertIn(('SILENT', 1, (own(1), 0), (mine, theirs)), fixed)
            self.assertEqual(fixed[-1], ('RUN', 3, (own(3), 0), (mine, theirs)))           # frame 3 on the guest's last sticks
            self.assertEqual(game.errors, [])


class SafetyFloorTests(unittest.TestCase):
    """The per-seat safety floor (lead, 17 Nov 2026): k = 5 unless this seat's own frames are so slow that a correction would take
    more than two frames; it is measured after a warm-up, only ever lowers the cap, and changes nothing on the wire."""

    def test_the_rule_on_the_measured_costs(self):
        frame = 1000.0 / 60
        self.assertEqual([rollback.safety_floor(frame, cost, 5) for cost in (2.53, 3.64, 5.5, 6.0, 8.0, 12.0, 20.0)],
                         [5, 5, 5, 4, 3, 1, 1])       # NES here, NES on the ThinkPad (17 Nov), then heavier machines
        self.assertEqual(rollback.safety_floor(frame, 0.0, 5), 5)

    def test_a_slow_seat_lowers_its_own_cap_after_the_warm_up_and_waits_are_counted(self):
        with Host(self, cap=5, game=SteppedGame(cost_us=20000)) as host:      # 20 ms a frame at 60 Hz: the floor is 1
            host.peer(1, *[(0, 0)] * 32)
            for frame in range(rollback.FLOOR_WARMUP + 1):
                if frame and frame % 30 == 0:
                    host.peer(frame + 2, *[(0, 0)] * 32)
                host.ask(frame)
            self.assertEqual((host.driver.cap_now, host.driver.stats['cap_lowered']), (1, 1))
            self.assertEqual(host.driver.snapshot()['cap_now'], 1)
            waits = host.driver.stats['cap_waits']
            for _ in range(60):                             # no more records from seat 2: past them, one frame on a guess, then a wait
                if host.driver.stats['cap_waits'] > waits:
                    break
                host.ask(host.driver.next_run)
            self.assertLessEqual(host.driver.next_run - host.driver._confirmed(), 1)
            self.assertGreater(host.driver.stats['cap_waits'], waits)
            self.assertEqual(host.game.errors, [])
        with Host(self, cap=5, game=SteppedGame(cost_us=2500)) as host:       # NES-like: the floor never moves it
            host.peer(1, *[(0, 0)] * 32)
            for frame in range(rollback.FLOOR_WARMUP + 1):
                if frame and frame % 30 == 0:
                    host.peer(frame + 2, *[(0, 0)] * 32)
                host.ask(frame)
            self.assertEqual((host.driver.cap_now, host.driver.stats['cap_lowered']), (5, 0))


class ChatTests(unittest.TestCase):
    """The worker's side of the in-game chat (session ABI 3): a line the game sends goes to the room; the room's lines and
    the turn notices come to the game."""

    def test_a_line_from_the_game_goes_to_the_room_and_a_broken_one_ends_the_match(self):
        with Host(self, cap=4) as host:
            said = []
            host.driver.on_chat = lambda phrase, text: said.append((phrase, text))
            host.ask(0)
            host.game._sink((pipe.MSG_CHAT_OUT, bytes([0, 5]) + b'hello'))
            host.game._sink((pipe.MSG_CHAT_OUT, bytes([pipe.PHRASE_GG, 0])))
            settle(host.driver)
            self.assertEqual(said, [(0, 'hello'), (pipe.PHRASE_GG, '')])
            self.assertEqual(host.driver.chat_lines, 2)
        for bad in (bytes([0, 0]), bytes([7, 0]), bytes([1, 2]) + b'hi', bytes([0, 2]) + b'h\x01', bytes([0, 81]) + b'x' * 81):
            with self.assertRaises(pipe.Broken):
                pipe.parse_chat_out(bad)

    def test_the_rooms_lines_reach_the_game_as_the_kit_reads_them(self):
        with Host(self, cap=4) as host:
            host.driver.chat_show(0, 'Nadïa', 'salut ca va ?')
            host.driver.chat_show(pipe.PHRASE_READY, 'Arthur', 'ignored with a phrase')
            host.driver.chat_slow()
            settle(host.driver)
            self.assertEqual(host.game.chat, [(0, 'Nadia', 'salut ca va ?'), (pipe.PHRASE_READY, 'Arthur', '')])
            self.assertIn((pipe.NOTICE_CHAT_SLOW, ''), host.game.notices)
            self.assertEqual(host.game.errors, [])
        self.assertEqual(len(pipe.chat_show(0, 'x' * 40, 'y' * 200)), 4 + 2 + 16 + 1 + 80)     # bounded

    def test_in_turns_each_game_is_told_who_has_the_controls_once_per_change(self):
        with Host(self, cap=4, sharing=seat_map.SHARED_TURNS, names=('Arthur', 'Nadia')) as host:
            host.ask(0)
            self.assertEqual(host.game.notices, [(pipe.NOTICE_YOUR_TURN, '')])        # the host starts with the token
            host.driver.pass_token(1)
            settle(host.driver)
            host.peer(1, *[(0, 0)] * 6)
            for frame in range(1, 6):
                host.ask(frame)
            self.assertEqual(host.game.notices, [(pipe.NOTICE_YOUR_TURN, ''), (pipe.NOTICE_TURN, 'Nadia')])
        with Host(self, cap=4) as host:                                                # one pad each: never a turn notice
            for frame in range(3):
                host.ask(frame)
            self.assertEqual(host.game.notices, [])

    def test_no_line_reaches_a_game_before_its_setup(self):
        # (found by the three-player lobby test: a line said while the match started reached a game before its SETUP, and
        # the kit ends the session on any other message then)
        sent = []
        game = type('Game', (), {'attach': lambda self, sink: None, 'send': lambda self, data: sent.append(data) or True})()
        link = type('Link', (), {'open': lambda self, sink: None, 'send': lambda self, *a: None})()
        driver = LockstepDriver(game, link, Settings(seat=1, seats=2, delay=2))
        for phase, told in (('hello', False), ('gate', True), ('play', True), ('done', False)):
            sent.clear()
            driver._phase = phase
            driver._chat_tell(pipe.chat_show(0, 'Nadia', 'hi'))
            self.assertEqual(bool(sent), told, phase)

    def test_the_room_worker_forwards_the_rooms_chat_to_the_game_during_a_match_only(self):
        from retrorecomp.netplay import room_worker
        shown, slow = [], []
        driver = type('Driver', (), {'chat_show': lambda self, *a: shown.append(a), 'chat_slow': lambda self: slow.append(1)})()
        worker = room_worker.RoomWorker.__new__(room_worker.RoomWorker)
        worker.lock, worker.match = threading.RLock(), None
        worker._chat_to_game({'event': 'lobby_chat', 'name': 'Nadia', 'ascii': 'hi', 'phrase': 0})
        self.assertEqual(shown, [])                                                    # no match: the window shows it
        worker.match = type('Match', (), {'driver': driver})()
        worker._chat_to_game({'event': 'lobby_chat', 'name': 'Nadïa', 'text': 'héhé', 'ascii': 'hehe', 'phrase': 0})
        worker._chat_to_game({'event': 'lobby_chat', 'name': 'Arthur', 'text': 'GG', 'ascii': 'GG', 'phrase': 1})
        worker._chat_to_game({'event': 'lobby_chat', 'name': 'X', 'ascii': 'x', 'phrase': 99})
        worker._chat_to_game({'event': 'lobby_notice', 'code': 'chat_too_fast', 'detail': ''})
        worker._chat_to_game({'event': 'lobby_notice', 'code': 'busy', 'detail': ''})
        self.assertEqual(shown, [(0, 'Nadïa', 'hehe'), (1, 'Arthur', ''), (0, 'X', 'x')])
        self.assertEqual(slow, [1])


class LaunchTierTests(unittest.TestCase):
    """The tier byte of the LAN room's LAUNCH: its encoding, its bounds and the host's decision (all pure)."""

    def launch(self, **changes):
        fields = dict(match_id=7, seat=1, seats=2, delay=0, digest_every=60, redundancy=3, machine='nes', stamp=bytes(32),
                      rom_sha=bytes(32), names=('Arthur', 'Nadia'), options='speed=1')
        fields.update(changes)
        return control.Launch(**fields)

    def test_the_tier_byte_round_trips_within_one_to_eight_and_zero_is_the_delay_tier(self):
        self.assertEqual(self.launch().rollback, 0)
        for cap in (0, 1, 5, control.MAX_ROLLBACK):
            kind, payload = control.encode(self.launch(rollback=cap))
            decoded = control.decode(kind, payload)
            self.assertEqual(decoded.rollback, cap)
            self.assertEqual(control.encode(decoded), (kind, payload))                     # the canonical form
        self.assertEqual(control.MAX_ROLLBACK, 8)
        self.assertEqual(control.encode(self.launch(rollback=3))[1][11], 3)               # one byte, after the input mode

    def test_a_tier_byte_out_of_bounds_is_refused_by_the_encoder_and_the_decoder_never_with_an_exception_but_a_frame_error(self):
        for bad in (-1, control.MAX_ROLLBACK + 1, 255, True, '3', 2.0, None):
            with self.assertRaises(ValueError, msg=bad):
                control.encode(self.launch(rollback=bad))
        kind, payload = control.encode(self.launch(rollback=2))
        for byte in (control.MAX_ROLLBACK + 1, 30, 255):
            changed = bytearray(payload)
            changed[11] = byte
            with self.assertRaises(control.FrameError):
                control.decode(kind, bytes(changed))
        with self.assertRaises(control.FrameError):                                        # the old layout, one byte short
            control.decode(kind, payload[:11] + payload[12:])

    def test_a_guest_takes_the_cap_through_launch_settings_within_the_wire_bound(self):
        message = {'seat': 1, 'seats': 2}
        self.assertEqual(launch_settings({**message, 'rollback': 8}, rollback_max=control.MAX_ROLLBACK).rollback, 8)
        self.assertEqual(launch_settings(message, rollback_max=control.MAX_ROLLBACK).rollback, 0)
        for bad in (9, 30, -1, True, '8', None):
            refusal = launch_settings({**message, 'rollback': bad}, rollback_max=control.MAX_ROLLBACK)
            self.assertIsInstance(refusal, Refusal, bad)
            self.assertTrue(refusal.reason.isascii())

    def test_the_host_chooses_rollback_only_when_every_game_reported_a_snapshot(self):
        self.assertEqual(rollback.choose_tier('auto', [SNAP]), rollback.DEFAULT_PREDICTION)
        self.assertEqual(rollback.choose_tier('auto', [SNAP, SNAP, SNAP], 3), 3)
        self.assertEqual(rollback.choose_tier('auto', [SNAP, PLAIN]), 0)                    # one without: the delay tier for all
        self.assertEqual(rollback.choose_tier('auto', [PLAIN, SNAP]), 0)
        self.assertEqual(rollback.choose_tier('auto', [SNAP, None]), 0)                     # a game that never said HELLO
        self.assertEqual(rollback.choose_tier('auto', []), 0)
        # a driven machine with snapshots rolls back since session ABI 5
        self.assertEqual(rollback.choose_tier('auto', [hello_of(pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT | pipe.CAP_DRIVEN)]),
                         rollback.DEFAULT_PREDICTION)

    def test_the_host_can_override_the_decision_and_a_forced_rollback_is_refused_with_a_reason_when_a_game_cannot(self):
        self.assertEqual(rollback.choose_tier('delay', [SNAP, SNAP]), 0)
        self.assertEqual(rollback.choose_tier('rollback', [SNAP, SNAP], 6), 6)
        for hellos in ([SNAP, PLAIN], [None], []):
            refusal = rollback.choose_tier('rollback', hellos)
            self.assertIsInstance(refusal, Refusal)
            self.assertIn('snapshots', refusal.reason)
        for mode, cap in (('maybe', 4), ('auto', 0), ('auto', 9), ('delay', 9), ('rollback', True), ('auto', '4')):
            self.assertIsInstance(rollback.choose_tier(mode, [SNAP], cap), Refusal, (mode, cap))
            self.assertIsInstance(rollback.check_tier(mode, cap), Refusal)
        self.assertIsNone(rollback.check_tier('auto', 8))

    def test_a_game_without_snapshots_refuses_a_launch_that_says_rollback_and_says_why(self):
        game = SteppedGame(caps=pipe.CAP_DIGEST, bound=0)
        driver = driver_for(game, PongLink(), Settings(seat=1, seats=2, rollback=4, rollback_required=True, packet_rate=1e9))
        driver.start()
        try:
            self.assertTrue(driver.wait_for(lambda seen: seen.outcome is not None, 10), driver.snapshot())
            self.assertEqual(driver.outcome, 'refused')
            self.assertIn('keeps no snapshot', driver.detail)
            self.assertEqual(game.commands, [])                                              # no SETUP: the game was never started on it
        finally:
            driver.stop()
            driver.join(30)

    def test_a_game_with_snapshots_is_not_refused_and_without_the_requirement_the_delay_tier_stays_quiet(self):
        with Host(self, cap=4, rollback_required=True) as host:
            self.assertEqual(host.driver.snapshot()['tier'], 'rollback')
        with Host(self, cap=4, game=SteppedGame(caps=pipe.CAP_DIGEST, bound=0)) as host:    # not required: the old behaviour
            self.assertEqual(host.driver.snapshot()['tier'], 'delay')


class RollbackThroughRealPipesTests(unittest.TestCase):
    def test_worker_processes_predict_correct_and_end_in_the_state_of_the_confirmed_history(self):
        reason = selftest.fake.ready()
        if reason:
            self.skipTest(reason)
        code, output, seconds = selftest.run_checks(ROOT / '.build/netplay-rollback-selftest')
        self.assertEqual(code, 0, output)
        self.assertIn(f'PASS: {len(selftest.SCENARIOS)} scenarios', output)
        self.assertEqual(len(selftest.SCENARIOS), 15)
        self.assertLess(seconds, 900, output)     # a hang, not a speed


if __name__ == '__main__':
    unittest.main()
