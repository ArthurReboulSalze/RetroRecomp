"""The multiplayer lobby, pure: its messages, its rules, its game check against scratch libraries, the window's model.

No socket, no process, no ROM, no window and no clock: every rule runs on made-up time, every library is a scratch folder
under the temporary directory with an inventory file of its own and fake conversion reports (never the converter's real
library: `compiled_games.Inventory(path)` reads only the path it is given). The same rules through real sockets on
127.0.0.1 and through worker processes are in tests/test_netplay_lobby_loopback.py."""
import importlib.util
import json
from pathlib import Path
import random
import shutil
import struct
import tempfile
import unicodedata
import unittest

from retrorecomp import compiled_games, simulation_identity
from retrorecomp.netplay import control, handshake, lobby, lobby_check, lobby_client
from retrorecomp.netplay.lobby import Event, GuestLobby, HostLobby, Send
from retrorecomp.systems import ALL_PROFILES

ROOT = Path(__file__).resolve().parents[1]
SECRET = bytes(range(16))
SHA = 'ab' * 32
ENGINE = 'cd' * 32


def game(**changes) -> control.Game:
    fields = dict(mode=control.MODE_PORTABLE, schema=simulation_identity.SCHEMA, seats_max=2, machine='nes', converter=(1, 7, 9),
                  rom=bytes.fromhex(SHA), engine=bytes.fromhex(ENGINE), options=bytes(range(32)), sources=bytes([7]) * 32,
                  firmware=bytes(32), title='Battletoads', game_options='speed=1')
    fields.update(changes)
    return control.Game(**fields)


def keys():
    return handshake.tcp_keys(handshake.session_key(SECRET, 3, bytes(16), bytes(range(16, 32))))


MESSAGES = (control.Roster(65535, control.PHASE_PLAYING, 4, 9, (control.Player(0, 'Arthur', True, True, control.CHECK_SAME),
                                                                control.Player(1, 'Hélène', False, True, control.CHECK_OTHER),
                                                                control.Player(2, 'Karl', True, False, control.CHECK_MISSING),
                                                                control.Player(3, 'N' * 48, False, False, control.CHECK_FAILED)),
                           2),
            control.Roster(0, control.PHASE_LOBBY, 0, 0, (control.Player(0, 'a'),)),
            control.Roster(3, control.PHASE_LOBBY, 4, 2, (control.Player(0, 'a'), control.Player(1, 'b')), 1),
            control.Chat(2, 'Hélène', 'Salut à tous ' + chr(0x1f600)), control.Chat(0, 'a', 'x'),
            control.Select(9, game()), control.Select(65535, game(mode=control.MODE_FULL, title='T' * 96, game_options='')),
            control.Select(1, None), control.Notice(control.NOTICE_CHAT_FAST), control.Back(77, 8),
            control.Say('ça va ?'), control.Ready(True), control.Ready(False), control.Answer(9, control.CHECK_OTHER, 0x7f, (1, 7, 3)))
FROM_GUEST = (control.Say, control.Ready, control.Answer)


class WireTests(unittest.TestCase):
    def test_every_lobby_message_round_trips_and_is_canonical(self):
        for message in MESSAGES:
            kind, payload = control.encode(message)
            self.assertLessEqual(len(payload), control.MAX_PAYLOAD)
            self.assertEqual(control.decode(kind, payload), message)
            self.assertEqual(control.encode(control.decode(kind, payload)), (kind, payload))

    def test_through_sealed_frames_one_byte_at_a_time_and_only_in_the_right_direction(self):
        to_host, to_guest = keys()
        for message in MESSAGES:
            from_guest = isinstance(message, FROM_GUEST)
            writer, reader = control.FrameWriter(to_host if from_guest else to_guest), control.FrameReader(
                to_host if from_guest else to_guest, control.FROM_GUEST if from_guest else control.FROM_HOST)
            data, got = writer.seal(message), []
            for index in range(len(data)):
                got += reader.feed(data[index:index + 1])
            self.assertEqual(got, [message])
            wrong = control.FrameReader(to_host if from_guest else to_guest, control.FROM_HOST if from_guest else control.FROM_GUEST)
            with self.assertRaises(control.FrameError, msg=message):
                wrong.feed(data)

    def test_the_biggest_messages_fit_the_frame_and_the_reader_buffer(self):
        biggest = [control.encode(message)[1] for message in (MESSAGES[0], MESSAGES[5])]
        chat = control.encode(control.Chat(3, 'N' * 48, '\U0001f600' * 80))[1]
        self.assertTrue(all(len(payload) + 3 + 16 < control.READ_BUFFER for payload in biggest + [chat]))
        with self.assertRaises(ValueError):
            control.encode(control.Say('x' * 321))
        with self.assertRaises(ValueError):
            control.encode(control.Say(''))
        control.encode(control.Say('\U0001f600' * 80))

    def test_a_message_out_of_the_rules_is_refused_by_the_decoder(self):
        good = {kind: control.encode(message)[1] for message in MESSAGES for kind in (control.encode(message)[0],)}
        roster = bytearray(control.encode(MESSAGES[0])[1])
        for index, value in ((0, control.LOBBY_VERSION + 1), (3, 3), (4, 5), (5, 4), (8, 0), (8, 5)):  # another lobby version, a phase, seats, a mode, a count
            damaged = bytearray(roster)
            damaged[index] = value
            with self.assertRaises(control.FrameError, msg=(index, value)):
                control.decode(control.ROSTER, bytes(damaged))
        select = control.encode(MESSAGES[4])[1]
        for kind, payload in [(control.ROSTER, b''), (control.ROSTER, roster[:-1] + b''), (control.ROSTER, bytes(roster) + b'x'),
                              (control.CHAT, b'\x04\x01a\x01\x00x'), (control.CHAT, struct.pack('<BB', 0, 1) + b'a' + struct.pack('<H', 0)),
                              (control.CHAT, struct.pack('<BB', 0, 1) + b'a' + struct.pack('<H', 1) + b'\xff'),
                              (control.CHAT, struct.pack('<BB', 0, 1) + b'a' + struct.pack('<H', 321) + b'a' * 321),
                              (control.SELECT, struct.pack('<HB', 0, 0)), (control.SELECT, struct.pack('<HB', 1, 2)),
                              (control.SELECT, struct.pack('<HB', 1, 0) + b'x'), (control.SELECT, select[:-1]), (control.SELECT, select + b'x'),
                              (control.SELECT, select[:2] + b'\x02' + select[3:]),                          # a mode that is not one
                              (control.NOTICE, b'\x00'), (control.NOTICE, b'\x04'), (control.NOTICE, b''), (control.BACK, struct.pack('<IB', 1, 0)),
                              (control.BACK, struct.pack('<IB', 1, 13)), (control.SAY, b'\x00\x00'), (control.SAY, struct.pack('<H', 2) + b'a'),
                              (control.READY, b'\x02'), (control.READY, b''), (control.ANSWER, struct.pack('<HBB3H', 1, 1, 0, 0, 0, 0)),
                              (control.ANSWER, struct.pack('<HBB3H', 1, 2, 0x80, 0, 0, 0)), (control.ANSWER, struct.pack('<HBB3H', 0, 2, 0, 0, 0, 0))]:
            with self.assertRaises(control.FrameError, msg=(kind, payload)):
                control.decode(kind, payload)
        self.assertEqual(set(good), set(range(control.ROSTER, control.ANSWER + 1)))

    def test_mutated_payloads_are_a_frame_error_or_the_same_message_never_another_exception(self):
        rng = random.Random(20261117)
        accepted = 0
        for message in MESSAGES:
            kind, payload = control.encode(message)
            for _ in range(600):
                data = bytearray(payload)
                for _ in range(rng.randint(1, 3)):
                    action = rng.choice('flip cut grow set')
                    if action == 'flip' and data:
                        data[rng.randrange(len(data))] ^= 1 << rng.randrange(8)
                    elif action == 'cut' and data:
                        del data[rng.randrange(len(data)):]
                    elif action == 'grow':
                        data += bytes(rng.randrange(256) for _ in range(rng.randint(1, 4)))
                    elif data:
                        data[rng.randrange(len(data))] = rng.randrange(256)
                try:
                    found = control.decode(kind, bytes(data))
                except control.FrameError:
                    continue
                accepted += 1
                self.assertEqual(control.encode(found), (kind, bytes(data)))       # accepted means canonical
        self.assertGreater(accepted, 0)

    def test_the_digest_is_of_what_is_compared_and_nothing_else(self):
        base = game()
        self.assertEqual(base.digest(), game(title='Other title', game_options='', seats_max=4, sources=bytes(32)).digest())   # portable: no sources
        for change in ({'converter': (1, 7, 8)}, {'engine': bytes(32)}, {'options': bytes(32)}, {'firmware': bytes([1]) * 32},
                       {'rom': bytes(32)}, {'machine': 'md'}, {'schema': 9}, {'mode': control.MODE_FULL}):
            self.assertNotEqual(base.digest(), game(**change).digest(), change)
        full = game(mode=control.MODE_FULL)
        self.assertNotEqual(full.digest(), game(mode=control.MODE_FULL, sources=bytes(32)).digest())     # full: the sources count
        self.assertEqual(len(base.digest()), 32)


class ChatTextTests(unittest.TestCase):
    def test_a_line_is_cleaned_as_a_name_is_and_cut_at_80_characters(self):
        self.assertEqual(lobby.clean_chat('  hello   there \t\n'), 'hello there')
        self.assertEqual(lobby.clean_chat('a' + chr(0x200b) + 'b' + chr(0x202e) + 'c' + chr(0) + 'd' + chr(7) + 'e' + chr(0xe000) + chr(0x378)), 'abcde')
        self.assertEqual(lobby.clean_chat('Zo' + chr(0x301) + 'e'), 'Z' + chr(0xf3) + 'e')                         # NFC
        self.assertEqual(lobby.clean_chat('x' * 200), 'x' * 80)
        self.assertEqual(len(lobby.clean_chat('\U0001f600' * 200).encode('utf-8')), 320)
        self.assertEqual(lobby.clean_chat(b'caf\xc3\xa9'), 'café')
        self.assertEqual(lobby.clean_chat(b'caf\xe9'), '')                                                           # not UTF-8: refused, not repaired
        self.assertEqual(lobby.clean_chat(' \t​\x01 '), '')
        self.assertEqual(lobby.clean_chat('ab' + chr(0xd800) + 'cd'), 'abcd')                                         # a lone surrogate

    def test_the_ascii_copy_follows_the_games_catalogue_rule(self):
        spec = importlib.util.spec_from_file_location('build_languages_for_lobby', ROOT / 'tools' / 'build_languages.py')
        tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tools)
        for text in ('Hélène', 'Ça va très bien… « oui » – non', 'Zoë ’quoted’ “quoted”', 'plain', 'Ñandú à la plage', 'ÀÉÎÕÜ'):
            self.assertEqual(lobby.ascii_chat(text), tools.ascii_text(text), text)
        self.assertEqual(lobby.ascii_chat('straße ø æ œ ł đ'), 'strasse o ae oe l d')
        self.assertEqual(lobby.ascii_chat('日本 \U0001f600 ok'), '?? ? ok')
        self.assertTrue(all(lobby.ascii_chat(chr(code)).isascii() for code in range(0x20, 0x3000)))
        self.assertEqual(lobby.ascii_chat('e' + chr(0x301)), 'e')

    def test_five_lines_in_five_seconds_and_no_more(self):
        limit = lobby.SlidingLimit(5, 5.0)
        self.assertEqual([limit.take(0.1 * index) for index in range(7)], [True] * 5 + [False] * 2)
        self.assertFalse(limit.take(4.99))
        self.assertTrue(limit.take(5.1))            # the first line (at 0.0) is more than 5 seconds old; the second (0.1) just is
        self.assertFalse(limit.take(5.05))          # the window now holds 0.1, 0.2, 0.3, 0.4 and 5.1
        # at any moment, no 5-second window holds more than five accepted lines, whatever the pattern
        rng, limit, accepted = random.Random(5), lobby.SlidingLimit(5, 5.0), []
        now = 0.0
        for _ in range(2000):
            now += rng.random() * 1.5
            if limit.take(now):
                accepted.append(now)
        for index, moment in enumerate(accepted):
            self.assertLessEqual(len([other for other in accepted[index:] if other - moment < 5.0]), 5)


def joined(room: HostLobby, count: int, now: float = 0.0) -> list:
    out = []
    for number in range(1, count + 1):
        out += room.joined(number, f'Guest{number}', now)
    return out


def sends(actions, kind=None):
    return [action for action in actions if isinstance(action, Send) and (kind is None or isinstance(action.message, kind))]


def events(actions, name=None):
    return [action.data for action in actions if isinstance(action, Event) and (name is None or action.data['event'] == name)]


class HostLobbyTests(unittest.TestCase):
    def room(self, guests: int = 3, capacity: int = 4) -> HostLobby:
        room = HostLobby('Arthur', capacity)
        joined(room, guests)
        room.tick(1.0)
        return room

    def test_a_guest_gets_the_roster_and_the_pick_at_once_and_the_others_in_the_next_roster(self):
        room = HostLobby('Arthur', 4)
        self.assertEqual(room.joined(1, 'Nadia', 0.0)[0].message, room.roster())
        self.assertEqual([player.name for player in room.roster().players], ['Arthur', 'Nadia'])
        room.select(game(), 0.5)
        actions = room.joined(2, 'Karl', 0.6)
        self.assertEqual([type(action.message) for action in actions], [control.Roster, control.Select])
        self.assertEqual(actions[0].to, 2)
        self.assertEqual(room.roster().players[2].check, control.CHECK_ASKING)
        tick = room.tick(1.0)
        self.assertEqual([type(action.message) for action in sends(tick)], [control.Roster])
        self.assertIsNone(sends(tick)[0].to)                                 # every guest
        self.assertEqual(room.tick(1.0), [])                                 # nothing changed: nothing sent
        self.assertEqual(room.joined(1, 'Again', 2.0), [])                   # a guest id the lobby has
        full = joined(HostLobby('a', 3), 5)
        self.assertEqual(len(sends(full, control.Roster)), 2)                # a room of three seats takes two guests

    def test_the_roster_goes_out_at_most_ten_times_a_second(self):
        room = self.room(2)
        sent = 0
        for step in range(200):                       # a guest that joins and leaves a hundred times a second, for two seconds
            now = 2.0 + step * 0.01
            room.joined(9, 'Churn', now)
            room.left(9)
            sent += len(sends(room.tick(now), control.Roster))
        self.assertLessEqual(sent, 21)
        self.assertGreater(sent, 5)

    def test_the_host_stamps_the_sender_and_a_guest_cannot_say_another_name(self):
        room = self.room()
        actions = room.on_message(2, control.Say('  hi   all '), 1.0)
        self.assertEqual(sends(actions)[0].message, control.Chat(2, 'Guest2', 'hi all'))
        self.assertIsNone(sends(actions)[0].to)
        self.assertEqual(events(actions)[0], {'event': 'lobby_chat', 'sender': 2, 'name': 'Guest2', 'text': 'hi all', 'ascii': 'hi all',
                                             'phrase': 0})
        self.assertEqual(sends(room.say(0, 'Hélène ?', 1.0))[0].message, control.Chat(0, 'Arthur', 'Hélène ?'))
        self.assertEqual(events(room.say(0, 'Hélène ?', 1.1))[0]['ascii'], 'Helene ?')
        self.assertFalse(hasattr(control.Say, 'name'))                      # the wire has no field for a name to be claimed in

    def test_chat_is_limited_per_sender_and_a_refused_line_costs_one_notice_a_while(self):
        room = self.room()
        delivered = notices = 0
        for step in range(40):                                # 40 lines in 4 seconds from guest 1
            actions = room.on_message(1, control.Say(f'line {step}'), step * 0.1)
            delivered += len(sends(actions, control.Chat))
            notices += len(sends(actions, control.Notice))
        self.assertEqual(delivered, 5)
        self.assertLessEqual(notices, 8)                      # one every half second, not one per refused line
        self.assertEqual(len(sends(room.on_message(2, control.Say('me too'), 4.0), control.Chat)), 1)       # another sender has its own limit
        self.assertEqual(len(sends(room.say(0, 'host', 4.0), control.Chat)), 1)
        self.assertEqual(sends(room.on_message(3, control.Say('​\x07'), 4.0))[0].message, control.Notice(control.NOTICE_BAD_TEXT))
        self.assertEqual(room.on_message(9, control.Say('x'), 4.0), [])                                         # a guest the lobby does not have

    def test_a_pick_numbers_itself_clears_the_flags_and_asks_everyone(self):
        room = self.room()
        room.on_message(1, control.Ready(True), 1.0)
        actions, refusal = room.select(game(), 2.0)
        self.assertIsNone(refusal)
        self.assertEqual(sends(actions)[0].message, control.Select(1, game()))
        self.assertEqual(events(actions)[0]['game']['title'], 'Battletoads')
        self.assertEqual({room.member_status(guest)['check'] for guest in (1, 2, 3)}, {'asking'})
        self.assertFalse(room.member_status(1)['ready'])
        self.assertEqual(room.select(game(machine='md'), 3.0)[0][0].message.ident, 2)
        self.assertEqual(sends(room.select(None, 3.0)[0])[0].message, control.Select(3, None))
        self.assertEqual({room.member_status(guest)['check'] for guest in (1, 2, 3)}, {'none'})
        for bad in (game(seats_max=1), game(game_options='Speed=1'), game(game_options='a=b\n\n'), game(game_options='x' * 40 + '=1')):
            self.assertIsNotNone(room.select(bad, 4.0)[1], bad.game_options)
        self.assertEqual(room.ident, 3)                      # a refusal changes nothing

    def test_numbers_wrap_in_sixteen_bits_and_skip_zero(self):
        room = self.room(1)
        room.ident = 0xffff
        self.assertEqual(room.select(game(), 1.0)[0][0].message.ident, 1)

    def test_an_answer_counts_for_the_current_pick_only(self):
        room = self.room()
        room.select(game(), 1.0)
        room.select(game(), 1.1)                                                     # a second pick: number 2
        self.assertEqual(room.on_message(1, control.Answer(1, control.CHECK_SAME, 0, (1, 7, 9)), 1.2), [])
        self.assertEqual(room.member_status(1)['check'], 'asking')
        actions = room.on_message(1, control.Answer(2, control.CHECK_OTHER, 3, (1, 7, 3)), 1.2)
        self.assertEqual(events(actions)[0]['status'], 'other')
        self.assertEqual(events(actions)[0]['text'], 'same game, other version (reconvert: converter version, engine)')
        room.on_message(2, control.Answer(2, control.CHECK_MISSING, 0, (0, 0, 0)), 1.2)
        self.assertEqual(events(room.on_message(2, control.Answer(2, control.CHECK_MISSING, 0, (0, 0, 0)), 1.3))[0]['text'],
                         f'not found (needs Battletoads, SHA-256 {SHA})')
        self.assertEqual(events(room.on_message(3, control.Answer(2, control.CHECK_SAME, 0, (1, 7, 9)), 1.2))[0]['text'], 'same game')
        self.assertGreaterEqual(room.ignored, 1)

    def test_a_guest_that_does_not_answer_is_a_failed_check_after_fifteen_seconds(self):
        room = self.room(2)
        room.select(game(), 10.0)
        room.on_message(1, control.Answer(1, control.CHECK_SAME, 0, (1, 7, 9)), 11.0)
        self.assertEqual(events(room.tick(24.9), 'lobby_check'), [])
        late = events(room.tick(25.0), 'lobby_check')
        self.assertEqual([(item['guest'], item['status'], item['text']) for item in late], [(2, 'failed', 'no answer')])
        self.assertEqual(room.member_status(2)['check'], 'failed')

    def test_ready_flags_change_a_few_times_and_only_in_the_lobby(self):
        room = self.room()
        before = room.revision
        for step in range(10):
            room.on_message(1, control.Ready(step % 2 == 0), 1.0)
        self.assertEqual(room.revision, before + 4)                                  # four changes taken in two seconds, six refused
        self.assertEqual(room.on_message(1, control.Ready(True), 3.5), [])
        self.assertTrue(room.member_status(1)['ready'])
        room.select(game(), 4.0)
        room.on_message(1, control.Answer(1, control.CHECK_SAME, 0, (1, 7, 9)), 4.1)
        room.begin([1], 1)
        refused = room.on_message(2, control.Ready(True), 5.0)
        self.assertEqual(sends(refused)[0].message, control.Notice(control.NOTICE_BUSY))
        self.assertFalse(room.member_status(2)['ready'])

    def test_the_host_moves_guests_in_the_lobby_only(self):
        room = self.room()
        self.assertIsNone(room.move(3, 1))
        self.assertEqual(room.guests(), [3, 1, 2])
        self.assertEqual([player.guest for player in room.roster().players], [0, 3, 1, 2])         # the host stays seat 0
        for guest, seat in ((3, 0), (3, 4), (9, 1), (1, -1)):
            self.assertIsNotNone(room.move(guest, seat), (guest, seat))
        room.begin([3], 1)
        self.assertIsNotNone(room.move(1, 1))
        self.assertEqual(room.guests(), [3, 1, 2])

    def test_a_launch_takes_the_players_who_have_the_game_in_seat_order_and_the_others_stay(self):
        room = self.room()
        self.assertEqual(room.plan_launch().reason, 'no game is chosen')
        room.select(game(seats_max=3), 1.0)
        self.assertEqual(room.plan_launch().reason, 'nobody has the game')
        for guest, status in ((1, control.CHECK_MISSING), (2, control.CHECK_SAME), (3, control.CHECK_SAME)):
            room.on_message(guest, control.Answer(1, status, 0, (1, 7, 9)), 1.1)
        room.on_message(3, control.Ready(True), 1.2)
        plan = room.plan_launch()
        self.assertEqual((plan.guests, plan.stamp, plan.rom, plan.options), ((2, 3), game(seats_max=3).digest(), bytes.fromhex(SHA), 'speed=1'))
        self.assertEqual([(guest, reason) for guest, _name, reason in plan.left_out], [(1, 'does not have the game')])
        ready = room.plan_launch(need_ready=True)
        self.assertEqual((ready.guests, ready.left_out[1][2]), ((3,), 'is not ready'))
        room.move(3, 1)                                                           # seat order is the host's
        self.assertEqual(room.plan_launch().guests, (3, 2))
        room.select(game(seats_max=2), 2.0)                                       # a two-player game takes one guest
        for guest in (1, 2, 3):
            room.on_message(guest, control.Answer(2, control.CHECK_SAME, 0, (1, 7, 9)), 2.1)
        two = room.plan_launch()
        self.assertEqual((two.guests, [reason for _g, _n, reason in two.left_out]), ((3,), ['the game has no more seats'] * 2))
        room.on_message(3, control.Answer(2, control.CHECK_OTHER, 1, (1, 7, 3)), 2.2)
        self.assertEqual(room.plan_launch().guests, (1,))
        self.assertEqual(room.plan_launch(need_ready=True).reason, 'nobody who has the game is ready')

    def test_a_match_that_ends_brings_everyone_back_to_the_lobby_with_the_pick_kept(self):
        room = self.room(2)
        room.select(game(), 1.0)
        for guest in (1, 2):
            room.on_message(guest, control.Answer(1, control.CHECK_SAME, 0, (1, 7, 9)), 1.1)
        room.on_message(1, control.Ready(True), 1.2)
        started = room.begin([1], 5)
        self.assertEqual(events(started)[0], {'event': 'lobby_launch', 'match_id': 5, 'seats': 2, 'names': ['Arthur', 'Guest1'],
                                               'left_out': [{'guest': 2, 'name': 'Guest2', 'reason': 'not seated'}],
                                           'sharing': 'per_player'})
        self.assertEqual((room.phase, room.roster().players[1].in_match, room.roster().players[2].in_match), (control.PHASE_LAUNCHING, True, False))
        room.playing()
        self.assertEqual(room.phase, control.PHASE_PLAYING)
        self.assertEqual(room.plan_launch().reason, 'a match is already starting or running')
        self.assertIsNotNone(room.select(game(machine='md'), 2.0)[1])                # no switching in the middle of a match
        back = room.finished(5, 'desync')
        self.assertEqual(sends(back)[0].message, control.Back(5, 8))
        self.assertEqual(events(back)[0], {'event': 'lobby_back', 'match_id': 5, 'reason': 'desync'})
        self.assertEqual((room.phase, room.game, room.member_status(1)['ready'], room.member_status(1)['in_match']),
                         (control.PHASE_LOBBY, game(), False, False))
        self.assertEqual(room.member_status(1)['check'], 'same')
        self.assertEqual(room.finished(5, 'ended'), [])                              # once
        room.begin([1], 6)
        self.assertEqual(sends(room.finished(6, 'a reason nobody knows'))[0].message, control.Back(6, 10))
        for outcome in ('ended', 'game_closed', 'pipe_lost', 'left', 'seat_left', 'seat_silent', 'host_closed', 'desync', 'boot_mismatch',
                        'error', 'launch_failed', 'refused'):
            self.assertIn(lobby.BACK_CODES[outcome], control.BACK_REASONS)

    def test_a_guest_who_leaves_is_off_the_roster_and_a_switch_asks_the_rest_again(self):
        room = self.room()
        room.select(game(), 1.0)
        room.left(2)
        self.assertEqual([player.guest for player in room.roster().players], [0, 1, 3])
        self.assertEqual(room.on_message(2, control.Say('ghost'), 2.0), [])
        room.on_message(1, control.Answer(1, control.CHECK_SAME, 0, (1, 7, 9)), 2.0)
        room.select(game(machine='md', title='Sonic 2'), 3.0)
        self.assertEqual(room.member_status(1)['check'], 'asking')

    def test_the_check_lines_for_a_log(self):
        self.assertEqual(lobby.check_text(game(), control.CHECK_FAILED), 'could not check')
        self.assertEqual(lobby.check_text(game(), control.CHECK_OTHER, lobby_check.R_FIRMWARE | lobby_check.R_NO_IDENTITY),
                         'same game, other version (reconvert: firmware, no simulation identity)')


class GuestLobbyTests(unittest.TestCase):
    def test_a_guest_follows_the_host_and_asks_its_library_for_each_pick(self):
        guest = GuestLobby('Nadia')
        guest.me = 2
        roster = control.Roster(4, control.PHASE_LOBBY, 2, 1, (control.Player(0, 'Arthur', True), control.Player(2, 'Nadia')))
        first = guest.on_message(roster, 0.0)
        self.assertEqual(events(first)[0]['me'], 2)
        self.assertEqual(guest.on_message(roster, 0.1), [])                           # the same revision twice is one change
        picked = guest.on_message(control.Select(1, game()), 0.2)
        self.assertEqual([item['event'] for item in events(picked)], ['lobby_selection', 'lobby_check_request'])
        self.assertEqual(events(picked)[1]['game']['digest'], game().digest().hex())
        self.assertEqual(guest.answer(2, control.CHECK_SAME), [])                       # an answer to another number is not sent
        self.assertEqual(guest.answer(1, 9), [])
        sent = guest.answer(1, control.CHECK_SAME, 0, (1, 7, 9))
        self.assertEqual(sent, [Send(None, control.Answer(1, control.CHECK_SAME, 0, (1, 7, 9)))])
        cleared = guest.on_message(control.Select(2, None), 0.3)
        self.assertEqual([item['event'] for item in events(cleared)], ['lobby_selection'])
        self.assertEqual(guest.answer(2, control.CHECK_SAME), [])

    def test_a_guest_cleans_what_the_host_sends_before_it_reaches_a_window(self):
        guest = GuestLobby('Nadia')
        shown = events(guest.on_message(control.Chat(1, 'Karl​', 'hi\x07 there ' + chr(0xe9)), 0.0))[0]
        self.assertEqual((shown['name'], shown['text'], shown['ascii']), ('Karl', 'hi there é', 'hi there e'))
        self.assertEqual(guest.on_message(control.Chat(1, 'Karl', '\x07​'), 0.0), [])
        self.assertEqual(events(guest.on_message(control.Notice(control.NOTICE_CHAT_FAST), 0.0))[0]['code'], 'chat_too_fast')
        self.assertEqual(events(guest.on_message(control.Back(3, 1), 0.0))[0], {'event': 'lobby_back', 'match_id': 3, 'reason': 'ended'})

    def test_a_guest_cleans_the_hosts_names_and_title_and_never_looks_up_a_pick_that_is_not_valid(self):
        guest = GuestLobby('Nadia')
        roster = control.Roster(1, control.PHASE_LOBBY, 0, 0, (control.Player(0, 'Ar‮thur'), control.Player(1, '​')))
        self.assertEqual([player['name'] for player in events(guest.on_message(roster, 0.0))[0]['players']], ['Arthur', '?'])
        picked = events(guest.on_message(control.Select(1, game(title='Evil‮ title')), 0.0), 'lobby_check_request')[0]
        self.assertEqual(picked['game']['title'], 'Evil title')
        self.assertEqual(guest.game.digest(), game().digest())                          # the title is not what is compared
        bad = guest.on_message(control.Select(2, game(game_options='Speed=1')), 0.1)
        self.assertEqual([item['event'] for item in events(bad)], ['lobby_selection', 'lobby_notice'])
        self.assertIsNone(events(bad)[0]['game'])
        self.assertEqual(sends(bad)[0].message, control.Answer(2, control.CHECK_FAILED, 0, (0, 0, 0)))
        self.assertEqual(guest.answer(2, control.CHECK_SAME), [])                         # and nothing can turn it into a yes
        launch = control.Launch(1, 1, 2, 0, 60, 3, 'nes', game().digest(), bytes.fromhex(SHA), ('Arthur', 'Nadia'), '')
        self.assertEqual(guest.launch_status(launch), control.LAUNCHED_FAILED)

    def test_a_guest_limits_its_own_chat_and_ready_flags_before_the_host_has_to(self):
        guest = GuestLobby('Nadia')
        said = [guest.say(f'line {step}', step * 0.1) for step in range(8)]
        self.assertEqual([bool(sends(actions)) for actions in said], [True] * 5 + [False] * 3)
        self.assertEqual(events(said[5])[0]['code'], 'chat_too_fast')
        self.assertEqual(events(guest.say('​', 9.0))[0]['code'], 'bad_text')
        self.assertEqual(sum(bool(guest.ready(step % 2 == 0, 20.0)) for step in range(10)), 4)

    def test_a_launch_is_accepted_only_for_the_game_this_pc_said_the_same_to(self):
        guest = GuestLobby('Nadia')
        launch = control.Launch(1, 1, 2, 0, 60, 3, 'nes', game().digest(), bytes.fromhex(SHA), ('Arthur', 'Nadia'), 'speed=1')
        self.assertEqual(guest.launch_status(launch), control.LAUNCHED_READY)           # no pick: the launch's own identity decides
        guest.on_message(control.Select(1, game()), 0.0)
        self.assertEqual(guest.launch_status(launch), control.LAUNCHED_FAILED)          # not answered
        for answer, wanted in ((control.CHECK_SAME, control.LAUNCHED_READY), (control.CHECK_MISSING, control.LAUNCHED_NOT_OWNED),
                               (control.CHECK_OTHER, control.LAUNCHED_OTHER_STAMP), (control.CHECK_FAILED, control.LAUNCHED_FAILED)):
            guest.answer(1, answer)
            self.assertEqual(guest.launch_status(launch), wanted, answer)
        guest.answer(1, control.CHECK_SAME)
        for other in (launch.__class__(**{**launch.__dict__, 'stamp': bytes(32)}), launch.__class__(**{**launch.__dict__, 'rom_sha': bytes(32)}),
                      launch.__class__(**{**launch.__dict__, 'machine': 'md'})):
            self.assertEqual(guest.launch_status(other), control.LAUNCHED_OTHER_STAMP)


# ---- the check, against scratch libraries ----

def report(machine='nes', rom=SHA, version='1.7.9', engine=ENGINE, sources='11' * 32, options=None, firmware=None, identity=True, title=None,
           schema=simulation_identity.SCHEMA):
    record = {'schema': schema, 'identity': ('f' * 64) if identity else None, 'engine': {'files': 3, 'pins': {}, 'sha256': engine},
              'rom': rom, 'options': {'standard_override': None} if options is None else options,
              'sources': {'files': 2, 'sha256': sources} if sources else None, 'reason': None if identity else 'no build project'}
    data = {'tool': 'Retro-Recomp', 'version': version, 'system': {'id': machine}, 'rom': {'sha256': rom}, 'executable': 'game.exe',
            'simulation_identity': record}
    if title:
        data['title'] = title
    if firmware:
        data['bios'] = {'sha256': firmware}
    return data


class Scratch:
    """A scratch library: a folder with an inventory file of its own, fake reports and fake executables."""

    def __init__(self, test: unittest.TestCase):
        self.root = Path(tempfile.mkdtemp(prefix='lobby-library-'))
        test.addCleanup(shutil.rmtree, self.root, True)
        self.inventory = compiled_games.Inventory(self.root / 'datas' / 'compiled-games.json', base=self.root)
        self.count = 0

    def add(self, data: dict | None, *, machine='nes', rom=SHA, title='Battletoads', version='1.7.9', exe=True, modified=0):
        self.count += 1
        folder = self.root / f'game{self.count}'
        folder.mkdir()
        executable = folder / 'game.exe'
        if exe:
            executable.write_bytes(b'MZ fake')
        report_path = folder / 'conversion-report.json'
        if data is not None:
            report_path.write_text(json.dumps(data), encoding='utf-8')
        entry = compiled_games.Game(str(executable), machine, rom, title, str(report_path), version, modified=modified)
        self.inventory.remember(entry)
        return entry

    def library(self) -> lobby_check.LocalLibrary:
        return lobby_check.LocalLibrary(self.inventory)


def host_pick(machine='nes', **changes) -> control.Game:
    candidate = lobby_check.game_from_report(report(machine=machine, **changes), 'Battletoads')
    assert candidate.game is not None, candidate.reason
    return candidate.game


class CheckTests(unittest.TestCase):
    def test_the_data_in_one_place(self):
        # The per-machine facts are the profiles' (`SystemProfile.netplay_*`, 17 Nov 2026), read through lobby_check.
        portable = {profile.id for profile in ALL_PROFILES if lobby_check.portable(profile.id)}
        self.assertEqual(portable, {'nes', 'md', 'sms'})                       # the machines whose mixed-build gate passed
        self.assertEqual({profile.id for profile in ALL_PROFILES if lobby_check.session_capable(profile.id)},
                         {'nes', 'md', 'sms', 'gg', 'gb', 'snes', 'cps1', 'cps2', 'msx', 'msx2', 'msx2plus', 'pce', 'atarist', 'psx',
                          'ng', 'n64', 'gba', 'amiga', 'a1200', 'x68', 'cpc'})
        self.assertTrue(all(1 <= lobby_check.machine_seats(profile.id) <= control.MAX_SEATS for profile in ALL_PROFILES))
        self.assertEqual(lobby_check.machine_seats('no such machine'), 1)
        self.assertFalse(lobby_check.portable(None) or lobby_check.session_capable('no such machine'))
        source = (ROOT / 'retrorecomp/netplay/lobby_check.py').read_text(encoding='utf-8')
        self.assertIn('MIXED_BUILD_GATE.md', source)
        self.assertNotRegex(source, r"frozenset\(\('nes'")                       # no copy of the profiles' data here
        self.assertEqual(lobby_check.mode_for('nes'), control.MODE_PORTABLE)
        self.assertEqual(lobby_check.mode_for('gg'), control.MODE_FULL)                # the Game Gear was not run in the gate

    def test_versions_and_reasons(self):
        self.assertEqual(lobby_check.parse_version('1.7.9'), (1, 7, 9))
        for text in ('1.7', '1.7.9-dev', '', None, 'x.y.z', '1.7.70000', '1.7.9.1'):
            self.assertIsNone(lobby_check.parse_version(text), text)
        self.assertEqual(lobby_check.reason_names(lobby_check.R_ENGINE | lobby_check.R_SOURCES), ['engine', 'learned paths'])
        self.assertEqual(lobby_check.reason_names(0), [])

    def test_a_report_becomes_a_comparable_game_or_says_why_not(self):
        picked = lobby_check.game_from_report(report(title='From the report'), 'Battletoads', game_options='speed=1')
        self.assertEqual((picked.game.machine, picked.game.converter, picked.game.rom.hex(), picked.game.engine.hex(), picked.game.seats_max,
                          picked.game.mode, picked.game.title, picked.game.game_options, picked.version),
                         ('nes', (1, 7, 9), SHA, ENGINE, 2, control.MODE_PORTABLE, 'Battletoads', 'speed=1', (1, 7, 9)))
        self.assertEqual(picked.game.sources, bytes.fromhex('11' * 32))
        self.assertEqual(picked.game.firmware, bytes(32))
        self.assertEqual(lobby_check.game_from_report(report(machine='snes'), 't').game.mode, control.MODE_FULL)
        self.assertEqual(lobby_check.game_from_report(report(machine='gb'), 't').game.seats_max, 1)
        self.assertEqual(lobby_check.game_from_report(report(machine='n64'), 't', seats_max=3).game.seats_max, 3)
        self.assertEqual(lobby_check.game_from_report(report(), '​').game.title, 'nes')              # a title with nothing left
        self.assertNotEqual(lobby_check.game_from_report(report(firmware='9' * 64), 't').game.firmware, bytes(32))
        self.assertEqual(lobby_check.game_from_report(report(firmware='9' * 64), 't').game.firmware,
                         lobby_check.game_from_report(report(firmware='9' * 64), 'u').game.firmware)
        # the options are digested in a canonical order
        self.assertEqual(lobby_check.game_from_report(report(options={'a': 1, 'b': 2}), 't').game.options,
                         lobby_check.game_from_report(report(options={'b': 2, 'a': 1}), 't').game.options)
        for bad, why in ((None, 'not a record'), ({}, 'no machine'), (report(version='dev'), 'converter version'),
                         (report(schema=1), 'no simulation identity'), (report(engine='zz'), 'incomplete'),
                         (dict(report(), rom={'sha256': '00' * 32}), 'incomplete'), (report(machine='snes', sources=None), 'no identity of its generated sources'),
                         (report(machine='snes', identity=False), 'no build project')):
            candidate = lobby_check.game_from_report(bad, 't')
            self.assertIsNone(candidate.game)
            self.assertIn(why, candidate.reason, bad)
        removed = report()
        del removed['simulation_identity']
        self.assertIn('reconvert', lobby_check.game_from_report(removed, 't').reason)
        self.assertIsNotNone(lobby_check.game_from_report(report(sources=None, identity=False), 't').game)          # portable: no sources needed

    def test_compare_names_what_differs_and_the_learned_paths_only_where_they_count(self):
        host = host_pick()
        self.assertEqual(lobby_check.compare(host, host), 0)
        self.assertEqual(lobby_check.compare(host, host_pick(sources='22' * 32)), 0)                       # NES: other learned paths, same game
        self.assertEqual(lobby_check.compare(host_pick('snes'), host_pick('snes', sources='22' * 32)), lobby_check.R_SOURCES)
        self.assertEqual(lobby_check.compare(host, host_pick(version='1.7.8')), lobby_check.R_CONVERTER)
        self.assertEqual(lobby_check.compare(host, host_pick(engine='ee' * 32)), lobby_check.R_ENGINE)
        self.assertEqual(lobby_check.compare(host, host_pick(options={'standard_override': 'pal'})), lobby_check.R_OPTIONS)
        self.assertEqual(lobby_check.compare(host, host_pick(firmware='9' * 64)), lobby_check.R_FIRMWARE)
        many = lobby_check.compare(host, host_pick(version='1.7.8', engine='ee' * 32, firmware='9' * 64))
        self.assertEqual(many, lobby_check.R_CONVERTER | lobby_check.R_ENGINE | lobby_check.R_FIRMWARE)
        # a host that claims a mode this converter does not give the machine cannot weaken the comparison
        weak = control.Game(**{**host_pick('snes').__dict__, 'mode': control.MODE_PORTABLE, 'sources': bytes(32)})
        self.assertEqual(lobby_check.compare(weak, host_pick('snes')), lobby_check.R_SOURCES)

    def test_a_guest_looks_in_its_own_library_and_answers_same_other_or_not_found(self):
        mine = Scratch(self)
        pick = host_pick()
        self.assertEqual(mine.library().check(pick).status, control.CHECK_MISSING)
        nobody = mine.library().check(pick)
        self.assertEqual(nobody.text, f'not found (needs Battletoads, SHA-256 {SHA})')
        mine.add(report(rom='0f' * 32), rom='0f' * 32)                                   # another game of the same machine
        mine.add(report(machine='md'), machine='md')                                     # the same dump on another machine
        self.assertEqual(mine.library().check(pick).status, control.CHECK_MISSING)
        mine.add(None, exe=False)                                                        # an entry with no report and no executable
        self.assertEqual(mine.library().check(pick).status, control.CHECK_MISSING)
        old = mine.add(report(version='1.7.3'), version='1.7.3')
        answer = mine.library().check(pick)
        self.assertEqual((answer.status, answer.reasons, answer.version, answer.found), (control.CHECK_OTHER, lobby_check.R_CONVERTER, (1, 7, 3), old))
        self.assertEqual(answer.text, 'same game, other version (reconvert: converter version)')
        same = mine.add(report(sources='33' * 32), modified=5)                           # the learned paths differ: the same game on the NES
        answer = mine.library().check(pick)
        self.assertEqual((answer.status, answer.reasons, answer.found, answer.text), (control.CHECK_SAME, 0, same, 'same game'))

    def test_the_best_export_wins_and_the_newest_of_equals(self):
        mine = Scratch(self)
        mine.add(report(version='1.7.1', engine='01' * 32, firmware='9' * 64), modified=1)         # three differences
        two = mine.add(report(version='1.7.2', engine='02' * 32), modified=2)                       # two
        self.assertEqual(mine.library().check(host_pick()).found, two)
        one = mine.add(report(version='1.7.3'), modified=3)
        newer = mine.add(report(version='1.7.4'), modified=4)                                       # one, and newer
        answer = mine.library().check(host_pick())
        self.assertEqual((answer.reasons, answer.found), (lobby_check.R_CONVERTER, newer))
        answer = mine.library().check(host_pick(version='1.7.3'))
        self.assertEqual((answer.status, answer.found), (control.CHECK_SAME, one))

    def test_full_machines_compare_the_generated_sources_and_firmware_when_a_report_names_it(self):
        mine = Scratch(self)
        mine.add(report(machine='snes', sources='22' * 32), machine='snes')
        answer = mine.library().check(host_pick('snes'))
        self.assertEqual((answer.status, answer.reasons), (control.CHECK_OTHER, lobby_check.R_SOURCES))
        self.assertEqual(answer.text, 'same game, other version (reconvert: learned paths)')
        mine.add(report(machine='snes', firmware='9' * 64), machine='snes')
        self.assertEqual(mine.library().check(host_pick('snes', firmware='9' * 64)).reasons, 0)
        self.assertEqual(mine.library().check(host_pick('snes', firmware='8' * 64)).reasons, lobby_check.R_FIRMWARE)     # the better export is judged

    def test_an_export_without_identity_is_one_to_reconvert_and_an_unreadable_report_is_not_a_crash(self):
        mine = Scratch(self)
        removed = report()
        del removed['simulation_identity']
        mine.add(removed)
        answer = mine.library().check(host_pick())
        self.assertEqual((answer.status, answer.reasons), (control.CHECK_OTHER, lobby_check.R_NO_IDENTITY))
        broken = mine.add(None)
        Path(broken.report).write_text('{not json', encoding='utf-8')
        self.assertEqual(mine.library().check(host_pick()).reasons, lobby_check.R_NO_IDENTITY)
        Path(broken.report).write_bytes(b'[]')
        self.assertEqual(len(mine.library().hostable()), 0)

    def test_the_host_can_pick_what_has_an_identity_and_a_second_player_or_a_handheld(self):
        mine = Scratch(self)
        nes = mine.add(report(), title='Battletoads')
        gg = mine.add(report(machine='gg'), machine='gg')                                # a handheld: one player, input sharing
        mine.add(report(machine='gb'), machine='gb')                                     # a handheld: one player, input sharing (since its rollback)
        mine.add(report(machine='gba'), machine='gba')                                   # a handheld: one player, input sharing (the delay tier: its digest, no snapshot)
        mine.add(report(machine='scummvm'), machine='scummvm')                           # one player and not a pad game: not offered
        mine.add(report(identity=False, machine='snes', sources=None), machine='snes')    # no identity of its sources
        listed = mine.library().hostable()
        self.assertEqual(sorted((entry.system, picked.title, picked.seats_max) for entry, picked in listed),
                         [('gb', 'Battletoads', 1), ('gba', 'Battletoads', 1), ('gg', 'Battletoads', 1), ('nes', 'Battletoads', 2)])
        self.assertIn(gg, [entry for entry, _picked in listed])
        self.assertEqual(mine.library().game_of(nes, 'speed=2').game.game_options, 'speed=2')
        Path(nes.executable).unlink()
        self.assertIn('cannot be read', mine.library().game_of(nes).reason)
        self.assertEqual(lobby_check.game_config(nes), {'exe': nes.executable, 'cwd': str(Path(nes.executable).parent)})

    def test_the_library_is_the_one_given_and_never_the_real_one(self):
        scratch = Scratch(self)
        # Resolved on both sides: a Windows temp folder may be given by its 8.3 short name (RUNNER~1) and kept long.
        self.assertEqual(scratch.inventory.path.parent.parent.resolve(), scratch.root.resolve())
        self.assertEqual(scratch.library().inventory.snapshot(), [])
        self.assertFalse(scratch.inventory.path.exists())                         # nothing was even written


# ---- the window's model and the controller ----

class FakeWorker:
    def __init__(self):
        self.calls = []

    def call(self, name, **fields):
        self.calls.append((name, fields))


class ModelTests(unittest.TestCase):
    def test_a_list_of_events_becomes_the_state_a_window_draws(self):
        model = lobby_client.LobbyModel()
        for event in ({'event': 'room_open', 'address': '127.0.0.1', 'port': 5000},
                      {'event': 'lobby_roster', 'revision': 1, 'phase': 'lobby', 'seats_max': 0, 'selection': 0,
                       'players': [{'seat': 0, 'guest': 0, 'name': 'Arthur', 'ready': True, 'in_match': False, 'check': 'none'}]},
                      {'event': 'lobby_selection', 'selection': 2, 'game': {'title': 'Battletoads'}},
                      {'event': 'lobby_check', 'guest': 1, 'name': 'Nadia', 'selection': 2, 'status': 'same', 'reasons': 0, 'version': [1, 7, 9],
                       'text': 'same game'},
                      {'event': 'lobby_check', 'guest': 2, 'name': 'Old', 'selection': 1, 'status': 'same', 'reasons': 0, 'version': [0, 0, 0], 'text': ''},
                      {'event': 'lobby_chat', 'sender': 1, 'name': 'Nadia', 'text': 'hi', 'ascii': 'hi'},
                      {'event': 'lobby_notice', 'code': 'chat_too_fast', 'detail': ''},
                      {'event': 'lobby_launch', 'match_id': 1, 'seats': 2, 'names': ['Arthur', 'Nadia'], 'left_out': []},
                      {'event': 'match_over', 'match_id': 1, 'outcome': 'ended', 'detail': ''},
                      {'event': 'lobby_back', 'match_id': 1, 'reason': 'ended'}, {'event': 'launch_error', 'detail': 'busy'},
                      {'event': 'something_new'}, 'not an event'):
            model.apply(event)
        self.assertEqual((model.room, model.address, model.selection, model.phase, model.version), ('open', ('127.0.0.1', 5000), 2, 'lobby', 13))
        self.assertEqual(model.checks, {1: {'name': 'Nadia', 'status': 'same', 'reasons': 0, 'version': [1, 7, 9], 'text': 'same game'}})    # an old pick's answer is not shown
        self.assertEqual(list(model.chat), [{'sender': 1, 'name': 'Nadia', 'text': 'hi', 'ascii': 'hi', 'phrase': 0}])
        self.assertEqual((model.last_launch['names'], model.last_back, model.matches[0]['outcome'], model.errors[0]['detail']),
                         (['Arthur', 'Nadia'], {'match_id': 1, 'reason': 'ended'}, 'ended', 'busy'))

    def test_the_model_is_bounded(self):
        model = lobby_client.LobbyModel()
        for number in range(1000):
            model.apply({'event': 'lobby_chat', 'sender': 1, 'name': 'N', 'text': str(number), 'ascii': str(number)})
            model.apply({'event': 'lobby_notice', 'code': 'bad_text'})
            model.apply({'event': 'match_over', 'match_id': number})
        self.assertEqual((len(model.chat), len(model.notices), len(model.matches)), (lobby_client.CHAT_KEPT, lobby_client.NOTICES_KEPT, lobby_client.NOTICES_KEPT))
        self.assertEqual(model.chat[-1]['text'], '999')


class ControllerTests(unittest.TestCase):
    def test_a_guest_answers_from_its_own_library_and_resolves_the_launch_to_the_executable_it_found(self):
        mine = Scratch(self)
        found = mine.add(report(sources='33' * 32))
        controller = lobby_client.LobbyController(mine.library())
        worker = FakeWorker()
        controller.attach(worker)
        pick = host_pick()
        controller._check({'selection': 4, 'game': lobby.game_dict(pick)})
        self.assertEqual(worker.calls, [('lobby_answer', {'selection': 4, 'status': control.CHECK_SAME, 'reasons': 0, 'version': [1, 7, 9]})])
        request = {'machine': 'nes', 'rom': SHA, 'stamp': pick.digest().hex(), 'match_id': 7}
        self.assertEqual(controller.resolve(request)['game'], {'exe': found.executable, 'cwd': str(Path(found.executable).parent)})
        self.assertEqual(controller.resolve(request)['match_id'], 7)
        for wrong in ({**request, 'stamp': '00' * 32}, {**request, 'rom': '00' * 32}, {**request, 'machine': 'md'}):
            self.assertEqual(controller.resolve(wrong)['call'], 'launch_refused')
        # the pick changes to a version this PC does not have: no executable is kept, and the launch is refused
        other = host_pick(version='1.7.8')
        controller._check({'selection': 5, 'game': lobby.game_dict(other)})
        self.assertEqual(worker.calls[-1][1], {'selection': 5, 'status': control.CHECK_OTHER, 'reasons': lobby_check.R_CONVERTER, 'version': [1, 7, 9]})
        self.assertEqual(controller.answers[-1]['text'], 'same game, other version (reconvert: converter version)')
        self.assertEqual(controller.resolve({**request, 'stamp': other.digest().hex()})['call'], 'launch_refused')

    def test_what_this_pc_cannot_check_is_answered_as_not_checked_and_never_raises(self):
        controller = lobby_client.LobbyController(Scratch(self).library())
        worker = FakeWorker()
        controller.attach(worker)
        controller._check({'selection': 1, 'game': {'machine': 'nes'}})
        self.assertEqual(worker.calls[0][1]['status'], control.CHECK_FAILED)
        self.assertIn('could not check', controller.answers[0]['text'])
        self.assertEqual(controller.resolve({'machine': 'nes', 'rom': SHA, 'stamp': '00' * 32, 'match_id': 1})['call'], 'launch_refused')

    def test_the_host_picks_and_launches_through_calls_and_nothing_else(self):
        mine = Scratch(self)
        entry = mine.add(report(), title='Battletoads')
        controller = lobby_client.LobbyController(mine.library())
        worker = FakeWorker()
        controller.attach(worker)
        self.assertEqual(controller.launch(), 'no game is picked')
        self.assertEqual(controller.pick(entry, 'speed=1'), '')
        name, fields = worker.calls[-1]
        self.assertEqual((name, fields['game']['title'], fields['game']['game_options']), ('lobby_select', 'Battletoads', 'speed=1'))
        self.assertEqual(lobby.game_from_dict(fields['game']), control.Game(**{**host_pick().__dict__, 'game_options': 'speed=1'}))
        controller.say('hello')
        controller.ready(True)
        controller.move(2, 1)
        self.assertEqual(controller.launch({'delay': 3}, need_ready=True), '')
        self.assertEqual([call[0] for call in worker.calls[1:]], ['lobby_chat', 'lobby_ready', 'lobby_move', 'lobby_launch'])
        self.assertEqual(worker.calls[-1][1]['settings'], {'delay': 3})
        self.assertEqual(worker.calls[-1][1]['game']['exe'], entry.executable)
        Path(entry.executable).unlink()
        self.assertIn('cannot be read', controller.pick(entry))
        controller.clear_pick()
        self.assertEqual(worker.calls[-1], ('lobby_select', {'game': None}))
        self.assertEqual(controller.launch(), 'no game is picked')

    def test_game_dictionaries_round_trip_and_refuse_what_the_wire_would(self):
        pick = host_pick('snes')
        self.assertEqual(lobby.game_from_dict(lobby.game_dict(pick)), pick)
        data = lobby.game_dict(host_pick())
        self.assertEqual((data['sources'], data['firmware']), ('11' * 32, ''))
        for change in ({'rom': 'zz'}, {'rom': '00'}, {'mode': 'weird'}, {'machine': 'a b'}, {'converter': [1, 2]}, {'title': ''},
                       {'game_options': 'é'}, {'seats_max': 9}, {'schema': True}, {'title': 7}):
            with self.assertRaises(ValueError, msg=change):
                lobby.game_from_dict({**data, **change})
        with self.assertRaises(ValueError):
            lobby.game_from_dict([])


class WindowApiTests(unittest.TestCase):
    """What the Multiplayer window calls (`lobby_client`): configs, codes it can translate, the link line, a safe close."""

    def test_configs_codes_link_and_invitation_of_the_port_really_bound(self):
        from pathlib import Path
        from retrorecomp.netplay import invitation, lobby_client
        from retrorecomp.netplay.lan_transport import RoomError, room_code, NO_ANSWER
        config, text = lobby_client.host_config('192.168.1.18', 24611, 'Arthur', 'per_player', Path('logs'))
        room = config['room']
        self.assertEqual((room['role'], room['capacity'], room['port'], config['tests']), ('host', 4, 24611, False))
        self.assertEqual(invitation.parse(text).port, 24611)
        with self.assertRaises(ValueError):
            lobby_client.host_config('8.8.8.8', 24611, 'Arthur', 'per_player', Path('logs'))
        guest = lobby_client.guest_config(' ' + text + ' ', 'Nadia', Path('logs'))
        self.assertEqual((guest['room']['role'], guest['room']['invitation'], len(guest['room']['version'])), ('guest', text, 3))
        with self.assertRaises(invitation.InvitationError):
            lobby_client.guest_config('not an invitation', 'Nadia', Path('logs'))
        self.assertEqual([room_code(r) for r in (NO_ANSWER, 'the room is full', 'update Retro-Recomp on both PCs',
                                                  'the host closed the room', 'the connection to the host broke',
                                                  'the host was silent for ten seconds', 'something new')],
                         ['unreachable', 'full', 'other_version', 'closed', 'lost', 'timeout', 'other'])
        self.assertEqual(RoomError('the room is full').code, 'full')
        model = lobby_client.LobbyModel()
        model.secret = bytes.fromhex(room['secret'])
        model.apply({'event': 'room_open', 'address': '192.168.1.18', 'port': 24700})
        self.assertEqual(invitation.parse(model.invitation).port, 24700)        # the port the room bound, not the one asked
        model.apply({'event': 'launching', 'tier': 'rollback', 'prediction': 5})
        model.apply({'event': 'slow_link', 'delay': 10})
        self.assertEqual(model.link, {'tier': 'rollback', 'prediction': 5, 'delay': None, 'slow': 10, 'path': 'lan'})
        model.apply({'event': 'lobby_back', 'match_id': 1, 'reason': 'ended'})
        self.assertIsNone(model.link)
        model.apply({'event': 'host_gone', 'detail': 'the host closed the room', 'code': 'closed'})
        self.assertEqual((model.room, model.room_code), ('host_gone', 'closed'))
        model.apply({'event': 'launch_refused', 'detail': 'x'})
        self.assertEqual(model.errors[-1]['code'], 'launch_refused')

    def test_the_compiled_games_right_click_hosts_only_where_a_session_is_possible(self):
        from retrorecomp import i18n
        from retrorecomp.netplay.lobby_check import session_capable
        source = (ROOT / 'retrorecomp/compiled_games_view.py').read_text(encoding='utf-8')
        self.assertIn("self.owner.show_multiplayer(pick=game)", source)
        self.assertIn("session_capable(single.system)", source)
        self.assertTrue(session_capable('nes') and session_capable('gg') and not session_capable('scummvm'))
        for key in ('mp_host_game', 'mp_not_offered'):
            self.assertIn(key, i18n.UI if hasattr(i18n, 'UI') else (ROOT / 'retrorecomp/i18n.py').read_text(encoding='utf-8'))

    def test_close_is_safe_twice_and_from_any_thread(self):
        import threading
        from retrorecomp.netplay import lobby_client
        calls = []
        worker = type('Worker', (), {'call': lambda self, name, **f: calls.append(name), 'join': lambda self, t=None: True,
                                     'cleanup': lambda self: calls.append('cleanup'), 'status': {'delay': 2}})()
        controller = lobby_client.LobbyController(library=None)
        controller.attach(worker)
        controller.model.apply({'event': 'launch_request', 'tier': 'rollback', 'prediction': 5})
        self.assertEqual(controller.link()['delay'], 2)
        threads = [threading.Thread(target=controller.close) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)
        controller.close()
        self.assertEqual(calls, ['close_room', 'cleanup'])


if __name__ == '__main__':
    unittest.main()
