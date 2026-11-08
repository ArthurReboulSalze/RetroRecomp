"""The Nintendo 64 profile and its input reader, on synthetic images (no ROM byte: a header written for the test)."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from retrorecomp import n64
from retrorecomp.core import ConversionError
from retrorecomp.systems import get_profile


def image(code: bytes = b'NXXE', size: int = 0x101000, entry: int = 0x80000400) -> bytes:
    """A big-endian cartridge image of `size` bytes: the PI header word, the entry point, a name and a game code."""
    data = bytearray(size)
    data[0:4] = bytes.fromhex('80371240')
    data[8:12] = entry.to_bytes(4, 'big')
    data[0x10:0x18] = bytes(range(1, 9))
    data[0x20:0x34] = b'RETRO RECOMP TEST   '
    data[0x3B:0x3F] = code
    data[0x3F] = 2
    for offset in range(0x40, size, 997):
        data[offset] = offset & 0xFF
    return bytes(data)


def as_order(big: bytes, order: str) -> bytes:
    if order == 'z64':
        return big
    out = bytearray(big)
    if order == 'v64':
        out[0::2], out[1::2] = big[1::2], big[0::2]
    else:
        out[0::4], out[1::4], out[2::4], out[3::4] = big[3::4], big[2::4], big[1::4], big[0::4]
    return bytes(out)


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='n64-test-'))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def write(self, name, data):
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_the_three_byte_orders_are_one_game(self):
        big = image()
        identities = set()
        for order, suffix in (('z64', '.z64'), ('v64', '.v64'), ('n64', '.n64')):
            rom = n64.read_input(self.write('game' + suffix, as_order(big, order)))
            self.assertEqual(rom.order, order)
            self.assertEqual(rom.data(), big)
            identities.add(rom.sha256)
        self.assertEqual(identities, {hashlib.sha256(big).hexdigest()})

    def test_the_order_comes_from_the_content_not_the_name(self):
        # A byte-swapped image named .n64 (common in dumps) is read as what it is.
        rom = n64.read_input(self.write('swapped.n64', as_order(image(), 'v64')))
        self.assertEqual(rom.order, 'v64')

    def test_the_header(self):
        rom = n64.read_input(self.write('a.z64', image(b'NSMP')))
        header = rom.header
        self.assertEqual((header.name, header.game_code, header.country, header.revision), ('RETRO RECOMP TEST', 'NSMP', 'P', 2))
        self.assertTrue(header.pal)
        self.assertEqual(header.entry_point, 0x80000400)
        self.assertFalse(n64.read_input(self.write('b.z64', image(b'NSME'))).header.pal)
        self.assertEqual(rom.metadata()['region'], 'PAL')

    def test_video_mode_follows_the_country(self):
        self.assertEqual(n64.video_mode(self.write('p.z64', image(b'NZLD'))), 'pal')
        self.assertEqual(n64.video_mode(self.write('n.z64', image(b'NZLJ'))), 'ntsc')
        self.assertEqual(n64.video_mode(self.write('x.z64', b'not a cartridge')), 'ntsc')

    def test_refusals(self):
        for name, data in (('short.z64', image()[:0x1000]), ('word.z64', b'\0' * 0x101000),
                           ('odd.z64', image() + b'\0\0'), ('entry.z64', image(entry=0x12345678))):
            path = self.write(name, data)
            with self.assertRaises(ConversionError, msg=name):
                n64.read_input(path)
            self.assertFalse(n64.recognise(path), name)

    def test_a_changed_file_is_refused_when_read_again(self):
        path = self.write('c.z64', image())
        rom = n64.read_input(path)
        path.write_bytes(image(b'NABE'))
        with self.assertRaises(ConversionError):
            rom.data()


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='n64-profile-'))
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.profile = get_profile('n64')

    def test_identity_of_the_profile(self):
        p = self.profile
        self.assertEqual((p.status, p.linux, p.export_folder, p.quick_state_family), ('experimental', 'witnessed', 'Nintendo 64', 'n64'))
        self.assertEqual(p.feedback_kinds, frozenset({25}))
        self.assertEqual(p.path_spec.order, 14)
        self.assertEqual([(cpu.arch, cpu.role) for cpu in p.cpus], [('vr4300', 'main')])
        self.assertEqual(p.video_modes, ('ntsc', 'pal'))

    def test_a_rom_file_is_claimed_by_its_content_only(self):
        rom = self.folder / 'Zelda64.rom'
        rom.write_bytes(image(b'CZLE'))
        other = self.folder / 'other.rom'
        other.write_bytes(b'\0' * 0x200000)
        if self.profile.available():
            self.assertIs(self.profile.identify_path(rom, '.rom', None), self.profile)
        self.assertIsNone(self.profile.identify_path(other, '.rom', None))
        self.assertIsNone(self.profile.identify_path(rom, '.bin', None))

    def test_the_converter_files_are_shipped(self):
        self.assertTrue(n64.converter_available())


if __name__ == '__main__':
    unittest.main()
