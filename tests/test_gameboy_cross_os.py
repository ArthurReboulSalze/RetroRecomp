"""tools/gameboy_cross_os.py on synthetic trace folders: no ROM, no executable."""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
SPEC = importlib.util.spec_from_file_location('gameboy_cross_os', TOOLS / 'gameboy_cross_os.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

HEADER = 'frame,picture,sound,nonzero_samples,ram,pc\n'


def write(folder: Path, rows: list[str], system='win32', script='a', state='s', crlf=False):
    folder.mkdir(parents=True)
    text = HEADER + ''.join(row + '\n' for row in rows)
    (folder / 'boot.csv').write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('ascii'))
    (folder / 'summary.json').write_text(json.dumps({'system': system, 'executable': 'g', 'routes': {'boot': {
        'frames': len(rows), 'trace_sha256': tool.sha256(folder / 'boot.csv'), 'script_sha256': script, 'state_sha256': state}}}),
        encoding='utf-8')


def compare(a: Path, b: Path):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = tool.compare_command(SimpleNamespace(a=a, b=b))
    return status, out.getvalue()


ROWS = ['1,aa,bb,0,cc,0100', '2,aa,dd,5,cc,0103', '3,ee,ff,5,cc,0106']


class CompareTests(unittest.TestCase):
    def test_identical_traces_agree_even_with_other_line_ends(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', ROWS, system='linux', crlf=True)
            status, text = compare(root / 'a', root / 'b')
            self.assertEqual(status, 0)
            self.assertIn('boot: 3 frames: trace =, final state =  same', text)

    def test_a_different_frame_names_the_frame_and_the_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', [ROWS[0], '2,aa,dd,5,cc,0104', ROWS[2]])
            status, text = compare(root / 'a', root / 'b')
            self.assertEqual(status, 1)
            self.assertIn('first difference at frame 2: pc (0103 / 0104)', text)

    def test_different_scripts_are_not_compared_and_a_shorter_trace_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', ROWS, script='other')
            status, text = compare(root / 'a', root / 'b')
            self.assertEqual(status, 1)
            self.assertIn('not comparable', text)
            self.assertIn('agree on 2 frames but have 3 and 2 rows',
                          tool.first_difference(root / 'a' / 'boot.csv', self._short(root)))

    def test_a_different_final_state_alone_is_a_difference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', ROWS, state='t')
            self.assertEqual(compare(root / 'a', root / 'b')[0], 1)

    def _short(self, root: Path) -> Path:
        path = root / 'short.csv'
        path.write_text(HEADER + '\n'.join(ROWS[:2]) + '\n', encoding='ascii')
        return path


class RoutesOfTests(unittest.TestCase):
    def test_the_report_of_the_executable_is_read_in_a_folder_of_several_games(self):
        with tempfile.TemporaryDirectory() as folder:
            games = Path(folder)
            for name, sha in (('aaa', 'a' * 64), ('zzz', 'f' * 64)):
                report = games / 'datas' / 'reports' / f'{name}-{sha[:12]}'
                report.mkdir(parents=True)
                (report / 'conversion-report.json').write_text(json.dumps({'executable': f'{name}.exe', 'rom': {'sha256': sha},
                    'final_checks': [{'scenario': 'boot', 'frames': 10 if name == 'aaa' else 20, 'input_script': ''}]}), encoding='utf-8')
            self.assertEqual(tool.routes_of(games / 'zzz.exe')['boot'][1], 20)
            self.assertEqual(tool.routes_of(games / 'aaa.exe')['boot'][1], 10)

    def test_an_executable_that_no_report_names_is_refused_not_given_another_report(self):
        with tempfile.TemporaryDirectory() as folder:
            games = Path(folder)
            report = games / 'datas' / 'reports' / 'aaa-aaaaaaaaaaaa'
            report.mkdir(parents=True)
            (report / 'conversion-report.json').write_text(json.dumps({'executable': 'aaa.exe', 'rom': {'sha256': 'a' * 64},
                'final_checks': [{'scenario': 'boot', 'frames': 10, 'input_script': ''}]}), encoding='utf-8')
            with self.assertRaises(SystemExit) as caught:
                tool.routes_of(games / 'renamed')
            self.assertIn('renamed', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
