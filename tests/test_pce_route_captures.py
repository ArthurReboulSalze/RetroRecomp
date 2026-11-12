"""tools/pce_route_captures.py on a synthetic report and synthetic pictures: no ROM, no game."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'pce_route_captures.py'
SPEC = importlib.util.spec_from_file_location('pce_route_captures', TOOL)
captures = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(captures)


def report(level='extended', presses=2, confirm=None):
    rows = [{'name': 'attract', 'frames': 3600}, {'name': 'play', 'frames': 3600}]
    if level != 'standard':
        rows.append({'name': 'long-1', 'frames': 18000})
    return {'rom': {'sha256': 'ab' * 32}, 'scan_level': level, 'route_start': {'run_presses': presses, 'confirm': confirm}, 'final_checks': rows}


class PlanTests(unittest.TestCase):
    def test_the_routes_are_those_the_report_lists(self):
        self.assertEqual(['attract', 'play', 'long-1'], [row[0] for row in captures.plan(report())])
        self.assertEqual(['attract', 'play'], [row[0] for row in captures.plan(report('standard'))])

    def test_the_route_is_the_conversions_own(self):
        from retrorecomp.pce_conversion import routes
        self.assertEqual(routes('ab' * 32, frames=3600, level='extended', presses=2), captures.plan(report()))

    def test_a_start_that_taps_i_is_replayed_as_the_conversion_played_it(self):
        from retrorecomp.pce_conversion import routes
        self.assertEqual(routes('ab' * 32, frames=3600, level='extended', presses=2, confirm=True), captures.plan(report(confirm='I')))
        self.assertNotEqual(captures.plan(report(confirm='I')), captures.plan(report()))

    def test_the_run_presses_of_the_report_are_used(self):
        one, two = captures.plan(report(presses=1)), captures.plan(report(presses=2))
        self.assertNotEqual(dict((n, s) for n, _, s in one)['play'], dict((n, s) for n, _, s in two)['play'])

    def test_the_spacing_gives_about_the_pictures_asked(self):
        self.assertEqual(1500, captures.spacing(18000, 12))
        self.assertEqual(300, captures.spacing(3600, 12))
        self.assertEqual(1, captures.spacing(5, 12))


class SheetTests(unittest.TestCase):
    def picture(self, folder, name, value):
        path = Path(folder) / name
        path.write_bytes(b'P6\n2 2\n255\n' + bytes([value]) * 12)
        return path

    def test_a_sheet_counts_the_distinct_pictures(self):
        with tempfile.TemporaryDirectory() as folder:
            pictures = [self.picture(folder, f'{n}.ppm', value) for n, value in enumerate((0, 0, 200, 90, 200))]
            target = Path(folder) / 'out' / 'sheet.png'
            self.assertEqual(3, captures.contact_sheet(pictures, target))
            self.assertTrue(target.is_file())

    def test_no_picture_writes_no_sheet(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'sheet.png'
            self.assertEqual(0, captures.contact_sheet([], target))
            self.assertFalse(target.exists())


if __name__ == '__main__':
    unittest.main()
