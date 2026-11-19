"""What a seat that is not honest can do to a lockstep driver, and what the driver does instead
(`.build/multiplayer/SECURITY_REVIEW.md`, "Security fixes before the transport"): records far ahead, a flood of packets,
a seat that pings but never plays, launch settings from another PC, forged PONG, MEASURE and BYE_DESYNC, a boot
mismatch that blames the wrong seat, a match that grows without end.

No socket, no ROM, no visible window: the hostile seat is the test itself, speaking through a stub link or the
in-memory simulator to a real driver over a pure-Python game; every wait has a bound (a hang, not a speed).
"""
import random
import struct
import threading
import time
import unittest

from retrorecomp.netplay import LinkSimulator, LockstepDriver, Settings, input_records as wire, scripted_inputs, session_pipe as pipe
from retrorecomp.netplay import lockstep, worker
from retrorecomp.netplay.launch import FIELDS, Refusal, launch_settings
from tests.test_netplay_worker import FakeGame

BOOT = 0x9e3779b97f4a7c15           # FakeGame's state after SETUP (its salt 0)
NO_ACKS = [wire.NONE] * 4


class RecordingGame(FakeGame):
    """A FakeGame that remembers the reason of every STOP it was sent."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.stops = []
        self._parser = pipe.MessageReader()

    def send(self, data):
        for kind, payload in self._parser.feed(data):
            if kind == pipe.MSG_STOP:
                self.stops.append(struct.unpack('<H', payload)[0])
        return super().send(data)


class StubLink:
    """The driver's link, held by the test: what the driver sends is kept, what the test says goes straight to the sink."""

    def __init__(self, seat=0):
        self.seat = seat
        self.sink = None
        self.sent = []
        self.opened = threading.Event()

    def open(self, sink):
        self.sink = sink
        self.opened.set()

    def send(self, to_seat, data):
        self.sent.append((to_seat, data))

    def close(self):
        self.sink = None


def settle(driver, timeout=10.0):
    """Returns when the loop has handled everything queued before this call (events are taken in order)."""
    done = threading.Event()
    driver._events.put(('call', done.set))
    if not done.wait(timeout):
        raise AssertionError(f'the driver did not settle: {driver.snapshot()}')


class Fixture:
    """A host driver on a stub link, past its gate: every guest said its boot digest, the delay is the preset 2."""

    def __init__(self, test, seats=2, game=None, **settings):
        self.test, self.seats = test, seats
        self.game = game or RecordingGame()
        self.link = StubLink(0)
        values = dict(seat=0, seats=seats, delay=2, digest_every=25, packet_rate=1e9,
                      local_source=scripted_inputs.local_source({'kind': 'pad', 'seat': 0}))
        values.update(settings)
        self.driver = LockstepDriver(self.game, self.link, Settings(**values))

    def __enter__(self):
        self.driver.start()
        self.test.assertTrue(self.link.opened.wait(10))
        for seat in range(1, self.seats):
            self.say(seat, wire.encode_boot(seat, BOOT))
        self.test.assertTrue(self.driver.wait_for(lambda driver: driver.delay is not None, 20), self.driver.snapshot())
        return self

    def __exit__(self, *_exc):
        self.driver.stop()
        self.driver.join(30)
        return False

    def say(self, seat, data):
        self.link.sink(seat, data)

    def sent_to(self, seat):
        return [wire.decode(data, 4) for to, data in list(self.link.sent) if to == seat]


class RecordWindowTests(unittest.TestCase):
    def test_records_far_ahead_are_dropped_counted_and_never_forwarded(self):
        # A guest that sends 32 new records per packet, far ahead of the match, used to grow the host's records without
        # end and to make the host forward each packet to every other guest (D1).
        with Fixture(self, seats=3) as fixture:
            driver = fixture.driver
            for k in range(200):
                records = [(k & 0xffff, 0)] * 32
                fixture.say(1, wire.encode_input(1, 0, NO_ACKS, [(1, 2 + 32 * k, records)]))
            settle(driver)
            limit = driver.next_run + driver.delay + lockstep.RECORD_WINDOW
            self.assertLessEqual(len(driver._records[1]), limit + 1)
            self.assertGreater(len(driver._records[1]), 30)             # what is inside the window was taken
            self.assertGreater(driver.stats['records_beyond_window'], 6000)
            frames = [section.first_frame + len(section.records) - 1 for packet in fixture.sent_to(2)
                      if packet.kind == wire.INPUT for section in packet.sections if section.seat == 1]
            self.assertTrue(frames)                                     # the records that were taken were forwarded
            self.assertLessEqual(max(frames), limit)                    # and nothing that was dropped was

    def test_the_window_is_wide_enough_for_an_honest_seat_at_the_longest_delay(self):
        self.assertGreaterEqual(lockstep.RECORD_WINDOW, 2 * wire.MAX_DELAY + 1)

    def test_a_far_frame_or_digest_is_not_believed(self):
        with Fixture(self) as fixture:
            driver = fixture.driver
            fixture.say(1, wire.encode_input(1, 10 ** 6, NO_ACKS, [], digest_frame=10 ** 6, digest=5))
            settle(driver)
            self.assertIsNone(driver._peer_frame[1])                    # D8: a frame a million away is not a frame
            self.assertEqual(driver._peer_digests[1], {})               # D9: nor is a digest of one
            fixture.say(1, wire.encode_input(1, 2, NO_ACKS, [], digest_frame=3, digest=7))
            settle(driver)
            self.assertEqual(driver._peer_frame[1][0], 2)
            self.assertEqual(driver._peer_digests[1], {3: 7})

    def test_a_section_about_another_seat_from_a_guest_is_refused_and_counted(self):
        with Fixture(self, seats=3) as fixture:
            fixture.say(1, wire.encode_input(1, 0, NO_ACKS, [(2, 2, [(1, 0)])]))     # seat 1 speaks for seat 2: only the host does that
            settle(fixture.driver)
            self.assertEqual(len(fixture.driver._records[2]), 2)
            self.assertEqual(fixture.driver.stats['sections_refused'], 1)

    def test_a_packet_whose_seat_byte_is_not_the_links_seat_is_ignored(self):
        with Fixture(self, seats=3) as fixture:
            before = fixture.driver.stats['packets_ignored']
            fixture.say(1, wire.encode_ping(2, 5))                      # seat 1's link, seat 2's header
            settle(fixture.driver)
            self.assertEqual(fixture.driver.stats['packets_ignored'], before + 1)


class BoundedWorkTests(unittest.TestCase):
    def blocked(self, **settings):
        """A driver whose loop is held inside a call, so that nothing it is sent is taken: the queue shows what is kept."""
        link = StubLink(0)
        driver = LockstepDriver(RecordingGame(), link, Settings(seat=0, seats=3, **settings))
        entered, release = threading.Event(), threading.Event()
        driver.start()
        self.assertTrue(link.opened.wait(10))
        driver._events.put(('call', lambda: (entered.set(), release.wait(60))))
        self.assertTrue(entered.wait(10))
        return driver, release

    def finish(self, driver, release):
        release.set()
        driver.stop()
        driver.join(30)

    def test_the_event_queue_is_bounded_and_the_excess_counted(self):
        driver, release = self.blocked(packet_rate=1e9)
        try:
            ping = wire.encode_ping(1, 1)
            for _ in range(20000):
                driver._net_in(1, ping)                                 # never blocks, never raises
            self.assertLessEqual(driver._events.qsize(), lockstep.EVENT_QUEUE_MAX + lockstep.EVENT_QUEUE_HEADROOM)
            self.assertGreater(driver.stats['packets_dropped_queue'], 20000 - lockstep.EVENT_QUEUE_MAX - 100)
        finally:
            self.finish(driver, release)

    def test_one_seats_packet_rate_is_limited_and_the_excess_counted(self):
        driver, release = self.blocked()
        try:
            ping, started = wire.encode_ping(1, 1), time.monotonic()
            for _ in range(3000):
                driver._net_in(1, ping)
            elapsed = time.monotonic() - started
            taken = 3000 - driver.stats['packets_dropped_rate']
            self.assertLessEqual(taken, 60 + 240 * elapsed + 5)         # the burst, and what the rate refilled meanwhile
            self.assertGreater(driver.stats['packets_dropped_rate'], 2000)
            queued = driver._events.qsize()
            driver._net_in(2, ping)                                     # another seat has its own bucket
            self.assertEqual(driver._events.qsize(), queued + 1)
            driver._net_in(9, ping)                                     # a link that names no seat: nothing queued
            self.assertEqual(driver._events.qsize(), queued + 1)
        finally:
            self.finish(driver, release)

    def test_the_token_bucket_refills_with_the_callers_clock(self):
        bucket = lockstep.TokenBucket(rate=10.0, burst=5, now=100.0)
        self.assertEqual([bucket.take(100.0) for _ in range(7)], [True] * 5 + [False] * 2)
        self.assertEqual([bucket.take(100.25) for _ in range(3)], [True, True, False])     # two tokens back after a quarter second
        self.assertEqual(sum(bucket.take(500.0) for _ in range(9)), 5)  # never more than the burst, however long it waited

    def test_an_honest_rate_is_not_limited(self):
        driver = LockstepDriver(RecordingGame(), StubLink(0), Settings(seat=0, seats=4))
        self.assertGreaterEqual(driver._packet_rate(), 240.0)
        self.assertGreaterEqual(driver._packet_rate(), 5 * 60)          # five packets a frame at 60 Hz


class SilentSeatTests(unittest.TestCase):
    def test_a_seat_that_pings_but_sends_no_record_is_dropped(self):
        # D3: it kept the host's `last_heard` fresh for ever while every game waited for it.
        simulator = LinkSimulator(2, seed=3)
        game = RecordingGame()
        driver = LockstepDriver(game, simulator.endpoint(0), Settings(
            seat=0, seats=2, delay=2, digest_every=25, waiting_after=0.2, drop_after=1.0,
            local_source=scripted_inputs.local_source({'kind': 'pad', 'seat': 0})))
        hostile = simulator.endpoint(1)
        hostile.open(lambda source, data: None)
        stop = threading.Event()

        def chatter():
            counter = 0
            while not stop.wait(0.02):
                counter += 1
                hostile.send(0, wire.encode_ping(1, counter))
                hostile.send(0, wire.encode_boot(1, BOOT))

        thread = threading.Thread(target=chatter, daemon=True)
        driver.start()
        thread.start()
        try:
            self.assertTrue(driver.join(20), driver.snapshot())
        finally:
            stop.set()
            thread.join(5)
            driver.stop()
            driver.join(30)
            simulator.close()
        self.assertEqual(driver.outcome, 'seat_silent')
        self.assertIn('seat 2', driver.detail)
        self.assertEqual(driver.stats['stalls'], 1)
        self.assertGreaterEqual(driver.stats['waits'], 1)               # it was "waiting for Player 2" first
        self.assertEqual(game.stops, [pipe.STOP_ENDED])
        self.assertGreater(driver.stats['packets_received'], 20)        # it was heard all along


class SessionEnvironmentTests(unittest.TestCase):
    def test_check_switches_that_change_a_run_never_reach_a_session_game(self):
        # A player's environment holding one of the converter's own check switches would make that seat compute another game.
        from retrorecomp.netplay import session_game
        for name in ('RETRORECOMP_HOST_TEST_FRAMES', 'SMSRECOMP_REFERENCE', 'GENESIS_FORCE_INTERP', 'RR_SNES_FORCE_INTERP',
                     'SNESRECOMP_LLE_BOUNCE', 'GBARECOMP_RTC_GUEST_EPOCH', 'GBARECOMP_SELFHEAL_RECOMPILE'):
            self.assertIn(name, session_game.NEVER_IN_A_SESSION)


class LaunchSettingsTests(unittest.TestCase):
    GOOD = dict(seat=1, seats=3, names=['Arthur', 'Nadia', 'Karl'], delay=None, digest_every=60, redundancy=3,
                options='speed=1\nregion=eu')

    def refused(self, **changes):
        message = {**self.GOOD, **changes}
        result = launch_settings(message)
        self.assertIsInstance(result, Refusal, changes)
        self.assertTrue(result.reason and result.reason.isascii())
        return result

    def test_a_good_launch_becomes_settings(self):
        result = launch_settings(self.GOOD)
        self.assertIsInstance(result, Settings)
        self.assertEqual((result.seat, result.seats, result.names, result.delay, result.digest_every, result.redundancy),
                         (1, 3, ('Arthur', 'Nadia', 'Karl'), None, 60, 3))
        self.assertEqual(result.options, 'speed=1\nregion=eu')
        self.assertEqual((result.local_source, result.words_filter, result.clock_ppm, result.last_frame, result.topology),
                         (None, None, 0, None, 'star'))
        self.assertEqual(launch_settings({'seat': 1, 'seats': 2}).options, '')         # the rest has defaults
        self.assertIsInstance(launch_settings({**self.GOOD, 'delay': 15, 'digest_every': 600, 'redundancy': 8}), Settings)
        self.assertIsInstance(launch_settings({**self.GOOD, 'seat': 0}, guest=False), Settings)

    def test_each_number_at_its_bounds_and_one_past_them(self):
        for key, bad in (('seats', 1), ('seats', 5), ('seats', True), ('seats', 3.0), ('seats', None), ('seat', 0), ('seat', 3),
                         ('seat', -1), ('seat', '1'), ('delay', 0), ('delay', 16), ('delay', -2), ('delay', 2.5),
                         ('digest_every', 0), ('digest_every', 9), ('digest_every', 601), ('digest_every', None),
                         ('redundancy', 0), ('redundancy', 9)):
            self.refused(**{key: bad})
        for key, good in (('seats', 2), ('seats', 4), ('delay', 1), ('digest_every', 10), ('redundancy', 1)):
            changes = {key: good, 'names': ['A', 'B', 'C', 'D'][:good]} if key == 'seats' else {key: good}
            if key == 'seats':
                changes['seat'] = 1
            self.assertIsInstance(launch_settings({**self.GOOD, **changes}), Settings, (key, good))
        self.assertIsInstance(launch_settings({**self.GOOD, 'seat': 0}, guest=False), Settings)

    def test_the_options_are_plain_key_value_lines_few_and_short(self):
        for bad in ('speed', 'speed=1\x07', 'speed=é', '../x=1', 'Speed=1', 'speed=C:\\x', 'speed=a b', 'k=' + 'v' * 33,
                    'k' * 33 + '=1', '\n'.join(f'k{index}=1' for index in range(33)), 'a=1;b=2', 'path=/etc/passwd', 5, None,
                    b'speed=1'):
            self.refused(options=bad)
        self.assertEqual(launch_settings({**self.GOOD, 'options': '\nspeed=1\n\nregion=\n'}).options, 'speed=1\nregion=')
        self.assertIsInstance(launch_settings({**self.GOOD, 'options': '\n'.join(f'k{index}=1' for index in range(32))}), Settings)
        # A CPS-1 board's DIP switches: three words, comma separated (rrhk_cps1.c session_options).
        self.assertEqual(launch_settings({**self.GOOD, 'options': 'dips=ffff,00fb,0000'}).options, 'dips=ffff,00fb,0000')

    def test_names_are_cleaned_as_the_game_draws_them(self):
        result = launch_settings({**self.GOOD, 'names': ['Hélène\x07\n', 'x' * 500, '日本']})
        self.assertEqual(result.names, ('Helene??', 'x' * 16, '??'))
        self.refused(names=['A', 'B'])
        self.refused(names='Arthur')
        self.refused(names=['A', 5, 'C'])

    def test_a_setting_the_host_cannot_say_is_refused(self):
        for key, value in (('clock_ppm', 5000), ('local_source', 'pad'), ('words_filter', 'xor'), ('last_frame', 10),
                           ('topology', 'mesh'), ('pace', False), ('drop_after', 1e9), ('anything', 1)):
            self.refused(**{key: value})
        for bad in (None, [], 'seat=1', 5, b''):
            self.assertIsInstance(launch_settings(bad), Refusal)

    def test_garbage_never_raises(self):
        chance = random.Random(11)
        pool = [None, True, 0, 1, 2, 3, 15, 16, 600, 2 ** 40, -1, 2.5, float('nan'), '', 'a=b', 'é', '\x00', [], {}, ['a'], b'x', 'x' * 9000]
        for _ in range(5000):
            message = {key: chance.choice(pool) for key in FIELDS if chance.random() < 0.8}
            result = launch_settings(message, guest=chance.random() < 0.5)
            self.assertIsInstance(result, (Settings, Refusal))

    def test_the_driver_cleans_the_names_it_is_given_again(self):
        driver = LockstepDriver(FakeGame(), StubLink(0), Settings(seat=0, seats=3, names=('Zoë\n%s', 'x' * 99)))
        self.assertEqual(driver.names, ('Zoe?%s', 'x' * 16, 'Player 3'))

    def test_the_test_hooks_need_the_test_flag(self):
        for field, value in (('local_source', {'kind': 'pad', 'seat': 0}), ('words_filter', {'kind': 'xor', 'frame': 1, 'port': 0, 'mask': 1}),
                             ('clock_ppm', 100), ('topology', 'mesh')):
            with self.assertRaisesRegex(ValueError, field):
                worker.settings_from({'seat': 0, 'seats': 2, field: value})
            self.assertIsInstance(worker.settings_from({'seat': 0, 'seats': 2, field: value}, tests=True), Settings)
        self.assertIsInstance(worker.settings_from({'seat': 0, 'seats': 2, 'delay': 3, 'topology': 'star'}), Settings)


class MeasuresTests(unittest.TestCase):
    def test_a_pong_nobody_asked_for_changes_nothing(self):
        with Fixture(self) as fixture:
            driver = fixture.driver
            for value in (0, 1, 123456, 0xffffffff):
                fixture.say(1, wire.encode_pong(1, value))
            settle(driver)
            self.assertEqual((driver._rtt[1], driver._one_way_ms[1], driver.stats['pongs_refused']), ([], 0.0, 4))

    def test_a_pong_answers_a_ping_once_and_not_a_late_one(self):
        with Fixture(self) as fixture:
            driver = fixture.driver
            fixture.link.sent.clear()
            self.assertTrue(driver.wait_for(lambda d: any(p.kind == wire.PING for p in fixture.sent_to(1)), 10))
            ping = next(p for p in fixture.sent_to(1) if p.kind == wire.PING)
            fixture.say(1, wire.encode_pong(1, ping.time))
            fixture.say(1, wire.encode_pong(1, ping.time))              # a duplicate: the second is not a measure
            settle(driver)
            self.assertEqual(len(driver._rtt[1]), 1)
            self.assertEqual(driver.stats['pongs_refused'], 1)
            old = (int(time.monotonic() * 1e6) - 5_000_000) & 0xffffffff      # a PING sent five seconds ago, answered now
            driver._pings_sent[1].append(old)
            fixture.say(1, wire.encode_pong(1, old))
            settle(driver)
            self.assertEqual((len(driver._rtt[1]), driver.stats['pongs_refused']), (1, 2))

    def test_a_forged_measure_cannot_force_a_large_delay(self):
        driver = LockstepDriver(FakeGame(), StubLink(0), Settings(seat=0, seats=3))
        for guest in (1, 2):
            driver._rtt[guest] = [20.0] * 8                             # the host's own measure: 10 ms one way
            driver._measures[guest] = (60000, 60000)                    # what the guest says
        one_way, jitter = driver._worst_path()
        self.assertLessEqual(one_way, 2 * (1.5 * 10.0 + lockstep.MEASURE_SLACK_MS))
        self.assertLessEqual(wire.choose_delay(one_way, jitter, 1000 / 60), 6)
        self.assertEqual(driver.stats['measures_clamped'], 2)
        for guest in (1, 2):                                            # an honest guest is believed as it said
            driver._measures[guest] = (11, 2)
        driver.stats['measures_clamped'] = 0
        self.assertLessEqual(driver._worst_path()[0], 22.0)
        self.assertEqual(driver.stats['measures_clamped'], 0)

    def test_a_measure_after_the_gate_is_ignored(self):
        with Fixture(self, seats=3) as fixture:
            fixture.say(1, wire.encode_measure(1, 900, 900))
            settle(fixture.driver)
            self.assertEqual(fixture.driver._measures, {})              # the match runs: the delay was chosen long ago

    def test_a_hold_is_bounded_on_the_wire(self):
        packet = bytearray(wire.encode_input(0, 0, NO_ACKS, [], delay=3, hold_ms=500))
        self.assertIsNotNone(wire.decode(bytes(packet), 2))
        packet[29:31] = struct.pack('<H', 501)
        self.assertIsNone(wire.decode(bytes(packet), 2))
        self.assertEqual(struct.unpack_from('<H', wire.encode_input(0, 0, NO_ACKS, [], hold_ms=30000), 29)[0], wire.MAX_HOLD_MS)

    def test_flags_must_be_zero_and_a_text_from_the_game_is_printable(self):
        ping = bytearray(wire.encode_ping(1, 5))
        self.assertIsNotNone(wire.decode(bytes(ping), 2))
        ping[7] = 1
        self.assertIsNone(wire.decode(bytes(ping), 2))
        hello = pipe.parse_hello(struct.pack('<HBBIIB', pipe.ABI, 2, pipe.CAP_DIGEST, 0, 60000, 6) + b'N\x1bE\x00S\n')
        self.assertEqual(hello.name, 'NES')
        self.assertEqual(pipe.parse_refused(struct.pack('<HB', 1, 5) + b'a\x07\xffb\r')[1], 'ab')


class EndingsTests(unittest.TestCase):
    def test_a_guest_s_out_of_step_is_not_believed_without_the_hosts_own_digests(self):
        # D6: BYE_DESYNC from a guest used to stop every game with "The games went out of step" on its word alone.
        with Fixture(self, desync_confirm=0.3) as fixture:
            driver = fixture.driver
            fixture.say(1, wire.encode_bye(1, wire.BYE_DESYNC, 9))
            self.assertTrue(driver.wait_for(lambda d: d.outcome is not None, 20), driver.snapshot())
            self.assertEqual(driver.outcome, 'seat_left')
            self.assertIsNone(driver.desync)
            self.assertIn('left, reporting the games out of step', driver.detail)
            self.assertEqual(driver.stats['desync_claims'], 1)
            driver.join(30)
            self.assertEqual(fixture.game.stops, [pipe.STOP_ENDED])     # never STOP_DESYNC on a guest's word

    def test_a_host_s_out_of_step_is_believed_by_a_guest(self):
        link = StubLink(1)
        game = RecordingGame()
        driver = LockstepDriver(game, link, Settings(seat=1, seats=2))
        driver.start()
        try:
            self.assertTrue(link.opened.wait(10))
            link.sink(0, wire.encode_bye(0, wire.BYE_DESYNC, 4))
            self.assertTrue(driver.wait_for(lambda d: d.outcome is not None, 20))
            self.assertEqual(driver.outcome, 'desync')
        finally:
            driver.stop()
            driver.join(30)
        self.assertEqual(game.stops, [pipe.STOP_DESYNC])

    def test_a_boot_mismatch_tells_the_culprit_and_the_others_a_neutral_reason(self):
        simulator = LinkSimulator(3, seed=2, latency_ms=2.0)
        games = [RecordingGame(salt=5 if seat == 2 else 0) for seat in range(3)]
        drivers = [LockstepDriver(games[seat], simulator.endpoint(seat), Settings(
            seat=seat, seats=3, delay=2, names=('Arthur', 'Nadia', 'Karl'), local_source=scripted_inputs.local_source(
                {'kind': 'pad', 'seat': seat}))) for seat in range(3)]
        for driver in drivers:
            driver.start()
        try:
            for driver in drivers:
                self.assertTrue(driver.join(60), driver.snapshot())
        finally:
            simulator.close()
        self.assertEqual([driver.outcome for driver in drivers], ['boot_mismatch'] * 3)
        self.assertEqual([game.stops for game in games], [[pipe.STOP_ENDED], [pipe.STOP_ENDED], [pipe.STOP_BOOT_MISMATCH]])
        self.assertIn('Karl', drivers[0].detail)
        self.assertIn('boot digest', drivers[0].detail)                 # the host's converter sees the digests
        self.assertIn('Karl', drivers[1].detail)
        self.assertNotIn('boot digest', drivers[1].detail)              # the other guest is told neither digest nor blame beyond that
        self.assertTrue(drivers[2].detail.startswith('your game'), drivers[2].detail)
        self.assertNotIn('Karl', drivers[2].detail)

    def test_a_boot_digest_counts_only_in_the_gate(self):
        with Fixture(self) as fixture:
            before = dict(fixture.driver._boots)
            fixture.say(1, wire.encode_boot(1, 12345))
            settle(fixture.driver)
            self.assertEqual(fixture.driver._boots, before)             # the match runs: a later BOOT changes nothing


class BoundedMemoryTests(unittest.TestCase):
    def test_a_record_log_speaks_in_frames_and_forgets_the_old_ones(self):
        log = lockstep.RecordLog([(0, 0)] * 2)
        for frame in range(2, 300):
            log.append((frame, 0))
        self.assertEqual(len(log), 300)
        log.trim(10)                                                    # below a chunk: nothing yet
        self.assertEqual(log.base, 0)
        log.trim(200)
        self.assertEqual((len(log), log.base, log[250]), (300, 200, (250, 0)))
        with self.assertRaises(IndexError):
            log[199]
        with self.assertRaises(IndexError):
            log[300]
        self.assertEqual(log.span(150, 3), [(200, 0), (201, 0), (202, 0)])      # the oldest kept, when asked for older
        self.assertEqual(log.span(298, 32), [(298, 0), (299, 0)])
        log.trim(10 ** 9)                                               # never beyond what exists
        self.assertEqual(len(log), 300)

    def test_a_long_match_does_not_keep_every_record_and_digest(self):
        simulator = LinkSimulator(2, seed=4)
        games = [FakeGame() for _ in range(2)]
        drivers = [LockstepDriver(games[seat], simulator.endpoint(seat), Settings(
            seat=seat, seats=2, delay=3, digest_every=10, last_frame=900, local_source=scripted_inputs.local_source(
                {'kind': 'pad', 'seat': seat}))) for seat in range(2)]
        for driver in drivers:
            driver.start()
        try:
            for driver in drivers:
                self.assertTrue(driver.join(90), driver.snapshot())
        finally:
            simulator.close()
        for driver in drivers:
            self.assertEqual(driver.outcome, 'ended', driver.detail)
            self.assertEqual(driver.history_frames, 900)
            self.assertEqual(driver.history, [])                        # not kept: only a test asks for it
            self.assertGreater(len(driver.digests), 0)
            self.assertLessEqual(len(driver.digests), lockstep.DIGESTS_KEPT + 4)      # trimmed every 32 frames
            for log in driver._records:
                self.assertGreaterEqual(len(log), 900)
                self.assertGreater(log.base, 400)
                self.assertLess(len(log._items), 450)                   # a margin behind the match and a window ahead
        self.assertEqual(drivers[0].history_digest, drivers[1].history_digest)      # still the same match on both seats
        self.assertNotEqual(drivers[0].history_digest, 0)
        self.assertEqual(games[0].acc ^ games[0].frames, games[1].acc ^ games[1].frames)

    def test_a_result_too_big_for_the_channel_goes_without_its_history(self):
        small = {'history': [[1, 2]] * 3, 'digests': {'1': 2}, 'outcome': 'ended'}
        self.assertEqual(worker.result_message(small), worker.json.dumps(small).encode())
        big = {'history': [[1, 2, 3, 4]] * 20000, 'digests': {str(frame): frame for frame in range(500)}, 'outcome': 'ended'}
        slim = worker.json.loads(worker.result_message(big, limit=100000))
        self.assertEqual((slim['history'], slim['truncated'], slim['outcome'], len(slim['digests'])), ([], True, 'ended', 64))
        self.assertLess(len(worker.result_message(big, limit=100000)), 100000)


if __name__ == '__main__':
    unittest.main()
