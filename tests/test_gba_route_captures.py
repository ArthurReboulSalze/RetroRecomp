"""tools/gba_route_captures.py against a fake player: authored bytes only, no ROM, no BIOS, no compiler."""
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import gba_fresh_process as base  # noqa: E402
import gba_route_captures as tool  # noqa: E402


def ppm(value: int) -> bytes:
    return b'P6\n4 2\n255\n' + bytes([value]) * 24


class FakePlayer:
    """Writes the picture of every frame it was asked for (its colour is the frame number unless `still`), then the last picture and its stats line."""

    def __init__(self, still=False, skip=None, code=0):
        self.still, self.skip, self.code = still, skip, code
        self.environments = []

    def __call__(self, command, cwd, env, **kwargs):
        self.environments.append(env)
        frames = int(env['RETRORECOMP_HOST_TEST_FRAMES'])
        shots = [int(item) for item in env.get('RETRORECOMP_GBA_SHOTS', '').split(',') if item]
        folder = Path(env['RETRORECOMP_GBA_SHOT_DIR'])
        for frame in shots:
            if frame != self.skip:
                (folder / f'shot-{frame}.ppm').write_bytes(ppm(7 if self.still else frame % 251))
        Path(env['RETRORECOMP_GBA_DUMP']).write_bytes(ppm(1))

        class Done:
            returncode = self.code
            stdout = ''
            stderr = f'[host] frames={frames} audio_samples=0 audio_nonzero=0 audio_peak=0 interpreted=5\n'
        return Done()


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.exe = self.root / 'Game.exe'
        self.exe.write_bytes(b'MZ authored bytes')
        self.keys = self.root / 'route.keys'
        self.keys.write_text(base.key_script_text([(5, 8), (9, 0)]), encoding='ascii')

    def run_tool(self, fake, frames=240, shots=12):
        with unittest.mock.patch.object(base.subprocess, 'run', fake):
            return tool.run_captures(self.exe, self.root / 'work', self.keys, frames, shots, 60)

    def test_the_shots_are_spread_over_the_route_and_the_last_one_is_its_last_frame(self):
        self.assertEqual(tool.shot_frames(240, 12), list(range(20, 241, 20)))
        self.assertEqual(tool.shot_frames(5, 12), [1, 2, 3, 4, 5])
        with self.assertRaises(base.CheckError):
            tool.shot_frames(0, 12)

    def test_a_route_gives_twelve_pictures_a_contact_sheet_and_a_report(self):
        fake = FakePlayer()
        report = self.run_tool(fake)
        result = report['result']
        self.assertEqual(result['verdict'], 'pass', result)
        self.assertEqual((len(result['shots']), result['different_pictures'], result['interpreted_instructions']), (12, 12, 5))
        self.assertEqual(fake.environments[0]['RETRORECOMP_GBA_SHOTS'], ','.join(str(frame) for frame in range(20, 241, 20)))
        sheet = Path(result['contact_sheet'])
        self.assertEqual(sheet.read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        self.assertIsNone(result['read_by'])                       # a person reads the sheet; the report does not claim it
        self.assertTrue((self.root / 'work' / 'captures' / 'game.exe').is_file())
        json.dumps(report)

    def test_a_route_that_stands_still_a_missing_picture_and_a_failed_player_are_reported(self):
        self.assertEqual(self.run_tool(FakePlayer(still=True))['result']['verdict'], 'error')
        report = self.run_tool(FakePlayer(skip=240))
        self.assertIn('no picture at frames [240]', report['result']['problems'][0])
        self.assertIsNone(report['result']['contact_sheet'])
        self.assertEqual(self.run_tool(FakePlayer(code=3))['result']['verdict'], 'error')

    def test_the_contact_sheet_lays_the_pictures_in_rows(self):
        paths = []
        for number in range(5):
            path = self.root / f'p{number}.ppm'
            path.write_bytes(ppm(number * 10))
            paths.append(path)
        width, height, rgb = tool.contact_sheet(paths, columns=4)
        self.assertEqual((width, height, len(rgb)), (16, 4, 16 * 4 * 3))
        self.assertEqual(rgb[0], 0)                                   # the first picture, top left
        self.assertEqual(rgb[(2 * 16 + 0) * 3], 40)                   # the fifth, second row, first column
        self.assertEqual(rgb[(0 * 16 + 4) * 3], 10)                   # the second, next to the first


if __name__ == '__main__':
    unittest.main()
