"""tools/startup_cost.py: the helpers of the start-up measurement (the measurement itself needs a quiet PC and is not run here)."""
import tempfile
import unittest
from pathlib import Path

from tools import startup_cost


class StartupCostTests(unittest.TestCase):
    def test_every_console_has_a_headless_command_and_an_unknown_one_is_refused(self):
        for machine in startup_cost.MACHINES:
            command = startup_cost.headless_command(machine, Path('game.exe'), Path('run'), 1)
            self.assertEqual(command[0], 'game.exe')
            self.assertIn('1', command)
        with self.assertRaises(SystemExit):
            startup_cost.headless_command('amiga', Path('game.exe'), Path('run'), 1)

    def test_only_unpacked_builds_of_a_known_console_are_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            build, packed = Path(folder) / 'a.exe', Path(folder) / 'b.exe'
            build.write_bytes(b'MZ build')
            packed.write_bytes(b'MZ UPX! packed')
            self.assertEqual(startup_cost.parse_games([f'gb:{build}']), [('a', 'gb', build)])
            for bad in (f'gb:{packed}', f'zz:{build}', f'gb:{folder}/missing.exe', 'gb'):
                with self.assertRaises(SystemExit):
                    startup_cost.parse_games([bad])

    def test_the_summary_is_in_milliseconds_with_median_and_spread(self):
        summary = startup_cost.summary([0.1, 0.3, 0.2])
        self.assertEqual((summary['median_ms'], summary['min_ms'], summary['max_ms'], summary['n']), (200.0, 100.0, 300.0, 3))
        self.assertEqual(startup_cost.summary([0.5])['stdev_ms'], 0.0)

    def test_the_method_constant_is_the_packing_modules(self):
        from retrorecomp import packing
        self.assertTrue(hasattr(packing, startup_cost.method_constant()))
        self.assertEqual(startup_cost.METHODS, tuple(packing.METHOD_FLAGS))


if __name__ == '__main__':
    unittest.main()
