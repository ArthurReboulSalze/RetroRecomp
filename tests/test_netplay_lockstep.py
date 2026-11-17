"""The converter's netplay worker on the delay tier (retrorecomp/netplay, multiplayer stage 1).

Without a compiler: the pipe codec against the C header, the input packets (round trip, bounded parsing), the delay
and time-sync rules, what a HELLO is refused for, the link simulator (the same seed gives every packet the same
fate). With a C compiler and the pinned SDL2 build: tools/netplay_lockstep_selftest.py, two to four fake games each
driven by its own worker process, the workers joined through the link simulator (clean, slow and lossy links, a star
through the host, a boot-digest mismatch, pause, stop, forced desync, lost pipe, silent seat, time sync). No ROM, no visible window, no sound device, and no socket here: only lan_transport.py imports one, and its test is tests/test_netplay_loopback.py."""
import importlib.util
from pathlib import Path
import random
import re
import struct
import threading
import time
import unittest

from retrorecomp.netplay import LinkSimulator, input_records as wire, session_pipe as pipe

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'retrorecomp/netplay'
spec = importlib.util.spec_from_file_location('netplay_lockstep_selftest', ROOT / 'tools' / 'netplay_lockstep_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)


class PipeCodecTests(unittest.TestCase):
    def test_the_numbers_are_the_header_s(self):
        header = (ROOT / 'native/hostkit/hostkit_session.h').read_text(encoding='utf-8')
        constants = {name: int(value) for name, value in re.findall(r'\b(RRHK_\w+) = (\d+)', header)}
        self.assertEqual(constants, pipe.HEADER_NAMES)      # every name of the header, and no other
        for name, value in (('ABI', pipe.ABI), ('MAX_PAYLOAD', pipe.MAX_PAYLOAD), ('MAX_RING', pipe.MAX_RING)):
            self.assertEqual(int(re.search(rf'#define RRHK_SESSION_{name} (\d+)', header).group(1)), value)
        self.assertEqual(re.search(r'#define RRHK_SESSION_ENV "(\w+)"', header).group(1), pipe.ENV)
        limits = (ROOT / 'native/hostkit/hostkit.h').read_text(encoding='utf-8')
        self.assertEqual(int(re.search(r'#define RRHK_MAX_PLAYERS (\d+)', limits).group(1)), pipe.MAX_PLAYERS)
        self.assertIn('within +-20000', header)
        self.assertEqual(pipe.PACE_LIMIT, 20000)

    def test_messages_are_framed_and_bounded(self):
        reader = pipe.MessageReader()
        data = pipe.run(7, (1, 2, 3)) + pipe.digest() + pipe.stop(pipe.STOP_DESYNC)
        got = []
        for index in range(len(data)):                      # one byte at a time
            got += reader.feed(data[index:index + 1])
        self.assertEqual([kind for kind, _ in got], [pipe.MSG_RUN, pipe.MSG_DIGEST, pipe.MSG_STOP])
        self.assertEqual(struct.unpack('<IBB3H', got[0][1]), (7, 0, 3, 1, 2, 3))
        with self.assertRaises(pipe.Broken):
            pipe.MessageReader().feed(struct.pack('<HH', pipe.MSG_LOCAL, pipe.MAX_PAYLOAD + 1))
        with self.assertRaises(pipe.Broken):
            pipe.MessageReader().feed(struct.pack('<HH', 0, 0))
        with self.assertRaises(pipe.Broken):
            pipe.parse_local(b'\0' * 7)
        self.assertEqual(pipe.pace(10 ** 9)[4:], struct.pack('<i', 20000))

    def test_a_hello_is_refused_for_what_stage_1_cannot_do(self):
        def hello(abi=pipe.ABI, players=2, caps=pipe.CAP_DIGEST, rate=60000):
            return pipe.parse_hello(struct.pack('<HBBIIB', abi, players, caps, 0, rate, 3) + b'NES')
        pipe.check_hello(hello(), 2)
        pipe.check_hello(hello(caps=pipe.CAP_DIGEST | pipe.CAP_SNAPSHOT | pipe.CAP_DRIVEN), 1)
        self.assertEqual(hello().name, 'NES')
        self.assertAlmostEqual(hello().frame_seconds, 1 / 60)
        for wrong, word in ((dict(abi=pipe.ABI + 1), 'ABI'), (dict(caps=0), 'digest'),
                            (dict(caps=pipe.CAP_DIGEST | pipe.CAP_POINTER), 'pointer'),
                            (dict(caps=pipe.CAP_DIGEST | pipe.CAP_AXES), 'sticks'),
                            (dict(caps=pipe.CAP_DIGEST | pipe.CAP_KEYBOARD), 'keyboard'), (dict(rate=0), 'frame rate')):
            with self.assertRaisesRegex(pipe.Refused, word):
                pipe.check_hello(hello(**wrong), 2)
        with self.assertRaisesRegex(pipe.Refused, '3 seats'):
            pipe.check_hello(hello(), 3)
        with self.assertRaises(pipe.Broken):
            pipe.parse_hello(b'\1\0\2\2')

    def test_a_name_is_what_a_game_can_draw(self):
        self.assertEqual(pipe.clean_name('Hélène'), b'Helene')
        self.assertEqual(pipe.clean_name('日本'), b'??')
        self.assertEqual(pipe.clean_name('a' * 40), b'a' * 16)
        self.assertEqual(pipe.clean_name('\n'), b'?')
        self.assertEqual(pipe.pause(True, 'Zoë')[4:], b'\x01\x03Zoe')
        self.assertEqual(pipe.pause(False, 'Zoë')[4:], b'\x00\x00')


class InputRecordTests(unittest.TestCase):
    def test_an_input_packet_round_trips(self):
        records = [(frame * 3 & 0xffff, frame & 1) for frame in range(32)]
        data = wire.encode_input(2, 1234, [1300, wire.NONE, 1200, 7], [(2, 1201, records)], delay=5, hold_ms=140,
                                 resume_frame=1100, digest_frame=1199, digest=0xfedcba9876543210)
        packet = wire.decode(data, 4)
        self.assertEqual((packet.kind, packet.seat, packet.sender_frame, packet.acks, packet.delay, packet.hold_ms,
                          packet.resume_frame, packet.digest_frame, packet.digest),
                         (wire.INPUT, 2, 1234, (1300, wire.NONE, 1200, 7), 5, 140, 1100, 1199, 0xfedcba9876543210))
        self.assertEqual(packet.sections, (wire.Section(2, 1201, tuple(records)),))
        self.assertLessEqual(len(data), wire.MAX_PACKET)
        with self.assertRaises(ValueError):
            wire.encode_input(0, 0, [], [(0, 0, [(0, 0)] * 33)])
        self.assertEqual(wire.decode(wire.encode_ping(1, 77), 2).time, 77)
        self.assertEqual(wire.decode(wire.encode_pong(1, 2 ** 32 + 5), 2).time, 5)
        measure = wire.decode(wire.encode_measure(1, 120.2, 19.5), 2)
        self.assertEqual((measure.one_way_ms, measure.jitter_ms), (121, 20))
        bye = wire.decode(wire.encode_bye(0, wire.BYE_DESYNC, 99), 2)
        self.assertEqual((bye.kind, bye.reason, bye.frame, bye.who), (wire.BYE, wire.BYE_DESYNC, 99, wire.NO_SEAT))
        gone = wire.decode(wire.encode_bye(0, wire.BYE_SEAT_GONE, 5, 1), 3)
        self.assertEqual((gone.reason, gone.who), (wire.BYE_SEAT_GONE, 1))
        self.assertIsNone(wire.decode(wire.encode_bye(0, wire.BYE_SEAT_GONE, 5, 3), 3))     # a seat the match does not have
        boot = wire.decode(wire.encode_boot(2, 0xfedcba9876543210), 3)
        self.assertEqual((boot.kind, boot.seat, boot.digest), (wire.BOOT, 2, 0xfedcba9876543210))

    def test_a_packet_out_of_the_rules_is_ignored_whole(self):
        good = wire.encode_input(1, 10, [9, 9], [(1, 8, [(1, 0), (2, 0), (3, 1)])], delay=2)
        self.assertIsNotNone(wire.decode(good, 2))
        self.assertIsNone(wire.decode(good, 1))                             # a seat the match does not have
        self.assertIsNone(wire.decode(b'XXXX' + good[4:], 2))               # another magic
        self.assertIsNone(wire.decode(good[:4] + bytes([wire.PROTO - 1]) + good[5:], 2))    # the first protocol version
        self.assertIsNone(wire.decode(good + b'\0', 2))                     # bytes after the last record
        self.assertIsNone(wire.decode(good + b'\0' * 600, 2))               # above the size limit
        self.assertIsNone(wire.decode(wire.encode_bye(0, wire.BYE_LEFT, 1)[:-6] + b'\x09\0\0\0\0\xff', 2))    # unknown reason
        for cut in range(len(good)):                                        # truncated anywhere
            self.assertIsNone(wire.decode(good[:cut], 2), cut)
        count_at = 8 + wire._INPUT.size + 5                         # the section's record count
        self.assertIsNone(wire.decode(good[:count_at] + b'\xff' + good[count_at + 1:], 2))
        chance = random.Random(5)
        for _ in range(3000):                                               # noise never raises
            noise = bytearray(good)
            for _ in range(chance.randint(1, 6)):
                noise[chance.randrange(len(noise))] = chance.randrange(256)
            packet = wire.decode(bytes(noise[:chance.randint(0, len(noise))]), 2)
            if packet is not None:
                self.assertLess(packet.seat, 2)
                self.assertLessEqual(len(packet.sections), wire.MAX_SECTIONS)
                self.assertTrue(all(len(section.records) <= wire.MAX_RECORDS for section in packet.sections))

    def test_the_delay_covers_the_worst_link(self):
        frame = 1000 / 60
        self.assertEqual(wire.choose_delay(0, 0, frame), 1)                 # the floor: a driver outside the game
        self.assertEqual(wire.choose_delay(1, 5, frame), 2)
        self.assertEqual(wire.choose_delay(15, 5, frame), 3)
        self.assertEqual(wire.choose_delay(60, 5, frame), 5)
        self.assertEqual(wire.choose_delay(120, 20, frame), 10)
        self.assertEqual(wire.choose_delay(150, 0, frame), 10)
        self.assertEqual(wire.choose_delay(2000, 0, frame), 15)             # the cap: such a link is not covered
        self.assertTrue(wire.covers(10, 150, 0, frame))
        self.assertFalse(wire.covers(9, 150, 0, frame))
        self.assertFalse(wire.covers(15, 2000, 0, frame))

    def test_time_sync_only_slows_and_by_two_per_cent_at_most(self):
        self.assertEqual([wire.pace_for(value) for value in (-3, 0, 0.5)], [0, 0, 0])
        self.assertEqual(wire.pace_for(0.6), 2500)
        self.assertEqual(wire.pace_for(1.5), 7500)
        self.assertEqual(wire.pace_for(40), 20000)
        self.assertEqual([wire.pace_for(value, 2.0) for value in (1.9, 2.0, 2.1, 3.0)], [0, 0, 2500, 5000 + 2500])
        values = [wire.pace_for(step / 10) for step in range(0, 60)]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(0 <= value <= pipe.PACE_LIMIT for value in values))


class LinkSimulatorTests(unittest.TestCase):
    def fates(self, seed):
        link = LinkSimulator(3, seed=seed, loss=0.1, duplicate=0.1, reorder=0.1, latency_ms=1.0, jitter_ms=1.0)
        try:
            for index in range(300):
                link.endpoint(index % 3).send((index + 1) % 3, bytes([index & 255]))
            return {key: ''.join(value) for key, value in link.fates.items()}, dict(link.counts)
        finally:
            link.close()

    def test_one_seed_gives_every_packet_the_same_fate(self):
        first, counts = self.fates(11)
        self.assertEqual(self.fates(11)[0], first)
        self.assertNotEqual(self.fates(12)[0], first)
        self.assertTrue(counts['lost'] and counts['duplicated'] and counts['reordered'], counts)

    def test_packets_arrive_late_and_a_silent_seat_hears_nothing(self):
        link = LinkSimulator(2, latency_ms=60.0)
        try:
            got, arrived = [], threading.Event()
            link.endpoint(1).open(lambda source, data: (got.append((source, data, time.monotonic())), arrived.set()))
            sent = time.monotonic()
            link.endpoint(0).send(1, b'one')
            self.assertTrue(arrived.wait(5))
            self.assertEqual(got[0][:2], (0, b'one'))
            self.assertGreaterEqual(got[0][2] - sent, 0.055)                 # held back, not a measure of speed
            link.silence(1, True)
            link.endpoint(0).send(1, b'two')
            link.silence(1, False)
            arrived.clear()
            link.endpoint(0).send(1, b'three')
            self.assertTrue(arrived.wait(5))
            self.assertEqual([item[1] for item in got], [b'one', b'three'])
            self.assertEqual(link.counts['silenced'], 1)
        finally:
            link.close()


class NothingOpenedTests(unittest.TestCase):
    def test_only_the_transport_imports_socket(self):
        """Stage 2: `lan_transport.py` is the one module that imports `socket` (and `selectors`); every other module of the
        package, the worker and the driver included, opens nothing and names no socket call."""
        for path in sorted(PACKAGE.glob('*.py')):
            text = path.read_text(encoding='utf-8')
            if path.name == 'lan_transport.py':
                self.assertRegex(text, r'(?m)^import socket$')
                continue
            self.assertNotRegex(text, r'(?m)^\s*(import|from)\s+(socket|socketserver|asyncio|http|urllib|ssl|selectors)\b',
                                path.name)
            self.assertNotRegex(text, r'\b(socket|bind|listen|sendto|recvfrom|create_connection)\s*\(', path.name)

    def test_a_desync_is_decided_in_one_place(self):
        text = (PACKAGE / 'lockstep.py').read_text(encoding='utf-8')
        self.assertEqual(len(re.findall(r'STOP_DESYNC', text)), 2)      # found here, or reported by another seat
        self.assertIn('def _desync(self', text)


class DriversThroughRealPipesTests(unittest.TestCase):
    def test_two_to_four_worker_processes_stay_in_step_pause_stop_and_end_together(self):
        reason = selftest.fake.ready()
        if reason:
            self.skipTest(reason)
        code, output, seconds = selftest.run_checks(ROOT / '.build/netplay-lockstep-selftest')
        self.assertEqual(code, 0, output)
        self.assertIn(f'PASS: {len(selftest.SCENARIOS)} scenarios', output)
        self.assertEqual(len(selftest.SCENARIOS), 25)
        self.assertLess(seconds, 900, output)     # a hang, not a speed


if __name__ == '__main__':
    unittest.main()
