"""Schema 3 of the paths travels (stage B2): the exchange file, the shared base and the upload.

`.rrknowledge` version 3 and the shared base (index, entry and archive format 3, its only format since
1.6.1) carry the CPU-keyed records of `path_profiles`; everything after the readers still works on schema 1
records (the qualified bank keeps its shape), so a version 3 file or a format 3 entry gives exactly the paths
its version 2 twin gives. A converter reads every version of a file, uploads version 3, and reads the
one line of the base only: formats 1 and 2 are not read.
"""
import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from retrorecomp import knowledge, knowledge_exchange as kx, online, path_profiles as pp
from tests.test_paths_schema import ENGINE, FIXTURES, SHA
from tests.test_shared_base import (BaseHarness, IDENTITY, KEY, base_archive, entry, grouped_entry, part,
                                    qualified)
from tests.test_shared_sync import sms_record

NG_NAMES = ('ng', 'ng-deltas')


def legacy_payload(*names):
    consoles = {}
    for name in names:
        system, identity, record = FIXTURES[name]
        consoles.setdefault(system, {})[identity] = copy.deepcopy(record)
    return {'schema': 1, 'consoles': consoles}


def collected(*names, observations=None):
    payload = legacy_payload(*names)
    titles = {system: {identity: 'A game' for identity in games} for system, games in payload['consoles'].items()}
    rows = observations if observations is not None else {}
    return {'games': sum(len(games) for games in payload['consoles'].values()), 'consoles': {}, 'discoveries': 1,
            'omitted': {}, 'observations': rows, 'observation_count': 0, 'payload': payload, 'titles': titles}


def header(path):
    with gzip.open(path, 'rb') as stream:
        return json.loads(stream.read())


class ExchangeFileTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def test_a_version_3_file_reads_to_the_paths_its_version_2_twin_gives(self):
        names = ('sms', 'gb', 'nes', 'md', 'snes', 'ng')
        rows = {'sms': {FIXTURES['sms'][1]: [[1, 0x300, 0, 2, 0x10]]}}
        gathered = collected(*names, observations=rows)
        old, new = self.folder / 'old.rrknowledge', self.folder / 'new.rrknowledge'
        self.assertEqual(kx.write_knowledge(gathered, old, channel=None)['version'], 2)
        self.assertEqual(kx.write_knowledge(gathered, new, channel=None, version=3)['version'], 3)
        self.assertEqual((header(old)['version'], header(new)['version']), (2, 3))
        self.assertEqual(header(new)['knowledge']['schema'], 3)
        first, second = kx.read_exchange(old), kx.read_exchange(new)
        self.assertEqual(second['knowledge'], first['knowledge'], 'the readers see schema 1 whatever the version')
        self.assertEqual(second['knowledge'], gathered['payload'])
        self.assertEqual((first['version'], second['version']), (2, 3))
        self.assertEqual(second['observations'], first['observations'])
        self.assertEqual(second['titles'], first['titles'])

    def test_the_default_is_version_2_and_only_3_is_asked_for(self):
        self.assertEqual((kx.VERSION, kx.LATEST_VERSION, kx.READ_VERSIONS), (2, 3, (1, 2, 3)))
        with self.assertRaises(ValueError):
            kx.write_knowledge(collected('sms'), self.folder / 'x.rrknowledge', channel=None, version=1)
        with self.assertRaises(ValueError):
            kx.write_knowledge(collected('sms'), self.folder / 'x.rrknowledge', channel=None, version=4)

    def test_a_record_with_no_valid_schema_3_form_falls_back_to_version_2(self):
        # Schema 1 allows an odd Mega Drive RAM length; schema 3 follows the local code (even, 2 to 16).
        gathered = collected('md')
        gathered['payload']['consoles']['md'][FIXTURES['md'][1]]['ram_refs'] = [[0xff0002, 4096, 3]]
        path = self.folder / 'odd.rrknowledge'
        written = kx.write_knowledge(gathered, path, channel=None, version=3)
        self.assertEqual((written['version'], header(path)['version']), (2, 2))
        self.assertEqual(kx.read_exchange(path)['knowledge'], gathered['payload'])
        with self.assertRaises(ValueError):
            kx.write_knowledge(gathered, path, channel=None, version=3, fallback=False)

    def test_what_a_version_3_file_may_not_hold_is_refused(self):
        good = self.folder / 'good.rrknowledge'
        kx.write_knowledge(collected('md', 'sms'), good, channel=None, version=3)
        base = header(good)
        md_key = 'md:' + FIXTURES['md'][1]

        def refused(document, why):
            path = self.folder / 'bad.rrknowledge'
            path.write_bytes(gzip.compress(json.dumps(document).encode()))
            with self.assertRaises((ValueError, TypeError, KeyError), msg=why):
                kx.read_exchange(path)

        refused({**base, 'version': 4}, 'a later version')
        refused({**base, 'version': True}, 'a boolean is not a version')
        refused({**base, 'knowledge': {'schema': 1, 'consoles': {}}}, 'schema 1 in a version 3 file')
        refused({**base, 'version': 2}, 'schema 3 in a version 2 file')
        refused({**base, 'knowledge': {**base['knowledge'], 'extra': 1}}, 'an unknown key')
        broken = copy.deepcopy(base)
        broken['knowledge']['games'][md_key]['cpus']['m68k']['paths']['entries'][0]['table'] = {'n': 1, 'cols': [
            {'enc': 'list', 'v': [2 ** 40]}]}
        refused(broken, 'an offset outside the ROM')
        moved = copy.deepcopy(base)
        moved['knowledge']['games']['sms:' + SHA] = moved['knowledge']['games'].pop(md_key)
        refused(moved, 'a record filed under another game')
        from tests.test_paths_schema import x68_document
        machine = copy.deepcopy(base)
        document = x68_document()
        machine['knowledge']['games'][document['game']] = document
        pp.validate_game(document)                                    # a valid schema 3 record...
        refused(machine, 'a machine that shares nothing yet')          # ...that no file shares yet
        extra = copy.deepcopy(base)
        extra['knowledge']['games'][md_key]['devices'] = {'gsu': {'core': ENGINE, 'paths': {}}}
        refused(extra, 'a device on a Mega Drive game')
        titled = copy.deepcopy(base)
        titled['titles'] = {'md': {'ab' * 32: 'not in the file'}}
        refused(titled, 'a title for a game the file does not hold')

    def test_a_version_1_file_is_still_read(self):
        path = self.folder / 'v1.rrknowledge'
        document = {'format': 'retro-recomp-knowledge', 'version': 1, 'converter': '1.2.5',
                    'knowledge': legacy_payload('md'), 'titles': {}}
        path.write_bytes(gzip.compress(json.dumps(document).encode()))
        self.assertEqual(kx.read_exchange(path)['knowledge'], legacy_payload('md'))

    def test_importing_a_version_3_file_gives_the_bank_a_version_2_file_gives(self):
        gathered = collected('md', 'sms', 'snes', observations={'sms': {FIXTURES['sms'][1]: [[1, 0x300, 0, 2, 0x10]]}})
        banks = []
        for version in (2, 3):
            with tempfile.TemporaryDirectory() as temp:
                bank = Path(temp) / 'knowledge' / 'imported.json.gz'
                with patch('retrorecomp.knowledge.imported_path', return_value=bank), \
                        patch('retrorecomp.knowledge_exchange.imported_path', return_value=bank), \
                        patch('retrorecomp.paths.data_directory', return_value=Path(temp)):
                    path = Path(temp) / f'v{version}.rrknowledge'
                    kx.write_knowledge(gathered, path, channel=None, version=version)
                    preview = kx.preview_import(path)
                    outcome = kx.import_knowledge(path)
                    banks.append((preview, outcome, knowledge.read(bank), kx._observation_bank()))
        self.assertGreater(banks[0][0]['discoveries'], 0)
        self.assertEqual(banks[0][0], banks[1][0])
        self.assertEqual({k: banks[0][1][k] for k in ('games', 'consoles', 'new', 'enriched')},
                         {k: banks[1][1][k] for k in ('games', 'consoles', 'new', 'enriched')})
        self.assertEqual(banks[0][2], banks[1][2])
        self.assertEqual(banks[0][3], banks[1][3])

    def test_the_paths_the_claims_name_do_not_depend_on_the_version(self):
        gathered = collected('md', 'snes', 'ng')
        keys = []
        for version in (2, 3):
            path = self.folder / f'claims{version}.rrknowledge'
            kx.write_knowledge(gathered, path, channel=None, version=version)
            keys.append(kx.discovery_paths(kx.read_exchange(path)))
        self.assertEqual(keys[0], keys[1])
        self.assertTrue(any(game['hints'] for game in keys[0].values()))

    def test_a_version_3_file_is_smaller_for_large_ordered_paths(self):
        # The point of the codecs: sorted offsets are a first value and small gaps.
        record = {'engine': ENGINE, 'rom_bytes': 1 << 20, 'rom_entries': [[0x200 + 2 * number] for number in range(20000)]}
        gathered = collected('md')
        gathered['payload']['consoles']['md'][FIXTURES['md'][1]] = record
        sizes = {}
        for version in (2, 3):
            path = self.folder / f'size{version}.rrknowledge'
            sizes[version] = kx.write_knowledge(gathered, path, channel=None, version=version)['bytes']
        self.assertLess(sizes[3], sizes[2] // 4)


class EntryFormatTests(unittest.TestCase):
    def grouped(self):
        return grouped_entry(part(47, 'extended', (0x100, 0x180), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x140,)),
                             part(60, 'standard', record=False, rows=[[1, 0x400, 0, 2, 0x20]]),
                             qualified=[qualified((0x100,)), qualified((0x180,), engine='d' * 40, by='maintainer')])

    def test_a_grouped_game_goes_up_to_format_3_and_is_read_back_whole(self):
        value = self.grouped()
        up = kx.entry_to_v3(value)
        self.assertEqual(up['format'], 3)
        self.assertEqual([item['cores'] for item in up['qualified']], sorted(item['engine'] for item in value['qualified']))
        self.assertTrue(all(item['record']['schema'] == 3 for item in up['qualified']))
        self.assertEqual([part_['source'] for part_ in up['parts']], [47, 52, 60])
        self.assertIsNone(up['parts'][2]['record'])
        self.assertEqual(up['parts'][2]['observations'], [[1, 0x400, 0, 2, 0x20]])
        sha = hashlib.sha256(kx.canonical_bytes(up)).hexdigest()
        read = kx.base_entry(sha, up, 'sms', IDENTITY)
        self.assertEqual(read.pop('format'), 3)
        self.assertEqual(read['sources'], [47, 52, 60])
        self.assertEqual([item['record'] for item in read['qualified']], [item['record'] for item in value['qualified']])
        self.assertEqual([part_['record'] for part_ in read['parts']], [part_['record'] for part_ in value['parts']])
        self.assertEqual([item['engine'] for item in read['qualified']], [item['engine'] for item in value['qualified']])

    def test_a_format_3_entry_is_checked_before_it_is_used(self):
        value3 = kx.entry_to_v3(self.grouped())
        sha3 = hashlib.sha256(kx.canonical_bytes(value3)).hexdigest()
        self.assertIsNone(kx.base_entry('0' * 64, value3, 'sms', IDENTITY), 'named by the hash of another text')
        self.assertIsNone(kx.base_entry(sha3, value3, 'sms', 'cd' * 32), 'another game')
        self.assertIsNone(kx.base_entry(sha3, value3, 'gg', IDENTITY), 'another console')
        extra = {**value3, 'extra': 1}
        self.assertIsNone(kx.base_entry(hashlib.sha256(kx.canonical_bytes(extra)).hexdigest(), extra, 'sms', IDENTITY))
        # `engine` is the word of the entries of 1.6.0 and before: an element without `cores` is skipped, not the game.
        misnamed = copy.deepcopy(value3)
        misnamed['qualified'][0]['engine'] = misnamed['qualified'][0].pop('cores')
        found = kx.base_entry(hashlib.sha256(kx.canonical_bytes(misnamed)).hexdigest(), misnamed, 'sms', IDENTITY)
        self.assertEqual(len(found['qualified']), len(value3['qualified']) - 1)
        self.assertEqual(len(found['parts']), 3)
        # A schema 3 record that does not validate (an entry outside the ROM) or of another game: skipped.
        broken = copy.deepcopy(value3)
        broken['parts'][0]['record']['identity']['sources']['rom']['bytes'] = 8192
        broken['parts'][0]['record']['cpus']['z80']['paths']['entries'][0]['table']['n'] = 7
        stranger = copy.deepcopy(value3)
        stranger['parts'][1]['record']['game'] = 'sms:' + 'cd' * 32
        found = kx.base_entry(hashlib.sha256(kx.canonical_bytes(broken)).hexdigest(), broken, 'sms', IDENTITY)
        self.assertEqual([part_['source'] for part_ in found['parts']], [52, 60])
        self.assertEqual(found['sources'], [47, 52, 60], 'sources still names every part')
        found = kx.base_entry(hashlib.sha256(kx.canonical_bytes(stranger)).hexdigest(), stranger, 'sms', IDENTITY)
        self.assertEqual([part_['source'] for part_ in found['parts']], [47, 60])
        # A record in the schema 1 shape is not a schema 3 record.
        legacy_in_3 = copy.deepcopy(value3)
        legacy_in_3['parts'][0]['record'] = self.grouped()['parts'][0]['record']
        found = kx.base_entry(hashlib.sha256(kx.canonical_bytes(legacy_in_3)).hexdigest(), legacy_in_3, 'sms', IDENTITY)
        self.assertEqual([part_['source'] for part_ in found['parts']], [52, 60])
        # Entries of the formats 1 and 2 (converters before 1.6.0) are not read any more.
        for old_format in (1, 2):
            old = {**self.grouped(), 'format': old_format}
            if old_format == 1:
                del old['qualified']
            self.assertIsNone(kx.base_entry(hashlib.sha256(kx.canonical_bytes(old)).hexdigest(), old, 'sms', IDENTITY))

    def test_what_schema_3_cannot_hold_is_left_out_and_counted(self):
        # A schema 1 record that schema 3 refuses (an odd Mega Drive RAM length).
        md = {'engine': ENGINE, 'rom_bytes': 1 << 20, 'rom_entries': [[0x200]], 'ram_refs': [[0xff0002, 4096, 3]]}
        md_entry = grouped_entry(part(5, 'standard', record=False), identity='ee' * 32, system='md',
                                 qualified=[qualified(record=md), qualified(record={**md, 'ram_refs': [[0xff0002, 4096, 4]]},
                                                                           engine='d' * 40)])
        md_entry['parts'][0]['record'] = md
        report = {}
        up = kx.entry_to_v3(md_entry, report)
        self.assertEqual(report, {'qualified': 1, 'parts': 1})
        self.assertEqual([item['cores'] for item in up['qualified']], ['d' * 40])
        self.assertIsNone(up['parts'][0]['record'])
        # A schema 3 record of several cores has no schema 1 form for the readers behind the base: skipped.
        document = pp.to_v3(*FIXTURES['md'])
        document['cpus']['z80']['core'] = 'e' * 40
        multi = {'format': 3, 'system': 'md', 'identity': FIXTURES['md'][1], 'parts': [],
                 'qualified': [{'cores': ENGINE, 'level': 'standard', 'by': 'players', 'record': document}]}
        read = kx.base_entry(hashlib.sha256(kx.canonical_bytes(multi)).hexdigest(), multi, 'md', FIXTURES['md'][1])
        self.assertEqual(read['qualified'], [])


class ArchiveFormatTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def head(self, data, **options):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return kx.read_archive_head(archive, **options)

    def test_an_archive_and_its_index_name_the_one_format(self):
        built = entry(part(1, 'standard', (0x100,)))
        data = base_archive(5, {KEY: (built[0], [1])}, {built[0]: built[1]})
        head = self.head(data)
        self.assertEqual((head['format'], head['index']['format'], head['version']), (3, 3, 5))
        self.assertEqual(self.head(data, version=5)['version'], 5)
        with self.assertRaises(kx.BaseArchiveError):
            self.head(data, version=6)
        # The format 2 base of the converters before 1.6.0 is not a base.
        data2 = base_archive(5, {KEY: (built[0], [1])}, {built[0]: built[1]}, format=2)
        with self.assertRaises(kx.BaseArchiveError):
            self.head(data2)
        # The manifest says 3 and the index says 2 (or the other way): not one base.
        for manifest_format, index_format in ((3, 2), (2, 3)):
            index = {'format': index_format, 'version': 5, 'built_utc': 'x', 'games': {}}
            raw = kx.canonical_bytes(index)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w') as archive:
                archive.writestr('manifest.json', json.dumps({'format': manifest_format, 'version': 5, 'built_utc': 'x',
                                                              'games': 0, 'index_sha256': hashlib.sha256(raw).hexdigest()}))
                archive.writestr('index.json', raw)
            with self.assertRaises(kx.BaseArchiveError):
                self.head(buffer.getvalue())
        for unknown in (1, 2, 4):
            self.assertIsNone(kx.parse_base_index(kx.canonical_bytes({'format': unknown, 'version': 1, 'games': {}})))

    def test_only_a_format_3_archive_is_applied(self):
        built = entry(part(1, 'standard', (0x100,)))
        bank = self.folder / 'datas' / 'knowledge' / 'imported.json.gz'
        path = self.folder / 'base.zip'
        with patch('retrorecomp.knowledge.imported_path', return_value=bank), \
                patch('retrorecomp.knowledge_exchange.imported_path', return_value=bank), \
                patch('retrorecomp.knowledge_exchange.installer_base_path', return_value=self.folder / 'none.zip'):
            path.write_bytes(base_archive(5, {KEY: (built[0], [1])}, {built[0]: built[1]}, format=2))
            with self.assertRaises(kx.BaseArchiveError):
                kx.apply_base_archive(path, version=5)
            self.assertIsNone(kx.local_base(), 'a refused archive changes nothing')
            path.write_bytes(base_archive(5, {KEY: (built[0], [1])}, {built[0]: built[1]}))
            base = kx.apply_base_archive(path, version=5)
            self.assertEqual((base['format'], base['version']), (3, 5))
            self.assertEqual(kx.local_base()['format'], 3)
            with kx.BaseEntries() as entries:
                text = entries.text(built[0])
            self.assertEqual(kx.base_entry(built[0], json.loads(text), 'sms', IDENTITY)['parts'][0]['record']['rom_entries'],
                             [[0x100, 0, 0, 0, 1]])


class OneLineTests(BaseHarness):
    """The base is one line, format 3, read at `GET base3`; the stub `GET base` of the service is never asked."""

    def rows(self):
        return knowledge.imported_record('sms', IDENTITY).get('rom_entries')

    def grown(self):
        return entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)), part(60, 'thorough', (0x200,)))

    def test_a_converter_without_a_base_reads_base3_and_never_the_stub(self):
        first = entry(part(47, 'extended', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)))
        self.publish(7, {KEY: (first[0], [47, 52])}, entries=[first])
        prepared = online.prepare_batch([KEY])
        update = prepared['base']['update']
        self.assertEqual((update['version'], update['source'], update['error']), (7, 'full', None))
        self.assertEqual(self.gets(), ['base3', 'dl/retro-recomp-base3-7.zip'])
        self.assertEqual(self.rows(), [[0x100, 0, 0, 0, 1], [0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [[1, 0x300, 0, 2, 0x10]])
        self.assertEqual(kx.local_base()['format'], 3)

    def test_the_installers_copy_follows_by_difference(self):
        first = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)))
        self.install(3, {KEY: (first[0], [47, 52])}, [first])
        self.publish(3, {KEY: (first[0], [47, 52])}, entries=[first], full=False)
        grown = self.grown()
        self.publish(4, {KEY: (grown[0], [47, 52, 60])}, entries=[first, grown], full=False)
        summary = online.sync_base([KEY])
        self.assertEqual(self.gets(), ['base3', 'base3/files/retro-recomp-base3-3-4.zip'])
        self.assertEqual((summary['version'], summary['update']['source'], summary['origin']), (4, 'delta', 'download'))
        self.assertEqual(len(self.rows()), 3)

    def test_the_cursor_revocations_and_quarantine_come_from_the_manifest(self):
        first = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)))
        self.publish(5, {KEY: (first[0], [47, 52])}, entries=[first], revoked=[52], quarantined=[[47, KEY]], cursor=33)
        online.sync_base([KEY])
        site = json.loads((self.store / 'site.json').read_text(encoding='utf-8'))
        self.assertEqual((site['revoked'], site['quarantined'], site['cursor']), ([52], [[47, KEY]], 33))
        self.assertEqual(self.rows(), None, 'the only two sources are barred')

    def test_a_downloaded_base_of_format_2_is_set_aside_for_the_installers_copy(self):
        first = entry(part(47, 'extended', (0x100,)))
        self.install(3, {KEY: (first[0], [47])}, [first])
        # What a converter of 1.6.0 left on a disk that had followed the format 2 line: version 9, format 2.
        index = kx.canonical_bytes({'format': 2, 'version': 9, 'built_utc': 'x', 'games': {}})
        self.store.mkdir(parents=True)
        (self.store / 'index.json').write_bytes(index)
        kx.write_base_state({'version': 9, 'index_sha256': hashlib.sha256(index).hexdigest(), 'origin': 'download',
                             'cursor': 0}, self.url)
        base = kx.local_base()
        self.assertEqual((base['version'], base['origin'], base['format']), (3, 'installer', 3))
        kx.settle_local_base(self.url)
        self.assertEqual(kx.read_base_state()['origin'], 'installer')
        self.assertFalse((self.store / 'index.json').exists())

    def test_an_installers_copy_of_format_2_is_not_a_base(self):
        old = entry(part(47, 'extended', (0x100,)))
        self.installer.parent.mkdir(parents=True, exist_ok=True)
        self.installer.write_bytes(base_archive(3, {KEY: (old[0], [47])}, {old[0]: old[1]}, format=2))
        self.assertIsNone(kx.installer_base())
        self.assertIsNone(kx.local_base())

    def test_a_base_older_than_every_difference_reports_no_path_and_keeps_its_base(self):
        first = entry(part(47, 'extended', (0x100,)))
        self.install(3, {KEY: (first[0], [47])}, [first])
        grown = self.grown()
        self.publish(9, {KEY: (grown[0], [47, 52, 60])}, entries=[grown], full=False)
        self.server.base['manifest']['deltas'] = {}
        summary = online.sync_base([KEY])
        self.assertEqual((summary['update']['error'], summary['version']), ('no_path', 3))

    def test_the_qualified_bank_keeps_its_shape(self):
        value = entry(part(47, 'standard', (0x100,)), qualified=[qualified((0x100, 0x140))])
        self.publish(2, {KEY: (value[0], [47])}, entries=[value])
        summary = online.sync_base([KEY])
        self.assertEqual(summary['qualified'], 1)
        bank = knowledge.read(kx.qualified_bank_path())
        self.assertEqual(bank['schema'], 1, 'the bank is still schema 1')
        self.assertEqual(bank['consoles']['sms'][IDENTITY]['rom_entries'], [[0x100, 0, 0, 0, 1], [0x140, 0, 0, 0, 1]])


class UploadVersionTests(BaseHarness):
    def test_an_upload_is_a_version_3_file_whatever_the_service_lists(self):
        self.sign_in()
        gathered = collected('md')
        gathered['levels'] = {}
        for listed in (None, [1, 2], [1, 2, 3]):
            self.server.calls.clear()
            self.server.hits.clear()
            self.server.knowledge_versions = listed
            with patch('retrorecomp.knowledge_exchange.mark_shared'):
                online._send_one(gathered, online.account())
            body = [call for call in self.server.calls if call[1].endswith('/contributions')][0][3]
            document = json.loads(gzip.decompress(body))
            self.assertEqual((document['version'], document['knowledge']['schema']), (3, 3), listed)
            self.assertFalse([hit for hit in self.server.hits if hit[1].endswith('/status')], 'the service is not asked')


if __name__ == '__main__':
    unittest.main()
