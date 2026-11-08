"""The PlayStation disc pack and conversion routes on synthetic discs (no game, no BIOS)."""
import os
import stat
import struct
import tempfile
import unittest
from pathlib import Path

from retrorecomp import psx_beetle, psx_conversion, psx_pack
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


    def _sheet_of(self, silence: int, *, index00: bool = False, second_silent: bool = True) -> str:
        """The sheet the pack holds for data + audio + `silence` silent sectors + audio, in one file with a sheet of INDEX 01 only."""
        first = audio_track(100) if not second_silent else audio_track(100 - silence) + bytes(silence * SECTOR)
        (self.dir / 'g.bin').write_bytes(self.raw + first + audio_track(40))
        start = self.frames + 100
        gap = f'    INDEX 00 {psx_pack._msf(start - 5)}\n' if index00 else ''
        (self.dir / 'g.cue').write_text(
            'FILE "g.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
            f'  TRACK 02 AUDIO\n    PREGAP 00:02:00\n    INDEX 01 {psx_pack._msf(self.frames)}\n'
            f'  TRACK 03 AUDIO\n{gap}    INDEX 01 {psx_pack._msf(start)}\n', encoding='ascii')
        lines, data = manifest(psx_pack.write_in_place(self.dir / 'g.cue', self.dir / 'out' / 'pack.bin'))
        sheet = next(line for line in lines if line.startswith('file disc1.cue raw 0 '))
        offset, size = map(int, sheet.split()[-2:])
        return data[offset:offset + size].decode('ascii')

    def test_the_silent_gap_of_an_audio_track_goes_back_to_that_track(self):
        # Tobal No. 1's sheet: two seconds of digital silence before the track, and only its INDEX 01.
        text = self._sheet_of(90)
        start = self.frames + 100
        self.assertIn(f'TRACK 03 AUDIO\r\n    INDEX 00 {psx_pack._msf(start - 90)}\r\n    INDEX 01 {psx_pack._msf(start)}', text)
        self.assertEqual(text.count('INDEX 00'), 1)    # not the data track, not track 2 (its gap is not stored: PREGAP)
        self.assertIn('PREGAP 00:02:00', text)

    def test_a_gap_is_read_only_where_silence_shows_one(self):
        self.assertNotIn('INDEX 00', self._sheet_of(0, second_silent=False))     # the sound runs up to the track
        self.assertNotIn('INDEX 00', self._sheet_of(74))                         # shorter than a seek can land early

    def test_the_gap_stops_at_two_seconds_and_keeps_a_sector_of_the_track_before(self):
        start = self.frames + 100
        self.assertIn(f'INDEX 00 {psx_pack._msf(start - 99)}', self._sheet_of(100))
        (self.dir / 'g.bin').write_bytes(self.raw + audio_track(100) + bytes(200 * SECTOR) + audio_track(40))
        (self.dir / 'g.cue').write_text(
            'FILE "g.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
            f'  TRACK 02 AUDIO\n    PREGAP 00:02:00\n    INDEX 01 {psx_pack._msf(self.frames)}\n'
            f'  TRACK 03 AUDIO\n    INDEX 01 {psx_pack._msf(self.frames + 300)}\n', encoding='ascii')
        lines, data = manifest(psx_pack.write_in_place(self.dir / 'g.cue', self.dir / 'out' / 'pack.bin'))
        sheet = next(line for line in lines if line.startswith('file disc1.cue raw 0 '))
        offset, size = map(int, sheet.split()[-2:])
        self.assertIn(f'INDEX 00 {psx_pack._msf(self.frames + 150)}', data[offset:offset + size].decode('ascii'))

    def test_a_sheet_that_states_its_gap_is_kept_as_it_is(self):
        start = self.frames + 100
        text = self._sheet_of(90, index00=True)
        self.assertIn(f'INDEX 00 {psx_pack._msf(start - 5)}\r\n    INDEX 01 {psx_pack._msf(start)}', text)

    @unittest.skipIf(os.name == 'nt', 'Windows has no execute bit')
    def test_the_embedded_game_stays_executable(self):
        program = self.dir / 'program'
        program.write_bytes(bytes(100))
        program.chmod(0o755)
        game = psx_pack.write_embedded(self.dir / 'g.cue', program, self.dir / 'game')
        self.assertEqual(stat.S_IMODE(game.stat().st_mode), 0o755)


class UndrawnRowsTests(unittest.TestCase):
    def test_the_rows_a_wrapping_display_reads_stay_at_their_place_and_are_only_those_the_game_cannot_draw(self):
        gpu = next(new for rel, old, new in psx_beetle.REPLACEMENTS if 'GPU_BlankUndrawnRows' in new and rel.endswith('gpu.c'))
        self.assertIn('return y < GPU.ClipY0 || y > GPU.ClipY1;', gpu)                       # outside the drawing area
        self.assertIn('(((int32_t)GPU.VertEnd - (int32_t)GPU.VertStart) << full) <= 512', gpu)  # only a display that wraps
        self.assertIn('row < rows && y < 512', gpu)                                          # only before the wrap
        self.assertIn('(GPU.DisplayMode & DISP_RGB24)', gpu)                                 # a film is left alone
        self.assertIn('memset(', gpu)                                                        # black, never a crop
        self.assertNotIn('height =', gpu)


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
