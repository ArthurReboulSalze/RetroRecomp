"""The shared base around a batch: updates, revocation, rejection, outcomes.

A local fake service stands in for the site (tests/test_online.py, plus the
base routes): the manifest, the difference files and a complete base at a
direct address. The converter keeps one local base (tests/test_base_store.py
covers the store itself); what these tests follow is what a batch gets from it:
parts join the imported banks like fetched paths and are withdrawn when the
service revokes their source or the player's conversion rejects them.
"""
import hashlib
import io
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from retrorecomp import knowledge, knowledge_exchange, online
from tests.test_online import SHA, FakeService, collected
from tests.test_shared_sync import ENGINE, calls_to, sms_record

IDENTITY = 'ab' * 32
KEY = f'sms:{IDENTITY}'
OTHER_KEY = 'sms:' + 'cd' * 32
OTHER_ENGINE = 'd' * 40


class BaseService(FakeService):
    """FakeService plus the base routes. `server.base` holds `manifest` (None
    answers 404 no_base), `files` (the difference files by name), `downloads`
    (the complete bases by name, served at /dl/ or, through a redirect, at
    /redirect/), `entries` ({sha: value}) and `versions`; `server.hits` lists
    every GET."""

    def do_GET(self):
        path = self.path.split('?')[0]
        self.server.hits.append(('GET', path))
        base = self.server.base
        if path.endswith('/api/v1/base3'):
            if base['manifest'] is None:
                self.answer(404, {'error': 'no_base'})
            elif base.get('fail'):
                self.answer(500, {'error': 'server'})
            else:
                self.answer(200, base['manifest'])
        elif '/api/v1/base3/files/' in path:
            self.file(base['files'].get(path.rsplit('/', 1)[1]))
        elif path.startswith('/dl/'):
            self.file(base['downloads'].get(path.rsplit('/', 1)[1]))
        elif path.startswith('/redirect/'):
            self.send_response(302)
            self.send_header('Location', base.get('redirect_to') or '/dl/' + path.rsplit('/', 1)[1])
            self.send_header('Content-Length', '0')
            self.end_headers()
        elif path.endswith('/api/v1/status'):
            self.answer(200, {'service': 'retro-recomp', 'api': 1, 'accepting': True, 'min_converter': '1.5.3'})
        else:
            super().do_GET()

    def file(self, data):
        if data is None:
            self.answer(404, {'error': 'not_found'})
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path.endswith('/contributions') and self.server.mode == 'outdated':
            self.body()
            minimum = getattr(self.server, 'minimum', None)
            self.answer(426, {'error': 'converter_outdated', **({'detail': minimum} if minimum else {})})
        else:
            super().do_POST()


def part(source, level='standard', addresses=(), rows=None, record=True):
    return {'source': source, 'level': level, 'record': sms_record(*addresses) if record and addresses else None,
            'observations': rows or []}


def qualified(addresses=(), engine=ENGINE, level='standard', by='players', record=None):
    """A qualified element of a game entry: Master System paths built with `engine`."""
    return {'engine': engine, 'level': level, 'by': by,
            'record': record if record is not None else {**sms_record(*addresses), 'engine': engine}}


def grouped_entry(*parts, identity=IDENTITY, system='sms', qualified=()):
    """A game's parts as the builder groups them before they become an entry (schema 1 records, `engine`)."""
    return {'format': 2, 'system': system, 'identity': identity,
            'qualified': sorted(qualified, key=lambda item: str(item.get('engine')) if isinstance(item, dict) else ''),
            'parts': sorted(parts, key=lambda item: item['source'])}


def entry(*parts, identity=IDENTITY, system='sms', qualified=()):
    """(sha, value) of a game entry built the way the service names it: format 3, the only one of the base."""
    value = knowledge_exchange.entry_to_v3(grouped_entry(*parts, identity=identity, system=system, qualified=qualified))
    return hashlib.sha256(knowledge_exchange.canonical_bytes(value)).hexdigest(), value


def base_archive(version, games, entries, wanted=None, built='2026-10-27T03:00:00+00:00',
                 compression=zipfile.ZIP_DEFLATED, format=3):
    """The bytes of a base archive: manifest.json, index.json (the complete
    index of `version`: `games` is {key: (entry sha, [sources])}) and the entries
    of `wanted` (default: all those the index names) found in `entries`."""
    index = {'format': format, 'version': version, 'built_utc': built,
             'games': {key: {'entry': value[0], 'sources': list(value[1])} for key, value in games.items()}}
    raw = knowledge_exchange.canonical_bytes(index)
    manifest = {'format': format, 'version': version, 'built_utc': built, 'games': len(games),
                'index_sha256': hashlib.sha256(raw).hexdigest()}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression) as archive:
        def put(name, data):
            # A fixed date: two calls a second apart must give the same bytes.
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 27, 3, 0, 0))
            info.compress_type = compression
            archive.writestr(info, data)
        put('manifest.json', json.dumps(manifest))
        put('index.json', raw)
        for sha in sorted({value[0] for value in games.values()} if wanted is None else wanted):
            if sha in entries:
                put(f'entries/{sha}.json', knowledge_exchange.canonical_bytes(entries[sha]))
    return buffer.getvalue()


def ng_engine():
    from retrorecomp.neogeo_build import GEOLITH_REV, LITHOGEN_REV
    return f'{GEOLITH_REV}:{LITHOGEN_REV}'


def calls_after(server, kind):
    return [hit for hit in server.hits if hit[0] == kind]


class BaseHarness(unittest.TestCase):
    """A temporary application folder (the installer's copy goes beside it),
    a temporary data folder and the fake service. No tests of its own."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.data = self.root / 'datas'
        self.bank = self.data / 'knowledge/imported.json.gz'
        self.folder = self.bank.parent
        self.store = self.folder / 'base'
        self.installer = self.root / 'app' / 'Retro-Recomp-base.zip'
        self.engines = {'sms': ENGINE, 'gg': ENGINE, 'ng': ng_engine()}
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), BaseService)
        self.server.calls, self.server.mode, self.server.claims = [], 'ok', 'ok'
        self.server.store, self.server.encodings, self.server.hits = {}, [], []
        self.server.base = {'manifest': None, 'files': {}, 'downloads': {}, 'entries': {}, 'versions': {}}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.stop_server)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}'
        for item in (patch.dict(os.environ, {'RETRO_RECOMP_SERVICE': self.url}),
                     patch('retrorecomp.paths.data_directory', return_value=self.data),
                     patch('retrorecomp.knowledge.imported_path', return_value=self.bank),
                     patch('retrorecomp.knowledge_exchange.imported_path', return_value=self.bank),
                     patch('retrorecomp.knowledge_exchange.installer_base_path', return_value=self.installer),
                     patch('retrorecomp.knowledge_exchange._current_engines',
                           side_effect=lambda: dict(self.engines))):
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(knowledge._imported_bank.cache_clear)
        self.addCleanup(knowledge._observation_bank.cache_clear)
        self.addCleanup(knowledge_exchange._installer_head.cache_clear)

    def stop_server(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

    def sign_in(self):
        online.request_code('p@example.test', 'en')
        online.sign_in('p@example.test', '123456', 'Retro-Recomp test')

    def publish(self, version, games, *, revoked=(), cursor=0, format=3, entries=(), quarantined=None, full=True):
        """Serve base `version`: `games` is {key: (entry sha, [sources])}; the
        `entries` ((sha, value) pairs) join those the service holds. Serves a
        difference file from every earlier version, and, with `full`, a complete
        base (True: this version; a number: that earlier version's)."""
        base = self.server.base
        base['entries'].update(dict(entries))
        base['versions'][version] = dict(games)
        manifest_full = None
        if full:
            number = version if full is True else full
            name = f'retro-recomp-base3-{number}.zip'
            blob = base_archive(number, base['versions'][number], base['entries'])
            base['downloads'][name] = blob
            route = 'redirect' if base.get('redirect') else 'dl'
            manifest_full = {'version': number, 'url': f'{self.url}/{route}/{name}',
                             'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}
        deltas = {}
        for earlier, before in base['versions'].items():
            if earlier >= version:
                continue
            name = f'retro-recomp-base3-{earlier}-{version}.zip'
            blob = base_archive(version, games, base['entries'],
                                {value[0] for value in games.values()} - {value[0] for value in before.values()})
            base['files'][name] = blob
            deltas[str(earlier)] = {'file': name, 'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}
        base['manifest'] = {'format': format, 'formats': [format], 'version': version,
                            'built_utc': '2026-10-27T03:00:00+00:00', 'published_utc': '2026-10-27T03:01:00+00:00',
                            'cursor': cursor, 'min_converter': '1.5.4', 'games': len(games), 'revoked': list(revoked),
                            'full': manifest_full, 'deltas': deltas}
        if quarantined is not None:
            base['manifest']['quarantined'] = quarantined

    def install(self, version, games, entries):
        """Lay the installer's copy beside the program."""
        self.installer.parent.mkdir(parents=True, exist_ok=True)
        self.installer.write_bytes(base_archive(version, games, dict(entries)))

    def later(self, steps=1):
        return time.time() + steps * (online.BASE_UPDATE_EVERY + 1)

    def state(self, name):
        return json.loads((self.folder / name).read_text(encoding='utf-8'))

    def gets(self):
        """The GET requests made so far, as 'base', 'base3/files/<file>', 'dl/<file>'."""
        return [hit[1].split('/api/v1/', 1)[1] if '/api/v1/' in hit[1] else hit[1].lstrip('/')
                for hit in self.server.hits if hit[0] == 'GET']


class PublishedBaseTests(BaseHarness):
    # --- Updates before a batch ------------------------------------------------

    def test_the_batch_roms_come_from_the_base_with_no_account(self):
        first = entry(part(47, 'extended', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)))
        elsewhere = entry(part(9, 'standard', (0x200,)), identity='cd' * 32)
        self.publish(7, {KEY: (first[0], [47, 52]), OTHER_KEY: (elsewhere[0], [9])}, cursor=90,
                     entries=[first, elsewhere])
        self.server.calls.clear()
        prepared = online.prepare_batch([KEY])
        self.assertEqual({name: prepared['base'][name] for name in ('version', 'games', 'discarded', 'note', 'error',
                                                                  'origin', 'offline')},
                         {'version': 7, 'games': 1, 'discarded': 0, 'note': None, 'error': None, 'origin': 'download',
                          'offline': False})
        update = prepared['base']['update']
        self.assertEqual((update['previous'], update['version'], update['source'], update['error']), (None, 7, 'full', None))
        self.assertIsNone(prepared['summary'], 'no account: no per-account fetch')
        self.assertEqual(calls_to(self.server, '/knowledge/fetch'), [])
        self.assertEqual(prepared['paths'], {KEY: {'level': 'extended', 'records': 2}})
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'],
                         [[0x100, 0, 0, 0, 1], [0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [[1, 0x300, 0, 2, 0x10]])
        self.assertEqual(knowledge.imported_record('sms', 'cd' * 32), {}, 'only the batch\'s games are applied')
        # The manifest and the complete base, publicly; no other request.
        self.assertEqual(self.gets(), ['base3', 'dl/retro-recomp-base3-7.zip'])
        self.assertEqual(calls_after(self.server, 'POST'), [])
        state = json.loads((self.store / 'state.json').read_text(encoding='utf-8'))
        self.assertEqual((state['version'], state['origin'], state['cursor'], state['service']), (7, 'download', 90, self.url))
        self.assertEqual(state['index_sha256'], hashlib.sha256((self.store / 'index.json').read_bytes()).hexdigest())
        self.assertEqual(sorted(path.name for path in (self.store / 'entries').iterdir()),
                         sorted(f'{sha}.json' for sha in (first[0], elsewhere[0])))
        site = json.loads((self.store / 'site.json').read_text(encoding='utf-8'))
        self.assertEqual((site['latest'], site['revoked'], site['cursor']), (7, [], 90))
        use = self.state('base-use.json')
        self.assertEqual({name: use[KEY][name] for name in ('entry', 'sources', 'level', 'records', 'version', 'rejected',
                                                          'engine_id', 'qualified')},
                         {'entry': first[0], 'sources': [47, 52], 'level': 'extended', 'records': 2, 'version': 7,
                          'rejected': [], 'engine_id': ENGINE, 'qualified': None})
        self.assertNotIn(OTHER_KEY, use)

    def test_the_base_is_updated_at_most_once_a_day_and_by_the_difference_alone(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(3, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        self.assertEqual(self.gets(), ['base3', 'dl/retro-recomp-base3-3.zip'])
        self.server.hits.clear()
        # Within the day: no request at all.
        online.sync_base([KEY], now=time.time() + online.BASE_UPDATE_EVERY - 60)
        self.assertEqual(self.server.hits, [])
        # The next day: the manifest only (same version), no download.
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual(self.gets(), ['base3'])
        self.assertEqual((summary['update']['source'], summary['update']['error'], summary['version']), (None, None, 3))
        # A new version downloads its difference, not the complete base.
        grown = entry(part(1, 'standard', (0x100,)), part(2, 'thorough', (0x200,)))
        self.publish(4, {KEY: (grown[0], [1, 2])}, entries=[grown])
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later(2))
        self.assertEqual(self.gets(), ['base3', 'base3/files/retro-recomp-base3-3-4.zip'])
        self.assertEqual((summary['version'], summary['games'], summary['update']['source']), (4, 1, 'delta'))
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'thorough', 'records': 2}})
        self.assertEqual(json.loads((self.store / 'state.json').read_text(encoding='utf-8'))['version'], 4)
        # Without the option nothing is asked, whatever the day.
        self.publish(5, {KEY: (grown[0], [1, 2])}, entries=[grown])
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later(5), enabled=False)
        self.assertEqual((self.server.hits, summary['update'], summary['version']), ([], None, 4))

    def test_an_archive_that_is_not_what_the_manifest_says_leaves_the_base_alone(self):
        good = entry(part(1, 'standard', (0x100,)))
        forged = json.loads(json.dumps(good[1]))
        forged['parts'][0]['record'] = sms_record(0x999)
        # An entry whose text is not the one its name says: the whole archive is refused.
        self.publish(1, {KEY: (good[0], [1])}, entries=[(good[0], forged)])
        summary = online.sync_base([KEY])
        self.assertEqual((summary['update']['error'], summary['version'], summary['games']), ('verify', None, 0))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertFalse((self.store / 'state.json').exists())
        self.assertFalse(list((self.store / 'entries').glob('*')) if (self.store / 'entries').exists() else [])
        # A failed update is tried again at the next batch, not the next day.
        self.publish(1, {KEY: (good[0], [1])}, entries=[good])
        self.server.hits.clear()
        self.assertEqual(online.sync_base([KEY], now=time.time() + 60)['games'], 1)
        self.assertEqual(self.gets(), ['base3', 'dl/retro-recomp-base3-1.zip'])

    def test_an_entry_is_checked_against_the_hash_that_named_it_when_it_is_used(self):
        stranger = entry(part(1, 'standard', (0x100,)), identity='11' * 32)   # named by its own hash
        flawed = entry(part(1, 'standard', (0x100,)), part(2, 'thorough', rows=[[1, 0x400, 0, 2, 0x20]]),
                       part(3, 'standard', (0x300,)))
        # Part 1 is not a record at all, part 3 is not a part; part 2 has a good row among bad ones.
        flawed[1]['parts'][0]['record'] = {'engine': 'not hex', 'rom_bytes': 8192}
        flawed[1]['parts'][1]['observations'].append([99, 1, 0, 2, 0])
        flawed[1]['parts'][2]['level'] = 'galactic'
        flawed = (hashlib.sha256(knowledge_exchange.canonical_bytes(flawed[1])).hexdigest(), flawed[1])
        # An entry of another ROM, under the right hash: refused when this ROM asks for it.
        self.publish(1, {KEY: (stranger[0], [1])}, entries=[stranger])
        summary = online.sync_base([KEY])
        self.assertEqual((summary['version'], summary['games'], summary['error']), (1, 0, None))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertFalse((self.folder / 'base-use.json').exists(), 'and asked again next time')
        # Invalid parts are skipped one by one.
        self.publish(2, {KEY: (flawed[0], [1, 2, 3])}, entries=[flawed])
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['games'], summary['error']), (1, None))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [[1, 0x400, 0, 2, 0x20]])
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'thorough', 'records': 0}})

    def test_a_long_batch_is_applied_in_groups(self):
        games, entries = {}, []
        for number in range(30):
            identity = '%064x' % number
            built = entry(part(number + 1, 'standard', (0x100,)), identity=identity)
            games[f'sms:{identity}'] = (built[0], [number + 1])
            entries.append(built)
        self.publish(1, games, entries=entries)
        with patch.object(online, 'BASE_IMPORT_BATCH', 8):
            summary = online.sync_base(list(games))
        self.assertEqual((summary['games'], summary['error']), (30, None))
        self.assertEqual(sum(bool(knowledge.imported_record('sms', '%064x' % number)) for number in range(30)), 30)

    # --- Revocation, removal, rejection ----------------------------------------

    def test_a_revoked_source_withdraws_its_part_and_the_account_cursor_starts_again(self):
        self.sign_in()
        built = entry(part(47, 'thorough', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)))
        self.publish(1, {KEY: (built[0], [47, 52])}, cursor=40, entries=[built])
        self.server.store = {KEY: [{'id': 30, 'record': sms_record(0x100), 'level': 'thorough'}]}
        prepared = online.prepare_batch([KEY])
        self.assertEqual(prepared['paths'], {KEY: {'level': 'thorough', 'records': 2}})
        cursors = self.state('shared-cursors.json')['roms']
        self.assertEqual(cursors[KEY]['cursor'], 40, 'the base holds what the fetch would serve up to its cursor')
        self.assertEqual([json.loads(call[3])['roms'] for call in calls_to(self.server, '/knowledge/fetch')], [{KEY: 40}])
        # The service revokes upload 47 (and the rows only it brought): the manifest says so.
        self.publish(1, {KEY: (built[0], [47, 52])}, cursor=40, revoked=[47], entries=[built])
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual(self.gets(), ['base3'])
        self.assertEqual((summary['discarded'], summary['games']), (1, 1))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [])
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'quick', 'records': 1}})
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['sources'], use['entry']), ([52], built[0]))
        rejected = json.loads((self.folder / 'imported-rejected.json').read_text(encoding='utf-8'))
        self.assertTrue(rejected[-1]['reason'].startswith('shared base: '))
        cursors = self.state('shared-cursors.json')['roms']
        self.assertEqual(cursors[KEY]['cursor'], 0, 'served again from the start, not skipped by the base cursor')
        self.assertNotIn('level', cursors[KEY])
        # The fetch of the same batch serves the game from the start again.
        self.server.calls.clear()
        self.assertEqual(online.sync_shared([KEY])['records'], 1)
        self.assertEqual([json.loads(call[3])['roms'] for call in calls_to(self.server, '/knowledge/fetch')], [{KEY: 0}])
        self.assertEqual(self.state('shared-cursors.json')['roms'][KEY]['cursor'], 30)

    def test_a_game_that_left_the_base_or_lost_a_source_is_withdrawn(self):
        first = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(1, {KEY: (first[0], [1, 2])}, entries=[first])
        online.sync_base([KEY])
        # The entry is replaced by one that lacks source 2: the game is rebuilt from the new entry.
        second = entry(part(1, 'standard', (0x100,)), part(3, 'extended', (0x300,)))
        self.publish(2, {KEY: (second[0], [1, 3])}, entries=[second])
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['discarded'], summary['games']), (1, 1))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'],
                         [[0x100, 0, 0, 0, 1], [0x300, 0, 0, 0, 1]])
        # The game disappears from the base: nothing of it stays.
        self.publish(3, {OTHER_KEY: (entry(part(9, 'standard', (0x100,)), identity='cd' * 32)[0], [9])},
                     entries=[entry(part(9, 'standard', (0x100,)), identity='cd' * 32)])
        summary = online.sync_base([KEY], now=self.later(2))
        self.assertEqual((summary['discarded'], summary['games']), (1, 0))
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        self.assertEqual(online.shared_paths([KEY]), {})
        # An entry that only grows keeps what is there and adds the new part.
        grown = entry(part(3, 'extended', (0x300,)))
        self.publish(4, {KEY: (grown[0], [3])}, entries=[grown])
        online.sync_base([KEY], now=self.later(3))
        more = entry(part(3, 'extended', (0x300,)), part(4, 'quick', (0x400,)))
        self.publish(5, {KEY: (more[0], [3, 4])}, entries=[more])
        summary = online.sync_base([KEY], now=self.later(4))
        self.assertEqual(summary['discarded'], 0)
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 2)

    def test_a_rejected_entry_is_not_imported_again_until_the_base_changes_for_that_game(self):
        built = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)))
        self.publish(1, {KEY: (built[0], [1, 2])}, entries=[built])
        online.sync_base([KEY])
        # A conversion rejects the shared paths: the window discards and forgets them.
        knowledge.discard_imported('sms', IDENTITY, 'conversion broke')
        online.forget_shared([KEY])
        self.assertEqual(online.shared_paths([KEY]), {})
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['rejected'], use['rejected_sources'], use['sources']), ([built[0]], [1, 2], []))
        self.server.hits.clear()
        for step in (1, 2):
            summary = online.sync_base([KEY], now=self.later(step))
            self.assertEqual((summary['games'], summary['discarded']), (0, 0))
        self.assertEqual(self.gets(), ['base3', 'base3'], 'the manifest only')
        self.assertEqual(knowledge.imported_record('sms', IDENTITY), {})
        # The base names another entry for the game: it comes in.
        newer = entry(part(1, 'standard', (0x100,)), part(2, 'standard', (0x200,)), part(8, 'extended', (0x800,)))
        self.publish(2, {KEY: (newer[0], [1, 2, 8])}, entries=[newer])
        self.assertEqual(online.sync_base([KEY], now=self.later(3))['games'], 1)
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 3)
        self.assertEqual(self.state('base-use.json')[KEY]['rejected'], [built[0]])

    def test_removing_the_imported_banks_restarts_the_import_too(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        for path in self.folder.glob('imported*.json.gz'):
            path.unlink()
        self.assertEqual(online.shared_paths([KEY]), {})
        self.assertEqual(online.sync_base([KEY], now=self.later())['games'], 1)
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 1)

    # --- Formats, failures, accounts ----------------------------------------------

    def test_an_unknown_format_keeps_the_local_base(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        self.publish(2, {KEY: (built[0], [1])}, entries=[built], format=4)
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['note'], summary['format'], summary['version'], summary['error']), ('format', 4, 1, None))
        self.assertEqual(self.gets(), ['base3'])
        self.assertEqual(json.loads((self.store / 'state.json').read_text(encoding='utf-8'))['version'], 1)
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'standard', 'records': 1}})
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 1)

    def test_no_base_yet_and_a_failing_service_never_stop_the_batch(self):
        summary = online.sync_base([KEY])
        self.assertEqual((summary['note'], summary['version'], summary['error'], summary['offline']),
                         ('no_base', None, None, False))
        self.assertEqual(online.prepare_batch([KEY])['paths'], {})
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, entries=[built])
        online.sync_base([KEY])
        self.server.base['fail'] = True
        prepared = online.prepare_batch([KEY], now=self.later())
        self.assertEqual(prepared['base']['error'].reason, 'server')
        self.assertEqual(prepared['base']['version'], 1, 'the base already here still applies')
        self.assertEqual(prepared['paths'], {KEY: {'level': 'standard', 'records': 1}})
        self.stop_server()
        prepared = online.prepare_batch([KEY], now=self.later(2))
        self.assertIsInstance(prepared['base']['error'], online.ServiceConnectionError)
        self.assertTrue(prepared['base']['offline'])
        self.assertEqual(prepared['paths'], {KEY: {'level': 'standard', 'records': 1}})

    def test_an_entry_that_cannot_be_read_is_tried_again_and_keeps_the_cursor_back(self):
        self.sign_in()
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, cursor=60, entries=[built])
        online.update_base()
        (self.store / 'entries' / f'{built[0]}.json').write_text('{"damaged": true}', encoding='utf-8')
        prepared = online.prepare_batch([KEY, OTHER_KEY])
        self.assertEqual(prepared['paths'], {})
        cursors = self.state('shared-cursors.json')['roms']
        self.assertNotIn(KEY, cursors, 'what the base could not give stays for the fetch')
        self.assertEqual(cursors[OTHER_KEY]['cursor'], 60, 'a ROM the base does not list is covered up to its cursor')
        (self.store / 'entries' / f'{built[0]}.json').write_bytes(knowledge_exchange.canonical_bytes(built[1]))
        self.assertEqual(online.sync_base([KEY], now=self.later())['games'], 1)
        self.assertEqual(self.state('shared-cursors.json')['roms'][KEY]['cursor'], 60)

    def test_with_an_account_the_fetch_follows_the_base_and_without_one_it_is_skipped(self):
        built = entry(part(1, 'standard', (0x100,)))
        self.publish(1, {KEY: (built[0], [1])}, cursor=25, entries=[built])
        self.server.store = {KEY: [{'id': 20, 'record': sms_record(0x100)},
                                   {'id': 31, 'record': sms_record(0x900), 'level': 'extended'}]}
        self.sign_in()
        prepared = online.prepare_batch([KEY])
        # The fetch asks from the base's cursor: only what is newer comes.
        self.assertEqual([json.loads(call[3])['roms'] for call in calls_to(self.server, '/knowledge/fetch')], [{KEY: 25}])
        self.assertEqual(prepared['summary']['records'], 1)
        self.assertEqual(prepared['paths'], {KEY: {'level': 'extended', 'records': 2}},
                         'the base\'s paths and the fetch\'s together')
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 2)
        online.forget_shared([KEY])
        self.assertEqual(online.shared_paths([KEY]), {})
        online.sign_out()
        self.server.calls.clear()
        prepared = online.prepare_batch([KEY])
        self.assertEqual((prepared['summary'], prepared['error']), (None, None))
        self.assertEqual(prepared['base']['version'], 1)
        self.assertEqual(calls_to(self.server, '/knowledge/fetch'), [])

    # --- Outcomes: what the base became for a converted game ---------------------------

    def noted(self):
        return json.loads((self.folder.parent / 'account-converted.json').read_text(encoding='utf-8'))

    def test_the_outcome_of_the_base_is_noted_with_the_conversion_and_replaced_by_a_later_one(self):
        built = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)))
        self.publish(3, {KEY: (built[0], [47, 52])}, entries=[built])
        online.sync_base([KEY])
        self.assertFalse(online.note_conversion('sms', IDENTITY), 'no account: nothing is noted')
        self.assertFalse((self.folder.parent / 'account-converted.json').exists())
        self.assertEqual(online.converted_outcomes(), {})
        self.sign_in()
        self.assertTrue(online.note_conversion('sms', OTHER_KEY[4:]), 'a game the base gave nothing')
        self.assertTrue(online.note_conversion('sms', IDENTITY))
        used = {'base': 3, 'entry': built[0], 'sources': [47, 52], 'outcome': 'used'}
        self.assertEqual(online.converted_outcomes(), {KEY: used})
        self.assertEqual(online.noted_conversions(), [OTHER_KEY, KEY])
        self.assertEqual(self.noted()['outcomes'], {KEY: used})
        # The batch set the paths aside and succeeded without them.
        self.assertTrue(online.note_conversion('sms', IDENTITY, rejected=True))
        rejected = {**used, 'outcome': 'rejected'}
        self.assertEqual(online.converted_outcomes(), {KEY: rejected})
        self.assertEqual(online.noted_conversions(), [OTHER_KEY, KEY], 'the game is noted once')
        knowledge.discard_imported('sms', IDENTITY, 'conversion broke')
        online.forget_shared([KEY])
        # A later conversion without any base part leaves what is not sent yet.
        online.note_conversion('sms', IDENTITY)
        self.assertEqual(online.converted_outcomes(), {KEY: rejected})
        # The base names a newer entry; this conversion used it: it replaces the outcome.
        newer = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)), part(60, 'thorough', (0x600,)))
        self.publish(4, {KEY: (newer[0], [47, 52, 60])}, entries=[newer])
        online.sync_base([KEY], now=self.later())
        online.note_conversion('sms', IDENTITY)
        self.assertEqual(online.converted_outcomes(),
                         {KEY: {'base': 4, 'entry': newer[0], 'sources': [47, 52, 60], 'outcome': 'used'}})

    def test_a_game_the_base_only_qualified_has_no_outcome_to_send(self):
        built = entry(part(47, 'extended', (0x100,)), qualified=[qualified((0x100,))])
        self.publish(3, {KEY: (built[0], [47])}, entries=[built])
        self.sign_in()
        online.sync_base([KEY])
        only = entry(qualified=[qualified((0x300,))], identity='cd' * 32)
        self.publish(4, {KEY: (built[0], [47]), OTHER_KEY: (only[0], [])}, entries=[only])
        online.sync_base([KEY, OTHER_KEY], now=self.later())
        online.note_conversion('sms', 'cd' * 32)
        self.assertEqual(online.converted_outcomes(), {}, 'nothing pending was imported for it')
        online.note_conversion('sms', IDENTITY)
        self.assertEqual(online.converted_outcomes()[KEY]['sources'], [47])

    def test_the_window_tells_the_note_when_the_conversion_set_the_base_paths_aside(self):
        from retrorecomp import gui
        owner = gui.Application.__new__(gui.Application)
        game = type('Game', (), {'system': 'sms', 'identity': IDENTITY})()
        with patch.object(online, 'note_conversion') as note:
            owner.note_conversion({'status': 'success', 'imported_hints_rejected': True}, game)
            owner.note_conversion({'status': 'success'}, game)
            owner.note_conversion({'status': 'error', 'imported_hints_rejected': True}, game)
        self.assertEqual([(call.args, call.kwargs) for call in note.call_args_list],
                         [(('sms', IDENTITY), {'rejected': True}), (('sms', IDENTITY), {'rejected': False})])

    def test_claims_carry_the_outcome_only_for_the_games_that_have_one(self):
        built = entry(part(47, 'extended', (0x100,)), part(52, 'quick', (0x180,)))
        self.publish(3, {KEY: (built[0], [47, 52])}, entries=[built])
        self.sign_in()
        online.sync_base([KEY])
        known = {'engine': 'd' * 40, 'rom_bytes': 8192, 'level': 'extended', 'title': 'Known Game'}
        other = OTHER_KEY[4:]
        online.note_conversion('sms', IDENTITY, rejected=True)
        online.note_conversion('sms', other)
        found = {**collected(), 'converted': {'sms': {IDENTITY: known, other: known}}}
        pending = online.pending(found)
        self.assertEqual(sorted(pending['converted_keys']), sorted([KEY, OTHER_KEY]))
        result = online.send(pending)
        self.assertEqual(result['claims']['games'], 3)
        games = {game['identity']: game for game in json.loads(calls_to(self.server, '/claims')[-1][3])['games']}
        self.assertEqual(games[IDENTITY]['shared'], {'base': 3, 'entry': built[0], 'sources': [47, 52],
                                                     'outcome': 'rejected'})
        self.assertTrue(games[IDENTITY]['converted'])
        self.assertNotIn('shared', games[other], 'converted, but the base gave it nothing')
        self.assertNotIn('shared', games[SHA], 'raw observations only')
        self.assertEqual(online.noted_conversions(), [])
        self.assertEqual(online.converted_outcomes(), {})
        self.assertNotIn('outcomes', self.noted())

    def test_a_claim_that_could_not_be_delivered_keeps_its_outcome_for_the_retry(self):
        built = entry(part(47, 'extended', (0x100,)))
        self.publish(3, {KEY: (built[0], [47])}, entries=[built])
        self.sign_in()
        online.sync_base([KEY])
        online.note_conversion('sms', IDENTITY)
        self.server.claims = 'busy'
        known = {'engine': 'd' * 40, 'rom_bytes': 8192, 'level': 'standard', 'title': 'Known Game'}
        online.send(online.pending({**collected(), 'converted': {'sms': {IDENTITY: known}}}))
        self.server.claims = 'ok'
        self.server.calls.clear()
        online.send(online.pending(collected()))
        games = {game['identity']: game for game in json.loads(calls_to(self.server, '/claims')[0][3])['games']}
        self.assertEqual(games[IDENTITY]['shared']['outcome'], 'used')

    def test_note_files_written_before_the_outcomes_still_load(self):
        self.sign_in()
        current = online.account()
        path = self.folder.parent / 'account-converted.json'
        path.write_text(json.dumps({'service': current['service'], 'email': current.get('email'),
                                    'games': [KEY, OTHER_KEY]}, indent=1), encoding='utf-8')
        self.assertEqual(online.noted_conversions(), [KEY, OTHER_KEY])
        self.assertEqual(online.converted_outcomes(), {})
        # Malformed outcomes are dropped one by one; a good one stays.
        good = {'base': 2, 'entry': 'ef' * 32, 'sources': [3, 1], 'outcome': 'used'}
        path.write_text(json.dumps({'service': current['service'], 'email': current.get('email'),
                                    'games': [KEY, OTHER_KEY],
                                    'outcomes': {KEY: good, OTHER_KEY: {**good, 'outcome': 'maybe'},
                                                 f'sms:{"12" * 32}': good, 'bogus': good}}), encoding='utf-8')
        self.assertEqual(online.converted_outcomes(), {KEY: {**good, 'sources': [1, 3]}})
        path.write_text(json.dumps({'service': current['service'], 'email': current.get('email'),
                                    'games': [KEY], 'outcomes': 'nonsense'}), encoding='utf-8')
        self.assertEqual((online.noted_conversions(), online.converted_outcomes()), ([KEY], {}))
        self.assertTrue(online.note_conversion('sms', OTHER_KEY[4:]))
        self.assertEqual(online.noted_conversions(), [KEY, OTHER_KEY])

    # --- Quarantine: a (source, game) pair set aside by the service -----------------

    def test_a_quarantined_pair_is_not_imported(self):
        built = entry(part(47, 'extended', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)))
        elsewhere = entry(part(47, 'standard', (0x200,)), identity='cd' * 32)
        games = {KEY: (built[0], [47, 52]), OTHER_KEY: (elsewhere[0], [47])}
        # Quarantined before anything was imported: the part never comes in.
        self.publish(1, games, entries=[built, elsewhere], quarantined=[[47, KEY]])
        self.assertEqual(online.sync_base([KEY, OTHER_KEY])['games'], 2)
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [])
        self.assertEqual(len(knowledge.imported_record('sms', 'cd' * 32)['rom_entries']), 1,
                         'the same source stays for its other games')
        self.assertEqual(self.state('base-use.json')[KEY]['sources'], [52])
        self.assertEqual(json.loads((self.store / 'site.json').read_text(encoding='utf-8'))['quarantined'], [[47, KEY]])

    def test_quarantine_after_the_import_follows_the_revocation_path_and_can_be_lifted(self):
        self.sign_in()
        built = entry(part(47, 'extended', (0x100,), [[1, 0x300, 0, 2, 0x10]]), part(52, 'quick', (0x180,)))
        self.publish(1, {KEY: (built[0], [47, 52])}, cursor=40, entries=[built])
        self.server.store = {KEY: [{'id': 30, 'record': sms_record(0x100), 'level': 'thorough'}]}
        online.prepare_batch([KEY])
        self.assertEqual(self.state('shared-cursors.json')['roms'][KEY]['cursor'], 40)
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 2)
        # Only the valid pair counts; every other shape is ignored without a word.
        odd = [[47, KEY], [True, KEY], [47], [47, 'nonsense'], ['47', KEY], [47, KEY, 1], 'x', None, {'a': 1},
               [48, f'xbox:{IDENTITY}']]
        self.publish(1, {KEY: (built[0], [47, 52])}, cursor=40, entries=[built], quarantined=odd)
        self.server.hits.clear()
        summary = online.sync_base([KEY], now=self.later())
        self.assertEqual((summary['discarded'], summary['games'], summary['error']), (1, 1, None))
        self.assertEqual(json.loads((self.store / 'site.json').read_text(encoding='utf-8'))['quarantined'], [[47, KEY]])
        self.assertEqual(knowledge.imported_record('sms', IDENTITY)['rom_entries'], [[0x180, 0, 0, 0, 1]])
        self.assertEqual(knowledge.imported_observations('sms', IDENTITY), [])
        use = self.state('base-use.json')[KEY]
        self.assertEqual((use['sources'], use['entry']), ([52], built[0]))
        reason = json.loads((self.folder / 'imported-rejected.json').read_text(encoding='utf-8'))[-1]['reason']
        self.assertTrue(reason.startswith('shared base: '), reason)
        cursors = self.state('shared-cursors.json')['roms'][KEY]
        self.assertEqual(cursors['cursor'], 0, 'the account sync serves the game again, not skipped by the base cursor')
        self.assertNotIn('level', cursors)
        self.assertEqual(online.shared_paths([KEY]), {KEY: {'level': 'quick', 'records': 1}})
        # Nothing more happens while the pair stays quarantined.
        self.server.hits.clear()
        self.assertEqual(online.sync_base([KEY], now=self.later(2))['discarded'], 0)
        self.assertEqual(self.gets(), ['base3'])
        # The maintainer lifts it: the part comes back.
        self.publish(1, {KEY: (built[0], [47, 52])}, cursor=40, entries=[built], quarantined=[])
        summary = online.sync_base([KEY], now=self.later(3))
        self.assertEqual((summary['discarded'], summary['games']), (0, 1))
        self.assertEqual(len(knowledge.imported_record('sms', IDENTITY)['rom_entries']), 2)
        self.assertEqual(self.state('base-use.json')[KEY]['sources'], [47, 52])

    def test_a_manifest_without_quarantine_and_an_older_site_file_keep_working(self):
        built = entry(part(47, 'extended', (0x100,)))
        self.publish(1, {KEY: (built[0], [47])}, entries=[built])
        online.sync_base([KEY])
        site = json.loads((self.store / 'site.json').read_text(encoding='utf-8'))
        self.assertEqual(site['quarantined'], [])
        del site['quarantined']
        (self.store / 'site.json').write_text(json.dumps(site), encoding='utf-8')
        summary = online.sync_base([KEY], now=time.time() + 60)
        self.assertEqual((summary['version'], summary['discarded'], summary['error']), (1, 0, None))
        self.publish(1, {KEY: (built[0], [47])}, entries=[built], quarantined='nonsense')
        self.assertEqual(online.sync_base([KEY], now=self.later())['discarded'], 0)
        self.assertEqual(json.loads((self.store / 'site.json').read_text(encoding='utf-8'))['quarantined'], [])

    # --- 426 converter_outdated ---------------------------------------------------

    def test_an_outdated_converter_is_told_to_update_and_its_games_stay_pending(self):
        self.sign_in()
        self.server.mode = 'outdated'
        self.server.minimum = '1.5.3'
        found = collected()
        with self.assertRaises(online.ServiceError) as caught:
            online.send(online.pending(found))
        self.assertEqual((caught.exception.status, caught.exception.reason, caught.exception.detail),
                         (426, 'converter_outdated', '1.5.3'))
        self.assertEqual(online.pending(found)['games'], 1, 'nothing was marked as shared')
        # A service that gives no detail: the minimum comes from GET status.
        self.server.minimum = None
        with self.assertRaises(online.ServiceError) as caught:
            online.send(online.pending(found))
        self.assertEqual(caught.exception.detail, '1.5.3')
        self.assertEqual(online.pending(found)['games'], 1)
        self.assertEqual(online.minimum_converter(online.ServiceError(426, 'converter_outdated', 'not a version'), ask=False), '')
        self.assertEqual(online.minimum_converter(online.ServiceError(426, 'converter_outdated', '1.6.0'), ask=False), '1.6.0')
        # The window turns it into a real message, in every language.
        from retrorecomp import gui
        from retrorecomp.i18n import tr
        from retrorecomp.languages import LANGUAGES
        owner = gui.Application.__new__(gui.Application)
        error = online.ServiceError(426, 'converter_outdated', '1.5.3')
        plain = online.ServiceError(426, 'converter_outdated')
        for code in LANGUAGES:
            owner.language = code
            message = owner.service_problem(error)
            self.assertIn('1.5.3', message, code)
            self.assertEqual(message, tr('online_outdated_min', code, minimum='1.5.3'))
            self.assertNotIn('converter_outdated', message)
            self.assertNotIn('{', owner.service_problem(plain))
            if code != 'en':
                self.assertNotEqual(message, tr('online_outdated_min', 'en', minimum='1.5.3'), code)
                self.assertNotEqual(owner.service_problem(plain), tr('online_outdated', 'en'), code)

    # --- The window's log lines ---------------------------------------------------

    def test_the_window_says_what_the_base_gave_in_every_language(self):
        from queue import Queue
        from retrorecomp import gui
        from retrorecomp.i18n import tr
        from retrorecomp.languages import LANGUAGES
        owner = gui.Application.__new__(gui.Application)
        owner.messages = Queue()
        def lines(base, summary=None, error=None, quiet=False):
            owner.log_published_base(base, summary, error, quiet)
            found = []
            while not owner.messages.empty():
                found.append(owner.messages.get_nowait())
            return found
        def log(base, **extra):
            return [item[1] for item in lines(base, **extra) if item[0] == 'log']
        received = {'version': 412, 'games': 3, 'asked': 5, 'note': None, 'error': None, 'offline': False, 'update': None}
        for code in LANGUAGES:
            owner.language = code
            owner.base_notice_given = False
            text = log(received)
            self.assertEqual(text, [tr('shared_base_received', code, version=412, games=3)])
            self.assertIn('412', text[0])
            self.assertIn('3', text[0])
            if code != 'en':
                self.assertNotEqual(text[0], tr('shared_base_received', 'en', version=412, games=3), code)
            self.assertEqual(len(log({**received, 'games': 0})), 1)
            self.assertEqual(log({**received, 'games': 0}, summary={'roms': 0}), [], 'the sync of the account says it')
            self.assertEqual(len(log({'version': 4, 'games': 0, 'asked': 1, 'note': 'format', 'format': 2, 'error': None})), 1)
            problem = log({'version': 4, 'games': 0, 'asked': 1, 'note': None, 'error': online.ServiceError(200, 'verify'),
                           'offline': False})
            self.assertEqual(problem, [tr('shared_base_unavailable', code, error=tr('base_error_verify', code))])
            self.assertEqual(log({'version': None, 'games': 0, 'asked': 1, 'note': 'no_base', 'error': None}), [])
            # An update that came in is said, with its size.
            updated = {**received, 'games': 0, 'update': {'source': 'delta', 'version': 412, 'previous': 410,
                                                          'downloaded_bytes': 3 * 1048576, 'error': None}}
            self.assertEqual(log(updated)[0], tr('base_updated', code, version=412, size='3.0 MiB'))
            # No connection: the local base is said to be used, and with none, the full discovery,
            # in the log and as one notice per session.
            offline = {'version': 412, 'games': 0, 'asked': 1, 'note': None, 'offline': True,
                       'error': online.ServiceConnectionError(), 'update': None}
            self.assertEqual(log(offline), [tr('base_local_offline', code, version=412)])
            nothing = {'version': None, 'games': 0, 'asked': 1, 'note': None, 'offline': True,
                       'error': online.ServiceConnectionError(), 'update': None}
            first = lines(nothing)
            self.assertEqual(first, [('log', tr('base_none', code)), ('notice', tr('base_none', code))])
            self.assertEqual(lines(nothing), [('log', tr('base_none', code))], 'the notice comes once')
            self.assertEqual(lines(nothing, quiet=True), [], 'a game asked for in the middle of a batch says nothing')
            if code != 'en':
                self.assertNotEqual(tr('base_none', code), tr('base_none', 'en'))
        self.assertEqual(lines(None), [])

    def test_the_knowledge_menu_item_reports_in_every_language(self):
        from retrorecomp import gui
        from retrorecomp.i18n import tr
        from retrorecomp.languages import LANGUAGES
        owner = gui.Application.__new__(gui.Application)
        for code in LANGUAGES:
            owner.language = code
            done = {'version': 9, 'previous': 7, 'downloaded_bytes': 2048, 'source': 'delta', 'error': None}
            self.assertEqual(owner.base_update_line(done), tr('base_updated', code, version=9, size='2 KiB'))
            self.assertEqual(owner.base_update_line({**done, 'source': None, 'downloaded_bytes': 0}),
                             tr('base_up_to_date', code, version=9))
            for failure, phrase in (('offline', 'online_unreachable'), ('verify', 'base_error_verify'),
                                    ('no_base', 'base_error_nobase'), ('no_path', 'base_error_nopath'),
                                    ('format', 'base_error_format'), ('disk', 'base_error_disk'),
                                    ('unavailable', 'base_error_unavailable')):
                self.assertEqual(owner.base_update_line({**done, 'source': None, 'error': failure}),
                                 tr('base_update_failed', code, error=tr(phrase, code)), (code, failure))
            self.assertIn('service', owner.base_update_line({**done, 'source': None, 'error': 'service'}))
            for key in ('knowledge_sync', 'knowledge_sync_signin'):
                self.assertNotEqual(tr(key, code), '')
                if code != 'en':
                    self.assertNotEqual(tr(key, code), tr(key, 'en'), (code, key))

    def test_sync_updates_the_base_then_sends_once_signed_in(self):
        # One Knowledge entry both ways: the base update chains the send of this
        # account's discoveries; signed out (or offline) it stops after the base.
        from retrorecomp import gui
        from retrorecomp.i18n import tr
        owner = gui.Application.__new__(gui.Application)
        owner.language, owner.compiled_view, owner.closing_send = 'en', None, False
        owner.busy, owner.manual_sending, owner.messages = True, False, __import__('queue').Queue()
        owner.set_controls = lambda enabled: None
        reports, collected_kinds = [], []
        owner.knowledge_report = reports.append
        owner.collect_discoveries = collected_kinds.append
        done = {'version': 9, 'previous': 7, 'downloaded_bytes': 2048, 'source': 'delta', 'error': None}
        line = owner.base_update_line(done)
        owner.syncing, owner.sync_line = True, ''
        with patch.object(online, 'account', return_value=None):
            owner.knowledge_done(('base_updated', done), None)
        self.assertEqual(reports, [line + '\n\n' + tr('knowledge_sync_signin', 'en')])
        self.assertEqual(collected_kinds, [])
        reports.clear()
        owner.syncing = True
        offline = {**done, 'source': None, 'error': 'offline'}
        with patch.object(online, 'account', return_value={'token': 't'}):
            owner.knowledge_done(('base_updated', offline), None)
        self.assertEqual(reports, [owner.base_update_line(offline)])
        self.assertEqual(collected_kinds, [], 'offline, the send is not tried')
        reports.clear()
        owner.syncing = True
        with patch.object(online, 'account', return_value={'token': 't'}):
            owner.knowledge_done(('base_updated', done), None)
        self.assertEqual((reports, collected_kinds, owner.sync_line, owner.syncing),
                         ([], ['send_collect'], line, False))
        # Nothing new to send: one notice with both results, then the line is spent.
        with patch.object(online, 'pending', return_value={'games': 0}):
            owner.knowledge_done(('send_collect', {}), None)
        self.assertEqual(reports, [line + '\n\n' + tr('knowledge_send_none', 'en')])
        self.assertEqual(owner.sync_line, '')
        # The plain base update (the startup choice) does not send.
        reports.clear()
        owner.knowledge_done(('base_updated', done), None)
        self.assertEqual((reports, collected_kinds), ([line], ['send_collect']))


if __name__ == '__main__':
    unittest.main()
