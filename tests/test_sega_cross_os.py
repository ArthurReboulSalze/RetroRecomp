"""tools/sega_cross_os.py on synthetic trace folders: no ROM, no executable."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
SPEC = importlib.util.spec_from_file_location('sega_cross_os', TOOLS / 'sega_cross_os.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

HEADER = 'frame,vram_h,cram_h,reg_h,ram_h,r8,r9,r0,r1,sp,pixels_h,psg_h,psg_nz\n'


def write(folder: Path, rows: list, *, ram='r', cpu=None, crlf=False, rom='abc'):
    folder.mkdir(parents=True)
    text = HEADER + ''.join(row + '\n' for row in rows)
    (folder / 'play.csv').write_bytes((text.replace('\n', '\r\n') if crlf else text).encode('ascii'))
    (folder / 'summary.json').write_text(json.dumps({'schema': 1, 'system': 'x', 'executable': 'g', 'rom_sha256': rom, 'routes': {'play': {
        'frames': len(rows), 'exit': 0, 'trace_sha256': tool.sha256(folder / 'play.csv', text=True), 'final_ram_sha256': ram,
        'final_cpu': cpu or {'pc': 1}}}}), encoding='utf-8')


def compare(a: Path, b: Path):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = tool.compare_command(SimpleNamespace(a=a, b=b))
    return code, out.getvalue()


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_equal_traces_ram_and_registers_are_identical_even_with_other_line_ends(self):
        rows = ['1,a,b,c,d,0,0,0,0,DFF0,p1,s1,0', '2,a,b,c,e,0,0,0,0,DFF0,p2,s2,3']
        write(self.root / 'a', rows)
        write(self.root / 'b', rows, crlf=True)
        code, text = compare(self.root / 'a', self.root / 'b')
        self.assertEqual(code, 0, text)
        self.assertIn('IDENTICAL', text)

    def test_a_different_frame_names_the_first_frame_and_the_columns(self):
        write(self.root / 'a', ['1,a,b,c,d,0,0,0,0,DFF0,p1,s1,0', '2,a,b,c,e,0,0,0,0,DFF0,p2,s2,3'])
        write(self.root / 'b', ['1,a,b,c,d,0,0,0,0,DFF0,p1,s1,0', '2,a,b,c,e,0,0,0,0,DFF0,p9,s2,3'])
        code, text = compare(self.root / 'a', self.root / 'b')
        self.assertEqual(code, 1)
        self.assertIn('"frame": 2', text)
        self.assertIn('pixels_h', text)

    def test_other_ram_or_registers_or_another_game_are_different(self):
        rows = ['1,a,b,c,d,0,0,0,0,DFF0,p1,s1,0']
        write(self.root / 'a', rows)
        write(self.root / 'b', rows, ram='other')
        self.assertEqual(compare(self.root / 'a', self.root / 'b')[0], 1)
        write(self.root / 'c', rows, cpu={'pc': 2})
        self.assertEqual(compare(self.root / 'a', self.root / 'c')[0], 1)
        write(self.root / 'd', rows, rom='zzz')
        self.assertEqual(compare(self.root / 'a', self.root / 'd')[0], 1)


if __name__ == '__main__':
    unittest.main()
