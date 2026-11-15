"""The PlayStation per-frame trace and its format (retrorecomp/psx_conversion.py, native/psx_machine/psx_main.c): format 2 (1.7.7)
adds the hash of the core's VRAM; both formats are read, an unknown one is refused, and two formats are never compared."""
from pathlib import Path
import tempfile
import unittest

from retrorecomp import psx_conversion as conversion
from retrorecomp.core import ConversionError
from retrorecomp.paths import ASSETS

V1 = ('frame,ram,image,pcm,samples,audible,size,cpu\n'
      '1,aaaa,bbbb,cccc,735,0,320x240,dddd\n'
      '2,aaab,bbbc,cccd,735,1,320x240,ddde\n')
V2 = ('frame,ram,image,pcm,samples,audible,size,cpu,vram\n'
      '1,aaaa,bbbb,cccc,735,0,320x240,dddd,eeee\n'
      '2,aaab,bbbc,cccd,735,1,320x240,ddde,eeef\n')


class TraceFormatTests(unittest.TestCase):
    def write(self, folder, name, text):
        path = Path(folder) / name
        path.write_text(text, encoding='ascii')
        return path

    def test_the_game_writes_format_two(self):
        main = (ASSETS / 'native' / 'psx_machine' / 'psx_main.c').read_text(encoding='utf-8')
        self.assertIn('"' + conversion.TRACE_FORMATS[conversion.TRACE_FORMAT] + '\\n"', main)
        self.assertEqual(conversion.TRACE_FORMAT, 2)
        self.assertTrue(conversion.TRACE_FORMATS[2].startswith(conversion.TRACE_FORMATS[1] + ','))
        session = (ASSETS / 'native' / 'psx_machine' / 'psx_session.c').read_text(encoding='utf-8')
        self.assertIn('info->vram = GPU.vram ? fnv(GPU.vram,', session)

    def test_both_formats_are_read(self):
        with tempfile.TemporaryDirectory() as folder:
            for text, number in ((V1, 1), (V2, 2)):
                path = self.write(folder, f'v{number}.csv', text)
                self.assertEqual(conversion.trace_format(path), number)
                rows = list(conversion.trace_rows(path))
                self.assertEqual([(r.frame, r.audible) for r in rows], [(1, False), (2, True)])

    def test_an_unknown_format_is_refused_with_a_sentence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.write(folder, 'other.csv', 'frame,ram\n1,aa\n')
            with self.assertRaisesRegex(ConversionError, 'not a PlayStation trace of a known format'):
                conversion.trace_format(path)

    def test_two_formats_are_never_compared(self):
        with tempfile.TemporaryDirectory() as folder:
            one, two = self.write(folder, 'a.csv', V1), self.write(folder, 'b.csv', V2)
            with self.assertRaisesRegex(ConversionError, 'two formats cannot be compared'):
                conversion.trace_difference(one, two)
            same = self.write(folder, 'c.csv', V2)
            self.assertIsNone(conversion.trace_difference(two, same))
            other = self.write(folder, 'd.csv', V2.replace('eeef', 'eef0'))
            self.assertEqual(conversion.trace_difference(two, other), 1)   # the second row: VRAM alone differs


if __name__ == '__main__':
    unittest.main()
