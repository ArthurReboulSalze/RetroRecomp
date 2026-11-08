"""PlayStation disc and BIOS readers on synthetic images built here (no game, no BIOS byte)."""
import hashlib
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from retrorecomp import psx_bios, psx_disc

SECTOR, USER = 2352, 2048


def bcd(n):
    return (n // 10) << 4 | n % 10


def msf(lba):
    lba += 150
    return lba // 4500, lba // 75 % 60, lba % 75


def raw_sector(lba, user, form2=False):
    m, s, f = msf(lba)
    head = psx_disc.SYNC + bytes((bcd(m), bcd(s), bcd(f), 2))
    sub = bytes((0, 0, 0x28 if form2 else 0x08, 0)) * 2
    body = user.ljust(2324 if form2 else USER, b'\0')
    return (head + sub + body).ljust(SECTOR, b'\0')


def dir_record(name, lba, size, directory=False):
    n = name.encode()
    length = 33 + len(n) + (len(n) + 1) % 2
    rec = bytearray(length)
    rec[0] = length
    struct.pack_into('<I', rec, 2, lba)
    struct.pack_into('>I', rec, 6, lba)
    struct.pack_into('<I', rec, 10, size)
    struct.pack_into('>I', rec, 14, size)
    rec[25] = 2 if directory else 0
    rec[32] = len(n)
    rec[33:33 + len(n)] = n
    return bytes(rec)


def psexe(pc=0x80010000, size=0x800):
    head = bytearray(0x800)
    head[:8] = b'PS-X EXE'
    struct.pack_into('<4I', head, 0x10, pc, 0, 0x80010000, size)
    struct.pack_into('<2I', head, 0x30, 0x801FFFF0, 0)
    head[0x4C:0x4C + 50] = b'Sony Computer Entertainment Inc. for Europe area'.ljust(50, b'\0')
    return bytes(head) + bytes(range(256)) * (size // 256)


def user_sectors(boot='SLES_123.45', licence=b'          Licensed  by          Sony Computer Entertainment Euro pe   '):
    """The 2,048-byte sectors of a small PlayStation data track: licence at 4, PVD at 16, root at 18, files from 20."""
    exe = psexe()
    cnf = f'BOOT = cdrom:\\{boot};1\r\nTCB = 4\r\n'.encode()
    files = [('SYSTEM.CNF;1', cnf), (boot + ';1', exe)]
    sectors = {4: licence}
    lba = 20
    records = [dir_record('\0', 18, USER, True), dir_record('\1', 18, USER, True)]
    for name, data in files:
        records.append(dir_record(name, lba, len(data)))
        for i in range(0, len(data), USER):
            sectors[lba] = data[i:i + USER]
            lba += 1
    pvd = bytearray(USER)
    pvd[0] = 1
    pvd[1:6] = b'CD001'
    pvd[8:40] = b'PLAYSTATION'.ljust(32)
    pvd[40:72] = b'TESTDISC'.ljust(32)
    pvd[156:190] = dir_record('\0', 18, USER, True)
    sectors[16] = bytes(pvd)
    sectors[18] = b''.join(records)
    count = max(lba, 40)
    return [sectors.get(i, b'') for i in range(count)], exe


def audio_track(frames):
    return (bytes((i * 7) & 0xff for i in range(256)) * (frames * SECTOR // 256 + 1))[:frames * SECTOR]


class DiscReaders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.user, self.exe = user_sectors()
        self.raw = b''.join(raw_sector(i, u) for i, u in enumerate(self.user))
        self.audio = audio_track(20)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, disc, audio=True):
        ident = psx_disc.identity(disc)
        self.assertEqual(ident.serial, 'SLES-12345')
        self.assertEqual(ident.boot, 'SLES_123.45')
        self.assertEqual(ident.region, 'pal')
        self.assertEqual(ident.system_id, 'PLAYSTATION')
        self.assertEqual(ident.exe_sha256, hashlib.sha256(self.exe).hexdigest())
        self.assertEqual(ident.exe.pc, 0x80010000)
        if audio:
            self.assertEqual(disc.tracks[1].mode, 'AUDIO')
            self.assertEqual(disc.raw(disc.tracks[1].start), self.audio[:SECTOR])
        return ident

    def test_cue_single_bin_with_audio(self):
        (self.dir / 'g.bin').write_bytes(self.raw + self.audio)
        frames = len(self.user)
        m, s, f = frames // 4500, frames // 75 % 60, frames % 75
        (self.dir / 'g.cue').write_text(
            'FILE "g.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
            f'  TRACK 02 AUDIO\n    INDEX 01 {m:02d}:{s:02d}:{f:02d}\n', encoding='ascii')
        disc = psx_disc.open_disc(self.dir / 'g.cue')
        self.check(disc)
        self.assertEqual(disc.leadout, frames + 20)
        disc.close()

    def test_cue_one_file_per_track_and_pregap(self):
        (self.dir / 'g (Track 1).bin').write_bytes(self.raw)
        (self.dir / 'g (Track 2).bin').write_bytes(self.audio)
        (self.dir / 'g.cue').write_text(
            'FILE "g (Track 1).bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
            'FILE "g (Track 2).bin" BINARY\n  TRACK 02 AUDIO\n    PREGAP 00:02:00\n    INDEX 01 00:00:00\n', encoding='ascii')
        disc = psx_disc.open_disc(self.dir / 'g.cue')
        self.check(disc)
        self.assertEqual(disc.tracks[1].start, len(self.user) + 150)
        disc.close()

    def test_renamed_bin_beside_a_single_file_sheet(self):
        (self.dir / 'Game.bin').write_bytes(self.raw)
        (self.dir / 'Game.cue').write_text('FILE "SLES-12345.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')
        self.check(psx_disc.open_disc(self.dir / 'Game.cue'), audio=False)

    def test_bare_bin_and_iso(self):
        (self.dir / 'b.bin').write_bytes(self.raw)
        self.check(psx_disc.open_disc(self.dir / 'b.bin'), audio=False)
        (self.dir / 'i.iso').write_bytes(b''.join(u.ljust(USER, b'\0') for u in self.user))
        disc = psx_disc.open_disc(self.dir / 'i.iso')
        self.assertEqual(disc.container, 'iso')
        self.assertIsNone(disc.raw(0))
        self.check(disc, audio=False)

    def test_clonecd_with_subchannel(self):
        frames = len(self.user)
        (self.dir / 'c.img').write_bytes(self.raw + self.audio)
        sub = bytearray((frames + 20) * 96)
        for i in range(frames + 20):
            sub[i * 96 + 12:i * 96 + 24] = bytes((0x41, 1, 1)) + bytes(9) if i < frames else bytes((0x01, 2, 1)) + bytes(9)
        (self.dir / 'c.sub').write_bytes(bytes(sub))
        (self.dir / 'c.ccd').write_text(
            '[CloneCD]\nVersion=3\n[Disc]\nTocEntries=4\n'
            '[Entry 0]\nPoint=0xa2\nControl=0x04\nPLBA=%d\n' % (frames + 20) +
            '[Entry 1]\nPoint=0x01\nControl=0x04\nPLBA=0\n'
            '[Entry 2]\nPoint=0x02\nControl=0x00\nPLBA=%d\n' % frames +
            '[TRACK 1]\nMODE=2\nINDEX 1=0\n[TRACK 2]\nMODE=0\nINDEX 1=%d\n' % frames)
        disc = psx_disc.open_disc(self.dir / 'c.ccd')
        self.check(disc)
        self.assertEqual(disc.subq(0)[:3], bytes((0x41, 1, 1)))
        self.assertEqual(disc.subq(frames)[:3], bytes((0x01, 2, 1)))
        disc.close()

    def pbp_image(self, discs, signed=False):
        """An unsigned PS1 Classics EBOOT holding `discs` copies of the test disc (data + one audio track)."""
        image = self.raw + self.audio
        frames = len(image) // SECTOR
        pad = (-frames) % 16
        image += bytes(pad * SECTOR)
        blobs, table = [], bytearray(0x100000 - 0x4000)
        offset = 0
        for i in range(len(image) // psx_disc.PBP_BLOCK):
            block = image[i * psx_disc.PBP_BLOCK:(i + 1) * psx_disc.PBP_BLOCK]
            c = zlib.compressobj(9, zlib.DEFLATED, -15)
            data = c.compress(block) + c.flush() if i % 2 == 0 else block   # stored blocks too
            struct.pack_into('<IH', table, i * 32, offset, len(data))
            blobs.append(data)
            offset += len(data)
        toc = bytearray(10 * 102)

        def entry(i, kind, point, index1):
            m, s, f = msf(index1)
            toc[i * 10:(i + 1) * 10] = bytes((kind, 0, point, 0, 0, 0, 0, bcd(m), bcd(s), bcd(f)))
        entry(0, 0x41, 0xA0, 0)
        toc[1 * 10 + 7] = bcd(2)
        entry(2, 0x41, 0xA2, frames)
        entry(3, 0x41, 1, 0)
        entry(4, 0x01, 2, len(self.user))
        iso = bytearray(0x100000)
        iso[:12] = b'PSISOIMG0000'
        if signed:
            iso[0x400:0x404] = b'\0PGD'
        iso[0x800:0x800 + len(toc)] = toc
        iso[0x4000:0x4000 + len(table)] = table
        iso = bytes(iso) + b''.join(blobs)
        if discs == 1:
            psar = iso
        else:
            head = bytearray(0x400)
            head[:16] = b'PSTITLEIMG000000'
            psar = bytearray(head)
            offsets = []
            for d in range(discs):
                offsets.append(len(psar))
                psar += iso
            struct.pack_into('<%dI' % discs, psar, 0x200, *offsets)
            psar = bytes(psar)
        header = bytearray(0x28)
        header[:4] = b'\0PBP'
        struct.pack_into('<I', header, 0x24, 0x28)
        return bytes(header) + psar

    def test_pbp_single_and_multi_disc(self):
        (self.dir / 'one.pbp').write_bytes(self.pbp_image(1))
        disc = psx_disc.open_disc(self.dir / 'one.pbp')
        self.check(disc)
        self.assertEqual(disc.raw(5), self.raw[5 * SECTOR:6 * SECTOR])
        disc.close()
        (self.dir / 'three.pbp').write_bytes(self.pbp_image(3))
        ids = psx_disc.describe(self.dir / 'three.pbp')
        self.assertEqual([i.disc_index for i in ids], [0, 1, 2])
        self.assertTrue(all(i.disc_count == 3 for i in ids))

    def test_signed_pbp_is_refused(self):
        (self.dir / 's.pbp').write_bytes(self.pbp_image(1, signed=True))
        with self.assertRaisesRegex(psx_disc.DiscError, 'signed'):
            psx_disc.open_disc(self.dir / 's.pbp')

    def test_same_dump_same_digest_across_containers(self):
        (self.dir / 'g.bin').write_bytes(self.raw + self.audio)
        frames = len(self.user)
        (self.dir / 'g.cue').write_text(
            'FILE "g.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
            f'  TRACK 02 AUDIO\n    INDEX 01 00:00:{frames:02d}\n')
        (self.dir / 'p.pbp').write_bytes(self.pbp_image(1))
        cue = psx_disc.open_disc(self.dir / 'g.cue')
        pbp = psx_disc.open_disc(self.dir / 'p.pbp')
        self.assertEqual(cue.geometry(), pbp.geometry())
        self.assertEqual(cue.digest(), pbp.digest())

    def test_m3u_playlist(self):
        (self.dir / 'a.bin').write_bytes(self.raw)
        (self.dir / 'b.bin').write_bytes(self.raw)
        (self.dir / 'g.m3u').write_text('# discs\na.bin\nb.bin\n')
        ids = psx_disc.describe(self.dir / 'g.m3u')
        self.assertEqual(len(ids), 2)
        self.assertEqual(ids[1].disc_index, 1)

    def test_not_a_disc(self):
        (self.dir / 'x.bin').write_bytes(bytes(SECTOR * 4))
        with self.assertRaises(psx_disc.DiscError):
            psx_disc.open_disc(self.dir / 'x.bin')
        (self.dir / 'audio.cue').write_text('FILE "x.bin" BINARY\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n')
        with self.assertRaisesRegex(psx_disc.DiscError, 'audio'):
            psx_disc.identity(psx_disc.open_disc(self.dir / 'audio.cue'))

    def test_serials(self):
        self.assertEqual(psx_disc.serial_of('SLUS_005.94'), 'SLUS-00594')
        self.assertEqual(psx_disc.serial_of('DATA\\SCES_008.67'), 'SCES-00867')
        self.assertIsNone(psx_disc.serial_of('PSX.EXE'))
        self.assertEqual(psx_disc.boot_path({'BOOT': 'cdrom:\\\\SLPS_018.00;1 1'}), 'SLPS_018.00')


class BiosIdentity(unittest.TestCase):
    def test_sizes_unknown_and_openbios(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'short.bin').write_bytes(bytes(1000))
            with self.assertRaisesRegex(psx_bios.BiosError, 'bytes'):
                psx_bios.identify(tmp / 'short.bin')
            (tmp / 'unknown.bin').write_bytes(bytes(psx_bios.BIOS_BYTES))
            with self.assertRaisesRegex(psx_bios.BiosError, 'not a known'):
                psx_bios.identify(tmp / 'unknown.bin')
            blob = bytearray(psx_bios.BIOS_BYTES)
            blob[0x78:0x80] = b'OpenBIOS'
            (tmp / 'openbios.bin').write_bytes(bytes(blob))
            b = psx_bios.identify(tmp / 'openbios.bin')
            self.assertTrue(b.free)
            self.assertIsNone(psx_bios.choose([tmp], 'pal'))   # a free BIOS is never chosen for a region

    def test_table(self):
        self.assertEqual(len(psx_bios.BY_SHA1), len(psx_bios.KNOWN))
        for region, model in psx_bios.PREFERRED.items():
            self.assertTrue(any(k.model == model and k.region == region for k in psx_bios.KNOWN))


if __name__ == '__main__':
    unittest.main()
