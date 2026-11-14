"""A route the game ends itself (its own Quit) is a valid reference when it ran long enough; any other stop is a failure."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from retrorecomp import amiga_conversion as conversion
from retrorecomp.core import ConversionError


def fake_player(report):
    """A `spawn` that leaves the report a real player would write and exits as it does (2 when the install stopped)."""
    def spawn(args, **kwargs):
        folder = Path(args[args.index('--report') + 1]).parent
        (folder / 'result.json').write_text(json.dumps(report), encoding='utf-8')
        return SimpleNamespace(returncode=2 if report.get('stopped') else 0)
    return spawn


class EndedRouteTests(unittest.TestCase):
    def run_route(self, report, *, frames=3000, game_may_quit=True):
        with tempfile.TemporaryDirectory() as folder, patch.object(conversion, 'spawn', fake_player(report)):
            return conversion.replay(Path('player'), Path(folder) / 'run', frames, Path('inputs.txt'), game_may_quit=game_may_quit)

    def test_a_game_that_quits_after_enough_frames_ends_its_route_there(self):
        report = self.run_route({'quit': True, 'stopped': True, 'frames': 1702, 'error': 'the game quit'})
        self.assertTrue(report['ended_by_game'])
        self.assertEqual(report['frames'], 1702)

    def test_a_quit_before_the_minimum_is_a_failure(self):
        with self.assertRaisesRegex(ConversionError, 'stopped at frame 400'):
            self.run_route({'quit': True, 'stopped': True, 'frames': 400, 'error': 'the game quit'})

    def test_any_other_stop_is_a_failure(self):
        with self.assertRaisesRegex(ConversionError, 'stopped at frame 2000'):
            self.run_route({'quit': False, 'stopped': True, 'frames': 2000, 'error': 'resload call refused'})

    def test_a_replay_that_may_not_quit_keeps_the_old_rule(self):
        with self.assertRaisesRegex(ConversionError, 'stopped at frame 1702'):
            self.run_route({'quit': True, 'stopped': True, 'frames': 1702, 'error': 'the game quit'}, game_may_quit=False)

    def test_a_complete_run_is_unchanged(self):
        report = self.run_route({'quit': False, 'stopped': False, 'frames': 3000, 'error': ''})
        self.assertNotIn('ended_by_game', report)


class KickstartAddressesTests(unittest.TestCase):
    """The Kickstart's addresses are kept, never its bytes; the words come from the player's own image when the steps are written."""
    IMAGE = bytes(range(256)) * 1024        # 256 KiB of authored bytes (no Kickstart)

    def test_the_words_are_read_from_the_image_in_its_window(self):
        samples = conversion.kick_samples({0xFC0002, 0xFFFFFE}, self.IMAGE)
        self.assertIn((0xFC0002, self.IMAGE[2:14].hex()), samples)
        self.assertIn((0xFFFFFE, self.IMAGE[-2:].hex()), samples)           # the end of the image gives a shorter sample

    def test_an_install_without_a_kickstart_has_no_kickstart_sample(self):
        self.assertEqual(conversion.kick_samples(set(), b''), set())      # no addresses, no image: the case of every install without one

    def test_an_image_of_an_odd_size_is_refused(self):
        with self.assertRaisesRegex(ConversionError, 'unexpected size'):
            conversion.kick_samples({0xFC0000}, b'\x00' * 1000)

    def test_a_run_observation_gives_the_words_as_they_stood_and_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'o.kick'
            path.write_text('fc0100 4e714e75\nfc0100 4ef900c0\n', encoding='ascii')       # the same address, patched by a slave
            self.assertEqual(conversion.read_kick_observation(path), {(0xFC0100, '4e714e75'), (0xFC0100, '4ef900c0')})
            for bad in ('fc0101 4e71\n', '001000 4e71\n', 'fc0100 4e7\n', 'fc0100 zz71\n'):
                path.write_text(bad, encoding='ascii')
                with self.assertRaises(ValueError):
                    conversion.read_kick_observation(path)

    def test_the_address_file_holds_numbers_only_and_is_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'o.kick'
            path.write_text('fc0100\nfc0102\n', encoding='ascii')
            self.assertEqual(conversion.read_kick_addresses(path), {0xFC0100, 0xFC0102})
            for bad in ('fc0101\n', '001000\n', 'f800d2\n', '1000000\n'):   # odd, in RAM, the authored boot ROM, past the window
                path.write_text(bad, encoding='ascii')
                with self.assertRaises(ValueError):
                    conversion.read_kick_addresses(path)


class RememberedDataTests(unittest.TestCase):
    """What the library remembers of an install (observations, Kickstart addresses) only ever helps: a file that is valid but wrong
    never stops a conversion. A conversion that fails after merging it is tried once more without it, as a fresh one."""
    def memory(self, folder, observations=None, addresses=None):
        memory = Path(folder)
        if observations is not None:
            (memory / conversion.OBSERVATIONS).write_text(observations, encoding='ascii')
        if addresses is not None:
            (memory / conversion.KICK_ADDRESSES).write_text(addresses, encoding='ascii')
        return memory

    def test_a_valid_but_wrong_file_is_read_as_it_stands_and_a_damaged_or_oversized_one_is_ignored(self):
        kick = SimpleNamespace()
        said = []
        with tempfile.TemporaryDirectory() as folder:
            wrong = self.memory(folder, '001000 4afc\n001002 ffff\n', 'fc0100\n')              # words no program runs, in the right places
            samples, addresses, ignored = conversion.load_remembered(wrong, kick, said.append)
            self.assertEqual((samples, addresses, ignored), ({(0x1000, '4afc'), (0x1002, 'ffff')}, {0xFC0100}, []))
            self.assertEqual(conversion.load_remembered(wrong, None, said.append)[1], set())      # no Kickstart: no address is merged
            self.memory(folder, 'not a line\n', 'fc0101\n')                                      # damaged: bad words, an odd address
            self.assertEqual(conversion.load_remembered(wrong, kick, said.append), (set(), set(), ['kickstart addresses', 'observations']))
            big = ''.join(f'{pc:06x} 4e71\n' for pc in range(0x1000, 0x1000 + 2 * 1048577, 2))   # valid lines, past the observation bound
            self.memory(folder, big, '')
            self.assertEqual(conversion.load_remembered(wrong, kick, said.append)[2], ['observations'])
        self.assertEqual(len(said), 3)                                                           # each ignored file was said

    def test_the_report_says_what_the_memory_added_and_why_it_was_dropped(self):
        self.assertEqual(conversion.remembered_report(0, 0, None), {'used': False, 'added_instructions': 0, 'added_kickstart_addresses': 0,
                                                                     'ignored_unreadable': [], 'dropped_after_failure': False})
        report = conversion.remembered_report(12, 3, 'diverged', ['observations'])
        self.assertEqual((report['used'], report['dropped_after_failure'], report['failure_with_remembered_data']), (True, True, 'diverged'))

    def run_convert(self, behaviour):
        calls, said = [], []

        def once(path, **options):
            calls.append(options)
            return behaviour(len(calls), options)
        with patch.object(conversion, '_convert_once', once):
            try:
                return conversion.convert(Path('game.lha'), emit=said.append, passes=1), calls, said
            except ConversionError as error:
                return error, calls, said

    def test_a_failure_after_the_memory_was_merged_is_tried_again_without_it(self):
        def behaviour(n, options):
            if n == 1:
                options['trace']['remembered_used'] = True
                raise ConversionError('Amiga main: the native game and the fresh reference diverged.')
            return Path('exported.exe')
        result, calls, said = self.run_convert(behaviour)
        self.assertEqual(result, Path('exported.exe'))
        self.assertEqual(len(calls), 2)
        self.assertNotIn('use_remembered', calls[0])                                             # the first call is the ordinary one
        self.assertFalse(calls[1]['use_remembered'])
        self.assertIn('diverged', calls[1]['dropped_reason'])
        self.assertEqual(calls[1]['passes'], 1)                                                  # the options of the first call, unchanged
        self.assertTrue(any('trying once more without them' in line for line in said))

    def test_a_failure_the_memory_did_not_touch_is_not_retried_and_a_second_failure_is_the_failure(self):
        def plain(n, options):
            raise ConversionError('the install stopped at frame 40')
        result, calls, _ = self.run_convert(plain)
        self.assertIsInstance(result, ConversionError)
        self.assertEqual(len(calls), 1)

        def both(n, options):
            if n == 1:
                options['trace']['remembered_used'] = True
            raise ConversionError(f'failure {n}')
        result, calls, _ = self.run_convert(both)
        self.assertEqual((len(calls), str(result)), (2, 'failure 2'))


if __name__ == '__main__':
    unittest.main()


class RouteScriptTests(unittest.TestCase):
    def test_the_main_route_presses_1_and_2_for_a_menu_of_choices_but_never_the_quit_key(self):
        keys = [(begin, code) for begin, _, kind, code, _ in conversion.main_route(3600, 0x59) if kind == 'key']
        self.assertIn((400, 0x01), keys)
        self.assertIn((1300, 0x02), keys)
        self.assertNotIn(0x02, [code for _, _, kind, code, _ in conversion.main_route(3600, 0x02) if kind == 'key'])

    def test_an_install_with_an_answer_answers_first_then_plays_the_generic_route_after_it(self):
        answer = conversion.ROUTE_ANSWERS['f9811f6041b178fa9669cb3508137ebd65ae7bc5eedc334f4f2591268a112596']
        route = conversion.answered_route(answer, 7000, 0x59)
        self.assertEqual(route[:1], [(1900, 1906, 'key', 0x44, 1)])
        self.assertTrue(set(answer['events']) <= set(route))
        later = [event for event in route if event not in answer['events']]
        self.assertTrue(later and min(begin for begin, *_ in later) >= answer['then'])
        self.assertTrue(max(end for _, end, *_ in route) <= 7000)

    def test_another_world_answers_its_wheel_with_the_joystick_and_its_routes_leave_the_mouse_out(self):
        answer = conversion.ROUTE_ANSWERS['87f9ecbba2c2ef98bb9cc806f58e60c3f4be0f99f218d356079c8369df7caf9b']
        route = conversion.answered_route(answer, 7000, 0x59)
        self.assertEqual([kind for _, _, kind, _, _ in answer['events']], ['joy'] * 24)        # three submissions, joystick only
        self.assertFalse([event for event in route if event[2] == 'mouse'])
        later = [event for event in route if event not in answer['events']]
        self.assertTrue(later and min(begin for begin, *_ in later) >= answer['then'])
        # A long or exploration route of the install starts with the same answer.
        long_ = conversion.answered_route(answer, 18000, 0x59, lambda n: conversion.long_route('x' * 64, 0, n, 0x59))
        self.assertTrue(set(answer['events']) <= set(long_))
        self.assertFalse([event for event in long_ if event[2] == 'mouse'])

    def test_lemmings_clicks_1_player_after_its_intro_then_plays_the_generic_route(self):
        answer = conversion.ROUTE_ANSWERS['37b8afa13b085e804015599e9f67833a9dbdcdbead90438f9a46a2a6aeda21c5']
        route = conversion.answered_route(answer, 7200, 0x59)
        self.assertEqual(min(begin for begin, *_ in route), 3600)                                 # nothing during the intro
        self.assertIn((3660, 3666, 'mouse', 2, 1), route)
        self.assertTrue(max(end for _, end, *_ in route) <= 7200)

    def test_a_known_stop_is_words_for_the_report_and_changes_no_route(self):
        mi2 = 'f9811f6041b178fa9669cb3508137ebd65ae7bc5eedc334f4f2591268a112596'
        words = conversion.route_stops(mi2)
        self.assertEqual(len(words), 1)
        self.assertTrue(words[0].startswith('known stop (panel of 13 November 2026): Monkey Island 2: '))
        self.assertEqual(conversion.route_stops('ab' * 32), [])
        self.assertEqual(conversion.route_events(mi2, 'long-1', 18000, 0x59),
                         conversion.answered_route(conversion.ROUTE_ANSWERS[mi2], 18000, 0x59, lambda n: conversion.long_route(mi2, 0, n, 0x59)))

    def test_route_events_is_the_one_writer_of_every_route_answered_or_not(self):
        lemmings = '37b8afa13b085e804015599e9f67833a9dbdcdbead90438f9a46a2a6aeda21c5'
        answer = conversion.ROUTE_ANSWERS[lemmings]
        self.assertEqual(conversion.route_events(lemmings, 'main', 7200, 0x59), conversion.answered_route(answer, 7200, 0x59))
        self.assertEqual(conversion.route_events(lemmings, 'explore', 7200, 0x59),
                         conversion.answered_route(answer, 7200, 0x59, lambda n: conversion.explore_route(n, 0x59)))
        self.assertEqual(conversion.route_events(lemmings, 'long-1', 18000, 0x59),
                         conversion.answered_route(answer, 18000, 0x59, lambda n: conversion.long_route(lemmings, 0, n, 0x59)))
        # Not answered: an install without an entry, or a qualification script in place of the main route.
        other = 'ab' * 32
        self.assertEqual(conversion.route_events(other, 'main', 3600, 0x59), conversion.main_route(3600, 0x59))
        self.assertEqual(conversion.route_events(other, 'explore', 3600, 0x59), conversion.explore_route(3600, 0x59))
        self.assertEqual(conversion.route_events(other, 'long-2', 18000, 0x59), conversion.long_route(other, 1, 18000, 0x59))
        self.assertEqual(conversion.route_events(lemmings, 'long-1', 18000, 0x59, answered=False), conversion.long_route(lemmings, 0, 18000, 0x59))
        with self.assertRaises(ValueError):
            conversion.route_events(other, 'mouse', 3600, 0x59)

    def test_the_route_pictures_replay_the_answered_route_and_refuse_a_script_of_another_revision(self):
        import hashlib
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
        import amiga_route_captures
        identity = '87f9ecbba2c2ef98bb9cc806f58e60c3f4be0f99f218d356079c8369df7caf9b'
        events = conversion.route_events(identity, 'main', 7000, 0x59)
        digest = hashlib.sha256(''.join(f'{b} {e} {k} {c} {v}\n' for b, e, k, c, v in events).encode('ascii')).hexdigest()
        report = {'whdload': {'key_exit': 0x59}, 'source_identity': identity, 'final_checks': [{'route': 'main', 'frames': 7000, 'script_sha256': digest}]}
        self.assertEqual(amiga_route_captures.plan(report), [('main', 7000, events)])
        report['final_checks'][0]['script_sha256'] = '0' * 64
        with self.assertRaises(SystemExit):
            amiga_route_captures.plan(report)

    def test_the_two_player_route_is_the_main_route_of_the_installs_listed_only(self):
        identity, other = 'c' * 64, 'd' * 64
        player2 = {'events': [(600, 608, 'joy', 4, 1), (1000, 4000, 'joy2', 4, 1), (5000, 5010, 'joy2', 3, 1)]}
        with unittest.mock.patch.dict(conversion.ROUTE_PLAYER2, {identity: player2}):
            main = conversion.route_events(identity, 'main', 3600, 0x59)
            self.assertEqual(main, [(600, 608, 'joy', 4, 1), (1000, 3600, 'joy2', 4, 1)])   # cut to the route, nothing after its end
            self.assertFalse([e for e in conversion.route_events(identity, 'explore', 3600, 0x59) if e[2] == 'joy2'])
            self.assertFalse([e for e in conversion.route_events(identity, 'main', 3600, 0x59, answered=False) if e[2] == 'joy2'])
            self.assertEqual(conversion.route_events(other, 'main', 3600, 0x59), conversion.main_route(3600, 0x59))
        lotus = conversion.ROUTE_PLAYER2['827a20e727a7825848febba8cf2afdc9fa94d73072b5865f303bacc917edbfb1']['events']
        self.assertTrue([e for e in lotus if e[2] == 'joy2'] and [e for e in lotus if e[2] == 'joy'])   # two players, both on the route
        self.assertTrue(all(kind in ('joy', 'joy2') and 0 <= code < 6 and begin < end for begin, end, kind, code, _ in lotus))
        # The player reads the kind (amiga_player.c: joy2, codes 0..5 as joy).
        player = (Path(conversion.__file__).parents[1] / 'native' / 'amiga_machine' / 'amiga_player.c').read_text(encoding='utf-8')
        self.assertIn('!strcmp(kind, "joy2") && code >= 0 && code < 6', player)

    def test_the_damaged_states_follow_the_players_header(self):
        # The offsets the conversion flips are the fields of StateHead in amiga_session.cpp (200 bytes, asserted there too).
        source = (Path(conversion.__file__).parents[1] / 'native' / 'amiga_machine' / 'amiga_session.cpp').read_text(encoding='utf-8')
        self.assertIn('char magic[16]; char abi[72]; char identity[72]; uint64_t frame; uint32_t joy, mouse_left, mouse_right, '
                      'snapshot_size, audio_size, port1; uint64_t checksum;', source)
        self.assertIn('sizeof(StateHead) == 200', source)
        self.assertIn('STATE_MAGIC[16] = "RRAMIGA-STATE-4"', source)
        self.assertEqual(conversion.STATE_HEADER, 200)
        self.assertEqual(conversion.STATE_OFFSETS['checksum'], 192)
        self.assertEqual(conversion.STATE_OFFSETS['port1'], 188)       # the device port 1 holds and the second joystick's bits
        state = bytes(range(256)) * 64
        damaged = conversion.damaged_states(state)
        self.assertTrue({'empty', 'one-byte-short', 'one-byte-longer', 'magic', 'abi', 'identity', 'checksum', 'payload', 'port1'} <= set(damaged))
        self.assertTrue(all(data != state for data in damaged.values()))

    def test_a_route_script_is_the_same_lf_bytes_on_every_system(self):
        # Windows and Linux runs of the same route compare their script_sha256 (G13): no CRLF from text mode.
        with tempfile.TemporaryDirectory() as folder:
            path = conversion.write_events(Path(folder) / 'inputs-main.txt', [(400, 406, 'key', 0x01, 1), (500, 900, 'joy', 0x40, 1)])
            self.assertEqual(path.read_bytes(), b'400 406 key 1 1\n500 900 joy 64 1\n')
