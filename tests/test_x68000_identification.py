"""`.d88` and `.m3u` are claimed by the X68000 only when their content says X68000 (authored headers, no disk bytes)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from retrorecomp.systems import UnsupportedConsoleError, profile_for_path
from retrorecomp.x68000_media import D88_HEADER_BYTES, identify_disk


def d88_header(media: int) -> bytes:
    """A header-only D88 file that describes itself: its size field is the file's size and track 0 starts after the header."""
    header = bytearray(D88_HEADER_BYTES)
    header[0x1A] = 0x00                    # write protect: none
    header[0x1B] = media
    header[0x1C:0x20] = D88_HEADER_BYTES.to_bytes(4, 'little')
    header[0x20:0x24] = D88_HEADER_BYTES.to_bytes(4, 'little')
    return bytes(header)


RAW_2HD_BYTES = 77 * 2 * 8 * 1024          # a raw (XDF) 2HD image: no header


class X68000IdentificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make(self, name: str, data: bytes | str) -> Path:
        path = self.root / name
        path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8'))
        return path

    def test_a_d88_of_a_two_d_disk_is_no_x68000_disk(self):
        # What the X1, PC-88 and PC-98 write: 80 files of the owner's x1 folder were labelled X68000 by their extension.
        for media, label in ((0x00, '2D'), (0x10, '2DD'), (0x30, '1D'), (0x40, '1DD')):
            with self.subTest(label), self.assertRaisesRegex(UnsupportedConsoleError, f'{label} disk') as caught:
                profile_for_path(self.make(f'game{media}.d88', d88_header(media)), None)
            self.assertIn('not an X68000 2HD disk', str(caught.exception))

    def test_a_d88_of_a_two_hd_disk_is_left_to_the_x68000_reader(self):
        self.assertEqual(profile_for_path(self.make('game.d88', d88_header(0x20)), None).id, 'x68')
        self.assertEqual(profile_for_path(self.make('other.88d', d88_header(0x20)), None).id, 'x68')

    def test_a_raw_disk_with_an_empty_first_sector_named_d88_is_not_refused(self):
        # A data disk whose first sector is zeros has 00 00 where a D88 header keeps its write protect and media bytes (three of
        # the owner's X68000 disks do). Named .d88, it is still a raw 2HD image that identify_disk reads: it is not refused.
        image = bytearray(RAW_2HD_BYTES)
        image[1024:1040] = b'authored data 01'          # the second sector: anything but a header
        for media in (0x00, 0x10):                       # the header's 2D and 2DD values, here only zeros of the disk
            image[0x1B] = media
            with self.subTest(media=media):
                path = self.make(f'data{media}.d88', bytes(image))
                self.assertEqual(profile_for_path(path, None).id, 'x68')
                disk = identify_disk(path)
                self.assertEqual((disk.size, disk.converted), (RAW_2HD_BYTES, None))

    def test_a_file_that_is_no_d88_at_all_still_reaches_the_reader(self):
        self.assertEqual(profile_for_path(self.make('junk.d88', b'not a disk'), None).id, 'x68')

    def test_the_other_x68000_extensions_are_unchanged(self):
        for name in ('a.dim', 'b.xdf', 'c.hdm', 'd.2hd', 'e.dup'):
            with self.subTest(name):
                self.assertEqual(profile_for_path(self.make(name, bytes(300)), None).id, 'x68')

    def test_a_playlist_of_x68000_disks_is_a_disk_set(self):
        playlist = self.make('Game.m3u', '# a set\nGame (Disk 1).dim\nGame (Disk 2).xdf\n')
        self.assertEqual(profile_for_path(playlist, None).id, 'x68')

    def test_a_playlist_of_discs_is_no_x68000_disk_set(self):
        # A PlayStation or Saturn frontend's multi-disc playlist: its members are discs, not floppies.
        for name, text in (('psx.m3u', 'Game (Disc 1).cue\nGame (Disc 2).cue\n'),
                           ('chd.m3u', 'Game.chd\n'),
                           ('mixed.m3u', 'Game (Disk 1).dim\nGame (Disc 2).cue\n'),
                           ('empty.m3u', '# nothing\n')):
            with self.subTest(name), self.assertRaisesRegex(UnsupportedConsoleError, 'not an X68000 disk set'):
                profile_for_path(self.make(name, text), None)

    def test_a_playlist_that_names_msx_disks_stays_the_msx2_plus(self):
        marked = self.make('msx.m3u', '# Retro-Recomp system: msx2plus\nQuest (Disk 1).dsk\n')
        self.assertEqual(profile_for_path(marked, None).id, 'msx2plus')


if __name__ == '__main__':
    unittest.main()
