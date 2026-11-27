"""PlayStation discs in CHD images, on a synthetic disc built here (no game byte): the CHD and the CUE/BIN set of the same disc must
give the same identity, the same digest (the game key), the same sheet for the core and the same exported pack. The CHD is written
uncompressed by this test; the codecs themselves are libchdr's (the converter's reader, retrorecomp/chd_native.py)."""
import struct
import tempfile
import unittest
from pathlib import Path

from retrorecomp import psx, psx_disc, psx_pack
from retrorecomp.core import ConversionError

from tests.test_psx_disc import SECTOR, audio_track, raw_sector, user_sectors

FRAME = 2448
HUNK_FRAMES = 8


def write_chd(path: Path, tracks: list[tuple[str, bytes, int]]) -> None:
    """An uncompressed version 5 CHD of CD tracks: (type, the track's raw sectors from its first stored one, stored pregap frames).
    CD audio is stored big-endian, as chdman does; every track is padded to a multiple of four frames."""
    frames, records = bytearray(), []
    for number, (kind, data, stored) in enumerate(tracks, start=1):
        count = len(data) // SECTOR
        if kind == 'AUDIO':
            swapped = bytearray(data)
            swapped[0::2], swapped[1::2] = data[1::2], data[0::2]
            data = bytes(swapped)
        for i in range(count):
            frames += data[i * SECTOR:(i + 1) * SECTOR] + bytes(FRAME - SECTOR)
        frames += bytes(FRAME) * (-count % 4)
        pregap = f'PREGAP:{stored} PGTYPE:V{kind}' if stored else 'PREGAP:0 PGTYPE:MODE1'
        records.append(f'TRACK:{number} TYPE:{kind} SUBTYPE:NONE FRAMES:{count} {pregap} PGSUB:NONE POSTGAP:0'.encode() + b'\0')
    hunk_bytes = FRAME * HUNK_FRAMES
    logical = len(frames)
    frames += bytes(-len(frames) % hunk_bytes)
    hunks = len(frames) // hunk_bytes
    header_len = 124
    map_offset = header_len
    rawmap = b''.join(struct.pack('>I', 0) for _ in range(hunks))     # placeholders, set below
    meta_offset = map_offset + len(rawmap)
    meta = bytearray()
    for i, record in enumerate(records):
        following = meta_offset + len(meta) + 16 + len(record)
        last = i == len(records) - 1
        meta += b'CHT2' + struct.pack('>I', (1 << 24) | len(record)) + struct.pack('>Q', 0 if last else following) + record
    data_offset = meta_offset + len(meta)
    data_offset += -data_offset % hunk_bytes
    rawmap = b''.join(struct.pack('>I', data_offset // hunk_bytes + i) for i in range(hunks))
    header = (b'MComprHD' + struct.pack('>II', header_len, 5) + bytes(16) + struct.pack('>QQQ', logical, map_offset, meta_offset)
              + struct.pack('>II', hunk_bytes, FRAME) + bytes(60))
    assert len(header) == header_len
    blob = bytearray(header + rawmap + meta)
    blob += bytes(data_offset - len(blob))
    path.write_bytes(bytes(blob) + bytes(frames))


class ChdTwins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from retrorecomp import chd_native
        try:
            chd_native.ensure_tool(lambda _: None)
        except (ConversionError, OSError) as error:
            raise unittest.SkipTest(f'the CHD reader cannot be built here: {error}')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        user, _ = user_sectors()
        self.data = b''.join(raw_sector(i, u) for i, u in enumerate(user))
        self.frames = len(user)
        self.gap = bytes(150 * SECTOR)
        self.audio = audio_track(21)
        # The CUE/BIN set: one BIN, the audio track's two-second gap kept in it (INDEX 00).
        (self.dir / 'g.bin').write_bytes(self.data + self.gap + self.audio)
        n = self.frames
        index0, index1 = n, n + 150
        mm = lambda f: f'{f // 4500:02d}:{f // 75 % 60:02d}:{f % 75:02d}'
        (self.dir / 'g.cue').write_text('FILE "g.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n'
                                        f'  TRACK 02 AUDIO\n    INDEX 00 {mm(index0)}\n    INDEX 01 {mm(index1)}\n', encoding='ascii')
        # The CHD of the same disc, as chdman makes it from that sheet: the gap stored in track 2 (PGTYPE:V...).
        self.chd = self.dir / 'g.chd'
        write_chd(self.chd, [('MODE2_RAW', self.data, 0), ('AUDIO', self.gap + self.audio, 150)])

    def facts(self, path):
        disc = psx_disc.open_disc(path)
        try:
            ident = psx_disc.identity(disc)
            names = {id(s): f'disc1-{n}.bin' for n, s in enumerate(disc.sources, start=1)}
            return (ident.serial, ident.exe_sha256, ident.region, disc.geometry(), disc.digest(), psx_pack._cue_for(disc, names),
                    disc.raw(disc.tracks[1].start))
        finally:
            disc.close()

    def test_a_chd_and_its_cue_set_are_the_same_disc(self):
        cue, chd = self.facts(self.dir / 'g.cue'), self.facts(self.chd)
        self.assertEqual(chd, cue)
        self.assertEqual(chd[6], self.audio[:SECTOR])          # little-endian audio, as on the disc
        self.assertEqual(chd[3]['tracks'][1][2:], [self.frames + 150, 21, 150])

    def test_the_exported_pack_holds_the_same_bytes(self):
        program = self.dir / 'program.exe'
        program.write_bytes(b'MZ' + bytes(62))
        a = psx_pack.write_embedded(self.dir / 'g.cue', program, self.dir / 'a' / 'game.exe')
        b = psx_pack.write_embedded(self.chd, program, self.dir / 'b' / 'game.exe')
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_the_reference_pack_holds_the_decoded_sectors(self):
        pack = psx_pack.write_in_place(self.chd, self.dir / 'disc.rrpack')
        blob = pack.read_bytes()
        self.assertIn(self.data[:SECTOR * 4], blob)
        self.assertIn(self.audio[:SECTOR], blob)
        self.assertNotIn(str(self.chd.resolve()).encode(), blob)    # the compressed file is never named for the core

    def test_the_profile_claims_it_by_its_content(self):
        self.assertIs(psx.recognise(self.chd), True)
        other = self.dir / 'other.chd'
        write_chd(other, [('MODE1_RAW', b''.join(raw_sector(i, b'') for i in range(8)), 0)])
        self.assertIsNone(psx.recognise(other))                     # no PlayStation volume: left to the other machines
        broken = self.dir / 'broken.chd'
        broken.write_bytes(b'MComprHD' + bytes(200))
        self.assertIsNone(psx.recognise(broken))

    def test_a_track_mode_the_reader_does_not_take_is_named(self):
        odd = self.dir / 'odd.chd'
        write_chd(odd, [('MODE2_FORM1', bytes(8 * SECTOR), 0)])
        with self.assertRaisesRegex(psx_disc.DiscError, 'MODE2_FORM1'):
            psx_disc.open_disc(odd)


if __name__ == '__main__':
    unittest.main()
