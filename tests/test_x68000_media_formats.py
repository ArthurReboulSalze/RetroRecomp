"""X68000 floppy images are recognised by their content: D88, DIM with or without its signature, raw 2HD (authored bytes only).

The disks here are pseudo-random bytes in the published layouts of the formats; no game, no firmware.
"""
import hashlib
import inspect
import random
import tempfile
import unittest
from pathlib import Path

from retrorecomp.x68000_media import (
    CGROM_BYTES, D88_HEADER_BYTES, IPL_BYTES, XDF_BYTES, build_manifest, identify_disk,
)
from tools.x68000_reference import _checked_copy

TRACK = 8 * 1024
RECORD = 16 + 1024


def raw_disk(seed=7):
    return random.Random(seed).randbytes(XDF_BYTES)


def d88_disk(raw, *, order=range(1, 9), media=0x20, protect=0x10 * 0, mutate=None, tracks=154, name=b'AUTHORED'):
    """The D88 form of a raw 2HD disk: 0x2B0-byte header, then each track's eight sector records (16-byte header + data)."""
    header = bytearray(D88_HEADER_BYTES)
    header[:len(name)] = name
    header[0x1A] = protect
    header[0x1B] = media
    body = bytearray()
    for track in range(tracks):
        header[0x20 + 4 * track:0x24 + 4 * track] = (D88_HEADER_BYTES + len(body)).to_bytes(4, 'little')
        for number in order:
            data = raw[(track * 8 + number - 1) * 1024:(track * 8 + number) * 1024]
            record = bytearray([track // 2, track % 2, number, 3]) + (8).to_bytes(2, 'little') + bytes([0, 0, 0]) + bytes(5) + (1024).to_bytes(2, 'little')
            if mutate:
                mutate(track, number, record)
            body += record + data
    header[0x1C:0x20] = (D88_HEADER_BYTES + len(body)).to_bytes(4, 'little')
    return bytes(header) + bytes(body)


def dim_disk(raw, signature=True):
    header = bytearray(256)
    header[0] = 0
    for track in range(154):
        header[1 + track] = 1
    if signature:
        header[171:186] = b'DIFC HEADER\0\0\0\0'
    return bytes(header) + raw


class FloppyFormatTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.raw = raw_disk()

    def write(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path

    def test_a_standard_d88_is_stored_as_the_raw_disk_it_describes(self):
        image = identify_disk(self.write('game.d88', d88_disk(self.raw)))
        self.assertEqual((image.format, image.size, image.sector_bytes, image.sectors_per_track), ('xdf', XDF_BYTES, 1024, 8))
        self.assertEqual(image.present_tracks, tuple(range(154)))
        self.assertEqual(image.content(), self.raw)
        self.assertEqual(image.sha256, hashlib.sha256(self.raw).hexdigest())

    def test_a_d88_and_an_xdf_of_the_same_disk_are_the_same_game(self):
        ipl, cgrom = self.write('iplrom.dat', b'I' * IPL_BYTES), self.write('cgrom.dat', b'C' * CGROM_BYTES)
        from_d88 = build_manifest([self.write('a.d88', d88_disk(self.raw))], ipl, cgrom)
        from_xdf = build_manifest([self.write('a.xdf', self.raw)], ipl, cgrom)
        self.assertEqual(from_d88.sha256, from_xdf.sha256)
        self.assertEqual(from_d88.media[0].local_record()['stored_from'], 'd88')
        self.assertNotIn('stored_from', from_xdf.media[0].local_record())

    def test_sectors_stored_in_another_physical_order_are_put_back_in_sector_order(self):
        image = identify_disk(self.write('interleaved.d88', d88_disk(self.raw, order=(1, 5, 2, 6, 3, 7, 4, 8))))
        self.assertEqual(image.content(), self.raw)

    def test_the_name_never_decides_the_format(self):
        d88 = d88_disk(self.raw)
        for name, data, expected in (('d88-as.xdf', d88, 'xdf'), ('d88-as.dim', d88, 'xdf'), ('raw-as.dim', self.raw, 'xdf'),
                                     ('blank.dim', bytes(XDF_BYTES), 'xdf'), ('dim-as.xdf', dim_disk(self.raw), 'dim'),
                                     ('dim.hdm', dim_disk(self.raw), 'dim'), ('raw.2hd', self.raw, 'xdf'), ('raw.dup', self.raw, 'xdf')):
            with self.subTest(name=name):
                self.assertEqual(identify_disk(self.write(name, data)).format, expected)

    def test_a_dim_without_its_signature_is_still_a_dim(self):
        image = identify_disk(self.write('plain.dim', dim_disk(self.raw, signature=False)))
        self.assertEqual((image.format, image.size), ('dim', 256 + XDF_BYTES))
        self.assertIsNone(image.converted)

    def test_a_d88_that_is_not_the_standard_2hd_layout_is_refused_with_its_reason(self):
        def deleted(track, number, record):
            record[7] = 0x10 if (track, number) == (3, 2) else record[7]

        def failing(track, number, record):
            record[8] = 0xB0 if (track, number) == (3, 2) else record[8]

        def wrong_size(track, number, record):
            record[3] = 2 if (track, number) == (10, 8) else record[3]

        cases = {'deleted mark': d88_disk(self.raw, mutate=deleted), 'error status': d88_disk(self.raw, mutate=failing),
                 'another sector size': d88_disk(self.raw, mutate=wrong_size), 'a 2DD disk': d88_disk(self.raw, media=0x10),
                 'a missing track': d88_disk(self.raw, tracks=153), 'a repeated sector': d88_disk(self.raw, order=(1, 1, 2, 3, 4, 5, 6, 7))}
        for label, data in cases.items():
            with self.subTest(label), self.assertRaisesRegex(ValueError, 'D88'):
                identify_disk(self.write('protected.d88', data))

    def test_a_d88_whose_size_field_is_wrong_and_other_files_are_not_images(self):
        broken = bytearray(d88_disk(self.raw))
        broken[0x1C] ^= 1
        for name, data in (('size.d88', bytes(broken)), ('empty.d88', b''), ('short.d88', b'D88' * 10),
                           ('random.dim', random.Random(3).randbytes(5000)), ('big.xdf', bytes(XDF_BYTES + 5))):
            with self.subTest(name=name), self.assertRaises(ValueError):
                identify_disk(self.write(name, data))
        with self.assertRaisesRegex(ValueError, 'not executed'):
            identify_disk(self.write('script.bat', b'echo no'))

    def test_a_stored_equivalent_is_staged_from_its_bytes_and_checked_against_its_hash(self):
        image = identify_disk(self.write('game.d88', d88_disk(self.raw)))
        destination = self.root / 'stage' / 'disk-01.xdf'
        _checked_copy(image.converted, destination, image.sha256)
        self.assertEqual(destination.read_bytes(), self.raw)
        with self.assertRaisesRegex(ValueError, 'changed while copying'):
            _checked_copy(image.converted, self.root / 'stage' / 'disk-02.xdf', '0' * 64)
        self.assertFalse((self.root / 'stage' / 'disk-02.xdf').exists())

    def test_the_conversion_embeds_the_stored_bytes_not_the_file(self):
        from retrorecomp import x68000_conversion
        self.assertIn('disk.content()', inspect.getsource(x68000_conversion.payload))


if __name__ == '__main__':
    unittest.main()
