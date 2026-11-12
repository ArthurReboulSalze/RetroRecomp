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
