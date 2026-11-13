"""The pure parts of the Game Boy Advance fresh-process check (gates G6 and G7): key scripts, the player's test switch, picture and save
statistics, the verdicts and the report, plus the two checks run against a fake player (a patched subprocess). Authored data only: no
ROM, no executable, no picture of a game."""
import hashlib
import io
import json
import re
import sys
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import gba_fresh_process as tool  # noqa: E402


def ppm(colour: int, width: int = 4, height: int = 2) -> bytes:
    return f'P6\n{width} {height}\n255\n'.encode() + bytes([colour]) * (width * height * 3)


class FakeProcess:
    """Stands in for subprocess.run: a player whose picture is its frame count and the keys it was given, whose state file
    restores the frame count it was saved at, and whose save is written when the key script is named 'write'."""

    def __init__(self, restore_state=True, same_picture_without_state=False, write_save=True, old_player=False, refuse_damaged=True, create_on_missing=False):
        self.refuse_damaged = refuse_damaged
        self.create_on_missing = create_on_missing
        self.restore_state = restore_state
        self.same_picture_without_state = same_picture_without_state
        self.write_save = write_save
        self.old_player = old_player
        self.saved_frame = None
        self.calls = []

    def __call__(self, command, cwd, env, **kwargs):
        cwd = Path(cwd)
        frames = int(env['RETRORECOMP_HOST_TEST_FRAMES'])
        switch = env.get('RETRORECOMP_GBA_STATE', '')
        keys = Path(env['RETRORECOMP_GBA_INPUT']).name if 'RETRORECOMP_GBA_INPUT' in env else ''
        self.calls.append((switch, keys, frames))
        lines = []
        end = frames
        save = re.fullmatch(r'save@(\d+)', switch)
        load = re.fullmatch(r'load@(\d+)=(\d+)', switch)
        sav_file = cwd / 'datas' / 'saves' / 'game-0123.sav'
        known_save = sav_file.is_file()
        if save and not self.old_player:
            (cwd / 'datas' / 'states').mkdir(parents=True, exist_ok=True)
            (cwd / 'datas' / 'states' / 'game-0123.rrstate').write_bytes(b'state' * 100)
            self.saved_frame = int(save.group(1))
            lines.append(f'[state] save at frame {save.group(1)} ok')
        elif load and not self.old_player:
            at, resume = int(load.group(1)), int(load.group(2))
            state_file = cwd / 'datas' / 'states' / 'game-0123.rrstate'
            if not state_file.is_file():
                lines.append(f'[state] load at frame {at} FAILED')
                if self.create_on_missing:
                    state_file.parent.mkdir(parents=True, exist_ok=True)
                    state_file.write_bytes(b'')
            elif self.refuse_damaged and state_file.read_bytes() != b'state' * 100:
                lines.append('[host] quick state refused: snapshot: bad magic (not a GBAS file)')
                lines.append(f'[state] load at frame {at} FAILED')
            else:
                lines.append(f'[state] load at frame {at} ok')
                end = resume + (frames - at)       # the player counts from the saved frame whether or not the state restored
        colour = (end * 7 + sum(map(ord, keys))) % 251
        if load and not self.restore_state and not self.same_picture_without_state:
            colour = (colour + 99) % 251
        if self.same_picture_without_state:
            colour = 17
        (cwd / Path(env['RETRORECOMP_GBA_DUMP']).name).write_bytes(ppm(colour))
        if self.write_save and keys.startswith('write'):
            sav_file.parent.mkdir(parents=True, exist_ok=True)
            sav_file.write_bytes(bytes(range(256)) * 128)
        elif known_save is False and not (cwd / 'datas' / 'saves').exists():
            sav_file.parent.mkdir(parents=True, exist_ok=True)
            sav_file.write_bytes(b'\xff' * 32768)           # a game with no save starts from an erased file
        picture = colour
        if keys.startswith('show') and known_save:
            picture = (colour + 40) % 251                   # the file-select screen shows the saved slot
            (cwd / Path(env['RETRORECOMP_GBA_DUMP']).name).write_bytes(ppm(picture))
        lines.append(f'[host] frames={end} audio_samples=0 audio_nonzero=0 audio_peak=0 interpreted=0')

        class Done:
            returncode = 0
            stdout = ''
            stderr = '\n'.join(lines) + '\n'
        return Done()


class KeyScriptTest(unittest.TestCase):
    def test_active_low_and_a_release_at_frame_zero(self):
        text = tool.key_script_text([(10, 0x8), (14, 0)], 'what it reaches\nsecond line')
        self.assertEqual(text.splitlines()[:2], ['# what it reaches', '# second line'])
        self.assertIn('0,0x03ff', text)
        self.assertIn('10,0x03f7', text)       # Start pressed: bit 3 low
        self.assertIn('14,0x03ff', text)
        self.assertTrue(text.endswith('\n'))
        self.assertNotIn('\r', text)

    def test_a_script_that_starts_at_frame_zero_has_no_extra_release(self):
        text = tool.key_script_text([(0, 0x1), (5, 0)])
        self.assertEqual([line for line in text.splitlines() if not line.startswith('#')], ['0,0x03fe', '5,0x03ff'])

    def test_events_must_not_collide(self):
        with self.assertRaises(ValueError):
            tool.key_script_text([(3, 1), (3, 0)])
        with self.assertRaises(ValueError):
            tool.key_script_text([(-1, 1)])

    def test_pulses(self):
        self.assertEqual(tool.pulse_events(1, 100, 250, 50, 4), [(100, 1), (104, 0), (150, 1), (154, 0), (200, 1), (204, 0)])
        for bad in ((1, 0, 10, 4, 4), (1, 0, 10, 4, 0), (1, -1, 10, 4, 2)):
            with self.assertRaises(ValueError):
                tool.pulse_events(*bad)

    def test_parse_events_and_read_back(self):
        events = tool.parse_events('300:8, 304:0 ,0x140:0x101')
        self.assertEqual(events, [(300, 8), (304, 0), (0x140, 0x101)])
        with self.assertRaises(ValueError):
            tool.parse_events('300')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'route.keys'
            path.write_text(tool.key_script_text(sorted(events)), encoding='ascii')
            pairs = tool.read_key_script(path)
        self.assertEqual(pairs[0], (0, 0x3ff))
        self.assertEqual(pairs[1], (300, 0x3f7))
        self.assertEqual(pairs[-1], (0x140, 0x3ff & ~0x101))

    def test_read_key_script_refuses_what_the_player_would_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, body in (('words', '10,hello\n'), ('high', '10,0x7ff\n'), ('order', '20,0x3ff\n10,0x3ff\n')):
                path = Path(directory) / f'{name}.keys'
                path.write_text(body, encoding='ascii')
                with self.assertRaises(tool.CheckError, msg=name):
                    tool.read_key_script(path)


class SwitchTest(unittest.TestCase):
    def test_state_switch(self):
        self.assertEqual(tool.state_switch(save_frame=600), 'save@600')
        self.assertEqual(tool.state_switch(load_frame=2, resume=600), 'load@2=600')
        self.assertEqual(tool.state_switch(load_frame=2), 'load@2')
        self.assertEqual(tool.state_switch(save_frame=5, load_frame=9, resume=5), 'save@5,load@9=5')
        self.assertEqual(tool.state_switch(), '')

    def test_environment_is_hidden_and_does_not_leak_switches(self):
        with unittest.mock.patch.dict('os.environ', {'RETRORECOMP_GBA_SELFTEST': '1', 'RETRORECOMP_GBA_STATE': 'load@1'}):
            env = tool.player_environment(Path('f'), 300, Path('k.keys'), Path('p.ppm'))
        self.assertEqual((env['SDL_VIDEODRIVER'], env['SDL_AUDIODRIVER']), ('dummy', 'dummy'))
        self.assertEqual(env['RETRORECOMP_HOST_TEST_FRAMES'], '300')
        self.assertNotIn('RETRORECOMP_GBA_SELFTEST', env)
        self.assertNotIn('RETRORECOMP_GBA_STATE', env)
        self.assertEqual(env['RETRORECOMP_GBA_INPUT'], str(Path('k.keys').resolve()))     # absolute: the player runs elsewhere
        self.assertTrue(Path(env['RETRORECOMP_GBA_DUMP']).is_absolute())

    def test_player_output(self):
        text = ('[host] renderer=software\n[state] save at frame 600 ok\n[state] load at frame 2 FAILED\n'
                '[host] frames=720 audio_samples=1 audio_nonzero=0 audio_peak=0 interpreted=12\n')
        self.assertEqual(tool.parse_player_output(text), (720, 12, [('save', 600, True), ('load', 2, False)]))
        self.assertEqual(tool.parse_player_output('nothing'), (None, None, []))


class PictureAndSaveTest(unittest.TestCase):
    def test_picture_hash_ignores_the_header(self):
        with tempfile.TemporaryDirectory() as directory:
            one, two, other = (Path(directory) / name for name in ('one.ppm', 'two.ppm', 'other.ppm'))
            one.write_bytes(ppm(9))
            two.write_bytes(b'P6\n# a comment-free header\n'.replace(b'# a comment-free header', b'4 2') + b'255\n' + bytes([9]) * 24)
            other.write_bytes(ppm(10))
            self.assertEqual(tool.picture_sha256(one), tool.picture_sha256(two))
            self.assertNotEqual(tool.picture_sha256(one), tool.picture_sha256(other))
            self.assertEqual(tool.picture_sha256(one), hashlib.sha256(bytes([9]) * 24).hexdigest())
            self.assertEqual(tool.ppm_pixels(one)[:2], (4, 2))

    def test_a_truncated_or_foreign_picture_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'bad.ppm'
            bad.write_bytes(b'P6\n4 2\n255\n' + b'\x00' * 5)
            with self.assertRaises(tool.CheckError):
                tool.picture_sha256(bad)
            bad.write_bytes(b'P5\n4 2\n255\n')
            with self.assertRaises(tool.CheckError):
                tool.picture_sha256(bad)

    def test_png_is_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'p.png'
            tool.write_png(path, 4, 2, bytes(range(24)), scale=2)
            data = path.read_bytes()
        self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(data[12:16], b'IHDR')
        self.assertEqual(int.from_bytes(data[16:20], 'big'), 8)
        self.assertEqual(int.from_bytes(data[20:24], 'big'), 4)
        self.assertTrue(data.endswith(b'IEND\xaeB`\x82'))

    def test_save_statistics(self):
        erased = tool.save_stats(b'\xff' * 1024)
        self.assertTrue(erased['trivial'])
        self.assertEqual((erased['size'], erased['distinct_values'], erased['fill'], erased['bytes_differing_from_fill']), (1024, 1, 255, 0))
        self.assertTrue(tool.save_stats(b'\x00' * 8)['trivial'])
        self.assertTrue(tool.save_stats(b'')['trivial'])
        written = tool.save_stats(b'\xff' * 1000 + b'Metroid' * 3 + b'\xff' * 3)
        self.assertFalse(written['trivial'])
        self.assertEqual(written['bytes_differing_from_fill'], 21)
        self.assertEqual(len(written['sha256']), 64)


def run(label, picture='a' * 64, frames=720, code=0, states=(), interpreted=0):
    return tool.RunResult(label, code, frames, interpreted, list(states), picture_sha256=picture)


class StateVerdictTest(unittest.TestCase):
    def verdict(self, a=None, b=None, control=None, size=600000):
        a = a or run('A', states=[('save', 600, True)])
        b = b or run('B', states=[('load', 2, True)])
        control = control or run('control', picture='c' * 64)
        return tool.state_verdict(a, b, control, 600, size)

    def test_pass(self):
        result = self.verdict()
        self.assertEqual((result['verdict'], result['pictures_equal'], result['control_differs'], result['problems']), ('pass', True, True, []))

    def test_a_state_that_does_not_restore_is_a_fail(self):
        result = self.verdict(b=run('B', picture='b' * 64, states=[('load', 2, True)]))
        self.assertEqual(result['verdict'], 'fail')
        self.assertFalse(result['pictures_equal'])

    def test_a_picture_that_does_not_tell_the_state_from_nothing_is_weak(self):
        result = self.verdict(control=run('control', picture='a' * 64))
        self.assertEqual(result['verdict'], 'weak')

    def test_an_old_player_is_an_error_not_a_pass(self):
        result = self.verdict(a=run('A'), b=run('B'))
        self.assertEqual(result['verdict'], 'error')
        self.assertIn('RETRORECOMP_GBA_STATE', result['problems'][0])

    def test_a_load_that_failed_a_missing_file_a_crash_and_another_end_frame(self):
        self.assertEqual(self.verdict(b=run('B', states=[('load', 2, False)]))['verdict'], 'error')
        self.assertEqual(self.verdict(size=None)['verdict'], 'error')
        self.assertEqual(self.verdict(a=run('A', code=3, states=[('save', 600, True)]))['verdict'], 'error')
        self.assertEqual(self.verdict(b=run('B', frames=719, states=[('load', 2, True)]))['verdict'], 'error')
        self.assertEqual(self.verdict(a=run('A', picture=None, states=[('save', 600, True)]))['verdict'], 'error')


class SaveVerdictTest(unittest.TestCase):
    GOOD = tool.save_stats(bytes(range(256)) * 4)
    FRESH = tool.save_stats(b'\xff' * 1024)

    def test_pass(self):
        runs = [run('A'), run('B'), run('control')]
        result = tool.save_verdict(self.GOOD, self.FRESH, self.GOOD, 'b' * 64, 'c' * 64, runs)
        self.assertEqual((result['verdict'], result['save_read_back_in_picture'], result['save_unchanged_by_b']), ('pass', True, True))

    def test_failures(self):
        runs = [run('A'), run('B'), run('control')]
        self.assertEqual(tool.save_verdict(None, self.FRESH, None, 'b', 'c', runs)['verdict'], 'fail')
        self.assertEqual(tool.save_verdict(self.FRESH, self.FRESH, self.FRESH, 'b', 'c', runs)['verdict'], 'fail')
        same_as_fresh = tool.save_verdict(self.GOOD, self.GOOD, self.GOOD, 'b', 'c', runs)
        self.assertEqual(same_as_fresh['verdict'], 'fail')
        self.assertIn('played nothing', same_as_fresh['problems'][0])
        not_shown = tool.save_verdict(self.GOOD, self.FRESH, self.GOOD, 'b', 'b', runs)
        self.assertEqual((not_shown['verdict'], not_shown['save_read_back_in_picture']), ('fail', False))
        self.assertEqual(tool.save_verdict(self.GOOD, self.FRESH, self.GOOD, 'b', 'c', [run('A', code=1)])['verdict'], 'fail')

    def test_a_save_that_b_changes_is_reported_not_failed(self):
        other = tool.save_stats(bytes(range(255, -1, -1)) * 4)
        result = tool.save_verdict(self.GOOD, self.FRESH, other, 'b', 'c', [run('A')])
        self.assertEqual((result['verdict'], result['save_unchanged_by_b']), ('pass', False))


class ChecksAgainstAFakePlayerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.work = Path(self.directory.name) / 'work'
        self.exe = Path(self.directory.name) / 'Fake Game.exe'
        self.exe.write_bytes(b'MZ authored bytes, not a program')
        self.keys = Path(self.directory.name) / 'write.keys'
        self.keys.write_text(tool.key_script_text([(5, 8), (9, 0)]), encoding='ascii')
        self.show = Path(self.directory.name) / 'show.keys'
        self.show.write_text(tool.key_script_text([(5, 8), (9, 0)]), encoding='ascii')

    def run_state(self, fake):
        with unittest.mock.patch.object(tool.subprocess, 'run', fake):
            return tool.run_state_check(self.exe, self.work, self.keys, 600, 120, 2, 60)

    def test_state_check_passes_and_ran_three_separate_processes(self):
        fake = FakeProcess()
        report = self.run_state(fake)
        self.assertEqual(report['result']['verdict'], 'pass', report['result'])
        self.assertEqual([call[0] for call in fake.calls], ['save@600', 'load@2=600', ''])
        self.assertEqual([call[2] for call in fake.calls], [720, 122, 122])
        self.assertEqual(report['runs']['A']['frames'], report['runs']['B']['frames'])
        self.assertEqual(report['runs']['A']['picture_sha256'], report['runs']['B']['picture_sha256'])
        self.assertEqual(report['result']['state_file_bytes'], 500)
        self.assertTrue((self.work / 'state' / 'A.png').is_file())
        self.assertTrue((self.work / 'state' / 'game.exe').is_file())

    def test_a_state_that_does_not_restore_is_found(self):
        report = self.run_state(FakeProcess(restore_state=False))
        self.assertEqual(report['result']['verdict'], 'fail')

    def test_an_old_player_stops_the_check(self):
        report = self.run_state(FakeProcess(old_player=True))
        self.assertEqual(report['result']['verdict'], 'error')

    def test_a_static_game_is_weak(self):
        self.assertEqual(self.run_state(FakeProcess(same_picture_without_state=True))['result']['verdict'], 'weak')

    def test_the_delivered_executable_is_copied_not_run_in_place(self):
        fake = FakeProcess()
        self.run_state(fake)
        self.assertTrue(self.exe.is_file())
        self.assertFalse((self.exe.parent / 'datas').exists())

    def run_refusals(self, fake):
        with unittest.mock.patch.object(tool.subprocess, 'run', fake):
            return tool.run_refusal_check(self.exe, self.work, self.keys, 600, 120, 2, 60)

    def test_refusal_check_passes_when_every_damaged_state_is_refused_and_a_missing_one_creates_nothing(self):
        fake = FakeProcess()
        report = self.run_refusals(fake)
        result = report['result']
        self.assertEqual(result['verdict'], 'pass', result)
        self.assertEqual(len(result['variants']), 9)             # eight damaged forms and the missing state
        self.assertTrue(all(row['ok'] for row in result['variants'].values() if row['required']), result['variants'])
        self.assertEqual(result['files_created_by_the_missing_state'], [])
        self.assertEqual(fake.calls[0][0], 'save@600')
        self.assertTrue(all(call[0] == 'load@2=600' for call in fake.calls[2:]))
        self.assertEqual(fake.calls[1], ('', 'write.keys', 122))   # the control never loads

    def test_a_player_that_accepts_a_damaged_state_fails_the_check(self):
        result = self.run_refusals(FakeProcess(refuse_damaged=False))['result']
        self.assertEqual(result['verdict'], 'fail')
        self.assertFalse(result['variants']['emptied']['ok'])
        self.assertIn('emptied', ' '.join(result['problems']))

    def test_a_missing_state_that_creates_a_file_fails_the_check(self):
        result = self.run_refusals(FakeProcess(create_on_missing=True))['result']
        self.assertEqual(result['verdict'], 'fail')
        self.assertEqual(result['files_created_by_the_missing_state'], ['game-0123.rrstate'])

    def test_an_old_player_stops_the_refusal_check(self):
        with self.assertRaises(tool.CheckError):
            self.run_refusals(FakeProcess(old_player=True))

    def test_the_damaged_forms_break_the_container_but_one(self):
        data = bytes(range(256)) * 4
        forms = tool.damaged_states(data)
        self.assertEqual(len(forms), 8)
        self.assertEqual([name for name, (_, required) in forms.items() if not required], ['one byte inverted in the middle'])
        self.assertTrue(all(blob != data for blob, _ in forms.values()))
        self.assertEqual(forms['noise of the same size'][0], tool.damaged_states(data)['noise of the same size'][0])   # deterministic
        self.assertEqual(len(forms['noise of the same size'][0]), len(data))

    def test_a_route_reports_the_last_picture_the_frames_and_the_interpreted_count(self):
        with unittest.mock.patch.object(tool.subprocess, 'run', FakeProcess()):
            report = tool.run_route_check(self.exe, self.work, self.keys, 300, 60)
        self.assertEqual(report['result']['verdict'], 'pass', report['result'])
        self.assertEqual((report['result']['frames'], report['result']['interpreted_instructions']), (300, 0))
        self.assertEqual(len(report['result']['picture_sha256']), 64)
        self.assertEqual(len(report['parameters']['keys_sha256']), 64)

    def test_state_check_arguments_are_checked(self):
        with self.assertRaises(tool.CheckError):
            tool.run_state_check(self.exe, self.work, self.keys, 100, 10, 100, 60)
        with self.assertRaises(tool.CheckError):
            tool.run_state_check(Path(self.directory.name) / 'missing.exe', self.work, None, 100, 10, 2, 60)

    def test_save_check_passes(self):
        fake = FakeProcess()
        with unittest.mock.patch.object(tool.subprocess, 'run', fake):
            report = tool.run_save_check(self.exe, self.work, self.keys, 3000, self.show, 900, 60)
        self.assertEqual(report['result']['verdict'], 'pass', report['result'])
        self.assertEqual(report['runs']['save A']['distinct_values'], 256)
        self.assertEqual(report['runs']['save fresh']['distinct_values'], 1)
        self.assertEqual([call[2] for call in fake.calls], [3000, 900, 900])
        self.assertTrue((self.work / 'save-A.sav').is_file())

    def test_save_check_fails_when_the_game_writes_nothing(self):
        with unittest.mock.patch.object(tool.subprocess, 'run', FakeProcess(write_save=False)):
            report = tool.run_save_check(self.exe, self.work, self.keys, 3000, self.show, 900, 60)
        self.assertEqual(report['result']['verdict'], 'fail')

    def test_a_timeout_is_an_error(self):
        def slow(*args, **kwargs):
            raise tool.subprocess.TimeoutExpired('game', 1)
        with unittest.mock.patch.object(tool.subprocess, 'run', slow):
            with self.assertRaises(tool.CheckError):
                self.run_state(slow)


class ReportAndCommandLineTest(unittest.TestCase):
    def test_report_is_hashes_and_numbers_and_renders(self):
        with tempfile.TemporaryDirectory() as directory:
            exe = Path(directory) / 'G.exe'
            exe.write_bytes(b'authored')
            a = run('A', states=[('save', 600, True)])
            report = tool.build_report('state', exe, {'A': a}, {'verdict': 'pass', 'problems': [], 'pictures_equal': True}, {'save_frame': 600})
        self.assertEqual(report['exe'], 'G.exe')
        self.assertEqual(report['exe_sha256'], hashlib.sha256(b'authored').hexdigest())
        self.assertEqual(report['report_version'], tool.REPORT_VERSION)
        text = tool.render_text(report)
        self.assertIn('PASS', text)
        self.assertIn('save@600 ok', text)
        json.dumps(report)

    def test_arguments(self):
        args = tool.build_parser().parse_args(['state', '--exe', 'g.exe', '--keys', 'r.keys', '--save-frame', '900'])
        self.assertEqual((args.command, args.save_frame, args.more, args.load_frame), ('state', 900, 120, 2))
        args = tool.build_parser().parse_args(['save', '--exe', 'g.exe', '--keys-a', 'a', '--frames-a', '9', '--keys-b', 'b', '--frames-b', '3'])
        self.assertEqual((args.frames_a, args.frames_b, args.timeout), (9, 3, 1800))
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            tool.build_parser().parse_args(['state'])

    def test_keys_command_writes_a_route(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / 'sub' / 'r.keys'
            with redirect_stdout(io.StringIO()):
                code = tool.main(['keys', '--out', str(out), '--header', 'title to play', '--events', '100:8,104:0', '--pulse',
                                  '1,200,300,50,4'])
            self.assertEqual(code, 0)
            pairs = tool.read_key_script(out)
        self.assertEqual(pairs[:3], [(0, 0x3ff), (100, 0x3f7), (104, 0x3ff)])
        self.assertEqual(pairs[3:5], [(200, 0x3fe), (204, 0x3ff)])

    def test_main_reports_a_check_that_could_not_run(self):
        with redirect_stderr(io.StringIO()) as errors:
            code = tool.main(['state', '--exe', str(ROOT / 'no-such-player.exe'), '--work', str(ROOT / '.build' / 'unit-never-created')])
        self.assertEqual(code, 2)
        self.assertIn('not a file', errors.getvalue())


if __name__ == '__main__':
    unittest.main()
