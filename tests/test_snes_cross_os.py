"""tools/snes_cross_os.py on synthetic trace folders: no ROM, no executable."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
SPEC = importlib.util.spec_from_file_location('snes_cross_os', TOOLS / 'snes_cross_os.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

HEADER = 'frame,frame_hash,native,interpreted,audio_hash\n'
ROWS = ['1,aa,10,0,bb', '2,aa,20,0,dd', '3,ee,30,0,ff']


def write(folder: Path, rows: list[str], system='win32', script='a', report=None, crlf=False):
    folder.mkdir(parents=True)
    text = HEADER + ''.join(row + '\n' for row in rows)
    (folder / 'play.csv').write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('ascii'))
    (folder / 'summary.json').write_text(json.dumps({'system': system, 'executable': 'g', 'routes': {'play': {
        'frames': len(rows), 'trace_sha256': tool.sha256(folder / 'play.csv'), 'script_sha256': script,
        'report': report or {'cpu_hash': '1', 'ram_hash': '2'}}}}), encoding='utf-8')


def compare(a: Path, b: Path):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = tool.compare_command(SimpleNamespace(a=a, b=b))
    return status, out.getvalue()


class CompareTests(unittest.TestCase):
    def test_identical_traces_agree_even_with_other_line_ends(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', ROWS, system='linux', crlf=True)
            status, text = compare(root / 'a', root / 'b')
            self.assertEqual(status, 0)
            self.assertIn('play: 3 frames: trace =, report hashes =  same', text)

    def test_a_different_frame_names_the_frame_and_the_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', [ROWS[0], '2,aa,21,0,dd', ROWS[2]])
            status, text = compare(root / 'a', root / 'b')
            self.assertEqual(status, 1)
            self.assertIn('first difference at frame 2: native (20 / 21)', text)

    def test_a_report_hash_that_differs_is_named(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', ROWS, report={'cpu_hash': '1', 'ram_hash': '3'})
            status, text = compare(root / 'a', root / 'b')
            self.assertEqual(status, 1)
            self.assertIn('report hashes != (ram_hash)', text)

    def test_different_scripts_are_not_compared(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write(root / 'a', ROWS)
            write(root / 'b', ROWS, script='other')
            status, text = compare(root / 'a', root / 'b')
            self.assertEqual(status, 1)
            self.assertIn('the input scripts or the lengths differ', text)


if __name__ == '__main__':
    unittest.main()
