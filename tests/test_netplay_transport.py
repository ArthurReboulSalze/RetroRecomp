"""The room's transport of multiplayer stage 2, as pure code (`SECURITY_REVIEW.md` sections 2 and 3): the invitation, the
keys, the handshake machines, the control frames, the datagrams and their replay window, the limits on a made-up clock, the
binding rules, the log, and a seeded fuzz of every parser that reads bytes from the network.

No socket is opened here, no port, not even on loopback: the one test that binds (127.0.0.1 only) is
tests/test_netplay_loopback.py. No ROM, no window, no real time (clocks are made up), every loop bounded.
"""
import hashlib
import json
import random
import socket
import struct
import threading
import time
import tracemalloc
import types
from unittest import mock
import unittest

from retrorecomp.netplay import WorkerProcess, control, datagram, handshake, invitation, limits, room_log, session_pipe as pipe
from retrorecomp.netplay import input_records as wire, worker_channel as channel
from retrorecomp.netplay import lan_transport, room_worker
from retrorecomp.netplay.launch import Refusal, launch_settings
from retrorecomp.netplay.lockstep import Settings

SECRET = bytes(range(16))
NONCE_G, NONCE_H = bytes(range(100, 116)), bytes(range(200, 216))


def counting_rng(*values):
    items = list(values)
    return lambda size: items.pop(0)


# ---- 1. the keys ----

class KeyTests(unittest.TestCase):
    def test_mac_is_keyed_blake2b_over_length_prefixed_parts(self):
        key = b'k' * 16
        independent = hashlib.blake2b(key=key, digest_size=16)
        for part in (b'a', b'bc'):
            independent.update(len(part).to_bytes(2, 'little') + part)
        self.assertEqual(handshake.mac(key, b'a', b'bc'), independent.digest())
        self.assertEqual(handshake.mac(key, b'a', b'bc').hex(), '032fc6d2da12d958a592a427d2e23595')
        self.assertNotEqual(handshake.mac(key, b'ab', b'c'), handshake.mac(key, b'a', b'bc'))      # no two inputs collide
        self.assertNotEqual(handshake.mac(key, b'', b'a'), handshake.mac(key, b'a', b''))
        self.assertEqual(len(handshake.mac(key, b'x', n=32)), 32)

    def test_each_key_of_the_review_against_a_frozen_vector(self):
        self.assertEqual(handshake.auth_key(SECRET).hex(), '615a8330ff37edda235b0ac9a94500de20df580f438298c996ecc3765a20a190')
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        self.assertEqual(session.hex(), 'fb376067577d0e436fa8703741979d18ef0104886b03591d60f7151e19b771ad')
        to_host, to_guest = handshake.tcp_keys(session)
        self.assertEqual(to_host.hex(), '94d68ccf4baee771d0c45d40665f27fbab40cd9ab46d60bc9c3413e0a5c28106')
        self.assertEqual(to_guest.hex(), 'b1e6b0398d7f1b15eb2108696e7d55e9d9206084e115a1222b412615b3dc95a0')
        up, down = handshake.udp_keys(session, 7, 2)
        self.assertEqual(up.hex(), 'bd729025ec9c413d577e6538c61980aa6447f459d7820c33c92e597961790ed6')
        self.assertEqual(down.hex(), 'a947835b2e37042242e1d8ca16be73327a8d29c4ffab4722a1cf623f9d739cee')
        auth = handshake.auth_key(SECRET)
        self.assertEqual(handshake._first(auth, 3, NONCE_G).hex(), 'ebeadc61998180a5e2c10f437ec88026')
        self.assertEqual(handshake._proof_host(auth, 3, NONCE_G, NONCE_H).hex(), '653e49c3c2a71af882b3aff9c317d680')
        self.assertEqual(handshake._proof_guest(auth, 3, NONCE_G, NONCE_H).hex(), '95ddf32339e0daee51e2c3b7eb625c84')

    def test_two_directions_two_matches_two_seats_and_two_connections_give_different_keys(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        keys = {handshake.tcp_keys(session)[0], handshake.tcp_keys(session)[1]}
        for match in (1, 2):
            for seat in (1, 2):
                keys.update(handshake.udp_keys(session, match, seat))
        keys.add(handshake.session_key(SECRET, 3, NONCE_G, bytes(16)))       # another connection (another host nonce)
        keys.add(handshake.session_key(SECRET, 4, NONCE_G, NONCE_H))         # another protocol number
        keys.add(handshake.session_key(bytes(16), 3, NONCE_G, NONCE_H))      # another secret
        self.assertEqual(len(keys), 2 + 8 + 3)


# ---- 2. the invitation ----

class InvitationTests(unittest.TestCase):
    def test_round_trip_and_case(self):
        text = invitation.format_invitation('192.168.1.20', 24611, SECRET)
        self.assertEqual(text, 'rr1:lan:192.168.1.20:24611:AAAQEAYEAUDAOCAJBIFQYDIOB4')
        found = invitation.parse(f'  {text.lower()}\n')
        self.assertEqual((found.address, found.port, found.secret), ('192.168.1.20', 24611, SECRET))
        random_secret = invitation.new_secret()
        self.assertEqual(len(random_secret), 16)
        self.assertEqual(invitation.parse(invitation.format_invitation('10.1.2.3', 65535, random_secret)).secret, random_secret)

    def test_every_malformed_class_is_refused_without_repeating_the_text(self):
        good = 'rr1:lan:192.168.1.20:24611:AAAQEAYEAUDAOCAJBIFQYDIOB4'
        secret = 'AAAQEAYEAUDAOCAJBIFQYDIOB4'
        bad = [
            good.replace('rr1', 'rr2'), good.replace('lan', 'wan'), 'rr1:net:192.168.1.20:24611:' + secret,
            'rr1:lan:example.com:24611:' + secret, 'rr1:lan:8.8.8.8:24611:' + secret, 'rr1:lan:1.1.1.1:24611:' + secret,
            'rr1:lan:100.63.255.255:24611:' + secret, 'rr1:lan:100.128.0.1:24611:' + secret, 'rr1:lan:127.0.0.1:24611:' + secret,
            'rr1:lan:0.0.0.0:24611:' + secret, 'rr1:lan:192.168.001.20:24611:' + secret, 'rr1:lan:192.168.1.256:24611:' + secret,
            'rr1:lan:192.168.1:24611:' + secret, 'rr1:lan:::1:24611:' + secret,
            'rr1:lan:192.168.1.20:0:' + secret, 'rr1:lan:192.168.1.20:1023:' + secret, 'rr1:lan:192.168.1.20:70000:' + secret,
            'rr1:lan:192.168.1.20:024611:' + secret, 'rr1:lan:192.168.1.20:2461x:' + secret, 'rr1:lan:192.168.1.20::' + secret,
            'rr1:lan:192.168.1.20:24611:' + secret[:25], 'rr1:lan:192.168.1.20:24611:' + secret + 'A',
            'rr1:lan:192.168.1.20:24611:' + secret[:-1] + '1', 'rr1:lan:192.168.1.20:24611:' + secret[:-1] + 'B',
            'rr1:lan:192.168.1.20:24611:' + secret[:-1] + '=', 'rr1:lan:192.168.1.20:24611:' + 'A' * 65,
            good + ':extra', 'rr1:lan:192.168.1.20:24611', '', ' ', 'rr1', 'RR1:lan:192.168.1.20:24611:' + secret,
            good.replace('1.20', '1.20 '), good.replace(':24611', ': 24611'), good.replace('1.20', '１.20'), good + '\x00',
        ]
        for text in bad:
            with self.assertRaises(invitation.InvitationError, msg=text):
                invitation.parse(text)
            try:
                invitation.parse(text)
            except invitation.InvitationError as error:
                self.assertNotIn(text.strip()[:12] or 'zzz', error.reason + 'x' if len(text.strip()) > 12 else 'x')
                self.assertNotIn(secret, error.reason)
        for not_text in (None, 5, b'rr1:lan:192.168.1.20:24611:' + secret.encode(), ['x']):
            with self.assertRaises(invitation.InvitationError):
                invitation.parse(not_text)
        with self.assertRaisesRegex(invitation.InvitationError, 'no Internet room'):
            invitation.parse('rr1:net:192.168.1.20:24611:' + secret)

    def test_the_ranges_are_written_out_and_loopback_is_for_tests_only(self):
        for address in ('10.0.0.1', '10.255.255.255', '172.16.0.1', '172.31.255.255', '192.168.0.1', '169.254.1.1',
                        '100.64.0.1', '100.127.255.255'):
            self.assertTrue(invitation.is_lan_address(address), address)
        for address in ('9.255.255.255', '172.15.255.255', '172.32.0.0', '192.167.255.255', '169.253.0.1', '100.63.255.255',
                        '100.128.0.0', '8.8.8.8', '0.0.0.0', '255.255.255.255', '224.0.0.1', '127.0.0.1', '127.0.0.2', '', 'x'):
            self.assertFalse(invitation.is_lan_address(address), address)
        self.assertTrue(invitation.is_lan_address('127.0.0.1', tests=True))
        self.assertFalse(invitation.is_lan_address('127.0.0.2', tests=True))      # exactly one loopback address, for the test
        self.assertEqual(invitation.parse('rr1:lan:127.0.0.1:30000:' + invitation.encode_secret(SECRET), tests=True).address, '127.0.0.1')


# ---- 3. the handshake ----

def shake(secret_host=SECRET, secret_guest=SECRET, proto=handshake.PROTO, nonces=None, now=0.0):
    nonces = nonces or limits.NonceMemory()
    host = handshake.HostHandshake(secret_host, now, nonces, counting_rng(NONCE_H))
    guest = handshake.GuestHandshake(secret_guest, now, counting_rng(NONCE_G), proto)
    return host, guest


class HandshakeTests(unittest.TestCase):
    def run_handshake(self, host, guest, now=0.0):
        step1 = host.feed(guest.first(), now)
        if step1.closed:
            return step1, None, None
        step2 = guest.feed(step1.send, now)
        if step2.closed:
            return step1, step2, None
        return step1, step2, host.feed(step2.send, now)

    def test_a_right_secret_gives_both_ends_the_same_session_and_nothing_secret_goes_on_the_wire(self):
        host, guest = shake()
        first = guest.first()
        self.assertEqual(len(first), handshake.FIRST_SIZE)
        step1, step2, step3 = self.run_handshake(host, guest)
        self.assertEqual(len(step1.send), handshake.SECOND_SIZE)
        self.assertTrue(step2.done and len(step2.send) == handshake.THIRD_SIZE)
        self.assertTrue(step3.done and step3.leftover == b'')
        self.assertEqual(host.session.key, guest.session.key)
        self.assertEqual(host.session.key, handshake.session_key(SECRET, 3, NONCE_G, NONCE_H))
        for wire_bytes in (first, step1.send, step2.send):
            self.assertNotIn(SECRET, wire_bytes)
            self.assertNotIn(host.session.key, wire_bytes)
        self.assertEqual(first[:4], b'RRNP')

    def test_a_wrong_secret_gets_silence_from_the_host_and_none_is_sent_back_by_the_guest(self):
        host, guest = shake(secret_guest=bytes(16))
        step = host.feed(guest.first(), 0.0)
        self.assertTrue(step.closed)
        self.assertEqual(step.send, b'')                  # a stranger gets zero bytes
        self.assertEqual(step.reason, 'tag')
        host, guest = shake(secret_host=bytes(16))        # the host that does not hold the secret: the guest answers nothing
        step1 = host.feed(guest.first(), 0.0)
        self.assertTrue(step1.closed and step1.send == b'')

    def test_message_two_from_a_peer_without_the_secret_is_refused_by_the_guest(self):
        _host, guest = shake()
        guest.first()
        forged = guest.feed(bytes(16) + bytes(16), 0.0)
        self.assertTrue(forged.closed and forged.send == b'' and not forged.done)
        _host, guest = shake()
        for blob in (b'', b'\x00' * 31):
            self.assertEqual(guest.feed(blob, 0.0), handshake.Step())      # not enough yet: no answer either

    def test_message_one_replayed_is_refused_and_so_is_an_old_proof_at_step_three(self):
        nonces = limits.NonceMemory()
        host, guest = shake(nonces=nonces)
        first = guest.first()
        self.run_handshake(host, guest)
        replayed = handshake.HostHandshake(SECRET, 1.0, nonces, counting_rng(NONCE_H))
        step = replayed.feed(first, 1.0)
        self.assertTrue(step.closed and step.send == b'' and step.reason == 'replay')
        # message 1 replayed against a host with no memory: it answers message 2, and then the old proof fails over the new nonce
        fresh = handshake.HostHandshake(SECRET, 2.0, limits.NonceMemory(), counting_rng(bytes(range(50, 66))))
        reply = fresh.feed(first, 2.0)
        self.assertEqual(len(reply.send), 32)
        _h, old_guest = shake()
        old_guest.first()
        old_step = old_guest.feed(NONCE_H + handshake._proof_host(handshake.auth_key(SECRET), 3, NONCE_G, NONCE_H), 0.0)
        late = fresh.feed(old_step.send, 2.0)
        self.assertTrue(late.closed and late.send == b'' and late.reason == 'proof')

    def test_another_protocol_number_still_reaches_a_tagged_session_for_the_reject(self):
        host, guest = shake(proto=4)
        _s1, _s2, step3 = self.run_handshake(host, guest)
        self.assertTrue(step3.done)
        self.assertEqual(host.session.proto, 4)
        self.assertEqual(host.session.key, guest.session.key)       # both ends can seal and read the REJECT(version)
        to_host, to_guest = handshake.tcp_keys(host.session.key)
        frame = control.FrameWriter(to_guest).seal(control.Reject(control.REJECT_VERSION))
        self.assertEqual(control.FrameReader(to_guest, control.FROM_HOST).feed(frame), [control.Reject(control.REJECT_VERSION)])

    def test_bytes_delivered_one_at_a_time_and_pipelined_frames_after_message_three(self):
        host, guest = shake()
        first = guest.first()
        for index in range(len(first) - 1):
            self.assertEqual(host.feed(first[index:index + 1], 0.0), handshake.Step())
        step1 = host.feed(first[-1:], 0.0)
        self.assertEqual(len(step1.send), 32)
        got = handshake.Step()
        for index in range(len(step1.send)):
            got = guest.feed(step1.send[index:index + 1], 0.0)
        self.assertTrue(got.done)
        to_host, _to_guest = handshake.tcp_keys(guest.session.key)
        hello = control.FrameWriter(to_host).seal(control.Hello((1, 2, 3), 'Nadia'))
        for index, byte in enumerate(got.send + hello):
            step = host.feed(bytes([byte]), 0.0)
            if step.done:
                self.assertEqual(index, len(got.send) - 1)
                break
        host2, guest2 = shake()
        s1 = host2.feed(guest2.first(), 0.0)
        s2 = guest2.feed(s1.send, 0.0)
        pipelined = host2.feed(s2.send + hello, 0.0)
        self.assertTrue(pipelined.done)
        self.assertEqual(pipelined.leftover, hello)         # the frames that came behind message three are kept

    def test_the_deadline_and_extra_bytes_and_a_wrong_magic(self):
        host, guest = shake()
        self.assertTrue(host.feed(b'', 4.99) == handshake.Step() and not host.expired(4.99))
        self.assertTrue(host.expired(5.0))
        self.assertEqual(host.feed(guest.first(), 5.0).reason, 'deadline')
        host, guest = shake()
        self.assertEqual(host.feed(guest.first() + b'x', 0.0).reason, 'size')       # nothing can follow message 1
        host, _guest = shake()
        step = host.feed(b'GET /', 0.0)
        self.assertTrue(step.closed and step.send == b'' and step.reason == 'magic')
        guest_deadline = handshake.GuestHandshake(SECRET, 0.0, counting_rng(NONCE_G))
        self.assertTrue(guest_deadline.expired(5.0))


# ---- 4. the control frames ----

LAUNCH = control.Launch(7, 2, 3, 0, 60, 3, 'nes', bytes(range(32)), bytes(range(32, 64)), ('Arthur', 'Nadia', 'Hélène'), 'speed=1\nx=y')
ALL_MESSAGES = (control.Welcome(2, 4), control.Reject(control.REJECT_FULL), control.Hello((1, 7, 9), 'Hélène'), LAUNCH,
                control.Launched(7, control.LAUNCHED_READY), control.End(7, wire.BYE_ENDED, 0xff), control.Ping(5), control.Pong(5),
                control.Bye(1))


class ControlTests(unittest.TestCase):
    def keys(self):
        return handshake.tcp_keys(handshake.session_key(SECRET, 3, NONCE_G, NONCE_H))

    def test_every_message_round_trips_through_a_sealed_frame_one_byte_at_a_time(self):
        to_host, to_guest = self.keys()
        for key, allowed, messages in ((to_host, control.FROM_GUEST, [m for m in ALL_MESSAGES if isinstance(m, (
                control.Hello, control.Launched, control.End, control.Ping, control.Pong, control.Bye))]),
                                       (to_guest, control.FROM_HOST, [m for m in ALL_MESSAGES if isinstance(m, (
                                           control.Welcome, control.Reject, control.Launch, control.End, control.Ping,
                                           control.Pong, control.Bye))])):
            writer, reader = control.FrameWriter(key), control.FrameReader(key, allowed)
            data = b''.join(writer.seal(message) for message in messages)
            got = []
            for index in range(len(data)):
                got += reader.feed(data[index:index + 1])
            self.assertEqual(got, messages)

    def test_a_frame_replayed_reordered_cut_or_from_the_other_direction_fails_the_tag(self):
        to_host, to_guest = self.keys()
        writer = control.FrameWriter(to_host)
        first, second = writer.seal(control.Ping(1)), writer.seal(control.Ping(2))
        with self.assertRaises(control.FrameError):
            control.FrameReader(to_host, control.FROM_GUEST).feed(second)               # reordered (a sequence of 1)
        reader = control.FrameReader(to_host, control.FROM_GUEST)
        reader.feed(first)
        with self.assertRaises(control.FrameError):
            reader.feed(first)                                                         # replayed
        with self.assertRaises(control.FrameError):
            control.FrameReader(to_guest, control.FROM_GUEST).feed(first)              # reflected: another key
        for index in range(len(first) * 8):                                            # every bit flipped: never a message
            damaged = bytearray(first)
            damaged[index // 8] ^= 1 << (index % 8)
            try:
                self.assertEqual(control.FrameReader(to_host, control.FROM_GUEST).feed(bytes(damaged)), [], index)   # a longer length: waits
            except control.FrameError:
                pass
        cut = control.FrameReader(to_host, control.FROM_GUEST)
        self.assertEqual(cut.feed(first[:-1]), [])                                      # a cut frame waits
        with self.assertRaises(control.FrameError):
            control.FrameReader(to_host, control.FROM_GUEST).feed(first[:-1] + bytes([first[-1] ^ 1]))

    def test_a_length_above_the_limit_and_an_unexpected_type_are_refused_on_the_header(self):
        to_host, _to_guest = self.keys()
        with self.assertRaises(control.FrameError):
            control.FrameReader(to_host, control.FROM_GUEST).feed(struct.pack('<HB', control.MAX_PAYLOAD + 1, control.PING))
        control.FrameReader(to_host, control.FROM_GUEST).feed(struct.pack('<HB', control.MAX_PAYLOAD, control.PING))   # waits: allowed
        for kind in (control.WELCOME, control.REJECT, control.LAUNCH, 0, 10, 255):      # a guest may not say these
            with self.assertRaises(control.FrameError, msg=kind):
                control.FrameReader(to_host, control.FROM_GUEST).feed(struct.pack('<HB', 0, kind))
        with self.assertRaises(ValueError):
            control.FrameWriter(to_host).seal(control.Launch(1, 1, 2, 0, 60, 3, 'nes', bytes(32), bytes(32), ('a', 'b'), 'x' * 600))

    def test_a_payload_of_the_wrong_size_or_a_field_out_of_range_is_refused(self):
        for kind, payload in [(control.WELCOME, b'\x01'), (control.WELCOME, b'\x00\x04'), (control.WELCOME, b'\x04\x04'),
                              (control.WELCOME, b'\x01\x05'), (control.REJECT, b'\x09'), (control.REJECT, b''),
                              (control.HELLO, b'\x00' * 6), (control.HELLO, struct.pack('<3HB', 1, 2, 3, 2) + b'a'),
                              (control.HELLO, struct.pack('<3HB', 1, 2, 3, 0)), (control.HELLO, struct.pack('<3HB', 1, 2, 3, 1) + b'\xff'),
                              (control.HELLO, struct.pack('<3HB', 1, 2, 3, 49) + b'a' * 49),
                              (control.LAUNCHED, struct.pack('<IB', 1, 4)), (control.END, struct.pack('<IBB', 1, 7, 0)),
                              (control.END, struct.pack('<IBB', 1, 3, 9)), (control.PING, b'abc'), (control.BYE, b'\x09'),
                              (control.LAUNCH, b''), (control.LAUNCH, control.encode(LAUNCH)[1] + b'x'),
                              (control.LAUNCH, control.encode(LAUNCH)[1][:-1])]:
            with self.assertRaises(control.FrameError, msg=(kind, payload)):
                control.decode(kind, payload)
        launch = control.encode(LAUNCH)[1]
        self.assertEqual(control.decode(control.LAUNCH, launch), LAUNCH)

    def test_the_names_are_cleaned_as_the_review_says(self):
        self.assertEqual(control.display_name(b'  Nadia   Bell \t'), 'Nadia Bell')
        self.assertEqual(control.display_name('Zo' + chr(0x301) + 'e'), 'Z' + chr(0xf3) + 'e')                      # NFC
        self.assertEqual(control.display_name('a' + chr(0x200b) + 'b' + chr(0x202e) + 'c' + chr(0) + 'd' + chr(7) + 'e'), 'abcde')   # Cf and Cc removed
        self.assertEqual(control.display_name('x' + chr(0xe000) + 'y'), 'xy')                                    # private use
        self.assertEqual(control.display_name('x' * 40), 'x' * 16)
        self.assertLessEqual(len(control.display_name('\U0001f600' * 30).encode('utf-8')), control.MAX_NAME_BYTES)
        self.assertEqual(control.display_name(b'\xff\xfe', 'Player 2'), 'Player 2')                              # not repaired
        self.assertEqual(control.display_name('​\x00', 'Player 3'), 'Player 3')
        taken = ['Nadia', 'nadia (2)']
        self.assertEqual(control.unique_name('Nadia', taken), 'Nadia (3)')
        self.assertEqual(control.unique_name('Karl', taken), 'Karl')
        self.assertLessEqual(len(control.unique_name('A' * 16, ['A' * 16])), 16)


# ---- 5. the datagrams ----

KEY = handshake.udp_keys(handshake.session_key(SECRET, 3, NONCE_G, NONCE_H), 7, 2)[0]


def packet(kind, seat, *args):
    return {wire.INPUT: wire.encode_input, wire.PING: wire.encode_ping, wire.PONG: wire.encode_pong,
            wire.MEASURE: wire.encode_measure, wire.BYE: wire.encode_bye, wire.BOOT: wire.encode_boot}[kind](seat, *args)


class DatagramTests(unittest.TestCase):
    def test_seal_and_open_round_trip_every_type_at_the_smallest_and_the_largest_sizes(self):
        sections = [(owner, 5, [(1, 0)] * 32) for owner in (1, 2, 3)]
        largest = wire.encode_input(0, 9, [1, 2, 3, 4], sections, delay=4, hold_ms=500, resume_frame=3, digest_frame=8, digest=7)
        inner = {wire.INPUT: largest, wire.PING: wire.encode_ping(2, 5), wire.PONG: wire.encode_pong(2, 5),
                 wire.MEASURE: wire.encode_measure(2, 3, 4), wire.BYE: wire.encode_bye(2, wire.BYE_LEFT, 9),
                 wire.BOOT: wire.encode_boot(2, 11)}
        for kind, data in inner.items():
            seat = 0 if kind == wire.INPUT else 2
            split = datagram.split_inner(data, seat)
            self.assertEqual(split[0], kind)
            sealed = datagram.seal(KEY, kind, 2, 7, 1, split[1])
            self.assertTrue(datagram.MIN_SIZE <= len(sealed) <= datagram.MAX_SIZE, (kind, len(sealed)))
            found = datagram.open_(sealed, lambda seat_, match: KEY if (seat_, match) == (2, 7) else None)
            self.assertEqual(found, (2, kind, 1, split[1]))
            self.assertEqual(datagram.join_inner(kind, seat, split[1]), data)        # the driver's packet, head rebuilt
        self.assertEqual(len(datagram.seal(KEY, wire.INPUT, 0, 7, 1, datagram.split_inner(largest, 0)[1])), 478)
        smallest = datagram.seal(KEY, wire.PING, 2, 7, 1, struct.pack('<I', 1))
        self.assertEqual(len(smallest), datagram.MIN_SIZE)

    def test_every_single_bit_flip_of_a_sealed_datagram_is_refused(self):
        for body in (struct.pack('<I', 5), bytes(range(200)) + bytes(242)):
            sealed = datagram.seal(KEY, wire.PING if len(body) == 4 else wire.INPUT, 2, 7, 3, body)
            lookup = lambda seat, match: KEY      # even with the key found for whatever seat and match the damaged head says
            for index in range(len(sealed) * 8):
                damaged = bytearray(sealed)
                damaged[index // 8] ^= 1 << (index % 8)
                self.assertIsNone(datagram.open_(bytes(damaged), lookup), index)
            for cut in range(len(sealed)):
                self.assertIsNone(datagram.open_(sealed[:cut], lookup))
            self.assertIsNone(datagram.open_(sealed + b'\0', lookup))

    def test_direction_match_and_seat_are_in_the_key(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        up, down = handshake.udp_keys(session, 1, 1)
        sealed = datagram.seal(up, wire.PING, 1, 1, 1, struct.pack('<I', 1))
        self.assertIsNotNone(datagram.open_(sealed, lambda seat, match: up))
        self.assertIsNone(datagram.open_(sealed, lambda seat, match: down))              # a guest-to-host datagram, host-to-guest key
        self.assertIsNone(datagram.open_(sealed, lambda seat, match: handshake.udp_keys(session, 2, 1)[0]))      # match 1 in match 2
        self.assertIsNone(datagram.open_(sealed, lambda seat, match: handshake.udp_keys(session, 1, 2)[0]))      # seat 2's key for seat 1
        for body in (b'x', b'x' * (datagram.MAX_BODY + 1)):
            with self.assertRaises(ValueError):
                datagram.seal(up, wire.PING, 1, 1, 1, body)
        with self.assertRaises(ValueError):
            datagram.seal(up, wire.PING, 1, 1, 0, struct.pack('<I', 1))             # the counter counts from 1
        with self.assertRaises(ValueError):
            datagram.seal(up, 99, 1, 1, 1, struct.pack('<I', 1))

    def test_the_replay_window(self):
        window = datagram.ReplayWindow()
        self.assertFalse(window.accept(0))
        for counter in (1, 2, 3):
            self.assertTrue(window.accept(counter))
        self.assertFalse(window.accept(2))                    # a duplicate
        self.assertTrue(window.accept(100))
        self.assertFalse(window.accept(100))
        self.assertTrue(window.accept(100 - 63))              # the 64th counter of the window: once
        self.assertFalse(window.accept(100 - 63))
        self.assertFalse(window.accept(100 - 64))             # one further back: refused
        self.assertFalse(window.accept(3))                    # old and seen, and out of the window
        self.assertTrue(window.accept(50))                    # in the window, never seen: taken once
        self.assertFalse(window.accept(50))
        self.assertTrue(window.accept(100 + 2 ** 32))         # a jump of 2^32 is fine and forgets the past
        self.assertFalse(window.accept(100))
        self.assertTrue(window.accept(100 + 2 ** 32 - 5))
        self.assertFalse(window.accept(1 << 64))
        self.assertFalse(window.accept(-1))
        window = datagram.ReplayWindow()
        self.assertTrue(window.accept((1 << 64) - 1))
        self.assertFalse(window.accept((1 << 64) - 1))

    def test_a_datagram_from_nowhere_costs_no_hash(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        up, _down = handshake.udp_keys(session, 1, 1)
        counters = limits.Counters()
        receiver = datagram.HostReceiver(counters, 0.0)
        receiver.begin_match(1, {1: ('192.168.1.5', up)}, 0.0, seat_count=2)
        good = datagram.seal(up, wire.PING, 1, 1, 1, struct.pack('<I', 9))
        other_match = datagram.seal(up, wire.PING, 1, 2, 1, struct.pack('<I', 9))
        other_seat = datagram.seal(up, wire.PING, 3, 1, 1, struct.pack('<I', 9))
        calls = []
        real = datagram._tag

        def counting(key, data):
            calls.append(1)
            return real(key, data)
        with mock.patch.object(datagram, '_tag', counting):
            for source, data in [(('10.0.0.9', 5000), good),                                           # an address nobody authenticated
                                 (('192.168.1.5', 5000), good[:39]), (('192.168.1.5', 5000), good + bytes(500)),     # sizes
                                 (('192.168.1.5', 5000), b'x' * 100),                                         # not a datagram
                                 (('192.168.1.5', 5000), other_match),                                        # another match
                                 (('192.168.1.5', 5000), other_seat)]:                                        # not a seat of that address
                self.assertIsNone(receiver.receive(source, data, 0.0))
            self.assertEqual(calls, [], 'a datagram that fails steps 1 to 3 must not be hashed')
            accepted = receiver.receive(('192.168.1.5', 5000), good, 0.0)
            self.assertEqual(len(calls), 1)
            self.assertEqual((accepted.seat, accepted.address), (1, ('192.168.1.5', 5000)))
            self.assertEqual(wire.decode(accepted.packet).seat, 1)
        self.assertEqual(counters.total['source'], 1)
        self.assertEqual(counters.total['size'], 2)
        self.assertEqual(counters.total['format'], 3)

    def test_the_host_learns_a_seats_port_from_the_newest_datagram_only(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        up, _down = handshake.udp_keys(session, 1, 1)
        receiver = datagram.HostReceiver(limits.Counters(), 0.0)
        receiver.begin_match(1, {1: ('192.168.1.5', up)}, 0.0, seat_count=2)
        body = struct.pack('<I', 9)
        receiver.receive(('192.168.1.5', 5000), datagram.seal(up, wire.PING, 1, 1, 5, body), 0.0)
        self.assertEqual(receiver.channels[1].port, 5000)
        receiver.receive(('192.168.1.5', 6000), datagram.seal(up, wire.PING, 1, 1, 3, body), 0.0)       # an older counter: not a move
        self.assertEqual(receiver.channels[1].port, 5000)
        receiver.receive(('192.168.1.5', 6000), datagram.seal(up, wire.PING, 1, 1, 6, body), 0.0)
        self.assertEqual(receiver.channels[1].port, 6000)

    def test_the_guest_takes_only_the_hosts_exact_address_and_port(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        _up, down = handshake.udp_keys(session, 1, 1)
        receiver = datagram.GuestReceiver(limits.Counters(), ('192.168.1.2', 24611), 1, 1, down, 2, 0.0)
        good = datagram.seal(down, wire.PING, 0, 1, 1, struct.pack('<I', 9))
        for source in (('192.168.1.2', 24612), ('192.168.1.3', 24611)):
            self.assertIsNone(receiver.receive(source, good, 0.0))
        self.assertIsNone(receiver.receive(('192.168.1.2', 24611), datagram.seal(down, wire.PING, 1, 1, 2, struct.pack('<I', 9)), 0.0))
        accepted = receiver.receive(('192.168.1.2', 24611), good, 0.0)
        self.assertEqual(accepted.seat, 0)
        self.assertEqual(wire.decode(accepted.packet).kind, wire.PING)
        self.assertIsNone(receiver.receive(('192.168.1.2', 24611), good, 0.0))      # replayed


# ---- 6. the limits, on a made-up clock ----

class LimitTests(unittest.TestCase):
    def setUp(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        self.up, _down = handshake.udp_keys(session, 1, 1)
        self.counters = limits.Counters()
        self.receiver = datagram.HostReceiver(self.counters, 0.0)
        self.receiver.begin_match(1, {1: ('192.168.1.5', self.up)}, 0.0, seat_count=2)
        self.counter = 0

    def damaged(self, counter):
        data = bytearray(datagram.seal(self.up, wire.PING, 1, 1, counter, bytes(4)))
        data[-1] ^= 1
        return bytes(data)

    def send(self, now):
        self.counter += 1
        return self.receiver.receive(('192.168.1.5', 5000), datagram.seal(self.up, wire.PING, 1, 1, self.counter, struct.pack('<I', 9)), now)

    def test_a_seat_has_a_burst_of_60_then_240_a_second_and_is_reported_after_five_seconds_over(self):
        first = [self.send(0.0) is not None for _ in range(100)]
        self.assertEqual(sum(first), 60)                      # the bucket of 60
        self.assertEqual(self.counters.total['seat_rate'], 40)
        self.assertFalse(self.receiver.over(0.0))
        self.assertEqual(sum(self.send(1.0) is not None for _ in range(100)), 60)        # a second later: refilled to the burst
        now = 1.0
        for _ in range(int(5.5 * 400)):                       # 400 a second for five and a half seconds: above 240 all the time
            now += 1 / 400
            self.send(now)
        self.assertEqual(self.receiver.over(now), [1])
        self.assertEqual(self.receiver.over(now + 2.0), [])   # a gap longer than a second ends the streak
        quiet = datagram.HostReceiver(limits.Counters(), 0.0)
        quiet.begin_match(1, {1: ('192.168.1.5', self.up)}, 0.0, seat_count=2)
        for step in range(0, 10 * 200):                       # 200 a second (an honest seat is 110 to 170): never over
            self.counter += 1
            quiet.receive(('192.168.1.5', 5000), datagram.seal(self.up, wire.PING, 1, 1, self.counter, struct.pack('<I', 9)), step / 200)
        self.assertEqual(quiet.over(10.0), [])
        self.assertEqual(quiet.counters.total['seat_rate'], 0)

    def test_the_address_bucket_is_before_the_tag_and_counts_what_it_drops(self):
        calls = []
        real = datagram._tag
        garbage = [self.damaged(index + 1) for index in range(3000)]     # the right head, a wrong tag
        with mock.patch.object(datagram, '_tag', lambda key, data: (calls.append(1), real(key, data))[1]):
            for data in garbage:                              # 2,000 reach the tag check, the rest are dropped before it
                self.receiver.receive(('192.168.1.5', 5000), data, 0.0)
        self.assertEqual(len(calls), 2000)                    # the burst of the address bucket (a CPU guard, review L1)
        self.assertEqual(self.counters.total['address_rate'], 1000)
        self.assertEqual(self.counters.total['tag'], 2000)

    def test_a_spoofer_with_the_seats_address_cannot_starve_the_real_seat_review_l1(self):
        """The head of a datagram is public (magic, match, seat): copied with the seat's source address and a wrong tag, it
        used to take a token of the address bucket (1,000 a second): at 5,000 a second the real seat (150) was starved."""
        garbage = self.damaged(1)
        accepted = refused = 0
        for step in range(5000 * 2):                          # two seconds: 5,000 forged datagrams a second
            now = step / 5000
            self.receiver.receive(('192.168.1.5', 5000), garbage, now)
            if step % 33 == 0:                                # about 150 real datagrams a second, from the same address
                if self.send(now) is not None:
                    accepted += 1
                else:
                    refused += 1
        self.assertGreater(accepted + refused, 250)
        self.assertEqual(refused, 0)

    def test_the_whole_room_bucket_holds_40000_a_second_across_addresses(self):
        receiver = datagram.HostReceiver(limits.Counters(), 0.0)
        seats = {seat: (f'10.0.0.{seat}', self.up) for seat in range(1, 5)}
        receiver.begin_match(1, seats, 0.0, seat_count=5)
        for index in range(2000):
            for seat in range(1, 5):               # 8,000 forged datagrams from four addresses, all at once
                data = bytearray(datagram.seal(self.up, wire.PING, seat, 1, index + 1, bytes(4)))
                data[-1] ^= 1
                receiver.receive((f'10.0.0.{seat}', 5000), bytes(data), 0.0)
        self.assertEqual(receiver.counters.total['address_rate'] + receiver.counters.total['tag'], 8000)
        self.assertEqual(receiver.counters.total['tag'], limits.TOTAL_BURST)      # the all-sources burst reaches the tag check
        self.assertEqual((limits.ADDRESS_RATE, limits.TOTAL_RATE), (20000.0, 40000.0))

    def test_unauthenticated_connections_handshake_failures_and_the_five_minute_refusal(self):
        admission = limits.Admission()
        self.assertTrue(admission.may_accept('10.0.0.1', 0.0))
        admission.opened('10.0.0.1')
        admission.opened('10.0.0.1')
        self.assertFalse(admission.may_accept('10.0.0.1', 0.0))            # two per source address
        self.assertTrue(admission.may_accept('10.0.0.2', 0.0))
        for number in range(2, 8):
            admission.opened(f'10.0.1.{number}')
        self.assertEqual(sum(admission._open.values()), 8)
        self.assertFalse(admission.may_accept('10.0.0.9', 0.0))            # eight in the room
        admission.closed('10.0.0.1')
        self.assertTrue(admission.may_accept('10.0.0.9', 0.0))
        self.assertTrue(admission.may_accept('10.0.0.1', 0.0))
        admission = limits.Admission()
        self.assertFalse(admission.failed('10.0.0.3', 0.0))
        self.assertFalse(admission.failed('10.0.0.3', 30.0))
        self.assertTrue(admission.failed('10.0.0.3', 59.0))                # the third in a minute
        self.assertFalse(admission.may_accept('10.0.0.3', 60.0))
        self.assertFalse(admission.may_accept('10.0.0.3', 358.9))
        self.assertTrue(admission.may_accept('10.0.0.3', 359.1))           # five minutes after the third failure
        for moment in (0.0, 61.0, 122.0, 183.0):                           # three failures but never three in a minute
            self.assertFalse(limits.Admission().failed('10.0.0.4', moment))
        spread = limits.Admission()
        self.assertEqual([spread.failed('10.0.0.4', moment) for moment in (0.0, 61.0, 122.0, 183.0)], [False] * 4)
        many = limits.Admission()
        for number in range(limits.TABLE_LIMIT * 3):                       # a flood of sources never grows the table without bound
            many.failed(f'10.{number // 256}.{number % 256}.1', 0.0)
        self.assertLessEqual(len(many._failures), limits.TABLE_LIMIT)

    def test_the_control_frame_bucket_is_20_a_second_with_a_burst_of_40(self):
        bucket = limits.TokenBucket(limits.FRAME_RATE, limits.FRAME_BURST, 0.0)
        self.assertEqual(sum(bucket.take(0.0) for _ in range(100)), 40)
        self.assertEqual(sum(bucket.take(1.0) for _ in range(100)), 20)

    def test_the_nonce_memory_holds_the_last_64(self):
        memory = limits.NonceMemory(64)
        for number in range(70):
            memory.remember(bytes([number]) * 16)
        self.assertFalse(memory.seen(bytes([0]) * 16))
        self.assertTrue(memory.seen(bytes([69]) * 16))
        self.assertTrue(memory.seen(bytes([6]) * 16))


# ---- 7. binding: what the module can bind ----

class BindingTests(unittest.TestCase):
    def test_the_address_is_checked_before_any_socket_exists(self):
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('a socket was made')):
            for bad in ('0.0.0.0', '', '::', '::1', 'localhost', '127.0.0.1', '8.8.8.8', '100.63.255.255', '100.128.0.1', '255.255.255.255',
                        ' 192.168.1.2', '192.168.1.2 ', '192.168.1.256', None, 5, '192.168.1.2\n'):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    lan_transport.RoomHost(bad, 30000)
            for good in ('192.168.1.2', '10.0.0.1', '172.20.0.5', '169.254.9.9', '100.64.0.1', '100.100.100.100'):
                lan_transport.RoomHost(good, 30000)
            lan_transport.RoomHost('127.0.0.1', 30000, tests=True)
            with self.assertRaises(ValueError):
                lan_transport.RoomHost('127.0.0.2', 30000, tests=True)
            for bad_port in (0, 80, 1023, 65536, -1, True, 'x'):
                with self.assertRaises(ValueError, msg=bad_port):
                    lan_transport.RoomHost('192.168.1.2', bad_port)
            with self.assertRaises(ValueError):
                lan_transport.RoomHost('192.168.1.2', 30000, capacity=5)
            with self.assertRaises(ValueError):
                lan_transport.RoomHost('192.168.1.2', 30000, secret=b'short')

    def test_a_guest_refuses_a_public_invitation_before_any_socket_exists(self):
        public = invitation.Invitation('8.8.8.8', 30000, SECRET)
        with mock.patch.object(socket, 'socket', side_effect=AssertionError('a socket was made')):
            with self.assertRaises(lan_transport.RoomError):
                lan_transport.RoomGuest(public, 'x')
            with self.assertRaises(lan_transport.RoomError):
                lan_transport.RoomGuest(invitation.Invitation('127.0.0.1', 30000, SECRET), 'x')

    def test_the_only_module_that_binds_never_names_a_wildcard_address(self):
        with open(lan_transport.__file__, encoding='utf-8') as source:
            text = source.read()
        for wildcard in ("'0.0.0.0'", '"0.0.0.0"', "bind(('',", 'bind(("",', "'::'", 'INADDR_ANY', 'SO_BROADCAST', 'SO_REUSEPORT'):
            self.assertNotIn(wildcard, text, wildcard)
        self.assertEqual(text.count('.bind('), 3)        # the TCP listener, the UDP socket, the guest's UDP socket: each on a checked address
        self.assertIn('SO_EXCLUSIVEADDRUSE', text)


# ---- 8. the log ----

class LogTests(unittest.TestCase):
    def test_the_log_formats_what_it_is_given_and_has_no_place_for_a_secret(self):
        log = room_log.RoomLog(None)
        log.room('opened', '192.168.1.2', 24611)
        log.joined('Nadia\x00\n', '192.168.1.5')
        log.launch(3, 'nes', bytes(range(32)), 2, 0)
        log.counts({('tag', '10.0.0.9'): 5}, now=100.0, force=True)
        text = '\n'.join(log.lines)
        self.assertIn('stamp 00010203,', text)                  # eight hex digits of the stamp, no more
        self.assertNotIn('0405', text)
        self.assertIn('refused tag x5 from 10.0.0.9', text)
        self.assertNotIn('\x00', text)
        self.assertEqual(len(text.splitlines()), 4)

    def test_a_file_is_kept_to_a_mebibyte_with_one_older_file(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'room.log'
            log = room_log.RoomLog(path)
            for _ in range(30000):
                log.note('x' * 80)
            self.assertTrue(path.exists() and path.with_suffix('.log.1').exists())
            self.assertLess(path.stat().st_size, room_log.LIMIT + 200)
            self.assertEqual(sorted(item.name for item in Path(folder).iterdir()), ['room.log', 'room.log.1'])

    def test_the_log_ten_second_lines_are_one_per_reason_and_address_not_one_per_packet(self):
        log = room_log.RoomLog(None, clock=lambda: 0.0)
        counters = limits.Counters()
        for _ in range(500):
            counters.count('source', '10.0.0.9')
        counters.count('tag', '10.0.0.9')
        self.assertFalse(log.counts(counters.take_window(), now=5.0))       # not due yet
        counters.count('source', '10.0.0.9')
        self.assertTrue(log.counts(counters.take_window(), now=10.0))
        self.assertEqual(len(log.lines), 1)


# ---- 9. a whole match's datagrams, host to guest and back, with no socket ----

class RoundTripTests(unittest.TestCase):
    def test_a_host_and_a_guest_receiver_carry_driver_packets_both_ways(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        up, down = handshake.udp_keys(session, 4, 1)
        counters = limits.Counters()
        host_rx = datagram.HostReceiver(counters, 0.0)
        host_rx.begin_match(4, {1: ('192.168.1.5', up)}, 0.0, seat_count=2)
        guest_rx = datagram.GuestReceiver(counters, ('192.168.1.2', 24611), 4, 1, down, 2, 0.0)
        guest_tx, host_tx = datagram.Sender(up, 4, 1), datagram.Sender(down, 4, 0)
        for index in range(100):
            ping = wire.encode_ping(1, index)
            kind, body = datagram.split_inner(ping, 1)
            got = host_rx.receive(('192.168.1.5', 5000), guest_tx.pack(kind, body), index * 0.01)
            self.assertEqual((got.seat, got.packet), (1, ping))
            pong = wire.encode_input(0, index, [index, 0, 0, 0], [(1, index, [(3, 0)])])
            kind, body = datagram.split_inner(pong, 0)
            got = guest_rx.receive(('192.168.1.2', 24611), host_tx.pack(kind, body), index * 0.01)
            self.assertEqual((got.seat, got.packet), (0, pong))
        self.assertEqual(sum(counters.total.values()), 0)
        self.assertIsNone(datagram.split_inner(wire.encode_ping(2, 1), 1))              # a packet of another seat is not sent
        self.assertIsNone(datagram.split_inner(b'RRNG\x02\x02\x01\x01' + bytes(4), 1))   # flags set
        self.assertIsNone(datagram.split_inner(b'RRNG\x01\x02\x01\x00' + bytes(4), 1))   # another protocol of the driver
        self.assertIsNone(datagram.split_inner(wire.encode_ping(1, 1) + bytes(datagram.MAX_BODY), 1))


# ---- 9b. the worker of a room and the room's idle question, without a socket ----

class WorkerRoomTests(unittest.TestCase):
    def test_the_test_hooks_need_the_test_flag_and_the_network_can_never_set_them(self):
        base = Settings(seat=0, seats=2)
        with self.assertRaises(ValueError):
            room_worker.test_settings(base, {'keep_history': True}, tests=False)
        with self.assertRaises(ValueError):
            room_worker.test_settings(base, {'seat': 3}, tests=True)             # not a test hook: refused even under tests
        with self.assertRaises(ValueError):
            room_worker.test_settings(base, {'topology': 'mesh'}, tests=True)
        changed = room_worker.test_settings(base, {'keep_history': True, 'last_frame': 9, 'local_source': {'kind': 'pad', 'seat': 0}}, True)
        self.assertTrue(changed.keep_history and changed.last_frame == 9 and callable(changed.local_source))
        self.assertIs(room_worker.test_settings(base, {}, tests=False), base)
        for name in ('local_source', 'words_filter', 'clock_ppm', 'topology'):       # launch_settings never takes them from a launch
            self.assertIsInstance(launch_settings({'seat': 1, 'seats': 2, name: 1}), Refusal)

    def test_a_measured_delay_above_eight_is_applied_with_one_lobby_line(self):
        for delay, preset, told in ((11, None, 1), (8, None, 0), (9, None, 1), (11, 11, 0)):
            sent = []

            class Writer:
                def send(self, kind, payload=b''):
                    sent.append((kind, json.loads(payload)))
                    return True
            worker = room_worker.RoomWorker({'room': {'role': 'host'}}, channel.Reader(), Writer(), 0)
            driver = types.SimpleNamespace(delay=delay, settings=types.SimpleNamespace(delay=preset), snapshot=lambda: {'seat': 0})
            match = room_worker._Match(5, driver, None, True)
            with mock.patch.object(room_worker, 'STATUS_EVERY', 0.005):
                thread = threading.Thread(target=worker._report, args=(match,))
                thread.start()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline and len([item for item in sent if item[0] == channel.EVENT]) < told:
                    time.sleep(0.01)
                time.sleep(0.05)
                match.finished.set()
                thread.join(5)
            events = [item[1] for item in sent if item[0] == channel.EVENT]
            self.assertEqual(len(events), told, (delay, preset, events))
            if told:
                self.assertEqual((events[0]['event'], events[0]['delay'], events[0]['detail']),
                                 ('slow_link', delay, f'Slow link: delay of {delay} frames'))

    def test_an_empty_room_asks_once_after_thirty_minutes_and_not_while_anyone_is_in_it(self):
        now = [1000.0]
        heard = []
        host = lan_transport.RoomHost('127.0.0.1', 30000, tests=True, on_event=heard.append, clock=lambda: now[0])
        host._timers(now[0] + 1799)
        host._flush()
        self.assertEqual(heard, [])
        host._timers(now[0] + 1801)
        host._timers(now[0] + 2500)
        host._flush()
        self.assertEqual([event['event'] for event in heard], ['room_idle'])
        self.assertNotIn('127.0.0.1', json.dumps(heard))


# ---- 10. the fuzz: seeded, bounded, over every parser that reads bytes of the network ----

FUZZ_INPUTS = 20000
SLOWEST = 0.25           # seconds one input may take (a loose bound: a busy PC is not a finding; a loop on an input would be)


def mutations(rng, valid):
    """Inputs near the valid ones: cut at every length, extended, bit flips, a field set to 0, 1, 255, 65535, all ones, two glued."""
    for item in valid:
        for cut in range(len(item)):
            yield item[:cut]
    while True:
        item = bytearray(rng.choice(valid))
        action = rng.randrange(6)
        if action == 0 and item:
            item[rng.randrange(len(item))] ^= 1 << rng.randrange(8)
        elif action == 1:
            item += bytes(rng.randrange(256) for _ in range(rng.randrange(1, 601)))
        elif action == 2 and item:
            for _ in range(rng.randrange(1, 4)):
                item[rng.randrange(len(item))] = rng.choice((0, 1, 2, 3, 0x7f, 0x80, 0xfe, 0xff))
        elif action == 3 and len(item) >= 2:
            at = rng.randrange(len(item) - 1)
            item[at:at + 2] = rng.choice((b'\x00\x00', b'\x01\x00', b'\xff\xff', b'\x00\x01', b'\x00\x04', b'\x00\x05'))
        elif action == 4:
            item += rng.choice(valid)
        else:
            item = bytearray(rng.randrange(256) for _ in range(rng.randrange(0, 700)))
        yield bytes(item)


class FuzzTests(unittest.TestCase):
    """A fixed seed and a fixed count, so the run is the same every time (a longer run by hand: FUZZ_INPUTS)."""

    def run_target(self, name, valid, target, refusal=(), accepted_property=None, count=FUZZ_INPUTS, text=False):
        rng = random.Random(f'fuzz:{name}')
        inputs = mutations(rng, valid)
        slowest, accepted, started = 0.0, 0, time.perf_counter()
        for index in range(count):
            data = next(inputs)
            if text:
                data = data.decode('latin-1')
            before = time.perf_counter()
            try:
                result = target(data)
            except refusal:
                result = None
            except Exception as error:                  # any other exception is a finding
                self.fail(f'{name}: {type(error).__name__}: {error} on input {index}: {data!r}')
            slowest = max(slowest, time.perf_counter() - before)
            if result is not None:
                accepted += 1
                if accepted_property is not None:
                    accepted_property(data, result)
        self.assertLess(slowest, SLOWEST, f'{name}: one input took {slowest:.3f} s')
        self.assertLess(time.perf_counter() - started, 60, f'{name} took too long')
        # memory: no input needs more than 64 KiB (the peak of a sample, measured by tracemalloc)
        tracemalloc.start()
        sample = mutations(random.Random(f'memory:{name}'), valid)
        peak = 0
        for _ in range(300):
            data = next(sample)
            data = data.decode('latin-1') if text else data
            tracemalloc.reset_peak()
            base = tracemalloc.get_traced_memory()[0]
            try:
                target(data)
            except refusal:
                pass
            peak = max(peak, tracemalloc.get_traced_memory()[1] - base)
        tracemalloc.stop()
        self.assertLess(peak, 64 * 1024, f'{name}: {peak} bytes for one input')
        return accepted

    def test_the_invitation_parser(self):
        valid = [invitation.format_invitation('192.168.1.20', 24611, SECRET).encode(),
                 invitation.format_invitation('100.100.1.1', 65535, bytes(range(16, 32))).encode()]

        def canonical(data, found):
            again = invitation.format_invitation(found.address, found.port, found.secret).encode()
            self.assertEqual(again.lower(), data.strip().encode().lower())
        accepted = self.run_target('invitation', valid, invitation.parse, (invitation.InvitationError,), canonical, text=True)
        self.assertGreater(accepted, 0)        # case flips and the like still parse: the canonical property was exercised

    def test_the_control_decoders_and_the_frame_reader(self):
        valid = [control.encode(message)[1] for message in ALL_MESSAGES]
        kinds = [control.encode(message)[0] for message in ALL_MESSAGES]
        for kind in range(0, 12):
            payloads = [payload for payload, own in zip(valid, kinds) if own == kind] or valid

            def target(data, kind=kind):
                return control.decode(kind, data)

            def canonical(data, message, kind=kind):
                self.assertEqual(control.encode(message), (kind, data))
            self.run_target(f'control-{kind}', payloads, target, (control.FrameError,), canonical, count=2000)
        to_host, to_guest = handshake.tcp_keys(handshake.session_key(SECRET, 3, NONCE_G, NONCE_H))
        stream = [b''.join(control.FrameWriter(to_guest).seal(message) for message in ALL_MESSAGES
                           if control.encode(message)[0] in control.FROM_HOST)]
        stream += [control.FrameWriter(to_guest).seal(message) for message in ALL_MESSAGES if control.encode(message)[0] in control.FROM_HOST]

        def reader(data):
            return control.FrameReader(to_guest, control.FROM_HOST).feed(data) or None
        self.run_target('frames', stream, reader, (control.FrameError,), count=4000)

    def test_the_datagram_parsers_and_both_receivers(self):
        session = handshake.session_key(SECRET, 3, NONCE_G, NONCE_H)
        up, down = handshake.udp_keys(session, 1, 1)
        valid = [datagram.seal(up, wire.PING, 1, 1, 1, struct.pack('<I', 5)),
                 datagram.seal(up, wire.BYE, 1, 1, 2, struct.pack('<BIB', 2, 9, 0xff)),
                 datagram.seal(up, wire.INPUT, 1, 1, 3, datagram.split_inner(
                     wire.encode_input(1, 5, [3, 4, 0, 0], [(1, 2, [(1, 0)] * 3)], digest_frame=3, digest=9), 1)[1])]

        def head(data):
            return datagram.parse_head(data)

        def opened(data):
            return datagram.open_(data, lambda seat, match: up)

        def host(data):
            receiver = datagram.HostReceiver(limits.Counters(), 0.0)
            receiver.begin_match(1, {1: ('192.168.1.5', up)}, 0.0, seat_count=2)
            return receiver.receive(('192.168.1.5', 5000), data, 0.0)

        def guest(data):
            return datagram.GuestReceiver(limits.Counters(), ('1.1.1.1', 1), 1, 1, down, 2, 0.0).receive(('1.1.1.1', 1), data, 0.0)

        def reseal(data, result):                 # what is accepted is exactly a datagram that was sealed: the same bytes
            self.assertEqual(datagram.seal(up, result[1], result[0], 1, result[2], result[3]), data)
        self.run_target('datagram-head', valid, head)
        self.run_target('datagram-open', valid, opened, (), reseal)
        self.run_target('host-receiver', valid, host, count=5000)
        self.run_target('guest-receiver', valid, guest, count=5000)

    def test_the_input_record_decoder_and_the_driver_packets_inside(self):
        valid = [wire.encode_input(1, 5, [3, 4, 0, 0], [(1, 2, [(1, 0)] * 3), (2, 0, [(5, 1)])], delay=3, hold_ms=20, digest_frame=3, digest=9),
                 wire.encode_ping(1, 5), wire.encode_pong(1, 5), wire.encode_measure(1, 3, 4), wire.encode_bye(1, 2, 9, 0xff), wire.encode_boot(1, 9)]
        self.run_target('input-records', valid, lambda data: wire.decode(data, 4))

    def test_the_two_handshake_machines(self):
        host_valid = [handshake.GuestHandshake(SECRET, 0.0, counting_rng(NONCE_G)).first()]
        guest_valid = [NONCE_H + handshake._proof_host(handshake.auth_key(SECRET), 3, NONCE_G, NONCE_H)]

        def host(data):
            machine = handshake.HostHandshake(SECRET, 0.0, limits.NonceMemory(), counting_rng(NONCE_H))
            step = machine.feed(data, 0.0)
            if not step.done:
                self.assertTrue(step.send == b'' or len(step.send) == handshake.SECOND_SIZE)      # never more than message 2
                if step.closed:
                    self.assertEqual(step.send, b'')                                              # a stranger gets zero bytes
            return step if step.send else None

        def guest(data):
            machine = handshake.GuestHandshake(SECRET, 0.0, counting_rng(NONCE_G))
            step = machine.feed(data, 0.0)
            if step.closed:
                self.assertEqual(step.send, b'')
            return step if step.done else None
        # a stranger's bytes, never the valid message of the secret, are the whole input: only the valid ones may succeed
        self.run_target('handshake-host', host_valid, host, count=5000)
        self.run_target('handshake-guest', guest_valid, guest, count=5000)

    def test_the_other_readers_of_the_package(self):
        channel_valid = [channel.frame(channel.CONFIG, b'{}'), channel.frame(channel.NET_IN, b'\x01abc') + channel.frame(channel.CALL, b'{}'),
                         channel.frame(channel.EVENT, b'{"event": "x"}')]
        self.run_target('worker-channel', channel_valid, lambda data: channel.Reader().feed(data) or None, (channel.Broken,), count=5000)
        pipe_valid = [pipe.run(7, (1, 2, 3)) + pipe.digest() + pipe.stop(pipe.STOP_DESYNC), pipe.setup(1, 2, 0, guest=True, options='a=b'),
                      struct.pack('<HBBIIB', pipe.ABI, 2, pipe.CAP_DIGEST, 0, 60000, 3) + b'NES']
        self.run_target('pipe-messages', pipe_valid, lambda data: pipe.MessageReader().feed(data) or None, (pipe.Broken,), count=5000)
        for name, parse in (('hello', pipe.parse_hello), ('local', pipe.parse_local), ('digest-of', pipe.parse_digest_of),
                            ('refused', pipe.parse_refused), ('exit', pipe.parse_exit)):
            self.run_target(f'pipe-{name}', pipe_valid[2:] + [bytes(range(1, 20))], parse, (pipe.Broken,), count=3000)

    def test_launch_settings_never_raises_on_a_decoded_launch(self):
        rng = random.Random('launch')
        for _ in range(3000):
            fields = {'seat': rng.choice((0, 1, 2, 3, 4, -1, 2 ** 40, None, 'x')), 'seats': rng.choice((1, 2, 3, 4, 5, 0, None)),
                      'names': rng.choice((['a', 'b'], [], None, ['é' * 100, '\x00'], list('abcd'))),
                      'delay': rng.choice((None, 0, 1, 15, 16, -1)), 'digest_every': rng.choice((0, 9, 10, 600, 601, 60)),
                      'redundancy': rng.choice((0, 1, 8, 9)), 'options': rng.choice(('', 'a=b', 'x' * 5000, 'a=b\nc', 'é', 'A=b'))}
            self.assertTrue(isinstance(launch_settings(fields), (Settings, Refusal)))



# ---- 10. the fixes after the transport review (TRANSPORT_REVIEW.md, N1 to N5, L1, L3, L4, L7): no socket, no thread ----

class FakeSock:
    """A socket that is not one: queued `recv` results (bytes, or an exception to raise), a `send` that takes everything or
    blocks, and flags for what the test wants to see."""

    def __init__(self, chunks=(), blocked=False, setblocking_error=None):
        self.chunks, self.blocked, self.setblocking_error = list(chunks), blocked, setblocking_error
        self.sent, self.closed = bytearray(), False

    def recv(self, size):
        if not self.chunks:
            raise BlockingIOError()
        item = self.chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def send(self, data):
        if self.blocked:
            raise BlockingIOError()
        self.sent += data
        return len(data)

    def setblocking(self, flag):
        if self.setblocking_error:
            raise self.setblocking_error

    def setsockopt(self, *args):
        pass

    def fileno(self):
        return 77

    def close(self):
        self.closed = True


class FakeSelector:
    def __init__(self, register_error=None):
        self.register_error, self.registered = register_error, []

    def register(self, sock, events, data):
        if self.register_error:
            raise self.register_error
        self.registered.append(sock)

    def unregister(self, sock):
        if sock not in self.registered:
            raise KeyError(sock)
        self.registered.remove(sock)

    def close(self):
        pass


class FakeListener:
    def __init__(self, *socks):
        self.queue = list(socks)

    def accept(self):
        if not self.queue:
            raise BlockingIOError()
        return self.queue.pop(0), ('192.168.1.9', 5000)


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def fake_host(clock=None, **keywords):
    """A `RoomHost` that was never opened: no socket, no thread; the tests call its methods the way its thread would."""
    host = lan_transport.RoomHost('127.0.0.1', 40000, SECRET, 4, tests=True, clock=clock or Clock(), **keywords)
    host._selector = FakeSelector()
    return host


def stranger(host, ip, chunks, now=0.0, blocked=False):
    """A connection that was accepted and is still shaking hands (what `_accept` leaves)."""
    sock = FakeSock(chunks, blocked)
    peer = lan_transport._Peer(sock, ip, 5000, now, handshake.HostHandshake(SECRET, now, host._nonces, counting_rng(NONCE_H)))
    host._admission.opened(ip)
    host._peers.append(peer)
    host._selector.registered.append(sock)
    return peer


GUEST_NUMBER = [0]


def joined_guest(host, ip, now=0.0, blocked=False):
    """A guest that holds the secret and does the whole handshake through the host's own `_readable`."""
    GUEST_NUMBER[0] += 1
    guest = handshake.GuestHandshake(SECRET, now, counting_rng(bytes([GUEST_NUMBER[0] % 250 + 1]) * 16))
    peer = stranger(host, ip, [guest.first()], now)
    host._readable(peer, now)
    step = guest.feed(bytes(peer.sock.sent), now)
    peer.sock.chunks.append(step.send)
    peer.sock.blocked = blocked
    host._readable(peer, now)
    return peer


class ReviewFixTests(unittest.TestCase):
    # -- N1 --
    def test_n1_a_stranger_who_closes_by_himself_counts_as_a_failure_and_ends_in_a_refusal(self):
        host = fake_host()
        for attempt, ending in enumerate((b'', ConnectionResetError(10054), b'')):    # three connections, three ways to leave
            self.assertTrue(host._admission.may_accept('192.168.1.9', 1.0 + attempt))
            peer = stranger(host, '192.168.1.9', [b'RRN', ending], now=1.0 + attempt)      # a piece of message 1, then gone
            host._readable(peer, 1.0 + attempt)
            host._readable(peer, 1.0 + attempt)
            self.assertTrue(peer.dead)
            self.assertEqual(peer.sock.sent, b'')                                  # nothing was ever sent to him
        self.assertEqual(host._counters.total['handshake_closed'], 3)
        self.assertFalse(host._admission.may_accept('192.168.1.9', 4.0))           # refused for five minutes
        self.assertTrue(host._admission.may_accept('192.168.1.10', 4.0))           # and only that address
        self.assertEqual(sum(host._admission._open.values()), 0)                   # no slot is held

    def test_n1_four_addresses_cannot_hold_the_rooms_eight_slots_for_ever(self):
        host = fake_host()
        for address in range(4):
            for attempt in range(3):
                ip = f'192.168.1.{20 + address}'
                if host._admission.may_accept(ip, float(attempt)):
                    peer = stranger(host, ip, [b'x', b''], now=float(attempt))
                    host._readable(peer, float(attempt))
                    host._readable(peer, float(attempt))
        self.assertTrue(all(not host._admission.may_accept(f'192.168.1.{20 + address}', 5.0) for address in range(4)))
        self.assertEqual(len(host._peers), 0)
        self.assertTrue(host._admission.may_accept('192.168.1.99', 5.0))           # a real guest from another address is let in

    def test_n1_a_guest_that_is_through_its_handshake_is_not_a_failure_when_it_leaves(self):
        host = fake_host()
        peer = joined_guest(host, '192.168.1.30')
        self.assertIsNotNone(peer.guest_id)
        peer.sock.chunks.append(b'')
        host._readable(peer, 1.0)
        self.assertTrue(peer.dead)
        self.assertEqual(host._counters.total['handshake_closed'], 0)

    # -- N2 --
    def test_n2_joins_per_address_are_six_a_minute_then_five_minutes_of_refusal(self):
        admission = limits.Admission()
        self.assertEqual([admission.joined('10.0.0.1', moment / 10) for moment in range(7)], [True] * 6 + [False])
        self.assertTrue(admission.refused('10.0.0.1', 200.0))
        self.assertFalse(admission.may_accept('10.0.0.1', 200.0))
        self.assertTrue(admission.may_accept('10.0.0.1', 301.0))
        self.assertTrue(admission.joined('10.0.0.2', 0.5))                         # another address is not concerned
        spread = limits.Admission()
        self.assertTrue(all(spread.joined('10.0.0.3', moment * 11.0) for moment in range(30)))   # a join every 11 s: never six in a minute
        many = limits.Admission()
        for number in range(limits.TABLE_LIMIT * 3):                               # the table never grows without bound
            many.joined(f'10.{number // 256}.{number % 256}.1', 0.0)
        self.assertLessEqual(len(many._joins), limits.TABLE_LIMIT)

    def test_n2_the_seventh_join_in_a_minute_is_closed_with_no_event_and_the_address_is_refused(self):
        host = fake_host()
        events = []
        host._on_event = events.append
        peers = [joined_guest(host, '192.168.1.40', now=float(number)) for number in range(7)]
        self.assertIsNotNone(peers[0].guest_id)
        self.assertTrue(peers[6].dead)
        self.assertIsNone(peers[6].guest_id)
        self.assertEqual(len(peers[6].sock.sent), handshake.SECOND_SIZE)            # message 2 of the handshake, then not even a WELCOME or a REJECT
        self.assertEqual(host._counters.total['join_rate'], 1)
        self.assertTrue(host._admission.refused('192.168.1.40', 7.0))
        self.assertFalse(host._admission.may_accept('192.168.1.40', 7.0))
        self.assertEqual(sum(host._admission._open.values()), 0)                    # the slot count is right (no double release)

    def test_n2_a_worker_process_keeps_the_last_thousand_events_and_counts_every_one(self):
        worker = WorkerProcess({'room': {'role': 'host'}}, command=['never started'])
        for number in range(2500):
            worker._event({'event': 'joined' if number % 2 else 'left', 'n': number})
        self.assertEqual(len(worker.events), 1000)
        self.assertEqual(worker.events[-1]['n'], 2499)
        self.assertEqual(worker.event_count, 2500)
        self.assertEqual((worker.event_totals['joined'], worker.event_totals['left']), (1250, 1250))
        worker._event({'event': 'match_over', 'n': 2500})
        self.assertEqual(worker.wait_event('match_over', 0.0, after=2500)['n'], 2500)    # `after` counts in events ever reported
        self.assertIsNone(worker.wait_event('match_over', 0.0, after=2501))
        self.assertIsNone(worker.wait_event('joined', 0.0, after=2501))

    # -- N3 --
    def test_n3_a_window_of_many_sources_is_sixteen_lines_and_one_more_in_one_open(self):
        import tempfile
        from pathlib import Path
        opens = []
        real_open = open

        def counting_open(*args, **keywords):
            opens.append(args)
            return real_open(*args, **keywords)
        with tempfile.TemporaryDirectory() as folder:
            log = room_log.RoomLog(Path(folder) / 'room.log', clock=lambda: 0.0)
            window = {('tag', f'10.0.{number // 256}.{number % 256}'): number + 1 for number in range(256)}
            with mock.patch.object(room_log, 'open', counting_open, create=True):
                self.assertTrue(log.counts(window, now=10.0))
            text = (Path(folder) / 'room.log').read_text(encoding='utf-8')
        self.assertEqual(len(opens), 1)
        lines = text.splitlines()
        self.assertEqual(len(lines), room_log.COUNT_LINES + 1)
        self.assertIn('x256 from 10.0.0.255', text)                                   # the largest sources are the ones named
        self.assertIn(f'refused x{sum(range(1, 241))} more from 240 other', lines[-1])
        self.assertEqual(len(log.lines), 17)

    def test_n3_the_counts_are_written_after_the_rooms_lock_is_released(self):
        host = fake_host()
        seen = []

        class Probe(room_log.RoomLog):
            def due(self, now=None):
                return True

            def counts(self, window, now=None, force=False):
                answer = []

                def other_thread():                 # what the driver's send does: it needs the room's lock
                    answer.append(host._lock.acquire(blocking=False))
                    if answer[0]:
                        host._lock.release()
                thread = threading.Thread(target=other_thread)
                thread.start()
                thread.join(5)
                seen.append(answer[0])
                return True
        host.log = Probe(None)
        host._counters.count('tag', '192.168.1.77')
        host._tick([], 20.0)
        self.assertEqual(seen, [True])                                            # called once, and the lock was free

    # -- N4 --
    def test_n4_a_peer_that_never_reads_is_closed_at_64_kib_of_waiting_bytes(self):
        stream = lan_transport._Stream(FakeSock(blocked=True), '192.168.1.5', 5000, 0.0)
        writes = 0
        while stream.write(b'p' * 512):
            writes += 1
            self.assertLessEqual(writes, 200)                                      # bounded, whatever the peer does
        self.assertTrue(stream.closed and stream.overflow)
        self.assertLessEqual(len(stream.pending), lan_transport.PENDING_LIMIT)
        self.assertEqual(writes, lan_transport.PENDING_LIMIT // 512)               # the write that passed the limit is the one refused
        self.assertFalse(stream.write(b'more'))

    def test_n4_the_host_closes_such_a_peer_and_frees_its_place(self):
        host = fake_host()
        peer = joined_guest(host, '192.168.1.50', blocked=True)
        self.assertIn(peer, host._peers)
        for _ in range(300):                                                        # bounded, whatever the code does
            if not peer.write(b'pong' * 128):
                break
        host._timers(1.0)
        self.assertTrue(peer.dead and peer.sock.closed)
        self.assertNotIn(peer, host._peers)
        self.assertEqual(len([other for other in host._peers if other.guest_id is not None]), 0)

    def test_n4_a_peer_being_turned_away_is_closed_after_two_seconds_whatever_waits(self):
        clock = Clock()
        host = fake_host(clock)
        peer = joined_guest(host, '192.168.1.51', blocked=True)
        self.assertTrue(host.kick(peer.guest_id))                                   # its REJECT cannot leave
        self.assertTrue(peer.closing and peer.waiting())
        host._timers(1.9)
        self.assertIn(peer, host._peers)
        host._timers(lan_transport.CLOSING_SECONDS)
        self.assertNotIn(peer, host._peers)
        self.assertTrue(peer.sock.closed)

    def test_n4_a_guest_whose_host_never_reads_ends_the_connection(self):
        guest = lan_transport.RoomGuest(invitation.Invitation('192.168.1.5', 24611, SECRET), 'Nadia', tests=True)
        guest._stream = lan_transport._Stream(FakeSock(blocked=True), '192.168.1.5', 24611, 0.0)
        for _ in range(300):
            if not guest._stream.write(b'ping' * 128):
                break
        guest._timers(1.0)
        self.assertTrue(guest._gone)
        self.assertEqual([item[1]['event'] for item in guest._outbox if item[0] == 'event'], ['host_gone'])

    # -- N5 --
    def test_n5_an_error_on_a_new_socket_closes_that_socket_and_nothing_else(self):
        for broken in (FakeSock(setblocking_error=OSError(10038, 'not a socket')), FakeSock()):
            host = fake_host()
            host._tcp = FakeListener(broken)
            if broken.setblocking_error is None:
                host._selector = FakeSelector(register_error=OSError(24, 'too many open files'))
            host._accept(0.0)                                                      # raises nothing
            self.assertTrue(broken.closed)
            self.assertEqual(host._counters.total['accept_error'], 1)
            self.assertEqual(sum(host._admission._open.values()) + len(host._peers), 0)    # no half-made peer is left behind
        host = fake_host()                                                          # the room goes on: the next one is accepted
        host._tcp = FakeListener(FakeSock(setblocking_error=OSError(1, 'x')), FakeSock())
        host._accept(0.0)
        self.assertEqual(len(host._peers), 1)
        self.assertEqual(sum(host._admission._open.values()), 1)

    # -- L1 (the tests are with the others: the address bucket, the whole-room bucket and the spoofer) --

    # -- L3, L4, L7 --
    def test_l3_the_refusal_table_is_bounded_too(self):
        admission = limits.Admission()
        for number in range(limits.TABLE_LIMIT * 3):
            for _ in range(limits.FAILURES_PER_MINUTE):
                admission.failed(f'10.{number // 256}.{number % 256}.1', 0.0)
        self.assertLessEqual(len(admission._refused_until), limits.TABLE_LIMIT)
        self.assertFalse(admission.may_accept(f'10.{(limits.TABLE_LIMIT * 3 - 1) // 256}.{(limits.TABLE_LIMIT * 3 - 1) % 256}.1', 1.0))

    def test_l4_the_secret_and_the_session_key_are_not_in_a_repr(self):
        invited = invitation.Invitation('192.168.1.5', 24611, SECRET)
        session = handshake.Session(b'\x77' * 32, 3)
        for text in (repr(invited), f'{invited}', repr(session), f'{session}'):
            self.assertNotIn(SECRET.hex(), text.lower())
            self.assertNotIn(repr(SECRET), text)
            self.assertNotIn('77' * 8, text)
            self.assertNotIn('\\x77', text)
        self.assertIn('192.168.1.5', repr(invited))

    def test_l7_a_version_is_always_three_numbers(self):
        from retrorecomp.netplay.room_cli import version_numbers
        self.assertEqual(version_numbers('1.7.9'), (1, 7, 9))
        self.assertEqual(version_numbers('1.8.0rc1'), (1, 8, 0))
        self.assertEqual(version_numbers('2'), (2, 0, 0))
        self.assertEqual(version_numbers('x.y'), (0, 0, 0))
        self.assertEqual(version_numbers('1.2.3.4'), (1, 2, 3))
        self.assertEqual(version_numbers('1.70000.3'), (1, 3, 0))
        for bad in ((1, 8), (1, 8, 0, 0), (1, 8, 70000), (1, 8, -1), (1, 8, 'x')):
            with self.assertRaises(ValueError):
                lan_transport.RoomGuest(invitation.Invitation('192.168.1.5', 24611, SECRET), 'Nadia', tests=True, version=bad)


if __name__ == '__main__':
    unittest.main()
