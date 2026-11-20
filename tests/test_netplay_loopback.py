"""The one test of multiplayer stage 2 that opens sockets: 127.0.0.1 only, a port the system chooses.

Two worker processes (`RetroRecomp.py _netplay-worker`), each driving a fake game (tools/hostkit_session/fake.c, built as
tools/netplay_lockstep_selftest.py builds it) through the real transport (`lan_transport`): the host's worker opens the
room, the guest's worker joins it with the invitation, the host launches, the guest's converter side is asked which game
that is and answers, and a few hundred frames run with the digests equal. Around it, a stranger: a TCP connection of
garbage and one with the wrong secret get no byte back; garbage datagrams, from the one address the room knows, are dropped
and counted and get no byte back; after three failed handshakes the address is refused, even with the right secret.

127.0.0.1 is accepted because the workers are told `"tests": true`; the product never is. Nothing outside loopback is
opened, no firewall or system setting is touched, nothing is timed (waits are bounds). Skipped, with its reason, where
there is no C toolchain or where loopback sockets are refused (a firewall that blocks new executables).
"""
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest

from retrorecomp.netplay import WorkerProcess, handshake, invitation
from retrorecomp.netplay.lan_transport import RoomError, RoomGuest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('netplay_lockstep_selftest', ROOT / 'tools' / 'netplay_lockstep_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)

FRAMES = 360
SECOND = 150
DELAY = 4
IDENTITY = {'machine': 'fake', 'stamp': '11' * 32, 'rom': '22' * 32}


def loopback_refused() -> str | None:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            probe.bind(('127.0.0.1', 0))
            probe.listen(1)
        finally:
            probe.close()
    except OSError as error:
        return f'loopback sockets are refused here ({error})'
    return None


def silent(sock: socket.socket, wait: float = 1.0) -> bool:
    """True when nothing comes back (an orderly close is no byte)."""
    sock.settimeout(wait)
    try:
        return sock.recv(100) == b''
    except socket.timeout:
        return True
    except ConnectionError:
        return True


class LoopbackTests(unittest.TestCase):
    def test_two_workers_play_through_the_real_transport_and_a_stranger_gets_nothing(self):
        reason = selftest.fake.ready() or loopback_refused()
        if reason:
            self.skipTest(reason)
        executable = selftest.fake.build(ROOT / '.build/hostkit-session-selftest')
        out = Path(tempfile.mkdtemp(prefix='room-', dir=ROOT / '.build'))
        secret = invitation.new_secret()
        game_env = dict(selftest.HIDDEN, SESSION_FAKE_HZ='60')

        def game(folder: Path, name: str) -> dict:
            folder.mkdir(parents=True, exist_ok=True)
            return dict(exe=str(executable), cwd=str(folder), env=game_env, stdout=str(folder / f'{name}-stdout.txt'),
                        stderr=str(folder / f'{name}-stderr.txt'))

        host_config = {'room': {'role': 'host', 'address': '127.0.0.1', 'port': 0, 'secret': secret.hex(), 'capacity': 2,
                                'name': 'Arthur', 'log': str(out / 'room.log')}, 'tests': True}
        host = WorkerProcess(host_config, log=out / 'host-worker.txt').start()
        guest = None
        try:
            opened = host.wait_event('room_open', 30)
            self.assertIsNotNone(opened, host.events)
            port = opened['port']
            self.assertEqual(opened['address'], '127.0.0.1')
            self.assertNotEqual(port, 0)
            text = invitation.format_invitation('127.0.0.1', port, secret, tests=True)

            # a stranger's TCP connection, garbage then the right shape with the wrong secret: no byte back, two failures
            with socket.create_connection(('127.0.0.1', port), timeout=5) as stranger:
                stranger.sendall(b'GET / HTTP/1.0\r\n\r\n')
                self.assertTrue(silent(stranger))
            with socket.create_connection(('127.0.0.1', port), timeout=5) as stranger:
                stranger.sendall(handshake.GuestHandshake(bytes(16), 0.0).first())
                self.assertTrue(silent(stranger))

            # the guest's worker: its converter side answers which game that is on this PC
            lengths = {1: FRAMES, 2: SECOND, 3: 100000}

            def resolve(event):
                self.assertEqual((event['machine'], event['stamp'], event['rom']), tuple(IDENTITY.values()))
                self.assertEqual(event['names'], ['Arthur', 'Nadia'])
                return {'call': 'launch', 'match_id': event['match_id'], 'game': game(out / 'seat2', f'guest{event["match_id"]}'),
                        'test_settings': {'local_source': selftest.script(1), 'keep_history': True,
                                          'last_frame': lengths[event['match_id']]}}
            guest_config = {'room': {'role': 'guest', 'invitation': text, 'name': 'Nadia'}, 'tests': True}
            guest = WorkerProcess(guest_config, log=out / 'guest-worker.txt', resolve=resolve).start()
            self.assertIsNotNone(guest.wait_event('joined_room', 30), guest.events)
            joined = host.wait_event('joined', 30)
            self.assertEqual((joined['name'], joined['address']), ('Nadia', '127.0.0.1'))

            def launch(match_id, frames, **more):
                mark = len(host.events)
                host.call('launch', game=game(out / 'seat1', f'host{match_id}'), identity=IDENTITY,
                          settings={'delay': DELAY, 'digest_every': 50, 'redundancy': 3, 'options': 'speed=1',
                                    'local_source': selftest.script(0), 'keep_history': True, 'last_frame': frames, **more})
                return host.wait_event('launching', 30, after=mark)
            self.assertIsNotNone(launch(1, FRAMES), host.events)
            self.assertTrue(host.reached(60, 60), host.summary())

            # a second guest, with the right secret, while a match runs: the handshake succeeds and the room says why not
            with self.assertRaises(RoomError) as busy:
                RoomGuest(invitation.parse(text, tests=True), 'Late', tests=True).connect(timeout=5.0)
            self.assertIn('match is running', busy.exception.reason)

            # a stranger's datagrams while the match runs: from the one address the room knows, so they pass the first
            # step and die at the head or the tag. Nothing comes back, and the match goes on.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.bind(('127.0.0.1', 0))          # explicit: never a wildcard port, even for the stranger
                udp.settimeout(0.3)
                packets = [b'x' * 10, bytes(40), bytes(600), b'RRNG\x03\x02\x01\x00' + bytes(40),
                           b'RRNG\x03\x02\x01\x00\x01\x00\x00\x00' + bytes(8) + bytes(4) + bytes(16)]
                for packet in packets * 6:
                    udp.sendto(packet, ('127.0.0.1', port))
                with self.assertRaises(socket.timeout):
                    udp.recvfrom(100)

            self.assertIsNotNone(host.wait_event('match_over', 120), host.summary())
            self.assertIsNotNone(guest.wait_event('match_over', 60), guest.summary())
            for worker in (host, guest):
                self.assertTrue(worker.wait_for(lambda w: w.result is not None, 30), worker.summary())

            # both seats ran the same frames on the same words, and the games agree with the drivers
            wanted = selftest.expected(2, DELAY, FRAMES)
            for seat, worker in enumerate((host, guest)):
                result = worker.result
                self.assertEqual(result['outcome'], 'ended', (seat, result['outcome'], result['detail']))
                self.assertEqual(result['history'], [tuple(words) for words in wanted], seat)
                self.assertEqual(result['delay'], DELAY)
                self.assertTrue(result['stats']['final_compared'], result['stats'])
                self.assertEqual(result['exit_code'], 0)
            self.assertEqual(host.result['digests'], guest.result['digests'])
            self.assertEqual(host.result['digests'][FRAMES - 1], selftest.fold(wanted))
            self.assertEqual(host.result['boot_digest'], guest.result['boot_digest'])
            self.assertEqual(len(host.result['digests']), -(-FRAMES // 50))
            over = [event for event in host.events if event['event'] == 'match_over'][0]
            counters = over['counters']
            self.assertGreater(counters.get('format', 0) + counters.get('tag', 0), 0, counters)        # the stranger's datagrams
            self.assertEqual(counters.get('handshake_magic', 0) + counters.get('handshake_tag', 0), 2)

            # the match is over and the room is still there with its one guest: a second guest finds it full
            with self.assertRaises(RoomError) as full:
                RoomGuest(invitation.parse(text, tests=True), 'Late', tests=True).connect(timeout=5.0)
            self.assertIn('full', full.exception.reason)

            # the worker lives as long as the room: a second match in it, with new keys, and the same checks
            self.assertEqual(len(host.results), 1)
            self.assertIsNotNone(launch(2, SECOND), host.events)
            self.assertIsNotNone(host.wait_event('match_over', 120, after=host.events.index(over) + 1), host.summary())
            self.assertTrue(host.wait_for(lambda w: len(w.results) == 2, 30), host.summary())
            self.assertTrue(guest.wait_for(lambda w: len(w.results) == 2, 60), guest.summary())
            wanted = selftest.expected(2, DELAY, SECOND)
            for worker in (host, guest):
                result = worker.results[1]
                self.assertEqual((result['match_id'], result['outcome']), (2, 'ended'), result['detail'])
                self.assertEqual(result['history'], [tuple(words) for words in wanted])
            self.assertEqual(host.results[1]['digests'], guest.results[1]['digests'])
            self.assertEqual(host.results[1]['digests'][SECOND - 1], selftest.fold(wanted))

            # a guest that is killed mid-match (no BYE, no ten seconds of silence): the closed connection is the host's word
            # that the seat is gone, at once (the host's silence limit is set far above what this waits)
            self.assertIsNotNone(launch(3, 100000, drop_after=60.0), host.events)
            self.assertTrue(host.wait_for(lambda w: w.status.get('match_id') == 3 and w.next_run >= 40, 60), host.summary())
            killed = len(host.events)
            guest.kill()
            gone = host.wait_event('match_over', 20, after=killed)
            self.assertIsNotNone(gone, host.summary())
            self.assertEqual(gone['outcome'], 'seat_left', gone)
            left = [event for event in host.events[killed:] if event['event'] == 'left']
            self.assertEqual([event['name'] for event in left], ['Nadia'])
            # A killed process: Windows resets its connection, Linux closes it; either is the guest gone.
            self.assertIn(left[0]['detail'], ('the connection broke', 'the connection closed'))

            # three failed handshakes from one address: it is refused, even with the right secret
            with socket.create_connection(('127.0.0.1', port), timeout=5) as stranger:
                stranger.sendall(b'RRNP' + bytes(34))
                self.assertTrue(silent(stranger))
            late = RoomGuest(invitation.parse(text, tests=True), 'Late', tests=True)
            with self.assertRaises(RoomError) as refused:
                late.connect(timeout=2.0)
            self.assertIn('no answer', refused.exception.reason)
        finally:
            for worker in (guest, host):
                if worker is not None:
                    worker.call('close_room')
            for worker in (guest, host):
                if worker is not None:
                    self.assertTrue(worker.join(30), worker.summary())
                    worker.cleanup()
        self.assertEqual(host.exit_code_of_process, 0, host.summary())

        # nothing secret was ever said: not in an event, a status, a result, a log or the workers' text
        base32 = invitation.encode_secret(secret)
        everything = json.dumps([worker.events for worker in (host, guest)] + [worker.status for worker in (host, guest)],
                                default=str)
        everything += (out / 'room.log').read_text(encoding='utf-8')
        for name in ('host-worker.txt', 'guest-worker.txt'):
            everything += (out / name).read_text(encoding='utf-8', errors='replace')
        self.assertNotIn(secret.hex(), everything)
        self.assertNotIn(base32, everything.upper())
        log = (out / 'room.log').read_text(encoding='utf-8')
        for wanted_line in ('room opened on 127.0.0.1:', 'join Nadia from 127.0.0.1', 'launch match 1: fake stamp 11111111, 2 seats',
                            'refused handshake_', 'refused format', 'room closed'):
            self.assertIn(wanted_line, log)
        shutil.rmtree(out, ignore_errors=True)         # kept only when something above failed


if __name__ == '__main__':
    unittest.main()
