"""The PlayStation disc pack and conversion routes on synthetic discs (no game, no BIOS)."""
import struct
import tempfile
import unittest
from pathlib import Path

from retrorecomp import psx_conversion, psx_pack
from tests.test_psx_disc import SECTOR, audio_track, raw_sector, user_sectors


def manifest(path: Path) -> tuple[list[str], bytes]:
    data = path.read_bytes()
    assert data[-24:-16] == psx_pack.MAGIC
    offset, size = struct.unpack('<QQ', data[-16:])
    return data[offset:offset + size].decode('utf-8').splitlines(), data


class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        user, _ = user_sectors()
        self.raw = b''.join(raw_sector(i, u) for i, u in enumerate(user))
        self.frames = len(user)
        (self.dir / 'g.bin').write_bytes(self.raw + audio_track(20))
        (self.dir / 'g.cue').write_text(
            'FILE "g.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
            f'  TRACK 02 AUDIO\n    INDEX 01 00:00:{self.frames:02d}\n', encoding='ascii')

    def tearDown(self):
        self.tmp.cleanup()

    def test_in_place_pack_names_the_players_files_and_stores_only_the_sheet(self):
        pack = psx_pack.write_in_place(self.dir / 'g.cue', self.dir / 'out' / 'pack.bin')
        lines, data = manifest(pack)
        self.assertEqual(lines[0], psx_pack.FORMAT_LINE)
        self.assertTrue(any(line.startswith('source 1 ') and line.endswith('g.bin') for line in lines))
        self.assertIn('disc disc1.cue', lines)
        self.assertLess(len(data), 4096)           # the disc itself is not copied
        sheet = next(line for line in lines if line.startswith('file disc1.cue raw 0 '))
        offset, size = map(int, sheet.split()[-2:])
        text = data[offset:offset + size].decode('ascii')
        self.assertIn('FILE "disc1-1.bin" BINARY', text)
        self.assertIn('TRACK 02 AUDIO', text)
        self.assertIn(f'INDEX 01 00:00:{self.frames:02d}', text)

    def test_embedded_pack_carries_every_byte_after_the_program(self):
        program = self.dir / 'program.exe'
        program.write_bytes(b'MZ' + bytes(1000))
        game = psx_pack.write_embedded(self.dir / 'g.cue', program, self.dir / 'game.exe')
        lines, data = manifest(game)
        self.assertTrue(data.startswith(program.read_bytes()))
        self.assertFalse(any(line.startswith('source ') for line in lines))   # an exported game names only itself
        image = next(line for line in lines if line.startswith('file disc1-1.bin raw 0 '))
        offset, size = map(int, image.split()[-2:])
        self.assertEqual(data[offset:offset + size], (self.dir / 'g.bin').read_bytes())


class RouteTests(unittest.TestCase):
    def test_routes_are_deterministic_and_ordered(self):
        a = psx_conversion.routes('0123456789abcdef', frames=3600, level='standard')
        b = psx_conversion.routes('0123456789abcdef', frames=3600, level='standard')
        self.assertEqual(a, b)
        self.assertEqual([name for name, _, _ in a], ['attract', 'play'])
        frames = [int(line.split()[0]) for line in a[1][2].splitlines()]
        self.assertEqual(frames, sorted(frames))
        self.assertGreaterEqual(frames[0], psx_conversion.BOOT_FRAMES)   # nothing is pressed while the BIOS boots
        self.assertEqual([name for name, _, _ in psx_conversion.routes('ff', frames=3600, level='thorough')],
                         ['attract', 'play', 'long-1', 'long-2'])


if __name__ == '__main__':
    unittest.main()
