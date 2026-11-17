"""The seat mapper and input sharing, pure: no socket, no process, no ROM, no window and no clock.

`retrorecomp/netplay/seat_map.py` is a function of the confirmed frame's records; these tests hold its rules (the OR-merge and the
opposite directions, the turns and the token, a change taking effect on a confirmed frame and never before, a request that
only the right seat can make), that every PC computes the same ports, the handhelds' rule, the mode in the launch settings and
in the lobby, and the hello check of a shared match. The same mapper under real games is in
tools/netplay_lockstep_selftest.py (the scenarios `shared-*`, run by tests/test_netplay_lockstep.py)."""
import random
import unittest

from retrorecomp.netplay import control, launch, lobby, lobby_check, seat_map, session_pipe as pipe
from retrorecomp.netplay.lockstep import LockstepDriver, Settings
from retrorecomp.netplay.seat_map import (PER_PLAYER, SHARED_ALL, SHARED_TURNS, SYS_PASS, SYS_PAUSE, SYS_SET_ALL, SYS_SET_TURNS,
                                          SYS_TO_SHIFT)
from tests.test_netplay_lobby import game

LEFT, RIGHT, UP, DOWN = 1, 2, 4, 8        # any bits will do: the mapper is told which are opposite
OPPOSITES = ((LEFT, RIGHT), (UP, DOWN))


def to(seat: int) -> int:
    return (seat + 1) << SYS_TO_SHIFT


def run(sharing, frames, seats, opposites=()):
    """The words of every frame of a stream of records (`frames[i]` the (word, system) of each seat of frame i), and the tokens
    and modes in force at each of them."""
    state, words, tokens = seat_map.start(sharing, seats), [], []
    for records in frames:
        tokens.append((state.sharing, state.token))
        mapped, state = seat_map.step(state, records, opposites)
        words.append(mapped)
    return words, tokens


class MapperRules(unittest.TestCase):
    def test_one_controller_per_player_is_the_seats_words_and_nothing_else(self):
        state = seat_map.start(PER_PLAYER, 3)
        # every control bit is only a bit of the system word here: nothing a seat asks for changes a per-player match
        frames = [((1, 0), (2, SYS_PASS | to(2)), (4, SYS_SET_TURNS)), ((0xffff, SYS_PAUSE), (0, 0), (7, SYS_PASS))]
        for records in frames:
            words, after = seat_map.step(state, records)
            self.assertEqual(words, tuple(word for word, _ in records))
            self.assertEqual(after, state)
        self.assertEqual(seat_map.ports(PER_PLAYER, 3), 3)

    def test_everyone_is_the_or_of_all_the_seats_on_one_port(self):
        words, _ = run(SHARED_ALL, [((0x01, 0), (0x10, 0), (0x100, 0)), ((0, 0), (0, 0), (0, 0)), ((0xf0f0, 0), (0x0f0f, 0), (0, 0))], 3)
        self.assertEqual(words, [(0x111,), (0,), (0xffff,)])
        self.assertEqual(seat_map.ports(SHARED_ALL, 3), 1)
        self.assertEqual(seat_map.ports(SHARED_TURNS, 4), 1)

    def test_opposite_directions_held_together_are_cancelled_and_nothing_else(self):
        # one player holds left, another right: neither (no pad can make both); up with down the same; the buttons stay
        records = ((LEFT | 0x40, 0), (RIGHT | 0x80, 0), (UP, 0))
        self.assertEqual(run(SHARED_ALL, [records], 3, OPPOSITES)[0], [(0x40 | 0x80 | UP,)])
        both = ((LEFT | UP, 0), (RIGHT | DOWN, 0))
        self.assertEqual(run(SHARED_ALL, [both], 2, OPPOSITES)[0], [(0,)])
        alone = ((LEFT | DOWN | 1 << 12, 0), (0, 0))
        self.assertEqual(run(SHARED_ALL, [alone], 2, OPPOSITES)[0], [(LEFT | DOWN | 1 << 12,)])
        # with no pairs given the mapper only merges (the host kit cleans every word it is given, the same on every PC)
        self.assertEqual(run(SHARED_ALL, [records], 3)[0], [(LEFT | RIGHT | UP | 0xc0,)])
        self.assertEqual(seat_map.merge([LEFT, RIGHT], OPPOSITES), 0)
        self.assertEqual(seat_map.merge([0xffff], OPPOSITES), 0xffff & ~(LEFT | RIGHT | UP | DOWN))

    def test_turns_give_port_0_the_holders_word_only_and_the_host_starts(self):
        records = ((0x01, 0), (0x02, 0), (0x04, 0))
        state = seat_map.start(SHARED_TURNS, 3)
        self.assertEqual(state.token, 0)
        self.assertEqual(seat_map.step(state, records)[0], (0x01,))
        for holder in range(3):
            self.assertEqual(seat_map.step(state._replace(token=holder), records)[0], (1 << holder,))
        self.assertEqual(seat_map.step(state._replace(token=3), records)[0], (0x01,))      # a token that is no seat is the host's

    def test_the_holder_passes_to_the_next_seat_in_order_and_it_wraps_from_the_following_frame(self):
        frames = [((0x01, 0), (0x02, 0), (0x04, 0)),
                  ((0x01, SYS_PASS), (0x02, 0), (0x04, 0)),        # the host passes: this frame is still his
                  ((0x01, 0), (0x02, 0), (0x04, 0)),               # seat 1 from here
                  ((0x01, 0), (0x02, SYS_PASS), (0x04, 0)),
                  ((0x01, 0), (0x02, 0), (0x04, 0)),               # seat 2
                  ((0x01, 0), (0x02, 0), (0x04, SYS_PASS)),
                  ((0x01, 0), (0x02, 0), (0x04, 0))]               # back to the host
        words, tokens = run(SHARED_TURNS, frames, 3)
        self.assertEqual([token for _mode, token in tokens], [0, 0, 1, 1, 2, 2, 0])
        self.assertEqual(words, [(0x01,), (0x01,), (0x02,), (0x02,), (0x04,), (0x04,), (0x01,)])

    def test_a_request_counts_on_its_rising_edge_only(self):
        # both seats keep their pass pressed: the host's press passes the turn once; seat 1, now the holder, has had its bit down since
        # the first frame, so its held bit is no new request; only after both let go does a new press count (seat 1's, to seat 0)
        down, up = ((1, SYS_PASS), (2, SYS_PASS)), ((1, 0), (2, 0))
        _words, tokens = run(SHARED_TURNS, [down] * 5 + [up, down, up], 2)
        self.assertEqual([token for _mode, token in tokens], [0, 1, 1, 1, 1, 1, 1, 0])

    def test_only_the_holder_and_the_host_can_move_the_token(self):
        nothing = (0, 0)
        # seat 2 passes while seat 0 holds: nothing; seat 1 gives a token to seat 2 with a target: nothing (a guest has no target)
        frames = [(nothing, nothing, (0, SYS_PASS)), (nothing, (0, SYS_PASS | to(2)), nothing), (nothing, (0, SYS_PASS), nothing), (nothing,) * 3]
        _words, tokens = run(SHARED_TURNS, frames, 3)
        self.assertEqual({token for _mode, token in tokens}, {0})
        # the host gives it to any seat, whoever holds it, and a target outside the match gives nothing
        frames = [((0, SYS_PASS | to(2)), nothing, nothing), (nothing,) * 3, ((0, SYS_PASS | to(1)), nothing, nothing), (nothing,) * 3,
                  ((0, SYS_PASS | to(3)), nothing, nothing), (nothing,) * 3]
        _words, tokens = run(SHARED_TURNS, frames, 3)
        self.assertEqual([token for _mode, token in tokens], [0, 2, 2, 1, 1, 1])        # the last give names seat 4: nothing
        # the host holding the token passes it with no target like any holder; the host who does not hold it and names nobody does nothing
        _words, tokens = run(SHARED_TURNS, [((0, SYS_PASS), nothing, nothing), (nothing,) * 3], 3)
        self.assertEqual(tokens[1][1], 1)
        state = seat_map.start(SHARED_TURNS, 3)._replace(token=1)
        self.assertEqual(seat_map.step(state, ((0, SYS_PASS), nothing, nothing))[1].token, 1)
        # the host's give wins over the holder's own pass in the same frame (seat 1 holds: its pass alone would go to seat 2)
        self.assertEqual(seat_map.step(state, ((0, SYS_PASS | to(0)), (0, SYS_PASS), nothing))[1].token, 0)
        self.assertEqual(seat_map.step(state, (nothing, (0, SYS_PASS), nothing))[1].token, 2)

    def test_the_host_moves_a_shared_match_between_everyone_and_turns_and_nobody_else_can(self):
        nothing = (0, 0)
        rec = ((1, 0), (2, 0), (4, 0))
        frames = [rec, ((1, SYS_SET_TURNS), (2, SYS_SET_ALL), (4, SYS_SET_TURNS)), rec, rec,
                  ((1, SYS_SET_ALL | SYS_SET_TURNS), nothing, nothing), rec,       # both at once: neither
                  ((1, SYS_SET_ALL), nothing, nothing), rec]
        words, tokens = run(SHARED_ALL, frames, 3)
        self.assertEqual([mode for mode, _token in tokens], [SHARED_ALL, SHARED_ALL, SHARED_TURNS, SHARED_TURNS, SHARED_TURNS,
                                                              SHARED_TURNS, SHARED_TURNS, SHARED_ALL])
        self.assertEqual(words[1], (7,))          # the frame that asks is still mapped as it was
        self.assertEqual(words[2], (1,))          # then only the holder (the host), who is seat 0
        self.assertEqual(words[7], (7,))
        # the same bits in a per-player match change nothing at all
        words, tokens = run(PER_PLAYER, frames, 3)
        self.assertEqual({mode for mode, _token in tokens}, {PER_PLAYER})

    def test_a_change_decided_by_frame_f_is_in_force_from_f_plus_one_and_never_earlier(self):
        rng = random.Random(7)
        for _ in range(50):
            frames = [tuple((rng.getrandbits(8), rng.choice((0, 0, 0, SYS_PASS, SYS_PASS | to(rng.randrange(4)), SYS_SET_ALL,
                                                             SYS_SET_TURNS, SYS_PAUSE))) for _seat in range(3)) for _frame in range(40)]
            words, tokens = run(SHARED_TURNS, frames, 3)
            for frame in range(40):
                # an independent look at the same stream: the mode and token of frame F depend on frames before F only
                again, earlier = run(SHARED_TURNS, frames[:frame] + [frames[frame]], 3)
                self.assertEqual(again[frame], words[frame])
                self.assertEqual(earlier[frame], tokens[frame])
                altered = [records if index < frame else tuple((word ^ 0xff, system ^ 0x7f03) for word, system in records)
                           for index, records in enumerate(frames[:40])]
                self.assertEqual(run(SHARED_TURNS, altered, 3)[1][frame], tokens[frame])      # later frames never reach back

    def test_every_pc_computes_the_same_ports(self):
        # three PCs hold the same confirmed records however they arrived; each runs its own mapper frame by frame
        rng = random.Random(11)
        for sharing in (PER_PLAYER, SHARED_ALL, SHARED_TURNS):
            for seats in (2, 3, 4):
                frames = [tuple((rng.getrandbits(16), rng.choice((0, 0, SYS_PASS, SYS_PASS | to(rng.randrange(seats)), SYS_SET_ALL,
                                                                  SYS_SET_TURNS, SYS_PAUSE))) for _seat in range(seats))
                          for _frame in range(200)]
                runs = [run(sharing, frames, seats, OPPOSITES) for _pc in range(3)]
                self.assertEqual(runs[0], runs[1])
                self.assertEqual(runs[1], runs[2])
                self.assertEqual(len(runs[0][0][0]), seat_map.ports(sharing, seats))

    def test_the_request_a_worker_makes_means_something_only_where_it_can(self):
        self.assertEqual(seat_map.request(PER_PLAYER, 0), 0)
        self.assertEqual(seat_map.request(SHARED_TURNS, 1), SYS_PASS)
        self.assertEqual(seat_map.request(SHARED_TURNS, 0, target=2), SYS_PASS | to(2))
        self.assertEqual(seat_map.request(SHARED_TURNS, 1, target=2), 0)                  # a guest has no target
        self.assertEqual(seat_map.request(SHARED_TURNS, 0, target=4), 0)
        self.assertEqual(seat_map.request(SHARED_ALL, 0, mode=SHARED_TURNS), SYS_SET_TURNS)
        self.assertEqual(seat_map.request(SHARED_TURNS, 0, mode=SHARED_ALL), SYS_SET_ALL)
        self.assertEqual(seat_map.request(SHARED_ALL, 1, mode=SHARED_TURNS), 0)
        self.assertEqual(seat_map.request(SHARED_ALL, 0, mode=PER_PLAYER), 0)
        self.assertEqual(seat_map.request(SHARED_ALL, 0, mode=-1), 0)

    def test_a_driver_hands_the_game_pause_only_and_the_workers_request_rides_one_record(self):
        class NoGame:
            def attach(self, _sink):
                pass
        driver = LockstepDriver(NoGame(), type('Link', (), {'open': lambda self, sink: None, 'send': lambda self, *a: None})(),
                                Settings(seat=0, seats=3, delay=2, sharing=SHARED_TURNS))
        self.assertEqual(driver.snapshot()['sharing'], 'turns')
        self.assertEqual(driver.snapshot()['token'], 0)
        driver._phase, driver._holding = 'play', False
        driver._set_delay(2, 0.0)
        driver._holding = False
        driver._ask(seat_map.request(SHARED_TURNS, 0, target=1))
        # a game that sets every system bit gets its pause through and nothing else; the worker's request is added once
        driver._local(0, 5, 0xffff)
        driver._local(1, 5, 0xffff)
        self.assertEqual(driver._records[0][2], (5, SYS_PAUSE | SYS_PASS | to(1)))
        self.assertEqual(driver._records[0][3], (5, SYS_PAUSE))
        self.assertEqual(driver.stats['requests_refused'], 0)                             # the host may name a seat
        host_guest = LockstepDriver(NoGame(), type('Link', (), {'open': lambda self, sink: None, 'send': lambda self, *a: None})(),
                                    Settings(seat=1, seats=3, delay=2, sharing=SHARED_TURNS))
        host_guest._ask(seat_map.request(SHARED_TURNS, 1, target=2))
        self.assertEqual(host_guest.stats['requests_refused'], 1)
        with self.assertRaises(ValueError):
            LockstepDriver(NoGame(), None, Settings(seat=0, seats=2, delay=2, sharing=3))


class HandheldsAndSeats(unittest.TestCase):
    def test_a_handheld_plays_in_input_sharing_only(self):
        for machine in ('gb', 'gba', 'gg'):
            self.assertTrue(seat_map.forced(machine))
            self.assertEqual(seat_map.effective(machine, PER_PLAYER), SHARED_ALL)
            self.assertEqual(seat_map.effective(machine, SHARED_TURNS), SHARED_TURNS)
            self.assertFalse(seat_map.allowed(machine, PER_PLAYER))
            self.assertTrue(seat_map.allowed(machine, SHARED_ALL) and seat_map.allowed(machine, SHARED_TURNS))
        for machine in (None, 'nes', 'md', 'sms', 'cps1', 'scummvm'):
            self.assertFalse(seat_map.forced(machine))
            self.assertEqual(seat_map.effective(machine, PER_PLAYER), PER_PLAYER)
            self.assertTrue(seat_map.allowed(machine, PER_PLAYER))
        self.assertFalse(seat_map.allowed('nes', 3) or seat_map.allowed('nes', True) or seat_map.allowed('nes', '1'))

    def test_the_handhelds_are_the_machines_with_one_player_and_a_pad(self):
        self.assertEqual(seat_map.HANDHELDS, {machine for machine, seats in lobby_check.MACHINE_SEATS.items() if seats == 1} - {'scummvm'})

    def test_input_sharing_seats_up_to_four_whatever_the_machine_has_and_one_controller_per_player_only_the_players(self):
        for players in (1, 2, 3, 4):
            self.assertEqual(seat_map.seat_limit(players, PER_PLAYER), players)
            self.assertEqual(seat_map.seat_limit(players, SHARED_ALL), 4)
            self.assertEqual(seat_map.seat_limit(players, SHARED_TURNS), 4)

    def test_the_cps_boards_say_four_as_a_ceiling_and_their_report_or_hello_says_their_own_number(self):
        self.assertEqual(lobby_check.MACHINE_SEATS['cps1'], 4)
        self.assertEqual(lobby_check.MACHINE_SEATS['cps2'], 4)
        report = {'system': {'id': 'cps1'}, 'qualification_scope': {'controls': 'players 1 to 3: joystick, up to six buttons, Start, coin; '
                                                                               'validation routes drive players 1 and 2'}}
        self.assertEqual(lobby_check.players_in_report(report), 3)
        report['qualification_scope']['controls'] = 'players 1 to 2: joystick'
        self.assertEqual(lobby_check.players_in_report(report), 2)
        report['qualification_scope']['controls'] = 'players 1 to 4: joystick'
        self.assertEqual(lobby_check.players_in_report(report), 4)
        for broken in ({}, {'system': {'id': 'cps1'}}, {'system': {'id': 'cps1'}, 'qualification_scope': {'controls': 'a stick'}},
                       {'system': {'id': 'cps1'}, 'qualification_scope': {'controls': 'players 1 to 9'}},
                       {'system': {'id': 'nes'}, 'qualification_scope': {'controls': 'players 1 to 4'}}, None, 'text'):
            self.assertIsNone(lobby_check.players_in_report(broken))

    def test_the_hello_is_checked_against_the_game_s_players_unless_the_match_shares(self):
        import struct

        def hello(players):
            return pipe.parse_hello(struct.pack('<HBBIIB', pipe.ABI, players, pipe.CAP_DIGEST, 0, 60000, 3) + b'GB ')
        pipe.check_hello(hello(2), 2)
        pipe.check_hello(hello(4), 4)
        with self.assertRaisesRegex(pipe.Refused, '3 seats asked, the game has 2'):
            pipe.check_hello(hello(2), 3)
        for seats in (1, 2, 3, 4):                                  # a handheld has one player: four seats share its controls
            pipe.check_hello(hello(1), seats, shared=True)
        with self.assertRaisesRegex(pipe.Refused, 'seats'):
            pipe.check_hello(hello(1), 5, shared=True)
        with self.assertRaisesRegex(pipe.Refused, 'pointer'):       # a pointer is not shared by OR-merging: still refused
            pipe.check_hello(pipe.parse_hello(struct.pack('<HBBIIB', pipe.ABI, 2, pipe.CAP_DIGEST | pipe.CAP_POINTER, 0, 60000, 0)),
                             2, shared=True)


class LaunchSettings(unittest.TestCase):
    MESSAGE = dict(seat=1, seats=3, names=['a', 'b', 'c'], delay=2, digest_every=60, redundancy=3, options='')

    def test_the_mode_is_a_setting_of_the_launch_and_only_the_three_that_exist(self):
        settings = launch.launch_settings(dict(self.MESSAGE))
        self.assertEqual(settings.sharing, PER_PLAYER)
        for sharing in (PER_PLAYER, SHARED_ALL, SHARED_TURNS):
            self.assertEqual(launch.launch_settings({**self.MESSAGE, 'sharing': sharing}, machine='nes').sharing, sharing)
        for wrong in (3, -1, True, 1.0, '1', None, [1]):
            self.assertIsInstance(launch.launch_settings({**self.MESSAGE, 'sharing': wrong}), launch.Refusal, wrong)

    def test_a_handheld_is_never_launched_one_controller_per_player_by_either_end(self):
        for machine in ('gb', 'gba', 'gg'):
            refusal = launch.launch_settings({**self.MESSAGE, 'sharing': PER_PLAYER}, machine=machine)
            self.assertIsInstance(refusal, launch.Refusal)
            self.assertIn('input sharing only', refusal.reason)
            self.assertEqual(launch.launch_settings({**self.MESSAGE, 'sharing': SHARED_ALL}, machine=machine).sharing, SHARED_ALL)
        # a caller that does not say the machine is not asked about it (the host's own values are checked with it)
        self.assertEqual(launch.launch_settings({**self.MESSAGE, 'sharing': PER_PLAYER}).sharing, PER_PLAYER)

    def test_the_mode_is_on_the_wire_and_a_mode_that_does_not_exist_is_refused_by_the_decoder(self):
        launch_message = control.Launch(1, 1, 3, 2, 60, 3, 'gb', bytes(32), bytes(32), ('a', 'b', 'c'), '', SHARED_TURNS)
        kind, payload = control.encode(launch_message)
        self.assertEqual(control.decode(kind, payload), launch_message)
        self.assertEqual(control.decode(kind, payload).sharing, SHARED_TURNS)
        self.assertEqual(payload[10], SHARED_TURNS)
        for wrong in (3, 255):
            with self.assertRaises(control.FrameError):
                control.decode(kind, payload[:10] + bytes([wrong]) + payload[11:])
        with self.assertRaises(ValueError):
            control.encode(control.Launch(1, 1, 3, 2, 60, 3, 'gb', bytes(32), bytes(32), ('a', 'b', 'c'), '', 3))
        roster = control.Roster(1, control.PHASE_LOBBY, 4, 1, (control.Player(0, 'a'), control.Player(1, 'b')), SHARED_ALL)
        kind, payload = control.encode(roster)
        self.assertEqual(control.decode(kind, payload), roster)
        with self.assertRaises(control.FrameError):
            control.decode(kind, payload[:5] + b'\x03' + payload[6:])
        with self.assertRaises(ValueError):
            control.encode(control.Roster(1, control.PHASE_LOBBY, 4, 1, (control.Player(0, 'a'),), 3))


class LobbyChoice(unittest.TestCase):
    def setUp(self):
        self.lobby = lobby.HostLobby('Arthur')
        for guest, name in ((1, 'Nadia'), (2, 'Karl'), (3, 'Zoe')):
            self.lobby.joined(guest, name, 0.0)

    def answer_all(self, same=(1, 2, 3)):
        for guest in same:
            self.lobby.on_message(guest, control.Answer(self.lobby.ident, control.CHECK_SAME, 0, (1, 7, 9)), 1.0)

    def test_the_host_chooses_the_mode_and_the_roster_says_it_to_everyone(self):
        self.assertEqual(self.lobby.sharing, PER_PLAYER)
        self.assertIsNone(self.lobby.set_sharing(SHARED_TURNS))
        self.assertEqual(self.lobby.roster().sharing, SHARED_TURNS)
        self.assertEqual(lobby.roster_dict(self.lobby.roster())['sharing'], 'turns')
        self.assertIsInstance(self.lobby.set_sharing(5), lobby.Refusal)
        self.assertIsInstance(self.lobby.set_sharing(True), lobby.Refusal)
        self.assertEqual(lobby.HostLobby('a', 4, SHARED_ALL).sharing, SHARED_ALL)      # chosen when the room is created
        with self.assertRaises(ValueError):
            lobby.HostLobby('a', 4, 3)

    def test_a_change_of_mode_is_a_roster_change_and_asks_nobody_again(self):
        self.lobby.select(game(), 0.0)
        self.answer_all()
        revision = self.lobby.revision
        self.assertIsNone(self.lobby.set_sharing(SHARED_ALL))
        self.assertNotEqual(self.lobby.revision, revision)
        self.assertEqual({self.lobby.member_status(guest)['check'] for guest in (1, 2, 3)}, {'same'})
        revision = self.lobby.revision
        self.assertIsNone(self.lobby.set_sharing(SHARED_ALL))                      # the same mode again: no change at all
        self.assertEqual(self.lobby.revision, revision)

    def test_the_mode_cannot_change_while_a_match_starts_or_runs(self):
        self.lobby.select(game(), 0.0)
        self.answer_all()
        plan = self.lobby.plan_launch()
        self.lobby.begin(plan.guests, 1)
        self.assertIsInstance(self.lobby.set_sharing(SHARED_ALL), lobby.Refusal)
        self.lobby.finished(1, 'ended')
        self.assertIsNone(self.lobby.set_sharing(SHARED_ALL))

    def test_one_controller_per_player_seats_the_games_players_and_sharing_seats_up_to_four(self):
        self.lobby.select(game(seats_max=2), 0.0)
        self.answer_all()
        self.assertEqual(self.lobby.roster().seats_max, 2)
        plan = self.lobby.plan_launch()
        self.assertEqual((plan.guests, plan.sharing), ((1,), PER_PLAYER))
        self.assertEqual([item[2] for item in plan.left_out], ['the game has no more seats'] * 2)
        self.lobby.set_sharing(SHARED_ALL)
        self.assertEqual(self.lobby.roster().seats_max, 4)
        plan = self.lobby.plan_launch()
        self.assertEqual((plan.guests, plan.left_out, plan.sharing), ((1, 2, 3), (), SHARED_ALL))
        self.lobby.set_sharing(SHARED_TURNS)
        self.assertEqual(self.lobby.plan_launch().sharing, SHARED_TURNS)
        self.lobby.set_sharing(PER_PLAYER)
        self.lobby.select(game(seats_max=4, machine='cps1'), 0.0)         # a four-player board seats four
        self.answer_all()
        self.assertEqual(self.lobby.plan_launch().guests, (1, 2, 3))

    def test_a_handheld_game_is_played_in_input_sharing_whatever_the_host_chose_and_can_be_picked_with_one_player(self):
        handheld = game(machine='gb', seats_max=1, title='Tetris')
        self.assertIsInstance(HostPick.refused(lobby.HostLobby('a'), game(machine='nes', seats_max=1)), lobby.Refusal)    # not a handheld
        self.assertEqual(self.lobby.sharing, PER_PLAYER)
        actions, refusal = self.lobby.select(handheld, 0.0)
        self.assertIsNone(refusal)
        self.assertEqual(self.lobby.sharing, SHARED_ALL)                           # in force, though the host's own choice is unchanged
        self.assertEqual(self.lobby.chosen, PER_PLAYER)
        self.assertEqual(self.lobby.roster().sharing, SHARED_ALL)
        self.assertEqual(self.lobby.roster().seats_max, 4)
        self.assertIsInstance(self.lobby.set_sharing(PER_PLAYER), lobby.Refusal)   # and it cannot be set back
        self.assertIsNone(self.lobby.set_sharing(SHARED_TURNS))                    # a shared mode is the host's to choose
        self.answer_all()
        plan = self.lobby.plan_launch()
        self.assertEqual((plan.guests, plan.sharing), ((1, 2, 3), SHARED_TURNS))
        # the host's choice comes back when a game that is not a handheld's is picked
        self.lobby.set_sharing(SHARED_ALL)
        self.lobby.select(game(), 0.0)
        self.assertEqual(self.lobby.sharing, SHARED_ALL)
        lobby2 = lobby.HostLobby('b')
        lobby2.select(handheld, 0.0)
        lobby2.select(game(), 0.0)
        self.assertEqual(lobby2.sharing, PER_PLAYER)

    def test_the_launch_event_and_the_model_say_the_mode(self):
        self.lobby.select(game(), 0.0)
        self.answer_all()
        self.lobby.set_sharing(SHARED_ALL)
        plan = self.lobby.plan_launch()
        events = [action.data for action in self.lobby.begin(plan.guests, 1) if isinstance(action, lobby.Event)]
        self.assertEqual(events[0]['sharing'], 'everyone')
        from retrorecomp.netplay.lobby_client import LobbyModel
        model = LobbyModel()
        model.apply(lobby.roster_dict(self.lobby.roster()))
        self.assertEqual((model.sharing, model.seats_max), ('everyone', 4))
        model.apply(events[0])
        self.assertEqual(model.last_launch['sharing'], 'everyone')

    def test_every_machine_a_room_can_pick_has_a_rule_and_the_handhelds_are_hostable(self):
        self.assertTrue(set(seat_map.HANDHELDS) <= set(lobby_check.MACHINE_SEATS))


class HostPick:
    @staticmethod
    def refused(host, picked):
        return host.select(picked, 0.0)[1]


if __name__ == '__main__':
    unittest.main()
