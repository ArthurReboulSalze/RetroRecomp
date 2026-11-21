"""The PC Engine CD's disc readers on discs the test builds itself (no commercial disc, no System Card, no engine, no compiler).

Every container the machine reads is built here: an ISO, a CUE sheet with BIN files, and a CHD of version 5 (uncompressed, with the
Huffman-coded map and `cdzl` or `cdlz` hunks) or version 4 (uncompressed or deflated). A disc is the same list of tracks whatever its
container, so each one must give the same boot record and the same sector.
"""
from __future__ import annotations

import binascii
import hashlib
import lzma
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from retrorecomp import pcecd, pcecd_card, pcecd_chd, pcecd_disc  # noqa: E402
from retrorecomp.systems import registry, UnsupportedConsoleError  # noqa: E402

FRAME, SECTOR, SYNC = 2448, 2352, b'\x00' + b'\xff' * 10 + b'\x00'


def ipl_sector(title: str = 'AUTHORED TEST DISC') -> bytes:
    data = bytearray(2048)
    data[0:3] = (2).to_bytes(3, 'big')           # the boot file starts at sector 2
    data[3] = 2                                  # two sectors
    struct.pack_into('<HH', data, 4, 0x4000, 0x4000)
    data[8:13] = bytes(range(5))
    data[32:56] = b'PC Engine CD-ROM SYSTEM\x00'
    data[0x6A:0x6A + len(title)] = title.encode('ascii')
    return bytes(data)


def user_sectors(count: int = 5) -> list:
    """The user data of the data track: a blank sector, the IPL, then recognisable filler."""
    return [bytes(2048), ipl_sector()] + [bytes([n]) * 2048 for n in range(2, count)]


def raw_sector(user: bytes, lba: int) -> bytes:
    """A Mode 1 raw sector: sync, header, user data, then zeros where the EDC and the parity go."""
    return SYNC + bytes([0, 2 + lba // 75 % 60, lba % 75, 1]) + user + bytes(SECTOR - 16 - 2048)


def audio_sector(seed: int) -> bytes:
    return bytes((seed + n) % 251 for n in range(SECTOR))


class Layout:
    """The tracks of a synthetic disc: an audio track, the data track with the IPL, another audio track (the real layout of the
    library's discs), each with the frames the image stores."""

    def __init__(self, data_cooked: bool = False):
        self.data_cooked = data_cooked
        self.tracks = []        # (type, frames as 2352-byte sectors, pregap)
        if data_cooked:
            self.tracks.append(('MODE1', [s for s in user_sectors()], 0))
        else:
            self.tracks.append(('AUDIO', [audio_sector(1) for _ in range(6)], 0))
            self.tracks.append(('MODE1_RAW', [raw_sector(u, n) for n, u in enumerate(user_sectors())], 150))
            self.tracks.append(('AUDIO', [audio_sector(9) for _ in range(5)], 150))

    def metadata(self) -> bytes:
        rows = b''
        for number, (kind, frames, pregap) in enumerate(self.tracks, 1):
            rows += f'TRACK:{number} TYPE:{kind} SUBTYPE:NONE FRAMES:{len(frames)} PREGAP:{pregap} PGTYPE:{"MODE1" if kind != "AUDIO" else "AUDIO"} '.encode() + b'PGSUB:NONE POSTGAP:0\0'
        return rows

    def logical(self) -> bytes:
        """The frames as a CHD stores them: 2,448 bytes each, every track padded to a multiple of four frames."""
        out = bytearray()
        for kind, frames, _pregap in self.tracks:
            for sector in frames:
                body = sector if kind != 'MODE1' else sector + bytes(SECTOR - 2048)
                out += body + bytes(FRAME - SECTOR)
            out += bytes(FRAME) * (-len(frames) % 4)
        return bytes(out)


# ---- containers -----------------------------------------------------------------------------------------------------------

def write_iso(path: Path) -> None:
    path.write_bytes(b''.join(user_sectors()))


def write_cue(folder: Path, name: str = 'disc') -> Path:
    layout = Layout()
    audio1 = b''.join(layout.tracks[0][1])
    data = b''.join(layout.tracks[1][1])
    audio2 = b''.join(layout.tracks[2][1])
    (folder / f'{name} (Track 1).bin').write_bytes(audio1)
    (folder / f'{name} (Track 2).bin').write_bytes(data)
    (folder / f'{name} (Track 3).bin').write_bytes(audio2)
    sheet = folder / f'{name}.cue'
    sheet.write_text(
        f'FILE "{name} (Track 1).bin" BINARY\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
        f'FILE "{name} (Track 2).bin" BINARY\n  TRACK 02 MODE1/2352\n    PREGAP 00:02:00\n    INDEX 01 00:00:00\n'
        f'FILE "{name} (Track 3).bin" BINARY\n  TRACK 03 AUDIO\n    PREGAP 00:02:00\n    INDEX 01 00:00:00\n', encoding='utf-8')
    return sheet


def _packed_hunk(hunk: bytes, base) -> bytes:
    """A CD hunk as the cdzl and cdlz codecs store it: no flagged frame, the base stream, then the sub-channel deflated."""
    frames = len(hunk) // FRAME
    sectors = b''.join(hunk[n * FRAME:n * FRAME + SECTOR] for n in range(frames))
    sub = b''.join(hunk[n * FRAME + SECTOR:(n + 1) * FRAME] for n in range(frames))
    base_bytes = base(sectors)
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    return bytes((frames + 7) // 8) + len(base_bytes).to_bytes(2, 'big') + base_bytes + deflater.compress(sub) + deflater.flush()


def _deflate(data: bytes) -> bytes:
    deflater = zlib.compressobj(9, zlib.DEFLATED, -15)
    return deflater.compress(data) + deflater.flush()


def _lzma(data: bytes) -> bytes:
    return lzma.compress(data, format=lzma.FORMAT_RAW, filters=[{'id': lzma.FILTER_LZMA1, 'dict_size': 1 << 20, 'lc': 3, 'lp': 0, 'pb': 2}])


class _BitWriter:
    def __init__(self):
        self.bits = ''

    def write(self, value: int, width: int) -> None:
        self.bits += format(value, f'0{width}b') if width else ''

    def data(self) -> bytes:
        padded = self.bits + '0' * (-len(self.bits) % 8)
        return int(padded, 2).to_bytes(len(padded) // 8, 'big') if padded else b''


def write_chd_v5(path: Path, layout: Layout, codec: str | None, hunk_frames: int = 8) -> None:
    """A version 5 CHD. codec None: uncompressed hunks. 'cdzl' or 'cdlz': every hunk compressed by it (map type 1 or 0)."""
    logical = layout.logical()
    hunk_bytes = hunk_frames * FRAME
    assert len(logical) % hunk_bytes == 0
    hunks = [logical[n:n + hunk_bytes] for n in range(0, len(logical), hunk_bytes)]
    metadata = layout.metadata()
    compressors = [b'\0\0\0\0'] * 4
    if codec:
        compressors = [b'cdlz', b'cdzl', b'cdfl', b'\0\0\0\0']
    header_len = 124
    if codec is None:
        data = b''.join(hunks)
        map_bytes = bytes(4 * len(hunks))
        data_offset = header_len + len(map_bytes)
        data_offset += -data_offset % hunk_bytes
        # an uncompressed map holds the position of each hunk in units of the hunk size
        first = data_offset // hunk_bytes
        map_bytes = b''.join(struct.pack('>I', first + n) for n in range(len(hunks)))
        meta_offset = data_offset + len(data)
        body = map_bytes + bytes(data_offset - header_len - len(map_bytes)) + data
        map_offset = header_len
    else:
        base = _lzma if codec == 'cdlz' else _deflate
        kind = 0 if codec == 'cdlz' else 1
        packed = [_packed_hunk(h, base) for h in hunks]
        lengthbits = 16
        writer = _BitWriter()
        # the tree: 16 codes, only the kind in use has a (one bit) code; written as run-length coded lengths, four bits each
        lengths = [0] * 16
        lengths[kind] = 1
        index = 0
        while index < 16:
            if lengths[index] == 1:
                writer.write(1, 4)
                writer.write(1, 4)
                index += 1
                continue
            run = 1
            while index + run < 16 and lengths[index + run] == 0:
                run += 1
            if run >= 3:
                writer.write(1, 4)
                writer.write(0, 4)
                writer.write(run - 3, 4)
            else:
                for _ in range(run):
                    writer.write(0, 4)
            index += run
        for _ in packed:
            writer.write(0, 1)                                  # the one-bit code of the kind
        for payload, hunk in zip(packed, hunks):
            writer.write(len(payload), lengthbits)
            writer.write(binascii.crc_hqx(hunk, 0xFFFF), 16)
        packed_map = writer.data()
        # the data follows the map; only the first offset is stored, the others follow the lengths
        first_offset = header_len + 16 + len(packed_map)
        raw_map, position = bytearray(), first_offset
        for payload, hunk in zip(packed, hunks):
            raw_map += bytes([kind]) + len(payload).to_bytes(3, 'big') + position.to_bytes(6, 'big') + binascii.crc_hqx(hunk, 0xFFFF).to_bytes(2, 'big')
            position += len(payload)
        map_header = (struct.pack('>I', len(packed_map)) + first_offset.to_bytes(6, 'big') + struct.pack('>H', binascii.crc_hqx(bytes(raw_map), 0xFFFF))
                      + bytes([lengthbits, 0, 0, 0]))
        body = map_header + packed_map + b''.join(packed)
        map_offset = header_len
        meta_offset = header_len + len(body)
    meta_records = b''
    # the metadata chain: one CHT2 record per track line
    lines = [row for row in metadata.split(b'\0') if row]
    position = meta_offset
    for number, row in enumerate(lines):
        following = position + 16 + len(row) + 1 if number + 1 < len(lines) else 0
        meta_records += b'CHT2' + struct.pack('>I', (1 << 24) | (len(row) + 1)) + struct.pack('>Q', following) + row + b'\0'
        position = following
    sha = bytes(20)
    header = (b'MComprHD' + struct.pack('>II', header_len, 5) + b''.join(compressors) + struct.pack('>QQQ', len(logical), map_offset, meta_offset)
              + struct.pack('>II', hunk_bytes, FRAME) + sha + sha + sha)
    assert len(header) == header_len
    path.write_bytes(header + body + meta_records)


def write_chd_v4(path: Path, layout: Layout, compressed: bool, hunk_frames: int = 4) -> None:
    logical = layout.logical()
    hunk_bytes = hunk_frames * FRAME
    hunks = [logical[n:n + hunk_bytes] for n in range(0, len(logical), hunk_bytes)]
    header_len = 108
    map_len = 16 * len(hunks) + 16          # the entries, then the end-of-list cookie libchdr looks for
    body, entries, position = b'', b'', header_len + map_len
    for hunk in hunks:
        if compressed:
            payload = _deflate(hunk)
            kind, length = 1, len(payload)
        else:
            payload, kind, length = hunk, 2, hunk_bytes
        entries += struct.pack('>QI', position, zlib.crc32(hunk)) + struct.pack('>H', length & 0xFFFF) + bytes([length >> 16, kind])
        body += payload
        position += len(payload)
    meta_offset = header_len + map_len + len(body)
    lines = [row for row in layout.metadata().split(b'\0') if row]
    meta, at = b'', meta_offset
    for number, row in enumerate(lines):
        following = at + 16 + len(row) + 1 if number + 1 < len(lines) else 0
        meta += b'CHTR' + struct.pack('>I', len(row) + 1) + struct.pack('>Q', following) + row + b'\0'
        at = following
    sha = bytes(20)
    header = (b'MComprHD' + struct.pack('>II', header_len, 4) + struct.pack('>III', 0, 1 if compressed else 0, len(hunks))
              + struct.pack('>QQ', len(logical), meta_offset) + struct.pack('>I', hunk_bytes) + bytes(20) + bytes(20) + sha)
    assert len(header) == header_len, len(header)
    path.write_bytes(header + entries + b'EndOfListCookie\0' + body + meta)


# ---- tests ----------------------------------------------------------------------------------------------------------------

class DiscReaderTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix='rr-pcecd-')
        self.addCleanup(self._temp.cleanup)
        self.folder = Path(self._temp.name)

    def containers(self) -> dict:
        out = {}
        out['iso'] = self.folder / 'a.iso'
        write_iso(out['iso'])
        (self.folder / 'cue').mkdir()
        out['cue'] = write_cue(self.folder / 'cue')
        layout = Layout()
        for name, writer in (('v5 raw', lambda p: write_chd_v5(p, layout, None)), ('v5 cdzl', lambda p: write_chd_v5(p, layout, 'cdzl')),
                             ('v5 cdlz', lambda p: write_chd_v5(p, layout, 'cdlz')), ('v4 raw', lambda p: write_chd_v4(p, layout, False)),
                             ('v4 zlib', lambda p: write_chd_v4(p, layout, True))):
            out[name] = self.folder / (name.replace(' ', '-') + '.chd')
            writer(out[name])
        return out

    def test_every_container_gives_the_same_boot_record_and_the_same_sector(self):
        expected = ipl_sector()
        for name, path in self.containers().items():
            with self.subTest(name):
                identity = pcecd_disc.describe(path)
                self.assertEqual((identity.ipl.start_sector, identity.ipl.sector_count, identity.ipl.load_address, identity.ipl.entry_address),
                                 (2, 2, 0x4000, 0x4000))
                self.assertEqual(identity.title, 'AUTHORED TEST DISC')
                disc = pcecd_disc.open_disc(path)
                try:
                    track = pcecd_disc.first_data_track(disc)
                    self.assertEqual(disc.user(track.start + 1), expected)
                    self.assertEqual(disc.user(track.start + 3), bytes([3]) * 2048)
                finally:
                    disc.close()
                self.assertTrue(pcecd.recognise(path))

    def test_the_track_table_follows_the_engines_numbering(self):
        # a virtual pregap is added to the numbering, a stored one is part of the track: here three tracks, two with 150 virtual frames
        disc = pcecd_disc.open_disc(self.containers()['v5 cdzl'])
        try:
            self.assertEqual([(t.number, t.mode, t.start, t.length) for t in disc.tracks],
                             [(1, 'AUDIO', 0, 6), (2, 'MODE1/2352', 156, 5), (3, 'AUDIO', 311, 5)])
            self.assertEqual(disc.leadout, 316)
        finally:
            disc.close()

    def test_a_disc_of_one_cooked_data_track_and_no_audio(self):
        path = self.folder / 'cooked.chd'
        write_chd_v5(path, Layout(data_cooked=True), 'cdzl')
        identity = pcecd_disc.describe(path)
        self.assertEqual((identity.tracks, identity.data_tracks, identity.audio_tracks), (1, 1, 0))
        self.assertEqual(identity.ipl.title, 'AUTHORED TEST DISC')

    def test_a_flagged_frame_has_its_sync_and_parity_put_back(self):
        # the encoder drops the sync and the parity of a frame whose parity can be rebuilt and sets its bit in the hunk's header; the decoder
        # (and the CRC of the file's map) work on the whole sector
        frames = [bytearray(raw_sector(bytes([n]) * 2048, n)) for n in range(8)]
        for sector in frames[:2]:
            pcecd_chd._ecc_generate(sector)
        whole = b''.join(bytes(s) for s in frames)
        stripped = bytearray(whole)
        for n in range(2):
            stripped[n * SECTOR:n * SECTOR + 12] = bytes(12)
            stripped[n * SECTOR + pcecd_chd._ECC_P_OFFSET:(n + 1) * SECTOR] = bytes(SECTOR - pcecd_chd._ECC_P_OFFSET)
        base = _deflate(bytes(stripped))
        packed = bytes([0b00000011]) + len(base).to_bytes(2, 'big') + base + _deflate(bytes(96 * 8))
        chd = object.__new__(pcecd_chd.Chd)
        chd.hunk_bytes, chd.path = 8 * FRAME, Path('synthetic.chd')
        decoded = chd._compressed('cdzl', packed)
        for n in range(8):
            self.assertEqual(decoded[n * FRAME:n * FRAME + SECTOR], whole[n * SECTOR:(n + 1) * SECTOR], n)
        self.assertNotEqual(whole[pcecd_chd._ECC_P_OFFSET:SECTOR], bytes(SECTOR - pcecd_chd._ECC_P_OFFSET))

    def test_a_corrupted_hunk_is_refused_by_its_checksum(self):
        path = self.containers()['v5 cdzl']
        blob = bytearray(path.read_bytes())
        start = 124 + 16 + int.from_bytes(blob[124:128], 'big')       # past the header and the map: the hunks' compressed data
        for n in range(start, len(blob) - 400):
            blob[n] ^= 0x01
        path.write_bytes(bytes(blob))
        self.assertIsNone(pcecd.recognise(path))
        with self.assertRaises(pcecd_disc.DiscError):
            pcecd_disc.describe(path)

    def test_a_hunk_of_the_audio_codec_is_named_not_guessed(self):
        chd = object.__new__(pcecd_chd.Chd)
        chd.path, chd.hunk_bytes = Path('x.chd'), 19584
        with self.assertRaises(pcecd_chd.ChdCodecError):
            chd._compressed('cdfl', b'\0' * 64)

    def test_a_disc_without_the_boot_record_belongs_to_somebody_else(self):
        other = self.folder / 'other.iso'
        other.write_bytes(bytes(2048 * 4))
        self.assertIsNone(pcecd.recognise(other))
        text = self.folder / 'text.chd'
        text.write_bytes(b'not a disc at all')
        self.assertIsNone(pcecd.recognise(text))
        not_a_disc = self.folder / 'file.txt'
        not_a_disc.write_bytes(ipl_sector())
        self.assertIsNone(pcecd.recognise(not_a_disc))

    def test_the_identity_of_a_cue_set_is_the_engines_record(self):
        (self.folder / 'set').mkdir()
        sheet = write_cue(self.folder / 'set', 'game')
        lines = ['PCE-CUE-1', f'cue\t{sheet.stat().st_size}\t{hashlib.sha256(sheet.read_bytes()).hexdigest()}']
        for n in (1, 2, 3):
            image = sheet.parent / f'game (Track {n}).bin'
            lines.append(f'file\t{image.name}\t{image.stat().st_size}\t{hashlib.sha256(image.read_bytes()).hexdigest()}')
        self.assertEqual(pcecd_disc.image_sha256(sheet), hashlib.sha256(('\n'.join(lines) + '\n').encode()).hexdigest())
        iso = self.folder / 'b.iso'
        write_iso(iso)
        self.assertEqual(pcecd_disc.image_sha256(iso), hashlib.sha256(iso.read_bytes()).hexdigest())
        self.assertEqual(len(pcecd_disc.files_of(sheet)), 4)

    def test_the_input_names_the_disc_and_the_card_changes_the_machine_identity(self):
        iso = self.folder / 'c.iso'
        write_iso(iso)
        item = pcecd.read_input(iso)
        self.assertEqual((item.title, item.sha256, item.metadata()['system']), ('AUTHORED TEST DISC', hashlib.sha256(iso.read_bytes()).hexdigest(), 'pcecd'))
        none = pcecd.machine_identity(item, None)
        card = self.folder / 'card.pce'
        card.write_bytes(bytes(pcecd_card.CARD_BYTES))
        saved = pcecd_card.KNOWN
        try:
            pcecd_card.KNOWN = (pcecd_card.KnownCard(hashlib.sha1(card.read_bytes()).hexdigest(), 'Test card', '9.0', 'usa', 'untried'),)
            pcecd_card.BY_SHA1 = {c.sha1: c for c in pcecd_card.KNOWN}
            self.assertNotEqual(pcecd.machine_identity(item, card), none)
            self.assertEqual(pcecd_card.choose([self.folder]).name, 'Test card')
        finally:
            pcecd_card.KNOWN = saved
            pcecd_card.BY_SHA1 = {c.sha1: c for c in saved}


class SystemCardTests(unittest.TestCase):
    def test_the_two_known_cards_are_listed_by_hash_and_nothing_else_is_accepted(self):
        self.assertEqual({(c.version, c.region) for c in pcecd_card.KNOWN}, {('3.0', 'usa'), ('3.0', 'japan')})
        with tempfile.TemporaryDirectory(prefix='rr-pcecd-card-') as temp:
            wrong_size = Path(temp) / 'a.pce'
            wrong_size.write_bytes(bytes(1000))
            with self.assertRaises(pcecd_card.CardError):
                pcecd_card.identify(wrong_size)
            unknown = Path(temp) / 'b.pce'
            unknown.write_bytes(bytes(pcecd_card.CARD_BYTES))
            with self.assertRaises(pcecd_card.CardError):
                pcecd_card.identify(unknown)
            self.assertIsNone(pcecd_card.choose([Path(temp)]))


class ProfileTests(unittest.TestCase):
    def test_the_profile_is_experimental_developer_only_and_separate_from_the_pc_engine(self):
        profile = next(p for p in registry.all_profiles() if p.id == 'pcecd')
        self.assertEqual((profile.status, profile.developer_only, profile.linux, profile.media_kinds, profile.firmware),
                         ('experimental', True, 'pending', ('disc',), ('system_card',)))
        self.assertEqual([c.arch for c in profile.cpus], ['huc6280'])
        self.assertNotEqual(profile.id, 'pce')
        self.assertIn('pcecd', [p.id for p in registry.all_profiles()])

    def test_a_disc_is_claimed_by_what_it_holds_and_refused_while_the_machine_is_not_installed(self):
        profile = next(p for p in registry.all_profiles() if p.id == 'pcecd')
        with tempfile.TemporaryDirectory(prefix='rr-pcecd-profile-') as temp:
            iso = Path(temp) / 'game.iso'
            write_iso(iso)
            other = Path(temp) / 'other.iso'
            other.write_bytes(bytes(2048 * 3))
            self.assertIsNone(profile.identify_path(other, '.iso', None))
            self.assertIsNone(profile.identify_path(iso, '.bin', None))
            if profile.available():
                self.assertIs(profile.identify_path(iso, '.iso', None), profile)
            else:
                with self.assertRaises(UnsupportedConsoleError):
                    profile.identify_path(iso, '.iso', None)


if __name__ == '__main__':
    unittest.main()
