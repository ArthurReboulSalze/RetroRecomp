"""Schema 3 of the paths travels (stage B2): the exchange file, the shared base and the upload.

`.rrknowledge` version 3 and the second line of the shared base (index, entry and archive format 3) carry
the CPU-keyed records of `path_profiles`; everything after the readers still works on schema 1 records
(the qualified bank keeps its shape), so a version 3 file or a format 3 entry gives exactly the paths its
version 2 twin gives. A converter reads both lines of the base and both versions of a file, writes
version 2 unless the receiver says it reads 3, and stays on the line its local base is in.
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
from tests.test_shared_base import (BaseHarness, BaseService, IDENTITY, KEY, base_archive, calls_after, entry,
                                    part, qualified)
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
        cps = copy.deepcopy(base)
        cps['knowledge']['games']['cps1:' + SHA] = {
            'schema': 3, 'game': 'cps1:' + SHA, 'devices': {},
            'identity': {'system': 'cps1', 'sources': {'maincpu': {'bytes': 4096}}, 'layout': {}},
            'cpus': {'m68k': {'map': 'cps1', 'core': ENGINE, 'paths': {}}}}
        pp.validate_game(cps['knowledge']['games']['cps1:' + SHA])   # a valid schema 3 record...
        refused(cps, 'a machine that shares nothing yet')           # ...that no file shares yet
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


class EntryProjectionTests(unittest.TestCase):
    def entry2(self):
        return entry(part(47, 'extended', (0x100, 0x180), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x140,)),
                     part(60, 'standard', record=False, rows=[[1, 0x400, 0, 2, 0x20]]),
                     qualified=[qualified((0x100,)), qualified((0x180,), engine='d' * 40, by='maintainer')])

    def test_a_format_2_entry_goes_up_and_comes_back_the_same(self):
        sha, value = self.entry2()
        up = kx.entry_to_v3(value)
        self.assertEqual(up['format'], 3)
        self.assertEqual([item['cores'] for item in up['qualified']], sorted(item['engine'] for item in value['qualified']))
        self.assertTrue(all(item['record']['schema'] == 3 for item in up['qualified']))
        self.assertEqual([part_['source'] for part_ in up['parts']], [47, 52, 60])
        self.assertIsNone(up['parts'][2]['record'])
        self.assertEqual(up['parts'][2]['observations'], [[1, 0x400, 0, 2, 0x20]])
        self.assertEqual(kx.entry_to_v2(up), value)

    def test_the_base_reads_a_format_3_entry_to_what_the_format_2_entry_gives(self):
        sha2, value = self.entry2()
        value3 = kx.entry_to_v3(value)
        sha3 = hashlib.sha256(kx.canonical_bytes(value3)).hexdigest()
        self.assertNotEqual(sha2, sha3)
        old = kx.base_entry(sha2, value, 'sms', IDENTITY)
        new = kx.base_entry(sha3, value3, 'sms', IDENTITY)
        self.assertEqual(new.pop('format'), 3)
        self.assertEqual(old.pop('format'), 2)
        self.assertEqual(new, old)

    def test_a_format_3_entry_is_checked_like_a_format_2_one(self):
        sha2, value = self.entry2()
        value3 = kx.entry_to_v3(value)
        sha3 = hashlib.sha256(kx.canonical_bytes(value3)).hexdigest()
        self.assertIsNone(kx.base_entry(sha2, value3, 'sms', IDENTITY), 'named by the hash of another text')
        self.assertIsNone(kx.base_entry(sha3, value3, 'sms', 'cd' * 32), 'another game')
        self.assertIsNone(kx.base_entry(sha3, value3, 'gg', IDENTITY), 'another console')
        extra = {**value3, 'extra': 1}
        self.assertIsNone(kx.base_entry(hashlib.sha256(kx.canonical_bytes(extra)).hexdigest(), extra, 'sms', IDENTITY))
        # `engine` is format 2's word: a format 3 qualified element without `cores` is skipped, not the game.
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
        # A record of a version-2 record shape is not a schema 3 record.
        legacy_in_3 = copy.deepcopy(value3)
        legacy_in_3['parts'][0]['record'] = value['parts'][0]['record']
        found = kx.base_entry(hashlib.sha256(kx.canonical_bytes(legacy_in_3)).hexdigest(), legacy_in_3, 'sms', IDENTITY)
        self.assertEqual([part_['source'] for part_ in found['parts']], [52, 60])

    def test_a_base_projects_up_and_down_with_the_same_games_and_sources(self):
        entries, games = {}, {}
        for number, addresses in enumerate(((0x100,), (0x100, 0x200), (0x300,))):
            identity = '%064x' % (number + 1)
            sha, value = entry(part(number + 1, 'standard', addresses), identity=identity,
                               qualified=[qualified(addresses)])
            entries[sha] = kx.canonical_bytes(value).decode('ascii')
            games[f'sms:{identity}'] = {'entry': sha, 'sources': [number + 1]}
        report = {}
        up, up_games = kx.project_base(entries, games, 3, report)
        self.assertEqual(report, {})
        self.assertEqual(set(up_games), set(games))
        self.assertTrue(all(up_games[key]['sources'] == games[key]['sources'] for key in games))
        self.assertTrue(set(up).isdisjoint(entries), 'a format 3 entry is another text, so another name')
        down, down_games = kx.project_base(up, up_games, 2, report)
        self.assertEqual((down, down_games), (entries, games))
        with self.assertRaises(ValueError):
            kx.project_base(entries, games, 4)

    def test_what_the_other_schema_cannot_hold_is_left_out_and_counted(self):
        sha, value = self.entry2()
        # A schema 1 record that schema 3 refuses (an odd Mega Drive RAM length).
        md = {'engine': ENGINE, 'rom_bytes': 1 << 20, 'rom_entries': [[0x200]], 'ram_refs': [[0xff0002, 4096, 3]]}
        sha_md, md_entry = entry(part(5, 'standard', record=False), identity='ee' * 32, system='md',
                                 qualified=[qualified(record=md), qualified(record={**md, 'ram_refs': [[0xff0002, 4096, 4]]},
                                                                           engine='d' * 40)])
        md_entry['parts'][0]['record'] = md
        report = {}
        up = kx.entry_to_v3(md_entry, report)
        self.assertEqual(report, {'qualified': 1, 'parts': 1})
        self.assertEqual([item['cores'] for item in up['qualified']], ['d' * 40])
        self.assertIsNone(up['parts'][0]['record'])
        # A schema 3 record of several cores has no schema 1 form either.
        document = pp.to_v3(*FIXTURES['md'])
        document['cpus']['z80']['core'] = 'e' * 40
        multi = {'format': 3, 'system': 'md', 'identity': FIXTURES['md'][1], 'parts': [],
                 'qualified': [{'cores': ENGINE, 'level': 'standard', 'by': 'players', 'record': document}]}
        report = {}
        down = kx.entry_to_v2(multi, report)
        self.assertEqual(report, {'qualified': 1})
        self.assertEqual(down['qualified'], [])


def archive3(version, games, entries, wanted=None, built='2026-10-27T03:00:00+00:00', format=3):
    """A base archive of `format` (3: line 3). `games` is {key: (entry sha, [sources])}, `entries` {sha: value}."""
    index = {'format': format, 'version': version, 'built_utc': built,
             'games': {key: {'entry': value[0], 'sources': list(value[1])} for key, value in games.items()}}
    raw = kx.canonical_bytes(index)
    manifest = {'format': format, 'version': version, 'built_utc': built, 'games': len(games),
                'index_sha256': hashlib.sha256(raw).hexdigest()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest))
        archive.writestr('index.json', raw)
        for sha in sorted({value[0] for value in games.values()} if wanted is None else wanted):
            if sha in entries:
                archive.writestr(f'entries/{sha}.json', kx.canonical_bytes(entries[sha]))
    return buffer.getvalue()


def entry3(*parts, **options):
    """(sha, value) of the format 3 twin of `entry(*parts, **options)`."""
    value = kx.entry_to_v3(entry(*parts, **options)[1])
    return hashlib.sha256(kx.canonical_bytes(value)).hexdigest(), value


class ArchiveFormatTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)

    def head(self, data, **options):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return kx.read_archive_head(archive, **options)

    def test_an_archive_and_its_index_name_one_format(self):
        built = entry3(part(1, 'standard', (0x100,)))
        data = archive3(5, {KEY: (built[0], [1])}, {built[0]: built[1]})
        head = self.head(data)
        self.assertEqual((head['format'], head['index']['format'], head['version']), (3, 3, 5))
        self.assertEqual(self.head(data, format=3)['version'], 5)
        with self.assertRaises(kx.BaseArchiveError):
            self.head(data, format=2)
        old = entry(part(1, 'standard', (0x100,)))
        data2 = base_archive(5, {KEY: (old[0], [1])}, {old[0]: old[1]})
        self.assertEqual(self.head(data2)['format'], 2)
        with self.assertRaises(kx.BaseArchiveError):
            self.head(data2, format=3)
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
        for unknown in (1, 4):
            self.assertIsNone(kx.parse_base_index(kx.canonical_bytes({'format': unknown, 'version': 1, 'games': {}})))

    def test_an_archive_is_applied_in_its_line_only(self):
        built = entry3(part(1, 'standard', (0x100,)))
        data = archive3(5, {KEY: (built[0], [1])}, {built[0]: built[1]})
        path = self.folder / 'line3.zip'
        path.write_bytes(data)
        bank = self.folder / 'datas' / 'knowledge' / 'imported.json.gz'
        with patch('retrorecomp.knowledge.imported_path', return_value=bank), \
                patch('retrorecomp.knowledge_exchange.imported_path', return_value=bank), \
                patch('retrorecomp.knowledge_exchange.installer_base_path', return_value=self.folder / 'none.zip'):
            with self.assertRaises(kx.BaseArchiveError):
                kx.apply_base_archive(path, version=5, format=2)
            self.assertIsNone(kx.local_base(), 'a refused archive changes nothing')
            base = kx.apply_base_archive(path, version=5, format=3)
            self.assertEqual((base['format'], base['version']), (3, 5))
            self.assertEqual(kx.local_base()['format'], 3)
            with kx.BaseEntries() as entries:
                text = entries.text(built[0])
            self.assertEqual(kx.base_entry(built[0], json.loads(text), 'sms', IDENTITY)['parts'][0]['record']['rom_entries'],
                             [[0x100, 0, 0, 0, 1]])


class Base3Service(BaseService):
    """BaseService plus line 3: `server.base3` holds `manifest` (None: not served, 404), `files`, and
    `fail` ('format' answers a format 2 manifest); `GET status` lists `server.knowledge_versions`."""

    def do_GET(self):
        path = self.path.split('?')[0]
        base3 = self.server.base3
        if path.endswith('/api/v1/base3'):
            self.server.hits.append(('GET', path))
            if base3['manifest'] is None:
                self.answer(404, {'error': 'not_found'})
            elif base3.get('fail') == 'format':
                self.answer(200, {**base3['manifest'], 'format': 2})
            else:
                self.answer(200, base3['manifest'])
        elif '/api/v1/base3/files/' in path:
            self.server.hits.append(('GET', path))
            self.file(base3['files'].get(path.rsplit('/', 1)[1]))
        elif path.endswith('/api/v1/status'):
            self.server.hits.append(('GET', path))
            self.answer(200, {'service': 'retro-recomp', 'api': 1, 'accepting': True, 'min_converter': '1.5.3',
                              **({'knowledge_versions': self.server.knowledge_versions}
                                 if self.server.knowledge_versions is not None else {})})
        else:
            super().do_GET()


class LineHarness(BaseHarness):
    def setUp(self):
        super().setUp()
        self.server.RequestHandlerClass = Base3Service
        self.server.base3 = {'manifest': None, 'files': {}, 'versions': {}, 'entries': {}}
        self.server.knowledge_versions = None
        online._UPLOAD_VERSION.update(asked=0.0, version=2, service='')
        self.addCleanup(online._UPLOAD_VERSION.update, asked=0.0, version=2, service='')

    def publish_lines(self, version, games2, entries2, games3=None, entries3=None, *, line3=True, full3=True,
                      full2=True, cursor=0, advertise=True):
        """Version `version` in both lines: line 2 as `publish` does, line 3 with its own archives."""
        self.publish(version, games2, entries=entries2, full=full2, cursor=cursor)
        base3 = self.server.base3
        manifest = self.server.base['manifest']
        manifest['lines'] = [2, 3] if (line3 and advertise) else [2]
        if not line3:
            base3['manifest'] = None
            return
        base3['entries'].update(dict(entries3))
        base3['versions'][version] = dict(games3)
        deltas, full = {}, None
        if full3:
            name = f'retro-recomp-base3-{version}.zip'
            blob = archive3(version, base3['versions'][version], base3['entries'])
            self.server.base['downloads'][name] = blob
            full = {'version': version, 'url': f'{self.url}/dl/{name}', 'sha256': hashlib.sha256(blob).hexdigest(),
                    'bytes': len(blob)}
        for earlier, before in base3['versions'].items():
            if earlier >= version:
                continue
            name = f'retro-recomp-base3-{earlier}-{version}.zip'
            blob = archive3(version, games3, base3['entries'],
                            {value[0] for value in games3.values()} - {value[0] for value in before.values()})
            base3['files'][name] = blob
            deltas[str(earlier)] = {'file': name, 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}
        base3['manifest'] = {'format': 3, 'formats': [3], 'version': version, 'built_utc': manifest['built_utc'],
                             'published_utc': manifest['published_utc'], 'cursor': cursor, 'min_converter': '1.5.4',
                             'games': len(games3), 'revoked': manifest['revoked'], 'full': full, 'deltas': deltas}

    def install3(self, version, games, entries):
        self.installer.parent.mkdir(parents=True, exist_ok=True)
        self.installer.write_bytes(archive3(version, games, dict(entries)))

    def rows(self):
        return knowledge.imported_record('sms', IDENTITY).get('rom_entries')


class BaseLineTests(LineHarness):
    def two_lines(self, version=7, extra=()):
        first2 = entry(part(47, 'extended', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)), *extra)
        first3 = (hashlib.sha256(kx.canonical_bytes(kx.entry_to_v3(first2[1]))).hexdigest(), kx.entry_to_v3(first2[1]))
        self.publish_lines(version, {KEY: (first2[0], [47, 52])}, [first2], {KEY: (first3[0], [47, 52])}, [first3])
        return first2, first3

    def test_a_converter_without_a_base_starts_on_line_3_and_reads_its_entries(self):
        self.two_lines()
        self.server.calls.clear()
        prepared = online.prepare_batch([KEY])
        update = prepared['base']['update']
        self.assertEqual((update['version'], update['source'], update['error']), (7, 'full', None))
        self.assertEqual(self.gets(), ['base', 'base3', 'dl/retro-recomp-base3-7.zip'])
        self.assertEqual(prepared['base']['games'], 1)
        self.assertEqual(self.rows(), [[0x100, 0, 0, 0, 1], [0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [[1, 0x300, 0, 2, 0x10]])
        self.assertEqual(kx.local_base()['format'], 3)
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'extended', 'records': 2}})

    def test_a_base_in_line_3_is_updated_by_the_line_3_difference(self):
        first2, first3 = self.two_lines(3)
        online.sync_base([KEY])
        self.server.hits.clear()
        grown2 = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)), part(60, 'thorough', (0x200,)))
        grown3 = (hashlib.sha256(kx.canonical_bytes(kx.entry_to_v3(grown2[1]))).hexdigest(), kx.entry_to_v3(grown2[1]))
        self.publish_lines(4, {KEY: (grown2[0], [47, 52, 60])}, [grown2], {KEY: (grown3[0], [47, 52, 60])}, [grown3])
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual(self.gets(), ['base', 'base3', 'base3/files/retro-recomp-base3-3-4.zip'])
        self.assertEqual((summary['version'], summary['update']['source'], summary['update']['error']), (4, 'delta', None))
        self.assertEqual(kx.local_base()['format'], 3)
        self.assertEqual(self.rows(), [[0x100, 0, 0, 0, 1], [0x180, 0, 0, 0, 1], [0x200, 0, 0, 0, 1]])
        # Nothing new: the manifest of line 2 alone says so.
        self.server.hits.clear()
        online.sync_base([KEY], now=self.later(2))
        self.assertEqual(self.gets(), ['base'])

    def test_the_installers_copy_in_line_3_is_enough_to_follow_by_difference(self):
        first2, first3 = self.two_lines(3)
        self.install3(3, {KEY: (first3[0], [47, 52])}, [first3])
        grown2 = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)), part(60, 'thorough', (0x200,)))
        grown3 = (hashlib.sha256(kx.canonical_bytes(kx.entry_to_v3(grown2[1]))).hexdigest(), kx.entry_to_v3(grown2[1]))
        self.publish_lines(4, {KEY: (grown2[0], [47, 52, 60])}, [grown2], {KEY: (grown3[0], [47, 52, 60])}, [grown3],
                           full3=False, full2=False)
        summary = online.sync_base([KEY])
        self.assertEqual(self.gets(), ['base', 'base3', 'base3/files/retro-recomp-base3-3-4.zip'])
        self.assertEqual((summary['version'], summary['update']['source'], summary['origin']), (4, 'delta', 'download'))
        self.assertEqual(len(self.rows()), 3)

    def test_a_base_in_line_2_stays_in_line_2_while_its_line_leads_to_the_latest_version(self):
        first2, first3 = self.two_lines(3)
        self.install(3, {KEY: (first2[0], [47, 52])}, [first2])
        grown2 = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)), part(60, 'thorough', (0x200,)))
        grown3 = (hashlib.sha256(kx.canonical_bytes(kx.entry_to_v3(grown2[1]))).hexdigest(), kx.entry_to_v3(grown2[1]))
        self.publish_lines(4, {KEY: (grown2[0], [47, 52, 60])}, [grown2], {KEY: (grown3[0], [47, 52, 60])}, [grown3])
        summary = online.sync_base([KEY])
        self.assertEqual(self.gets(), ['base', 'base/files/retro-recomp-base-3-4.zip'], 'line 3 is not even asked for')
        self.assertEqual((summary['version'], summary['update']['source']), (4, 'delta'))
        self.assertEqual(kx.local_base()['format'], 2)
        self.assertEqual(len(self.rows()), 3)

    def test_a_base_in_line_2_moves_to_line_3_only_when_its_line_leads_nowhere(self):
        first2, first3 = self.two_lines(3)
        self.install(3, {KEY: (first2[0], [47, 52])}, [first2])
        grown2 = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)), part(60, 'thorough', (0x200,)))
        grown3 = (hashlib.sha256(kx.canonical_bytes(kx.entry_to_v3(grown2[1]))).hexdigest(), kx.entry_to_v3(grown2[1]))
        # Line 2 of version 5 has no difference from 3 and no newer complete base; line 3 has a complete one.
        self.publish_lines(5, {KEY: (grown2[0], [47, 52, 60])}, [grown2], {KEY: (grown3[0], [47, 52, 60])}, [grown3],
                           full2=False)
        self.server.base['manifest']['deltas'] = {}
        summary = online.sync_base([KEY])
        self.assertEqual(self.gets(), ['base', 'base3', 'dl/retro-recomp-base3-5.zip'])
        self.assertEqual((summary['version'], summary['update']['source'], summary['update']['error']), (5, 'full', None))
        self.assertEqual(kx.local_base()['format'], 3)
        self.assertEqual(len(self.rows()), 3)
        # And it stays: the old line's entries are gone from the store.
        names = {path.stem for path in (self.store / 'entries').iterdir()}
        self.assertEqual(names, {grown3[0]})

    def test_a_service_without_line_3_is_never_asked_for_it(self):
        old = entry(part(47, 'extended', (0x100,)))
        self.publish(5, {KEY: (old[0], [47])}, entries=[old])
        self.assertNotIn('lines', self.server.base['manifest'])
        summary = online.sync_base([KEY])
        self.assertEqual(self.gets(), ['base', 'dl/retro-recomp-base-5.zip'])
        self.assertEqual((summary['version'], kx.local_base()['format']), (5, 2))

    def test_line_3_that_does_not_answer_leaves_line_2(self):
        first2, first3 = self.two_lines(5)
        self.server.base3['manifest'] = None            # advertised, but 404
        summary = online.sync_base([KEY])
        self.assertEqual(self.gets(), ['base', 'base3', 'dl/retro-recomp-base-5.zip'])
        self.assertEqual((summary['version'], summary['update']['error'], kx.local_base()['format']), (5, None, 2))
        self.assertEqual(len(self.rows()), 2)

    def test_a_line_3_manifest_in_another_format_leaves_line_2(self):
        self.two_lines(5)
        self.server.base3['fail'] = 'format'
        summary = online.sync_base([KEY])
        self.assertEqual((summary['version'], summary['update']['error'], kx.local_base()['format']), (5, None, 2))

    def test_an_archive_of_the_wrong_line_is_refused_and_changes_nothing(self):
        first2, first3 = self.two_lines(5)
        # The service names a format 2 file in its line 3 manifest.
        self.server.base['downloads']['retro-recomp-base3-5.zip'] = base_archive(5, {KEY: (first2[0], [47, 52])},
                                                                                   {first2[0]: first2[1]})
        blob = self.server.base['downloads']['retro-recomp-base3-5.zip']
        full = self.server.base3['manifest']['full']
        full.update(sha256=hashlib.sha256(blob).hexdigest(), bytes=len(blob))
        summary = online.sync_base([KEY])
        self.assertEqual(summary['update']['error'], 'verify')
        self.assertIsNone(kx.local_base())
        self.assertEqual(self.rows(), None)

    def test_the_cursor_revocations_and_quarantine_come_from_line_2s_manifest(self):
        self.two_lines(5)
        self.server.base['manifest'].update(revoked=[52], quarantined=[[47, KEY]], cursor=33)
        online.sync_base([KEY])
        site = json.loads((self.store / 'site.json').read_text(encoding='utf-8'))
        self.assertEqual((site['revoked'], site['quarantined'], site['cursor']), ([52], [[47, KEY]], 33))
        self.assertEqual(self.rows(), None, 'the only two sources are barred')

    def test_the_qualified_bank_keeps_its_shape(self):
        value = entry(part(47, 'standard', (0x100,)), qualified=[qualified((0x100, 0x140))])
        value3 = (hashlib.sha256(kx.canonical_bytes(kx.entry_to_v3(value[1]))).hexdigest(), kx.entry_to_v3(value[1]))
        self.publish_lines(2, {KEY: (value[0], [47])}, [value], {KEY: (value3[0], [47])}, [value3])
        summary = online.sync_base([KEY])
        self.assertEqual(summary['qualified'], 1)
        bank = knowledge.read(kx.qualified_bank_path())
        self.assertEqual(bank['schema'], 1, 'the bank is still schema 1')
        self.assertEqual(bank['consoles']['sms'][IDENTITY]['rom_entries'], [[0x100, 0, 0, 0, 1], [0x140, 0, 0, 0, 1]])


class UploadVersionTests(LineHarness):
    def test_the_version_follows_what_the_service_says_it_reads(self):
        self.assertEqual(online.upload_version(), 2, 'a service that lists nothing reads 2')
        now = time.time()
        for step, (listed, expected) in enumerate((([1, 2, 3], 3), ([1, 2], 2), (None, 2), ('3', 2), ([True, 2], 2), ([3], 3))):
            self.server.knowledge_versions = listed
            self.assertEqual(online.upload_version(now=now + 7200 * (step + 1)), expected, listed)

    def test_it_is_asked_once_an_hour_and_a_failure_means_2(self):
        self.server.knowledge_versions = [1, 2, 3]
        now = time.time()
        self.assertEqual(online.upload_version(now), 3)
        asked = len([hit for hit in self.server.hits if hit[1].endswith('/status')])
        self.server.knowledge_versions = [1, 2]
        self.assertEqual(online.upload_version(now + 600), 3, 'remembered')
        self.assertEqual(len([hit for hit in self.server.hits if hit[1].endswith('/status')]), asked)
        self.assertEqual(online.upload_version(now + 7200), 2)
        with patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': 'http://127.0.0.1:1'}):
            self.assertEqual(online.upload_version(now + 20000), 2)

    def test_an_upload_is_a_version_3_file_when_the_service_reads_it(self):
        self.sign_in()
        gathered = collected('md')
        gathered['levels'] = {}
        for listed, expected in ((None, 2), ([1, 2, 3], 3)):
            self.server.knowledge_versions = listed
            self.server.calls.clear()
            online._UPLOAD_VERSION.update(asked=0.0)
            with patch('retrorecomp.knowledge_exchange.mark_shared'):
                online._send_one(gathered, online.account())
            body = [call for call in self.server.calls if call[1].endswith('/contributions')][0][3]
            document = json.loads(gzip.decompress(body))
            self.assertEqual((document['version'], document['knowledge']['schema']), (expected, 3 if expected == 3 else 1))


if __name__ == '__main__':
    unittest.main()
