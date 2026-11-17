"""The multiplayer lobby through real sockets on 127.0.0.1 and through real worker processes (127.0.0.1 only, a port the system
chooses, never anything else).

Two layers. The first runs a `RoomHost` and three `RoomGuest` in this process, with no game: the roster, the chat (stamped by
the host, limited by the host whatever a guest does), the check (the test plays the converter and answers each pick), the ready
flags, a pick that changes, a launch that takes only the guests who have the game and a match end that brings everybody back, and
a guest that sends what only a host may send. The second starts three worker processes (`RetroRecomp.py _netplay-worker`) with
three fake games in three scratch libraries (`tools/hostkit_session/fake.c` is the only executable, copied once per game: no ROM):
chat, the check, a launch that leaves the player without the game in the lobby (he chats during the match), the match end back to
the lobby, a switch of game that takes another player, a reconverted game that is checked again, and the identical frames of every
match. Nothing is timed (waits are bounds); skipped, with the reason, without a C toolchain or where loopback is refused.
No firewall or system setting is touched; the converter's real library is never read."""
import importlib.util
import json
from pathlib import Path
import shutil
import socket
import tempfile
import threading
import time
import unittest

from retrorecomp.netplay import WorkerProcess, control, invitation, lobby_check, lobby_client
from retrorecomp.netplay.lan_transport import RoomError, RoomGuest, RoomHost
from tests.test_netplay_lobby import ENGINE, Scratch, game, report

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('netplay_lockstep_selftest', ROOT / 'tools' / 'netplay_lockstep_selftest.py')
selftest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selftest)

FRAMES, DELAY = 120, 4


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


OPEN_TRIES, OPEN_PAUSE = 6, 2.0


def bind_refused_now(reason: str) -> bool:
    """Whether a room could not open for the one reason that is the system's and not the room's: the system refusing every
    exclusive bind of a loopback port for a moment (WSAEACCES, which was seen for about ten seconds on a PC where every test
    process in the middle of opening a room failed together, and where a plain bind and a later run were fine)."""
    return 'could not open a port' in reason


def open_room(test: unittest.TestCase, host: RoomHost) -> None:
    """Opens `host`, again a few times when the system refuses the bind (see `bind_refused_now`), and skips, with the reason, if it
    still does: a test of the lobby is not a test of what the system lets a program bind."""
    for attempt in range(OPEN_TRIES):
        try:
            host.open()
            return
        except RoomError as error:
            if not bind_refused_now(error.reason):
                raise
            if attempt + 1 < OPEN_TRIES:
                threading.Event().wait(OPEN_PAUSE)
            else:
                test.skipTest(f'the system refuses to bind a loopback port: {error.reason}')


class Collector:
    """The events of one room end, in order, and a way to sleep until something has happened (no polling)."""

    def __init__(self):
        self.events: list[dict] = []
        self.launches: list = []
        self.cond = threading.Condition()

    def on_event(self, event: dict) -> None:
        with self.cond:
            self.events.append(event)
            self.cond.notify_all()

    def on_launch(self, launch) -> None:
        with self.cond:
            self.launches.append(launch)
            self.cond.notify_all()

    def wait(self, predicate, timeout: float = 20.0) -> bool:
        with self.cond:
            return self.cond.wait_for(lambda: predicate(self), timeout)

    def named(self, name: str) -> list[dict]:
        with self.cond:
            return [event for event in self.events if event['event'] == name]

    def last_roster(self) -> dict | None:
        found = self.named('lobby_roster')
        return found[-1] if found else None


def names_of(roster: dict | None) -> list[str]:
    return [player['name'] for player in roster['players']] if roster else []


class RoomLobbyTests(unittest.TestCase):
    """A host and three guests in this process: the lobby over the real control stream, with no game."""

    def setUp(self):
        reason = loopback_refused()
        if reason:
            self.skipTest(reason)
        self.host_events = Collector()
        self.host = RoomHost('127.0.0.1', 0, capacity=4, name='Arthur', tests=True, on_event=self.host_events.on_event)
        self.addCleanup(self.host.close)
        open_room(self, self.host)
        self.text = self.host.invitation()
        self.guests: dict[str, tuple] = {}

    def join(self, name: str) -> tuple:
        collector = Collector()
        guest = RoomGuest(invitation.parse(self.text, tests=True), name, tests=True, on_event=collector.on_event, on_launch=collector.on_launch)
        guest.connect(timeout=5.0)
        self.addCleanup(guest.close)
        self.guests[name] = (guest, collector)
        return guest, collector

    def everyone_sees(self, names: list[str]) -> None:
        self.assertTrue(self.host_events.wait(lambda c: names_of(c.last_roster()) == names), names_of(self.host_events.last_roster()))
        for name, (_guest, collector) in self.guests.items():
            if name in names:
                self.assertTrue(collector.wait(lambda c: names_of(c.last_roster()) == names), (name, names_of(collector.last_roster())))

    def test_the_lobby_over_the_real_control_stream(self):
        nadia, nadia_events = self.join('Nadia')
        karl, karl_events = self.join('Karl')
        self.everyone_sees(['Arthur', 'Nadia', 'Karl'])
        self.assertEqual(nadia_events.last_roster()['me'], 1)
        self.assertEqual((karl_events.last_roster()['me'], self.host_events.last_roster()['phase']), (2, 'lobby'))

        # chat: cleaned, stamped with the sender's name by the host, delivered to everybody, the sender included
        first_line_at = time.monotonic()
        nadia.lobby_say('  hello ​  all ')
        self.host.lobby_say('Bonjour Hélène')
        for collector in (self.host_events, nadia_events, karl_events):
            self.assertTrue(collector.wait(lambda c: len(c.named('lobby_chat')) == 2), collector.events)
            lines = {event['sender']: event for event in collector.named('lobby_chat')}       # the two lines may arrive in either order
            self.assertEqual((lines[1]['name'], lines[1]['text']), ('Nadia', 'hello all'))
            self.assertEqual((lines[0]['name'], lines[0]['text'], lines[0]['ascii']), ('Arthur', 'Bonjour Hélène', 'Bonjour Helene'))

        # the host's limit holds whatever a guest does: eight lines sent at once past the guest's own rule, and Nadia (who already said
        # one) has five lines in all, however many she sends
        with nadia._lock:
            for number in range(8):
                nadia._stream.send(control.Say(f'spam {number}'))
        self.assertTrue(nadia_events.wait(lambda c: any(event['code'] == 'chat_too_fast' for event in c.named('lobby_notice'))), nadia_events.events)
        # (the host's rule is five lines in any five seconds: Nadia's first line counts unless five seconds went by before the burst, which
        # a loaded PC may take; the burst itself is sent in one go, so it is never more than five either way)
        burst_at = time.monotonic()
        for collector in (self.host_events, karl_events):
            self.assertTrue(collector.wait(lambda c: len([e for e in c.named('lobby_chat') if e['name'] == 'Nadia']) >= 5), collector.events)
            delivered = len([e for e in collector.named('lobby_chat') if e['name'] == 'Nadia'])
            self.assertTrue(delivered == 5 or (delivered == 6 and burst_at - first_line_at > 4.0), (delivered, burst_at - first_line_at))

        # the pick: each guest is asked, the test plays the converter and answers
        first = game(title='Fake One')
        self.assertIsNone(self.host.lobby_select(first))
        for collector in (nadia_events, karl_events):
            self.assertTrue(collector.wait(lambda c: bool(c.named('lobby_check_request'))))
            self.assertEqual(collector.named('lobby_check_request')[-1]['game']['title'], 'Fake One')
        number = nadia_events.named('lobby_check_request')[-1]['selection']
        nadia.lobby_answer(number, control.CHECK_SAME, 0, (1, 7, 9))
        karl.lobby_answer(number, control.CHECK_MISSING)
        self.assertTrue(self.host_events.wait(lambda c: len(c.named('lobby_check')) == 2))
        self.assertEqual([(e['name'], e['status']) for e in self.host_events.named('lobby_check')], [('Nadia', 'same'), ('Karl', 'missing')])
        self.assertIn('not found (needs Fake One', self.host_events.named('lobby_check')[1]['text'])
        self.assertTrue(self.host_events.wait(lambda c: [p['check'] for p in c.last_roster()['players']] == ['same', 'same', 'missing']))

        # an answer to an old pick, and a guest that floods ready flags: ignored, bounded, nobody is cut off
        with karl._lock:
            karl._stream.send(control.Answer(number + 100, control.CHECK_SAME, 0, (1, 7, 9)))
        before = len(karl_events.named('lobby_roster'))
        with nadia._lock:
            for step in range(30):
                nadia._stream.send(control.Ready(step % 2 == 0))
        self.assertTrue(karl_events.wait(lambda c: len(c.named('lobby_roster')) > before))
        self.assertLessEqual(len(karl_events.named('lobby_roster')) - before, 6)
        self.assertEqual(names_of(self.host_events.last_roster()), ['Arthur', 'Nadia', 'Karl'])
        # The first roster may leave the host before it has read the whole flood. Nadia's own answer, sent after it on the same stream,
        # is handled after it: when the host reports it (a third check), every flag change of the flood has been taken or ignored.
        nadia.lobby_answer(number, control.CHECK_SAME, 0, (1, 7, 9))
        self.assertTrue(self.host_events.wait(lambda c: len(c.named('lobby_check')) == 3), self.host_events.events)
        self.assertGreaterEqual(self.host.lobby.ignored, 2)

        # another pick: everyone is asked again and the flags are clear
        second = game(title='Fake Two', machine='md')
        self.assertIsNone(self.host.lobby_select(second))
        self.assertTrue(nadia_events.wait(lambda c: len(c.named('lobby_check_request')) == 2))
        self.assertTrue(karl_events.wait(lambda c: len(c.named('lobby_check_request')) == 2))
        self.assertTrue(self.host_events.wait(lambda c: [p['check'] for p in c.last_roster()['players']] == ['same', 'asking', 'asking']))
        self.assertFalse(any(player['ready'] for player in self.host_events.last_roster()['players'][1:]))
        number = nadia_events.named('lobby_check_request')[-1]['selection']
        self.assertEqual(number, 2)
        nadia.lobby_answer(number, control.CHECK_SAME, 0, (1, 7, 9))
        karl.lobby_answer(number, control.CHECK_OTHER, lobby_check.R_CONVERTER, (1, 7, 3))
        self.assertTrue(self.host_events.wait(lambda c: [p['check'] for p in c.last_roster()['players']] == ['same', 'same', 'other']))
        self.assertTrue(self.host_events.wait(lambda c: c.named('lobby_check')[-1]['text'] == 'same game, other version (reconvert: converter version)'))

        # the launch takes the player who has the game; the other one stays in the lobby, and is told the match is over
        info = self.host.lobby_launch(delay=2)
        self.assertEqual((info.seats, info.names), (2, ('Arthur', 'Nadia')))
        self.assertTrue(nadia_events.wait(lambda c: bool(c.launches)))
        self.assertEqual((nadia_events.launches[0].machine, nadia_events.launches[0].stamp, nadia_events.launches[0].seat),
                         ('md', second.digest(), 1))
        nadia.launched(nadia_events.launches[0].match_id, control.LAUNCHED_READY)
        self.assertTrue(self.host_events.wait(lambda c: bool(c.named('all_launched'))))
        self.assertEqual(karl_events.launches, [])
        self.assertTrue(self.host_events.wait(lambda c: [p['in_match'] for p in c.last_roster()['players']] == [True, True, False]))
        self.assertEqual(self.host_events.last_roster()['phase'], 'playing')
        karl.lobby_say('still here')                                                  # chat goes on during a match, from the lobby
        self.assertTrue(nadia_events.wait(lambda c: any(e['text'] == 'still here' for e in c.named('lobby_chat'))))
        self.assertTrue(karl_events.wait(lambda c: any(e['text'] == 'still here' for e in c.named('lobby_chat'))))
        self.assertEqual(self.host.lobby_launch().reason, 'a match is already starting or running')      # a second launch is refused
        self.host.end_match('desync')
        for collector in (self.host_events, nadia_events, karl_events):
            self.assertTrue(collector.wait(lambda c: bool(c.named('lobby_back'))), collector.events)
            self.assertEqual(collector.named('lobby_back')[0]['reason'], 'desync')
        self.assertTrue(self.host_events.wait(lambda c: c.last_roster()['phase'] == 'lobby' and not any(p['in_match'] for p in c.last_roster()['players'])))

        # a guest that sends what only a host may send is cut off, and the room goes on
        mallory, mallory_events = self.join('Mallory')
        self.everyone_sees(['Arthur', 'Nadia', 'Karl', 'Mallory'])
        with mallory._lock:
            mallory._stream.send(control.Roster(1, 0, 0, 0, (control.Player(0, 'Arthur'),)))
        self.assertTrue(self.host_events.wait(lambda c: any(e['name'] == 'Mallory' for e in c.named('left'))))
        self.everyone_sees(['Arthur', 'Nadia', 'Karl'])

    def test_a_launch_with_nobody_who_has_the_game_is_refused_and_a_full_room_is_a_full_room(self):
        nadia, nadia_events = self.join('Nadia')
        self.everyone_sees(['Arthur', 'Nadia'])
        self.assertEqual(self.host.lobby_launch().reason, 'no game is chosen')
        self.host.lobby_select(game())
        self.assertEqual(self.host.lobby_launch().reason, 'nobody has the game')
        self.assertTrue(nadia_events.wait(lambda c: bool(c.named('lobby_check_request'))))
        nadia.lobby_answer(nadia_events.named('lobby_check_request')[-1]['selection'], control.CHECK_FAILED)
        self.assertTrue(self.host_events.wait(lambda c: bool(c.named('lobby_check'))))
        self.assertEqual(self.host_events.named('lobby_check')[0]['status'], 'failed')
        self.assertEqual(self.host.lobby_launch().reason, 'nobody has the game')
        self.assertEqual(self.host.lobby_move(1, 1), None)
        self.assertEqual(self.host.lobby_move(1, 3).reason, 'a seat the room does not have')
        self.join('Karl')
        self.join('Hélène')
        with self.assertRaises(RoomError) as full:
            RoomGuest(invitation.parse(self.text, tests=True), 'Late', tests=True).connect(timeout=5.0)
        self.assertIn('full', full.exception.reason)

    def test_a_guest_that_was_not_asked_is_refused_a_launch_of_another_game(self):
        """A host that launches a game other than the pick it made gets a refusal from the guest, not a match."""
        nadia, nadia_events = self.join('Nadia')
        self.everyone_sees(['Arthur', 'Nadia'])
        self.host.lobby_select(game(title='Fake One'))
        self.assertTrue(nadia_events.wait(lambda c: bool(c.named('lobby_check_request'))))
        nadia.lobby_answer(1, control.CHECK_SAME, 0, (1, 7, 9))
        self.assertTrue(self.host_events.wait(lambda c: bool(c.named('lobby_check'))))
        info = self.host.launch(machine='nes', stamp=bytes(32), rom_sha=bytes(32), guests=[1])          # not the pick's identity
        self.assertEqual(info.seats, 2)
        self.assertTrue(nadia_events.wait(lambda c: bool(c.named('launch_refused'))))
        self.assertEqual(nadia_events.launches, [])
        self.assertTrue(self.host_events.wait(lambda c: bool(c.named('launch_failed'))))
        self.assertIn('another version', self.host_events.named('launch_failed')[0]['detail'])
        self.assertTrue(nadia_events.wait(lambda c: bool(c.named('lobby_back'))))
        self.assertEqual(nadia_events.named('lobby_back')[0]['reason'], 'launch_failed')


# ---- three worker processes and three fake games ----

IDENT = [('a1' * 32, 'Fake One'), ('b2' * 32, 'Fake Two'), ('c3' * 32, 'Fake Three')]


class FakeLibrary:
    """A scratch library whose executables are copies of the fake game: one per entry, so that each has a place of its own."""

    def __init__(self, test: unittest.TestCase, executable: Path):
        self.scratch = Scratch(test)
        self.executable = executable
        self.entries = {}
        self.envs = {}                  # the entry's executable -> the environment its copy of the fake game is started with

    def add(self, number: int, env: dict | None = None, **changes):
        rom, title = IDENT[number]
        entry = self.scratch.add(report(rom=rom, title=title, **changes), rom=rom, title=title, version=changes.get('version', '1.7.9'))
        shutil.copyfile(self.executable, entry.executable)            # the fake game stands in for every game
        self.entries[number] = entry
        self.envs[str(entry.executable)] = env or {}      # e.g. SESSION_FAKE_NO_SNAPSHOT=1: a machine that keeps no snapshot
        return entry

    def game_for(self, entry) -> dict:
        folder = Path(entry.executable).parent
        return {'exe': entry.executable, 'cwd': str(folder), 'env': dict(selftest.HIDDEN, SESSION_FAKE_HZ='60', **self.envs.get(str(entry.executable), {})),
                'stdout': str(folder / 'stdout.txt'), 'stderr': str(folder / 'stderr.txt')}


class Player:
    """One worker process with its controller and its library: what the Multiplayer window will be made of."""

    def __init__(self, name: str, library: FakeLibrary, config: dict, out: Path, test: unittest.TestCase, frames: dict,
                 guest_test: dict | None = None):
        self.name, self.library, self.cond, self.stopped = name, library, threading.Condition(), False
        self.controller = lobby_client.LobbyController(library.scratch.library(), game_for=library.game_for)
        self.frames = frames

        def resolve(event):
            reply = self.controller.resolve(event)
            if reply['call'] == 'launch':
                reply['test_settings'] = {'local_source': selftest.script(event['seat']), 'keep_history': True,
                                          'last_frame': self.frames['last'], **(guest_test or {})}
            return reply

        def on_event(event):
            self.controller.on_event(event)
            with self.cond:
                self.cond.notify_all()
        self.worker = WorkerProcess(config, log=out / f'{name}-worker.txt', resolve=resolve, on_event=on_event)
        self.controller.attach(self.worker)
        self.worker.start()
        test.addCleanup(self.stop)

    def until(self, predicate, timeout: float = 60.0) -> bool:
        with self.cond:
            return self.cond.wait_for(lambda: predicate(self.controller.model), timeout)

    def stop(self) -> None:
        if not self.stopped:
            self.stopped = True
            self.worker.call('close_room')
            self.worker.join(30)
            self.worker.cleanup()


class LobbyMatchTests(unittest.TestCase):
    def test_chat_check_launch_end_and_switch_with_three_players_and_three_fake_games(self):
        reason = selftest.fake.ready() or loopback_refused()
        if reason:
            self.skipTest(reason)
        executable = selftest.fake.build(ROOT / '.build/hostkit-session-selftest')
        out = Path(tempfile.mkdtemp(prefix='lobby-', dir=ROOT / '.build'))
        secret = invitation.new_secret()
        frames = {'last': FRAMES}

        host_library, nadia_library, karl_library = (FakeLibrary(self, executable) for _ in range(3))
        for number in range(3):
            host_library.add(number)
        nadia_library.add(0, sources='99' * 32)                  # the same NES game with other learned paths: the same game
        nadia_old = nadia_library.add(1, version='1.7.8')         # another version of the second game
        karl_library.add(1)

        host = Player('host', host_library, {'room': {'role': 'host', 'address': '127.0.0.1', 'port': 0, 'secret': secret.hex(), 'capacity': 3,
                                                       'name': 'Arthur', 'log': str(out / 'room.log')}, 'tests': True}, out, self, frames)
        opened = host.worker.wait_event('room_open', 30)
        if opened is None and any(bind_refused_now(event.get('detail', '')) for event in host.worker.events):
            self.skipTest('the system refuses to bind a loopback port right now')
        self.assertIsNotNone(opened, host.worker.events)
        text = invitation.format_invitation('127.0.0.1', opened['port'], secret, tests=True)
        nadia = Player('nadia', nadia_library, {'room': {'role': 'guest', 'invitation': text, 'name': 'Nadia'}, 'tests': True}, out, self, frames)
        # Seats follow the order of arrival, and two worker processes started together arrive in whatever order their start-up takes
        # (under load Karl was first, twice in twelve runs): Karl is started once the host has seated Nadia, so the order is the test's.
        self.assertTrue(host.until(lambda m: [p['name'] for p in m.players] == ['Arthur', 'Nadia']), host.controller.model.players)
        karl = Player('karl', karl_library, {'room': {'role': 'guest', 'invitation': text, 'name': 'Karl'}, 'tests': True}, out, self, frames)
        everyone = (host, nadia, karl)
        for player in everyone:
            self.assertTrue(player.until(lambda m: [p['name'] for p in m.players] == ['Arthur', 'Nadia', 'Karl']), player.controller.model.players)

        # chat, as the host stamps it
        nadia.controller.say('salut  à tous')
        karl.controller.say('hi')
        for player in everyone:
            self.assertTrue(player.until(lambda m: len(m.chat) == 2), player.name)
        self.assertEqual(sorted((line['name'], line['text'], line['ascii']) for line in karl.controller.model.chat),
                         [('Karl', 'hi', 'hi'), ('Nadia', 'salut à tous', 'salut a tous')])

        # the host picks a game nobody has: each says so, and the launch is refused
        self.assertEqual(host.controller.pick(host_library.entries[2], 'speed=1'), '')
        self.assertTrue(host.until(lambda m: [p['check'] for p in m.players] == ['same', 'missing', 'missing']), host.controller.model.players)
        self.assertEqual(nadia.controller.answers[-1]['text'], f'not found (needs Fake Three, SHA-256 {IDENT[2][0]})')
        mark = host.worker.event_count
        self.assertEqual(host.controller.launch({'delay': DELAY}), '')
        self.assertIsNotNone(host.worker.wait_event('launch_error', 30, after=mark))
        self.assertTrue(host.until(lambda m: any(error['detail'] == 'nobody has the game' for error in m.errors)))

        # the first match: Nadia has the game (other learned paths, same game), Karl does not and stays in the lobby with the chat
        self.assertEqual(host.controller.pick(host_library.entries[0]), '')
        self.assertTrue(host.until(lambda m: [p['check'] for p in m.players] == ['same', 'same', 'missing']), host.controller.model.players)
        self.assertEqual(nadia.controller.answers[-1]['text'], 'same game')
        settings = {'delay': DELAY, 'digest_every': 50, 'redundancy': 3, 'local_source': selftest.script(0), 'keep_history': True,
                    'last_frame': FRAMES}
        self.assertEqual(host.controller.launch(settings), '')
        self.assertTrue(host.until(lambda m: m.last_launch is not None and m.last_launch['match_id'] == 1))
        self.assertEqual(host.controller.model.last_launch['names'], ['Arthur', 'Nadia'])
        self.assertEqual(host.controller.model.last_launch['left_out'], [{'guest': 2, 'name': 'Karl', 'reason': 'missing'}])
        self.assertTrue(host.until(lambda m: m.phase == 'playing' and [p['in_match'] for p in m.players] == [True, True, False]))
        self.assertTrue(karl.until(lambda m: m.phase == 'playing'))
        self.assertEqual([e for e in karl.worker.events if e['event'] == 'launch_request'], [])          # nothing was asked of Karl
        karl.controller.say('watching')                                                     # from the lobby, during the match
        for player in (host, nadia):
            self.assertTrue(player.until(lambda m: any(line['text'] == 'watching' for line in m.chat)), player.name)
        for player in everyone:                                                               # the match ends: everybody is in the lobby
            self.assertTrue(player.until(lambda m: m.last_back is not None and m.last_back['match_id'] == 1), player.name)
            self.assertEqual(player.controller.model.last_back['reason'], 'ended')
        self.assertTrue(host.until(lambda m: m.phase == 'lobby' and not any(p['in_match'] for p in m.players)))
        self.assertTrue(nadia.worker.wait_for(lambda w: len(w.results) == 1, 60), nadia.worker.summary())
        self.assertTrue(host.worker.wait_for(lambda w: len(w.results) == 1, 60), host.worker.summary())
        wanted = selftest.expected(2, DELAY, FRAMES)
        for worker in (host.worker, nadia.worker):
            self.assertEqual((worker.results[0]['outcome'], worker.results[0]['history']), ('ended', [tuple(words) for words in wanted]), worker.summary())
        self.assertEqual(host.worker.results[0]['digests'], nadia.worker.results[0]['digests'])
        self.assertEqual(karl.worker.results, [])

        # the switch: the second game is another version for Nadia and the same for Karl: Karl plays, Nadia stays in the lobby
        self.assertEqual(host.controller.pick(host_library.entries[1]), '')
        self.assertTrue(host.until(lambda m: [p['check'] for p in m.players] == ['same', 'other', 'same']), host.controller.model.players)
        self.assertEqual(host.controller.model.checks[1]['text'], 'same game, other version (reconvert: converter version)')
        self.assertEqual(host.controller.model.checks[1]['version'], [1, 7, 8])
        self.assertEqual(nadia.controller.resolve({'machine': 'nes', 'rom': IDENT[1][0], 'stamp': '00' * 32, 'match_id': 2})['call'], 'launch_refused')
        self.assertEqual(host.controller.launch(settings), '')
        self.assertTrue(host.until(lambda m: m.last_launch['match_id'] == 2))
        self.assertEqual((host.controller.model.last_launch['names'], host.controller.model.last_launch['left_out']),
                         (['Arthur', 'Karl'], [{'guest': 1, 'name': 'Nadia', 'reason': 'other'}]))
        for player in everyone:
            self.assertTrue(player.until(lambda m: m.last_back['match_id'] == 2), player.name)
        self.assertTrue(karl.worker.wait_for(lambda w: len(w.results) == 1, 60), karl.worker.summary())
        self.assertTrue(host.worker.wait_for(lambda w: len(w.results) == 2, 60), host.worker.summary())
        self.assertEqual((karl.worker.results[0]['outcome'], karl.worker.results[0]['history']), ('ended', [tuple(words) for words in wanted]))
        self.assertEqual(host.worker.results[1]['digests'], karl.worker.results[0]['digests'])

        # Nadia reconverts the second game (here: adds an export of the right version) and checks again: she is the same now, in seat 1
        nadia_library.add(1)
        nadia.controller.recheck()
        self.assertTrue(host.until(lambda m: [p['check'] for p in m.players] == ['same', 'same', 'same']), host.controller.model.players)
        self.assertEqual(host.controller.launch(settings), '')
        self.assertTrue(host.until(lambda m: m.last_launch['match_id'] == 3))
        self.assertEqual(host.controller.model.last_launch['names'], ['Arthur', 'Nadia'])           # the first guest in the host's order takes the seat
        self.assertEqual(host.controller.model.last_launch['left_out'], [{'guest': 2, 'name': 'Karl', 'reason': 'not seated'}])
        for player in everyone:
            self.assertTrue(player.until(lambda m: m.last_back['match_id'] == 3), player.name)
        self.assertTrue(nadia.worker.wait_for(lambda w: len(w.results) == 2, 60), nadia.worker.summary())
        self.assertEqual(nadia.worker.results[1]['history'], [tuple(words) for words in wanted])
        ran = [(Path(entry.executable).parent / 'stdout.txt').exists() for entry in (nadia_old, nadia_library.entries[1])]
        self.assertEqual(ran, [False, True])                                                         # the new export is the one that ran

        self.assertEqual([len(player.controller.model.errors) > 0 for player in everyone], [True, False, False])    # the host's refused launch
        everything = json.dumps([player.worker.events for player in everyone], default=str)
        self.assertNotIn(secret.hex(), everything)
        self.assertNotIn(invitation.encode_secret(secret), everything.upper())
        for player in everyone:
            player.stop()
            self.assertEqual(player.worker.exit_code_of_process, 0, player.worker.summary())
        shutil.rmtree(out, ignore_errors=True)         # kept only when something above failed


class LobbyTierTests(unittest.TestCase):
    """The tier of a LAN match (127.0.0.1 only, two real worker processes, fake games, no ROM): the host decides it from its own
    game's HELLO and the LAUNCH carries it; each launch decides again, so a switch of game does too."""

    def test_the_host_chooses_the_tier_for_each_game_and_the_guest_applies_it_or_refuses(self):
        reason = selftest.fake.ready() or loopback_refused()
        if reason:
            self.skipTest(reason)
        executable = selftest.fake.build(ROOT / '.build/hostkit-session-selftest')
        out = Path(tempfile.mkdtemp(prefix='tier-', dir=ROOT / '.build'))
        secret = invitation.new_secret()
        frames = {'last': FRAMES}
        no_snapshot = {'SESSION_FAKE_NO_SNAPSHOT': '1'}
        host_library, nadia_library = FakeLibrary(self, executable), FakeLibrary(self, executable)
        for number in range(3):                       # game 0: snapshots on both; game 1: none on the host's; game 2: none on Nadia's
            host_library.add(number, env=no_snapshot if number == 1 else None)
            nadia_library.add(number, env=no_snapshot if number == 2 else None)

        host = Player('host', host_library, {'room': {'role': 'host', 'address': '127.0.0.1', 'port': 0, 'secret': secret.hex(), 'capacity': 2,
                                                       'name': 'Arthur', 'log': str(out / 'room.log')}, 'tests': True}, out, self, frames)
        opened = host.worker.wait_event('room_open', 30)
        if opened is None and any(bind_refused_now(event.get('detail', '')) for event in host.worker.events):
            self.skipTest('the system refuses to bind a loopback port right now')
        self.assertIsNotNone(opened, host.worker.events)
        text = invitation.format_invitation('127.0.0.1', opened['port'], secret, tests=True)
        # Nadia's game runs 10 % fast with no time sync, so she gets ahead of the host's records and guesses (rollbacks are then certain)
        nadia = Player('nadia', nadia_library, {'room': {'role': 'guest', 'invitation': text, 'name': 'Nadia'}, 'tests': True}, out, self, frames,
                       guest_test={'clock_ppm': -100000, 'pace': False})
        self.assertTrue(host.until(lambda m: [p['name'] for p in m.players] == ['Arthur', 'Nadia']), host.controller.model.players)
        settings = {'delay': 1, 'digest_every': 50, 'redundancy': 3, 'local_source': selftest.script(0), 'keep_history': True,
                    'last_frame': FRAMES}

        def pick(number: int) -> None:
            before = host.controller.model.selection
            self.assertEqual(host.controller.pick(host_library.entries[number]), '')
            self.assertTrue(host.until(lambda m: m.selection > before and m.checks.get(1, {}).get('status') == 'same'),
                            (host.controller.model.selection, host.controller.model.checks))

        def tiers(worker, name: str, match_id: int) -> list:
            return [(event['tier'], event['prediction']) for event in worker.events if event['event'] == name and event['match_id'] == match_id]

        # 1. both games keep snapshots: the host chooses the rollback tier (the cap of 8 by default), the guest applies it
        pick(0)
        self.assertEqual(host.controller.launch(settings), '')
        for player in (host, nadia):
            self.assertTrue(player.until(lambda m: m.last_back is not None and m.last_back['match_id'] == 1), player.name)
        for worker in (host.worker, nadia.worker):
            self.assertTrue(worker.wait_for(lambda w: len(w.results) == 1, 60), worker.summary())
        self.assertEqual(tiers(host.worker, 'launching', 1), [('rollback', 8)])
        self.assertEqual(tiers(nadia.worker, 'launch_request', 1), [('rollback', 8)])
        wanted = [tuple(words) for words in selftest.expected(2, 1, FRAMES)]
        results = [host.worker.results[0], nadia.worker.results[0]]
        for result in results:
            self.assertEqual((result['outcome'], result['tier'], result['prediction_cap'], result['delay']), ('ended', 'rollback', 8, 1),
                             result['detail'])
            self.assertEqual(result['history'], wanted)                       # the confirmed history is the scripts shifted by the delay
            stats = result['stats']
            self.assertGreaterEqual(stats['rollback_frames'], stats['rollbacks'])
            self.assertLessEqual(stats['rollback_depth_max'], 8)
            self.assertEqual(stats['digests_skipped'], 0)
            self.assertTrue(result['digests'])
        self.assertEqual(results[0]['digests'], results[1]['digests'])        # equal across the two seats
        rollbacks = [result['stats']['rollbacks'] for result in results]
        self.assertGreater(sum(rollbacks), 0, results[1]['stats'])            # the fast guest guessed, was corrected, and ended in step
        counts = {name: [result['stats'][name] for result in results] for name in ('rollbacks', 'rollback_frames', 'predicted_frames')}

        # 2. the switch: the host's second game keeps no snapshot: the host chooses the delay tier again, for both
        pick(1)
        self.assertEqual(host.controller.launch({**settings, 'delay': DELAY}), '')
        for player in (host, nadia):
            self.assertTrue(player.until(lambda m: m.last_back['match_id'] == 2), player.name)
        for worker in (host.worker, nadia.worker):
            self.assertTrue(worker.wait_for(lambda w: len(w.results) == 2, 60), worker.summary())
        self.assertEqual(tiers(host.worker, 'launching', 2), [('delay', 0)])
        self.assertEqual(tiers(nadia.worker, 'launch_request', 2), [('delay', 0)])
        wanted = [tuple(words) for words in selftest.expected(2, DELAY, FRAMES)]
        for worker in (host.worker, nadia.worker):
            result = worker.results[1]
            self.assertEqual((result['outcome'], result['tier'], result['history']), ('ended', 'delay', wanted), result['detail'])
            self.assertNotIn('rollbacks', result['stats'])
        self.assertEqual(host.worker.results[1]['digests'], nadia.worker.results[1]['digests'])

        # 3. the host forces the rollback tier on a game that keeps no snapshot, then a cap out of bounds: refused with the reason
        mark = host.worker.event_count
        self.assertEqual(host.controller.launch({**settings, 'tier': 'rollback'}), '')
        error = host.worker.wait_event('launch_error', 60, after=mark)
        self.assertIsNotNone(error, host.worker.events)
        self.assertIn('snapshots', error['detail'])
        mark = host.worker.event_count
        self.assertEqual(host.controller.launch({**settings, 'tier': 'auto', 'rollback': 9}), '')
        error = host.worker.wait_event('launch_error', 60, after=mark)
        self.assertIsNotNone(error, host.worker.events)
        self.assertIn('prediction cap', error['detail'])

        # 4. the host's game keeps snapshots and Nadia's does not (it should not happen: the host decided from its own HELLO): she
        # refuses the rollback launch with the reason, and the match ends for both
        pick(2)
        self.assertEqual(host.controller.launch(settings), '')
        for player in (host, nadia):
            self.assertTrue(player.until(lambda m: m.last_back['match_id'] == 3), player.name)
        for worker in (host.worker, nadia.worker):
            self.assertTrue(worker.wait_for(lambda w: len(w.results) == 3, 60), worker.summary())
        refused = nadia.worker.results[2]
        self.assertEqual(refused['outcome'], 'refused')
        self.assertIn('keeps no snapshot', refused['detail'])
        self.assertNotEqual(host.worker.results[2]['outcome'], 'ended')

        for player in (host, nadia):
            player.stop()
            self.assertEqual(player.worker.exit_code_of_process, 0, player.worker.summary())
        print('tier loopback counts per seat (rollbacks, frames run again, frames on a guess):', counts)
        shutil.rmtree(out, ignore_errors=True)         # kept only when something above failed


if __name__ == '__main__':
    unittest.main()
