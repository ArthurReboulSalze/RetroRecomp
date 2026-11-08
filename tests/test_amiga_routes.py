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


if __name__ == '__main__':
    unittest.main()
