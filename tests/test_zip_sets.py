"""The shared arcade ZIP reader against the console bodies it retires. Synthetic ZIPs only."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import BadZipFile, ZipFile, ZipInfo, ZIP_STORED

from retrorecomp import cps1, neogeo, zip_sets


def reference_neogeo_members(path: Path, *, hash_contents: bool = False, cartridge_paths: bool = False):
    """The neogeo.archive_members body retired by zip_sets, kept as the reference."""
    records = []
    try:
        if path.stat().st_size > neogeo.MAX_SET_BYTES:
            raise ValueError('Neo Geo archive exceeds the size limit.')
        with ZipFile(path) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            if not entries or len(entries) > 1024:
                raise ValueError('Invalid Neo Geo archive member count.')
            if sum(entry.file_size for entry in entries) > neogeo.MAX_ARCHIVE_EXPANDED_BYTES:
                raise ValueError('Neo Geo archive exceeds the expanded size limit.')
            seen = set()
            for entry in entries:
                name = entry.filename.replace('\\', '/').rsplit('/', 1)[-1].casefold()
                unique = entry.filename.replace('\\', '/').casefold() if cartridge_paths else name
                if not name or unique in seen or entry.flag_bits & 1:
                    raise ValueError('Ambiguous or encrypted Neo Geo archive member.')
                seen.add(unique)
                if entry.file_size > neogeo.MAX_MEMBER_BYTES:
                    raise ValueError('Neo Geo archive member exceeds the size limit.')
                record = {'name': name, 'bytes': entry.file_size, 'crc32': entry.CRC}
                if cartridge_paths:
                    record['archive_path'] = entry.filename
                if hash_contents:
                    digest = hashlib.sha256()
                    count = 0
                    with archive.open(entry) as source:
                        while chunk := source.read(1024 * 1024):
                            count += len(chunk)
                            if count > entry.file_size:
                                raise ValueError('Neo Geo member size changed while reading.')
                            digest.update(chunk)
                    if count != entry.file_size:
                        raise ValueError('Truncated Neo Geo archive member.')
                    record['sha256'] = digest.hexdigest()
                records.append(record)
    except (BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError(f'Cannot read Neo Geo ZIP: {exc}') from exc
    return tuple(sorted(records, key=lambda item: item['name']))


def reference_cps1_members(path: Path):
    """The cps1.archive_members body retired by zip_sets, kept as the reference."""
    records = []
    try:
        if path.stat().st_size > cps1.MAX_ARCHIVE_BYTES:
            raise ValueError('CPS-1 archive exceeds the size limit.')
        with ZipFile(path) as archive:
            entries = [entry for entry in archive.infolist() if not entry.is_dir()]
            if not entries or len(entries) > cps1.MAX_MEMBERS:
                raise ValueError('Invalid CPS-1 archive member count.')
            if sum(entry.file_size for entry in entries) > cps1.MAX_EXPANDED_BYTES:
                raise ValueError('CPS-1 archive exceeds the expanded size limit.')
            for entry in entries:
                if entry.flag_bits & 1:
                    raise ValueError('Encrypted CPS-1 archive member.')
                if entry.file_size > cps1.MAX_MEMBER_BYTES:
                    raise ValueError('CPS-1 archive member exceeds the size limit.')
                records.append({'name': entry.filename.replace('\\', '/').rsplit('/', 1)[-1].casefold(),
                                'archive_path': entry.filename, 'bytes': entry.file_size, 'crc32': entry.CRC})
    except (BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError(f'Cannot read CPS-1 ZIP: {exc}') from exc
    return tuple(sorted(records, key=lambda item: item['archive_path']))


def reference_cps1_read_member(archive: ZipFile, record: dict):
    """The cps1._read_member body retired by zip_sets, kept as the reference."""
    sha1, sha256, count = hashlib.sha1(), hashlib.sha256(), 0
    with archive.open(record['archive_path']) as source:
        while chunk := source.read(1024 * 1024):
            count += len(chunk)
            if count > record['bytes']:
                raise ValueError('CPS-1 member size changed while reading.')
            sha1.update(chunk); sha256.update(chunk)
    if count != record['bytes']:
        raise ValueError('Truncated CPS-1 archive member.')
    return {'sha1': sha1.hexdigest(), 'sha256': sha256.hexdigest()}


def outcome(action):
    """'ok' with the result, or 'error' with the message: failures compare too."""
    try:
        return ('ok', action())
    except ValueError as error:
        return ('error', str(error))


def fabricated(count, size=0):
    entries = []
    for number in range(count):
        entry = ZipInfo(f'member-{number}.bin');entry.file_size = size;entry.CRC = 0
        entries.append(entry)
    return entries


class StubArchive:
    """An open ZIP stand-in: the listed entries, one payload for every open."""
    def __init__(self, entries, payload):
        self.entries = entries;self.payload = payload
    def __enter__(self):return self
    def __exit__(self, *exception):return False
    def infolist(self):return self.entries
    def open(self, member):return io.BytesIO(self.payload)


SCENARIOS = {
    'plain': {'p1.rom': b'program', 'm1.bin': b'sound'},
    'nested and cased': {'Folder/Sub/P1.ROM': b'program', 'other/M1.BIN': b'sound'},
    'duplicate basenames': {'a/x.rom': b'first', 'b/x.rom': b'second'},
    'empty member name': {'': b'anonymous'},
    'only a folder': {'folder/': b''},
    'single member': {'only.rom': b'\x00\xff' * 7},
}


class ZipSetsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write_zip(self, name, entries, *, encrypted=False):
        path = self.root / name
        with ZipFile(path, 'w', compression=ZIP_STORED) as archive:
            for member, data in entries.items():archive.writestr(member, data)
        if encrypted:
            data = bytearray(path.read_bytes())
            index = data.find(b'PK\x01\x02')
            while index != -1:
                data[index + 8] |= 1  # the general-purpose flag of each central-directory entry
                index = data.find(b'PK\x01\x02', index + 4)
            path.write_bytes(data)
        return path

    def stub_path(self):
        path = self.root / 'stub.zip';path.write_bytes(b'stub')
        return path

    def test_flat_name_flattens_and_casefolds(self):
        self.assertEqual(zip_sets.flat_name('dir/sub/Name.ROM'), 'name.rom')
        self.assertEqual(zip_sets.flat_name('dir\\sub\\Name.ROM'), 'name.rom')
        self.assertEqual(zip_sets.flat_name('plain.rom'), 'plain.rom')
        self.assertEqual(zip_sets.flat_name('trailing/'), '')
        self.assertEqual(zip_sets.flat_name(''), '')

    def test_neogeo_matches_the_retired_body(self):
        archives = [self.write_zip('plain.zip', {'p1.rom': b'program', 'm1.bin': b'sound'})]
        for label, entries in SCENARIOS.items():
            archives.append(self.write_zip('scenario.zip', entries))
        archives.append(self.write_zip('locked.zip', {'p1.rom': b'program'}, encrypted=True))
        not_a_zip = self.root / 'not-a-zip.zip';not_a_zip.write_text('certainly not a zip archive')
        archives.append(not_a_zip)
        archives.append(self.root / 'missing.zip')
        for path in archives:
            for hash_contents in (False, True):
                for cartridge_paths in (False, True):
                    self.assertEqual(
                        outcome(lambda: neogeo.archive_members(path, hash_contents=hash_contents,
                                                               cartridge_paths=cartridge_paths)),
                        outcome(lambda: reference_neogeo_members(path, hash_contents=hash_contents,
                                                                 cartridge_paths=cartridge_paths)),
                        (path.name, hash_contents, cartridge_paths))

    def test_cps1_matches_the_retired_body(self):
        archives = [self.write_zip('plain.zip', {'ff.01': b'program', 'ff.02': b'sound'})]
        for label, entries in SCENARIOS.items():
            archives.append(self.write_zip('scenario.zip', entries))
        archives.append(self.write_zip('locked.zip', {'ff.01': b'program'}, encrypted=True))
        archives.append(self.root / 'not-a-zip.zip')
        archives.append(self.root / 'missing.zip')
        for path in archives:
            self.assertEqual(outcome(lambda: cps1.archive_members(path)),
                             outcome(lambda: reference_cps1_members(path)), path.name)

    def test_cps1_read_member_matches_the_retired_body(self):
        for label, entries in SCENARIOS.items():
            if not any(entries.values()):
                continue  # a folder entry alone is refused before any member is read
            path = self.write_zip('read.zip', entries)
            records = cps1.archive_members(path)
            with ZipFile(path) as archive:
                for record in records:
                    self.assertEqual(cps1._read_member(archive, record),
                                     reference_cps1_read_member(archive, record), (label, record))

    def test_hashed_contents_are_the_original_member_bytes(self):
        path = self.write_zip('hashes.zip', {'p.rom': b'program', 'Sub/M1.BIN': b'sound'})
        records = neogeo.archive_members(path, hash_contents=True)
        self.assertEqual([(record['name'], record['sha256']) for record in records],
                         [('m1.bin', hashlib.sha256(b'sound').hexdigest()),
                          ('p.rom', hashlib.sha256(b'program').hexdigest())])
        records = cps1.archive_members(path)
        with ZipFile(path) as archive:
            self.assertEqual(cps1._read_member(archive, records[0]),
                             {'sha1': hashlib.sha1(b'sound').hexdigest(),
                              'sha256': hashlib.sha256(b'sound').hexdigest()})

    def test_encrypted_members_are_refused(self):
        path = self.write_zip('locked.zip', {'p.rom': b'program', 'm1.bin': b'sound'}, encrypted=True)
        with ZipFile(path) as archive:
            self.assertTrue(all(entry.flag_bits & 1 for entry in archive.infolist()))
        with self.assertRaisesRegex(ValueError, 'Ambiguous or encrypted Neo Geo archive member.'):
            neogeo.archive_members(path)
        with self.assertRaisesRegex(ValueError, 'Encrypted CPS-1 archive member.'):
            cps1.archive_members(path)

    def test_empty_and_excessive_member_counts_are_refused(self):
        empty = self.write_zip('empty.zip', {})
        for path in (empty,):
            with self.assertRaisesRegex(ValueError, 'Invalid Neo Geo archive member count.'):
                neogeo.archive_members(path)
            with self.assertRaisesRegex(ValueError, 'Invalid CPS-1 archive member count.'):
                cps1.archive_members(path)
        for module, label in ((neogeo, 'Neo Geo'), (cps1, 'CPS-1')):
            with patch(f'{module.__name__}.ZipFile') as factory:
                factory.return_value.__enter__.return_value.infolist.return_value = fabricated(1025)
                with self.assertRaisesRegex(ValueError, f'Invalid {label} archive member count.'):
                    module.archive_members(self.stub_path())

    def test_expanded_and_single_member_bounds_hold(self):
        too_wide = fabricated(9, 128 * 1024 * 1024)
        with patch('retrorecomp.neogeo.ZipFile') as factory:
            entries = factory.return_value.__enter__.return_value.infolist
            entries.return_value = too_wide[:8]
            self.assertEqual(len(neogeo.archive_members(self.stub_path())), 8)
            entries.return_value = too_wide
            with self.assertRaisesRegex(ValueError, 'Neo Geo archive exceeds the expanded size limit.'):
                neogeo.archive_members(self.stub_path())
            entries.return_value = fabricated(2, neogeo.MAX_MEMBER_BYTES + 1)
            with self.assertRaisesRegex(ValueError, 'Neo Geo archive member exceeds the size limit.'):
                neogeo.archive_members(self.stub_path())
        wide = fabricated(6, 100 * 1024 * 1024)
        with patch('retrorecomp.cps1.ZipFile') as factory:
            entries = factory.return_value.__enter__.return_value.infolist
            entries.return_value = wide
            with self.assertRaisesRegex(ValueError, 'CPS-1 archive exceeds the expanded size limit.'):
                cps1.archive_members(self.stub_path())
            entries.return_value = fabricated(2, cps1.MAX_MEMBER_BYTES + 1)
            with self.assertRaisesRegex(ValueError, 'CPS-1 archive member exceeds the size limit.'):
                cps1.archive_members(self.stub_path())

    def test_container_size_bound_is_checked_before_opening(self):
        path = self.write_zip('container.zip', {'p.rom': b'program'})
        with patch.object(neogeo, 'MAX_SET_BYTES', 4):
            with self.assertRaisesRegex(ValueError, 'Neo Geo archive exceeds the size limit.'):
                neogeo.archive_members(path)
        with patch.object(cps1, 'MAX_ARCHIVE_BYTES', 4):
            with self.assertRaisesRegex(ValueError, 'CPS-1 archive exceeds the size limit.'):
                cps1.archive_members(path)

    def test_members_whose_read_length_disagrees_are_refused(self):
        entry = ZipInfo('short.rom');entry.file_size = 5;entry.CRC = 0
        with patch('retrorecomp.neogeo.ZipFile', return_value=StubArchive([entry], b'abc')):
            with self.assertRaisesRegex(ValueError, 'Truncated Neo Geo archive member.'):
                neogeo.archive_members(self.stub_path(), hash_contents=True)
        entry.file_size = 2
        with patch('retrorecomp.neogeo.ZipFile', return_value=StubArchive([entry], b'abcd')):
            with self.assertRaisesRegex(ValueError, 'Neo Geo member size changed while reading.'):
                neogeo.archive_members(self.stub_path(), hash_contents=True)
        with self.assertRaisesRegex(ValueError, 'Truncated CPS-1 archive member.'):
            cps1._read_member(StubArchive([], b'abc'), {'archive_path': 'm.rom', 'bytes': 5})
        with self.assertRaisesRegex(ValueError, 'CPS-1 member size changed while reading.'):
            cps1._read_member(StubArchive([], b'abcd'), {'archive_path': 'm.rom', 'bytes': 2})

    def test_duplicate_basenames_split_the_consoles(self):
        path = self.write_zip('duplicates.zip', {'a/x.rom': b'first', 'b/x.rom': b'second'})
        with self.assertRaisesRegex(ValueError, 'Ambiguous or encrypted Neo Geo archive member.'):
            neogeo.archive_members(path)
        records = neogeo.archive_members(path, cartridge_paths=True)
        self.assertEqual([record['archive_path'] for record in records], ['a/x.rom', 'b/x.rom'])
        records = cps1.archive_members(path)
        self.assertEqual([(record['archive_path'], record['bytes']) for record in records],
                         [('a/x.rom', 5), ('b/x.rom', 6)])

    def test_zipfile_and_os_failures_are_translated(self):
        text = self.root / 'text.zip';text.write_text('certainly not a zip archive')
        missing = self.root / 'missing.zip'
        for path in (text, missing):
            with self.assertRaisesRegex(ValueError, 'Cannot read Neo Geo ZIP'):
                neogeo.archive_members(path)
            with self.assertRaisesRegex(ValueError, 'Cannot read CPS-1 ZIP'):
                cps1.archive_members(path)

    def test_records_keep_the_flat_name_and_the_original_path(self):
        path = self.write_zip('named.zip', {'Folder/Sub/P1.ROM': b'program'})
        neo = neogeo.archive_members(path, cartridge_paths=True)[0]
        self.assertEqual((neo['name'], neo['archive_path']), ('p1.rom', 'Folder/Sub/P1.ROM'))
        cap = cps1.archive_members(path)[0]
        self.assertEqual((cap['name'], cap['archive_path']), ('p1.rom', 'Folder/Sub/P1.ROM'))

    def test_sort_orders_are_unchanged(self):
        # The flattened name ranks the Neo Geo records, the original path the CPS-1 ones.
        path = self.write_zip('ordered.zip', {'b/a.rom': b'one', 'a/b.rom': b'two', 'a/x.rom': b'lowest'})
        self.assertEqual([(record['name'], record['archive_path'])
                          for record in neogeo.archive_members(path, cartridge_paths=True)],
                         [('a.rom', 'b/a.rom'), ('b.rom', 'a/b.rom'), ('x.rom', 'a/x.rom')])
        self.assertEqual([record['archive_path'] for record in cps1.archive_members(path)],
                         ['a/b.rom', 'a/x.rom', 'b/a.rom'])


if __name__ == '__main__':
    unittest.main()
