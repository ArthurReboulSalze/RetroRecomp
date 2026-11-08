"""The desktop autostart picks the only program of disk 1 from its root directory, on authored disk images written by the test
(a boot sector, two FATs and a root directory of a few entries: no game, no disk of anyone, no TOS)."""
import struct
import unittest

from retrorecomp import atarist_disk


def entry(name: str, ext: str, attr: int = 0, size: int = 1000) -> bytes:
    return name.ljust(8).encode() + ext.ljust(3).encode() + bytes([attr]) + bytes(14) + struct.pack('<HI', 2, size)


def st_image(entries: list[bytes], spt: int = 9, heads: int = 2) -> bytes:
    """An 80-track ST image whose boot sector has a BPB (512-byte sectors, 2 per cluster, 1 reserved, 2 FATs of 5 sectors,
    112 root entries) and whose root directory holds the given entries."""
    boot = bytearray(512)
    boot[11:19] = struct.pack('<HBHBH', 512, 2, 1, 2, 112)
    boot[19:21] = struct.pack('<H', 80 * spt * heads)
    boot[22:28] = struct.pack('<HHH', 5, spt, heads)
    disk = bytearray(80 * spt * heads * 512)
    disk[:512] = boot
    root = (1 + 2 * 5) * 512
    for n, e in enumerate(entries):
        disk[root + 32 * n:root + 32 * (n + 1)] = e
    return bytes(disk)


def msa_image(st: bytes, spt: int = 9, heads: int = 2) -> bytes:
    """The same disk as an MSA image, every track run-length encoded when it saves room."""
    out = bytearray(b'\x0e\x0f' + struct.pack('>HHHH', spt, heads - 1, 0, 79))
    size = spt * 512
    for t in range(80 * heads):
        track = st[t * size:(t + 1) * size]
        if track == bytes(size):
            packed = b'\xe5\x00' + struct.pack('>H', size)
        else:
            packed = track
        out += struct.pack('>H', len(packed)) + packed
    return bytes(out)


class AutostartTests(unittest.TestCase):
    def test_the_only_program_is_started(self):
        disk = st_image([entry('GAME', 'DAT'), entry('PLAY', 'PRG'), entry('DESKTOP', 'INF')])
        self.assertEqual(atarist_disk.autostart_program(disk, '.st')[0], 'A:\\PLAY.PRG')
        self.assertEqual(atarist_disk.autostart_program(msa_image(disk), 'msa')[0], 'A:\\PLAY.PRG')

    def test_installers_hidden_files_and_deleted_entries_are_not_programs_to_open(self):
        deleted = b'\xe5' + entry('OLD', 'PRG')[1:]
        disk = st_image([entry('INSTALL', 'PRG'), entry('SECRET', 'PRG', attr=0x02), deleted, entry('GAME', 'APP')])
        self.assertEqual(atarist_disk.autostart_program(disk, 'st')[0], 'A:\\GAME.APP')

    def test_two_programs_an_auto_folder_or_no_file_system_mean_no_autostart(self):
        two = st_image([entry('ONE', 'PRG'), entry('TWO', 'TOS')])
        self.assertEqual(atarist_disk.autostart_program(two, 'st'), (None, 'disk 1 holds 2 programs to open (exactly one is needed)'))
        auto = st_image([entry('AUTO', '', attr=0x10), entry('GAME', 'PRG')])
        self.assertIsNone(atarist_disk.autostart_program(auto, 'st')[0])
        self.assertIn('AUTO folder', atarist_disk.autostart_program(auto, 'st')[1])
        self.assertIsNone(atarist_disk.autostart_program(bytes(737280), 'st')[0])
        self.assertIsNone(atarist_disk.autostart_program(b'not a disk', 'ipf')[0])
        self.assertIn('STX', atarist_disk.autostart_program(bytes(1000), 'stx')[1])

    def test_a_one_sided_disk_is_read_by_its_own_geometry(self):
        disk = st_image([entry('PLAY', 'PRG')], spt=10, heads=1)
        self.assertEqual(atarist_disk.autostart_program(disk, 'st')[0], 'A:\\PLAY.PRG')


if __name__ == '__main__':
    unittest.main()
