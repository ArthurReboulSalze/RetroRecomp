"""The Amstrad CPC disk reader (retrorecomp/cpc_disk.py) on images built here: no disk of a game."""
from __future__ import annotations

from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from retrorecomp import cpc_disk


def header(kind: int) -> bytes:
    """A 128-byte AMSDOS header of the given type (0 BASIC, 2 binary) with its checksum."""
    record = bytearray(128)
    record[1:9] = b'PROGRAM '
    record[0x12] = kind
    record[0x40] = 1
    checksum = sum(record[:0x43]) & 0xFFFF
    record[0x43:0x45] = struct.pack('<H', checksum)
    return bytes(record)


def entry(name: str, ext: str, block: int, hidden: bool = False, user: int = 0) -> bytes:
    raw = bytearray(32)
    raw[0] = user
    raw[1:9] = name.ljust(8).encode()
    raw[9:12] = ext.ljust(3).encode()
    if hidden:
        raw[10] |= 0x80
    raw[15] = 8
    raw[16] = block
    return bytes(raw)


def image(files=(), extended=False, first=0xC1, cylinders=40, weak_track=None, lengths=True) -> bytes:
    """A one-sided AMSDOS image of the given format, its directory holding `files` = ((name, ext, type, hidden), ...):
    each file's header in the block after the directory (blocks 2, 3, ...)."""
    directory_cylinder = {0xC1: 0, 0x41: 2}[first]
    sectors = {}

    def put(logical: int, data: bytes):
        sectors[(directory_cylinder + logical // 9, first + logical % 9)] = data.ljust(512, b'\0')

    dirent = b''.join(entry(name, ext, 2 + k, hidden) for k, (name, ext, _, hidden) in enumerate(files))
    dirent = dirent.ljust(2048, b'\xe5')
    for k in range(4):
        put(k, dirent[k * 512:(k + 1) * 512])
    for k, (_, _, kind, _) in enumerate(files):
        put((2 + k) * 2, header(kind) if kind is not None else b'10 PRINT "HI"\r\n')
    disk = bytearray(256)
    disk[:34] = (b'EXTENDED CPC DSK File\r\nDisk-Info\r\n' if extended else b'MV - CPCEMU Disk-File\r\nDisk-Info\r\n')
    disk[0x30], disk[0x31] = cylinders, 1
    track_size = 256 + 9 * 512
    if not extended:
        disk[0x32:0x34] = struct.pack('<H', track_size)
    for t in range(cylinders):
        size = track_size + (2 * 512 if t == weak_track else 0)
        if extended:
            disk[0x34 + t] = size >> 8
        block = bytearray(256)
        block[:12] = b'Track-Info\r\n'
        block[0x10], block[0x14], block[0x15], block[0x16], block[0x17] = t, 2, 9, 0x4E, 0xE5
        data = b''
        for s in range(9):
            r = first + s
            copies = 3 if t == weak_track and s == 0 else 1
            stored = 512 * copies
            info = struct.pack('<6BH', t, 0, r, 2, 0x20 if copies > 1 else 0, 0x20 if copies > 1 else 0,
                               stored if extended and lengths else 0)
            block[0x18 + 8 * s:0x20 + 8 * s] = info
            data += sectors.get((t, r), bytes([t, r]) * 256) * copies
        disk += block + data
    return bytes(disk)


class ReaderTests(unittest.TestCase):
    def test_a_standard_image(self):
        disk = cpc_disk.disk_from_bytes(Path('game.dsk'), '', image((('DISC', 'BAS', 0, False),)))
        self.assertEqual((disk.extended, disk.cylinders, disk.sides, disk.format, disk.sector_count), (False, 40, 1, 'data', 360))
        self.assertEqual(disk.size, 256 + 40 * (256 + 9 * 512))
        self.assertEqual(disk.features()['odd_tracks'], 0)
        self.assertEqual(disk.run_command, 'RUN"DISC')

    def test_an_extended_image_with_a_weak_sector(self):
        disk = cpc_disk.disk_from_bytes(Path('game.dsk'), '', image((('GAME', 'BAS', 0, False),), extended=True, weak_track=5))
        sector = disk.tracks[5].sectors[0]
        self.assertEqual((sector.copies, sector.stored, sector.weak), (3, 512, True))
        features = disk.features()
        self.assertEqual((features['weak_sectors'], features['odd_tracks'], features['error_sectors']), (1, 1, 1))
        self.assertEqual(disk.tracks[6].sectors[0].offset - disk.tracks[5].sectors[0].offset, 256 + 11 * 512)

    def test_an_early_extended_image_without_lengths(self):
        disk = cpc_disk.disk_from_bytes(Path('game.dsk'), '', image(extended=True, lengths=False))
        self.assertTrue(all(sector.stored == 512 for track in disk.tracks for sector in track.sectors))

    def test_refused_images(self):
        good = image()
        for bad, reason in ((b'NOT A DISK' + good[10:], 'signature'), (good[:-1], 'past the end'),
                            (good[:0x30] + b'\0' + good[0x31:], 'cylinders')):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                cpc_disk.disk_from_bytes(Path('x.dsk'), '', bad)

    def test_the_system_format_and_cpm(self):
        disk = cpc_disk.disk_from_bytes(Path('cpm.dsk'), '', image(first=0x41))
        self.assertEqual((disk.format, disk.files, disk.run_command), ('system', (), '|CPM'))

    def test_files_from_a_zip_and_their_sha(self):
        data = image((('BOMB', '', 0, False), ('BJCODE', 'BIN', 2, False)))
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / 'Game (Europe).zip'
            with zipfile.ZipFile(archive, 'w') as bundle:
                bundle.writestr('Game (E).dsk', data)
                bundle.writestr('readme.txt', 'x')
            self.assertTrue(cpc_disk.looks_like_cpc(archive))
            disk = cpc_disk.read_disk(archive)
            self.assertEqual((disk.member, disk.size), ('Game (E).dsk', len(data)))
            import hashlib
            self.assertEqual(disk.sha256, hashlib.sha256(data).hexdigest())
            msx = Path(folder) / 'msx.dsk'
            msx.write_bytes(bytes(368640))
            self.assertFalse(cpc_disk.looks_like_cpc(msx))
            with zipfile.ZipFile(Path(folder) / 'two.zip', 'w') as bundle:
                bundle.writestr('a.dsk', data)
                bundle.writestr('b.dsk', data)
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                cpc_disk.read_disk(Path(folder) / 'two.zip')


class StartCommandTests(unittest.TestCase):
    def start(self, files, **options):
        disk = cpc_disk.disk_from_bytes(Path('g.dsk'), '', image(files, **options))
        return disk.run_command, disk.candidates

    def test_the_rules_in_order(self):
        # a DISC program wins
        self.assertEqual(self.start((('GAME', 'BAS', 0, False), ('DISC', 'BIN', 2, True)))[0], 'RUN"DISC')
        # one command, whatever the extensions (RUN"GAME finds GAME.BAS before GAME.BIN)
        self.assertEqual(self.start((('GAME', 'BAS', 0, False), ('GAME', 'BIN', 2, False)))[0], 'RUN"GAME')
        # the one BASIC loader among binaries
        self.assertEqual(self.start((('BJCODE', 'BIN', 2, False), ('BOMB', '', 0, False), ('BJSCREEN', 'BIN', 2, False)))[0], 'RUN"BOMB')
        # the name the others start with
        self.assertEqual(self.start((('GRYZOR', 'BIN', 2, False), ('GRYZOR1', 'BIN', 2, False), ('GRYZOR2', 'BIN', 2, False)))[0],
                         'RUN"GRYZOR')
        # the shown programs first: a hidden loader does not compete
        self.assertEqual(self.start((('LOAD', 'BAS', 0, False), ('PART', 'BAS', 0, True)))[0], 'RUN"LOAD')

    def test_undecided_never_guesses(self):
        command, candidates = self.start((('ALPHA', 'BIN', 2, False), ('BETA', 'BIN', 2, False)))
        self.assertIsNone(command)
        self.assertEqual(candidates, ('RUN"ALPHA', 'RUN"BETA'))
        # two BASIC programs and a headerless file: still undecided
        command, _ = self.start((('ONE', 'BAS', 0, False), ('TWO', 'BAS', 0, False), ('THREE', '', None, False)))
        self.assertIsNone(command)

    def test_a_header_needs_its_checksum(self):
        record = bytearray(header(0))
        self.assertEqual(cpc_disk._header_type(bytes(record)), 'basic')
        record[0x43] ^= 1
        self.assertIsNone(cpc_disk._header_type(bytes(record)))
        self.assertIsNone(cpc_disk._header_type(bytes(128)))


if __name__ == '__main__':
    unittest.main()
